const test=require('node:test'),assert=require('node:assert/strict');
const Client=require('../app/client.js'),Drafts=require('../app/drafts.js');
const memory=()=>{const m=new Map();return {get length(){return m.size;},key:i=>[...m.keys()][i]??null,getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};};

test('blocked browser storage retains this tab and reports the recovery limit',()=>{
 let failures=0;const safe=Client.safeStorage(()=>{throw new Error('blocked');},()=>failures++);
 safe.setItem('draft','new answer');assert.equal(safe.getItem('draft'),'new answer');
 safe.removeItem('draft');assert.equal(safe.getItem('draft'),null);assert(failures>0);
});
test('quota failure cannot replace a newer draft with the persisted older value',()=>{
 const disk=memory();disk.setItem('draft','old');let failures=0;
 disk.setItem=()=>{throw new Error('quota');};disk.removeItem=()=>{throw new Error('quota');};
 const safe=Client.safeStorage(()=>disk,()=>failures++);
 assert.equal(safe.getItem('draft'),'old');safe.setItem('draft','new');assert.equal(safe.getItem('draft'),'new');
 safe.removeItem('draft');assert.equal(safe.getItem('draft'),null);assert.equal(failures,2);
});
test('rename migration preserves both colliding drafts',()=>{
 const session=memory(),disk=memory();
 const draft=value=>JSON.stringify({values:{message:value},expected:{message:''},shown:{message:''},attempt:null});
 disk.setItem('previous-draft:editar:one',draft('old unsaved'));disk.setItem('stubbs_jobs-draft:editar:one',draft('new unsaved'));
 Drafts.migrate(session,disk);
 assert.equal(JSON.parse(disk.getItem('previous-draft:editar:one')).values.message,'old unsaved');
 assert.equal(JSON.parse(disk.getItem('stubbs_jobs-draft:editar:one')).values.message,'new unsaved');
});
test('split migration retains original when its destination has another draft',()=>{
 const disk=memory();const draft=value=>JSON.stringify({values:{applicationMode:value},expected:{applicationMode:'review'},shown:{applicationMode:'review'},attempt:null});
 disk.setItem('stubbs_jobs-draft:ajustes:global',draft('auto'));
 disk.setItem('stubbs_jobs-draft:opciones-solicitud:global',draft('review'));
 Drafts.migrate(memory(),disk);
 assert.equal(JSON.parse(disk.getItem('stubbs_jobs-draft:ajustes:global')).values.applicationMode,'auto');
 assert.equal(JSON.parse(disk.getItem('stubbs_jobs-draft:opciones-solicitud:global')).values.applicationMode,'review');
});
test('quota failure during migration never deletes the original recoverable draft',()=>{
 const raw=JSON.stringify({values:{message:'Recover me'},expected:{message:''},shown:{message:''}});
 const disk=memory();disk.setItem('previous-draft:editar:one',raw);
 disk.setItem=()=>{throw new Error('quota');};
 Drafts.migrate(memory(),Client.safeStorage(()=>disk));
 assert.equal(disk.getItem('previous-draft:editar:one'),raw);
 assert.equal(disk.getItem('stubbs_jobs-draft:editar:one'),null);
});
test('HTTP conflict keeps the latest state for an explicit decision',async()=>{
 const state={revision:2};
 await assert.rejects(Client.request('/api/action',{id:'same'},{fetcher:async()=>({ok:false,status:409,json:async()=>({error:'Cambio posterior',state})})}),e=>e.status===409&&e.state===state);
});
test('malformed success response is not treated as a saved draft',async()=>{
 for(const body of [null,[],3])await assert.rejects(Client.request('/api/state',null,{fetcher:async()=>({ok:true,json:async()=>body})}),/interpretar/);
 await assert.rejects(Client.request('/api/state',null,{fetcher:async()=>({ok:true,json:async()=>{throw new SyntaxError();}})}),/incompleta/);
});
test('slow writes time out without an automatic retry or a success claim',async()=>{
 let calls=0;
 const fetcher=(_,options)=>{calls++;return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted'))));};
 await assert.rejects(Client.request('/api/action',{id:'same'},{fetcher,timeout:15}),/borrador se conserva/);
 assert.equal(calls,1);
});
