"""Saved search strategies. Identity, documents, applications and permissions stay shared.

All mutations are writer operations; views are pure and legacy projections have
one owner. A request's snapshot is independent of the default or an open window.
"""
import copy
import re
from stubbs_jobs_core import digest, now
from state_support import instant

VERSION = 1
LEGACY_ID = 'search-current'
SEARCH_FIELDS = ('targetRoles', 'keywords', 'searchPriorities', 'regions', 'workMode',
                 'onsiteLocations', 'currency', 'sourceUrls', 'platforms', 'searchNotes')
CRITERIA_FIELDS = ('contract', 'location', 'maxTrips', 'minimumFixed')


def profiles(data):
    saved = data.get('app', {}).get('searchProfiles')
    if saved is not None:
        if data['app'].get('searchProfilesVersion')!=VERSION:
            raise ValueError('Versión de perfiles de búsqueda no compatible; conserva el registro')
        validate(saved, data['app'].get('defaultSearchProfileId'))
        return saved
    app = data.get('app', {})
    from personalization import CONTEXT
    from app_context import DEFAULT_CRITERIA
    search = {**CONTEXT, **app.get('searchContext', {})}
    criteria = {**DEFAULT_CRITERIA, **app.get('criteria', {}),
                'minimumFixed': data['profile'].get('minimumFixed', 32000)}
    return [{'id': LEGACY_ID, 'name': 'Criterios actuales', 'revision': 1,
             'searchContext': {k: search.get(k, '') for k in SEARCH_FIELDS},
             'criteria': {k: criteria[k] for k in CRITERIA_FIELDS}, 'archivedAt': None}]


def default_id(data):
    return data.get('app', {}).get('defaultSearchProfileId', LEGACY_ID)


def visible_profiles(data):
    return [profile for profile in profiles(data) if not profile.get('deletedAt')]


def deleted_profiles(data):
    return [{key: profile.get(key) for key in ('id', 'name', 'archivedAt', 'deletedAt')}
            for profile in profiles(data) if profile.get('deletedAt')]


def get(data, identifier=None, available=False):
    identifier = identifier or default_id(data)
    profile = next((p for p in profiles(data) if p['id'] == identifier), None)
    if not profile:
        raise ValueError('No existe ese perfil de búsqueda; actualiza el estado')
    if available and (profile.get('archivedAt') or profile.get('deletedAt')):
        raise ValueError('Recupera ese perfil antes de editarlo o solicitar una búsqueda')
    return profile


def validate(saved, default):
    if not isinstance(saved, list) or not 1 <= len(saved) <= 100:
        raise ValueError('La lista de perfiles de búsqueda no es válida')
    identifiers, names = set(), set()
    for profile in saved:
        if (not isinstance(profile, dict) or not isinstance(profile.get('id'), str) or
                not re.fullmatch(r'search-[a-zA-Z0-9-]{1,80}', profile['id']) or profile['id'] in identifiers or
                not isinstance(profile.get('name'), str) or not profile['name'].strip() or len(profile['name']) > 100 or
                type(profile.get('revision')) is not int or profile['revision'] < 1 or
                not isinstance(profile.get('searchContext'), dict) or set(profile['searchContext']) != set(SEARCH_FIELDS) or
                not isinstance(profile.get('criteria'), dict) or set(profile['criteria']) != set(CRITERIA_FIELDS)):
            raise ValueError('Hay un perfil de búsqueda incompleto o duplicado')
        from personalization import validate_context
        validate_context(profile['searchContext'])
        validate_criteria(profile['criteria'])
        if profile['name'].strip().casefold() in names:
            raise ValueError('Hay perfiles de búsqueda con el mismo nombre')
        if profile.get('archivedAt') is not None and not instant(profile['archivedAt']):
            raise ValueError('La fecha de archivo del perfil no es válida')
        if profile.get('deletedAt') is not None and (not instant(profile['deletedAt']) or not profile.get('archivedAt')):
            raise ValueError('La eliminación del perfil debe estar fechada y conservar su archivo')
        identifiers.add(profile['id'])
        names.add(profile['name'].strip().casefold())
    if default not in identifiers or get_default_archived(saved, default):
        raise ValueError('El perfil predeterminado debe estar disponible')


def get_default_archived(saved, default):
    return next(p for p in saved if p['id'] == default).get('archivedAt') is not None


def validate_model(data):
    identifiers={profile['id'] for profile in profiles(data)}
    app=data.get('app',{})
    assignments=app.get('offerCriteria',{})
    if not isinstance(assignments,dict):
        raise ValueError('La asignación de criterios no es válida')
    for assigned in assignments.values():
        if not isinstance(assigned,dict) or assigned.get('searchProfileId') not in identifiers:
            raise ValueError('Una oferta hace referencia a un perfil de búsqueda inexistente')
    for request in app.get('requests',[]):
        identifier=(request.get('round') or {}).get('searchProfileId')
        if identifier and identifier not in identifiers:
            raise ValueError('Una búsqueda hace referencia a un perfil inexistente')
    appearances=app.get('offerSearches',{})
    if not isinstance(appearances,dict):
        raise ValueError('Las apariciones de ofertas no son válidas')
    for items in appearances.values():
        if not isinstance(items,list):raise ValueError('Las apariciones de ofertas no son válidas')
        seen=set()
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get('requestId'),str) or item['requestId'] in seen or item.get('searchProfileId') and item['searchProfileId'] not in identifiers:
                raise ValueError('Una aparición está duplicada o tiene un perfil inexistente')
            seen.add(item['requestId'])


def validate_criteria(values):
    if set(values) - set(CRITERIA_FIELDS):
        raise ValueError('Criterio de búsqueda desconocido')
    for key, value in values.items():
        if key in ('contract', 'location') and (not isinstance(value, str) or len(value) > 300):
            raise ValueError('Describe el contrato y la zona con texto válido')
        if key == 'maxTrips' and value is not None and (type(value) is not int or not 0 <= value <= 31):
            raise ValueError('Revisa el número de viajes')
        if key == 'minimumFixed' and value is not None and (type(value) is not int or not 0 <= value <= 1000000000):
            raise ValueError('Revisa el salario fijo mínimo')


def migrate(data):
    app = data['app']
    if 'searchProfiles' in app:
        validate(app['searchProfiles'], app.get('defaultSearchProfileId'))
        return False
    if app.get('setupComplete') is False:
        raise ValueError('Termina la preparación inicial antes de crear perfiles de búsqueda')
    app['searchProfiles'] = copy.deepcopy(profiles(data))
    app['searchProfilesVersion'] = VERSION
    app['defaultSearchProfileId'] = LEGACY_ID
    app['searchProfilesMigratedAt'] = now()
    # Common salary currency is captured before any profile can be switched.
    data['profile'].setdefault('salaryCurrency', app.get('searchContext', {}).get('currency', 'EUR'))
    app.setdefault('offerCriteria', {})
    for row in data['sheets']['Oportunidades']:
        key = row['ID']
        request_id=app.get('offerRounds',{}).get(key)
        historic=next((r for r in app.get('requests',[]) if r['id']==request_id),{})
        if not historic.get('round') or key in app.get('currentCriteria', []):
            app['offerCriteria'].setdefault(key, {'searchProfileId': LEGACY_ID})
    # Existing rounds and packages keep their exact contents. Do not guess a
    # historic profile or assign discoveries based only on dates.
    project(data)
    for request in app.get('requests', []):
        if request['type']=='discovery' and request['status'] in ('queued','running','blocked','interrupted') and not request.get('round'):
            request['round']=copy.deepcopy(snapshot(data,LEGACY_ID))
            request['roundOrigin']='legacy-migration'
            request['roundCapturedAt']=app['searchProfilesMigratedAt']
            request['searchProfileId']=LEGACY_ID
            request['searchKey']=digest({k:v for k,v in request['round'].items() if k not in ('searchProfileName','profileRevision')})
    return True


def project(data):
    """Compatibility fields mirror the default. They are never a second source."""
    profile = get(data)
    app = data['app']
    app['searchContext'] = {**app.get('searchContext', {}), **profile['searchContext'], 'checkMail': False}
    app['criteria'] = {k: profile['criteria'][k] for k in ('contract', 'location', 'maxTrips')}
    data['profile']['minimumFixed'] = profile['criteria']['minimumFixed']


def edit(data, operation, search=None, criteria=None):
    """Expectations are checked by the caller against this exact profile."""
    identifier = operation.get('searchProfileId')
    if 'searchProfiles' in data['app'] and not identifier:
        # Old single-profile agents remain compatible only while unambiguous.
        if len(profiles(data)) != 1:
            raise ValueError('Indica searchProfileId: hay varios perfiles de búsqueda')
    migrate(data)
    profile = get(data, identifier, available=True)
    if search:
        from personalization import validate_context
        validate_context(search)
    if criteria:
        validate_criteria(criteria)
    changed = any(profile['searchContext'].get(k) != v for k, v in (search or {}).items()) or any(
        profile['criteria'].get(k) != v for k, v in (criteria or {}).items())
    if changed:
        profile['searchContext'].update(search or {})
        profile['criteria'].update(criteria or {})
        profile['revision'] += 1
        profile['updatedAt'] = now()
        if profile['id'] == default_id(data):
            project(data)
    return profile, changed


def snapshot(data, identifier=None):
    from personalization import context, FIT_CONTEXT
    from app_context import criteria
    search = context(data, identifier)
    result = {'searchContext': {k: search[k] for k in sorted(FIT_CONTEXT | {'sourceUrls', 'platforms'})
                               if search.get(k) not in (None, '')}, 'criteria': criteria(data, identifier)}
    if 'searchProfiles' in data.get('app', {}):
        profile = get(data, identifier, available=True)
        result.update(searchProfileId=profile['id'], searchProfileName=profile['name'], profileRevision=profile['revision'])
    return result


def effective_snapshot(data, key):
    assigned = data.get('app', {}).get('offerCriteria', {}).get(key)
    if assigned:
        if assigned.get('snapshot'):
            return assigned['snapshot']
        # Archived profiles continue to explain existing offers.
        profile = get(data, assigned['searchProfileId'])
        return {'searchContext': profile['searchContext'], 'criteria': profile['criteria'],
                'searchProfileId': profile['id'], 'searchProfileName': profile['name'], 'profileRevision': profile['revision']}
    return None


def offer_info(data, key):
    app = data.get('app', {})
    request_id = app.get('offerRounds', {}).get(key)
    request = next((r for r in app.get('requests', []) if r['id'] == request_id), {})
    basis = effective_snapshot(data, key) or request.get('round') or {}
    identifier = basis.get('searchProfileId')
    if not identifier and not request_id:
        identifier = default_id(data)
    profile = next((p for p in profiles(data) if p['id'] == identifier), {})
    memberships = app.get('offerSearches', {}).get(key, [])
    ids = {r.get('searchProfileId') for r in memberships if r.get('searchProfileId')}
    if identifier:
        ids.add(identifier)
    return {'searchProfileId': identifier, 'searchProfileName': profile.get('name') or basis.get('searchProfileName'),
            'searchProfileDeleted': bool(profile.get('deletedAt')),
            'searchProfileIds': sorted(ids), 'searchAppearances': copy.deepcopy(memberships),
            'criteriaScope': 'current' if key in app.get('offerCriteria', {}) or not request_id else 'round'}


def discovery_request(data, request_id=None, require_running=True):
    import app_workflow as w
    requests = data.get('app', {}).get('requests', [])
    if request_id:
        request = next((r for r in requests if r['id'] == request_id), None)
        if not request or request['type'] != 'discovery' or require_running and request['status'] != 'running':
            raise ValueError('Indica una búsqueda realmente en curso')
        if require_running:
            w.require_current_execution(request)
            w.require_owner(request)
        return request
    running = [r for r in requests if r['type'] == 'discovery' and r['status'] == 'running' and r.get('executionId') == w.execution_id()]
    if len(running) > 1:
        raise ValueError('Indica requestId: hay varias búsquedas en curso')
    if running:
        return discovery_request(data, running[0]['id'])
    return None


def discovery_data(data, request):
    if not request or not request.get('round'):
        return data
    scoped = copy.copy(data)
    scoped['_discoverySnapshot'] = request['round']
    return scoped


def associate(data, key, request=None, identifier=None, new=False):
    app = data.get('app', {})
    if request:
        basis = request.get('round') or {}
        item = {'requestId': request['id'], 'searchProfileId': basis.get('searchProfileId'),
                'profileRevision': basis.get('profileRevision'), 'at': now(), 'new': new}
        appearances = app.setdefault('offerSearches', {}).setdefault(key, [])
        if not any(a['requestId'] == request['id'] for a in appearances):
            appearances.append(item)
        if key in {r['ID'] for r in data['sheets']['Oportunidades']}:
            app.setdefault('offerRounds', {}).setdefault(key, request['id'])
        request.setdefault('discoveredOpportunityIds', [])
        if key not in request['discoveredOpportunityIds']:
            request['discoveredOpportunityIds'].append(key)
        if new:
            request.setdefault('newOpportunityIds', [])
            if key not in request['newOpportunityIds']:
                request['newOpportunityIds'].append(key)
    elif 'searchProfiles' in app:
        profile = get(data, identifier, available=True)
        app.setdefault('offerCriteria', {}).setdefault(key, {'searchProfileId': profile['id']})


def handle(data, operation):
    kind = operation['kind']
    if kind not in ('ui-search-profile', 'ui-search-profiles-migrate'):
        return False
    import app_workflow as w
    app = data['app']
    w.expect(data['revision'], operation.get('expectedRevision'))
    if kind == 'ui-search-profiles-migrate':
        if not operation.get('proof'):
            raise ValueError('Conserva la razón de la migración')
        if migrate(data):
            w.record(data, 'Perfiles de búsqueda preparados', actor=operation.get('actor', 'Usuario'), detail=operation['proof'])
        return True
    migrate(data)
    action = operation.get('action')
    if action == 'archive':
        raise ValueError('Archivar perfiles está retirado; usa Eliminar, que permite recuperarlos')
    if action not in ('create', 'duplicate', 'rename', 'restore', 'default', 'delete'):
        raise ValueError('Acción de perfil de búsqueda desconocida')
    if action!='create' and not operation.get('id'):
        raise ValueError('Indica el ID del perfil de búsqueda')
    if action in ('create', 'duplicate', 'rename'):
        name = operation.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError('Da al perfil un nombre de hasta 100 caracteres')
        name = name.strip()
        if any(p['name'].casefold() == name.casefold() and p['id'] != operation.get('id') for p in profiles(data)):
            raise ValueError('Ya hay un perfil con ese nombre')
    profile = get(data, operation.get('id')) if action != 'create' else None
    if profile and profile.get('deletedAt') and action != 'restore':
        raise ValueError('Recupera el perfil eliminado antes de modificarlo')
    if action in ('create', 'duplicate'):
        if len(profiles(data)) >= 100:
            raise ValueError('Se ha alcanzado el límite de perfiles guardados')
        identifier = operation.get('newId')
        if not isinstance(identifier, str) or not re.fullmatch(r'search-[a-zA-Z0-9-]{1,80}', identifier):
            raise ValueError('El perfil nuevo necesita un identificador estable search-…')
        if any(p['id'] == identifier for p in profiles(data)):
            raise ValueError('Ese identificador de perfil ya existe')
        if action == 'duplicate':
            search, conditions = copy.deepcopy(profile['searchContext']), copy.deepcopy(profile['criteria'])
        else:
            search = dict.fromkeys(SEARCH_FIELDS, '')
            conditions = {'contract': 'Sin preferencia', 'location': '', 'maxTrips': None, 'minimumFixed': None}
        profile = {'id': identifier, 'name': name, 'revision': 1, 'searchContext': search, 'criteria': conditions,
                   'createdAt': now(), 'updatedAt': now(), 'archivedAt': None}
        app['searchProfiles'].append(profile)
    elif action == 'rename':
        profile['name'] = name
    elif action == 'restore':
        profile['archivedAt'] = None
        profile.pop('deletedAt', None)
    elif action == 'delete':
        if profile['id'] == default_id(data):
            raise ValueError('Elige otro perfil predeterminado antes de eliminar este')
        pending = [request for request in app.get('requests', [])
                   if request.get('type') == 'discovery' and request.get('status') in ('queued', 'running')
                   and (request.get('round') or {}).get('searchProfileId', request.get('searchProfileId')) == profile['id']]
        if pending:
            raise ValueError('Termina o cancela la búsqueda pendiente de este perfil antes de eliminarlo')
        profile['archivedAt'] = profile.get('archivedAt') or now()
        profile['deletedAt'] = now()
    elif action == 'default':
        get(data, profile['id'], available=True)
        app['defaultSearchProfileId'] = profile['id']
        project(data)
    labels = {'create': 'Perfil de búsqueda creado', 'duplicate': 'Perfil de búsqueda duplicado', 'rename': 'Perfil de búsqueda renombrado',
              'restore': 'Perfil de búsqueda recuperado', 'default': 'Perfil predeterminado cambiado',
              'delete': 'Perfil de búsqueda eliminado'}
    event = w.record(data, labels[action], actor=operation.get('actor', 'Usuario'), detail=profile['name'])
    event['searchProfileId'] = profile['id']
    return True
