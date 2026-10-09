'use strict';
// Coverage and chronological order share the same timestamp interpretation.
(() => {
  const Dates=typeof module!=='undefined'?require('./formatting.js'):window.StubbsJobsFormatting;
  const Workflow=typeof module!=='undefined'?require('./workflow.js'):window.StubbsJobsWorkflow;
  function newest(items,field){
    return items.reduce((latest,item)=>{
      const at=Dates.tableTimestamp(item[field]);
      return at!==null&&(latest===null||at>Dates.tableTimestamp(latest[field]))?item:latest;
    },null);
  }
  function chronological(items,field='at'){
    const value=item=>typeof field==='function'?field(item):item[field];
    return items.slice().sort((a,b)=>(Dates.tableTimestamp(value(a))??-Infinity)-(Dates.tableTimestamp(value(b))??-Infinity));
  }
  const followupTitles={waiting:'Estado comprobado: sin novedades',reviewing:'Estado comprobado: en revisión',unknown:'Estado sin confirmar',rejected:'Rechazo confirmado',closed:'Proceso cerrado por la empresa'};
  const availabilityTitles={open:'El anuncio acepta solicitudes',closed:'El anuncio ya no acepta solicitudes',unknown:'Anuncio sin confirmar'};
  function title(item){
    const fact=item.activity||{},value=String(item.title||'');
    if(fact.kind==='followup')return followupTitles[fact.outcome]||'Estado comprobado';
    if(fact.kind==='availability')return availabilityTitles[fact.outcome]||'Anuncio comprobado';
    if(/^(Envío confirmado|Solicitud enviada)$/.test(value))return 'Solicitud enviada';
    if(value==='Investigación solicitada')return 'Comprobación pedida';
    if(value==='Revisión solicitada')return 'Preparación pedida';
    if(value==='Envío puesto en cola')return 'Envío pendiente';
    if(value.startsWith('Envío autorizado'))return 'Envío autorizado';
    if(value==='Seguimiento comprobado')return 'Estado comprobado';
    if(value==='Disponibilidad comprobada')return 'Anuncio comprobado';
    if(value==='Tarea sin efecto pendiente')return 'Tarea resuelta';
    if(/^(Encargo|Tarea) terminado$/.test(value)&&fact.kind==='task')return ({review:'Preparación terminada',investigate:'Comprobación terminada',change:'Cambios aplicados',send:'Tarea de envío terminada',discovery:'Búsqueda terminada'})[fact.type]||'Tarea terminada';
    return value.replaceAll('Oferta elegida para solicitar','Oferta seleccionada').replaceAll('Encargo','Tarea')
      .replace(/\bTarea (terminado|cancelado|interrumpido)\b/g,(_,word)=>'Tarea '+word.slice(0,-1)+'a')
      .replaceAll('Paquete listo para tu decisión','Solicitud lista para revisar')
      .replace(/\bPaquete (revisado|autorizado|revocado|guardado|aprobado|actualizado|invalidado)\b/g,(_,word)=>'Solicitud '+word.slice(0,-1)+'a')
      .replaceAll('Paquete','Solicitud').replaceAll('Candidatura','Solicitud').replaceAll('candidatura','solicitud');
  }
  function caseHistory(job,model){
    const items=(model.history||[]).filter(h=>h.opportunityId===job.id).map(h=>({...h}));
    if(job.sent&&!items.some(h=>/^(Envío confirmado|Solicitud enviada)$/.test(h.title||''))){
      const at=job.sent.at||job.lifecycle?.sentAt;
      if(Dates.tableTimestamp(at)!==null)items.push({id:'receipt-view:'+job.id,opportunityId:job.id,title:'Envío confirmado',
        at,actor:job.sent.actor||'Registro',packageId:job.sent.packageId,activity:{kind:'event',type:'sent',packageId:job.sent.packageId}});
    }
    for(const [kind,value,record] of [['availability','Disponibilidad comprobada',job.lifecycle?.availability],['followup','Seguimiento comprobado',job.lifecycle?.lastCheck]]){
      if(!record||Dates.tableTimestamp(record.observedAt)===null)continue;
      if(items.some(h=>h.activity?.kind===kind&&h.activity?.checkId&&h.activity.checkId===record.id))continue;
      // Old clients may only supply the last check. Match it narrowly; never
      // apply its outcome to earlier checks with the same wording or proof.
      const matches=items.filter(h=>h.title===value&&Dates.tableTimestamp(h.at)!==null&&(!h.activity||h.activity.kind===kind)&&
        Math.abs(Dates.tableTimestamp(h.at)-Dates.tableTimestamp(record.observedAt))<=60000&&
        (h.detail&&record.proof?h.detail===record.proof:Dates.tableTimestamp(h.at)===Dates.tableTimestamp(record.observedAt)));
      const fact={kind,outcome:record.outcome,checkId:record.id,sourceUrl:record.sourceUrl,observedAt:record.observedAt};
      if(matches.length===1){if(!matches[0].activity)Object.assign(matches[0],{activity:fact,at:record.observedAt});continue;}
      items.push({id:'check-view:'+kind+':'+(record.id||job.id),opportunityId:job.id,title:value,at:record.observedAt,actor:record.actor||'Registro',activity:fact});
    }
    return chronological(items);
  }
  function grouped(items,model){
    const undo=new Set((model.undo||[]).map(item=>item.id)),requests=model.requests||[];
    const rows=chronological(items).map(item=>({...item,sourceIds:item.sourceIds?.slice()||[item.id]})),hidden=new Set();
    for(const item of rows){
      if(!/^(Encargo|Tarea) terminado$/.test(item.title||'')||undo.has(item.id))continue;
      const request=requests.find(r=>r.id===item.requestId&&r.status==='done');
      if(!request)continue;
      const candidates=rows.filter(h=>h!==item&&!undo.has(h.id)&&!/^((Encargo|Tarea) |Tarea sin efecto)/.test(h.title||'')&&
        (h.activity?.kind==='followup'||h.activity?.kind==='availability'||/^(Envío confirmado|Solicitud enviada|Paquete (listo|revisado)|Solicitud (lista|revisada))/.test(h.title||''))&&matchesCompletion(h,request));
      if(candidates.length!==1)continue;
      candidates[0].sourceIds.push(item.id);hidden.add(item.id);
    }
    return rows.filter(item=>!hidden.has(item.id));
  }
  function relevant(item){
    if(['followup','availability','event'].includes(item.activity?.kind))return true;
    return /^(?:Oferta (seleccionada|retirada|descartada|recibida)|Envío (confirmado|autorizado|suspendido|puesto en cola)|Solicitud (enviada|lista|revisada|lograda)|Respuesta|Entrevista|Proceso cerrado|Candidatura rechazada|Rechazo registrado por ti|Seguimiento (comprobado|cerrado)|Disponibilidad comprobada|Anuncio disponible|Revisión solicitada|Investigación solicitada|Paquete (listo|revisado)|Borrador actualizado|Respuestas (actualizadas|generales restauradas)|Nota de seguimiento guardada|Autorización retirada|Cambio deshecho|(?:Encargo|Tarea) (necesita|interrumpido))\b/.test(item.title||'');
  }
  function recent(items,model,limit=3){
    const rows=grouped(items,model),packageId=item=>item.activity?.packageId||item.packageId||
      (model.requests||[]).find(r=>r.id===item.requestId)?.packageId;
    const sent=rows.filter(h=>/^(Envío confirmado|Solicitud enviada)$/.test(h.title||''));
    const superseded=item=>/^(Envío autorizado|Envío puesto en cola)/.test(item.title||'')&&packageId(item)&&
      sent.some(h=>h.opportunityId===item.opportunityId&&packageId(h)===packageId(item)&&
        Dates.tableTimestamp(h.at)!==null&&Dates.tableTimestamp(item.at)!==null&&Dates.tableTimestamp(h.at)>=Dates.tableTimestamp(item.at));
    return rows.filter(item=>relevant(item)&&!superseded(item)).reverse().slice(0,limit);
  }
  function details(item,model){
    const fact=item.activity||{},job=(model.opportunities||[]).find(j=>j.id===item.opportunityId);
    if(['followup','availability'].includes(fact.kind)&&fact.outcome)return {kind:fact.kind,sourceUrl:fact.sourceUrl};
    if(fact.type==='sent'||/^(Envío confirmado|Solicitud enviada)$/.test(item.title||'')){
      const packageId=fact.packageId||item.packageId;
      const pack=packageId?(job?.packages||[]).find(p=>p.id===packageId):null;
      if(pack)return {kind:'sent',package:pack};
    }
    if(item.changedFields?.length)return {kind:'change',fields:item.changedFields};
    // Legacy answer changes contain labels. Show only known labels, never the
    // opaque historical proof or the user's saved answers.
    if(item.title==='Respuestas actualizadas'){
      const known=new Set(Object.values(job?.fieldDefinitions||model.fieldDefinitions||{}).map(f=>f.label));
      const fields=String(item.detail||'').split(', ').filter(label=>known.has(label));
      if(fields.length)return {kind:'change',fields};
    }
    return item.sourceIds?.length>1?{kind:'records'}:null;
  }
  function coverage(model){
    const expected=new Set((model.publicSources||[]).map(item=>item.id));
    const checked=(model.health||[]).filter(item=>Dates.tableTimestamp(item.checkedAtUtc)!==null);
    const good=checked.filter(item=>item.status==='ok'&&!item.errors?.length).length;
    const failed=(model.health||[]).filter(item=>item.errors?.length||item.checkedAtUtc&&item.status!=='ok').length;
    const checkedIds=new Set(checked.map(item=>item.sourceId));
    const pending=[...expected].filter(id=>!checkedIds.has(id)).length;
    const summary=checked.length?(pending?`${good} de ${expected.size} webs revisadas`:`${good} ${good===1?'web revisada':'webs revisadas'}`)+(checked.some(item=>item.scope||item.coverage?.scope)?' según el alcance registrado':''):'Sin revisión de webs registrada';
    const extra=[failed?`${failed} con problemas`:'',pending?`${pending} ${pending===1?'pendiente':'pendientes'}`:'',model.sourceConfigurationError?'Configuración pendiente de comprobar':''].filter(Boolean).join(' · ');
    return {checked,good,failed,pending,summary,lastAt:newest(checked,'checkedAtUtc')?.checkedAtUtc||null,extra};
  }
  function searchModel(request,model){
    if(request.activityResult)return request.activityResult;
    const start=Dates.tableTimestamp(request.startedAt||request.createdAt),end=Dates.tableTimestamp(Workflow.taskAt(request));
    // Legacy requests have proof, but no frozen coverage. Only show retained
    // checks in their date range, never the coverage of a newer search.
    const within=value=>{const at=Dates.tableTimestamp(value);return start!==null&&end!==null&&at!==null&&at>=start&&at<=end;};
    const health=(model.health||[]).filter(item=>within(item.checkedAtUtc));
    return {health,publicSources:health.map(item=>({id:item.sourceId,company:item.company})),portalAccess:Object.fromEntries(Object.entries(model.portalAccess||{}).filter(([,record])=>within(record.checkedAt))),legacy:true};
  }
  function searchTitle(request){
    const count=request.activityResult?.newOfferCount;
    if(Number.isInteger(count)&&count>=0)return `Búsqueda realizada: ${count} ${count===1?'nueva oferta':'nuevas ofertas'}`;
    const text=[request.summary,request.result].filter(Boolean).join(' ');
    const match=text.match(/\b(\d+)\s+(?:ofertas\s+(?:guardadas|preseleccionadas)|preselecciones\b)/i);
    return match?`Búsqueda realizada: ${match[1]} ${Number(match[1])===1?'oferta preseleccionada':'ofertas preseleccionadas'}`:'Búsqueda realizada';
  }
  function completions(model){
    const done=(model.requests||[]).filter(r=>r.type!=='mail'&&r.status==='done'&&(r.summary||r.result||r.activityResult));
    const selected=new Map();
    for(const [index,request] of chronological(done,Workflow.taskAt).entries()){
      const key=request.type==='discovery'?'search:'+(request.id||index):request.type==='send'?'send:'+(request.packageId||request.id||index):request.opportunityId?'job:'+request.opportunityId:'global:'+request.type;
      selected.set(key,request);
    }
    return [...selected.values()].filter(request=>!request.opportunityId||request.type==='send'||!done.some(r=>r.type==='send'&&r.opportunityId===request.opportunityId&&Dates.tableTimestamp(Workflow.taskAt(r))>=Dates.tableTimestamp(Workflow.taskAt(request))));
  }
  function matchesCompletion(item,request){
    if(item.requestId)return item.requestId===request.id&&request.status==='done';
    if(request.type==='send'&&item.packageId&&item.packageId===request.packageId&&item.opportunityId===request.opportunityId&&/^(Envío confirmado|Solicitud enviada)$/.test(item.title||''))return true;
    const at=Dates.tableTimestamp(item.at),end=Dates.tableTimestamp(Workflow.taskAt(request));
    return (item.opportunityId||null)===(request.opportunityId||null)&&at!==null&&end!==null&&Math.abs(at-end)<=1000&&(item.detail===request.result||/^(Encargo|Tarea) terminado$/.test(item.title||''));
  }
  function outcomes(model){
    const done=(model.requests||[]).filter(r=>r.status==='done'&&r.type!=='mail');
    const results=completions(model).filter(r=>['discovery','send','review','change','investigate'].includes(r.type)).map(request=>({at:Workflow.taskAt(request),request}));
    // Keep business outcomes; permissions, saves and internal checks remain in
    // the original history. Matching completions must appear only once.
    const useful=/^(?:Envío confirmado|Solicitud enviada|Respuesta recibida|Respuesta de empresa|Entrevista\b|Oferta recibida|Solicitud lograda|Proceso cerrado|Candidatura rechazada|Rechazo registrado por ti|Seguimiento cerrado por ti|Disponibilidad comprobada|Seguimiento comprobado|Paquete listo para tu decisión|Paquete revisado|Solicitud lista para revisar|Solicitud revisada)\b/i;
    const events=(model.history||[]).filter(item=>useful.test(item.title||'')&&!done.some(request=>matchesCompletion(item,request)));
    const seen=new Set();
    for(const item of chronological(events).reverse()){
      const ready=/^(Paquete|Solicitud)/i.test(item.title||'');
      if(ready&&item.opportunityId&&done.some(r=>r.opportunityId===item.opportunityId&&Dates.tableTimestamp(Workflow.taskAt(r))>=Dates.tableTimestamp(item.at)))continue;
      const key=ready?'ready:'+item.opportunityId:[item.title,item.opportunityId,item.packageId||item.at,item.detail].join('|');
      if(seen.has(key))continue;
      seen.add(key);results.push({at:item.at,event:item});
    }
    return results.sort((a,b)=>(Dates.tableTimestamp(b.at)??-Infinity)-(Dates.tableTimestamp(a.at)??-Infinity));
  }
  function days(items,timeZone='Europe/Madrid'){
    const groups=new Map(),format=new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone});
    for(const item of items){
      const at=Dates.tableTimestamp(item.at);
      // A date without time already identifies its day; never shift it through
      // a timezone or infer a clock time.
      const parts=at===null?{}:Object.fromEntries(format.formatToParts(at).map(part=>[part.type,part.value]));
      const key=/^\d{4}-\d{2}-\d{2}$/.test(item.at||'')?item.at:at===null?'unknown':`${parts.year}-${parts.month}-${parts.day}`;
      if(!groups.has(key))groups.set(key,{key,at:item.at,items:[]});
      groups.get(key).items.push(item);
    }
    return [...groups.values()];
  }
  const work=model=>Workflow.work(model);
  function entries(model){
    const queued=Workflow.work(model).queued.filter(request=>request.type!=='mail').map(request=>({at:Workflow.taskAt(request)||request.createdAt,request}));
    return [...queued,...outcomes(model)].sort((a,b)=>(Dates.tableTimestamp(b.at)??-Infinity)-(Dates.tableTimestamp(a.at)??-Infinity));
  }
  const api={coverage,chronological,newest,searchModel,searchTitle,completions,matchesCompletion,outcomes,entries,days,work,title,caseHistory,grouped,relevant,recent,details};
  if(typeof module!=='undefined')module.exports=api;else window.StubbsJobsActivity=api;
})();
