"""Date projections preserve legacy records without granting fresh permissions."""
from datetime import datetime, timedelta, timezone
import math
from stubbs_jobs_core import vacancy_key


def instant(value):
    """Return an aware UTC instant, or None when the evidence is incomplete."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def excel_date(value):
    if type(value) not in (int, float):
        return value if value is None or isinstance(value, str) else None
    try:
        if not math.isfinite(value):
            return None
        return (datetime(1899, 12, 30) + timedelta(days=value)).date().isoformat()
    except (OverflowError, ValueError):
        return None


def first_seen_dates(data):
    """Earliest recorded discovery; never use publication, promotion or later activity.

    Preserve timestamp precision for local calendar display; legacy day-only records
    keep their precision. Reading old stores needs no migration or operational write.
    """
    by_key, by_id = {}, {}

    def add(index, key, value):
        if not key:
            return
        value = excel_date(value)
        if not isinstance(value, str):
            return
        try:
            if len(value) == 10:
                day = datetime.strptime(value, '%Y-%m-%d').date().isoformat()
                if day != value:
                    return
            else:
                if instant(value) is None:
                    return
                day = datetime.fromisoformat(value.replace('Z', '+00:00')).date().isoformat()
        except (ValueError, OverflowError):
            return
        previous = index.get(key)
        if previous is None:
            index[key] = value
        elif len(previous) > 10 and len(value) > 10:
            if instant(value) < instant(previous):
                index[key] = value
        elif day < previous[:10] or day == previous[:10] and len(value) > 10:
            index[key] = value

    for key, observation in data.get('observations', {}).items():
        add(by_key, key, observation.get('firstSeenAt'))
        add(by_key, vacancy_key(observation), observation.get('firstSeenAt'))
    for entry in data['sheets'].get('Entradas', []):
        add(by_id, entry.get('ID oportunidad'), entry.get('Primera vista'))
        add(by_key, vacancy_key(entry), entry.get('Primera vista'))
        add(by_key, entry.get('Clave canónica'), entry.get('Primera vista'))
    result = {}
    for row in data['sheets']['Oportunidades']:
        op_id = row['ID']
        add(by_id, op_id, row.get('Primera vista'))
        candidates = [by_id.get(op_id), by_key.get(vacancy_key(row)), by_key.get(row.get('Clave canónica'))]
        earliest = {}
        for value in candidates:
            add(earliest, op_id, value)
        result[op_id] = earliest.get(op_id)
    return result


def cycle_view(record, at=None):
    result = dict(record)
    if record.get('status') != 'running':
        return result
    started = instant(record.get('startedAt'))
    if started is None:
        result['timeIssue'] = 'Falta una fecha válida para comprobar esta ejecución anterior.'
    elif (at or datetime.now(timezone.utc)) - started > timedelta(hours=2):
        result['status'] = 'interrupted'
    return result
