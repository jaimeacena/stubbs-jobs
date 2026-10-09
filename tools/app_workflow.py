"""Application actions shared by the local UI and the external agent.

All register changes still pass through stubbs_jobs.apply_batch and its writer.
"""
import copy
import json
import os
import sys
import re
import uuid
import view_cache
from contextlib import contextmanager
from contextvars import ContextVar
import app_context as context
from datetime import datetime, timedelta, timezone
from stubbs_jobs_core import ROOT, DATA, now, digest, atomic_bytes, atomic_json
from state_support import instant, excel_date

LABELS={'currentCity':'Ciudad actual','workPermitWithoutSponsorship':'Permiso para trabajar en España, sin patrocinio','salaryExpectationFixed':'Salario para formularios (bruto anual)','noticeDays':'Preaviso','minimumFixed':'Salario fijo mínimo anual'}
PERSONAL=('currentCity','workPermitWithoutSponsorship','salaryExpectationFixed')
CONTACT_FIELDS={
    'email':{'label':'Email','inputType':'email','autocomplete':'email','maxlength':254},
    'phone':{'label':'Teléfono','inputType':'tel','autocomplete':'tel','maxlength':100,'placeholder':'Incluye el prefijo internacional'},
    'currentCountry':{'label':'País de residencia','autocomplete':'country-name','maxlength':100},
    'postalCode':{'label':'Código postal','autocomplete':'postal-code','maxlength':40},
    'address':{'label':'Dirección','autocomplete':'street-address','maxlength':500},
    'linkedinUrl':{'label':'LinkedIn','inputType':'url','maxlength':2000,'placeholder':'https://www.linkedin.com/in/...'},
    'websiteUrl':{'label':'Web o portfolio','inputType':'url','maxlength':2000,'placeholder':'https://...'},
}
DEMOGRAPHIC_FIELDS={
    'gender':{'label':'Género (opcional)','type':'text','maxlength':100,
              'placeholder':'Ej.: hombre, mujer, no binario o prefiero no responder',
              'descriptionId':'profile-gender-help','help':'Solo se utiliza cuando el formulario lo pide y aceptas participar en su encuesta demográfica.'},
    'demographicSurveyParticipation':{'label':'Participar en encuestas demográficas (opcional)','type':'boolean',
              'descriptionId':'profile-demographic-help','help':'Sí: usar tus datos guardados en encuestas opcionales de las solicitudes que elijas. No: omitirlas o elegir «Prefiero no responder». No incluye el consentimiento para tramitar la candidatura.'},
}
FORM_FIELDS=(*PERSONAL,'noticeDays',*CONTACT_FIELDS,*DEMOGRAPHIC_FIELDS)
CHECKS=('cv','form','destination','vacancy','duplicates')
CLOSED=('Rechazada','Descartada','Cerrada','Lograda','Oferta')
AUTOMATION_DEFAULTS={'applicationMode':'review'}

class Conflict(ValueError): pass

def request_timestamp(request,activity=True):
    """Advance the task token, retaining a separate date for actual activity."""
    at=datetime.now(timezone.utc)
    if activity:request['activityAt']=at.isoformat(timespec='microseconds')
    elif 'activityAt' not in request:request['activityAt']=request.get('updatedAt')
    previous=instant(request.get('updatedAt'))
    if previous is not None and at<=previous:
        try:at=previous+timedelta(microseconds=1)
        except OverflowError as exc:raise ValueError('La fecha anterior de esta tarea no permite registrar un cambio; comprueba ese dato antes de continuar') from exc
    return at.isoformat(timespec='microseconds')

_pending_packages=ContextVar('pending_packages',default=None)
_execution=ContextVar('stubbs_jobs_execution',default=None)
_execution_scope=ContextVar('stubbs_jobs_execution_scope',default=None)
_interface_execution=object()

@contextmanager
def execution_owner(identifier):
    token=_execution.set(identifier)
    try:yield
    finally:_execution.reset(token)


def execution_id():
    if _execution.get() is _interface_execution:return None
    return (_execution.get() or os.environ.get('STUBBS_JOBS_RUN_ID') or
            os.environ.get('STUBBS_JOBS_EXECUTION_ID') or os.environ.get('CODEX_THREAD_ID'))

@contextmanager
def interface_writer():
    """User actions never inherit the agent that happened to launch the server."""
    owner=_execution.set(_interface_execution);scope=_execution_scope.set(None)
    try:yield
    finally:
        _execution_scope.reset(scope);_execution.reset(owner)

@contextmanager
def execution_scope(request_ids):
    if request_ids is not None and (not isinstance(request_ids,(list,tuple)) or not request_ids or
            any(not isinstance(key,str) or not key.strip() for key in request_ids) or
            len(set(request_ids))!=len(request_ids)):
        raise ValueError('Indica los IDs exactos de la instantánea original, sin duplicados')
    token=_execution_scope.set(sorted(request_ids) if request_ids is not None else None)
    try:yield
    finally:_execution_scope.reset(token)

def selection_matches(choice,at,identifier=None):
    # A timestamp is history, not a decision's identity. Missing IDs match only
    # unchanged legacy selections; a new decision always carries its own ID.
    return bool(choice and choice.get('at')==at and choice.get('id')==identifier)

def validate_execution_scope(data):
    """Every new write retains the original snapshot of a scoped execution."""
    owner=execution_id()
    saved=data.get('app',{}).get('executionScopes',{}).get(owner)
    if saved is None:return
    if _execution_scope.get() is None:
        raise ValueError('Conserva --request-ids con la instantánea original; esta ejecución tiene su alcance fijado')
    if saved['requestIds']!=_execution_scope.get():
        raise ValueError('La instantánea de esta ejecución ya está fijada; las instrucciones nuevas necesitan otra continuación')

def continuation_eligible(data,request,owner=None):
    """Eligibility is causal and local to the original agent's fixed snapshot."""
    owner=owner or execution_id()
    link=request.get('continuation',{})
    scope=state(data).get('executionScopes',{}).get(owner,{})
    root=next((item for item in state(data)['requests'] if item['id']==link.get('rootRequestId')),None)
    choice=selection(data,request.get('opportunityId'))
    package=next((item for item in state(data)['packages'] if item['id']==request.get('packageId')),None)
    valid=bool(request['type']=='send' and request['status']=='queued' and owner and
        link.get('executionId')==owner and root and root['type'] in ('review','investigate') and
        root.get('opportunityId')==request.get('opportunityId') and root['status']=='done' and
        root.get('executionId')==owner and owner not in root.get('invalidatedExecutionIds',[]) and
        owner not in request.get('invalidatedExecutionIds',[]) and root['id'] in scope.get('requestIds',[]) and
        scope.get('rootSelections',{}).get(root['id'])==link.get('selectionAt') and
        scope.get('rootSelectionIds',{}).get(root['id'])==link.get('selectionId') and
        choice and choice.get('selected') and choice.get('mode')=='auto' and selection_matches(choice,link.get('selectionAt'),link.get('selectionId')) and
        package and package.get('approvalSource')=='selection' and not package.get('revokedAt') and
        package.get('approvedAt')==link.get('authorizationAt') and package.get('selectionAt')==link.get('selectionAt') and
        package.get('selectionId')==link.get('selectionId') and
        package['id']==stamp(data,request['opportunityId']) and not readiness(data,request['opportunityId']) and
        not pending_change(data,request['opportunityId']))
    if not valid:return False
    try:
        require_delivery_resolved(data,request['opportunityId'],request)
        approved_package(data,request['opportunityId'],request['packageId'])
    except ValueError:return False
    return True

def eligible_continuations(data,owner=None):
    return [item['id'] for item in state(data)['requests'] if continuation_eligible(data,item,owner)]

def bind_execution_scope(data,request):
    ids=_execution_scope.get();owner=execution_id()
    if ids is None:
        if request.get('continuation') or owner in state(data).get('executionScopes',{}):
            raise ValueError('Conserva --request-ids con la instantánea original; esta ejecución tiene su alcance fijado')
        return
    if not owner:raise ValueError('La instantánea necesita un execution-id propio')
    scopes=state(data).setdefault('executionScopes',{})
    saved=scopes.get(owner)
    if saved is None:
        roots={item['id']:item for item in state(data)['requests'] if item['id'] in ids}
        if len(roots)!=len(ids) or any(item['status']!='queued' or owner in item.get('invalidatedExecutionIds',[]) for item in roots.values()):
            raise ValueError('La instantánea inicial solo puede contener encargos actualmente en cola y disponibles')
        if request['id'] not in ids:raise ValueError('Este encargo no pertenece a la instantánea original')
        choices={};choice_ids={}
        for key,item in roots.items():
            choice=selection(data,item.get('opportunityId')) if item.get('opportunityId') else None
            if item['type'] in ('review','investigate') and choice and choice.get('selected') and choice.get('mode')=='auto':
                choices[key]=choice['at']
                if choice.get('id') is not None:choice_ids[key]=choice['id']
        saved={'requestIds':list(ids),'rootSelections':choices,'rootSelectionIds':choice_ids,'createdAt':now()}
        scopes[owner]=saved
    elif saved['requestIds']!=ids:
        raise ValueError('La instantánea de esta ejecución ya está fijada; las instrucciones nuevas necesitan otra continuación')
    if request['id'] not in saved['requestIds'] and not continuation_eligible(data,request,owner):
        raise ValueError('Este encargo no deriva de la revisión automática de la instantánea original')

def causal_continuation(data,op_id,package):
    owner=execution_id();scope=state(data).get('executionScopes',{}).get(owner,{})
    if not owner or not scope or _execution_scope.get() is None or _execution_scope.get()!=scope.get('requestIds'):return None
    roots=[item for item in state(data)['requests'] if item['id'] in scope['requestIds'] and
           item['type'] in ('review','investigate') and item.get('opportunityId')==op_id and
           item['status']=='running' and item.get('executionId')==owner and owner not in item.get('invalidatedExecutionIds',[]) and
           scope.get('rootSelections',{}).get(item['id'])==package.get('selectionAt') and
           scope.get('rootSelectionIds',{}).get(item['id'])==package.get('selectionId')]
    if len(roots)!=1:return None
    link={'rootRequestId':roots[0]['id'],'executionId':owner,'selectionAt':package['selectionAt'],
          'authorizationAt':package['approvedAt']}
    if package.get('selectionId') is not None:link['selectionId']=package['selectionId']
    return link


def require_current_execution(request):
    if execution_id() and execution_id() in request.get('invalidatedExecutionIds', []):
        raise ValueError('El identificador de esta ejecución fue retirado de la tarea. Consulta el estado y usa un identificador nuevo para una continuación autorizada.')


def require_owner(request):
    require_current_execution(request)
    if request.get('executionId') and request['executionId'] != execution_id():
        raise ValueError('Este encargo ya pertenece a otra ejecución.')

@contextmanager
def package_transaction(data):
    pending={};token=_pending_packages.set(pending)
    protected={p['id'] for p in data.get('app',{}).get('packages',[])}
    try:
        yield
        for key,(p,content) in pending.items():publish_package(key,p,content,key in protected)
    finally:_pending_packages.reset(token)

def publish_package(key,p,content,protected=False):
    directory=DATA/'packages'/key
    expected={'cv.pdf':content,'package.json':(json.dumps(p,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),'presentacion.txt':p['message'].encode('utf-8')}
    if directory.exists():
        if directory.is_symlink() or directory.resolve().parent!=(DATA/'packages').resolve():raise ValueError('Ruta de paquete no válida')
        matches={name:(directory/name).is_file() and (json.loads((directory/name).read_text(encoding='utf-8'))==p if name=='package.json' else (directory/name).read_bytes()==raw) for name,raw in expected.items()}
        if all(matches.values()):return
        if protected or any((directory/name).exists() and not matches[name] for name in expected):
            raise ValueError('La copia conservada ha cambiado; revisar antes de seguir')
        recovery=DATA/'package-recovery'/(key+'-'+uuid.uuid4().hex)
        recovery.parent.mkdir(parents=True,exist_ok=True)
        directory.rename(recovery)
    elif protected:raise ValueError('Falta una copia conservada; recuperar antes de seguir')
    staging=DATA/'package-staging'/uuid.uuid4().hex
    atomic_bytes(staging/'cv.pdf',content)
    atomic_json(staging/'package.json',p)
    atomic_bytes(staging/'presentacion.txt',p['message'].encode('utf-8'))
    directory.parent.mkdir(parents=True,exist_ok=True)
    staging.rename(directory)

def material_versions(data):
    seed(data)
    return {r['ID']:(stamp(data,r['ID']),r.get('Prioridad'),r['Estado'] in CLOSED) for r in data['sheets']['Oportunidades']}

def protect_material(data,before):
    """All writers, including legacy operations and undo, share this invariant."""
    changed=False
    for key,previous in before.items():
        row=row_for(data,key)
        current=(stamp(data,key),row.get('Prioridad'),row['Estado'] in CLOSED)
        if previous==current:continue
        changed=True
        if any(r['type']=='send' and r['status']=='running' and r.get('opportunityId')==key for r in state(data)['requests']):
            raise ValueError('Hay un envío en curso. Espera su confirmación antes de cambiar estos datos.')
        auto_review(data,key)
    if changed:reconcile(data)

def state(data):
    return data.setdefault('app',{'version':1,'drafts':{},'packages':[],'requests':[],'history':[],'snoozes':{},'seenAt':None,'undo':[]})

def automation(data):
    app=state(data)
    settings=app.setdefault('automation',{})
    for key,value in AUTOMATION_DEFAULTS.items():settings.setdefault(key,value)
    # Stored contact/schedule metadata is history, not an active instruction.
    if 'scheduleEnabled' in settings:settings['scheduleEnabled']=False
    if 'searchFrequency' in settings:settings['searchFrequency']='manual'
    app.setdefault('selections',{})
    return settings

def selection(data,op_id):
    automation(data)
    return state(data)['selections'].get(op_id)

def archived(data,op_id):
    from offer_actions import archived as lookup
    return lookup(data,op_id)

def row_for(data,op_id):
    rows=view_cache.memo(('rows',id(data)),lambda:{r['ID']:r for r in data['sheets']['Oportunidades']})
    return rows[op_id]

def seed(data):
    app=state(data)
    retire_mail(data)
    automation(data)
    app.setdefault('legacyImported',True)
    for row in data['sheets']['Oportunidades']:draft(data,row['ID'])
    return app

def retire_mail(data):
    """Retire old mail work without deleting its history or taking a running claim."""
    app=state(data)
    search=app.get('searchContext',{})
    changed='checkMail' in search and search['checkMail'] is not False
    if changed:search['checkMail']=False
    for req in app['requests']:
        if req['type']=='mail' and req['status'] in ('queued','blocked','interrupted'):
            req.update(status='cancelled',updatedAt=request_timestamp(req),result='Búsqueda en correo retirada. Este trabajo no se ejecutará.')
            changed=True
    if changed:record(data,'Búsqueda en correo retirada',actor='Sistema',detail='Configuración y tareas antiguas desactivadas; historial conservado.')

def draft(data,op_id):
    return state(data)['drafts'].setdefault(op_id,{'message':'','recipient':row_for(data,op_id)['URL original'],'answers':{},'requiredAnswers':[],'checks':{},'cvReason':'Pendiente de selección y revisión.','changes':'','updatedAt':now()})

@view_cache.cached(lambda data,op_id:(id(data),op_id))
def answers(data,op_id):
    result={k:data['profile'].get(k) for k in LABELS}
    if 'searchProfiles' in data.get('app',{}):
        result['minimumFixed']=context.scoped_criteria(data,op_id)['minimumFixed']
    d=draft(data,op_id)
    requested=set(d['requiredAnswers'])|set(d.get('formAnswerKeys') or [])
    result.update({k:data['profile'].get(k) for k in (*CONTACT_FIELDS,'demographicSurveyParticipation') if k in requested})
    if 'gender' in requested:
        participation=d['answers'].get('demographicSurveyParticipation',data['profile'].get('demographicSurveyParticipation'))
        result['gender']=data['profile'].get('gender') if participation is True else 'Prefiero no responder' if participation is False else None
    result.update({k:data['profile'].get(k) for k,f in context.definitions(data,op_id).items() if k.startswith('custom_') and f['scope']=='global' and k in requested})
    result.update(draft(data,op_id)['answers'])
    return result

def cv_bytes(row):
    value=row.get('CV preparado')
    path=(ROOT/value).resolve() if value else None
    if not path or not path.is_relative_to(ROOT.resolve()) or path.suffix.lower()!='.pdf' or not path.is_file(): return None
    def read():
        try:return path.read_bytes()
        except OSError:return None
    return view_cache.memo(('cv',str(path)),read)

@view_cache.cached(lambda data,op_id:(id(data),op_id))
def payload(data,op_id):
    row=row_for(data,op_id); d=draft(data,op_id); content=cv_bytes(row)
    result={'opportunityId':op_id,'company':row['Empresa'],'title':row['Puesto'],'url':row['URL original'],
            'recipient':d['recipient'],'message':d['message'],'answers':answers(data,op_id),
            'requiredAnswers':d['requiredAnswers'],'cvHash':digest(content) if content else None,'cv':row.get('CV preparado'),
            'cvReason':d['cvReason'],'changes':d['changes'],
            'conditions':{k:row.get(k) for k in ('Remoto España','Indefinido','Viajes ≤1/mes','Fijo ≥32 k€','Fijo mín. confirmado','Vigencia')}}
    for key in ('Fijo máx. confirmado','Moneda fijo confirmado','Viajes mín. al mes','País','Ubicación','Modalidad','Contrato'):
        if row.get(key) is not None:result['conditions'][key]=row[key]
    if 'criteria' in state(data):
        result['preferences']=context.scoped_criteria(data,op_id)
        fit=state(data).get('fitReviews',{}).get(op_id,{})
        result['fitDecision']={k:fit[k] for k in ('apply','accept')} if fit.get('fingerprint')==context.fit_stamp(data,row) else None
    if d.get('questions'):result['questions']=d['questions']
    # Optional delivery metadata leaves historical package fingerprints intact.
    for key in ('messageUsage','formAnswerKeys'):
        if d.get(key) is not None:result[key]=d[key]
    if 'experience' in state(data):result['experience']=state(data)['experience']
    contacts={k:data['profile'][k] for k in CONTACT_FIELDS if data['profile'].get(k) not in (None,'')}
    if contacts:result['profileContacts']=contacts
    if 'searchContext' in state(data):result['searchContext']=context.application_context(data,context.scoped_search(data,op_id))
    if 'searchProfiles' in state(data) and result['answers'].get('salaryExpectationFixed') is not None:
        currency=data['profile'].get('salaryCurrency') or ''
        if currency!=result.get('searchContext',{}).get('currency',''):
            result['salaryExpectationCurrency']=currency
    if context.offer_requirements(row):result['offerRequirements']=context.offer_requirements(row)
    return result

@view_cache.cached(lambda data,op_id:(id(data),op_id))
def stamp(data,op_id): return digest(payload(data,op_id))

@view_cache.cached(lambda data,op_id:(id(data),op_id))
def missing(data,op_id):
    row=row_for(data,op_id); d=draft(data,op_id); p=payload(data,op_id); result=[]
    if row['Estado'] in CLOSED: result.append('Proceso cerrado')
    elif archived(data,op_id): result.append('Oferta archivada')
    if not p['cvHash']: result.append('Seleccionar un CV disponible')
    if not isinstance(d.get('formAnswerKeys'),list):result.append('Comprobar las preguntas que pide el destino')
    if d.get('messageUsage') is None:result.append('Comprobar si el destino utiliza presentación')
    if d.get('messageUsage')=='unknown':result.append('Comprobar si el formulario utiliza presentación')
    if d.get('messageUsage')!='unused' and not p['message'].strip(): result.append('Preparar el texto de solicitud')
    if not p['recipient'].strip(): result.append('Confirmar el destinatario')
    for key in d['requiredAnswers']:
        if p['answers'].get(key) is None or p['answers'].get(key)=='': result.append(context.definitions(data,op_id).get(key,{}).get('label',key))
    review=d.get('review',{})
    if review.get('fingerprint')!=stamp(data,op_id) or not all(d['checks'].get(k) for k in CHECKS): result.append('Revisión final del agente')
    else:
        reviewed_at=instant(review.get('at'))
        age=datetime.now(timezone.utc)-reviewed_at if reviewed_at else None
        if age is None or not -timedelta(minutes=5)<=age<=timedelta(hours=48):result.append('Revalidar la oferta y el formulario')
    return result

def record(data,title,op_id=None,actor='Agente',detail='',artifact=None):
    app=state(data)
    item={'id':len(app['history'])+1,'at':now(),'opportunityId':op_id,'actor':actor,'title':title,'detail':detail}
    if artifact:item['packageId']=artifact
    app['history'].append(item)
    return item

def validate_answer(key,value,definition=None):
    if key=='salaryCurrency':
        if value not in (None,'') and (not isinstance(value,str) or not re.fullmatch('[A-Z]{3}',value)):
            raise ValueError('Usa una moneda de tres letras para el salario de formularios')
        return
    if definition and key.startswith('custom_'):return context.validate_custom(definition,value)
    if key in DEMOGRAPHIC_FIELDS:
        if value is None:return
        if key=='demographicSurveyParticipation':
            if type(value) is not bool:raise ValueError('Elige Sí, No o Sin responder para las encuestas demográficas')
        elif not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>100:
            raise ValueError('Describe tu género o indica «Prefiero no responder», hasta 100 caracteres')
        return
    if key in CONTACT_FIELDS:
        if value is None:return
        if not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>CONTACT_FIELDS[key]['maxlength']:raise ValueError('Revisa «'+CONTACT_FIELDS[key]['label']+'»')
        if key=='email' and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',value):raise ValueError('Escribe un email válido')
        if key=='phone' and sum(c.isdecimal() for c in value)<3:raise ValueError('Escribe un teléfono con su prefijo y número')
        if key in ('linkedinUrl','websiteUrl'):
            from personalization import validate_url
            validate_url(value)
        return
    if key=='workAuthorizations':
        from personalization import validate_work_authorizations
        return validate_work_authorizations(value)
    if key not in LABELS: raise ValueError('Dato de perfil no admitido')
    if value is None:return
    if key=='currentCity':
        if not isinstance(value,str) or not value.strip() or len(value)>100:raise ValueError('Escribe una ciudad válida')
    elif key=='workPermitWithoutSponsorship':
        if type(value) is not bool:raise ValueError('El permiso debe ser sí, no o pendiente')
    elif key=='noticeDays':
        if type(value) is int and 0<=value<=365:return  # Legacy records retain their units as unknown.
        if not isinstance(value,str) or not value.strip() or len(value)>300:raise ValueError('Describe el preaviso, indicando si son días laborables o naturales')
    elif type(value) is not int or not 1 <= value <= 1000000000:raise ValueError('Revisa la cantidad indicada')

def expect(current,expected):
    if current!=expected:raise Conflict('Este dato cambió mientras lo editabas. Tu borrador se conserva; revisa el valor actual antes de guardar.')

def pending_change(data,op_id,exclude_owner=False):
    owner=execution_id()
    return any(r['type']=='change' and not r.get('interpretationOnly') and r['status'] not in ('done','cancelled') and r.get('opportunityId') in (None,op_id)
               and not (exclude_owner and owner and r['status']=='running' and r.get('executionId')==owner)
               for r in state(data)['requests'])

def undo_current(data,item):
    app=state(data);kind=item['kind'];key=item.get('opportunityId')
    if kind=='offer-archive':return {key:archived(data,key) for key in item['after']}
    if kind=='selection':return selection(data,key)
    if kind=='section':
        from personalization import context as search_context
        profile_id=item.get('searchProfileId')
        values={**search_context(data,profile_id),**data['profile'],**context.criteria(data,profile_id)}
        return {k:values.get(k) for k in item['after']}
    if kind=='experience':return context.experience(data)
    if kind=='responses':return {scope:{k:(data['profile'] if scope=='global' else draft(data,key)['answers']).get(k) for k in values} for scope,values in item['after'].items()}
    if kind=='change':
        req=next((r for r in app['requests'] if r['id']==item['requestId']),None)
        return req.get('instructions',[]) if req and req['status']=='queued' else None
    if kind=='snooze':return app['snoozes'].get(item['key'])
    target=(data['profile'] if item.get('scope')=='global' else draft(data,key)['answers']) if kind=='profile' else draft(data,key)
    return {k:target.get(k) for k in item['after']}

def undo_available(data,item):
    if item['used'] or undo_current(data,item)!=item['after']:return False
    if item['kind']=='offer-archive':return not any(value and value.get('outcome')=='achieved' for value in item['after'].values())
    if item['kind']=='change' and any(r['id']==item['requestId'] and r.get('interpretationOnly') for r in state(data)['requests']):return True
    key=item.get('opportunityId')
    if key and (row_for(data,key)['Estado'] in CLOSED or any(e['type']=='sent' and e['opportunityId']==key for e in data['events'])):return False
    return not any(r['type']=='send' and r['status']=='running' and (not key or r.get('opportunityId')==key) for r in state(data)['requests'])

def archive(data,op_id,cv=None,external=False):
    p=payload(data,op_id); row=row_for(data,op_id)
    content=(ROOT/cv).read_bytes() if cv else cv_bytes(row)
    if not content:raise ValueError('No hay CV para conservar')
    p['cvHash']=digest(content)
    if cv:p['cv']=cv
    fingerprint=digest(p)
    entry=next((x for x in state(data)['packages'] if x['id']==fingerprint),None)
    pending=_pending_packages.get()
    if pending is None:publish_package(fingerprint,p,content,entry is not None)
    else:pending[fingerprint]=(copy.deepcopy(p),content)
    if not entry:
        entry={'id':fingerprint,'opportunityId':op_id,'createdAt':now(),'payload':p,'external':external,'approvedAt':None}
        # Preparation context is preserved separately from material and sending permission.
        import offer_quality
        argument=offer_quality.current_argument(data,row)
        if argument:
            entry['preparationArgument']={**argument,'assessmentFingerprint':offer_quality.fingerprint(data,row)}
        state(data)['packages'].append(entry)
    return entry

def verify_package(package):
    """Check the exact archived material before showing it or using its permission."""
    key=package['id']
    if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key):
        raise ValueError('Identificador de copia conservada no válido')
    directory=DATA/'packages'/key
    try:
        resolved_directory=directory.resolve()
        if directory.is_symlink() or resolved_directory.parent!=(DATA/'packages').resolve():
            raise ValueError('Ruta de copia conservada no válida')
        contents={}
        for name in ('cv.pdf','package.json','presentacion.txt'):
            path=directory/name
            if path.is_symlink() or path.resolve().parent!=resolved_directory:
                raise ValueError('Ruta de copia conservada no válida')
            contents[name]=path.read_bytes()
        payload_copy=json.loads(contents['package.json'])
        if payload_copy!=package['payload'] or digest(payload_copy)!=key:
            raise ValueError('El material conservado ha cambiado; recupera la copia original antes de continuar.')
        if digest(contents['cv.pdf'])!=payload_copy['cvHash']:
            raise ValueError('El CV conservado ha cambiado; recupera la copia original antes de continuar.')
        if contents['presentacion.txt']!=payload_copy['message'].encode('utf-8'):
            raise ValueError('El material conservado ha cambiado; recupera la copia original antes de continuar.')
    except (OSError,UnicodeError,KeyError,json.JSONDecodeError) as exc:
        raise ValueError('No se puede comprobar la copia conservada. El agente debe recuperar sus archivos originales.') from exc


def package_issue(package):
    def check():
        try:verify_package(package)
        except ValueError as exc:return str(exc)
        return None
    return view_cache.memo(('package-integrity',package['id']),check)


def approved_package(data,op_id,package_id):
    p=next(x for x in state(data)['packages'] if x['id']==package_id and x['opportunityId']==op_id)
    from stubbs_jobs_core import vacancy_key
    same={r['ID'] for r in data['sheets']['Oportunidades'] if r['ID']!=op_id and vacancy_key(r)==vacancy_key(row_for(data,op_id))}
    if any(e['type']=='sent' and e['opportunityId'] in same for e in data['events']) or any(
            r['type']=='send' and r.get('opportunityId') in same and (r['status']=='running' or r in unresolved_sends(data,r.get('opportunityId'))) for r in state(data)['requests']):
        raise ValueError('La misma vacante tiene otro envío confirmado o sin resolver, aunque su enlace sea distinto')
    if not (selection(data,op_id) or {}).get('selected'):
        raise ValueError('La oferta ya no está seleccionada')
    if pending_change(data,op_id):raise ValueError('Hay cambios pendientes. Revisa la nueva solicitud antes de enviar.')
    if not p.get('approvedAt') or p.get('revokedAt'):raise ValueError('Este paquete no tiene autorización vigente')
    if p.get('approvalSource')=='selection':
        choice=selection(data,op_id)
        if not choice or not choice.get('selected') or choice.get('mode')!='auto' or not selection_matches(choice,p.get('selectionAt'),p.get('selectionId')):
            raise ValueError('La selección que autorizaba el envío ya no está vigente')
    checked=instant(draft(data,op_id).get('review',{}).get('at'))
    if not checked or datetime.now(timezone.utc)-checked>timedelta(days=1):raise ValueError('La comprobación del destino y la vacante tiene más de 24 horas; necesita revalidación antes de enviar')
    if p['id']!=stamp(data,op_id) or readiness(data,op_id):raise ValueError('El paquete cambió o necesita revalidación; revisar antes de enviar')
    return conserved_package(p)

def conserved_package(p):
    """Validate the immutable material, independently of permission for a new effect."""
    pending=_pending_packages.get()
    if pending is not None and p['id'] in pending:
        payload_copy,content=pending[p['id']]
        if payload_copy!=p['payload'] or digest(content)!=p['payload']['cvHash']:raise ValueError('El material conservado ha cambiado')
        return p
    verify_package(p)
    return p

def require_delivery_resolved(data,op_id,request=None):
    from request_workflow import require_delivery_resolved as guard
    guard(data,op_id,request)

def unresolved_sends(data,op_id=None):
    from request_workflow import unresolved_attempts
    keys=[op_id] if op_id is not None else {item.get('opportunityId') for item in state(data)['requests'] if item['type']=='send'}
    return [item for key in keys for item in unresolved_attempts(data,key)]

def superseded_sends(data):
    from request_workflow import superseded_send
    return {item['id']:successor for item in state(data)['requests'] if (successor:=superseded_send(data,item))}

@view_cache.cached(lambda data,op_id:(id(data),op_id))
def readiness(data,op_id):
    import stubbs_jobs as j
    pending=missing(data,op_id)
    if j.conditions(data,row_for(data,op_id))[0] not in ('Sí','Sí, aclarar'):pending.append('Resolver el encaje o las condiciones')
    if 'criteria' in state(data):
        review=state(data).get('fitReviews',{}).get(op_id,{})
        if review.get('fingerprint')!=context.fit_stamp(data,row_for(data,op_id)):
            pending.append('Comprobar la oferta con los criterios actuales')
    return pending

def reconcile(data):
    app=state(data)
    import application_lifecycle
    application_lifecycle.reconcile(data, __import__('sys').modules[__name__])
    for b in data['blocks']:
        if b['id']=='profile':
            values=answers(data,b['opportunityId']) if b.get('opportunityId') else data['profile']
            b['status']='resolved' if all(values.get(k) is not None for k in PERSONAL) else 'open'
    for row in data['sheets']['Oportunidades']:
        d=app['drafts'].get(row['ID'],{});required=d.get('requiredAnswers',[])
        if row['Estado'] in CLOSED or archived(data,row['ID']) or any(e['type']=='sent' and e['opportunityId']==row['ID'] for e in data['events']):continue
        if row['Estado']=='Lista para revisión' and readiness(data,row['ID']):
            row['Estado']='Preparar';row['Siguiente paso']='Revisar el paquete vigente antes de solicitar una decisión de envío.'
        unanswered=[k for k in required if answers(data,row['ID']).get(k) in (None,'')]
        block_id='profile' if row['ID']=='legacy-profile-record' else 'ui-answers-'+row['ID']
        block=next((b for b in data['blocks'] if b['id']==block_id),None)
        if not required:
            if block and block.get('status')=='open':
                block.update(status='resolved',question='El formulario ya no requiere estas respuestas.')
                if row['Estado'] in ('Pendiente de Usuario','Pendiente de ti'):
                    row['Estado']='Preparar';row['Siguiente paso']='Comprobar el formulario actualizado antes de continuar.'
            continue
        if not block:
            block={'id':block_id,'opportunityId':row['ID'],'owner':'Usuario' if app.get('personalized') else 'Usuario','due':None};data['blocks'].append(block)
        block.update(status='open' if unanswered else 'resolved',question=('Responder: '+', '.join(context.definitions(data,row['ID'])[k]['label'].lower() for k in unanswered)+'.') if unanswered else 'Respuestas guardadas.')
        if unanswered:
            row['Estado']='Pendiente de ti' if app.get('personalized') else 'Pendiente de Usuario';row['Siguiente paso']='Responder: '+', '.join(context.definitions(data,row['ID'])[k]['label'].lower() for k in unanswered)+'. Después, comprobación del agente.'
        elif row['Estado'] in ('Pendiente de Usuario','Pendiente de ti'):
            row['Estado']='Preparar';row['Siguiente paso']='Respuestas completas. Revisar vigencia, destinatario y formulario con el CV seleccionado.'
    # Silence is a presentation cue, never evidence that work stopped or ownership ended.
    # A verified interruption goes through the owning update or ui-request-interrupt.

def handle(data,op):
    app=seed(data); kind=op['kind']; op_id=op.get('opportunityId'); actor=op.get('actor','Agente')
    if kind in ('ui-add-opportunity','ui-draft','ui-review','ui-cv-review','ui-approve','ui-select-opportunity','ui-contact-draft','ui-request-update','ui-delivery-check','ui-offer-assessment','ui-source-review'):
        from onboarding import require_ready
        require_ready(data)
    import source_reviews, application_lifecycle
    if application_lifecycle.handle(data,op,__import__('sys').modules[__name__]):pass
    elif source_reviews.handle(data,op):pass
    elif context.handle(data,op):pass
    elif kind=='ui-criteria-scope':
        expect(data['revision'],op.get('expectedRevision'))
        if not op.get('proof'):raise ValueError('Explica por qué cambia el criterio de estas ofertas')
        if op.get('mode') not in ('current','round'):raise ValueError('Elige criterios actuales o de la ronda')
        tags=app.get('offerRounds',{})
        rows={r['ID'] for r in data['sheets']['Oportunidades']}
        ids={target['id'] for target in op.get('targets',[])}
        if op.get('round'):ids|={key for key,value in tags.items() if value==op['round']}
        if not ids:raise ValueError('Indica ofertas o una ronda')
        if ids-rows:raise ValueError('Hay ofertas desconocidas')
        if op['mode']=='round' and ids-set(tags):raise ValueError('Hay ofertas que no pertenecen a ninguna ronda')
        adopted=set(app.get('currentCriteria',[]))
        adopted=adopted|ids if op['mode']=='current' else adopted-ids
        app['currentCriteria']=sorted(adopted)
        if op.get('searchProfileId') or 'searchProfiles' in app:
            import search_profiles
            search_profiles.migrate(data)
            if op['mode']=='current' and len(search_profiles.profiles(data))>1 and not op.get('searchProfileId'):
                raise ValueError('Indica searchProfileId para cambiar la base de evaluación')
            if op['mode']=='round' and any(not next((r.get('round') for r in app['requests'] if r['id']==tags[key]),None) for key in ids):
                raise ValueError('No consta una copia histórica de esa búsqueda para recuperar')
            profile=search_profiles.get(data,op.get('searchProfileId'),available=op['mode']=='current')
            for key in ids:
                if op['mode']=='current':app['offerCriteria'][key]={'searchProfileId':profile['id']}
                else:app['offerCriteria'].pop(key,None)
        record(data,'Criterios de ronda cambiados',actor=actor,detail=op['proof'])
    elif kind=='ui-minimum-reconcile':
        expect(data['revision'],op.get('expectedRevision'))
        if not op.get('proof'):raise ValueError('Explica el alcance de la reclasificación de mínimos')
        record(data,'Requisitos mínimos actualizados',actor=actor,detail=op['proof'])
    elif kind in ('ui-offer-note','ui-offer-context'):
        from onboarding import require_ready
        require_ready(data)
        row=row_for(data,op_id)
        keys=('Notas de seguimiento',) if kind=='ui-offer-note' else ('Requisitos de la oferta','Notas de seguimiento')
        values=op.get('values')
        if not isinstance(values,dict) or set(values)!=set(keys) or any(not isinstance(v,str) or len(v)>10000 for v in values.values()):
            raise ValueError('Indica los requisitos y notas por separado, como texto')
        expected={key:row.get(key) for key in keys}
        if kind=='ui-offer-context':expected['Observaciones']=row.get('Observaciones')
        expect(expected,op.get('expected'))
        if kind=='ui-offer-context' and not op.get('proof'):
            raise ValueError('Conserva cómo separaste los requisitos de las notas; no omitas condiciones del anuncio')
        row.update(values)
        record(data,'Nota de seguimiento guardada' if kind=='ui-offer-note' else 'Requisitos separados de las notas',op_id,actor,op.get('proof',''))
    elif kind=='ui-bulk-action':
        import offer_actions
        import sys
        offer_actions.handle(data,op,__import__('sys').modules[__name__])
    elif kind=='ui-contact-draft':
        row_for(data,op_id)
        recipient=op.get('recipient');message=op.get('message');purpose=op.get('purpose','Contacto sobre la oferta')
        if not all(isinstance(v,str) and v.strip() for v in (recipient,message,purpose)) or len(recipient)>500 or len(message)>15000 or len(purpose)>200:
            raise ValueError('Completa destinatario, finalidad y texto del contacto')
        item={'id':digest([op_id,recipient.strip(),message.strip(),purpose.strip()]),'opportunityId':op_id,
              'recipient':recipient.strip(),'message':message.strip(),'purpose':purpose.strip(),'createdAt':now(),'actor':actor,'status':'draft'}
        drafts=app.setdefault('contactDrafts',[])
        if not any(d['id']==item['id'] for d in drafts):
            drafts.append(item);record(data,'Mensaje de contacto preparado',op_id,actor,'Borrador guardado; no se ha contactado con nadie.')
    elif kind=='ui-automation-settings':
        current=automation(data)
        values=op.get('values',{})
        if not isinstance(values,dict) or not values:raise ValueError('Ajustes no válidos')
        if set(values) & {'contactMode','searchTime'}:
            raise ValueError('Los ajustes globales de contacto y horario se han retirado.')
        if set(values)-{'applicationMode','searchFrequency','scheduleEnabled'}:raise ValueError('Ajustes no válidos')
        if 'scheduleEnabled' in values and values['scheduleEnabled'] is not False:
            raise ValueError('La programación local se ha retirado; prográmala en tu agente externo.')
        if 'searchFrequency' in values and values['searchFrequency']!='manual':
            raise ValueError('La programación local se ha retirado; prográmala en tu agente externo.')
        expect({k:current.get(k) for k in values},op.get('expected'))
        if 'applicationMode' in values and values['applicationMode'] not in ('review','auto'):
            raise ValueError('Elige cómo revisar los envíos')
        current.update(values)
        record(data,'Ajustes históricos actualizados',actor=actor)
    elif kind=='ui-schedule-attempt':
        raise ValueError('La programación local se ha retirado; continúa desde tu agente externo.')
    elif kind=='ui-select-opportunity':
        row=row_for(data,op_id)
        if row['Estado'] in CLOSED or archived(data,op_id) or any(e['type']=='sent' and e['opportunityId']==op_id for e in data['events']):
            raise ValueError('Esta oferta ya no se puede seleccionar')
        selected=op.get('selected')
        if type(selected) is not bool:raise ValueError('Indica si quieres solicitar esta oferta')
        choices=app['selections']
        expect(choices.get(op_id),op.get('expected'))
        previous=copy.deepcopy(choices.get(op_id))
        if not selected and previous is None:return
        if selected:
            if choices.get(op_id):raise ValueError('Esta oferta ya está seleccionada')
            import stubbs_jobs as j
            if j.conditions(data,row)[0] in ('No','Ya enviada','Resolver conflicto'):
                raise ValueError('Esta oferta tiene una incompatibilidad o contradicción. Revisa sus condiciones antes de solicitarla')
            mode=op.get('mode')
            if mode not in ('review','auto'):raise ValueError('Indica revisión final o envío automático para esta oferta')
            choices[op_id]={'id':uuid.uuid4().hex,'selected':True,'mode':mode,'at':now(),'actor':actor}
            ready=not readiness(data,op_id) and any(p['id']==stamp(data,op_id) for p in app['packages'])
            if ready and mode=='review':row['Siguiente paso']='Revisar el paquete completo y decidir si autorizas su envío.'
            if not (ready and mode=='review') and not any(r.get('opportunityId')==op_id and not r.get('interpretationOnly') and r['status'] in ('queued','running','blocked','interrupted') for r in app['requests']):
                before=len(app['requests'])
                request(data,op_id,'review' if payload(data,op_id)['cvHash'] else 'investigate',actor=actor)
                if len(app['requests'])>before:app['requests'][-1]['fromSelection']=True
            event=record(data,'Oferta seleccionada',op_id,actor,'Solicitud automática' if mode=='auto' else 'Solicitud con revisión')
        else:
            if any(r['type']=='send' and r['status']=='running' and r.get('opportunityId')==op_id for r in app['requests']):
                raise ValueError('El envío está en curso; comprueba su resultado antes de retirar la oferta')
            choices.pop(op_id,None)
            for p in app['packages']:
                if p['opportunityId']==op_id and p.get('approvedAt') and not p.get('revokedAt'):
                    p['revokedAt']=now()
            for req in app['requests']:
                if req.get('opportunityId')==op_id and req['status']=='queued' and (req.get('fromSelection') or req['type']=='send'):
                    req.update(status='cancelled',updatedAt=request_timestamp(req),result='La persona retiró esta oferta de su selección.')
            row['Siguiente paso']='Oferta retirada de la selección. Puedes volver a seleccionarla si te interesa.'
            event=record(data,'Oferta retirada de la selección',op_id,actor)
        app['undo'].append({'id':event['id'],'kind':'selection','opportunityId':op_id,'before':previous,'after':copy.deepcopy(choices.get(op_id)),'used':False})
    elif kind=='ui-profile':
        scope=op.get('scope','global'); target=data['profile'] if scope=='global' else draft(data,op_id)['answers']
        if scope not in ('global','opportunity'):raise ValueError('Indica el alcance global o particular de la respuesta')
        values=op['values']; before={k:target.get(k) for k in values}; absent=[k for k in values if k not in target]
        if 'minimumFixed' in values and 'searchProfiles' in app:
            raise ValueError('Guarda el mínimo en el perfil de búsqueda mediante ui-preferences y searchProfileId')
        expect(before,op['expected'])
        if 'workAuthorizations' in values:
            if scope!='global':raise ValueError('Los destinos con permiso se guardan en Mi perfil')
            validate_answer('workAuthorizations',values['workAuthorizations'])
            if values['workAuthorizations'] is not None and 'workPermitWithoutSponsorship' in values:
                compatible=True if any(v in ('España','Unión Europea') for v in values['workAuthorizations']) else None
                if values['workPermitWithoutSponsorship']!=compatible:raise ValueError('El permiso anterior de España debe coincidir con los destinos confirmados')
            # The compatibility answer is Spain-specific, never a universal work permit.
            if 'workPermitWithoutSponsorship' not in values:
                values={**values,'workPermitWithoutSponsorship':True if values['workAuthorizations'] and any(v in ('España','Unión Europea') for v in values['workAuthorizations']) else None}
            before['workPermitWithoutSponsorship']=target.get('workPermitWithoutSponsorship')
            if 'workPermitWithoutSponsorship' not in target:absent.append('workPermitWithoutSponsorship')
        fields=context.definitions(data,op_id)
        if scope=='global' and 'workAuthorizations' not in values and data['profile'].get('workAuthorizations') is not None and 'workPermitWithoutSponsorship' in values:
            compatible=True if any(v in ('España','Unión Europea') for v in data['profile']['workAuthorizations']) else None
            if values['workPermitWithoutSponsorship']!=compatible:raise ValueError('Actualiza los países con permiso en Mi perfil; este dato anterior solo corresponde a España')
        if scope=='global' and any(k.startswith('custom_') and fields.get(k,{}).get('scope')!='global' for k in values):
            raise ValueError('Esta pregunta pertenece a una oferta; su respuesta no puede guardarse en el perfil general')
        for key,value in values.items():validate_answer(key,value,context.definitions(data,op_id).get(key))
        if scope!='global' and any(k not in PERSONAL and k not in CONTACT_FIELDS and k not in DEMOGRAPHIC_FIELDS and not k.startswith('custom_') for k in values):raise ValueError('Ese límite es general, no por solicitud')
        target.update(values)
        changed={k:v for k,v in values.items() if before[k]!=v or k in absent}
        if changed:
            event=record(data,'Respuestas actualizadas',op_id,actor,', '.join(context.definitions(data,op_id)[k]['label'] for k in changed))
            event['changedFields']=[context.definitions(data,op_id)[k]['label'] for k in changed]
            app['undo'].append({'id':event['id'],'kind':'profile','scope':scope,'opportunityId':op_id,'before':before,'absent':absent,'after':values,'used':False})
        reconcile(data)
    elif kind=='ui-inherit':
        d=draft(data,op_id);expect(d['answers'],op['expected']);before=copy.deepcopy(d['answers']);d['answers']={}
        event=record(data,'Respuestas generales restauradas',op_id,actor)
        app['undo'].append({'id':event['id'],'kind':'draft','opportunityId':op_id,'before':{'answers':before},'after':{'answers':{}},'used':False})
    elif kind=='ui-draft':
        if not isinstance(op.get('values'),dict) or not isinstance(op.get('expected'),dict):
            raise ValueError('El borrador necesita campos y valores anteriores válidos')
        d=draft(data,op_id); expect({k:d.get(k) for k in op['values']},op['expected'])
        if set(op['values'])-{'message','recipient','answers','requiredAnswers','cvReason','changes','questions','messageUsage','formAnswerKeys'}:raise ValueError('Campo de borrador no admitido')
        values=op['values']
        if 'questions' in values:context.validate_questions(data,op_id,values['questions'])
        allowed_questions=set(FORM_FIELDS)|{f['key'] for f in values.get('questions',d.get('questions',[]))}
        if 'messageUsage' in values and values['messageUsage'] not in ('form','email','unused','unknown'):
            raise ValueError('Indica dónde se utiliza el texto de presentación')
        keys=values.get('formAnswerKeys',d.get('formAnswerKeys'))
        if keys is not None or 'formAnswerKeys' in values:
            if not isinstance(keys,list) or any(not isinstance(k,str) for k in keys) or len(set(keys))!=len(keys) or set(keys)-allowed_questions:
                raise ValueError('Indica las respuestas que pide el formulario')
        required=values.get('requiredAnswers',d['requiredAnswers'])
        if not isinstance(required,list) or any(not isinstance(k,str) for k in required) or len(set(required))!=len(required) or set(required)-allowed_questions:raise ValueError('Preguntas no admitidas')
        if 'answers' in values:
            if not isinstance(values['answers'],dict):raise ValueError('Las respuestas deben indicar cada pregunta y su valor')
            for k,v in values['answers'].items():validate_answer(k,v,({**context.definitions(data,op_id),**{f['key']:f for f in values.get('questions',[])}}).get(k))
        for key in ('message','recipient','cvReason','changes'):
            if key in values and (not isinstance(values[key],str) or len(values[key])>15000):raise ValueError('Texto inválido o demasiado largo')
        if all(d.get(k)==v for k,v in values.items()):return
        before={k:copy.deepcopy(d.get(k)) for k in values}; absent=[k for k in values if k not in d]
        d.update(values);d['updatedAt']=now()
        event=record(data,'Borrador actualizado',op_id,actor)
        app['undo'].append({'id':event['id'],'kind':'draft','opportunityId':op_id,'before':before,'absent':absent,'after':copy.deepcopy(values),'used':False})
    elif kind=='ui-review':
        d=draft(data,op_id)
        if d.get('messageUsage') not in ('form','email','unused') or not isinstance(d.get('formAnswerKeys'),list):
            raise ValueError('Comprueba si el destino utiliza presentación e indica messageUsage y formAnswerKeys antes de revisar el paquete; no uses el mínimo interno como respuesta.')
        if set(d['requiredAnswers'])-set(d['formAnswerKeys']):
            raise ValueError('Las preguntas obligatorias deben figurar entre las respuestas que pide el destino')
        if not (selection(data,op_id) or {}).get('selected'):
            raise ValueError('Elige la oferta antes de preparar su envío')
        if not op.get('proof') or not all(op.get('checks',{}).get(k) is True for k in CHECKS):raise ValueError('La revisión necesita las cinco comprobaciones y su prueba')
        if op.get('fingerprint')!=stamp(data,op_id):raise Conflict('El paquete cambió durante la revisión')
        d['cvReview']={'cvHash':payload(data,op_id)['cvHash'],'fingerprint':context.cv_stamp(data,op_id),'at':now(),'proof':op['proof']}
        d['checks']=op['checks'];d['review']={'at':now(),'proof':op['proof'],'fingerprint':stamp(data,op_id)}
        if readiness(data,op_id):raise ValueError('Todavía faltan datos o condiciones: '+', '.join(readiness(data,op_id)))
        p=archive(data,op_id)
        row_for(data,op_id)['Paquete listo desde']=now()
        row_for(data,op_id)['Estado']='Lista para revisión'
        row_for(data,op_id)['Siguiente paso']='Revisar el paquete completo y decidir si autorizas su envío.'
        for block in data['blocks']:
            if block['id']=='send-'+op_id:block['status']='resolved'
        record(data,'Paquete listo para tu decisión',op_id,detail=op['proof'],artifact=p['id'])
        choice=selection(data,op_id)
        if choice and choice.get('selected') and choice.get('mode')=='auto' and not pending_change(data,op_id,exclude_owner=True):
            require_delivery_resolved(data,op_id)
            same_authorization=(p.get('approvedAt') and not p.get('revokedAt') and
                p.get('approvalSource')=='selection' and selection_matches(choice,p.get('selectionAt'),p.get('selectionId')))
            # Rechecking identical material does not replace the permission that
            # its queued causal continuation already references.
            if not same_authorization:p['approvedAt']=now()
            p.pop('revokedAt',None)
            p['approvalSource']='selection';p['selectionAt']=choice['at']
            if choice.get('id') is not None:p['selectionId']=choice['id']
            else:p.pop('selectionId',None)
            row_for(data,op_id)['Siguiente paso']='Envío autorizado para esta oferta. Pendiente de confirmación real del portal.'
            request(data,op_id,'send',p['id'],actor='Sistema',continuation=causal_continuation(data,op_id,p))
            record(data,'Envío autorizado por selección de la oferta',op_id,actor,artifact=p['id'])
    elif kind=='ui-approve':
        require_delivery_resolved(data,op_id)
        if any(e['type']=='sent' and e['opportunityId']==op_id for e in data['events']):raise ValueError('Esta solicitud ya está enviada')
        if any(r['type']=='send' and r.get('opportunityId')==op_id and r['status']=='running' for r in app['requests']):raise ValueError('El envío ya está en curso; espera su confirmación')
        if not (selection(data,op_id) or {}).get('selected'):
            raise ValueError('Elige la oferta antes de autorizar su envío')
        if pending_change(data,op_id):raise ValueError('Hay cambios pendientes. Revisa la nueva solicitud antes de autorizar.')
        expect(stamp(data,op_id),op['fingerprint'])
        if readiness(data,op_id):raise ValueError('El paquete todavía necesita revisión: '+', '.join(readiness(data,op_id)))
        p=archive(data,op_id);p['approvedAt']=now();p.pop('revokedAt',None);p['approvalSource']='manual'
        row_for(data,op_id)['Siguiente paso']='Envío autorizado. Pendiente de que el agente lo ejecute y confirme.'
        record(data,'Envío autorizado; pendiente de ejecución',op_id,actor,artifact=p['id'])
        request(data,op_id,'send',p['id'])
    elif kind=='ui-revoke':
        p=next(x for x in app['packages'] if x['id']==op['packageId'])
        if any(e.get('packageId')==p['id'] and e['type']=='sent' for e in data['events']):raise ValueError('El envío ya está confirmado y no se puede deshacer')
        p['revokedAt']=now()
        running=any(r.get('packageId')==p['id'] and r['status']=='running' for r in app['requests'])
        row_for(data,p['opportunityId'])['Siguiente paso']='Permiso retirado. Pide al agente que detenga el paso en curso y compruebe si llegó a enviarse.' if running else 'Autorización retirada. Revisar el paquete antes de decidir un nuevo envío.'
        for r in app['requests']:
            if r.get('packageId')==p['id'] and r['status'] in ('queued','blocked','interrupted'):r.update(status='cancelled',updatedAt=request_timestamp(r))
        record(data,'Autorización retirada',p['opportunityId'],actor,'No detiene instantáneamente un formulario ya iniciado. Su resultado debe comprobarse.' if running else '')
    elif kind=='ui-request':request(data,op_id,op['type'],actor=actor,purpose=op.get('purpose'),search_profile_id=op.get('searchProfileId'))
    elif kind in ('ui-request-update','ui-request-interrupt','ui-delivery-check','ui-recover-backup'):
        import request_workflow
        request_workflow.handle(data,op)
    elif kind=='ui-offer-assessment':
        import offer_quality
        import sys
        offer_quality.assess(data,op,__import__('sys').modules[__name__])
    elif kind=='ui-dispatch-attempt':
        raise ValueError('El lanzador local se ha retirado; continúa desde tu agente externo.')
    elif kind=='ui-snooze':
        if op_id:row_for(data,op_id)
        until=op.get('until')
        if until is not None and not instant(until):raise ValueError('El recordatorio necesita una fecha válida con zona horaria')
        key=op_id or 'profile'; before=app['snoozes'].get(key);app['snoozes'][key]=until
        event=record(data,'Recordatorio pospuesto' if until else 'Recordatorio recuperado',op_id,actor,until or '')
        app['undo'].append({'id':event['id'],'kind':'snooze','key':key,'before':before,'after':until,'used':False})
    elif kind=='ui-seen':
        seen=instant(op.get('at'));previous=instant(app.get('seenAt'))
        if seen is None or seen>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('Las novedades necesitan una fecha válida con zona horaria')
        if previous is None or seen>previous:app['seenAt']=op['at']
    elif kind=='ui-undo':
        item=next(x for x in app['undo'] if x['id']==op['id'] and not x['used'])
        expect(undo_current(data,item),item['after'])
        if item['kind']!='offer-archive' and any(r['type']=='send' and r['status']=='running' and (not item.get('opportunityId') or r.get('opportunityId')==item['opportunityId']) for r in app['requests']):
            raise ValueError('Hay un envío en curso. Espera su confirmación antes de deshacer.')
        if not undo_available(data,item):raise ValueError('Este cambio ya no se puede deshacer. Comprueba la actividad de la solicitud.')
        if item['kind']=='offer-archive':
            for key,value in item['before'].items():
                if value is None:app['offerArchives'].pop(key,None)
                else:app['offerArchives'][key]=copy.deepcopy(value)
            record(data,'Archivo deshecho',actor=actor,detail='Ofertas recuperadas sin restaurar selecciones ni permisos de envío.')
        elif item['kind']=='selection':
            # Recovering a selection never recovers an old send permission.
            handle(data,{'kind':'ui-select-opportunity','opportunityId':item['opportunityId'],'selected':bool(item['before']),
                         'mode':'review','expected':item['after'],'actor':actor})
        elif item['kind']=='section':
            handle(data,{'kind':'ui-profile-section','section':item['section'],'values':item['before'],'expected':item['after'],'actor':actor,
                         **({'searchProfileId':item['searchProfileId']} if item.get('searchProfileId') else {})})
        elif item['kind']=='experience':
            if item.get('absent'):app.pop('experience',None)
            else:app['experience']=item['before']
            context.add_change(data,None,'Revisar los materiales con la experiencia recuperada del Perfil.',actor)
        elif item['kind']=='responses':
            for scope,values in item['before'].items():
                target=data['profile'] if scope=='global' else draft(data,item['opportunityId'])['answers']
                target.update(values)
                for key in item['absent'].get(scope,[]):target.pop(key,None)
        elif item['kind']=='change':
            req=next(r for r in app['requests'] if r['id']==item['requestId'])
            req['instructions']=copy.deepcopy(item['before'])
            if not req['instructions']:req.update(status='cancelled',updatedAt=request_timestamp(req),result='Petición deshecha antes de iniciar.')
        elif item['kind']=='snooze':
            expect(app['snoozes'].get(item['key']),item['after']);app['snoozes'][item['key']]=item['before']
        else:
            target=(data['profile'] if item.get('scope')=='global' else draft(data,item['opportunityId'])['answers']) if item['kind']=='profile' else draft(data,item['opportunityId'])
            expect({k:target.get(k) for k in item['after']},item['after']);target.update(item['before'])
            absent=item.get('absent',[])
            if item['kind']=='draft' and 'absent' not in item:
                # Older undo records used None for optional draft fields that did
                # not exist. Restoring that sentinel would create invalid lists.
                absent=[key for key in ('questions','messageUsage','formAnswerKeys') if key in item['before'] and item['before'][key] is None]
            for key in absent:target.pop(key,None)
        item['used']=True;record(data,'Cambio deshecho',item.get('opportunityId'),actor)
    else:raise ValueError('Acción de aplicación desconocida')
    reconcile(data)

def auto_review(data,op_id):
    """Hand changed, complete material to the agent; never authorize a send."""
    import stubbs_jobs as j
    row=row_for(data,op_id);p=payload(data,op_id)
    for req in state(data)['requests']:
        if req['opportunityId']==op_id and req['type']=='send' and req['status']=='queued':
            req.update(status='cancelled',updatedAt=request_timestamp(req),result='El material cambió. Se requiere revisar y autorizar la versión nueva.')
            pack=next(p for p in state(data)['packages'] if p['id']==req['packageId'])
            pack['revokedAt']=now()
            record(data,'Envío suspendido por cambios',op_id,'Sistema',req['result'])
    if not (selection(data,op_id) or {}).get('selected'):return
    if j.conditions(data,row)[0] not in ('Sí','Sí, aclarar'):return
    if not p['cvHash'] or not p['recipient'].strip():return
    if p.get('messageUsage')!='unused' and not p['message'].strip():return
    if any(p['answers'].get(k) in (None,'') for k in p['requiredAnswers']):return
    # Material produced by the owner is part of its current preparation. User
    # edits use interface_writer (no owner), so they still create a continuation.
    owner=execution_id()
    if owner and any(req.get('opportunityId')==op_id and req['type'] in ('review','investigate') and
                     req['status']=='running' and req.get('executionId')==owner and
                     not req.get('interpretationOnly') and owner not in req.get('invalidatedExecutionIds',[])
                     for req in state(data)['requests']):return
    for req in state(data)['requests']:
        if req.get('opportunityId')==op_id and req['type']=='review' and req['status']=='blocked' and req.get('need')=='answers':
            req.update(status='queued',autoStart=True,updatedAt=request_timestamp(req),result='Respuestas guardadas. Comprobarlas antes de continuar.')
            req.pop('summary',None);req.pop('need',None)
            req.pop('launchAttemptedAt',None);req.pop('executionId',None)
    request(data,op_id,'review',actor='Sistema')

def discovery_result(data,req,at):
    """Preserve this attempt's outcomes; later searches cannot rewrite its coverage."""
    import personalization
    import source_reviews
    baseline=req.get('discoveryBaseline')
    started=instant(req.get('startedAt'))
    finished=instant(at)
    try:
        import search_profiles
        expected=personalization.public_sources(search_profiles.discovery_data(data,req))
        configuration_error=None
    except (OSError,ValueError,TypeError,KeyError):
        expected=[]
        configuration_error='No se pudo leer la configuración de webs.'
    checked=[]
    for source in expected:
        health=next((h for h in reversed(req.get('scanChecks',[])) if h.get('sourceId')==source['id']),None)
        if health is None:
            health={} if (req.get('round') or {}).get('searchProfileId') else data.get('sourceHealth',{}).get(source['id'],{})
        checked_at=instant(health.get('checkedAtUtc'))
        if started and finished and checked_at and started<=checked_at<=finished:
            checked.append(copy.deepcopy({key:health.get(key) for key in ('sourceId','company','status','checkedAtUtc','lastSuccessUtc','errors','coverage','sourceUrl','scope','method') if key in health}))
    result={'at':at,'health':checked,
            'publicSources':[{'id':source['id'],'company':source['company']} for source in expected],
            'sourceConfigurationError':configuration_error,
            'portalAccess':copy.deepcopy({key:value for key,value in state(data).get('portalAccess',{}).items()
                if started and instant(value.get('checkedAt')) and started<=instant(value['checkedAt'])<=finished})}
    manual=source_reviews.snapshot(data,req,at,configuredSources=expected)
    result['manualReviews']=manual['reviews']
    result['scanChecks']=copy.deepcopy(checked)
    by_source={item['sourceId']:item for item in checked}
    for item in manual['health']:
        previous=by_source.get(item['sourceId'])
        if not previous or instant(item['checkedAtUtc'])>=instant(previous['checkedAtUtc']):by_source[item['sourceId']]=item
    result['health']=list(by_source.values())
    sources={item['id']:item for item in result['publicSources']}
    for item in manual['publicSources']:sources.setdefault(item['id'],item)
    result['publicSources']=list(sources.values())
    if isinstance(baseline,list) and started:
        before=set(baseline)
        if 'discoveredOpportunityIds' in req or (req.get('round') or {}).get('searchProfileId'):
            result['newOpportunityIds']=[key for key in req.get('newOpportunityIds',[]) if key in {row['ID'] for row in data['sheets']['Oportunidades']}]
            result['seenOpportunityIds']=list(req.get('discoveredOpportunityIds',[]))
        else:result['newOpportunityIds']=[row['ID'] for row in data['sheets']['Oportunidades'] if row['ID'] not in before]
        result['newOfferCount']=len(result['newOpportunityIds'])
    return result


def search_round(data,search_profile_id=None):
    """Criteria at request creation; later edits never rewrite them."""
    from search_profiles import snapshot
    return snapshot(data,search_profile_id)

def rounds(data):
    """One entry per search that recorded its criteria, oldest first.

    Eligibility is read with the criteria in force now, so a round shows what
    its offers are worth today, not what they were worth when found."""
    import offer_minimums
    app=state(data)
    tags=app.get('offerRounds',{})
    rows={r['ID']:r for r in data['sheets']['Oportunidades']}
    sent={e['opportunityId'] for e in data['events'] if e['type']=='sent'}
    result,previous=[],None
    for req in app['requests']:
        snapshot=req.get('round')
        if req['type']!='discovery' or not snapshot:continue
        found=[k for k,v in tags.items() if v==req['id'] and k in rows]
        flat={**snapshot['criteria'],**{'searchContext.'+k:v for k,v in snapshot['searchContext'].items()}}
        changed=sorted(k for k in set(flat)|set(previous) if flat.get(k)!=previous.get(k)) if previous is not None else []
        result.append({'requestId':req['id'],'status':req['status'],'startedAt':req.get('startedAt'),'changed':changed,
                       'searchProfileId':snapshot.get('searchProfileId'),'searchProfileName':snapshot.get('searchProfileName'),
                       'seenOffers':len(req.get('discoveredOpportunityIds',found)),
                       'newOffers':len(found),'eligibleNow':sum(1 for k in found if offer_minimums.view(data,rows[k])['canApply']),
                       'archivedNow':sum(1 for k in found if archived(data,k)),'sent':sum(1 for k in found if k in sent)})
        previous=flat
    return result

def request(data,op_id,kind,package_id=None,actor='Usuario',continuation=None,interpretation_only=False,purpose=None,search_profile_id=None):
    from onboarding import require_ready
    require_ready(data)
    if kind=='mail':raise ValueError('La búsqueda en correo se ha retirado de Stubbs Jobs')
    if kind not in ('review','investigate','send','discovery','change'):raise ValueError('Encargo desconocido')
    if op_id and kind != 'discovery':
        from application_lifecycle import achievement
        if achievement(data,row_for(data,op_id)):raise ValueError('La solicitud está lograda; su seguimiento ha terminado')
    if kind in ('review','investigate','send'):
        row=row_for(data,op_id)
        sent=any(e['type']=='sent' and e['opportunityId']==op_id for e in data['events'])
        if purpose is not None and (purpose!='followup' or kind!='investigate' or not sent):raise ValueError('El seguimiento comprueba una candidatura ya enviada')
        if row['Estado'] in CLOSED or sent and purpose!='followup':raise ValueError('Esta oferta está cerrada o ya enviada; no necesita otra preparación')
    if kind!='change' and op_id and archived(data,op_id):raise ValueError('Esta oferta está cerrada; recupérala antes de crear trabajo nuevo')
    if kind in ('review','send') and not (selection(data,op_id) or {}).get('selected'):
        raise ValueError('Selecciona la oferta antes de preparar o enviar su solicitud')
    if kind=='send' and (not package_id or not approved_package(data,op_id,package_id)):
        raise ValueError('El envío necesita un paquete aprobado')
    if kind=='send':require_delivery_resolved(data,op_id)
    app=state(data)
    snapshot=search_round(data,search_profile_id) if kind=='discovery' else None
    if kind=='discovery' and 'searchProfiles' in app and not (
            snapshot['searchContext'].get('targetRoles','').strip() and
            (snapshot['criteria'].get('location','').strip() or snapshot['searchContext'].get('regions','').strip())):
        raise ValueError('Completa los puestos y la zona de este perfil antes de buscar')
    search_key=digest({k:v for k,v in snapshot.items() if k not in ('searchProfileName','profileRevision')}) if snapshot else None
    for r in app['requests']:
        if r['type']!=kind or r.get('opportunityId')!=op_id or r.get('packageId')!=package_id:continue
        if r.get('purpose')!=purpose:continue
        if kind=='change':
            if r['status']=='queued' and bool(r.get('interpretationOnly'))==interpretation_only:return
            continue
        if kind=='discovery':
            old=r.get('searchKey') or (digest({k:v for k,v in r['round'].items() if k not in ('searchProfileName','profileRevision')}) if r.get('round') else None)
            if old is not None and old!=search_key:continue
        if kind=='review' and r['status']=='running' and r.get('materialFingerprint')!=stamp(data,op_id):continue
        if r['status'] in ('queued','running','blocked','interrupted'):return
    req={'id':'req-'+digest([now(),len(app['requests']),op_id,kind])[:16],'type':kind,'opportunityId':op_id,'packageId':package_id,'status':'queued','createdAt':now(),'result':'Pendiente de la próxima ejecución del agente.'}
    if snapshot:
        req['round']=copy.deepcopy(snapshot);req['searchKey']=search_key
        if snapshot.get('searchProfileId'):req['searchProfileId']=snapshot['searchProfileId']
    if purpose:req['purpose']=purpose
    if kind=='change' and interpretation_only:req['interpretationOnly']=True
    req['updatedAt']=request_timestamp(req)
    if kind=='review':req['materialFingerprint']=stamp(data,op_id)
    if kind=='send' and continuation:req['continuation']=copy.deepcopy(continuation)
    req['autoStart']=actor in ('Usuario','Usuario','Sistema')
    app['requests'].append(req)
    if kind!='change':record(data,{'review':'Revisión solicitada','investigate':'Investigación solicitada','send':'Envío puesto en cola','discovery':'Búsqueda solicitada','change':'Cambio pendiente del agente'}[kind],op_id,actor)['requestId']=req['id']
