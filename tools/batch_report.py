"""Read-only report of an application batch, with its funnel and the person's morning list (04/11/2026)."""
import collections
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import app_workflow as workflow
import pending_entries
from state_support import instant
from stubbs_jobs_core import ROOT, atomic_bytes

EXCEL_EPOCH = date(1899, 12, 30)
NEED_TITLES = {'access': 'Accesos y verificaciones', 'answers': 'Preguntas por responder', 'decision': 'Decisiones tuyas',
               'contact': 'Contactos', 'other': 'Otras incidencias', None: 'Sin clasificar'}
# First match wins, from the most specific reason to the most general.
REASONS = (('Oferta caducada o cerrada', r'cerrad|caducad|no disponible|ya no |retirad|404'),
           ('Duplicada o ya presentada', r'duplic|ya present|ya enviad|ya cons|historial|misma vacante'),
           ('Contrato', r'contrat|aut[oó]nom|freelance|b2b|indefinid|temporal'),
           ('Modalidad o ubicación', r'h[ií]brid|presencial|oficina|on.?site|solo desde|ubicaci|fuera de espa|pa[ií]s|reside'),
           ('Jornada u horario', r'jornada|horario|part.?time|\b\d+\s?h(oras)?\b'),
           ('Salario', r'salari|sueldo|k€|banda|retribu'),
           ('Requisitos o experiencia', r'requisit|a[ñn]os|experiencia|python|spark|java\b|sap\b|aws|nivel|imprescindible|consultor'),
           ('Puesto fuera de objetivo', r'fuera de|ajen|marketing|ventas|comercial|funcional|no encaja|otro perfil|objetivo'))


def reason_group(text):
    words = str(text or '').casefold()
    if not words.strip():
        return 'Sin motivo registrado'
    return next((name for name, pattern in REASONS if re.search(pattern, words)), 'Otros motivos')


def _since(value):
    if value in (None, ''):
        return datetime.now(timezone.utc)-timedelta(hours=24)
    moment = instant(value)
    if moment is None:
        raise ValueError('Indica --from con una fecha ISO, por ejemplo 2026-11-03T20:00:00+00:00')
    return moment


def _within(value, since):
    """Adverts keep the day as an Excel serial; other records keep an ISO instant or date."""
    if type(value) in (int, float):
        return EXCEL_EPOCH+timedelta(days=int(value)) >= since.date()
    moment = instant(value) if value else None
    if moment is not None:
        return moment >= since
    try:
        return date.fromisoformat(str(value)) >= since.date()
    except ValueError:
        return False


def funnel(data, since):
    """Counts from recorded states and reasons; the groups are an orientation, never a decision."""
    rows = data['sheets']['Oportunidades']
    entries = [e for e in data['sheets']['Entradas'] if _within(e.get('Primera vista'), since)]
    discarded = [e for e in entries if e.get('Estado') in ('Descartada', 'Cerrada')]
    archives = {key: value for key, value in data.get('app', {}).get('offerArchives', {}).items()
                if isinstance(value, dict) and _within(value.get('at') or value.get('archivedAt'), since)}
    reasons = collections.Counter(reason_group(e.get('Motivo / comprobación')) for e in discarded)
    reasons.update(reason_group(value.get('reason')) for value in archives.values())
    sent = [e for e in data['events'] if e['type'] == 'sent' and _within(e.get('at'), since)]
    return {'from': since.isoformat(timespec='seconds'), 'seen': len(entries),
            'promoted': sum(1 for e in entries if e.get('ID oportunidad')), 'discardedEntries': len(discarded),
            'archivedOffers': len(archives), 'pendingEntries': sum(1 for e in entries if e.get('Estado') == 'Nueva'),
            'sent': len(sent), 'reasons': reasons.most_common(),
            'allTime': {'opportunities': len(rows), 'sent': sum(1 for e in data['events'] if e['type'] == 'sent')},
            'limits': 'Los grupos se deducen del texto del motivo; un motivo puede tener más de una causa.'}


def _package(data, identifier):
    return next((p for p in data.get('app', {}).get('packages', []) if p['id'] == identifier), None)


def _sent_items(data, since):
    items = []
    for event in data['events']:
        if event['type'] != 'sent' or not _within(event.get('at'), since):
            continue
        row = workflow.row_for(data, event['opportunityId'])
        payload = (_package(data, event.get('packageId')) or {}).get('payload') or {}
        scoped = {q['key']: q for q in payload.get('questions') or [] if q.get('scope') == 'opportunity'}
        answers = [{'label': scoped[k]['label'], 'value': payload.get('answers', {}).get(k)}
                   for k in payload.get('formAnswerKeys') or [] if k in scoped]
        items.append({'id': event['opportunityId'], 'company': row.get('Empresa'), 'title': row.get('Puesto'), 'url': row.get('URL original'),
                      'at': event.get('at'), 'confirmation': event.get('confirmation'), 'reportedBy': event.get('reportedBy'),
                      'cvAdaptation': payload.get('cvAdaptation'), 'cvReason': payload.get('cvReason'), 'answersToReview': answers})
    return items


def _morning(data):
    """Everything that waits on the person, grouped by what they have to do."""
    uncertain = {r['id'] for r in workflow.unresolved_sends(data)}
    groups = collections.defaultdict(list)
    for request in data.get('app', {}).get('requests', []):
        if request.get('supersededByRequestId') or (request['status'] != 'blocked' and request['id'] not in uncertain):
            continue
        key = request.get('opportunityId')
        row = workflow.row_for(data, key) if key else {}
        if key and workflow.archived(data, key):
            continue
        need = request.get('need') if request.get('need') in NEED_TITLES else None
        groups[need].append({'requestId': request['id'], 'type': request['type'], 'company': row.get('Empresa'), 'title': row.get('Puesto'),
                             'url': row.get('URL original'), 'summary': request.get('summary') or str(request.get('result') or '')[:300],
                             'uncertainDelivery': request['id'] in uncertain})
    return [{'need': need, 'title': NEED_TITLES[need], 'items': items} for need, items in groups.items()]


def _chosen_unsent(data):
    sent = {e['opportunityId'] for e in data['events'] if e['type'] == 'sent'}
    blocked = {r.get('opportunityId') for r in data.get('app', {}).get('requests', []) if r['status'] == 'blocked'}
    result = []
    for row in data['sheets']['Oportunidades']:
        key = row['ID']
        if key in sent or key in blocked or workflow.archived(data, key) or row.get('Estado') in workflow.CLOSED:
            continue
        if (workflow.selection(data, key) or {}).get('selected'):
            result.append({'id': key, 'company': row.get('Empresa'), 'title': row.get('Puesto'), 'url': row.get('URL original')})
    return result


def report(data, since=None):
    start = _since(since)
    sent = _sent_items(data, start)
    import requirement_match
    return {'from': start.isoformat(timespec='seconds'), 'sent': sent,
            'skillGaps': requirement_match.gaps_summary(data),
            'reusedCv': [item['company'] for item in sent if item['cvAdaptation'] == 'reused'],
            'morning': _morning(data), 'chosenNotSent': _chosen_unsent(data),
            'pendingEntries': pending_entries.summary(data), 'funnel': funnel(data, start)}


def markdown(result):
    lines = ['# Informe de la tanda', '', 'Desde ' + result['from'] + '.', '', f"## Enviadas ({len(result['sent'])})", '']
    for item in result['sent']:
        cv = {'adapted': 'CV adaptado', 'reused': 'CV general'}.get(item['cvAdaptation'], 'CV sin declarar')
        origin = ' Enviada por ti.' if item.get('reportedBy') == 'user' else ''
        lines.append(f"- **{item['company']}** · {item['title']} · {cv}.{origin} Confirmación: {item['confirmation'] or 'sin recibo registrado'}. {item['url']}")
    if not result['sent']:
        lines.append('Ninguna en este periodo.')
    review = [item for item in result['sent'] if item['answersToReview']]
    if review:
        lines += ['', '## Respuestas para revisar', '']
        for item in review:
            lines.append(f"- **{item['company']}**: " + '; '.join(f"{a['label']}: {a['value']}" for a in item['answersToReview']))
    lines += ['', '## Lo que te toca a ti', '']
    for group in result['morning']:
        lines += ['### ' + group['title'], '']
        for item in group['items']:
            place = f"**{item['company']}** · {item['title']}: " if item['company'] else ''
            warning = ' Envío sin confirmar: comprueba el portal antes de repetirlo.' if item['uncertainDelivery'] else ''
            lines.append(f"- {place}{item['summary']}{warning} {item['url'] or ''}".rstrip())
        lines.append('')
    if not result['morning']:
        lines += ['Nada bloqueado.', '']
    if result['chosenNotSent']:
        lines += ['### Elegidas sin enviar', '']
        lines += [f"- **{item['company']}** · {item['title']} {item['url']}" for item in result['chosenNotSent']]
        lines.append('')
    funnel_view = result['funnel']
    lines += ['## Embudo', '',
              f"Anuncios vistos: {funnel_view['seen']} · promovidos: {funnel_view['promoted']} · descartados: {funnel_view['discardedEntries']} · "
              f"ofertas archivadas: {funnel_view['archivedOffers']} · sin revisar: {funnel_view['pendingEntries']} · enviadas: {funnel_view['sent']}", '']
    if funnel_view['reasons']:
        lines += ['| Motivo de descarte | Ofertas |', '| --- | --- |']
        lines += [f'| {name} | {count} |' for name, count in funnel_view['reasons']]
        lines += ['', funnel_view['limits']]
    if result.get('skillGaps'):
        lines += ['', '## Requisitos que más te faltan en las ofertas abiertas', '', '| Requisito | Ofertas |', '| --- | --- |']
        lines += [f'| {name} | {count} |' for name, count in result['skillGaps']]
        lines += ['', 'Comparación por palabras con tus competencias confirmadas: orienta, no decide.']
    return '\n'.join(lines).rstrip()+'\n'


def write(data, since=None, root=None):
    """Save the report beside other generated outputs; the registry is not touched."""
    result = report(data, since)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    path = Path(root or ROOT)/'outputs/informes'/f'tanda-{stamp}.md'
    atomic_bytes(path, markdown(result).encode('utf-8'))
    return {**result, 'file': path.relative_to(Path(root or ROOT)).as_posix()}
