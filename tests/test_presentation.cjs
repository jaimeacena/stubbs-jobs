const {test}=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../app/presentation.js');
const at=new Date('2026-09-22T10:00:00Z');

test('an authorized queued send asks to start the agent without asking for permission again',()=>{
 for(const mode of ['review','auto']){
  const value=job({selection:{selected:true,mode},missing:[],
   packages:[{id:'TEST-package',isCurrent:true,approvedAt:new Date().toISOString()}],
   requests:[{type:'send',status:'queued',packageId:'TEST-package'}]});
  const before=structuredClone(value),message=ui.nextAction(value);
  assert.match(message,/Envío autorizado/);assert.match(message,/aún no está confirmado/);
  assert.match(message,/Continúa con Stubbs Jobs/);
  assert.doesNotMatch(message,/Tendrás que aprobar|tras revisar el paquete/);
  assert.equal(ui.step(value).label,'Autorizada · aún sin enviar');
  assert.deepEqual(value,before);
 }
});

test('a revoked or old package never explains a queued task as an authorized send',()=>{
 for(const pack of [{isCurrent:true,approvedAt:'TEST',revokedAt:'TEST'},
                    {isCurrent:false,approvedAt:'TEST'}]){
  const value=job({selection:{selected:true,mode:'review'},packages:[pack],
   requests:[{type:'send',status:'queued'}]});
  assert.doesNotMatch(ui.nextAction(value),/Envío autorizado/);
 }
});

test('achieved results stay final and never suggest accepting, choosing or reopening',()=>{
 for(const values of [{state:'Oferta'},{state:'Lograda'},{state:'Enviada',archiveOutcome:'achieved',archivedAt:'2026-10-02'}]){
  const value=job({...values,sent:{at:'2026-10-01'},next:'Acepta la propuesta.',lifecycle:{closure:{label:'La empresa te ofrece el puesto.'}}}),before=structuredClone(value);
  assert.equal(ui.offerState(value).key,'logradas');assert.equal(ui.active(value),false);assert.equal(ui.canChoose(value),false);
  assert.equal(ui.flowStage(value),'historial');assert.equal(ui.nextAction(value),'');assert.equal(ui.decisions(model([value])).length,0);
  assert.doesNotMatch(ui.detailMessage(value),/Acepta|cerrad|rechazad/i);assert.deepEqual(value,before);
 }
});

test('ad closure, company rejection and manual follow-up closure have separate meanings',()=>{
 assert.equal(ui.offerState(job({state:'Cerrada',sent:{at:'2026-10-01'}})).label,'Cerrada');
 assert.equal(ui.offerState(job({state:'Enviada',sent:{at:'2026-10-01'},archiveOutcome:'closed',archivedAt:'2026-10-02'})).label,'Cerrada');
 assert.equal(ui.offerState(job({state:'Rechazada',sent:{at:'2026-10-01'}})).label,'Rechazada');
 assert.equal(ui.offerState(job({sent:{at:'2026-10-01'},lifecycle:{availability:{outcome:'closed'}}})).label,'Siguiendo');
});

test('an agent verification blocker does not ask the person for an unspecified input',()=>{
 const value=job({requests:[{id:'test',type:'investigate',status:'blocked',actionOwner:'agent',summary:'Comprobar el enlace de la misma oferta.'}]});
 assert.equal(ui.step(value).owner,'agent');assert.equal(ui.step(value).label,'Pendiente del agente');assert.equal(ui.step(value).action,'open');
});
test('minimum conditions alone gate choice and pending technical investigation remains selectable',()=>{
 const value=job({apply:'Sí, aclarar',priority:'C',minimums:{canApply:true,unknowns:['Fijo']},requests:[{type:'investigate',status:'queued'}]});
 assert.equal(ui.canChoose(value),true);assert.equal(ui.offerState(value).label,'Por decidir');
 value.minimums={canApply:false,violations:[{reason:'La oferta exige trabajo híbrido.'}]};
 assert.equal(ui.canChoose(value),false);assert.equal(ui.offerState(value).label,'Descartada');
 assert.equal(ui.detailMessage(value),'La oferta exige trabajo híbrido.');
 value.sent={at:'2026-10-01'};assert.equal(ui.offerState(value).label,'Siguiendo');
 value.sent=null;value.minimums={canApply:true};value.state='Pendiente de ti';
 assert.equal(ui.offerState(value).label,'Por decidir');
 value.requests=[{type:'send',status:'interrupted',interruptionUnconfirmed:true}];
 assert.equal(ui.canChoose(value),false);assert.equal(ui.offerState(value).label,'Por atender');
});
test('form responses exclude internal answers without changing their stored meaning',()=>{
  const material={answers:{custom_email:'persona@example.com',minimumFixed:35000,custom_solicitud_previa:false},formAnswerKeys:['custom_email']};
  assert.deepEqual(ui.formAnswers(material),{custom_email:'persona@example.com'});
  assert.equal(material.answers.custom_solicitud_previa,false);
  assert.deepEqual(ui.formAnswers({answers:material.answers}),{});
  assert.deepEqual(ui.formAnswers({...material,formAnswerKeys:[]}),{});
  assert.equal(ui.answerTitle('Correo de contacto para la solicitud'),'Correo');
  assert.equal(ui.answerTitle('Una pregunta específica'),'Una pregunta específica');
});
test('presentation explains verified delivery and does not invent it for older versions',()=>{
  assert.match(ui.presentationUsage({messageUsage:'unused'}),/no pide presentación.*no se adjunta ni se envía por correo/);
  assert.match(ui.presentationUsage({messageUsage:'form'}),/campo de presentación del formulario/);
  assert.match(ui.presentationUsage({messageUsage:'email'}),/cuerpo del correo/);
  assert.match(ui.presentationUsage({}),/debe comprobar/);
});
test('a presentation is visible only when its actual use is confirmed',()=>{
  for(const messageUsage of [undefined,'unknown','unused'])assert.equal(ui.presentationVisible({messageUsage,message:'Borrador anterior'}),false);
  for(const messageUsage of ['form','email'])assert.equal(ui.presentationVisible({messageUsage,message:'Texto para el destino comprobado'}),true);
  assert.equal(ui.presentationVisible({messageUsage:'form',message:'  '}),false);
  assert.equal(ui.presentationVisible(undefined),false);
});

test('manual closure separates prospects from submissions and interpretation work does not reopen either',()=>{
 const discarded=job({archivedAt:'2026-10-01',archiveOutcome:'discarded'}),rejected=job({sent:{at:'2026-10-01'},archivedAt:'2026-10-02',archiveOutcome:'rejected'});
 assert.equal(ui.offerState(discarded).key,'descartadas');assert.equal(ui.offerState(rejected).key,'rechazadas');
 rejected.requests=[{type:'change',status:'blocked',interpretationOnly:true}];
 assert.equal(ui.offerState(rejected).key,'rechazadas');assert.equal(ui.offerState(discarded).key,'descartadas');
 const follow=job({sent:{at:'2026-10-01'},requests:rejected.requests});assert.equal(ui.offerState(follow).key,'seguimiento');
 const reopened=job({apply:'Sí, aclarar',requests:[{type:'change',status:'queued',interpretationOnly:true}]});
 assert.equal(ui.offerState(reopened).key,'sin-elegir');assert.equal(ui.canChoose(reopened),true);
 const sending=job({requests:[{type:'send',status:'running',updatedAt:new Date().toISOString()},...rejected.requests]});
 assert.equal(ui.offerState(sending).key,'enviando');
});
function job(values={}){return {id:'a',state:'Preparar',questions:[],packages:[],requests:[],missing:['review'],due:null,cvUrl:'/cv',...values};}
function model(jobs,values={}){return {opportunities:jobs,requests:[],snoozes:{},...values};}
test('nine exclusive offer categories distinguish selection, preparation, attention, delivery, follow-up and archive without writes',()=>{
 const now=Date.now(),fresh=new Date(now).toISOString();
 assert.deepEqual(ui.offerStates.map(s=>s.label),['Descartada','Por decidir','En preparación','Por atender','Enviando','Siguiendo','Cerrada','Rechazada','Lograda']);
 const cases=[
  [job({apply:'Sí'}),'sin-elegir'],[job({apply:'No'}),'sin-elegir'],
  [job({requests:[{type:'investigate',status:'queued'}]}),'sin-elegir'],
  [job({selection:{selected:true,mode:'review'},requests:[{type:'review',status:'queued'}]}),'preparacion'],
  [job({selection:{selected:true,mode:'auto'},packages:[{isCurrent:true,approvedAt:fresh}],requests:[{type:'send',status:'queued'}]}),'preparacion'],
  [job({selection:{selected:true},missing:[]}),'atencion'],
  [job({questions:[{key:'city'}]}),'atencion'],[job({pendingChange:true}),'atencion'],
  [job({integrityError:'TEST broken document'}),'atencion'],
  [job({requests:[{type:'investigate',status:'blocked'}]}),'atencion'],
  [job({requests:[{type:'send',status:'running',updatedAt:fresh}]}),'enviando'],
  [job({sent:{at:fresh}}),'seguimiento'],[job({state:'Pendiente de empresa'}),'seguimiento'],[job({state:'Entrevista'}),'seguimiento'],[job({state:'Oferta'}),'logradas'],[job({state:'Lograda'}),'logradas'],
  [job({state:'Pendiente de ti'}),'atencion'],[job({state:'Pendiente de Usuario'}),'atencion'],
  [job({state:'Enviada'}),'atencion'],
  [job({state:'Rechazada',sent:{at:fresh}}),'rechazadas'],...['Cerrada','Descartada'].map(state=>[job({state,sent:{at:fresh}}),'cerradas']),
  [job({historical:true,originalState:'Enviada'}),'descartadas']
 ];
 for(const [value,key] of cases){const before=structuredClone(value);assert.equal(ui.offerState(value,now).key,key);assert(ui.offerStates.includes(ui.offerState(value,now)));assert.deepEqual(value,before);}
});
test('uncertain and withdrawn delivery takes precedence over archive and cannot be mistaken for an active send',()=>{
 const now=Date.now(),fresh=new Date(now).toISOString(),old=new Date(now-7200001).toISOString();
 for(const state of ['Preparar','Enviada','Entrevista','Oferta','Cerrada','Descartada','Rechazada']){
  for(const request of [
   {type:'send',status:'blocked'},
   {type:'send',status:'interrupted',interruptionUnconfirmed:true},
   {type:'send',status:'running',updatedAt:old},
   {type:'send',status:'running',updatedAt:'invalid'},
   {type:'send',status:'cancelled',packageId:'TEST-package',startedAt:old}
  ])assert.equal(ui.offerState(job({state,requests:[request]}),now).key,'atencion');
 }
 const request={type:'send',status:'cancelled',packageId:'TEST-package',startedAt:old,deliveryCheck:{outcome:'not_sent',packageId:'TEST-package',at:fresh,proof:'TEST portal checked'}};
 assert.equal(ui.offerState(job({requests:[request]}),now).key,'sin-elegir');
 assert.equal(ui.offerState(job({state:'Cerrada',requests:[request]}),now).key,'cerradas');
 request.deliveryCheck.at=old;assert.equal(ui.offerState(job({state:'Cerrada',requests:[request]}),now).key,'atencion');
 request.supersededByRequestId='next-attempt';assert.equal(ui.offerState(job({state:'Cerrada',requests:[request]}),now).key,'cerradas');
});
test('attention keeps a useful reason and follow-up identifies interviews without claiming a receipt',()=>{
 const value=job({selection:{selected:true},missing:[]});assert.match(ui.detailMessage(value),/Falta tu permiso/);
 assert.match(ui.detailMessage(job({state:'Entrevista',next:'Confirma tu disponibilidad.'})),/^Entrevista: Confirma tu disponibilidad/);
 assert.equal(ui.detailMessage(job({state:'Oferta',next:'Revisa el salario.'})),'La empresa te ofrece el puesto.');
 assert.match(ui.detailMessage(job({sent:{at:'2026-10-05'}})),/Sin respuesta conocida/);
 assert.match(ui.detailMessage(job({state:'Enviada'})),/No consta una confirmación/);
 const legacy=ui.detailMessage(job({state:'Pendiente de ti',next:'Puedes seleccionarla. Fijo y viajes pendientes.'}));
 assert.match(legacy,/revisa su encaje con el agente/);assert.doesNotMatch(legacy,/Puedes seleccionarla|Fijo|viajes/);
 assert.match(ui.detailMessage(job({sent:{at:'2026-10-05'},requests:[{type:'change',status:'blocked',summary:'TEST empresa pide un dato.'}]})),/TEST empresa pide un dato/);
});
function assessedJob(values={}){return job({company:'Empresa ficticia',priority:'A',apply:'Revisar',assessment:{isCurrent:true,unknowns:['Confirmar días presenciales antes de elegir.']},...values});}
test('the first checked doubt is brief guidance and never a new task or selection',()=>{
 const current=assessedJob({assessment:{isCurrent:true,unknowns:['  Confirmar\n días presenciales.  ','Otra duda']}}),before=structuredClone(current);
 assert.equal(ui.nextCheck(current),'Confirmar días presenciales.');assert.deepEqual(current,before);
 for(const values of [{sent:true},{historical:true},{state:'Cerrada'},{state:'Entrevista'},{state:'Oferta'},{apply:'No'},{selection:{selected:true}},{questions:[{key:'city'}]},{assessment:{isCurrent:false,unknowns:['Antes']}}])assert.equal(ui.nextCheck(assessedJob(values)),'');
});
test('guidance does not compete with queued work, delivery reconciliation or an interruption',()=>{
 for(const request of [{type:'investigate',status:'queued'},{type:'review',status:'running'},{type:'send',status:'cancelled',packageId:'TEST-package',startedAt:'2026-09-21T10:00:00Z',authorizationAt:'2026-09-21T09:00:00Z'},{type:'investigate',status:'blocked'},{type:'investigate',status:'interrupted'}])assert.equal(ui.nextCheck(assessedJob({requests:[request]})),'');
 assert.ok(ui.nextCheck(assessedJob({requests:[{type:'investigate',status:'done'}]})));
});
test('a single recommended offer respects priority and an actual current deadline without sorting the saved list',()=>{
 const list=[assessedJob({id:'b',priority:'B'}),assessedJob({id:'a'}),assessedJob({id:'urgent',priority:'C',externalDeadline:'2026-09-22T18:00:00Z'})],state=model(list),before=structuredClone(state);
 assert.equal(ui.recommendation(state,at).id,'urgent');assert.deepEqual(state,before);
 list[2].externalDeadline=null;assert.equal(ui.recommendation(state,at).id,'a');
});
test('summary keeps personal decisions and uncertain work ahead of another offer suggestion',()=>{
 const candidate=assessedJob({id:'candidate'});
 for(const other of [job({id:'answer',questions:[{key:'city'}]}),job({id:'interview',state:'Entrevista'}),job({id:'review',selection:{selected:true},missing:[]})])assert.equal(ui.recommendation(model([candidate,other]),at),null);
 for(const status of ['queued','running','blocked','interrupted']){
  const pending={type:'investigate',status};assert.equal(ui.recommendation(model([assessedJob({requests:[pending]})],{requests:[pending]}),at),null);
 }
});
test('old, incompatible, snoozed and damaged offers do not become recommendations',()=>{
 for(const values of [{assessment:{isCurrent:false,unknowns:['Antes']}},{apply:'No'},{integrityError:'TEST PDF corrupto'},{sent:true},{selection:{selected:true}},{assessment:{isCurrent:true,unknowns:[]}}])assert.equal(ui.recommendation(model([assessedJob(values)]),at),null);
 assert.equal(ui.recommendation(model([assessedJob()],{snoozes:{a:'2026-09-23T10:00:00Z'}}),at),null);
});
test('a process moves through choosing, applying, following and history without treating uncertainty as a send',()=>{
  const pending=job({apply:'Revisar'});
  assert.equal(ui.flowStage(pending),'elegir');assert.equal(ui.canChoose(pending),false);
  const ready=job({apply:'Sí'});assert.equal(ui.canChoose(ready),true);
  assert.equal(ui.canChoose(job({apply:'Sí',requests:[{type:'change',status:'queued'}]})),false);
  assert.equal(ui.flowStage(job({selection:{selected:true}})),'solicitar');
  assert.equal(ui.flowStage(job({sent:{at:'2026-09-22'}})),'seguir');
  assert.equal(ui.flowStage(job({state:'Oferta'})),'historial');
  assert.equal(ui.flowStage(job({state:'Rechazada',sent:{}})),'historial');
  assert.equal(ui.flowStage(job({historical:true})),'historial');
});

test('an unchecked offer explains the check before proposing selection',()=>{
  assert.match(ui.step(job({apply:'Revisar'})).detail,/comprobar las condiciones/);
  assert.match(ui.step(job({apply:'Sí'})).detail,/Puedes seleccionar esta oferta/);
});
test('offer modality preserves confirmed negatives and contradictions in all projections',()=>{
 assert.equal(ui.offerMode(job({conditions:{'Remoto España':'Sí'}})),'Remoto desde España');
 assert.equal(ui.offerMode(job({conditions:{'Remoto España':'No'}})),'No remoto desde España');
 assert.equal(ui.offerMode(job({conditions:{'Remoto España':'Contradicción'}})),'Datos contradictorios');
 assert.equal(ui.offerMode(job({conditions:{'Remoto España':'Pendiente'}})),'Sin concretar');
 assert.equal(ui.offerMode(job(), '—'),'—');
});
test('profile questions never hide a ready packet',()=>{
  const items=ui.inbox(model([job({questions:[{key:'currentCity'}]}),job({id:'b',missing:[],selection:{selected:true,mode:'review'}})]),at);
  assert.deepEqual(items.map(x=>x.kind),['profile','review']);
});
test('interview survives reminder postponement and confirmed send',()=>{
  const j=job({state:'Entrevista',sent:{id:'sent'}});
  assert.equal(ui.status(j).label,'Entrevista');
  assert.equal(ui.inbox(model([j],{snoozes:{a:'2026-09-23T12:00:00Z'}}),at)[0].kind,'milestone');
});
test('closed processes are closed even with an old sent event',()=>{
  assert.equal(ui.status(job({state:'Rechazada',sent:{}})).label,'Rechazada');
});
test('only an imminent target overrides postponement',()=>{
  const m=model([job({due:'2026-09-22'})],{snoozes:{a:'2026-09-23T12:00:00Z'}});
  assert.equal(ui.inbox(m,at)[0].kind,'due');
  m.opportunities[0].due='2026-09-25';assert.equal(ui.inbox(m,at).length,0);
});
test('blocked independent discovery requests surface on Hoy',()=>{
  const m=model([],{requests:[{id:'discovery',type:'discovery',status:'blocked'}]});
  assert.equal(ui.inbox(m,at)[0].request.id,'discovery');
});
test('source failures remain visible even when there are no user decisions',()=>{
  const m=model([],{health:[{company:'Source',status:'error'}]});
  assert.equal(ui.inbox(m,at)[0].kind,'sources');
});
test('pending and running work have different statuses',()=>{
  assert.equal(ui.status(job({requests:[{status:'queued',type:'review'}]})).label,'Tarea en cola');
  assert.equal(ui.status(job({requests:[{status:'running',type:'review',updatedAt:new Date().toISOString()}]})).label,'Preparando');
  assert.equal(ui.status(job({requests:[{status:'queued',type:'investigate'}]})).label,'Tarea en cola');
  assert.equal(ui.status(job({state:'Investigar',cvUrl:null})).label,'Por comprobar');
});
test('a changed or expired packet cannot be authorized from an old screen',()=>{
  const snapshot=job({fingerprint:'one',missing:[],selection:{selected:true,mode:'review'},packages:[{id:'one',isCurrent:true}]});
  assert.equal(ui.reviewValid(snapshot,snapshot),true);
  assert.equal(ui.reviewValid(snapshot,{...snapshot,fingerprint:'two'}),false);
  assert.equal(ui.reviewValid(snapshot,{...snapshot,missing:['expired']}),false);
  assert.equal(ui.reviewValid(snapshot,{...snapshot,sent:{}}),false);
  assert.equal(ui.reviewValid(snapshot,{...snapshot,pendingChange:true}),false);
  assert.equal(ui.reviewValid(snapshot,{...snapshot,requests:[{type:'change',status:'queued'}]}),false);
});
test('review cannot authorize another package until every original send outcome is resolved',()=>{
 const snapshot=job({fingerprint:'one',missing:[],selection:{selected:true,mode:'review'},packages:[{id:'one',isCurrent:true}]});
 const request={type:'send',status:'cancelled',packageId:'original',startedAt:'2026-09-01T10:00:00Z',updatedAt:'2026-09-01T10:05:00Z'};
 for(const status of ['running','blocked','interrupted','cancelled'])assert.equal(ui.reviewValid(snapshot,{...snapshot,requests:[{...request,status}]}),false);
 request.deliveryCheck={outcome:'unknown',packageId:'original',at:'2026-09-01T10:06:00Z',proof:'TEST: portal incierto'};
 assert.equal(ui.reviewValid(snapshot,{...snapshot,requests:[request]}),false);
 request.deliveryCheck.outcome='not_sent';request.deliveryCheck.at=new Date().toISOString();assert.equal(ui.reviewValid(snapshot,{...snapshot,requests:[request]}),true);
 assert.equal(request.status,'cancelled');
});

test('historical cancelled absence offers rechecking and prevents premature authorization',()=>{
 const request={id:'original',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-09-01T10:00:00Z',deliveryCheck:{outcome:'not_sent',packageId:'original',at:'2026-09-01T10:05:00Z',proof:'TEST absence'},deliveryRecheckRequired:true};
 const j=job({fingerprint:'current',missing:[],apply:'Sí',selection:{selected:true,mode:'review'},packages:[{id:'current',isCurrent:true}],requests:[request]}),step=ui.step(j);
 assert.equal(step.action,'recovery');assert.equal(step.cta,'Copiar petición para comprobar de nuevo');assert.equal(step.requestId,'original');
 assert.match(step.label,/No enviado/);assert.doesNotMatch(step.label,/sin confirmar/);assert.equal(ui.status(j).deliveryUnknown,false);
 assert.equal(ui.reviewValid(j,j),false);assert.equal(ui.canChoose({...j,selection:{selected:false}}),false);
 request.deliveryRecheckRequired=false;assert.equal(ui.reviewValid(j,j),true);
});

test('an original send with a validated successor cannot hide the current work or block selection',()=>{
 const original={id:'original',type:'send',status:'blocked',supersededByRequestId:'current',need:'access',summary:'Old blocked step'};
 const ready=job({apply:'Sí',missing:[],fingerprint:'packet',packages:[{id:'packet',isCurrent:true}],selection:{selected:true,mode:'review'},requests:[original]});
 assert.equal(ui.canChoose({...ready,selection:{selected:false}}),true);assert.equal(ui.reviewValid(ready,ready),true);assert.notEqual(ui.step(ready).action,'recovery');
 const current={id:'current',type:'send',status:'running',updatedAt:new Date().toISOString()};ready.requests.push(current);
 assert.equal(ui.step(ready).label,'Enviando');assert.equal(ui.reviewValid(ready,ready),false);
});
test('authorization is unavailable without the archived packet',()=>{
  const current=job({fingerprint:'one',missing:[]});
  assert.equal(ui.reviewValid(current,current),false);
});
test('an approved packet is shown as queued instead of needing another decision',()=>{
  const current=job({fingerprint:'one',missing:[],packages:[{id:'one',isCurrent:true,approvedAt:'2026-09-22'}]});
  assert.equal(ui.status(current).owner,'agent');
  assert.equal(ui.reviewValid(current,current),false);
  assert.equal(ui.inbox(model([current]),at).length,0);
});
test('Madrid day determines whether a target is today',()=>{
  const items=ui.inbox(model([job({due:'2026-09-23'})]),new Date('2026-09-22T22:30:00Z'));
  assert.equal(items[0].kind,'due');assert.equal(items[0].overdue,false);
});
test('Inicio contains decisions only, without queued work or preparation suggestions',()=>{
  const r={id:'r',status:'queued',type:'review',opportunityId:'a'};
  assert.deepEqual(ui.decisions(model([job({requests:[r]})],{requests:[r]}),at),[]);
});
test('interviews precede routine decisions while an achieved offer needs no further decision',()=>{
  const items=ui.decisions(model([job({state:'Entrevista',sent:{}}),job({id:'b',state:'Oferta'}),job({id:'c',missing:[],selection:{selected:true,mode:'review'}})]),at);
  assert.deepEqual(items.map(x=>x.kind),['milestone','review']);
});
test('routine due dates do not create a user task',()=>{
  assert.deepEqual(ui.decisions(model([job({due:'2026-09-22'})]),at),[]);
});
test('access problems are grouped as one action',()=>{
  const m=model([],{health:[{status:'error'}],requests:[{type:'discovery',status:'blocked'}]});
  assert.deepEqual(ui.decisions(m,at).map(x=>x.kind),['help']);
});
test('saving data never advances last completed check',()=>{
  const m=model([],{updatedAt:'2026-09-22T10:00:00Z',cycles:[]});
  assert.equal(ui.progress(m).latest,undefined);
  m.cycles=[{status:'partial',finishedAt:'2026-09-21T10:00:00Z'}];
  assert.equal(ui.progress(m).latest,undefined);assert.equal(ui.progress(m).busy,false);
});
test('starting is not working and a completed process is not a submitted application',()=>{
  assert.equal(ui.progress(model([],{execution:{status:'starting'}})).label,'Iniciando el agente…');
  assert.equal(ui.progress(model([],{execution:{status:'done'}})).busy,false);
  assert.equal(ui.status(job()).label,'Por comprobar');
});
test('current progress excludes retired mail and full-cycle indicators',()=>{
  const m=model([],{lastMail:'2026-09-22T10:00:00Z',lastFullSuccess:'2026-09-21T08:00:00Z',health:[{status:'ok',checkedAtUtc:'2026-09-22T09:50:00Z'}],publicSources:[{id:'one'},{id:'two'}]});
  const progress=ui.progress(m);
  assert.equal(progress.checks.mailAt,undefined);assert.equal(progress.checks.fullAt,undefined);
  assert.equal(progress.checks.sources.ok,1);assert.equal(progress.checks.sources.total,2);
});
test('a due candidature with missing answers does not duplicate the profile decision',()=>{
  const items=ui.decisions(model([job({questions:[{key:'currentCity'}],due:'2026-09-22'})]),at);
  assert.deepEqual(items.map(x=>x.kind),['profile']);
});
test('contextual step surfaces the concrete blocker without dumping its proof',()=>{
  const j=job({next:'Indicar un canal disponible',requests:[{status:'blocked',need:'contact',result:'Technical proof with details'}]});
  assert.equal(ui.step(j).cta,'Aclarar contacto');assert.equal(ui.step(j).detail,'Indicar un canal disponible');
});
test('confirmed interviews and external deadlines outrank routine preparation dates',()=>{
  assert.equal(ui.rank(job({state:'Entrevista'}),at),0);
  assert.equal(ui.rank(job({externalDeadline:'2026-09-22'}),at),0);
  assert.equal(ui.rank(job({due:'2026-09-22'}),at),5);
});
test('historical rows preserve uncertainty and avoid duplicate or non-job entries',()=>{
  const m=model([job({canonicalKey:'same'})],{historical:[{id:'old',canonicalKey:'same',category:'Empleo'},{id:'party',category:'No laboral'},{id:'unknown',category:'Empleo',state:'Inscrito'}]});
  const rows=ui.archive(m);assert.equal(rows.length,1);assert.equal(rows[0].originalState,'Inscrito');
  assert.equal(ui.step(rows[0]).label,'Sin seguimiento reciente');assert.equal(ui.step(rows[0]).cta,null);
});
test('new instructions have an honest pending state even if an older task is blocked',()=>{
  const j=job({requests:[{type:'review',status:'blocked'},{type:'change',status:'queued'}]});
  assert.match(ui.step(j).label,/falta comprobación/);assert.match(ui.step(j).detail,/bloqueo sigue vigente/);assert.equal(ui.step(j).owner,'agent');
});
test('a blocked decision has a specific action',()=>{
  const j=job({requests:[{type:'review',status:'blocked',need:'decision',summary:'Confirma el antecedente.'}]});
  assert.equal(ui.step(j).cta,'Aclarar decisión');assert.equal(ui.step(j).detail,'Confirma el antecedente.');
});

test('a legacy running cycle does not claim current agent activity',()=>{
 const m=model([],{cycles:[{status:'running',startedAt:'2020-01-01T00:00:00Z'}]});
 assert.equal(ui.progress(m).busy,false);
 assert.equal(ui.progress(m).label,'Sin trabajo en curso');
});

test('pending profile changes cannot be presented as a request ready to authorize',()=>{
 const pending=job({pendingChange:true,missing:[],requests:[]});
 assert.equal(ui.status(pending).owner,'agent');assert.equal(ui.step(pending).cta,null);
 assert.match(ui.step(pending).detail,/comprobar los cambios del perfil/);
 assert.equal(ui.inbox(model([pending]),at).some(item=>item.kind==='review'),false);
 assert.equal(ui.reviewValid(pending,pending),false);
});

test('an uncertain cancelled delivery outranks withdrawn selection, profile questions and incompatibility',()=>{
 const request={id:'cancelled-send',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-10-01T10:00:00Z',updatedAt:'2026-10-01T11:00:00Z'};
 for(const state of ['Preparar','Cerrada']){
  const j=job({state,selection:{selected:false},apply:'No',requests:[request],questions:[{label:'Ciudad'}]}),step=ui.step(j);
  assert.match(step.label,/Permiso retirado/);assert.equal(step.action,'recovery');assert.equal(step.requestId,'cancelled-send');
  assert.equal(step.cta,'Copiar petición de comprobación');assert.equal(ui.canChoose(j),false);assert.equal(ui.progress(model([j],{requests:[request]})).busy,false);
 }
});

test('a cancelled unsent result offers no retry or prompt to continue',()=>{
 const request={id:'cancelled-send',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-10-01T10:00:00Z',deliveryCheck:{outcome:'not_sent',packageId:'original',at:new Date().toISOString(),proof:'TEST absent application'}};
 const j=job({selection:{selected:false},apply:'Sí',requests:[request]});
 assert.notEqual(ui.step(j).action,'recovery');assert.equal(ui.step(j).cta,null);assert.equal(ui.canChoose(j),true);
 assert.equal(ui.progress(model([j],{requests:[request]})).busy,false);
});

test('confirmed original delivery remains follow-up even if a cancelled task was awaiting reconciliation',()=>{
 const j=job({selection:{selected:false},sent:{packageId:'original'},requests:[{id:'old',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-10-01T10:00:00Z'}]});
 assert.equal(ui.flowStage(j),'seguir');assert.equal(ui.step(j).cta,null);assert.match(ui.step(j).label,/Enviada/);
});

test('legacy interrupted-by-silence remains unconfirmed even with a recent not-sent portal result',()=>{
 const request={id:'legacy-send',type:'send',status:'interrupted',executionId:'old-owner',packageId:'original',startedAt:'2026-10-01T08:00:00Z',result:'No se ha recibido actividad durante dos horas. Revisar antes de reintentar.',deliveryCheck:{outcome:'not_sent',packageId:'original',at:new Date().toISOString(),proof:'TEST old check'}},j=job({apply:'No',selection:{selected:false},requests:[request]}),step=ui.step(j);
 assert.equal(step.label,'Actividad pendiente de confirmar');assert.equal(step.action,'recovery');assert.equal(step.requestId,'legacy-send');
 assert.equal(step.cta,'Copiar petición para retomar');assert.match(step.detail,/detención real/);
 assert.equal(ui.progress(model([j],{requests:[request]})).label,'Actividad pendiente de confirmar');
 assert.equal(request.status,'interrupted');assert.equal(request.executionId,'old-owner');
});

test('a brief unconfirmed-interruption flag preserves the offer recovery and progress message',()=>{
 const request={id:'brief-legacy',type:'review',status:'interrupted',interruptionUnconfirmed:true,executionId:'old-owner'},j=job({selection:{selected:false},apply:'No',requests:[request]});
 const step=ui.step(j);assert.equal(step.label,'Actividad pendiente de confirmar');assert.equal(step.action,'recovery');
 assert.equal(step.requestId,'brief-legacy');assert.equal(step.cta,'Copiar petición para retomar');
 assert.equal(ui.progress(model([j],{requests:[request]})).label,'Actividad pendiente de confirmar');
 assert.equal(Object.hasOwn(request,'result'),false);assert.equal(request.executionId,'old-owner');
});


test('queued selection explains the permission and next step persistently without claiming execution',()=>{
 for(const mode of ['auto','review']){
  const value=job({selection:{selected:true,mode},requests:[{type:'review',status:'queued'}]});const text=ui.nextAction(value);
  assert.match(text,/La tarea está guardada.*Continúa con Stubbs Jobs.*para iniciarla/);
  assert.match(text,mode==='auto'?/Permites enviar esta oferta tras revisar el paquete exacto/:/aprobar el paquete final/);
  assert.equal(value.requests[0].status,'queued');
 }
 const value=job({selection:{selected:true,mode:'auto'},requests:[{type:'send',status:'running'}]});assert.match(ui.nextAction(value),/Permiso retirado.*compruebe si llegó a enviarse/);
});
