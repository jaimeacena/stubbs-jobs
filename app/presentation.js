'use strict';
// Shared decisions for the list, detail and inbox. No DOM or stored mutations.
(() => {
  const Workflow=typeof module!=='undefined'?require('./workflow.js'):window.StubbsJobsWorkflow;
  const active = job => !job.archivedAt&&job.archiveOutcome!=='achieved'&&!['Cerrada','Descartada','Rechazada','Oferta','Lograda'].includes(job.state);
  const conciseAnswerLabels={
    'Nombre para el formulario':'Nombre','Apellidos para el formulario':'Apellidos',
    'Correo de contacto para la solicitud':'Correo','Teléfono de contacto para la solicitud':'Teléfono',
    'País de residencia para el formulario':'País','Disponibilidad de incorporación para el formulario':'Disponibilidad',
    '¿Has solicitado antes esta oferta o han presentado ya tu perfil al mismo cliente?':'Solicitud o presentación previa',
    'Salario para formularios (€ brutos al año)':'Salario esperado (€ brutos/año)',
    'Salario fijo mínimo anual':'Mínimo fijo (€ brutos/año)'
  };
  const answerTitle=label=>conciseAnswerLabels[label]||label;
  const presentationVisible=material=>['form','email'].includes(material?.messageUsage)&&!!material?.message?.trim();
  function presentationUsage(material){
    return {
      form:'Se utiliza en el campo de presentación del formulario.',
      email:'Se utiliza en el cuerpo del correo de solicitud.',
      unused:'Este formulario no pide presentación. Este borrador no se adjunta ni se envía por correo.'
    }[material.messageUsage]||'Borrador opcional. El agente debe comprobar si el destino admite este texto antes de utilizarlo.';
  }
  function formAnswers(material){
    if(!Array.isArray(material.formAnswerKeys))return {};
    return Object.fromEntries(material.formAnswerKeys.filter(k=>k!=='minimumFixed'&&Object.hasOwn(material.answers||{},k)).map(k=>[k,material.answers[k]]));
  }
  function nextAction(job){
    if(job.sent)return '';
    const sending=(job.requests||[]).some(r=>r.type==='send'&&r.status==='running');
    if(sending)return approved(job)?'El agente tiene un envío iniciado. Puedes retirar el permiso; después deberá comprobar su resultado.':'Permiso retirado. Pide al agente que detenga el paso en curso y compruebe si llegó a enviarse.';
    if((job.requests||[]).some(r=>r.type==='send'&&r.status==='queued')&&approved(job))return 'Envío autorizado para esta versión. El envío aún no está confirmado. Pide «Continúa con Stubbs Jobs» en el chat del agente para iniciarlo.';
    if(job.selection?.selected&&(job.requests||[]).some(r=>r.status==='queued'))return (job.selection.mode==='auto'?'Permites enviar esta oferta tras revisar el paquete exacto. ':'Tendrás que aprobar el paquete final antes del envío. ')+'La tarea está guardada. Pide «Continúa con Stubbs Jobs» en el chat del agente para iniciarla.';
    if(canChoose(job))return 'Con revisión: apruebas el paquete final. Automática: permites enviar esta oferta tras las comprobaciones. Después de elegir, continúa en el chat del agente.';
    return '';
  }
  const approved = job => job.packages.some(p => p.isCurrent && p.approvedAt && !p.revokedAt);
  const offerMode = (job,unknown='Sin concretar') => ({Sí:'Remoto desde España',No:'No remoto desde España',Contradicción:'Datos contradictorios'})[job.conditions?.['Remoto España']]||unknown;
  const day = (at = new Date()) => new Intl.DateTimeFormat('sv-SE', {timeZone:'Europe/Madrid'}).format(at);
  const snoozed = (model, key, at = new Date()) => new Date(model.snoozes[key] || 0) > at;
  function flowStage(job) {
    if (job.historical || !active(job)) return 'historial';
    if (job.sent || ['Entrevista','Oferta'].includes(job.state)) return 'seguir';
    return job.selection?.selected ? 'solicitar' : 'elegir';
  }
  const offerStates=Object.freeze([
    ['descartadas','Descartada','archive'],['sin-elegir','Por decidir','question'],['preparacion','En preparación','file'],
    ['atencion','Por atender','bell'],['enviando','Enviando','send'],
    ['seguimiento','Siguiendo','check'],['cerradas','Cerrada','lock'],['rechazadas','Rechazada','close'],['logradas','Lograda','trophy']
  ].map(([key,label,icon])=>Object.freeze({key,label,icon})));
  const stateByKey=Object.fromEntries(offerStates.map(state=>[state.key,state]));
  // One display category, derived from the existing facts. It never grants permission
  // or substitutes for the operational step, task ownership or a delivery receipt.
  function offerState(job,at=Date.now()){
    const tasks=(job.requests||[]).filter(request=>!request.interpretationOnly).map(request=>({request,task:Workflow.task(request,at)})).filter(({task})=>!task.superseded);
    const deliveryProblem=!job.sent&&tasks.some(({request,task})=>request.type==='send'&&
      (task.delivery||task.interruptionUnconfirmed||task.stale));
    if(deliveryProblem)return stateByKey.atencion;
    if(job.archiveOutcome==='achieved'||['Oferta','Lograda'].includes(job.state))return stateByKey.logradas;
    if(job.archiveOutcome==='closed'||job.state==='Cerrada')return stateByKey.cerradas;
    if(job.state==='Rechazada'||job.archiveOutcome==='rejected')return stateByKey.rechazadas;
    if(!active(job)&&job.sent)return stateByKey.cerradas;
    if(!job.sent&&job.minimums?.canApply===false)return stateByKey.descartadas;
    if(job.historical||!active(job))return stateByKey.descartadas;
    if(tasks.some(({request,task})=>task.stale||['blocked','interrupted'].includes(request.status))||
      !job.sent&&(job.integrityError||job.pendingChange&&(!job.minimums||job.selection?.selected)||(job.questions||[]).length))return stateByKey.atencion;
    if(!job.sent&&tasks.some(({request})=>request.type==='send'&&request.status==='running'))return stateByKey.enviando;
    if(['Pendiente de ti','Pendiente de Usuario'].includes(job.state)&&!(job.minimums?.canApply&&!job.selection?.selected))return stateByKey.atencion;
    if(job.sent||['Pendiente de empresa','Entrevista','Oferta'].includes(job.state))return stateByKey.seguimiento;
    // A stored "Enviada" without its receipt is not evidence of delivery.
    if(job.state==='Enviada')return stateByKey.atencion;
    if(job.selection?.selected){
      const waiting=tasks.some(({request})=>['queued','running'].includes(request.status));
      if(!waiting&&!(job.missing||[]).length&&!approved(job))return stateByKey.atencion;
      return stateByKey.preparacion;
    }
    return stateByKey['sin-elegir'];
  }
  function canChoose(job) {
    if (flowStage(job)!=='elegir' || !['Sí','Sí, aclarar'].includes(job.apply)) return false;
    if(job.minimums?.canApply===false)return false;
    return !job.requests.some(r=>!r.interpretationOnly&&!Workflow.task(r).superseded&&
      (['queued','running','blocked','interrupted'].includes(r.status)&&!(r.type==='investigate'&&r.status==='queued')||Workflow.task(r).delivery));
  }

  function status(job) {
    if(job.historical)return {label:'Sin seguimiento reciente',owner:'closed',action:'Ver ficha'};
    const requests=job.requests.filter(r=>!r.interpretationOnly&&!Workflow.task(r).superseded),currentTask=Workflow.nextRequest(requests);
    const task=currentTask&&Workflow.task(currentTask);
    if(task?.interruptionUnconfirmed)return {label:task.label,owner:'agent',action:'Ver ficha',unconfirmed:true,requestId:currentTask.id};
    if(!job.sent&&task?.delivery)return {label:task.deliveryRecheckRequired?'No enviado · comprobación antigua':task.cancelledStarted?'Permiso retirado · envío sin confirmar':task.deliveryChecked?'Envío pendiente de continuar':'Envío sin confirmar',owner:'you',action:'Comprobar envío',deliveryUnknown:!task.deliveryRecheckRequired,deliveryRecheckRequired:task.deliveryRecheckRequired,deliveryChecked:task.deliveryChecked,requestId:currentTask.id};
    if (!active(job)) return {label:job.state, owner:'closed', action:'Ver ficha'};
    if (!job.selection?.selected && job.apply==='No') return {label:'No encaja con tus condiciones',owner:'closed',action:'Ver motivo'};
    if (['Entrevista','Oferta'].includes(job.state)) return {label:job.state, owner:'you', action:'Ver siguiente paso'};
    if (job.sent) return {label:'Enviada · esperando respuesta', owner:'company', action:'Ver ficha'};
    if(task?.stale)return {label:task.label,owner:'agent',action:'Ver ficha',unconfirmed:true,requestId:currentTask.id};
    if(currentTask?.type==='send'&&currentTask.status==='running')return {label:'Enviando',owner:'agent',action:'Ver ficha'};
    if (job.questions.length) return {label:'Faltan tus respuestas', owner:'you', action:'Responder'};
    const change=requests.find(r=>r.type==='change'&&['queued','running'].includes(r.status));
    if(change){
      const blocked=requests.some(r=>r.type!=='change'&&['blocked','interrupted'].includes(r.status));
      return {label:blocked?(change.status==='running'?'Revisando aclaración · falta comprobación':'Aclaración recibida · falta comprobación'):(change.status==='running'?'Revisando tus cambios':'Cambios recibidos'),owner:'agent',action:'Ver ficha',blockedPending:blocked};
    }
    const interrupted = requests.find(r => ['blocked','interrupted'].includes(r.status));
    if (interrupted) return {label:interrupted.actionOwner==='agent'?'Pendiente del agente':'Por atender', owner:'agent', action:'Ver qué falta', warning:true};
    const running = requests.find(r => r.status==='running');
    if (running) return {label:running.type==='send'?'Enviando':'Preparando', owner:'agent', action:'Ver ficha'};
    if (job.pendingChange) return {label:'Cambios pendientes de comprobar', owner:'agent', action:'Ver ficha', pendingChange:true};
    if (approved(job)) return {label:'Autorizada · aún sin enviar', owner:'agent', action:'Ver ficha'};
    if (requests.some(r=>r.status==='queued')) return {label:'Tarea en cola', owner:'agent', action:'Ver ficha'};
    if (!job.selection?.selected) return {label:['Sí','Sí, aclarar'].includes(job.apply)?'Por decidir':'Por comprobar', owner:'agent', action:'Ver ficha'};
    if (!job.missing.length) return {label:'Lista para revisar', owner:'you', action:'Revisar solicitud'};
    if (job.selection?.selected) return {label:'Oferta seleccionada', owner:'agent', action:'Ver ficha'};
    return {label:'Por comprobar', owner:'agent', action:'Ver ficha'};
  }
  function archive(model){
    const keys=new Set(model.opportunities.map(j=>j.canonicalKey).filter(Boolean));
    return (model.historical||[]).filter(h=>h.category!=='No laboral'&&!keys.has(h.canonicalKey)).map(h=>({...h,id:'historical:'+h.id,historical:true,packages:[],requests:[],questions:[],missing:[],originalState:h.state}));
  }
  function step(job){
    const s=status(job),r=job.requests.find(r=>!Workflow.task(r).superseded&&['blocked','interrupted'].includes(r.status));
    if(job.historical)return {...s,detail:'Último estado registrado: '+job.originalState,cta:null};
    if(s.unconfirmed||s.deliveryUnknown||s.deliveryRecheckRequired){
      const request=job.requests.find(r=>r.id===s.requestId),task=Workflow.task(request);
      return {...s,detail:task.detail,cta:s.deliveryRecheckRequired?'Copiar petición para comprobar de nuevo':s.deliveryChecked?'Copiar petición para continuar':s.deliveryUnknown?'Copiar petición de comprobación':'Copiar petición para retomar',action:'recovery',lastAt:task.lastAt};
    }
    if(!active(job))return {...s,detail:'Proceso finalizado',cta:null};
    if(!job.selection?.selected && job.apply==='No')return {...s,detail:'La oferta no cumple una condición de tu búsqueda. Abre la ficha para ver qué se comprobó.',cta:'Ver motivo',action:'open'};
    if(['Entrevista','Oferta'].includes(job.state))return {...s,detail:job.next||'Consulta el siguiente paso',cta:'Ver siguiente paso',action:'open'};
    if(job.questions.length&&!job.sent)return {...s,detail:job.questions.map(q=>q.label).join(' · '),cta:'Responder',action:'answers'};
    if(s.warning&&r?.actionOwner==='agent')return {...s,owner:'agent',detail:r.summary||'El agente debe comprobar lo pendiente.',cta:'Ver ficha',action:'open'};
    if(s.warning)return {...s,owner:'you',detail:r?.summary||job.next||'El agente necesita un dato o acceso para continuar.',cta:({contact:'Aclarar contacto',access:'Aclarar acceso',answers:'Aportar respuesta',decision:'Aclarar decisión',other:'Ver qué falta'})[r?.need]||'Ver qué falta',action:'resolve'};
    if(s.blockedPending)return {...s,detail:(job.requests.some(r=>r.type==='change'&&r.status==='running')?'La IA está comprobando tu aclaración.':'Tu aclaración está en cola para la IA.')+' El bloqueo sigue vigente hasta que se compruebe.',cta:null};
    if(s.pendingChange)return {...s,detail:'El agente debe comprobar los cambios del perfil o de esta solicitud antes de autorizar el envío.',cta:null};
    if(!job.sent&&!job.missing.length&&!approved(job)&&s.owner==='you')return {...s,detail:'Solicitud revisada. Falta tu permiso de envío.',cta:'Revisar solicitud',action:'review'};
    return {...s,detail:job.sent?'Envío confirmado. Esperando novedades.':s.label==='Cambios recibidos'?'Tu petición está guardada para la IA.':s.label==='Revisando tus cambios'?'La IA está atendiendo tu petición.':s.label==='Preparando'?'La IA está comprobando los documentos y la oferta.':approved(job)?'La IA tiene permiso para enviar esta solicitud. El envío aún no está confirmado.':s.label==='Tarea en cola'?'El agente aún no ha comenzado esta tarea.':job.selection?.selected?job.selection.mode==='auto'?'Has seleccionado esta oferta. La IA preparará la solicitud y podrá continuar con su envío tras comprobarla.':'Has seleccionado esta oferta. La IA preparará la solicitud.':canChoose(job)?'Puedes seleccionar esta oferta para que la IA prepare la solicitud.':'El agente debe comprobar las condiciones de esta oferta.',cta:null};
  }
  function rank(job,at=new Date()){
    const s=step(job);
    if(['Entrevista','Oferta'].includes(job.state))return 0;
    if(job.externalDeadline&&job.externalDeadline.slice(0,10)<=day(at)&&active(job))return 0;
    if(s.action==='answers')return 1;
    if(s.action==='review')return 2;
    if(s.owner==='you')return 3;
    if(job.requests.some(r=>r.status==='running'))return 4;
    return job.sent?6:5;
  }

  // Only explain a concrete next step or an unresolved operational boundary here.
  // Fit and offer conditions have their own places in the detail view.
  function detailMessage(job,current=step(job)){
    if(job.historical)return '';
    const state=offerState(job);
    if(['descartadas','rechazadas','cerradas','logradas'].includes(state.key))return job.lifecycle?.closure?.label||job.archiveReason||(state.key==='logradas'?'La empresa te ofrece el puesto.':'')||(job.minimums?.violations||[]).map(v=>v.reason).join(' ')||({Rechazada:'Candidatura rechazada.',Descartada:'Esta oferta se ha descartado.',Cerrada:'El proceso ha finalizado.'})[job.state]||(job.archivedAt?(job.sent?'Seguimiento cerrado por ti.':'Oferta descartada por ti.'):'');
    if(current.unconfirmed||current.deliveryUnknown||current.deliveryRecheckRequired||
      current.warning||current.blockedPending||current.pendingChange||
      current.action==='answers'||current.action==='review')return current.detail;
    if(state.key==='atencion'){
      const request=(job.requests||[]).find(r=>!Workflow.task(r).superseded&&
        (Workflow.task(r).stale||Workflow.task(r).delivery||['blocked','interrupted'].includes(r.status)));
      if(request)return Workflow.task(request).detail||'Revisa el último paso con el agente para continuar.';
      if(job.state==='Enviada'&&!job.sent)return 'No consta una confirmación del envío. El agente debe comprobar qué ocurrió antes de repetir la solicitud.';
      if(['Pendiente de ti','Pendiente de Usuario'].includes(job.state))return job.selection?.selected?
        'Hay una aclaración pendiente. Revísala con el agente para continuar la solicitud.':
        'Antes de elegir esta oferta, revisa su encaje con el agente.';
      return job.integrityError?'Revisa el problema del documento indicado abajo.':'El agente debe comprobar lo pendiente antes de continuar.';
    }
    if(state.key==='seguimiento'){
      if(job.state==='Entrevista')return 'Entrevista: '+(job.next||'consulta el siguiente paso con la empresa.');
      if(job.state==='Oferta')return 'Oferta recibida: '+(job.next||'revisa la propuesta de la empresa.');
      return job.lifecycle?.label||'Sin respuesta conocida de la empresa.';
    }
    return '';
  }

  // The agent orders the checked assessment's doubts; this view adds no facts or work.
  function nextCheck(job){
    if(!job.assessment?.isCurrent||flowStage(job)!=='elegir'||job.questions?.length||
      job.apply==='No'||(job.requests||[]).some(request=>!Workflow.task(request).superseded&&
        (['queued','running','blocked','interrupted'].includes(request.status)||Workflow.task(request).delivery)))return '';
    return (job.assessment.unknowns||[]).find(text=>typeof text==='string'&&text.trim())?.replace(/\s+/g,' ').trim()||'';
  }
  function recommendation(model,at=new Date()){
    const choices=model.opportunities.filter(job=>nextCheck(job)&&!job.integrityError&&!snoozed(model,job.id,at));
    if(!choices.length)return null;
    const work=Workflow.work(model);
    if(work.busy||work.blocked.length||work.failure||decisions(model,at).length)return null;
    const urgent=job=>job.externalDeadline&&job.externalDeadline.slice(0,10)<=day(at)?0:1;
    const priority=job=>({A:0,B:1,C:2})[job.priority]??3;
    return choices.sort((a,b)=>urgent(a)-urgent(b)||priority(a)-priority(b)||
      (a.externalDeadline||'9999').localeCompare(b.externalDeadline||'9999')||a.id.localeCompare(b.id))[0]||null;
  }

  function inbox(model, at = new Date()) {
    const items=[], jobs=model.opportunities.filter(active), today=day(at);
    const sourceErrors=(model.health||[]).filter(h=>h.status!=='ok');
    if(sourceErrors.length)items.push({kind:'sources',rank:1,sources:sourceErrors});
    const questions=jobs.filter(j=>!j.sent && j.questions.length && !snoozed(model,j.id,at));
    if (questions.length && !snoozed(model,'profile',at)) {
      items.push({kind:'profile',rank:3,ids:questions.map(j=>j.id),keys:[...new Set(questions.flatMap(j=>j.questions.map(q=>q.key)))]});
    }
    for (const j of jobs) {
      const urgent=j.due && j.due.slice(0,10)<=today;
      // A reminder never hides an interview, offer or imminent target date.
      if (snoozed(model,j.id,at) && !urgent && !['Entrevista','Oferta'].includes(j.state)) continue;
      const s=status(j);
      if (['Entrevista','Oferta'].includes(j.state)) items.push({kind:'milestone',rank:0,id:j.id});
      else if (s.warning) items.push({kind:'blocked',rank:1,id:j.id});
      else if (urgent) items.push({kind:'due',rank:2,id:j.id,overdue:j.due.slice(0,10)<today});
      else if (s.label==='Lista para revisar') items.push({kind:'review',rank:4,id:j.id});
    }
    // Standalone blocked work also matters (discovery has no candidature).
    for (const r of model.requests.filter(r=>!r.opportunityId && ['blocked','interrupted'].includes(r.status))) {
      items.push({kind:'request',rank:1,request:r});
    }
    return items.sort((a,b)=>a.rank-b.rank || (model.opportunities.find(j=>j.id===a.id)?.due||'').localeCompare(model.opportunities.find(j=>j.id===b.id)?.due||''));
  }

  function reviewValid(snapshot,current) {
    return !!snapshot && !!current && active(current) && !!current.selection?.selected && !current.sent &&
      !current.integrityError && !current.pendingChange && !(current.requests||[]).some(r=>r.type==='change'&&!['done','cancelled'].includes(r.status)) &&
      !(current.requests||[]).some(r=>r.type==='send'&&(r.status==='running'||Workflow.task(r).uncertain||Workflow.task(r).deliveryRecheckRequired)) &&
      snapshot.fingerprint===current.fingerprint && !current.missing.length &&
      current.packages.some(p=>p.id===snapshot.fingerprint) && !approved(current);
  }
  function decisions(model, at=new Date()) {
    // Routine dates and preparation belong to the agent, not the user's inbox.
    const items=inbox(model,at).filter(x=>['profile','review','milestone'].includes(x.kind) ||
      x.kind==='due' && !model.opportunities.find(j=>j.id===x.id).questions.length && status(model.opportunities.find(j=>j.id===x.id)).owner==='you');
    if(inbox(model,at).some(x=>['blocked','request','sources'].includes(x.kind)))items.push({kind:'help',rank:5});
    return items;
  }
  function progress(model) {
    const work=Workflow.work(model),pending=work.queued.length;
    const running=work.busy;
    const sources=model.health||[];
    const checks={sources:{total:model.publicSources?.length||sources.length,ok:sources.filter(h=>h.status==='ok').length,attemptAt:sources.map(h=>h.checkedAtUtc).filter(Boolean).sort().at(-1)||null}};
    return {busy:work.busy,label:work.unconfirmed.length||work.blocked.some(r=>Workflow.task(r).interruptionUnconfirmed)?'Actividad pendiente de confirmar':work.starting?'Iniciando el agente…':running?'El agente está trabajando':pending?'Hay tareas en cola':'Sin trabajo en curso',checks};
  }
  const api={active,approved,offerMode,day,snoozed,flowStage,offerStates,offerState,canChoose,status,inbox,reviewValid,decisions,progress,archive,step,detailMessage,rank,nextCheck,recommendation,answerTitle,presentationUsage,presentationVisible,formAnswers,nextAction};
  if (typeof module!=='undefined') module.exports=api;
  else window.StubbsJobsUI=api;
})();
