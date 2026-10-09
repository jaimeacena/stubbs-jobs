"""First-run setup and user-owned context. No example person is seeded."""
import json
import ipaddress
import re
from urllib.parse import urlsplit
from stubbs_jobs_core import ROOT, now, identity, digest

SEARCH_PLATFORMS=('linkedin','infojobs','indeed','tecnoempleo','glassdoor','empresas')
FIT_CONTEXT={'targetRoles','keywords','searchPriorities','regions','workMode','onsiteLocations','languages','currency','previousApplications','searchNotes'}
CONTEXT={'name':'','targetRoles':'','keywords':'','searchPriorities':'','searchNotes':'','regions':'','workMode':'','onsiteLocations':'','languages':'','currency':'EUR','previousApplications':'','sourceUrls':'','platforms':'','checkMail':False}

def validate_work_authorizations(value):
    if value is None:return
    if not isinstance(value,list) or len(value)>40 or any(not isinstance(v,str) or not v.strip() or v!=v.strip() or len(v)>100 for v in value) or len(set(v.casefold() for v in value))!=len(value):
        raise ValueError('Selecciona países o zonas válidos, sin duplicados')

def display_title(row):
    translated=row.get('Puesto traducido')
    return translated.strip() if isinstance(translated,str) and translated.strip() else row['Puesto']

def validate_display_title(value,proof):
    if (not isinstance(proof,str) or not proof.strip() or value is not None and
            (not isinstance(value,str) or not value.strip() or len(value)>300)):
        raise ValueError('El título traducido necesita una traducción fiel y su prueba, conservando el puesto original')

def source_allowed(data,url):
    """A supplied site is an exclusive discovery origin; destinations are separate."""
    chosen=[line.strip() for line in context(data)['sourceUrls'].splitlines() if line.strip()]
    if not chosen:return True
    try:
        validate_public_source_url(url)
        host=urlsplit(url).hostname.lower().removeprefix('www.')
        for link in chosen:
            configured=urlsplit(link);allowed_host=configured.hostname.lower().removeprefix('www.')
            same=host==allowed_host or {host,allowed_host}<={'boards.greenhouse.io','job-boards.greenhouse.io'}
            if not same:continue
            if allowed_host in ('boards.greenhouse.io','job-boards.greenhouse.io','jobs.ashbyhq.com'):
                board=configured.path.strip('/').split('/')[0]
                if board and urlsplit(url).path.strip('/').split('/')[0]!=board:continue
            return True
        return False
    except (ValueError,AttributeError):return False
OPPORTUNITY_FIELDS=['ID','Empresa','Puesto','Puesto traducido','País','Ubicación','Modalidad','Contrato','Prioridad','Estado','Apta solicitar','Apta aceptar','Siguiente paso','Fecha objetivo','URL original','Fuente','Publicada','Revisada','Vigencia','Remoto España','Indefinido','Viajes ≤1/mes','Fijo ≥32 k€','Fijo mín. confirmado','Fijo máx. confirmado','Moneda fijo confirmado','Banda publicada','Horario real','Mañanas','Tecnologías','Familia','CV usado','Fecha candidatura','Cliente / duplicado posible','Observaciones','Requisitos de la oferta','Notas de seguimiento','Clave canónica','CV preparado','Oferta elegida']

def blank_store():
    from onboarding import initial
    from app_workflow import CONTACT_FIELDS
    return {'schemaVersion':2,'revision':0,'createdAt':now(),'updatedAt':now(),'workbookHash':None,'workbookRevision':0,
            'sheets':{key:[] for key in ('Oportunidades','Entradas','Evidencias','Actividad','Fuentes')},
            'events':[],'observations':{},'sourceHealth':{},'cycles':[],'historicalApplications':[],
            'historicalReconciliation':{'status':'pending','expectedCount':None,'source':'Pendiente de indicar candidaturas anteriores'},
            'blocks':[],'appliedBatches':[],'changes':[],
            'profile':{'currentCity':None,'workPermitWithoutSponsorship':None,'workAuthorizations':None,'salaryExpectationFixed':None,'minimumFixed':None,'noticeDays':None,
                       **dict.fromkeys(CONTACT_FIELDS)},
            'app':{'version':1,'personalized':True,'setupComplete':False,'assistantMode':'external','searchContext':{**CONTEXT,'currency':''},
                   'experience':'','criteria':{'contract':'Sin preferencia','location':'','maxTrips':None},
                   'drafts':{},'packages':[],'requests':[],'history':[],'snoozes':{},'seenAt':None,'undo':[],'cvLibrary':[],
                   'portalAccess':{},'onboarding':initial(),
                   'selections':{},'automation':{'applicationMode':'review'}}}

def context(data,search_profile_id=None):
    # Keep the retired flag false for older agents and saved profiles.
    result={**CONTEXT,**data.get('app',{}).get('searchContext',{}),'checkMail':False}
    if data.get('_discoverySnapshot'):
        from search_profiles import SEARCH_FIELDS
        return {**result,**{k:data['_discoverySnapshot']['searchContext'].get(k,'') for k in SEARCH_FIELDS}}
    if search_profile_id or 'searchProfiles' in data.get('app',{}):
        import search_profiles
        result.update(search_profiles.get(data,search_profile_id)['searchContext'])
    return result

def assistant_mode(data):
    # The dashboard has one agent handoff. Keep the stored legacy choice for
    # recovery, but never launch a second agent behind a copied instruction.
    return 'external'

def application_verification(data):
    saved=data.get('app',{}).get('applicationVerification',{})
    return {'enabled':saved.get('enabled') is True,'account':saved.get('account',''),
            'confirmedAt':saved.get('confirmedAt'),'proof':saved.get('proof','')}

def validate_context(values):
    if set(values)-set(CONTEXT):raise ValueError('Dato de búsqueda desconocido')
    for key,value in values.items():
        if key=='checkMail':
            if value is not False:raise ValueError('La búsqueda en correo se ha retirado de Stubbs Jobs')
        elif not isinstance(value,str) or len(value)>(10000 if key=='previousApplications' else 3000):raise ValueError('Revisa los datos de búsqueda')
    if values.get('currency') and not re.fullmatch('[A-Z]{3}',values['currency']):raise ValueError('Usa un código de moneda de tres letras, como EUR o USD')
    if 'platforms' in values:
        chosen=values['platforms'].split(',') if values['platforms'] else []
        if len(chosen)!=len(set(chosen)) or any(item not in SEARCH_PLATFORMS for item in chosen):
            raise ValueError('Elige plataformas de búsqueda válidas')
    for url in values.get('sourceUrls','').splitlines():
        if url.strip():validate_public_source_url(url.strip())

def validate_url(url):
    p=urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError('Introduce un enlace http o https válido, sin contraseñas')


def validate_public_source_url(url):
    """Source pages are fetched by the local scanner, unlike offer links."""
    validate_url(url)
    parsed=urlsplit(url)
    try:
        port=parsed.port
    except ValueError as exc:
        raise ValueError('La web pública tiene un puerto no válido') from exc
    host=parsed.hostname.lower().rstrip('.')
    if host=='localhost' or host.endswith(('.local','.localhost','.internal','.test','.invalid')):
        raise ValueError('La web pública no puede ser una dirección local')
    if parsed.scheme!='https' or port not in (None,443) or not host or '.' not in host:
        raise ValueError('Añade una web pública https, sin puerto especial')
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError('La web pública no puede ser una dirección local')

def validate_source_configuration(value):
    """Validate configured boards before their IDs become filenames or fetches."""
    if isinstance(value,dict):
        value=value.get('sources')
    if not isinstance(value,list):raise ValueError('La configuración de webs necesita una lista sources válida')
    ids=set()
    reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    for source in value:
        if not isinstance(source,dict):raise ValueError('Cada web configurada necesita un objeto con sus datos')
        identifier=source.get('id')
        if (not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}',identifier) or
                identifier.endswith('.') or identifier.split('.')[0].upper() in reserved):
            raise ValueError('El identificador de la web no puede ser una ruta ni un nombre reservado')
        if identifier.casefold() in ids:raise ValueError('Las webs configuradas no pueden compartir identificador')
        ids.add(identifier.casefold())
        company=source.get('company');kind=source.get('kind')
        if not isinstance(company,str) or not company.strip() or len(company)>300:
            raise ValueError('La web configurada necesita un nombre de empresa válido')
        if not isinstance(kind,str) or not kind.strip() or len(kind)>100:
            raise ValueError('La web configurada necesita un tipo de fuente válido')
        if 'enabled' in source and type(source['enabled']) is not bool:
            raise ValueError('Indica con true o false si la web está activa')
        if kind in ('greenhouse','ashby'):
            board=source.get('board')
            if not isinstance(board,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}',board):
                raise ValueError('La web de ofertas necesita un identificador de portal válido')
        if kind=='html' or 'url' in source:
            url=source.get('url')
            if not isinstance(url,str) or len(url)>3000:
                raise ValueError('La web configurada necesita un enlace público válido')
            validate_public_source_url(url)
    return value

def public_sources(data):
    """User sites replace defaults; blank sites leave discovery unrestricted."""
    links=[link.strip() for link in context(data)['sourceUrls'].splitlines() if link.strip()]
    sources=[]
    if not links:
        configured=json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
        sources=list(validate_source_configuration(configured))
    if links:
        sources=[]
        for link in links:
            link=link.strip()
            if not link:continue
            validate_public_source_url(link)
            parts=urlsplit(link);segments=parts.path.strip('/').split('/')
            source={'id':'source-'+digest(link)[:12],'company':parts.hostname,'kind':'html','url':link,'enabled':True}
            if parts.hostname in ('boards.greenhouse.io','job-boards.greenhouse.io') and segments[0]:source.update(kind='greenhouse',board=segments[0])
            elif parts.hostname=='jobs.ashbyhq.com' and segments[0]:source.update(kind='ashby',board=segments[0])
            if not any(existing.get('url')==link for existing in sources):sources.append(source)
    return [source for source in validate_source_configuration(sources) if source.get('enabled')]

def handle(data,op):
    import app_workflow as w
    import app_context as c
    app=w.state(data);kind=op['kind'];actor=op.get('actor','Usuario')
    import search_profiles
    if search_profiles.handle(data,op):return True
    import onboarding
    if onboarding.handle(data,op):return True
    if kind=='ui-email-verification-settings':
        current=application_verification(data)
        w.expect({k:current[k] for k in ('enabled','account')},op.get('expected'))
        enabled=op.get('enabled');account=op.get('account');proof=op.get('proof')
        if type(enabled) is not bool:raise ValueError('Indica si permites verificar las solicitudes por correo')
        if not isinstance(account,str) or len(account)>254 or (account and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',account)):
            raise ValueError('Indica la cuenta de correo autorizada')
        if enabled and not account:raise ValueError('Indica la cuenta de correo autorizada')
        if not isinstance(proof,str) or not proof.strip() or len(proof)>2000:
            raise ValueError('Conserva la instrucción expresa de la persona')
        if current['enabled']==enabled and current['account']==account:return True
        app['applicationVerification']={'enabled':enabled,'account':account,'confirmedAt':now(),'proof':proof.strip()}
        w.record(data,'Verificación de solicitudes por correo '+('permitida' if enabled else 'desactivada'),actor=actor,
                 detail='Solo para completar solicitudes expresamente autorizadas. '+proof.strip())
        return True
    if kind=='ui-portal-access':
        portal=op.get('portal');status=op.get('status');browser=op.get('browser');proof=op.get('proof')
        if not isinstance(portal,str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,99}',portal):
            raise ValueError('Identifica el portal con su nombre o dominio, en minúsculas')
        if status not in ('ready','login_required','blocked'):
            raise ValueError('Estado de acceso no válido')
        if not isinstance(browser,str) or not browser.strip() or len(browser)>80:
            raise ValueError('Indica el navegador que comprobaste')
        if not isinstance(proof,str) or not proof.strip() or len(proof)>1000:
            raise ValueError('Explica qué comprobaste en el portal')
        app.setdefault('portalAccess',{})[portal]={'status':status,'browser':browser.strip(),
            'proof':proof.strip(),'checkedAt':w.now()}
        w.record(data,'Acceso a '+portal+' comprobado',actor=actor)
        return True
    if kind=='ui-profile-section':
        if 'expectedRevision' in op:w.expect(data['revision'],op['expectedRevision'])
        if op.get('searchProfileId'):search_profiles.migrate(data)
        personal=set(w.PERSONAL)|set(w.CONTACT_FIELDS)|set(w.DEMOGRAPHIC_FIELDS)|{'workAuthorizations','salaryCurrency'}|{k for k,f in c.definitions(data).items() if k.startswith('custom_') and f['scope']=='global'}
        groups={'about':{'name','noticeDays'}|personal,'search':set(search_profiles.SEARCH_FIELDS)|{'languages','previousApplications','salaryExpectationFixed','salaryCurrency'}|set(c.criteria(data)),
                'sources':{'sourceUrls','checkMail','platforms'}}
        values=op['values'];section=op.get('section')
        if section not in groups or not isinstance(values,dict) or set(values)-groups[section]:raise ValueError('Ese dato no pertenece a esta sección del perfil')
        profile_id=op.get('searchProfileId')
        if section in ('search','sources') and 'searchProfiles' in app and not profile_id:
            if len(search_profiles.profiles(data))!=1:
                raise ValueError('Indica searchProfileId: hay varios perfiles de búsqueda')
            profile_id=search_profiles.get(data)['id']
        old={**context(data,profile_id),**data['profile'],**c.criteria(data,profile_id)}
        w.expect({k:old.get(k) for k in values},op['expected'])
        changed={k:v for k,v in values.items() if old.get(k)!=v}
        undo_start=len(app['undo'])
        # The writer applies this entire operation to a copy: conflicts or invalid
        # values in any group roll back all groups together.
        for fields,operation in ((set(CONTEXT),'ui-search-context'),(set(c.criteria(data)),'ui-preferences'),(personal,'ui-profile')):
            subset={k:v for k,v in values.items() if k in fields}
            if subset:
                child={'kind':operation,'values':subset,'expected':{k:old.get(k) for k in subset},'actor':actor,'scope':'global'}
                if profile_id:child['searchProfileId']=profile_id
                if operation=='ui-search-context':handle(data,child)
                elif operation=='ui-preferences':c.handle(data,child)
                else:w.handle(data,child)
        if 'workAuthorizations' in changed and old.get('workPermitWithoutSponsorship')!=data['profile'].get('workPermitWithoutSponsorship'):
            changed['workPermitWithoutSponsorship']=data['profile'].get('workPermitWithoutSponsorship')
        if changed:
            del app['undo'][undo_start:]
            event=w.record(data,{'about':'Datos personales guardados','search':'Criterios de búsqueda guardados','sources':'Fuentes guardadas'}[section],actor=actor)
            app['undo'].append({'id':event['id'],'kind':'section','section':section,'before':{k:old.get(k) for k in changed},'after':changed,'used':False})
            if profile_id:app['undo'][-1]['searchProfileId']=profile_id
        return True
    if kind=='ui-assistant-settings':
        mode=op.get('mode')
        if mode!='external':raise ValueError('Continúa el trabajo desde el chat de tu agente')
        w.expect(assistant_mode(data),op.get('expected'))
        app['assistantMode']='external';w.record(data,'Asistente actualizado',actor=actor)
        return True
    if kind=='ui-onboarding':
        if app.get('setupComplete',True):raise ValueError('El perfil ya está configurado; edítalo desde Perfil')
        values=op['values'];expected=op.get('expected',False);w.expect(app.get('setupComplete',False),expected)
        onboarding.confirm(data,op)
        validate_initial(values,data=data)
        # Missing fields have an explicit blank decision; inherited defaults are
        # not personal answers. Keep the retired mail flag false for compatibility.
        search={k:values.get(k,'').strip() for k in CONTEXT if k!='checkMail'}
        search['checkMail']=False
        validate_context(search)
        app['searchContext']=search;app['experience']=values.get('experience','').strip()
        app['criteria']={'contract':values.get('contract','').strip(),'location':values.get('location','').strip(),'maxTrips':values.get('maxTrips')}
        import profile_interview
        personal={k for k in profile_interview.fields(data) if k not in CONTEXT and k not in ('experience','contract','location','maxTrips','cv')}
        data['profile'].update({k:values.get(k) for k in personal})
        if 'workPermitWithoutSponsorship' in values:
            data['profile']['workPermitWithoutSponsorship']=values['workPermitWithoutSponsorship']
        if 'workAuthorizations' in values:
            data['profile']['workPermitWithoutSponsorship']=True if values['workAuthorizations'] and any(v in ('España','Unión Europea') for v in values['workAuthorizations']) else None
        app['setupComplete']=True;onboarding.completed(data,op);w.record(data,'Perfil inicial guardado',actor=actor)
        return True
    if kind=='ui-search-context':
        old=context(data,op.get('searchProfileId'));values=op['values'];validate_context(values)
        w.expect({k:old.get(k) for k in values},op['expected'])
        if app.get('setupComplete') and 'searchProfiles' not in app and not op.get('searchProfileId') and 'targetRoles' in values and values['targetRoles']!=old['targetRoles'] and not values['targetRoles'].strip():
            raise ValueError('Indica al menos un puesto antes de guardar la búsqueda')
        if app.get('setupComplete') and 'name' in values and values['name']!=old['name'] and not values['name'].strip():
            raise ValueError('Indica tu nombre antes de guardar el perfil')
        if not any(old[k]!=v for k,v in values.items()):return True
        scoped=bool(op.get('searchProfileId') or 'searchProfiles' in app)
        if scoped:
            search_profiles.edit(data,op,search={k:v for k,v in values.items() if k in search_profiles.SEARCH_FIELDS})
            app['searchContext'].update({k:v for k,v in values.items() if k not in search_profiles.SEARCH_FIELDS})
        else:app['searchContext']={**old,**values}
        w.record(data,'Búsqueda actualizada',actor=actor)
        if not scoped and {k for k,v in values.items() if old[k]!=v} & FIT_CONTEXT:
            if any((w.selection(data,row['ID']) or {}).get('selected') and row['Estado'] not in w.CLOSED and not any(e['type']=='sent' and e['opportunityId']==row['ID'] for e in data['events']) for row in data['sheets']['Oportunidades']):
                c.add_change(data,None,'Revisar el encaje de las ofertas activas con el contexto de búsqueda actualizado.',actor)
        return True
    if kind=='ui-add-opportunity':
        values=op['values']
        if set(values)!={'company','title','url'} or any(not isinstance(v,str) or not v.strip() or len(v)>2000 for v in values.values()):raise ValueError('Completa empresa, puesto y enlace')
        validate_url(values['url']);key=identity(values['url'])
        from stubbs_jobs_core import vacancy_key
        if any(vacancy_key(r)==key for r in data['sheets']['Oportunidades']):raise ValueError('Esta oferta ya está guardada')
        row={k:None for k in OPPORTUNITY_FIELDS}
        row.update({'ID':key,'Clave canónica':key,'Empresa':values['company'].strip(),'Puesto':values['title'].strip(),'URL original':values['url'].strip(),'Fuente':'Añadida por ti','Prioridad':'B','Estado':'Investigar','Vigencia':'Sin comprobar','Siguiente paso':'Comprobar la oferta y su encaje con tu perfil.'})
        data['sheets']['Oportunidades'].append(row);w.draft(data,key)
        request=search_profiles.discovery_request(data,op.get('requestId'))
        search_profiles.associate(data,key,request,op.get('searchProfileId'),new=True)
        w.request(data,key,'investigate',actor=actor)
        w.record(data,'Oferta añadida',key,actor);return True
    return False


def validate_initial(values,data=None):
    import app_workflow as w
    allowed=set(CONTEXT)|set(w.CONTACT_FIELDS)|set(w.DEMOGRAPHIC_FIELDS)|{'experience','currentCity','workPermitWithoutSponsorship','workAuthorizations','salaryExpectationFixed',
                          'contract','location','maxTrips','minimumFixed','noticeDays'}
    import profile_interview
    custom={k:f for k,f in profile_interview.fields(data).items() if k.startswith('custom_')}
    allowed.update(custom)
    if not isinstance(values,dict) or set(values)-allowed:raise ValueError('Revisa los datos del perfil inicial')
    validate_context({k:v for k,v in values.items() if k in CONTEXT})
    if 'experience' in values and (not isinstance(values['experience'],str) or len(values['experience'])>20000):raise ValueError('Revisa la experiencia')
    for key in ('contract','location'):
        if key in values and (not isinstance(values[key],str) or len(values[key])>300):raise ValueError('Revisa contrato y ubicación')
    if values.get('maxTrips') is not None and (type(values['maxTrips']) is not int or not 0<=values['maxTrips']<=31):raise ValueError('Revisa el número de viajes')
    for key in ('minimumFixed','noticeDays','currentCity','workPermitWithoutSponsorship','salaryExpectationFixed',*w.CONTACT_FIELDS,*w.DEMOGRAPHIC_FIELDS):
        if key in values:w.validate_answer(key,values[key])
    if 'workAuthorizations' in values:validate_work_authorizations(values['workAuthorizations'])
    for key,field in custom.items():
        if key in values:w.validate_answer(key,values[key],field)
