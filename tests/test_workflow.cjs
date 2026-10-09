const test=require('node:test'),assert=require('node:assert/strict');
const Workflow=require('../app/workflow.js'),UI=require('../app/presentation.js'),Recovery=require('../app/recovery.js');
const at=Date.parse('2026-10-01T12:00:00Z');

test('a stale task is uncertain and preserves the original owner and stored state',()=>{
 for(const updatedAt of ['2026-10-01T08:00:00Z','invalid',undefined,'2026-10-02T12:00:00Z']){
  const request={id:'one',type:'review',status:'running',executionId:'original',updatedAt},before=structuredClone(request);
  const result=Workflow.task(request,at);
  assert.equal(result.state,'unconfirmed');assert.equal(result.canRetry,false);assert.match(result.detail,/última actividad/);
  const work=Workflow.work({requests:[request]},at);assert.equal(work.busy,true);assert.equal(work.running[0].executionId,'original');assert.equal(work.unconfirmed[0],request);
  assert.deepEqual(request,before);
 }
});
test('actual recent work and copying queued work remain separate',()=>{
 const queued={id:'waiting',type:'review',status:'queued',updatedAt:'2026-10-01T11:59:00Z'};
 assert.equal(Workflow.task(queued,at).state,'queued');assert.match(Workflow.task(queued,at).detail,/todavía no ha empezado/);
 assert.equal(Workflow.task({...queued,status:'running'},at).state,'running');
 assert.equal(Workflow.work({requests:[queued]},at).busy,false);
});

test('a new summary token does not make old running work recent or transfer its owner',()=>{
 const request={id:'one',type:'review',status:'running',executionId:'original',startedAt:'2026-10-01T07:00:00Z',activityAt:'2026-10-01T08:00:00Z',updatedAt:'2026-10-01T11:59:00.000001Z'},before=structuredClone(request),state=Workflow.task(request,at);
 assert.equal(Workflow.taskAt(request),request.activityAt);assert.equal(state.stale,true);assert.equal(state.state,'unconfirmed');assert.equal(state.lastAt,request.activityAt);assert.equal(state.canRetry,false);
 const work=Workflow.work({requests:[request]},at);assert.equal(work.busy,true);assert.equal(work.unconfirmed[0],request);assert.equal(work.running[0].executionId,'original');assert.deepEqual(request,before);
 assert.equal(Workflow.task({...request,activityAt:'2026-10-01T11:59:00Z'},at).stale,false);
 const legacy={...request};delete legacy.activityAt;assert.equal(Workflow.taskAt(legacy),legacy.updatedAt);assert.equal(Workflow.task(legacy,at).state,'running');
 assert.equal(Workflow.task({...request,activityAt:'invalid'},at).stale,true);
});

test('editing a completed summary cannot hide a later execution failure as if there were new work',()=>{
 const execution={status:'failed',message:'Fallo posterior real',updatedAt:'2026-10-01T10:00:00Z'},request={id:'old',type:'review',status:'done',activityAt:'2026-10-01T09:00:00Z',updatedAt:'2026-10-01T11:59:00Z'};
 assert.equal(Workflow.work({requests:[request],execution},at).failure,execution);
 assert.equal(Workflow.work({requests:[{...request,activityAt:'2026-10-01T11:00:00Z'}],execution},at).failure,null);
 const legacy={...request};delete legacy.activityAt;assert.equal(Workflow.work({requests:[legacy],execution},at).failure,null);
});
test('an uncertain delivery cannot become an ordinary retry or personal answer task',()=>{
 for(const status of ['blocked','interrupted']){
  const request={id:'send',type:'send',status,updatedAt:new Date().toISOString()};
  const job={state:'Preparar',selection:{selected:true},sent:null,requests:[request],packages:[],questions:[{label:'Ciudad'}],missing:['Respuesta']};
  assert.equal(Workflow.task(request,at).canRetry,false);
  const step=UI.step(job);assert.equal(step.label,'Envío sin confirmar');assert.equal(step.action,'recovery');assert.equal(step.requestId,'send');
  assert.match(Recovery.taskPrompt('C:/Ejemplo',request),/solo autoriza comprobar el resultado/);
  assert.match(Recovery.taskPrompt('C:/Ejemplo',request),/no reenviar/);
 }
});
test('a running send takes precedence over unrelated blocked preparation',()=>{
 const blocked={id:'old',type:'review',status:'blocked'},send={id:'send',type:'send',status:'running',updatedAt:new Date().toISOString()};
 assert.equal(Workflow.nextRequest([blocked,send]),send);
 assert.equal(UI.status({state:'Preparar',requests:[blocked,send],questions:[],packages:[],missing:[]}).label,'Enviando');
});
test('recovery messages identify the task without copying saved answers or granting permissions',()=>{
 const request={id:'specific',type:'review',status:'interrupted',answers:{private:'private test value'}};
 const message=Recovery.taskPrompt('C:/Ejemplo',request);
 assert.match(message,/specific/);assert.doesNotMatch(message,/private test value/);assert.match(message,/No tomes trabajo running de otro chat/);
 const backup=Recovery.backupPrompt('C:/Ejemplo','ejemplo.zip');assert.match(backup,/carpeta nueva/);assert.match(backup,/no autoriza búsquedas/);
});

test('cancelled delivery with a real start remains a check of the original effect, never work or retry',()=>{
 const request={id:'cancelled-send',type:'send',status:'cancelled',packageId:'original-package',executionId:'original',startedAt:'2026-10-01T09:00:00Z',updatedAt:'2026-10-01T10:00:00Z'},before=structuredClone(request);
 const state=Workflow.task(request,at),work=Workflow.work({requests:[request]},at);
 assert.equal(state.state,'cancelled');assert.equal(state.delivery,true);assert.equal(state.uncertain,true);
 assert.equal(state.canRetry,false);assert.equal(state.canCancel,false);assert.equal(state.deliveryChecked,false);
 assert.match(state.detail,/permiso está retirado/);assert.match(state.detail,/no permite volver a enviarlo/);
 assert.equal(work.busy,false);assert.equal(work.running.length,0);assert.equal(work.queued.length,0);assert.equal(work.blocked[0],request);
 assert.equal(Workflow.nextRequest([{id:'review',type:'review',status:'queued'},request]),request);
 assert.deepEqual(request,before);
});

test('cancelled deliveries never begun or lacking a valid start and package create no uncertainty',()=>{
 const base={id:'cancelled',type:'send',status:'cancelled',packageId:'package',startedAt:'2026-10-01T09:00:00Z'};
 for(const values of [{startedAt:undefined},{startedAt:'invalid'},{startedAt:'2026-10-01'},{startedAt:'2026-10-02T12:00:00Z'},{packageId:undefined},{type:'review'}]){
  const request={...base,...values},state=Workflow.task(request,at);
  assert.equal(state.delivery,false);assert.equal(state.uncertain,false);assert.equal(state.canRetry,false);
  assert.equal(Workflow.work({requests:[request]},at).blocked.length,0);
 }
});

test('a cancelled not-sent receipt resolves uncertainty without reopening the one-hour retry window',()=>{
 const request={id:'cancelled',type:'send',status:'cancelled',packageId:'package',startedAt:'2026-10-01T08:00:00Z',updatedAt:'2026-10-01T11:30:00Z',deliveryRecheckRequired:false,deliveryCheck:{outcome:'not_sent',packageId:'package',at:'2026-10-01T11:30:00Z',proof:'TEST portal found no application'}},before=structuredClone(request);
 const state=Workflow.task(request,at);
 assert.equal(state.deliveryAbsent,true);assert.equal(state.deliveryChecked,false);assert.equal(state.delivery,false);
 assert.equal(state.uncertain,false);assert.equal(state.canRetry,false);assert.match(state.detail,/permiso sigue retirado/);
 assert.equal(Workflow.nextRequest([request]),null);assert.equal(Workflow.work({requests:[request]},at).blocked.length,0);
 assert.deepEqual(request,before);
});

test('expired cancelled absence stays known and requests a fresh check for a new authorized send',()=>{
 const request={id:'cancelled',type:'send',status:'cancelled',packageId:'package',startedAt:'2026-10-01T08:00:00Z',deliveryCheck:{outcome:'not_sent',packageId:'package',at:'2026-10-01T09:00:00Z',proof:'TEST historical absence'}},before=structuredClone(request);
 const state=Workflow.task(request,at);
 assert.equal(state.deliveryAbsent,true);assert.equal(state.uncertain,false);assert.equal(state.deliveryRecheckRequired,true);assert.equal(state.delivery,true);
 assert.equal(state.canRetry,false);assert.equal(state.deliveryChecked,false);assert.match(state.label,/No enviado/);assert.match(state.detail,/antes de otro envío autorizado/);
 assert.equal(Workflow.work({requests:[request]},at).blocked[0],request);assert.equal(Workflow.work({requests:[request]},at).busy,false);
 assert.equal(Workflow.nextRequest([request]),request);assert.deepEqual(request,before);
 assert.equal(Workflow.task({...request,deliveryRecheckRequired:false},at).delivery,false);
 assert.equal(Workflow.task({...request,deliveryCheck:{...request.deliveryCheck,at:'2026-10-01T11:59:00Z'},deliveryRecheckRequired:true},at).delivery,true);
});

test('validated successors make original sends history without trusting a raw consumed pointer',()=>{
 for(const status of ['queued','blocked','interrupted','cancelled']){
  const request={id:'original',type:'send',status,packageId:'package',startedAt:'2026-10-01T08:00:00Z',supersededByRequestId:'successor',deliveryCheck:{outcome:'not_sent',packageId:'package',at:'2026-10-01T09:00:00Z',proof:'TEST absent',consumedByRequestId:'successor'}},before=structuredClone(request);
  const state=Workflow.task(request,at),work=Workflow.work({requests:[request]},at);
  assert.equal(state.superseded,true);assert.equal(state.supersededByRequestId,'successor');assert.equal(state.canRetry,false);assert.equal(state.delivery,false);
  assert.equal(work.queued.length,0);assert.equal(work.blocked.length,0);assert.equal(Workflow.nextRequest([request]),null);assert.deepEqual(request,before);
  const raw={...request};delete raw.supersededByRequestId;
  assert.equal(Workflow.task(raw,at).superseded,false);
  if(status!=='queued')assert.equal(Workflow.task(raw,at).delivery,true);
  else assert.equal(Workflow.work({requests:[raw]},at).queued[0],raw);
 }
 const running={id:'live',type:'send',status:'running',supersededByRequestId:'invalid'};
 assert.equal(Workflow.task(running,at).superseded,false);assert.equal(Workflow.work({requests:[running]},at).running[0],running);
});

test('unknown, wrong-package or pre-start receipts never quietly resolve a cancelled effect',()=>{
 const base={id:'cancelled',type:'send',status:'cancelled',packageId:'package',startedAt:'2026-10-01T10:00:00Z',updatedAt:'2026-10-01T11:00:00Z'};
 for(const values of [{outcome:'unknown'},{packageId:'different'},{at:'2026-10-01T08:00:00Z'},{proof:''}]){
  const request={...base,deliveryCheck:{outcome:'not_sent',packageId:'package',at:'2026-10-01T11:00:00Z',proof:'TEST',...values}},state=Workflow.task(request,at);
  assert.equal(state.delivery,true);assert.equal(state.deliveryChecked,false);assert.equal(state.canRetry,false);
  assert.equal(Workflow.work({requests:[request]},at).busy,false);
  if(values.outcome==='unknown')assert.match(state.detail,/solo si hay una prueba nueva/);
 }
});

test('a stored sent receipt can resolve a cancelled check without reviving work',()=>{
 const request={id:'cancelled',type:'send',status:'cancelled',packageId:'package',startedAt:'2026-10-01T10:00:00Z',deliveryCheck:{outcome:'sent',packageId:'package',at:'2026-10-01T11:00:00Z',proof:'TEST original receipt'}};
 const state=Workflow.task(request,at);
 assert.equal(state.deliveryDelivered,true);assert.equal(state.delivery,false);assert.equal(state.canRetry,false);
 assert.match(state.detail,/permiso sigue retirado/);assert.equal(Workflow.nextRequest([request]),null);
});

test('legacy silence interruptions retain ownership and cannot retry even with a recent not-sent check',()=>{
 const result='No se ha recibido actividad durante dos horas. Revisar antes de reintentar.';
 for(const type of ['review','send']){
  const request={id:'legacy',type,status:'interrupted',result,executionId:'old-owner',packageId:'package',startedAt:'2026-10-01T08:00:00Z',updatedAt:'2026-10-01T11:00:00Z',deliveryCheck:{outcome:'not_sent',packageId:'package',at:'2026-10-01T11:59:00Z',proof:'TEST old portal check'}},before=structuredClone(request),state=Workflow.task(request,at);
  assert.equal(state.state,'unconfirmed');assert.equal(state.interruptionUnconfirmed,true);assert.equal(state.deliveryChecked,false);
  assert.equal(state.canRetry,false);assert.equal(state.canCancel,true);assert.match(state.detail,/sin confirmar que el agente se hubiera detenido/);
  assert.equal(Workflow.nextRequest([{id:'later',type:'review',status:'queued'},request]),request);assert.deepEqual(request,before);
  assert.equal(Workflow.task({...request,result:'TEST confirmed interruption'},at).canRetry,true);
  assert.equal(Workflow.task({...request,status:'cancelled'},at).interruptionUnconfirmed,false);
 }
});

test('brief legacy projection retains the unconfirmed guard without exposing its full result',()=>{
 const request={id:'brief-legacy',type:'send',status:'interrupted',interruptionUnconfirmed:true,executionId:'old-owner',packageId:'package',startedAt:'2026-10-01T08:00:00Z',updatedAt:'2026-10-01T11:00:00Z',deliveryCheck:{outcome:'not_sent',packageId:'package',at:'2026-10-01T11:59:00Z',proof:'TEST old check'}},before=structuredClone(request),state=Workflow.task(request,at),work=Workflow.work({requests:[request]},at);
 assert.equal(Object.hasOwn(request,'result'),false);assert.equal(state.state,'unconfirmed');assert.equal(state.canRetry,false);
 assert.equal(state.deliveryChecked,false);assert.equal(work.blocked[0],request);assert.equal(work.running.length,0);
 assert.equal(Workflow.nextRequest([{id:'blocked',type:'review',status:'blocked'},request]),request);
 assert.match(Recovery.taskPrompt('C:/Ficticio',request),/ui-request-interrupt/);assert.deepEqual(request,before);
 assert.equal(Workflow.task({...request,status:'cancelled'},at).interruptionUnconfirmed,false);
});
