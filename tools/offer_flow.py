"""Composite agent commands: prepare an offer, start its send and record the outcome.

Each command translates one short JSON description into the same writer
operations an agent would otherwise write by hand (21/10/2026). Fingerprints and
expected values are computed from the state left by the previous step, every
step is recorded as its own batch, and the caller saves only when all of them
succeed: a failure leaves the registry exactly as it was.
"""
import shutil
import uuid
from datetime import datetime, timezone

import app_workflow as workflow
import app_context
import stubbs_jobs
from stubbs_jobs_core import ROOT, digest

PREPARE_KEYS = {'requestId', 'observedAt', 'sourceUrl', 'start', 'facts', 'factsProof', 'evidence', 'assessment',
                'fit', 'cv', 'form', 'review', 'result'}
FORM_DRAFT = {'recipient': 'recipient', 'messageUsage': 'messageUsage', 'message': 'message', 'questions': 'questions',
              'requiredAnswers': 'requiredAnswers', 'formAnswerKeys': 'formAnswerKeys'}
FINISH_KEYS = {'outcome', 'at', 'proof', 'confirmation', 'summary', 'need', 'reapplicationAuthorization', 'form'}
OPEN = ('queued', 'running', 'blocked', 'interrupted')


class Steps:
    """Sequential writer batches on one in-memory registry, saved together by the caller."""

    def __init__(self, data, label):
        self.data, self.base, self.count, self.applied = data, label + '-' + uuid.uuid4().hex[:12], 0, []

    def apply(self, title, operation):
        self.count += 1
        try:
            stubbs_jobs.apply_batch(self.data, {'id': f'{self.base}-{self.count:02d}', 'operations': [operation]})
        except ValueError as exc:
            raise type(exc)(f'{title}: {exc}') from exc
        self.applied.append(title)


def _only(spec, allowed, name):
    if not isinstance(spec, dict):
        raise ValueError(name + ' debe ser un objeto JSON')
    unknown = set(spec) - allowed
    if unknown:
        raise ValueError(name + ': campos desconocidos ' + ', '.join(sorted(unknown)) + '. Revisa docs/operations.md')


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Falta ' + name)
    return value.strip()


def _request(data, case, types, request_id=None):
    requests = workflow.state(data)['requests']
    if request_id:
        found = next((r for r in requests if r['id'] == request_id), None)
        if not found or found.get('opportunityId') != case or found['type'] not in types:
            raise ValueError('Ese encargo no pertenece a esta oferta')
        return found
    owner = workflow.execution_id()
    candidates = [r for r in requests if r.get('opportunityId') == case and r['type'] in types
                  and r['status'] in OPEN and not r.get('interpretationOnly')]
    for status in ('running', 'queued', 'blocked', 'interrupted'):
        mine = [r for r in candidates if r['status'] == status and (status != 'running' or r.get('executionId') == owner)]
        if mine:
            return mine[-1]
    return None


def _start(steps, request, proof):
    if request['status'] == 'running':
        workflow.require_owner(request)
        return
    if request['status'] in ('blocked', 'interrupted'):
        steps.apply('Tarea en cola de nuevo', {'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': proof})
    steps.apply('Inicio de la tarea', {'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': proof})


def _current(data, request):
    # A successful batch replaces the registry objects: read the task again by its ID.
    return next(r for r in workflow.state(data)['requests'] if r['id'] == request['id'])


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def prepare(data, case, spec):
    """Facts, evidence, valuation, fit, CV, form and review of one offer in one call."""
    _only(spec, PREPARE_KEYS, 'La preparación')
    row = workflow.row_for(data, case)
    steps = Steps(data, 'prepare')
    observed = spec.get('observedAt') or _now()
    source = spec.get('sourceUrl') or row['URL original']
    request = _request(data, case, ('review', 'investigate'), spec.get('requestId'))
    if request:
        _start(steps, request, spec.get('start') or 'Inicio real de la preparación de la oferta con el comando prepare.')
    elif spec.get('result'):
        raise ValueError('No hay una tarea de preparación abierta para esta oferta; no se puede registrar su resultado')

    if spec.get('facts'):
        steps.apply('Datos del anuncio', {'kind': 'opportunity', 'id': case, 'values': spec['facts'],
                                          'proof': _text(spec.get('factsProof'), 'factsProof con lo leído en el anuncio')})
    for item in spec.get('evidence') or []:
        if not isinstance(item, dict):
            raise ValueError('Cada evidencia necesita condition, state y proof')
        steps.apply('Evidencia: ' + str(item.get('condition')),
                    {'kind': 'evidence', 'id': case, 'url': item.get('url', source), 'at': item.get('at', observed),
                     **{k: v for k, v in item.items() if k not in ('url', 'at')}})
    if spec.get('assessment'):
        import offer_quality
        assessment = dict(spec['assessment'])
        assessment.setdefault('observedAt', observed)
        steps.apply('Valoración', {'kind': 'ui-offer-assessment', 'opportunityId': case,
                                   'fingerprint': offer_quality.fingerprint(data, workflow.row_for(data, case)), **assessment})
    if spec.get('fit'):
        from offer_minimums import view as minimums
        fit = dict(spec['fit'])
        current = workflow.row_for(data, case)
        fit.setdefault('apply', minimums(data, current)['canApply'])
        steps.apply('Encaje con tus criterios', {'kind': 'ui-fit-review', 'opportunityId': case,
                                                 'fingerprint': app_context.fit_stamp(data, current), **fit})

    draft_values = {}
    cv = spec.get('cv')
    if cv:
        _only(cv, {'build', 'use', 'adaptation', 'reason'}, 'cv')
        if 'build' in cv:
            import build_cv
            build_cv.register(data, case, cv['build'])
            steps.applied.append('CV adaptado con build-cv')
        elif 'use' not in cv:
            # Keep the CV already assigned to the offer and only declare its adaptation.
            if cv.get('adaptation') not in workflow.CV_ADAPTATIONS:
                raise ValueError('Indica cv.adaptation: adapted (CV propio de esta oferta) o reused (CV general)')
            draft_values.update(cvAdaptation=cv['adaptation'], cvReason=_text(cv.get('reason'), 'cv.reason'))
        else:
            path = _text(cv.get('use'), 'cv.use con la ruta de un PDF de Currículums')
            from cv_retirement import catalog, retired
            document = next((d for d in catalog(data, ROOT) if d['path'] == path), None)
            if not document or not document.get('fingerprint'):
                raise ValueError('cv.use debe ser un PDF disponible en Currículums (cvLibrary de agent-status)')
            if retired(data, document['fingerprint']):
                raise ValueError('Ese CV está retirado; elige uno vigente')
            if workflow.row_for(data, case).get('CV preparado') != path:
                steps.apply('CV de la solicitud', {'kind': 'opportunity', 'id': case, 'values': {'CV preparado': path}})
            if cv.get('adaptation') not in workflow.CV_ADAPTATIONS:
                raise ValueError('Indica cv.adaptation: adapted (CV propio de esta oferta) o reused (CV general)')
            draft_values.update(cvAdaptation=cv['adaptation'], cvReason=_text(cv.get('reason'), 'cv.reason'))

    form = spec.get('form') or {}
    _only(form, set(FORM_DRAFT) | {'answers'}, 'form')
    draft_values.update({FORM_DRAFT[k]: v for k, v in form.items() if k in FORM_DRAFT})
    if draft_values:
        current = workflow.draft(data, case)
        if any(current.get(k) != v for k, v in draft_values.items()):
            steps.apply('Formulario y presentación', {'kind': 'ui-draft', 'opportunityId': case, 'values': draft_values,
                                                      'expected': {k: current.get(k) for k in draft_values}})
    answers = form.get('answers') or {}
    if answers:
        if not isinstance(answers, dict):
            raise ValueError('form.answers debe indicar cada pregunta y su respuesta')
        current = workflow.answers(data, case)
        changed = {k: v for k, v in answers.items() if current.get(k) != v}
        if changed:
            steps.apply('Respuestas del formulario', {'kind': 'ui-responses', 'opportunityId': case, 'values': changed,
                                                      'expected': {k: current.get(k) for k in changed}})

    review = spec.get('review')
    if review:
        _only(review, {'proof', 'checks'}, 'review')
        checks = review.get('checks') or {key: True for key in workflow.CHECKS}
        steps.apply('Revisión final del paquete', {'kind': 'ui-review', 'opportunityId': case,
                                                   'fingerprint': workflow.stamp(data, case), 'checks': checks,
                                                   'proof': _text(review.get('proof'), 'review.proof con lo comprobado en el formulario real')})

    result = spec.get('result')
    if result is None and review and request:
        result = {'status': 'done', 'proof': review['proof']}
    if result:
        _only(result, {'status', 'proof', 'summary', 'need'}, 'result')
        operation = {'kind': 'ui-request-update', 'id': request['id'], 'status': result.get('status'),
                     'proof': _text(result.get('proof'), 'result.proof')}
        for key in ('summary', 'need'):
            if key in result:
                operation[key] = result[key]
        steps.apply('Resultado de la tarea', operation)

    request = _current(data, request) if request else None
    missing = list(workflow.readiness(data, case))
    package = next((p for p in workflow.state(data)['packages'] if p['id'] == workflow.stamp(data, case)), None)
    sends = [r['id'] for r in workflow.state(data)['requests'] if r.get('opportunityId') == case
             and r['type'] == 'send' and r['status'] == 'queued']
    return {'opportunityId': case, 'steps': steps.applied, 'requestId': request['id'] if request else None,
            'requestStatus': request['status'] if request else None, 'missing': missing,
            'packageId': package['id'] if package else None,
            'authorized': bool(package and package.get('approvedAt') and not package.get('revokedAt')),
            'queuedSends': sends,
            'next': ('send-start --case ' + case) if sends else
                    'La persona revisa y autoriza el paquete en la app' if package and not missing else
                    'Completa lo indicado en missing' if missing else None}


def _package(data, request):
    package = next((p for p in workflow.state(data)['packages'] if p['id'] == request.get('packageId')), None)
    if not package:
        raise ValueError('El envío no tiene un paquete conservado')
    return package


def _authorization(data, case, package):
    choice = workflow.selection(data, case) or {}
    if package.get('approvalSource') == 'selection':
        text = 'Auto-solicitud elegida ' + ('por la persona' if not choice.get('mandate') else
                                            'con su indicación «' + choice['mandate']['text'] + '»')
        return text + f" ({choice.get('at')}); paquete autorizado tras la revisión el {package.get('approvedAt')}."
    return f"Paquete aprobado por la persona en la app el {package.get('approvedAt')}."


def send_start(data, case, proof=None):
    """Start the authorized send and return everything needed to fill the form."""
    steps = Steps(data, 'send-start')
    request = _request(data, case, ('send',))
    if not request:
        raise ValueError('No hay un envío autorizado en cola para esta oferta. Consulta eligibleContinuations o el permiso en agent-status')
    _start(steps, request, proof or 'Inicio real del envío: paquete, permiso, destino y vacante revalidados justo antes de transmitir.')
    package = _package(data, request)
    workflow.conserved_package(package)
    payload = package['payload']
    definitions = app_context.definitions(data, case)
    from personalization import cv_file_name
    upload_name = cv_file_name(data, workflow.row_for(data, case).get('Empresa'))
    folder = ROOT / 'outputs/envios' / digest(case)[:12]
    folder.mkdir(parents=True, exist_ok=True)
    upload = folder / upload_name
    shutil.copyfile(ROOT / 'data/packages' / package['id'] / 'cv.pdf', upload)
    keys = [k for k in payload.get('formAnswerKeys') or [] if k != 'minimumFixed' and k in payload['answers']]
    usage = payload.get('messageUsage')
    return {'opportunityId': case, 'steps': steps.applied, 'requestId': request['id'], 'packageId': package['id'],
            'company': payload['company'], 'title': payload['title'], 'url': payload['url'], 'recipient': payload['recipient'],
            'cvUpload': upload.relative_to(ROOT).as_posix(), 'cvArchived': f"data/packages/{package['id']}/cv.pdf",
            'answers': [{'key': k, 'label': definitions.get(k, {}).get('label', k), 'value': payload['answers'][k]} for k in keys],
            'message': payload['message'] if usage in ('form', 'email') else None, 'messageUsage': usage,
            'autoApply': {k: data['profile'].get(k) for k in workflow.AUTO_APPLY_FIELDS},
            'next': 'Rellena el formulario con este material y registra el resultado con send-finish --case ' + case}


def send_finish(data, case, spec):
    """Record the real outcome of the running send: a receipt, or a stop with its portal check."""
    _only(spec, FINISH_KEYS, 'El resultado del envío')
    steps = Steps(data, 'send-finish')
    request = next((r for r in workflow.state(data)['requests'] if r.get('opportunityId') == case and r['type'] == 'send'
                    and r['status'] == 'running'), None)
    if not request:
        raise ValueError('No hay un envío en curso para esta oferta; inícialo con send-start')
    workflow.require_owner(request)
    package = _package(data, request)
    outcome, proof = spec.get('outcome'), _text(spec.get('proof'), 'proof con lo que mostró el portal')
    if outcome == 'sent':
        at = spec.get('at') or _now()
        event = {'id': 'sent-' + digest([case, package['id'], at])[:24], 'opportunityId': case, 'type': 'sent', 'at': at,
                 'proof': proof, 'packageId': package['id'], 'cv': f"data/packages/{package['id']}/cv.pdf",
                 'authorization': _authorization(data, case, package), 'historyChecked': True,
                 'confirmation': _text(spec.get('confirmation'), 'confirmation con el mensaje o recibo del portal')}
        if spec.get('reapplicationAuthorization'):
            event['reapplicationAuthorization'] = spec['reapplicationAuthorization']
        steps.apply('Envío confirmado', {'kind': 'event', 'event': event})
        steps.apply('Tarea de envío terminada', {'kind': 'ui-request-update', 'id': request['id'], 'status': 'done', 'proof': proof})
    elif outcome in ('not_sent', 'unknown'):
        if spec.get('need') not in ('answers', 'access', 'decision', 'contact', 'other'):
            raise ValueError('Indica need: answers, access, decision, contact u other')
        steps.apply('Envío detenido', {'kind': 'ui-request-update', 'id': request['id'], 'status': 'blocked', 'proof': proof,
                                       'need': spec['need'], 'summary': _text(spec.get('summary'), 'summary con una frase para la persona')})
        current = _current(data, request)
        steps.apply('Comprobación del portal', {'kind': 'ui-delivery-check', 'id': request['id'], 'expected': current['updatedAt'],
                                                'outcome': outcome, 'proof': proof, 'packageId': package['id'],
                                                'recipient': package['payload']['recipient']})
        # The portal check writes a generic summary; keep the person's concrete reason.
        current = _current(data, request)
        steps.apply('Motivo para la persona', {'kind': 'ui-request-summary', 'id': request['id'],
                                               'expectedUpdatedAt': current['updatedAt'],
                                               'summary': spec['summary'].strip(), 'need': spec['need']})
        form = spec.get('form')
        if form:
            # New questions found on the portal reach the person in the app; answering them prepares the offer again.
            _only(form, {'questions', 'requiredAnswers', 'formAnswerKeys'}, 'form')
            draft = workflow.draft(data, case)
            steps.apply('Preguntas nuevas del formulario', {'kind': 'ui-draft', 'opportunityId': case, 'values': form,
                                                            'expected': {k: draft.get(k) for k in form}})
    else:
        raise ValueError('Indica outcome: sent (con confirmation), not_sent (no se pulsó el botón final) o unknown')
    return {'opportunityId': case, 'steps': steps.applied, 'requestId': request['id'], 'outcome': outcome}
