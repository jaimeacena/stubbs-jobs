"""Retire superseded CVs from future use while preserving exact historical files."""
import re
from datetime import datetime
from pathlib import PurePosixPath

from stubbs_jobs_core import digest, now


def valid_time(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def retired(data, fingerprint):
    return bool(fingerprint and fingerprint in data.get('app', {}).get('retiredCVs', {}))


def validate(data):
    records = data.get('app', {}).get('retiredCVs', {})
    if not isinstance(records, dict):
        raise ValueError('El registro de CV retirados no es válido')
    for key, record in records.items():
        if (not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key) or not isinstance(record, dict)
                or record.get('fingerprint') != key or not valid_time(record.get('retiredAt'))
                or not isinstance(record.get('reason'), str) or not record['reason'].strip() or len(record['reason']) > 1000
                or not isinstance(record.get('documents'), list) or not record['documents']):
            raise ValueError('El CV retirado necesita identidad, fecha, motivo y documentos')
        for document in record['documents']:
            path = document.get('path') if isinstance(document, dict) else None
            if (not isinstance(path, str) or '\\' in path or not path.startswith('outputs/')
                    or '..' in PurePosixPath(path).parts or not path.endswith('.pdf')):
                raise ValueError('Ruta de CV retirado no válida')


def catalog(data, root):
    """Read known originals, including retired ones, with fresh hashes for writes."""
    import cv_usage
    documents = [dict(item) for item in data.get('app', {}).get('cvLibrary', [])]
    documents += [{'name': p.name, 'path': p.relative_to(root).as_posix()}
                  for p in cv_usage.legacy_paths(data, root)]
    for document in documents:
        path = (root / document['path']).resolve()
        if not path.is_relative_to((root / 'outputs').resolve()) or path.suffix != '.pdf':
            raise ValueError('Ruta de CV no válida')
        content = path.read_bytes() if path.is_file() and path.stat().st_size <= 10_000_000 else None
        actual = digest(content) if content else None
        expected = document.get('id')
        if expected and actual and expected != actual:
            raise ValueError('El CV guardado ha cambiado; recuperar el original antes de retirarlo')
        document['fingerprint'] = expected or actual
    return documents


def handle(data, operation, workflow):
    kind = operation['kind']
    if kind not in ('ui-cv-retire', 'ui-cv-restore'):
        return False
    workflow.expect(data['revision'], operation.get('expectedRevision'))
    reason = operation.get('reason')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValueError('Explica por qué se retiran o recuperan estos CV')
    app = workflow.state(data)
    if any(r['type'] == 'send' and r['status'] == 'running' for r in app['requests']):
        raise ValueError('Hay un envío en curso; espera su confirmación antes de cambiar los CV')
    validate(data)
    records = app.setdefault('retiredCVs', {})
    if kind == 'ui-cv-restore':
        keys = operation.get('fingerprints')
        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) for k in keys) or len(keys) != len(set(keys)):
            raise ValueError('Indica los CV retirados que quieres recuperar')
        if any(not isinstance(k, str) or k not in records for k in keys):
            raise ValueError('Hay un CV retirado desconocido')
        for key in keys:
            del records[key]
        workflow.record(data, 'CV recuperados para uso futuro', actor=operation.get('actor', 'Agente'),
                        detail=reason.strip())
        return True
    targets = operation.get('documents')
    if not isinstance(targets, list) or not targets or len(targets) > 500:
        raise ValueError('Indica los documentos concretos que se retiran')
    known = {d['path']: d for d in catalog(data, workflow.ROOT)}
    checked = []
    seen = set()
    for target in targets:
        if not isinstance(target, dict) or set(target) != {'path', 'fingerprint'}:
            raise ValueError('Cada CV necesita su ruta y huella comprobadas')
        path, key = target['path'], target['fingerprint']
        if not isinstance(path, str) or path in seen or path not in known:
            raise ValueError('Hay documentos desconocidos o repetidos')
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('El CV necesita una huella válida')
        workflow.expect(known[path]['fingerprint'], key)
        checked.append(known[path])
        seen.add(path)
    for document in checked:
        key = document['fingerprint']
        record = records.setdefault(key, {'fingerprint': key, 'retiredAt': now(),
                    'reason': reason.strip(), 'documents': []})
        if not any(d['path'] == document['path'] for d in record['documents']):
            record['documents'].append({k: document[k] for k in ('name', 'path')})
    keys = {d['fingerprint'] for d in checked}
    sent_packages = {e.get('packageId') for e in data['events'] if e['type'] == 'sent'}
    affected = set()
    for package in app['packages']:
        if package['payload'].get('cvHash') in keys and package['id'] not in sent_packages:
            affected.add(package['id'])
            if package.get('approvedAt') and not package.get('revokedAt'):
                package['revokedAt'] = now()
    for request in app['requests']:
        if request['type'] == 'send' and request['status'] == 'queued' and request.get('packageId') in affected:
            request.update(status='cancelled', updatedAt=workflow.request_timestamp(request),
                           result='El CV se retiró. Sustituye el documento y revisa el paquete antes de solicitar otro envío.')
    workflow.record(data, 'CV retirados del perfil', actor=operation.get('actor', 'Agente'),
                    detail=str(len(checked)) + ' documentos. ' + reason.strip())
    return True
