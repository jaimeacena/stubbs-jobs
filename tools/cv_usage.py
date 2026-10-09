"""Read-only associations between an exact PDF and recorded application material."""
from datetime import datetime, timezone
import re
import view_cache
from stubbs_jobs_core import digest, identity, vacancy_key


def legacy_paths(data, root):
    """The same visible legacy originals belong to the library and its backup."""
    if data.get('app', {}).get('personalized'):
        return []
    return sorted({path for pattern in ('CV-Usuario-*.pdf', 'CV-Usuario-*.pdf')
                   for path in (root / 'outputs').glob(pattern) if path.is_file()})


def file_hash(root, relative):
    """One bounded read per snapshot; filenames alone never identify a CV version."""
    def read():
        try:
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()) or path.suffix.lower() != '.pdf':
                return None
            if not path.is_file() or path.stat().st_size > 10_000_000:
                return None
            return digest(path.read_bytes())
        except (OSError, ValueError, TypeError):
            return None
    return view_cache.memo(('cv-library-file', str(root), relative), read)


def _time(value):
    try:
        parsed = datetime.fromisoformat(value)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return 0


def enrich(data, documents, root, package_issue):
    """Use saved hashes, immutable packages and confirmed receipts, without writes."""
    rows = {row['ID']: row for row in data['sheets']['Oportunidades']}
    by_canonical = {vacancy_key(row): row for row in rows.values()}
    history = {item['id']: item for item in data.get('historicalApplications', [])}
    packages = {item['id']: item for item in data.get('app', {}).get('packages', [])}
    associations = {}

    def target(op_id, payload=None):
        row = rows.get(op_id)
        if row:
            return {'opportunityId': op_id, 'company': row['Empresa'], 'title': row['Puesto']}
        payload = payload or {}
        canonical = identity(payload['url']) if payload.get('url') else None
        previous = next((item for item in history.values()
                         if item.get('category') != 'No laboral' and canonical
                         and vacancy_key(item) == canonical), None)
        if previous:
            current = by_canonical.get(canonical)
            if current:
                return target(current['ID'])
            return {'opportunityId': 'historical:' + str(previous['id']),
                    'company': previous['company'], 'title': previous.get('title', ''), 'historical': True}
        return None

    def add(fingerprint, usage):
        if not re.fullmatch(r'[a-f0-9]{64}', fingerprint or '') or not usage:
            return
        existing = associations.setdefault(fingerprint, {}).get(usage['opportunityId'])
        rank = lambda item: (item['kind'] == 'sent', _time(item.get('at')))
        if existing is None or rank(usage) > rank(existing):
            associations[fingerprint][usage['opportunityId']] = usage

    for package in packages.values():
        payload = package.get('payload', {})
        location = target(package.get('opportunityId'), payload)
        if location and not package_issue(package):
            add(payload.get('cvHash'), {**location, 'kind': 'prepared', 'at': package.get('createdAt'),
                                      'packageId': package['id']})

    for event in data.get('events', []):
        if event.get('type') != 'sent' or not str(event.get('confirmation') or '').strip():
            continue
        package = packages.get(event.get('packageId'))
        if event.get('packageId'):
            if (not package or package.get('opportunityId') != event.get('opportunityId') or
                    package.get('payload', {}).get('cvHash') != event.get('cvHash') or
                    digest(package.get('payload')) != package['id']):
                continue
        location = target(event.get('opportunityId'), package.get('payload') if package else None)
        if location:
            usage = {**location, 'kind': 'sent', 'at': event.get('at')}
            if package:
                usage['packageId'] = package['id']
            add(event.get('cvHash'), usage)

    for previous in history.values():
        if previous.get('category') == 'No laboral':
            continue
        if not str(previous.get('proof') or '').strip() or previous.get('state') != 'Enviada':
            continue
        current = by_canonical.get(vacancy_key(previous))
        location = target(current['ID']) if current else {
            'opportunityId': 'historical:' + str(previous['id']), 'company': previous['company'],
            'title': previous.get('title', ''), 'historical': True}
        add(previous.get('cvHash'), {**location, 'kind': 'sent', 'at': previous.get('at') or previous.get('sentAt')})

    result = []
    for document in documents:
        actual = file_hash(root, document.get('path'))
        expected = document.get('id')
        registered = bool(re.fullmatch(r'[a-f0-9]{64}', expected or ''))
        fingerprint = expected if registered else actual
        usage = list(associations.get(fingerprint, {}).values())
        usage.sort(key=lambda item: (_time(item.get('at')), item['opportunityId']), reverse=True)
        result.append({**document, 'fingerprint': fingerprint,
                       'available': bool(actual and (not registered or actual == expected)), 'usage': usage})
    return result
