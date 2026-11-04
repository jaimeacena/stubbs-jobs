"""Search plans for job portals, discovery yield and source productivity (21/10/2026).

Read-only views for the agent and the interface. Portal plans are ready-made
search addresses built from one search profile. Their filters must be checked
in the live portal before claiming coverage. Nothing here searches, scores or
promotes offers.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit

from state_support import instant
from stubbs_jobs_core import digest

LINKEDIN_GEO = {'españa': '105646813', 'espana': '105646813', 'spain': '105646813'}
SPAIN = re.compile(r'espa(?:ñ|n)a|spain', re.I)
WINDOWS = {'day': {'label': 'últimas 24 horas', 'linkedin': 'r86400', 'infojobs': '_24_HOURS', 'indeed': '1', 'tecnoempleo': True},
           'week': {'label': 'últimos 7 días', 'linkedin': 'r604800', 'infojobs': '_7_DAYS', 'indeed': '7', 'tecnoempleo': False},
           'month': {'label': 'últimos 15 días', 'linkedin': 'r2592000', 'infojobs': '_15_DAYS', 'indeed': '14', 'tecnoempleo': False}}
PORTAL_NAMES = {'linkedin': 'LinkedIn', 'infojobs': 'InfoJobs', 'indeed': 'Indeed', 'tecnoempleo': 'Tecnoempleo',
                'wellfound': 'Wellfound'}
# Main job portals by where they serve. «search» is a link verified on 04/11/2026 to return the
# query; the rest open the portal and the agent searches there. Only the first five get per-role plans.
MAIN_PORTALS = ('linkedin', 'indeed', 'infojobs', 'tecnoempleo', 'wellfound')
PORTALS = (
    {'id': 'linkedin', 'name': 'LinkedIn', 'url': 'https://www.linkedin.com/jobs/', 'hosts': ('linkedin.com',), 'regions': ('global',), 'account': 'apply'},
    {'id': 'indeed', 'name': 'Indeed', 'url': 'https://www.indeed.com/', 'hosts': ('indeed.com',), 'regions': ('global',), 'account': 'apply'},
    {'id': 'infojobs', 'name': 'InfoJobs', 'url': 'https://www.infojobs.net/', 'hosts': ('infojobs.net',), 'regions': ('es',), 'account': 'apply'},
    {'id': 'tecnoempleo', 'name': 'Tecnoempleo', 'url': 'https://www.tecnoempleo.com/', 'hosts': ('tecnoempleo.com',), 'regions': ('es',), 'account': 'apply', 'sector': 'Tecnología'},
    {'id': 'wellfound', 'name': 'Wellfound', 'url': 'https://wellfound.com/jobs', 'hosts': ('wellfound.com',), 'regions': ('remote',), 'account': 'search', 'sector': 'Startups'},
    {'id': 'glassdoor', 'name': 'Glassdoor', 'url': 'https://www.glassdoor.com/Job/', 'hosts': ('glassdoor.com', 'glassdoor.es'), 'regions': ('global',), 'account': 'apply'},
    {'id': 'talent', 'name': 'Talent.com', 'url': 'https://www.talent.com/', 'search': 'https://es.talent.com/jobs?k={q}', 'hosts': ('talent.com',), 'regions': ('global',), 'account': 'none'},
    {'id': 'jooble', 'name': 'Jooble', 'url': 'https://jooble.org/', 'hosts': ('jooble.org',), 'regions': ('global',), 'account': 'none'},
    {'id': 'infoempleo', 'name': 'Infoempleo', 'url': 'https://www.infoempleo.com/', 'hosts': ('infoempleo.com',), 'regions': ('es',), 'account': 'apply'},
    {'id': 'empleate', 'name': 'Empléate (SEPE)', 'url': 'https://www.empleate.gob.es/', 'hosts': ('empleate.gob.es',), 'regions': ('es',), 'account': 'apply'},
    {'id': 'manfred', 'name': 'Manfred', 'url': 'https://www.getmanfred.com/ofertas-empleo', 'hosts': ('getmanfred.com',), 'regions': ('es',), 'account': 'apply', 'sector': 'Tecnología'},
    {'id': 'eures', 'name': 'EURES', 'url': 'https://europa.eu/eures/portal/jv-se/home', 'hosts': ('europa.eu',), 'regions': ('eu',), 'account': 'none'},
    {'id': 'welcometothejungle', 'name': 'Welcome to the Jungle', 'url': 'https://www.welcometothejungle.com/', 'hosts': ('welcometothejungle.com',), 'regions': ('eu',), 'account': 'apply'},
    {'id': 'weworkremotely', 'name': 'We Work Remotely', 'url': 'https://weworkremotely.com/', 'search': 'https://weworkremotely.com/remote-jobs/search?term={q}', 'hosts': ('weworkremotely.com',), 'regions': ('remote',), 'account': 'none'},
    {'id': 'remotive', 'name': 'Remotive', 'url': 'https://remotive.com/', 'hosts': ('remotive.com',), 'regions': ('remote',), 'account': 'none'},
    {'id': 'remoteok', 'name': 'Remote OK', 'url': 'https://remoteok.com/', 'hosts': ('remoteok.com',), 'regions': ('remote',), 'account': 'none'},
    {'id': 'himalayas', 'name': 'Himalayas', 'url': 'https://himalayas.app/jobs', 'hosts': ('himalayas.app',), 'regions': ('remote',), 'account': 'none'},
    {'id': 'computrabajo', 'name': 'Computrabajo', 'url': 'https://www.computrabajo.com/', 'hosts': ('computrabajo.com',), 'regions': ('latam',), 'account': 'apply'},
    {'id': 'getonboard', 'name': 'Get on Board', 'url': 'https://www.getonbrd.com/jobs', 'hosts': ('getonbrd.com',), 'regions': ('latam',), 'account': 'apply', 'sector': 'Tecnología'},
    {'id': 'reed', 'name': 'Reed', 'url': 'https://www.reed.co.uk/', 'search': 'https://www.reed.co.uk/jobs/{slug}-jobs', 'hosts': ('reed.co.uk',), 'regions': ('uk',), 'account': 'apply'},
    {'id': 'totaljobs', 'name': 'Totaljobs', 'url': 'https://www.totaljobs.com/', 'search': 'https://www.totaljobs.com/jobs/{slug}', 'hosts': ('totaljobs.com',), 'regions': ('uk',), 'account': 'apply'},
    {'id': 'stepstone', 'name': 'StepStone', 'url': 'https://www.stepstone.de/', 'search': 'https://www.stepstone.de/work/{slug}', 'hosts': ('stepstone.de',), 'regions': ('de',), 'account': 'apply'},
    {'id': 'hellowork', 'name': 'Hellowork', 'url': 'https://www.hellowork.com/', 'search': 'https://www.hellowork.com/fr-fr/emploi/recherche.html?k={q}', 'hosts': ('hellowork.com',), 'regions': ('fr',), 'account': 'apply'},
    {'id': 'apec', 'name': 'APEC', 'url': 'https://www.apec.fr/', 'hosts': ('apec.fr',), 'regions': ('fr',), 'account': 'apply'},
    {'id': 'net-empregos', 'name': 'Net-Empregos', 'url': 'https://www.net-empregos.com/', 'hosts': ('net-empregos.com',), 'regions': ('pt',), 'account': 'apply'},
    {'id': 'ziprecruiter', 'name': 'ZipRecruiter', 'url': 'https://www.ziprecruiter.com/', 'hosts': ('ziprecruiter.com',), 'regions': ('us',), 'account': 'apply'},
    {'id': 'seek', 'name': 'SEEK', 'url': 'https://www.seek.com.au/', 'hosts': ('seek.com.au',), 'regions': ('au',), 'account': 'apply'},
    {'id': 'naukri', 'name': 'Naukri', 'url': 'https://www.naukri.com/', 'search': 'https://www.naukri.com/{slug}-jobs', 'hosts': ('naukri.com',), 'regions': ('in',), 'account': 'apply'},
)
PORTAL_IDS = {portal['id'] for portal in PORTALS}
REGION_WORDS = (('es', r'espa(?:ñ|n)a|spain|madrid|barcelona|c[aá]diz|sevilla|m[aá]laga|valencia'), ('uk', r'reino unido|united kingdom|\buk\b|london|londres'),
                ('de', r'alemania|germany|deutschland|berl[ií]n|m[uú]nich'), ('fr', r'francia|france|par[ií]s'), ('pt', r'portugal|lisboa|lisbon|oporto'),
                ('us', r'estados unidos|united states|\busa\b|\bee\.?uu'), ('au', r'australia'), ('in', r'\bindia\b'),
                ('latam', r'm[eé]xico|colombia|argentina|chile|per[uú]|latam|latinoam[eé]rica|ecuador|uruguay'),
                ('eu', r'europa|europe|\bue\b|\beu\b|italia|italy|irlanda|ireland|pa[ií]ses bajos|netherlands|b[eé]lgica|polonia'))
EU_REGIONS = {'es', 'de', 'fr', 'pt', 'eu'}
ACCESS_DAYS = 30
SCHEDULES = {'morning': 'solo de mañana', 'afternoon': 'solo de tarde', 'continuous': 'jornada continua'}
# Fragments that describe the search instead of naming a role are not search terms.
GENERIC = re.compile(r'^(?:puestos?|roles?|perfiles?|cualquier|otros?|otras?|áreas?|horarios?|jornadas?|trabajos?|incluye|compatible|tareas?)\b', re.I)


def search_terms(search):
    """Short role names from targetRoles; prose and long sentences are left out."""
    terms = []
    for part in re.split(r'[,;\n.]|\s+(?:y|o|e|u|and|or)\s+', search.get('targetRoles') or ''):
        term = part.strip(' .:()')
        term = re.sub(r'^incluye\s+', '', term, flags=re.I)
        if term and not GENERIC.match(term) and len(term.split()) <= 6 and term.casefold() not in {t.casefold() for t in terms}:
            terms.append(term)
    if not terms:
        for part in re.split(r'[,;\n]', search.get('keywords') or ''):
            term = part.strip(' .')
            if term and len(term.split()) <= 4 and term.casefold() not in {t.casefold() for t in terms}:
                terms.append(term)
    return terms


def _search_key(data, profile_id):
    import search_profiles
    basis = data.get('_discoverySnapshot') or search_profiles.snapshot(data, profile_id)
    return digest({key: value for key, value in basis.items() if key not in ('searchProfileName', 'profileRevision')})


def _done_discoveries(data, profile_id, search_key):
    found = []
    for request in data.get('app', {}).get('requests', []):
        basis = request.get('round') or {}
        prior_key = request.get('searchKey') or (digest({key: value for key, value in basis.items()
                                                       if key not in ('searchProfileName', 'profileRevision')})
                                                if 'searchContext' in basis and 'criteria' in basis else None)
        if (request.get('type') == 'discovery' and request.get('status') == 'done' and
                basis.get('searchProfileId', request.get('searchProfileId')) == profile_id and
                prior_key == search_key):
            at = instant(request.get('activityAt') or request.get('updatedAt'))
            if at:
                found.append((at, request))
    return sorted(found, key=lambda item: item[0])


def _complete_scanner(data, request):
    """A zero is meaningful only if every currently configured board completed."""
    import personalization
    import search_profiles
    try:
        expected={item['id'] for item in personalization.public_sources(search_profiles.discovery_data(data,request))}
    except (OSError,ValueError,TypeError,KeyError):
        return False
    result=request.get('activityResult') or {}
    checks={item.get('sourceId'):item for item in result.get('scanChecks',[]) if isinstance(item,dict)}
    return bool(expected) and all((checks.get(identifier) or {}).get('status')=='ok' for identifier in expected)


def _plan_identity(url):
    """The date window changes the URL, but not which role and portal were checked."""
    parsed=urlsplit(url)
    query=tuple(sorted((key,value) for key,value in parse_qsl(parsed.query)
                       if key not in ('f_TPR','fromage','sinceDate','ult_24h')))
    return parsed.hostname,parsed.path.rstrip('/'),query


def _complete_portals(data, request, profile_id):
    import search_profiles
    basis=request.get('round') or {}
    if 'searchContext' not in basis or 'criteria' not in basis:
        return False
    scoped=search_profiles.discovery_data(data,request)
    planned=plans(scoped,profile_id,_window_override='month')
    if not planned['available'] or not planned['plans']:
        return False
    expected={_plan_identity(item['url']) for item in planned['plans']}
    reviewed={_plan_identity(item['sourceUrl']) for item in (request.get('activityResult') or {}).get('manualReviews',[])
              if item.get('outcome')=='reviewed' and item.get('sourceUrl')}
    return expected.issubset(reviewed)


def discovery_yield(data, profile_id, now=None):
    """Consecutive complete company-board scans with exact criteria and no new offer."""
    now = now or datetime.now(timezone.utc)
    done = _done_discoveries(data, profile_id, _search_key(data, profile_id))
    streak = []
    for at, request in reversed(done):
        result=request.get('activityResult') or {}
        if not _complete_scanner(data, request) or result.get('newOfferCount') != 0:
            break
        streak.append((at, request))
    last = done[-1][0] if done else None
    scanned = [instant(h.get('checkedAtUtc')) for _, r in streak[:1] for h in (r.get('activityResult') or {}).get('scanChecks', [])]
    scanned = max((at for at in scanned if at), default=None)
    exhausted = len(streak) >= 2
    result = {'lastSearchAt': last.isoformat(timespec='seconds') if last else None,
              'searchesWithoutNewOffers': len(streak),
              'lastScannerComplete': _complete_scanner(data, done[-1][1]) if done else False,
              'sinceAt': streak[-1][0].isoformat(timespec='seconds') if streak else None,
              'sourcesExhausted': exhausted,
              'skipScanner': bool(exhausted and scanned and now - scanned < timedelta(hours=24))}
    if exhausted:
        result['message'] = (f'Las últimas {len(streak)} revisiones completas de las webs de empresa de este perfil no añadieron ofertas nuevas. '
                             'No repitas el captador sin información nueva'
                             + (' (las webs configuradas se revisaron hace menos de 24 horas)' if result['skipScanner'] else '')
                             + ': recorre portalPlans con su ventana de fechas y registra cada portal con ui-source-review.')
    return result


def _window(data, profile_id, now=None):
    now = now or datetime.now(timezone.utc)
    done = _done_discoveries(data, profile_id, _search_key(data, profile_id))
    complete=next((at for at,request in reversed(done) if _complete_portals(data,request,profile_id)),None)
    if not complete:
        return 'month'
    age = now - complete
    return 'day' if age <= timedelta(days=1) else 'week' if age <= timedelta(days=7) else 'month'


def plans(data, profile_id=None, _window_override=None):
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
    window = _window_override or _window(data, profile_id)
    dates = WINDOWS[window]
    place = ' '.join(filter(None, (criteria.get('location'), search.get('regions')))).strip()
    spain = not place or bool(SPAIN.search(place))
    remote = 'remote' in categories(search.get('workMode') or criteria.get('location'), 'mode', preference=True)
    schedule = SCHEDULES.get(search.get('requiredSchedule'))
    check = ['Comprueba en la página que se aplicaron palabras, ubicación, remoto y fecha; el enlace por sí solo no lo acredita.',
             'Lee modalidad, contrato, salario y ubicación en cada anuncio antes de promoverlo.']
    if schedule:
        check.append('Horario obligatorio: ' + schedule + '; promueve solo anuncios que lo confirmen.')
    items = []

    def add(portal, query, url, applied, manual):
        items.append({'portal': portal, 'name': PORTAL_NAMES[portal], 'query': query, 'url': url,
                      'filtersApplied': applied, 'filtersToSet': manual + check})

    geo = LINKEDIN_GEO.get(place.casefold()) if place else LINKEDIN_GEO['españa']
    for query in terms:
        params = {'keywords': query, **({'geoId': geo} if geo else {'location': place}), 'f_TPR': dates['linkedin']}
        applied = ['palabras clave', 'fecha: ' + dates['label'], 'España' if geo else 'ubicación escrita']
        if remote:
            params['f_WT'] = '2'
            applied.append('en remoto')
        add('linkedin', query, 'https://www.linkedin.com/jobs/search/?' + urlencode(params), applied,
            [] if geo else ['Comprueba que la ubicación que muestra LinkedIn es ' + place + '.'])
    for term in terms:
        query = term
        host = 'es.indeed.com' if spain else 'www.indeed.com'
        location = 'Teletrabajo' if remote and spain else place or ('España' if spain else '')
        add('indeed', query, f'https://{host}/jobs?' + urlencode({'q': query, 'l': location, 'fromage': dates['indeed']}),
            ['palabras clave', 'fecha: ' + dates['label'], 'teletrabajo' if remote and spain else 'ubicación'], [])
    if spain:
        for term in terms:
            params = {'keyword': term, 'sinceDate': dates['infojobs']}
            if remote:
                params['teleworkingIds'] = '2'
            add('infojobs', term, 'https://www.infojobs.net/jobsearch/search-results/list.xhtml?' + urlencode(params),
                ['palabra clave', 'fecha: ' + dates['label']] + (['solo teletrabajo'] if remote else []),
                ['En Jornada, marca la que encaje con tu horario si aparece.'] if schedule else [])
        for term in terms:
            params = {'te': term, **({'ult_24h': '1'} if dates['tecnoempleo'] else {})}
            add('tecnoempleo', term, 'https://www.tecnoempleo.com/ofertas-trabajo/?' + urlencode(params),
                ['palabra clave'] + (['fecha: últimas 24 horas'] if dates['tecnoempleo'] else []),
                (['Marca Teletrabajo en los filtros de la página.'] if remote else []) +
                ([] if dates['tecnoempleo'] else ['Ordena por fecha y revisa solo lo publicado en los ' + dates['label'] + '.']))
    if remote:
        add('wellfound','; '.join(terms),'https://wellfound.com/jobs',[],
            ['Inicia sesión y busca los puestos equivalentes del perfil por separado.',
             'Marca Only remote y comprueba en cada anuncio Hires Remotely From: Spain.',
             'Si filtras por sueldo, incluye también anuncios sin salario publicado.'])
    excluded = excluded_portals(search)
    items = [item for item in items if item['portal'] not in excluded]
    preferred = [p for p in (search.get('platforms') or '').split(',') if p]
    items.sort(key=lambda item: (item['portal'] not in preferred, list(PORTAL_NAMES).index(item['portal'])))
    return {'available': True, 'searchProfileId': profile_id, 'window': window, 'windowLabel': dates['label'],
            'terms': terms, 'remote': remote, 'plans': items, 'morePortals': more_portals(search, criteria, terms),
            'howTo': 'Abre cada enlace con tu sesión y comprueba que el portal aplicó sus filtros. Revisa los anuncios nuevos, promueve solo los que cumplan los mínimos y '
                     'registra cada portal revisado con ui-source-review (sourceUrl = url del plan, scope y resultado reales).'}


def excluded_portals(search):
    return {item for item in str(search.get('excludedPortals') or '').split(',') if item}


def _regions(search, criteria, remote=None):
    place = ' '.join(filter(None, (str(criteria.get('location') or ''), str(search.get('regions') or ''), str(search.get('onsiteLocations') or ''))))
    found = {name for name, pattern in REGION_WORDS if re.search(pattern, place, re.I)} or ({'es'} if not place.strip() else set())
    if found & EU_REGIONS:
        found.add('eu')
    if remote is None:
        from offer_minimums import categories
        remote = 'remote' in categories(search.get('workMode') or criteria.get('location'), 'mode', preference=True)
    return found | {'global'} | ({'remote'} if remote else set())


def relevant_portals(search, criteria):
    regions = _regions(search, criteria)
    return [portal for portal in PORTALS if regions & set(portal['regions'])]


def more_portals(search, criteria, terms):
    """Other relevant portals, without per-role plans: useful when the main ones run short."""
    from urllib.parse import quote_plus
    excluded, result = excluded_portals(search), []
    for portal in relevant_portals(search, criteria):
        if portal['id'] in MAIN_PORTALS or portal['id'] in excluded:
            continue
        links = []
        if portal.get('search'):
            links = [portal['search'].format(q=quote_plus(term), slug=re.sub(r'[^a-z0-9]+', '-', term.casefold()).strip('-')) for term in terms]
        result.append({'portal': portal['id'], 'name': portal['name'], 'url': portal['url'], 'searchLinks': links, 'account': portal['account'],
                       'howTo': 'Busca los puestos del perfil y comprueba ubicación, modalidad y fecha.' if not links else 'Abre cada enlace y comprueba ubicación, modalidad y fecha.'})
    return result


def _host(url):
    return (urlsplit(str(url or '')).hostname or '').casefold().removeprefix('www.')


def _portal_of(host):
    return next((portal['id'] for portal in PORTALS if any(host == name or host.endswith('.'+name) for name in portal['hosts'])), None)


def where_view(data, profile_id=None):
    """Where one search looks and where applications went: one plain map for the person."""
    import app_context
    import personalization
    search, criteria = personalization.context(data, profile_id), app_context.criteria(data, profile_id)
    packages = {package['id']: package for package in data.get('app', {}).get('packages', [])}
    rows = {row['ID']: row for row in data['sheets']['Oportunidades']}
    found, sent, other = {}, {}, {}
    for row in rows.values():
        key = _portal_of(_host(row.get('URL original')))
        if key:
            found[key] = found.get(key, 0)+1
    for event in data.get('events', []):
        if event.get('type') != 'sent':
            continue
        payload = (packages.get(event.get('packageId')) or {}).get('payload') or {}
        row = rows.get(event.get('opportunityId')) or {}
        host = _host(payload.get('recipient')) or _host(row.get('URL original'))
        key = _portal_of(host)
        if key:
            sent[key] = sent.get(key, 0)+1
        elif host:
            other[host] = other.get(host, 0)+1
    access = data.get('app', {}).get('portalAccess', {})
    excluded = excluded_portals(search)
    now = datetime.now(timezone.utc)
    relevant = relevant_portals(search, criteria)
    shown = relevant+[portal for portal in PORTALS if portal not in relevant and (found.get(portal['id']) or sent.get(portal['id']))]
    portals = []
    for portal in shown:
        record = access.get(portal['id']) or {}
        checked = instant(record.get('checkedAt'))
        fresh = bool(checked and now-checked <= timedelta(days=ACCESS_DAYS))
        session = record.get('status') if fresh else None
        portals.append({'id': portal['id'], 'name': portal['name'], 'url': portal['url'], 'sector': portal.get('sector'), 'main': portal['id'] in MAIN_PORTALS,
                        'active': portal['id'] not in excluded and portal in relevant, 'relevant': portal in relevant, 'account': portal['account'], 'session': session,
                        'found': found.get(portal['id'], 0), 'sent': sent.get(portal['id'], 0)})
    exclusive = [line.strip() for line in str(search.get('sourceUrls') or '').splitlines() if line.strip()]
    return {'exclusive': bool(exclusive), 'portals': portals, 'totalSent': sum(sent.values())+sum(other.values()),
            'sentOnCompanyWebs': sum(other.values()), 'otherHosts': sorted(other.items(), key=lambda item: (-item[1], item[0]))}


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
        result.append({'id': key, 'company': source.get('company'), 'url': source.get('url'), 'captured': captured, 'offers': len(offers),
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
