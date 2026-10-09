"""Hard conditions decide eligibility; missing facts and technical fit do not.

Only recorded condition facts are used. Never parse prose, job titles, priority,
CV contents or an assessment into a rejection or a sending permission.
"""
import json
import math
import re
import unicodedata
import view_cache
from state_support import instant, excel_date


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '').lower())
                   if not unicodedata.combining(c))


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def categories(value, kind, preference=False):
    """Read categorical fields, including qualifiers, without mining other prose.

    Alternatives remain alternatives. Negated or merely preferred categories do
    not establish an exclusive requirement. Hybrid schedules are one category,
    even when their detail mentions remote days.
    """
    text = normalized(value).strip()
    if not text or re.search(r'sin preferencia|indiferente|por confirmar|sin concretar|no publicado', text):
        return set()
    if preference and re.search(r'prefer(?:ible|entemente|encia)|deseable|idealmente', text):
        return set()
    patterns = ({'remote': r'\b(?:remot[oa]|remote|teletrabajo)\b',
                 'hybrid': r'\b(?:hibrid[oa]|hybrid)\b',
                 'onsite': r'\b(?:presencial|on[- ]?site|onsite)\b'} if kind == 'mode' else
                {'permanent': r'\b(?:indefinid[oa]|permanent|indefinite)\b',
                 'temporary': r'\b(?:temporal|temporary|fixed[- ]term|duracion determinada)\b',
                 'self_employed': r'\b(?:freelance|autonom[oa]|mercantil|self[- ]employed|contractor)\b',
                 'internship': r'\b(?:practicas|internship|beca)\b'})
    matches = sorted((match.start(), match.end(), key) for key, pattern in patterns.items()
                     for match in re.finditer(pattern, text))
    if not matches:
        return set()
    # A negative label does not identify the positive category that replaces it.
    if re.search(r'\b(?:no|excepto|excluye|sin)\s+(?:100\s*%\s*)?(?:remot|presencial|hibrid|indefinid|temporal|freelance|mercantil)', text):
        return set()
    # Read the current label and only the alternatives connected to it. A
    # separator inside a schedule or a later sentence is not another option.
    previous = matches[0]
    options = {previous[2]}
    for index, current in enumerate(matches[1:], 1):
        gap = text[previous[1]:current[0]]
        qualifier = re.sub(r'\([^()]*\)', '', gap)
        if re.search(r'[()\n;:.!?]', qualifier):
            break
        if kind == 'mode' and re.search(r'\b(?:dias?|semanas?|horas?|turnos?)\b', gap):
            break
        if current[2] == previous[2]:
            previous = current
            continue
        connector = re.search(r'(?:\b(?:o|or)\b|[/|])\s*'
                              r'(?:(?:modalidad|contrato|trabajo|full|fully|100\s*%)\s+)*$', qualifier)
        # A plain list ("Remoto, Híbrido y Presencial") enumerates alternatives.
        # Commas and "y/and/e/&" only count when nothing else sits between the
        # two labels, so descriptive prose after a comma is still not an option.
        connector = connector or re.fullmatch(
            r'[\s,]*(?:(?:y|e|and|&)\b\s*)?(?:(?:modalidad|contrato|trabajo|full|fully|100\s*%)\s+)*', qualifier)
        end = matches[index+1][0] if index+1 < len(matches) else len(text)
        following = text[current[1]:end].strip(' ,:—-(')
        future = re.match(r'(?:al (?:finalizar|terminar|acabar)|tras\b|despues\b|after\b|'
                          r'en el futuro\b|mas adelante\b)', following)
        if not connector or future:
            break
        options.add(current[2])
        previous = current
    return options


def places(value):
    """Names of the places where on-site or hybrid presence is acceptable.

    The person writes a plain list (commas, semicolons, lines, "o"/"y"); an
    empty list means no geographic restriction was configured.
    """
    parts = re.split(r'[\n;,/|]|\b(?:o|y|or|and)\b', normalized(value))
    return [part.strip(' .()') for part in parts if part.strip(' .()')]


def site_allowed(site, allowed):
    """One published site matches an accepted place when either names the other."""
    return any(place in site or (len(site) >= 4 and site in place) for place in allowed)


def presence_problem(row, search, modes):
    """Reason why a hybrid/on-site offer is outside the accepted places, or None.

    Only applies when presence is acceptable at all (the work-mode criterion
    lists hybrid or on-site), places were configured, and the offer is known to
    require presence with no remote alternative. The place is a recorded fact
    (field Ubicación); it is never mined from descriptions.
    """
    allowed = places(search.get('onsiteLocations'))
    published = categories(row.get('Modalidad'), 'mode')
    if (not allowed or 'remote' in published or not published & {'hybrid', 'onsite'}
            or not modes & {'hybrid', 'onsite'}):
        return None
    shown = ', '.join(part.strip() for part in re.split(r'[\n;,]', str(search.get('onsiteLocations'))) if part.strip())
    sites = [site.strip() for site in re.split(r'[\n;/|]', normalized(row.get('Ubicación'))) if site.strip()]
    if not sites:
        return 'El anuncio es híbrido o presencial y no consta su ubicación; solo aceptas presencia en: '+shown+'.'
    outside = [site for site in sites if not site_allowed(site, allowed)]
    if outside:
        return 'La presencia que exige el anuncio ('+str(row.get('Ubicación')).strip()+') queda fuera de tus zonas: '+shown+'.'
    return None


def evidence_times(data):
    """Recover precision only from an exact observation or unambiguous retained batch."""
    def build():
        from stubbs_jobs import CONDITIONS, excel_day
        operations = {}
        for batch in data.get('changes', []):
            for op in batch.get('operations', []):
                at = instant(op.get('at'))
                if op.get('kind') != 'evidence' or not at or op.get('condition') not in CONDITIONS:
                    continue
                signature = (op.get('id'), CONDITIONS[op['condition']], op.get('state'),
                             op.get('proof'), op.get('url'), excel_day(op['at']))
                operations.setdefault(signature, set()).add(at)
        result = {}
        for record in data['sheets'].get('Evidencias', []):
            at = instant(record.get('observedAt'))
            if at is None:
                signature = tuple(record.get(k) for k in
                                  ('ID oportunidad', 'Condición', 'Estado', 'Texto o motivo', 'Fuente', 'Comprobada'))
                candidates = operations.get(signature, set())
                if len(candidates) == 1:
                    at = next(iter(candidates))
            result[id(record)] = at
        return result
    return view_cache.memo(('evidence-times', id(data)), build)


def latest_evidence(data, row, condition):
    records = [e for e in data['sheets'].get('Evidencias', [])
               if e.get('ID oportunidad') == row['ID'] and e.get('Condición') == condition]
    if not records:
        return {}
    times = evidence_times(data)
    if all(times[id(record)] is not None for record in records):
        return max(enumerate(records), key=lambda item: (times[id(item[1])], item[0]))[1]
    # Records without recoverable time retain their original day precision and
    # writer order. Do not invent an observation time to break an ambiguous tie.
    def day(record):
        value = excel_date(record.get('Comprobada'))
        return value[:10] if isinstance(value, str) else ''
    newest_day = max(day(record) for record in records)
    candidates = [(index, record) for index, record in enumerate(records) if day(record) == newest_day]
    if all(times[id(record)] is not None for _, record in candidates):
        return max(candidates, key=lambda item: (times[id(item[1])], item[0]))[1]
    return candidates[-1][1]


def current_numbers(data, row):
    """Keep figures tied to their observation, without rewriting legacy stores.

    Old evidence sheets did not store the figures. Recover their provenance from
    the retained official batch when possible; otherwise preserve legacy fields.
    """
    from stubbs_jobs import excel_day
    result = {}
    for condition, key, fields in (
        ('Fijo ≥32 k€', 'Fijo ≥32 k€', {'fixed':'Fijo mín. confirmado', 'fixedMax':'Fijo máx. confirmado', 'currency':'Moneda fijo confirmado'}),
        ('Viajes', 'Viajes ≤1/mes', {'trips':'Viajes mín. al mes'}),
    ):
        latest = latest_evidence(data, row, condition)
        numbers = latest.get('numericValues')
        # XLSX stores structured provenance as literal JSON text. Legacy imports
        # retain that cell unchanged; the reader restores its meaning here.
        if isinstance(numbers,str):
            try:numbers=json.loads(numbers)
            except ValueError:numbers=None
        if not isinstance(numbers,dict):numbers=None
        if numbers is None and latest:
            for batch in reversed(data.get('changes', [])):
                for operation in reversed(batch.get('operations', [])):
                    if (operation.get('kind') == 'evidence' and operation.get('id') == row['ID'] and operation.get('condition') == key
                            and operation.get('state') == latest.get('Estado') and operation.get('proof') == latest.get('Texto o motivo')
                            and operation.get('url') == latest.get('Fuente') and excel_day(operation['at']) == latest.get('Comprobada')):
                        numbers = {k:operation[k] for k in fields if k in operation}
                        break
                if numbers is not None:break
        result.update({field: numbers.get(name) if numbers is not None else row.get(field)
                       for name, field in fields.items()})
    return result


def current_facts(data, row):
    """Project current proof over legacy indicators, without changing the store."""
    from stubbs_jobs import CONDITIONS
    result = current_numbers(data, row)
    for key, condition in CONDITIONS.items():
        latest = latest_evidence(data, row, condition)
        if latest.get('Estado') in ('Sí', 'No', 'Pendiente', 'Contradicción'):
            result[key] = latest['Estado']
    return result


def view(data, row):
    import app_context
    from personalization import context
    row = {**row, **current_facts(data, row)}
    criteria = app_context.scoped_criteria(data, row['ID'])
    search = app_context.scoped_search(data, row['ID'])
    modes = categories(search.get('workMode') or criteria.get('location'), 'mode', preference=True)
    contracts = categories(criteria.get('contract'), 'contract', preference=True)
    violations, unknowns = [], []
    for key, required, field, kind, label in (
        ('Remoto España', modes, 'Modalidad', 'mode', 'La modalidad publicada no cumple tu requisito de trabajo: '+str(search.get('workMode') or criteria.get('location'))+'.'),
        ('Indefinido', contracts, 'Contrato', 'contract', 'El contrato publicado no cumple tu requisito: '+str(criteria.get('contract'))+'.'),
    ):
        if not required:
            continue
        published = categories(row.get(field), kind)
        legacy_required = required == ({'remote'} if kind == 'mode' else {'permanent'})
        incompatible = bool(published) and published.isdisjoint(required)
        if incompatible or (legacy_required and row.get(key) == 'No'):
            violations.append({'key': key, 'reason': label})
        elif row.get(key)=='Contradicción' or (published and not published.issubset(required)) or (not published and not (legacy_required and row.get(key) == 'Sí')):
            unknowns.append(key)
    if not any(v['key'] == 'Remoto España' for v in violations) and modes:
        problem = presence_problem(row, search, modes)
        if problem:
            violations.append({'key': 'Remoto España', 'reason': problem})
    trips = criteria.get('maxTrips')
    if number(trips):
        required_trips = row.get('Viajes mín. al mes')
        if (number(required_trips) and required_trips > trips) or (
                not number(required_trips) and trips <= 1 and row.get('Viajes ≤1/mes') == 'No'):
            violations.append({'key': 'Viajes ≤1/mes', 'reason': 'Los desplazamientos exigidos superan tu máximo de '+str(trips)+' al mes.'})
        elif not number(required_trips) and not (row.get('Viajes ≤1/mes') == 'Sí' and trips >= 1):
            unknowns.append('Viajes ≤1/mes')
    minimum = criteria.get('minimumFixed')
    currency = search.get('currency') or 'EUR'
    same_currency = row.get('Moneda fijo confirmado') == currency if data.get('app', {}).get('personalized') else (row.get('Moneda fijo confirmado') or 'EUR') == currency
    low, high = row.get('Fijo mín. confirmado'), row.get('Fijo máx. confirmado')
    if number(minimum):
        # A range crossing the minimum is an opportunity to negotiate, not a rejection.
        ceiling = high if number(high) else low
        if same_currency and number(ceiling) and ceiling < minimum:
            violations.append({'key': 'Fijo ≥32 k€', 'reason': 'El fijo publicado queda por debajo de '+str(minimum)+' '+currency+' brutos anuales.'})
        else:
            latest = latest_evidence(data, row, 'Fijo ≥32 k€')
            limit = latest.get('minimumFixed', 32000)
            evidence_currency = latest.get('currency', 'EUR')
            if not number(ceiling) and row.get('Fijo ≥32 k€') == 'No' and number(limit) and minimum >= limit and evidence_currency == currency:
                violations.append({'key': 'Fijo ≥32 k€', 'reason': 'El salario publicado incumple el mínimo fijo de '+str(minimum)+' '+currency+' brutos anuales.'})
            elif not same_currency or not number(low) or low < minimum:
                unknowns.append('Fijo ≥32 k€')
    return {'canApply': not violations, 'violations': violations, 'unknowns': unknowns,
            'confirmed': not violations and not unknowns}


def reconcile(data, workflow):
    """Persist automatic archives only inside the official atomic writer.

    Manual archives and confirmed submissions retain their identity. Recovering
    eligibility never restores a selection, a sending permission or a task.
    """
    app = workflow.state(data)
    for row in data['sheets']['Oportunidades']:
        key = row['ID']
        existing = app.get('offerArchives', {}).get(key)
        if row['Estado'] in workflow.CLOSED or any(e['type'] == 'sent' and e['opportunityId'] == key for e in data['events']):
            continue
        decision = view(data, row)
        if decision['canApply']:
            if existing and existing.get('source') == 'minimums':
                app['offerArchives'].pop(key)
                workflow.record(data, 'Oferta disponible para decidir', key, 'Sistema', 'Ya no consta un incumplimiento de los mínimos actuales. No se recuperan permisos anteriores.')
            continue
        if existing and existing.get('source') != 'minimums':
            continue
        reasons = decision['violations']
        if existing and existing.get('violations') == reasons:
            continue
        # Reuse the archive action's withdrawal and delivery-preservation contract.
        if not existing:
            import offer_actions
            undo_size = len(app['undo'])
            offer_actions.handle(data, {'action': 'archive', 'targets': [{'id': key}],
                                        'expectedRevision': data['revision'], 'actor': 'Sistema'}, workflow)
            # Undo restores the person's criteria/action, not an automatic fact projection.
            del app['undo'][undo_size:]
        app['offerArchives'][key].update(source='minimums', violations=reasons,
                                         reason=' '.join(v['reason'] for v in reasons))
        workflow.record(data, 'Descartada por requisitos mínimos', key, 'Sistema', app['offerArchives'][key]['reason'])
