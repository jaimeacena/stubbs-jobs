"""Immutable, scoped browser checks owned by an actual discovery execution."""
import copy
from datetime import datetime, timezone
from urllib.parse import urlsplit

from state_support import instant
from stubbs_jobs_core import canonical_url, digest

OUTCOMES = {'reviewed': 'ok', 'partial': 'partial', 'blocked': 'blocked', 'unsupported': 'unsupported'}


def configured_url(source):
    if source.get('url'):
        return source['url']
    board = source.get('board')
    if isinstance(board, str) and board and source.get('kind') == 'greenhouse':
        return 'https://job-boards.greenhouse.io/' + board
    if isinstance(board, str) and board and source.get('kind') == 'ashby':
        return 'https://jobs.ashbyhq.com/' + board
    return None


def _source_identity(url):
    parts = urlsplit(canonical_url(url))
    host = parts.hostname.removeprefix('www.')
    if host == 'boards.greenhouse.io':
        host = 'job-boards.greenhouse.io'
    return host, parts.path, parts.query


def source_key(url):
    return 'manual-' + digest(_source_identity(url))[:16]


def _text(operation, name, maximum):
    value = operation.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('La revisión de fuente necesita ' + name + ' concreto y válido')
    return value.strip()


def record(data, operation, workflow):
    from personalization import validate_public_source_url, source_allowed
    request_id = _text(operation, 'requestId', 200)
    request = next((item for item in workflow.state(data)['requests'] if item['id'] == request_id), None)
    if not request or request.get('type') != 'discovery' or request.get('status') != 'running':
        raise ValueError('La revisión requiere un encargo de búsqueda realmente iniciado')
    owner = workflow.execution_id()
    if not isinstance(owner, str) or not owner.strip() or not request.get('executionId'):
        raise ValueError('La revisión requiere --execution-id propio y un propietario registrado')
    workflow.require_owner(request)
    if 'expectedUpdatedAt' not in operation or 'expectedExecutionId' not in operation:
        raise ValueError('Comprueba la última actividad y el propietario de la búsqueda')
    workflow.expect(request.get('updatedAt'), operation['expectedUpdatedAt'])
    workflow.expect(request.get('executionId'), operation['expectedExecutionId'])
    identifier = _text(operation, 'id', 200)
    url = _text(operation, 'sourceUrl', 2000)
    validate_public_source_url(url)
    from search_profiles import discovery_data
    if not source_allowed(discovery_data(data,request),url):raise ValueError('Esta web no está entre las fuentes exclusivas de esta búsqueda')
    name = _text(operation, 'name', 200)
    checked_at = _text(operation, 'checkedAt', 100)
    recorded_at=datetime.now(timezone.utc).isoformat(timespec='microseconds')
    checked, started = instant(checked_at), instant(request.get('startedAt'))
    recorded = instant(recorded_at)
    if not checked or not started or not recorded or not started <= checked <= recorded:
        raise ValueError('La fecha comprobada requiere zona horaria y debe estar dentro de esta búsqueda')
    scope = _text(operation, 'scope', 2000)
    proof = _text(operation, 'proof', 15000)
    outcome = operation.get('outcome')
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise ValueError('Indica reviewed, partial, blocked o unsupported para la revisión')
    issues = operation.get('issues')
    if not isinstance(issues, list) or len(issues) > 20 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 1000 for item in issues):
        raise ValueError('Las incidencias requieren una lista de textos concretos')
    if outcome == 'reviewed' and issues:
        raise ValueError('Una revisión con incidencias debe declarar cobertura parcial o un bloqueo')
    if outcome != 'reviewed' and not issues:
        raise ValueError('Explica la incidencia que impide completar el alcance de la revisión')
    result = {'id': identifier, 'requestId': request_id, 'executionId': owner,
              'sourceId': source_key(url), 'sourceUrl': canonical_url(url), 'name': name,
              'checkedAt': checked_at, 'scope': scope, 'outcome': outcome,
              'issues': [item.strip() for item in issues], 'proof': proof}
    records = workflow.state(data).setdefault('sourceReviews', [])
    previous = next((item for item in records if item['id'] == identifier), None)
    if previous:
        if {key: previous.get(key) for key in result} != result:
            raise workflow.Conflict('Esta comprobación ya existe con otro contenido; conserva el original y usa otro ID')
        return
    result['recordedAt'] = recorded_at
    records.append(result)
    event = workflow.record(data, 'Fuente revisada desde el navegador', actor=operation.get('actor', 'Agente'),
                            detail=name + ': ' + scope, artifact=identifier)
    event['requestId'] = request_id


def handle(data, operation):
    if operation.get('kind') != 'ui-source-review':
        return False
    import app_workflow
    record(data, operation, app_workflow)
    return True


def snapshot(data, request, at, configuredSources=()):
    """Freeze this request's declared checks; never infer a whole-site review."""
    started, finished = instant(request.get('startedAt')), instant(at)
    if not started or not finished:
        return {'reviews': [], 'health': [], 'publicSources': []}
    configured = {}
    for source in configuredSources:
        try:
            configured[_source_identity(configured_url(source))] = source
        except (KeyError, TypeError, ValueError):
            continue
    reviews, latest, sources, successes = [], {}, {}, {}
    for stored in data.get('app', {}).get('sourceReviews', []):
        checked = instant(stored.get('checkedAt'))
        if stored.get('requestId') != request.get('id') or not checked or not started <= checked <= finished:
            continue
        item = copy.deepcopy(stored)
        source = configured.get(_source_identity(item['sourceUrl']), {})
        key = source.get('id') or item['sourceId']
        item['coverageSourceId'] = key
        reviews.append(item)
        sources[key] = {'id': key, 'company': item['name'], 'url': item['sourceUrl']}
        if item['outcome'] == 'reviewed' and (key not in successes or instant(successes[key]) <= checked):
            successes[key] = item['checkedAt']
        check = {'sourceId': key, 'company': item['name'], 'sourceUrl': item['sourceUrl'],
                 'status': OUTCOMES[item['outcome']], 'checkedAtUtc': item['checkedAt'],
                 'lastSuccessUtc': item['checkedAt'] if item['outcome'] == 'reviewed' else None,
                 'errors': list(item['issues']), 'scope': item['scope'], 'method': 'manual',
                 'requestId': item['requestId'], 'reviewId': item['id'],
                 'proof': item['proof'], 'executionId': item['executionId']}
        if key not in latest or instant(latest[key]['checkedAtUtc']) <= checked:
            latest[key] = check
    for key, check in latest.items():
        check['lastSuccessUtc'] = successes.get(key)
    return {'reviews': reviews, 'health': list(latest.values()), 'publicSources': list(sources.values())}
