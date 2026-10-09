const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const UI=require('../app/presentation.js'),Drafts=require('../app/drafts.js'),Client=require('../app/client.js');

test('a legacy receipt never presents current draft answers or a current CV as sent material',()=>{
 const t=setup(),job={id:'TEST-legacy',company:'TEST Empresa',state:'Enviada',sent:{at:'2026-10-01T10:00:00Z'},requests:[],packages:[],questions:[],missing:[],draft:{messageUsage:'form',message:'TEST presentación actual',formAnswerKeys:['noticeDays']},answers:{noticeDays:'TEST respuesta actual'}};
 t.model.opportunities=[job];t.a.setSelected(job.id);
 const before=structuredClone(t.model),html=t.a.detail();
 assert.doesNotMatch(html,/TEST presentación actual|TEST respuesta actual|Pendiente de preparar|Pendiente de comprobar el acceso/);
 assert.match(html,/CV enviado no disponible/);assert.match(html,/no conserva las respuestas ni la presentación/);
 assert.deepEqual(t.model,before);
 job.cvUrl='/api/document?id=sent%3ATEST-legacy';job.cvLabel='TEST original.pdf';
 job.sentMaterial={answers:{},formAnswerKeys:[],messageUsage:'unknown',legacyIncomplete:true};
 const known=t.a.detail();assert.match(known,/TEST original.pdf/);assert.match(known,/id=sent%3ATEST-legacy/);
 assert.doesNotMatch(known,/TEST presentación actual|TEST respuesta actual|CV enviado no disponible/);
});

test('salary ranges keep mixed units and shared thousands in every supported currency',()=>{
 const t=setup();
 for(const [raw,low,high] of [
  ['40.000-50k EUR',40000,50000],['40k-50.000 EUR',40000,50000],
  ['40000-50k USD',40000,50000],['40k-50000 GBP',40000,50000],
  ['40000-50 k EUR',40000,50000],['40 k-50000 USD',40000,50000],
  ['35-45k USD',35000,45000],['35-45k GBP',35000,45000],
  ['35k-45 USD',35000,45000],['35–45 k€',35000,45000],
  ['35.5-45.5k USD',35500,45500],['35,5k-45,5 GBP',35500,45500]
 ]){
  const info=t.a.salaryInfo(raw);assert.equal(info.low,low,raw);assert.equal(info.high,high,raw);
  assert.equal(t.a.salaryNumber(raw),low,raw);assert.equal(info.kind,'range',raw);
 }
});

test('the result selector writes exactly the personal outcome and disappears when achieved',async()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:'2026-10-01T10:00:00Z'},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};
 t.model.opportunities=[job];t.a.setSelected(job.id);const before=structuredClone(t.model),html=t.a.detail();
 assert.match(html,/<details id="offer-outcome-one" class="offer-outcome-picker"><summary>Registrar resultado/);
 for(const [action,label] of [['achieve','Lograda'],['mark-rejected','Rechazada'],['close','Cerrada']])assert.match(html,new RegExp(`data-offer-outcome="${action}" data-job-id="one">${label}</button>`));
 assert.deepEqual(t.model,before);const calls=[];
 t.env.fetch=async(path,options)=>{calls.push(JSON.parse(options.body).operation);return {ok:true,json:async()=>({state:t.model})};};
 for(const action of ['mark-rejected','close','achieve'])await t.click({dataset:{offerOutcome:action,jobId:'one'}});
 assert.deepEqual(calls.map(op=>op.action),['mark-rejected','close','achieve']);assert(calls.every(op=>op.kind==='ui-bulk-action'&&op.expectedRevision===t.model.revision&&op.targets.length===1&&op.targets[0].id==='one'));
 Object.assign(t.a.getModel().opportunities[0],{archiveOutcome:'achieved',archivedAt:'2026-10-02T10:00:00Z',lifecycle:{closure:{label:'La empresa te ofrece el puesto.'},canReopen:false}});
 const final=t.a.detail();assert.match(final,/<strong data-offer-state="logradas"><svg[^>]*data-icon="trophy"[\s\S]*?<\/svg>Lograda/);assert.doesNotMatch(final,/data-offer-outcome=|data-followup-check=|data-change=|Registrar resultado|Cambiar resultado|Encaje contigo/);
 for(const action of ['close','mark-rejected','reopen-followup']){
  await t.click({dataset:{offerOutcome:action,jobId:'one'}});assert.match(t.env.document.querySelector('#toast').innerHTML,/ha cambiado/);
 }
 assert.equal(calls.length,3);
});

test('closed or rejected submissions can report a job offer but cannot trigger preparation',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:'2026-10-01T10:00:00Z'},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},archivedAt:'2026-10-02T10:00:00Z'};
 t.model.opportunities=[job];t.a.setSelected(job.id);
 for(const [archiveOutcome,current] of [['closed','close'],['rejected','mark-rejected']]){
  job.archiveOutcome=archiveOutcome;const before=structuredClone(t.model),html=t.a.detail();
  assert.match(html,/<summary>Cambiar resultado/);assert.match(html,/data-offer-outcome="achieve" data-job-id="one">Lograda/);
  assert.match(html,new RegExp(`data-offer-outcome="${current}"[^>]* disabled`));assert.doesNotMatch(html,/data-followup-check=|data-select=|data-investigate=/);assert.deepEqual(t.model,before);
 }
});

test('final offers hide current and stale fit while active sent offers retain it',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',state:'Cerrada',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},assessment:{reason:'TEST: encaje guardado',isCurrent:false}};
 t.model.opportunities=[job];t.a.setSelected(job.id);
 for(const state of ['Cerrada','Rechazada','Descartada','Oferta','Lograda'])for(const isCurrent of [false,true]){
  job.state=state;job.assessment.isCurrent=isCurrent;const before=structuredClone(job),html=t.a.detail();
  assert.doesNotMatch(html,/Encaje contigo|TEST: encaje guardado|Esta valoración necesita actualizarse/);assert.deepEqual(job,before);
 }
 job.state='Enviada';job.sent={at:'2026-10-01'};job.lifecycle={availability:{outcome:'closed'}};job.assessment.isCurrent=false;
 assert.match(t.a.detail(),/Esta valoración necesita actualizarse/);job.assessment.isCurrent=true;assert.match(t.a.detail(),/TEST: encaje guardado/);
});

test('brief activity uses relative times and full history retains exact dates in the same format',()=>{
 const t=setup(),sentAt=new Date(Date.now()-4*86400000).toISOString();
 t.model.opportunities=[{id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:sentAt},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}}];
 t.model.history=[{id:'sent',opportunityId:'one',title:'Envío confirmado',at:sentAt,actor:'Agente'}];t.a.setSelected('one');const before=structuredClone(t.model);
 const brief=t.a.detail().match(/<section[^>]*data-offer-section="activity"[\s\S]*?<\/section>/)[0];
 assert.match(brief,/<small><time data-activity-at="[^"]+" datetime="[^"]+" title="[^"]+">Hace 4 días<\/time> · Agente<\/small>/);
 const full=t.a.history();assert.doesNotMatch(full,/data-activity-at=|Hace 4 días/);assert.match(full,/<ol class="timeline">/);assert.deepEqual(t.model,before);
});

test('relative activity time counts complete calendar months and years without inventing a time',()=>{
 const F=require('../app/formatting.js'),options={timeZone:'Europe/Madrid'},now=Date.parse('2026-10-07T10:00:00Z');
 assert.equal(F.relativeTime('2026-07-07T10:00:00Z',now,options),'Hace 3 meses');
 assert.equal(F.relativeTime('2026-07-07T10:00:01Z',now,options),'Hace 2 meses');
 assert.equal(F.relativeTime('2026-07-07',now,options),'Hace 3 meses');
 assert.equal(F.relativeTime('2025-10-07T10:00:00Z',now,options),'Hace 1 año');
 assert.equal(F.relativeTime('2024-02-29T11:00:00Z',Date.parse('2025-02-28T11:00:00Z'),options),'Hace 1 año');
 assert.equal(F.relativeTime('2026-01-31T11:00:00Z',Date.parse('2026-02-28T11:00:00Z'),options),'Hace 1 mes');
 assert.equal(F.relativeTime('2026-12-07T11:00:00Z',now,options),'Dentro de 2 meses');
 assert.equal(F.relativeTime('2026-10-07',NaN,options),'—');
});

test('case activity reads past internal records and opens the exact sent CV without a write',async()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:'2026-10-06T10:00:00Z',packageId:'old'},requests:[],questions:[],missing:[],draft:{},answers:{},
  packages:[{id:'old',createdAt:'2026-10-05',cvUrl:'/old.pdf',messageUrl:'/old-message',payload:{message:'PRIVATE UNUSED PRESENTATION',messageUsage:'unused'}},
   {id:'new',isCurrent:true,createdAt:'2026-10-07',cvUrl:'/new.pdf',payload:{messageUsage:'unused'}}]};
 t.model.opportunities=[job];t.model.history=[{id:'sent',title:'Envío confirmado',opportunityId:'one',packageId:'old',at:job.sent.at,actor:'Agente',detail:'PRIVATE TECHNICAL RECEIPT'},
  ...['Encaje comprobado','Valoración guardada','Tarea sin efecto pendiente'].map((title,i)=>({id:'noise'+i,title,opportunityId:'one',at:`2026-10-07T1${i}:00:00Z`,actor:'Sistema'}))];
 const before=structuredClone(t.model),calls=[];t.env.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>t.model};};
 await t.a.setScreen('detalle',job.id);assert.match(calls.at(-1).url,/case=one.*history=1/);
 const activity=t.a.detail().match(/<section[^>]*data-offer-section="activity"[\s\S]*?<\/section>/)[0];assert.match(activity,/data-report="event:sent"/);assert.match(activity,/Solicitud enviada/);assert.doesNotMatch(activity,/Encaje comprobado|Valoración guardada|Tarea resuelta/);
 await t.click({dataset:{report:'event:sent'}});const report=t.a.activityReport();assert.match(report,/href="\/old.pdf"/);assert.doesNotMatch(report,/\/new.pdf|PRIVATE|Ver presentación/);assert.match(calls.at(-1).url,/case=one/);
 await t.a.goBack();assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,job.id);
 await t.click({dataset:{activity:job.id}});const full=t.a.history();assert.match(full,/Encaje comprobado|Valoración guardada/);assert.match(full,/Versiones conservadas/);assert.match(full,/\/old.pdf/);assert.match(full,/\/new.pdf/);
 assert.ok(calls.every(call=>!call.options?.method||call.options.method==='GET'));assert.deepEqual(t.model,before);
});

test('answer changes show short field labels and escape content without exposing raw proof',()=>{
 const t=setup();t.model.history=[{id:'answers',title:'Respuestas actualizadas',at:'2026-10-07T10:00:00Z',actor:'Usuario',changedFields:['Ciudad','<script>'],detail:'PRIVATE RAW PROOF'}];
 t.a.setSelected('event:answers');const html=t.a.activityReport();assert.match(html,/Qué cambió/);assert.match(html,/<li>Ciudad<\/li>/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/PRIVATE RAW PROOF|<script>/);
});

test('follow-up fits in status and activity while keeping ad closure separate from the candidature',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa ficticia',title:'Analista',state:'Enviada',sent:{at:'2026-10-01T10:00:00Z'},requests:[],packages:[],questions:[],missing:[],draft:{messageUsage:'unused'},answers:{},lifecycle:{sentAt:'2026-10-01T10:00:00Z',label:'Sin respuesta conocida',availability:{outcome:'closed',observedAt:'2026-10-06T10:00:00Z',sourceUrl:'https://example.org/123',fresh:true},lastCheck:{outcome:'reviewing',observedAt:'2026-10-06T10:00:00Z',fresh:true},nextCheckAt:'2026-10-13T10:00:00Z',plan:null}}];
 t.a.setSelected('one');const before=structuredClone(t.model),html=t.a.detail(),status=html.match(/<section[^>]*data-offer-section="status"[\s\S]*?<\/section>/)[0];
 assert.match(status,/Siguiendo/);assert.match(status,/Sin respuesta conocida/);assert.match(status,/Enviada: <time[^>]*datetime="2026-10-01T10:00:00Z"/);assert.match(status,/Última comprobación: <time[^>]*datetime="2026-10-06T10:00:00Z"/);assert.match(status,/En revisión según el portal/);assert.match(status,/El anuncio ya no acepta nuevas solicitudes/);
 assert.match(status,/data-followup-check="one">Pedir comprobación/);assert.match(status,/Registrar resultado/);assert.match(status,/data-offer-outcome="close"[^>]*>Cerrada/);
 const activity=html.match(/<section[^>]*data-offer-section="activity"[\s\S]*?<\/section>/)[0];assert.match(activity,/<ol class="timeline">/);assert.match(activity,/<li><strong><button[^>]*>Estado comprobado: en revisión<\/button><\/strong><small>/);assert.match(activity,/<li><strong><button[^>]*>El anuncio ya no acepta solicitudes<\/button><\/strong><small>/);assert.match(activity,/<li><strong>Solicitud enviada<\/strong><small>/);assert.match(activity,/>Ver historial completo<\/button>/);assert.doesNotMatch(activity,/<details|offer-receipt|offer-check-evidence|Constancia del envío|Detalles de las comprobaciones/);
 assert.doesNotMatch(html,/data-offer-section="followup"|data-followup-(?:plan|date)|Próxima revisión|Guardar fecha|no hay vigilancia automática|data-offer-outcome="reject"/);assert.deepEqual(t.model,before);
});

test('checking the advertisement or refreshing the app does not count as checking a submitted candidature',()=>{
 const t=setup(),sentAt=new Date(Date.now()-3*86400000).toISOString();
 t.model.opportunities=[{id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:sentAt},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},lifecycle:{label:'Sin respuesta conocida',availability:{outcome:'open',observedAt:new Date().toISOString(),fresh:true},lastCheck:null}}];
 t.a.setSelected('one');const html=t.a.detail();assert.match(html,/Enviada: <time[^>]*>Hace 3 días<\/time>/);assert.match(html,/Sin comprobaciones posteriores al envío/);assert.doesNotMatch(html,/Última comprobación:|Sin comprobar|Disponible cuando se comprobó|data-offer-section="followup"/);
});

test('requesting a candidature check saves only an explicit pending task and does not start it',async()=>{
 const t=setup(),sentAt=new Date(Date.now()-86400000).toISOString();
 const job={id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:sentAt},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},lifecycle:{label:'Sin respuesta conocida'}};
 t.model.opportunities=[job];t.a.setSelected('one');const calls=[];
 t.env.fetch=async(path,options)=>{calls.push({path,body:options?.body?JSON.parse(options.body):null});return {ok:true,json:async()=>({state:t.model})};};
 await t.click({dataset:{followupCheck:'one'}});
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/action');assert.equal(calls[0].body.operation.kind,'ui-request');assert.equal(calls[0].body.operation.type,'investigate');assert.equal(calls[0].body.operation.purpose,'followup');assert.equal(calls[0].body.operation.opportunityId,'one');
 assert.match(t.env.document.querySelector('#toast').innerHTML,/guardada para el agente; aún no ha consultado el portal/);
 for(const status of ['queued','running','blocked','interrupted']){
  job.requests=[{id:'check',purpose:'followup',type:'investigate',status,summary:'Comprobar el portal'}];const html=t.a.detail();assert.match(html,/data-followup-check="one" disabled/);assert.match(html,status==='running'?/Comprobación en curso/:/Comprobación pendiente/);
 }
});

test('closed follow-up preserves the receipt and a new response can be reopened from existing actions',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa ficticia',state:'Cerrada',sent:{at:'2026-10-01T10:00:00Z',confirmation:'Recibo ficticio conservado'},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},lifecycle:{closure:{label:'Seguimiento cerrado por ti'},canReopen:true}}];
 t.a.setSelected('one');const before=structuredClone(t.model),html=t.a.detail();assert.match(html,/<li><strong>Solicitud enviada<\/strong><small>/);assert.match(html,/data-offer-outcome="reopen-followup"/);assert.doesNotMatch(html,/data-followup-check=|data-offer-section="followup"|offer-receipt/);assert.deepEqual(t.model,before);assert.equal(t.model.opportunities[0].sent.confirmation,'Recibo ficticio conservado');
});

test('the same timeline format keeps known receipts and checks without duplicating matching history',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:'2026-10-01T10:00:00Z',confirmation:'Prueba original'},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},lifecycle:{label:'Sin respuesta conocida',lastCheck:{outcome:'waiting',observedAt:'2026-10-06T10:00:00Z',proof:'Prueba de consulta',sourceUrl:'https://example.org/123'}}};
 t.model.opportunities=[job];t.model.history=[{id:'sent-real',title:'Envío confirmado',opportunityId:'one',at:'2026-10-01T10:00:00Z',actor:'Agente',detail:'Prueba original'},
  {id:'check-real',title:'Seguimiento comprobado',opportunityId:'one',at:'2026-10-06T10:00:10Z',actor:'Agente',detail:'Prueba de consulta'},
  {id:'other',title:'Nota guardada',opportunityId:'other',at:'2026-10-07T10:00:00Z',actor:'Tú'}];
 t.a.setSelected('one');const before=structuredClone(t.model),html=t.a.detail(),activity=html.match(/<section[^>]*data-offer-section="activity"[\s\S]*?<\/section>/)[0];
 assert.equal((activity.match(/<li>/g)||[]).length,2);assert.equal((activity.match(/>Estado comprobado: sin novedades</g)||[]).length,1);assert.equal((activity.match(/>Solicitud enviada</g)||[]).length,1);assert.doesNotMatch(activity,/Nota guardada|<details|offer-receipt/);
 const all=t.a.history();assert.equal((all.match(/>Estado comprobado: sin novedades</g)||[]).length,1);assert.equal((all.match(/>Solicitud enviada</g)||[]).length,1);assert.deepEqual(t.model,before);
 t.model.history=[];assert.match(t.a.history(),/Solicitud enviada/);assert.match(t.a.history(),/Estado comprobado: sin novedades/);assert.equal(t.model.history.length,0);
});

test('agent-owned blockers show agent work instead of asking for personal help',()=>{
 const t=setup();t.model.requests=[{id:'one',type:'investigate',status:'blocked',actionOwner:'agent',need:'other',summary:'Verificar si el enlace sigue disponible.'}];
 const html=t.a.agentPage();assert.match(html,/Comprobaciones pendientes del agente/);assert.doesNotMatch(html,/Necesita tu ayuda/);
});
test('a poll started before a save cannot roll the screen back',async()=>{
 const t=setup();t.model.revision=5;t.a.setDirty(true);
 let deliver;
 t.env.fetch=(path)=>path.startsWith('/api/state')?new Promise(resolve=>{deliver=resolve;}):Promise.resolve({ok:true,json:async()=>({state:{...t.model,revision:6}})});
 const poll=t.a.refresh();
 assert.equal(await t.a.action({kind:'ui-seen',at:'test'}),true);
 deliver({ok:true,json:async()=>({...t.model,revision:5})});await poll;
 assert.equal(t.a.getModel().revision,6);
 assert.equal(t.a.acceptState({...t.model,revision:4}),false);
 assert.equal(t.a.getModel().revision,6);
});
test('an incomplete write response leaves the exact attempt recoverable',async()=>{
 const t=setup();t.env.fetch=async()=>({ok:true,json:async()=>({ok:true})});
 assert.equal(await t.a.action({kind:'ui-seen',at:'test'}),false);
 assert.equal(t.a.getModel(),t.model);
});
test('an incomplete poll preserves the last readable screen state',async()=>{
 const t=setup();t.env.fetch=async()=>({ok:true,json:async()=>({ok:true})});
 await t.a.refresh(true);assert.equal(t.a.getModel(),t.model);
});
test('adding a CV also rejects a poll that started before the upload',async()=>{
 const t=setup();t.model.revision=5;let deliver;
 t.env.FileReader=class{readAsDataURL(){this.result='data:application/pdf;base64,cGRm';this.onload();}};
 t.env.fetch=(path)=>path.startsWith('/api/state')?new Promise(resolve=>{deliver=resolve;}):Promise.resolve({ok:true,json:async()=>({state:{...t.model,revision:6,cvLibrary:[{name:'Nuevo.pdf'}]}})});
 const poll=t.a.refresh();await t.a.importCv({name:'Nuevo.pdf',size:30});
 deliver({ok:true,json:async()=>({...t.model,revision:5})});await poll;
 assert.equal(t.a.getModel().revision,6);assert.equal(t.a.getModel().cvLibrary[0].name,'Nuevo.pdf');
});
test('theme preference applies immediately and survives another page load',()=>{
 const values=new Map(),buttons=['system','light','dark'].map(theme=>({dataset:{theme},setAttribute(name,value){this[name]=value;}}));
 const root={dataset:{},removeAttribute(name){if(name==='data-theme')delete this.dataset.theme;}};
 const storage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
 const load=()=>{const env={window:{},document:{documentElement:root,querySelectorAll:()=>buttons},localStorage:storage};vm.runInNewContext(fs.readFileSync(require.resolve('../app/theme.js'),'utf8'),env);return env.window.StubbsJobsTheme;};
 let theme=load();assert.equal(theme.get(),'system');theme.set('dark');assert.equal(root.dataset.theme,'dark');assert.equal(buttons[2]['aria-pressed'],'true');
 theme=load();assert.equal(theme.get(),'dark');theme.set('light');assert.equal(root.dataset.theme,'light');
 theme.set('system');assert.equal(root.dataset.theme,undefined);assert.equal(values.get('stubbs_jobs-theme'),'system');
});
test('two tabs retain independent pending saves',()=>{
 const memory=()=>{const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};};
 const shared=memory(),one=Drafts.storage(memory(),shared),two=Drafts.storage(memory(),shared);
 assert.equal(one.getItem('draft'),null);assert.equal(two.getItem('draft'),null);
 one.setItem('draft','attempt-A');two.setItem('draft','attempt-B');
 assert.equal(one.getItem('draft'),'attempt-A');assert.equal(two.getItem('draft'),'attempt-B');
 one.removeItem('draft');assert.equal(shared.getItem('draft'),'attempt-B');
 assert.equal(one.getItem('draft'),null);
});
test('saved drafts survive the application rename',()=>{
 const memory=()=>{const m=new Map();return {get length(){return m.size;},key:i=>[...m.keys()][i],getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};};
 const session=memory(),durable=memory(),value=JSON.stringify({values:{applicationMode:'auto'},expected:{applicationMode:'review'},shown:{applicationMode:'review'},attempt:null});
 durable.setItem('previous-draft:perfil:global',value);
 Drafts.migrate(session,durable);
 assert.equal(JSON.parse(durable.getItem('stubbs_jobs-draft:opciones-solicitud:global')).values.applicationMode,'auto');
 assert.equal(durable.getItem('previous-draft:perfil:global'),null);
});
test('old combined settings drafts split across their new locations',()=>{
 const m=new Map(),store={get length(){return m.size;},key:i=>[...m.keys()][i],getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};
 store.setItem('stubbs_jobs-draft:ajustes:global',JSON.stringify({values:{applicationMode:'auto',contactMode:'draft',searchTime:'09:00',searchFrequency:'daily'},expected:{applicationMode:'review',contactMode:'ask',searchTime:'08:00',searchFrequency:'manual'},shown:{applicationMode:'review',contactMode:'ask',searchTime:'08:00',searchFrequency:'manual'},attempt:null}));
 Drafts.migrate(store,store);
 assert.deepEqual(JSON.parse(store.getItem('stubbs_jobs-draft:opciones-solicitud:global')).values,{applicationMode:'auto',contactMode:'draft'});
 assert.deepEqual(JSON.parse(store.getItem('stubbs_jobs-draft:programacion:global')).values,{searchTime:'09:00',scheduleEnabled:'true'});
 assert.equal(store.getItem('stubbs_jobs-draft:ajustes:global'),null);
});
test('saved language and previous-application edits follow their fields into search',()=>{
 const m=new Map(),store={get length(){return m.size;},key:i=>[...m.keys()][i],getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};
 store.setItem('stubbs_jobs-draft:datos:global',JSON.stringify({values:{name:'Persona',languages:'Inglés C1',salaryExpectationFixed:'65000'},expected:{name:'Persona',languages:'',salaryExpectationFixed:null},shown:{name:'Persona',languages:'',salaryExpectationFixed:null},attempt:null}));
 store.setItem('stubbs_jobs-draft:antecedentes:global',JSON.stringify({values:{previousApplications:'Hospital A'},expected:{previousApplications:''},shown:{previousApplications:''},attempt:null}));
 Drafts.migrate(store,store);
 const search=JSON.parse(store.getItem('stubbs_jobs-draft:busqueda:global'));
 assert.deepEqual(search.values,{languages:'Inglés C1',salaryExpectationFixed:'65000',previousApplications:'Hospital A'});
 assert.deepEqual(JSON.parse(store.getItem('stubbs_jobs-draft:datos:global')).values,{name:'Persona'});
 assert.equal(store.getItem('stubbs_jobs-draft:antecedentes:global'),null);
});
function setup(){
 const headerUndo={hidden:true,dataset:{},setAttribute(k,v){this[k]=v;}},storage=new Map(),errorBox={},infoBox={},button={hidden:false},toastBox={innerHTML:'',hidden:true},pendingBox={hidden:true,innerHTML:''},pageBack={hidden:true,innerHTML:''},connectionBox={textContent:''},listeners={};let forms=[];
 const mainListeners={},mainListenerOptions={},windowListeners={},main={addEventListener(name,handler,options){mainListeners[name]=handler;mainListenerOptions[name]=options;},querySelector(s){return s==='form[data-form]'?forms[0]||null:null;},querySelectorAll(s){return s==='form[data-form]'?forms:[];},contains(){return false;}};
 let seq=0;
 const env={window:{StubbsJobsIcons:require('../app/icons.js'),StubbsJobsUI:UI,StubbsJobsExplanations:require('../app/explanations.js'),StubbsJobsWorkflow:require('../app/workflow.js'),StubbsJobsCriteria:require('../app/criteria.js'),StubbsJobsRecovery:require('../app/recovery.js'),StubbsJobsClient:Client,StubbsJobsActivity:require('../app/activity.js'),StubbsJobsFormatting:require('../app/formatting.js'),StubbsJobsDrafts:Drafts,StubbsJobsTheme:{get:()=>'system',set(){}},addEventListener(){},scrollTo(){},scrollY:0},document:{hidden:false,querySelector(s){return s==='#main'?main:s==='#toast'?toastBox:s==='#pending-work'?pendingBox:s==='#header-undo'?headerUndo:s==='#page-back'?pageBack:s==='#connection'?connectionBox:{};},querySelectorAll(){return [];},getElementById(){return null;},addEventListener(){}},localStorage:{get length(){return storage.size;},key:i=>[...storage.keys()][i]??null,getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},sessionStorage:{get length(){return storage.size;},key:i=>[...storage.keys()][i]??null,getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},crypto:{randomUUID:()=>`attempt-${++seq}`},structuredClone,URLSearchParams,Intl,console,setTimeout(){},clearTimeout(){},FormData:class{constructor(f){this.values=f.values;}keys(){return Object.keys(this.values)[Symbol.iterator]();}[Symbol.iterator](){return Object.entries(this.values)[Symbol.iterator]();}}};
 env.window.history={pushState(){},replaceState(){}};env.requestAnimationFrame=fn=>fn();env.window.addEventListener=(name,handler)=>{windowListeners[name]=handler;};
 env.document.addEventListener=(name,handler)=>{listeners[name]=handler;};
 // Criteria previews have no effect unless a test describes one; other requests reach the test's fetch.
 let fetcher;const noEffect={toEligible:[],toDiscarded:[],assessments:[],fitReviews:[],packages:[],authorizedPackages:[],excluded:[]};
 Object.defineProperty(env,'fetch',{configurable:true,get:()=>(path,options)=>path==='/api/criteria-preview'?Promise.resolve({ok:true,json:async()=>env.criteriaPreview?env.criteriaPreview(JSON.parse(options.body)):noEffect}):fetcher(path,options),set:value=>{fetcher=value;}});
 let code=fs.readFileSync(require.resolve('../app/app.js'),'utf8');
 const end=code.lastIndexOf('start().catch(error=>');
 code=code.slice(0,end)+"window.audit={setModel(x){model=x;},setSelected(x){selected=x;},setScreenState(x){screen=x;},setQuery(query){filterText=query;},setFlowFilter(tab,value){flowFilters[tab]=value;},setTableSort(tab,key,direction=1){tableState[tab].sort=key;tableState[tab].direction=direction;},setTableFilter(tab,key,values){tableState[tab].filters[key]=values;},salaryNumber,salaryInfo,relativeTime,updateActivityTimes,history,setHistoryLimit(value){historyLimit=value;},setActivityDayLimit(value){activityDayLimit=value;},setDirty(x){dirty=x;},isDirty(){return dirty;},agentPage,searchSettingsPanels,applyPage,followPage,findPage,findResults,changeForm,detail,coverage:()=>coverageContent(window.StubbsJobsActivity.coverage(model)),activityReport,profileForm,selectOpportunity,activityWork,copyRequestButton,openSearchOffers,saveVisibleChangesAndCopy,saveProfileChanges,syncDirty,backupsPage,setupReady,setupAgentPrompt,setupForm,scheduleForm,render,formSource,formValues,syncSourceControls,rememberForm,restoreForm,updateSave,saveAttempt,refresh};\n})();";
 code=code.slice(0,code.lastIndexOf('})();'))+"window.audit.action=action;window.audit.importCv=importCv;window.audit.acceptState=acceptState;window.audit.getModel=()=>model;window.audit.reviewPage=reviewPage;window.audit.setReviewSnapshot=value=>{reviewSnapshot=value;};\n})();";
 code=code.slice(0,code.lastIndexOf('})();'))+"Object.assign(window.audit,{setScreen,goBack,backDestination,renderBackNavigation,offerConditions,backupDrafts,createBackup,flowRecord,columnCatalog,populateColumnMenu,openColumnMenu,closeColumnMenu,placeColumnMenu,filterMenuChoices,captureFocus,restoreFocus,getTableState(){return tableState.solicitar;},getOpenFilter(){return openFilterMenu;},getView(){return {screen,selected,filterText};}});\n})();";
 code=code.slice(0,code.lastIndexOf('})();'))+"Object.assign(window.audit,{growField,growProfileFields,workAuthorizationValues,saveWorkAuthorizationChoices,bulkOptions,bulkToolbar,bulkAction,bulkReviewPage,bulkEditorPage,bulkEditorFields,saveBulkEditor,commonBulkOptions,startOfferTour,offerTourIds,offerNavigation,captureOfferSection,moveOffer,getTableSelection:()=>tableSelection,getBulkEditor:()=>bulkEditor,getOfferTour:()=>offerTour,setBulkReview(value){bulkReviewSnapshots=value;bulkReviewTotal=tableSelection.size;}});\n})();";
 vm.runInNewContext(fs.readFileSync(require.resolve('../app/setup.js'),'utf8'),env);
 vm.runInNewContext(code,env);
 const model={revision:0,workspaceId:'workspace-test',setupComplete:true,profile:{},preferences:{},searchContext:{},opportunities:[],historical:[],requests:[],health:[],cycles:[],execution:{status:'idle'},snoozes:{},export:{status:'ok'},history:[]};
 env.window.audit.acceptState(model);
const prefix='stubbs_jobs-workspace:workspace-test:';
 const workspaceStorage={get:k=>storage.get(prefix+k),has:k=>storage.has(prefix+k),set:(k,v)=>storage.set(prefix+k,v)};
 const event=(target,values={})=>({target,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},...values});
 return {env,model,storage:workspaceStorage,rawStorage:storage,a:env.window.audit,event,mainListenerOptions,dispatch(name,target,values={}){return listeners[name]?.(event(target,values));},dispatchMain(name,target,values={}){return mainListeners[name]?.(event(target,values));},dispatchWindow(name){return windowListeners[name]?.();},click(b){return listeners.click(event({closest(selector){if(selector==='.column-menu>summary')return b.tagName==='SUMMARY'?b:null;if(selector==='[data-profile-section]')return b.dataset?.profileSection?b:null;return b;}}));},setForm(f){forms=f?[f]:[];},setForms(items){forms=items;},button,errorBox,infoBox,pendingBox,headerUndo,pageBack,connectionBox};
}

test('search shares all nine offer columns and values without changing marks or saved data',async()=>{
 const t=setup(),job={id:'parity',company:'Empresa ficticia',title:'Analista',country:'Canadá',mode:'Remoto',contract:'Indefinido',salary:'No publicado',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};
 t.model.opportunities=[job];const before=structuredClone(t.model);
 const table=t.a.applyPage();t.a.setQuery('Empresa ficticia');const search=t.a.findResults();
 assert.deepEqual([...search.matchAll(/class="column-title"[^>]*>([^<]+)/g)].map(m=>m[1].trim()),['Encontrada','Empresa','Puesto','País','Modalidad','Contrato','Horario','Salario','Estado']);
 assert.equal(search.match(/<tbody>[\s\S]*?<\/tbody>/)[0],table.match(/<tbody>[\s\S]*?<\/tbody>/)[0]);
 assert.doesNotMatch(search,/>No publicado<|Situación|Empresa y puesto/);
 await t.click({dataset:{bulkMode:'1'}});t.a.getTableSelection().add(job.id);
 t.a.setQuery('sin coincidencias');assert.match(t.a.findResults(),/Sin resultados guardados/);
 assert.deepEqual([...t.a.getTableSelection()],[job.id]);t.a.setQuery('Empresa ficticia');assert.doesNotMatch(t.a.findResults(),/data-bulk-select/);
 assert.deepEqual(t.model,before);
});

test('search adds 100 rows at a time with the shared table',async()=>{
 const t=setup(),base={title:'Puesto de prueba',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};
 t.model.opportunities=Array.from({length:205},(_,i)=>({...base,id:'row-'+i,company:'Empresa '+i}));
 t.env.fetch=async()=>({ok:true,json:async()=>t.model});await t.a.setScreen('encontrar');t.a.setQuery('Puesto de prueba');t.a.render();
 assert.equal((t.a.findResults().match(/data-job-row=/g)||[]).length,100);
 await t.click({dataset:{moreHistory:'1'}});assert.equal((t.a.findResults().match(/data-job-row=/g)||[]).length,200);
 await t.click({dataset:{moreHistory:'1'}});const html=t.a.findResults();assert.equal((html.match(/data-job-row=/g)||[]).length,205);assert.doesNotMatch(html,/data-more-history/);
 assert.deepEqual(t.model.requests,[]);
});

test('clicking an offer cell opens its case while text selection and checkbox labels stay independent',async()=>{
 const t=setup(),job={id:'whole-row',company:'Empresa ficticia',title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};
 t.model.opportunities=[job];t.env.fetch=async()=>({ok:true,json:async()=>t.model});await t.a.setScreen('solicitar');
 const row={dataset:{jobRow:job.id}},cell={closest(selector){return selector==='button,[data-job-row],a[data-job]'?row:null;}};
 await t.dispatch('click',cell);assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,job.id);assert.deepEqual([...t.a.offerTourIds()],[job.id]);
 await t.a.goBack();t.env.window.getSelection=()=>({toString:()=> 'Texto que se está copiando'});
 await t.dispatch('click',cell);assert.equal(t.a.getView().screen,'solicitar');
 t.env.window.getSelection=()=>({toString:()=> ''});const label={closest(selector){return selector==='.offer-select-control'?{tagName:'LABEL'}:selector==='button,[data-job-row],a[data-job]'?row:null;}};
 await t.dispatch('click',label);assert.equal(t.a.getView().screen,'solicitar');assert.deepEqual(t.model.requests,[]);
});

test('search navigation freezes its own sorted results and returns to that search',async()=>{
 const t=setup(),base={company:'Empresa ficticia',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},url:'https://example.org/job?a=1&b=2'};
 t.model.opportunities=[{...base,id:'second',title:'Zoología'},{...base,id:'first',title:'Analista'},{...base,id:'other',company:'Otra empresa',title:'Ventas'}];
 t.env.fetch=async()=>({ok:true,json:async()=>t.model});await t.a.setScreen('encontrar');t.a.setQuery('Empresa ficticia');t.a.setTableSort('encontrar','title',1);t.a.render();await t.a.setScreen('detalle','first');
 assert.deepEqual([...t.a.offerTourIds()],['first','second']);assert.equal(t.a.backDestination().page,'encontrar');
 let html=t.a.detail();assert.match(html,/<h1[^>]*><a class="offer-title-link" href="https:\/\/example.org\/job\?a=1&amp;b=2"/);assert.doesNotMatch(html,/Oferta original|offer-origin/);
 await t.click({dataset:{offerMove:'1'}});assert.equal(t.a.getView().selected,'second');await t.a.goBack();assert.equal(t.a.getView().screen,'encontrar');assert.equal(t.a.getView().filterText,'Empresa ficticia');
 const rows=[...t.a.findResults().matchAll(/data-job-row="([^"]+)"/g)].map(m=>m[1]);assert.deepEqual(rows,['first','second']);assert.deepEqual(t.model.requests,[]);
});

test('a clipboard failure keeps the visible message available for manual copying without starting work',async()=>{
 const t=setup(),message={focused:false,focus(){this.focused=true;}};t.model.setupComplete=false;t.model.workspacePath='C:\\Carpeta de prueba';t.env.document.getElementById=id=>id==='setup-message'?message:null;
 const before=structuredClone(t.model);t.a.setScreenState('configurar');t.a.render();
 assert.match(t.env.document.querySelector('#main').innerHTML,/<pre id="setup-message"/);
 await t.click({dataset:{copySetup:'1'}});assert.equal(message.focused,true);assert.deepEqual(t.model,before);
 assert.match(t.env.document.querySelector('#toast').innerHTML,/Selecciona el mensaje visible/);
 assert.doesNotMatch(t.a.setupForm(),/<details|<select/);
});
test('review shows actual form responses, hides unused presentation and groups authorization actions',()=>{
 const t=setup(),material={recipient:'https://example.org/apply',message:'Hola, me interesa el puesto.',messageUsage:'unused',answers:{custom_email:'persona@example.org',minimumFixed:35000,custom_solicitud_previa:false},formAnswerKeys:['custom_email']};
 const job={id:'one',company:'Test',title:'Analista',state:'Preparar',requests:[],missing:[],selection:{selected:true,mode:'review'},fingerprint:'version',cvLabel:'Adaptado.pdf',draft:{messageUsage:'email',review:{proof:'Internal check'}},fieldDefinitions:{custom_email:{label:'Correo de contacto para la solicitud'}},packages:[{id:'version',isCurrent:true,cvUrl:'/api/document?id=version',payload:material}]};
 t.model.labels={};t.model.opportunities=[job];t.a.setSelected('one');t.a.setReviewSnapshot(job);
 const html=t.a.reviewPage();assert.match(html,/<h2>CV adaptado<\/h2>/);assert.match(html,/<dt>Correo<\/dt>/);
 assert.match(html,/src="\/api\/preview\?id=version"/);assert.match(html,/Vista previa de la primera página/);assert.match(html,/href="\/api\/document\?id=version"/);assert.doesNotMatch(html,/<iframe/);
 assert.doesNotMatch(html,/Presentación|Hola, me interesa|cuerpo del correo|35000|custom_solicitud_previa|Qué comprobó la IA|<details|Internal check/);
 assert.match(html,/class="authorization"[\s\S]*data-approve="one"[\s\S]*Autorizar envío[\s\S]*secondary-change" data-change="one">Pedir cambio/);
 assert.match(html,/data-approve="one"/);assert.doesNotMatch(html,/data-approve="one" disabled/);
 const frozen={...job};t.a.setReviewSnapshot(frozen);job.fingerprint='new-version';
 const stale=t.a.reviewPage();assert.match(stale,/Esta versión no se puede autorizar/);assert.match(stale,/data-approve="one" disabled/);
});
test('all applications put actual form answers before a verified presentation and hide legacy drafts',()=>{
 const t=setup(),material={recipient:'https://example.org/apply',message:'Borrador anterior',answers:{custom_email:'persona@example.org'},formAnswerKeys:['custom_email']};
 const job={id:'one',company:'Empresa',title:'Analista',state:'Preparar',requests:[],missing:[],questions:[],selection:{selected:true,mode:'review'},fingerprint:'version',cvLabel:'Adaptado.pdf',cvUrl:'/cv',fieldDefinitions:{custom_email:{label:'Correo'}},answerOverrides:{},packages:[{id:'version',isCurrent:true,cvUrl:'/cv',payload:material}]};
 t.model.labels={};t.model.opportunities=[job];t.a.setSelected('one');t.a.setReviewSnapshot(job);
 for(const messageUsage of [undefined,'unknown','unused','form','email']){
  material.messageUsage=messageUsage;job.draft={...material,requiredAnswers:[]};job.answers=material.answers;
  const detail=t.a.detail(),review=t.a.reviewPage();
  for(const [html,heading] of [[detail,'Formulario de solicitud'],[review,'Respuestas del formulario']]){
   assert.match(html,new RegExp(heading));assert.match(html,/<dt>Correo<\/dt>/);
   if(['form','email'].includes(messageUsage)){assert(html.indexOf('<dt>Correo</dt>')<html.indexOf('Presentación'));assert.match(html,/Borrador anterior/);}
   else assert.doesNotMatch(html,/Presentación|Borrador anterior/);
  }
  assert.match(detail,/<dt>CV para la oferta<\/dt>[\s\S]*?<\/dl>/);
  if(['form','email'].includes(messageUsage))assert.match(detail,/<dl class="meta">[\s\S]*<span>Presentación<\/span>[\s\S]*Borrador anterior[\s\S]*<\/dl>/);
 }
});
test('Perfil retains independent editors and Activity is an uncluttered daily summary',()=>{
 const t=setup();t.model.health=[{company:'Test Source',status:'partial',errors:['Page 2 failed']}];
 const profile=t.a.profileForm();assert.match(profile,/<h1>Mi perfil<\/h1>/);assert.match(profile,/<h2>Sobre mi<\/h2>[\s\S]*<h2>Lo que busco<\/h2>/);assert.doesNotMatch(profile,/<h2>Mis solicitudes anteriores/);
 for(const key of ['keywords','languages','previousApplications','sourceUrls','searchPriorities'])assert.match(profile,new RegExp(`name="${key}"`));
 assert.match(profile,/class="profile-layout"[\s\S]*class="profile-content"/);assert.match(profile,/data-save-profile="1"[^>]*>Guardar cambios/);assert.doesNotMatch(profile,/Guardar y copiar petición|type="submit"/);
 assert.doesNotMatch(profile,/Estado actual|Ver historial|Últimos cambios|Cómo funciona/);
 const agent=t.a.agentPage();assert.match(agent,/<h1 id="agent-activity-title">Resumen<\/h1>/);assert.match(agent,/Aquí aparecerán los resultados/);assert.doesNotMatch(agent,/Test Source|Estado actual|Ver historial|data-form=|data-copy-agent-command/);
 const offers=t.a.applyPage();assert.match(offers,/<h1>Ofertas<\/h1>/);assert.doesNotMatch(offers,/data-copy-agent-command|Copiar petición de búsqueda/);assert.match(offers,/data-screen="nueva"/);assert.match(offers,/Aún no hay ofertas/);assert.doesNotMatch(offers,/franja general|Descargar Excel/);
});

test('first visit explains folder, interview and confirmation in order',()=>{
 const t=setup();t.model.workspacePath='C:\\StubbsJobs & familia';t.model.setupComplete=false;
 const first=t.a.setupForm();assert.match(first,/<h1>Empieza con Stubbs Jobs<\/h1>[\s\S]*1<\/span> Añade esta carpeta como proyecto en tu agente de IA[\s\S]*2<\/span> Pega este mensaje en un chat dentro de tu nuevo proyecto para empezar el on-boarding/);
 assert.doesNotMatch(first,/<select|<details|Codex|Claude|Adjunta tus CV|Tus respuestas se conservan|condiciones de su proveedor/);
 assert.match(first,/Copiar ubicación/);assert.match(first,/C:\\StubbsJobs &amp; familia/);assert.match(first,/data-copy-setup="1"/);assert.match(first,/<pre[^>]*>[\s\S]*INICIO.md[\s\S]*<\/pre>/);
 assert.match(first,/<pre id="setup-message"[\s\S]*<\/pre><button class="primary" data-copy-setup="1"[^>]*>Copiar mensaje<\/button>/);
 assert.doesNotMatch(first,/<form|Crear mi perfil/);
 t.model.setupComplete=true;
 const backups=t.a.backupsPage();assert.match(backups,/<h1>Copias de seguridad<\/h1>/);assert.match(backups,/Crear una copia/);assert.doesNotMatch(backups,/Empieza con Stubbs Jobs|data-copy-setup/);assert.match(t.a.setupAgentPrompt(),/C:\\StubbsJobs & familia/);
});
test('setup stays on one screen while exposing the guide',()=>{
 const t=setup();t.model.setupComplete=false;t.a.setScreenState('configurar');t.a.render();
 assert.match(t.env.document.querySelector('#main').innerHTML,/Añade esta carpeta como proyecto en tu agente/);
 assert.match(t.env.document.querySelector('#main').innerHTML,/Copiar ubicación/);
});

test('first-run progress stays in one preparation view with every instruction directly visible',()=>{
 const t=setup();t.model.setupComplete=false;
 for(const status of ['waiting','access_checked','preparing','awaiting_confirmation','blocked']){
  t.model.onboarding={status,agent:'Agente de prueba',checkedAt:status==='waiting'?null:'2026-10-01T12:00:00Z',summary:'Falta acceso a los archivos.',executionId:status==='waiting'?null:'synthetic'};
  const html=t.a.setupForm();assert.match(html,/<h1>Empieza con Stubbs Jobs<\/h1>/);assert.match(html,/Copiar ubicación/);
  assert.match(html,/<pre id="setup-message"[\s\S]*<\/pre><button[^>]*data-copy-setup/);
  assert.doesNotMatch(html,/Tus respuestas se conservan en esta carpeta|<details|<summary|<select|<form|Conectado|Último paso registrado|Acceso comprobado:/);
  if(status==='waiting')assert.doesNotMatch(html,/data-setup-retry/);
  else {assert.match(html,/Retomar en otro chat/);assert.match(html,/retira al chat anterior el acceso a esta preparación/);}
  if(status==='awaiting_confirmation')assert.match(html,/Revisa el resumen en el chat y confírmalo o pide cambios/);
  if(status==='blocked')assert.match(html,/Falta acceso a los archivos/);
 }
 assert.equal(t.model.setupComplete,false);assert.deepEqual(t.model.requests,[]);
});

test('clipboard uses the currently detected folder including spaces and accents without saving or starting work',async()=>{
 const t=setup(),copied=[];t.model.setupComplete=false;t.env.navigator={clipboard:{async writeText(text){copied.push(text);}}};
 t.env.fetch=async()=>{assert.fail('Copying must not write or start the agent');};
 t.model.workspacePath='C:\\Mi instalación\\Empleo & diseño';let before=structuredClone(t.model);
 await t.click({dataset:{copyPath:'1'}});assert.equal(copied[0],t.model.workspacePath);assert.deepEqual(t.model,before);
 t.model.workspacePath='D:\\Carpeta trasladada\\Stubbs Jobs';before=structuredClone(t.model);
 await t.click({dataset:{copySetup:'1'}});assert.equal(copied[1],t.a.setupAgentPrompt());assert.ok(copied[1].includes(t.model.workspacePath));assert.ok(!copied[1].includes('C:\\Mi instalación'));
 assert.match(copied[1],/Muéstrame el resumen antes de guardar solo lo que confirme/);assert.match(copied[1],/No busques ofertas ni envíes solicitudes todavía/);assert.deepEqual(t.model,before);
});

test('a successful message copy shows Copiado for two seconds and survives a repaint or another click',async()=>{
 const t=setup(),timers=new Map();let sequence=0,now=1000;
 t.model.setupComplete=false;t.model.workspacePath='C:\\Prueba';const before=structuredClone(t.model);
 t.env.Date=class extends Date{static now(){return now;}};
 t.env.navigator={clipboard:{async writeText(){}}};
 t.env.setTimeout=(callback,delay)=>{const id=++sequence;timers.set(id,{callback,delay});return id;};t.env.clearTimeout=id=>timers.delete(id);
 const first={dataset:{copySetup:'1',copyLabel:'Copiar mensaje'},textContent:'Copiar mensaje'};
 await t.click(first);assert.equal(first.textContent,'Copiado');assert.equal(timers.size,1);assert.equal([...timers.values()][0].delay,2000);
 assert.match(t.a.setupForm(),/data-copy-setup="1"[^>]*>Copiado<\/button>/);
 const repainted={dataset:{copySetup:'1',copyLabel:'Copiar mensaje'},textContent:'Copiado'},main=t.env.document.querySelector('#main'),query=main.querySelectorAll;
 main.querySelectorAll=selector=>selector==='[data-copy-setup]'?[repainted]:query(selector);
 now=1500;await t.click(repainted);assert.equal(timers.size,1);assert.equal(repainted.textContent,'Copiado');
 now=3500;[...timers.values()][0].callback();assert.equal(repainted.textContent,'Copiar mensaje');assert.match(t.a.setupForm(),/data-copy-setup="1"[^>]*>Copiar mensaje<\/button>/);
 assert.deepEqual(t.model,before);
});

test('an unavailable folder disables copying and never copies a placeholder or claims success',async()=>{
 const t=setup();t.model.setupComplete=false;const before=structuredClone(t.model);
 t.env.navigator={clipboard:{async writeText(){assert.fail('No folder is available');}}};
 const html=t.a.setupForm();assert.match(html,/Cargando ubicación/);assert.match(html,/data-copy-path="1" disabled/);assert.match(html,/data-copy-setup="1"[^>]* disabled/);
 for(const dataset of [{copyPath:'1'},{copySetup:'1'}]){
  await t.click({dataset});assert.match(t.env.document.querySelector('#toast').innerHTML,/ubicación aún no está disponible/);assert.deepEqual(t.model,before);
 }
});

test('help remains accessible before the initial profile is saved',()=>{
 const t=setup();t.model.setupComplete=false;t.a.setScreenState('copias');t.a.render();
 assert.match(t.env.document.querySelector('#main').innerHTML,/Copias de seguridad/);
 assert.doesNotMatch(t.env.document.querySelector('#main').innerHTML,/Vamos a preparar tu perfil/);
});

test('help shows the release identity without changing the initial workflow',()=>{
 const t=setup();t.env.window.StubbsJobsRelease=JSON.parse(fs.readFileSync(require.resolve('../config/release.json'),'utf8'));
 t.model.setupComplete=false;t.a.setScreenState('copias');t.a.render();
 const html=t.env.document.querySelector('#main').innerHTML;
 const release=t.env.window.StubbsJobsRelease;assert.ok(html.includes(`${release.label} · ${release.version} · ${release.platform}`));
 assert.match(html,/<h1>Copias de seguridad<\/h1>/);assert.doesNotMatch(html,/data-copy-setup/);assert.equal(t.model.setupComplete,false);
});

test('initial profile completion shows an explicit welcome instead of an empty offer table',async()=>{
 const t=setup();t.model.setupComplete=false;t.a.setScreenState('configurar');
 const next={...structuredClone(t.model),revision:1,setupComplete:true,onboarding:{status:'ready',token:'synthetic-token',revision:3,workspaceId:t.model.workspaceId,summary:'Perfil confirmado.',needsWelcome:true}};
 next.searchContext={name:'Persona ficticia',targetRoles:'Analista BI'};next.preferences={location:'España'};
 t.env.fetch=async()=>({ok:true,json:async()=>next});await t.a.refresh(true);
 const html=t.env.document.querySelector('#main').innerHTML;assert.match(html,/Tu perfil está preparado/);
 assert.match(html,/Revisar mi perfil/);assert.doesNotMatch(html,/Puedes cambiar tus datos en Mi perfil cuando quieras|Guardar el perfil no inicia una búsqueda/);
});

test('partial onboarding state is rejected without changing the saved model',()=>{
 const t=setup();const invalid={...t.model,onboarding:{status:'ready',token:'synthetic-token',revision:0,workspaceId:'other',needsWelcome:true,summary:'Prueba'}};
 assert.throws(()=>Client.validateState(invalid),/preparación inicial/);assert.equal(t.model.onboarding,undefined);
});
test('the header offers task destinations, search, back and theme',()=>{
 const markup=fs.readFileSync(require.resolve('../app/index.html'),'utf8'),header=markup.split('</header>')[0];
 assert.match(header,/<button type="button" class="brand" data-screen="solicitar" aria-label="Ir a Ofertas"><img src="\/assets\/stubbs.png" alt=""><\/button>/);
 assert.doesNotMatch(header,/<strong>Stubbs Jobs<\/strong>/);
 assert.match(header,/<nav[^>]*>[\s\S]*data-screen="perfil"[\s\S]*data-screen="solicitar"[\s\S]*data-screen="agente"[\s\S]*<\/nav>/);
 assert.doesNotMatch(header,/<nav[^>]*>[\s\S]*data-screen="ayuda"[\s\S]*<\/nav>/);
 assert.match(header,/class="header-menu"[\s\S]*<summary aria-label="Más opciones"[\s\S]*class="header-menu-options"[\s\S]*class="header-help" data-screen="copias" aria-label="Copias de seguridad"[\s\S]*<span>Copias de seguridad<\/span>[\s\S]*class="theme-picker"[\s\S]*<span>Apariencia<\/span>/);
 assert.doesNotMatch(header,/data-screen="elegir"/);
 assert.doesNotMatch(header,/data-screen="ajustes"|data-screen="seguir"/);
 assert.doesNotMatch(header,/id="page-back"|id="header-back"/);assert.match(header,/id="global-search"/);assert.doesNotMatch(markup,/id="pending-work"/);assert.match(markup,/<nav id="page-back"[^>]*hidden><\/nav><main/);
 assert.match(header,/<summary aria-label="Apariencia"[^>]*><svg/);
 for(const choice of ['system','light','dark'])assert.match(header,new RegExp(`data-theme="${choice}"`));
 const t=setup();assert.match(t.a.backupsPage(),/<h1>Copias de seguridad<\/h1>/);assert.doesNotMatch(t.a.backupsPage(),/Acerca de Stubbs Jobs|class="quiet back"/);
});
test('Agente reports real web coverage and dates without retired features',()=>{
 const t=setup();Object.assign(t.model,{health:[{sourceId:'one',company:'Source',status:'ok',checkedAtUtc:'2026-09-22T09:50:00Z'}],publicSources:[{id:'one'},{id:'two'}],lastMail:'2026-09-22T10:00:00Z',lastFullSuccess:'2026-09-22T11:00:00Z',searchContext:{checkMail:true}});
 const settings=t.a.searchSettingsPanels();assert.match(settings,/Especificar webs de búsqueda \(opcional\)/);assert.doesNotMatch(settings,/Incluir mi correo|name="checkMail"|data-mail-check|data-platform=|<legend>Plataformas/);
 const agent=t.a.agentPage();assert.doesNotMatch(agent,/webs revisadas|pendiente|09:50/);assert.doesNotMatch(agent,/<dt>Correo|Búsqueda completa|No incluida|9 de 9/);
 const detail=t.a.coverage();assert.match(detail,/1 de 2 webs revisadas/);assert.doesNotMatch(detail,/Ciclo completo|Sin búsqueda completa registrada/);
});
test('Agente keeps web access problems concrete and does not count unreviewed sources as successful',()=>{
 const t=setup();Object.assign(t.model,{health:[{sourceId:'one',company:'Source',status:'error',checkedAtUtc:'2026-09-22T09:50:00Z',errors:['Necesita acceso al portal']}],publicSources:[{id:'one'},{id:'two'}]});
 const agent=t.a.coverage();assert.match(agent,/0 de 2 webs revisadas/);assert.match(agent,/1 con problemas · 1 pendiente/);assert.match(agent,/Necesita acceso al portal/);assert.doesNotMatch(agent,/data-tone="ok"/);
});
test('a historical mail result does not displace the latest current work',()=>{
 const t=setup();t.model.requests=[{type:'discovery',status:'done',summary:'Búsqueda de webs terminada.',updatedAt:'2026-09-22T09:00:00Z'},{type:'mail',status:'done',summary:'Lectura antigua de correo.',updatedAt:'2026-09-22T10:00:00Z'}];
 const agent=t.a.agentPage();assert.match(agent,/Búsqueda realizada/);assert.doesNotMatch(agent,/Lectura antigua de correo/);
});

test('a preferred portal only shows access after the agent records a check',()=>{
 const t=setup();t.model.searchContext={platforms:'linkedin,indeed'};
 let html=t.a.coverage();assert.match(html,/LinkedIn<\/strong><span>Sin comprobar/);assert.match(html,/Indeed<\/strong><span>Sin comprobar/);
 t.model.portalAccess={linkedin:{status:'login_required',browser:'Navegador del agente',checkedAt:'2026-09-25T09:00:00Z',proof:'El portal pidió iniciar sesión.'}};
 html=t.a.coverage();assert.match(html,/LinkedIn<\/strong><span>Inicia sesión/);assert.doesNotMatch(html,/Ver comprobación/);assert.doesNotMatch(html,/El portal pidió iniciar sesión/);assert.equal(t.model.portalAccess.linkedin.proof,'El portal pidió iniciar sesión.');
 assert.match(html,/Indeed<\/strong><span>Sin comprobar/);
 assert.doesNotMatch(t.a.searchSettingsPanels(),/El portal pidió iniciar sesión|Sin comprobar|Acceso a fuentes/);
});
test('Búsqueda shows search settings directly and Perfil shows personal information',()=>{
 const t=setup();Object.assign(t.model,{searchContext:{name:'Persona de prueba',targetRoles:'Enfermera, Docente',workMode:'Remoto'},preferences:{location:'España'},profile:{currentCity:'Cádiz'},cvLibrary:[{name:'CV-1.pdf',url:'/api/document?id=1'},{name:'CV-2.pdf',url:'/api/document?id=2'}],experience:'Experiencia clínica'});
 const html=t.a.profileForm();assert.doesNotMatch(t.a.applyPage(),/data-copy-agent-command/);assert.doesNotMatch(html,/data-screen="ayuda"|Ver actividad/);assert.match(html,/name="targetRoles"[^>]*>Enfermera, Docente<\/textarea>/);assert.match(html,/name="location"[^>]*value="España"/);assert.match(html,/name="workMode"[^>]*value="Remoto"/);
 const profile=t.a.profileForm();assert.match(profile,/Persona de prueba/);assert.match(profile,/Cádiz/);assert.match(profile,/Experiencia clínica/);assert.match(profile,/CV-1.pdf/);assert.match(profile,/CV-2.pdf/);assert.match(profile,/name="targetRoles"/);assert.match(profile,/name="sourceUrls"/);
 t.model.searchContext.targetRoles='';assert.match(t.a.profileForm(),/name="targetRoles"/);
});
test('all search fields and saved webs are directly visible',()=>{
 const t=setup();t.model.searchContext={languages:'Inglés C1',sourceUrls:'https://example.org/jobs'};
 let html=t.a.searchSettingsPanels();assert.match(t.a.profileForm(),/name="languages" form="profile-search-form"[^>]*>Inglés C1<\/textarea>/);assert.doesNotMatch(html,/name="languages"/);assert.match(html,/<span id="profile-sourceUrls-label">Especificar webs de búsqueda \(opcional\)<\/span><textarea[^>]*>https:\/\/example.org\/jobs<\/textarea>/);
 assert.doesNotMatch(html,/<details|<summary/);
 t.storage.set('stubbs_jobs-draft:busqueda:global','{}');t.storage.set('stubbs_jobs-draft:fuentes:global','{}');
 html=t.a.searchSettingsPanels();assert.match(t.a.profileForm(),/name="languages" form="profile-search-form"/);assert.match(html,/name="sourceUrls"/);
});
test('Búsqueda puts related fields together and has one save for all sources',()=>{
 const t=setup();t.model.searchContext={platforms:'linkedin',checkMail:true,currency:'EUR',sourceUrls:'https://example.org/jobs'};
 t.model.profile={salaryExpectationFixed:35000};t.model.preferences={minimumFixed:35000};
 const html=t.a.searchSettingsPanels();
 const order=['name="targetRoles"','name="keywords"','name="searchPriorities"','name="location"','name="workMode"','name="contract"','name="maxTrips"','name="minimumFixed"','name="salaryExpectationFixed"','name="previousApplications"'];
 for(let i=1;i<order.length;i++)assert.ok(html.indexOf(order[i-1])<html.indexOf(order[i]),`${order[i-1]} antes de ${order[i]}`);
 for(const key of ['targetRoles','keywords'])assert.match(html,new RegExp(`name="${key}"[^>]*rows="1"`));
 assert.match(html,/name="minimumFixed"[^>]*value="35000"[^>]*><input name="currency"[^>]*value="EUR"[\s\S]*name="salaryExpectationFixed"[^>]*value="35000"[^>]*><span data-salary-currency="1">EUR<\/span>/);
 const sources=html.split('data-form="sources"')[1];for(const field of ['platforms','sourceUrls'])assert.match(sources,new RegExp(`name="${field}"`));
 assert.equal((sources.match(/type="submit"/g)||[]).length,0);assert.doesNotMatch(sources,/Guardar fuentes/);assert.equal((t.a.profileForm().match(/data-save-profile="1"/g)||[]).length,1);
 assert.match(sources,/Fuentes priorizadas: LinkedIn/);assert.match(sources,/data-clear-platforms="1">Quitar prioridades/);assert.doesNotMatch(sources,/data-platform=|Sin limitar plataformas|Webs adicionales/);
});
test('a previously saved platform is preserved without appearing as a new choice',()=>{
 const t=setup();t.model.searchContext={platforms:'glassdoor'};
 const html=t.a.searchSettingsPanels();assert.match(html,/name="platforms" value="glassdoor"/);
 assert.match(html,/Fuentes priorizadas: Glassdoor/);assert.match(html,/Quitar prioridades/);assert.doesNotMatch(html,/data-platform="glassdoor"/);
});
test('legacy local schedule does not add a message or a control',()=>{
 const t=setup();t.model.automation={scheduleEnabled:true,searchFrequency:'daily'};
 const html=t.a.searchSettingsPanels();assert.doesNotMatch(html,/programación local|data-schedule-check|data-search-time|Iniciar Codex aquí/);
});
test('ordinary requests use the agent chat while actual pending work stays visible in Summary',()=>{
 const t=setup();t.model.searchContext={targetRoles:'Analista'};t.model.preferences={location:'España'};
 assert.equal(t.a.activityWork(),'');assert.doesNotMatch(t.a.applyPage(),/data-copy-agent-command|Copia la petición/);assert.match(t.a.setupReady(),/Busca ofertas nuevas/);
 t.model.requests=[{status:'queued',type:'review'}];assert.match(t.a.agentPage(),/Pendiente de iniciar/);assert.equal(t.a.activityWork(),'');assert.doesNotMatch(t.a.agentPage(),/activity-work|pídele que continúe en su chat|data-copy-agent-command/);
 t.model.requests=[{status:'blocked',type:'investigate',summary:'Inicia sesión en el portal'}];assert.match(t.a.activityWork(),/Inicia sesión en el portal/);assert.doesNotMatch(t.a.activityWork(),/data-copy-agent-command/);
 t.model.requests=[{status:'running',type:'review',updatedAt:new Date().toISOString()}];assert.match(t.a.activityWork(),/Revisando solicitud/);assert.doesNotMatch(t.a.applyPage(),/data-copy-agent-command/);
 t.model.requests=[];assert.equal(t.a.activityWork(),'');
});

test('work can start without showing missing search criteria as a global notice',()=>{
 const t=setup();t.model.searchContext={targetRoles:''};t.model.execution={status:'starting'};
 assert.match(t.a.agentPage(),/El agente se está iniciando/);assert.doesNotMatch(t.a.agentPage(),/El agente está trabajando|data-copy-agent-command/);
 t.model.execution={status:'idle'};t.model.requests=[{status:'queued',type:'change'}];assert.match(t.a.agentPage(),/Pendiente de iniciar/);assert.equal(t.a.activityWork(),'');
});

test('an agent-owned deadline does not become a personal decision',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí',due:'2020-01-01',requests:[],packages:[],questions:[],missing:['review']}];
 const html=t.a.profileForm();assert.doesNotMatch(html,/Necesita tu decisión/);
 assert.doesNotMatch(html,/Empresa · Hay un plazo cercano/);
});
test('Activity gives the concrete blocker and distinguishes tasks still waiting',()=>{
 const t=setup();t.model.requests=[{status:'queued',type:'change'},{status:'blocked',type:'discovery',need:'access',actionOwner:'user',summary:'Inicia sesión en el portal.'}];
 const html=t.a.agentPage();assert.match(html,/Necesita tu ayuda/);assert.match(html,/Inicia sesión en el portal/);assert.doesNotMatch(html,/data-checks=/);assert.match(html,/Resuélvelo en el chat del agente/);assert.match(html,/1 tarea pendiente de iniciar/);assert.doesNotMatch(html,/data-copy-agent-command|Copiar trabajo en cola/);assert.doesNotMatch(html,/Acceso a portales/);
 assert.match(t.a.coverage(),/<dd>Sin revisión de webs registrada<\/dd>/);
});

test('each available offer keeps its explicit request modes in the detail instead of the table',()=>{
 const t=setup();t.model.automation={applicationMode:'auto'};
 t.model.opportunities=[{id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']}];
 t.a.setSelected('one');const detail=t.a.detail();
 assert.doesNotMatch(t.a.applyPage(),/data-select=|data-investigate=|flow-table-action/);
 assert.match(detail,/<button class="primary request-button" data-select="one" data-selection-mode="review"[^>]*><span class="request-icon" aria-hidden="true"><svg[^>]*data-icon="eye"[\s\S]*?<\/svg><\/span>Solicitar con revisión<\/button>/);
 assert.match(detail,/<button class="primary request-button" data-select="one" data-selection-mode="auto"[^>]*><span class="request-icon" aria-hidden="true"><svg[^>]*data-icon="bot"[\s\S]*?<\/svg><\/span>Auto-solicitud<\/button>/);
 assert.match(detail,/sin tu aprobación final/);assert.match(detail,/aria-describedby="offer-auto-help-one"/);assert.doesNotMatch(detail,/offer-request-options/);
 assert.doesNotMatch(t.a.applyPage(),/data-auto-setting|Contacto con reclutadores/);
 t.a.setSelected(null);assert.doesNotMatch(t.a.profileForm(),/Cambiar valor propuesto/);
 const index=fs.readFileSync(require.resolve('../app/index.html'),'utf8');
 assert.doesNotMatch(index,/id="choose-mode"|name="selectionMode"/);
 assert.doesNotMatch(t.a.applyPage(),/guardan la solicitud para el agente|Con revisión, tú autorizas/);
});

test('direct selection uses its explicit mode and retains the stage, column filter and sort',async()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};
 t.model.automation={applicationMode:'auto',contactMode:'ask'};
 t.model.opportunities=[{...base,id:'one',salary:'40.000 EUR'},{...base,id:'two',salary:'35.000 EUR'},{...base,id:'three',salary:'45.000 EUR'},{...base,id:'other',company:'Otra',salary:'37.000 EUR'}];
 t.a.setFlowFilter('solicitar','sin-elegir');t.a.setTableFilter('solicitar','company',['Empresa']);t.a.setTableSort('solicitar','salary',-1);
 const before=t.a.applyPage();assert(before.indexOf('data-job-row="three"')<before.indexOf('data-job-row="one"'));
 let submitted;
 t.env.fetch=async(path,options)=>{assert.equal(path,'/api/action');submitted=JSON.parse(options.body).operation;const state=structuredClone(t.model);state.opportunities[0].selection={selected:true,mode:submitted.mode};state.opportunities[0].requests=[{type:'review',status:'queued'}];return {ok:true,json:async()=>({state})};};
 assert.equal(await t.a.selectOpportunity('one','review'),true);
 assert.equal(submitted.mode,'review');assert.equal(submitted.opportunityId,'one');
 const after=t.a.applyPage();assert.match(after,/data-flow-filter="sin-elegir"[^>]*aria-pressed="true"/);assert.doesNotMatch(after,/data-job-row="one"|data-job-row="other"/);
 assert(after.indexOf('data-job-row="three"')<after.indexOf('data-job-row="two"'));assert.match(after,/data-clear-table="solicitar"/);
});

test('automatic selection keeps the all-offers filter and records only the clicked offer',async()=>{
 const t=setup(),job={id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[job];t.model.automation={applicationMode:'review'};
 t.env.fetch=async(_,options)=>{const op=JSON.parse(options.body).operation;assert.equal(op.mode,'auto');const state=structuredClone(t.model);state.opportunities[0].selection={selected:true,mode:op.mode};state.opportunities[0].requests=[{type:'review',status:'queued'}];return {ok:true,json:async()=>({state})};};
 assert.equal(await t.a.selectOpportunity('one','auto'),true);
 assert.match(t.env.document.querySelector('#toast').innerHTML,/Para iniciar la preparación[\s\S]*Continúa con Stubbs Jobs[\s\S]*chat del agente/);
 const html=t.a.applyPage();assert.match(html,/data-flow-filter="todas"[^>]*aria-pressed="true"/);assert.match(html,/data-job-row="one"/);assert.doesNotMatch(html,/Auto-solicitud|class="selection-mode"|data-select="one"/);t.a.setSelected('one');assert.match(t.a.detail(),/offer-selection-mode">Auto-solicitud/);
});

test('selection without a mode never submits a request',async()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa'}];let called=false;t.env.fetch=async()=>{called=true;};
 await assert.rejects(t.a.selectOpportunity('one'),/Selecciona cómo/);assert.equal(called,false);
});

test('a preserved table render retains both horizontal and page scrolling',()=>{
 const t=setup(),main=t.env.document.querySelector('#main'),previousQuery=main.querySelector.bind(main);
 let table={scrollLeft:690};Object.defineProperty(main,'innerHTML',{set(){table={scrollLeft:0};}});
 main.querySelector=selector=>selector==='.workflow-table-wrap'?table:previousQuery(selector);
 let pageScroll;t.env.window.scrollY=420;t.env.window.scrollTo=(x,y)=>{pageScroll=[x,y];};
 t.a.render(true);assert.equal(table.scrollLeft,690);assert.deepEqual(pageScroll,[0,420]);
});

test('a blocked access request explains the next step and retains queued clarification',()=>{
 const t=setup(),job={id:'one',company:'Empresa de prueba',title:'Role',state:'Preparar',requests:[{type:'review',status:'blocked',need:'access',summary:'Falta iniciar sesión.'},{type:'change',status:'queued',instructions:[{text:'Ya abrí mi cuenta.'}]}],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[job];t.a.setSelected('one');const html=t.a.changeForm();
 assert.match(html,/Aclarar el acceso/);assert.match(html,/Falta iniciar sesión/);assert.match(html,/Ya abrí mi cuenta/);assert.match(html,/No escribas contraseñas/);assert.match(html,/bloqueo seguirá vigente/);
});
test('one offers list shows each process exactly once and keeps its state',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[
  {...base,id:'choose',company:'Elegible',apply:'Sí'},
  {...base,id:'checking',company:'Por comprobar',apply:'Revisar',requests:[{type:'investigate',status:'queued'}]},
  {...base,id:'apply',company:'Elegida',selection:{selected:true,mode:'review'}},
  {...base,id:'sent',company:'Enviada',sent:{at:'2026-09-22T12:00:00Z'}},
  {...base,id:'closed',company:'Cerrada',state:'Rechazada'}
 ];
 const all=t.a.applyPage();
 for(const id of ['choose','checking','apply','sent','closed'])assert.equal((all.match(new RegExp(`data-job-row="${id}"`,'g'))||[]).length,1);
 assert.match(all,/data-tone="action" data-anchor="job-choose"/);assert.match(all,/data-tone="working" data-anchor="job-checking"/);
 assert.match(all,/data-tone="sent" data-anchor="job-sent"/);assert.match(all,/data-tone="past" data-anchor="job-closed"/);
 assert.doesNotMatch(all,/Candidaturas previas|Descargar Excel/);assert.doesNotMatch(all,/data-auto-setting/);
 t.a.setFlowFilter('solicitar','elegidas');const chosen=t.a.applyPage();assert.match(chosen,/data-job-row="apply"/);assert.doesNotMatch(chosen,/data-job-row="choose"|data-job-row="sent"/);
});
test('offer filters keep chosen, waiting, unsuitable and earlier processes accessible',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[
  {...base,id:'ready',company:'Lista',apply:'Sí'},
  {...base,id:'waiting',company:'En cola',apply:'Revisar',requests:[{type:'investigate',status:'queued'}]},
  {...base,id:'chosen',company:'Elegida',selection:{selected:true,mode:'review'}},
  {...base,id:'unsuitable',company:'Descartada',apply:'No'},
  {...base,id:'sent',company:'Actual',sent:{at:'2026-09-22T12:00:00Z'}}
 ];
 t.model.historical=[{id:'older',company:'Anterior',title:'Analista',state:'Rechazada',category:'Laboral'}];
 let html=t.a.applyPage();assert.match(html,/Por decidir <span class="filter-count">3<\/span>/);assert.match(html,/En preparación <span class="filter-count">1<\/span>/);assert.match(html,/data-job-row="ready"/);assert.match(html,/data-job-row="waiting"/);assert.match(html,/data-job-row="unsuitable"/);assert.match(html,/data-job-row="chosen"/);assert.match(html,/data-job-row="historical:older"/);
 t.a.setFlowFilter('solicitar','elegidas');html=t.a.applyPage();assert.match(html,/data-job-row="chosen"/);assert.doesNotMatch(html,/data-job-row="ready"|data-job-row="unsuitable"/);
 t.a.setFlowFilter('solicitar','enviadas');html=t.a.applyPage();assert.match(html,/data-job-row="sent"/);assert.doesNotMatch(html,/data-job-row="historical:older"/);
 t.a.setFlowFilter('solicitar','rechazadas');html=t.a.applyPage();assert.match(html,/data-job-row="historical:older"/);assert.doesNotMatch(html,/data-job-row="sent"/);
});
test('an unverified offer cannot be selected and a queued investigation stays queued',()=>{
 const t=setup(),job={id:'fresh',company:'Ficticia',title:'Artista',state:'Preparar',apply:'Revisar',requests:[{type:'investigate',status:'queued'}],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[job];let html=t.a.applyPage();
 assert.match(html,/>Por decidir<\/span>/);assert.doesNotMatch(html,/data-select="fresh"|data-investigate="fresh"/);
 t.a.setSelected('fresh');assert.doesNotMatch(t.a.detail(),/data-select=|data-investigate=/);
 job.requests=[];html=t.a.applyPage();assert.doesNotMatch(html,/Pedir comprobación|data-select="fresh"/);assert.match(t.a.detail(),/data-investigate="fresh"/);assert.match(html.split('<tbody>')[1],/data-offer-state="sin-elegir" class="flow-status"/);
 job.apply='Sí';html=t.a.applyPage();assert.doesNotMatch(html,/data-select=/);assert.match(t.a.detail(),/data-select="fresh" data-selection-mode="review"[^>]*>[\s\S]*?Solicitar con revisión<\/button>/);assert.match(html.split('<tbody>')[1],/data-offer-state="sin-elegir" class="flow-status"/);
 job.requests=[{type:'change',status:'queued'}];html=t.a.applyPage();assert.doesNotMatch(html,/data-select="fresh"/);assert.doesNotMatch(t.a.detail(),/data-select="fresh"/);
});
test('a blocked offer and queued offer both stay directly visible',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',apply:'Revisar',packages:[],questions:[],missing:['review']};
 t.model.opportunities=[
  {...base,id:'blocked',company:'Necesita acceso',requests:[{type:'investigate',status:'blocked',need:'access',summary:'Inicia sesión.'}]},
  {...base,id:'waiting',company:'En espera',requests:[{type:'investigate',status:'queued'}]}
 ];
 const html=t.a.applyPage();assert.match(html,/data-job-row="blocked"/);assert.match(html,/data-job-row="waiting"/);
 assert.match(html,/data-tone="blocked" data-anchor="job-blocked"/);
 assert.match(html,/>Por atender<\/span>/);assert.doesNotMatch(html,/data-select=|data-resolve=/);t.a.setSelected('blocked');assert.match(t.a.detail(),/data-resolve="blocked"/);
 assert.doesNotMatch(html,/Necesita aclaración|Pendiente de comprobar/);
});
test('source errors and dates remain in preserved diagnostics',()=>{
 const t=setup();Object.assign(t.model,{health:[{company:'Prueba',status:'partial',checkedAtUtc:'2026-09-25T09:00:00Z'}],fieldDefinitions:{},searchContext:{},profile:{},preferences:{}});
 const html=t.a.coverage();assert.match(html,/Prueba · Cobertura sin completar/);assert.match(html,/Último intento: 25 sept 2026, 11:00/);
});
test('Activity omits routine changes while preserving the original history',()=>{
 const t=setup();t.model.history=[{at:'2026-09-24T08:00:00Z',title:'Encargo anterior'},{at:'2026-09-25T09:00:00Z',title:'Búsqueda actualizada'}];
 assert.doesNotMatch(t.a.agentPage(),/Encargo anterior|Búsqueda actualizada|Ver historial/);
 assert.match(t.a.history(),/Tarea anterior/);assert.match(t.a.history(),/Búsqueda actualizada/);assert.equal(t.model.history.length,2);
});

test('an old execution failure does not resurface after later confirmed activity',()=>{
 const t=setup();t.model.execution={status:'failed',message:'Error antiguo',updatedAt:'2026-09-23T18:52:00Z'};
 assert.match(t.a.agentPage(),/Error antiguo/);
 t.model.history=[{title:'Búsqueda actualizada',at:'2026-09-26T21:09:00Z',actor:'Usuario'}];assert.doesNotMatch(t.a.agentPage(),/Error antiguo|Búsqueda actualizada/);
 assert.equal(t.model.execution.message,'Error antiguo');
});

test('undo for a routine save remains in the header and history without adding feed noise',()=>{
 const t=setup();t.model.setupComplete=true;t.model.history=[{id:'change-1',title:'Búsqueda actualizada',at:'2026-09-26T21:09:00Z',actor:'Usuario'}];t.model.undo=[{id:'change-1',actor:'Usuario',title:'Búsqueda actualizada'}];
 t.a.setScreenState('agente');t.a.render();assert.equal(t.headerUndo.hidden,false);assert.equal(t.headerUndo.dataset.undo,'change-1');
 assert.doesNotMatch(t.a.agentPage(),/Búsqueda actualizada|data-undo/);assert.match(t.a.history(),/data-undo="change-1"/);
});

test('current blockers stay concise and the preserved diagnostics retain full evidence',()=>{
 const t=setup();t.model.health=[{company:'Fuente ficticia',status:'partial',checkedAtUtc:'2026-09-25T09:00:00Z',lastSuccessUtc:'2026-09-24T09:00:00Z',errors:['Página 2 no disponible']}];
 t.model.requests=[{type:'discovery',status:'blocked',updatedAt:'2026-09-25T10:00:00Z',summary:'Acceso pendiente',result:'No se revisó la página',instructions:[{text:'Revisar el acceso'}]}];
 t.model.history=Array.from({length:35},(_,i)=>({at:'2026-09-25T10:00:00Z',title:`Cambio ${i+1}`,actor:'Agente'}));
 const html=t.a.agentPage();assert.match(html,/Acceso pendiente/);assert.doesNotMatch(html,/No se revisó la página|Revisar el acceso|Cambio 35|Página 2 no disponible/);
 for(const text of ['Último éxito:','Último intento:'])assert.ok(t.a.coverage().includes(text),text);assert.equal(t.model.requests[0].result,'No se revisó la página');assert.equal(t.model.requests[0].instructions[0].text,'Revisar el acceso');
 assert.match(t.a.history(),/Cargar anteriores/);t.a.setHistoryLimit(60);assert.match(t.a.history(),/Cambio 1<\/strong>/);assert.match(t.a.history(),/Cambio 35<\/strong>/);
});

test('a completed search replaces an old failure with an honest count and a direct offer link',()=>{
 const t=setup();t.model.execution={status:'failed',message:'Fallo antiguo',updatedAt:'2026-09-23T10:00:00Z'};
 const proof='Detalle completo conservado. '.repeat(100);
 t.model.requests=[{type:'discovery',status:'done',updatedAt:'2026-09-28T09:00:00Z',summary:'Búsqueda terminada: 3 ofertas guardadas para elegir. No se ha enviado nada.',result:proof}];
 const html=t.a.agentPage();assert.match(html,/3 ofertas preseleccionadas/);assert.match(html,/data-search-offers="1">Ver ofertas/);assert.doesNotMatch(html,/Fallo antiguo|Detalle completo conservado/);
 assert.equal(t.model.requests[0].result,proof);
 t.model.requests[0].status='queued';assert.doesNotMatch(t.a.agentPage(),/3 ofertas preseleccionadas/);assert.match(t.a.agentPage(),/Pendiente de iniciar/);
});

test('a result without an accredited count does not invent offers or copy technical proof into the summary',()=>{
 const t=setup(),proof='Resultado confirmado con sus límites. '.repeat(100);
 t.model.requests=[{type:'discovery',status:'done',updatedAt:'2026-09-28T09:00:00Z',result:proof}];
 const html=t.a.agentPage();assert.ok(html.length<2500);assert.match(html,/Búsqueda realizada/);assert.doesNotMatch(html,/0 nuevas ofertas|Resultado confirmado/);assert.equal(t.model.requests[0].result,proof);
});

test('Activity uses the latest completed offer task with a direct link and excludes cancellations',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa ficticia'}];
 t.model.requests=[{type:'discovery',status:'done',updatedAt:'2026-09-28T09:00:00Z',summary:'Búsqueda terminada'},
 {type:'change',status:'done',opportunityId:'one',updatedAt:'2026-09-28T12:00:00Z',summary:'Solicitud corregida, sin enviar.'},
 {type:'review',status:'cancelled',opportunityId:'one',updatedAt:'2026-09-28T12:01:00Z',result:'Revisión duplicada cancelada'}];
 const html=t.a.agentPage();assert.match(html,/Solicitud actualizada: Empresa ficticia/);assert.match(html,/Solicitud corregida, sin enviar/);assert.match(html,/data-job="one">Ver solicitud/);assert.doesNotMatch(html,/Revisión duplicada cancelada|data-report/);
});

test('Activity distinguishes a queued task from starting and actual work',()=>{
 const t=setup();t.model.requests=[{type:'review',status:'queued'}];
 let html=t.a.activityWork();assert.equal(html,'');assert.match(t.a.agentPage(),/Comprobar solicitud/);assert.match(t.a.agentPage(),/Pendiente de iniciar/);assert.doesNotMatch(t.a.agentPage(),/El agente está trabajando|activity-work/);
 t.model.execution={status:'starting'};html=t.a.activityWork();assert.match(html,/El agente se está iniciando/);assert.doesNotMatch(html,/El agente está trabajando/);
 t.model.execution={status:'idle'};t.model.requests[0].status='running';t.model.requests[0].updatedAt=new Date().toISOString();html=t.a.activityWork();assert.match(html,/Revisando solicitud/);assert.doesNotMatch(html,/pendiente de iniciar/);
});

test('pending offer decisions stay visible in the table and actionable only in their detail',()=>{
 const t=setup();t.model.opportunities=['one','two'].map(id=>({id,company:'Empresa '+id,title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],selection:{selected:true,mode:'review'}}));
 const table=t.a.applyPage();assert.equal((table.match(/>Por atender<\/span>/g)||[]).length,2);assert.doesNotMatch(table,/data-review=/);
 for(const id of ['one','two']){t.a.setSelected(id);assert.match(t.a.detail(),new RegExp(`data-review="${id}"`));}
 assert.doesNotMatch(t.a.agentPage(),/data-review=|Empresa one|Empresa two|Necesita tu ayuda/);t.a.setSelected(null);assert.doesNotMatch(t.a.profileForm(),/data-review=|Empresa one|Empresa two/);
});

test('activity ages use singular and plural minutes, hours and days with future dates handled',()=>{
 const t=setup(),now=Date.parse('2026-09-28T12:00:00Z');
 for(const [elapsed,text] of [[0,'Ahora'],[60000,'Hace 1 minuto'],[25*60000,'Hace 25 minutos'],[3600000,'Hace 1 hora'],[3*3600000,'Hace 3 horas'],[86400000,'Hace 1 día'],[25*86400000,'Hace 25 días'],[-3*3600000,'Dentro de 3 horas']])assert.equal(t.a.relativeTime(new Date(now-elapsed).toISOString(),now),text);
 assert.equal(t.a.relativeTime(null,now),'—');assert.equal(t.a.relativeTime('invalid',now),'—');
});
test('date-only activity uses calendar days without inventing an hour, including a daylight saving change',()=>{
 const t=setup(),morning=Date.parse('2026-09-28T06:00:00Z');
 assert.equal(t.a.relativeTime('2026-09-28',morning),'Hoy');assert.equal(t.a.relativeTime('2026-09-27',morning),'Hace 1 día');assert.equal(t.a.relativeTime('2026-09-29',morning),'Dentro de 1 día');
 assert.equal(t.a.relativeTime('2026-10-25',Date.parse('2026-10-26T06:00:00Z')),'Hace 1 día');
});
test('unchanged state refreshes ages without rebuilding the page or clearing date filters',async()=>{
 const t=setup(),cell={dataset:{activityAt:new Date(Date.now()-3*3600000).toISOString()},textContent:'Hace 2 horas'},found={dataset:{foundAt:new Date(Date.now()-12*60000).toISOString()},textContent:'Hace 11 min'};
 const main=t.env.document.querySelector('#main');const old=main.querySelectorAll.bind(main);main.querySelectorAll=selector=>selector==='[data-activity-at]'?[cell]:selector==='[data-found-at]'?[found]:old(selector);
 t.env.fetch=async()=>({ok:true,json:async()=>({...t.model,version:'same-view'})});await t.a.refresh();
 main.innerHTML='Unchanged page';t.a.setTableFilter('solicitar','activity',['fixed-timestamp']);
 t.env.fetch=async()=>({ok:true,json:async()=>({unchanged:true,version:'same-view'})});await t.a.refresh();assert.equal(cell.textContent,'Hace 3 horas');assert.equal(found.textContent,'Hace 12 min');assert.equal(main.innerHTML,'Unchanged page');assert.deepEqual(Array.from(t.a.getTableState().filters.activity),['fixed-timestamp']);
});
test('a saved legacy region appears in the single search zone without an extra field',()=>{
 const t=setup();t.model.searchContext={regions:'Portugal',currency:'EUR'};t.model.preferences={location:'España',minimumFixed:32000};
 const html=t.a.searchSettingsPanels();assert.match(html,/name="location"[^>]*value="España; Portugal"/);assert.match(html,/name="minimumFixed"[^>]*value="32000"[^>]*><input name="currency"[^>]*value="EUR"/);
 assert.doesNotMatch(html,/name="regions"|Otras zonas|Moneda del sueldo mínimo/);
});
test('an unsaved old region remains visible and editable in the single zone',()=>{
 const t=setup();t.a.setScreenState('perfil');t.model.searchContext={regions:'Portugal',workMode:'Remoto'};t.model.preferences={location:'España'};
 const key='stubbs_jobs-draft:busqueda:global';t.storage.set(key,JSON.stringify({values:{location:'España',workMode:'Remoto',regions:'Francia'},expected:{location:'España',workMode:'Remoto',regions:'Portugal'},shown:{location:'España',workMode:'Remoto',regions:'Portugal'}}));
 const location={value:'',dataset:{type:'text'}},mode={value:'',dataset:{type:'text'}},info={textContent:''};const form={dataset:{form:'search'},values:{get location(){return location.value;},get workMode(){return mode.value;}},_expected:{location:'España',workMode:'Remoto'},_shown:{location:'España; Portugal',workMode:'Remoto'},elements:{namedItem(name){return {location,workMode:mode}[name]||null;}},querySelector(){return info;}};
 t.a.restoreForm(form);assert.equal(location.value,'España; Francia');assert.equal(mode.value,'Remoto');assert.equal(form._shown.location,'España; Portugal');assert.equal(form._expected.regions,'Portugal');assert.equal(form.dataset.mergedRegions,'1');assert.equal(info.textContent,'');
});
test('inline proposed permissions leave a chosen offer and its state unchanged',()=>{
 const t=setup(),job={id:'one',company:'Empresa',title:'Analista',state:'Preparar',selection:{selected:true,mode:'auto'},requests:[{type:'review',status:'queued'}],packages:[],questions:[],missing:['review'],salary:'45.000 EUR',conditions:{'Remoto España':'Sí',Indefinido:'Sí'}};
 t.model.opportunities=[job];t.a.setFlowFilter('solicitar','elegidas');const html=t.a.applyPage();
 assert.match(html,/>En preparación<\/span>/);assert.match(html,/45.000 €/);assert.doesNotMatch(html,/data-auto-setting|Auto-solicitud|class="selection-mode"/);assert.doesNotMatch(html,/data-screen="opciones-solicitud"|Modo elegido:|Has elegido ofertas|flow-handoff|Remoto · Indefinido/);t.a.setSelected('one');assert.match(t.a.detail(),/offer-selection-mode">Auto-solicitud/);
 assert.equal(job.selection.mode,'auto');
 assert.doesNotMatch(html,/data-select="one"/);
});
test('offer table filters every column and sorts published salaries without treating ceilings as minimums',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[
  {...base,id:'higher',company:'Beta',salary:'45.000 EUR'},
  {...base,id:'lower',company:'Álfa',salary:'35.000–49.000 EUR'},
  {...base,id:'ceiling',company:'Gamma',salary:'Hasta 48.000 EUR'}
 ];
 let html=t.a.applyPage();
 assert.match(html,/<table class="workflow-table">/);assert.match(html,/class="workflow-table-wrap" role="region"[^>]*tabindex="0"/);assert.doesNotMatch(html,/data-toggle-view|workflow-card-list|Ver tarjetas|Ver tabla/);
 for(const key of ['company','title','country','mode','contract','salary','status']){assert.match(html,new RegExp(`data-table-sort="${key}"`));assert.match(html,new RegExp(`data-menu-key="${key}"`));}
 assert.doesNotMatch(html,/data-table-sort="activity"|data-menu-key="activity"/);
 assert.match(html,/data-table-option-search="1"/);assert.match(html,/data-table-select-visible="all"/);assert.doesNotMatch(html,/data-table-value=/);assert.equal(t.a.columnCatalog('solicitar','company').labels['Álfa'],'Álfa');
 assert.match(html,/data-job-row="lower"/);assert.match(html,/data-job="lower"[^>]*>[\s\S]*?<span class="company-name">Álfa<\/span>/);assert.doesNotMatch(html,/data-select="lower"/);
 t.a.setTableSort('solicitar','salary');html=t.a.applyPage();
 assert.deepEqual([...html.matchAll(/data-job-row="([^"]+)"/g)].map(match=>match[1]),['lower','higher','ceiling']);
 t.a.setTableSort('solicitar','salary',-1);html=t.a.applyPage();
 assert.deepEqual([...html.matchAll(/data-job-row="([^"]+)"/g)].map(match=>match[1]),['higher','lower','ceiling']);
 t.a.setTableFilter('solicitar','company',['Álfa']);html=t.a.applyPage();assert.match(html,/data-job-row="lower"/);assert.doesNotMatch(html,/data-job-row="higher"|data-job-row="ceiling"/);assert.match(html,/1 oferta de 3/);
 assert.equal(t.a.salaryNumber('38–49 k€ base'),38000);assert.equal(t.a.salaryNumber('Hasta 48.000 EUR'),null);
 assert.equal(t.a.salaryInfo('35.000–49.000 €; fijo sin especificar').note,'Fijo sin confirmar');
 assert.equal(t.a.salaryInfo('Hasta 48.000 € fijos + 5.000 € variable').kind,'ceiling');
 assert.equal(t.a.salaryInfo('38–49 k€ base; cifras contradictorias').kind,'ambiguous');
 assert.match(html,/35.000–49.000 €/);assert.doesNotMatch(html,/salary-track|salary-band|Escala salarial/);
 t.a.setTableFilter('solicitar','company',[]);html=t.a.applyPage();assert.match(html,/Ninguna oferta coincide con estos filtros/);assert.match(html,/Limpiar filtros/);
});
test('published salaries preserve unsupported or ambiguous currency and nonannual units independently of the profile',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};
 const untouched=['80.000–100.000 CAD','95.000CHF','120kAUD','8.000.000 JPY','90.000 CNY','60000 $','75.000 ¥','40.000 EUR / 50.000 USD','35.000 USD y 40.000 pesos','35.000 USD más 2.000 yenes','35.000 USD y 40.000 francos','35.000 USD y 40.000 dólares canadienses','35.000 USD + C$2000','35.000 USD + 40.000 Australian dollars','3500 € / mes','2.500 GBP mensual','50000 USD per month','1500 EUR/h','40.000 EUR por hora','50.000 USD hourly','2000 EUR por semana','80000 USD a month'];
 for(const currency of ['EUR','USD','CAD']){
  t.model.searchContext.currency=currency;
  for(const raw of untouched){assert.equal(t.a.salaryInfo(raw).label,raw,raw);assert.equal(t.a.salaryNumber(raw),null,raw);}
  assert.equal(t.a.salaryInfo('40.000 EUR brutos/año').label,'40.000 €');assert.equal(t.a.salaryInfo('80.000 USD annually').label,'80.000 USD');assert.equal(t.a.salaryInfo('60.000 £ yearly').label,'60.000 GBP');
 }
 t.model.opportunities=[{...base,id:'cad',company:'Canadiense ficticia',salary:untouched[0]},{...base,id:'monthly',company:'Mensual ficticia',salary:'3500 € / mes'},{...base,id:'annual',company:'Anual ficticia',salary:'40.000 EUR brutos/año'}];
 t.a.setTableSort('solicitar','salary');const html=t.a.applyPage();assert.deepEqual([...html.matchAll(/data-job-row="([^"]+)"/g)].map(match=>match[1]),['annual','cad','monthly']);
 assert.match(html,/<span>80\.000–100\.000 CAD<\/span>/);assert.match(html,/<span>3500 € \/ mes<\/span>/);assert.match(html,/<span>40\.000 €<\/span>/);
 assert.equal(t.model.opportunities[0].salary,untouched[0]);assert.deepEqual(t.model.requests,[]);
});
test('the unified table orders historical activity and keeps state last',()=>{
 const t=setup();t.model.opportunities=[];t.model.historical=[
  {id:'old',company:'Empresa A',title:'Analista',state:'Rechazada',category:'Laboral',lastActivityLabel:'11 may 2026'},
  {id:'recent',company:'Empresa B',title:'Analista',state:'Rechazada',category:'Laboral',lastActivityLabel:'09 sep 2026'}
 ];
 t.a.setFlowFilter('solicitar','rechazadas');
 t.a.setTableSort('solicitar','activity',-1);const html=t.a.applyPage();
 assert.deepEqual([...html.matchAll(/data-job-row="([^"]+)"/g)].map(match=>match[1]),['historical:recent','historical:old']);
 assert.doesNotMatch(html,/data-menu-key="activity"/);assert.match(html,/Orden: Actividad ↓/);assert.match(html,/data-table-sort="status"/);assert.match(html,/data-menu-key="mode"/);
});
test('offer table filters equivalent labels together and preserves the original offer data',()=>{
 const t=setup(),base={title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[]};
 t.model.opportunities=[{...base,id:'a',company:'Uno',country:'Spain',workMode:'Remoto',contract:'Permanent',schedule:'7:30 - 15:30 h'},
 {...base,id:'b',company:'Dos',country:'España',workMode:'100% remoto',contract:'Indefinido',schedule:'07:30-15:30'},
 {...base,id:'c',company:'Tres',country:'España',workMode:'Híbrido',contract:'Temporal',schedule:'No concretado en el anuncio'}];
 const before=structuredClone(t.model),ids=html=>[...html.matchAll(/data-job-row="([^"]+)"/g)].map(m=>m[1]);
 t.a.applyPage();assert.deepEqual([...t.a.columnCatalog('solicitar','mode').values],['Híbrido','Remoto']);
 assert.deepEqual([...t.a.columnCatalog('solicitar','country').values],['España']);
 assert.deepEqual([...t.a.columnCatalog('solicitar','schedule').values],['—','07:30–15:30']);
 // A prior page filter expressed with the old label still selects the same remote offers.
 t.a.setTableFilter('solicitar','mode',['100% remoto']);t.a.setTableFilter('solicitar','contract',['Permanent']);
 t.a.setTableFilter('solicitar','schedule',['7:30 - 15:30 h']);assert.deepEqual(ids(t.a.applyPage()).sort(),['a','b']);
 t.a.setQuery('Analista');t.a.setTableFilter('encontrar','mode',['Remoto']);assert.deepEqual(ids(t.a.findResults()).sort(),['a','b']);assert.deepEqual(t.model,before);
});

test('first discovery day groups searches and sorts chronologically across years with missing dates last',()=>{
 const t=setup(),base={title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[]};
 t.model.opportunities=[{...base,id:'latest',company:'Actual',firstSeenAt:'2026-10-07'},
 {...base,id:'old',company:'Anterior',firstSeenAt:'2025-10-07'},
 {...base,id:'same-day',company:'Misma búsqueda',firstSeenAt:'2026-10-07'},
 {...base,id:'missing',company:'Sin fecha'}, {...base,id:'invalid',company:'Fecha dañada',firstSeenAt:'2026-02-30'}];
 const before=structuredClone(t.model),ids=html=>[...html.matchAll(/data-job-row="([^"]+)"/g)].map(m=>m[1]);
 t.a.setTableSort('solicitar','firstSeen');let html=t.a.applyPage();assert.deepEqual(ids(html),['old','latest','same-day','invalid','missing']);
 assert.match(html,/<time data-found-at="2025-10-07" datetime="2025-10-07" title="Primera detección: 7 oct 2025">[^<]+<\/time>/);
 const catalog=t.a.columnCatalog('solicitar','firstSeen');assert.equal(catalog.values.length,3);assert(catalog.values.includes('—'));
 assert.equal(catalog.labels[String(new Date('2026-10-07T12:00:00').getTime())],'7 oct 2026');
 t.a.setTableSort('solicitar','firstSeen',-1);assert.deepEqual(ids(t.a.applyPage()),['latest','same-day','old','invalid','missing']);
 t.a.setTableFilter('solicitar','firstSeen',[String(new Date('2026-10-07T12:00:00').getTime())]);assert.deepEqual(ids(t.a.applyPage()),['latest','same-day']);
 t.a.setTableFilter('solicitar','firstSeen',['—']);assert.deepEqual(ids(t.a.applyPage()),['invalid','missing']);assert.deepEqual(t.model,before);
});

test('relative discovery labels keep exact chronology and absolute day filters in both tables',()=>{
 const t=setup(),now=Date.parse('2026-10-07T12:00:00Z'),base={title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[]};
 t.env.Date=class extends Date{static now(){return now;}};
 t.model.opportunities=[{...base,id:'older-minute',company:'A',firstSeenAt:'2026-10-07T11:48:00Z'},{...base,id:'latest-minute',company:'Z',firstSeenAt:'2026-10-07T11:57:00Z'},{...base,id:'older-year',company:'C',firstSeenAt:'2024-02-16'},{...base,id:'missing',company:'D'}];
 const before=structuredClone(t.model),ids=html=>[...html.matchAll(/data-job-row="([^"]+)"/g)].map(m=>m[1]);
 let html=t.a.applyPage();assert.deepEqual(ids(html),['latest-minute','older-minute','older-year','missing']);
 assert.match(html,/<time data-found-at="2026-10-07T11:57:00Z" datetime="2026-10-07T11:57:00Z" title="Primera detección: 7 oct 2026, 13:57">Hace 3 min<\/time>/);assert.match(html,/>Hace 12 min<\/time>/);assert.match(html,/>Feb 2024<\/time>/);
 t.a.setTableSort('solicitar','firstSeen',1);assert.deepEqual(ids(t.a.applyPage()),['older-year','older-minute','latest-minute','missing']);
 t.a.setTableSort('solicitar','firstSeen',-1);assert.deepEqual(ids(t.a.applyPage()),['latest-minute','older-minute','older-year','missing']);
 const catalog=t.a.columnCatalog('solicitar','firstSeen');assert.equal(catalog.values.length,3);assert(catalog.values.includes('—'));assert(Object.values(catalog.labels).includes('7 oct 2026'));assert.doesNotMatch(JSON.stringify(catalog.labels),/Hace /);
 t.a.setTableFilter('solicitar','firstSeen',[String(new Date('2026-10-07T12:00:00').getTime())]);assert.deepEqual(ids(t.a.applyPage()),['latest-minute','older-minute']);
 t.a.setScreenState('buscar');t.a.setQuery('Analista');assert.match(t.a.findResults(),/>Hace 3 min<\/time>/);assert.match(t.a.findResults(),/>Feb 2024<\/time>/);assert.deepEqual(t.model,before);
});

test('all source facts appear in Conditions while consultation links accompany their date',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'ABAP',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},country:'España',workMode:'100% remoto',contract:'Indefinido',salary:'No publicado; según experiencia',schedule:'07:30-15:30 habitual; 08:00-15:00 verano',assessment:{isCurrent:true,reason:'Requiere aprender SAP.',references:[{url:'https://example.org/jobs/one',text:'07:30-15:30 habitual; 08:00-15:00 verano; 100% remoto; No publicado; según experiencia. 1-2 años junior o 3-5 años middle; ABAP con CFM/TRM o PM Distribución'}]}};
 t.model.opportunities=[job];t.a.setSelected(job.id);const before=structuredClone(job),html=t.a.detail();
 const assessment=html.match(/<section class="case-section offer-assessment">([\s\S]*?)<\/section>/)[1];assert.match(assessment,/href="https:\/\/example.org\/jobs\/one"[^>]*>Fuentes consultadas<\/a>/);assert.doesNotMatch(assessment,/Fuente del anuncio|assessment-evidence|no garantiza|1-2 años junior|ABAP con CFM\/TRM|15:30|remoto|No publicado|según experiencia/);
 const conditions=t.a.offerConditions(job);assert.match(conditions,/<dt>País<\/dt><dd>España<\/dd>/);assert.match(conditions,/<dt>Modalidad<\/dt><dd>Remoto<\/dd>/);assert.equal((conditions.match(/07:30–15:30/g)||[]).length,1);assert.match(conditions,/No publicado; según experiencia/);assert.match(conditions,/<dt>Experiencia requerida<\/dt><dd>1-2 años junior o 3-5 años middle<\/dd>/);assert.match(conditions,/<dt>Tecnologías<\/dt><dd>ABAP con CFM\/TRM o PM Distribución<\/dd>/);assert.deepEqual(job,before);
});

test('each offer tab defaults to its own actual milestone date and a chosen column order can be restored',async()=>{
 const t=setup(),base={title:'Analista',apply:'Sí',requests:[],packages:[],questions:[],missing:[]};
 const old='2026-09-28T10:00:00Z',recent='2026-10-07T10:00:00Z';
 t.model.opportunities=[
  {...base,id:'found-old',company:'Z Antigua',state:'Investigar',firstSeenAt:old,lastActivityAt:recent},
  {...base,id:'found-new',company:'A Nueva',state:'Investigar',firstSeenAt:recent},
  {...base,id:'discard-new',company:'Z Descartada',state:'Descartada',firstSeenAt:old,discardedAt:recent},
  {...base,id:'discard-old',company:'A Descartada',state:'Descartada',firstSeenAt:recent,discardedAt:old},
  {...base,id:'sent-new',company:'Z Enviada',state:'Enviada',firstSeenAt:old,sent:{at:recent}},
  {...base,id:'sent-old',company:'A Enviada',state:'Enviada',firstSeenAt:recent,sent:{at:old},lastActivityAt:recent},
  {...base,id:'reject-new',company:'Z Rechazada',state:'Rechazada',firstSeenAt:old,sent:{at:old},rejectedAt:recent},
  {...base,id:'reject-old',company:'A Rechazada',state:'Rechazada',firstSeenAt:recent,sent:{at:recent},rejectedAt:old},
  {...base,id:'reject-unknown',company:'B Fecha ausente',state:'Rechazada',sent:{at:recent},lastActivityAt:recent}
 ];
 const before=structuredClone(t.model),ids=html=>[...html.matchAll(/data-job-row="([^"]+)"/g)].map(m=>m[1]);
 let html=t.a.applyPage();assert.match(html,/<th scope="col" aria-sort="descending"[^>]*>/);assert.equal(ids(html).at(-1),'reject-unknown');
 t.a.setFlowFilter('solicitar','sin-elegir');assert.deepEqual(ids(t.a.applyPage()),['found-new','found-old']);
 t.a.setFlowFilter('solicitar','descartadas');assert.deepEqual(ids(t.a.applyPage()),['discard-new','discard-old']);assert.match(t.a.applyPage(),/Orden: descarte, de más reciente a más antiguo/);
 t.a.setFlowFilter('solicitar','seguimiento');assert.deepEqual(ids(t.a.applyPage()),['sent-new','sent-old']);
 t.a.setFlowFilter('solicitar','rechazadas');assert.deepEqual(ids(t.a.applyPage()),['reject-new','reject-old','reject-unknown']);
 t.a.setTableSort('solicitar','company');assert.deepEqual(ids(t.a.applyPage()),['reject-old','reject-unknown','reject-new']);
 await t.click({dataset:{clearOrder:'solicitar'}});assert.deepEqual(ids(t.a.applyPage()),['reject-new','reject-old','reject-unknown']);
 assert.deepEqual(t.model,before);
});

test('short table dates keep chronological sorting and exact filters across years',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[
  {...base,id:'recent',company:'Actual',externalDeadline:'2026-09-19'},
  {...base,id:'older',company:'Anterior',externalDeadline:'2025-09-19'},
  {...base,id:'middle',company:'Intermedia',externalDeadline:'2026-02-20'},
  {...base,id:'unknown',company:'Sin fecha'}
 ];
 t.model.history=[{opportunityId:'recent',at:'2026-09-19T15:25:00+02:00'}, {opportunityId:'older',at:'2025-09-19T13:25:00Z'}, {opportunityId:'middle',at:'2026-02-20T09:00:00Z'}];
 let html=t.a.applyPage();const tbody=html.split('<tbody>')[1];
 assert.equal((tbody.match(/>19 sep<\/td>/g)||[]).length,0);assert.doesNotMatch(tbody,/data-activity-at=|Hace \d/);assert.doesNotMatch(tbody,/>19 sep 15:25 h<\/td>/);
 const dates=t.a.columnCatalog('solicitar','activity').labels;assert.equal(dates[String(Date.parse('2025-09-19T13:25:00Z'))],'19 sept 2025, 15:25');assert.equal(dates[String(Date.parse('2026-09-19T13:25:00Z'))],'19 sept 2026, 15:25');
 const order=html=>[...html.matchAll(/data-job-row="([^"]+)"/g)].map(match=>match[1]);
 t.a.setTableSort('solicitar','deadline');assert.deepEqual(order(t.a.applyPage()),['older','middle','recent','unknown']);
 t.a.setTableSort('solicitar','activity',-1);assert.deepEqual(order(t.a.applyPage()),['recent','middle','older','unknown']);
 t.a.setTableFilter('solicitar','activity',[String(Date.parse('2025-09-19T13:25:00Z'))]);assert.deepEqual(order(t.a.applyPage()),['older']);
 t.a.setTableFilter('solicitar','activity',[String(Date.parse('2026-09-19T13:25:00Z'))]);assert.deepEqual(order(t.a.applyPage()),['recent']);
 t.a.setTableFilter('solicitar','activity',[String(Date.parse('2025-09-19T13:25:00Z')),String(Date.parse('2026-09-19T13:25:00Z'))]);
 t.a.setTableFilter('solicitar','deadline',[String(new Date('2025-09-19T12:00:00').getTime())]);assert.deepEqual(order(t.a.applyPage()),['older']);
});
test('table activity compares timestamps with different time zone offsets',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[{...base,id:'one',company:'Uno'},{...base,id:'two',company:'Dos'}];
 t.model.history=[{opportunityId:'one',at:'2026-09-19T15:25:00+02:00'}, {opportunityId:'one',at:'2026-09-19T14:25:00Z'}, {opportunityId:'two',at:'2026-09-19T15:30:00+02:00'}];
 t.a.setTableSort('solicitar','activity',-1);const html=t.a.applyPage();
 assert.deepEqual([...html.matchAll(/data-job-row="([^"]+)"/g)].map(match=>match[1]),['one','two']);assert.equal(t.a.flowRecord(t.model.opportunities[0],'elegir').activityAt,'2026-09-19T14:25:00Z');assert.equal(t.a.columnCatalog('solicitar','activity').labels[String(Date.parse('2026-09-19T14:25:00Z'))],'19 sept 2026, 16:25');
});
test('global finder searches saved current and historical processes',()=>{
 const t=setup(),job={id:'current',canonicalKey:'same',company:'Alfa',title:'Analista',state:'Preparar',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[job];t.model.historical=[{id:'old-copy',canonicalKey:'same',company:'Alfa',title:'Analista',state:'Enviada',category:'Laboral'},{id:'old',canonicalKey:'older',company:'Beta',title:'Desarrollador',state:'Rechazada',category:'Laboral',lastActivityLabel:'Julio 2025'},{id:'other',company:'Otra',title:'Curso',category:'No laboral'}];
 t.a.setQuery('analista');let html=t.a.findResults();assert.match(html,/Alfa/);assert.doesNotMatch(html,/Beta|old-copy|Otra/);
 t.a.setQuery('desarrollador');html=t.a.findResults();assert.match(html,/>Rechazada<\/span>/);assert.doesNotMatch(html,/Alfa/);
 assert.match(t.a.followPage(),/>Rechazada<\/span>/);
});
test('there is no persistent banner in any of the three main tabs',()=>{
 const t=setup();t.model.setupComplete=true;t.model.requests=[{status:'queued',type:'change'},{status:'queued',type:'review'}];
 for(const screen of ['solicitar','perfil','agente']){t.a.setScreenState(screen);t.a.render();assert.doesNotMatch(t.env.document.querySelector('#main').innerHTML,/global-next-step|Estado actual/);}
 assert.equal((t.a.agentPage().match(/Pendiente de iniciar/g)||[]).length,2);assert.doesNotMatch(t.a.agentPage(),/activity-work|tareas pendientes de iniciar/);assert.doesNotMatch(t.a.profileForm(),/Pendiente de iniciar/);assert.doesNotMatch(t.a.applyPage(),/Pendiente de iniciar/);
 const index=fs.readFileSync(require.resolve('../app/index.html'),'utf8');assert.doesNotMatch(index,/pending-work/);
});

test('a ready request is marked for attention in the table and reviewable in the detail',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],selection:{selected:true,mode:'review'}}];
 assert.match(t.a.applyPage(),/>Por atender<\/span>/);assert.doesNotMatch(t.a.applyPage(),/data-review=/);t.a.setSelected('one');assert.match(t.a.detail(),/data-review="one"/);assert.equal(t.a.activityWork(),'');assert.doesNotMatch(t.a.agentPage(),/Falta tu permiso de envío|Sin tareas/);
});

test('back returns through a request to the same offer and the filtered list',async()=>{
 const t=setup(),job={id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],selection:{selected:true,mode:'review'},fingerprint:'v1',draft:{messageUsage:'unused',requiredAnswers:[]},answers:{},answerOverrides:{}};
 job.packages=[{id:'v1',isCurrent:true,cvUrl:'/api/document?id=cv',payload:{messageUsage:'unused',answers:{}}}];t.model.opportunities=[job];
 t.env.fetch=async()=>({ok:true,json:async()=>t.model});
 await t.a.setScreen('solicitar');t.a.setFlowFilter('solicitar','atencion');t.a.setTableSort('solicitar','company',-1);t.a.setTableFilter('solicitar','company',['Empresa']);t.a.setQuery('Empresa');
 await t.a.setScreen('detalle','one');assert.equal(t.pageBack.hidden,false);assert.match(t.pageBack.innerHTML,/Volver a Ofertas/);assert.equal((t.pageBack.innerHTML.match(/data-back="1"/g)||[]).length,1);assert.doesNotMatch(t.a.detail(),/data-back="1"/);
 await t.a.setScreen('revisar','one');assert.match(t.pageBack.innerHTML,/Volver a la oferta/);
 await t.a.setScreen('cambio','one');assert.match(t.pageBack.innerHTML,/Volver a la solicitud/);
 await t.a.goBack();assert.equal(t.a.getView().screen,'revisar');assert.equal(t.a.getView().selected,'one');
 await t.a.goBack();assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,'one');
 await t.a.goBack();assert.equal(t.a.getView().screen,'solicitar');assert.equal(t.a.getView().filterText,'Empresa');assert.equal(t.pageBack.hidden,true);
 const html=t.a.applyPage();assert.match(html,/data-flow-filter="atencion"[^>]*aria-pressed="true"/);assert.match(html,/Empresa: Empresa/);assert.match(html,/<th scope="col" aria-sort="descending"/);
});

test('auxiliary pages and search return to their actual origin without losing the offer',async()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review'],draft:{messageUsage:'unused'},answers:{},answerOverrides:{}}];t.env.fetch=async()=>({ok:true,json:async()=>t.model});
 await t.a.setScreen('buscar');await t.a.setScreen('actividad');
 assert.match(t.pageBack.innerHTML,/Volver a Mi perfil/);await t.a.goBack();assert.equal(t.a.getView().screen,'perfil');
 await t.a.setScreen('detalle','one');await t.a.setScreen('encontrar');await t.a.goBack();assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,'one');
 await t.a.setScreen('ayuda');assert.match(t.pageBack.innerHTML,/Volver a la oferta/);await t.a.goBack();assert.equal(t.a.getView().selected,'one');
 const reload=setup();reload.a.setScreenState('detalle');reload.a.setSelected('one');reload.a.renderBackNavigation();assert.match(reload.pageBack.innerHTML,/Volver a Ofertas/);
});

test('Activity reads preserved history and previous history links remain readable',async()=>{
 const t=setup(),urls=[];t.env.fetch=async url=>{urls.push(url);return {ok:true,json:async()=>t.model};};
 await t.a.setScreen('agente');assert.equal(t.a.getView().screen,'agente');assert.equal(t.pageBack.hidden,true);assert.match(urls.at(-1),/history=1/);
 await t.a.setScreen('actividad');assert.equal(t.a.getView().screen,'actividad');assert.match(t.pageBack.innerHTML,/Volver a Resumen/);
 await t.a.goBack();assert.equal(t.a.getView().screen,'agente');assert.equal(t.pageBack.hidden,true);
 await t.a.setScreen('buscar');assert.doesNotMatch(urls.at(-1),/history=1/);
});

test('case shows offer conditions without current search criteria or legacy thresholds',()=>{
 const t=setup(),job={id:'one',company:'Test',title:'Role',state:'Preparar',requests:[],packages:[],missing:['Review'],questions:[],draft:{message:'text',recipient:'https://example.org'},answers:{},conditions:{'Viajes ≤1/mes':'Sí','Fijo ≥32 k€':'Sí'},apply:'Revisar',answerOverrides:{}};
 t.model.opportunities=[job];t.model.preferences={contract:'Indefinido',location:'Cádiz',minimumFixed:45000,maxTrips:0};t.a.setSelected('one');
 job.salary='40.000–50.000 € brutos/año';job.schedule='De lunes a viernes';job.draft.messageUsage='unused';
 const html=t.a.detail();assert.match(html,/40.000–50.000 € brutos\/año/);assert.match(html,/De lunes a viernes/);assert.doesNotMatch(html,/45000|0 viajes\/mes|Criterios actuales|Faltan condiciones|Comprobaciones anteriores|32.000|Presentación/);assert.match(html,/<h2>Condiciones<\/h2>[\s\S]*<h2>[\s\S]*?Formulario de solicitud[\s\S]*?<\/h2>[\s\S]*<h2>Actividad<\/h2>/);assert.doesNotMatch(html,/<summary>(Condiciones|Formulario de solicitud|Actividad)<\/summary>/);
 t.model.legacyEvidenceMode=false;assert.doesNotMatch(t.a.detail(),/32.000|Comprobaciones anteriores/);
 job.cvUrl='/api/document?id=cv&case=one';job.contactDrafts=[{recipient:'Selección',purpose:'Aclarar condiciones',message:'¿Cuál es el fijo?'}];
 const updated=t.a.detail();assert.match(updated,/Abrir PDF/);assert.doesNotMatch(updated,/<iframe|cv-preview/);assert.match(updated,/Borradores de contacto \(1\)/);assert.match(updated,/No enviados/);assert.match(updated,/data-copy-contact="0"/);
});
test('lost response replays exact attempt and preserves later edits',async()=>{
 const t=setup(),key='draft',form={_expected:{message:'Initial'},_shown:{message:'Initial'},dataset:{form:'draft'},values:{message:'First'},elements:{namedItem(){return {dataset:{}};}},querySelector(){return t.button;}};
 t.setForm(form);
 let stored={values:{message:'First'},expected:form._expected,shown:form._shown};t.storage.set(key,JSON.stringify(stored));
 const requests=[],committed=new Map();let fail=true;
 t.env.fetch=async(path,args)=>{const body=JSON.parse(args.body);requests.push(body);committed.set(body.id,body.operation);if(fail){fail=false;throw Error('TEST lost response after commit');}return {ok:true,json:async()=>({state:t.model})};};
 const op={kind:'ui-draft',values:{message:'First'},expected:{message:'Initial'}};
 assert.equal(await t.a.saveAttempt(form,op,stored,key),false);
 stored=JSON.parse(t.storage.get(key));stored.values.message='Second';form.values.message='Second';t.storage.set(key,JSON.stringify(stored));
 assert.equal(await t.a.saveAttempt(form,{...op,values:{message:'Second'}},stored,key),false);
 assert.deepEqual(requests[0],requests[1]);assert.equal(committed.size,1);
 const retained=JSON.parse(t.storage.get(key));assert.equal(retained.values.message,'Second');assert.equal(retained.expected.message,'First');
 assert.equal(await t.a.saveAttempt(form,{...op,values:{message:'Second'},expected:{message:'First'}},retained,key),true);
 assert.equal(committed.size,2);assert.notEqual(requests[2].id,requests[1].id);assert.equal(t.storage.has(key),false);
});
test('typing while a save finishes does not erase the new draft',async()=>{
 const t=setup(),key='draft',form={_expected:{message:'A'},_shown:{message:'A'},dataset:{form:'draft'},values:{message:'C'},elements:{namedItem(){return {dataset:{}};}},querySelector(){return t.button;}};t.setForm(form);
 const stored={values:{message:'B'},expected:{message:'A'},shown:{message:'A'}};t.storage.set(key,JSON.stringify(stored));
 t.env.fetch=async()=>{const current=JSON.parse(t.storage.get(key));current.values.message='C';t.storage.set(key,JSON.stringify(current));return {ok:true,json:async()=>({state:t.model})};};
 assert.equal(await t.a.saveAttempt(form,{kind:'ui-draft',values:{message:'B'}},stored,key),false);
 assert.equal(JSON.parse(t.storage.get(key)).values.message,'C');
});
test('background refreshes never overlap and hidden tabs do not poll',async()=>{
 const t=setup();let calls=0,resolve;
 t.env.fetch=()=>{calls++;return new Promise(r=>{resolve=()=>r({ok:true,json:async()=>({unchanged:true})});});};
 const a=t.a.refresh(),b=t.a.refresh();assert.equal(calls,1);resolve();await Promise.all([a,b]);
 t.env.document.hidden=true;await t.a.refresh();assert.equal(calls,1);
});

test('search settings and profile use saved information in their own places',()=>{
 const t=setup();Object.assign(t.model,{profile:{currentCity:'Toronto',workPermitWithoutSponsorship:true,salaryExpectationFixed:65000},preferences:{contract:'Indefinido',location:'Toronto',minimumFixed:60000,maxTrips:0,noticeDays:10},searchContext:{name:'Test person',targetRoles:'Nurse',currency:'CAD',checkMail:false},fieldDefinitions:{currentCity:{label:'Ciudad',type:'text'},workPermitWithoutSponsorship:{label:'Permiso',type:'boolean'},salaryExpectationFixed:{label:'Sueldo',type:'number'}},experience:'Synthetic nursing experience',cvLibrary:[]});
 const search=t.a.searchSettingsPanels();assert.match(search,/name="targetRoles"[^>]*>Nurse<\/textarea>/);assert.match(search,/name="minimumFixed"[^>]*value="60000"[^>]*><input name="currency"[^>]*value="CAD"/);assert.match(search,/name="salaryExpectationFixed"[^>]*value="65000"[^>]*><span data-salary-currency="1">CAD<\/span>/);assert.doesNotMatch(search,/name="regions"|name="languages"/);assert.match(search,/name="previousApplications"/);assert.doesNotMatch(search,/name="name"/);
 const about=t.a.profileForm();assert.match(about,/value="Test person"/);assert.match(about,/value="Toronto"/);assert.match(about,/name="minimumFixed"/);
 const profile=t.a.profileForm();assert.match(profile,/Synthetic nursing experience/);assert.doesNotMatch(profile,/data-form="automation"|name="applicationMode"|name="scheduleEnabled"/);assert.doesNotMatch(profile,/data-screen="autonomia"/);assert.match(profile,/data-work-authorizations/);
 assert.doesNotMatch(profile,/data-screen="opciones-solicitud"|data-screen="fuentes"|data-screen="actividad"|Actividad y copias|Descargar CSV|Descargar Excel|Abrir Excel/);assert.doesNotMatch(t.a.applyPage(),/data-auto-setting|name="applicationMode"|name="contactMode"/);assert.doesNotMatch(t.a.scheduleForm(),/name="scheduleEnabled"/);assert.doesNotMatch(search,/data-mail-check|checkMail|Incluir mi correo/);
 assert.match(profile,/<h1>Mi perfil<\/h1>/);
 assert.match(profile,/<h2>Sobre mi<\/h2>[\s\S]*<span>Mi experiencia<\/span>[\s\S]*<h2>Currículums<\/h2>/);assert.match(profile,/<h2>Lo que busco<\/h2>[\s\S]*name="previousApplications"/);assert.equal((profile.match(/<h2>/g)||[]).length,3);
 for(const section of ['about','experience'])assert.match(profile,new RegExp(`data-form="${section}"`));for(const section of ['search','sources'])assert.match(search,new RegExp(`data-form="${section}"`));
 t.model.experience='Primera línea\nSegunda línea\nTercera línea\nCuarta línea';
 const longProfile=t.a.profileForm();assert.match(longProfile,/Primera línea[\s\S]*Segunda línea[\s\S]*Tercera línea[\s\S]*Cuarta línea/);assert.doesNotMatch(longProfile,/Ver más experiencia|experience-more/);
 assert.doesNotMatch(t.a.profileForm(),/¿Qué toca ahora\?/);
 assert.doesNotMatch(t.a.backupsPage(),/data-copy-setup|Preparar búsqueda|Opciones avanzadas/);
});

test('secondary search editor separates a legacy combined zone and modality',()=>{
 const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',workMode:''},preferences:{location:'Remoto habitual desde España/Cádiz'},profile:{},fieldDefinitions:{}});
 const html=t.a.searchSettingsPanels();
 assert.match(html,/name="location"[^>]*value="España\/Cádiz"/);
 assert.match(html,/name="workMode"[^>]*value="Remoto habitual"/);
 const form={dataset:{form:'search'},values:{keywords:'',minimumFixed:''},_shown:{keywords:'',minimumFixed:null},elements:{namedItem(k){return {dataset:{type:k==='minimumFixed'?'number':'text'}};}},querySelector(){return t.button;}};
 t.setForm(form);t.a.updateSave();assert.equal(t.button.disabled,true);
 form.values.minimumFixed='50000';t.a.updateSave();assert.equal(t.button.disabled,false);
});

test('editing an offer response reveals the save action and reverting hides it',()=>{
 const t=setup(),form={dataset:{form:'profile'},values:{currentCity:'Old'},_shown:{currentCity:'Old'},_dirty:false,elements:{namedItem(){return {dataset:{type:'text'}};}},querySelector(){return t.button;}};
 t.button.hidden=true;t.a.updateSave(form);assert.equal(t.button.hidden,true);
 form.values.currentCity='New';t.a.updateSave(form);assert.equal(t.button.hidden,false);assert.equal(t.button.disabled,false);
 form.values.currentCity='Old';t.a.updateSave(form);assert.equal(t.button.hidden,true);
 form._dirty=true;t.a.updateSave(form);assert.equal(t.button.hidden,false);
});

test('an authorization retry keeps its identity after a lost response',async()=>{
 const t=setup(),calls=[],operation={kind:'ui-approve',opportunityId:'one',fingerprint:'version'};
 t.env.fetch=async(_,options)=>{calls.push(JSON.parse(options.body));if(calls.length===1)throw Error('TEST lost response');return {ok:true,json:async()=>({state:t.model})};};
 assert.equal(await t.a.action(operation),false);assert.equal(await t.a.action(operation),true);
 assert.equal(calls[0].id,calls[1].id);assert.deepEqual(calls[0].operation,calls[1].operation);
 assert.equal([...t.rawStorage.keys()].some(key=>key.includes('stubbs_jobs-action:')),false);
});

test('a pending write prevents another authorization and background polling',async()=>{
 const t=setup();let calls=0,deliver;
 t.env.fetch=async()=>{calls++;return new Promise(resolve=>{deliver=resolve;});};
 const pending=t.a.action({kind:'ui-approve',opportunityId:'one',fingerprint:'version'});
 assert.equal(await t.a.action({kind:'ui-approve',opportunityId:'two',fingerprint:'other'}),false);
 await t.a.refresh(true);assert.equal(calls,1);
 deliver({ok:true,json:async()=>({state:t.model})});assert.equal(await pending,true);
});

test('a partial state cannot confirm a write or discard its recovery journal',async()=>{
 const t=setup();t.env.fetch=async()=>({ok:true,json:async()=>({state:{opportunities:[]}})});
 assert.equal(await t.a.action({kind:'ui-approve',opportunityId:'one',fingerprint:'version'}),false);
 assert.equal(t.a.getModel(),t.model);assert.equal([...t.rawStorage.keys()].some(key=>key.includes('stubbs_jobs-action:')),true);
});

test('search reports preserve a concrete source configuration failure without linking technical logs',()=>{
 const t=setup();t.model.sourceConfigurationError='El agente debe comprobar config/sources.json.';
 assert.equal(t.model.sourceConfigurationError,'El agente debe comprobar config/sources.json.');assert.doesNotMatch(t.a.agentPage(),/data-checks=/);
 t.model.requests=[{id:'failed-sources',type:'discovery',status:'done',summary:'La búsqueda no pudo revisar las webs.',updatedAt:'2026-10-01T10:00:00Z',activityResult:{newOfferCount:0,health:[],publicSources:[],sourceConfigurationError:t.model.sourceConfigurationError}}];t.a.setSelected('failed-sources');const html=t.a.activityReport();assert.match(html,/La búsqueda no pudo revisar las webs/);assert.match(html,/El agente debe comprobar config\/sources.json/);assert.doesNotMatch(html,/data-checks=|Pruebas y pasos anteriores/);
 assert.doesNotMatch(t.a.coverage(),/solo correo/);
});
test('reverting an edit clears its recovery draft',()=>{
 const t=setup(),form={dataset:{form:'draft'},values:{message:'Changed'},_expected:{message:'Original'},_shown:{message:'Original'},elements:{namedItem(){return {dataset:{}};}},querySelector(){return t.button;}};
 t.a.setScreenState('perfil');t.setForm(form);t.a.rememberForm();assert.equal(t.storage.has('stubbs_jobs-draft:perfil:global'),true);
 form.values.message='Original';t.a.rememberForm();assert.equal(t.storage.has('stubbs_jobs-draft:perfil:global'),false);
});
test('separate search panels preserve independent drafts',()=>{
 const t=setup();t.a.setScreenState('perfil');
 const make=(kind,key,original,changed)=>({dataset:{form:kind},values:{[key]:changed},_expected:{[key]:original},_shown:{[key]:original},elements:{namedItem(){return {dataset:{type:'text'}};}},querySelector(selector){return selector==='[type=submit]'?t.button:null;}});
 const search=make('search','targetRoles','Analista','Diseñador'),sources=make('sources','sourceUrls','', 'https://example.org');t.setForms([search,sources]);
 t.a.rememberForm(search);t.a.rememberForm(sources);
 assert.equal(t.storage.has('stubbs_jobs-draft:busqueda:global'),true);assert.equal(t.storage.has('stubbs_jobs-draft:fuentes:global'),true);assert.equal(t.a.isDirty(),true);
 search.values.targetRoles='Analista';t.a.rememberForm(search);
 assert.equal(t.storage.has('stubbs_jobs-draft:busqueda:global'),false);assert.equal(t.storage.has('stubbs_jobs-draft:fuentes:global'),true);assert.equal(t.a.isDirty(),true);
});

test('old search links reach Perfil with all four independent editors',async()=>{
 const t=setup();t.env.fetch=async()=>({ok:true,json:async()=>t.model});
 for(const alias of ['buscar','busqueda','fuentes','datos','contexto']){
  await t.a.setScreen(alias);assert.equal(t.a.getView().screen,'perfil');
  const html=t.env.document.querySelector('#main').innerHTML;
  for(const kind of ['about','experience','search','sources'])assert.match(html,new RegExp(`data-form="${kind}"`));
 }
});
test('a daily summary replaces the matching completion and keeps undo in the preserved history',()=>{
 const t=setup(),result='Solicitud corregida sin enviar.';t.model.opportunities=[{id:'one',company:'Empresa'}];
 t.model.requests=[{type:'change',status:'done',opportunityId:'one',updatedAt:'2026-09-28T12:00:00Z',result}];
 t.model.history=[{id:'completion',opportunityId:'one',at:'2026-09-28T12:00:00Z',title:'Encargo terminado',detail:result},{id:'edit',at:'2026-09-28T12:05:00Z',title:'Perfil actualizado',actor:'Usuario'}];t.model.undo=[{id:'completion'},{id:'edit'}];
 const html=t.a.agentPage();assert.equal((html.match(/Solicitud corregida sin enviar/g)||[]).length,1);assert.equal((html.match(/class="activity-day"/g)||[]).length,1);assert.match(html,/data-job="one">Ver solicitud/);assert.doesNotMatch(html,/Perfil actualizado|data-report|Ver historial/);
 assert.match(t.a.history(),/data-undo="completion"/);assert.match(t.a.history(),/data-undo="edit"/);
});

test('submission appears once and distinct responses remain visible without changing history',()=>{
 const t=setup(),result='El portal confirma la inscripción.';t.model.opportunities=[{id:'one',company:'Empresa'}];
 t.model.requests=[{type:'send',status:'done',opportunityId:'one',updatedAt:'2026-09-28T12:00:00Z',result}];
 t.model.history=[{id:'sent',opportunityId:'one',at:'2026-09-28T12:00:00Z',title:'Envío confirmado',detail:result},{id:'completion',opportunityId:'one',at:'2026-09-28T12:00:00Z',title:'Encargo terminado',detail:result},{id:'reply',opportunityId:'two',at:'2026-09-28T12:01:00Z',title:'Respuesta recibida',detail:'Mensaje de la empresa'}];t.model.undo=[{id:'sent'},{id:'completion'}];
 const html=t.a.agentPage();assert.equal((html.match(/Solicitud enviada/g)||[]).length,1);assert.match(html,/Respuesta recibida/);assert.match(html,/data-job="one">Ver solicitud/);assert.doesNotMatch(html,/data-report/);assert.equal(t.model.history.length,3);assert.match(t.a.history(),/data-undo="sent"/);
});

test('coverage names pending sources and keeps portal access separate from reviews',()=>{
 const t=setup();Object.assign(t.model,{
  publicSources:[{id:'one',company:'Web revisada'},{id:'two',company:'Web pendiente'}],
  health:[{sourceId:'one',company:'Web revisada',status:'ok',checkedAtUtc:'2026-09-28T09:00:00Z'}],
  portalAccess:{linkedin:{status:'ready',checkedAt:'2026-09-28T08:00:00Z'},infojobs:{status:'login_required',checkedAt:'2026-09-28T08:00:00Z'},outlook:{status:'ready',checkedAt:'2026-09-28T08:00:00Z'}}
 });
 const html=t.a.agentPage();assert.doesNotMatch(html,/1 de 2 webs revisadas|Ver detalle/);assert.doesNotMatch(html,/agent-coverage|Acceso a portales/);
 const detail=t.a.coverage();assert.match(detail,/Web revisada/);assert.match(detail,/Por revisar: Web pendiente/);assert.match(detail,/Acceso a portales/);assert.match(detail,/Inicia sesión/);assert.match(detail,/El acceso comprobado no confirma/);assert.doesNotMatch(detail,/outlook|Outlook/);
});

test('completed searches join sends in chronological cards without a fixed coverage board',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa A'},{id:'two',company:'Empresa B'}];
 t.model.requests=[{id:'search',type:'discovery',status:'done',updatedAt:'2026-09-28T09:00:00Z',summary:'Tres ofertas preseleccionadas.',activityResult:{newOfferCount:3,health:[],publicSources:[]}},
  {id:'sent-a',type:'send',opportunityId:'one',status:'done',updatedAt:'2026-09-28T10:00:00Z',summary:'Confirmación A'},
  {id:'sent-b',type:'send',opportunityId:'two',status:'done',updatedAt:'2026-09-28T11:00:00Z',summary:'Confirmación B'}];
 const html=t.a.agentPage();assert.match(html,/Búsqueda realizada<\/strong>[\s\S]*3 nuevas ofertas/);assert.match(html,/data-search-offers="1">Ver ofertas/);assert.equal((html.match(/class="activity-day"/g)||[]).length,1);
 assert(html.indexOf('Empresa B')<html.indexOf('Empresa A'));assert(html.indexOf('Empresa A')<html.indexOf('Búsqueda realizada'));
 assert.doesNotMatch(html,/agent-overview|agent-coverage|Qué se ha revisado/);
});

test('a search report opens its exact result and returns to Activity while retaining internal proof',async()=>{
 const t=setup(),urls=[];t.model.requests=[{id:'older',type:'discovery',status:'done',updatedAt:'2026-09-28T10:00:00Z',summary:'Resultado anterior',result:'PRUEBA ANTERIOR',activityResult:{newOfferCount:3,health:[],publicSources:[]}},
 {id:'newer',type:'discovery',status:'done',updatedAt:'2026-09-30T10:00:00Z',summary:'Resultado posterior',result:'PRUEBA POSTERIOR',activityResult:{newOfferCount:0,health:[],publicSources:[]}}];
 t.env.fetch=async path=>{urls.push(path);return {ok:true,json:async()=>t.model};};
 await t.a.setScreen('agente');await t.a.setScreen('informe','older');
 assert.equal(t.a.getView().screen,'informe');assert.equal(t.a.getView().selected,'older');
 assert.match(t.env.document.querySelector('#main').innerHTML,/Resultado anterior/);assert.doesNotMatch(t.env.document.querySelector('#main').innerHTML,/PRUEBA ANTERIOR|PRUEBA POSTERIOR|Resultado posterior/);assert.equal(t.model.requests[0].result,'PRUEBA ANTERIOR');
 assert.match(urls.at(-1),/history=1/);assert.doesNotMatch(urls.at(-1),/case=older/);
 await t.a.goBack();assert.equal(t.a.getView().screen,'agente');
});

test('a summary-only edit retains result date and historical evidence window in the actual report route',async()=>{
 const t=setup();t.model.requests=[{id:'old-result',type:'discovery',status:'done',createdAt:'2026-09-28T09:00:00Z',activityAt:'2026-09-28T10:00:00Z',updatedAt:'2026-10-02T12:00:00.000001Z',summary:'Resumen aclarado',result:'Prueba original'}];
 t.model.health=[{sourceId:'old-source',company:'Web original ficticia',status:'ok',checkedAtUtc:'2026-09-28T09:30:00Z',errors:[]},{sourceId:'later-source',company:'Web posterior ficticia',status:'ok',checkedAtUtc:'2026-09-30T09:30:00Z',errors:[]}];
 t.model.history=[{id:'old-proof',title:'Comprobación original',detail:'Detalle original conservado',at:'2026-09-28T09:40:00Z'},{id:'new-proof',title:'Comprobación posterior',detail:'Detalle ajeno posterior',at:'2026-09-30T09:40:00Z'}];
 t.a.setScreenState('agente');t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});const before=structuredClone(t.model);await t.click({dataset:{report:'old-result'}});for(let i=0;i<20&&!t.env.document.querySelector('#main').innerHTML;i++)await Promise.resolve();
 const html=t.env.document.querySelector('#main').innerHTML;assert.equal(t.a.getView().screen,'informe');assert.match(html,/<p class="muted">28 sept 2026, 12:00<\/p>/);assert.match(html,/Web original ficticia/);assert.match(html,/Resumen aclarado/);assert.doesNotMatch(html,/Web posterior ficticia|Comprobación original|Comprobación posterior|Prueba original|2 oct 2026, 14:00/);assert.deepEqual(t.a.getModel(),before);
 const now=new Date().toISOString(),earlier=new Date(Date.now()-60_000).toISOString();t.a.getModel().requests=[{id:'working',type:'review',status:'running',updatedAt:now,activityAt:earlier}];assert(t.a.activityWork().includes('Último registro: '+new Intl.DateTimeFormat('es-ES',{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Madrid'}).format(new Date(earlier))));
});

test('a partial search keeps its concrete issue visible while full coverage stays in its report',()=>{
 const t=setup();t.model.requests=[{id:'search',type:'discovery',status:'done',summary:'Resultados parciales',updatedAt:'2026-09-30T10:00:00Z',activityResult:{newOfferCount:0,health:[{sourceId:'failed',company:'Web ficticia',status:'partial',checkedAtUtc:'2026-09-30T09:00:00Z',errors:['Página 2 no disponible']}],publicSources:[{id:'failed'},{id:'pending'}]}}];
 const html=t.a.agentPage();assert.match(html,/0 nuevas ofertas/);assert.match(html,/Web ficticia: Página 2 no disponible/);assert.doesNotMatch(html,/data-report|Acceso a portales/);assert.doesNotMatch(html,/Acceso a portales/);
});

test('Activity keeps date-only records without inventing a time',()=>{
 const t=setup();t.model.requests=[{id:'search',type:'discovery',status:'done',updatedAt:'2026-09-28',summary:'Búsqueda realizada'}];
 const html=t.a.agentPage();assert.match(html,/datetime="2026-09-28"/);assert.doesNotMatch(html,/>0:00<|>2:00<|10:00/);
});
test('daily summary date-only labels retain their calendar day in extreme timezones while timed records use local days',()=>{
 const original=process.env.TZ;
 try{
  for(const zone of ['Pacific/Kiritimati','Pacific/Pago_Pago','America/Los_Angeles','Europe/Madrid']){
   process.env.TZ=zone;const t=setup();t.model.personalized=true;t.model.history=[{id:'calendar',title:'Respuesta recibida',at:'2026-10-01',detail:'Respuesta ficticia'}];
   assert.match(t.a.agentPage(),/<time datetime="2026-10-01">1 oct(?: 2026)?<\/time>/,zone);assert.equal(t.model.history[0].at,'2026-10-01');
   t.model.history=[{id:'timed',title:'Respuesta recibida',at:'2026-10-01T00:30:00Z',detail:'Respuesta ficticia'}];
   const previousDay=['Pacific/Pago_Pago','America/Los_Angeles'].includes(zone);
   assert.match(t.a.agentPage(),previousDay?/<time datetime="2026-09-30">30 sept(?: 2026)?<\/time>/:/<time datetime="2026-10-01">1 oct(?: 2026)?<\/time>/,zone);assert.equal(t.model.history[0].at,'2026-10-01T00:30:00Z');assert.deepEqual(t.model.requests,[]);
  }
 }finally{if(original===undefined)delete process.env.TZ;else process.env.TZ=original;}
});

test('Ver anteriores adds complete older days in the same daily summary',()=>{
 const t=setup();t.model.requests=Array.from({length:10},(_,i)=>({id:'search-'+i,type:'discovery',status:'done',updatedAt:`2026-09-${String(30-i).padStart(2,'0')}T10:00:00Z`,activityResult:{newOfferCount:i,health:[],publicSources:[]}}));
 let html=t.a.agentPage();assert.equal((html.match(/class="activity-day"/g)||[]).length,7);assert.match(html,/data-more-activity="1">Ver anteriores/);assert.doesNotMatch(html,/data-screen="actividad"|data-report/);
 t.a.setActivityDayLimit(14);html=t.a.agentPage();assert.equal((html.match(/class="activity-day"/g)||[]).length,10);assert.doesNotMatch(html,/Ver anteriores/);assert.equal(t.model.requests.length,10);
});

test('Ver ofertas clears filters that could hide the results without changing applications',async()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa',title:'Analista',state:'Preparar',requests:[],packages:[],questions:[],missing:['review']}];t.env.fetch=async()=>({ok:true,json:async()=>t.model});
 await t.a.setScreen('solicitar');t.a.setFlowFilter('solicitar','enviadas');t.a.setTableFilter('solicitar','company',['Otra']);t.a.setQuery('Otra');
 await t.a.setScreen('agente');await t.a.openSearchOffers();
 assert.equal(t.a.getView().screen,'solicitar');assert.equal(t.a.getView().filterText,'');assert.match(t.a.applyPage(),/data-flow-filter="todas"[^>]*aria-pressed="true"/);assert.match(t.a.applyPage(),/Empresa/);assert.equal(t.model.opportunities[0].state,'Preparar');
});

test('copying a petition never creates work and uses the queue only when there is pending work',async()=>{
 const t=setup(),copied=[],calls=[];t.model.searchContext.targetRoles='Analista';t.model.preferences.location='España';
 t.env.navigator={clipboard:{writeText:async text=>copied.push(text)}};t.env.fetch=async path=>{calls.push(path);throw Error('Unexpected API call');};
 await t.a.saveVisibleChangesAndCopy();assert.deepEqual(copied,['Busca ofertas nuevas']);assert.deepEqual(calls,[]);assert.deepEqual(t.model.requests,[]);
 t.model.requests=[{id:'existing',type:'change',status:'queued'}];await t.a.saveVisibleChangesAndCopy();assert.deepEqual(copied,['Busca ofertas nuevas','Continúa con Stubbs Jobs']);assert.equal(t.model.requests.length,1);
 t.model.requests[0].status='running';await t.a.saveVisibleChangesAndCopy();assert.equal(copied.length,2);assert.deepEqual(calls,[]);
});

function profileFixture(t){
 t.a.setScreenState('perfil');
 const make=(kind,values,original)=>({dataset:{form:kind},values,_expected:{...original},_shown:{...original},elements:{namedItem(key){return {dataset:{type:'text'},get value(){return values[key];},focus(){}};}},querySelector(){return null;},reportValidity(){return true;}});
 const forms=[make('about',{currentCity:'Cádiz'},{currentCity:'Madrid'}),make('experience',{text:'Experiencia confirmada'},{text:'Anterior'}),make('search',{targetRoles:'Analista',location:'España'},{targetRoles:'Diseñador',location:'España'}),make('sources',{sourceUrls:'https://example.org/jobs'},{sourceUrls:''})];
 const saveButton={disabled:false,textContent:''},bar={hidden:true,querySelector(){return saveButton;},setAttribute(){}};
 const main=t.env.document.querySelector('#main');t.setForms(forms);main.querySelector=selector=>{if(selector==='form[data-form]')return forms[0];if(selector==='[data-profile-savebar]')return bar;const match=selector.match(/^form\[data-form="([^"]+)"\]$/);return match?forms.find(form=>form.dataset.form===match[1])||null:null;};
 return {forms,bar,saveButton};
}

test('one profile save covers every changed section without copying or starting the agent',async()=>{
 const t=setup(),{bar,saveButton}=profileFixture(t),steps=[];
 t.env.navigator={clipboard:{writeText:async()=>{throw Error('Must not copy');}}};
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;steps.push(operation.section||operation.kind);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};
 assert.equal(await t.a.saveProfileChanges(),true);assert.deepEqual(steps,['about','ui-experience','search','sources']);assert.equal(t.a.isDirty(),false);assert.equal(bar.hidden,true);assert.equal(saveButton.disabled,false);assert.equal(t.model.requests.length,0);
});

test('partial profile saving retains failed and remaining sections and does not claim complete success',async()=>{
 const t=setup(),{forms,bar}=profileFixture(t),steps=[];
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;steps.push(operation.section||operation.kind);if(steps.length===2)throw Error('TEST unavailable');return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};
 assert.equal(await t.a.saveProfileChanges(),false);assert.deepEqual(steps,['about','ui-experience']);assert.equal(forms[0]._dirty,false);for(const form of forms.slice(1))assert.equal(form._dirty,true);assert.equal(bar.hidden,false);assert.equal(t.storage.has('stubbs_jobs-draft:experiencia:global'),true);
 assert.match(t.env.document.querySelector('#toast').innerHTML,/Se guardó una sección[\s\S]*Sobre mi/);assert.doesNotMatch(t.env.document.querySelector('#toast').innerHTML,/Cambios guardados/);
});

test('profile save validates all edited sections before writing any',async()=>{
 const t=setup(),{forms,bar}=profileFixture(t);let calls=0;forms[2].reportValidity=()=>false;t.env.fetch=async()=>{calls++;throw Error('Must not write');};
 assert.equal(await t.a.saveProfileChanges(),false);assert.equal(calls,0);assert.equal(bar.hidden,false);assert.equal(t.a.isDirty(),true);
});

test('notice units and jurisdiction lists survive edits, drafts, navigation and a single profile save',async()=>{
 const t=setup();Object.assign(t.model,{profile:{noticeDays:15,workAuthorizations:['Canadá'],workPermitWithoutSponsorship:null},searchContext:{name:'Persona ficticia'},preferences:{location:'Canadá'},experience:'Experiencia ficticia'});const dom=groupedProfileDom(t),operations=[];t.a.setScreenState('perfil');t.a.render();t.a.rememberAllForms?.();assert.equal(t.a.isDirty(),false);
 assert.equal(dom.field('noticeDays').dataset.type,'text');assert.equal(dom.field('workAuthorizations').dataset.type,'multiselect');
 dom.field('noticeDays').value='15 días laborables (3 semanas naturales)';await t.dispatchMain('input',dom.field('noticeDays'));
 dom.field('workAuthorizations').value=JSON.stringify(['Canadá','Japón']);await t.dispatchMain('input',dom.field('workAuthorizations'));
 t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});await t.a.setScreen('solicitar');await t.a.setScreen('perfil');assert.equal(dom.field('noticeDays').value,'15 días laborables (3 semanas naturales)');assert.deepEqual(JSON.parse(dom.field('workAuthorizations').value),['Canadá','Japón']);
 t.env.fetch=async(_,options)=>{const op=JSON.parse(options.body).operation;operations.push(op);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:1,profile:{...t.a.getModel().profile,...op.values}}})};};assert.equal(await t.a.saveProfileChanges(),true);assert.equal(operations.length,1);assert.deepEqual(operations[0].expected,{noticeDays:15,workAuthorizations:['Canadá']});assert.deepEqual(operations[0].values,{noticeDays:'15 días laborables (3 semanas naturales)',workAuthorizations:['Canadá','Japón']});assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);
});

test('legacy permits never become EU permission and arbitrary countries are retained as literal confirmed choices',()=>{
 const t=setup();t.model.profile={workPermitWithoutSponsorship:true};t.model.preferences={location:'España'};assert.deepEqual(Array.from(t.a.workAuthorizationValues(undefined)),['España']);assert.doesNotMatch(t.a.profileForm(),/data-permit-option="Unión Europea" checked/);
 t.model.preferences.location='Toronto';assert.deepEqual(Array.from(t.a.workAuthorizationValues(undefined)),[]);
 t.model.profile.workAuthorizations=['India','Sudáfrica'];const html=t.a.profileForm();assert.match(html,/data-permit-option="India" checked/);assert.match(html,/data-permit-option="Sudáfrica" checked/);assert.doesNotMatch(html,/name="workPermitWithoutSponsorship"/);
});

test('the salary currency can be edited in place and survives drafts and a single profile save',async()=>{
 const t=setup();Object.assign(t.model,{profile:{noticeDays:null},searchContext:{currency:'CAD',name:'Persona ficticia'},preferences:{minimumFixed:6000000,location:'Canadá'},experience:'Experiencia ficticia'});const dom=groupedProfileDom(t),operations=[];t.a.setScreenState('perfil');t.a.render();
 assert.match(t.a.profileForm(),/name="currency"[^>]*class="currency-input"[^>]*value="CAD"/);assert.equal(dom.field('currency').value,'CAD');assert.equal(t.a.isDirty(),false);
 dom.field('currency').value='jpy';await t.dispatchMain('input',dom.field('currency'));assert.equal(dom.field('currency').value,'JPY');
 t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});await t.a.setScreen('solicitar');await t.a.setScreen('perfil');assert.equal(dom.field('currency').value,'JPY');
 t.env.fetch=async(_,options)=>{const op=JSON.parse(options.body).operation;operations.push(op);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:1,searchContext:{...t.a.getModel().searchContext,...op.values}}})};};assert.equal(await t.a.saveProfileChanges(),true);assert.equal(operations.length,1);assert.deepEqual(operations[0].expected,{currency:'CAD'});assert.deepEqual(operations[0].values,{currency:'JPY'});assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);
});

test('the five compact profile textareas grow with wrapped content and shrink after deleting without moving the page',()=>{
 const t=setup(),html=t.a.profileForm();for(const key of ['targetRoles','keywords','languages','sourceUrls','previousApplications'])assert.match(html,new RegExp(`<textarea name="${key}"[^>]*data-auto-grow="1"[^>]*rows="1"`));
 const style={},field={style,getBoundingClientRect:()=>({width:280}),scrollHeight:120,offsetHeight:44,clientHeight:42};t.env.window.scrollY=350;t.a.growField(field);assert.equal(style.height,'122px');assert.equal(t.env.window.scrollY,350);field.scrollHeight=42;t.a.growField(field);assert.equal(style.height,'44px');
 assert(html.indexOf('id="search-field-previousApplications"')<html.indexOf('id="profile-sourceUrls"'));assert.doesNotMatch(html,/Borrador recuperado|Anota empresas a las que|Trabajo y horario/);
});

test('contact facts are visible in About me and retain their values, expectations and drafts across navigation',async()=>{
 const t=setup();Object.assign(t.model,{profile:{email:'fictional@example.org',phone:'+81 90 1234 5678',currentCountry:'Japón',postalCode:'001-0001',address:'Dirección ficticia',linkedinUrl:'https://www.linkedin.com/in/fictional/',websiteUrl:'https://example.org/portfolio'},searchContext:{name:'Persona ficticia',currency:'JPY',searchPriorities:'Turno de mañana'},fieldDefinitions:{custom_language:{label:'Otro dato general',type:'text',scope:'global'},custom_private:{label:'Respuesta específica',type:'text',scope:'opportunity'}}});const dom=groupedProfileDom(t),ops=[];t.a.setScreenState('perfil');t.a.render();
 const about=dom.html.split('id="profile-about"')[1].split('</section>')[0];for(const key of ['email','phone','currentCountry','postalCode','address','linkedinUrl','websiteUrl'])assert.match(about,new RegExp(`name="${key}"`));assert.match(about,/name="email"[^>]*type="email"/);assert.match(about,/name="phone"[^>]*type="tel"/);assert.match(about,/name="linkedinUrl"[^>]*type="url"/);assert.match(about,/name="custom_language"/);assert.doesNotMatch(about,/name="custom_private"/);assert.equal(dom.field('postalCode').value,'001-0001');
 assert.match(dom.html,/<textarea name="searchPriorities"[^>]*data-auto-grow="1"[^>]*rows="1"/);assert.equal(t.a.isDirty(),false);
 dom.field('email').value='updated@example.org';await t.dispatchMain('input',dom.field('email'));t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});await t.a.setScreen('solicitar');await t.a.setScreen('perfil');assert.equal(dom.field('email').value,'updated@example.org');
 t.env.fetch=async(_,options)=>{const op=JSON.parse(options.body).operation;ops.push(op);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:1,profile:{...t.a.getModel().profile,...op.values}}})};};assert.equal(await t.a.saveProfileChanges(),true);assert.equal(ops.length,1);assert.deepEqual(ops[0].expected,{email:'fictional@example.org'});assert.deepEqual(ops[0].values,{email:'updated@example.org'});assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);
});

test('the pending work summary names the saved offer and opens it without starting work',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa ficticia',title:'Puesto ficticio',state:'Investigar',requests:[],questions:[],missing:[]}];t.model.requests=[{id:'pending',type:'investigate',status:'queued',opportunityId:'one'}];const before=structuredClone(t.model),html=t.a.agentPage();assert.equal(t.a.activityWork(),'');assert.match(html,/Comprobar oferta · Empresa ficticia/);assert.match(html,/Pendiente de iniciar · Puesto ficticio/);assert.match(html,/data-job="one">Ver oferta/);assert.doesNotMatch(html,/activity-work|tarea pendiente de iniciar|data-execute|data-run|data-copy-agent-command/);assert.deepEqual(t.model,before);
 t.model.requests.push({id:'two',type:'discovery',status:'queued'});assert.match(t.a.agentPage(),/Buscar ofertas/);assert.equal((t.a.agentPage().match(/Pendiente de iniciar/g)||[]).length,2);assert.equal(t.a.activityWork(),'');
});

test('offer pages load exactly 100 more while retaining filters, selection and the nine explicit columns',async()=>{
 const t=setup(),base={title:'Enfermería',state:'Investigar',apply:'Sí, aclarar',requests:[],packages:[],questions:[],missing:[],country:'Canadá',workMode:'Presencial',contract:'Temporal'};t.model.opportunities=Array.from({length:230},(_,i)=>({...base,id:'country-'+i,company:'Hospital '+String(i).padStart(3,'0'),salary:i%2?'No publicado':null}));t.a.getTableSelection().add('country-5');let html=t.a.applyPage();assert.equal((html.match(/data-job-row=/g)||[]).length,100);assert.match(html,/100 de 230 ofertas/);assert.match(html,/Cargar más/);assert.doesNotMatch(html,/No publicado<\/span>/);
 assert.deepEqual([...html.matchAll(/class="column-title"[^>]*>([^<]+)/g)].map(m=>m[1].trim()),['Encontrada','Empresa','Puesto','País','Modalidad','Contrato','Horario','Salario','Estado']);assert.match(html,/<td>Canadá<\/td><td>Presencial<\/td><td>Temporal<\/td>/);
 await t.click({dataset:{moreHistory:'1'}});html=t.a.applyPage();assert.equal((html.match(/data-job-row=/g)||[]).length,200);assert(t.a.getTableSelection().has('country-5'));await t.click({dataset:{moreHistory:'1'}});assert.equal((t.a.applyPage().match(/data-job-row=/g)||[]).length,230);assert.doesNotMatch(t.a.applyPage(),/Cargar más/);
 t.a.setTableFilter('solicitar','salary',['No publicado']);assert.equal((t.a.applyPage().match(/data-job-row=/g)||[]).length,230);t.a.setTableFilter('solicitar','country',['Canadá']);assert.equal((t.a.applyPage().match(/data-job-row=/g)||[]).length,230);
});

test('experience saved before a later failure can be edited again without a false conflict',async()=>{
 const t=setup(),{forms}=profileFixture(t);t.model.experience='Anterior';let failSources=true;
 t.env.fetch=async(_,options)=>{
  const op=JSON.parse(options.body).operation,next={...t.a.getModel(),revision:t.a.getModel().revision+1};
  if(op.kind==='ui-experience'){assert.equal(op.expected,next.experience);next.experience=op.text;}
  if(op.section==='sources'&&failSources)throw Error('TEST sources unavailable');
  return {ok:true,json:async()=>({state:next})};
 };
 assert.equal(await t.a.saveProfileChanges(),false);assert.equal(forms[1]._dirty,false);assert.equal(forms[1]._expected.text,'Experiencia confirmada');
 forms[1].values.text='Experiencia editada de nuevo';failSources=false;
 assert.equal(await t.a.saveProfileChanges(),true);assert.equal(t.a.getModel().experience,'Experiencia editada de nuevo');
});

test('a second profile save and navigation cannot interrupt the active save',async()=>{
 const t=setup(),{bar,saveButton}=profileFixture(t),steps=[];let finish;
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;steps.push(operation.section||operation.kind);if(steps.length===1)await new Promise(resolve=>{finish=resolve;});return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};
 const saving=t.a.saveProfileChanges();assert.equal(bar.hidden,false);assert.equal(saveButton.disabled,true);assert.equal(saveButton.textContent,'Guardando…');assert.equal(await t.a.saveProfileChanges(),false);await t.a.setScreen('agente');assert.equal(t.a.getView().screen,'perfil');await t.a.refresh(true);assert.equal(steps.length,1);assert.equal(await t.a.action({kind:'ui-undo',id:1}),false);
 finish();assert.equal(await saving,true);assert.equal(saveButton.disabled,false);assert.equal(bar.hidden,true);
});

test('edits typed during profile saving remain recoverable and visible',async()=>{
 const t=setup(),{forms,bar}=profileFixture(t);let finish;
 t.env.fetch=async()=>{await new Promise(resolve=>{finish=resolve;});return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};
 const saving=t.a.saveProfileChanges();forms[0].values.currentCity='Bilbao';t.a.rememberForm(forms[0]);finish();assert.equal(await saving,false);assert.equal(forms[0].values.currentCity,'Bilbao');assert.equal(forms[0]._dirty,true);assert.equal(bar.hidden,false);assert.equal(t.storage.has('stubbs_jobs-draft:datos:global'),true);
});

test('renamed tabs preserve new and old navigation links',async()=>{
 const t=setup();t.env.fetch=async()=>({ok:true,json:async()=>t.model});
 for(const route of ['ofertas','candidaturas','elegir','seguir']){await t.a.setScreen(route);assert.equal(t.a.getView().screen,'solicitar');assert.match(t.a.applyPage(),/>Ofertas<\/h1>/);}
 for(const route of ['resumen','agente']){await t.a.setScreen(route);assert.equal(t.a.getView().screen,'agente');assert.match(t.a.agentPage(),/>Resumen<\/h1>/);}
});


test('an uncertain send offers a specific portal check without reopening the form',()=>{
 const t=setup();const request={id:'specific-send',type:'send',status:'interrupted',updatedAt:new Date().toISOString()};
 const job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí, aclarar',requests:[request],packages:[],questions:[],missing:['Revisión'],draft:{recipient:'',message:'',messageUsage:'unused'},answers:{},conditions:{},selection:{selected:true,mode:'review'}};
 t.model.requests=[request];t.model.opportunities=[job];t.a.setSelected('one');
 assert.match(t.a.detail(),/El envío quedó sin confirmar/);assert.match(t.a.detail(),/data-copy-recovery="specific-send"/);
 assert.match(t.a.activityWork(),/El envío quedó sin confirmar/);assert.doesNotMatch(t.a.detail(),/data-approve=|data-retry=/);
});
test('a stale running task records its date and gives no claim of permanent connection',()=>{
 const t=setup();t.model.requests=[{id:'old',type:'review',status:'running',updatedAt:'2020-01-01T10:00:00Z',executionId:'original'}];
 const html=t.a.activityWork();assert.match(html,/Actividad pendiente de confirmar/);assert.match(html,/Último registro/);assert.match(html,/data-copy-recovery="old"/);assert.equal(t.model.requests[0].status,'running');
});
test('a withdrawn offer keeps a started uncertain send visible without restoring send controls',()=>{
 const t=setup(),request={id:'revoked-send',opportunityId:'one',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-09-01T10:00:00Z',updatedAt:'2026-09-01T10:05:00Z'};
 const job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí, aclarar',requests:[request],packages:[],questions:[],missing:['Revisión'],draft:{recipient:'',message:'',messageUsage:'unused'},answers:{},conditions:{},selection:{selected:false,mode:'review'}};
 t.model.requests=[request];t.model.opportunities=[job];t.a.setSelected('one');
 const detail=t.a.detail(),work=t.a.activityWork();
 assert.match(detail,/data-copy-recovery="revoked-send"/);assert.match(detail,/El permiso está retirado/);
 assert.match(work,/data-copy-recovery="revoked-send"/);assert.doesNotMatch(detail,/data-approve=|data-retry=|data-select=/);
 assert.equal(request.status,'cancelled');assert.equal(job.selection.selected,false);
 request.deliveryCheck={outcome:'not_sent',packageId:'original',at:new Date().toISOString(),proof:'TEST: portal comprobado sin solicitud'};
 assert.equal(t.a.activityWork(),'');assert.doesNotMatch(t.a.detail(),/data-copy-recovery="revoked-send"|data-retry=/);
 assert.equal(request.status,'cancelled');
});
test('offer assessments show reason, source and unknowns, and hide an obsolete reason',()=>{
 const t=setup(),job={id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Sí, aclarar',requests:[],packages:[],questions:[],missing:['review'],draft:{recipient:'',message:'',messageUsage:'unused'},answers:{},conditions:{},assessment:{reason:'Experiencia defendible en BI.',at:new Date().toISOString(),isCurrent:true,unknowns:['Parte fija pendiente'],references:[{url:'https://example.org/offer',text:'Modelos de datos'}]}};
 t.model.opportunities=[job];t.a.setSelected('one');let html=t.a.detail();assert.match(html,/Encaje contigo/);assert.doesNotMatch(html,/Parte fija pendiente|Consultar fuente|assessment-details|data-checks=/);assert.equal(job.assessment.unknowns[0],'Parte fija pendiente');assert.equal(job.assessment.references[0].url,'https://example.org/offer');
 job.assessment.isCurrent=false;html=t.a.detail();assert.match(html,/Esta valoración necesita actualizarse/);assert.doesNotMatch(html,/Experiencia defendible en BI/);
});
test('Help offers checked backups while retaining the three main navigation tabs',()=>{
 const t=setup();const html=t.a.backupsPage();assert.match(html,/Crear copia de seguridad/);assert.match(html,/carpeta aparte/);assert.doesNotMatch(t.a.applyPage(),/Crear copia de seguridad/);
});
test('outcome tabs use the requested order and details expose the appropriate subtle actions',()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Investigar',apply:'Sí',conditions:{},requests:[],packages:[],questions:[],missing:['CV'],draft:{messageUsage:'unused'},answers:{}};
 t.model.opportunities=[{...base,id:'decide'},{...base,id:'discarded',archivedAt:'2026-10-01',archiveOutcome:'discarded'},
  {...base,id:'sent',state:'Enviada',sent:{at:'2026-10-01'}},{...base,id:'rejected',state:'Rechazada',sent:{at:'2026-10-01'}}];
 const html=t.a.applyPage(),before=structuredClone(t.model);
 assert.deepEqual([...html.matchAll(/data-flow-filter="([^"]+)"/g)].map(m=>m[1]),['todas','descartadas','sin-elegir','seguimiento','cerradas','rechazadas','logradas']);
 assert.doesNotMatch(html,/Archivada|Archivar/);
 for(const j of t.model.opportunities){
  t.a.setSelected(j.id);const detail=t.a.detail();
  assert.match(detail,new RegExp('class="offer-change" data-change="'+j.id+'"'));
  assert.equal(/data-offer-outcome="discard"/.test(detail),j.id==='decide');
  assert.equal(/data-offer-outcome="close"/.test(detail),['sent','rejected'].includes(j.id));
  if(j.id==='sent')assert.match(detail,/data-offer-outcome="close"[^>]*>Cerrada<\/button>/);
 }
 assert.deepEqual(t.model,before);
});
test('individual outcome actions go through the guarded bulk writer and keep the current offer open',async()=>{
 const t=setup(),job={id:'one',company:'Empresa',title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:['CV'],draft:{},answers:{}};
 t.model.opportunities=[job];t.a.setSelected(job.id);t.a.setScreenState('detalle');const operations=[];
 t.env.fetch=async(_,options)=>{operations.push(JSON.parse(options.body).operation);return {ok:true,json:async()=>({state:t.model})};};
 await t.click({dataset:{offerOutcome:'discard',jobId:'one'}});
 assert.deepEqual(operations[0],{kind:'ui-bulk-action',action:'discard',targets:[{id:'one'}],expectedRevision:0});
 assert.equal(t.a.getView().screen,'detalle');
 job.sent={at:'2026-10-01'};job.state='Enviada';await t.click({dataset:{offerOutcome:'reject',jobId:'one'}});
 assert.equal(operations[1].action,'reject');
});
test('mixed bulk selection closes only the displayed prospects or submitted applications',()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:['CV'],draft:{}};
 t.model.opportunities=[{...base,id:'decide'},{...base,id:'sent',state:'Enviada',sent:{at:'2026-10-01'}},
  {...base,id:'discarded',archivedAt:'2026-10-01',archiveOutcome:'discarded'}];
 ['decide','sent','discarded'].forEach(id=>t.a.getTableSelection().add(id));const html=t.a.bulkToolbar();
 assert.match(html,/data-bulk-action="discard" data-bulk-targets="\[&quot;decide&quot;\]"[^>]*>Descartar \(1\)/);
 assert.match(html,/data-bulk-action="close" data-bulk-targets="\[&quot;sent&quot;\]"[^>]*>Cerrar seguimiento \(1\)/);
 assert.doesNotMatch(html,/Archivar/);
});
test('offer detail retains the explicit modality and contract shown in its table',()=>{
 const t=setup(),job={country:'Canadá',workMode:'Híbrido',contract:'Temporal',conditions:{'Remoto España':'Pendiente',Indefinido:'Pendiente'}};
 const before=structuredClone(job),html=t.a.offerConditions(job);
 assert.match(html,/<dt>Modalidad<\/dt><dd>Híbrido<\/dd>/);
 assert.match(html,/<dt>Contrato<\/dt><dd>Temporal<\/dd>/);
 assert.doesNotMatch(html,/España/);assert.deepEqual(job,before);
});
test('offer detail uses the latest travel evidence and preserves explicit trip counts',()=>{
 const t=setup(),job={conditions:{},evidence:[
  {'Condición':'Viajes',Estado:'Sí',Comprobada:46000,'Texto o motivo':'No hay viajes.'},
  {'Condición':'Viajes',Estado:'Sí',Comprobada:46002,'Texto o motivo':'Un viaje mensual.'},
  {'Condición':'Viajes',Estado:'Sí',Comprobada:46001,'Texto o motivo':'Un viaje trimestral.'}
 ]};
 const before=structuredClone(job);
 assert.match(t.a.offerConditions(job),/Un viaje mensual/);
 assert.doesNotMatch(t.a.offerConditions(job),/No hay viajes|Un viaje trimestral/);
 assert.deepEqual(job,before);
 job.evidence.push({'Condición':'Viajes',Estado:'No',Comprobada:46002,'Texto o motivo':'Tres viajes mensuales.'});
 assert.match(t.a.offerConditions(job),/Tres viajes mensuales/);
 assert.doesNotMatch(t.a.offerConditions(job),/Un viaje mensual|No hay viajes/);
 job.evidence.push({'Condición':'Viajes',Estado:'Pendiente',Comprobada:46003,'Texto o motivo':'Comprobar el anuncio actualizado.'});
 assert.match(t.a.offerConditions(job),/<p class="conditions-pending"><span>Por concretar:<\/span> [^<]*desplazamientos/);assert.doesNotMatch(t.a.offerConditions(job),/<dt>Desplazamientos<\/dt>/);
 job.minimumTrips=2;assert.match(t.a.offerConditions(job),/Al menos 2 viajes al mes/);
});
test('offer conditions show confirmed facts and group unpublished ones in a single line',()=>{
 const t=setup(),job={workMode:'Remoto',contract:'Indefinido',conditions:{},salary:null,schedule:null};
 const html=t.a.offerConditions(job);
 assert.match(html,/<dt>Modalidad<\/dt><dd>Remoto<\/dd>/);assert.match(html,/<dt>Contrato<\/dt><dd>Indefinido<\/dd>/);
 assert.match(html,/<p class="conditions-pending"><span>Por concretar:<\/span> salario publicado, parte fija, desplazamientos y horario\.<\/p>/);
 assert.doesNotMatch(html,/Sin concretar|Sin desglosar/);
 const none=t.a.offerConditions({conditions:{}});assert.doesNotMatch(none,/<dl/);assert.match(none,/Por concretar:<\/span> modalidad, contrato, salario publicado, parte fija, desplazamientos y horario\./);
 job.salary='35.000 € brutos';job.schedule='Jornada intensiva en verano';job.fixedSalary=35000;job.fixedSalaryCurrency='EUR';job.minimumTrips=0;
 const full=t.a.offerConditions(job);assert.doesNotMatch(full,/conditions-pending/);assert.match(full,/<dt>Horario<\/dt><dd>Jornada intensiva en verano<\/dd>/);
});
test('empty table values recede visually and are announced as missing data',()=>{
 const t=setup(),job={id:'one',company:'Uno',title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},conditions:{},country:'España',workMode:'Remoto'};
 t.model.opportunities=[job];const html=t.a.applyPage();
 assert.match(html,/<td>España<\/td><td>Remoto<\/td><td><span class="empty-value" aria-hidden="true">—<\/span><span class="sr-only">Sin dato<\/span><\/td>/);
 assert.match(html,/class="salary-cell"[^>]*><span><span class="empty-value" aria-hidden="true">—<\/span><span class="sr-only">Sin dato<\/span><\/span>/);
});
test('the daily summary keeps a search issue concrete without raw addresses',()=>{
 const t=setup();t.model.requests=[{id:'search',type:'discovery',status:'done',summary:'Resultados parciales',updatedAt:'2026-09-30T10:00:00Z',activityResult:{newOfferCount:2,health:[{sourceId:'web',company:'Web ficticia',status:'partial',checkedAtUtc:'2026-09-30T09:00:00Z',errors:['Enlace de paginación no comprobado: https://example.org/jobs?page=2']}],publicSources:[{id:'web'}]}}];
 const html=t.a.agentPage();assert.match(html,/Web ficticia: Enlace de paginación no comprobado/);assert.doesNotMatch(html,/example\.org\/jobs\?page=2/);
});
test('confirmed fixed salary retains its own currency after the profile currency changes',()=>{
 const t=setup();t.model.searchContext.currency='USD';
 const job={conditions:{'Remoto España':'No',Indefinido:'Contradicción'},fixedSalary:40000,fixedSalaryCurrency:'EUR',salary:'40.000 EUR brutos anuales'};
 const html=t.a.offerConditions(job);
 assert.match(html,/<dt>Parte fija<\/dt><dd>40\.000 EUR brutos\/año<\/dd>/);assert.doesNotMatch(html,/40\.000 USD/);
 assert.match(html,/<dt>Modalidad<\/dt><dd>No remoto desde España<\/dd>/);assert.match(html,/<dt>Contrato<\/dt><dd>Datos contradictorios<\/dd>/);
 delete job.fixedSalaryCurrency;
 assert.match(t.a.offerConditions(job),/40\.000 brutos\/año · moneda por comprobar/);assert.doesNotMatch(t.a.offerConditions(job),/40\.000 USD/);
 job.fixedSalary=30000;job.fixedSalaryMax=40000;job.fixedSalaryCurrency='EUR';job.minimumTrips=2;
 assert.match(t.a.offerConditions(job),/<dt>Parte fija<\/dt><dd>30\.000–40\.000 EUR brutos\/año<\/dd>/);
 assert.match(t.a.offerConditions(job),/Al menos 2 viajes al mes/);delete job.fixedSalaryMax;
 job.fixedSalary=0;assert.match(t.a.offerConditions(job),/<dt>Parte fija<\/dt><dd>0 EUR brutos\/año<\/dd>/);
 job.conditions['Remoto España']='Contradicción';assert.match(t.a.offerConditions(job),/<dt>Modalidad<\/dt><dd>Datos contradictorios<\/dd>/);
});
test('every table stage marks a withdrawn started send for attention and its detail prioritizes recovery',()=>{
 const t=setup(),request={id:'original-send',type:'send',status:'cancelled',packageId:'original',startedAt:'2026-09-01T10:00:00Z',updatedAt:'2026-09-01T10:05:00Z'};
 const job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí, aclarar',requests:[request],packages:[],questions:[],missing:['review'],draft:{messageUsage:'unused'},answers:{},conditions:{}};
 t.model.opportunities=[job];t.model.requests=[request];
 for(const state of ['Preparar','Cerrada'])for(const apply of ['Sí, aclarar','No','Resolver conflicto']){
  job.state=state;job.apply=apply;
  for(const kind of ['elegir','solicitar','seguir']){
   const record=t.a.flowRecord(job,kind);assert.equal(record.action,undefined);assert.equal(record.status,'Por atender');assert.equal(record.tone,'blocked');
   t.a.setSelected('one');const detail=t.a.detail();assert.match(detail,/data-copy-recovery="original-send"/);assert.match(detail,/permiso está retirado/);assert.doesNotMatch(detail,/data-investigate|data-select|data-approve|data-retry/);
  }
  assert.match(t.a.applyPage(),/>Por atender<\/span>/);assert.doesNotMatch(t.a.applyPage(),/data-copy-recovery=/);
 }
 job.state='Preparar';job.apply='Sí, aclarar';request.deliveryCheck={outcome:'not_sent',packageId:'original',at:new Date().toISOString(),proof:'TEST: portal sin solicitud original'};
 assert.doesNotMatch(t.a.applyPage(),/data-copy-recovery="original-send"/);assert.match(t.a.detail(),/data-selection-mode="review"/);assert.equal(request.status,'cancelled');
});
test('Help and copied continuation explain the permitted next steps without starting the agent',async()=>{
 const t=setup(),copied=[];t.model.requests=[{id:'review-one',type:'review',status:'queued',opportunityId:'one'}];
 t.env.navigator={clipboard:{writeText:async text=>copied.push(text)}};t.env.fetch=async()=>{throw Error('Copy must not start or save work');};
 assert.match(UI.nextAction({selection:{selected:true,mode:'auto'},requests:[{type:'review',status:'queued'}]}),/Permites enviar esta oferta.*Continúa con Stubbs Jobs/);
 assert.match(t.a.copyRequestButton('Copiar petición pendiente'),/siguientes pasos permitidos de esas mismas solicitudes/);
 await t.a.saveVisibleChangesAndCopy();assert.deepEqual(copied,['Continúa con Stubbs Jobs']);assert.equal(t.model.requests[0].status,'queued');
 assert.doesNotMatch(t.a.backupsPage(),/Selecciona ofertas|data-copy-setup/);
});
test('backup warnings find pending drafts outside the visible screen and only in this workspace',()=>{
 const t=setup();t.a.setScreenState('copias');
 const draft=JSON.stringify({values:{currentCity:'Cádiz'},expected:{currentCity:'Madrid'},shown:{currentCity:'Madrid'},attempt:null});
 t.storage.set('stubbs_jobs-draft:datos:global',draft);
 t.rawStorage.set('stubbs_jobs-workspace:another-workspace:stubbs_jobs-draft:experiencia:global',JSON.stringify({values:{text:'Datos de otra carpeta'},shown:{text:''}}));
 t.storage.set('stubbs_jobs-draft:busqueda:global',JSON.stringify({values:{minimumFixed:'32000',maxTrips:''},shown:{minimumFixed:32000,maxTrips:null},expected:{minimumFixed:32000,maxTrips:null}}));
 t.storage.set('stubbs_jobs-action:other',JSON.stringify({id:'pending-action'}));
 const html=t.a.backupsPage();assert.match(html,/Hay borradores sin guardar/);assert.match(html,/No se incluirán en la copia/);assert.match(html,/permanecerán en este navegador/);
 assert.match(html,/data-backup-draft="stubbs_jobs-draft:datos:global">Sobre mi/);assert.match(html,/Crear copia de los datos guardados/);assert.match(html,/data-backup-saved-only="1"/);
 assert.doesNotMatch(html,/Datos de otra carpeta|>Experiencia laboral<|>Qué buscas<\/button>/);assert.equal(t.a.backupDrafts().length,1);assert.equal(t.a.isDirty(),false);
 assert.equal(t.storage.get('stubbs_jobs-draft:datos:global'),draft);
});
test('a backup draft link follows the real navigation event and preserves the saved browser draft',async()=>{
 const t=setup();t.a.setScreenState('copias');
 const key='stubbs_jobs-draft:datos:global',draft=JSON.stringify({values:{currentCity:'Cádiz'},expected:{currentCity:'Madrid'},shown:{currentCity:'Madrid'},attempt:null});
 t.storage.set(key,draft);t.env.fetch=async path=>{assert.match(path,/^\/api\/state/);return {ok:true,json:async()=>t.model};};
 await t.click({dataset:{backupDraft:key}});assert.equal(t.a.getView().screen,'perfil');assert.equal(t.a.getView().selected,null);assert.equal(t.storage.get(key),draft);
});
test('a draft arriving after Help rendered is disclosed before a saved-data backup can be created',async()=>{
 const t=setup();t.a.setScreenState('copias');t.a.render();const calls=[];
 const key='stubbs_jobs-draft:cambio:global',draft=JSON.stringify({values:{message:'Cambio pendiente de guardar'},expected:{message:''},shown:{message:''},attempt:null});t.storage.set(key,draft);
 t.env.fetch=async path=>{calls.push(path);assert.equal(path,'/api/backup');return {ok:true,json:async()=>({name:'TEST-backup.zip',download:'/api/document?id=backup',files:3,revision:0})};};
 await t.click({dataset:{createBackup:'1'},disabled:false});assert.deepEqual(calls,[]);assert.match(t.env.document.querySelector('#main').innerHTML,/Crear copia de los datos guardados/);
 assert.match(t.env.document.querySelector('#toast').innerHTML,/Hay borradores sin guardar/);
 await t.click({dataset:{createBackup:'1',backupSavedOnly:'1'},disabled:false});assert.deepEqual(calls,['/api/backup']);assert.match(t.env.document.querySelector('#main').innerHTML,/Copia comprobada: 3 archivos/);
 assert.equal(t.storage.get(key),draft);assert.deepEqual(t.model.requests,[]);assert.equal(t.model.revision,0);
});

test('historic absence remains visible in the table and keeps its recheck guard in offer and review',()=>{
 const t=setup(),request={id:'original',opportunityId:'one',type:'send',status:'cancelled',packageId:'old',startedAt:'2026-09-01T10:00:00Z',deliveryRecheckRequired:true,deliveryCheck:{outcome:'not_sent',packageId:'old',at:'2026-09-01T10:05:00Z',proof:'TEST retained absence'}};
 const job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí',requests:[request],packages:[{id:'new',isCurrent:true,cvUrl:'/cv',payload:{answers:{},messageUsage:'unused'}}],questions:[],missing:[],fingerprint:'new',draft:{messageUsage:'unused'},answers:{},conditions:{},selection:{selected:true,mode:'review'}};
 t.model.requests=[request];t.model.opportunities=[job];t.a.setSelected('one');t.a.setReviewSnapshot(structuredClone(job));
 assert.match(t.a.applyPage(),/>Por atender<\/span>/);assert.doesNotMatch(t.a.applyPage(),/data-copy-recovery=|data-select=/);
 for(const html of [t.a.detail(),t.a.activityWork()]){assert.match(html,/data-copy-recovery="original"/);assert.match(html,/comprobar de nuevo/);assert.doesNotMatch(html,/envío sin confirmar|data-retry=/i);}
 assert.match(t.a.reviewPage(),/data-approve="one" disabled/);assert.equal(request.status,'cancelled');
 request.deliveryRecheckRequired=false;request.deliveryCheck.at=new Date().toISOString();t.a.setReviewSnapshot(structuredClone(job));
 assert.doesNotMatch(t.a.reviewPage(),/data-approve="one" disabled/);assert.doesNotMatch(t.a.detail(),/data-copy-recovery="original"/);assert.equal(t.a.activityWork(),'');
});

test('superseded attempts retain their proof and the actual successor link without returning to pending work',async()=>{
 const t=setup(),original={id:'original',opportunityId:'one',type:'send',status:'queued',supersededByRequestId:'successor',summary:'OLD BLOCKER',deliveryCheck:{at:'2026-09-01T10:05:00Z',proof:'TEST original absence'}},successor={id:'successor',opportunityId:'one',type:'send',status:'running',updatedAt:new Date().toISOString()};
 const job={id:'one',company:'Empresa ficticia',state:'Preparar',apply:'Sí',requests:[original,successor],packages:[],questions:[],missing:[],draft:{messageUsage:'unused'},answers:{},conditions:{},selection:{selected:true,mode:'review'}};
 t.model.requests=[original,successor];t.model.opportunities=[job];t.a.setSelected('one');
 assert.match(t.a.detail(),/Enviando/);assert.doesNotMatch(t.a.activityWork(),/OLD BLOCKER|data-copy-recovery="original"/);
 assert.equal(original.deliveryCheck.proof,'TEST original absence');assert.equal(original.supersededByRequestId,'successor');assert.doesNotMatch(t.a.detail(),/TEST original absence|data-checks=/);
 let anchored;t.env.document.getElementById=id=>({scrollIntoView(){anchored=id;},querySelector(){return null;}});t.env.fetch=async()=>({ok:true,json:async()=>t.model});
 await t.a.setScreen('comprobaciones','one');assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,'one');assert.equal(anchored,undefined);
 const copied=[];t.env.navigator={clipboard:{writeText:async text=>copied.push(text)}};t.model.requests=[original];t.a.setScreenState('copias');t.a.setSelected(null);
 await t.a.saveVisibleChangesAndCopy();assert.equal(copied.length,0);assert.equal(original.status,'queued');
});

test('an old combined profile draft is consultable and copied without opening a form that ignores it',async()=>{
 const t=setup(),key='stubbs_jobs-draft:perfil:global',draft=JSON.stringify({values:{currentCity:'CIUDAD TEST',willingToTravel:false,empty:null},shown:{currentCity:'',willingToTravel:true,empty:''},expected:{currentCity:''},attempt:{id:'OLD ATTEMPT'}});
 t.storage.set(key,draft);t.a.setScreenState('copias');const html=t.a.backupsPage();
 assert.match(html,/Datos de Mi perfil de una versión anterior/);assert.match(html,/data-copy-backup-draft="stubbs_jobs-draft:perfil:global"/);assert.match(html,/CIUDAD TEST/);assert.doesNotMatch(html,/data-backup-draft="stubbs_jobs-draft:perfil:global"/);
 const copied=[];t.env.navigator={clipboard:{writeText:async text=>copied.push(text)}};t.env.fetch=async()=>{throw Error('Copy must not write');};
 await t.click({dataset:{copyBackupDraft:key}});assert.equal(copied.length,1);assert.match(copied[0],/CIUDAD TEST/);assert.match(copied[0],/No cambies permisos ni inicies búsquedas o envíos/);assert.doesNotMatch(copied[0],/OLD ATTEMPT/);
 assert.equal(t.storage.get(key),draft);assert.equal(t.a.getView().screen,'copias');assert.equal(t.model.revision,0);
});

test('backup disclosure preserves each offer draft route and exposes a removed offer draft for consultation',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa',draft:{}}];const keys=['perfil:one','editar:one','cambio:one','nueva:global','editar:removed'];
 for(const part of keys)t.storage.set('stubbs_jobs-draft:'+part,JSON.stringify({values:{message:'TEST '+part},shown:{message:''},expected:{message:''}}));
 const drafts=t.a.backupDrafts();
 for(const part of keys.slice(0,4)){const draft=drafts.find(item=>item.key.endsWith(part));assert.equal(draft.page,part.split(':')[0]);assert.equal(draft.id,part.endsWith('global')?null:'one');}
 const removed=drafts.find(item=>item.key.endsWith('editar:removed'));assert.equal(removed.page,null);assert.match(removed.content[0][1],/TEST editar:removed/);
 assert.match(t.a.backupsPage(),/data-copy-backup-draft="stubbs_jobs-draft:editar:removed"/);
});

test('coverage shows partial portal scope and dates with proof and previous failures folded',()=>{
 const t=setup();Object.assign(t.model,{publicSources:[{id:'portal',company:'Portal test'},{id:'pending',company:'Web pendiente'}],health:[{sourceId:'portal',company:'Portal test',status:'ok',method:'manual',scope:'Solo los 12 anuncios de Analista en Cádiz',sourceUrl:'https://example.org/jobs',checkedAtUtc:'2026-10-01T10:00:00Z',lastSuccessUtc:'2026-10-01T10:00:00Z',coverage:{scope:'Solo los 12 anuncios de Analista en Cádiz',pages:['https://example.org/jobs?page=1'],completeness:'observed_pages'}}],manualReviews:[{id:'current',sourceId:'portal',name:'Portal test',sourceUrl:'https://example.org/jobs',checkedAt:'2026-10-01T10:00:00Z',scope:'Solo los 12 anuncios de Analista en Cádiz',outcome:'reviewed',proof:'TEST MANUAL PROOF'},{id:'old',sourceId:'portal',checkedAt:'2026-09-30T10:00:00Z',scope:'Listado no accesible',outcome:'blocked',issues:['TEST OLD MANUAL ERROR'],proof:'TEST OLD MANUAL PROOF'}],scanChecks:[{sourceId:'portal',checkedAtUtc:'2026-09-29T10:00:00Z',errors:['TEST OLD SCAN ERROR'],coverage:{scope:'Página de inicio',completeness:'error'}}],portalAccess:{linkedin:{status:'ready',checkedAt:'2026-10-01T09:00:00Z'}}});
 const html=t.a.coverage();assert.match(html,/Portal test · Revisado según el alcance indicado/);assert.match(html,/Comprobación: 1 oct 2026, 12:00/);assert.match(html,/Alcance: Solo los 12 anuncios de Analista en Cádiz · Solo páginas observadas/);
 assert.match(html,/href="https:\/\/example.org\/jobs"/);assert.doesNotMatch(html,/Pruebas y páginas comprobadas|TEST MANUAL PROOF/);assert.equal(t.model.manualReviews[0].proof,'TEST MANUAL PROOF');
 assert.doesNotMatch(html,/source-previous-checks|TEST OLD MANUAL ERROR|TEST OLD SCAN ERROR/);assert.equal(t.model.manualReviews[1].issues[0],'TEST OLD MANUAL ERROR');assert.equal(t.model.scanChecks[0].errors[0],'TEST OLD SCAN ERROR');assert.doesNotMatch(html,/coverage-problems/);
 assert.match(html,/según el alcance registrado/);assert.match(html,/Por revisar: Web pendiente/);assert.match(html,/El acceso comprobado no confirma que se hayan revisado las ofertas del portal/);
});

test('a retained search report never borrows newer coverage or portal checks',async()=>{
 const t=setup(),snapshot={newOfferCount:0,publicSources:[{id:'one'}],health:[{sourceId:'one',company:'Web del resultado',status:'ok',method:'scan',checkedAtUtc:'2026-09-29T09:00:00Z',scope:'Listado original',sourceUrl:'https://example.org/original',coverage:{scope:'Listado original',pages:[],completeness:'returned_listing'}}],manualReviews:[],scanChecks:[],portalAccess:{}};
 t.model.requests=[{id:'search',type:'discovery',status:'done',updatedAt:'2026-09-29T10:00:00Z',summary:'TEST retained result',activityResult:snapshot}];t.model.health=[{sourceId:'two',company:'Nueva comprobación',status:'error',checkedAtUtc:'2026-10-01T10:00:00Z',scope:'Nuevo alcance',errors:['NEW ERROR']}];t.model.portalAccess={linkedin:{status:'blocked',checkedAt:'2026-10-01T10:00:00Z'}};
 t.env.fetch=async()=>({ok:true,json:async()=>t.model});await t.a.setScreen('informe','search');const html=t.env.document.querySelector('#main').innerHTML;
 assert.match(html,/Alcance: Listado original/);assert.match(html,/29 sept 2026, 11:00/);assert.doesNotMatch(html,/Nueva comprobación|Nuevo alcance|NEW ERROR|Acceso bloqueado/);assert.deepEqual(t.model.requests[0].activityResult,snapshot);
});

function desktopTableFixture(native=true){
 const t=setup(),main=t.env.document.querySelector('#main'),columns=['company','title','mode','salary','deadline','activity','status'];let menus=[],html='',paints=0,table={scrollLeft:0,scrollTop:0};
 t.model.opportunities=['Álfa','Beta','Gamma'].map((company,index)=>({id:'offer-'+index,company,title:'Analítica',state:'Preparar',apply:'Sí',conditions:{'Remoto España':'Sí'},salary:'40.000 EUR',requests:[],packages:[],questions:[],missing:['review'],draft:{messageUsage:'unused',requiredAnswers:[]},answers:{},answerOverrides:{},fieldDefinitions:{},selection:{selected:false}}));
 t.env.window.innerWidth=1024;t.env.window.innerHeight=768;
 t.env.window.scrollTo=(left,top)=>{t.env.window.scrollY=typeof left==='object'?left.top:top;};
 const node=(tag,dataset={})=>({tagName:tag,dataset,id:'',name:'',textContent:'',focus(){t.env.document.activeElement=this;},closest(selector){if(selector==='form')return null;if(selector==='.column-menu')return this.panel&&this.panel.parentElement!==this.menu?null:this.menu||null;if(selector==='.column-menu-panel')return this.panel||null;if(selector==='.column-value')return this.label||null;return null;}});
 function makeMenu(key){
  const menu={dataset:{menuTab:'solicitar',menuKey:key},open:false};const summary=node('SUMMARY');summary.parentElement=menu;summary.menu=menu;summary.textContent=key;summary.getBoundingClientRect=()=>({left:key==='status'?970:40,top:160,bottom:192});
  const search=node('INPUT',{tableOptionSearch:'1'}),values={scrollTop:0},panel={style:{},scrollHeight:410,items:[],removeAttribute(){},contains(element){return element===search||this.items.some(item=>item===element||item.label===element);},querySelector(selector){return selector==='[data-table-option-search]'?search:selector==='.column-menu-values'?values:null;},querySelectorAll(selector){return selector==='[data-option-label]'?this.items.map(item=>item.label):selector==='[data-table-value]'?this.items:selector==='button,input'?[search,...this.items]:[];}};
  panel.parentElement=menu;search.panel=panel;search.menu=menu;
  if(native){panel.showPopover=()=>{panel.shown=true;};panel.hidePopover=()=>{panel.shown=false;};}
  Object.defineProperty(values,'innerHTML',{get(){return this.html||'';},set(value){this.html=value;panel.items=[...value.matchAll(/aria-label="([^"]*)" data-table-value="([^"]*)" data-table-key="([^"]*)" data-table-tab="([^"]*)" (checked)?/g)].map(match=>{const input=node('INPUT',{tableValue:match[2],tableKey:match[3],tableTab:match[4]}),label={dataset:{optionLabel:match[1]},hidden:false};input.checked=Boolean(match[5]);input.panel=panel;input.menu=menu;input.label=label;return input;});}});
  menu.contains=element=>element===summary||panel.contains(element);menu.appendChild=child=>{child.parentElement=menu;};menu.querySelector=selector=>selector==='summary'?summary:selector==='.column-menu-panel'?panel:null;menu.querySelectorAll=selector=>panel.querySelectorAll(selector);
  return {menu,summary,panel,search,values};
 }
 main.querySelector=selector=>{if(selector==='.workflow-table-wrap')return table;if(selector==='.column-menu[open]')return menus.find(item=>item.menu.open)?.menu||null;const key=selector.match(/data-menu-key="([^"]+)"/);return key?menus.find(item=>item.menu.dataset.menuKey===key[1])?.menu||null:null;};
 main.querySelectorAll=selector=>selector==='button,summary,input,textarea,select,a'?menus.flatMap(item=>[item.summary,...(item.panel.parentElement===item.menu?[item.search,...item.panel.items]:[])]):selector==='form[data-form]'?[]:[];
 main.contains=element=>menus.some(item=>item.summary===element||item.panel.parentElement===item.menu&&item.panel.contains(element));
 Object.defineProperty(main,'innerHTML',{get(){return html;},set(value){html=value;paints++;menus=columns.map(makeMenu);table={scrollLeft:0,scrollTop:0};}});
 const body={children:[],appendChild(panel){this.children.push(panel);panel.parentElement=this;}};t.env.document.body=body;
 t.env.fetch=async()=>({ok:true,json:async()=>({...t.model,version:'desktop-fixture'})});t.a.render();
 return {t,main,body,getMenu:key=>menus.find(item=>item.menu.dataset.menuKey===key),getTable:()=>table,paintCount:()=>paints};
}

test('desktop headers sort directly and preserve explicit filters across offer groups',async()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};t.model.opportunities=[{...base,id:'one',company:'Beta'},{...base,id:'two',company:'Álfa',selection:{selected:true,mode:'review'}}];
 let html=t.a.applyPage();assert.match(html,/class="column-title" data-table-sort="company"/);assert.match(html,/aria-label="Filtrar empresa"/);assert.doesNotMatch(html,/Ordenar A a Z/);
 await t.click({dataset:{tableSort:'company',tableTab:'solicitar',tableDirection:'1'}});html=t.a.applyPage();assert(html.indexOf('data-job-row="two"')<html.indexOf('data-job-row="one"'));assert.match(html,/data-table-direction="-1"/);
 t.a.setTableFilter('solicitar','company',['Álfa']);await t.click({dataset:{flowFilter:'elegidas',filterTab:'solicitar'}});html=t.a.applyPage();assert.match(html,/Empresa: Álfa/);assert.match(html,/Orden: Empresa ↑/);assert.match(html,/data-job-row="two"/);
 await t.click({dataset:{flowFilter:'sin-elegir',filterTab:'solicitar'}});assert.match(t.a.applyPage(),/Ninguna oferta coincide con estos filtros/);assert.match(t.a.applyPage(),/Empresa: Álfa/);
 await t.click({dataset:{clearTable:'solicitar'}});assert.match(t.a.applyPage(),/data-job-row="one"/);assert.match(t.a.applyPage(),/Orden: Empresa ↑/);
 await t.click({dataset:{clearOrder:'solicitar'}});assert.doesNotMatch(t.a.applyPage(),/Orden: Empresa/);assert.deepEqual(t.model.requests,[]);
});

test('filter catalogues are lazy and the last column uses the top layer within a 1024px viewport',async()=>{
 const {t,getMenu}=desktopTableFixture();assert.doesNotMatch(t.a.applyPage(),/class="column-value"/);assert.equal(Object.keys(t.a.getTableState().choices).length,0);
 const item=getMenu('status');await t.click(item.summary);assert.equal(t.a.getOpenFilter(),item.menu);assert.equal(item.panel.shown,true);assert.equal(item.panel._topLayer,true);assert.equal(t.env.document.activeElement,item.search);
 assert.equal(Object.keys(t.a.getTableState().choices).length,1);assert.equal(t.a.getTableState().choices.status.length,1);assert(Number.parseInt(item.panel.style.left)+260<=1012);
 await t.dispatch('keydown',item.search,{key:'Escape'});assert.equal(item.menu.open,false);assert.equal(item.panel.shown,false);assert.equal(t.env.document.activeElement,item.summary);assert.equal(t.model.revision,0);
});

test('a filter uses its actual CSS width and the viewport space excluding scrollbars at desktop and zoom',async()=>{
 for(const [windowWidth,clientWidth] of [[1024,1009],[640,625]]){
  const {t,getMenu}=desktopTableFixture();t.env.window.innerWidth=windowWidth;t.env.document.documentElement={clientWidth,clientHeight:740};const item=getMenu('status');
  item.summary.getBoundingClientRect=()=>({left:clientWidth-39,top:160,bottom:192});item.panel.getBoundingClientRect=()=>({width:280,height:410});await t.click(item.summary);
  const left=Number.parseFloat(item.panel.style.left),top=Number.parseFloat(item.panel.style.top);assert(left>=12);assert(left+280<=clientWidth-12);assert(top>=12);assert(top+410<=740-12);assert.equal(item.panel.style.maxWidth,(clientWidth-24)+'px');assert.equal(item.panel.shown,true);
 }
});

test('filters outside an overflow table use a real fallback and close on outside click or resize',async()=>{
 const {t,getMenu,body}=desktopTableFixture(false);const item=getMenu('company');await t.click(item.summary);assert.equal(item.panel.parentElement,body);assert.equal(item.panel._detached,true);assert(item.panel.items.length===3);
 await t.dispatch('click',{closest(){return null;}});assert.equal(item.panel.parentElement,item.menu);assert.equal(item.menu.open,false);assert.equal(t.env.document.activeElement,item.summary);
 await t.click(item.summary);t.dispatchWindow('resize');assert.equal(item.panel.parentElement,item.menu);assert.equal(t.a.getOpenFilter(),null);
});

test('a detached fallback filter handles its checkbox and restores focus after new state',async()=>{
 const {t,getMenu,body}=desktopTableFixture(false);let item=getMenu('company');await t.click(item.summary);const input=item.panel.items.find(input=>input.dataset.tableValue==='Beta');assert.equal(input.closest('.column-menu'),null);input.checked=false;input.focus();await t.dispatch('change',input);
 item=getMenu('company');assert.equal(item.panel.parentElement,body);assert.equal(t.env.document.activeElement.dataset.tableValue,'Beta');assert.equal(t.env.document.activeElement.checked,false);assert.equal(t.env.document.activeElement.closest('.column-menu'),null);
 await t.a.refresh(true);assert.equal(t.env.document.activeElement.dataset.tableValue,'Beta');assert.equal(t.env.document.activeElement.checked,false);assert.equal(getMenu('company').panel.parentElement,body);
});

test('an open lazy filter preserves query, value, scroll and checkbox focus through polling',async()=>{
 const {t,getMenu,getTable}=desktopTableFixture();let item=getMenu('company');await t.click(item.summary);item.search.value='alfa';await t.dispatch('input',item.search);assert.equal(item.panel.items.find(input=>input.dataset.tableValue==='Álfa').label.hidden,false);assert.equal(item.panel.items.find(input=>input.dataset.tableValue==='Beta').label.hidden,true);item.search.value='be';await t.dispatch('input',item.search);
 item.values.scrollTop=85;getTable().scrollTop=440;getTable().scrollLeft=310;const input=item.panel.items.find(input=>input.dataset.tableValue==='Beta');input.checked=false;input.focus();await t.dispatch('change',input);
 item=getMenu('company');assert.equal(item.search.value,'be');assert.equal(item.values.scrollTop,85);assert.equal(getTable().scrollTop,0);assert.equal(t.env.window.scrollY,440);assert.equal(getTable().scrollLeft,310);assert.equal(t.env.document.activeElement.dataset.tableValue,'Beta');assert.equal(t.env.document.activeElement.checked,false);
 await t.a.refresh(true);item=getMenu('company');assert.equal(item.search.value,'be');assert.equal(item.values.scrollTop,85);assert.equal(t.env.document.activeElement.dataset.tableValue,'Beta');assert.equal(t.env.document.activeElement.checked,false);assert.equal(item.panel.shown,true);
});

test('returning to offers folds the old table position into page scrolling once and restores company focus',async()=>{
 const {t,main,getTable,paintCount}=desktopTableFixture();await t.a.setScreen('solicitar');const initial=paintCount();await t.a.setScreen('solicitar');assert.equal(paintCount()-initial,1);
 const company={tagName:'BUTTON',id:'',name:'',dataset:{job:'offer-1'},closest(){return null;},focus(){t.env.document.activeElement=this;}};const previousAll=main.querySelectorAll;main.querySelectorAll=selector=>selector==='[data-job]'||selector==='button,summary,input,textarea,select,a'?[company]:previousAll(selector);main.contains=element=>element===company;
 getTable().scrollLeft=220;getTable().scrollTop=610;t.env.window.scrollY=200;await t.a.setScreen('detalle','offer-1');await t.a.goBack();
 assert.equal(t.a.getView().screen,'solicitar');assert.equal(getTable().scrollLeft,220);assert.equal(getTable().scrollTop,0);assert.equal(t.env.window.scrollY,810);assert.equal(t.env.document.activeElement,company);
 await t.a.setScreen('detalle','offer-1');await t.a.goBack();assert.equal(t.env.window.scrollY,810);assert.equal(getTable().scrollLeft,220);assert.equal(getTable().scrollTop,0);
});

test('profile index navigates locally without saving and names the sections with pending edits',async()=>{
 const t=setup(),{forms}=profileFixture(t);const html=t.a.profileForm();assert.match(html,/class="profile-workspace"[\s\S]*class="profile-section-nav"[\s\S]*class="profile-content"/);assert.equal((html.match(/data-profile-section=/g)||[]).length,3);assert.match(html,/href="#profile-about"/);
 const main=t.env.document.querySelector('#main'),prior=main.querySelector,pending={textContent:''};main.querySelector=selector=>selector==='[data-profile-pending]'?pending:prior(selector);forms.forEach(form=>{form._dirty=true;});t.a.syncDirty();assert.match(pending.textContent,/Sobre mi, Lo que busco/);
 let scrolled,focused;const heading={setAttribute(){},focus(){focused=true;}};t.env.document.getElementById=id=>({scrollIntoView(){scrolled=id;},querySelector(){return heading;}});t.env.fetch=async()=>{throw Error('Local index must not write or refresh');};
 await t.click({dataset:{profileSection:'profile-experience'}});assert.equal(scrolled,'profile-about');assert.equal(focused,true);assert.equal(t.a.isDirty(),true);assert.equal(t.model.revision,0);assert.match(t.a.profileForm(),/data-profile-section="profile-about" aria-current="location"/);
});

test('Ctrl K searches and Ctrl S only saves the current form, never authorizes a review',async()=>{
 const t=setup(),search={focus(){this.focused=true;},select(){this.selected=true;}},prior=t.env.document.querySelector;t.env.document.querySelector=selector=>selector==='#global-search'?search:prior(selector);const target={closest(){return null;}};
 await t.dispatch('keydown',target,{key:'k',ctrlKey:true});assert.equal(search.focused,true);assert.equal(search.selected,true);
 profileFixture(t);const operations=[];t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;operations.push(operation);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};
 await t.dispatch('keydown',target,{key:'s',ctrlKey:true});assert.deepEqual(operations.map(op=>op.section||op.kind),['about','ui-experience','search','sources']);assert.equal(t.a.isDirty(),false);
 t.setForm(null);t.a.setScreenState('revisar');await t.dispatch('keydown',target,{key:'s',ctrlKey:true});await t.dispatch('keydown',target,{key:'Enter',ctrlKey:true});assert.equal(operations.length,4);assert(operations.every(operation=>!['ui-approve','ui-request','ui-send'].includes(operation.kind)));
});

test('Ctrl S preserves validation failures and ignores modal dialogs and in-flight saves',async()=>{
 const t=setup(),{forms}=profileFixture(t),target={closest(){return null;}};let writes=0;forms[2].reportValidity=()=>false;t.env.fetch=async()=>{writes++;throw Error('Must not save');};
 await t.dispatch('keydown',target,{key:'s',ctrlKey:true});assert.equal(writes,0);assert.equal(t.a.isDirty(),true);
 const prior=t.env.document.querySelector;t.env.document.querySelector=selector=>selector==='dialog[open]'?{open:true}:prior(selector);const event=t.event(target,{key:'s',ctrlKey:true});await t.dispatch('keydown',target,event);assert.equal(event.defaultPrevented,false);assert.equal(writes,0);
 const other=setup();profileFixture(other);let finish,count=0;other.env.fetch=async()=>{count++;if(count===1)await new Promise(resolve=>{finish=resolve;});return {ok:true,json:async()=>({state:{...other.a.getModel(),revision:other.a.getModel().revision+1}})};};const saving=other.dispatch('keydown',target,{key:'s',ctrlKey:true});await other.dispatch('keydown',target,{key:'s',ctrlKey:true});assert.equal(count,1);finish();await saving;assert.equal(count,4);assert.equal(other.a.isDirty(),false);
});

test('global saved-offer search ignores accents without changing stored titles',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa',title:'Analítica de datos',state:'Preparar',requests:[],questions:[],missing:[],packages:[]}];t.a.setQuery('analitica');assert.match(t.a.findResults(),/Analítica de datos/);t.a.setQuery('ANALÍTICA');assert.match(t.a.findResults(),/data-job="one"/);assert.equal(t.model.opportunities[0].title,'Analítica de datos');
});

test('new-state notices survive unchanged polls while drafts and expected values stay intact',async()=>{
 const t=setup();t.env.fetch=async()=>({ok:true,json:async()=>({...t.model,version:'initial'})});await t.a.refresh(true);const {forms}=profileFixture(t);for(const form of forms)t.a.rememberForm(form);const expected=structuredClone(forms.map(form=>form._expected));
 t.env.fetch=async()=>({ok:true,json:async()=>({...t.a.getModel(),revision:1,version:'new-state',history:[{at:'2026-10-01T10:00:00Z',title:'TEST unrelated update'}]})});await t.a.refresh();assert.equal(t.connectionBox.textContent,'Hay datos nuevos. Tu borrador se conserva.');
 t.env.fetch=async path=>{assert.match(path,/since=new-state/);return {ok:true,json:async()=>({unchanged:true,version:'new-state'})};};await t.a.refresh();await t.a.refresh();assert.equal(t.connectionBox.textContent,'Hay datos nuevos. Tu borrador se conserva.');assert.equal(forms[0].values.currentCity,'Cádiz');assert.deepEqual(forms.map(form=>form._expected),expected);assert.equal(t.a.isDirty(),true);
 t.env.fetch=async()=>{throw Error('TEST real connection failure');};await t.a.refresh();assert.equal(t.connectionBox.textContent,'TEST real connection failure');t.a.rememberForm(forms[0]);assert.equal(t.connectionBox.textContent,'TEST real connection failure');
 t.env.fetch=async()=>({ok:true,json:async()=>({unchanged:true,version:'new-state'})});await t.a.refresh();assert.equal(t.connectionBox.textContent,'Hay datos nuevos. Tu borrador se conserva.');
 const saved=t.storage.get('stubbs_jobs-draft:datos:global');t.setForms([]);t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});await t.a.setScreen('ayuda');assert.equal(t.connectionBox.textContent,'');assert.equal(t.storage.get('stubbs_jobs-draft:datos:global'),saved);
});

test('a successful profile save clears the new-state notice without weakening expected-value guards',async()=>{
 const t=setup();t.env.fetch=async()=>({ok:true,json:async()=>({...t.model,version:'initial'})});await t.a.refresh(true);const {forms}=profileFixture(t);for(const form of forms)t.a.rememberForm(form);const original=structuredClone(forms[0]._expected);
 t.env.fetch=async()=>({ok:true,json:async()=>({...t.a.getModel(),revision:1,version:'new-state'})});await t.a.refresh();assert.match(t.connectionBox.textContent,/Hay datos nuevos/);const operations=[];
 t.env.fetch=async(_,options)=>{const op=JSON.parse(options.body).operation;operations.push(op);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};assert.equal(await t.a.saveProfileChanges(),true);assert.equal(t.connectionBox.textContent,'');assert.deepEqual(operations[0].expected,original);assert.equal(t.a.isDirty(),false);assert.equal(t.storage.has('stubbs_jobs-draft:datos:global'),false);
});

test('a review with no saved form answers stays neutral while its offer retains only the CV field',()=>{
 const t=setup(),material={recipient:'https://example.org/form',answers:{internalAnswer:'PRIVATE TEST'},formAnswerKeys:[],messageUsage:'unused'},job={id:'one',company:'Empresa',title:'Analista',state:'Preparar',requests:[],missing:[],questions:[],selection:{selected:true,mode:'review'},fingerprint:'current',draft:material,answers:material.answers,answerOverrides:{},conditions:{},packages:[{id:'current',isCurrent:true,cvUrl:'/api/document?id=current',payload:material}]};t.model.opportunities=[job];t.a.setSelected('one');t.a.setReviewSnapshot(job);
 const review=t.a.reviewPage(),detail=t.a.detail();assert.match(review,/Respuestas del formulario[\s\S]*Sin respuestas de formulario guardadas\./);assert.match(detail,/Formulario de solicitud[\s\S]*<dt>CV para la oferta<\/dt>/);
 for(const html of [review,detail])assert.doesNotMatch(html,/PRIVATE TEST|no pide respuestas|no necesita respuestas/i);
 assert.deepEqual(job.packages[0].payload,material);assert.deepEqual(t.model.requests,[]);
});

// Build form ownership from the emitted markup, including controls associated
// with a form outside their containing card. This is a DOM contract fixture,
// not a layout or accessibility acceptance test.
function groupedProfileDom(t){
 const main=t.env.document.querySelector('#main'),priorId=t.env.document.getElementById,priorQuery=main.querySelector,priorAll=main.querySelectorAll;
 let html='',forms=[],controls=[],cards=new Map(),writes=0;
 const decode=value=>String(value||'').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
 const attrs=tag=>Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([,key,value])=>[key,decode(value)]));
 const pending={textContent:''},save={disabled:false,textContent:'',dataset:{saveProfile:'1'}},bar={hidden:true,setAttribute(){},querySelector(){return save;}};
 Object.defineProperty(main,'innerHTML',{configurable:true,get(){return html;},set(value){
  html=value;writes++;forms=[];controls=[];cards=new Map();const byId=new Map(),formStack=[],cardStack=[];
  for(const match of html.matchAll(/<form\b[^>]*>/g)){
   const a=attrs(match[0]);if(!a['data-form'])continue;
   const fields=new Map(),error={innerHTML:''},info={textContent:''},form={id:a.id||'',dataset:{form:a['data-form'],...(a['data-search-profile-id']?{searchProfileId:a['data-search-profile-id']}:{})},values:{},elements:{namedItem:name=>fields.get(name)||null},querySelector(selector){return selector==='.form-error'?error:selector==='.form-info'?info:null;},reportValidity(){const invalid=[...fields.values()].find(field=>{if(field.maxLength&&field.value.length>field.maxLength)return true;if(field.dataset.type!=='number'||field.value==='')return false;const value=Number(field.value),base=field.min===''?0:Number(field.min);return !Number.isFinite(value)||field.min!==''&&value<Number(field.min)||field.max!==''&&value>Number(field.max)||field.step!=='any'&&Math.abs((value-base)/Number(field.step||1)-Math.round((value-base)/Number(field.step||1)))>1e-9;});if(invalid){invalid.focus();return false;}return true;},scrollIntoView(){},fields};forms.push(form);if(form.id)byId.set(form.id,form);
  }
  let formIndex=0;
  for(const match of html.matchAll(/<\/?form\b[^>]*>|<\/?section\b[^>]*>|<input\b[^>]*>|<textarea\b[^>]*>[\s\S]*?<\/textarea>|<select\b[^>]*>[\s\S]*?<\/select>/g)){
   const tag=match[0],a=attrs(tag);
   if(/^<form\b/.test(tag)){formStack.push(forms[formIndex++]);continue;}if(/^<\/form/.test(tag)){formStack.pop();continue;}
   if(/^<section\b/.test(tag)){const error={innerHTML:''},info={textContent:''},card={id:a.id,error,info,querySelector(selector){return selector.startsWith('.form-error')?error:selector.startsWith('.form-info')?info:null;},scrollIntoView(){}};cardStack.push(card);if(card.id)cards.set(card.id,card);continue;}if(/^<\/section/.test(tag)){cardStack.pop();continue;}
   if(!a.name)continue;const owner=a.form?byId.get(a.form):formStack.at(-1),container=formStack.at(-1),card=cardStack.at(-1);if(!owner)continue;
   const initial=tag.startsWith('<textarea')?decode(tag.replace(/^<textarea[^>]*>/,'').replace(/<\/textarea>$/,'')):tag.startsWith('<select')?attrs(tag.match(/<option\b[^>]*\bselected[^>]*>/)?.[0]||'').value||'':a.value||'';
   owner.values[a.name]=initial;
   const control={tagName:tag.startsWith('<textarea')?'TEXTAREA':tag.startsWith('<select')?'SELECT':'INPUT',name:a.name,id:a.id||'',min:a.min??'',max:a.max??'',step:a.step??'',maxLength:Number(a.maxlength)||0,dataset:{...(a['data-type']?{type:a['data-type']}: {})},form:owner,selectionStart:0,selectionEnd:0,get value(){return owner.values[a.name];},set value(value){owner.values[a.name]=value==null?'':String(value);},closest(selector){return selector.startsWith('form')?container:selector.startsWith('section')?card:null;},focus(){t.env.document.activeElement=this;},setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}};
   owner.fields.set(a.name,control);controls.push(control);
  }
  t.setForms(forms);
 }});
 main.querySelector=selector=>selector==='[data-profile-savebar]'?bar:selector==='[data-profile-pending]'?pending:selector==='form[data-form]'?forms[0]||null:priorQuery(selector);
 main.querySelectorAll=selector=>selector==='form[data-form]'?forms:selector==='button,summary,input,textarea,select,a'?controls:priorAll(selector);
 main.contains=element=>controls.includes(element);t.env.document.getElementById=id=>cards.get(id)||forms.find(form=>form.id===id)||controls.find(control=>control.id===id)||priorId(id);
 return {get forms(){return forms;},get writes(){return writes;},get html(){return html;},field(name){return controls.find(control=>control.name===name);},card(id){return cards.get(id);},pending,bar};
}

test('profile markup has three flat panels with an independent CV library, four canonical writers and no visual subgroups',()=>{
 const t=setup(),html=t.a.profileForm();const ids=['profile-about','profile-work','profile-cv'];
 assert.equal((html.match(/<section class="profile-card"/g)||[]).length,3);assert.equal((html.match(/<form data-form=/g)||[]).length,4);assert.equal((html.match(/data-save-profile="1"/g)||[]).length,1);assert.equal((html.match(/<h2>/g)||[]).length,3);assert.equal((html.match(/class="profile-fields"/g)||[]).length,2);
 assert.deepEqual([...html.matchAll(/<h2>([^<]+)<\/h2>/g)].map(match=>match[1]),['Sobre mi','Lo que busco','Currículums']);assert.deepEqual([...html.matchAll(/data-profile-section="[^"]+"[^>]*>([^<]+)<\/a>/g)].map(match=>match[1]),['Sobre mi','Lo que busco','Currículums']);assert.doesNotMatch(html,/Sobre mí|Mi búsqueda|Mis currículums/);
 assert.doesNotMatch(html,/<fieldset|<legend|search-panel|search-settings-content|search-salary/);
 for(const id of ids)assert.match(html,new RegExp(`data-profile-section="${id}"`));
 const section=id=>html.split(`id="${id}"`)[1].split('</section>')[0];
 assert.match(section('profile-about'),/name="currentCity"[\s\S]*class="profile-field-wide"><label class="field"><span>Mi experiencia<\/span><textarea name="text"[\s\S]*class="profile-field-wide"><label class="field"><span>Idiomas<\/span><textarea name="languages" form="profile-search-form"/);assert.doesNotMatch(section('profile-about'),/previousApplications|Currículums|cv-upload|<h3>|<fieldset|<section/);
 assert.match(section('profile-work'),/name="targetRoles"[\s\S]*name="keywords"[\s\S]*name="searchPriorities"/);
 assert.doesNotMatch(section('profile-work'),/name="languages"|<h3>|<fieldset|<section/);
 assert.match(section('profile-work'),/name="minimumFixed"[\s\S]*name="salaryExpectationFixed"[\s\S]*name="sourceUrls"/);
 assert.match(section('profile-work'),/Empresas a evitar[\s\S]*name="previousApplications" form="profile-search-form"[\s\S]*Especificar webs de búsqueda/);
 assert.match(section('profile-cv'),/<h2>Currículums<\/h2>[\s\S]*Añadir PDF[\s\S]*id="cv-upload"/);assert.doesNotMatch(section('profile-cv'),/<form|<fieldset|<section|profile-fields/);
 assert.match(section('profile-work'),/Si indicas webs, buscaré solo en ellas\./);
});

test('language edits keep their canonical draft and expectations across tabs and Ctrl S saves all four areas once',async()=>{
 const t=setup();Object.assign(t.model,{searchContext:{name:'Persona ficticia',targetRoles:'Analista',languages:'Inglés B2',currency:'EUR',sourceUrls:''},profile:{currentCity:'Madrid'},preferences:{location:'España'},experience:'Experiencia ficticia',cvLibrary:[{id:'test-cv',name:'Ficticio.pdf'}]});
 const originalCv=structuredClone(t.model.cvLibrary),dom=groupedProfileDom(t);t.a.setScreenState('perfil');t.a.render();
 const language=dom.field('languages'),search=dom.forms.find(form=>form.dataset.form==='search'),experience=dom.forms.find(form=>form.dataset.form==='experience');
 assert.equal(language.form,search);assert.equal(language.closest('form[data-form]'),experience);assert.equal(dom.field('previousApplications').form,search);assert.equal(dom.field('previousApplications').closest('form[data-form]'),undefined);assert.equal(Object.hasOwn(experience.values,'languages'),false);language.value='Inglés C1';language.focus();language.setSelectionRange(3,8);await t.dispatchMain('input',language);
 assert.equal(JSON.parse(t.storage.get('stubbs_jobs-draft:busqueda:global')).values.languages,'Inglés C1');assert.equal(t.storage.has('stubbs_jobs-draft:experiencia:global'),false);assert.match(dom.pending.textContent,/Sobre mi/);
 for(const [name,value] of [['currentCity','Cádiz'],['text','Experiencia revisada ficticia'],['minimumFixed','35000'],['previousApplications','Empresa ficticia A — 2026'],['sourceUrls','https://example.org/jobs']]){const field=dom.field(name);field.value=value;await t.dispatchMain('input',field);}
 const drafts=['datos','experiencia','busqueda','fuentes'].map(area=>t.storage.get(`stubbs_jobs-draft:${area}:global`));assert(drafts.every(Boolean));assert.equal(dom.pending.textContent,'Cambios en Sobre mi, Lo que busco');
 t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});await t.a.setScreen('solicitar');await t.a.setScreen('perfil');assert.equal(dom.field('languages').value,'Inglés C1');assert.equal(dom.field('previousApplications').value,'Empresa ficticia A — 2026');assert.deepEqual(['datos','experiencia','busqueda','fuentes'].map(area=>t.storage.get(`stubbs_jobs-draft:${area}:global`)),drafts);
 const operations=[];t.env.fetch=async(_,options)=>{const op=JSON.parse(options.body).operation;operations.push(op);const current=t.a.getModel(),state={...current,revision:current.revision+1,profile:{...current.profile},searchContext:{...current.searchContext},preferences:{...current.preferences}};if(op.kind==='ui-experience')state.experience=op.text;else for(const [key,value] of Object.entries(op.values)){if(Object.hasOwn(state.profile,key))state.profile[key]=value;else if(['location','minimumFixed'].includes(key))state.preferences[key]=value;else state.searchContext[key]=value;}return {ok:true,json:async()=>({state})};};
 await t.dispatch('keydown',dom.field('languages'),{key:'s',ctrlKey:true});assert.deepEqual(operations.map(op=>op.section||op.kind),['about','ui-experience','search','sources']);assert.equal(operations[2].values.languages,'Inglés C1');assert.equal(operations[2].expected.languages,'Inglés B2');assert.equal(Object.hasOwn(operations[1],'languages'),false);assert.equal(dom.field('languages').value,'Inglés C1');assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().cvLibrary,originalCv);assert.deepEqual(t.a.getModel().requests,[]);
});

test('an uncertain canonical search attempt survives regrouping and language changes without rewriting its identity',async()=>{
 const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',languages:'Inglés B2'},profile:{},preferences:{location:'España'},experience:'Ficticia'});
 const operation={kind:'ui-profile-section',section:'search',values:{languages:'Inglés C1',previousApplications:'TEST empresa'},expected:{languages:'Inglés B2',previousApplications:null}},attempt={id:'prior-exact-attempt',operation,values:{languages:'Inglés C1',previousApplications:'TEST empresa'}};
 const stored={values:{languages:'Inglés C1',previousApplications:'TEST empresa'},shown:{languages:'Inglés B2',previousApplications:null},expected:{languages:'Inglés B2',previousApplications:null},attempt};t.storage.set('stubbs_jobs-draft:busqueda:global',JSON.stringify(stored));
 const dom=groupedProfileDom(t);t.a.setScreenState('perfil');t.a.render();assert.equal(dom.field('languages').value,'Inglés C1');assert.equal(dom.field('previousApplications').value,'TEST empresa');assert.deepEqual(JSON.parse(t.storage.get('stubbs_jobs-draft:busqueda:global')).attempt,attempt);
 dom.field('languages').value='Inglés C2';await t.dispatchMain('input',dom.field('languages'));const requests=[];t.env.fetch=async(_,options)=>{requests.push(JSON.parse(options.body));return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:1,searchContext:{targetRoles:'Analista',languages:'Inglés C1',previousApplications:'TEST empresa'}}})};};
 assert.equal(await t.a.saveProfileChanges(),false);assert.equal(requests[0].id,'prior-exact-attempt');assert.deepEqual(requests[0].operation,operation);assert.equal(dom.field('languages').value,'Inglés C2');const remaining=JSON.parse(t.storage.get('stubbs_jobs-draft:busqueda:global'));assert.equal(remaining.attempt,null);assert.equal(remaining.expected.languages,'Inglés C1');assert.equal(t.a.isDirty(),true);
});

test('a stale language expectation conflicts without losing the draft or silently saving the other session value',async()=>{
 const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',languages:'Inglés B2'},profile:{},preferences:{location:'España'},experience:'Ficticia'});const dom=groupedProfileDom(t);t.a.setScreenState('perfil');t.a.render();dom.field('languages').value='Inglés C1';await t.dispatchMain('input',dom.field('languages'));
 const remote={...t.a.getModel(),revision:1,version:'remote-language',searchContext:{targetRoles:'Analista',languages:'Francés B2'}};t.env.fetch=async()=>({ok:true,json:async()=>remote});await t.a.refresh(true);assert.equal(dom.field('languages').value,'Inglés C1');const calls=[];
 t.env.fetch=async(_,options)=>{calls.push(JSON.parse(options.body).operation);return {ok:false,status:409,json:async()=>({error:'TEST idioma cambiado por otra sesión',state:remote})};};
 await t.dispatch('keydown',dom.field('languages'),{key:'s',ctrlKey:true});assert.equal(calls.length,1);assert.equal(calls[0].expected.languages,'Inglés B2');assert.equal(t.a.getModel().searchContext.languages,'Francés B2');assert.equal(dom.field('languages').value,'Inglés C1');assert.equal(t.a.isDirty(),true);assert.match(dom.card('profile-about').error.innerHTML,/TEST idioma cambiado/);assert.match(dom.card('profile-about').error.innerHTML,/form="profile-search-form" data-current/);assert.equal(JSON.parse(t.storage.get('stubbs_jobs-draft:busqueda:global')).values.languages,'Inglés C1');
});

test('reverting every draft after a remote update paints current state once and preserves caret, scroll and unrelated drafts',async()=>{
 const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',languages:'Inglés B2'},profile:{currentCity:'Madrid'},preferences:{location:'España'},experience:'Ficticia'});const dom=groupedProfileDom(t);t.a.setScreenState('perfil');t.a.render();const language=dom.field('languages');language.value='Inglés C1';language.focus();await t.dispatchMain('input',language);
 const other=JSON.stringify({values:{message:'Borrador de otra pantalla'},shown:{message:''},expected:{message:''},attempt:null});t.storage.set('stubbs_jobs-draft:cambio:other-offer',other);t.env.window.scrollY=480;
 t.env.fetch=async()=>({ok:true,json:async()=>({...t.a.getModel(),revision:1,version:'remote-clean',profile:{currentCity:'Valencia'},searchContext:{targetRoles:'Analista',languages:'Francés B2'}})});await t.a.refresh(true);assert.equal(dom.field('currentCity').value,'Madrid');assert.match(t.connectionBox.textContent,/Hay datos nuevos/);const writes=dom.writes;
 language.value='Inglés B2';language.setSelectionRange(2,6);await t.dispatchMain('input',language);await Promise.resolve();assert.equal(dom.writes,writes+1);assert.equal(dom.field('languages').value,'Francés B2');assert.equal(dom.field('currentCity').value,'Valencia');assert.equal(t.connectionBox.textContent,'');assert.equal(t.a.isDirty(),false);assert.equal(t.storage.has('stubbs_jobs-draft:busqueda:global'),false);assert.equal(t.storage.get('stubbs_jobs-draft:cambio:other-offer'),other);assert.equal(t.env.document.activeElement,dom.field('languages'));assert.equal(dom.field('languages').selectionStart,2);assert.equal(t.env.window.scrollY,480);
});

test('a preserved dirty form keeps the new-state notice through a local repaint and only the last revert paints current data',async()=>{
 const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',languages:'Inglés B2'},profile:{currentCity:'Madrid'},preferences:{location:'España'},experience:'Ficticia'});const dom=groupedProfileDom(t);t.a.setScreenState('perfil');t.a.render();
 for(const [name,value] of [['languages','Inglés C1'],['currentCity','Cádiz']]){dom.field(name).value=value;await t.dispatchMain('input',dom.field(name));}
 t.env.fetch=async()=>({ok:true,json:async()=>({...t.a.getModel(),revision:1,version:'remote-two',profile:{currentCity:'Valencia'},searchContext:{targetRoles:'Analista',languages:'Francés B2'}})});await t.a.refresh(true);t.a.render(true);assert.match(t.connectionBox.textContent,/Hay datos nuevos/);assert.equal(dom.field('languages').value,'Inglés C1');assert.equal(dom.field('currentCity').value,'Cádiz');const writes=dom.writes;
 dom.field('currentCity').value='Madrid';await t.dispatchMain('input',dom.field('currentCity'));await Promise.resolve();assert.equal(dom.writes,writes);assert.equal(t.a.isDirty(),true);assert.match(t.connectionBox.textContent,/Hay datos nuevos/);
 dom.field('languages').value='Inglés B2';await t.dispatchMain('input',dom.field('languages'));await Promise.resolve();assert.equal(dom.writes,writes+1);assert.equal(dom.field('currentCity').value,'Valencia');assert.equal(dom.field('languages').value,'Francés B2');assert.equal(t.a.isDirty(),false);assert.equal(t.connectionBox.textContent,'');
});

test('new-state notice settlement during an active save does not reenter painting or start another save',async()=>{
 const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',languages:'Inglés B2'},profile:{},preferences:{location:'España'},experience:'Ficticia'});const dom=groupedProfileDom(t);t.a.setScreenState('perfil');t.a.render();dom.field('languages').value='Inglés C1';await t.dispatchMain('input',dom.field('languages'));
 t.env.fetch=async()=>({ok:true,json:async()=>({...t.a.getModel(),revision:1,version:'remote-before-save'})});await t.a.refresh(true);const writes=dom.writes;let finish,calls=0;t.env.fetch=async()=>{calls++;await new Promise(resolve=>{finish=resolve;});return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:2,searchContext:{targetRoles:'Analista',languages:'Inglés C1'}}})};};
 const save=t.a.saveProfileChanges();await new Promise(resolve=>setImmediate(resolve));assert.equal(dom.writes,writes);assert.equal(calls,1);assert.equal(await t.a.saveProfileChanges(),false);finish();assert.equal(await save,true);await Promise.resolve();assert.equal(dom.writes,writes+1);assert.equal(calls,1);assert.equal(t.connectionBox.textContent,'');assert.equal(dom.field('languages').value,'Inglés C1');assert.equal(t.a.isDirty(),false);
});

test('past applications outside the search form retain their draft, caret and old expectation through navigation and conflict',async()=>{
 const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',languages:'Inglés B2',previousApplications:'TEST Empresa A'},profile:{},preferences:{location:'España'},experience:'Ficticia'});const dom=groupedProfileDom(t);t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});await t.a.setScreen('perfil');let previous=dom.field('previousApplications');previous.value='TEST Empresa B — 2026';previous.focus();previous.setSelectionRange(5,10);await t.dispatchMain('input',previous);
 assert.equal(t.storage.has('stubbs_jobs-draft:busqueda:global'),true);assert.equal(dom.pending.textContent,'Cambios en Lo que busco');const saved=t.storage.get('stubbs_jobs-draft:busqueda:global');
 t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});await t.a.setScreen('solicitar');await t.a.setScreen('perfil');previous=dom.field('previousApplications');assert.equal(previous.value,'TEST Empresa B — 2026');assert.equal(t.env.document.activeElement,previous);assert.equal(previous.selectionStart,5);assert.equal(previous.selectionEnd,10);assert.equal(t.storage.get('stubbs_jobs-draft:busqueda:global'),saved);
 const remote={...t.a.getModel(),revision:1,version:'remote-previous',searchContext:{...t.a.getModel().searchContext,previousApplications:'TEST Empresa C'}};t.env.fetch=async()=>({ok:true,json:async()=>remote});await t.a.refresh(true);const operations=[];t.env.fetch=async(_,options)=>{operations.push(JSON.parse(options.body).operation);return {ok:false,status:409,json:async()=>({error:'TEST solicitud anterior cambiada',state:remote})};};await t.dispatch('keydown',previous,{key:'s',ctrlKey:true});
 assert.equal(operations.length,1);assert.equal(operations[0].section,'search');assert.equal(operations[0].expected.previousApplications,'TEST Empresa A');assert.equal(previous.value,'TEST Empresa B — 2026');assert.match(dom.card('profile-work').error.innerHTML,/TEST solicitud anterior cambiada/);assert.match(dom.card('profile-work').error.innerHTML,/form="profile-search-form" data-current/);assert.equal(t.a.getModel().searchContext.previousApplications,'TEST Empresa C');assert.equal(t.a.isDirty(),true);assert.deepEqual(t.a.getModel().requests,[]);
});

test('the seven prior anchors and older profile routes resolve to the current profile and independent CV panels',async()=>{
 const t=setup();let destination,focus;t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});t.env.document.getElementById=id=>['profile-about','profile-work','profile-cv'].includes(id)?{scrollIntoView(){destination=id;},querySelector(){return {focus(){focus=id;}};}}:null;
 for(const [route,expected] of [['profile-about','profile-about'],['profile-experience','profile-about'],['profile-cv','profile-cv'],['profile-work','profile-work'],['search-settings-criteria','profile-work'],['search-settings-sources','profile-work'],['profile-previous','profile-work'],['perfil-previous','profile-work'],['buscar','profile-work'],['busqueda','profile-work'],['fuentes','profile-work'],['experiencia','profile-about'],['cv','profile-cv'],['datos','profile-about'],['antecedentes','profile-work']]){destination=null;focus=null;await t.a.setScreen(route);assert.equal(t.a.getView().screen,'perfil',route);assert.equal(destination,expected,route);assert.equal(focus,expected,route);}
 for(const [anchor,expected] of [['profile-experience','profile-about'],['profile-cv','profile-cv'],['search-settings-criteria','profile-work'],['search-settings-sources','profile-work']]){await t.a.setScreen('perfil',null,true,anchor);assert.equal(destination,expected);}
 assert.equal(t.a.getModel().revision,0);assert.deepEqual(t.a.getModel().requests,[]);
});

test('offer companies have no decorative mark while legacy activity filters and order remain clearable',()=>{
 const t=setup(),base={title:'Analista',state:'Preparar',apply:'Sí',requests:[],questions:[],missing:[],packages:[],lastActivityAt:'2026-10-01T10:00:00Z'};t.model.opportunities=[{...base,id:'one',company:'Primera Empresa'},{...base,id:'two',company:'Segunda Empresa'}];const html=t.a.applyPage();
 assert.doesNotMatch(html,/class="company-mark"|data-table-sort="activity"|data-menu-key="activity"|data-activity-at=/);assert.match(html,/aria-label="Abrir ficha de Primera Empresa: Analista"/);assert.match(html,/aria-label="Abrir ficha de Segunda Empresa: Analista"/);
 t.a.setTableSort('solicitar','activity',-1);t.a.setTableFilter('solicitar','activity',[String(Date.parse('2026-10-01T10:00:00Z'))]);assert.equal((t.a.applyPage().match(/data-job-row=/g)||[]).length,2);assert.match(t.a.applyPage(),/Orden: Actividad ↓/);assert.match(t.a.applyPage(),/Actividad: 1 oct 2026/);
});

test('optional demographic fields appear once in About me, without inferred answers or recruitment consent',()=>{
 const t=setup(),html=t.a.profileForm(),about=html.split('<h2>Sobre mi</h2>')[1].split('<h2>Lo que busco</h2>')[0];
 assert.match(about,/Género \(opcional\)/);assert.match(about,/name="gender"[^>]*aria-describedby="profile-gender-help" aria-labelledby="profile-gender-help-label"[^>]*value=""[^>]*maxlength="100"/);
 assert.match(about,/Participar en encuestas demográficas \(opcional\)/);assert.match(about,/name="demographicSurveyParticipation"[^>]*data-type="boolean"><option value="">Sin responder<\/option>/);
 assert.doesNotMatch(about,/<option value="(?:true|false)" selected/);assert.match(about,/No incluye el consentimiento para tramitar la candidatura/);
 assert.equal((html.match(/name="gender"/g)||[]).length,1);assert.equal((html.match(/name="demographicSurveyParticipation"/g)||[]).length,1);
 assert.deepEqual(t.model.profile,{});assert.deepEqual(t.model.requests,[]);
});

test('optional demographic answers use the existing single profile save and preserve an explicit No',async()=>{
 const t=setup();Object.assign(t.model,{profile:{gender:null,demographicSurveyParticipation:null},searchContext:{name:'Persona ficticia'}});
 const dom=groupedProfileDom(t),operations=[];t.env.fetch=async(_,options)=>{
  if(!options.body)return {ok:true,json:async()=>t.a.getModel()};
  const operation=JSON.parse(options.body).operation;operations.push(operation);const state=structuredClone(t.a.getModel());
  state.revision++;Object.assign(state.profile,operation.values);return {ok:true,json:async()=>({state})};
 };
 await t.a.setScreen('perfil');dom.field('gender').value='Prefiero no responder';await t.dispatchMain('input',dom.field('gender'));
 dom.field('demographicSurveyParticipation').value='false';await t.dispatchMain('change',dom.field('demographicSurveyParticipation'));
 assert.equal(dom.pending.textContent,'Cambios en Sobre mi');await t.dispatch('keydown',dom.field('gender'),{key:'s',ctrlKey:true});
 assert.equal(operations.length,1);assert.equal(operations[0].kind,'ui-profile-section');assert.equal(operations[0].section,'about');
 assert.deepEqual(operations[0].values,{gender:'Prefiero no responder',demographicSurveyParticipation:false});
 assert.deepEqual(operations[0].expected,{gender:null,demographicSurveyParticipation:null});
 assert.equal(t.a.getModel().profile.demographicSurveyParticipation,false);assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);
});

test('source and prior-application fields have concise names, separate accessible help and full-width wrappers',()=>{
 const t=setup(),html=t.a.profileForm(),sources=html.match(/<label class="field profile-field-wide"><span id="profile-sourceUrls-label">[\s\S]*?<\/label>/)[0];
 assert.match(sources,/<span id="profile-sourceUrls-label">Especificar webs de búsqueda \(opcional\)<\/span>/);assert.match(sources,/name="sourceUrls" id="profile-sourceUrls" data-auto-grow="1" aria-labelledby="profile-sourceUrls-label" aria-describedby="profile-sourceUrls-help"/);assert.match(sources,/<small class="helper" id="profile-sourceUrls-help">Si indicas webs/);
 assert.match(html,/class="profile-field-wide" id="search-field-previousApplications"><label class="field"><span>Empresas a evitar<\/span><textarea name="previousApplications" form="profile-search-form" id="profile-previousApplications" data-auto-grow="1"/);
 assert.doesNotMatch(html,/id="profile-previousApplications-help"/);assert.match(html,/name="previousApplications"[^>]*maxlength="10000"/);assert.doesNotMatch(html,/<div class="form-grid"><div class="profile-field-wide" id="search-field-previousApplications"/);
 assert.doesNotMatch(html,/Anota empresas a las que no quieras presentarte/);
});

test('old prior-application links and its backup draft focus the retained field within My search',async()=>{
 const t=setup(),notes='TEST Empresa A — analista — 2025\nEvitar TEST Empresa B; preferencia confirmada';Object.assign(t.model,{searchContext:{targetRoles:'Analista',languages:'Inglés B2',previousApplications:notes},profile:{},preferences:{location:'España'},experience:'Ficticia'});const dom=groupedProfileDom(t);t.env.fetch=async()=>({ok:true,json:async()=>t.a.getModel()});
 for(const route of ['profile-previous','perfil-previous','antecedentes']){await t.a.setScreen(route);assert.equal(t.a.getView().screen,'perfil');assert.equal(t.env.document.activeElement,dom.field('previousApplications'));assert.equal(dom.field('previousApplications').value,notes);assert.equal((dom.html.match(/<section class="profile-card"/g)||[]).length,3);}
 for(const anchor of ['profile-previous','perfil-previous','search-field-previousApplications']){await t.a.setScreen('perfil',null,true,anchor);assert.equal(t.env.document.activeElement,dom.field('previousApplications'));}
 dom.field('previousApplications').value=notes+'\nTEST Empresa C — puesto por confirmar';await t.dispatchMain('input',dom.field('previousApplications'));const draft=t.a.backupDrafts().find(draft=>draft.key==='stubbs_jobs-draft:busqueda:global');assert.equal(draft.label,'Lo que busco');assert.equal(draft.section,'profile-previous');assert.equal(dom.pending.textContent,'Cambios en Lo que busco');
 await t.a.setScreen('ayuda');await t.click({dataset:{backupDraft:draft.key}});assert.equal(t.env.document.activeElement,dom.field('previousApplications'));assert.equal(dom.field('previousApplications').value,notes+'\nTEST Empresa C — puesto por confirmar');assert.equal(JSON.parse(t.storage.get(draft.key)).expected.previousApplications,notes);assert.equal(t.a.getModel().searchContext.previousApplications,notes);assert.deepEqual(t.a.getModel().requests,[]);assert.deepEqual(t.a.getModel().opportunities,[]);
});

test('profile index keeps the independent CV panel active at the scroll limit before its heading reaches the header',async()=>{
 const t=setup(),main=t.env.document.querySelector('#main'),priorAll=main.querySelectorAll,links=['profile-about','profile-work','profile-cv'].map(id=>({dataset:{profileSection:id},setAttribute(key,value){this[key]=value;},removeAttribute(key){delete this[key];}}));t.a.setScreenState('perfil');
 links[0].setAttribute('aria-current','location');main.querySelectorAll=selector=>selector==='[data-profile-section]'?links:priorAll(selector);t.env.document.documentElement={clientHeight:1400,scrollHeight:2000};let headingTop=370,focused=false;
 const search={getBoundingClientRect(){return {top:headingTop};},scrollIntoView(){t.env.window.scrollY=600;headingTop=270;},querySelector(){return {setAttribute(){},focus(){focused=true;}};}};t.env.document.getElementById=id=>id==='profile-cv'?search:id==='profile-about'?{getBoundingClientRect(){return {top:-500};}}:id==='profile-work'?{getBoundingClientRect(){return {top:160};}}:null;t.env.window.scrollY=500;
 t.dispatchWindow('scroll');assert.equal(links[0]['aria-current'],'location');assert.match(t.a.profileForm(),/data-profile-section="profile-about" aria-current="location"/);
 await t.click({dataset:{profileSection:'profile-cv'}});assert.equal(focused,true);assert.equal(t.env.window.scrollY,600);assert.equal(headingTop,270);assert.equal(links[2]['aria-current'],'location');t.dispatchWindow('scroll');assert.equal(links[2]['aria-current'],'location');assert.equal(links[0]['aria-current'],undefined);assert.match(t.a.profileForm(),/data-profile-section="profile-cv" aria-current="location"/);assert.equal(t.a.getModel().revision,0);assert.deepEqual(t.a.getModel().requests,[]);
});

test('profile index does not activate the final panel when everything fits without scrolling and keeps normal heading tracking',()=>{
 const t=setup(),main=t.env.document.querySelector('#main'),priorAll=main.querySelectorAll,links=['profile-about','profile-work','profile-cv'].map(id=>({dataset:{profileSection:id},setAttribute(key,value){this[key]=value;},removeAttribute(key){delete this[key];}}));t.a.setScreenState('perfil');main.querySelectorAll=selector=>selector==='[data-profile-section]'?links:priorAll(selector);t.env.document.documentElement={clientHeight:1400,scrollHeight:1200};let searchTop=750;t.env.window.scrollY=0;t.env.document.getElementById=id=>({getBoundingClientRect(){return {top:id==='profile-work'?searchTop:id==='profile-cv'?1100:130};}});
 t.dispatchWindow('scroll');assert.match(t.a.profileForm(),/data-profile-section="profile-about" aria-current="location"/);assert.doesNotMatch(t.a.profileForm(),/data-profile-section="profile-work" aria-current="location"/);
 t.env.document.documentElement.scrollHeight=4000;t.env.window.scrollY=1000;searchTop=110;t.dispatchWindow('scroll');assert.equal(links[1]['aria-current'],'location');assert.match(t.a.profileForm(),/data-profile-section="profile-work" aria-current="location"/);
 t.env.document.documentElement.scrollHeight=1400;t.env.window.scrollY=0;searchTop=750;t.dispatchWindow('scroll');assert.equal(links[0]['aria-current'],'location');assert.equal(links[1]['aria-current'],undefined);
});

test('CV cards keep identically named documents separate and show only the projected preparation or confirmed-send relations',()=>{
 const t=setup();t.model.cvLibrary=[{name:'Currículum ficticio.pdf',url:'/api/document?id=uploaded%3Afirst',usage:[{opportunityId:'offer-A',company:'Empresa A ficticia',title:'Analista',kind:'prepared',at:'2026-10-01T09:00:00Z',packageId:'package-A'},{opportunityId:'historical:offer-B',company:'Empresa B ficticia',title:'Consultor',kind:'sent',at:'2026-09-20T12:00:00Z',packageId:'package-B',historical:true,proof:'PRIVATE PROOF MUST STAY IN HISTORY'}]},{name:'Currículum ficticio.pdf',url:'/api/document?id=uploaded%3Asecond',usage:[]}];
 const html=t.a.profileForm(),cards=[...html.matchAll(/<article class="cv-card">[\s\S]*?<\/article>/g)].map(match=>match[0]);assert.equal(cards.length,2);assert.equal((html.match(/<h3 class="cv-card-title" title="Currículum ficticio.pdf">Currículum ficticio.pdf<\/h3>/g)||[]).length,2);assert.match(cards[0],/href="\/api\/document\?id=uploaded%3Afirst"/);assert.match(cards[1],/href="\/api\/document\?id=uploaded%3Asecond"/);
 assert.match(cards[0],/href="#detalle\/offer-A" data-job="offer-A"[^>]*><span class="cv-usage-company">Empresa A ficticia<\/span><span class="cv-usage-title">Analista/);assert.match(cards[0],/data-kind="prepared">CV preparado/);assert.match(cards[0],/href="#detalle\/historical%3Aoffer-B" data-job="historical:offer-B"/);assert.match(cards[0],/data-kind="sent">Envío confirmado/);assert.match(cards[0],/Registro anterior/);assert.match(cards[0],/1 oct 2026/);assert.match(cards[0],/20 sept 2026/);assert.doesNotMatch(cards[0],/PRIVATE PROOF|data-approve|data-select|data-retry|package-A|package-B|Solicitud preparada/);
 assert.match(cards[1],/Sin solicitudes asociadas/);assert.doesNotMatch(cards[1],/Empresa A|Empresa B|CV preparado|Envío confirmado/);assert.match(cards[0],/aria-label="Abrir PDF: Currículum ficticio.pdf"/);assert.match(cards[0],/class="cv-card-icon"[^>]*aria-hidden="true"/);assert.match(html,/Despliega cada tarjeta para ver las ofertas asociadas a ese mismo PDF\./);
 const panel=html.split('id="profile-cv"')[1].split('</section>')[0];assert.doesNotMatch(panel,/<form|<section|profile-fields/);assert.equal((html.match(/data-save-profile="1"/g)||[]).length,1);assert.equal((html.match(/id="cv-upload"/g)||[]).length,1);assert.deepEqual(t.a.getModel().requests,[]);
});

test('missing CV provenance never infers use or a send from matching names, selections, approval or old offer state',()=>{
 const t=setup();t.model.cvLibrary=[{name:'Sin origen.pdf',url:'/api/document?id=source-unknown'},{name:'Otro CV.pdf',url:'/api/document?id=known-unused',usage:[]},{name:'Versión futura.pdf',url:'/api/document?id=unknown-kind',usage:[{kind:'approved',opportunityId:'same-name',company:'Do not infer sent'}]}];
 t.model.opportunities=[{id:'same-name',company:'No relation from model',title:'Analista',cvLabel:'Sin origen.pdf',cv:'Sin origen.pdf',selection:{selected:true,mode:'auto'},sent:{at:'2026-10-01T10:00:00Z',packageId:'other-file'},packages:[{id:'approval-only',approvedAt:'2026-10-01T09:00:00Z'}]}];t.model.historical=[{id:'old-name',company:'No relation from history',title:'Analista',state:'Enviada',cv:'Sin origen.pdf',category:'Laboral'}];
 const panel=t.a.profileForm().split('id="profile-cv"')[1].split('</section>')[0];assert.equal((panel.match(/Aún no hay usos registrados para este CV/g)||[]).length,2);assert.equal((panel.match(/Sin solicitudes asociadas/g)||[]).length,1);assert.doesNotMatch(panel,/No relation|Do not infer sent|CV preparado|Envío confirmado|data-job=/);assert.equal(t.model.opportunities[0].selection.mode,'auto');assert.equal(t.model.opportunities[0].sent.packageId,'other-file');
});

test('unavailable CV files keep their projected history without offering a broken PDF link',()=>{
 const t=setup();t.model.cvLibrary=[{id:'uploaded:absent',name:'Archivo ausente ficticio.pdf',available:false,url:'/api/document?id=uploaded%3Aabsent',usage:[{opportunityId:'historical:sent-with-absent-file',company:'Empresa anterior ficticia',title:'Analista',kind:'sent',at:'2026-09-20T12:00:00Z',historical:true}]},{id:'uploaded:available',name:'Archivo disponible ficticio.pdf',available:true,url:'/api/document?id=uploaded%3Aavailable',usage:[]},{name:'Archivo anterior ficticio.pdf',url:'/api/document?id=old-fixture',usage:[]}];
 const html=t.a.profileForm(),cards=[...html.matchAll(/<article class="cv-card">[\s\S]*?<\/article>/g)].map(match=>match[0]);assert.equal(cards.length,3);assert.match(cards[0],/Vuelve a añadir el PDF para abrirlo\./);assert.doesNotMatch(cards[0],/Abrir PDF|cv-card-open|data-document|href="\/api\/document/);assert.match(cards[0],/data-job="historical:sent-with-absent-file"/);assert.match(cards[0],/data-kind="sent">Envío confirmado/);assert.match(cards[0],/Registro anterior/);assert.match(cards[1],/href="\/api\/document\?id=uploaded%3Aavailable"/);assert.match(cards[2],/href="\/api\/document\?id=old-fixture"/);assert.deepEqual(t.a.getModel().requests,[]);assert.equal(t.a.getModel().revision,0);
});

test('CV usage links open current or historical offers and returning preserves profile edits without creating work',async()=>{
 const t=setup(),current={id:'current-offer',company:'Empresa actual ficticia',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],selection:{selected:true,mode:'review'},fingerprint:'version',draft:{messageUsage:'unused',requiredAnswers:[],formAnswerKeys:[]},answers:{},answerOverrides:{},conditions:{},fieldDefinitions:{}};
 Object.assign(t.model,{searchContext:{name:'Persona ficticia',targetRoles:'Analista',languages:'Inglés B2'},profile:{currentCity:'Madrid'},preferences:{location:'España'},experience:'Ficticia',opportunities:[current],historical:[{id:'old-offer',company:'Empresa anterior ficticia',title:'Consultor',state:'Enviada',category:'Laboral',proof:'TEST recibo antiguo',url:'https://example.org/old'}],cvLibrary:[{name:'Ficticio.pdf',url:'/api/document?id=test-pdf',usage:[{opportunityId:'current-offer',company:current.company,title:current.title,kind:'prepared'},{opportunityId:'historical:old-offer',company:'Empresa anterior ficticia',title:'Consultor',kind:'sent',historical:true}]}]});
 const dom=groupedProfileDom(t),paths=[];t.env.fetch=async(path,options)=>{assert.equal(options.method,'GET');assert.equal(options.body,undefined);assert.match(path,/^\/api\/state/);paths.push(path);return {ok:true,json:async()=>t.a.getModel()};};await t.a.setScreen('perfil',null,true,'profile-cv');dom.field('currentCity').value='Cádiz';dom.field('currentCity').focus();await t.dispatchMain('input',dom.field('currentCity'));const draft=t.storage.get('stubbs_jobs-draft:datos:global');
 await t.click({tagName:'A',dataset:{job:'current-offer'}});assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,'current-offer');assert.equal(t.a.getView().filterText,'');assert.match(dom.html,/Empresa actual ficticia/);await t.a.goBack();assert.equal(t.a.getView().screen,'perfil');assert.equal(dom.field('currentCity').value,'Cádiz');assert.equal(t.storage.get('stubbs_jobs-draft:datos:global'),draft);assert.equal(t.env.document.activeElement,dom.field('currentCity'));
 await t.click({tagName:'A',dataset:{job:'historical:old-offer'}});assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,'historical:old-offer');assert.match(dom.html,/Empresa anterior ficticia/);assert.match(dom.html,/Último estado conocido: Enviada/);assert.doesNotMatch(dom.html,/TEST recibo antiguo|data-approve|data-select|data-retry/);assert.equal(t.model.historical[0].proof,'TEST recibo antiguo');await t.a.goBack();assert.equal(dom.field('currentCity').value,'Cádiz');assert.equal(t.storage.get('stubbs_jobs-draft:datos:global'),draft);assert.deepEqual(t.a.getModel().requests,[]);assert.equal(t.a.getModel().revision,0);assert(paths.some(path=>path.includes('case=historical%3Aold-offer')));
});

// Parse the native disclosure and its links from the actual profile markup.
// Layout and the browser's native keyboard behavior remain separate QA.
function cvDisclosureDom(t){
 const profile=groupedProfileDom(t),main=t.env.document.querySelector('#main'),htmlProperty=Object.getOwnPropertyDescriptor(main,'innerHTML'),priorAll=main.querySelectorAll,priorContains=main.contains,priorId=t.env.document.getElementById;let cards=[],nodes=[];
 const decode=value=>String(value||'').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
 const attrs=tag=>Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([,key,value])=>[key,decode(value)]));
 Object.defineProperty(main,'innerHTML',{configurable:true,get(){return htmlProperty.get.call(main);},set(value){
  htmlProperty.set.call(main,value);cards=[];nodes=[];
  for(const match of value.matchAll(/<details class="cv-card-details"[^>]*>[\s\S]*?<\/details>/g)){
   const tag=match[0].match(/^<details[^>]*>/)[0],a=attrs(tag),card={tagName:'DETAILS',dataset:{cvKey:a['data-cv-key']},open:/\sopen(?:\s|>)/.test(tag),links:[],querySelector(selector){return selector==='summary'?this.summary:null;}};
   const summaryHtml=match[0].match(/<summary[^>]*>[\s\S]*?<\/summary>/)[0],summaryAttrs=attrs(summaryHtml.match(/^<summary[^>]*>/)[0]);card.summary={tagName:'SUMMARY',id:summaryAttrs.id,dataset:{},textContent:decode(summaryHtml.replace(/<[^>]*>/g,'')),closest(selector){return selector==='details:not([open])'&&!card.open?card:null;},focus(){t.env.document.activeElement=this;}};
   for(const link of match[0].matchAll(/<a\b[^>]*>[\s\S]*?<\/a>/g)){const attributes=attrs(link[0].match(/^<a[^>]*>/)[0]);if(!attributes['data-job'])continue;card.links.push({tagName:'A',id:attributes.id,dataset:{job:attributes['data-job'],cvKey:attributes['data-cv-key']},textContent:decode(link[0].replace(/<[^>]*>/g,'')),closest(selector){return selector==='details:not([open])'&&!card.open?card:null;},focus(){t.env.document.activeElement=this;}});}
   cards.push(card);nodes.push(card,card.summary,...card.links);
  }
 }});
 main.querySelectorAll=selector=>selector==='details[data-cv-key]'?cards:selector==='button,summary,input,textarea,select,a'?[...priorAll(selector),...cards.flatMap(card=>[card.summary,...card.links])]:selector==='[data-job]'?cards.flatMap(card=>card.links):priorAll(selector);
 main.contains=element=>nodes.includes(element)||priorContains(element);t.env.document.getElementById=id=>nodes.find(node=>node.id===id)||priorId(id);
 return {...profile,get html(){return main.innerHTML;},get cards(){return cards;},card(key){return cards.find(card=>card.dataset.cvKey===key);},field:profile.field};
}

test('compact CV summaries are native, closed by default and keep the PDF action outside the disclosure',()=>{
 const t=setup(),name='Currículum ficticio con nombre completo y suficientemente largo.pdf';t.model.cvLibrary=[{id:'compact',name,url:'/api/document?id=compact',usage:[{opportunityId:'prepared',kind:'prepared',company:'Empresa A',title:'Analista'},{opportunityId:'sent',kind:'sent',company:'Empresa B',title:'Consultor',at:'2026-10-01T09:00:00Z'},{opportunityId:'ignored',kind:'approved',company:'No contar'},{kind:'sent',company:'Sin oferta'}]}];
 const html=t.a.profileForm(),summary=html.match(/<summary class="cv-card-summary"[^>]*>[\s\S]*?<\/summary>/)[0];assert.match(html,/<details class="cv-card-details" data-cv-key="id:compact">/);assert.match(summary,/<h3 class="cv-card-title" title="Currículum ficticio con nombre completo y suficientemente largo.pdf">Currículum ficticio con nombre completo y suficientemente largo.pdf<\/h3>/);assert.match(summary,/2 ofertas · 1 preparado · 1 envío confirmado/);assert.match(summary,/class="cv-card-chevron"[^>]*aria-hidden="true"/);assert.doesNotMatch(summary,/<a\b|<button\b|tabindex=|role="button"|Abrir PDF/);assert.match(html,/<\/details><div class="cv-card-actions"><a class="cv-card-open"/);assert.match(html,/class="cv-usage-company">Empresa A<\/span><span class="cv-usage-title">Analista/);assert.match(html,/class="cv-usage-meta"[\s\S]*data-kind="sent">Envío confirmado/);assert.doesNotMatch(html,/No contar|Sin oferta|data-approve|data-select/);assert.equal(t.a.getModel().revision,0);assert.deepEqual(t.a.getModel().requests,[]);
});

test('CV counts use distinct valid offers, prioritize confirmed sends and distinguish empty from unknown provenance',()=>{
 const t=setup();t.model.cvLibrary=[{id:'one',name:'One.pdf',url:'/api/document?id=one',usage:[{opportunityId:'same',kind:'prepared'},{opportunityId:'same',kind:'sent'},{opportunityId:'same',kind:'prepared'},{opportunityId:'ignore',kind:'unknown'}]},{id:'empty',name:'Empty.pdf',url:'/api/document?id=empty',usage:[]},{id:'unknown',name:'Unknown.pdf',url:'/api/document?id=unknown'},{id:'invalid',name:'Invalid.pdf',url:'/api/document?id=invalid',usage:[{opportunityId:'one',kind:'approved'},{kind:'sent'}]}];
 const cards=[...t.a.profileForm().matchAll(/<article class="cv-card">[\s\S]*?<\/article>/g)].map(match=>match[0]);assert.match(cards[0],/class="cv-card-counts">1 oferta · 1 envío confirmado/);assert.equal((cards[0].match(/class="cv-usage-offer"/g)||[]).length,1);assert.doesNotMatch(cards[0],/CV preparado|preparados|2 ofertas/);assert.match(cards[1],/class="cv-card-counts">Sin ofertas asociadas/);assert.match(cards[1],/Sin solicitudes asociadas\./);for(const card of cards.slice(2)){assert.match(card,/class="cv-card-counts">Uso no registrado/);assert.match(card,/Aún no hay usos registrados para este CV\./);assert.doesNotMatch(card,/1 oferta|envío confirmado|class="cv-usage-offer"/);}assert.deepEqual(t.a.getModel().requests,[]);
});

test('CV disclosures keep independent identities through pending toggle, polling, rename and navigation without writing data',async()=>{
 const t=setup(),hash='same-content-hash';t.model.cvLibrary=[{id:hash,name:'Homónimo.pdf',url:'/api/document?id=registered',usage:[]},{fingerprint:hash,path:'cvs/legacy-A.pdf',name:'Homónimo.pdf',url:'/api/document?id=legacy-A',usage:[]},{fingerprint:hash,path:'cvs/legacy-B.pdf',name:'Homónimo.pdf',url:'/api/document?id=legacy-B',usage:[]}];const dom=cvDisclosureDom(t);t.env.fetch=async(_,options)=>{assert.equal(options.method,'GET');return {ok:true,json:async()=>t.a.getModel()};};await t.a.setScreen('perfil');assert.equal(t.mainListenerOptions.toggle,true);assert(dom.cards.every(card=>!card.open));assert.equal(new Set(dom.cards.map(card=>card.dataset.cvKey)).size,3);
 const original=t.rawStorage.size;dom.card('id:'+hash).open=true;t.a.render(true);assert.equal(dom.card('id:'+hash).open,true,'snapshot catches native toggle before its delayed event');assert.equal(dom.card('fingerprint:'+hash+':cvs/legacy-A.pdf').open,false);assert.equal(dom.card('fingerprint:'+hash+':cvs/legacy-B.pdf').open,false);
 let second=dom.card('fingerprint:'+hash+':cvs/legacy-B.pdf');second.open=true;await t.dispatchMain('toggle',second);assert.equal(t.rawStorage.size,original);assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);second.summary.focus();const focusId=second.summary.id;t.env.window.scrollY=444;t.env.window.scrollTo=(left,top)=>{t.env.window.scrollY=typeof left==='object'?left.top:top;};
 const next=structuredClone(t.a.getModel());next.revision=1;next.version='cv-poll';next.cvLibrary.reverse();next.cvLibrary[0].name='Nombre nuevo.pdf';t.env.fetch=async(_,options)=>{assert.equal(options.method,'GET');return {ok:true,json:async()=>next};};await t.a.refresh();assert.equal(dom.card('id:'+hash).open,true);assert.equal(dom.card('fingerprint:'+hash+':cvs/legacy-B.pdf').open,true);assert.equal(dom.card('fingerprint:'+hash+':cvs/legacy-A.pdf').open,false);assert.equal(t.env.document.activeElement.id,focusId);assert.equal(t.env.window.scrollY,444);
 second.open=false;await t.dispatchMain('toggle',second);t.a.render(true);assert.equal(dom.card('fingerprint:'+hash+':cvs/legacy-B.pdf').open,true,'late event from removed DOM cannot reset current state');const registered=dom.card('id:'+hash);registered.open=false;await t.dispatchMain('toggle',registered);await t.a.setScreen('solicitar');await t.a.setScreen('perfil');assert.equal(dom.card('id:'+hash).open,false);assert.equal(dom.card('fingerprint:'+hash+':cvs/legacy-B.pdf').open,true);assert.equal(dom.card('fingerprint:'+hash+':cvs/legacy-A.pdf').open,false);assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);assert.equal(t.a.getModel().revision,1);
});

test('returning from a CV usage restores the exact link among duplicate offer associations and retains disclosure and drafts',async()=>{
 const t=setup(),offer={id:'shared-offer',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],selection:{selected:true,mode:'review'},fingerprint:'version',draft:{messageUsage:'unused',requiredAnswers:[],formAnswerKeys:[]},answers:{},answerOverrides:{},conditions:{},fieldDefinitions:{}};Object.assign(t.model,{profile:{currentCity:'Madrid'},opportunities:[offer],cvLibrary:['first','second'].map(id=>({id,name:'Mismo nombre.pdf',url:'/api/document?id='+id,usage:[{opportunityId:offer.id,company:offer.company,title:offer.title,kind:'prepared'}]}))});const dom=cvDisclosureDom(t),paths=[];t.env.fetch=async(path,options)=>{assert.equal(options.method,'GET');paths.push(path);return {ok:true,json:async()=>t.a.getModel()};};t.env.window.scrollTo=(left,top)=>{t.env.window.scrollY=typeof left==='object'?left.top:top;};await t.a.setScreen('perfil');dom.field('currentCity').value='Cádiz';await t.dispatchMain('input',dom.field('currentCity'));const draft=t.storage.get('stubbs_jobs-draft:datos:global'),second=dom.card('id:second');second.open=true;const origin=second.links[0];origin.focus();t.env.window.scrollY=360;
 await t.click(origin);assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,offer.id);second.open=false;await t.dispatchMain('toggle',second);await t.a.goBack();assert.equal(t.a.getView().screen,'perfil');assert.equal(dom.card('id:first').open,false);assert.equal(dom.card('id:second').open,true);assert.equal(t.env.document.activeElement,dom.card('id:second').links[0]);assert.notEqual(t.env.document.activeElement.id,dom.card('id:first').links[0].id);assert.equal(t.env.window.scrollY,360);assert.equal(dom.field('currentCity').value,'Cádiz');assert.equal(t.storage.get('stubbs_jobs-draft:datos:global'),draft);assert.deepEqual(t.a.getModel().requests,[]);assert.equal(t.a.getModel().revision,0);assert(paths.every(path=>path.startsWith('/api/state')));
});

test('conflict inspection shows exact current text rather than HTML entities and records no write',async()=>{
 const t=setup(),info={textContent:''},form={dataset:{form:'about'},values:{name:'Mis valores'},_shown:{name:'Anterior'},_expected:{name:'Anterior'},_dirty:true,_conflict:{operation:{kind:'ui-profile-section',section:'about',values:{name:'Mis valores'}}},elements:{namedItem(){return {dataset:{type:'text'}};}},querySelector(selector){return selector==='.form-info'?info:null;}};t.model.labels={name:'Nombre'};t.model.searchContext.name='AT&T <Equipo> "ficticio"';t.setForm(form);t.a.setScreenState('perfil');
 await t.click({dataset:{current:'1'},form});assert.equal(info.textContent,'Valores actuales: Nombre: AT&T <Equipo> "ficticio"');assert.deepEqual(form._expected,{name:'Anterior'});assert.equal(form._dirty,true);assert.equal(t.a.getModel().revision,0);assert.deepEqual(t.a.getModel().requests,[]);assert.equal(t.rawStorage.size,0);
});

test('custom numeric answers accept decimals and negative values while official integers and custom bounds remain validated',async()=>{
 const t=setup();Object.assign(t.model,{profile:{custom_decimal:0.5,custom_negative:-2,noticeDays:0},searchContext:{name:'Persona ficticia'},fieldDefinitions:{custom_decimal:{key:'custom_decimal',label:'Dato decimal ficticio',type:'number',scope:'global'},custom_negative:{key:'custom_negative',label:'Dato negativo ficticio',type:'number',scope:'global'}}});const dom=groupedProfileDom(t),operations=[];t.a.setScreenState('perfil');t.a.render();assert.equal(dom.field('custom_decimal').step,'any');assert.equal(dom.field('custom_decimal').min,'-1000000');assert.equal(dom.field('custom_decimal').max,'1000000');assert.equal(dom.field('noticeDays').dataset.type,'text');
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;operations.push(operation);const state=structuredClone(t.a.getModel());state.revision++;for(const [key,value] of Object.entries(operation.values)){if(key==='name')state.searchContext.name=value;else state.profile[key]=value;}return {ok:true,json:async()=>({state})};};dom.field('name').value='Nombre cambiado';await t.dispatchMain('input',dom.field('name'));assert.equal(await t.a.saveProfileChanges(),true);assert.deepEqual(operations[0].values,{name:'Nombre cambiado'});assert.equal(t.a.getModel().profile.custom_decimal,0.5);assert.equal(t.a.getModel().profile.custom_negative,-2);
 dom.field('custom_decimal').value='-0.25';await t.dispatchMain('input',dom.field('custom_decimal'));dom.field('noticeDays').value='x'.repeat(301);await t.dispatchMain('input',dom.field('noticeDays'));assert.equal(await t.a.saveProfileChanges(),false);assert.equal(operations.length,1);assert.equal(t.env.document.activeElement,dom.field('noticeDays'));dom.field('noticeDays').value='0';await t.dispatchMain('input',dom.field('noticeDays'));dom.field('custom_decimal').value='1000001';await t.dispatchMain('input',dom.field('custom_decimal'));assert.equal(await t.a.saveProfileChanges(),false);assert.equal(operations.length,1);assert.equal(t.env.document.activeElement,dom.field('custom_decimal'));dom.field('custom_decimal').value='-0.25';await t.dispatchMain('input',dom.field('custom_decimal'));await t.dispatch('keydown',dom.field('custom_decimal'),{key:'s',ctrlKey:true});assert.equal(operations.length,2);assert.deepEqual(operations[1].values,{custom_decimal:-0.25});assert.deepEqual(operations[1].expected,{custom_decimal:0.5});assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);
});

test('valid HTTP scheme casing keeps saved offer and application links usable',()=>{
 const t=setup(),recipient='HTTPS://example.org/apply?offer=synthetic&lang=es',material={recipient,answers:{},formAnswerKeys:[],messageUsage:'unused'},job={id:'uppercase-link',company:'Empresa ficticia',title:'Analista',url:'HTTP://example.org/jobs/synthetic',state:'Preparar',apply:'Sí',requests:[],missing:[],questions:[],selection:{selected:true,mode:'review'},fingerprint:'synthetic-package',draft:{...material,requiredAnswers:[]},answers:{},answerOverrides:{},conditions:{},packages:[{id:'synthetic-package',isCurrent:true,cvUrl:'/api/document?id=synthetic',payload:material}]};
 t.model.opportunities=[job];t.model.labels={};t.a.setSelected(job.id);t.a.setReviewSnapshot(job);
 assert.match(t.a.detail(),/href="HTTP:\/\/example.org\/jobs\/synthetic"/);for(const html of [t.a.detail(),t.a.reviewPage()]){assert.match(html,/href="HTTPS:\/\/example.org\/apply\?offer=synthetic&amp;lang=es"/);assert.match(html,/Formulario de solicitud/);}
 job.url='javascript:alert(1)';assert.doesNotMatch(t.a.detail(),/href="javascript:/);assert.equal(t.a.getModel().revision,0);assert.deepEqual(t.a.getModel().requests,[]);
});

test('dynamic interview exposes a brief coverage count and conscious blanks without extra steps',()=>{
 const t=setup();t.model.setupComplete=false;
 t.model.onboarding={status:'preparing',checkedAt:'2026-10-03T12:00:00Z',coverage:{total:21,provided:7,blank:2,pending:12,complete:false}};
 const html=t.a.setupForm();assert.match(html,/9 de 21 aspectos del perfil tratados/);assert.match(html,/Responde a lo pendiente/);
 assert.match(html,/2 dejados en blanco por tu decisión/);assert.match(html,/puedes dejar datos en blanco/);
 assert.doesNotMatch(html,/setup-progress|<li\b/);assert.doesNotMatch(html,/<form|<input|data-confirm-field/);
 const prompt=t.a.setupAgentPrompt();assert.match(prompt,/confirmar primero los datos esenciales de la búsqueda/);assert.match(prompt,/pregunta solo por lo necesario ahora/);
 assert.match(prompt,/confirma qué quiero dejar en blanco/);assert.match(prompt,/Si ya tengo perfil, no repitas la entrevista/);
 t.model.onboarding.coverage={total:21,provided:20,blank:1,pending:0,complete:true};
 const complete=t.a.setupForm();assert.match(complete,/21 de 21 aspectos del perfil tratados/);assert.match(complete,/Continúa en el chat para revisar el resumen/);assert.match(complete,/1 dejado en blanco/);
 assert.doesNotMatch(complete,/Quedan 0/);
});

test('welcome directs consciously blank essential answers to Mi perfil before searching',()=>{
 const t=setup();t.model.searchContext={name:'',targetRoles:''};t.model.preferences={location:''};t.model.cvLibrary=[];
 t.model.setupComplete=true;t.model.onboarding={needsWelcome:true};t.a.setScreenState('preparado');t.a.render();
 const html=t.env.document.querySelector('#main').innerHTML;assert.match(html,/data-setup-finish="perfil">Revisar mi perfil/);
 assert.match(html,/Antes de buscar, concreta los puestos y la zona/);assert.match(html,/pide «Busca ofertas nuevas» en el chat/);
 assert.equal((html.match(/<button /g)||[]).length,2);assert.doesNotMatch(html,/<form/);
});

test('an explicitly unknown salary currency is not displayed as a guessed euro',()=>{
 const t=setup();t.model.searchContext={currency:''};t.model.preferences={minimumFixed:null};t.model.profile={salaryExpectationFixed:null};
 const html=t.a.searchSettingsPanels();assert.match(html,/name="currency"[^>]*value=""/);assert.match(html,/<span data-salary-currency="1">Por indicar<\/span>/);
 assert.doesNotMatch(html,/<span>EUR<\/span>/);
});

test('existing offers explain their fit once and retain the complete experience example in checks',()=>{
 const t=setup(),example='Automaticé informes con Power Query para Empresa <ficticia>.',job={id:'one',company:'Empresa',title:'Analista',state:'Preparar',apply:'Revisar',requests:[],packages:[],questions:[],missing:['review'],draft:{recipient:'',message:'',messageUsage:'unused'},answers:{},conditions:{},assessment:{reason:'Valoración completa conservada.',at:new Date().toISOString(),isCurrent:true,unknowns:['Confirmar la parte fija.'],references:[{url:'https://example.org/offer',text:'Automatización e informes.'}],bestArgument:{experienceQuote:example,requirement:'Automatización <comprobada>.',sourceUrl:'https://example.org/offer'}}};
 t.model.opportunities=[job];t.a.setSelected('one');const before=structuredClone(job),html=t.a.detail();
 assert.match(html,/<h2>Encaje contigo<\/h2>/);assert.doesNotMatch(html,/Automaticé informes|Tu mejor argumento|offer-argument-example/);assert.equal(job.assessment.bestArgument.experienceQuote,example);assert.equal(job.assessment.bestArgument.requirement,'Automatización <comprobada>.');
 const assessment=html.match(/<section class="case-section offer-assessment[^"]*">([\s\S]*?)<\/section>/)[1];assert.equal((assessment.match(/<p[ >]/g)||[]).length,2);assert.match(assessment,/Fuente del anuncio|Valoración registrada/);assert.doesNotMatch(assessment,/<small|<details|<h3/);assert.match(assessment,/Valoración completa conservada/);
 assert.doesNotMatch(html,/Confirmar la parte fija|Consultar fuente|data-checks=/);assert.equal(job.assessment.unknowns[0],'Confirmar la parte fija.');assert.deepEqual(job,before);
 job.assessment.isCurrent=false;const stale=t.a.detail();assert.doesNotMatch(stale,/Tu mejor argumento|Automaticé informes|Automatización &lt;comprobada&gt;/);assert.match(stale,/han cambiado la oferta, tus preferencias o tu experiencia/);
 job.assessment.isCurrent=true;job.apply='No';assert.match(t.a.detail(),/Encaje contigo/);assert.doesNotMatch(t.a.detail(),/Por qué se descarta|Tu mejor argumento/);
});

test('the fit explanation keeps its meaning across sent and interview states with or without a CV example',()=>{
 const t=setup(),job={id:'one',company:'Empresa',title:'Analista',state:'Enviada',apply:'Ya enviada',sent:{at:new Date().toISOString()},requests:[],packages:[],questions:[],missing:[],draft:{recipient:'',message:'',messageUsage:'unused'},answers:{},conditions:{},assessment:{reason:'TEST: valoración conservada.',at:new Date().toISOString(),isCurrent:true,unknowns:[],references:[{url:'https://example.org/offer',text:'TEST: informes'}],bestArgument:{experienceQuote:'TEST: automaticé informes de una empresa ficticia.',requirement:'TEST: reporting corporativo.',sourceUrl:'https://example.org/offer'}}};
 t.model.opportunities=[job];t.a.setSelected('one');
 for(const state of ['Enviada','Entrevista']){job.state=state;const before=structuredClone(job),html=t.a.detail();assert.match(html,/Encaje contigo/);assert.doesNotMatch(html,/Incluido en el CV|Argumento enviado|TEST: automaticé informes/);assert.deepEqual(job,before);}
 delete job.assessment.bestArgument;assert.match(t.a.detail(),/Encaje contigo/);assert.doesNotMatch(t.a.detail(),/Tu mejor argumento|Por qué merece atención/);
});

test('the simplified offer view keeps actions and internal proof without duplicating checks',()=>{
 const t=setup(),doubt='Confirmar días presenciales antes de elegir.',job={id:'one',company:'Empresa <ficticia>',title:'Analista Power BI',state:'Preparar',apply:'Revisar',requests:[],packages:[],questions:[],missing:['review'],draft:{recipient:'',message:'',messageUsage:'unused'},answers:{},conditions:{},assessment:{reason:'Experiencia defendible en BI.',at:new Date().toISOString(),isCurrent:true,unknowns:[doubt,'Otra duda completa conservada.'],references:[{url:'https://example.org/offer',text:'Modelos de datos'}]}};
 t.model.opportunities=[job];t.a.setSelected('one');const before=structuredClone(t.model),html=t.a.detail();
 assert.match(html,/offer-detail/);assert.match(html,/Empresa &lt;ficticia&gt;/);assert.match(html,/<h1[^>]*>Analista Power BI<\/h1>/);
 assert.doesNotMatch(html,/Conviene comprobar|Confirmar días presenciales|Situación actual/);assert.match(html,/data-investigate="one">Pedir comprobación/);
 assert.doesNotMatch(html,/assessment-details|Otra duda completa conservada|Consultar fuente/);assert.equal(job.assessment.unknowns[1],'Otra duda completa conservada.');assert.equal(job.assessment.references[0].url,'https://example.org/offer');
 assert.ok(html.indexOf('offer-status')<html.indexOf('Condiciones'));assert.ok(html.indexOf('Condiciones')<html.indexOf('Formulario de solicitud'));
 assert.match(html,/data-change="one"/);assert.doesNotMatch(html,/data-checks=/);assert.match(html,/data-activity="one"/);assert.deepEqual(t.model,before);
 job.assessment.isCurrent=false;assert.doesNotMatch(t.a.detail(),/Conviene comprobar|Confirmar días presenciales/);
});
test('application sections keep verified destinations and the exact submitted material',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Revisar',requests:[],packages:[],questions:[],missing:[],draft:{recipient:'',messageUsage:'unused',formAnswerKeys:['currentCity']},answers:{currentCity:'Ciudad actual',minimumFixed:32000},answerOverrides:{},fieldDefinitions:{currentCity:{label:'Ciudad actual'}},conditions:{}};
 t.model.opportunities=[job];t.a.setSelected('one');let before=structuredClone(job),html=t.a.detail();
 assert.match(html,/<h2>Formulario de solicitud<\/h2>/);assert.match(html,/<dl class="meta">[\s\S]*<dt>Ciudad actual<\/dt>[\s\S]*<dt>CV para la oferta<\/dt><dd><article class="cv-card case-cv-card"[\s\S]*?<\/dl>/);
 assert.doesNotMatch(html,/Mi solicitud|Acceso al formulario|CV adjunto|Respuestas del formulario/);
 assert.match(html,/Pendiente de comprobar el acceso/);assert.match(html,/Pendiente de preparar/);assert.doesNotMatch(html,/Abrir PDF|32000/);assert.deepEqual(job,before);
 job.sent={at:'2026-10-01T10:00:00Z'};job.state='Enviada';job.cvUrl='/api/document?id=sent-cv';job.cvLabel='CV enviado.pdf';job.sentMaterial={recipient:'https://example.org/original-form',answers:{currentCity:'Ciudad enviada'},formAnswerKeys:['currentCity'],messageUsage:'unused'};
 job.draft.recipient='https://example.org/new-form';before=structuredClone(job);html=t.a.detail();
 assert.match(html,/<h2><a href="https:\/\/example.org\/original-form"[^>]*>Formulario de solicitud/);assert.match(html,/href="\/api\/document\?id=sent-cv"[^>]*>Abrir PDF/);assert.match(html,/Ciudad enviada/);assert.doesNotMatch(html,/new-form|<dd>Ciudad actual|data-answers=/);assert.deepEqual(job,before);
 const card=html.match(/<article class="cv-card case-cv-card"[\s\S]*?<\/article>/)[0];assert.match(card,/class="cv-card-icon"/);assert.match(card,/CV enviado.pdf/);assert.doesNotMatch(card,/<details|<summary|cv-card-counts|cv-card-chevron|Descargar|<p\b/);assert.equal((card.match(/<a\b/g)||[]).length,1);
 delete job.sent;delete job.sentMaterial;job.state='Preparar';job.draft.recipient='test@example.org';html=t.a.detail();assert.match(html,/Solicitud por correo: test@example.org/);assert.match(html,/<h2>Formulario de solicitud<\/h2>/);assert.doesNotMatch(html,/<h2><a[^>]*>Formulario de solicitud/);
});

test('the argument omits repeated status and condition uncertainty while keeping the technical gap and original proof',()=>{
 const t=setup(),reason='Tu automatización y reporting con Power BI encajan. La banda publicada no confirma la parte fija ni el contrato indefinido; falta aclarar el alcance de DAX y Fabric. La candidatura ya está enviada.',quote='Proyectos documentados en los CVs de base: automatización de facturación mensual con Power Query; desarrollo de informes de Power BI.',job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Enviada',apply:'Ya enviada',sent:{at:'2026-10-01T10:00:00Z'},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},conditions:{},assessment:{isCurrent:true,reason,unknowns:[],references:[],bestArgument:{experienceQuote:quote,requirement:'Reporting de Finanzas.'}}};
 t.model.opportunities=[job];t.a.setSelected('one');const before=structuredClone(job),html=t.a.offerConditions(job)+t.a.detail(),panel=html.match(/<section class="case-section offer-assessment[^\"]*">([\s\S]*?)<\/section>/)[1];
 assert.match(panel,/Tu automatización y reporting con Power BI encajan/);assert.match(panel,/Falta aclarar el alcance de DAX y Fabric/);assert.doesNotMatch(panel,/Automatización de facturación mensual con Power Query; desarrollo de informes de Power BI/);
 assert.doesNotMatch(panel,/ya está enviada|banda publicada|contrato indefinido|Proyectos documentados|Puedes apoyarte/);assert.equal((panel.match(/<p[ >]/g)||[]).length,1);
 assert.equal(job.assessment.reason,reason);assert.equal(job.assessment.bestArgument.experienceQuote,quote);assert.deepEqual(job,before);
 job.sent=null;job.apply='No';job.assessment.reason='El fijo de 30.000 EUR queda por debajo de tu mínimo. El contrato es temporal. Python profesional es obligatorio y solo consta uso personal básico.';
 const rejected=t.a.detail();assert.match(rejected,/Encaje contigo/);assert.doesNotMatch(rejected,/Por qué se descarta/);assert.match(rejected,/fijo de 30.000 EUR queda por debajo/);assert.match(rejected,/contrato es temporal/);assert.match(rejected,/Python profesional es obligatorio/);
 job.apply='Revisar';job.assessment.reason='Power BI encaja, pero falta experiencia en Python profesional y el contrato sigue sin confirmar.';assert.match(t.a.detail(),/falta experiencia en Python profesional/);
 job.assessment.reason='Candidatura ya enviada.';delete job.assessment.bestArgument;assert.doesNotMatch(t.a.detail(),/offer-assessment/);assert.equal(job.assessment.reason,'Candidatura ya enviada.');
});

test('fit copy preserves material conditions and unfamiliar technical gaps instead of filtering by keywords',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Investigar',apply:'Revisar',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},conditions:{},assessment:{isCurrent:true,reason:'',references:[],unknowns:[]}};
 t.model.opportunities=[job];t.a.setSelected(job.id);
 for(const reason of [
  'Tu reporting encaja. El contrato sigue sin confirmar si dbt y RLS son imprescindibles.',
  'El remoto no confirma que permita residir en Portugal.',
  'La banda publicada no confirma un fijo de 35.000 EUR sin variable.',
  'La presencialidad sigue sin confirmar: solo te sirve con máximo un viaje al mes.',
  'Pide Power BI; dbt es valorable. Tu formación no acredita experiencia profesional en dbt.',
  'La candidatura ya está enviada, pero el portal pide verificar su recepción.',
  'El fijo es 30.000 EUR y el contrato es temporal.'
 ]){
  job.assessment.reason=reason;const before=structuredClone(job),panel=t.a.detail().match(/<section class="case-section offer-assessment">([\s\S]*?)<\/section>/)[1];
  assert.ok(panel.includes(reason),reason);assert.deepEqual(job,before);
 }
 job.assessment.reason='Power BI encaja. La banda publicada no confirma la parte fija ni el contrato indefinido; falta aclarar dbt y RLS. Candidatura ya enviada.';
 const before=structuredClone(job),panel=t.a.detail().match(/<section class="case-section offer-assessment">([\s\S]*?)<\/section>/)[1];assert.match(panel,/Power BI encaja\. Falta aclarar dbt y RLS\./);assert.doesNotMatch(panel,/banda publicada|Candidatura ya enviada/);assert.deepEqual(job,before);
});

test('fit copy never turns a pending eligibility check into a human rejection or a repeated CV pitch',()=>{
 const t=setup(),reason='Coinciden tus informes de Power BI y el trabajo con negocio. Falta comprobar SQL avanzado.',job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Investigar',apply:'No',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},conditions:{},assessment:{isCurrent:true,reason,unknowns:[],references:[],bestArgument:{experienceQuote:'Automaticé informes de una empresa ficticia.',requirement:'TEST requisito comprobado'}}};
 t.model.opportunities=[job];t.a.setSelected(job.id);
 for(const values of [{state:'Investigar',apply:'No'},{state:'Enviada',apply:'Ya enviada'},{state:'Entrevista',apply:'Revisar'}]){
  Object.assign(job,values);const before=structuredClone(job),panel=t.a.detail().match(/<section class="case-section offer-assessment">([\s\S]*?)<\/section>/)[1];
  assert.match(panel,/<h2>Encaje contigo<\/h2>/);assert.ok(panel.includes(reason));assert.doesNotMatch(panel,/Por qué se descarta|Tu mejor argumento|Automaticé|<em>|<details|<h3|<small/);assert.deepEqual(job,before);
 }
 job.assessment.reason='';assert.doesNotMatch(t.a.detail(),/offer-assessment/);assert.equal(job.assessment.bestArgument.experienceQuote,'Automaticé informes de una empresa ficticia.');
 job.assessment.reason='Tu experiencia con Empresa <ficticia> no acredita SQL avanzado.';assert.match(t.a.detail(),/Empresa &lt;ficticia&gt; no acredita SQL avanzado/);
 job.assessment.isCurrent=false;assert.doesNotMatch(t.a.detail(),/no acredita SQL avanzado/);assert.match(t.a.detail(),/Esta valoración necesita actualizarse/);
});

test('all state labels keep plain text and a decorative vector while unresolved sends retain their recovery action',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Enviada',apply:'Ya enviada',sent:{at:'2026-10-01T10:00:00Z'},requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},conditions:{}};
 t.model.opportunities=[job];const before=structuredClone(job),html=t.a.applyPage();assert.match(html,/data-offer-state="seguimiento" class="flow-status"><svg[^>]*data-icon="check"[\s\S]*?<\/svg>Siguiendo<\/span>/);assert.doesNotMatch(html,/flow-status-sent/);assert.deepEqual(job,before);
 delete job.sent;job.state='Preparar';job.requests=[{id:'uncertain-send',type:'send',status:'blocked',startedAt:'2026-10-01T10:00:00Z',updatedAt:'2026-10-01T10:05:00Z'}];
 const uncertain=t.a.applyPage();assert.doesNotMatch(uncertain,/flow-status-sent|data-copy-recovery=/);assert.match(uncertain,/>Por atender<\/span>/);t.a.setSelected('one');assert.match(t.a.detail(),/data-copy-recovery="uncertain-send"/);
});

test('filters, column values and current or historical details share exactly the same nine categories',()=>{
 const t=setup(),fresh=new Date().toISOString(),base={title:'Analista ficticio',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review'],draft:{messageUsage:'unused'},answers:{},conditions:{}};
 const cases=[
  {...base,id:'choose',company:'Elegir'},
  {...base,id:'prepare',company:'Preparar',selection:{selected:true,mode:'auto'},requests:[{type:'review',status:'queued'}]},
  {...base,id:'review',company:'Revisar',selection:{selected:true,mode:'review'},missing:[]},
  {...base,id:'sending',company:'Envío activo',requests:[{id:'send',type:'send',status:'running',updatedAt:fresh}]},
  {...base,id:'follow',company:'Seguimiento',sent:{at:fresh}},
  {...base,id:'rejected',company:'Candidatura rechazada',state:'Rechazada',sent:{at:fresh}},
  {...base,id:'interview',company:'Entrevista sin recibo',state:'Entrevista',next:'Acuerda la fecha.'},
  {...base,id:'offer',company:'Oferta recibida',state:'Oferta'},
  {...base,id:'closed-uncertain',company:'Cierre con envío incierto',state:'Cerrada',requests:[{id:'uncertain',type:'send',status:'blocked'}]},
  {...base,id:'closed',company:'Proceso cerrado',state:'Cerrada'},
  {...base,id:'archived',company:'Archivo',state:'Descartada'}
 ];
 t.model.opportunities=cases;t.model.historical=[{id:'old',canonicalKey:'old',category:'Laboral',company:'Histórica',title:'Analista',state:'Enviada',lastActivityLabel:'Julio 2025'}];
 const before=structuredClone(t.model);t.a.setHistoryLimit(100);const all=[...cases,...UI.archive(t.model)],html=t.a.applyPage();
 assert.equal((html.match(/data-flow-filter=/g)||[]).length,10);
 assert.equal((html.match(/data-job-row=/g)||[]).length,all.length);
 for(const j of all){
  const state=UI.offerState(j),row=html.match(new RegExp(`data-job-row="${j.id}"[\\s\\S]*?</tr>`))[0];
  assert.match(row,new RegExp(`data-offer-state="${state.key}"[^>]*>[\\s\\S]*?${state.label}</span>`));
  t.a.setSelected(j.id);const detail=t.a.detail();assert.match(detail,new RegExp(`<strong data-offer-state="${state.key}"><svg[^>]*data-icon="${state.icon}"[\\s\\S]*?</svg>${state.label}</strong>`));
  const badge=row.match(/<span data-offer-state="[^"]+" class="flow-status"[^>]*>([\s\S]*?)<\/span>/)[1];
  assert.equal(badge.replace(/<svg[\s\S]*?<\/svg>/,''),state.label);assert.match(badge,new RegExp(`^<svg[^>]*data-icon="${state.icon}"[^>]*aria-hidden="true"[^>]*focusable="false"`));assert.match(badge,/fill="currentColor" stroke="none"/);assert.doesNotMatch(badge,/<img|[\p{Extended_Pictographic}]/u);
 }
 for(const state of UI.offerStates){
  t.a.setFlowFilter('solicitar',state.key);const filtered=t.a.applyPage(),expected=all.filter(j=>UI.offerState(j).key===state.key).map(j=>j.id).sort();
  assert.deepEqual([...filtered.matchAll(/data-job-row="([^"]+)"/g)].map(m=>m[1]).sort(),expected);
  const label=({descartadas:'Descartadas',logradas:'Logradas',cerradas:'Cerradas',rechazadas:'Rechazadas'})[state.key]||state.label;
  assert.match(filtered,new RegExp(`data-flow-filter="${state.key}"[^>]*aria-pressed="true">${label} <span class="filter-count">${expected.length}</span>`));
 }
 t.a.setFlowFilter('solicitar','todas');t.a.applyPage();const catalog=t.a.columnCatalog('solicitar','status');assert.deepEqual(Array.from(catalog.values).sort(),UI.offerStates.map(s=>s.label).sort());
 assert.deepEqual(t.model,before);
});

test('operational filters appear when needed while the six main categories remain accessible',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review']};
 t.model.opportunities=[job];const before=structuredClone(t.model);
 let html=t.a.applyPage();assert.equal((html.match(/data-flow-filter=/g)||[]).length,7);assert.match(html,/Por decidir <span class="filter-count">1<\/span>/);assert.doesNotMatch(html,/data-flow-filter="atencion"|data-flow-filter="enviando"/);
 t.a.setFlowFilter('solicitar','atencion');html=t.a.applyPage();assert.match(html,/data-flow-filter="atencion"[^>]*aria-pressed="true">Por atender <span class="filter-count">0<\/span>/);assert.match(html,/No hay ofertas en este grupo/);assert.deepEqual(t.model,before);
 job.requests=[{type:'investigate',status:'blocked',need:'access',summary:'Falta acceso.'}];html=t.a.applyPage();assert.match(html,/Por atender <span class="filter-count">1<\/span>/);assert.match(html,/data-job-row="one"/);assert.match(html,/data-flow-filter="sin-elegir"/);
 job.requests=[];html=t.a.applyPage();assert.match(html,/Por atender <span class="filter-count">0<\/span>/);assert.doesNotMatch(html,/data-job-row="one"/);
 t.a.setFlowFilter('solicitar','todas');html=t.a.applyPage();assert.doesNotMatch(html,/data-flow-filter="atencion"/);assert.match(html,/data-job-row="one"/);
});

test('detail keeps secondary actions open and change visible in the banner during a preserved poll render',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí',selection:{selected:true,mode:'review'},requests:[],packages:[],questions:[],missing:['review'],draft:{messageUsage:'unused'},answers:{},conditions:{}};
 t.model.opportunities=[job];t.a.setSelected(job.id);t.a.setScreenState('detalle');
 const main=t.env.document.querySelector('#main'),originalAll=main.querySelectorAll.bind(main);
 let disclosures=[{id:'offer-more-one',open:true}],html='';
 main.querySelectorAll=selector=>selector==='details[id]'?disclosures:originalAll(selector);
 t.env.document.getElementById=id=>disclosures.find(item=>item.id===id)||null;
 Object.defineProperty(main,'innerHTML',{get(){return html;},set(value){html=value;disclosures=disclosures.map(item=>({id:item.id,open:false}));}});
 const before=structuredClone(t.model);t.a.render(true);assert.ok(disclosures.every(item=>item.open));assert.deepEqual(t.model,before);
 assert.match(html,/<details class="case-disclosure case-more"[^>]*>[\s\S]*data-unselect="one"/);
 assert.match(html.match(/<section class="case-status offer-status"[\s\S]*?<\/section>/)[0],/class="offer-change" data-change="one">Pedir cambio/);assert.equal((html.match(/data-change="one"/g)||[]).length,1);
});

test('summary links one current recommendation directly to the existing offer with no write',()=>{
 const t=setup(),make=(id,priority)=>({id,priority,company:'Empresa '+id,title:'Analista',state:'Preparar',apply:'Revisar',requests:[],packages:[],questions:[],missing:['review'],assessment:{isCurrent:true,unknowns:['Comprobar modalidad.']}});
 t.model.opportunities=[make('b','B'),make('a','A')];const before=structuredClone(t.model),html=t.a.agentPage();
 assert.equal((html.match(/class="offer-recommendation"/g)||[]).length,1);assert.match(html,/Empresa a/);assert.match(html,/offer-recommendation-role"> · Analista/);assert.match(html,/data-job="a">Ver oferta/);
 assert.doesNotMatch(html,/data-investigate|data-select|data-approve/);assert.deepEqual(t.model,before);
 t.model.opportunities[1].assessment.isCurrent=false;assert.match(t.a.agentPage(),/data-job="b">Ver oferta/);
});
test('retired checks links return to the offer or summary without exposing or changing proof',async()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review'],draft:{messageUsage:'unused'},answers:{},conditions:{},evidence:[{'Condición':'Modalidad','Texto o motivo':'PRIVATE ORIGINAL PROOF','Fuente':'https://example.org/offer'}]};
 t.model.opportunities=[job];t.env.fetch=async()=>({ok:true,json:async()=>t.model});const before=structuredClone(t.model);
 for(const page of ['comprobaciones','salud']){
  await t.a.setScreen(page,'one');assert.equal(t.a.getView().screen,'detalle');assert.equal(t.a.getView().selected,'one');assert.doesNotMatch(t.env.document.querySelector('#main').innerHTML,/PRIVATE ORIGINAL PROOF|data-checks=|Consultar origen/);
  await t.a.setScreen(page);assert.equal(t.a.getView().screen,'agente');assert.equal(t.a.getView().selected,null);
  await t.a.setScreen(page,'missing');assert.equal(t.a.getView().screen,'agente');assert.equal(t.a.getView().selected,null);
 }
 assert.deepEqual(t.model,before);assert.doesNotMatch(t.a.history()+t.a.changeForm()+t.a.agentPage(),/data-checks=|Ver comprobaciones/);
});

test('a simple offer heading retains concrete blockers, mode, deadlines and uncertain delivery safeguards',()=>{
 const t=setup(),job={id:'one',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review'],draft:{messageUsage:'unused'},answers:{},conditions:{},assessment:{isCurrent:true,reason:'Tus informes encajan. Falta comprobar SQL avanzado.',unknowns:['Confirmar contrato.'],references:[]}};
 t.model.opportunities=[job];t.a.setSelected(job.id);const heading=()=>t.a.detail().match(/<section class="case-status offer-status"[\s\S]*?<\/section>/)[0];
 let html=heading();assert.match(html,/<strong data-offer-state="sin-elegir"><svg[^>]*data-icon="question"[\s\S]*?<\/svg>Por decidir<\/strong>/);assert.match(html,/Solicitar con revisión/);assert.match(html,/Auto-solicitud/);assert.match(html,/class="offer-change" data-change="one">Pedir cambio/);assert.doesNotMatch(html,/Situación actual|Conviene comprobar|Tus informes|Confirmar contrato|offer-request-options/);
 job.selection={selected:true,mode:'auto'};job.requests=[{id:'queued',type:'review',status:'queued'}];html=heading();assert.match(html,/En preparación<\/strong>[\s\S]*Auto-solicitud/);assert.doesNotMatch(html,/preparará|Puedes seleccionar|Último registro/);
 job.requests=[{id:'blocked',type:'review',status:'blocked',need:'access',summary:'Inicia sesión en el portal para continuar.',result:'PRIVATE FULL TECHNICAL PROOF'}];html=heading();assert.match(html,/Inicia sesión en el portal para continuar/);assert.match(html,/data-resolve="one"/);assert.doesNotMatch(html,/PRIVATE FULL TECHNICAL PROOF/);
 job.questions=[{key:'custom_idioma',label:'Nivel de inglés'}];html=heading();assert.match(html,/>Por atender<\/strong>/);assert.match(html,/Nivel de inglés/);assert.match(html,/data-answers="one"/);
 job.questions=[];job.requests=[{id:'uncertain',type:'send',status:'blocked',startedAt:'2026-10-01T10:00:00Z',updatedAt:'2026-10-01T10:05:00Z'}];html=heading();assert.match(html,/El envío quedó sin confirmar/);assert.match(html,/data-copy-recovery="uncertain"/);assert.doesNotMatch(html,/data-approve=|data-select=/);
 job.requests=[{id:'running',type:'send',status:'running',updatedAt:new Date().toISOString()}];html=heading();assert.match(html,/data-change=/);assert.doesNotMatch(html,/data-select=/);
 job.requests=[];job.sent={at:'2026-10-02T10:00:00Z'};html=heading();assert.match(html,/data-change=/);assert.doesNotMatch(html,/data-select=/);job.sent=null;
 job.requests=[];job.state='Entrevista';job.next='Confirma tu disponibilidad para la entrevista.';job.externalDeadline='2026-10-08';html=heading();assert.match(html,/Confirma tu disponibilidad/);assert.match(html,/Plazo:/);
});

test('activity results retain summaries and useful coverage while keeping technical proof internal',()=>{
 const t=setup(),request={id:'search',type:'discovery',status:'done',summary:'Dos ofertas nuevas para elegir.',result:'PRIVATE TECHNICAL PROOF',updatedAt:'2026-10-01T10:00:00Z',instructions:[{text:'Buscar puestos de analista.'}]};
 t.model.requests=[request];t.a.setSelected(request.id);const before=structuredClone(t.model),html=t.a.activityReport();
 assert.match(html,/Dos ofertas nuevas para elegir/);assert.match(html,/Buscar puestos de analista/);assert.doesNotMatch(html,/PRIVATE TECHNICAL PROOF|activity-proof|data-checks=|Pruebas y pasos anteriores/);assert.deepEqual(t.model,before);
 t.model.history=[{id:'checked',title:'Valoración guardada',detail:'PRIVATE HISTORICAL PROOF',at:'2026-10-01T10:00:00Z'}];t.a.setSelected('event:checked');assert.doesNotMatch(t.a.activityReport(),/PRIVATE HISTORICAL PROOF/);assert.equal(t.model.history[0].detail,'PRIVATE HISTORICAL PROOF');
});

test('official numeric limits reject all invalid edited panels before saving earlier personal edits',async()=>{
 for(const [key,value] of [['maxTrips','32'],['noticeDays','x'.repeat(301)],['minimumFixed','0'],['minimumFixed','1000000001'],['salaryExpectationFixed','0'],['salaryExpectationFixed','1000000001']]){
  const t=setup();Object.assign(t.model,{profile:{currentCity:'Madrid',noticeDays:15,salaryExpectationFixed:50000,minimumFixed:32000},preferences:{location:'España',contract:'Indefinido',maxTrips:1},searchContext:{targetRoles:'Analista'},experience:'Ficticia'});
  const dom=groupedProfileDom(t);t.a.setScreenState('perfil');t.a.render();let writes=0;t.env.fetch=async()=>{writes++;throw Error('TEST no se debe guardar');};
  dom.field('currentCity').value='Cádiz';await t.dispatchMain('input',dom.field('currentCity'));dom.field(key).value=value;await t.dispatchMain('input',dom.field(key));
  assert.equal(await t.a.saveProfileChanges(),false);assert.equal(writes,0,key+'='+value);assert.equal(t.env.document.activeElement,dom.field(key));assert.equal(t.a.isDirty(),true);assert.equal(t.a.getModel().profile.currentCity,'Madrid');assert.equal(dom.field('currentCity').value,'Cádiz');assert.deepEqual(t.a.getModel().requests,[]);
 }
});

test('keeping personal values after a conflict still validates edits made while resolving it',async()=>{
 const t=setup();Object.assign(t.model,{profile:{currentCity:'Madrid',noticeDays:15},preferences:{location:'España',contract:'Indefinido',maxTrips:1},searchContext:{targetRoles:'Analista'},experience:'Ficticia'});const dom=groupedProfileDom(t),operations=[];t.a.setScreenState('perfil');t.a.render();
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;operations.push(operation);const state=structuredClone(t.a.getModel());state.revision++;if(operations.length===1){state.profile.currentCity='Sevilla';return {ok:false,status:409,json:async()=>({error:'TEST conflicto',state})};}return {ok:true,json:async()=>({state})};};
 dom.field('currentCity').value='Cádiz';await t.dispatchMain('input',dom.field('currentCity'));assert.equal(await t.a.saveProfileChanges(),false);const form=dom.forms.find(form=>form.dataset.form==='about');assert(form._conflict);
 dom.field('noticeDays').value='x'.repeat(301);await t.dispatchMain('input',dom.field('noticeDays'));const originalQuery=t.env.document.querySelector,dialog={returnValue:'cancel',showModal(){},addEventListener(name,handler){if(name==='close'){this.returnValue='ok';handler();}}};t.env.document.querySelector=selector=>selector==='#confirm'?dialog:originalQuery(selector);
 await t.click({dataset:{keep:'1'},form});assert.equal(operations.length,1);assert.equal(t.env.document.activeElement,dom.field('noticeDays'));assert.equal(dom.field('currentCity').value,'Cádiz');assert.equal(dom.field('noticeDays').value,'x'.repeat(301));assert.equal(t.a.getModel().profile.currentCity,'Sevilla');assert.equal(t.a.isDirty(),true);assert.deepEqual(t.a.getModel().requests,[]);
});

test('resolving a search conflict preserves the visible legacy zone and mode as a single saved choice',async()=>{
 for(const initial of [{location:'España',workMode:'Remoto',regions:'Portugal'},{location:'Remoto en España',workMode:'',regions:''}]){
  const t=setup();Object.assign(t.model,{searchContext:{targetRoles:'Analista',keywords:'SQL',workMode:initial.workMode,regions:initial.regions},preferences:{location:initial.location},experience:'Ficticia'});
  const dom=groupedProfileDom(t),operations=[];t.a.setScreenState('perfil');t.a.render();
  const field=dom.field(initial.regions?'location':'keywords');field.value=initial.regions?'España; Francia':'Power BI';await t.dispatchMain('input',field);
  t.env.fetch=async(_,options)=>{
   const operation=JSON.parse(options.body).operation;operations.push(operation);const state=structuredClone(t.a.getModel());state.revision++;
   if(operations.length===1){state.searchContext.keywords='Python';if(initial.regions)state.searchContext.regions='Alemania';return {ok:false,status:409,json:async()=>({error:'TEST conflicto',state})};}
   for(const [key,value] of Object.entries(operation.values)){if(key==='location')state.preferences.location=value;else state.searchContext[key]=value;}
   return {ok:true,json:async()=>({state})};
  };
  assert.equal(await t.a.saveProfileChanges(),false);const form=dom.forms.find(form=>form.dataset.form==='search');assert(form._conflict);
  const originalQuery=t.env.document.querySelector,dialog={returnValue:'cancel',showModal(){},addEventListener(name,handler){if(name==='close'){this.returnValue='ok';handler();}}};
  t.env.document.querySelector=selector=>selector==='#confirm'?dialog:originalQuery(selector);
  await t.click({dataset:{keep:'1'},form});assert.equal(operations.length,2);
  assert.equal(operations[1].values.location,initial.regions?'España; Francia':'España');assert.equal(operations[1].values.workMode,initial.regions?undefined:'Remoto');
  if(initial.regions){assert.equal(operations[1].values.regions,'');assert.equal(operations[1].expected.regions,'Alemania');assert.equal(t.a.getModel().searchContext.regions,'');}
  assert.equal(dom.field('location').value,initial.regions?'España; Francia':'España');assert.equal(dom.field('workMode').value,'Remoto');assert.equal(t.a.isDirty(),false);assert.deepEqual(t.a.getModel().requests,[]);
 }
});

test('editing form answers includes known optional questions and saves only the changed answer with its old expectation',async()=>{
 const t=setup(),field={key:'custom_optional',label:'Respuesta opcional ficticia',type:'text',scope:'opportunity'},job={id:'optional-offer',company:'Empresa ficticia',title:'Analista',state:'Preparar',apply:'Sí',requests:[],packages:[],questions:[],missing:['review'],selection:{selected:true,mode:'review'},draft:{requiredAnswers:[],questions:[field],formAnswerKeys:['custom_optional','unknown_field'],messageUsage:'unused'},answers:{custom_optional:'Respuesta anterior'},answerOverrides:{custom_optional:'Respuesta anterior'},conditions:{},fieldDefinitions:{custom_optional:field,currentCity:{label:'Ciudad',type:'text'},workPermitWithoutSponsorship:{label:'Permiso',type:'boolean'},salaryExpectationFixed:{label:'Salario',type:'number'}}};t.model.labels={custom_optional:field.label};t.model.opportunities=[job];t.a.setSelected(job.id);assert.match(t.a.detail(),/data-answers="optional-offer"[^>]*>Editar/);const dom=groupedProfileDom(t),operations=[];t.env.fetch=async(_,options)=>{if(!options.body)return {ok:true,json:async()=>t.a.getModel()};const operation=JSON.parse(options.body).operation;operations.push(operation);const state=structuredClone(t.a.getModel());state.revision++;state.opportunities[0].answers.custom_optional=operation.values.custom_optional;state.opportunities[0].answerOverrides.custom_optional=operation.values.custom_optional;return {ok:true,json:async()=>({state})};};await t.click({dataset:{answers:job.id}});for(let i=0;i<20&&!dom.field('custom_optional');i++)await Promise.resolve();assert.equal(t.a.getView().screen,'perfil');assert(dom.field('custom_optional'));assert.equal((dom.html.match(/name="custom_optional"/g)||[]).length,1);assert.doesNotMatch(dom.html,/name="unknown_field"/);dom.field('custom_optional').value='Respuesta corregida';await t.dispatchMain('input',dom.field('custom_optional'));await t.dispatch('keydown',dom.field('custom_optional'),{key:'s',ctrlKey:true});assert.equal(operations.length,1);assert.equal(operations[0].kind,'ui-responses');assert.equal(operations[0].opportunityId,job.id);assert.deepEqual(operations[0].values,{custom_optional:'Respuesta corregida'});assert.deepEqual(operations[0].expected,{custom_optional:'Respuesta anterior'});assert.equal(t.a.getView().screen,'detalle');assert.match(dom.html,/Respuesta corregida/);assert.deepEqual(t.a.getModel().requests,[]);
});
test('table marks are independent of applications, show compatible counts and clear when changing state',async()=>{
 const t=setup(),base={state:'Investigar',apply:'Sí, aclarar',title:'Analista',requests:[],packages:[],questions:[],missing:['CV'],draft:{answers:{}},answers:{},answerOverrides:{}};
 const one={...base,id:'one',company:'Uno'},two={...base,id:'two',company:'Dos'};t.model.opportunities=[one,two];
 assert.doesNotMatch(t.a.applyPage(),/ofertas marcadas/);
 await t.click({dataset:{bulkMode:'1'}});
 const mark=id=>({dataset:{bulkSelect:id},checked:true});await t.dispatch('change',mark('one'));await t.dispatch('change',mark('two'));
 assert.deepEqual([...t.a.getTableSelection()],['one','two']);assert.equal(one.selection,undefined);
 let html=t.a.applyPage();assert.match(html,/2 ofertas marcadas/);assert.match(html,/data-bulk-action="select-review"/);assert.match(html,/data-bulk-action="select-auto"/);assert.match(html,/data-bulk-action="discard"/);assert.doesNotMatch(html,/data-select="one"/);
 two.requests=[{type:'review',status:'queued'}];html=t.a.applyPage();assert.match(html,/data-icon="eye"[\s\S]*?<\/svg><\/span>Solicitar con revisión \(1\)/);assert.match(html,/data-icon="bot"[\s\S]*?<\/svg><\/span>Auto-solicitud \(1\)/);assert.equal((html.match(/class="primary request-button"/g)||[]).length,2);assert.match(html,/>Descartar \(2\)<\/button>/);assert.match(html,/Alcance: 1 de 2 ofertas marcadas/);assert.doesNotMatch(html,/pasos distintos|bulk-more/);
 await t.click({dataset:{flowFilter:'sin-elegir',filterTab:'solicitar'}});assert.equal(t.a.getTableSelection().size,0);
});

test('table selection is opt-in and exiting removes every mark without choosing any offer',async()=>{
 const t=setup(),base={title:'Analista',state:'Investigar',apply:'Sí, aclarar',requests:[],packages:[],questions:[],missing:[]};t.model.opportunities=[{...base,id:'one',company:'Uno'},{...base,id:'two',company:'Dos'}];const before=structuredClone(t.model);
 let html=t.a.applyPage();assert.match(html,/data-bulk-mode="1"[^>]*>Seleccionar varias/);assert.doesNotMatch(html,/data-bulk-select|id="bulk-all"|type="checkbox"/);
 await t.dispatch('change',{dataset:{bulkSelect:'one'},checked:true});assert.equal(t.a.getTableSelection().size,0);
 await t.click({dataset:{bulkMode:'1'}});html=t.a.applyPage();assert.equal((html.match(/data-bulk-select="/g)||[]).length,2);assert.match(html,/data-bulk-select-all/);assert.match(html,/Salir de la selección múltiple/);
 assert.match(html,/<thead><tr><th scope="col" class="selection-cell">[\s\S]*?id="bulk-all"/);
 for(const row of html.split('<tbody>')[1].split('</tbody>')[0].match(/<tr[\s\S]*?<\/tr>/g)||[]){assert.match(row,/<tr[^>]*><td class="selection-cell">[\s\S]*?data-bulk-select=/);assert.doesNotMatch(row.match(/<td class="company-cell">[\s\S]*?<\/td>/)[0],/type="checkbox"/);}
 assert.match(html,/workflow-table-selectable/);
 await t.dispatch('change',{dataset:{bulkSelect:'one'},checked:true});assert.match(t.a.applyPage(),/Descartar \(1\)/);assert.deepEqual(t.model,before);
 t.a.setSelected('one');t.a.setSelected(null);assert.match(t.a.applyPage(),/data-bulk-select="one"[^>]*checked/);
 await t.click({dataset:{bulkClear:'1'}});html=t.a.applyPage();assert.equal(t.a.getTableSelection().size,0);assert.doesNotMatch(html,/data-bulk-select|id="bulk-all"|Descartar \(/);assert.match(html,/Seleccionar varias/);assert.deepEqual(t.model,before);
});
test('mark clicks do not open the case and all-visible marks have a native partial state',async()=>{
 const t=setup();await t.click({dataset:{bulkMode:'1'}});await t.click({dataset:{bulkSelect:'one'},tagName:'INPUT'});assert.equal(t.a.getView().selected,null);
 const rows=[{dataset:{bulkSelect:'one'},checked:false},{dataset:{bulkSelect:'two'},checked:false}],main=t.env.document.querySelector('#main');main.querySelectorAll=s=>s==='[data-bulk-select]'?rows:[];
 await t.dispatch('change',{dataset:{bulkSelectAll:'1'},checked:true});assert.deepEqual([...t.a.getTableSelection()],['one','two']);
 await t.dispatch('change',{dataset:{bulkSelectAll:'1'},checked:false});assert.equal(t.a.getTableSelection().size,0);
});
test('group actions make one explicit atomic request and preserve the marks on failure',async()=>{
 const t=setup(),base={state:'Investigar',apply:'Sí',title:'Analista',requests:[],packages:[],questions:[],missing:['CV'],draft:{answers:{}}};t.model.opportunities=[{...base,id:'one',company:'Uno'},{...base,id:'two',company:'Dos'}];t.a.getTableSelection().add('one');t.a.getTableSelection().add('two');let calls=[];
 t.env.fetch=async(path,options)=>{calls.push(JSON.parse(options.body));return {ok:false,status:409,json:async()=>({error:'Cambió una oferta',state:t.model})};};assert.equal(await t.a.bulkAction('select-auto'),false);assert.equal(t.a.getTableSelection().size,2);assert.equal(calls.length,1);assert.equal(calls[0].operation.action,'select-auto');assert.deepEqual(calls[0].operation.targets.map(x=>x.id),['one','two']);
 t.env.fetch=async(path,options)=>({ok:true,status:200,json:async()=>({ok:true,state:t.model})});assert.equal(await t.a.bulkAction('archive'),true);assert.equal(t.a.getTableSelection().size,0);
});
test('archived offers preserve unconfirmed send recovery and block renewed choices',()=>{
 const t=setup(),job={id:'one',company:'Uno',title:'Analista',state:'Preparar',archivedAt:'2026-10-05T00:00:00Z',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};t.model.opportunities=[job];assert.equal(UI.offerState(job).key,'descartadas');assert.equal(UI.canChoose(job),false);assert.equal(t.a.bulkOptions(job).length,0);
 job.requests=[{id:'uncertain',type:'send',status:'blocked',startedAt:'2026-10-05T00:00:00Z',packageId:'original'}];assert.equal(UI.offerState(job).key,'atencion');assert.equal(UI.step(job).action,'recovery');assert.match(t.a.bulkOptions(job)[0][0],/^recovery:/);
});
test('group review displays every frozen package and disables the single authorization when one changes',()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Preparar',fingerprint:'pack',selection:{selected:true,mode:'review'},requests:[],questions:[],missing:[],packages:[{id:'pack',isCurrent:true,cvUrl:'/cv',payload:{messageUsage:'unused',recipient:'https://example.org/apply',answers:{}}}],draft:{},answers:{}};const jobs=[{...base,id:'one'},{...base,id:'two',company:'Segunda'}];t.model.opportunities=jobs;t.a.setBulkReview(structuredClone(jobs));let html=t.a.bulkReviewPage();assert.match(html,/Empresa · Analista/);assert.match(html,/Segunda · Analista/);assert.equal((html.match(/class="authorization"/g)||[]).length,1);assert.match(html,/Autorizar 2 envíos/);assert.doesNotMatch(html,/data-approve="/);
 jobs[1].fingerprint='changed';html=t.a.bulkReviewPage();assert.match(html,/data-bulk-approve="1" disabled/);
});
test('group review loads the full materials only for marked cases before freezing their packages',async()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Preparar',fingerprint:'pack',selection:{selected:true,mode:'review'},requests:[],questions:[],missing:[],packages:[{id:'pack',isCurrent:true,cvUrl:'/cv'}]};
 t.model.opportunities=[{...base,id:'one'},{...base,id:'two'}];t.a.getTableSelection().add('one');t.a.getTableSelection().add('two');const calls=[];
 const full=structuredClone(t.model);for(const j of full.opportunities){j.draft={};j.answers={};j.packages[0].payload={messageUsage:'unused',recipient:'https://example.org/apply',answers:{}};}
 t.env.fetch=async(path)=>{calls.push(path);return {ok:true,json:async()=>full};};
 assert.equal(await t.a.bulkAction('review'),true);assert.equal(t.a.getView().screen,'revision-multiple');assert.match(t.a.bulkReviewPage(),/Autorizar 2 envíos/);assert(calls.every(path=>path.includes('brief=1')&&path.includes('case=one')&&path.includes('case=two')));
});
test('group answers deduplicate shared questions and retain specific answer scope and drafts',async()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Pendiente de ti',fingerprint:'v',selection:{selected:true,mode:'review'},requests:[],packages:[],missing:['Respuestas'],questions:[{key:'currentCity'},{key:'custom_tool'}],draft:{},answerOverrides:{},answers:{currentCity:null,custom_tool:null},fieldDefinitions:{currentCity:{label:'Ciudad',type:'text',scope:'global'},custom_tool:{label:'Herramienta',type:'text',scope:'opportunity'}}};t.model.opportunities=[{...base,id:'one'},{...base,id:'two'}];t.a.getTableSelection().add('one');t.a.getTableSelection().add('two');t.a.refresh=async()=>{};t.env.fetch=async()=>({ok:true,status:200,json:async()=>t.model});
 assert.equal(await t.a.bulkAction('responses'),true);assert.equal(t.a.getView().screen,'edicion-multiple');let html=t.a.bulkEditorPage();assert.equal((html.match(/name="global:currentCity"/g)||[]).length,1);assert.match(html,/name="offer-0:custom_tool"/);assert.match(html,/name="offer-1:custom_tool"/);
 const form={dataset:{bulkForm:'1'}},input={dataset:{},name:'global:currentCity',value:'Ciudad ficticia',form};await t.dispatchMain('input',input);assert.equal(t.a.getBulkEditor().values['global:currentCity'],'Ciudad ficticia');assert(t.a.isDirty());assert.match(t.a.bulkEditorPage(),/Ciudad ficticia/);
});

test('group editor heading escapes company names from offers',async()=>{
 const t=setup(),base={title:'Analista',state:'Pendiente de ti',fingerprint:'v',selection:{selected:true,mode:'review'},requests:[],packages:[],missing:['Respuestas'],questions:[{key:'currentCity'}],draft:{},answerOverrides:{},answers:{currentCity:null},fieldDefinitions:{currentCity:{label:'Ciudad',type:'text',scope:'global'}}};t.model.opportunities=[{...base,id:'one',company:'<img src=x data-undo="u">'},{...base,id:'two',company:'AT&T "Uno"'}];t.a.getTableSelection().add('one');t.a.getTableSelection().add('two');t.a.refresh=async()=>{};t.env.fetch=async()=>({ok:true,status:200,json:async()=>t.model});
 assert.equal(await t.a.bulkAction('responses'),true);const html=t.a.bulkEditorPage();assert.doesNotMatch(html,/<img/);assert.match(html,/&lt;img src=x data-undo=&quot;u&quot;&gt; · AT&amp;T &quot;Uno&quot;/);
});

test('partial group action uses the displayed scope and leaves incompatible marks untouched',async()=>{
 const t=setup(),base={state:'Investigar',apply:'Sí',title:'Analista',requests:[],packages:[],questions:[],missing:['CV'],draft:{}};
 t.model.opportunities=[{...base,id:'one',company:'Uno'},{...base,id:'two',company:'Dos',requests:[{type:'review',status:'queued'}]},{...base,id:'three',company:'Tres',requests:[{type:'review',status:'queued'}]}];
 ['one','two','three'].forEach(id=>t.a.getTableSelection().add(id));const html=t.a.bulkToolbar();assert.match(html,/data-icon="eye"[\s\S]*?<\/svg><\/span>Solicitar con revisión \(1\)/);assert.match(html,/Alcance: 1 de 3 ofertas marcadas/);assert.match(html,/data-bulk-targets="\[&quot;one&quot;\]"/);
 // A later change must not silently widen the exact scope of the clicked button.
 t.model.opportunities[1].requests=[];const operations=[];t.env.fetch=async(_,options)=>{operations.push(JSON.parse(options.body).operation);return {ok:true,json:async()=>({state:t.model})};};
 await t.click({dataset:{bulkAction:'select-review',bulkTargets:'["one"]',bulkTotal:'3'}});
 assert.deepEqual(operations[0].targets,[{id:'one'}]);assert.deepEqual([...t.a.getTableSelection()],['two','three']);assert.match(t.env.document.querySelector('#toast').innerHTML,/Aplicado a 1 oferta; 2 sin cambios/);assert.match(t.env.document.querySelector('#toast').innerHTML,/Continúa con Stubbs Jobs[\s\S]*chat del agente/);
});

test('a changed member of the displayed subset blocks the action without dropping marks',async()=>{
 const t=setup(),base={state:'Investigar',apply:'Sí',title:'Analista',requests:[],packages:[],questions:[],missing:['CV']};t.model.opportunities=[{...base,id:'one',company:'Uno'},{...base,id:'two',company:'Dos'}];
 ['one','two'].forEach(id=>t.a.getTableSelection().add(id));t.model.opportunities[0].requests=[{type:'review',status:'queued'}];let calls=0;t.env.fetch=async()=>{calls++;throw Error('Must not write');};
 await assert.rejects(t.a.bulkAction('select-review',['one'],2),/Cambió una/);assert.equal(calls,0);assert.equal(t.a.getTableSelection().size,2);
});

test('mixed actions show every compatible control directly with compact counts and accessible scope',()=>{
 const t=setup(),base={title:'Analista',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};
 t.model.opportunities=[{...base,id:'choose',company:'Uno',state:'Investigar',apply:'Sí'},{...base,id:'respond',company:'Dos',state:'Pendiente de ti',selection:{selected:true,mode:'review'},questions:[{key:'custom_question'}],missing:['Respuestas']}];
 ['choose','respond'].forEach(id=>t.a.getTableSelection().add(id));const html=t.a.bulkToolbar();assert.doesNotMatch(html,/<details|Más acciones|bulk-more/);assert.match(html,/>Responder \(1\)<\/button>/);assert.match(html,/>Retirar selección \(1\)<\/button>/);assert.equal((html.match(/class="primary request-button"/g)||[]).length,2);assert.match(html,/>Descartar \(1\)<\/button>/);assert.match(html,/aria-label="Responder \(1\)\. Alcance: 1 de 2 ofertas marcadas\."/);
});

test('partial joint authorization keeps unreviewed cases marked and loads only eligible packages',async()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Preparar',fingerprint:'pack',selection:{selected:true,mode:'review'},requests:[],questions:[],missing:[],packages:[{id:'pack',isCurrent:true,cvUrl:'/cv',payload:{messageUsage:'unused',recipient:'https://example.org/apply',answers:{}}}],draft:{},answers:{}};
 t.model.opportunities=[{...base,id:'one'},{...base,id:'two',packages:[],requests:[{type:'prepare',status:'queued'}]}];['one','two'].forEach(id=>t.a.getTableSelection().add(id));const calls=[];
 t.env.fetch=async(path,options)=>{calls.push({path,operation:options?.body?JSON.parse(options.body).operation:null});return {ok:true,json:async()=>options?.body?{state:t.model}:t.model};};
 await t.a.bulkAction('review');assert.equal(t.a.getView().screen,'revision-multiple');assert.match(t.a.bulkReviewPage(),/Autorizar 1 envío/);assert(calls.every(c=>c.path.includes('case=one')&&!c.path.includes('case=two')));
 await t.click({dataset:{bulkApprove:'1'}});assert.deepEqual(calls.find(c=>c.operation)?.operation.targets,[{id:'one',fingerprint:'pack'}]);assert.deepEqual([...t.a.getTableSelection()],['two']);
});

test('saving partial specific answers preserves marks outside the submitted scope',async()=>{
 const t=setup(),base={company:'Empresa',title:'Analista',state:'Pendiente de ti',fingerprint:'v',selection:{selected:true,mode:'review'},requests:[],packages:[],missing:['Respuestas'],questions:[{key:'custom_tool'}],draft:{},answerOverrides:{},answers:{custom_tool:null},fieldDefinitions:{custom_tool:{label:'Herramienta',type:'text',scope:'opportunity'}}};
 t.model.opportunities=[{...base,id:'one'},{...base,id:'two',requests:[{type:'prepare',status:'queued'}],questions:[],missing:[]}];['one','two'].forEach(id=>t.a.getTableSelection().add(id));const calls=[];
 t.env.fetch=async(_,options)=>{if(options?.body)calls.push(JSON.parse(options.body).operation);return {ok:true,json:async()=>options?.body?{state:t.model}:t.model};};
 await t.a.bulkAction('responses');await t.a.saveBulkEditor({values:{'offer-0:custom_tool':'SQL'},elements:[]});assert.deepEqual(calls[0].targets,[{id:'one',fingerprint:'v',values:{custom_tool:'SQL'},expected:{custom_tool:null}}]);assert.deepEqual([...t.a.getTableSelection()],['two']);
});

test('offer tour freezes the filtered order despite status changes and returns directly to the table',async()=>{
 const t=setup(),base={state:'Investigar',apply:'Sí',title:'Analista',requests:[],packages:[],questions:[],missing:['CV'],draft:{},answers:{}};
 t.model.opportunities=[{...base,id:'a',company:'Alpha'},{...base,id:'b',company:'Beta'},{...base,id:'c',company:'Gamma'}];t.env.fetch=async()=>({ok:true,json:async()=>t.model});
 t.a.setFlowFilter('solicitar','sin-elegir');t.a.setTableSort('solicitar','company',-1);t.a.setTableFilter('solicitar','company',['Alpha','Beta']);await t.a.setScreen('solicitar');await t.a.setScreen('detalle','b');assert.deepEqual([...t.a.offerTourIds()],['b','a']);assert.match(t.a.detail(),/1 \/ 2/);
 t.model.opportunities[0].state='Cerrada';await t.click({dataset:{offerMove:'1'}});assert.equal(t.a.getView().selected,'a');assert.deepEqual([...t.a.offerTourIds()],['b','a']);assert.equal(t.a.backDestination().page,'solicitar');assert.match(t.a.detail(),/data-offer-move="1"[^>]*disabled/);
 await t.a.goBack();assert.equal(t.a.getView().screen,'solicitar');assert.equal(t.a.getTableState().direction,-1);assert.deepEqual([...t.a.getTableState().filters.company],['Alpha','Beta']);
 // Browser forward must recover the original tour even if the case left its filter.
 await t.a.setScreen('detalle','a',false);assert.deepEqual([...t.a.offerTourIds()],['b','a']);assert.equal(t.a.getView().selected,'a');
});

test('tour can restrict navigation to marked offers and includes historical cases',async()=>{
 const t=setup(),base={state:'Investigar',apply:'Sí',title:'Analista',requests:[],packages:[],questions:[],missing:['CV'],draft:{},answers:{}};
 t.model.opportunities=[{...base,id:'a',company:'Alpha'},{...base,id:'b',company:'Beta'},{...base,id:'c',company:'Gamma'}];t.env.fetch=async()=>({ok:true,json:async()=>t.model});await t.a.setScreen('solicitar');['a','c'].forEach(id=>t.a.getTableSelection().add(id));await t.a.setScreen('detalle','a');assert.deepEqual([...t.a.offerTourIds()],['a','c']);assert.equal(t.a.getOfferTour().scope,'Ofertas marcadas');await t.a.moveOffer(1);assert.equal(t.a.getView().selected,'c');await t.a.moveOffer(1);assert.equal(t.a.getView().selected,'c');
 await t.a.setScreen('solicitar');await t.a.setScreen('detalle','b');assert.equal(t.a.offerTourIds().length,3);
 await t.a.goBack();t.model.historical=[{id:'older',company:'Anterior',title:'Analista',state:'Rechazada',category:'Laboral'}];t.a.applyPage();await t.a.setScreen('detalle','historical:older');assert.equal(t.a.offerTourIds().length,4);assert.match(t.a.detail(),/class="offer-heading"/);assert.match(t.a.detail(),/Recorrer ofertas filtradas/);assert.equal(t.a.backDestination().page,'solicitar');
});

test('sibling navigation restores the semantic form section below the sticky header',async()=>{
 const t=setup(),base={state:'Investigar',apply:'Sí',title:'Analista',requests:[],packages:[],questions:[],missing:['CV'],draft:{},answers:{}};
 t.model.opportunities=[{...base,id:'a',company:'Alpha'},{...base,id:'b',company:'Beta'}];t.env.fetch=async()=>({ok:true,json:async()=>t.model});await t.a.setScreen('solicitar');await t.a.setScreen('detalle','a');
 const main=t.env.document.querySelector('#main'),prior=main.querySelector,header={getBoundingClientRect:()=>({bottom:170,height:110})},form={dataset:{offerSection:'form'},getBoundingClientRect:()=>({top:200,bottom:500})};main.querySelector=s=>s==='.offer-heading'?header:s==='[data-offer-section="form"]'?form:prior(s);main.querySelectorAll=s=>s==='[data-offer-section]'?[form]:[];const previous=t.env.document.querySelector;t.env.document.querySelector=s=>s==='.site-header'?{getBoundingClientRect:()=>({height:60})}:previous(s);t.env.window.scrollY=300;let scroll;t.env.window.scrollTo=options=>{scroll=options.top;};
 // A tall, static side panel precedes the form in the DOM but must not steal its reading position.
 const conditions={dataset:{offerSection:'conditions'},getBoundingClientRect:()=>({top:-200,bottom:900})},rail={contains:section=>section===conditions};
 const queryWithHeader=main.querySelector;main.querySelector=s=>s==='.offer-rail'?rail:queryWithHeader(s);main.querySelectorAll=s=>s==='[data-offer-section]'?[conditions,form]:[];
 t.env.window.getComputedStyle=()=>({position:'static',gridColumnStart:'2'});
 assert.equal(t.a.captureOfferSection(),'form');await t.a.moveOffer(1);assert.equal(scroll,314);assert.equal(t.a.getView().selected,'b');assert.equal(t.a.backDestination().page,'solicitar');
});


test('backups replaces Help without a frame or onboarding guide and keeps recovery actions',()=>{
 const t=setup(),html=t.a.backupsPage();assert.match(html,/<h1>Copias de seguridad<\/h1>/);assert.match(html,/class="backup-content recovery-panel"/);
 assert.doesNotMatch(html,/class="panel recovery-panel"|settings-help|guide-steps|Empieza con Stubbs Jobs|data-copy-setup/);
 assert.match(html,/Crear copia de seguridad/);assert.match(html,/Recuperar una copia/);assert.match(html,/carpeta aparte/);
});

test('offer notes use their saved scope and can be recovered from backups without changing a form',()=>{
 const t=setup(),job={id:'one',company:'TEST Empresa',notes:'TEST saved note',answers:{currentCity:'TEST City'},requests:[],packages:[]};t.model.opportunities=[job];t.a.setSelected('one');
 assert.deepEqual(JSON.parse(JSON.stringify(t.a.formSource('offer-note'))),{'Notas de seguimiento':'TEST saved note'});
 const key='stubbs_jobs-draft:detalle:one';t.storage.set(key,JSON.stringify({values:{'Notas de seguimiento':'TEST new note'},shown:{'Notas de seguimiento':'TEST saved note'},expected:{'Notas de seguimiento':'TEST saved note'}}));
 const item=t.a.backupDrafts().find(d=>d.key===key);assert.equal(item.page,'detalle');assert.equal(item.id,'one');assert.match(item.label,/Nota de seguimiento/);
 assert.match(t.a.backupsPage(),/data-backup-draft="stubbs_jobs-draft:detalle:one"/);assert.equal(job.notes,'TEST saved note');
});

test('desktop offers page uses counted segments, a heading action and Escape to leave multi-select',async()=>{
 const t=setup(),base={title:'ANALISTA DE DATOS SENIOR',state:'Investigar',apply:'Sí, aclarar',requests:[],packages:[],questions:[],missing:[]};
 let html=t.a.applyPage();assert.match(html,/class="offers-heading"><div><h1>Ofertas<\/h1>[\s\S]*?<\/div><button class="primary offers-add" data-screen="nueva">/);assert.doesNotMatch(html,/data-bulk-mode/);
 t.model.opportunities=[{...base,id:'one',company:'TECDATA ENGINEERING'},{...base,id:'two',company:'IBM'}];const before=structuredClone(t.model);
 html=t.a.applyPage();assert.match(html,/data-flow-filter="todas"[^>]*>Todas <span class="filter-count">2<\/span><\/button>/);assert.match(html,/data-bulk-mode="1"[^>]*>Seleccionar varias/);
 assert.match(html,/<span class="company-name">Tecdata Engineering<\/span>/);assert.match(html,/<span class="company-name">IBM<\/span>/);assert.match(html,/<td title="ANALISTA DE DATOS SENIOR"><span class="offer-title-text">Analista de Datos Senior<\/span>/);
 assert.equal((html.match(/data-screen="nueva"/g)||[]).length,1);
 await t.click({dataset:{bulkMode:'1'}});await t.dispatch('change',{dataset:{bulkSelect:'one'},checked:true});assert.equal(t.a.getTableSelection().size,1);
 const toolbar=t.a.bulkToolbar(),review=toolbar.indexOf('data-bulk-action="select-review"'),auto=toolbar.indexOf('data-bulk-action="select-auto"'),discard=toolbar.indexOf('data-bulk-action="discard"');
 assert(review>=0&&auto>review&&discard>auto,'both request modes sit together before secondary actions');assert.doesNotMatch(toolbar,/<button class="primary" data-bulk-action="discard"/);
 await t.dispatch('keydown',{},{key:'Escape'});html=t.a.applyPage();assert.equal(t.a.getTableSelection().size,0);assert.doesNotMatch(html,/data-bulk-select=/);assert.match(html,/Seleccionar varias/);assert.deepEqual(t.model,before);
});

test('display case only normalises names published entirely in capitals',()=>{
 const F=require('../app/formatting.js');
 assert.equal(F.displayCase('ALVEA SOLUCIONES TECNOLOGICAS, S.L.'),'Alvea Soluciones Tecnologicas, S.L.');
 assert.equal(F.displayCase('DESARROLLADOR/A POWER BI + MICROSOFT FABRIC'),'Desarrollador/a Power BI + Microsoft Fabric');
 assert.equal(F.displayCase('EL CORTE INGLÉS'),'El Corte Inglés');
 for(const kept of ['IBM','KPMG','SAP SE','knowmad mood','Data visualization engineer POWER BI con Inglés','',null])assert.equal(F.displayCase(kept),kept??'');
});

test('desktop ficha keeps decision and conditions in one rail beside the reading column',()=>{
 const t=setup(),job={id:'one',company:'Empresa',title:'Analista',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{formAnswerKeys:['salaryExpectationFixed']},answers:{salaryExpectationFixed:35000}};
 t.model.opportunities=[job];t.model.labels={salaryExpectationFixed:'Salario esperado'};t.a.setSelected('one');const html=t.a.detail();
 const rail=html.slice(html.indexOf('<aside class="offer-rail"'),html.indexOf('</aside>'));
 assert.match(rail,/data-offer-section="status"/);assert.match(rail,/<h2>Condiciones<\/h2>/);assert.doesNotMatch(rail,/Formulario de solicitud|<h2>Actividad<\/h2>/);
 assert(html.indexOf('</aside>')<html.indexOf('data-offer-section="form"'));assert.doesNotMatch(html,/class="offer-overview"[^>]*><\/div>/);
 assert.match(html,/<article class="cv-card case-cv-card" aria-label="CV para la oferta" data-cv-state="pending">/);assert.match(html,/<dd>35\.000<\/dd>/);
});

test('numeric answers and Resumen days read naturally on screen',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa A'}];
 t.model.requests=[{id:'sent-a',type:'send',opportunityId:'one',status:'done',updatedAt:'2026-09-28T10:00:00Z',summary:'Confirmación A'},{id:'search',type:'discovery',status:'done',updatedAt:new Date().toISOString(),summary:'Tres ofertas.',activityResult:{newOfferCount:3,health:[],publicSources:[]}}];
 const html=t.a.agentPage();assert.match(html,/<time datetime="2026-09-28">28 sept<\/time><span class="activity-weekday">Lunes<\/span>/);assert.match(html,/<time datetime="[\d-]+">Hoy<\/time><span class="activity-weekday">[A-ZÁÉÍÓÚ][a-záéíóú]+, \d{1,2} [a-z]+\.?<\/span>/);
});

test('Summary shows only requested checks, not overdue orientation dates as agent obligations',()=>{
 const t=setup();t.model.opportunities=[{id:'one',company:'Empresa ficticia',state:'Enviada',sent:{at:'2026-01-01'},lifecycle:{nextCheckAt:'2026-01-08T10:00:00Z'}}];const before=structuredClone(t.model);
 const html=t.a.agentPage();assert.doesNotMatch(html,/Revisiones pendientes del agente|Comprobar tu candidatura|Estas fechas han vencido/);assert.deepEqual(t.model,before);
 t.model.requests=[{id:'check',opportunityId:'one',type:'investigate',purpose:'followup',status:'queued',summary:'Comprobar tu candidatura',createdAt:'2026-10-07T10:00:00Z'}];assert.match(t.a.agentPage(),/Comprobar tu candidatura/);
});
function effectDialog(t,{ok,check=false}){
 const parts={'#criteria-effect-intro':{textContent:''},'#criteria-effect-list':{innerHTML:''},'#criteria-effect-keep':{textContent:'',hidden:true}},input={checked:false};
 const box={hidden:true,querySelector(s){return s==='input'?input:(parts[s]||(parts[s]={textContent:''}));}};parts['#criteria-effect-rounds']=box;
 let close;const dialog={returnValue:'',shown:0,querySelector:s=>parts[s],addEventListener(_,handler){close=handler;},showModal(){this.shown++;if(check)input.checked=!box.hidden;this.returnValue=ok?'ok':'cancel';queueMicrotask(()=>close());}};
 const original=t.env.document.querySelector;t.env.document.querySelector=s=>s==='#criteria-effect'?dialog:original(s);
 return {dialog,parts,box};
}
test('saving criteria first states their effect on current offers and cancelling keeps the edit unsaved',async()=>{
 const t=setup(),{forms}=profileFixture(t),steps=[],previews=[],{dialog,parts}=effectDialog(t,{ok:false});
 t.env.criteriaPreview=body=>{previews.push(body);return {toEligible:[],toDiscarded:['a','b'],assessments:['a'],fitReviews:[],packages:[],authorizedPackages:[],excluded:[]};};
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;steps.push(operation.section||operation.kind);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};
 assert.equal(await t.a.saveProfileChanges(),false);
 assert.deepEqual(previews,[{values:{targetRoles:'Analista'}}]);assert.equal(dialog.shown,1);
 assert.match(parts['#criteria-effect-list'].innerHTML,/2 ofertas pasarán a descartadas[\s\S]*La valoración de 1 oferta/);
 assert.deepEqual(steps,['about','ui-experience']);assert.equal(forms[2]._dirty,true);assert.equal(forms[3]._dirty,true);
 assert.match(t.env.document.querySelector('#toast').innerHTML,/No se han guardado tus criterios/);
});
test('offers of earlier rounds move to the saved criteria only when the person ticks it',async()=>{
 const t=setup(),{forms}=profileFixture(t),steps=[],previews=[],{box}=effectDialog(t,{ok:true,check:true});
 t.a.acceptState({...t.a.getModel(),opportunities:[{id:'old',company:'Ronda anterior',title:'Analista',criteriaScope:'round',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}}]});
 t.env.criteriaPreview=body=>{previews.push(body);return {toEligible:body.mode?['old']:[],toDiscarded:[],assessments:[],fitReviews:[],packages:[],authorizedPackages:[],excluded:[]};};
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;steps.push(operation);return {ok:true,json:async()=>({state:{...t.a.getModel(),revision:t.a.getModel().revision+1}})};};
 assert.equal(await t.a.saveProfileChanges(),true);
 assert.deepEqual(previews[1],{values:{targetRoles:'Analista'},mode:'current',targets:[{id:'old'}]});assert.equal(box.hidden,false);
 assert.deepEqual(steps.map(op=>op.section||op.kind),['about','ui-experience','search','ui-criteria-scope','sources']);
 const scope=steps[3];assert.deepEqual(scope.targets,[{id:'old'}]);assert.equal(scope.mode,'current');assert.equal(scope.expectedRevision,3);
 assert.equal(forms.some(form=>form._dirty),false);
});

function strategyFixture(t){
 const make=(id,name,role,minimum,currency)=>({id,name,revision:1,archivedAt:null,searchContext:{targetRoles:role,keywords:'',searchPriorities:'Mañana',searchNotes:'TEST indicaciones',regions:'',workMode:'Remoto',onsiteLocations:'',currency,sourceUrls:'',platforms:''},criteria:{contract:'Indefinido',location:'España',maxTrips:1,minimumFixed:minimum}});
 t.a.acceptState({...t.a.getModel(),experience:'TEST experiencia',profile:{salaryExpectationFixed:35000,salaryCurrency:'EUR'},searchContext:{languages:'TEST Inglés',previousApplications:'TEST Empresa'},searchProfiles:[make('search-current','BI remoto','Analista BI',30000,'EUR'),make('search-two','Técnicos','Técnico',50000,'USD')],defaultSearchProfileId:'search-current'});
 t.a.setScreenState('perfil');const dom=groupedProfileDom(t);t.a.render();return dom;
}

test('search strategy switching is read-only and restores independent drafts without duplicating shared experience',async()=>{
 const t=setup(),dom=strategyFixture(t),before=structuredClone(t.a.getModel());
 t.env.fetch=async()=>{throw Error('Switching a strategy must be local');};
 dom.field('targetRoles').value='TEST edición BI';await t.dispatchMain('input',dom.field('targetRoles'));
 assert(t.storage.has('stubbs_jobs-draft:busqueda:profile:search-current'));
 await t.dispatchMain('change',{dataset:{searchProfile:'1'},value:'search-two'});
 assert.equal(dom.field('targetRoles').value,'Técnico');assert.equal(dom.field('minimumFixed').value,'50000');
 assert.match(dom.html,/<span data-salary-currency="1">EUR<\/span>/);assert.equal(dom.field('text').value,'TEST experiencia');
 dom.field('targetRoles').value='TEST edición técnicos';await t.dispatchMain('input',dom.field('targetRoles'));
 assert(t.storage.has('stubbs_jobs-draft:busqueda:profile:search-two'));
 await t.dispatchMain('change',{dataset:{searchProfile:'1'},value:'search-current'});
 assert.equal(dom.field('targetRoles').value,'TEST edición BI');assert.equal(dom.field('minimumFixed').value,'30000');
 assert.deepEqual(t.a.getModel(),before);
 const drafts=t.a.backupDrafts();assert.equal(drafts.length,2);assert(drafts.some(d=>d.searchProfileId==='search-two'&&d.label.includes('Técnicos')));
 assert.equal((dom.html.match(/<form data-form=/g)||[]).length,4);
});

test('saving a nondefault strategy keeps its stable identifier in preview, operation and durable attempt',async()=>{
 const t=setup(),dom=strategyFixture(t),operations=[],previews=[];
 await t.dispatchMain('change',{dataset:{searchProfile:'1'},value:'search-two'});
 dom.field('targetRoles').value='TEST técnico QA';await t.dispatchMain('input',dom.field('targetRoles'));
 t.env.criteriaPreview=body=>{previews.push(body);return {revision:t.a.getModel().revision};};
 t.env.fetch=async(_,options)=>{const operation=JSON.parse(options.body).operation;operations.push(operation);const state=structuredClone(t.a.getModel());state.revision++;state.searchProfiles.find(p=>p.id===operation.searchProfileId).searchContext.targetRoles=operation.values.targetRoles;return {ok:true,json:async()=>({state})};};
 assert.equal(await t.a.saveProfileChanges(),true);
 assert.equal(operations.length,1);assert.equal(operations[0].searchProfileId,'search-two');assert.equal(operations[0].expected.targetRoles,'Técnico');assert.equal(operations[0].expectedRevision,0);
 assert.equal(previews[0].searchProfileId,'search-two');assert.equal(t.a.getModel().defaultSearchProfileId,'search-current');
 assert.equal(t.a.getModel().searchProfiles[0].searchContext.targetRoles,'Analista BI');
 assert(!t.storage.has('stubbs_jobs-draft:busqueda:profile:search-two'));
});

test('filtering a strategy shows a shared vacancy once, preserves the nine columns and never changes permission',async()=>{
 const t=setup();strategyFixture(t);const base={title:'TEST oferta',state:'Investigar',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};
 const model=t.a.getModel();model.opportunities=[{...base,id:'shared',company:'TEST compartida',searchProfileIds:['search-current','search-two']},{...base,id:'first',company:'TEST solo BI',searchProfileIds:['search-current']}];const before=structuredClone(model);
 t.a.setScreenState('solicitar');await t.dispatchMain('change',{dataset:{offerProfile:'1'},value:'search-two'});
 const html=t.a.applyPage();assert.equal((html.match(/data-job-row="shared"/g)||[]).length,1);assert.doesNotMatch(html,/data-job-row="first"/);assert.equal((html.match(/class="column-title"/g)||[]).length,9);assert.deepEqual(t.a.getModel(),before);
});

test('a criteria edit only proposes previous rounds from its own search profile',async()=>{
 const t=setup(),dom=strategyFixture(t),previews=[],base={title:'TEST',state:'Investigar',criteriaScope:'round',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{}};
 t.a.getModel().opportunities=[{...base,id:'own',company:'TEST BI',searchProfileId:'search-current'},{...base,id:'other',company:'TEST técnicos',searchProfileId:'search-two'}];
 dom.field('targetRoles').value='TEST nuevo BI';await t.dispatchMain('input',dom.field('targetRoles'));
 t.env.criteriaPreview=body=>{previews.push(body);return {revision:t.a.getModel().revision};};
 t.env.fetch=async()=>({ok:true,json:async()=>({state:{...t.a.getModel(),revision:1}})});
 assert.equal(await t.a.saveProfileChanges(),true);
 assert.deepEqual(previews[1].targets,[{id:'own'}]);assert.equal(previews[1].searchProfileId,'search-current');
 assert(previews.every(body=>!(body.targets||[]).some(target=>target.id==='other')));
});

test('legacy search drafts move once and collisions preserve both exact copies and pending attempts',()=>{
 const entries=new Map(),store={getItem:key=>entries.get(key)??null,setItem:(key,value)=>entries.set(key,value),removeItem:key=>entries.delete(key)};
 const raw=JSON.stringify({values:{targetRoles:'TEST'},attempt:{id:'TEST-old',operation:{kind:'ui-profile-section',section:'search'}}});
 store.setItem('stubbs_jobs-draft:busqueda:global',raw);Drafts.bindSearchProfile(store,'search-current');
 assert.equal(store.getItem('stubbs_jobs-draft:busqueda:global'),null);assert.equal(store.getItem('stubbs_jobs-draft:busqueda:profile:search-current'),raw);
 store.setItem('stubbs_jobs-draft:busqueda:global','TEST different');Drafts.bindSearchProfile(store,'search-current');
 assert.equal(store.getItem('stubbs_jobs-draft:busqueda:global'),'TEST different');assert.equal(store.getItem('stubbs_jobs-draft:busqueda:profile:search-current'),raw);
});

test('deletion in another window preserves the removed profile draft and does not insert it in the default',async()=>{
 const t=setup(),dom=strategyFixture(t);
 dom.field('targetRoles').value='TEST borrador anterior';await t.dispatchMain('input',dom.field('targetRoles'));
 const next=structuredClone(t.a.getModel()),removed=next.searchProfiles.shift();
 next.defaultSearchProfileId='search-two';next.deletedSearchProfiles=[{id:removed.id,name:removed.name,deletedAt:'2026-10-08T20:00:00Z'}];
 next.revision++;t.a.acceptState(next);t.a.render();
 assert.equal(dom.field('targetRoles').value,'Técnico');
 assert.equal(JSON.parse(t.storage.get('stubbs_jobs-draft:busqueda:profile:search-current')).values.targetRoles,'TEST borrador anterior');
 const html=t.a.profileForm();assert.doesNotMatch(html,/<option[^>]*value="search-current"/);
 assert.match(html,/Papelera \(1\)/);
 const drafts=t.a.backupDrafts();assert(drafts.some(d=>d.searchProfileId===removed.id&&d.label.includes('Perfil eliminado')));
});

test('profile controls use accessible icons and omit archiving',async()=>{
 const t=setup();strategyFixture(t);
 let html=t.a.profileForm();
 for(const [action,label,name] of [['create','Crear','plus'],['duplicate','Duplicar','copy'],['rename','Renombrar','pencil']]){
  const button=html.match(new RegExp(`<button[^>]*data-search-profile-action="${action}"[\\s\\S]*?</button>`))[0];
  assert.match(button,new RegExp(`aria-label="${label} perfil de búsqueda" title="${label} perfil de búsqueda"`));
  assert.match(button,new RegExp(`data-icon="${name}"`));assert.match(button,/aria-hidden="true"/);
  assert.doesNotMatch(button,new RegExp(`>${label}<`));
 }
 assert.doesNotMatch(html,/data-search-profile-action="delete"/);
 await t.dispatchMain('change',{dataset:{searchProfile:'1'},value:'search-two'});
  html=t.a.profileForm();
  const deletion=html.match(/<button[^>]*data-search-profile-action="delete"[\s\S]*?<\/button>/)[0];
  assert.match(deletion,/class="profile-action-icon"/);
  assert.match(deletion,/aria-label="Eliminar perfil de búsqueda" title="Eliminar perfil de búsqueda"/);
  assert.match(deletion,/data-icon="trash"/);assert.match(deletion,/aria-hidden="true"/);
  assert.doesNotMatch(deletion,/>Eliminar/);
  assert.match(html,/>Usar por defecto<\/button>/);
  assert.doesNotMatch(html,/data-search-profile-action="archive"|>Archivar<\/button>/);
});

test('offer conditions contain published facts and the evaluation profile change stays in collapsed more actions',()=>{
 const t=setup();strategyFixture(t);
 const job={id:'TEST-old',company:'TEST Empresa',title:'TEST Puesto',state:'Por decidir',apply:'Sí',requests:[],packages:[],questions:[],missing:[],draft:{},answers:{},searchProfileName:'TEST perfil anterior',searchProfileDeleted:true};
 t.a.getModel().opportunities=[job];t.a.setSelected(job.id);
 const html=t.a.detail(),conditions=html.match(/<section class="case-section offer-conditions"[\s\S]*?<\/section>/)[0];
 assert.doesNotMatch(conditions,/data-offer-criteria|Evaluada con|Cambiar perfil/);
 assert.match(html,/<p class="helper offer-criteria-basis">Evaluada con: TEST perfil anterior · Perfil eliminado<\/p>/);
 const more=html.match(/<details class="case-disclosure case-more"[\s\S]*?<\/details>/)[0];
 assert.doesNotMatch(more,/<details[^>]*\bopen\b/);assert.match(more,/Cambiar perfil de evaluación/);
 job.sent={at:'2026-10-08T20:00:00Z'};assert.doesNotMatch(t.a.detail(),/data-offer-criteria-change/);
});
