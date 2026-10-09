"""Transactional job-search register. See OPERACION.md for the supported commands."""
import argparse
import copy
import json
import posixpath
import subprocess
import sys
import uuid
import zipfile
import view_cache
from runtime import configure_stdio, node_path, doctor
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from stubbs_jobs_core import ROOT, DATA, STORE, WORKBOOK, now, digest, lock, atomic_bytes, atomic_json, identity, vacancy_key, read_store, save_store, parse_json, snapshot_path
from state_support import instant

CONDITIONS={'Remoto España':'Remoto España','Indefinido':'Indefinido','Viajes ≤1/mes':'Viajes','Fijo ≥32 k€':'Fijo ≥32 k€'}
STATES={'Investigar','Preparar','Lista para revisión','Pendiente de Usuario','Pendiente de empresa','Enviada','Entrevista','Oferta','Rechazada','Descartada','Cerrada'}
STATES.update(('Pendiente de ti','Lograda'))
EVENTS={'ready','sent','response','interview','offer','rejected','closed','work','note'}

def excel_day(value=None):
    dt=datetime.fromisoformat(value.replace('Z','+00:00')) if value else datetime.now(timezone.utc)
    return (dt.date()-datetime(1899,12,30).date()).days

def read_xlsx(path):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        ss=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        relationships=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets={item.get('Id'):item.get('Target') for item in relationships
                 if item.get('TargetMode')!='External'}
        sheets={item.get('name'):targets.get(item.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'))
                for item in workbook.findall('s:sheets/s:sheet',ns)}
        result={}
        required={'Oportunidades':{'ID','URL original'},'Entradas':{'ID entrada','URL'},
                  'Evidencias':{'ID oportunidad','Condición'},'Actividad':{'Fecha','Acción'},'Fuentes':{'Fuente'}}
        for name,labels in required.items():
            target=sheets.get(name)
            if not target:raise ValueError('Falta la hoja '+name+' en el Excel; conserva el original')
            filename=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if not filename.startswith('xl/') or filename not in z.namelist():
                raise ValueError('No se pudo leer la hoja '+name+'; conserva el Excel original')
            grid={}
            for row in ET.fromstring(z.read(filename)).findall('.//s:sheetData/s:row',ns):
                values={}
                for c in row:
                    col=''.join(x for x in c.get('r','') if x.isalpha()); v=c.find('s:v',ns); inline=c.find('s:is',ns)
                    value=v.text if v is not None else ''.join(inline.itertext()) if inline is not None else None
                    if c.get('t')=='s' and value is not None: value=ss[int(value)]
                    elif c.get('t')=='b' and value is not None:
                        if value not in ('0','1'):raise ValueError('Valor booleano no válido en '+name+'; conserva el Excel original')
                        value=value=='1'
                    elif c.get('t') not in ('s','str','inlineStr','e','b') and value is not None:
                        try: value=float(value); value=int(value) if value.is_integer() else value
                        except ValueError: pass
                    if value is not None: values[col]=value
                grid[int(row.get('r'))]=values
            headers=[r for r in sorted(grid) if labels.issubset(set(grid[r].values()))]
            if not headers:raise ValueError('No se encuentran las columnas de '+name+'; conserva el Excel original')
            h=headers[0];header=grid[h]
            if any(not isinstance(label,str) for label in header.values()) or len(set(header.values()))!=len(header):
                raise ValueError('Hay columnas no válidas o repetidas en '+name+'; conserva el Excel original')
            if name=='Oportunidades':
                aliases={'Ubicación (dato anterior)':'Remoto España','Contrato (dato anterior)':'Indefinido',
                         'Viajes (dato anterior)':'Viajes ≤1/mes','Sueldo (indicador anterior)':'Fijo ≥32 k€'}
                # Restore only labels emitted by our exporter. If the canonical
                # field also exists, retain the extra column instead of losing it.
                original_labels=set(header.values())
                header={col:aliases.get(label,label) if aliases.get(label) not in original_labels else label
                        for col,label in header.items()}
            result[name]=[{label:grid[r].get(col) for col,label in header.items()} for r in sorted(grid)
                          if r>h and any(value not in (None,'') for value in grid[r].values())]
        return result

def migrate():
    raise ValueError('Esta copia empieza con init; no importa datos históricos de otra persona')

def get_op(data,op_id):
    found=[r for r in data['sheets']['Oportunidades'] if r['ID']==op_id]
    if len(found)!=1: raise ValueError('ID de oportunidad desconocido o duplicado: '+str(op_id))
    return found[0]

@view_cache.cached(lambda data,row:(id(data),row['ID']))
def conditions(data,row):
    if data.get('app',{}).get('offerArchives',{}).get(row['ID']):return 'No','No',False
    from offer_minimums import view as minimums, latest_evidence
    decision=minimums(data,row)
    if any(e['type']=='sent' and e['opportunityId']==row['ID'] for e in data['events']):return 'Ya enviada','Pendiente',False
    if row['Estado'] in ('Cerrada','Descartada','Rechazada','Lograda') or row.get('Vigencia')=='Cerrada':return 'No','No',False
    if not decision['canApply']:return 'No','No',True
    evidence_ok=True
    for condition in CONDITIONS.values():
        latest=latest_evidence(data,row,condition)
        if not(latest.get('Estado')=='Sí' and latest.get('Texto o motivo') and latest.get('Fuente') and latest.get('Comprobada')):evidence_ok=False
    accepted=decision['confirmed'] and evidence_ok and row.get('Vigencia')=='Vacante confirmada'
    # Priority and missing technical experience are advice, never a choice gate.
    return 'Sí, aclarar','Sí' if accepted else 'Pendiente',evidence_ok

def ingest(data,payload):
    if payload.get('schemaVersion')!=2 or not isinstance(payload.get('candidates'),list): raise ValueError('Feed incompatible')
    from personalization import context as search_context, source_allowed
    import search_profiles
    request=search_profiles.discovery_request(data,payload.get('requestId'))
    scoped=search_profiles.discovery_data(data,request)
    if 'searchProfiles' in data.get('app',{}) and not request:
        raise ValueError('La captación necesita el requestId de una búsqueda en curso')
    if 'searchProfiles' in data.get('app',{}) and (payload.get('requestId')!=request['id'] or payload.get('searchKey')!=request.get('searchKey')):
        raise ValueError('El feed necesita requestId y searchKey de esta búsqueda')
    if payload.get('searchKey') and (not request or payload['searchKey']!=request.get('searchKey')):
        raise ValueError('El feed no pertenece a los criterios de esta búsqueda')
    if search_context(scoped)['sourceUrls'].strip():
        boards=payload.get('boards',[])
        if not boards or any(not source_allowed(scoped,b.get('sourceUrl','')) for b in boards):raise ValueError('El feed incluye fuentes fuera de las webs exclusivas del perfil')
        ids={b['sourceId'] for b in boards}
        if any(c.get('sourceId') not in ids for c in payload['candidates']):raise ValueError('La oferta necesita una fuente de búsqueda permitida y comprobada')
    entries=data['sheets']['Entradas']; by_key={vacancy_key(r):r for r in [*data['sheets']['Oportunidades'],*entries]}; added=0
    for item in payload['candidates']:
        key=identity(item['url']); existing=by_key.get(key)
        observation_key=(existing.get('Clave canónica') if existing else None) or key
        obs=data['observations'].get(observation_key,{})
        data['observations'][observation_key]={**item,'firstSeenAt':obs.get('firstSeenAt',payload['checkedAtUtc']),'lastSeenAt':payload['checkedAtUtc'],'contentHash':digest(item)}
        if existing:
            search_profiles.associate(data,existing.get('ID') or existing.get('ID entrada'),request,new=False)
            continue
        row={'ID entrada':key,'Fuente':item['sourceId'],'Empresa':item['company'],'Puesto':item['title'],'URL':item['url'],
             'Primera vista':excel_day(payload['checkedAtUtc']),'Publicada':excel_day(item['originalPublishedAt']) if item.get('originalPublishedAt') else None,
             'Estado':'Nueva','ID oportunidad':None,'Motivo / comprobación':('Título relacionado; comprobar las tareas antes de preseleccionar.' if item.get('roleMatch')=='related' else 'Descubrimiento automático; todas las condiciones pendientes.'),
             'Clave canónica':key,'Última publicación':excel_day(item['lastPublishedAt']) if item.get('lastPublishedAt') else None}
        entries.append(row); by_key[key]=row; added+=1
        search_profiles.associate(data,key,request,new=True)
    for health in payload['boards']: data['sourceHealth'][health['sourceId']]=health
    if request:request.setdefault('scanChecks',[]).extend(copy.deepcopy(payload['boards']))
    return added

def apply_batch(data,batch):
    import app_workflow as workflow
    if not isinstance(batch,dict) or not isinstance(batch.get('id'),str) or not batch['id'].strip() or len(batch['id'])>200:
        raise ValueError('El guardado necesita un identificador de texto válido')
    if not isinstance(batch.get('operations'),list) or not batch['operations'] or any(not isinstance(op,dict) or not isinstance(op.get('kind'),str) for op in batch['operations']):
        raise ValueError('El guardado necesita una lista de operaciones válidas')
    try:json.dumps(batch,allow_nan=False)
    except (ValueError,TypeError) as exc:raise ValueError('Los datos contienen un valor no válido') from exc
    for op in batch['operations']:
        if 'proof' in op and (not isinstance(op['proof'],str) or not op['proof'].strip()):
            raise ValueError('La comprobación necesita una prueba de texto no vacía')
    candidate=copy.deepcopy(data)
    with workflow.package_transaction(data):
        changed=_apply_batch(candidate,batch)
    if changed:
        data.clear(); data.update(candidate)
    return changed

def validate_offer_facts(values, proof):
    # Views and the interface read these as text; another type would block every screen.
    for field in ('Empresa','Puesto'):
        if field in values and (not isinstance(values[field],str) or not values[field].strip() or len(values[field])>500):
            raise ValueError('Empresa y puesto necesitan un texto válido')
    if 'URL original' in values:
        if not isinstance(values['URL original'],str) or len(values['URL original'])>2000:
            raise ValueError('La oferta necesita un enlace http o https válido')
        identity(values['URL original'])
    if 'Puesto traducido' in values:
        from personalization import validate_display_title
        validate_display_title(values['Puesto traducido'],proof)
    for field in ('País','Ubicación','Modalidad','Contrato'):
        if field in values and (not proof or values[field] is not None and
                                (not isinstance(values[field],str) or not values[field].strip() or len(values[field])>300)):
            raise ValueError('País, ubicación, modalidad y contrato necesitan un dato válido y su prueba; no se deducen del perfil')


def _apply_batch(data,batch):
    if not batch.get('id') or not isinstance(batch.get('operations'),list): raise ValueError('Lote sin id u operaciones')
    if batch['id'] in data['appliedBatches']:
        previous=next((b for b in data['changes'] if b['id']==batch['id']),None)
        if previous is None or previous['operations']!=batch['operations']:
            from app_workflow import Conflict
            raise Conflict('Este guardado ya existe con otro contenido. Conserva el borrador y vuelve a comprobar los datos actuales.')
        return False
    import app_workflow as workflow
    workflow.validate_execution_scope(data)
    # Handlers may derive fields or retain nested objects in the candidate. Keep
    # the submitted batch exact for retries, history and failed transactions.
    for op in copy.deepcopy(batch['operations']):
        before_material=workflow.material_versions(data)
        kind=op['kind']
        if not kind.startswith('ui-') and kind!='profile':
            from onboarding import require_ready
            require_ready(data)
        if kind.startswith('ui-'):
            import app_workflow
            app_workflow.handle(data,op)
        elif kind=='profile':
            unknown=set(op['values'])-set(data['profile'])
            if unknown or not op.get('proof'): raise ValueError('Perfil: campos no admitidos o sin confirmación')
            if any(k in op['values'] for k in ('minimumFixed','noticeDays')): raise ValueError('Cambiar límites requiere una migración explícita')
            for key,value in op['values'].items():workflow.validate_answer(key,value)
            data['profile'].update(op['values'])
        elif kind=='opportunity':
            row=get_op(data,op['id']); values=op['values']
            if isinstance(row.get('Requisitos de la oferta'),str) and 'Observaciones' in values:
                raise ValueError('Las observaciones originales se conservan. Actualiza requisitos y notas con ui-offer-context')
            validate_offer_facts(values,op.get('proof'))
            if 'URL original' in values and any(other is not row and vacancy_key(other)==identity(values['URL original']) for other in data['sheets']['Oportunidades']):
                raise ValueError('Ese enlace ya pertenece a otra oferta guardada')
            forbidden={'ID','Clave canónica','Apta solicitar','Apta aceptar','Fecha candidatura','CV usado','Fijo mín. confirmado','Fijo máx. confirmado','Moneda fijo confirmado','Viajes mín. al mes','Evidencias completas'}
            if forbidden.intersection(values) or any(k in CONDITIONS for k in values): raise ValueError('Usar evidencias o eventos para este cambio')
            if values.get('Estado') in ('Enviada','Entrevista','Oferta','Lograda','Rechazada','Cerrada'): raise ValueError('El avance o cierre requiere un evento fechado y su ámbito comprobado')
            row.update(values)
        elif kind=='promote':
            entry=next(r for r in data['sheets']['Entradas'] if r['ID entrada']==op['entryId'])
            if entry.get('ID oportunidad'): raise ValueError('Entrada ya promovida')
            if any(vacancy_key(r)==vacancy_key(entry) for r in data['sheets']['Oportunidades']): raise ValueError('Oportunidad ya existente')
            values=op['values']
            validate_offer_facts(values,op.get('proof'))
            if values.get('Prioridad') not in ('A','B','C') or not values.get('Siguiente paso') or not op.get('reason'): raise ValueError('Promoción sin decisión defendible')
            from personalization import OPPORTUNITY_FIELDS
            row={k:None for k in (data['sheets']['Oportunidades'][0] if data['sheets']['Oportunidades'] else OPPORTUNITY_FIELDS)}
            row.update({'ID':entry['ID entrada'],'Clave canónica':entry['Clave canónica'],'Empresa':entry['Empresa'],'Puesto':entry['Puesto'],'URL original':entry['URL'],'Fuente':entry['Fuente'],'Estado':'Investigar','Vigencia':'Sin comprobar',**{k:'Pendiente' for k in CONDITIONS}})
            if any(k in CONDITIONS or k in ('ID','Clave canónica','Estado','Fecha candidatura','CV usado','Fijo mín. confirmado','Fijo máx. confirmado','Moneda fijo confirmado','Viajes mín. al mes','Apta solicitar','Apta aceptar','Evidencias completas') for k in values): raise ValueError('Promoción no puede confirmar condiciones o envíos')
            row.update(values); data['sheets']['Oportunidades'].append(row); entry['ID oportunidad']=row['ID']; entry['Estado']='Promovida'
            import search_profiles
            origins=data.get('app',{}).get('offerSearches',{}).get(row['ID'],[])
            original=next((r for r in data.get('app',{}).get('requests',[]) if origins and r['id']==origins[0]['requestId']),None)
            request=original or search_profiles.discovery_request(data,op.get('requestId'))
            search_profiles.associate(data,row['ID'],request,op.get('searchProfileId'),new=True)
        elif kind=='entry':
            row=next(r for r in data['sheets']['Entradas'] if r['ID entrada']==op['id'])
            if op['state'] not in ('Nueva','Descartada','Cerrada','Contradicción','Duplicada'): raise ValueError('Estado de entrada inválido')
            if not op.get('reason'): raise ValueError('Falta motivo')
            row['Estado']=op['state']; row['Motivo / comprobación']=op['reason']
        elif kind=='evidence':
            row=get_op(data,op['id']); key=op['condition']; state=op['state']
            if key not in CONDITIONS or state not in ('Sí','No','Pendiente','Contradicción'): raise ValueError('Condición inválida')
            if not op.get('proof') or not op.get('url') or not op.get('at'): raise ValueError('Evidencia incompleta')
            observed=instant(op.get('at'))
            if not observed or observed>datetime.now(timezone.utc)+timedelta(minutes=5):
                raise ValueError('La evidencia necesita fecha real con zona horaria, sin fechas futuras')
            from personalization import validate_url
            validate_url(op['url'])
            from offer_minimums import latest_evidence
            previous_row=copy.deepcopy(row)
            data['sheets']['Evidencias'].append({'ID oportunidad':row['ID'],'Condición':CONDITIONS[key],'Estado':state,'Texto o motivo':op['proof'],'Fuente':op['url'],'Comprobada':excel_day(op['at']),'observedAt':op['at'],
                                               'numericValues':{k:op[k] for k in ('fixed','fixedMax','currency','trips') if k in op}})
            row[key]=state
            # This observation replaces the current figures, including when none
            # are confirmed. Earlier observations and batch operations remain intact.
            if key=='Fijo ≥32 k€':
                for field in ('Fijo mín. confirmado','Fijo máx. confirmado','Moneda fijo confirmado'):row[field]=None
            if key=='Viajes ≤1/mes':row['Viajes mín. al mes']=None
            if 'fixed' in op and key!='Fijo ≥32 k€':raise ValueError('El sueldo pertenece a la condición salarial')
            if 'fixedMax' in op and ('fixed' not in op or key!='Fijo ≥32 k€'):raise ValueError('La banda fija necesita un mínimo y máximo salariales confirmados')
            if 'trips' in op and key!='Viajes ≤1/mes':raise ValueError('La frecuencia pertenece a la condición de viajes')
            if key=='Fijo ≥32 k€' and 'fixed' in op:
                if type(op['fixed']) not in (int,float) or not 0<=op['fixed']<=1000000000:raise ValueError('Sueldo confirmado no válido')
                if data.get('app',{}).get('personalized'):
                    from personalization import context
                    import app_context
                    if op.get('currency')!=app_context.scoped_search(data,row['ID'])['currency']:raise ValueError('La moneda confirmada debe coincidir con la del perfil; no se convierte por suposición')
                    row['Moneda fijo confirmado']=op['currency']
                row['Fijo mín. confirmado']=op['fixed']
                row['Fijo máx. confirmado']=op.get('fixedMax')
                if 'fixedMax' in op and (type(op['fixedMax']) not in (int,float) or not op['fixed']<=op['fixedMax']<=1000000000):raise ValueError('La banda fija confirmada no es válida')
            if key=='Fijo ≥32 k€':
                import app_context
                from personalization import context as search_context
                data['sheets']['Evidencias'][-1].update(minimumFixed=app_context.scoped_criteria(data,op['id'])['minimumFixed'],currency=app_context.scoped_search(data,op['id'])['currency'] or 'EUR')
            if key=='Viajes ≤1/mes' and 'trips' in op:
                if type(op['trips']) not in (int,float) or not 0<=op['trips']<=31:raise ValueError('La frecuencia de viajes no es válida')
                row['Viajes mín. al mes']=op['trips']
            if latest_evidence(data,row,CONDITIONS[key]) is not data['sheets']['Evidencias'][-1]:
                # Backfilled checks remain in history, without replacing a newer
                # checked condition or its figures in the current projection.
                row.clear();row.update(previous_row)
        elif kind=='event':
            event=copy.deepcopy(op['event']); row=get_op(data,event['opportunityId'])
            if event['type'] not in EVENTS or not all(isinstance(event.get(key),str) and event[key].strip() for key in ('id','at','proof')):raise ValueError('Evento incompleto')
            if datetime.fromisoformat(event['at'].replace('Z','+00:00')).tzinfo is None: raise ValueError('El evento requiere zona horaria')
            previous=next((e for e in data['events'] if e['id']==event['id']),None)
            if previous:
                if any(previous.get(k)!=v for k,v in event.items()): raise ValueError('ID de evento reutilizado con contenido distinto')
                continue
            from application_lifecycle import validate_event
            validate_event(data,row,event)
            event.update(source=row['Fuente'],family=row.get('Familia'),cohort=event['at'][:7])
            sent=[e for e in data['events'] if e['type']=='sent' and e['opportunityId']==row['ID']]
            if event['type']=='sent':
                if sent: raise ValueError('Candidatura ya enviada')
                if not event.get('packageId'): raise ValueError('El envío nuevo requiere un paquete aprobado; usa historical para conciliar solicitudes antiguas')
                if event.get('historyChecked') is not True or not all(isinstance(event.get(key),str) and event[key].strip() for key in ('authorization','confirmation')):raise ValueError('Falta autorización, conciliación de historial o confirmación de envío')
                prior=[h for h in data['historicalApplications'] if vacancy_key(h)==vacancy_key(row)]
                if prior and not event.get('reapplicationAuthorization'): raise ValueError('Coincide con una candidatura anterior; necesita decisión expresa de volver a solicitar')
                cv=(ROOT/event['cv']).resolve()
                if not cv.is_relative_to(ROOT.resolve()) or not cv.is_file(): raise ValueError('CV inexistente o fuera del proyecto')
                event['cvHash']=digest(cv.read_bytes()); row['CV usado']=event['cv']; row['Fecha candidatura']=excel_day(event['at'])
                import app_workflow as workflow
                workflow.seed(data)
                package=next(p for p in workflow.state(data)['packages'] if p['id']==event['packageId'] and p['opportunityId']==row['ID'])
                workflow.conserved_package(package)
                if package['payload']['cvHash']!=event['cvHash']:raise ValueError('El CV enviado no coincide con el paquete autorizado')
                running=next((r for r in workflow.state(data)['requests'] if r['type']=='send' and r.get('packageId')==package['id'] and r['status']=='running'),None)
                if not running:
                    raise ValueError('No hay un encargo de envío iniciado para este paquete')
                workflow.require_owner(running)
                from request_workflow import validate_sent_time
                event['authorizationAt']=validate_sent_time(running,package,event['at'])
                event['packageId']=package['id']
                event['archivedCV']='data/packages/'+package['id']+'/cv.pdf'
            elif event['type'] in ('response','interview','offer','rejected'):
                if not sent: raise ValueError('No hay envío previo confirmado; conciliar primero')
                event['cv']=sent[0].get('cv'); event['cvHash']=sent[0].get('cvHash')
            if event['type']=='work' and (type(event.get('minutes')) not in (int,float) or event['minutes']<0 or event.get('actor') not in ('Usuario','Usuario','Agente')): raise ValueError('Tiempo sin cantidad válida o responsable')
            if event['type']=='ready':
                import app_workflow as workflow
                workflow.seed(data)
                pending=workflow.readiness(data,row['ID'])
                if pending:raise ValueError('Paquete incompleto: '+', '.join(pending))
                row['Paquete listo desde']=event['at']
            old=row['Estado']
            data['events'].append(event)
            from application_lifecycle import project_event
            project_event(data,row,event)
            if event['type'] not in ('work','note'):
                import app_workflow as workflow
                history_item=workflow.record(data,{'ready':'Paquete preparado','sent':'Envío confirmado','response':'Respuesta de empresa','interview':'Entrevista registrada','offer':'Oferta recibida','rejected':'Candidatura rechazada','closed':'Proceso cerrado'}[event['type']],row['ID'],detail=event['proof'],artifact=event.get('packageId'))
                history_item['eventId']=event['id']
                history_item['at']=event['at']
            data['sheets']['Actividad'].append({'Fecha':excel_day(event['at']),'ID oportunidad':row['ID'],'Acción':event['type'],'Estado anterior':old,'Estado nuevo':row['Estado'],'CV / material':event.get('cv'),'Resultado / prueba':event['proof'],'Próximo paso':event.get('next')})
        elif kind=='block':
            block=op['block']
            if not isinstance(block,dict) or any(not isinstance(block.get(k),str) or not block[k].strip() or len(block[k])>5000 for k in ('id','owner','question')):raise ValueError('Bloqueo incompleto')
            if block.get('due') is not None and not isinstance(block['due'],str):raise ValueError('La fecha límite del bloqueo debe ser texto ISO')
            if block.get('opportunityId'): get_op(data,block['opportunityId'])
            if block.get('status') not in ('open','resolved'): raise ValueError('Bloqueo incompleto')
            data['blocks']=[b for b in data['blocks'] if b['id']!=block['id']]+[block]
        elif kind=='source':
            if not op.get('proof') or not op.get('id'): raise ValueError('Fuente sin identificador o prueba')
            allowed={'Tipo','Cuenta','Alertas','Última revisión','Último éxito','Error actual'}
            if set(op['values'])-allowed: raise ValueError('Campo de fuente no admitido')
            row=next((r for r in data['sheets']['Fuentes'] if r['Fuente']==op['id']),None)
            if row is None:
                row={'Fuente':op['id']}; data['sheets']['Fuentes'].append(row)
            row.update(op['values'])
        elif kind=='historical':
            record=op['record']
            if not isinstance(record,dict) or any(not isinstance(record.get(k),str) or not record[k].strip() for k in ('id','company','url','state','proof')) or record.get('title') is not None and not isinstance(record['title'],str): raise ValueError('Historial incompleto')
            record['canonicalKey']=identity(record['url'])
            data['historicalApplications']=[h for h in data['historicalApplications'] if h['id']!=record['id']]+[record]
        elif kind=='historical-complete':
            if not op.get('proof'): raise ValueError('Conciliación sin prueba')
            data['historicalReconciliation'].update(status='complete',actualCount=len(data['historicalApplications']),proof=op['proof'],at=now())
        elif kind in ('cycle-start','stage','cycle-finish'):
            raise ValueError('Los ciclos completo/breve se han retirado; registra el resultado en cada tarea.')
        else: raise ValueError('Operación desconocida: '+kind)
        workflow.retire_mail(data)
        workflow.protect_material(data,before_material)
    import application_lifecycle
    application_lifecycle.reconcile(data,workflow)
    from offer_minimums import reconcile as reconcile_minimums
    reconcile_minimums(data,workflow)
    data['appliedBatches'].append(batch['id'])
    data['changes'].append({'id':batch['id'],'at':now(),'operations':copy.deepcopy(batch['operations'])})
    validate(data)
    return True

def validate(data):
    if 'searchProfiles' in data.get('app',{}):
        from search_profiles import validate_model
        validate_model(data)
    rows=data['sheets']['Oportunidades']; ids=[r['ID'] for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError('IDs de oportunidades duplicados')
    keys=[r['Clave canónica'] for r in rows]
    if len(keys)!=len(set(keys)): raise ValueError('Vacantes canónicas duplicadas')
    for r in rows:
        if r['Estado'] not in STATES or r['Prioridad'] not in ('A','B','C'): raise ValueError('Estado o prioridad inválidos')
    for e in data['sheets']['Evidencias']:
        if e['ID oportunidad'] not in ids: raise ValueError('Evidencia huérfana')
    return True


def clear_opportunities(data, expected_revision):
    """Start a new search without discarding the person's confirmed context.

    The CLI holds the writer lock and save_store archives the exact previous
    registry before publishing this revision. This operation is deliberately
    unavailable through the application's generic action endpoint.
    """
    import agent_runner
    import app_context
    import app_workflow

    if type(expected_revision) is not int or expected_revision != data['revision']:
        raise ValueError('El registro cambió; comprueba su versión antes de vaciar las ofertas')
    app = app_workflow.state(data)
    if agent_runner.view()['status'] in agent_runner.ACTIVE or any(
        request['status'] == 'running' for request in app['requests']
    ) or any(cycle['status'] == 'running' and (instant(cycle.get('startedAt')) is None or
             datetime.now(timezone.utc)-instant(cycle.get('startedAt')) < timedelta(hours=2))
             for cycle in data['cycles']):
        raise ValueError('Hay trabajo en curso; termina o interrumpe esa ejecución antes de vaciar las ofertas')

    if app_workflow.unresolved_sends(data):
        raise ValueError('Hay un envío iniciado sin resolver; comprueba el portal y concilia su resultado antes de vaciar las ofertas')

    counts = {'ofertas': len(data['sheets']['Oportunidades']),
              'anuncios': len(data['sheets']['Entradas']),
              'anteriores': len(data['historicalApplications']),
              'encargos': len(app['requests'])}
    # Older personal registries read experience from perfil.md. Make it
    # explicit before removing the work history so the profile is portable.
    app['experience'] = app_context.experience(data)
    for name in ('Oportunidades', 'Entradas', 'Evidencias', 'Actividad', 'Fuentes'):
        data['sheets'][name] = []
    for key, empty in (('events', []), ('observations', {}), ('sourceHealth', {}),
                       ('cycles', []), ('historicalApplications', []), ('blocks', []),
                       ('appliedBatches', []), ('changes', [])):
        data[key] = empty
    data['historicalReconciliation'] = {
        'status': 'pending', 'expectedCount': None,
        'source': 'Antecedentes retirados al iniciar una búsqueda nueva'}
    for key, empty in (('drafts', {}), ('packages', []), ('requests', []),
                       ('history', []), ('snoozes', {}), ('undo', []),
                       ('selections', {}), ('fitReviews', {}), ('contactDrafts', []), ('offerArchives', {}),
                       ('offerRounds',{}),('currentCriteria',[]),('offerCriteria',{}),('offerSearches',{}),
                       ('availabilityChecks',{}),('followupChecks',{}),('followupPlans',{}),
                       ('offerAssessments',{}),('sourceReviews',[]),('executionScopes',{})):
        app[key] = empty
    app['seenAt'] = None
    app['legacyImported'] = True
    app['legacyOfferImportDisabled'] = True
    if any(counts.values()) or 'lastOpportunityReset' not in data:
        data['lastOpportunityReset'] = {'at': now(), 'counts': counts,
                                        'backupSha256': data.get('_baseHash')}
    validate(data)
    return counts

def view(data):
    result=copy.deepcopy(data)
    if not data['sheets']['Oportunidades']:
        from personalization import OPPORTUNITY_FIELDS
        result['opportunityFields']=OPPORTUNITY_FIELDS
    for item in data.get('app',{}).get('history',[]):
        if item['actor']=='Registro anterior' or item.get('eventId'):continue
        result['sheets']['Actividad'].append({'Fecha':excel_day(item['at']),'ID oportunidad':item.get('opportunityId'),'Acción':item['title'],'Estado anterior':None,'Estado nuevo':None,'CV / material':('data/packages/'+item['packageId']) if item.get('packageId') else None,'Resultado / prueba':item['actor']+': '+item['detail'],'Próximo paso':None})
    result['sheets']['Actividad'].sort(key=lambda item:item.get('Fecha') or 0)
    for row in result['sheets']['Oportunidades']:
        from offer_minimums import current_facts
        row.update(current_facts(data,row))
        row['Apta solicitar'],row['Apta aceptar'],row['Evidencias completas']=conditions(data,row)
        if data.get('app',{}).get('offerArchives',{}).get(row['ID']):
            archive=data['app']['offerArchives'][row['ID']]
            rejected=archive.get('outcome')=='rejected' or any(e['type']=='sent' and e['opportunityId']==row['ID'] for e in data['events'])
            from application_lifecycle import archive_outcome, achievement
            outcome=archive_outcome(data,row)
            row['Estado']='Lograda' if outcome=='achieved' else 'Rechazada' if outcome=='rejected' else 'Cerrada' if rejected or outcome=='closed' else 'Descartada'
            row['Siguiente paso']=achievement(data,row)['label'] if outcome=='achieved' else archive.get('reason') or ('Seguimiento cerrado por la persona; historial conservado.' if rejected else 'Oferta descartada; historial conservado.')
        else:
            from application_lifecycle import achievement
            if achievement(data,row):
                row['Estado']='Lograda'
                row['Siguiente paso']=achievement(data,row)['label']
        row['Bloqueos abiertos']='; '.join(b['owner']+': '+b['question'] for b in data['blocks'] if b.get('opportunityId')==row['ID'] and b['status']=='open')
        row['Oferta elegida']='Sí' if data.get('app',{}).get('selections',{}).get(row['ID'],{}).get('selected') else 'No'
        if 'searchProfiles' in data.get('app',{}):
            import search_profiles
            info=search_profiles.offer_info(data,row['ID'])
            names={p['id']:p['name'] for p in search_profiles.profiles(data)}
            row['Perfil de búsqueda']=info['searchProfileName'] or 'Búsqueda anterior sin perfil asignado'
            row['ID perfil de búsqueda']=info['searchProfileId']
            row['Búsquedas en que apareció']='; '.join(names.get(key,key) for key in info['searchProfileIds'])
    return result

def metrics(data):
    """Basic outcomes per process; no automatic comparisons of CV variants."""
    sent={e['opportunityId'] for e in data['events'] if e['type']=='sent'}
    response={e['opportunityId'] for e in data['events'] if e['type'] in ('response','interview','offer')}
    interview={e['opportunityId'] for e in data['events'] if e['type'] in ('interview','offer')}
    offer={e['opportunityId'] for e in data['events'] if e['type']=='offer'}
    return {'sent':len(sent),'responses':len(sent & response),'interviews':len(sent & interview),'offers':len(sent & offer)}

def preparation_metrics(data):
    result=[]
    for row in data['sheets']['Oportunidades']:
        discovered=data['observations'].get(row['Clave canónica'],{}).get('firstSeenAt')
        ready=row.get('Paquete listo desde')
        hours=None
        # A report must not fail on an incomplete legacy date; it simply has no duration.
        start,end=instant(discovered),instant(ready)
        if start and end:
            elapsed=(end-start).total_seconds()/3600
            if elapsed>=0: hours=round(elapsed,2)
        result.append({'opportunityId':row['ID'],'discoveredAt':discovered,'readyAt':ready,'hoursToReady':hours})
    return result

def report(data):
    import app_workflow as workflow
    superseded=workflow.superseded_sends(data)
    unresolved={r['id'] for r in workflow.unresolved_sends(data)}
    return {'revision':data['revision'],'opportunities':len(data['sheets']['Oportunidades']),'entries':len(data['sheets']['Entradas']),
            'sent':sum(e['type']=='sent' for e in data['events']),
            'historicalReconciliation':data['historicalReconciliation'],'sourceHealth':data['sourceHealth'],
            'blocks':[b for b in data['blocks'] if b['status']=='open'],'metrics':metrics(data),'preparationMetrics':preparation_metrics(data),
            'pendingRequests':[r for r in data.get('app',{}).get('requests',[]) if r['id'] not in superseded and (r['status'] not in ('done','cancelled') or r['id'] in unresolved)]}

def packages(data):
    import app_workflow as workflow
    workflow.seed(data)
    folder=ROOT/'outputs/candidaturas'; folder.mkdir(exist_ok=True)
    for row in data['sheets']['Oportunidades']:
        if row['Prioridad']!='A': continue
        cv=row.get('CV preparado'); cv_hash=digest((ROOT/cv).read_bytes()) if cv else None
        personal=workflow.answers(data,row['ID']); draft=workflow.draft(data,row['ID']); gates=conditions(data,row)
        sent=any(e['type']=='sent' and e['opportunityId']==row['ID'] for e in data['events'])
        text=f"# {row['Empresa']} · {row['Puesto']}\n\nEstado: {row['Estado']}. {'Envío confirmado en el registro.' if sent else 'Envío no confirmado.'}\n\nOferta: {row['URL original']}\n\nCV preparado: {cv}\n\nHuella del archivo: {cv_hash}\n\n"
        text+=f"## Borrador actual\n\nDestino: {draft['recipient']}\n\n{draft['message'] or 'Texto pendiente de preparar.'}\n\n"
        text+='## Respuestas reutilizables\n\n'
        import app_context as context
        destinations=data['profile'].get('workAuthorizations')
        fields=[('currentCity','Ciudad actual'),('salaryExpectationFixed','Expectativa fija anual')]
        if destinations is None:
            fields.insert(1,('workPermitWithoutSponsorship',context.definitions(data,row['ID'])['workPermitWithoutSponsorship']['label']))
        for key,label in fields:
            value=personal.get(key);text+=f'- {label}: {value if value is not None else "PENDIENTE: no completar por suposición"}.\n'
        if destinations is not None:
            text+='- Países o zonas con permiso de trabajo sin patrocinio: '+(', '.join(destinations) or 'PENDIENTE: no completar por suposición')+'.\n'
        notice=context.criteria(data)['noticeDays']
        if type(notice) is int:notice=f'{notice} (unidad pendiente de confirmar)'
        text+=f'- Preaviso: {notice if notice is not None else "PENDIENTE: no completar por suposición"}.\n\n'
        text+='## Experiencia confirmada vigente\n\n'+context.experience(data)+'\n\n'
        text+='## Decisión antes del envío\n\n'
        text+=f"Aptitud de condiciones: {gates[0]}. Aceptación: {gates[1]}.\n\n"
        text+='Reabrir la oferta y comprobar selección activa, destinatario, formulario final y posibles duplicados por cliente. Consultar historial previo, incluyendo candidaturas cerradas. El salario no publicado no impide solicitar una A. Registrar autorización concreta y confirmación del portal; nunca convertir un borrador en envío confirmado.\n\n'
        text+='Este archivo es una vista del borrador actual. Las versiones revisadas y autorizadas se consultan en la aplicación y se conservan en data/packages.\n'
        filename=digest(row['ID'])[:24] if any(c in row['ID'] for c in '<>:"/\\|?*') else row['ID']
        atomic_bytes(folder/(filename+'.md'),text.encode('utf-8'))

def recover_export(data):
    receipt=DATA/'export-receipt.json'
    if receipt.exists():
        pending_commit=json.loads(receipt.read_text(encoding='utf-8'))
        if pending_commit['revision']==data['revision'] and WORKBOOK.exists() and digest(WORKBOOK.read_bytes())==pending_commit['newHash']:
            data['workbookHash']=pending_commit['newHash']
            data['workbookRevision']=data['revision']+1
            if pending_commit.get('contentHash'):
                data['workbookContentHash']=pending_commit['contentHash']
            save_store(data)

def export_fingerprint(data):
    projected=view(data)
    return digest({k:projected[k] for k in ('sheets','events','historicalApplications','historicalReconciliation','sourceHealth','blocks')})

def export(data=None):
    from runtime import excel_available
    # Rendering happens outside the writer lock. User answers remain writable.
    with lock():
        data=read_store();recover_export(data)
        if data.get('app',{}).get('personalized') and not excel_available(ROOT):
            atomic_bytes(ROOT/'outputs/candidaturas.csv',table_csv(data));return data
        fingerprint=export_fingerprint(data)
    receipt=DATA/'export-receipt.json'
    current=WORKBOOK.read_bytes() if WORKBOOK.exists() else None
    if current is not None and digest(current)!=data['workbookHash']: raise ValueError('El Excel cambió externamente: conciliar antes de sobrescribir')
    runtime=node_path()
    folder=DATA/'exports'/str(uuid.uuid4());folder.mkdir(parents=True,exist_ok=True)
    projection=folder/'projection.json'; pending=folder/'busqueda-empleo.pending.xlsx'
    atomic_json(projection,view(data))
    subprocess.run([str(runtime),str(ROOT/'tools/export-tracker.mjs'),str(projection),str(pending)],
                   check=True,cwd=ROOT,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    with lock():
        fresh=read_store();recover_export(fresh)
        if export_fingerprint(fresh)!=fingerprint:raise ValueError('Hay cambios nuevos; se actualizará Excel con la siguiente revisión')
        latest=WORKBOOK.read_bytes() if WORKBOOK.exists() else None
        if latest!=current:raise ValueError('El Excel cambió durante la exportación; se conserva el archivo externo')
        if current is not None: atomic_bytes(DATA/'workbook-backups'/f'{digest(current)}.xlsx',current)
        output=pending.read_bytes()
        atomic_json(receipt,{'revision':fresh['revision'],'newHash':digest(output),'oldHash':fresh['workbookHash'],'contentHash':fingerprint})
        atomic_bytes(WORKBOOK,output)
        fresh['workbookHash']=digest(output); fresh['workbookRevision']=fresh['revision']+1;fresh['workbookContentHash']=fingerprint
        save_store(fresh)
        atomic_json(ROOT/'outputs/status.json',report(fresh))
    return fresh

def main():
    configure_stdio()
    ap=argparse.ArgumentParser()
    ap.add_argument('command',choices=['init','plan','handoff','migrate','upgrade-app','ingest','apply','import-cv','export','status','app-status','agent-status','refresh','packages','doctor','maintenance','backup','check-backup','restore','clear-opportunities'])
    ap.add_argument('--file'); ap.add_argument('--name'); ap.add_argument('--destination')
    ap.add_argument('--execution-id'); ap.add_argument('--expected-revision',type=int)
    ap.add_argument('--request-ids',help='IDs originales de la tanda, separados por comas')
    ap.add_argument('--case',help='Detalle de una oferta')
    ap.add_argument('--request',help='Detalle de un encargo')
    ap.add_argument('--profile',action='store_true',help='Perfil y antecedentes completos')
    ap.add_argument('--search-profile',help='Perfil de agent-status o de una búsqueda autorizada con plan; no cambia el predeterminado')
    ap.add_argument('--history',action='store_true');ap.add_argument('--limit',type=int,default=20)
    ap.add_argument('--since',help='Versión de la consulta anterior')
    args=ap.parse_args()
    if args.search_profile and args.command not in ('agent-status','plan'):
        raise ValueError('--search-profile corresponde a agent-status o plan; el captador utiliza --request')
    if args.execution_id:
        import os
        os.environ['STUBBS_JOBS_EXECUTION_ID']=args.execution_id
    if args.command=='agent-status':
        from agent_context import view as agent_view
        print(json.dumps(agent_view(read_store(),case=args.case,request_id=args.request,
                                    history=args.history,limit=args.limit,since=args.since,profile_detail=args.profile,search_profile_id=args.search_profile),ensure_ascii=False))
        return
    if args.command=='doctor':
        result=doctor(ROOT);print(json.dumps(result,ensure_ascii=False));return
    if args.command=='maintenance':
        from maintenance import plan
        print(json.dumps(plan(ROOT),ensure_ascii=False));return
    if args.command in ('backup','check-backup','restore'):
        import backup
        if args.command=='backup':result=backup.create(ROOT)
        else:
            if not args.file:raise ValueError('Indica la copia ZIP con --file')
            if args.command=='check-backup':
                result={'ok':True,**backup.verify(Path(args.file).read_bytes())['manifest']}
                result.pop('files',None)
            else:
                if not args.destination:raise ValueError('Indica una carpeta nueva con --destination')
                result=backup.restore(ROOT,args.file,args.destination)
        print(json.dumps(result,ensure_ascii=False));return
    if args.command=='refresh':
        before_run=json.loads((ROOT/'outputs/feeds/latest.json').read_text(encoding='utf-8')).get('runId') if (ROOT/'outputs/feeds/latest.json').exists() else None
        completed=subprocess.run([sys.executable,str(ROOT/'tools/scan_boards.py'),*(['--request',args.request] if args.request else [])])
        if completed.returncode not in (0,1): raise ValueError('Captador abortado; no importar resultados antiguos')
        if json.loads((ROOT/'outputs/feeds/latest.json').read_text(encoding='utf-8')).get('runId')==before_run: raise ValueError('El captador no produjo una ejecución nueva')
    with lock():
        if args.command=='migrate': data=migrate()
        elif args.command=='init':data=initialize()
        else:
            data=read_store()
            recover_export(data)
        if args.command in ('ingest','refresh'):
            from onboarding import require_ready
            require_ready(data)
            p=json.loads(Path(args.file or ROOT/'outputs/feeds/latest.json').read_text(encoding='utf-8'))
            added=ingest(data,p); validate(data); save_store(data); print('Nuevas entradas:',added)
        if args.command=='apply':
            if not args.file: raise ValueError('Falta --file')
            import app_workflow as workflow
            with workflow.execution_scope(args.request_ids.split(',') if args.request_ids is not None else None):
                if apply_batch(data,parse_json(Path(args.file).read_text(encoding='utf-8-sig'))): save_store(data)
        if args.command=='clear-opportunities':
            if args.expected_revision is None: raise ValueError('Indica --expected-revision')
            counts=clear_opportunities(data,args.expected_revision)
            save_store(data)
            print(json.dumps({'removed':counts,'revision':data['revision'],
                              'snapshot':str(snapshot_path(data['lastOpportunityReset']['backupSha256']))},ensure_ascii=False))
            return
        if args.command=='import-cv':
            if not args.file:raise ValueError('Indica el PDF con --file')
            path=Path(args.file)
            try:available=path.is_file() and path.stat().st_size<=10_000_000
            except OSError:available=False
            if not available:raise ValueError('Elige un PDF disponible de hasta 10 MB')
            if import_cv(data,args.name or path.name,path.read_bytes(),actor='Agente'):save_store(data)
            print(json.dumps({'cvLibrary':data['app']['cvLibrary']},ensure_ascii=False));return
        if args.command=='plan':
            import assistant_flow,agent_runner
            if not data.get('app',{}).get('setupComplete',True):raise ValueError('Completa primero el perfil inicial con tu IA')
            if agent_runner.view()['status'] in agent_runner.ACTIVE or any(r['status']=='running' for r in data.get('app',{}).get('requests',[])):raise ValueError('Hay trabajo en curso; espera antes de preparar más tareas')
            ops=assistant_flow.plan(data,args.search_profile)
            if ops and apply_batch(data,{'id':'plan-'+str(uuid.uuid4()),'operations':ops}):save_store(data)
        if args.command=='upgrade-app':
            import app_workflow as workflow
            import app_context as context
            before=copy.deepcopy(data);workflow.seed(data);context.question_catalog(data)
            if data!=before:save_store(data)
        if args.command=='packages': packages(data)
    if args.command=='export': data=export()
    if args.command=='handoff':
        from agent_runner import external_prompt
        print(external_prompt(data) or 'No hay trabajo pendiente.')
    elif args.command=='app-status':
        from stubbs_jobs_app import state_view
        print(json.dumps(state_view(),ensure_ascii=False))
    else:print(json.dumps(report(data),ensure_ascii=False))

def initialize():
    if STORE.exists():return read_store()
    from personalization import blank_store
    data=blank_store();validate(data);save_store(data);return data

def table_csv(data):
    import csv,io
    output=io.StringIO(newline='');writer=csv.writer(output)
    fields=['Empresa','Puesto','Estado','Siguiente paso','URL original']
    writer.writerow(fields)
    for row in data['sheets']['Oportunidades']:
        writer.writerow([("'"+str(row.get(k))) if str(row.get(k) or '').lstrip().startswith(('=','+','-','@')) else row.get(k) or '' for k in fields])
    return output.getvalue().encode('utf-8-sig')

def import_cv(data,name,content,actor='Usuario'):
    if not isinstance(name,str) or not name.lower().endswith('.pdf') or len(content)>10_000_000 or not content.startswith(b'%PDF-'):raise ValueError('Elige un PDF válido de hasta 10 MB')
    import pypdfium2
    try:pdf=pypdfium2.PdfDocument(content)
    except Exception as exc:raise ValueError('El PDF no se pudo leer. Comprueba que no esté dañado o protegido.') from exc
    try:
        if not 1<=len(pdf)<=50:raise ValueError('El PDF debe tener entre 1 y 50 páginas')
    finally:pdf.close()
    key=digest(content);relative='outputs/cv/'+key+'.pdf'
    library=data.setdefault('app',{}).setdefault('cvLibrary',[])
    registered=next((item for item in library if item['id']==key),None)
    if registered:
        path=(ROOT/registered['path']).resolve()
        if not path.is_relative_to((ROOT/'outputs/cv').resolve()):raise ValueError('Ruta de CV no válida')
        if path.is_file():
            if digest(path.read_bytes())!=key:raise ValueError('La copia de este CV ha cambiado. Conserva ese archivo y recupera el original antes de continuar.')
            return False
        atomic_bytes(path,content)
        import app_workflow as w
        w.record(data,'CV recuperado',actor=actor,detail='Se recuperó el PDF original aportado, sin crear otro documento ni cambiar sus datos.')
        return True
    atomic_bytes(ROOT/relative,content)
    library.append({'id':key,'name':Path(name.replace('\\','/')).name[:180],'path':relative})
    import app_workflow as w
    import app_context as c
    w.record(data,'CV añadido',actor=actor)
    if data.get('app',{}).get('setupComplete',True):
        c.add_change(data,None,'Revisar el CV aportado: '+relative+'. Contrastar sus datos con la experiencia confirmada; preguntar ante discrepancias. No reemplazar paquetes enviados.',actor)
    return True

if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError,KeyError,StopIteration) as exc: raise SystemExit(str(exc) or 'Referencia inexistente')
