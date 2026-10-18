"""An application the person sent herself, recorded through the registry writer.

It never invents a portal receipt or an agent delivery: the event keeps its
origin (reportedBy=user), the CV the person declares and her optional note.
Recording it ends the agent's pending sends for that offer and retires their
permissions, so no automatic attempt can repeat the application.
"""
import copy
from datetime import datetime, timedelta, timezone

from state_support import instant
from stubbs_jobs_core import digest, now, vacancy_key

KIND = 'ui-user-sent'
UNDO = 'user-sent'
NOTE_LIMIT = 2000
OPEN = ('queued', 'blocked', 'interrupted')


def _sent(data, key):
    return any(e.get('type') == 'sent' and e.get('opportunityId') == key for e in data['events'])


def _same_vacancy(data, row):
    canonical = vacancy_key(row)
    return {r['ID'] for r in data['sheets']['Oportunidades'] if r['ID'] != row['ID'] and vacancy_key(r) == canonical}


def _historical(data, row):
    canonical = vacancy_key(row)
    return [h for h in data.get('historicalApplications', []) if vacancy_key(h) == canonical]


def _current_package(data, key, workflow):
    current = workflow.stamp(data, key)
    return next((p for p in workflow.state(data)['packages'] if p['id'] == current and p.get('opportunityId') == key), None)


def blocker(data, row, workflow):
    """Why this offer cannot record the person's own send now, or None."""
    import request_workflow
    from application_lifecycle import achievement
    key = row['ID']
    if _sent(data, key):
        return 'Esta solicitud ya consta como enviada.'
    if workflow.archived(data, key) or row['Estado'] in workflow.CLOSED or achievement(data, row):
        return 'Esta oferta está cerrada o descartada. Recupérala antes de registrar tu envío.'
    requests = workflow.state(data)['requests']
    if any(r.get('type') == 'send' and r.get('opportunityId') == key and r['status'] == 'running' for r in requests):
        return ('El agente está enviando esta solicitud. Espera su resultado o pídele que detenga ese intento '
                'antes de registrar tu envío.')
    if any(r.get('type') == 'send' and r.get('opportunityId') == key and request_workflow.interruption_unconfirmed(r) for r in requests):
        return ('Un envío anterior del agente quedó sin confirmar que se detuviera. Pide al agente que confirme '
                'esa parada antes de registrar tu envío.')
    same = _same_vacancy(data, row)
    if any(e.get('type') == 'sent' and e.get('opportunityId') in same for e in data['events']):
        return 'Esta vacante ya tiene un envío registrado en otra ficha.'
    if any(r.get('type') == 'send' and r.get('opportunityId') in same and r['status'] == 'running' for r in requests):
        return 'La misma vacante tiene un envío del agente en curso en otra ficha.'
    return None


def conciliation(data, row, workflow):
    """What the person reviews before confirming; a change makes the dialog stale."""
    import request_workflow
    key = row['ID']
    requests = [r for r in workflow.state(data)['requests'] if r.get('type') == 'send' and r.get('opportunityId') == key]
    package = _current_package(data, key, workflow)
    return {
        'pendingSends': sorted(r['id'] for r in requests if r['status'] in OPEN),
        'uncertainAttempts': sorted(r['id'] for r in request_workflow.unresolved_attempts(data, key)),
        'historical': sorted(str(h['id']) for h in _historical(data, row)),
        'packageId': package['id'] if package else None,
    }


def view(data, row, workflow):
    """Read-only data for the detail dialog; no writes, permissions or work."""
    from application_lifecycle import achievement
    key = row['ID']
    if _sent(data, key) or workflow.archived(data, key) or row['Estado'] in workflow.CLOSED or achievement(data, row):
        return None
    reason = blocker(data, row, workflow)
    facts = conciliation(data, row, workflow)
    package = _current_package(data, key, workflow)
    issue = workflow.package_issue(package) if package else None
    option = None
    if package and not issue and package['payload'].get('cvHash'):
        from personalization import cv_file_name
        option = {'packageId': package['id'], 'name': cv_file_name(data, row['Empresa'])}
    historical = [{'company': h.get('company'), 'title': h.get('title'), 'state': h.get('state')} for h in _historical(data, row)]
    return {'available': reason is None, 'reason': reason, 'packageCv': option,
            'pendingSends': len(facts['pendingSends']), 'uncertainAttempts': len(facts['uncertainAttempts']),
            'historical': historical, 'conciliation': digest(facts)}


def _cv(data, row, choice, workflow):
    if not isinstance(choice, dict):
        raise ValueError('Indica el CV que enviaste: el del paquete preparado o uno de Currículums')
    if choice.get('source') == 'package' and set(choice) == {'source', 'packageId'}:
        package = _current_package(data, row['ID'], workflow)
        if not package or package['id'] != choice['packageId']:
            raise workflow.Conflict('El paquete preparado ha cambiado. Revisa la oferta y elige de nuevo el CV que enviaste.')
        workflow.conserved_package(package)
        archived = 'data/packages/' + package['id'] + '/cv.pdf'
        return {'cv': archived, 'archivedCV': archived, 'cvHash': package['payload']['cvHash'],
                'cvSource': 'package', 'cvPackageId': package['id']}
    if choice.get('source') == 'library' and set(choice) == {'source', 'path', 'fingerprint'}:
        import cv_retirement
        known = {d['path']: d for d in cv_retirement.catalog(data, workflow.ROOT)}
        document = known.get(choice['path']) if isinstance(choice['path'], str) else None
        if not document or not document.get('fingerprint'):
            raise ValueError('Ese CV no está en Currículums o no se puede leer')
        if document['fingerprint'] != choice['fingerprint']:
            raise workflow.Conflict('Ese CV ha cambiado en Currículums. Vuelve a elegir el que enviaste.')
        return {'cv': document['path'], 'archivedCV': document['path'], 'cvHash': document['fingerprint'],
                'cvSource': 'library'}
    raise ValueError('Indica el CV que enviaste: el del paquete preparado o uno de Currículums')


def record_sent(data, operation, workflow):
    from onboarding import require_ready
    require_ready(data)
    actor = operation.get('actor', 'Agente')
    if not workflow.chosen_by_person(actor):
        raise ValueError('Solo la persona registra una solicitud que envió ella misma; el agente registra envíos con su recibo')
    key = operation.get('opportunityId')
    row = workflow.row_for(data, key)
    reason = blocker(data, row, workflow)
    if reason:
        raise ValueError(reason)
    facts = conciliation(data, row, workflow)
    workflow.expect(digest(facts), operation.get('expected'))
    at = operation.get('sentAt')
    sent_at = instant(at) if isinstance(at, str) and 'T' in at else None
    try:
        zoned = sent_at is not None and datetime.fromisoformat(at.replace('Z', '+00:00')).tzinfo is not None
    except ValueError:
        zoned = False
    if not zoned or sent_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Indica la fecha y hora reales del envío, con zona horaria y sin fechas futuras')
    note = operation.get('note')
    if note is not None and (not isinstance(note, str) or len(note) > NOTE_LIMIT):
        raise ValueError('La nota admite hasta 2000 caracteres')
    note = (note or '').strip()
    if operation.get('duplicatesChecked') is not True:
        raise ValueError('Confirma que es tu única solicitud a esta vacante')
    if facts['historical'] and operation.get('reapplication') is not True:
        raise ValueError('Coincide con una candidatura anterior; confirma que es una solicitud nueva')
    cv = _cv(data, row, operation.get('cv'), workflow)
    app = workflow.state(data)
    stamp_at = now()
    cancelled, revoked = [], []
    for request in app['requests']:
        if request.get('type') != 'send' or request.get('opportunityId') != key or request['status'] not in OPEN:
            continue
        started = bool(request.get('startedAt'))
        request.update(status='cancelled', updatedAt=workflow.request_timestamp(request),
                       result='Enviaste tú la solicitud; el agente no la enviará.' +
                              (' Su intento anterior no se repetirá.' if started else ''))
        request.pop('need', None)
        cancelled.append(request['id'])
        workflow.record(data, 'Envío del agente cancelado', key, 'Sistema', request['result'],
                        request.get('packageId'))['requestId'] = request['id']
    for package in app['packages']:
        if package.get('opportunityId') == key and package.get('approvedAt') and not package.get('revokedAt'):
            package['revokedAt'] = stamp_at
            revoked.append(package['id'])
    from stubbs_jobs import excel_day
    from application_lifecycle import project_event
    proof = note or 'Indicado por ti desde la ficha. La app no conserva un recibo del portal.'
    event = {'id': 'user-sent-' + digest([key, at, stamp_at])[:24], 'type': 'sent', 'opportunityId': key,
             'at': at, 'proof': proof, 'reportedBy': 'user', 'actor': actor, 'recordedAt': stamp_at,
             'historyChecked': True, 'duplicatesChecked': True, **cv,
             'conciliation': {'cancelledRequestIds': cancelled, 'revokedPackageIds': revoked,
                              'uncertainAttemptIds': facts['uncertainAttempts'],
                              'historicalIds': facts['historical']},
             'source': row.get('Fuente'), 'family': row.get('Familia'), 'cohort': at[:7]}
    if note:
        event['note'] = note
    if facts['historical']:
        event['reapplication'] = True
    before = {field: copy.deepcopy(row.get(field)) for field in ('Estado', 'CV usado', 'Fecha candidatura', 'Siguiente paso')}
    data['events'].append(event)
    row['CV usado'] = cv['cv']
    row['Fecha candidatura'] = excel_day(at)
    project_event(data, row, event)
    row['Siguiente paso'] = 'Solicitud enviada por ti. Esperar novedades de la empresa.'
    history = workflow.record(data, 'Solicitud enviada', key, actor, proof)
    history.update(eventId=event['id'], at=at, recordedAt=stamp_at)
    data['sheets']['Actividad'].append({'Fecha': excel_day(at), 'ID oportunidad': key, 'Acción': 'sent',
                                        'Estado anterior': before['Estado'], 'Estado nuevo': row['Estado'],
                                        'CV / material': cv['cv'], 'Resultado / prueba': 'Enviada por la persona. ' + proof,
                                        'Próximo paso': row['Siguiente paso']})
    item = {'id': history['id'], 'kind': UNDO, 'opportunityId': key, 'eventId': event['id'],
            'before': before, 'used': False}
    item['after'] = undo_current(data, item)
    app['undo'].append(item)


def undo_current(data, item):
    """The record can be undone only while nothing has happened after it."""
    key = item['opportunityId']
    app = data.get('app', {})
    return {'event': item['eventId'] if any(e.get('id') == item['eventId'] for e in data['events']) else None,
            'events': sorted(e['id'] for e in data['events'] if e.get('opportunityId') == key and e.get('type') != 'note'),
            'checks': len(app.get('followupChecks', {}).get(key, [])),
            'plan': copy.deepcopy(app.get('followupPlans', {}).get(key)),
            'archive': copy.deepcopy(app.get('offerArchives', {}).get(key))}


def undo(data, item, workflow, actor):
    """Withdraw the record; cancelled sends and retired permissions stay as they are."""
    event = next(e for e in data['events'] if e.get('id') == item['eventId'])
    data['events'].remove(event)
    workflow.state(data).setdefault('retractedEvents', []).append(
        {**copy.deepcopy(event), 'retractedAt': now(), 'retractedBy': actor})
    row = workflow.row_for(data, item['opportunityId'])
    previous = row['Estado']
    for field, value in item['before'].items():
        row[field] = copy.deepcopy(value)
    row['Siguiente paso'] = ('Registro de tu envío deshecho. Los envíos cancelados y los permisos retirados '
                             'no se recuperan; revisa la oferta antes de decidir.')
    from stubbs_jobs import excel_day
    data['sheets']['Actividad'].append({'Fecha': excel_day(now()), 'ID oportunidad': row['ID'], 'Acción': 'sent-undone',
                                        'Estado anterior': previous, 'Estado nuevo': row['Estado'],
                                        'CV / material': event.get('cv'),
                                        'Resultado / prueba': 'La persona deshizo el registro de su envío.',
                                        'Próximo paso': row['Siguiente paso']})


def handle(data, operation, workflow):
    if operation['kind'] != KIND:
        return False
    record_sent(data, operation, workflow)
    return True
