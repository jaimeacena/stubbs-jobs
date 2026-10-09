"""Dated ad availability and application follow-up, without network or scheduling effects."""
import copy
from datetime import datetime, timedelta, timezone
from stubbs_jobs_core import canonical_url, digest, identity, now
from state_support import instant

BUSINESS = {'sent': 'Enviada', 'response': 'Pendiente de empresa', 'interview': 'Entrevista',
            'offer': 'Oferta', 'rejected': 'Rechazada', 'closed': 'Cerrada'}
CLOSED_SIGNALS = {'not_accepting', 'expired_notice', 'withdrawn_notice', 'filled_notice'}
REASONS = {'expired': 'Anuncio expirado', 'withdrawn': 'Anuncio retirado', 'filled': 'Puesto cubierto',
           'not_accepting': 'Anuncio cerrado a nuevas solicitudes',
           'unspecified': 'Proceso cerrado por la empresa; motivo no indicado',
           'cancelled': 'Proceso cancelado', 'user': 'Seguimiento cerrado por ti',
           'no_response': 'Seguimiento cerrado por ti por falta de respuesta'}
CHECK_DAYS = 7


def history_view(data):
    """Attach dated facts to a copy; never reinterpret or rewrite stored history."""
    app = data.get('app', {})
    items = copy.deepcopy(app.get('history', []))
    for scope, store, title in (
            ('availability', 'availabilityChecks', 'Disponibilidad comprobada'),
            ('followup', 'followupChecks', 'Seguimiento comprobado')):
        for key, records in app.get(store, {}).items():
            rows = [h for h in items if h.get('opportunityId') == key and h.get('title') == title]
            matches = {}
            used = set()
            # New records carry an exact identity. Legacy writes appended one
            # history row per check, in the same order, retaining the same proof.
            for index, record in enumerate(records):
                exact = [h for h in rows if h.get('checkId') == record.get('id') and record.get('id')]
                if len(exact) == 1:
                    matches[index] = exact[0]; used.add(exact[0]['id'])
            proofs = {r.get('proof') for r in records if r.get('proof')}
            for proof in proofs:
                pending = [(i, r) for i, r in enumerate(records) if i not in matches and r.get('proof') == proof]
                candidates = [h for h in rows if h['id'] not in used and h.get('detail') == proof]
                if len(pending) == len(candidates):
                    for (index, _), row in zip(pending, candidates):
                        matches[index] = row; used.add(row['id'])
            for index, record in enumerate(records):
                at = record.get('observedAt')
                if not instant(at):
                    continue
                row = matches.get(index)
                if row is None:
                    candidates = [h for h in rows if h['id'] not in used and instant(h.get('at')) == instant(at)
                                  and (not h.get('detail') or not record.get('proof') or h['detail'] == record['proof'])]
                    if len(candidates) == 1:
                        row = candidates[0]; used.add(row['id'])
                if row is None:
                    row = {'id': 'check-view:' + scope + ':' + key + ':' + (record.get('id') or str(index)),
                           'opportunityId': key, 'title': title, 'actor': 'Registro', 'at': at}
                    items.append(row)
                row['recordedAt'] = row.get('at')
                row['at'] = at
                row['activity'] = {'kind': scope, 'checkId': record.get('id'),
                                   'outcome': record.get('outcome'), 'sourceUrl': record.get('sourceUrl'),
                                   'observedAt': at}
    for item in items:
        events = [e for e in data.get('events', []) if e.get('opportunityId') == item.get('opportunityId')]
        exact = [e for e in events if e.get('id') == item.get('eventId') and item.get('eventId')]
        if not exact and item.get('title') in ('Envío confirmado', 'Solicitud enviada'):
            exact = [e for e in events if e.get('type') == 'sent' and
                     (item.get('packageId') and item['packageId'] == e.get('packageId') or
                      instant(item.get('at')) and instant(item.get('at')) == instant(e.get('at')) or
                      item.get('detail') and item['detail'] == e.get('proof'))]
        if len(exact) == 1:
            event = exact[0]
            item['activity'] = {'kind': 'event', 'type': event.get('type'), 'scope': event.get('scope'),
                                'packageId': event.get('packageId'), 'sourceUrl': event.get('sourceUrl')}
        request = next((r for r in app.get('requests', []) if r.get('id') == item.get('requestId')), None)
        creation_type = {'Investigación solicitada': 'investigate', 'Revisión solicitada': 'review',
                         'Envío puesto en cola': 'send', 'Búsqueda solicitada': 'discovery'}.get(item.get('title'))
        if request is None and creation_type and instant(item.get('at')):
            candidates = [r for r in app.get('requests', []) if r.get('type') == creation_type
                          and r.get('opportunityId') == item.get('opportunityId') and instant(r.get('createdAt'))
                          and abs((instant(item['at']) - instant(r['createdAt'])).total_seconds()) <= 1]
            if len(candidates) == 1:
                request = candidates[0]
                item['requestId'] = request['id']
        if request and not item.get('activity'):
            item['activity'] = {'kind': 'task', 'type': request.get('type'), 'purpose': request.get('purpose')}
    return items


def latest(items):
    valid = [item for item in items if instant(item.get('at') or item.get('observedAt'))]
    return max(valid, key=lambda item: (instant(item.get('at') or item.get('observedAt')),
               {'closed': 5, 'rejected': 5, 'offer': 4, 'interview': 3, 'response': 2, 'sent': 1}.get(item.get('type'), 0)), default=None)


def business_events(data, key):
    sent = any(e.get('opportunityId') == key and e.get('type') == 'sent' for e in data['events'])
    return [e for e in data['events'] if e.get('opportunityId') == key and e.get('type') in BUSINESS
            and not (sent and e.get('scope') == 'advertisement')]


def achievement(data, row):
    """A job offer ends the app's cycle; later decisions cannot undo that fact."""
    archive = data.get('app', {}).get('offerArchives', {}).get(row['ID'], {})
    offers = [e for e in business_events(data, row['ID']) if e['type'] == 'offer']
    first = min(offers, key=lambda e: instant(e.get('at')) or datetime.max.replace(tzinfo=timezone.utc), default=None)
    if archive.get('outcome') == 'achieved':
        return {'at': first['at'] if first else archive.get('at'), 'label': archive.get('reason'), 'proof': archive.get('reason')}
    if first:
        return {'at': first['at'], 'label': 'La empresa te ofrece el puesto.', 'proof': first.get('proof')}
    if row['Estado'] in ('Oferta', 'Lograda'):
        return {'at': None, 'label': 'Puesto ofrecido por la empresa.', 'proof': None}
    return None


def project_event(data, row, event):
    """Backfilled news stays in history; only the newest business fact changes the projection."""
    if event['type'] not in BUSINESS:
        return
    if event['type'] != 'offer' and achievement(data, row):
        return
    current = latest(business_events(data, row['ID']))
    if current and current.get('id') == event.get('id'):
        row['Estado'] = BUSINESS[event['type']]


def validate_event(data, row, event):
    observed = instant(event.get('at'))
    if observed and observed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Una noticia requiere su fecha real, sin fechas futuras')
    sent = latest([e for e in business_events(data, row['ID']) if e['type'] == 'sent'])
    if sent and observed and event['type'] in ('response', 'interview', 'offer', 'rejected') and observed < instant(sent['at']):
        raise ValueError('La respuesta no puede ser anterior al envío confirmado')
    if event['type'] != 'closed':
        return
    if event.get('scope') not in ('application', 'advertisement'):
        raise ValueError('Distingue cierre de anuncio y cierre de tu candidatura; usa una comprobación de seguimiento')
    canonical_url(event.get('sourceUrl', ''))
    if event.get('scope') == 'application':
        if not event.get('applicationReference') or event.get('reason') not in ('cancelled', 'filled', 'unspecified') or not any(e['type'] == 'sent' for e in business_events(data, row['ID'])):
            raise ValueError('El cierre de candidatura necesita un envío y una comunicación identificada')
    elif {'not_accepting':'not_accepting', 'expired_notice':'expired', 'withdrawn_notice':'withdrawn', 'filled_notice':'filled'}.get(event.get('signal')) != event.get('reason'):
        raise ValueError('El cierre de anuncio necesita un aviso expreso, no un fallo de acceso')


def archive_outcome(data, row):
    archive = data.get('app', {}).get('offerArchives', {}).get(row['ID'], {})
    if achievement(data, row):
        return 'achieved'
    event = latest(business_events(data, row['ID']))
    if archive and event and event['type'] == 'rejected' and instant(archive.get('at')) and instant(event['at']) > instant(archive['at']):
        return 'rejected'
    # Legacy manual rejection meant closing follow-up, not an employer decision.
    if archive.get('outcome') == 'rejected' and archive.get('source') not in ('employer', 'user_reported'):
        return 'closed'
    return archive.get('outcome')


def view(data, row, at=None):
    at = at or datetime.now(timezone.utc)
    app = data.get('app', {}); key = row['ID']; events = business_events(data, key)
    sent = latest([e for e in events if e['type'] == 'sent'])
    reply = latest([e for e in events if e['type'] in ('response', 'interview', 'offer', 'rejected')])
    archive = app.get('offerArchives', {}).get(key, {})
    achieved = achievement(data, row)
    event = latest(events)
    ad = copy.deepcopy(latest(app.get('availabilityChecks', {}).get(key, [])))
    checks = app.get('followupChecks', {}).get(key, [])
    check = copy.deepcopy(latest(checks))
    if ad:
        ad['fresh'] = at - instant(ad['observedAt']) <= timedelta(days=CHECK_DAYS)
    if check:
        check['fresh'] = at - instant(check['observedAt']) <= timedelta(days=CHECK_DAYS)
    closed = bool(achieved) or row['Estado'] in ('Cerrada', 'Rechazada', 'Descartada', 'Lograda', 'Oferta') or bool(archive)
    closure = None
    employer_after_archive = bool(archive and archive.get('outcome') != 'achieved' and event and event['type'] in ('rejected', 'closed') and instant(archive.get('at')) and instant(event['at']) > instant(archive['at']))
    if achieved:
        closure = {'reason': 'achieved', **achieved}
    elif archive and not employer_after_archive:
        closure = {'reason': archive.get('closureReason', 'user' if sent else 'discarded'),
                   # An automatic minimums discard keeps its stated reason; it was not the person's choice.
                   'label': archive.get('reason') if archive.get('source') == 'minimums' and archive.get('reason') or archive.get('source') == 'user_reported' and archive.get('outcome') in ('achieved', 'rejected') else REASONS.get(archive.get('closureReason'), 'Seguimiento cerrado por ti' if sent else 'Oferta descartada por ti'),
                   'at': archive.get('at'), 'proof': archive.get('reason')}
    elif closed and event and event['type'] in ('closed', 'rejected'):
        closure = {'reason': event.get('reason', event['type']),
                   'label': 'Rechazo comunicado por la empresa' if event['type'] == 'rejected' else REASONS.get(event.get('reason'), 'Cierre registrado; motivo sin concretar'),
                   'at': event['at'], 'proof': event.get('proof')}
    elif closed:
        closure = {'reason': 'legacy', 'label': 'Cierre anterior registrado; consulta su prueba', 'at': None}
    dates = [x.get('at') for x in (sent, reply) if x] + ([check['observedAt']] if check else [])
    if not sent and ad and ad['outcome'] == 'unknown':
        dates.append(ad['observedAt'])
    anchor = max(dates, key=instant, default=None)
    plan = app.get('followupPlans', {}).get(key, {})
    planned = plan.get('nextCheckAt') if instant(plan.get('at')) and anchor and instant(plan['at']) >= instant(anchor) else None
    next_at = (planned or (instant(anchor) + timedelta(days=CHECK_DAYS)).isoformat(timespec='seconds')) if anchor and (sent or ad and ad['outcome'] == 'unknown') and not closed else None
    return {'availability': ad, 'closure': closure, 'achievedAt': achieved.get('at') if achieved else None, 'sentAt': sent.get('at') if sent else None,
            'lastResponseAt': reply.get('at') if reply else None, 'lastCheck': check,
            'nextCheckAt': next_at, 'checkDue': bool(next_at and instant(next_at) <= at),
            'owner': 'agent' if next_at else 'closed' if closed else None,
            'label': 'Estado actualizado por el portal' if reply and reply.get('channel') == 'portal' else 'Respuesta registrada' if reply else 'Sin respuesta conocida' if sent else None,
            'plan': copy.deepcopy(plan) or None,
            'canReopen': bool(not achieved and sent and archive and event and event['type'] in ('response', 'interview', 'offer') and instant(archive.get('at')) and instant(event['at']) > instant(archive['at'])),
            'monitoring': False}


def reconcile(data, workflow):
    """Resolve obsolete preparation, preserving receipts, uncertain sends and running ownership."""
    app = workflow.state(data)
    for row in data['sheets']['Oportunidades']:
        key = row['ID']; sent = any(e.get('type') == 'sent' for e in business_events(data, key))
        original = latest([e for e in data['events'] if e.get('opportunityId') == key and e.get('type') in ('closed', 'rejected')])
        personal = latest(business_events(data, key))
        if sent and row['Estado'] == 'Cerrada' and not workflow.archived(data, key) and original and original.get('scope') == 'advertisement' and personal:
            row['Estado'] = BUSINESS[personal['type']]
        closed = row['Estado'] in workflow.CLOSED or workflow.archived(data, key) or achievement(data, row)
        if not closed and not sent:
            continue
        for request in app['requests']:
            if request.get('opportunityId') != key or request.get('interpretationOnly') or request['status'] not in ('queued', 'blocked', 'interrupted'):
                continue
            if request['type'] not in ('review', 'investigate', 'send') or not closed and request.get('purpose') == 'followup':
                continue
            if request['type'] == 'send' and request['status'] != 'queued':
                continue
            request.update(status='cancelled', updatedAt=workflow.request_timestamp(request),
                           result='Preparación resuelta: envío ya confirmado.' if sent else 'Tarea resuelta: oferta cerrada.')
            request.pop('need', None)
            workflow.record(data, 'Tarea sin efecto pendiente', key, 'Sistema', request['result'])['requestId'] = request['id']
        if closed:
            app.get('selections', {}).pop(key, None)
            for package in app['packages']:
                if package.get('opportunityId') == key and package.get('approvedAt') and not package.get('revokedAt') and not any(e.get('packageId') == package['id'] and e['type'] == 'sent' for e in data['events']):
                    package['revokedAt'] = now()
        for block in data['blocks']:
            preparation = block.get('id') in ('ui-answers-' + key, 'send-' + key, 'profile')
            if (block.get('opportunityId') == key and block.get('status') == 'open'
                    and (closed or preparation)):
                block.update(status='resolved', resolution='Oferta cerrada' if closed else 'Envío confirmado')


def request_view(data, request, workflow):
    result = copy.deepcopy(request)
    key = request.get('opportunityId')
    result['actionOwner'] = 'user' if request.get('need') in ('answers', 'access', 'decision', 'contact') else 'agent'
    if key and any(row['ID'] == key for row in data['sheets']['Oportunidades']) and request.get('need') == 'answers' and request.get('status') == 'blocked':
        draft = workflow.draft(data, key)
        missing = [workflow.context.definitions(data, key)[k]['label'] for k in draft.get('requiredAnswers', [])
                   if workflow.answers(data, key).get(k) in (None, '')]
        result['summary'] = ('Faltan tus respuestas: ' + '; '.join(missing)) if missing else 'Respuestas guardadas. Falta la comprobación del agente.'
        result['actionOwner'] = 'user' if missing else 'agent'
    return result


def handle(data, operation, workflow):
    kind = operation['kind']
    if kind not in ('ui-availability-check', 'ui-followup-check', 'ui-followup-plan', 'ui-lifecycle-reconcile'):
        return False
    if kind == 'ui-lifecycle-reconcile':
        workflow.expect(data['revision'], operation.get('expectedRevision'))
        if not operation.get('proof'):
            raise ValueError('La conciliación necesita una explicación')
        reconcile(data, workflow)
        workflow.record(data, 'Seguimiento conciliado', actor=operation.get('actor', 'Sistema'), detail=operation['proof'])
        return True
    key = operation.get('opportunityId'); row = workflow.row_for(data, key)
    if kind in ('ui-followup-check', 'ui-followup-plan') and achievement(data, row):
        raise ValueError('La solicitud está lograda; su seguimiento ha terminado')
    if kind == 'ui-followup-plan':
        plans = workflow.state(data).setdefault('followupPlans', {})
        workflow.expect(plans.get(key), operation.get('expected'))
        due = instant(operation.get('nextCheckAt'))
        if not due or due <= datetime.now(timezone.utc) or not operation.get('proof'):
            raise ValueError('Indica una próxima comprobación futura y su motivo')
        if not any(e['type'] == 'sent' for e in business_events(data, key)) or row['Estado'] in workflow.CLOSED or workflow.archived(data, key):
            raise ValueError('Solo se programa una revisión de una candidatura abierta y enviada')
        plans[key] = {'nextCheckAt': operation['nextCheckAt'], 'proof': operation['proof'], 'at': now()}
        workflow.record(data, 'Próxima comprobación acordada', key, operation.get('actor', 'Usuario'), operation['proof'])
        return True
    observed = instant(operation.get('observedAt'))
    if not observed or observed > datetime.now(timezone.utc) + timedelta(minutes=5) or not isinstance(operation.get('proof'), str) or not operation['proof'].strip():
        raise ValueError('La comprobación necesita fecha real con zona horaria y prueba, sin fechas futuras')
    canonical_url(operation.get('sourceUrl', ''))
    if identity(operation.get('vacancyUrl', '')) != identity(row['URL original']):
        raise ValueError('Comprueba esta misma vacante, no una publicación parecida')
    outcome = operation.get('outcome'); app = workflow.state(data)
    store = app.setdefault('availabilityChecks' if kind == 'ui-availability-check' else 'followupChecks', {})
    records = store.setdefault(key, [])
    record = {k: copy.deepcopy(operation.get(k)) for k in ('outcome', 'observedAt', 'sourceUrl', 'vacancyUrl', 'proof', 'signal', 'reason', 'applicationReference')}
    record['id'] = digest(record); record['at'] = operation['observedAt']
    if any(item['id'] == record['id'] for item in records):
        return True
    if kind == 'ui-availability-check':
        if outcome not in ('open', 'closed', 'unknown'):
            raise ValueError('Disponibilidad: open, closed o unknown')
        if outcome == 'closed' and (operation.get('signal') not in CLOSED_SIGNALS or
                {'not_accepting':'not_accepting', 'expired_notice':'expired', 'withdrawn_notice':'withdrawn', 'filled_notice':'filled'}[operation['signal']] != operation.get('reason')):
            raise ValueError('Un fallo de acceso o ausencia en búsquedas no confirma un cierre')
        records.append(record)
        if latest(records)['id'] == record['id'] and outcome == 'open' and row['Estado'] == 'Cerrada' and not workflow.archived(data, key):
            previous = latest([e for e in data['events'] if e.get('opportunityId') == key and e.get('type') in BUSINESS])
            if previous and previous.get('scope') == 'advertisement' and observed > instant(previous['at']) and not any(e['type'] == 'sent' for e in business_events(data, key)):
                row['Estado'] = 'Investigar'
                workflow.record(data, 'Anuncio disponible de nuevo', key, operation.get('actor', 'Agente'), 'Nueva disponibilidad comprobada; selección y permisos anteriores no recuperados.')
        if latest(records)['id'] == record['id'] and outcome == 'closed' and not any(e['type'] == 'sent' for e in business_events(data, key)):
            event = {'id': 'availability-' + record['id'], 'type': 'closed', 'opportunityId': key, 'at': operation['observedAt'],
                     'proof': operation['proof'], 'reason': operation['reason'], 'sourceUrl': operation['sourceUrl'], 'scope': 'advertisement'}
            data['events'].append(event); project_event(data, row, event)
        workflow.record(data, 'Disponibilidad comprobada', key, operation.get('actor', 'Agente'), operation['proof'])['checkId'] = record['id']
    else:
        sent = latest([e for e in business_events(data, key) if e['type'] == 'sent'])
        if not sent:
            raise ValueError('El seguimiento requiere un envío confirmado')
        if observed < instant(sent['at']):
            raise ValueError('La consulta de tu candidatura no puede ser anterior a su envío')
        if outcome not in ('waiting', 'reviewing', 'unknown', 'rejected', 'closed'):
            raise ValueError('Resultado de seguimiento no válido')
        if outcome in ('reviewing', 'rejected', 'closed') and not operation.get('applicationReference'):
            raise ValueError('Identifica tu candidatura; un anuncio no confirma su resultado')
        if outcome == 'closed':
            record['reason'] = operation.get('reason') if operation.get('reason') is not None else 'unspecified'
        if outcome == 'closed' and record['reason'] not in ('cancelled', 'filled', 'unspecified'):
            raise ValueError('Indica el motivo comunicado del cierre')
        records.append(record)
        if outcome in ('reviewing', 'rejected', 'closed'):
            event = {'id': 'followup-' + record['id'], 'type': 'response' if outcome == 'reviewing' else outcome, 'opportunityId': key, 'at': operation['observedAt'],
                     'proof': operation['proof'], 'reason': record.get('reason'), 'scope': 'application', 'channel': 'portal', 'sourceUrl': operation['sourceUrl']}
            data['events'].append(event); project_event(data, row, event)
        workflow.record(data, 'Seguimiento comprobado', key, operation.get('actor', 'Agente'), operation['proof'])['checkId'] = record['id']
    reconcile(data, workflow)
    return True
