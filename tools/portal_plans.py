"""Search plans for job portals, discovery yield and source productivity (21/10/2026).

Read-only views for the agent and the interface. Portal plans are ready-made
search addresses built from one search profile; their parameters were checked
on each portal on 21/10/2026. Filters a portal does not accept in its address
are listed for the agent to set by hand. Nothing here searches, scores or
promotes offers.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from state_support import instant

LINKEDIN_GEO = {'españa': '105646813', 'espana': '105646813', 'spain': '105646813'}
SPAIN = re.compile(r'espa(?:ñ|n)a|spain', re.I)
WINDOWS = {'day': {'label': 'últimas 24 horas', 'linkedin': 'r86400', 'infojobs': '_24_HOURS', 'indeed': '1', 'tecnoempleo': True},
           'week': {'label': 'últimos 7 días', 'linkedin': 'r604800', 'infojobs': '_7_DAYS', 'indeed': '7', 'tecnoempleo': False},
           'month': {'label': 'últimos 15 días', 'linkedin': 'r2592000', 'infojobs': '_15_DAYS', 'indeed': '14', 'tecnoempleo': False}}
PORTAL_NAMES = {'linkedin': 'LinkedIn', 'infojobs': 'InfoJobs', 'indeed': 'Indeed', 'tecnoempleo': 'Tecnoempleo'}
SCHEDULES = {'morning': 'solo de mañana', 'afternoon': 'solo de tarde', 'continuous': 'jornada continua'}
# Fragments that describe the search instead of naming a role are not search terms.
GENERIC = re.compile(r'^(?:puestos?|roles?|perfiles?|cualquier|otros?|otras?|áreas?|horarios?|jornadas?|trabajos?|incluye|compatible|tareas?)\b', re.I)


def search_terms(search):
    """Short role names from targetRoles; prose and long sentences are left out."""
    terms = []
    for part in re.split(r'[,;\n.]|\s+(?:y|o|e|u|and|or)\s+', search.get('targetRoles') or ''):
        term = part.strip(' .:()')
        if term and not GENERIC.match(term) and len(term.split()) <= 6 and term.casefold() not in {t.casefold() for t in terms}:
            terms.append(term)
    if not terms:
        for part in re.split(r'[,;\n]', search.get('keywords') or ''):
            term = part.strip(' .')
            if term and len(term.split()) <= 4 and term.casefold() not in {t.casefold() for t in terms}:
                terms.append(term)
    return terms[:8]


def _done_discoveries(data, profile_id):
    found = []
    for request in data.get('app', {}).get('requests', []):
        basis = request.get('round') or {}
        if (request.get('type') == 'discovery' and request.get('status') == 'done' and
                (basis.get('searchProfileId', request.get('searchProfileId')) == profile_id)):
            at = instant(request.get('activityAt') or request.get('updatedAt'))
            if at:
                found.append((at, request))
    return sorted(found, key=lambda item: item[0])


def discovery_yield(data, profile_id, now=None):
    """Consecutive finished searches of this profile that added no offer."""
    now = now or datetime.now(timezone.utc)
    done = _done_discoveries(data, profile_id)
    streak = []
    for at, request in reversed(done):
        if (request.get('activityResult') or {}).get('newOfferCount') != 0:
            break
        streak.append((at, request))
    last = done[-1][0] if done else None
    scanned = [instant(h.get('checkedAtUtc')) for _, r in streak[:1] for h in (r.get('activityResult') or {}).get('health', [])]
    scanned = max((at for at in scanned if at), default=None)
    exhausted = len(streak) >= 2
    result = {'lastSearchAt': last.isoformat(timespec='seconds') if last else None,
              'searchesWithoutNewOffers': len(streak),
              'sinceAt': streak[-1][0].isoformat(timespec='seconds') if streak else None,
              'sourcesExhausted': exhausted,
              'skipScanner': bool(exhausted and scanned and now - scanned < timedelta(hours=24))}
    if exhausted:
        result['message'] = (f'Las últimas {len(streak)} búsquedas de este perfil no añadieron ofertas nuevas. '
                             'No repitas el captador ni la misma búsqueda complementaria'
                             + (' (las webs configuradas se revisaron hace menos de 24 horas)' if result['skipScanner'] else '')
                             + ': recorre portalPlans con su ventana de fechas y registra cada portal con ui-source-review.')
    return result


def _window(data, profile_id, now=None):
    now = now or datetime.now(timezone.utc)
    done = _done_discoveries(data, profile_id)
    if not done:
        return 'month'
    age = now - done[-1][0]
    return 'day' if age <= timedelta(days=1) else 'week' if age <= timedelta(days=7) else 'month'


def _chunks(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]


def plans(data, profile_id=None):
    """Portal searches for one profile, newest-first, within the dates since the last search."""
    import app_context
    import search_profiles
    from offer_minimums import categories
    from personalization import context
    profile_id = profile_id or (data.get('_discoverySnapshot') or {}).get('searchProfileId') or search_profiles.default_id(data)
    search = context(data, None if data.get('_discoverySnapshot') else profile_id)
    criteria = app_context.criteria(data, None if data.get('_discoverySnapshot') else profile_id)
    if (search.get('sourceUrls') or '').strip():
        return {'available': False, 'reason': 'El perfil limita la búsqueda a sus webs exclusivas; los portales quedan fuera.', 'plans': []}
    terms = search_terms(search)
    if not terms:
        return {'available': False, 'reason': 'Faltan puestos breves en Lo que busco para construir búsquedas en portales.', 'plans': []}
    window = _window(data, profile_id)
    dates = WINDOWS[window]
    place = ' '.join(filter(None, (criteria.get('location'), search.get('regions')))).strip()
    spain = not place or bool(SPAIN.search(place))
    remote = 'remote' in categories(search.get('workMode') or criteria.get('location'), 'mode', preference=True)
    schedule = SCHEDULES.get(search.get('requiredSchedule'))
    check = ['Lee modalidad, contrato, salario y ubicación en cada anuncio antes de promoverlo.']
    if schedule:
        check.append('Horario obligatorio: ' + schedule + '; promueve solo anuncios que lo confirmen.')
    items = []

    def add(portal, query, url, applied, manual):
        items.append({'portal': portal, 'name': PORTAL_NAMES[portal], 'query': query, 'url': url,
                      'filtersApplied': applied, 'filtersToSet': manual + check})

    geo = LINKEDIN_GEO.get(place.casefold()) if place else LINKEDIN_GEO['españa']
    for group in _chunks(terms, 4):
        query = ' OR '.join(f'"{term}"' for term in group)
        params = {'keywords': query, **({'geoId': geo} if geo else {'location': place}), 'f_TPR': dates['linkedin']}
        applied = ['palabras clave', 'fecha: ' + dates['label'], 'España' if geo else 'ubicación escrita']
        if remote:
            params['f_WT'] = '2'
            applied.append('en remoto')
        add('linkedin', query, 'https://www.linkedin.com/jobs/search/?' + urlencode(params), applied,
            [] if geo else ['Comprueba que la ubicación que muestra LinkedIn es ' + place + '.'])
    for group in _chunks(terms, 4):
        query = ' OR '.join(f'"{term}"' for term in group)
        host = 'es.indeed.com' if spain else 'www.indeed.com'
        location = 'Teletrabajo' if remote and spain else place or ('España' if spain else '')
        add('indeed', query, f'https://{host}/jobs?' + urlencode({'q': query, 'l': location, 'fromage': dates['indeed']}),
            ['palabras clave', 'fecha: ' + dates['label'], 'teletrabajo' if remote and spain else 'ubicación'], [])
    if spain:
        for term in terms[:6]:
            params = {'keyword': term, 'sinceDate': dates['infojobs']}
            if remote:
                params['teleworkingIds'] = '2'
            add('infojobs', term, 'https://www.infojobs.net/jobsearch/search-results/list.xhtml?' + urlencode(params),
                ['palabra clave', 'fecha: ' + dates['label']] + (['solo teletrabajo'] if remote else []),
                ['En Jornada, marca la que encaje con tu horario si aparece.'] if schedule else [])
        for term in terms[:6]:
            params = {'te': term, **({'ult_24h': '1'} if dates['tecnoempleo'] else {})}
            add('tecnoempleo', term, 'https://www.tecnoempleo.com/ofertas-trabajo/?' + urlencode(params),
                ['palabra clave'] + (['fecha: últimas 24 horas'] if dates['tecnoempleo'] else []),
                (['Marca Teletrabajo en los filtros de la página.'] if remote else []) +
                ([] if dates['tecnoempleo'] else ['Ordena por fecha y revisa solo lo publicado en los ' + dates['label'] + '.']))
    preferred = [p for p in (search.get('platforms') or '').split(',') if p]
    items.sort(key=lambda item: (item['portal'] not in preferred, list(PORTAL_NAMES).index(item['portal'])))
    return {'available': True, 'searchProfileId': profile_id, 'window': window, 'windowLabel': dates['label'],
            'terms': terms, 'remote': remote, 'plans': items,
            'howTo': 'Abre cada enlace con tu sesión, revisa los anuncios nuevos, promueve los que cumplan los mínimos y '
                     'registra cada portal revisado con ui-source-review (sourceUrl = url del plan, scope y resultado reales).'}


def source_stats(data):
    """Productivity of each configured company board, from its own recorded results."""
    import personalization
    try:
        configured = personalization.public_sources(data, include_disabled=True)
    except (OSError, ValueError, TypeError, KeyError):
        return []
    disabled = data.get('app', {}).get('disabledSources', {})
    rows = data['sheets']['Oportunidades']
    archives = data.get('app', {}).get('offerArchives', {})
    sent = {e['opportunityId'] for e in data['events'] if e['type'] == 'sent'}
    result = []
    for source in configured:
        key = source['id']
        offers = [r['ID'] for r in rows if r.get('Fuente') == key]
        captured = sum(1 for e in data['sheets'].get('Entradas', []) if e.get('Fuente') == key)
        discarded = sum(1 for k in offers if k in archives and archives[k].get('source') != 'minimums' and k not in sent)
        minimums = sum(1 for k in offers if (archives.get(k) or {}).get('source') == 'minimums')
        applied = sum(1 for k in offers if k in sent)
        # Low yield: many offers, almost none sent and most discarded by you; or many listings and no offer.
        low = (len(offers) >= 10 and applied <= max(1, 0.05 * len(offers)) and discarded >= 0.7 * len(offers)) or (captured >= 20 and not offers)
        result.append({'id': key, 'company': source.get('company'), 'captured': captured, 'offers': len(offers),
                       'sent': applied, 'discardedByYou': discarded, 'discardedByMinimums': minimums,
                       'lowYield': low, 'enabled': key not in disabled,
                       'disabledAt': (disabled.get(key) or {}).get('at')})
    return result


def toggle(data, operation, workflow):
    """Stop or resume checking one configured board; history and offers stay as they are."""
    key, enabled = operation.get('sourceId'), operation.get('enabled')
    if type(enabled) is not bool:
        raise ValueError('Indica si la web vuelve a revisarse (true) o deja de revisarse (false)')
    import personalization
    if not any(s['id'] == key for s in personalization.public_sources(data, include_disabled=True)):
        raise ValueError('Esa web no está entre las fuentes configuradas')
    disabled = workflow.state(data).setdefault('disabledSources', {})
    workflow.expect(key not in disabled, operation.get('expected'))
    if enabled == (key not in disabled):
        return
    actor = operation.get('actor', 'Usuario')
    if enabled:
        disabled.pop(key)
    else:
        disabled[key] = {'at': workflow.now(), 'actor': actor}
    company = next(s['company'] for s in personalization.public_sources(data, include_disabled=True) if s['id'] == key)
    workflow.record(data, ('Web de nuevo en las búsquedas: ' if enabled else 'Web retirada de las búsquedas: ') + company,
                    actor=actor, detail='Las ofertas y el historial de esta web se conservan.')
