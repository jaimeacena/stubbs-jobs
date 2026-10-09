"""Atomic actions on an explicit set of offers, through the registry writer."""
import copy


def archived(data, key):
    return data.get('app', {}).get('offerArchives', {}).get(key)


def outcome_actions(data, key, workflow):
    """Closing a prospect and ending a submitted application are distinct decisions."""
    import request_workflow
    from offer_minimums import view as minimums
    row = workflow.row_for(data, key)
    from application_lifecycle import achievement
    if achievement(data, row):
        return set()
    sent = any(e['type'] == 'sent' and e['opportunityId'] == key for e in data['events'])
    requests = [r for r in workflow.state(data)['requests'] if r.get('opportunityId') == key and not r.get('interpretationOnly')]
    if any(r['type'] == 'send' and r['status'] == 'running' for r in requests):
        return set()
    results = {'achieve', 'mark-rejected', 'close'} if sent else set()
    if archived(data, key) or row['Estado'] in workflow.CLOSED:
        from application_lifecycle import view
        return results | ({'reopen-followup'} if view(data,row)['canReopen'] else set())
    if sent:
        return results | {'reject'}
    if request_workflow.unresolved_attempts(data, key) or (workflow.selection(data, key) or {}).get('selected'):
        return set()
    if row['Estado'] in ('Enviada', 'Pendiente de empresa', 'Entrevista', 'Oferta') or not minimums(data, row)['canApply']:
        return set()
    if any(r['status'] in ('blocked', 'interrupted') for r in requests):
        return set()
    return {'discard'}


def available(data, key, workflow):
    import stubbs_jobs as jobs
    import request_workflow
    row = workflow.row_for(data, key)
    app = workflow.state(data)
    sent = any(e['type'] == 'sent' and e['opportunityId'] == key for e in data['events'])
    if archived(data, key) or row['Estado'] in (*workflow.CLOSED, 'Entrevista', 'Oferta', 'Pendiente de empresa', 'Enviada') or sent:
        return outcome_actions(data, key, workflow)
    choice = workflow.selection(data, key)
    requests = [r for r in app['requests'] if r.get('opportunityId') == key and
                not r.get('interpretationOnly') and not request_workflow.superseded_send(data, r)]
    busy = any(r['status'] in ('queued', 'running', 'blocked', 'interrupted') for r in requests)
    choice_busy = any(r['status'] in ('queued', 'running', 'blocked', 'interrupted') and
                      not (r['type'] == 'investigate' and r['status'] == 'queued') for r in requests)
    sending = any(r['type'] == 'send' and r['status'] == 'running' for r in requests)
    result = outcome_actions(data, key, workflow)
    if any(workflow.answers(data,key).get(field) in (None,'') for field in workflow.draft(data,key)['requiredAnswers']):
        result.add('responses')
    if any(r['status'] in ('blocked','interrupted') for r in requests) and not request_workflow.unresolved_attempts(data,key):
        result.add('change')
    if choice and choice.get('selected'):
        if not sending:
            result.add('unselect')
        if any(p['opportunityId'] == key and p['id'] == workflow.stamp(data,key) and p.get('approvedAt') and
                               not p.get('revokedAt') for p in app['packages']):
            result.add('revoke')
        if not busy and not workflow.pending_change(data, key) and not workflow.readiness(data, key):
            result.add('approve')
    elif not choice_busy and not request_workflow.unresolved_attempts(data, key):
        eligibility = jobs.conditions(data, row)[0]
        if eligibility in ('Sí', 'Sí, aclarar'):
            result.update(('select-review', 'select-auto'))
        elif eligibility not in ('No', 'Resolver conflicto', 'Ya enviada'):
            result.add('investigate')
    return result


def handle(data, operation, workflow):
    from onboarding import require_ready
    require_ready(data)
    action = operation.get('action')
    if action not in ('archive', 'discard', 'close', 'reject', 'achieve', 'mark-rejected', 'reopen-followup', 'select-review', 'select-auto', 'investigate', 'approve', 'unselect', 'revoke', 'responses', 'change'):
        raise ValueError('Acción conjunta no disponible')
    targets = operation.get('targets')
    if not isinstance(targets, list) or not targets or len(targets) > 500 or any(
            not isinstance(item, dict) or not isinstance(item.get('id'), str) for item in targets):
        raise ValueError('Selecciona entre una y 500 ofertas')
    keys = [item['id'] for item in targets]
    if len(set(keys)) != len(keys):
        raise ValueError('La selección contiene ofertas repetidas')
    workflow.expect(data['revision'], operation.get('expectedRevision'))
    rows = {r['ID']: r for r in data['sheets']['Oportunidades']}
    historical = {'historical:' + str(h['id']) for h in data.get('historicalApplications', [])}
    if any(key not in rows and not (action == 'archive' and key in historical) for key in keys):
        raise ValueError('Una de las ofertas ya no está disponible. Actualiza la tabla')
    actor = operation.get('actor', 'Usuario')
    if action == 'archive':
        from application_lifecycle import achievement
        if any(key in rows and achievement(data, rows[key]) for key in keys):
            raise workflow.Conflict('Una solicitud lograda conserva su resultado final')
    if action in ('achieve', 'mark-rejected') and actor not in ('Usuario', 'Usuario'):
        raise ValueError('Este resultado debe indicarlo la persona; el agente registra comunicaciones comprobadas')
    # Validate the entire set before making changes. The outer writer also works
    # on a copy and commits once, so failures never leave a partial selection.
    if action != 'archive' and any(action not in available(data, key, workflow) for key in keys):
        raise workflow.Conflict('La acción ya no está disponible para todas las ofertas. Revisa la selección')
    if action=='responses':
        import app_context
        shared={}
        for item in targets:
            key=item['id'];values=item.get('values')
            if not isinstance(values,dict) or not values:raise ValueError('Revisa las respuestas de cada oferta')
            workflow.expect({field:workflow.answers(data,key).get(field) for field in values},item.get('expected'))
            workflow.expect(workflow.stamp(data,key),item.get('fingerprint'))
            definitions=app_context.definitions(data,key)
            for field,value in values.items():
                if field not in definitions:raise ValueError('Pregunta desconocida')
                if definitions[field]['scope']=='global' and field not in workflow.draft(data,key)['answers']:
                    if field in shared and shared[field]!=value:raise ValueError('Las respuestas generales deben coincidir')
                    shared[field]=value
    if action=='reopen-followup':
        from application_lifecycle import latest,business_events,BUSINESS
        for key in keys:
            event=latest(business_events(data,key))
            workflow.state(data)['offerArchives'].pop(key,None)
            rows[key]['Estado']=BUSINESS[event['type']]
            workflow.record(data,'Seguimiento reabierto por nueva respuesta',key,actor,'Nueva respuesta comprobada. Historial y permisos retirados conservados.')
        return
    if action in ('archive', 'discard', 'close', 'reject', 'achieve', 'mark-rejected'):
        archives = workflow.state(data).setdefault('offerArchives', {})
        manual_result = action in ('close', 'achieve', 'mark-rejected')
        result = {'achieve': 'achieved', 'mark-rejected': 'rejected'}.get(action, 'closed')
        changed = [key for key in keys if key in rows and
                   (manual_result and (key not in archives or archives[key].get('outcome') != result or
                                       result == 'rejected' and archives[key].get('source') != 'user_reported') or
                    not manual_result and rows[key]['Estado'] not in workflow.CLOSED and
                    (key not in archives or archives[key].get('source') == 'minimums' and actor != 'Sistema'))]
        if not changed:
            return
        before = {key: copy.deepcopy(archives.get(key)) for key in changed}
        app = workflow.state(data)
        for key in changed:
            sent = any(e['type'] == 'sent' and e['opportunityId'] == key for e in data['events'])
            outcome = result if sent else 'discarded'
            archives[key] = {'at': workflow.now(), 'actor': actor, 'outcome': outcome,
                             'closureReason':outcome if outcome in ('achieved', 'rejected') else operation.get('reason','user') if sent else 'discarded',
                             'reason': {'achieved':'La empresa te ofrece el puesto, según indicas.',
                                        'rejected':'La empresa ha rechazado tu solicitud, según indicas.',
                                        'closed':'Seguimiento cerrado por ti; no consta un rechazo de la empresa.',
                                        'discarded':'Oferta descartada por ti.'}[outcome]}
            if manual_result:archives[key]['source']='user_reported'
            app['selections'].pop(key, None)
            for package in app['packages']:
                if package['opportunityId'] == key and package.get('approvedAt') and not package.get('revokedAt') and not any(
                        e['type'] == 'sent' and e.get('packageId') == package['id'] for e in data['events']):
                    package['revokedAt'] = workflow.now()
            for request in app['requests']:
                if request.get('opportunityId') == key and request['status'] == 'queued':
                    request.update(status='cancelled', updatedAt=workflow.request_timestamp(request),
                                   result='La persona registró el resultado de esta solicitud.' if sent else 'La persona descartó esta oferta.')
            workflow.record(data, {'achieved':'Solicitud lograda', 'rejected':'Rechazo registrado por ti',
                                  'closed':'Seguimiento cerrado por ti', 'discarded':'Oferta descartada'}[outcome], key, actor,
                            'Historial conservado. Permisos futuros retirados; cualquier envío iniciado debe comprobarse.')
        event = workflow.record(data, 'Resultados actualizados' if action in ('achieve','mark-rejected') else 'Seguimientos cerrados por ti' if action in ('close','reject') else 'Ofertas descartadas' if action == 'discard' else 'Ofertas archivadas', actor=actor, detail=str(len(changed)))
        app['undo'].append({'id': event['id'], 'kind': 'offer-archive', 'before': before,
                            'after': {key: copy.deepcopy(archives[key]) for key in changed}, 'used': False})
        return
    for item in targets:
        key = item['id']
        if action.startswith('select-') or action == 'unselect':
            workflow.handle(data, {'kind': 'ui-select-opportunity', 'opportunityId': key,
                                  'selected': action != 'unselect', 'mode': action.removeprefix('select-'),
                                  'expected': copy.deepcopy(workflow.selection(data, key)), 'actor': actor})
        elif action == 'investigate':
            workflow.handle(data, {'kind': 'ui-request', 'opportunityId': key, 'type': 'investigate', 'actor': actor})
        elif action == 'approve':
            workflow.handle(data, {'kind': 'ui-approve', 'opportunityId': key,
                                  'fingerprint': item.get('fingerprint'), 'actor': actor})
        elif action == 'revoke':
            current = next(p for p in workflow.state(data)['packages'] if p['opportunityId'] == key and
                           p['id'] == workflow.stamp(data, key) and p.get('approvedAt') and not p.get('revokedAt'))
            workflow.handle(data, {'kind': 'ui-revoke', 'packageId': current['id'], 'actor': actor})
        elif action=='responses':
            workflow.handle(data, {'kind':'ui-responses','opportunityId':key,'values':item['values'],
                                  'expected':{field:workflow.answers(data,key).get(field) for field in item['values']},'actor':actor})
        elif action=='change':
            workflow.handle(data, {'kind':'ui-change','opportunityId':key,'message':operation.get('message'),'actor':actor})
