"""Task transitions and delivery recovery, used only through the registry writer."""
import copy
import os
from datetime import datetime, timedelta, timezone

from state_support import instant
from stubbs_jobs_core import digest

TRANSITIONS = {
    'queued': {'running', 'cancelled'},
    'running': {'running', 'done', 'blocked', 'interrupted'},
    'blocked': {'queued', 'cancelled'},
    'interrupted': {'queued', 'cancelled'},
    'done': set(),
    'cancelled': set(),
}
NEEDS = {'contact', 'answers', 'access', 'decision', 'other'}


def interruption_unconfirmed(request):
    return (request.get('status') == 'interrupted' and
            request.get('result') == 'No se ha recibido actividad durante dos horas. Revisar antes de reintentar.')


def delivery_checked(request, package_id, allow_cancelled=False):
    if (request.get('status') == 'cancelled' and not allow_cancelled) or interruption_unconfirmed(request):
        return False
    check = request.get('deliveryCheck', {})
    if check.get('consumedByRequestId'):return False
    at = instant(check.get('at'))
    age = datetime.now(timezone.utc) - at if at else None
    return (check.get('outcome') == 'not_sent' and check.get('packageId') == package_id and
            isinstance(check.get('proof'), str) and bool(check['proof'].strip()) and
             age is not None and -timedelta(minutes=5) <= age <= timedelta(hours=1))

def validate_sent_time(request,package,sent_at):
    """Normal and recovered receipts prove an effect of the same authorized start."""
    started=instant(request.get('startedAt'))
    authorization=request.get('authorizationAt',package.get('approvedAt'))
    approved=instant(authorization)
    current=datetime.now(timezone.utc)
    if not started or not approved or approved>started or started>current+timedelta(minutes=5):
        raise ValueError('La confirmación necesita un inicio real autorizado del paquete original')
    sent=instant(sent_at)
    if not sent or sent<started-timedelta(minutes=5) or sent>current+timedelta(minutes=5):
        raise ValueError('La confirmación necesita la fecha real del envío, posterior a su inicio autorizado y sin fechas futuras')
    return authorization


def superseded_send(data,request):
    """Only a preserved absence consumed by an actual successor closes this attempt."""
    check=request.get('deliveryCheck',{})
    successor=next((other for other in data.get('app',{}).get('requests',[]) if other['id']==check.get('consumedByRequestId')),None)
    if (request.get('type')=='send' and request.get('status')!='running' and not interruption_unconfirmed(request) and
            check.get('outcome')=='not_sent' and check.get('packageId')==request.get('packageId') and
            instant(check.get('at')) and isinstance(check.get('proof'),str) and check['proof'].strip() and
            successor and successor['id']!=request['id'] and successor.get('type')=='send' and
            successor.get('opportunityId')==request.get('opportunityId') and instant(successor.get('startedAt'))):
        return successor['id']
    return None


def unresolved_attempts(data, opportunity_id, current=None):
    """A new package/request cannot erase an earlier attempt's unknown effect."""
    if any(event['type']=='sent' and event.get('opportunityId')==opportunity_id for event in data['events']):return []
    requests=data.get('app',{}).get('requests',[])
    unresolved=[]
    for item in requests:
        if (item.get('type')!='send' or item.get('opportunityId')!=opportunity_id or
                not item.get('startedAt') or (current and item['id']==current['id'])):continue
        if item['status']=='running':
            unresolved.append(item);continue
        if superseded_send(data,item):continue
        if not delivery_checked(item,item.get('packageId'),allow_cancelled=True):unresolved.append(item)
    return unresolved


def require_delivery_resolved(data,opportunity_id,current=None):
    if any(event['type']=='sent' and event.get('opportunityId')==opportunity_id for event in data['events']):
        raise ValueError('Esta solicitud ya está enviada; no repetir el formulario')
    unresolved=unresolved_attempts(data,opportunity_id,current)
    if any(item['status']=='running' for item in unresolved):
        raise ValueError('El envío ya está en curso; espera su confirmación o detén ese intento y comprueba el portal')
    if unresolved:
        raise ValueError('Hay un envío anterior de esta oferta sin resolver. Detén cualquier intento activo y comprueba el portal con ui-delivery-check antes de autorizar o iniciar otro envío.')


def consume_prior_checks(data,request,workflow):
    for item in data.get('app',{}).get('requests',[]):
        if (item['id']!=request['id'] and item.get('type')=='send' and
                item.get('opportunityId')==request.get('opportunityId') and item.get('startedAt') and
                delivery_checked(item,item.get('packageId'),allow_cancelled=True)):
            item['deliveryCheck']['consumedByRequestId']=request['id']
            item['updatedAt']=workflow.request_timestamp(item)


def update(data, operation, workflow):
    import agent_runner
    app = workflow.state(data)
    request = next((item for item in app['requests'] if item['id'] == operation.get('id')), None)
    if request is None:
        raise ValueError('No se encuentra esta tarea. Actualiza el estado antes de continuar.')
    workflow.require_current_execution(request)
    previous, status = request['status'], operation.get('status')
    if not isinstance(status, str):
        raise ValueError('Indica un estado válido para la tarea')
    allowed = TRANSITIONS.get(previous, set())
    if request['type'] == 'mail':
        if status != 'cancelled':
            raise ValueError('La búsqueda en correo se ha retirado de Stubbs Jobs')
        allowed = allowed | {'cancelled'} if previous == 'running' else allowed
    if status not in allowed:
        raise ValueError('Transición de encargo no válida')
    if status=='queued' or status=='running' and previous!='running':
        if request.get('opportunityId') and not request.get('interpretationOnly') and (workflow.archived(data,request['opportunityId']) or workflow.row_for(data,request['opportunityId'])['Estado'] in workflow.CLOSED):
            raise ValueError('Esta oferta está archivada; recupérala antes de continuar')
    if status == 'queued' and interruption_unconfirmed(request):
        raise ValueError('La actividad antigua no confirma una parada. Registra ui-request-interrupt con la comprobación del chat anterior antes de continuar.')
    proof = operation.get('proof')
    if not isinstance(proof, str) or not proof.strip() or len(proof) > 15000:
        raise ValueError('El encargo necesita un resultado o explicación concreta')
    owner = workflow.execution_id()
    if previous == 'running':
        workflow.require_owner(request)
    if status == 'blocked' and (not isinstance(operation.get('summary'), str) or
            not 1 <= len(operation['summary'].strip()) <= 300 or operation.get('need') not in NEEDS):
        raise ValueError('Un bloqueo necesita un resumen concreto y el tipo de ayuda pendiente')
    if status == 'running':
        if previous!='running':workflow.bind_execution_scope(data,request)
        if app.get('personalized') and not owner:
            raise ValueError('Indica --execution-id con un identificador propio para este trabajo')
        if any(item['status'] == 'running' and item.get('executionId') != owner for item in app['requests']):
            raise ValueError('Otra IA está trabajando. Espera a que termine.')
        execution = agent_runner.read_state()
        if agent_runner.view()['status'] in agent_runner.ACTIVE and execution.get('id') != owner:
            raise ValueError('La app ya está ejecutando los encargos. Espera a que termine.')
        if os.environ.get('STUBBS_JOBS_RUN_ID') and (execution.get('id') != owner or request['id'] not in execution.get('requestIds', [])):
            raise ValueError('Este encargo no pertenece al lote de esta ejecución.')
    if request['type'] == 'send':
        if status=='queued':require_delivery_resolved(data,request['opportunityId'],request)
        if status == 'queued' and not delivery_checked(request, request.get('packageId')):
            raise ValueError('El envío quedó sin confirmar. Pide al agente que compruebe el portal y registre ui-delivery-check antes de reintentar.')
        if status == 'running':
            require_delivery_resolved(data,request['opportunityId'],request)
            package = workflow.approved_package(data, request['opportunityId'], request['packageId'])
            if previous != 'running' and request.get('startedAt') and not delivery_checked(request, request['packageId']):
                raise ValueError('La comprobación del portal ha caducado. Comprueba de nuevo si la solicitud ya se envió.')
            if previous != 'running':
                request.setdefault('authorizationAt', package['approvedAt'])
            # A portal check permits one attempt only, never another automatic retry.
            request.pop('deliveryCheck', None)
        if status == 'done' and not any(event['type'] == 'sent' and event.get('packageId') == request['packageId'] for event in data['events']):
            raise ValueError('Falta confirmación de envío')
        if status == 'cancelled':
            package = next(item for item in app['packages'] if item['id'] == request['packageId'])
            package['revokedAt'] = workflow.now()
            workflow.row_for(data, request['opportunityId'])['Siguiente paso'] = 'Envío cancelado. Revisar el paquete antes de autorizarlo de nuevo.'
            workflow.record(data, 'Autorización retirada al cancelar el envío', request['opportunityId'], operation.get('actor', 'Agente'))
    if status != previous:
        # A previous phase's impediment must not become the new result's summary.
        # Its original operation/proof remains in changes and the task history.
        for name in ('summary', 'need'):
            if name not in operation:
                request.pop(name, None)
    for name in ('summary', 'need'):
        if name in operation:
            value = operation[name]
            if not isinstance(value, str) or len(value) > 300:
                raise ValueError('Resumen demasiado largo')
            if name == 'need' and value not in NEEDS:
                raise ValueError('Tipo de ayuda desconocido')
            request[name] = value
            if name == 'summary':
                request[name] = value.strip()
    at = workflow.now()
    if status == 'running' and previous != 'running':
        request.setdefault('startedAt', at)
        if request['type']=='send':consume_prior_checks(data,request,workflow)
        if request['type'] == 'discovery':
            request.setdefault('discoveryBaseline', [row['ID'] for row in data['sheets']['Oportunidades']])
            if not request.get('round'):
                request['round']=workflow.search_round(data,request.get('searchProfileId'))
                request['roundOrigin']='legacy-start'
    updated_at=workflow.request_timestamp(request)
    if status == 'done' and request['type'] == 'discovery':
        request['activityResult'] = workflow.discovery_result(data, request, request['activityAt'])
        tags = workflow.state(data).setdefault('offerRounds', {})
        for key in request['activityResult'].get('newOpportunityIds', []):
            tags.setdefault(key, request['id'])
    request.update(status=status, result=proof, updatedAt=updated_at)
    if status == 'running' and owner:
        request['executionId'] = owner
    if status == 'queued':
        request.pop('executionId', None)
        request.pop('launchAttemptedAt', None)
        request['autoStart'] = True
    if status != 'running':
        title = {'done': 'Encargo terminado', 'blocked': 'Encargo necesita intervención', 'interrupted': 'Encargo interrumpido', 'queued': 'Encargo pendiente de reintento', 'cancelled': 'Encargo cancelado'}[status]
        event = workflow.record(data, title, request.get('opportunityId'), operation.get('actor', 'Agente'), proof)
        event['requestId'] = request['id']


def interrupt(data, operation, workflow):
    """An explicit stop records continuity; silence alone never releases ownership."""
    import agent_runner
    request = next((item for item in workflow.state(data)['requests'] if item['id'] == operation.get('id')), None)
    if not request or (request['status'] != 'running' and not interruption_unconfirmed(request)):
        raise ValueError('La interrupción explícita requiere un encargo en ejecución o una interrupción antigua sin confirmar')
    workflow.require_current_execution(request)
    if 'expectedUpdatedAt' not in operation or 'expectedExecutionId' not in operation:
        raise ValueError('Comprueba la última actividad y el propietario exactos antes de interrumpir')
    workflow.expect(request.get('updatedAt'), operation['expectedUpdatedAt'])
    previous_owner = request.get('executionId')
    workflow.expect(previous_owner, operation['expectedExecutionId'])
    owner = workflow.execution_id()
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError('Indica --execution-id con un identificador propio para registrar la interrupción')
    proof = operation.get('proof')
    if not isinstance(proof, str) or not proof.strip() or len(proof) > 15000:
        raise ValueError('La interrupción requiere una prueba concreta del último paso y de la parada')
    confirmation = operation.get('confirmation')
    if owner != previous_owner or previous_owner is None or confirmation is not None:
        if not isinstance(confirmation, str) or not confirmation.strip() or len(confirmation) > 15000:
            raise ValueError('Conserva la instrucción humana que confirma que se detuvo el chat anterior')
    execution = agent_runner.read_state()
    if agent_runner.view()['status'] in agent_runner.ACTIVE and (previous_owner is None or execution.get('id') == previous_owner):
        raise ValueError('La ejecución anterior sigue activa. Detén ese chat y comprueba su resultado antes de interrumpir')
    at = workflow.now()
    entry = {'at': at, 'byExecutionId': owner, 'previousExecutionId': previous_owner,
             'previousUpdatedAt': request.get('updatedAt'), 'startedAt': request.get('startedAt'),
             'previousResult': copy.deepcopy(request.get('result')), 'proof': proof}
    if 'deliveryCheck' in request:
        entry['previousDeliveryCheck'] = copy.deepcopy(request.pop('deliveryCheck'))
    if confirmation is not None:
        entry['confirmation'] = confirmation
    request.setdefault('interruptions', []).append(entry)
    if previous_owner is not None:
        invalidated = request.setdefault('invalidatedExecutionIds', [])
        if previous_owner not in invalidated:
            invalidated.append(previous_owner)
    summary = ('Envío interrumpido de forma explícita. Comprobar el portal antes de continuar.' if request['type'] == 'send'
               else 'Trabajo interrumpido de forma explícita. Comprobar el último paso antes de continuar.')
    request.update(status='interrupted', result=proof, updatedAt=workflow.request_timestamp(request), summary=summary, need='other')
    history = workflow.record(data, 'Encargo interrumpido de forma explícita', request.get('opportunityId'),
                              operation.get('actor', 'Agente'), proof)
    history['requestId'] = request['id']
    history['interruption'] = copy.deepcopy(entry)


def check_delivery(data, operation, workflow):
    """Record a real portal check without submitting or granting permission."""
    app = workflow.state(data)
    request = next((item for item in app['requests'] if item['id'] == operation.get('id')), None)
    if not request or request['type'] != 'send' or request['status'] not in ('blocked', 'interrupted', 'cancelled'):
        raise ValueError('Esta comprobación requiere un envío bloqueado, interrumpido o cancelado después de iniciarse')
    workflow.require_current_execution(request)
    workflow.expect(request['updatedAt'], operation.get('expected'))
    outcome, proof = operation.get('outcome'), operation.get('proof')
    if outcome not in ('sent', 'not_sent', 'unknown') or not isinstance(proof, str) or not proof.strip() or len(proof) > 15000:
        raise ValueError('Indica el resultado comprobado en el portal y su prueba concreta')
    package = next((item for item in app['packages'] if item['id'] == request.get('packageId')), None)
    if (not package or package.get('opportunityId') != request['opportunityId'] or
            operation.get('packageId') != package['id'] or operation.get('recipient') != package['payload']['recipient']):
        raise ValueError('Comprueba la oferta, el paquete y el destino exacto del envío')
    cancelled = request['status'] == 'cancelled'
    started = instant(request.get('startedAt'))
    authorization = request.get('authorizationAt', package.get('approvedAt'))
    approved = instant(authorization)
    if cancelled:
        if (not started or not approved or approved > started or
                started > datetime.now(timezone.utc) + timedelta(minutes=5)):
            raise ValueError('Un envío cancelado solo se concilia si conserva un inicio real autorizado del paquete original')
    workflow.verify_package(package)
    at = workflow.now()
    request['deliveryCheck'] = {'outcome': outcome, 'packageId': package['id'], 'at': at, 'proof': proof}
    if outcome == 'sent':
        authorization=validate_sent_time(request,package,operation.get('sentAt'))
        confirmation = operation.get('confirmation')
        if not isinstance(confirmation, str) or not confirmation.strip():
            raise ValueError('La confirmación necesita la fecha real, la prueba del portal y el envío original autorizado')
        if any(event['type'] == 'sent' and event['opportunityId'] == request['opportunityId'] for event in data['events']):
            raise ValueError('Esta solicitud ya tiene un envío registrado; concilia la prueba sin duplicarlo')
        if any(item['id'] != request['id'] and item['type'] == 'send' and item.get('opportunityId') == request['opportunityId']
               and item['status'] == 'running' for item in app['requests']):
            raise ValueError('Otro envío de esta oferta sigue en ejecución. Detén ese intento y comprueba su resultado antes de conciliar')
        archived_cv = 'data/packages/' + package['id'] + '/cv.pdf'
        event = {'id': 'recovered-' + digest([request['id'], package['id']])[:24], 'type': 'sent',
                 'opportunityId': request['opportunityId'], 'packageId': package['id'],
                 'at': operation['sentAt'], 'proof': proof, 'confirmation': confirmation,
                 'authorization': authorization, 'historyChecked': True, 'cv': archived_cv,
                 'cvHash': package['payload']['cvHash'], 'archivedCV': archived_cv,
                 'recovered': True}
        data['events'].append(event)
        row = workflow.row_for(data, request['opportunityId'])
        event.update(source=row.get('Fuente'), family=row.get('Familia'), cohort=operation['sentAt'][:7])
        from stubbs_jobs import excel_day
        row['CV usado'] = archived_cv
        row['Fecha candidatura'] = excel_day(operation['sentAt'])
        if row['Estado'] not in workflow.CLOSED and row['Estado'] not in ('Entrevista', 'Oferta'):
            row['Estado'] = 'Enviada'
            row['Siguiente paso'] = 'Envío confirmado al recuperar el seguimiento. Esperar novedades.'
        request.update(status='done', updatedAt=workflow.request_timestamp(request), result=proof, summary='Envío confirmado en el portal; no se repitió el formulario.')
        request.pop('need',None)
        history = workflow.record(data, 'Envío confirmado', request['opportunityId'], operation.get('actor', 'Agente'), proof, package['id'])
        history['requestId'] = request['id']
        for other in app['requests']:
            if (other['id'] == request['id'] or other['type'] != 'send' or
                    other.get('opportunityId') != request['opportunityId'] or other['status'] != 'queued'):
                continue
            other.update(status='cancelled', updatedAt=workflow.request_timestamp(other),
                         result='El envío original se confirmó en el portal. No repetir la solicitud. ' + proof)
            other_package = next((item for item in app['packages'] if item['id'] == other.get('packageId')), None)
            if other_package and other_package.get('approvedAt') and not other_package.get('revokedAt'):
                other_package['revokedAt'] = at
            cancelled_history = workflow.record(data, 'Envío duplicado cancelado al conciliar', request['opportunityId'],
                                                operation.get('actor', 'Agente'), other['result'], other.get('packageId'))
            cancelled_history['requestId'] = other['id']
    else:
        if cancelled:
            summary = ('El portal confirma que no se envió. El encargo sigue cancelado; no se reintentará.' if outcome == 'not_sent'
                       else 'El portal no permite confirmar el envío. El encargo sigue cancelado; no repetir la solicitud.')
        else:
            summary = ('El portal confirma que no se envió. Falta revalidar el permiso antes de continuar.' if outcome == 'not_sent'
                       else 'El portal no permite confirmar el envío. No repetir la solicitud.')
        request.update(updatedAt=workflow.request_timestamp(request), summary=summary, need='other')
        workflow.record(data, 'Resultado del envío comprobado', request['opportunityId'], operation.get('actor', 'Agente'), proof, package['id'])


def recover_backup(data, operation, workflow):
    """Restoring history never revives old delivery permissions or task owners."""
    original = workflow.DATA / 'recovery-original.json'
    if (not original.is_file() or original.is_symlink() or not data.get('_baseHash') or
            digest(original.read_bytes()) != data['_baseHash'] or
            operation.get('originalHash') != data['_baseHash']):
        raise ValueError('La recuperación solo se aplica al registro original comprobado de una copia aislada')
    if type(operation.get('expectedRevision')) is not int:
        raise ValueError('La recuperación necesita la revisión original comprobada')
    workflow.expect(data['revision'], operation.get('expectedRevision'))
    app = workflow.state(data)
    at = workflow.now()
    for package in app['packages']:
        if package.get('approvedAt') and not package.get('revokedAt'):
            package['revokedAt'] = at
    for draft in app['drafts'].values():
        if draft.get('review'):
            draft.setdefault('recoveryReviews', []).append(copy.deepcopy(draft.pop('review')))
    for request in app['requests']:
        if request['type'] == 'send' and request['status'] not in ('done', 'cancelled'):
            request.update(status='cancelled', updatedAt=workflow.request_timestamp(request), result='Copia recuperada. El envío requiere una nueva revisión y autorización.')
        elif request['status'] == 'running':
            request.update(status='interrupted', updatedAt=workflow.request_timestamp(request), result='Copia recuperada. Comprobar el último paso en el chat antes de continuar.')
    for selection in app.get('selections', {}).values():
        if selection.get('selected'):
            selection['mode'] = 'review'
    setup = app.get('onboarding')
    if setup and not app.get('setupComplete', True):
        from onboarding import initial
        fresh = initial()
        fresh.update(revision=setup.get('revision', 0) + 1, draft=copy.deepcopy(setup.get('draft', {})), updatedAt=at)
        app['onboarding'] = fresh
    workflow.record(data, 'Copia recuperada', actor='Sistema', detail=operation['proof'])


def handle(data, operation):
    import app_workflow
    {'ui-request-update': update, 'ui-request-interrupt': interrupt, 'ui-delivery-check': check_delivery,
     'ui-recover-backup': recover_backup}[operation['kind']](data, operation, app_workflow)
