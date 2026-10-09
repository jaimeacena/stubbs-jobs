const test=require('node:test'),assert=require('node:assert/strict');
const Activity=require('../app/activity.js');

test('personal job offer and rejection appear as results without becoming new agent work',()=>{
 const model={requests:[],history:[{id:'offer',opportunityId:'one',title:'Solicitud lograda',at:'2026-10-07T10:00:00Z',actor:'Usuario'},
  {id:'rejected',opportunityId:'two',title:'Rechazo registrado por ti',at:'2026-10-06T10:00:00Z',actor:'Usuario'}]},before=structuredClone(model);
 assert.deepEqual(Activity.recent(model.history,model).map(item=>item.id),['offer','rejected']);
 assert.deepEqual(Activity.outcomes(model).map(item=>item.event.id),['offer','rejected']);
 assert.equal(Activity.work(model).queued.length,0);assert.deepEqual(model,before);
});

test('recent case activity keeps useful facts despite later internal bookkeeping',()=>{
 const model={requests:[{id:'send',type:'send',status:'done',opportunityId:'one',packageId:'v1',updatedAt:'2026-10-07T10:00:00Z'}],history:[
  {id:1,title:'Oferta seleccionada',opportunityId:'one',at:'2026-10-07T08:00:00Z'},
  {id:2,title:'Paquete listo para tu decisión',opportunityId:'one',at:'2026-10-07T09:00:00Z'},
  {id:3,title:'Envío autorizado; pendiente de ejecución',opportunityId:'one',packageId:'v1',at:'2026-10-07T09:30:00Z'},
  {id:4,title:'Envío confirmado',opportunityId:'one',packageId:'v1',at:'2026-10-07T10:00:00Z'},
  {id:5,title:'Encargo terminado',requestId:'send',opportunityId:'one',at:'2026-10-07T10:00:00Z'},
  ...['Valoración guardada','Encaje comprobado','Tarea sin efecto pendiente','Seguimiento conciliado'].map((title,i)=>({id:6+i,title,opportunityId:'one',at:`2026-10-07T1${i+1}:00:00Z`}))]};
 const before=structuredClone(model),recent=Activity.recent(model.history,model);
 assert.deepEqual(recent.map(Activity.title),['Solicitud enviada','Solicitud lista para revisar','Oferta seleccionada']);
 assert.deepEqual(recent[0].sourceIds,[4,5]);assert.equal(Activity.grouped(model.history,model).length,8);assert.deepEqual(model,before);
 model.undo=[{id:5}];assert.equal(Activity.grouped(model.history,model).length,9);
});

test('pending sends stay distinct while earlier steps of a confirmed send leave the brief view',()=>{
 const model={requests:[{id:'old',type:'send',packageId:'v1'}]},items=[
  {id:1,title:'Envío puesto en cola',requestId:'old',opportunityId:'one',at:'2026-10-06T09:00:00Z'},
  {id:2,title:'Envío autorizado; pendiente de ejecución',packageId:'v1',opportunityId:'one',at:'2026-10-06T09:01:00Z'},
  {id:3,title:'Envío confirmado',packageId:'v1',opportunityId:'one',at:'2026-10-06T10:00:00Z'},
  {id:4,title:'Envío autorizado; pendiente de ejecución',packageId:'v2',opportunityId:'one',at:'2026-10-07T10:00:00Z'}];
 assert.deepEqual(Activity.recent(items,model).map(item=>item.id),[4,3]);
 assert.equal(Activity.grouped(items,model).length,4);
 assert.deepEqual(Activity.recent(items.slice(0,2),model).map(Activity.title),['Envío autorizado','Envío pendiente']);
});

test('different dated checks never fold together or borrow the latest outcome',()=>{
 const old={id:'old',title:'Seguimiento comprobado',opportunityId:'one',at:'2026-10-07T08:00:00Z',detail:'Same retained proof',activity:{kind:'followup',outcome:'waiting',checkId:'a'}},
 newer={...old,id:'new',at:'2026-10-07T10:00:00Z',activity:{kind:'followup',outcome:'reviewing',checkId:'b'}};
 const job={id:'one',lifecycle:{lastCheck:{id:'b',outcome:'reviewing',observedAt:newer.at,proof:old.detail}}},model={history:[old,newer],requests:[]},before=structuredClone(model);
 const rows=Activity.caseHistory(job,model);
 assert.deepEqual(Activity.grouped(rows,model).map(Activity.title),['Estado comprobado: sin novedades','Estado comprobado: en revisión']);assert.equal(rows.length,2);assert.deepEqual(model,before);
 const legacy={...old,activity:undefined};model.history=[legacy];
 const projected=Activity.caseHistory(job,model);assert.equal(projected.length,2);assert.equal(Activity.title(projected[0]),'Estado comprobado');assert.equal(Activity.title(projected[1]),'Estado comprobado: en revisión');
});

test('event detail follows the sent version and never substitutes a newer CV or opaque proof',()=>{
 const sent={id:'sent',title:'Envío confirmado',opportunityId:'one',packageId:'old',detail:'PRIVATE PROOF'},
 old={id:'old',cvUrl:'/old.pdf',payload:{messageUsage:'unused'}},fresh={id:'new',isCurrent:true,cvUrl:'/new.pdf'};
 const model={opportunities:[{id:'one',packages:[old,fresh]}]},before=structuredClone(model);
 assert.equal(Activity.details(sent,model).package.id,'old');assert.equal(Activity.details({...sent,packageId:null},model),null);
 assert.equal(Activity.details({title:'Valoración guardada',detail:'PRIVATE PROOF'},model),null);assert.deepEqual(model,before);
 assert.equal(Activity.title({title:'Investigación solicitada'}),'Comprobación pedida');
 assert.equal(Activity.title({title:'Seguimiento comprobado'}),'Estado comprobado');
 assert.equal(Activity.title({title:'Encargo terminado',activity:{kind:'task',type:'send'}}),'Tarea de envío terminada');
});

test('old orientation dates do not become pending work or activity without a human request',()=>{
 const model={requests:[],opportunities:[{id:'sent',state:'Enviada',sent:{at:'2026-10-01'},lifecycle:{nextCheckAt:'2026-10-06T10:00:00Z',checkDue:false}},
  {id:'unknown',state:'Investigar',lifecycle:{availability:{outcome:'unknown'},nextCheckAt:'2026-10-06T11:00:00Z'}},
  {id:'closed',state:'Cerrada',sent:{at:'2026-10-01'},lifecycle:{nextCheckAt:'2026-10-02T10:00:00Z'}}]},before=structuredClone(model);
 assert.deepEqual(Activity.entries(model),[]);assert.deepEqual(Activity.work(model).queued,[]);assert.deepEqual(model,before);
});

test('responses, employer rejection, personal closure and process closure stay visible in dated results',()=>{
 const history=['Respuesta de empresa','Candidatura rechazada','Proceso cerrado','Seguimiento cerrado por ti'].map((title,i)=>({id:i,title,opportunityId:'one',at:`2026-10-0${i+1}T10:00:00Z`,detail:'Prueba ficticia'}));
 const model={requests:[],history},before=structuredClone(model),results=Activity.outcomes(model);
 assert.deepEqual(results.map(x=>x.event.title),history.map(x=>x.title).reverse());assert.deepEqual(model,before);
});

test('pending tasks appear once in daily activity without becoming completed applications',()=>{
 const queued={id:'pending',opportunityId:'one',type:'investigate',status:'queued',createdAt:'2026-10-06T09:00:00Z'},done={id:'sent',opportunityId:'two',type:'send',status:'done',updatedAt:'2026-10-05T10:00:00Z',summary:'Recibo confirmado'},retired={id:'old',type:'mail',status:'queued'};
 const model={requests:[queued,done,retired],history:[]},before=structuredClone(model),entries=Activity.entries(model);
 assert.equal(entries.length,2);assert.equal(entries[0].request.id,'pending');assert.equal(entries[1].request.id,'sent');assert.equal(Activity.outcomes(model).length,1);assert.deepEqual(model,before);
 model.requests[0]={...queued,status:'done',summary:'Oferta comprobada',updatedAt:'2026-10-06T10:00:00Z'};assert.equal(Activity.entries(model).filter(item=>item.request.id==='pending').length,1);
});

test('each completed search keeps its own count and cannot borrow later coverage',()=>{
 const first={id:'first',type:'discovery',status:'done',updatedAt:'2026-09-28T10:00:00Z',activityResult:{newOfferCount:3,health:[{sourceId:'old',status:'partial',checkedAtUtc:'2026-09-28T09:50:00Z',errors:['Página pendiente']}],publicSources:[{id:'old'}]}};
 const second={id:'second',type:'discovery',status:'done',updatedAt:'2026-09-30T10:00:00Z',activityResult:{newOfferCount:0,health:[],publicSources:[]}};
 const model={requests:[first,second],health:[{sourceId:'new',status:'ok',checkedAtUtc:'2026-09-30T10:00:00Z'}]};
 assert.equal(Activity.searchTitle(first),'Búsqueda realizada: 3 nuevas ofertas');
 assert.equal(Activity.searchTitle(second),'Búsqueda realizada: 0 nuevas ofertas');
 assert.deepEqual(Activity.searchModel(first,model).health,first.activityResult.health);
 assert.equal(Activity.completions(model).length,2);
});
test('legacy preselection is never relabeled new and zero is not invented',()=>{
 assert.equal(Activity.searchTitle({summary:'Búsqueda terminada: 3 ofertas guardadas para elegir; sueldo pendiente.'}),'Búsqueda realizada: 3 ofertas preseleccionadas');
 assert.equal(Activity.searchTitle({summary:'Búsqueda terminada.'}),'Búsqueda realizada');
 const request={createdAt:'2026-09-28T09:00:00Z',updatedAt:'2026-09-28T10:00:00Z'};
 const model={health:[{sourceId:'later',checkedAtUtc:'2026-09-29T09:30:00Z'}],portalAccess:{linkedin:{checkedAt:'2026-09-29T09:30:00Z'}}};
 assert.deepEqual(Activity.searchModel(request,model).health,[]);
 assert.deepEqual(Activity.searchModel(request,model).portalAccess,{});
});
test('separate offers and submitted package versions survive summary grouping',()=>{
 const requests=[{id:'prep',opportunityId:'one',type:'review',status:'done',summary:'Lista',updatedAt:'2026-09-28T09:00:00Z'},
 {id:'a',opportunityId:'one',type:'send',packageId:'a',status:'done',result:'Prueba A',updatedAt:'2026-09-28T10:00:00Z'},
 {id:'b',opportunityId:'two',type:'send',packageId:'b',status:'done',result:'Prueba B',updatedAt:'2026-09-28T10:01:00Z'},
 {id:'c',opportunityId:'one',type:'send',packageId:'c',status:'done',result:'Prueba C',updatedAt:'2026-09-28T10:02:00Z'},
 {id:'cancelled',type:'review',status:'cancelled',result:'Cancelado',updatedAt:'2026-09-28T10:03:00Z'}];
 assert.deepEqual(Activity.completions({requests}).map(r=>r.id),['a','b','c']);
});
test('a matching request id cannot consume another request completion',()=>{
 const request={id:'one',status:'done',updatedAt:'2026-09-30T10:00:00Z'};
 assert.equal(Activity.matchesCompletion({requestId:'other',at:request.updatedAt,title:'Encargo terminado'},request),false);
 assert.equal(Activity.matchesCompletion({requestId:'one',at:request.updatedAt,title:'Encargo terminado'},request),true);
});

test('the daily summary preserves useful outcomes and leaves technical and permission history intact',()=>{
 const model={requests:[{id:'send',type:'send',status:'done',opportunityId:'one',packageId:'v1',summary:'Enviada',updatedAt:'2026-09-30T10:00:00Z'}],history:[
  {id:'sent',title:'Envío confirmado',opportunityId:'one',packageId:'v1',detail:'Otra redacción de la misma prueba',at:'2026-09-30T10:00:01Z'},
  {id:'ready',title:'Paquete listo para tu decisión',opportunityId:'one',at:'2026-09-30T09:00:00Z'},
  {id:'reply',title:'Respuesta recibida',opportunityId:'one',at:'2026-09-30T11:00:00Z'},
  {id:'interview',title:'Entrevista concertada',opportunityId:'one',at:'2026-09-30T12:00:00Z'},
  ...['Envío autorizado','Respuestas actualizadas','Encaje comprobado','Verificación de solicitudes por correo permitida','Encargo cancelado'].map((title,id)=>({id,title,at:'2026-09-30T13:00:00Z'}))]};
 const original=structuredClone(model),shown=Activity.outcomes(model);
 assert.deepEqual(shown.map(item=>item.request?.id||item.event.id),['interview','reply','send']);
 assert.deepEqual(model,original);
});

test('days use the same local calendar across timestamp offsets and keep dates without a time',()=>{
 const items=[{at:'2026-09-30T00:05:00+02:00'},{at:'2026-09-29T22:06:00Z'},{at:'2026-09-30'},{at:'2025-09-30T10:00:00Z'},{at:'invalid'}];
 const grouped=Activity.days(items);
 assert.deepEqual(grouped.map(day=>[day.key,day.items.length]),[['2026-09-30',3],['2025-09-30',1],['unknown',1]]);
 assert.equal(Activity.days([{at:'2026-09-30'}],'America/Los_Angeles')[0].key,'2026-09-30');
});

test('queued, starting, running and blocked work never become completed outcomes',()=>{
 for(const status of ['queued','running','blocked','interrupted','cancelled']){
  const model={requests:[{type:'discovery',status,summary:'Una búsqueda',updatedAt:'2026-09-30T10:00:00Z'}]};
  assert.equal(Activity.outcomes(model).length,0);
  const work=Activity.work(model);assert.equal(work.busy,status==='running');
  assert.equal(work.queued.length,status==='queued'?1:0);assert.equal(work.blocked.length,['blocked','interrupted'].includes(status)?1:0);
 }
 assert.equal(Activity.work({execution:{status:'starting'}}).starting,true);
 const model={execution:{status:'failed',message:'Fallo antiguo',updatedAt:'2026-09-29T10:00:00Z'},requests:[{type:'discovery',status:'done',updatedAt:'2026-09-30T10:00:00Z'}]};
 assert.equal(Activity.work(model).failure,null);
});

test('summary metadata cannot move a completed result to another day or consume later outcomes',()=>{
 const request={id:'old',type:'review',opportunityId:'one',status:'done',summary:'Resumen aclarado',result:'Prueba original',activityAt:'2026-09-28T10:00:00Z',updatedAt:'2026-10-02T12:00:00.000001Z'};
 const completion={id:'completed',opportunityId:'one',title:'Solicitud revisada',detail:request.result,at:'2026-09-28T10:00:00Z'};
 assert.equal(Activity.matchesCompletion(completion,request),true);assert.equal(Activity.matchesCompletion({...completion,at:request.updatedAt},request),false);
 const model={requests:[request,{id:'newer',type:'discovery',status:'done',summary:'Nueva búsqueda',updatedAt:'2026-09-30T10:00:00Z'}],history:[completion,{id:'ready',opportunityId:'one',title:'Paquete listo para tu decisión',detail:'Preparación posterior',at:'2026-09-29T10:00:00Z'}]},before=structuredClone(model),results=Activity.outcomes(model);
 assert.deepEqual(results.map(item=>item.request?.id||item.event.id),['newer','ready','old']);assert.deepEqual(Activity.days(results).map(day=>day.key),['2026-09-30','2026-09-29','2026-09-28']);assert.deepEqual(model,before);
 const progressed={...request,activityAt:'2026-10-02T12:00:00Z'};
 assert.equal(Activity.outcomes({requests:[progressed]})[0].at,progressed.activityAt);assert.equal(Activity.days(Activity.outcomes({requests:[progressed]}))[0].key,'2026-10-02');
});

test('completion precedence follows actual work rather than edits to older summaries',()=>{
 const earlier={id:'earlier',type:'review',opportunityId:'one',status:'done',summary:'Resumen editado',activityAt:'2026-09-28T09:00:00Z',updatedAt:'2026-10-02T12:00:00Z'},later={id:'later',type:'change',opportunityId:'one',status:'done',summary:'Corrección real',activityAt:'2026-09-29T09:00:00Z',updatedAt:'2026-09-29T09:00:00Z'};
 assert.deepEqual(Activity.completions({requests:[later,earlier]}).map(request=>request.id),['later']);
 const sent={id:'sent',type:'send',opportunityId:'one',packageId:'exact-package',status:'done',summary:'Confirmación real',updatedAt:'2026-09-28T10:00:00Z'};
 assert.deepEqual(Activity.completions({requests:[earlier,sent]}).map(request=>request.id),['sent']);
});

test('legacy search coverage stops at the recorded result even after its summary token advances',()=>{
 const request={createdAt:'2026-09-28T09:00:00Z',activityAt:'2026-09-28T10:00:00Z',updatedAt:'2026-10-02T12:00:00Z'},old={sourceId:'old',checkedAtUtc:'2026-09-28T09:30:00Z'},later={sourceId:'later',checkedAtUtc:'2026-09-30T09:30:00Z'};
 const model={health:[old,later],portalAccess:{old:{checkedAt:old.checkedAtUtc},later:{checkedAt:later.checkedAtUtc}}};
 const result=Activity.searchModel(request,model);assert.deepEqual(result.health,[old]);assert.deepEqual(Object.keys(result.portalAccess),['old']);
 assert.deepEqual(Activity.searchModel({...request,activityAt:undefined,updatedAt:'2026-09-28T10:00:00Z'},model).health,[old]);
 assert.deepEqual(Activity.searchModel({...request,activityAt:'2026-10-02T12:00:00Z'},model).health,[old,later]);
});
