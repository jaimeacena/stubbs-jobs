"""Loopback-only local application. No cloud service or browser credentials."""
import argparse
import application_lifecycle
import copy
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import signal
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from urllib.request import Request, urlopen
from stubbs_jobs_core import ROOT, DATA, WORKBOOK, lock, read_store, save_store, atomic_json, digest, now, parse_json, vacancy_key
import stubbs_jobs as j
import app_workflow as w
import agent_runner
import app_context as context
import offer_minimums
import view_cache
import personalization
import onboarding
import offer_quality
import window_icon
from runtime import excel_available
from state_support import cycle_view, excel_date, instant, first_seen_dates

WEB=ROOT/'app'
INSTANCE=DATA/'app-instance.json'
EXPORT_STATUS=DATA/'app-export.json'
PROJECT=digest(str(ROOT.resolve()))[:24]
SESSION=secrets.token_urlsafe(32)
COOKIE='stubbs_jobs_'+PROJECT

def service_build():
    """Identify the Python code loaded by this service, including its route list."""
    fingerprint=hashlib.sha256()
    for path in sorted((ROOT/'tools').glob('*.py')):
        fingerprint.update(path.name.encode('utf-8'))
        fingerprint.update(path.read_bytes())
    return fingerprint.hexdigest()

SERVICE_BUILD=service_build()
# Windows can map .js/.css to text/plain in its registry; with nosniff the
# window would refuse to run the interface. Known types never depend on it.
CONTENT_TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8',
               '.png':'image/png','.ico':'image/x-icon','.pdf':'application/pdf','.txt':'text/plain; charset=utf-8',
               '.json':'application/json; charset=utf-8','.csv':'text/csv; charset=utf-8','.zip':'application/zip',
               '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
SERVER_LOG=DATA/'app-server.log'
SERVER_LOG_LIMIT=1_000_000
LOG_LOCK=threading.Lock()

def content_type(name):
    return CONTENT_TYPES.get(Path(name).suffix.lower()) or mimetypes.guess_type(name)[0] or 'application/octet-stream'

def log_failure(method,path):
    """Keep unexpected failures diagnosable without request bodies or query values."""
    import traceback
    entry=json.dumps({'at':now(),'method':method,'path':urlsplit(path).path[:200],'build':SERVICE_BUILD[:12],
                      'error':traceback.format_exc()[-4000:]},ensure_ascii=False)+'\n'
    try:
        with LOG_LOCK:
            DATA.mkdir(parents=True,exist_ok=True)
            if SERVER_LOG.exists() and SERVER_LOG.stat().st_size>SERVER_LOG_LIMIT:
                os.replace(SERVER_LOG,SERVER_LOG.with_name(SERVER_LOG.name+'.1'))
            with SERVER_LOG.open('a',encoding='utf-8') as handle:handle.write(entry)
    except OSError:
        pass
PDF_LOCK=threading.Lock()
EXPORT_LOCK=threading.Lock()

def transact(batch):
    for retry in range(12):
        try:
            with w.interface_writer(),lock():
                data=read_store();j.recover_export(data)
                changed=j.apply_batch(data,batch)
                if changed:save_store(data)
                return data
        except RuntimeError:
            if retry==11:raise ValueError('El registro está ocupado. Tu borrador se conserva; vuelve a guardar en unos segundos.')
            time.sleep(.15)

def edit_token(data,op_id):
    d=w.draft(data,op_id)
    return {k:d.get(k) for k in ('message','recipient')}

def document_url(path):return '/api/document?id='+quote(path,safe='')

def request_view(request,unresolved_ids=None,superseded=None):
    from request_workflow import interruption_unconfirmed
    result={k:v for k,v in request.items() if k!='discoveryBaseline'}
    if interruption_unconfirmed(request):result['interruptionUnconfirmed']=True
    if superseded and request['id'] in superseded:result['supersededByRequestId']=superseded[request['id']]
    if (unresolved_ids is not None and request.get('type')=='send' and request.get('status')=='cancelled'
            and request.get('deliveryCheck',{}).get('outcome')=='not_sent'):
        result['deliveryRecheckRequired']=request['id'] in unresolved_ids
    return result

def state_view(data=None,brief=False,case=None,history=False,since=None,pure=False):
    cases = set(case) if isinstance(case, (list, tuple)) else {case} if case else set()
    if len(cases) > 500:
        raise ValueError('Selecciona como máximo 500 ofertas')
    with view_cache.snapshot():
        data=data if data is not None else read_store()
        execution=agent_runner.peek() if pure else agent_runner.view()
        version=state_version(data,brief,case,history,execution=execution)
        if since==version:return {'unchanged':True,'version':version}
        result=build_state(data,include_export=not brief,include_instructions=not brief,execution=execution)
        if brief:
            for row in result['opportunities']:
                if row['id'] in cases:continue
                for key in ('draft','answers','answerOverrides','sentMaterial','evidence','fieldDefinitions','changes','contactDrafts'):
                    row.pop(key,None)
                row['packages']=[{k:v for k,v in p.items() if k!='payload'} for p in row['packages']]
                row['requests']=[{k:v for k,v in r.items() if k not in ('result','instructions')} for r in row['requests']]
            if not history:result['history']=[h for h in result['history'] if h.get('opportunityId') in cases][-3:] if cases else []
            elif cases:result['history']=[h for h in result['history'] if h.get('opportunityId') in cases]
            if not history:
                result['requests']=[{k:v for k,v in r.items() if k not in ('result','instructions') or r.get('opportunityId') in cases} for r in result['requests']]
            result['undo']=[{k:v for k,v in item.items() if k in ('id','kind','opportunityId','title','actor')} for item in result['undo']]
            for key in ('entries','agentInstructions','handoff'):result.pop(key,None)
        result['version']=version
        return result

def state_version(data,brief=False,case=None,history=False,execution=None):
    files={}
    for row in data['sheets']['Oportunidades']:
        name=row.get('CV preparado')
        if name and name not in files:
            content=w.cv_bytes(row);files[name]=digest(content) if content else None
    paths=[ROOT/'perfil.md',ROOT/'config/sources.json']
    if not brief:paths.extend((EXPORT_STATUS,WORKBOOK))
    for path in paths:
        try:files[str(path)]=digest(path.read_bytes()) if path.is_file() else None
        except OSError:files[str(path)]='unreadable'
    # A damaged archived CV must invalidate an otherwise unchanged screen.
    for package in data.get('app',{}).get('packages',[]):
        files['package:'+package['id']]=w.package_issue(package)
    for row in data['sheets']['Oportunidades']:
        sent=next((e for e in data['events'] if e.get('type')=='sent' and e.get('opportunityId')==row['ID']),None)
        if sent and not sent.get('packageId'):
            files['sent:'+row['ID']]=legacy_sent_cv(row,sent)
    return digest([data.get('_baseHash') or digest(data),files,cv_library(data),agent_runner.view() if execution is None else execution,datetime.now(timezone.utc).isoformat(timespec='minutes'),brief,case,history])

def export_view(data):
    try:export=json.loads(EXPORT_STATUS.read_text(encoding='utf-8'))
    except (OSError,ValueError):export={'status':'pending'}
    if not isinstance(export,dict):export={'status':'pending'}
    if not WORKBOOK.is_file() and export.get('status')!='working':
        return {**export,'status':'pending','message':'Excel no está disponible. Puedes volver a prepararlo desde los datos guardados.'}
    content=j.export_fingerprint(data)
    workbook_changed=WORKBOOK.exists() and digest(WORKBOOK.read_bytes())!=data.get('workbookHash')
    if workbook_changed:return {'status':'pending','message':'Excel tiene cambios externos. El agente debe conciliarlos antes de actualizarlo.'}
    if data.get('workbookContentHash')==content and export.get('status')!='working':return {**export,'status':'ok'}
    if export.get('status')=='ok':return {**export,'status':'pending'}
    return export


def legacy_sent_cv(row,sent):
    """An old receipt can identify bytes; today's preparation cannot fill its gaps."""
    import cv_usage
    if sent.get('packageId'):
        return None,'No se conserva el paquete original de este envío.'
    expected=sent.get('cvHash')
    if isinstance(expected,str) and re.fullmatch(r'[a-f0-9]{64}',expected):
        for name in (sent.get('archivedCV'),sent.get('cv'),row.get('CV usado')):
            if not isinstance(name,str) or not name:continue
            try:
                path=(ROOT/name).resolve()
                allowed=any(path.is_relative_to((ROOT/folder).resolve()) for folder in ('outputs','data/packages'))
                if allowed and cv_usage.file_hash(ROOT,name)==expected:return name,None
            except (OSError,ValueError):continue
    return None,'El envío está confirmado, pero no se conserva un CV original cuyo contenido pueda comprobarse.'


def build_state(data,include_export=True,include_instructions=True,execution=None):
    app=w.seed(data)
    import search_profiles
    discovery_dates=first_seen_dates(data)
    unresolved_ids={r['id'] for r in w.unresolved_sends(data)}
    superseded=w.superseded_sends(data)
    packages=view_cache.grouped(app['packages'],'opportunityId')
    events=view_cache.grouped(data['events'],'opportunityId')
    requests_by_id=view_cache.grouped(app['requests'],'opportunityId')
    contacts_by_id=view_cache.grouped(app.get('contactDrafts',[]),'opportunityId')
    evidence=view_cache.grouped(data['sheets']['Evidencias'],'ID oportunidad')
    latest_activity={}
    for event in app['history']:
        op_id=event.get('opportunityId')
        if not op_id:continue
        try:
            parsed=datetime.fromisoformat(event['at'])
            stamp=(parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
        except (ValueError,TypeError,KeyError,OverflowError,OSError):continue
        if op_id not in latest_activity or stamp>latest_activity[op_id][0]:latest_activity[op_id]=(stamp,event['at'])
    rows=[]
    for row in data['sheets']['Oportunidades']:
        numbers=offer_minimums.current_facts(data,row)
        op_id=row['ID'];d=w.draft(data,op_id);p=w.payload(data,op_id)
        packs=packages.get(op_id,[])
        sent=next((e for e in events.get(op_id,[]) if e['type']=='sent'),None)
        archive=w.archived(data,op_id) or {}
        lifecycle=application_lifecycle.view(data,row)
        rejection_dates=[e.get('at') for e in events.get(op_id,[]) if e['type']=='rejected' and instant(e.get('at'))]
        if archive.get('source')=='employer' and archive.get('outcome')=='rejected' and instant(archive.get('at')):
            rejection_dates.append(archive['at'])
        rejected_at=max(rejection_dates,key=instant,default=None)
        sent_package=next((p for p in packs if sent and p['id']==sent.get('packageId')),None)
        legacy_cv,legacy_error=legacy_sent_cv(row,sent) if sent and not sent_package else (None,None)
        shown=sent_package['payload'] if sent_package else {'cv':legacy_cv,'cvHash':sent.get('cvHash'),
            'cvReason':'','changes':[],'answers':{},'formAnswerKeys':[],'message':'','messageUsage':'unknown',
            'recipient':sent.get('recipient'),'legacyIncomplete':True} if sent else p
        current_hash=w.stamp(data,op_id);missing=list(w.readiness(data,op_id))
        shown_package=sent_package or next((pack for pack in packs if pack['id']==current_hash),None)
        integrity_error=legacy_error if sent and not sent_package else w.package_issue(shown_package) if shown_package else None
        if integrity_error and not sent:missing.append(integrity_error)
        required=[context.definitions(data,op_id)[k] for k in d['requiredAnswers'] if p['answers'].get(k) is None or p['answers'].get(k)=='']
        reviewed=d.get('review',{}).get('fingerprint')==current_hash
        cv_checked=bool(p['cvHash']) and d.get('cvReview',{}).get('fingerprint')==context.cv_stamp(data,op_id)
        cv_state=('CV enviado no disponible' if integrity_error else 'CV enviado') if sent else 'CV revisado para esta oferta' if cv_checked or reviewed else 'CV elegido · pendiente de revisar' if p['cvHash'] else 'CV por preparar'
        available=bool(p['cvHash'])
        cv_url=None if integrity_error else document_url('package:'+sent_package['id']) if sent_package else document_url('sent:'+op_id) if sent and legacy_cv else document_url('cv:'+op_id) if not sent and available else None
        due=excel_date(row.get('Fecha objetivo'))
        records=[{**x,'isCurrent':x['id']==current_hash,'cvUrl':document_url('package:'+x['id']), 'messageUrl':document_url('message:'+x['id'])} for x in packs]
        requests=[application_lifecycle.request_view(data,request_view(r,unresolved_ids,superseded),w) for r in requests_by_id.get(op_id,[])
                  if r['status'] not in ('done','cancelled') or
                  r['type']=='send' and r['status']=='cancelled' and r.get('packageId') and instant(r.get('startedAt'))]
        authorized=any(p['id']==current_hash and p.get('approvedAt') and not p.get('revokedAt') for p in packs)
        who='Empresa' if sent and row['Estado'] not in w.CLOSED else 'Tú' if required or (not missing and not sent and not authorized) else 'Agente'
        if row['Estado'] in w.CLOSED:who='Proceso cerrado'
        rows.append({'id':op_id,'company':row['Empresa'],'title':personalization.display_title(row),'originalTitle':row['Puesto'],'priority':row['Prioridad'],'state':row['Estado'],'next':row.get('Siguiente paso'),'due':due,'externalDeadline':row.get('Plazo externo'),'canonicalKey':vacancy_key(row),'fieldDefinitions':context.definitions(data,op_id),'fitFingerprint':context.fit_stamp(data,row),
                     'url':row['URL original'],'source':row['Fuente'],'family':row.get('Familia'),'owner':who,'cv':shown['cv'],'cvLabel':Path(shown['cv']).name if shown['cv'] else None,
                     'integrityError':integrity_error,'cvFingerprint':context.cv_stamp(data,op_id),'cvHash':p['cvHash'],'cvState':cv_state,'cvUrl':cv_url,'cvReason':shown['cvReason'],'changes':shown['changes'],
                     'draft':d,'answers':p['answers'],'answerOverrides':d['answers'],'missing':missing,'questions':required,'fingerprint':current_hash,'packages':records,'sent':sent,'sentMaterial':shown if sent else None,
                     'requests':requests,'contactDrafts':contacts_by_id.get(op_id,[]),'selection':w.selection(data,op_id),'archivedAt':archive.get('at'),'discardedAt':archive.get('at') if not sent and archive.get('outcome')!='rejected' else None,'rejectedAt':rejected_at,'appliedAt':excel_date(row.get('Fecha candidatura')),'snoozedUntil':app['snoozes'].get(op_id),'apply':j.conditions(data,row)[0],'accept':j.conditions(data,row)[1],
                     'conditions':{k:numbers.get(k,row.get(k)) for k in j.CONDITIONS},'salary':row.get('Banda publicada'),'schedule':row.get('Horario real'),'firstSeenAt':discovery_dates.get(op_id),
                     'country':row.get('País'), 'place':row.get('Ubicación'), 'round':app.get('offerRounds',{}).get(op_id), **search_profiles.offer_info(data,op_id), 'workMode':row.get('Modalidad') or ('Remoto' if numbers.get('Remoto España',row.get('Remoto España'))=='Sí' else None), 'contract':row.get('Contrato'),
                     'technologies':row.get('Tecnologías'),'requirements':row.get('Requisitos de la oferta'),'notes':row.get('Notas de seguimiento'),
                     'lifecycle':lifecycle, 'minimums':offer_minimums.view(data,row), 'archiveReason':(w.archived(data,op_id) or {}).get('reason'), 'archiveOutcome':application_lifecycle.archive_outcome(data,row),
                     'fixedSalary':numbers.get('Fijo mín. confirmado'),
                     'fixedSalaryMax':numbers.get('Fijo máx. confirmado'), 'minimumTrips':numbers.get('Viajes mín. al mes'),
                     'fixedSalaryCurrency':numbers.get('Moneda fijo confirmado') or ('EUR' if not app.get('personalized') else None),
                     'pendingChange':w.pending_change(data,op_id),
                     'assessmentFingerprint':offer_quality.fingerprint(data,row),'assessment':offer_quality.view(data,row),'evidence':evidence.get(op_id,[]),'lastActivityAt':latest_activity.get(op_id,(None,None))[1]})
    source_error=None
    try:public_sources=personalization.public_sources(data)
    except (OSError,ValueError,TypeError,KeyError):
        public_sources=[]
        source_error='No se pudo leer la configuración de webs. El agente debe comprobar config/sources.json y las webs guardadas en Mi perfil.'
    configured_ids={source['id'] for source in public_sources}
    health=[]
    for h in data['sourceHealth'].values():
        if h.get('sourceId') in configured_ids:
            health.append({k:h.get(k) for k in ('sourceId','company','status','checkedAtUtc','lastSuccessUtc','errors','coverage','sourceUrl','scope','method') if k in h})
    cycles=[cycle_view(c) for c in data['cycles'][-5:]]
    export=export_view(data) if include_export else {'status':'on_request'}
    history_by_id={h['id']:h for h in app['history']}
    undo=[{**x,'title':history_by_id.get(x['id'],{}).get('title','Cambio guardado'),
           'actor':history_by_id.get(x['id'],{}).get('actor','Agente')} for x in app['undo'] if w.undo_available(data,x)]
    setup=onboarding.view(data,ROOT)
    if not include_instructions:setup.pop('draft',None)
    return {'revision':data['revision'],'updatedAt':data['updatedAt'],'workspaceId':digest(str(ROOT.resolve()))[:24],'onboarding':setup,'opportunities':rows,'profile':data['profile'],'labels':{k:f['label'] for k,f in context.definitions(data).items()},'fieldDefinitions':context.definitions(data),'preferences':context.criteria(data),
            'setupComplete':app.get('setupComplete',True),'personalized':app.get('personalized',False),'legacyEvidenceMode':not bool(data.get('lastOpportunityReset')) and not app.get('personalized',False),'searchContext':personalization.context(data),'excelAvailable':excel_available(ROOT),
            'searchProfiles':search_profiles.visible_profiles(data),'deletedSearchProfiles':search_profiles.deleted_profiles(data),
            'defaultSearchProfileId':search_profiles.default_id(data),
            'assistantMode':personalization.assistant_mode(data),'automation':{'applicationMode':w.automation(data)['applicationMode']},'workspacePath':str(ROOT),'agentInstructions':agent_runner.external_prompt(data) if include_instructions else '',
            'experience':context.experience(data),'applicationVerification':personalization.application_verification(data),
            'history':application_lifecycle.history_view(data),'seenAt':app['seenAt'],'snoozes':app['snoozes'],'rounds':w.rounds(data),'requests':[application_lifecycle.request_view(data,request_view(req,unresolved_ids,superseded),w) for req in app['requests']],'undo':undo,
            'metrics':j.metrics(data),
            'health':health,'sourceConfigurationError':source_error,'publicSources':[{'id':s['id'],'company':s['company'],'checked':s['id'] in data['sourceHealth']} for s in public_sources],
            'portalAccess':app.get('portalAccess',{}),
            'cycles':cycles,'export':export,'execution':agent_runner.view() if execution is None else execution,
            'handoff':f'Continúa los encargos pendientes o bloqueados de Stubbs Jobs en {ROOT}. Lee AGENTS.md, status y app-status. Revisa el motivo de cada bloqueo; no repitas un posible envío sin comprobar el portal. No autorices nuevos paquetes en mi nombre.',
            'historical':[{**record,'canonicalKey':vacancy_key(record)} for record in data['historicalApplications']],'entries':data['sheets']['Entradas'],
            'cvLibrary':cv_library(data)}

@view_cache.cached(lambda data:(id(data),str(ROOT)))
def cv_library(data):
    import cv_usage
    registered=[{'id':p['id'],'name':p['name'],'path':p['path'],'url':document_url('uploaded:'+p['id'])} for p in data.get('app',{}).get('cvLibrary',[])]
    legacy=[{'name':p.name,'path':p.relative_to(ROOT).as_posix(),'url':document_url('library:'+p.name)} for p in cv_usage.legacy_paths(data,ROOT)]
    return cv_usage.enrich(data,legacy+registered,ROOT,w.package_issue)

def doc_path(identifier):
    if identifier.startswith('backup:'):
        import backup
        name=identifier.removeprefix('backup:')
        if not re.fullmatch(r'Stubbs-Jobs-copia-[A-Za-z0-9_T.\-]+\.zip',name):raise ValueError('Copia de seguridad no disponible')
        path=backup.source_file(ROOT,'data/backups/'+name)
        backup.verify(path.read_bytes())
        return path
    data=read_store();kind,_,value=identifier.partition(':')
    if kind=='sent':
        row=w.row_for(data,value)
        sent=next((e for e in data['events'] if e.get('type')=='sent' and e.get('opportunityId')==value),None)
        if not sent:raise ValueError('No hay un envío confirmado para esta oferta')
        name,issue=legacy_sent_cv(row,sent)
        if issue:raise ValueError(issue)
        return (ROOT/name).resolve()
    if kind=='uploaded':
        item=next((p for p in data.get('app',{}).get('cvLibrary',[]) if p['id']==value),None)
        if not item:raise ValueError('CV desconocido')
        path=(ROOT/item['path']).resolve()
        if not path.is_relative_to((ROOT/'outputs/cv').resolve()) or path.suffix.lower()!='.pdf':raise ValueError('Ruta de CV no válida')
        if not path.is_file() or digest(path.read_bytes())!=item['id']:raise ValueError('El CV guardado ha cambiado o no está disponible. Recupera el archivo original o añade la versión nueva.')
        return path
    if kind=='cv':
        row=w.row_for(data,value);path=(ROOT/(row.get('CV preparado') or 'missing')).resolve()
        if not path.is_relative_to((ROOT/'outputs').resolve()) or path.suffix.lower()!='.pdf':raise ValueError('Documento no disponible')
        return path
    if kind in ('package','message'):
        package=next((p for p in w.state(data)['packages'] if p['id']==value),None)
        if not package:raise ValueError('Paquete desconocido')
        w.verify_package(package)
        return DATA/'packages'/value/('cv.pdf' if kind=='package' else 'presentacion.txt')
    if kind=='library':
        import cv_usage
        allowed={p.name:p for p in cv_usage.legacy_paths(data,ROOT)}
        if value not in allowed:raise ValueError('CV desconocido')
        path=allowed[value].resolve()
        if not path.is_relative_to((ROOT/'outputs').resolve()):raise ValueError('Ruta de CV no válida')
        return path
    if identifier=='excel':return WORKBOOK
    raise ValueError('Documento no disponible')

def preview(identifier):
    with PDF_LOCK:return render_preview(identifier)

def render_preview(identifier):
    import pypdfium2 as pdfium
    p=doc_path(identifier)
    if p.suffix.lower()!='.pdf':raise ValueError('La vista previa requiere un PDF')
    raw=p.read_bytes();cache=DATA/'preview-cache'/(digest(raw)+'.png')
    if cache.exists():return cache.read_bytes()
    pdf=pdfium.PdfDocument(raw)
    try:
        page=pdf[0];bitmap=page.render(scale=1.8)
        try:
            output=io.BytesIO();bitmap.to_pil().save(output,format='PNG');content=output.getvalue()
            from stubbs_jobs_core import atomic_bytes
            atomic_bytes(cache,content);return content
        finally:bitmap.close();page.close()
    finally:pdf.close()

def export_on_request():
    """Build Excel only for an explicit request; saving never launches a worker."""
    if not excel_available(ROOT):raise ValueError('Las dependencias de Excel no están disponibles.')
    if not EXPORT_LOCK.acquire(blocking=False):raise ValueError('Ya se está preparando Excel.')
    try:
        atomic_json(EXPORT_STATUS,{'status':'working','at':now()})
        try:
            j.export()
            atomic_json(EXPORT_STATUS,{'status':'ok','at':now()})
        except Exception as exc:
            atomic_json(EXPORT_STATUS,{'status':'pending','at':now(),'error':str(exc),
                                       'message':'Tus datos están guardados. Excel no se ha actualizado.'})
            raise ValueError('No se pudo preparar Excel: '+str(exc)) from exc
        return {'ok':True}
    finally:EXPORT_LOCK.release()

class Handler(BaseHTTPRequestHandler):
    timeout=20
    def log_message(self,*args):pass
    def headers_ok(self):
        return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def authenticated(self):
        cookie=SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie',''))
            return bool(cookie.get(COOKIE) and hmac.compare_digest(cookie[COOKIE].value,SESSION))
        except Exception:return False
    def send(self,status,body,content_type='application/json; charset=utf-8',extra=None):
        if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
    def do_GET(self):
        if not self.headers_ok():return self.send(403,{'error':'Acceso local no válido'})
        path=urlsplit(self.path).path
        if path=='/health':return self.send(200,{'project':PROJECT,'name':'Stubbs Jobs','build':SERVICE_BUILD,'pid':os.getpid()})
        if path in ('/window-icon.js','/window-icon-status'):
            token=parse_qs(urlsplit(self.path).query).get('token',[''])[0]
            if path=='/window-icon-status':return self.send(200,{'status':window_icon.status(token)})
            script=window_icon.script(token)
            return self.send(404,{'error':'No se encuentra esa página'}) if script is None else self.send(200,script.encode('utf-8'),'application/javascript; charset=utf-8')
        static={'/':'index.html','/icons.js':'icons.js','/app.js':'app.js','/client.js':'client.js','/formatting.js':'formatting.js','/workflow.js':'workflow.js','/criteria.js':'criteria.js','/recovery.js':'recovery.js','/explanations.js':'explanations.js','/activity.js':'activity.js','/setup.js':'setup.js','/drafts.js':'drafts.js','/presentation.js':'presentation.js','/theme.js':'theme.js','/release.js':'release.js','/redesign.css':'redesign.css','/assets/stubbs.png':'assets/stubbs.png','/assets/stubbs.ico':'assets/stubbs.ico','/favicon.ico':'assets/stubbs.ico'}
        if path in static:
            p=WEB/static[path];body=p.read_bytes()
            if path=='/':body=window_icon.html(body.decode('utf-8'),WEB/'assets',parse_qs(urlsplit(self.path).query).get('window-icon',[''])[0]).encode('utf-8')
            return self.send(200,body,content_type(p.name))
        if not self.authenticated():return self.send(401,{'error':'Abre Stubbs Jobs desde el acceso de la carpeta para recuperar la sesión.'})
        try:
            if path=='/api/state':
                query=parse_qs(urlsplit(self.path).query)
                cases=query.get('case',[])
                return self.send(200,state_view(brief=query.get('brief')==['1'],case=cases if len(cases)>1 else cases[0] if cases else None,history=query.get('history')==['1'],since=query.get('since',[None])[0]))
            if path=='/api/table':return self.send(200,j.table_csv(read_store()),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="candidaturas.csv"'})
            if path=='/api/preview':return self.send(200,preview(parse_qs(urlsplit(self.path).query).get('id',[''])[0]),'image/png')
            if path=='/api/document':
                identifier=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                p=doc_path(identifier)
                if not p.is_file():raise ValueError('El archivo no está disponible')
                kind=content_type(p.name)
                disposition='attachment' if identifier=='excel' or 'download' in parse_qs(urlsplit(self.path).query) else 'inline'
                return self.send(200,p.read_bytes(),kind,{'Content-Disposition':f"{disposition}; filename*=UTF-8''{quote(p.name)}"})
            return self.send(404,{'error':'No se encuentra esa página'})
        except (ValueError,StopIteration,FileNotFoundError) as exc:return self.send(404,{'error':str(exc) or 'No se encuentra ese elemento'})
        except KeyError:return self.send(404,{'error':'No se encuentra ese elemento'})
        except Exception:
            log_failure('GET',self.path)
            return self.send(503,{'error':'No se pudo leer el registro. Conserva la pantalla y vuelve a intentarlo.'})
    def do_POST(self):
        origin=f'http://127.0.0.1:{self.server.server_port}'
        if not self.headers_ok() or self.headers.get('Origin')!=origin or self.headers.get('X-StubbsJobs')!='1':return self.send(403,{'error':'Petición no autorizada'})
        try:
            lengths=self.headers.get_all('Content-Length',[])
            if len(lengths)!=1 or self.headers.get('Transfer-Encoding'):
                raise ValueError('La petición necesita una longitud única y completa')
            length=int(lengths[0])
            upload=urlsplit(self.path).path=='/api/import-cv'
            if upload and not self.authenticated():return self.send(401,{'error':'Abre Stubbs Jobs desde su acceso'})
            if length<1 or length>(14_000_000 if upload else 150000):raise ValueError('Petición demasiado grande o vacía')
            raw=self.rfile.read(length)
            if len(raw)!=length:raise ValueError('La petición llegó incompleta; vuelve a intentarlo con los mismos datos')
            body=parse_json(raw)
            if not isinstance(body,dict):raise ValueError('La petición debe contener los datos de la acción')
            try:json.dumps(body,allow_nan=False)
            except ValueError as exc:raise ValueError('La petición contiene una cantidad no válida') from exc
            path=urlsplit(self.path).path
            if path in ('/api/window-icon','/api/window-icon/start'):
                if not hmac.compare_digest(str(body.get('key','')),SESSION):return self.send(401,{'error':'Sesión no reconocida'})
                result=window_icon.register(str(body.get('token','')),DATA) if path.endswith('/start') else window_icon.acknowledge(str(body.get('token','')),str(body.get('status','')))
                return self.send(200 if result else 400,{'ok':result})
            if path=='/api/session':
                if not hmac.compare_digest(str(body.get('key','')),SESSION):return self.send(401,{'error':'Vuelve a abrir Stubbs Jobs desde su acceso.'})
                return self.send(200,{'ok':True},extra={'Set-Cookie':f'{COOKIE}={SESSION}; HttpOnly; SameSite=Strict; Path=/'})
            if not self.authenticated():return self.send(401,{'error':'La sesión terminó. Abre Stubbs Jobs desde el acceso de la carpeta.'})
            if path=='/api/backup':
                import backup
                result=backup.create(ROOT)
                return self.send(200,{**result,'download':document_url('backup:'+result['name'])})
            if path=='/api/import-cv':
                import base64
                content=base64.b64decode(body['content'],validate=True)
                with lock():
                    data=read_store()
                    if j.import_cv(data,body['name'],content):save_store(data)
                return self.send(200,{'state':state_view()})
            if path=='/api/run':
                raise ValueError('Abre tu agente y pídele que continúe con Stubbs Jobs; leerá el estado actual')
            if path=='/api/assist':
                raise ValueError('El lanzador local se ha retirado. Continúa con Stubbs Jobs en el chat de tu agente.')
            if path=='/api/export':
                return self.send(200,export_on_request())
            if path=='/api/open-excel':
                if os.name!='nt':raise ValueError('Abrir Excel está disponible en Windows; utiliza Descargar.')
                os.startfile(str(WORKBOOK))
                return self.send(200,{'ok':True})
            if path=='/api/criteria-preview':
                # Read-only: the estimate runs on a copy and is never saved.
                import criteria_preview
                return self.send(200,criteria_preview.preview(read_store(),body))
            if path!='/api/action':return self.send(404,{'error':'Acción desconocida'})
            operation=body['operation']
            if not isinstance(operation,dict):raise ValueError('Acción no válida')
            kind=operation.get('kind')
            allowed={'ui-setup-retry','ui-setup-finish','ui-profile-section','ui-assistant-settings','ui-search-context','ui-add-opportunity','ui-profile','ui-preferences','ui-experience','ui-responses','ui-change','ui-offer-note','ui-inherit','ui-draft','ui-request','ui-approve','ui-revoke','ui-request-update','ui-snooze','ui-seen','ui-undo','ui-automation-settings','ui-select-opportunity','ui-criteria-scope'}
            allowed.add('ui-search-profile')
            allowed.update(('ui-bulk-action','ui-followup-plan'))
            if kind not in allowed:raise ValueError('Acción no disponible desde la aplicación')
            if kind=='ui-request' and operation.get('type')=='send':raise ValueError('Revisa y autoriza el paquete antes de solicitar su envío')
            if kind=='ui-request-update' and operation.get('status') not in ('queued','cancelled'):raise ValueError('Solo el agente confirma la ejecución de un encargo')
            if kind=='ui-profile':
                fields=context.definitions(read_store(),operation.get('opportunityId'))
                allowed_fields=set(w.PERSONAL)|{k for k,f in fields.items() if k.startswith('custom_') and (operation.get('scope')!='global' or f['scope']=='global')}
                if set(operation['values'])-allowed_fields:raise ValueError('Ese dato no pertenece a estas respuestas')
            if kind=='ui-draft' and set(operation['values'])-{'message','recipient'}:raise ValueError('Ese cambio requiere revisión del agente')
            operation['actor']='Usuario' if read_store().get('app',{}).get('personalized') else 'Usuario'
            transact({'id':body['id'],'operations':[operation]})
            return self.send(200,{'ok':True,'state':state_view()})
        except w.Conflict as exc:return self.send(409,{'error':str(exc),'state':state_view()})
        except (ValueError,KeyError,StopIteration,TypeError) as exc:return self.send(400,{'error':str(exc) or 'Revisa los datos de la acción'})
        except Exception:
            log_failure('POST',self.path)
            return self.send(503,{'error':'No se pudo guardar. Tu borrador se conserva. Vuelve a intentarlo.'})

def existing():
    try:
        entry=json.loads(INSTANCE.read_text(encoding='utf-8'))
        with urlopen(f"http://127.0.0.1:{entry['port']}/health",timeout=1) as response:health=json.load(response)
        if entry.get('project')==PROJECT and health.get('project')==PROJECT:return entry,health
    except Exception:pass
    return None

def restart_stale(entry,health):
    """Stop only this app's idle service after a new backend build is installed."""
    if health.get('pid') not in (None,entry['pid']):
        raise RuntimeError('No se pudo identificar el servicio anterior de Stubbs Jobs.')
    address=f"http://127.0.0.1:{entry['port']}"
    request=Request(address+'/api/session',
        data=json.dumps({'key':entry['key']}).encode('utf-8'),
        headers={'Origin':address,'X-StubbsJobs':'1','Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=2) as response:
            if not json.load(response).get('ok'):raise ValueError('Sesión no reconocida')
    except Exception as exc:
        raise RuntimeError('No se pudo verificar el servicio anterior de Stubbs Jobs.') from exc
    if agent_runner.view()['status'] in agent_runner.ACTIVE:
        raise RuntimeError('Hay un trabajo en curso. Abre Stubbs Jobs cuando termine para actualizar la ventana.')
    data=read_store()
    if any(r.get('status')=='running' for r in data.get('app',{}).get('requests',[])) or any(c.get('status')=='running' for c in data.get('cycles',[])):
        raise RuntimeError('Hay trabajo en curso. Abre Stubbs Jobs cuando termine para actualizar la ventana.')
    try:export=json.loads(EXPORT_STATUS.read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError):export={}
    if export.get('status')=='working':
        raise RuntimeError('Se está preparando Excel. Abre Stubbs Jobs dentro de un momento.')
    try:os.kill(entry['pid'],signal.SIGTERM)
    except OSError as exc:
        # An already-gone service is the goal; a refused signal is not.
        if agent_runner.process_alive(entry['pid']):
            raise RuntimeError('No se pudo detener el servicio anterior de Stubbs Jobs. Ciérralo desde el Administrador de tareas y vuelve a abrirlo.') from exc
        return
    for _ in range(30):
        if not agent_runner.process_alive(entry['pid']):return
        time.sleep(.1)
    raise RuntimeError('El servicio anterior no se ha detenido. Vuelve a abrir Stubbs Jobs.')

def open_window(address):
    """Open the local dashboard as an app window, retaining the browser fallback."""
    candidates=[shutil.which('msedge.exe')]
    for variable in ('PROGRAMFILES(X86)','PROGRAMFILES','LOCALAPPDATA'):
        base=os.environ.get(variable)
        if base:candidates.append(str(Path(base)/'Microsoft/Edge/Application/msedge.exe'))
    edge=next((path for path in candidates if path and Path(path).is_file()),None)
    if edge:
        try:
            def spawn(arguments):
                return subprocess.Popen(arguments,stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
            launcher=WEB.parent/'Abrir Stubbs Jobs.exe'
            if os.name=='nt' and window_icon.launch(edge,address,launcher,PROJECT,DATA,spawn):return
            spawn([edge,'--app='+address])
            return
        except OSError:pass
    webbrowser.open(address)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--open',action='store_true');parser.add_argument('--port',type=int,default=18743);parser.add_argument('--no-export',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
    DATA.mkdir(exist_ok=True)
    # Separate OS-owned launch lock prevents two double-clicks spawning two servers.
    with lock(DATA/'app-launch'):
        running=existing()
        if running:
            entry,health=running
            if health.get('build')==SERVICE_BUILD:
                if args.open:open_window(f"http://127.0.0.1:{entry['port']}/#key={entry['key']}")
                return
            restart_stale(entry,health)
        from runtime import doctor
        dependencies=doctor(Path(__file__).resolve().parents[1])
        if not dependencies['ok']:
            missing=', '.join(item['name'] for item in dependencies['checks'] if not item['available'])
            raise ValueError('Faltan dependencias para abrir Stubbs Jobs: '+missing+'. Ejecuta tools/stubbs_jobs.py doctor.')
        with lock():
            j.initialize()
            data=read_store();before=copy.deepcopy(data);w.seed(data);w.reconcile(data)
            if data!=before:save_store(data)
        try:server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
        except OSError:server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.daemon_threads=True
        atomic_json(INSTANCE,{'port':server.server_port,'key':SESSION,'pid':os.getpid(),'project':PROJECT})
    address=f'http://127.0.0.1:{server.server_port}/#key={SESSION}'
    if args.open:open_window(address)
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':
    try:main()
    except Exception:
        import traceback
        DATA.mkdir(parents=True,exist_ok=True)
        (DATA/'app-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        if os.name=='nt' and sys.stdout is None:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'No se pudo abrir Stubbs Jobs. Tus datos siguen guardados. Pide al agente que revise data/app-error.log.','Stubbs Jobs',0x10)
        else:raise
