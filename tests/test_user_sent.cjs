const {test}=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../app/presentation.js');
const Dates=require('../app/formatting.js');
const Activity=require('../app/activity.js');

const fingerprint='a'.repeat(64);
function job(values={}){return {id:'one',state:'Preparar',questions:[],packages:[],requests:[],missing:[],selection:{selected:true,mode:'review'},
 selfReport:{available:true,reason:null,packageCv:null,pendingSends:0,uncertainAttempts:0,historical:[],conciliation:'TEST-conciliation'},...values};}
const library=[{name:'general.pdf',path:'outputs/cv/general.pdf',fingerprint,available:true},
 {name:'perdido.pdf',path:'outputs/cv/perdido.pdf',fingerprint:'b'.repeat(64),available:false}];

test('a datetime-local value keeps the person wall-clock time with an explicit offset',()=>{
 const value=Dates.zonedInstant('2026-10-16T09:30');
 assert.match(value,/^2026-10-16T09:30:00[+-]\d{2}:\d{2}$/);
 assert.equal(new Date(value).getTime(),new Date('2026-10-16T09:30').getTime());
 assert.equal(Dates.localInputValue(new Date('2026-10-16T09:30')),'2026-10-16T09:30');
 for(const invalid of ['', '16/10/2026 09:30', null, '2026-10-16'])assert.equal(Dates.zonedInstant(invalid),null);
});

test('the dialog offers the current package CV and available PDFs, and explains what it cancels',()=>{
 const value=job({selfReport:{...job().selfReport,packageCv:{packageId:'TEST-package',name:'cv-example.pdf'},pendingSends:1,uncertainAttempts:1,
  historical:[{company:'Example',title:'BI',state:'Enviada'}]}});
 const before=structuredClone(value),choices=ui.userSentChoices(value,library);
 assert.deepEqual(choices.options.map(o=>o.cv),[{source:'package',packageId:'TEST-package'},{source:'library',path:'outputs/cv/general.pdf',fingerprint}]);
 assert.equal(choices.warnings.length,3);
 assert.match(choices.warnings.join(' '),/Comprueba en el portal que solo figure una solicitud tuya/);
 assert.match(choices.warnings.join(' '),/Se cancelará el envío pendiente del agente/);
 assert.equal(choices.reapplication,true);
 assert.deepEqual(value,before);
});

test('no dialog when the offer is already sent, closed or busy sending',()=>{
 assert.equal(ui.userSentChoices(job({selfReport:null}),library),null);
 assert.equal(ui.userSentChoices(job({selfReport:{...job().selfReport,available:false,reason:'El agente está enviando'}}),library),null);
 assert.equal(ui.userSentChoices(job({sent:{type:'sent'}}),library),null);
});

test('the operation carries a real zoned time, the CV, the duplicate check and the conciliation only',()=>{
 const value=job(),choices=ui.userSentChoices(value,library),cv=choices.options[0].value;
 const base={cv,sentAt:'2026-10-16T09:30',note:'  Referencia TEST-1 ',duplicatesChecked:true,reapplication:false};
 const {operation}=ui.userSentOperation(value,choices,base,Date.parse('2026-10-16T12:00'));
 assert.deepEqual(Object.keys(operation).sort(),['cv','duplicatesChecked','expected','kind','note','opportunityId','sentAt']);
 assert.equal(operation.kind,'ui-user-sent');assert.equal(operation.note,'Referencia TEST-1');assert.equal(operation.expected,'TEST-conciliation');
 assert.match(operation.sentAt,/[+-]\d{2}:\d{2}$/);
 assert.equal(ui.userSentOperation(value,choices,{...base,note:'  '},Date.parse('2026-10-16T12:00')).operation.note,undefined);
 for(const [values,message] of [[{cv:''},/CV/],[{sentAt:''},/fecha/],[{duplicatesChecked:false},/única solicitud/]])
  assert.match(ui.userSentOperation(value,choices,{...base,...values},Date.parse('2026-10-16T12:00')).error,message);
 assert.match(ui.userSentOperation(value,choices,base,Date.parse('2026-10-15T12:00')).error,/futura/);
 const again=ui.userSentChoices(job({selfReport:{...job().selfReport,historical:[{company:'Example'}]}}),library);
 assert.match(ui.userSentOperation(value,again,base,Date.parse('2026-10-16T12:00')).error,/solicitud nueva/);
 assert.equal(ui.userSentOperation(value,again,{...base,reapplication:true},Date.parse('2026-10-16T12:00')).operation.reapplication,true);
});

test('a send recorded by the person reads as Siguiendo, sent by her, and its undo stays visible',()=>{
 const value=job({state:'Enviada',selfReport:null,sent:{type:'sent',reportedBy:'user',at:'2026-10-16T09:30:00+02:00'},
  requests:[{id:'TEST-send',type:'send',status:'cancelled',packageId:'p',startedAt:'2026-10-16T08:00:00Z'}]});
 assert.equal(ui.offerState(value).label,'Siguiendo');
 assert.equal(ui.step(value).detail,'Enviada por ti. Esperando novedades.');
 assert.equal(Activity.title({title:'Solicitud enviada',activity:{kind:'event',type:'sent',reportedBy:'user'}}),'Solicitud enviada por ti');
 assert.equal(Activity.title({title:'Solicitud enviada',activity:{kind:'event',type:'sent',reportedBy:'user',retracted:true}}),'Envío registrado por ti · deshecho');
 assert.equal(Activity.title({title:'Envío confirmado',activity:{kind:'event',type:'sent'}}),'Solicitud enviada');
});
