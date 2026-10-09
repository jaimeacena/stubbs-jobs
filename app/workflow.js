'use strict';
// Read-only task decisions shared by Resumen, offer cards and agent progress.
(() => {
  const Dates=typeof module!=='undefined'?require('./formatting.js'):window.StubbsJobsFormatting;
  const pending=new Set(['queued','running','blocked','interrupted']);
  const names={discovery:'Buscar ofertas',review:'Comprobar solicitud',investigate:'Comprobar oferta',change:'Aplicar tus cambios',send:'Enviar solicitud'};
  const taskAt=request=>request.activityAt||request.updatedAt;
  function task(request,at=Date.now()){
    const lastAt=taskAt(request)||request.startedAt,stamp=Dates.tableTimestamp(lastAt);
    const supersededByRequestId=request.type==='send'&&request.status!=='running'&&typeof request.supersededByRequestId==='string'&&request.supersededByRequestId.trim()?request.supersededByRequestId:null;
    if(supersededByRequestId)return {state:'superseded',label:'Intento anterior comprobado',detail:'El portal confirmó que este intento no se envió. Su comprobación se utilizó en un intento posterior; consulta ese intento para conocer el resultado actual.',superseded:true,supersededByRequestId,stale:false,interruptionUnconfirmed:false,uncertain:false,delivery:false,cancelledStarted:request.status==='cancelled',deliveryAbsent:true,deliveryDelivered:false,checkedUnknown:false,deliveryChecked:false,deliveryRecheckRequired:false,lastAt:stamp===null?null:lastAt,canRetry:false,canCancel:false};
    const interruptionUnconfirmed=request.status==='interrupted'&&(request.interruptionUnconfirmed===true||request.result==='No se ha recibido actividad durante dos horas. Revisar antes de reintentar.');
    const stale=interruptionUnconfirmed||request.status==='running'&&(stamp===null||!String(lastAt).includes('T')||stamp>at+300000||at-stamp>7200000);
    const check=request.deliveryCheck,checkedAt=Dates.tableTimestamp(check?.at);
    const recordedCheck=Boolean(check&&typeof request.packageId==='string'&&request.packageId.trim()&&check.packageId===request.packageId&&typeof check.proof==='string'&&check.proof.trim()&&checkedAt!==null&&String(check.at).includes('T')&&checkedAt<=at+300000);
    const startedAt=Dates.tableTimestamp(request.startedAt);
    const cancelledStarted=request.type==='send'&&request.status==='cancelled'&&typeof request.packageId==='string'&&Boolean(request.packageId.trim())&&startedAt!==null&&String(request.startedAt).includes('T')&&startedAt<=at+300000;
    const cancelledChecked=cancelledStarted&&recordedCheck&&checkedAt>=startedAt-300000;
    const deliveryAbsent=cancelledChecked&&check.outcome==='not_sent',deliveryDelivered=cancelledChecked&&check.outcome==='sent';
    const cancelledResolved=deliveryAbsent||deliveryDelivered;
    const deliveryRecheckRequired=Boolean(deliveryAbsent&&(request.deliveryRecheckRequired===true||request.deliveryRecheckRequired!==false&&at-checkedAt>3600000));
    const deliveryChecked=!interruptionUnconfirmed&&request.type==='send'&&request.status!=='cancelled'&&recordedCheck&&check.outcome==='not_sent'&&at-checkedAt<=3600000;
    const delivery=!interruptionUnconfirmed&&request.type==='send'&&(['blocked','interrupted'].includes(request.status)||cancelledStarted&&(!cancelledResolved||deliveryRecheckRequired));
    const uncertain=request.type==='send'&&(['running','blocked','interrupted'].includes(request.status)||cancelledStarted&&!cancelledResolved)&&!deliveryChecked;
    const checkedUnknown=Boolean(recordedCheck&&(!cancelledStarted||cancelledChecked)&&check.outcome==='unknown');
    const state=stale?'unconfirmed':request.status;
    const label=({queued:'Pendiente de iniciar',running:request.type==='send'?'Envío en curso':'Trabajo en curso',blocked:'Necesita ayuda',interrupted:'Trabajo interrumpido',unconfirmed:'Actividad pendiente de confirmar',done:'Trabajo terminado',cancelled:'Cancelado'})[state]||'Estado por comprobar';
    const detail=interruptionUnconfirmed?'La interrupción se anotó por falta de actividad, sin confirmar que el agente se hubiera detenido. Confirma primero la detención real y conserva su propietario.':cancelledStarted?deliveryDelivered?'El envío original está confirmado. El permiso sigue retirado y el formulario no se repitió.':deliveryRecheckRequired?'El portal dejó comprobado que no se envió. Esa comprobación es antigua: antes de otro envío autorizado hay que comprobar de nuevo el portal. La tarea sigue cancelada y el permiso retirado.':deliveryAbsent?'El permiso sigue retirado. El portal dejó comprobado que no se envió; la tarea permanece cancelada.':checkedUnknown?'El permiso sigue retirado y el portal no permitió confirmar el resultado. Comprueba de nuevo solo si hay una prueba nueva; no repitas el formulario.':'El permiso está retirado, pero el envío ya había comenzado. Comprobar lo que ocurrió no permite volver a enviarlo.':stale?'Vuelve al chat del agente para comprobar dónde quedó. La última actividad registrada no confirma que siga trabajando.':deliveryChecked?'El portal confirma que no se envió. El agente debe revalidar el paquete y el permiso antes de continuar.':uncertain&&request.status!=='running'?checkedUnknown?'El portal no permitió confirmar el envío. Conserva el bloqueo y comprueba de nuevo solo si hay una prueba nueva.':'El envío quedó sin confirmar. El agente debe comprobar el portal antes de repetir cualquier acción.':request.status==='queued'?'Guardado para el agente. Pega la petición en su chat; todavía no ha empezado.':request.status==='blocked'?(request.summary||'Abre el detalle para consultar el paso pendiente.'):request.status==='interrupted'?'Vuelve al chat del agente y comprueba el último paso antes de continuar.':request.summary||'';
    return {state,label:deliveryRecheckRequired?'No enviado · comprobación antigua':cancelledStarted&&uncertain?'Permiso retirado · envío sin confirmar':deliveryDelivered?'Envío original confirmado · permiso retirado':deliveryChecked?'Envío pendiente de continuar':label,detail,superseded:false,stale,interruptionUnconfirmed,uncertain,delivery,cancelledStarted,deliveryAbsent:Boolean(deliveryAbsent),deliveryDelivered:Boolean(deliveryDelivered),checkedUnknown,deliveryChecked:Boolean(deliveryChecked),deliveryRecheckRequired,lastAt:stamp===null?null:lastAt,canRetry:!interruptionUnconfirmed&&['blocked','interrupted'].includes(request.status)&&(request.type!=='send'||Boolean(deliveryChecked)),canCancel:['queued','blocked','interrupted'].includes(request.status)};
  }
  function work(model,at=Date.now()){
    const requests=(model.requests||[]).filter(r=>r.type!=='mail'&&!task(r,at).superseded);
    const running=requests.filter(r=>r.status==='running'),queued=requests.filter(r=>r.status==='queued'),blocked=requests.filter(r=>['blocked','interrupted'].includes(r.status)||r.status==='cancelled'&&task(r,at).delivery);
    const unconfirmed=running.filter(r=>task(r,at).stale),execution=model.execution||{};
    const latestWork=Math.max(0,...requests.filter(r=>r.status!=='queued').map(r=>Dates.tableTimestamp(taskAt(r))||0),...(model.health||[]).map(h=>Dates.tableTimestamp(h.checkedAtUtc)||0),...(model.history||[]).map(h=>Dates.tableTimestamp(h.at)||0));
    const executionAt=Dates.tableTimestamp(execution.updatedAt||execution.startedAt);
    const failure=!blocked.length&&!running.length&&['failed','blocked','interrupted'].includes(execution.status)&&execution.message&&executionAt!==null&&executionAt>=latestWork?execution:null;
    return {running,queued,blocked,unconfirmed,starting:execution.status==='starting',busy:running.length>0||['running','starting'].includes(execution.status),failure};
  }
  function nextRequest(requests){
    const active=(requests||[]).filter(r=>!task(r).superseded&&(pending.has(r.status)||r.status==='cancelled'&&task(r).delivery));
    return active.find(r=>r.type==='send'&&r.status==='running')||active.find(r=>r.status==='running')||active.find(r=>task(r).interruptionUnconfirmed)||active.find(r=>task(r).delivery)||active.find(r=>['blocked','interrupted'].includes(r.status))||active[0]||null;
  }
  const api={taskAt,task,work,nextRequest,names};
  if(typeof module!=='undefined')module.exports=api;else window.StubbsJobsWorkflow=api;
})();
