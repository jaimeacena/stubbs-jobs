"""Read-only, decision-sized context derived from the existing operational store."""
import copy

import app_workflow as workflow
from state_support import instant
from stubbs_jobs_core import ROOT, digest

OFFER_FILTERS = ('open', 'all', 'closed')
PAGE_SIZE = 20
QUEUED_DETAIL = 50


def neutral_minimums(minimums):
    """Agents read country-neutral condition names; the writer accepts both."""
    from stubbs_jobs import NEUTRAL_CONDITIONS as names
    if not isinstance(minimums, dict):
        return minimums
    return {**minimums,
            'violations': [{**v, 'key': names.get(v.get('key'), v.get('key'))} for v in minimums.get('violations', [])],
            'unknowns': [names.get(k, k) for k in minimums.get('unknowns', [])]}


def neutral_case(case):
    from stubbs_jobs import NEUTRAL_CONDITIONS as names
    case['minimums'] = neutral_minimums(case.get('minimums'))
    if isinstance(case.get('conditions'), dict):
        case['conditions'] = {names.get(k, k): v for k, v in case['conditions'].items()}
    for item in case.get('evidence') or []:
        if isinstance(item, dict) and item.get('Condición') in names:
            item['Condición'] = names[item['Condición']]
    return case


def abridged(value, text=240, items=3):
    """Shorten long proofs and lists in the general listing; --case keeps the complete record."""
    if isinstance(value, str) and len(value) > text:
        return value[:text]+'…', True
    if isinstance(value, list) and len(value) > items:
        value = value[-items:]
        shortened = [abridged(v, text, items) for v in value]
        return [v for v, _ in shortened], True
    if isinstance(value, list):
        shortened = [abridged(v, text, items) for v in value]
        return [v for v, _ in shortened], any(c for _, c in shortened)
    if isinstance(value, dict):
        shortened = {k: abridged(v, text, items) for k, v in value.items()}
        return {k: v for k, (v, _) in shortened.items()}, any(c for _, c in shortened.values())
    return value, False


def offer_page(rows, attention, offers='open', page=1, page_size=PAGE_SIZE):
    """General listing: offers needing attention first, then the most recent activity.

    Closed or discarded offers stay out of the default listing so the agent's
    context does not grow with the whole history; they remain available with
    --offers all/closed and through --case."""
    def closed(row):
        return row['state'] in workflow.CLOSED or bool(row.get('archivedAt'))
    if offers == 'all':
        pool = list(rows)
    elif offers == 'closed':
        pool = [row for row in rows if closed(row)]
    else:
        pool = [row for row in rows if row['id'] in attention or not closed(row)]
    def recency(row):
        moment = instant(row.get('lastActivityAt')) or instant(row.get('firstSeenAt'))
        return moment.timestamp() if moment else float('-inf')
    pool.sort(key=recency, reverse=True)
    pool.sort(key=lambda row: row['id'] not in attention)
    pages = max(1, -(-len(pool)//page_size))
    if page > pages:
        raise ValueError('Esa página no existe; hay '+str(pages)+' página(s) de ofertas')
    start = (page-1)*page_size
    return pool[start:start+page_size], len(pool), pages, sum(1 for row in rows if closed(row))


def knowledge_history(data, case, limit=20):
    """Recover the full grounds of past decisions without a second memory store."""
    kinds = {'ui-offer-assessment', 'ui-fit-review', 'ui-cv-review', 'ui-review'}
    records = []
    for batch in data.get('changes', []):
        for operation in batch.get('operations', []):
            if operation.get('kind') in kinds and operation.get('opportunityId') == case:
                records.append({'batchId': batch['id'], 'at': batch.get('at'),
                                'operation': copy.deepcopy(operation)})
    return {'records': records[-limit:], 'total': len(records),
            'remaining': max(0, len(records)-limit)}


def view(data, case=None, request_id=None, history=False, limit=20, since=None,profile_detail=False,search_profile_id=None,
         offers='open', page=1, page_size=PAGE_SIZE):
    from stubbs_jobs_app import state_view
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Usa un límite de historial entre 1 y 100')
    if offers not in OFFER_FILTERS:
        raise ValueError('Usa --offers open, all o closed')
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError('Usa una página desde 1 y un tamaño de página entre 1 y 100')
    # Seed and projection helpers may fill legacy defaults in memory only.
    data = copy.deepcopy(data)
    if case and not any(row['ID'] == case for row in data['sheets']['Oportunidades']):
        raise ValueError('No existe esa oferta en esta instalación')
    if request_id and not any(r['id'] == request_id for r in data.get('app', {}).get('requests', [])):
        raise ValueError('No existe ese encargo en esta instalación')
    requested = next((r for r in data.get('app', {}).get('requests', []) if r['id'] == request_id), None)
    requested_case = case or (requested.get('opportunityId') if requested else None)
    detail_case = requested_case if any(row['ID']==requested_case for row in data['sheets']['Oportunidades']) else None
    scoped = bool(case or request_id or profile_detail or search_profile_id)
    state = state_view(data, brief=True, case=detail_case,pure=True)
    version = digest([state['version'], case, request_id, history, limit,profile_detail,search_profile_id,workflow.execution_id(),
                      None if scoped else [offers, page, page_size]])
    if since == version:
        return {'unchanged': True, 'version': version}
    uncertain_ids={r['id'] for r in workflow.unresolved_sends(data)}
    raw_requests={r['id']:r for r in data['app']['requests']}
    active = []
    for request in state['requests']:
        if request.get('supersededByRequestId'):continue
        if request['status'] in ('queued', 'running', 'blocked', 'interrupted') or request['id'] in uncertain_ids:
            item = {k: copy.deepcopy(request[k]) for k in (
                'id', 'type', 'opportunityId', 'packageId', 'status', 'executionId',
                'startedAt', 'updatedAt', 'activityAt', 'summary', 'need', 'continuation',
                'interruptionUnconfirmed', 'deliveryCheck', 'invalidatedExecutionIds', 'interpretationOnly','searchProfileId','searchKey') if k in request}
            if request.get('round'):item['searchProfileName']=request['round'].get('searchProfileName')
            if 'deliveryRecheckRequired' in request:item['deliveryRecheckRequired']=request['deliveryRecheckRequired']
            item['detailCommand'] = 'agent-status --request '+request['id']
            import application_lifecycle
            projected=application_lifecycle.request_view(data,raw_requests[request['id']],workflow)
            item['summary']=projected.get('summary') or projected.get('result','')[:300]
            item['actionOwner']=projected['actionOwner']
            item['purpose']=projected.get('purpose')
            item['deliveryUnresolved']=request['id'] in uncertain_ids
            active.append(item)
    # queuedSnapshot keeps every queued ID; beyond a bound only the IDs are listed
    # and each task is read with agent-status --request ID before it starts.
    queued_snapshot = [r['id'] for r in active if r['status'] == 'queued']
    request_offers = {r.get('opportunityId') for r in active if r.get('opportunityId')}
    detailed, queued_seen = [], 0
    for item in active:
        if item['status'] == 'queued' and not item['deliveryUnresolved']:
            queued_seen += 1
            if queued_seen > QUEUED_DETAIL:continue
        detailed.append(item)
    compacted = len(active)-len(detailed)
    active = detailed
    opportunities = []
    if scoped:
        listed = [row for row in state['opportunities'] if row['id'] == detail_case]
        matching, pages, closed_count = len(listed), 1, None
    else:
        attention = set(request_offers)
        attention |= {row['id'] for row in state['opportunities'] if row.get('pendingChange')}
        listed, matching, pages, closed_count = offer_page(state['opportunities'], attention, offers, page, page_size)
    for row in listed:
        item = {k: copy.deepcopy(row.get(k)) for k in (
            'id', 'company', 'title', 'state', 'archivedAt', 'archiveReason', 'minimums', 'priority', 'selection', 'apply',
            'missing', 'integrityError', 'pendingChange', 'fingerprint', 'fitFingerprint',
            'assessmentFingerprint', 'cvFingerprint','notes','lifecycle')}
        item['minimums'] = neutral_minimums(item['minimums'])
        item['sent'] = bool(row.get('sent'))
        current = next((p for p in row['packages'] if p.get('isCurrent')), None)
        item['authorization'] = ({k: current.get(k) for k in
                                  ('id', 'approvedAt', 'revokedAt', 'approvalSource')}
                                 if current else None)
        item['assessment'] = ({k: row['assessment'].get(k) for k in
                               ('isCurrent', 'reason', 'unknowns', 'at','observedAt')}
                              if row.get('assessment') else None)
        if row.get('assessment', {}) and row['assessment']['isCurrent'] and row['assessment'].get('bestArgument'):
            item['assessment']['bestArgument'] = copy.deepcopy(row['assessment']['bestArgument'])
        item['detailCommand'] = 'agent-status --case '+row['id']
        if not scoped:
            cut = False
            for key in ('lifecycle', 'notes'):
                item[key], shortened = abridged(item[key])
                cut = cut or shortened
            if cut:
                item['abridged'] = True
        opportunities.append(item)
    execution = state['execution']
    result = {'schemaVersion': 1, 'version': version, 'revision': state['revision'],
              'updatedAt': state['updatedAt'], 'workspaceId': state['workspaceId'],
              'workspacePath': str(ROOT), 'viewOnly': True,
              'mandate': 'El alcance procede de la petición humana actual; esta consulta no inicia trabajo ni concede permisos.',
              'setupComplete': state['setupComplete'],
              'profile': {k:v for k,v in state['profile'].items() if k!='minimumFixed' or 'searchProfiles' not in data.get('app',{})}, 'preferences': state['preferences'],
              'searchProfiles':[{k:p.get(k) for k in ('id','name','revision','archivedAt')} for p in state['searchProfiles']],
              'deletedSearchProfiles':copy.deepcopy(state.get('deletedSearchProfiles',[])),
              'defaultSearchProfileId':state['defaultSearchProfileId'],'searchProfileDetailCommand':'agent-status --search-profile ID',
              'searchSourcesExclusive':bool(state['searchContext'].get('sourceUrls','').strip()),
              'searchContext': {k: v for k, v in state['searchContext'].items()
                                if k not in ('previousApplications', 'checkMail')},
              'previousApplicationsAvailable':bool(state['searchContext'].get('previousApplications')),
              'profileDetailCommand':'agent-status --profile',
              'experience': state['experience'],
              'cvLibrary':state['cvLibrary'],'fieldDefinitions':state['fieldDefinitions'],
              'onboarding': {k: state['onboarding'].get(k) for k in
                             ('status', 'token', 'revision', 'workspaceId', 'summary', 'needsWelcome', 'coverage')},
              'applicationVerification': state['applicationVerification'],
              'execution': {**{k: execution.get(k) for k in
                                ('id', 'status', 'updatedAt', 'startedAt', 'presenceUnconfirmed', 'message')},
                            'legacyTracking': True},
              'requests': active,
              'queuedSnapshot': queued_snapshot,
              'executionScope': copy.deepcopy(data.get('app', {}).get('executionScopes', {}).get(workflow.execution_id())),
              'eligibleContinuations': workflow.eligible_continuations(data) if hasattr(workflow, 'eligible_continuations') else [],
              'opportunities': opportunities,
              'scope': {'kind':'case' if case else 'request' if request_id else 'profile' if profile_detail else 'general',
                        'opportunityId':requested_case, 'requestId':request_id,
                        'opportunityUnavailable':bool(requested_case and not detail_case),
                        'totalOpportunities':len(state['opportunities']),
                        'omittedOpportunities':len(state['opportunities'])-len(opportunities),
                        **({} if scoped else {
                            'offerFilter':offers, 'page':page, 'pageSize':page_size, 'pages':pages,
                            'matchingOpportunities':matching, 'closedOpportunities':closed_count,
                            'nextPageCommand':'agent-status --offers '+offers+' --page '+str(page+1) if page < pages else None,
                            'listing':'Primero las ofertas con encargos activos o cambios pendientes; después, la actividad más reciente. '
                                      'Las descartadas y cerradas se consultan con --offers closed o --case ID. '
                                      'abridged=true indica pruebas o notas abreviadas: detailCommand devuelve el registro completo.',
                            'queuedRequestsWithoutDetail':compacted}),
                        'generalCommand':'agent-status', 'globalGuardsRetained':True},
              'globalBlocks': [copy.deepcopy(b) for b in data.get('blocks', [])
                               if b.get('status') == 'open' and not b.get('opportunityId')],
              'sourceConfigurationError': state.get('sourceConfigurationError')}
    if detail_case:
        import app_context
        result['searchContext']=app_context.scoped_search(data,detail_case)
        result['preferences']=app_context.scoped_criteria(data,detail_case)
        result['searchSourcesExclusive']=bool(result['searchContext'].get('sourceUrls','').strip())
        result['case'] = neutral_case(next(row for row in state['opportunities'] if row['id'] == detail_case))
        if history:
            result['history'] = [copy.deepcopy(h) for h in data.get('app', {}).get('history', [])
                                 if h.get('opportunityId') == detail_case][-limit:]
            result['knowledgeHistory'] = knowledge_history(data, detail_case, limit)
            result['events'] = [copy.deepcopy(e) for e in data['events'] if e.get('opportunityId') == detail_case]
            result['historicalApplications'] = [copy.deepcopy(h) for h in data.get('historicalApplications', [])
                                               if h.get('canonicalKey') == result['case'].get('canonicalKey')]
    if request_id:
        import application_lifecycle
        result['request'] = application_lifecycle.request_view(data,next(r for r in data['app']['requests'] if r['id'] == request_id),workflow)
        if requested.get('type')=='discovery' and requested.get('round'):
            import search_profiles, personalization, app_context
            effective=search_profiles.discovery_data(data,requested)
            result['searchContext']=personalization.context(effective)
            result['preferences']=app_context.criteria(effective)
            result['searchSourcesExclusive']=bool(result['searchContext'].get('sourceUrls','').strip())
    if history and not detail_case:
        result['history'] = copy.deepcopy(data.get('app', {}).get('history', [])[-limit:])
    if profile_detail:
        import onboarding
        result['searchContext']=state['searchContext']
        result['onboarding']=copy.deepcopy(onboarding.view(data,ROOT))
    if search_profile_id:
        if case or request_id:raise ValueError('Consulta el perfil por separado de una oferta o encargo')
        import search_profiles, personalization, app_context
        profile=search_profiles.get(data,search_profile_id)
        result['searchProfile']=copy.deepcopy(profile)
        result['searchContext']=personalization.context(data,search_profile_id)
        result['preferences']=app_context.criteria(data,search_profile_id)
        result['searchSourcesExclusive']=bool(result['searchContext'].get('sourceUrls','').strip())
        result['scope'].update(kind='search-profile',searchProfileId=search_profile_id)
    return result
