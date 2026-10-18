"""Captured announcements that nobody has screened yet.

The collector stores every listing in Entradas. Until the agent promotes or
closes an entry it stays «Nueva»: these views keep that backlog visible to the
person and to the agent, without turning it into offers or permissions.
"""
import copy

from state_support import excel_date

PENDING = 'Nueva'
DECISIONS = {'discard': ('Descartada', 'Descartada por ti desde Ofertas, sin revisar el anuncio.')}
MAX_TARGETS = 500


def _searches(data, key):
    return sorted({item.get('searchProfileId') for item in data.get('app', {}).get('offerSearches', {}).get(key, [])
                   if item.get('searchProfileId')})


def pending(data, search_profile_id=None):
    """Unscreened entries, newest first.

    A profile filter lists that profile's entries. Entries captured before search
    profiles existed have none: they belong to the default profile, so its next
    search reviews them instead of leaving them unscreened for ever."""
    from search_profiles import default_id
    observations = data.get('observations', {})
    inherits_unassigned = bool(search_profile_id) and search_profile_id == default_id(data)
    result = []
    for row in data['sheets'].get('Entradas', []):
        if row.get('Estado') != PENDING or row.get('ID oportunidad'):
            continue
        key = row.get('ID entrada')
        profiles = _searches(data, key)
        if search_profile_id and search_profile_id not in profiles and (profiles or not inherits_unassigned):
            continue
        seen = observations.get(row.get('Clave canónica') or key, {})
        result.append({'id': key, 'company': row.get('Empresa'), 'title': row.get('Puesto'), 'url': row.get('URL'),
                       'sourceId': row.get('Fuente'), 'firstSeenAt': seen.get('firstSeenAt') or excel_date(row.get('Primera vista')),
                       'location': seen.get('location') or None, 'roleMatch': seen.get('roleMatch'),
                       'reason': row.get('Motivo / comprobación'), 'searchProfileIds': profiles})
    result.sort(key=lambda item: (str(item['firstSeenAt'] or ''), str(item['id'])), reverse=True)
    return result


def summary(data, search_profile_id=None):
    items = pending(data, search_profile_id)
    dates = [str(item['firstSeenAt']) for item in items if item['firstSeenAt']]
    return {'count': len(items), 'oldestSeenAt': min(dates) if dates else None, 'newestSeenAt': max(dates) if dates else None,
            'command': 'agent-status --entries' + (' --search-profile ' + search_profile_id if search_profile_id else '')}


def page(data, search_profile_id=None, number=1, size=20):
    items = pending(data, search_profile_id)
    pages = max(1, -(-len(items) // size))
    listed = copy.deepcopy(items[(number - 1) * size:number * size])
    return {'entries': listed, 'scope': {'kind': 'entries', 'searchProfileId': search_profile_id, 'matchingEntries': len(items),
                                         'page': number, 'pageSize': size, 'pages': pages,
                                         'nextPageCommand': ('agent-status --entries --page ' + str(number + 1) +
                                                             (' --search-profile ' + search_profile_id if search_profile_id else ''))
                                         if number < pages else None,
                                         'listing': 'Anuncios captados que aún no se han promovido ni cerrado. Promover con promote; '
                                                    'cerrar con entry (Descartada, Duplicada o Cerrada) y su motivo.'}}


def handle(data, operation, workflow):
    if operation.get('kind') != 'ui-entry-decision':
        return False
    workflow.expect(data['revision'], operation.get('expectedRevision'))
    decision = DECISIONS.get(operation.get('decision'))
    if not decision:
        raise ValueError('Elige qué hacer con estos anuncios')
    targets = operation.get('entryIds')
    if (not isinstance(targets, list) or not targets or len(targets) > MAX_TARGETS or
            any(not isinstance(key, str) for key in targets) or len(set(targets)) != len(targets)):
        raise ValueError('Indica los anuncios, sin repetir ninguno')
    rows = {row.get('ID entrada'): row for row in data['sheets'].get('Entradas', [])}
    if any(key not in rows or rows[key].get('Estado') != PENDING or rows[key].get('ID oportunidad') for key in targets):
        raise ValueError('Algún anuncio ya se revisó. Actualiza la página antes de continuar.')
    state, reason = decision
    before = {key: {'Estado': rows[key]['Estado'], 'Motivo / comprobación': rows[key].get('Motivo / comprobación')} for key in targets}
    for key in targets:
        rows[key].update({'Estado': state, 'Motivo / comprobación': reason})
    actor = operation.get('actor', 'Agente')
    count = len(targets)
    event = workflow.record(data, 'Anuncio sin revisar descartado' if count == 1 else f'{count} anuncios sin revisar descartados', actor=actor,
                            detail='Decisión sobre anuncios captados; no crea ofertas, solicitudes ni permisos.')
    after = {key: {'Estado': state, 'Motivo / comprobación': reason} for key in targets}
    workflow.state(data)['undo'].append({'id': event['id'], 'kind': 'entries', 'before': before, 'after': after, 'used': False})
    return True


def undo_current(data, item):
    rows = {row.get('ID entrada'): row for row in data['sheets'].get('Entradas', [])}
    return {key: ({'Estado': rows[key].get('Estado'), 'Motivo / comprobación': rows[key].get('Motivo / comprobación')}
                  if key in rows else None) for key in item['after']}


def undo(data, item):
    rows = {row.get('ID entrada'): row for row in data['sheets'].get('Entradas', [])}
    for key, values in item['before'].items():
        rows[key].update(values)
