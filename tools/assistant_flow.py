"""Choose a small batch of useful work; never authorize or repeat blocked work."""
import app_workflow as w


def plan(data,search_profile_id=None):
    import stubbs_jobs as j
    import app_context
    import search_profiles
    from personalization import context
    scoped=bool(search_profile_id or 'searchProfiles' in data.get('app',{}))
    if scoped:search_profiles.get(data,search_profile_id,available=True)
    if data.get('app',{}).get('personalized') or scoped:
        search=context(data,search_profile_id)
        criteria=app_context.criteria(data,search_profile_id)
        if not search['targetRoles'].strip() or not (criteria['location'].strip() or search.get('regions','').strip()):
            raise ValueError('Antes de buscar, indica los puestos y la zona de búsqueda en Stubbs Jobs.')
    app = w.seed(data)
    pending = [r for r in app['requests'] if r['status'] not in ('done', 'cancelled')]
    operations = []
    kinds=('discovery',)
    desired=w.search_round(data,search_profile_id)
    search_key=__import__('stubbs_jobs_core').digest({k:v for k,v in desired.items() if k not in ('searchProfileName','profileRevision')})
    for kind in kinds:
        if not any(r['type'] == kind and (r.get('searchKey')==search_key or not r.get('searchKey') and not r.get('round')) for r in pending):
            operations.append({'kind': 'ui-request', 'type': kind, 'actor': 'Sistema',
                               **({'searchProfileId':search_profile_id or search_profiles.default_id(data)} if scoped else {})})
    slots = max(0, 3 - len({r.get('opportunityId') for r in pending if r.get('opportunityId') and r['status'] in ('queued','running')}))
    rows = sorted(data['sheets']['Oportunidades'], key=lambda r: (r.get('Prioridad', 'Z'), str(r.get('Fecha objetivo') or '9999'), r['ID']))
    for row in rows:
        key = row['ID']
        if not slots: break
        choice = w.selection(data,key)
        if not choice or not choice.get('selected'): continue
        if row['Estado'] in (*w.CLOSED, 'Entrevista', 'Oferta') or row.get('Prioridad') not in ('A', 'B'): continue
        if any(e['opportunityId'] == key and e['type'] == 'sent' for e in data['events']): continue
        if any(r.get('opportunityId') == key for r in pending): continue
        if j.conditions(data, row)[0] == 'No': continue
        p = w.payload(data, key)
        if any(p['answers'].get(k) in (None, '') for k in p['requiredAnswers']): continue
        if not w.readiness(data, key): continue
        # An existing approval is handled only by its existing send request.
        if any(x['opportunityId'] == key and x.get('approvedAt') and not x.get('revokedAt') for x in app['packages']): continue
        operations.append({'kind': 'ui-request', 'opportunityId': key,
                           'type': 'review' if p['cvHash'] else 'investigate', 'actor': 'Sistema'})
        slots -= 1
    return operations
