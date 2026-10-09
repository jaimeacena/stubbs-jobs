"""Small, explicit contracts for profile criteria, questions and contextual work."""
import re
import view_cache
from stubbs_jobs_core import digest, now

DEFAULT_CRITERIA={'contract':'Indefinido','location':'Remoto habitual desde España/tu ubicación','maxTrips':1}

def offer_requirements(row):
    """Recorded requirements are decision inputs, unlike discovery configuration."""
    # Legacy observations stay conservative until an explicit, recorded split.
    detail='Requisitos de la oferta' if isinstance(row.get('Requisitos de la oferta'),str) else 'Observaciones'
    return {key:row[key] for key in ('Tecnologías',detail) if row.get(key) not in (None,'')}

# Settings that belong to one search round. Languages, companies to avoid and
# notice period describe the person and always follow their current value.
ROUND_CONTEXT=('targetRoles','keywords','searchPriorities','regions','workMode','onsiteLocations','currency','searchNotes')

def round_snapshot(data,op_id):
    """Criteria of the search that found the offer, unless the person moved it to the current ones."""
    app=data.get('app',{})
    from search_profiles import effective_snapshot
    assigned=effective_snapshot(data,op_id)
    if assigned:return assigned
    request_id=app.get('offerRounds',{}).get(op_id)
    if not request_id or op_id in app.get('currentCriteria',()):return None
    for request in app.get('requests',()):
        if request.get('id')==request_id:return request.get('round')
    return None

def scoped_criteria(data,op_id):
    snapshot=round_snapshot(data,op_id)
    now=criteria(data)
    if not snapshot:return now
    return {**now,**{key:value for key,value in snapshot['criteria'].items() if key!='noticeDays'}}

def scoped_search(data,op_id):
    from personalization import context
    now=context(data)
    snapshot=round_snapshot(data,op_id)
    if not snapshot:return now
    return {**now,**{key:snapshot['searchContext'].get(key,'') for key in ROUND_CONTEXT}}

def application_context(data,search=None):
    from personalization import context
    return {key:value for key,value in (context(data) if search is None else search).items() if key not in ('sourceUrls','platforms','checkMail')
            and (key not in ('workMode','searchPriorities','onsiteLocations','searchNotes') or value)}

@view_cache.cached(lambda data:id(data))
def experience(data):
    import app_workflow as w
    if 'experience' in w.state(data):return w.state(data)['experience']
    path=w.ROOT/'perfil.md'
    if not path.exists():return ''
    section=path.read_text(encoding='utf-8').split('## Datos confirmados por Usuario',1)[-1].split('## ',1)[0].strip()
    # Operational preferences have their own editable source and must not be duplicated here.
    return '\n'.join(line for line in section.splitlines() if not line.startswith('- Preaviso contractual'))

@view_cache.cached(lambda data,key:(id(data),key))
def cv_stamp(data,key):
    import app_workflow as w
    row=w.row_for(data,key);content=w.cv_bytes(row)
    basis={'cvHash':digest(content) if content else None,'experience':experience(data),
           'opportunityId':key,'title':row['Puesto'],'url':row['URL original']}
    if offer_requirements(row):basis['offerRequirements']=offer_requirements(row)
    contacts={k:data['profile'][k] for k in w.CONTACT_FIELDS if data['profile'].get(k) not in (None,'')}
    if contacts:basis['profileContacts']=contacts
    return digest(basis)

def criteria(data,search_profile_id=None):
    result={**DEFAULT_CRITERIA,**data.get('app',{}).get('criteria',{}),
            'minimumFixed':data['profile'].get('minimumFixed',32000),
            'noticeDays':data['profile'].get('noticeDays',15)}
    if data.get('_discoverySnapshot'):result.update(data['_discoverySnapshot']['criteria'])
    elif search_profile_id or 'searchProfiles' in data.get('app',{}):
        import search_profiles
        result.update(search_profiles.get(data,search_profile_id)['criteria'])
    return result

@view_cache.cached(lambda data,row:(id(data),row['ID']))
def fit_stamp(data,row):
    criteria_now=scoped_criteria(data,row['ID'])
    if 'searchContext' in data.get('app',{}):
        # An empty new field must not invalidate packets prepared before it existed.
        criteria_now={**criteria_now,'searchContext':application_context(data,scoped_search(data,row['ID']))}
    basis={'criteria':criteria_now,'row':{k:row.get(k) for k in (
        'URL original','Puesto','Remoto España','Indefinido','Viajes ≤1/mes','Fijo ≥32 k€',
        'Fijo mín. confirmado','Vigencia','Horario real','Banda publicada')}}
    if data['profile'].get('workAuthorizations') is not None:basis['workAuthorizations']=data['profile']['workAuthorizations']
    if data['profile'].get('currentCountry') not in (None,''):basis['currentCountry']=data['profile']['currentCountry']
    if offer_requirements(row):basis['offerRequirements']=offer_requirements(row)
    for key in ('Fijo máx. confirmado','Moneda fijo confirmado','Viajes mín. al mes','País','Ubicación','Modalidad','Contrato'):
        if row.get(key) is not None:basis['row'][key]=row[key]
    return digest(basis)

@view_cache.cached(lambda data:id(data))
def question_catalog(data):
    """Keep meanings even after a draft stops asking a question."""
    import app_workflow as w
    catalog=w.state(data).setdefault('questionCatalog',{})
    if not w.state(data).get('questionCatalogInitialized'):
        for batch in data.get('changes',[]):
            for op in batch.get('operations',[]):
                if op.get('kind')!='ui-draft':continue
                for field in op.get('values',{}).get('questions',[]):
                    previous=catalog.get(field['key'])
                    if previous is not None and previous!=field:raise ValueError('Hay definiciones históricas contradictorias; conciliar antes de continuar')
                    catalog[field['key']]=dict(field)
        w.state(data)['questionCatalogInitialized']=True
    for d in w.state(data)['drafts'].values():
        for field in d.get('questions',[]):
            previous=catalog.get(field['key'])
            if previous is not None and previous!=field:
                raise ValueError('Hay definiciones contradictorias de una pregunta; conciliar antes de continuar')
            catalog[field['key']]=dict(field)
    return catalog

@view_cache.cached(lambda data,op_id=None:(id(data),op_id))
def definitions(data,op_id=None):
    import app_workflow as w
    result={k:{'key':k,'label':label,'type':'boolean' if k=='workPermitWithoutSponsorship' else 'text' if k in ('currentCity','noticeDays') else 'number','scope':'global'} for k,label in w.LABELS.items()}
    result['workAuthorizations']={'key':'workAuthorizations','label':'Permiso de trabajo sin patrocinio en','type':'multiselect','scope':'global'}
    result.update({k:{'key':k,'type':'text','scope':'global',**definition} for k,definition in w.CONTACT_FIELDS.items()})
    result.update({k:{'key':k,'scope':'global',**definition} for k,definition in w.DEMOGRAPHIC_FIELDS.items()})
    if data.get('app',{}).get('personalized'):
        from personalization import context
        if data['profile'].get('workAuthorizations') is None:result['workPermitWithoutSponsorship']['label']='Permiso de trabajo en el destino, sin patrocinio (dato anterior)'
        result['salaryExpectationFixed']['label']='Salario deseado (bruto anual, '+data['profile'].get('salaryCurrency',context(data)['currency'])+')'
    result['salaryCurrency']={'key':'salaryCurrency','label':'Moneda del salario para formularios','type':'text','scope':'global'}
    for field in question_catalog(data).values():
        if field['scope']=='global':result[field['key']]=field
    for field in w.state(data)['drafts'].get(op_id,{}).get('questions',[]):
        result[field['key']]=field
    return result

def validate_questions(data,op_id,fields):
    if not isinstance(fields,list) or len(fields)>30:raise ValueError('Revisa la lista de preguntas')
    seen=set();catalog=question_catalog(data)
    for f in fields:
        if not isinstance(f,dict) or set(f)-{'key','label','type','scope'}:raise ValueError('Pregunta no válida')
        key=f.get('key','')
        if not re.fullmatch(r'custom_[a-z][a-z0-9_]{0,59}',key) or key in seen:raise ValueError('Identificador de pregunta no válido')
        if not isinstance(f.get('label'),str) or not 1<=len(f['label'].strip())<=200:raise ValueError('La pregunta necesita un texto claro')
        if f.get('type') not in ('text','number','boolean') or f.get('scope') not in ('global','opportunity'):raise ValueError('Tipo de pregunta no válido')
        if key in catalog and catalog[key]!=f:raise ValueError('Esta pregunta ya tiene otro significado; utiliza otra clave')
        catalog[key]=dict(f)
        seen.add(key)

def validate_custom(field,value):
    if value is None:return
    kind=field['type']
    if kind=='boolean' and type(value) is not bool:raise ValueError('Elige Sí, No o Sin responder')
    if kind=='number' and (type(value) not in (int,float) or not -1000000<=value<=1000000):raise ValueError('Escribe un número válido')
    if kind=='text' and (not isinstance(value,str) or not value.strip() or len(value)>5000):raise ValueError('Escribe una respuesta de hasta 5000 caracteres')

def handle(data,op):
    import app_workflow as w
    import personalization
    if personalization.handle(data,op):return True
    app=w.state(data);kind=op['kind'];key=op.get('opportunityId');actor=op.get('actor','Agente')
    if kind=='ui-request-summary':
        r=next(r for r in app['requests'] if r['id']==op['id'])
        w.require_current_execution(r)
        if r['status']=='running':w.require_owner(r)
        w.expect(r['updatedAt'],op['expectedUpdatedAt'])
        if not isinstance(op.get('summary'),str) or not 1<=len(op['summary'].strip())<=300:raise ValueError('Escribe un resumen breve')
        if op.get('need') not in ('contact','answers','access','decision','other'):raise ValueError('Tipo de ayuda desconocido')
        r.update(summary=op['summary'].strip(),need=op['need'],updatedAt=w.request_timestamp(r,activity=False))
        return True
    if kind=='ui-responses':
        values=op['values'];fields=definitions(data,key)
        d=w.draft(data,key)
        editable=set(w.PERSONAL)|set(d['requiredAnswers'])|set(d.get('formAnswerKeys',[]))
        w.expect({k:w.answers(data,key).get(k) for k in values},op['expected'])
        before={};after={};absent={}
        for k,v in values.items():
            if k not in fields or k not in editable:raise ValueError('Pregunta desconocida')
            w.validate_answer(k,v,fields[k])
            scope='opportunity' if fields[k]['scope']=='opportunity' or k in w.draft(data,key)['answers'] else 'global'
            if k=='workPermitWithoutSponsorship' and scope=='global' and data['profile'].get('workAuthorizations') is not None:
                compatible=True if any(v in ('España','Unión Europea') for v in data['profile']['workAuthorizations']) else None
                if v!=compatible:raise ValueError('Actualiza los países con permiso en Mi perfil; esta pregunta anterior solo corresponde a España')
            target=w.draft(data,key)['answers'] if scope=='opportunity' else data['profile']
            before.setdefault(scope,{})[k]=target.get(k);after.setdefault(scope,{})[k]=v
            if k not in target:absent.setdefault(scope,[]).append(k)
            target[k]=v
        if before!=after or absent:
            event=w.record(data,'Respuestas guardadas',key,actor,', '.join(fields[k]['label'] for k in values))
            app['undo'].append({'id':event['id'],'kind':'responses','opportunityId':key,'before':before,'after':after,'absent':absent,'used':False})
        return True
    if kind=='ui-experience':
        w.expect(experience(data),op['expected'])
        text=op['text']
        if not isinstance(text,str) or not text.strip() or len(text)>20000:raise ValueError('Describe tu experiencia con un máximo de 20 000 caracteres')
        if experience(data)==text:return True
        old=experience(data);was_absent='experience' not in app;app['experience']=text
        event=w.record(data,'Experiencia actualizada',actor=actor)
        app['undo'].append({'id':event['id'],'kind':'experience','before':old,'after':text,'absent':was_absent,'used':False})
        add_change(data,None,'Revisar los CVs de base y las solicitudes pendientes con la experiencia actualizada del Perfil. No modificar copias enviadas.',actor)
        return True
    if kind=='ui-preferences':
        old=criteria(data,op.get('searchProfileId'));values=op['values']
        if set(values)-set(old):raise ValueError('Preferencia desconocida')
        w.expect({k:old[k] for k in values},op['expected'])
        for k,v in values.items():
            if k in ('minimumFixed','maxTrips') and v is None and not app.get('personalized'):raise ValueError('Escribe una cantidad entera')
            if k in ('contract','location') and (not isinstance(v,str) or not 1<=len(v.strip())<=300):raise ValueError('Describe la preferencia')
            if k=='maxTrips' and v is not None and (type(v) is not int or not 0<=v<=31):raise ValueError('Revisa el número de viajes')
            if k in ('minimumFixed','noticeDays'):
                if k=='minimumFixed' and v is not None and type(v) is not int:raise ValueError('Escribe una cantidad entera')
                w.validate_answer(k,v)
        changed={k:v for k,v in values.items() if v!=old[k]}
        if not changed:return True
        scoped=bool(op.get('searchProfileId') or 'searchProfiles' in app)
        if scoped:
            import search_profiles
            search_profiles.edit(data,op,criteria={k:v for k,v in changed.items() if k in search_profiles.CRITERIA_FIELDS})
            data['profile'].update({k:v for k,v in changed.items() if k not in search_profiles.CRITERIA_FIELDS})
        else:
            app['criteria']={**{k:old[k] for k in DEFAULT_CRITERIA},**{k:v for k,v in changed.items() if k in DEFAULT_CRITERIA}}
            data['profile'].update({k:v for k,v in changed.items() if k not in DEFAULT_CRITERIA})
        w.record(data,'Preferencias actualizadas',actor=actor,detail='El agente comprobará el encaje antes de preparar nuevos envíos.')
        if not scoped and any((w.selection(data,row['ID']) or {}).get('selected') and row['Estado'] not in w.CLOSED and not any(e['type']=='sent' and e['opportunityId']==row['ID'] for e in data['events']) for row in data['sheets']['Oportunidades']):
            add_change(data,None,'Comprobar el encaje de las ofertas activas con las preferencias actualizadas del Perfil.',actor)
        return True
    if kind=='ui-fit-review':
        row=w.row_for(data,key)
        w.expect(fit_stamp(data,row),op['fingerprint'])
        if type(op.get('apply')) is not bool or type(op.get('accept')) is not bool or not op.get('proof'):raise ValueError('Falta comprobar el encaje con las preferencias actuales')
        if op['accept'] and not op['apply']:raise ValueError('No se puede aceptar una oferta incompatible')
        from offer_minimums import view as minimums
        if op['apply'] != minimums(data,row)['canApply']:raise ValueError('La aptitud para solicitar depende solo de los mínimos explícitos; las dudas técnicas no la bloquean')
        app.setdefault('fitReviews',{})[key]={'fingerprint':op['fingerprint'],'apply':op['apply'],'accept':op['accept'],'proof':op['proof'],'at':now()}
        w.record(data,'Encaje comprobado',key,actor,op['proof']);return True
    if kind=='ui-cv-review':
        content=w.cv_bytes(w.row_for(data,key))
        if not content or digest(content)!=op.get('cvHash') or cv_stamp(data,key)!=op.get('fingerprint') or not op.get('proof'):raise ValueError('Hay que comprobar el CV y la experiencia actuales')
        w.draft(data,key)['cvReview']={'cvHash':digest(content),'fingerprint':op['fingerprint'],'proof':op['proof'],'at':now()}
        w.record(data,'CV revisado',key,actor,op['proof']);return True
    if kind=='ui-change':
        message=op.get('message')
        if not isinstance(message,str) or not message.strip() or len(message)>5000:raise ValueError('Describe el cambio o el dato que quieres aportar')
        if key and key.startswith('historical:'):
            record=next((h for h in data.get('historicalApplications',[]) if 'historical:'+str(h['id'])==key),None)
            if not record:raise ValueError('No existe ese registro anterior')
            label=record['company']+(' · '+record['title'] if record.get('title') else '')
            add_change(data,None,'Revisar únicamente la interpretación del registro anterior '+key+' ('+label+'): '+message.strip(),actor,interpretation_only=True)
            return True
        if key:w.row_for(data,key)
        add_change(data,key,message.strip(),actor);return True
    return False

def add_change(data,key,message,actor,interpretation_only=False):
    import app_workflow as w
    app=w.state(data)
    sent_ids={e['opportunityId'] for e in data['events'] if e['type']=='sent'}
    running_packages={r.get('packageId') for r in app['requests'] if r['type']=='send' and r['status']=='running'}
    interpretation_only=interpretation_only or bool(key and (key in sent_ids or w.archived(data,key) or w.row_for(data,key)['Estado'] in w.CLOSED or
                             any(r.get('opportunityId')==key and r['type']=='send' and r['status']=='running' for r in app['requests'])))
    existing=next((r for r in app['requests'] if r['type']=='change' and r.get('opportunityId')==key and r['status']=='queued' and bool(r.get('interpretationOnly'))==interpretation_only),None)
    if not existing:
        w.request(data,key,'change',actor=actor,interpretation_only=interpretation_only)
        existing=app['requests'][-1]
    if interpretation_only:existing['interpretationOnly']=True
    before=list(existing.get('instructions',[]))
    existing.setdefault('instructions',[]).append({'text':message,'at':now(),'actor':actor})
    existing['updatedAt']=w.request_timestamp(existing)
    existing['autoStart']=True;existing.pop('launchAttemptedAt',None)
    event=w.record(data,'Cambio pedido al agente',key,actor,message)
    app['undo'].append({'id':event['id'],'kind':'change','opportunityId':key,'requestId':existing['id'],'before':before,'after':list(existing['instructions']),'used':False})
    for request in app['requests']:
        if not interpretation_only and request['type']=='send' and request['status']=='running' and (key is None or request.get('opportunityId')==key):
            raise ValueError('El envío está en curso. Espera su confirmación antes de pedir cambios.')
        if not interpretation_only and request['type']=='send' and request['status']=='queued' and (key is None or request.get('opportunityId')==key):
            request.update(status='cancelled',updatedAt=w.request_timestamp(request),result='Hay cambios pendientes; revisar y autorizar la nueva solicitud.')
    for package in app['packages']:
        if not interpretation_only and (key is None or package['opportunityId']==key) and package['opportunityId'] not in sent_ids and package['id'] not in running_packages and package.get('approvedAt') and not package.get('revokedAt'):
            package['revokedAt']=now()
