'use strict';
// Shared decisions for the list, detail and inbox. No DOM or stored mutations.
(() => {
  const Workflow=typeof module!=='undefined'?require('./workflow.js'):window.StubbsJobsWorkflow;
  const Dates=typeof module!=='undefined'?require('./formatting.js'):window.StubbsJobsFormatting;
  const active = job => !job.archivedAt&&job.archiveOutcome!=='achieved'&&!['Cerrada','Descartada','Rechazada','Oferta','Lograda'].includes(job.state);
  const conciseAnswerLabels={
    'Nombre para el formulario':'Nombre','Apellidos para el formulario':'Apellidos',
    'Correo de contacto para la solicitud':'Correo','Teléfono de contacto para la solicitud':'Teléfono',
    'País de residencia para el formulario':'País','Disponibilidad de incorporación para el formulario':'Disponibilidad',
    '¿Has solicitado antes esta oferta o han presentado ya tu perfil al mismo cliente?':'Solicitud o presentación previa',
    'Salario para formularios (€ brutos al año)':'Salario esperado (€ brutos/año)',
    'Salario fijo mínimo anual':'Mínimo fijo (€ brutos/año)',
    'He participado en competiciones de programación o hackathons':'Competiciones de programación o hackathons',
    'Competiciones de programación o hackathons y resultados':'Competiciones o hackathons: detalle y resultados',
    "Respuesta a 'Are you a legally protected status person?' (sin definición adicional)":'Estatus legalmente protegido',
    'Autorizar tratar CV y datos de contacto para selección y conservarlos hasta 365 días':'Autorizo usar mi CV y contacto para selección y conservarlos hasta 365 días',
    'Autorizar tratar CV y contacto para selección con centros fuera de la UE, aunque el aviso no indique plazo de conservación':'Autorizo usar mi CV y contacto con centros fuera de la UE, aunque no indiquen plazo de conservación',
    'Autorizar conservar la respuesta Prefiero no responder en encuestas demográficas':'Autorizo guardar «Prefiero no responder» en encuestas demográficas'
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
    if(sending)return approved(job)?'El agente está enviando la solicitud. Si retiras el permiso, tendrá que comprobar si llegó a enviarse.':'Permiso retirado. En el chat del agente, pídele que pare y compruebe si llegó a enviarse.';
    if((job.requests||[]).some(r=>r.type==='send'&&r.status==='queued')&&approved(job))return 'Envío autorizado, aún no enviado. Pide «Continúa con Stubbs Jobs» en el chat del agente para enviarla.';
    if(job.selection?.selected&&(job.requests||[]).some(r=>r.status==='queued'))return (job.selection.mode==='auto'?'El agente la enviará cuando la tenga lista. ':'Revisarás la solicitud antes de que se envíe. ')+'Pide «Continúa con Stubbs Jobs» en el chat del agente para empezar.';
    if(canChoose(job))return 'Con revisión, apruebas la solicitud antes de enviarla. Con auto-solicitud, el agente la envía sin esperar tu aprobación.';
    return '';
  }
  // Says where the next step happens when it is outside the app.
  function actionPlace(job,current=step(job)){
    if(job.sent||job.historical)return '';
    if(current.action==='recovery')return 'Pega la petición copiada en el chat del agente.';
    if(current.retryRequestId&&current.action==='resolve')return 'Complétalo en la ventana del navegador que usa el agente. Después pulsa el botón y pide «Continúa con Stubbs Jobs» en su chat.';
    if(current.retryRequestId)return 'Después, el agente lo intentará de nuevo cuando le pidas «Continúa con Stubbs Jobs» en su chat.';
    return '';
  }
  const approved = job => job.packages.some(p => p.isCurrent && p.approvedAt && !p.revokedAt);
  // Personalized installations use the viewer's own timezone and describe the mode
  // condition against their saved preference; the original edition keeps Spain.
  let personalizedView = false;
  const configure = ({personalized=false}={}) => { personalizedView = Boolean(personalized); };
  const offerMode = (job,unknown='Sin concretar') => (personalizedView
    ? {Sí:'Cumple tu modalidad',No:'No cumple tu modalidad',Contradicción:'Datos contradictorios'}
    : {Sí:'Remoto desde España',No:'No remoto desde España',Contradicción:'Datos contradictorios'})[job.conditions?.['Remoto España']]||unknown;
  const day = (at = new Date()) => new Intl.DateTimeFormat('sv-SE', personalizedView ? {} : {timeZone:'Europe/Madrid'}).format(at);
  const snoozed = (model, key, at = new Date()) => new Date(model.snoozes[key] || 0) > at;
  function flowStage(job) {
    if (job.historical || !active(job)) return 'historial';
    if (job.sent || ['Entrevista','Oferta'].includes(job.state)) return 'seguir';
    return job.selection?.selected ? 'solicitar' : 'elegir';
  }
  const offerStates=Object.freeze([
    ['descartadas','Descartada','archive'],['sin-elegir','Por decidir','choice'],['preparacion','En preparación','file'],
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
  // Resumen shows four totals: every application sent and how those ended.
  // Closed, rejected and achieved reuse the Ofertas states, names and colours.
  const outcomeKeys=['seguimiento','cerradas','rechazadas','logradas'];
  function stateCounts(jobs,at=Date.now()){
    const counts={enviadas:0,cerradas:0,rechazadas:0,logradas:0};
    for(const job of jobs){
      const key=offerState(job,at).key;
      if(job.sent||outcomeKeys.includes(key))counts.enviadas++;
      if(key in counts)counts[key]++;
    }
    return [
      {key:'enviadas',state:'seguimiento',filter:'todas',label:'Enviadas',icon:'send',note:'Solicitudes enviadas en total'},
      {...stateByKey.cerradas,state:'cerradas',filter:'cerradas',label:'Cerradas',note:'Procesos terminados sin respuesta final'},
      {...stateByKey.rechazadas,state:'rechazadas',filter:'rechazadas',label:'Rechazadas',note:'La empresa no siguió adelante'},
      {...stateByKey.logradas,state:'logradas',filter:'logradas',label:'Logradas',note:'Te han ofrecido el puesto'}
    ].map(stat=>({...stat,value:counts[stat.key]}));
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
    // The agent cannot continue alone: the person may ask for another attempt (or discard the offer in Más acciones).
    if(s.warning&&r?.actionOwner==='agent')return {...s,owner:'agent',detail:r.summary||'El agente no pudo continuar.',cta:'Ver ficha',action:'open',
      retryRequestId:r.type!=='send'&&Workflow.task(r).canRetry?r.id:null};
    // After completing a portal step in the browser (login, CAPTCHA), the person can put the
    // same task back in the queue; the agent still checks the portal before repeating anything.
    if(s.warning)return {...s,owner:'you',detail:r?.summary||job.next||'El agente necesita un dato o un acceso para continuar.',cta:({contact:'Indicar contacto',access:'Explicar el acceso',answers:'Responder',decision:'Decidir',other:'Responder al agente'})[r?.need]||'Responder al agente',action:'resolve',
      retryRequestId:r&&r.type!=='send'&&r.need==='access'&&Workflow.task(r).canRetry?r.id:null};
    if(s.blockedPending)return {...s,detail:job.requests.some(r=>r.type==='change'&&r.status==='running')?'El agente está revisando tu aclaración.':'Tu aclaración está guardada. Pide «Continúa con Stubbs Jobs» en el chat del agente para que la revise.',cta:null};
    if(s.pendingChange)return {...s,detail:'Cambiaron tu perfil o esta solicitud. El agente debe revisarlos antes de que autorices el envío.',cta:null};
    if(!job.sent&&!job.missing.length&&!approved(job)&&s.owner==='you')return {...s,detail:'La solicitud está lista. Revísala y autoriza el envío.',cta:'Revisar solicitud',action:'review'};
    return {...s,detail:job.sent?(job.sent.reportedBy==='user'?'Enviada por ti. Esperando novedades.':'Envío confirmado. Esperando novedades.'):s.label==='Cambios recibidos'?'Tu petición está guardada. Pide «Continúa con Stubbs Jobs» en el chat del agente.':s.label==='Revisando tus cambios'?'El agente está atendiendo tu petición.':s.label==='Preparando'?'El agente está preparando la solicitud.':approved(job)?'Envío autorizado. El agente aún no lo ha confirmado.':s.label==='Tarea en cola'?'Tarea guardada. Pide «Continúa con Stubbs Jobs» en el chat del agente.':job.selection?.selected?job.selection.mode==='auto'?'El agente preparará la solicitud y la enviará cuando esté lista.':'El agente preparará la solicitud para que la revises.':canChoose(job)?'Puedes solicitarla: el agente preparará la solicitud.':'El agente debe comprobar las condiciones de esta oferta.',cta:null};
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
      if(request)return Workflow.task(request).detail||'Revisa el último paso en el chat del agente.';
      if(job.state==='Enviada'&&!job.sent)return 'No consta una confirmación del envío. El agente debe comprobar qué ocurrió antes de repetir la solicitud.';
      if(['Pendiente de ti','Pendiente de Usuario'].includes(job.state))return job.selection?.selected?
        'Hay una duda pendiente. Resuélvela en el chat del agente para seguir con la solicitud.':
        'Antes de elegirla, revisa el encaje con el agente en su chat.';
      return job.integrityError?'Hay un problema con un documento: lo verás abajo.':'El agente debe revisar lo pendiente antes de continuar.';
    }
    if(state.key==='seguimiento'){
      if(job.state==='Entrevista')return 'Entrevista: '+(job.next||'consulta el siguiente paso con la empresa.');
      if(job.state==='Oferta')return 'Oferta recibida: '+(job.next||'revisa la propuesta de la empresa.');
      return job.lifecycle?.label||'Sin respuesta conocida de la empresa.';
    }
    return '';
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
  // The person's own send: dialog choices and the writer operation. It records what
  // she declares, never a portal receipt, and grants no permission or work.
  function userSentChoices(job,library=[]){
    const report=job?.selfReport;
    if(!report?.available||job.sent)return null;
    const options=[];
    if(report.packageCv)options.push({value:'package:'+report.packageCv.packageId,label:'CV preparado para esta oferta · '+report.packageCv.name,
      cv:{source:'package',packageId:report.packageCv.packageId}});
    for(const cv of library||[])if(cv?.path&&cv.available!==false&&/^[a-f0-9]{64}$/.test(cv.fingerprint||''))
      options.push({value:'library:'+cv.fingerprint+':'+cv.path,label:'Currículums · '+cv.name,cv:{source:'library',path:cv.path,fingerprint:cv.fingerprint}});
    const warnings=[];
    if(report.uncertainAttempts)warnings.push('El agente empezó a enviar esta solicitud y no consta si llegó. Comprueba en el portal que solo figure una solicitud tuya.');
    if(report.pendingSends)warnings.push('Se cancelará el envío pendiente del agente y se retirará su permiso.');
    if(report.historical?.length)warnings.push('Ya consta una candidatura anterior a esta vacante. Regístralo solo si es una solicitud nueva.');
    return {options,warnings,reapplication:!!report.historical?.length,conciliation:report.conciliation};
  }
  function userSentOperation(job,choices,values,at=Date.now()){
    const option=choices?.options.find(item=>item.value===values.cv);
    if(!option)return {error:'Elige el CV que enviaste.'};
    const sentAt=Dates.zonedInstant(values.sentAt);
    if(!sentAt)return {error:'Indica la fecha y hora del envío.'};
    if(Date.parse(sentAt)>at+5*60000)return {error:'La fecha del envío no puede ser futura.'};
    if(values.duplicatesChecked!==true)return {error:'Confirma que es tu única solicitud a esta vacante.'};
    if(choices.reapplication&&values.reapplication!==true)return {error:'Confirma que es una solicitud nueva, distinta de la anterior.'};
    const note=String(values.note||'').trim();
    return {operation:{kind:'ui-user-sent',opportunityId:job.id,sentAt,cv:option.cv,...(note?{note}:{}),duplicatesChecked:true,
      ...(choices.reapplication?{reapplication:true}:{}),expected:choices.conciliation}};
  }
  const api={actionPlace,stateCounts,userSentChoices,userSentOperation,configure,active,approved,offerMode,day,snoozed,flowStage,offerStates,offerState,canChoose,status,inbox,reviewValid,decisions,progress,archive,step,detailMessage,rank,answerTitle,presentationUsage,presentationVisible,formAnswers,nextAction};
  if (typeof module!=='undefined') module.exports=api;
  else window.StubbsJobsUI=api;
})();
