const test=require('node:test'),assert=require('node:assert/strict');
const Client=require('../app/client.js'),Drafts=require('../app/drafts.js'),Dates=require('../app/formatting.js'),Activity=require('../app/activity.js');
const Recovery=require('../app/recovery.js');
const memory=()=>{const data=new Map();return {get length(){return data.size;},key:i=>[...data.keys()][i]??null,getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,String(value)),removeItem:key=>data.delete(key)};};

test('browser storage enumeration follows deletions from another tab',()=>{
 const disk=memory(),safe=Client.safeStorage(()=>disk);safe.setItem('draft','Saved');
 disk.removeItem('draft');assert.equal(safe.length,0);assert.equal(safe.key(0),null);
});

test('browser drafts remain separate when a port is reused by another installation',()=>{
 const shared=memory(),one=Drafts.scoped(shared,'one'),two=Drafts.scoped(shared,'two');
 one.setItem('stubbs_jobs-draft:datos:global','Persona A');
 assert.equal(two.getItem('stubbs_jobs-draft:datos:global'),null);
 two.setItem('stubbs_jobs-draft:datos:global','Persona B');
 assert.equal(one.getItem('stubbs_jobs-draft:datos:global'),'Persona A');
 assert.equal(one.length,1);assert.equal(two.length,1);two.removeItem('stubbs_jobs-draft:datos:global');
 assert.equal(one.length,1);assert.equal(two.length,0);
});

test('startup migration cannot move a scoped draft outside its workspace',()=>{
 const session=memory(),disk=memory(),scope=Drafts.scoped(disk,'one');
 const value=JSON.stringify({values:{text:'Pending experience'},expected:{text:''},shown:{text:''},attempt:null});
 scope.setItem('stubbs_jobs-draft:experiencia:global',value);
 Drafts.migrate(session,disk);
 assert.equal(scope.getItem('stubbs_jobs-draft:experiencia:global'),value);
 assert.equal(disk.getItem('stubbs_jobs-draft:experiencia:global'),null);
 const reopened=Drafts.storage(Drafts.scoped(memory(),'one'),scope);
 assert.equal(reopened.getItem('stubbs_jobs-draft:experiencia:global'),value);
});
test('legacy drafts are visible for explicit recovery and never replay their old save',()=>{
 const shared=memory(),tab=memory(),scope=Drafts.scoped(shared,'new-workspace');
 const original={values:{name:'Persona A'},shown:{name:'Persona'},expected:{name:'Persona'},attempt:{id:'old-attempt',operation:{kind:'ui-profile'}}};
 const raw=JSON.stringify(original);shared.setItem('stubbs_jobs-draft:datos:global',raw);
 const items=Drafts.legacyDrafts(tab,shared);assert.equal(items.length,1);
 assert.equal(scope.getItem(items[0].key),null);
 Drafts.recoverLegacy(scope,items[0]);
 assert.equal(JSON.parse(scope.getItem(items[0].key)).attempt,null);
 assert.equal(shared.getItem(items[0].key),raw);
 assert.throws(()=>Drafts.recoverLegacy(scope,items[0]),/Ya hay un borrador/);
});
test('different legacy drafts from two tabs are both retained for review',()=>{
 const one=memory(),shared=memory();
 const make=name=>JSON.stringify({values:{name},shown:{name:''},expected:{name:''}});
 one.setItem('stubbs_jobs-draft:datos:global',make('First'));shared.setItem('stubbs_jobs-draft:datos:global',make('Second'));
 assert.equal(Drafts.legacyDrafts(one,shared).length,2);
});
test('action retries keep their identity through a lost response and a reopened tab',()=>{
 const disk=memory(),scope=Drafts.scoped(disk,'workspace');let sequence=0;
 let journal=Drafts.actionJournal(Drafts.storage(memory(),scope));
 const operation={kind:'ui-approve',opportunityId:'one',fingerprint:'version'};
 const initial=journal.begin(operation,()=>`attempt-${++sequence}`);
 journal=Drafts.actionJournal(Drafts.storage(memory(),scope));
 const retry=journal.begin({fingerprint:'version',opportunityId:'one',kind:'ui-approve'},()=>`attempt-${++sequence}`);
 assert.deepEqual(initial,retry);assert.equal(sequence,1);
 journal.finish(operation);assert.equal(journal.begin(operation,()=>`attempt-${++sequence}`).id,'attempt-2');
});
test('failed storage writes remain enumerable without advertising a deleted old value',()=>{
 const disk=memory();disk.setItem('persisted','Old');disk.setItem=()=>{throw Error('quota');};disk.removeItem=()=>{throw Error('quota');};
 const safe=Client.safeStorage(()=>disk);safe.setItem('volatile','New');
 assert.equal(safe.length,2);assert.deepEqual(new Set([safe.key(0),safe.key(1)]),new Set(['persisted','volatile']));
 safe.removeItem('persisted');assert.equal(safe.length,1);assert.equal(safe.key(0),'volatile');
});
test('partial application state is never accepted as a confirmed save',()=>{
 const valid={revision:1,workspaceId:'workspace',setupComplete:true,profile:{},preferences:{},searchContext:{},execution:{},snoozes:{},opportunities:[],requests:[],history:[],health:[]};
 assert.equal(Client.validateState(valid),valid);
 for(const field of ['revision','workspaceId','setupComplete','preferences','requests']){
  const broken={...valid};delete broken[field];assert.throws(()=>Client.validateState(broken),/estado completo/);
 }
 assert.throws(()=>Client.validateState({...valid,opportunities:[{id:'one'}]}),/estado completo/);
});
test('invalid calendar dates never become a different deadline',()=>{
 for(const value of ['2026-02-30','2026-04-31','2025-02-29','2026-13-01','2026-01-00','2026-09-30T24:00:00Z','2026-09-30T12:60:00Z'])assert.equal(Dates.tableTimestamp(value),null,value);
 assert.notEqual(Dates.tableTimestamp('2024-02-29'),null);
 assert.equal(Dates.tableTimestamp('2026-09-30T12:00:00+02:00'),Dates.tableTimestamp('2026-09-30T10:00:00Z'));
});
test('coverage uses the latest real instant across time zones and retains pending sources',()=>{
 const model={publicSources:[{id:'one'},{id:'two'},{id:'three'}],health:[{sourceId:'one',status:'ok',checkedAtUtc:'2026-09-30T12:00:00+02:00'},
 {sourceId:'two',status:'partial',errors:['Page 2 failed'],checkedAtUtc:'2026-09-30T11:30:00Z'}]};
 const result=Activity.coverage(model);assert.equal(result.lastAt,'2026-09-30T11:30:00Z');assert.equal(result.pending,1);assert.equal(result.good,1);assert.equal(result.failed,1);
});
test('activity is sorted by occurrence without altering the original records',()=>{
 const items=[{at:'2026-09-30T11:00:00Z',id:1},{at:'2026-09-30T12:00:00+02:00',id:2},{at:'unknown',id:3}];
 assert.deepEqual(Activity.chronological(items).map(item=>item.id),[3,2,1]);assert.deepEqual(items.map(item=>item.id),[1,2,3]);
});

test('checking a cancelled started send cannot restore its permission or queue',()=>{
 const request={id:'cancelled-send',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-10-01T10:00:00Z',updatedAt:'2026-10-01T11:00:00Z',answers:{private:'PRIVATE ANSWER'}},before=structuredClone(request);
 const message=Recovery.taskPrompt('C:/Ficticio',request);
 assert.match(message,/cancelled-send/);assert.match(message,/ui-delivery-check/);assert.match(message,/permiso está retirado/);
 assert.match(message,/sin repetir el formulario ni reactivar el permiso/);assert.match(message,/not_sent o unknown conservan cancelled/);
 assert.match(message,/no permiten reponer la tarea en cola/);assert.match(message,/no reenviar, contactar ni cambiar permisos/);
 assert.doesNotMatch(message,/PRIVATE ANSWER/);assert.deepEqual(request,before);
});

test('a cancelled send never begun only offers consultation, not portal reconciliation',()=>{
 const message=Recovery.taskPrompt('C:/Ficticio',{id:'cancelled-send',type:'send',status:'cancelled',packageId:'original'});
 assert.match(message,/no consta un inicio real válido/);assert.doesNotMatch(message,/Registra ui-delivery-check/);
 assert.match(message,/sin activar trabajo ni permisos/);
});

test('cancelled not-sent proof never becomes a prompt to continue even while recent',()=>{
 const message=Recovery.taskPrompt('C:/Ficticio',{id:'cancelled-send',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-10-01T10:00:00Z',deliveryCheck:{outcome:'not_sent',packageId:'original',at:new Date().toISOString(),proof:'TEST portal result'}});
 assert.match(message,/permiso retirado/);assert.match(message,/no la repongas en cola/);
 assert.doesNotMatch(message,/Retoma únicamente|registrar el inicio real|puede continuar/);
});

test('a historical cancelled absence requests a new portal check without retrying or declaring it unknown',()=>{
 const request={id:'original',type:'send',status:'cancelled',packageId:'package',startedAt:'2026-09-01T10:00:00Z',deliveryRecheckRequired:true,deliveryCheck:{outcome:'not_sent',packageId:'package',at:'2026-09-01T10:05:00Z',proof:'TEST absence'}},before=structuredClone(request);
 const message=Recovery.taskPrompt('C:/Ficticio',request);
 assert.match(message,/comprobado que el intento original no se envió/);assert.match(message,/ui-delivery-check/);assert.match(message,/prueba actual/);
 assert.match(message,/Conserva cancelled/);assert.match(message,/permiso retirado/);assert.match(message,/paquete comprobado y permiso vigente/);
 assert.doesNotMatch(message,/Retoma únicamente|registrar el inicio real|resultado desconocido/);assert.deepEqual(request,before);
});

test('copying a superseded attempt consults its actual successor and never resumes the original',()=>{
 const request={id:'original',type:'send',status:'blocked',supersededByRequestId:'successor',answers:{private:'PRIVATE TEST'}};
 const message=Recovery.taskPrompt('C:/Ficticio',request);
 assert.match(message,/successor/);assert.match(message,/no reencoles ni reintentes el original/);assert.doesNotMatch(message,/PRIVATE TEST|ui-delivery-check|Retoma únicamente/);
});

test('an already unknown portal result requires new proof before another check',()=>{
 for(const status of ['cancelled','interrupted']){
  const message=Recovery.taskPrompt('C:/Ficticio',{id:'unknown-send',type:'send',status,packageId:'original',startedAt:'2026-10-01T10:00:00Z',deliveryCheck:{outcome:'unknown',packageId:'original',at:new Date().toISOString(),proof:'TEST unclear portal result'}});
  assert.match(message,/solo si hay una prueba nueva/);assert.match(message,/no reenviar/);
 }
});

test('stale running copy requires confirmed interruption and never treats copying as takeover',()=>{
 for(const type of ['review','send']){
  const request={id:'owned',type,status:'running',executionId:'old-owner',updatedAt:'2026-10-01T08:00:00Z'},before=structuredClone(request),message=Recovery.taskPrompt('C:/Ficticio',request);
  assert.match(message,/Conserva el propietario actual/);assert.match(message,/persona confirma expresamente que ya detuvo/);
  assert.match(message,/ui-request-interrupt/);assert.match(message,/expectedUpdatedAt y expectedExecutionId exactos/);
  assert.match(message,/no inicia ni transfiere el encargo/);assert.match(message,/intervención pendiente/);
  if(type==='send')assert.match(message,/No uses ui-delivery-check mientras siga running/);
  assert.deepEqual(request,before);
 }
});

test('legacy silence interruption copy requires confirmation before trusting a not-sent result',()=>{
 const request={id:'legacy-send',type:'send',status:'interrupted',executionId:'old-owner',result:'No se ha recibido actividad durante dos horas. Revisar antes de reintentar.',packageId:'original',startedAt:'2026-10-01T08:00:00Z',deliveryCheck:{outcome:'not_sent',packageId:'original',at:new Date().toISOString(),proof:'TEST old check'}},before=structuredClone(request),message=Recovery.taskPrompt('C:/Ficticio',request);
 assert.match(message,/no confirma que el chat o proceso anterior se detuviera/);assert.match(message,/no transfiere su propietario/);
 assert.match(message,/confirmar expresamente la detención real/);assert.match(message,/ui-request-interrupt/);
 assert.match(message,/expectedUpdatedAt y expectedExecutionId exactos/);assert.match(message,/Un not_sent anterior no habilita un reintento/);
 assert.match(message,/después de confirmar la interrupción, comprobar de nuevo el portal/);
 assert.doesNotMatch(message,/Retoma únicamente/);assert.deepEqual(request,before);
});
