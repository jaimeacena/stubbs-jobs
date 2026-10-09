"""Read-only estimate of what a criteria change would do; it never writes.

The same writer handlers that a save would use run on an in-memory copy, so the
estimate cannot drift from the real rules. Packages are never published and the
automatic archive is not run: eligibility is compared through the minimums view.
"""
import copy
import app_context as context
import app_workflow as workflow
import offer_minimums
import offer_quality
import view_cache

SEARCH_SECTION='search'


def _active(data,key):
    """Offers whose eligibility and material still matter: not closed, not sent, not archived by the person."""
    row=workflow.row_for(data,key)
    if row['Estado'] in workflow.CLOSED or any(e['type']=='sent' and e['opportunityId']==key for e in data['events']):
        return False
    archive=workflow.archived(data,key)
    return not archive or archive.get('source')=='minimums'


def _facts(data,key):
    row=workflow.row_for(data,key);app=workflow.state(data)
    stamp=workflow.stamp(data,key)
    packages=[p for p in app.get('packages',[]) if p['opportunityId']==key and p['id']==stamp]
    review=workflow.draft(data,key).get('review',{})
    assessment=app.get('offerAssessments',{}).get(key)
    fit=app.get('fitReviews',{}).get(key)
    return {'canApply':offer_minimums.view(data,row)['canApply'],
            'stamp':stamp,
            'package':bool(packages) or review.get('fingerprint')==stamp,
            'authorized':any(p.get('approvedAt') and not p.get('revokedAt') for p in packages),
            'assessment':bool(assessment) and assessment.get('fingerprint')==offer_quality.fingerprint(data,row),
            'fitReview':bool(fit) and fit.get('fingerprint')==context.fit_stamp(data,row)}


def _simulate(data,request):
    """Apply the requested change to a copy with the real handlers; return the copy."""
    candidate=copy.deepcopy(data)
    values=request.get('values')
    token=workflow._pending_packages.set({})  # Material is never published from a preview.
    try:
        if values is not None:
            if not isinstance(values,dict) or not values:raise ValueError('Indica los criterios que quieres comprobar')
            import personalization
            identifier=request.get('searchProfileId')
            old={**personalization.context(candidate,identifier),**candidate['profile'],**context.criteria(candidate,identifier)}
            workflow.handle(candidate,{'kind':'ui-profile-section','section':SEARCH_SECTION,'values':values,
                                       'expected':{k:old.get(k) for k in values},'actor':'Vista previa',
                                       **({'searchProfileId':identifier} if identifier else {})})
        if request.get('mode') is not None:
            scope={'kind':'ui-criteria-scope','mode':request['mode'],'targets':request.get('targets',[]),
                   'expectedRevision':candidate['revision'],'proof':'Vista previa sin guardar','actor':'Vista previa'}
            if request.get('round'):scope['round']=request['round']
            if request.get('searchProfileId'):scope['searchProfileId']=request['searchProfileId']
            workflow.handle(candidate,scope)
    finally:
        workflow._pending_packages.reset(token)
    return candidate


def preview(data,request):
    """Count what would change for the chosen offers, without saving anything.

    request: optional `values` (fields of the Lo que busco section, as a save
    would send them), optional `mode` ('current'|'round') with `targets` or
    `round` as in ui-criteria-scope. Without targets or round, every offer counts.
    """
    if not isinstance(request,dict) or request.get('values') is None and request.get('mode') is None:
        raise ValueError('Indica unos criterios o a qué criterios mover las ofertas')
    revision=data['revision']
    # Views fill defaults (drafts, settings) as they read; keep the caller's data untouched.
    data=copy.deepcopy(data)
    # Mutations may read intermediate fingerprints. Only cache the finished
    # projections, after every simulated save and scope change has completed.
    candidate=_simulate(data,request)
    with view_cache.snapshot():
        tags=workflow.state(data).get('offerRounds',{})
        keys=[r['ID'] for r in data['sheets']['Oportunidades']]
        chosen={t.get('id') for t in request.get('targets',[]) if isinstance(t,dict)}
        if request.get('round'):chosen|={k for k,v in tags.items() if v==request['round']}
        if chosen:keys=[k for k in keys if k in chosen]
        result={'toEligible':[],'toDiscarded':[],'assessments':[],'fitReviews':[],'packages':[],'authorizedPackages':[],'excluded':[]}
        for key in keys:
            if not _active(data,key):
                result['excluded'].append(key);continue
            before,after=_facts(data,key),_facts(candidate,key)
            if not before['canApply'] and after['canApply']:result['toEligible'].append(key)
            if before['canApply'] and not after['canApply']:result['toDiscarded'].append(key)
            for field,target in (('assessment','assessments'),('fitReview','fitReviews')):
                if before[field] and not after[field]:result[target].append(key)
            if before['package'] and before['stamp']!=after['stamp']:
                result['packages'].append(key)
                if before['authorized']:result['authorizedPackages'].append(key)
        del candidate
    return {'revision':revision,'offers':len(keys),**result,
            'counts':{k:len(v) for k,v in result.items()}}
