'use strict';
(()=>{
const UI=window.StubbsJobsUI;
const icon=window.StubbsJobsIcons.icon;
let storageProblem=false;
const sessionStorage=window.StubbsJobsClient.safeStorage(()=>globalThis.sessionStorage,()=>{storageProblem=true;});
const localStorage=window.StubbsJobsClient.safeStorage(()=>globalThis.localStorage,()=>{storageProblem=true;});
window.StubbsJobsTheme.set(window.StubbsJobsTheme.get());
window.StubbsJobsDrafts.migrate(sessionStorage,localStorage);
let draftStorage=window.StubbsJobsDrafts.storage(sessionStorage,localStorage);
let workspace=null,actionAttempts=window.StubbsJobsDrafts.actionJournal(draftStorage),workspaceSession=sessionStorage;
let refreshInFlight=null, stateVersion=null, navigationSerial=0, mutationSerial=0, saving=false,actionBusy=false,profileSaving=false;
let reviewSnapshot=null, navigationReady=false, historyLimit=30, toastTimer=null;
let activityDayLimit=7;
const openActivityGroups=new Set();
let setupCopiedUntil=0,setupCopyTimer=null;
const flowScreens=['perfil','solicitar','agente'];
const flowFilters={solicitar:'todas'};
const tableState={solicitar:{sort:'',direction:1,filters:{},choices:{}},encontrar:{sort:'',direction:1,filters:{},choices:{}}};
const tableSelection=new Set();let bulkSelectionMode=false,bulkReviewSnapshots=[],bulkReviewTotal=0,bulkEditor=null,offerTour=null;
const profileSections=[['profile-about','Datos personales'],['profile-experience','Experiencia'],['profile-work','Lo que busco'],['profile-cv','Currículums'],['profile-answers','Respuestas guardadas'],['profile-permissions','Permisos']];
function canonicalProfileSection(id){return ({'search-settings-criteria':'profile-work','search-settings-sources':'profile-work','profile-previous':'profile-work','perfil-previous':'profile-work'})[id]||id;}
let profileSection='profile-about',profileSectionRestored=false,profileSaveProblem='',openFilterMenu=null;
let searchProfileId=null,offerProfileFilter='';
const anonymousCvKeys=new WeakMap();let anonymousCvSequence=0;
let draftNeedsReview=false,draftRepaintQueued=false,rendering=false;
const draftUpdateNotice='Hay datos nuevos. Tu borrador se conserva.';
let viewMemory={};try{viewMemory=JSON.parse(sessionStorage.getItem('stubbs_jobs-views')||'{}');}catch{}
let lastFlowScreen='solicitar';
let navigationTrail=[];
const main=document.querySelector('#main'), connection=document.querySelector('#connection');
if(window.ResizeObserver){new window.ResizeObserver(([entry])=>document.documentElement.style.setProperty('--header-height',entry.target.getBoundingClientRect().height+'px')).observe(document.querySelector('.site-header'));}
// Sticky layers below the menu follow the real height of the toolbar and the offer heading.
const stickyLayers=[['.offer-toolbar','--offer-toolbar-height'],['.offer-heading','--offer-heading-height']];
const offerToolbarObserver=window.ResizeObserver?new window.ResizeObserver(entries=>{for(const {target} of entries)for(const [selector,name] of stickyLayers)if(target===main.querySelector(selector))main.style?.setProperty(name,target.getBoundingClientRect().height+'px');}):null;
function syncOfferToolbar(){
 offerToolbarObserver?.disconnect();
 for(const [selector,name] of stickyLayers){
  const layer=main.querySelector(selector);if(!layer?.getBoundingClientRect)continue;
  main.style?.setProperty(name,layer.getBoundingClientRect().height+'px');
  offerToolbarObserver?.observe(layer);
 }
}
function viewScroll(){
 const table=main.querySelector('.workflow-table-wrap'),top=table?.scrollTop||0;
 return {scroll:window.scrollY+(screen==='solicitar'?top:0),tableScroll:table?.scrollLeft||0,tableTop:screen==='solicitar'?0:top};
}
let model=null, screen='solicitar', selected=null, dirty=false, conflict=null, filterText='', caseReturn='solicitar', findReturn='solicitar', auxReturn='agente', pollTimer;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fieldLabel=v=>String(v??'').replace(/^Sueldo\b/,'Salario').replace(/^Candidaturas\b/,'Solicitudes');
const date=v=>{if(!v)return 'Sin comprobar';const at=window.StubbsJobsFormatting.tableTimestamp(v);return at===null?'Fecha no válida':new Intl.DateTimeFormat('es-ES',{dateStyle:'medium',timeStyle:String(v).includes('T')?'short':undefined,timeZone:undefined}).format(at);};
const isHttpUrl=value=>/^https?:\/\//i.test(value||'');
const url=value=>isHttpUrl(value)?esc(value):'#';
const getJob=id=>model?.opportunities.find(x=>x.id===id)||(model?UI.archive(model).find(x=>x.id===id):null);
const active=UI.active;
const requestModes={review:{label:'Solicitar con revisión',icon:'eye'},auto:{label:'Auto-solicitud',icon:'bot'}};
const platformNames={linkedin:'LinkedIn',infojobs:'InfoJobs',indeed:'Indeed',tecnoempleo:'Tecnoempleo',empresas:'Web',glassdoor:'Glassdoor'};
function lastUserUndo(){return (model?.undo||[]).filter(item=>['Usuario','Usuario'].includes(item.actor)).at(-1);}
function syncUndo(){const lastUndo=lastUserUndo(),button=document.querySelector('#header-undo');if(button){button.hidden=!lastUndo||model.setupComplete===false;button.dataset.undo=lastUndo?.id||'';button.title=lastUndo?'Deshacer: '+lastUndo.title:'Deshacer último cambio';button.setAttribute('aria-label',button.title);}}
function toast(text,undoId=null){const box=document.querySelector('#toast');box.innerHTML=`<span>${esc(text)}</span>${undoId?` <button class="toast-undo" data-undo="${esc(undoId)}">Deshacer</button>`:''}`;box.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{box.hidden=true;},undoId?12000:4500);}
function changeToast(text){toast(text,lastUserUndo()?.id);}
const api=(path,body)=>window.StubbsJobsClient.request(path,body,{fetcher:(...args)=>fetch(...args)});
const sameFieldValue=(left,right)=>left===right||Array.isArray(left)&&Array.isArray(right)&&JSON.stringify(left)===JSON.stringify(right)||[null,undefined,''].includes(left)&&[null,undefined,''].includes(right);
function acceptState(next){
 window.StubbsJobsClient.validateState(next);
 if(workspace&&workspace!==next.workspaceId)throw new Error('La app está respondiendo desde otra carpeta. Vuelve a abrir Stubbs Jobs desde su acceso.');
 if(Number.isFinite(model?.revision)&&Number.isFinite(next.revision)&&next.revision<model.revision)return false;
 if(!workspace){
  workspace=next.workspaceId;
  workspaceSession=window.StubbsJobsDrafts.scoped(sessionStorage,workspace);
  const durable=window.StubbsJobsDrafts.scoped(localStorage,workspace);
  window.StubbsJobsDrafts.migrate(workspaceSession,durable);
  draftStorage=window.StubbsJobsDrafts.storage(workspaceSession,durable);
  actionAttempts=window.StubbsJobsDrafts.actionJournal(draftStorage);
  try{const saved=JSON.parse(workspaceSession.getItem('stubbs_jobs-views')||'{}');viewMemory=saved&&typeof saved==='object'&&!Array.isArray(saved)?saved:{};}catch{viewMemory={};}
  try{const saved=JSON.parse(workspaceSession.getItem('stubbs_jobs-offer-tour')||'null');offerTour=saved&&Array.isArray(saved.ids)&&saved.ids.every(id=>typeof id==='string')?saved:null;}catch{offerTour=null;}
 }
 if(Array.isArray(next.searchProfiles)){
  if(!searchProfileId){searchProfileId=workspaceSession.getItem('stubbs_jobs-search-profile')||next.defaultSearchProfileId;offerProfileFilter=workspaceSession.getItem('stubbs_jobs-offer-profile')||'';}
  if(!next.searchProfiles.some(p=>p.id===searchProfileId))searchProfileId=next.defaultSearchProfileId;
  if(offerProfileFilter&&!next.searchProfiles.some(p=>p.id===offerProfileFilter))offerProfileFilter='';
  window.StubbsJobsDrafts.bindSearchProfile(draftStorage,'search-current');
 }
 model=next;return true;
}
function captureFocus(element=document.activeElement){
 if(!element||!main.contains(element)&&!columnMenuFor(element))return null;
 return {id:element.id,tag:element.tagName,name:element.name,form:controlForm(element)?.dataset.form,
  data:JSON.stringify(element.dataset||{}),text:element.tagName==='SUMMARY'?element.textContent:null,
  start:element.selectionStart,end:element.selectionEnd};
}
function restoreFocus(focus){
 if(!focus)return;
 const candidates=[...main.querySelectorAll('button,summary,input,textarea,select,a'),...(openFilterMenu?columnPanel(openFilterMenu)?.querySelectorAll('button,input')||[]:[])];
 const element=focus.id?document.getElementById(focus.id):candidates.find(el=>
  el.tagName===focus.tag&&el.name===focus.name&&controlForm(el)?.dataset.form===focus.form&&JSON.stringify(el.dataset||{})===focus.data&&
  (focus.text===null||el.textContent===focus.text));
 const collapsed=element?.closest('details:not([open])');
 const target=collapsed?collapsed.querySelector('summary'):element;
 target?.focus({preventScroll:true});
 if(target===element&&element?.setSelectionRange&&focus.start!==null&&focus.start!==undefined)element.setSelectionRange(focus.start,focus.end);
}
function draftKey(form=main.querySelector('form[data-form]')){const kind=form?.dataset.form;const legacy=!selected?(screen==='perfil'?{about:'datos',experience:'experiencia',search:'busqueda',sources:'fuentes'}[kind]:null):null;const scope=['search','sources'].includes(kind)&&form?.dataset.searchProfileId?'profile:'+form.dataset.searchProfileId:selected||'global';return 'stubbs_jobs-draft:'+(legacy||screen)+':'+scope;}
function visibleForms(){return [...main.querySelectorAll('form[data-form]')];}
function controlForm(control){return control?.form?.dataset?.form?control.form:control?.closest?.('form[data-form]');}
function formFeedback(form,selector){
 if(screen==='perfil'&&!selected&&form?.dataset.form==='search'){
  const values=formValues(form),key=form._lastEditedField||Object.keys(values).find(key=>!sameFieldValue(values[key],form._shown[key]));
  const fieldBox=key==='previousApplications'?document.getElementById('search-field-previousApplications')?.querySelector?.(selector+'[data-feedback-owner="search"]'):null;if(fieldBox)return fieldBox;
  const box=document.getElementById(profileFieldSection('search',key))?.querySelector?.(selector+'[data-feedback-owner="search"]');if(box)return box;
 }
 return form?.querySelector(selector);
}
function clearDraftUpdateNotice(){draftNeedsReview=false;if(connection.textContent===draftUpdateNotice)connection.textContent='';}
function repaintRevertedDraft(){
 if(draftRepaintQueued||rendering||saving||profileSaving||actionBusy||dirty||!draftNeedsReview)return;
 const view=screen+'/'+(selected||'');draftRepaintQueued=true;
 Promise.resolve().then(()=>{draftRepaintQueued=false;if(view!==screen+'/'+(selected||'')||rendering||saving||profileSaving||actionBusy||dirty||!draftNeedsReview)return;clearDraftUpdateNotice();render(true);});
}
function profileFieldSection(kind,key){
 if(key==='cvGuidelines')return 'profile-cv';
 if(AUTO_PERMISSION_KEYS().has(key))return 'profile-permissions';
 if(kind==='experience'||key==='languages')return 'profile-experience';
 if(kind==='about'){const layout=aboutLayout();if(layout.education.includes(key))return 'profile-experience';if(layout.answers.flat().includes(key))return 'profile-answers';return 'profile-about';}
 return 'profile-work';
}
function AUTO_PERMISSION_KEYS(){return new Set(permissionGroups().flatMap(group=>group.items.map(item=>item.key)));}
function profileChangedSections(forms=visibleForms()){
 const changed=new Set();for(const form of forms.filter(form=>form._dirty)){
  const values=formValues(form),fields=Object.keys(values).filter(key=>!sameFieldValue(values[key],form._shown[key]));
  if(!fields.length){try{const attempt=JSON.parse(draftStorage.getItem(draftKey(form)))?.attempt;if(attempt)fields.push(...Object.keys(attempt.operation.values||attempt.values||values));}catch{}}
  if(!fields.length)fields.push(Object.keys(values)[0]);for(const key of fields)changed.add(profileFieldSection(form.dataset.form,key));
 }return profileSections.filter(([id])=>changed.has(id)).map(([,label])=>label);
}
function syncDirty(){
 dirty=visibleForms().some(form=>form._dirty===true);
 if(!dirty){if(draftNeedsReview&&!rendering)repaintRevertedDraft();else clearDraftUpdateNotice();}
 const warning=document.querySelector('#storage-warning');if(warning)warning.hidden=!storageProblem;
 const bar=main.querySelector('[data-profile-savebar]'),button=bar?.querySelector('[data-save-profile]');
 if(bar){bar.hidden=!dirty&&!profileSaving;bar.setAttribute('aria-busy',String(profileSaving));if(button){button.disabled=profileSaving||saving||actionBusy;button.textContent=profileSaving?'Guardando…':'Guardar cambios';}}
 const pending=main.querySelector('[data-profile-pending]');bar?.classList?.toggle('profile-savebar--problem',Boolean(profileSaveProblem&&dirty));if(pending){const changed=profileChangedSections();pending.textContent=profileSaveProblem&&dirty?profileSaveProblem:changed.length?'Cambios en '+changed.map(label=>label==='Lo que busco'&&model.searchProfiles?.length>1&&currentSearchProfile()?`Lo que busco (${currentSearchProfile().name})`:label).join(', '):profileSaving?'Guardando tus cambios…':'Cambios sin guardar';for(const link of main.querySelectorAll('[data-profile-section]'))link.classList?.toggle('profile-nav-unsaved',changed.includes(profileSections.find(([id])=>id===link.dataset.profileSection)?.[1]));}
 main.querySelector('.profile-layout')?.classList?.toggle('profile-layout--pending',Boolean(bar&&!bar.hidden));
 const upload=main.querySelector('#cv-upload');if(upload)upload.disabled=profileSaving||saving;
 for(const copy of document.querySelectorAll('[data-copy-agent-command]'))copy.textContent=copy.dataset.copyLabel||'Copiar petición';
}
function rememberForm(form=main.querySelector('form[data-form]')){if(!form)return;const key=draftKey(form),values=Object.fromEntries(new FormData(form));try{const previous=JSON.parse(draftStorage.getItem(key)||'null');const current=formValues(form);const changed=Object.keys(current).some(k=>!sameFieldValue(current[k],form._shown[k]));if(!changed&&!previous?.attempt){draftStorage.removeItem(key);form._dirty=false;const info=formFeedback(form,'.form-info');if(info)info.textContent='';}else{draftStorage.setItem(key,JSON.stringify({values,expected:form._expected,shown:form._shown,attempt:previous?.attempt||null}));form._dirty=true;const info=formFeedback(form,'.form-info');if(info)info.textContent=previous?.attempt?'Guardado pendiente de confirmar. Vuelve a guardar para comprobarlo.':screen==='perfil'&&!selected?'':'Cambios sin guardar.';}}catch{form._dirty=true;}syncDirty();updateSave(form);}
function rememberAllForms(){for(const form of visibleForms())rememberForm(form);}
// Comparable text for a value that may come from a form (text) or from the state (number, list, null).
function draftPlain(value){return value===null||value===undefined||value==='null'?'':Array.isArray(value)?JSON.stringify(value):String(value).trim();}
// What a save must really change: a value already saved never travels, so an old one cannot block the rest.
function unsavedValues(form,values,stored){
 const changed=changedFormValues(form,values);
 if(stored.attempt||!['about','search','sources'].includes(form.dataset.form))return changed;
 const source=formSource(form.dataset.form);
 return Object.fromEntries(Object.entries(changed).filter(([key,value])=>draftPlain(value)!==draftPlain(source[key])));
}
function restoreForm(form=main.querySelector('form[data-form]')){
 if(!form)return;
 try{
  const stored=JSON.parse(draftStorage.getItem(draftKey(form))||'null');if(!stored)return;
  const source=formSource(form.dataset.form),touched=key=>Boolean(stored.attempt)||draftPlain(stored.values[key])!==draftPlain(stored.shown?.[key])&&draftPlain(stored.values[key])!==draftPlain(source[key]);
  const only=values=>Object.fromEntries(Object.entries(values||{}).filter(([key])=>touched(key)));
  for(const [key,value] of Object.entries(stored.values)){
   const field=form.elements.namedItem(key);if(!field||!touched(key))continue;
   const shownValue=key==='demographicSurveyParticipation'&&field.dataset.type==='choice'&&['true','false'].includes(String(value))?surveyMode(String(value)==='true'):value;
   // A previous text answer or boolean draft must survive a switch to options.
   if(field.tagName==='SELECT'&&field.options&&shownValue!==null&&shownValue!==''&&![...field.options].some(option=>option.value===String(shownValue))){
    const option=document.createElement('option');option.value=String(shownValue);option.hidden=true;option.textContent='Respuesta anterior: '+shownValue;field.add(option);
   }
   field.value=shownValue;
  }
  form._expected={...form._expected,...only(stored.expected)};form._shown={...form._shown,...only(stored.shown)};
  projectSurveyShown(form);
  if(form.dataset.form==='search'&&Object.hasOwn(stored.values,'regions')){
   const source=formSource('search');
   const wanted=visibleSearchLocation(stored.values.location??source.location,stored.values.workMode??source.workMode,stored.values.regions);
   const shown=visibleSearchLocation(stored.shown?.location??source.location,stored.shown?.workMode??source.workMode,stored.shown?.regions??source.regions);
   const locationField=form.elements.namedItem('location'),modeField=form.elements.namedItem('workMode');
   if(locationField)locationField.value=wanted.location;if(modeField)modeField.value=wanted.workMode;
   form._shown.location=shown.location;form._shown.workMode=shown.workMode;
   form._expected.regions=stored.expected?.regions??source.regions??'';form.dataset.mergedRegions='1';
   if(wanted.split||shown.split)form.dataset.splitLegacy='1';
  }
  form._dirty=true;const info=formFeedback(form,'.form-info');if(info)info.textContent='';
 }catch{}
}
// The brief state for the current screen, also returned after each action.
function stateParams(){
 const params=new URLSearchParams({brief:'1'});
 if(selected&&screen!=='informe')params.set('case',selected);
 if(screen==='revision-multiple')bulkReviewSnapshots.forEach(j=>params.append('case',j.id));
 if(screen==='edicion-multiple')bulkEditor?.jobs.forEach(j=>params.append('case',j.id));
 if(['agente','actividad','informe'].includes(screen)||selected)params.set('history','1');
 if(screen==='informe'&&selected?.startsWith('event:')){const item=activityRecord(selected.slice(6));if(item?.opportunityId)params.set('case',item.opportunityId);}
 return params;
}
async function refresh(force=false,{deferRender=false}={}){
 if(profileSaving||actionBusy||(document.hidden||saving)&&!force)return;
 if(refreshInFlight){await refreshInFlight;if(force)return refresh(true,{deferRender});return;}
 const view=screen+'/'+(selected||'')+'/'+historyLimit,readSerial=mutationSerial;
 const params=stateParams();
 if(!force&&stateVersion?.view===view)params.set('since',stateVersion.version);
 refreshInFlight=(async()=>{try{
  const next=await api('/api/state?'+params);
  if(view!==screen+'/'+(selected||'')+'/'+historyLimit||readSerial!==mutationSerial||saving||profileSaving)return;
  if(next.unchanged){if(!model||!params.has('since')||next.version!==params.get('since'))throw new Error('La actualización llegó incompleta. Vuelve a actualizar el estado.');connection.textContent=dirty&&draftNeedsReview?draftUpdateNotice:'';updateActivityTimes();return;}
  const changed=!model||next.revision!==model.revision||stateVersion?.version&&stateVersion.version!==next.version;
  if(!acceptState(next))return;
  connection.textContent='';
  stateVersion={view,version:next.version};
  if(screen==='configurar'&&model.setupComplete!==false){screen=model.onboarding?.needsWelcome?'preparado':'solicitar';selected=null;window.history.replaceState(null,'','#'+screen);toast('Tu perfil está confirmado y guardado.');}
  if(dirty){if(changed)draftNeedsReview=true;connection.textContent=draftNeedsReview?draftUpdateNotice:'';return;}
  clearDraftUpdateNotice();
  // Years and answer searches save apart from the page: never replace them while typing.
  if(document.activeElement?.dataset?.knowledge!==undefined){stateVersion=null;return;}
  if(!deferRender)render(true);
 }catch(error){connection.textContent=error.message;if(!model)main.innerHTML='<div class="empty-state"><h1>No se pudo cargar Stubbs Jobs</h1><p>Abre la app desde el acceso de su carpeta y vuelve a intentarlo.</p><button data-refresh-state="1">Reintentar</button></div>';}})();
 try{await refreshInFlight;}finally{refreshInFlight=null;}
}
async function poll(){await refresh();pollTimer=setTimeout(poll,document.hidden?30000:6000);}
async function setScreen(next,id=null,push=true,targetSection=null,sourceElement=null,move=null){
  if(saving||actionBusy||profileSaving){toast("Espera a que termine de guardar.");return;}
  const staysInProfile=!id&&['perfil','buscar','ajustes','cv','datos','busqueda','fuentes','experiencia','contexto','preferencias','antecedentes','search-settings-criteria','search-settings-sources','profile-previous','perfil-previous',...profileSections.map(([section])=>section)].includes(next);
  if(screen==='perfil'&&!selected&&dirty&&!staysInProfile&&!await settleUnsavedProfile('Has cambiado {sections}. ¿Qué quieres hacer antes de salir de Mi perfil?','Guardar y salir')){
   if(!push)window.history.pushState(null,'','#perfil');
   return;
  }
  const serial=++navigationSerial;
  const offerOrigin=sourceElement||(next==='detalle'&&id&&['solicitar','encontrar'].includes(screen)?[...main.querySelectorAll('[data-job]')].find(button=>button.dataset.job===id):null);
  if(navigationReady)viewMemory[screen+'/'+(selected||'')]={filterText,...viewScroll(),focus:captureFocus(offerOrigin)||captureFocus()||viewMemory[screen+'/'+(selected||'')]?.focus,limit:historyLimit,activityDays:activityDayLimit};
  closeColumnMenu();
  workspaceSession.setItem('stubbs_jobs-views',JSON.stringify(viewMemory));
  if(dirty){rememberAllForms();if(!staysInProfile)toast('Borrador conservado.');}
  const profileRoutes=Object.fromEntries([...profileSections.map(([id])=>id),'profile-experience','profile-cv','search-settings-criteria','search-settings-sources','profile-previous','perfil-previous'].map(id=>[id,'perfil']));
  const aliases={hoy:'solicitar',inicio:'solicitar',ofertas:'solicitar',resumen:'agente',buscar:'perfil',candidaturas:'solicitar',elegir:'solicitar',seguir:'solicitar',seguimiento:'solicitar',historial:'solicitar',ajustes:'perfil',salud:'comprobaciones',tabla:'solicitar',cv:'perfil',asistente:'copias',ayuda:'copias',datos:'perfil',busqueda:'perfil',fuentes:'perfil',experiencia:'perfil',contexto:'perfil',preferencias:'perfil',antecedentes:'perfil',autonomia:'solicitar','opciones-solicitud':'solicitar',...profileRoutes};
  const original=next,sectionTargets={buscar:'profile-work',datos:'profile-about',busqueda:'profile-work',fuentes:'profile-work',experiencia:'profile-experience',cv:'profile-cv',contexto:'profile-work',preferencias:'profile-work',antecedentes:'profile-previous'};
  const requestedSection=targetSection||sectionTargets[original]||(profileRoutes[original]?original:null),previousTarget=['profile-previous','perfil-previous','search-field-previousApplications'].includes(requestedSection);
  targetSection=canonicalProfileSection(previousTarget?'profile-work':requestedSection);next=aliases[next]||next;
  if(next==='perfil'&&profileSections.some(([section])=>section===targetSection)){profileSection=targetSection;profileSectionRestored=true;}
  if(next==='comprobaciones'){
   next=id&&getJob(id)?'detalle':'agente';
   if(next==='agente')id=null;
   targetSection=null;
  }
  if(model?.setupComplete===false&&!['configurar','copias'].includes(next)){next='configurar';id=null;}
  if(!['edicion-multiple','revision-multiple','preparado','programacion','copias','configurar','nueva','solicitar','agente','encontrar','perfil','detalle','editar','revisar','actividad','cambio','informe'].includes(next))next='solicitar';
  if(next==='detalle'&&id){
   if(['solicitar','encontrar'].includes(screen)&&navigationReady&&(push||!offerTour?.ids.includes(id)))startOfferTour(id);
   else if(!offerTour?.ids.includes(id)||['agente','perfil','encontrar'].includes(screen)&&selected!==id)offerTour=null;
   workspaceSession.setItem('stubbs_jobs-offer-tour',JSON.stringify(offerTour));
  }
  if(push&&model?.onboarding?.needsWelcome&&flowScreens.includes(next)){
   if(!await action(setupOperation('ui-setup-finish')))return;
  }
  if(flowScreens.includes(next)&&!id)navigationTrail=[];
  else if(!move&&navigationReady&&(next!==screen||id!==selected)){
   const previous=navigationTrail.findLastIndex(item=>item.page===next&&item.id===id);
   if(previous>=0)navigationTrail=navigationTrail.slice(0,previous);
   else if(push)navigationTrail.push({page:screen,id:selected});
  }
  historyLimit=30;
  screen=next;selected=id;dirty=false;conflict=null;clearDraftUpdateNotice();
  if(flowScreens.includes(next))lastFlowScreen=next;
  const saved=viewMemory[screen+'/'+(id||'')]||{};
  // Older views kept part of the vertical position inside the table.
  if(screen==='solicitar'&&saved.tableTop){saved.scroll=(saved.scroll||0)+saved.tableTop;saved.tableTop=0;}
  const initialLimit=['solicitar','encontrar'].includes(screen)?100:30;
  historyLimit=Number.isInteger(saved.limit)&&saved.limit>=initialLimit?saved.limit:initialLimit;
  activityDayLimit=Number.isInteger(saved.activityDays)&&saved.activityDays>=7?saved.activityDays:7;
  filterText=saved.filterText||'';
  reviewSnapshot=null;
  if(push)window.history.pushState(null,'','#'+next+(id?'/'+encodeURIComponent(id):''));
  else if(original!==next)window.history.replaceState(null,'','#'+next+(id?'/'+encodeURIComponent(id):''));
  navigationReady=true;
  if(id&&next!=='informe'&&!getJob(id)?.draft&&!getJob(id)?.historical)main.innerHTML='<p class="empty">Abriendo solicitud…</p>';
  await refresh(true,{deferRender:true});if(serial!==navigationSerial)return;
  reviewSnapshot=next==='revisar'&&getJob(id)?structuredClone(getJob(id)):null;render();
  requestAnimationFrame(()=>{const table=main.querySelector('.workflow-table-wrap');if(table){table.scrollLeft=saved.tableScroll||0;table.scrollTop=saved.tableTop||0;}if(move){restoreOfferSection(move.section);const arrow=main.querySelector(`[data-offer-move="${move.direction}"]`);(arrow?.disabled?main.querySelector(`[data-offer-move="${-move.direction}"]`):arrow)?.focus({preventScroll:true});}else if(targetSection){const target=document.getElementById(targetSection),field=previousTarget?visibleForms().find(form=>form.dataset.form==='search')?.elements.namedItem('previousApplications'):null;(previousTarget?document.getElementById('search-field-previousApplications')||target:target)?.scrollIntoView({block:'start',behavior:'instant'});(field||target?.querySelector('input,textarea,select'))?.focus({preventScroll:true});}else{window.scrollTo({top:saved.scroll||0,behavior:'instant'});if(document.activeElement?.id!=='global-search'){if(saved.focus)restoreFocus(saved.focus);else main.focus?.({preventScroll:true});}}});
}
async function route(){
  const [page,id]=location.hash.slice(1).split('/');
  if(page==='main'){main.focus();return;}
  let decoded=null;try{decoded=id?decodeURIComponent(id):null;}catch{toast('El enlace no es válido. Mostramos tus ofertas.');}
  if(page==='profile-cv'&&decoded){
   const inProfile=screen==='perfil'&&!selected;cvDetail=decoded;profileSection='profile-cv';profileSectionRestored=true;
   if(inProfile){rememberAllForms();render(true);}else await setScreen('perfil',null,false,'profile-cv');
   return;
  }
  if(page==='perfil'&&cvDetail&&screen==='perfil'&&!selected){closeCvDetail(false);return;}
  await setScreen(page||(model?.setupComplete===false?'configurar':model?.onboarding?.needsWelcome?'preparado':'solicitar'),decoded,false);
}
function historyTitle(value){return window.StubbsJobsActivity.title(typeof value==='object'?value:{title:value});}
function timeline(items,limit=30,withCompany=true,relative=false){
 if(!items.length)return '<p class="muted">Todavía no hay cambios registrados.</p>';
 return '<ol class="timeline">'+items.slice().reverse().slice(0,limit).map(item=>activityItem(item,withCompany,relative)).join('')+'</ol>';
}
function primaryAction(j,step=UI.step(j),inDetail=false){
  if(inDetail&&step.action==='open')return step.retryRequestId?`<button data-retry="${esc(step.retryRequestId)}" title="El agente comprobará lo ocurrido antes de continuar.">Pedir otro intento</button>`:'';
  if(!step.cta)return '';
  // A pending portal step is done in the agent's browser: one button reports it.
  // Explaining a problem instead stays in Más acciones > Pedir cambio.
  if(inDetail&&step.retryRequestId)return `<button class="primary" data-retry="${esc(step.retryRequestId)}" title="El agente comprobará el portal antes de continuar.">Ya he completado el acceso</button>`;
  const attr={review:'data-review',answers:'data-answers',resolve:'data-resolve',open:'data-job',recovery:'data-copy-recovery'}[step.action]||'data-job';
  return `<button class="primary" ${attr}="${esc(step.action==='recovery'?step.requestId:j.id)}">${esc(step.cta)}</button>`;
}
function formErrors(owner=null){const attr=owner?` data-feedback-owner="${owner}"`:'';return `<div class="form-error"${attr} role="alert"></div><div class="form-info muted"${attr}></div>`;}
function top(title,subtitle=''){return `<div class="title-row"><div><h1>${title}</h1>${subtitle?`<p class="muted">${subtitle}</p>`:''}</div></div>`;}
function setupCopyButton(label='Copiar mensaje',available=true){
 return `<button class="primary" data-copy-setup="1" data-copy-label="${esc(label)}"${available?'':' disabled'} aria-live="polite">${Date.now()<setupCopiedUntil?'Copiado':esc(label)}</button>`;
}
function setupAgentPrompt(){
 return `Quiero preparar mi perfil de Stubbs Jobs en esta carpeta: ${model.workspacePath||'[ubicación aún no disponible]'}.

Sigue docs/getting-started.md y comprueba el acceso a la carpeta y sus herramientas. Retoma el avance guardado y hazme una entrevista breve para confirmar primero los datos esenciales de la búsqueda: ayúdame con los CV que adjunte, pregunta solo por lo necesario ahora y conserva los demás datos como pendientes y confirma qué quiero dejar en blanco.

Muéstrame el resumen antes de guardar solo lo que confirme. Después, guíame paso a paso para conectar mi navegador y mi correo. Si ya tengo perfil, no repitas la entrevista. No busques ofertas ni envíes solicitudes todavía.`;
}
function toolsAgentPrompt(){
 return `Guíame paso a paso, de una en una, para conectar las herramientas pendientes de Stubbs Jobs, siguiendo docs/agent-tools.md en esta carpeta: ${model.workspacePath||'[ubicación aún no disponible]'}.

Soy principiante: dime exactamente dónde pulsar, comprueba tú que cada conexión funciona y registra el resultado. Si alguna no está disponible, dime qué cambia y sigue. No busques ofertas ni envíes solicitudes.`;
}
function toolsPending(){return (model.agentTools?.tools||[]).filter(tool=>model.agentTools.pending.includes(tool.key));}
function toolsList(tools){
 return `<ul class="tools-list">${tools.map(tool=>`<li><strong>${esc(tool.label)}</strong> <span class="muted">· ${esc(tool.statusText)}</span><br>${esc(tool.why)}</li>`).join('')}</ul>`;
}
function toolsCopyButton(primary=true){return `<button${primary?' class="primary"':''} data-copy-tools="1">Copiar mensaje para mi agente</button>`;}
// Recommended, never required: the person can use the app and search without them.
function toolsWelcome(){
 const tools=toolsPending();if(!tools.length)return '';
 return `<section class="setup-tools" aria-labelledby="setup-tools-title"><h2 id="setup-tools-title">Antes de tu primera búsqueda, conecta tus herramientas</h2><p>Tu agente trabajará mejor y te pedirá menos cosas. Copia este mensaje en el mismo chat: te guiará paso a paso.</p>${toolsList(tools)}${toolsCopyButton()}</section>`;
}
function toolsNotice(){
 const tools=toolsPending();if(!tools.length)return '';
 return `<details class="tools-notice"><summary>Recomendado: conecta ${tools.length===1?`${tools[0].key==='mail'?'tu correo':'la extensión de tu navegador'}`:'tu navegador y tu correo'} para mejores resultados</summary>${toolsList(tools)}<p class="helper">Pega este mensaje en el chat de tu agente y te guiará paso a paso.</p>${toolsCopyButton(false)}</details>`;
}
function setupAgentHelp(){
 return `<p class="setup-agent-help"><strong>¿Aún no tienes un agente de IA?</strong> Instala la <a href="https://claude.com/download" target="_blank" rel="noopener">app de escritorio de Claude</a> y abre su pestaña Code, o usa la app de ChatGPT con Codex. Los chats web, como claude.ai o chatgpt.com, no pueden trabajar con esta carpeta. El coste depende de cada servicio; conectar tu navegador puede requerir un plan de pago.</p>`;
}
function setupOperation(kind){const state=model.onboarding;return {kind,workspaceId:state.workspaceId,token:state.token,expected:state.revision};}
function setupForm(){
 const state=model.onboarding||{status:'waiting'},status=state.status;
 const path=typeof model.workspacePath==='string'?model.workspacePath:'',available=Boolean(path.trim());
 const progress={access_checked:'Carpeta comprobada. Continúa en el chat.',preparing:state.coverage?.complete?'Continúa en el chat para revisar el resumen.':'Responde a lo pendiente en el chat; puedes dejar datos en blanco.',awaiting_confirmation:'Revisa el resumen en el chat y confírmalo o pide cambios.',blocked:state.summary||'Consulta el chat para resolver el paso pendiente.'};
 const needed=state.coverage?.requiredTotal,coverage=state.coverage&&status!=='waiting'&&Number.isInteger(needed)?`${needed-(state.coverage.requiredPending||0)} de ${needed} datos necesarios tratados.${state.coverage.blank?` ${state.coverage.blank} dejado${state.coverage.blank===1?'':'s'} en blanco por tu decisión.`:''}`:'';
 // Once a chat has started the interview, the only thing left to do here is follow it or move it.
 const steps=state.executionId?'':`<section class="setup-instructions"><h2><span class="setup-step" aria-hidden="true">1</span> Añade esta carpeta como proyecto en tu agente de IA</h2><div class="copy-line"><code>${esc(available?path:'Cargando ubicación…')}</code><button data-copy-path="1"${available?'':' disabled'}>Copiar ubicación</button></div><h2><span class="setup-step" aria-hidden="true">2</span> Pega este mensaje en un chat dentro de tu nuevo proyecto para preparar tu perfil</h2><pre id="setup-message" class="setup-message" tabindex="0" aria-label="Mensaje para tu agente">${esc(setupAgentPrompt())}</pre>${setupCopyButton('Copiar mensaje',available)}</section>`;
 const current=progress[status]?`<p class="setup-coverage" role="status">${esc(progress[status])}${coverage?` <span>${esc(coverage)}</span>`:''}</p>`:'';
 return `<div class="welcome-view setup-view"><h1>Empieza con Stubbs Jobs</h1><p class="lead">Encuentra ofertas a tu medida y prepara tus solicitudes con tu agente de IA. Tú decides dónde solicitar.</p>${current}${typeof model.syncedFolder==='string'&&model.syncedFolder?`<p class="setup-warning" role="alert">Esta carpeta está dentro de ${esc(model.syncedFolder)}. Para evitar copias en conflicto de tus datos, cierra la app y mueve la carpeta completa a una ubicación local sin sincronizar, como C:\\StubbsJobs.</p>`:''}${status==='waiting'?setupAgentHelp():''}${steps}${state.executionId?`<section class="setup-resume" aria-labelledby="setup-resume-title"><h2 id="setup-resume-title">¿Has perdido ese chat o quieres cambiar a otro?</h2><p>Se conservan tus respuestas y CV, y te daremos el mensaje para pegar en el chat nuevo.</p><button data-setup-retry="1">Retomar en otro chat</button></section>`:''}</div>`;
}
function setupReady(){
 return `<div class="welcome-view setup-view"><h1>Tu perfil está preparado</h1><p class="lead">Para encontrar tus primeras ofertas, pide «Busca ofertas nuevas» en el chat de tu agente.</p>${toolsWelcome()}<div class="setup-actions"><button class="primary" data-setup-finish="solicitar">Ir a Ofertas</button><button data-setup-finish="perfil">Revisar mi perfil</button></div>${!String(model.searchContext.targetRoles||'').trim()||!String(model.preferences.location||model.searchContext.regions||'').trim()?'<p class="helper">Antes de buscar, concreta los puestos y la zona con tu agente o en Mi perfil.</p>':''}</div>`;
}
function sectionDefinitions(section){
 const context=window.StubbsJobsSetup.context,contact=window.StubbsJobsSetup.contact;
 const preferences={contract:{label:'Contrato',type:'text',placeholder:'Ej.: indefinido',suggestions:['Indefinido','Temporal','Autónomo','Prácticas']},location:{label:'Zona de búsqueda',type:'text',placeholder:'Países o zonas donde quieres trabajar'},maxTrips:{label:'Viajes al mes (máximo)',type:'number'},minimumFixed:{label:'Salario fijo mínimo (bruto anual)',type:'number'},keywords:{label:'Palabras clave',type:'text',placeholder:'Términos relevantes para tu sector'},noticeDays:{label:'Cuándo puedo empezar',type:'text',placeholder:'Ej.: 15 días laborables de preaviso, inmediato o desde el 1 de enero'},searchPriorities:{...context.searchPriorities,label:'Horario que prefiero',placeholder:'Ej.: mañana, flexible o sin turnos de noche'}};
 const keys=section==='about'?Object.values(aboutLayout()).flat(2):section==='search'?['targetRoles','keywords','location','workMode','onsiteLocations','contract','minimumFixed','salaryExpectationFixed','salaryCurrency','maxTrips','searchPriorities','requiredSchedule','searchNotes','languages','previousApplications','cvGuidelines']:section==='sources'?['sourceUrls','followedSources','excludedPortals','platforms']:[];
 const personal={currentSalary:{label:'Salario actual (bruto anual)',type:'number'},currentCity:{label:'Ciudad actual',type:'text'},workPermitWithoutSponsorship:{label:'Permiso de trabajo sin patrocinio',type:'boolean'},salaryExpectationFixed:{label:'Salario fijo esperado al año',type:'number'},noticeDays:{label:'Días de preaviso',type:'number'}};
 const defs={...context,...personal,...contact,...window.StubbsJobsSetup.demographics,...model.fieldDefinitions,...preferences,workMode:{...context.workMode,suggestions:['Remoto','Híbrido','Presencial']},name:{...context.name,label:'Nombre y apellidos',autocomplete:'name'},currentCity:{...(model.fieldDefinitions?.currentCity||personal.currentCity),label:'Ciudad'},currentCountry:{...contact.currentCountry,...model.fieldDefinitions?.currentCountry,label:'País'},searchPriorities:{...preferences.searchPriorities,type:'longtext',rows:1,autoGrow:true,maxlength:3000},workAuthorizations:{label:'Puedo trabajar sin patrocinio en',type:'multiselect'},gender:{...window.StubbsJobsSetup.demographics.gender,...model.fieldDefinitions?.gender,help:null,descriptionId:null},languages:{...context.languages,type:'longtext',rows:1,autoGrow:true,maxlength:3000},...(model.fieldDefinitions?.custom_education_level?{custom_education_level:{...model.fieldDefinitions.custom_education_level,suggestions:['Sin estudios','ESO','Bachillerato','FP Grado Medio','FP Grado Superior','Grado universitario','Máster','Doctorado'],placeholder:'Ej.: Grado universitario o FP Grado Superior'}}:{}),...(model.fieldDefinitions?.custom_birth_date?{custom_birth_date:{...model.fieldDefinitions.custom_birth_date,placeholder:'DD/MM/AAAA'}}:{})};
 return Object.fromEntries(keys.map(k=>[k,{...(defs[k]||{label:k,type:'text'}),...(section==='about'&&window.StubbsJobsSetup.aboutOptions.choices[k]?{options:window.StubbsJobsSetup.aboutOptions.choices[k]}:{})}]));
}
// A flat, occupation-independent order keeps related personal data together.
function aboutCustomGroup(key,definition){
 const text=(key+' '+(definition?.label||'')).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 if(/demogr|gender|genero|protected|protegid|ethnic|etnic|race|raza|veteran|disab|discapac|divers|pronoun|pronombre/.test(text))return 'demographic';
 if(/consent|retention|processing|privacy|gdpr|rgpd|autoriz|conserv/.test(text))return 'consent';
 if(/birth|nacimiento|nationality|nacionalidad|citizen|ciudadan/.test(text))return 'identity';
 if(/education|estudios|titulaci|degree/.test(text))return 'education';
 if(definition?.inputType==='url'||/github|gitlab|portfolio|web.?url|website|perfil.*url/.test(text))return 'link';
 if(/salary|salario|sueldo|compensation|remuneraci/.test(text))return 'salary';
 if(/driving|conducir|carnet|vehicle|vehiculo/.test(text))return 'mobility';
 if(/relocat|mudar|reubica|traslad/.test(text))return 'work';
 if(/self.?employ|autonomo/.test(text))return 'situation';
 if(/availability|incorporacion|disponibilidad/.test(text))return 'work';
 return 'answer';
}
function aboutCustomRank(key,definition){
 const text=(key+' '+(definition?.label||'')).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 return /birth|nacimiento|availability|incorporacion|disponibilidad|driving|conducir|carnet/.test(text)?0:/nationality|nacionalidad|current.*salary|salario actual|vehicle|vehiculo/.test(text)?1:/citizen|ciudadan/.test(text)?2:3;
}
function aboutLayout(){
 const definitions=model.fieldDefinitions||{},custom=Object.keys(definitions).filter(k=>k.startsWith('custom_')&&k!=='custom_current_gross_annual_salary_eur'&&definitions[k].scope==='global');
 const group=name=>custom.filter(k=>aboutCustomGroup(k,definitions[k])===name).sort((a,b)=>aboutCustomRank(a,definitions[a])-aboutCustomRank(b,definitions[b])||definitions[a].label.localeCompare(definitions[b].label,'es',{sensitivity:'base'})||a.localeCompare(b)),answers=[],used=new Set();
 const stem=k=>k.replace(/^custom_/,'').split('_').slice(0,2).join('_');
 // A yes/no question and its text detail (same key stem) share one row.
 for(const key of group('answer')){
  if(used.has(key))continue;used.add(key);
  const type=definitions[key].type,partner=group('answer').find(other=>!used.has(other)&&stem(other)===stem(key)&&[type,definitions[other].type].sort().join()==='boolean,text');
  if(partner){used.add(partner);answers.push(type==='boolean'?[key,partner]:[partner,key]);}else answers.push(key);
 }
 const demographic=group('demographic');
 // Related data stay together; within each run the order is fixed by meaning.
 // Optional surveys and sensitive data close Datos personales: they are personal data, used only when a form asks.
 return {identity:['name',...group('identity')],
  contact:['email','phone','linkedinUrl','websiteUrl',...group('link')],
  home:['currentCountry','currentCity','address','postalCode'],
  work:['workAuthorizations','noticeDays',...group('work'),...group('mobility')],
  salary:['currentSalary',...group('salary'),...group('situation'),'salaryExpectationFixed'],
  education:group('education'),
  answers,consent:group('consent'),demographic:['demographicSurveyParticipation','gender',...demographic],
  autoApply:(window.StubbsJobsSetup.autoApplyPermissions||[]).map(item=>item.key).filter(key=>definitions[key])};
}
function aboutFieldsHtml(keys,values,defs,formId=null){
 if(formId)defs=Object.fromEntries(Object.entries(defs).map(([key,definition])=>[key,{...definition,form:formId}]));
 const groups=permissionGroups().map(group=>({...group,items:group.items.filter(item=>defs[item.key])}));
 return keys.map(item=>{
  if(Array.isArray(item)){
   const [question,detail]=item,labelId='profile-pair-'+question+'-label';
   if(window.StubbsJobsSetup.aboutOptions.details[question]===detail){
    return `<div class="profile-field-wide profile-conditional" data-profile-detail="${esc(question)}">${fieldHtml(question,{...defs[question],falseLabel:'No aplica: no he participado',trueLabel:'Sí, he participado'},values[question])}<div data-profile-detail-content${values[question]===true?'':' hidden'}>${fieldHtml(detail,{...defs[detail],label:'Participación y resultados (opcional)',type:'longtext',rows:2,autoGrow:true,maxlength:5000,placeholder:'Competiciones, participación y resultados'},values[detail])}</div></div>`;
   }
   return `<div class="profile-field-wide field-pair" role="group" aria-labelledby="${esc(labelId)}"><span class="field-pair-label" id="${esc(labelId)}">${esc(fieldLabel(UI.answerTitle(defs[question].label)))}</span><div class="field-pair-controls">${fieldHtml(question,{...defs[question],labelClass:'sr-only'},values[question])}${fieldHtml(detail,{...defs[detail],labelClass:'sr-only',placeholder:defs[detail].placeholder||'Detalle y resultados'},values[detail])}</div></div>`;
  }
  const group=groups.find(candidate=>candidate.items.some(permission=>permission.key===item));
  if(group)return item===group.items[0].key?profilePermissionsField(group,values,formId):'';
  if(item==='currentSalary'){const owner=formId?` form="${esc(formId)}"`:'';return `<div class="field"><label for="profile-about-currentSalary">${esc(defs.currentSalary.label)}</label><span class="amount-input"><input id="profile-about-currentSalary" name="currentSalary" data-type="number" type="number" ${numberAttributes(item)} value="${esc(values.currentSalary)}"${owner}><input name="currentSalaryCurrency" data-type="text" class="currency-input" type="text" value="${esc(values.currentSalaryCurrency??'')}" maxlength="3" pattern="[A-Z]{3}" placeholder="EUR" aria-label="Moneda del salario actual, código de tres letras"${owner}></span></div>`;}
  if(item==='salaryExpectationFixed')return `<div class="field"><label for="profile-about-salaryExpectationFixed">Salario que pido (bruto anual, para formularios)</label><span class="amount-input"><input id="profile-about-salaryExpectationFixed" name="salaryExpectationFixed" data-type="number" type="number" ${numberAttributes(item)} value="${esc(values.salaryExpectationFixed)}"><input name="salaryCurrency" data-type="text" class="currency-input" type="text" value="${esc(values.salaryCurrency??'')}" maxlength="3" pattern="[A-Z]{3}" placeholder="EUR" aria-label="Moneda del salario que pido, código de tres letras"></span></div>`;
  if(item==='custom_demographic_decline_consent')return `<div data-profile-legacy-consent hidden>${fieldHtml(item,defs[item],values[item])}</div>`;
  const html=fieldHtml(item,defs[item],values[item]);
  if(item==='gender')return `<div data-profile-gender${surveyMode(values.demographicSurveyParticipation)==='use_saved'?'':' hidden'}>${html}</div>`;
  return item==='name'||item==='workAuthorizations'||item.startsWith('custom_')&&aboutCustomGroup(item,defs[item])==='link'?`<div class="profile-field-wide">${html}</div>`:html;
 }).join('');
}
function surveyMode(value){return value===true?'use_saved':value===false?'decline':['decline','omit','use_saved'].includes(value)?value:null;}
function projectSurveyShown(form){const key='demographicSurveyParticipation';if(form.elements.namedItem(key)?.dataset.type==='choice'&&typeof form._shown[key]==='boolean')form._shown[key]=surveyMode(form._shown[key]);}
function permissionSummary(permissions,values){
 const allowed=permissions.filter(item=>values[item.key]===true),pending=permissions.filter(item=>values[item.key]!==true&&values[item.key]!==false).length;
 if(pending===permissions.length)return 'Sin decidir';
 if(allowed.length===permissions.length)return permissions.length>1?'Todos autorizados':allowed[0].short;
 // A short summary: names while they fit at a glance, a count beyond that.
 const main=!allowed.length?'Ninguno autorizado':allowed.length<=2?allowed.map(item=>item.short).join(' · '):`${allowed.length} de ${permissions.length} autorizados`;
 return pending?`${main} · ${pending} sin decidir`:main;
}
// Two independent sets share one native control: CV and contact clauses, and the
// steps the agent may take without asking in offers chosen for Auto-solicitud.
function permissionGroups(){return [
 {id:'profile-cv-permissions',title:'Permisos sobre mi CV y contacto',help:'Solo para la selección de las candidaturas que elijas.',items:window.StubbsJobsSetup.aboutOptions.permissions},
 {id:'profile-auto-permissions',title:'Permisos para Auto-solicitud',help:'Lo que el agente hace sin preguntarte. Lo no marcado detiene solo esa oferta. CAPTCHA, contraseñas y cuentas nuevas siempre son tuyos.',items:window.StubbsJobsSetup.autoApplyPermissions||[]}];}
function profilePermissionsField(group,values,formId=null){
 const permissions=group.items,id=group.id,state=key=>values[key]===true?'true':values[key]===false?'false':'',owner=formId?` form="${esc(formId)}"`:'';
 // One line per permission: a short title, its scope as help and a mark only while undecided.
 const option=item=>`<label class="profile-permission-option"><input type="hidden" name="${esc(item.key)}" data-type="boolean" value="${state(item.key)}"${owner}><input type="checkbox"${owner} data-profile-permission="${esc(item.key)}" aria-describedby="permission-help-${esc(item.key)}"${values[item.key]===true?' checked':''}><span class="permission-text"><span class="permission-title">${esc(item.label)}<small class="permission-pending" data-permission-state="${esc(item.key)}"${state(item.key)?' hidden':''}>Sin decidir</small></span><small class="permission-help" id="permission-help-${esc(item.key)}">${esc(item.help||'')}</small></span></label>`;
 const bulk=`<div class="permission-bulk"><button type="button"${owner} class="link-button" data-permission-all="${id}" data-permission-value="true">Autorizar todos</button><button type="button"${owner} class="link-button" data-permission-all="${id}" data-permission-value="false">Ninguno</button></div>`;
 return `<div class="profile-panel profile-panel--flush" role="group" aria-labelledby="${id}-label"><div class="profile-panel-head"><div class="profile-panel-title"><h3 id="${id}-label">${esc(group.title)}</h3><p>${esc(group.help)}</p></div>${bulk}</div><details id="${id}" class="work-authorizations profile-permissions" data-profile-permissions="${id}" open><summary aria-labelledby="${id}-label ${id}-value"><span id="${id}-value">${esc(permissionSummary(permissions,values))}</span></summary><div class="profile-permission-options" role="group" aria-labelledby="${id}-label">${permissions.map(option).join('')}</div></details></div>`;
}
function syncProfileOptions(form){
 if(form?.dataset.form!=='about')return;
 // Saved answers and permissions have their own cards in Mi perfil; their controls still belong to this form.
 const scope=form.id==='profile-about-form'&&main.querySelectorAll?main:form;
 const read=key=>{const field=form.elements.namedItem(key);return field?field.dataset.type==='boolean'?(field.value===''?null:field.value==='true'):field.dataset.type==='choice'&&['true','false'].includes(field.value)?field.value==='true':field.value||null:null;};
 const gender=form.querySelector?.('[data-profile-gender]');if(gender)gender.hidden=surveyMode(read('demographicSurveyParticipation'))!=='use_saved';
 for(const box of scope.querySelectorAll?.('[data-profile-detail]')||[]){const key=box.dataset.profileDetail,detail=window.StubbsJobsSetup.aboutOptions.details[key],content=box.querySelector('[data-profile-detail-content]');if(content){content.hidden=read(key)!==true&&sameFieldValue(read(detail),form._shown?.[detail]);if(!content.hidden)for(const field of content.querySelectorAll('textarea[data-auto-grow]'))growField(field);}}
 const previous=form.querySelector?.('[data-profile-legacy-consent]');if(previous)previous.hidden=sameFieldValue(read('custom_demographic_decline_consent'),form._shown?.custom_demographic_decline_consent);
 const values={};
 for(const group of permissionGroups()){
  const permissions=group.items.filter(item=>form.elements.namedItem(item.key));
  for(const item of permissions)values[item.key]=read(item.key);
  const summary=scope.querySelector?.(`#${group.id}-value`);if(summary)summary.textContent=permissionSummary(permissions,values);
 }
 for(const checkbox of scope.querySelectorAll?.('[data-profile-permission]')||[]){const key=checkbox.dataset.profilePermission,value=values[key];checkbox.checked=value===true;checkbox.indeterminate=value===null;const state=scope.querySelector(`[data-permission-state="${key}"]`);if(state)state.hidden=value!==null;}
}
function numberAttributes(key){
 if(key.startsWith('custom_'))return 'step="any" min="-1000000" max="1000000"';
 const limits={noticeDays:[0,365],maxTrips:[0,31],minimumFixed:[1,1000000000],salaryExpectationFixed:[1,1000000000],currentSalary:[1,1000000000]}[key];
 return limits?`step="1" min="${limits[0]}" max="${limits[1]}"`:'step="1" min="0"';
}
function searchCriteriaFields(values,keys,association=null,{flat=false}={}){
 const defs=sectionDefinitions('search');
 const field=key=>`<div${['targetRoles','keywords','searchPriorities','previousApplications'].includes(key)?' class="profile-field-wide"':''} id="search-field-${key}">${['minimumFixed','salaryExpectationFixed'].includes(key)?`<div class="field"><label for="profile-${key}">${key==='minimumFixed'?'Salario fijo mínimo (bruto anual)':'Salario que pido en formularios (bruto anual)'}</label><span class="amount-input"><input id="profile-${key}" name="${key}" data-type="number" type="number" ${numberAttributes(key)} value="${esc(values[key])}">${key==='minimumFixed'?`<input name="currency" data-type="text" class="currency-input" type="text" value="${esc(values.currency??'')}" maxlength="3" pattern="[A-Z]{3}" placeholder="EUR" aria-label="Moneda del salario, código de tres letras (por ejemplo EUR o USD)"${association?` form="${association}"`:''}>`:`<span data-salary-currency="1">${esc(values.currency??'')||'Por indicar'}</span>`}</span></div>`:fieldHtml(key,{...defs[key],...(['targetRoles','keywords'].includes(key)?{type:'longtext',rows:1,autoGrow:true,maxlength:3000}:key==='previousApplications'?{label:'Empresas a evitar',rows:1,autoGrow:true,maxlength:10000,placeholder:'Empresas a las que no quiero presentarme',controlId:'profile-previousApplications',help:'Común a todos tus perfiles de búsqueda.',descriptionId:'profile-previousApplications-help'}:{}),form:association},values[key])}${key==='previousApplications'?formErrors('search'):''}</div>`;
 const fields=keys.map(key=>{
  let html=field(key);
  // The form currency is edited beside its amount, not in a second field.
  if(key==='salaryExpectationFixed')html=html.replace(/<span data-salary-currency="1">[^<]*<\/span>/,`<input name="salaryCurrency" data-type="text" class="currency-input" type="text" value="${esc(values.salaryCurrency??'')}" maxlength="3" pattern="[A-Z]{3}" placeholder="EUR" aria-label="Moneda del salario para formularios, código de tres letras"${association?` form="${association}"`:''}>`);
  if(key==='salaryExpectationFixed')html=html.replace('</span></div></div>','</span><small class="helper">Lo que respondes en los formularios.</small></div></div>');
  if(key==='searchNotes')html=html.replace('<div id="search-field-','<div class="profile-field-wide" id="search-field-');
  return html;
 }).join('');return flat?fields:`<div class="form-grid">${fields}</div>`;
}
function newOpportunityForm(){
  return `<div class="form-wrap">${top('Añadir una oferta')}<form data-form="new" class="panel">${Object.entries({company:'Empresa',title:'Puesto',url:'Enlace de la oferta'}).map(([k,label])=>fieldHtml(k,{label,type:'text'},'')).join('')}<p class="helper">La oferta quedará guardada para que el agente la compruebe. Guardarla no la elige ni envía una solicitud.</p>${formErrors()}<div class="form-actions"><button type="submit" class="primary">Guardar oferta</button><span class="shortcut-hint" aria-hidden="true"><kbd>Ctrl</kbd><kbd>S</kbd></span></div></form></div>`;
}
function flowShell(tab,content){
 return `<div class="flow-view flow-view--${tab}">${content}</div>`;
}
function searchLocation(location,workMode){
 const raw=String(location||'').trim();
 if(workMode)return {location:raw,workMode,split:false};
 const match=raw.match(/^(Remoto habitual) desde (.+)$/i)||raw.match(/^(Remoto|Presencial|Híbrido|Hibrido) en (.+)$/i);
 return match?{location:match[2].trim(),workMode:match[1].trim(),split:true}:{location:raw,workMode:'',split:false};
}
function visibleSearchLocation(location,workMode,regions){
 const parsed=searchLocation(location,workMode),extra=String(regions||'').trim();
 return {...parsed,location:[parsed.location,extra].filter(Boolean).join('; '),mergedRegions:Boolean(extra)};
}
function mailboxPortal(id){return /^(outlook|gmail|hotmail|mail|correo|microsoft365|office365)(\W|_|$)/i.test(id);}
function coverageContent(coverage,context=model){
 const expected=context.publicSources||[],health=context.health||[];
 const pending=expected.filter(source=>!coverage.checked.some(item=>item.sourceId===source.id));
 const sourceLink=sourceUrl=>sourceUrl?`<a href="${url(sourceUrl)}" target="_blank" rel="noopener">Consultar fuente</a>`:'';
 const sourceRows=health.map(h=>{
  const information=h.coverage||{},method=h.method||information.method,scope=h.scope||information.scope||'Alcance no registrado';
  const state=!h.checkedAtUtc?'Sin revisión registrada':h.status!=='ok'||h.errors?.length?'Cobertura sin completar':method==='manual'?'Revisado según el alcance indicado':'Última revisión sin error registrado';
  const sourceUrl=h.sourceUrl||expected.find(source=>source.id===h.sourceId)?.url;
  const completeness=({returned_listing:'Listado recibido de la fuente',declared_count:'Listado recorrido según el recuento publicado',observed_pages:'Solo páginas observadas',partial:'Cobertura parcial',unsupported:'Fuente sin revisión compatible',error:'La revisión falló'})[information.completeness];
  return `<li><p>${esc(h.company||h.sourceId||'Fuente')} · ${esc(state)}</p><small>Comprobación: ${date(h.checkedAtUtc)} · Último éxito: ${date(h.lastSuccessUtc)}${h.checkedAtUtc&&h.checkedAtUtc!==h.lastSuccessUtc?' · Último intento: '+date(h.checkedAtUtc):''}</small><p>Alcance: ${esc(scope)}${completeness?' · '+esc(completeness):''}</p>${sourceLink(sourceUrl)}${h.errors?.length?`<p class="coverage-problems">${esc(h.errors.join('; '))}</p>`:''}</li>`;
 }).join('');
 const pendingNames=pending.length?`<p class="coverage-pending">Por revisar: ${esc(pending.map(item=>item.company||item.id).join(', '))}.</p>`:'';
 const access=context.portalAccess||{},portals=[...new Set([...(context.searchContext?.platforms||'').split(',').filter(Boolean),...Object.keys(access)])].filter(id=>id!=='glassdoor'&&!mailboxPortal(id));
 const portalRows=portals.length?`<section class="coverage-portals"><h3>Acceso a portales</h3><ul>${portals.map(id=>{const record=access[id];return `<li><strong>${esc(platformNames[id]||id)}</strong><span>${esc(record?.status==='ready'?'Acceso comprobado':record?.status==='login_required'?'Inicia sesión':record?.status==='blocked'?'Acceso bloqueado':'Sin comprobar')}</span>${record?`<small>${date(record.checkedAt)}</small>`:''}</li>`;}).join('')}</ul><p class="helper">El acceso comprobado no confirma que se hayan revisado las ofertas del portal.</p></section>`:'';
 return `<dl class="agent-checks"><div data-tone="${coverage.failed?'warn':coverage.good&&!coverage.pending?'ok':'neutral'}"><dt>Webs de empleo</dt><dd>${esc(coverage.summary)}${coverage.extra?` · ${esc(coverage.extra)}`:''}</dd></div></dl>${coverage.lastAt?`<p class="agent-source-date">Última comprobación: ${date(coverage.lastAt)}</p>`:''}${sourceRows?`<ul class="coverage-sources">${sourceRows}</ul>`:''}${pendingNames}${portalRows}`;
}
function reportKey(request){return request.id||'legacy:'+model.requests.indexOf(request);}
function reportRequest(key){return key?.startsWith('legacy:')?model.requests[Number(key.slice(7))]:model.requests.find(request=>request.id===key);}
function resultTitle(request){return request.type==='discovery'?window.StubbsJobsActivity.searchTitle(request):({review:'Solicitud revisada',investigate:'Oferta comprobada',change:'Cambios aplicados',send:'Solicitud enviada'})[request.type]||'Trabajo terminado';}
function activityCard(request){
 const job=request.opportunityId?getJob(request.opportunityId):null,search=request.type==='discovery';
 if(request.status==='queued'){
  // A queued search names the profile whose criteria it froze and can be cancelled before it starts.
  const identifier=request.searchProfileId||request.round?.searchProfileId;
  const profile=search?[...(model.searchProfiles||[]),...(model.deletedSearchProfiles||[])].find(p=>p.id===identifier)?.name||request.round?.searchProfileName:'';
  return activityRow({kind:'pending',title:[request.purpose==='followup'?'Comprobar tu candidatura':window.StubbsJobsWorkflow.names[request.type]||'Trabajo guardado',job?.company||profile].filter(Boolean).join(' · '),text:['Pendiente de iniciar',job?.title].filter(Boolean).join(' · '),anchor:reportKey(request),target:job?`data-job="${esc(job.id)}"`:search?'data-screen="solicitar"':'data-screen="perfil"',action:job?'Ver oferta':search?'Ver ofertas':'Ver perfil',
   extra:search?`<button class="link-button" data-cancel="${esc(request.id)}">Cancelar búsqueda</button>`:''});
 }
 let title=search?'Búsqueda realizada':request.type==='send'?'Solicitud enviada'+(job?' a '+job.company:''):request.type==='investigate'?(request.purpose==='followup'?'Candidatura comprobada':'Oferta revisada')+(job?': '+job.company:''):request.type==='review'?'Solicitud revisada'+(job?': '+job.company:''):job?'Solicitud actualizada: '+job.company:'Perfil actualizado';
 let text=search?window.StubbsJobsActivity.searchTitle(request).replace(/^Búsqueda realizada:?\s*/,''):request.type==='send'?activityRole(job):request.summary||request.result||'';
 if(search){
  const snapshot=window.StubbsJobsActivity.searchModel(request,model),coverage=window.StubbsJobsActivity.coverage(snapshot);
  const issue=(snapshot.health||[]).find(h=>h.errors?.length||h.checkedAtUtc&&h.status!=='ok');
  const issueText=String(issue?.errors?.[0]||'').replace(/:?\s*https?:\/\/\S+/gi,'').trim();
  if(issue)text=[text,[issue.company||issue.sourceId,issueText||'Revisión incompleta'].join(': ')].filter(Boolean).join(' · ');
  else if(coverage.pending)text=[text,'Hay webs pendientes'].filter(Boolean).join(' · ');
 }else if(request.type==='investigate'){
  text=/encaje parcial/i.test(request.summary||request.result||'')?'Encaje parcial':request.summary||job?.title||'';
 }else if(!job&&request.type==='change'&&/CVs? comprobados/i.test(text)&&/experiencia/i.test(text))text='Experiencia y CV revisados';
 const target=job?`data-job="${esc(job.id)}"`:search?'data-search-offers="1"':'data-screen="perfil"';
 const action=job?request.type==='send'||request.type==='review'||request.type==='change'?'Ver solicitud':'Ver oferta':search?'Ver ofertas':'Ver perfil';
 if(job&&request.type!=='send'){const position=activityRole(job);if(position&&!text.includes(position))text=[position,text].filter(Boolean).join(' · ');}
 return activityRow({kind:request.type,title,text,at:window.StubbsJobsWorkflow.taskAt(request),anchor:reportKey(request),target,action});
}
function activityRole(job){return String(job?.title||'').replace(/\s*[|·]\s*100%\s+Remoto\b.*$/i,'').trim();}
function activityRow({kind,title,text,anchor,target,action,extra=''}){
 const mark=kind==='send'?'check':kind==='discovery'?'search':kind==='interview'?'clock':'arrow-right';
 return `<li class="activity-card" data-kind="${esc(kind)}" data-anchor="activity-${esc(anchor)}"><span class="activity-icon" aria-hidden="true">${icon(mark)}</span><div class="activity-card-body"><strong>${esc(title)}</strong>${text?`<p>${esc(conciseText(text,120))}</p>`:''}</div><div class="activity-card-actions">${extra}<button class="link-button" ${target}>${esc(action)} ${icon('arrow-right')}</button></div></li>`;
}
function activityEvent(item){
 const job=item.opportunityId?getJob(item.opportunityId):null;
 const sent=/^(Envío confirmado|Solicitud enviada)/i.test(item.title),ready=/^(Paquete|Solicitud)/i.test(item.title),interview=/^Entrevista/i.test(item.title);
 const title=(sent?'Solicitud enviada':historyTitle(item))+(job?' · '+job.company:'');
 const target=job?`data-job="${esc(job.id)}"`:'data-screen="solicitar"';
 return activityRow({kind:sent?'send':interview?'interview':'review',title,text:activityRole(job),anchor:'event-'+item.id,target,action:sent||ready?'Ver solicitud':'Ver oferta'});
}
function activityGroup(group,day){
 const key=day.key+':'+group.key,id='activity-group-'+encodeURIComponent(key);
 let rows=group.members.map(member=>member.item.request?activityCard(member.item.request):activityEvent(member.item.event)).join('');
 if(group.key==='found'){
  rows=group.offerIds.map(id=>{
   const job=getJob(id);if(!job)return '';
   return activityRow({kind:'discovery',title:job.company||'Oferta registrada',text:job.title,anchor:'found-'+day.key+'-'+id,target:`data-job="${esc(job.id)}"`,action:'Ver oferta'});
  }).join('');
  const absent=group.offerIds.filter(id=>!getJob(id)).length+group.unlistedCount;
  if(absent)rows+=`<li class="activity-group-note">${absent} ${absent===1?'oferta sin detalle de posiciones conservado':'ofertas sin detalle de posiciones conservado'}.</li>`;
 }
 // Saved work waits for the person's agent; say how it starts without a copy button.
 if(group.key==='pending')rows+=`<li class="activity-group-note">Para iniciar ${group.count===1?'esta tarea':'estas tareas'}, pide «Continúa con Stubbs Jobs» en el chat de tu agente.</li>`;
 const reports=['found','search'].includes(group.key)?`<div class="activity-group-reports">${group.items.map(({request})=>`<button class="link-button" data-report="${esc(reportKey(request))}">Ver resultado de la búsqueda${group.items.length>1?' · '+date(window.StubbsJobsWorkflow.taskAt(request)):''} ${icon('arrow-right')}</button>`).join('')}</div>`:'';
 const repeated=group.items.length>group.members.length&&!['found','search'].includes(group.key)?'<p class="activity-group-note">Se muestra la última acción del día para cada oferta. Las anteriores siguen en su historial.</p>':'';
 return `<li class="activity-group-item"><details class="activity-group" id="${esc(id)}" data-activity-key="${esc(key)}" data-anchor="group-${esc(key)}"${openActivityGroups.has(key)?' open':''}><summary><span class="activity-group-icon" aria-hidden="true">${icon(group.icon)}</span><strong>${esc(group.label)}</strong><span class="activity-group-chevron" aria-hidden="true">${icon('chevron-down')}</span></summary><div class="activity-group-content"><ol class="activity-group-rows">${rows}</ol>${repeated}${reports}</div></details></li>`;
}
// The summary shows four totals with the Ofertas names and colours;
// each count opens its filter (sent ones open all offers).
function activityStatistics(){
 const stats=UI.stateCounts([...model.opportunities,...UI.archive(model)]);
 return `<section class="activity-statistics" aria-label="Totales de tus ofertas">${stats.map(stat=>`<button type="button" class="activity-stat" data-offer-state="${stat.state}" data-open-offer-state="${stat.filter}" aria-label="${esc(stat.label)}: ${stat.value}. Ver en Ofertas"><span class="activity-stat-heading">${icon(stat.icon,'offer-state-icon','solid')}<span>${esc(stat.label)}</span></span><strong class="activity-stat-value">${stat.value.toLocaleString('es-ES')}</strong><span class="activity-stat-note">${esc(stat.note)}</span></button>`).join('')}</section>`;
}
function recentActivity(){
 const Activity=window.StubbsJobsActivity,timeZone=Intl.DateTimeFormat().resolvedOptions().timeZone;
 const days=Activity.days(Activity.entries(model,{allSteps:true}),timeZone);
 if(!days.length)return '<p class="muted activity-empty">Aquí aparecerán los resultados de tus búsquedas y solicitudes.</p>';
 const shown=days.slice(0,activityDayLimit),year=new Intl.DateTimeFormat('en',{year:'numeric',timeZone}).format(new Date());
 const label=day=>{
  const parsed=tableTimestamp(day.at);if(parsed===null)return 'Fecha sin confirmar';
  const dateOnly=/^\d{4}-\d{2}-\d{2}$/.test(day.at||''),at=dateOnly?Date.parse(day.at+'T12:00:00Z'):parsed,zone=dateOnly?'UTC':timeZone;
  return new Intl.DateTimeFormat('es-ES',{day:'numeric',month:'short',year:new Intl.DateTimeFormat('en',{year:'numeric',timeZone:zone}).format(at)===year?undefined:'numeric',timeZone:zone}).format(at);
 };
 // Recent days read as Hoy/Ayer with the weekday beside them, as a calendar would.
 const dayKey=at=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone}).format(at);
 const today=dayKey(new Date()),yesterday=dayKey(new Date(Date.now()-86400000));
 const heading=day=>{
  const key=/^\d{4}-\d{2}-\d{2}$/.test(day.key||'')?day.key:null,when=key?Date.parse(key+'T12:00:00Z'):null;
  const weekday=when===null?'':new Intl.DateTimeFormat('es-ES',{weekday:'long',timeZone:'UTC'}).format(when);
  const capital=text=>text?text[0].toLocaleUpperCase('es')+text.slice(1):'';
  const relative=key===today?'Hoy':key===yesterday?'Ayer':'';
  return relative?{main:relative,note:capital(weekday)+', '+label(day)}:{main:label(day),note:capital(weekday)};
 };
 return '<ol class="activity-days">'+shown.map(day=>{const title=heading(day);return `<li class="activity-day" data-anchor="day-${esc(day.key)}"><h2 class="activity-day-label"><time datetime="${esc(day.key==='unknown'?'':day.key)}">${esc(title.main)}</time>${title.note?`<span class="activity-weekday">${esc(title.note)}</span>`:''}</h2><ol class="activity-cards">${Activity.dailyGroups(day,model).map(group=>activityGroup(group,day)).join('')}</ol></li>`;}).join('')+'</ol>'+(days.length>shown.length?'<button class="activity-older" data-more-activity="1">Ver anteriores</button>':'');
}
function activityWork(){return window.StubbsJobsExplanations.work(model,{getJob,esc,date,conciseText});}
function agentPage(){
 return flowShell('agente',`<div class="agent-view"><h1 id="agent-activity-title">Resumen</h1>${activityStatistics()}${recentActivity()}</div>`);
}
function activityReport(){
 if(selected?.startsWith('event:')){
  const item=activityRecord(selected.slice(6));
  if(!item)return top('Cambio no disponible');
  const job=getJob(item.opportunityId),info=window.StubbsJobsActivity.details(item,model),pack=info?.package;
  const source=info?.sourceUrl&&/^https?:\/\//i.test(info.sourceUrl)?`<a href="${esc(info.sourceUrl)}" target="_blank" rel="noopener">Ver fuente</a>`:'';
  const content=info?.kind==='sent'?`<h2>Documentos enviados</h2><p><a href="${esc(pack.cvUrl)}" target="_blank" rel="noopener">Abrir CV enviado</a>${UI.presentationVisible(pack.payload)?` · <a href="${esc(pack.messageUrl)}" target="_blank" rel="noopener">Ver presentación</a>`:''}</p>`
    :['followup','availability'].includes(info?.kind)?`<h2>${info.kind==='followup'?'Tu solicitud':'El anuncio'}</h2><p>${esc(historyTitle(item))}.</p>${source?`<p>${source}</p>`:''}`
    :info?.kind==='change'?`<h2>Qué cambió</h2><ul>${info.fields.map(field=>`<li>${esc(field)}</li>`).join('')}</ul>`:'<p>Cambio guardado en el historial.</p>';
  const related=(item.sourceIds||[]).slice(1).map(id=>(model.history||[]).find(h=>h.id===id)).filter(Boolean);
  return `<div class="detail-wrap activity-report">${top(esc(historyTitle(item)))}<p class="muted">${date(item.at)}</p>${job?`<button data-job="${esc(job.id)}">Ver oferta</button>`:''}<section class="panel">${content}${related.length?`<h2>Otros apuntes de esta acción</h2>${timeline(related,Infinity,false)}`:''}${(model.undo||[]).some(u=>u.id===item.id)?`<button data-undo="${esc(item.id)}">Deshacer</button>`:''}</section></div>`;
 }
 const request=reportRequest(selected);if(!request)return top('Resultado no disponible');
 const job=request.opportunityId?getJob(request.opportunityId):null,search=request.type==='discovery';
 const snapshot=search?window.StubbsJobsActivity.searchModel(request,model):null;
 const requestAt=window.StubbsJobsWorkflow.taskAt(request);
 return `<div class="detail-wrap activity-report"><section class="panel activity-report-heading"><div>${top(esc(job?job.company:resultTitle(request)))}${job?`<p class="activity-result-label">${esc(resultTitle(request))}</p>`:''}<p class="muted">${date(requestAt)}</p></div>${job?`<button data-job="${esc(job.id)}">Ver oferta ${icon('arrow-up-right')}</button>`:''}</section><section class="panel"><h2>Resultado</h2>${request.summary?`<p>${esc(request.summary)}</p>`:''}${!request.summary?`<p>${esc(resultTitle(request))}</p>`:''}${request.instructions?.length?`<h3>Tu petición</h3><p class="note-text">${esc(request.instructions.map(item=>item.text).join('\n'))}</p>`:''}</section>${search?`<section class="panel"><h2>Qué se ha revisado</h2>${coverageContent(window.StubbsJobsActivity.coverage(snapshot),snapshot)}${snapshot.sourceConfigurationError?`<p class="activity-issue">${esc(snapshot.sourceConfigurationError)}</p>`:''}${snapshot.legacy?'<p class="helper">Este resultado conserva el alcance registrado en esa búsqueda.</p>':''}<p class="helper">Consultar listados no acredita una revisión exhaustiva de sus ofertas.</p></section>`:''}</div>`;
}
function conciseText(value,limit){const text=String(value||'').replace(/\s+/g,' ').trim();return text.length<=limit?text:text.slice(0,limit-1).replace(/\s+\S*$/,'').trimEnd()+'…';}
function groupedActivity(items){return window.StubbsJobsActivity.grouped(items,model);}
function activityItem(item,withCompany=true,relative=false){
 const title=historyTitle(item),hasDetail=window.StubbsJobsActivity.details(item,model),undo=(model.undo||[]).some(u=>u.id===item.id);
 const heading=hasDetail?`<button class="link-button activity-event-link" data-report="event:${esc(item.id)}" aria-label="Ver detalle: ${esc(title)}">${esc(title)}</button>`:esc(title);
 return `<li><strong>${heading}</strong>${withCompany&&item.opportunityId?` · <button class="link-button" data-job="${esc(item.opportunityId)}">${esc(getJob(item.opportunityId)?.company||item.opportunityId)}</button>`:''}${undo?` · <button class="link-button" data-undo="${esc(item.id)}">Deshacer</button>`:''}<small>${relative?activityTime(item.at):date(item.at)} · ${esc(['Usuario','Usuario'].includes(item.actor)?'Tú':item.actor||'Registro')}</small></li>`;
}
function searchActivity(items,limit=Infinity,withCompany=true){return timeline(groupedActivity(items),limit,withCompany);}
let entryLimit=30;
async function openSearchOffers(state='todas'){
 flowFilters.solicitar=state;tableState.solicitar.filters={};tableSelection.clear();
 viewMemory['solicitar/']={...(viewMemory['solicitar/']||{}),filterText:'',scroll:0};
 await setScreen('solicitar');
}
function flowToolbar(tab,choices){
 return `<div class="offer-toolbar" role="region" aria-label="Filtros y acciones de ofertas"><div class="flow-filter-choices" role="group" aria-label="Filtrar ofertas">${choices.map(([value,label,count])=>`<button data-flow-filter="${value}" data-filter-tab="${tab}" aria-pressed="${flowFilters[tab]===value}">${label} <span class="filter-count">${count}</span></button>`).join('')}</div><div class="offer-toolbar-actions">${bulkToolbar()||`${bulkSelectionMode?bulkExitButton():choices[0]?.[2]===0?'':'<button data-bulk-mode="1" aria-pressed="false">Seleccionar varias</button>'}`}</div></div>`;
}
function bulkExitButton(){return `<button class="icon-button bulk-clear" data-bulk-clear="1" aria-label="Salir de la selección múltiple" title="Salir de la selección múltiple (Esc)">${icon('close')}</button>`;}
function requestButtonContent(mode,label=requestModes[mode].label){return `<span class="request-icon" aria-hidden="true">${icon(requestModes[mode].icon)}</span>${esc(label)}`;}
const autoHelp='El agente la enviará sin esperar tu aprobación, con tu cuenta del portal. En Mi perfil › Permisos eliges qué puede aceptar sin preguntarte. Algunos portales, como LinkedIn, no permiten automatizar y pueden restringir la cuenta.';
function selectionButtons(j){return `<button class="primary request-button" data-select="${esc(j.id)}" data-selection-mode="review" title="Revisarás la solicitud antes de que se envíe.">${requestButtonContent('review')}</button><button class="primary request-button" data-select="${esc(j.id)}" data-selection-mode="auto" title="${esc(autoHelp)}" aria-describedby="offer-auto-help-${esc(j.id)}">${requestButtonContent('auto')}</button><span id="offer-auto-help-${esc(j.id)}" class="sr-only">${esc(autoHelp)}</span>`;}
function bulkOptions(j){
 if(j.historical)return [];
 const step=UI.step(j),options=[],category=UI.offerState(j).key;
 if(category==='por-solicitar'&&!j.selection?.selected)options.push(['discard','Descartar']);
 if(['en-espera','en-proceso'].includes(category)&&j.sent)options.push(['close','Cerrar seguimiento']);
 if(step.action==='recovery')return [['recovery:'+step.cta,step.cta]];
 if(!active(j))return [];
 if(UI.canChoose(j))options.push(['select-review',requestModes.review.label],['select-auto',requestModes.auto.label]);
 else if(step.action==='review')options.push(['review','Revisar solicitudes']);
 else if(step.action==='answers')options.push(['responses','Responder']);
 else if(step.action==='resolve')options.push(['change','Aclarar ofertas']);
 else if(!step.cta&&!j.selection?.selected&&!j.sent&&!j.requests.some(r=>!window.StubbsJobsWorkflow.task(r).superseded&&['queued','running','blocked','interrupted'].includes(r.status))&&!['No','Resolver conflicto'].includes(j.apply))options.push(['investigate','Pedir comprobación']);
 const sending=j.requests.some(r=>r.type==='send'&&r.status==='running');
 if(j.selection?.selected&&!j.sent&&!sending)options.push(['unselect','Retirar selección']);
 if(UI.approved(j)&&!j.sent)options.push(['revoke','Retirar permiso de envío']);
 return options;
}
function bulkJobs(){return [...tableSelection].map(getJob).filter(Boolean);}
function eligibleBulkJobs(key,jobs=bulkJobs()){return key==='archive'?jobs:jobs.filter(j=>bulkOptions(j).some(([option])=>option===key));}
function bulkLabel(label,count){return label+' ('+count+')';}
function finishBulk(ids,total,message='Aplicado a',remainingText='sin cambios'){
 ids.forEach(id=>tableSelection.delete(id));
 const remaining=Math.max(0,total-ids.length);
 return message+' '+ids.length+(ids.length===1?' oferta':' ofertas')+(remaining?'; '+remaining+' '+remainingText+'.':'.');
}
function bulkToolbar(){
 const jobs=bulkJobs();if(!jobs.length)return '';
 const priority=['select-review','select-auto','review','responses','change','investigate'],labels=new Map(jobs.flatMap(bulkOptions));
 const options=[...labels].map(([key,label])=>({key,label,ids:eligibleBulkJobs(key,jobs).map(j=>j.id)}));
 const rank=o=>priority.indexOf(o.key)<0?99:priority.indexOf(o.key);
 // Both request modes sit together at the same level; other actions follow as secondary buttons.
 const requests=options.filter(o=>['select-review','select-auto'].includes(o.key)).sort((a,b)=>rank(a)-rank(b));
 const primary=requests.length?null:options.filter(o=>!['unselect','revoke'].includes(o.key)).sort((a,b)=>b.ids.length-a.ids.length||rank(a)-rank(b))[0];
 const ordered=[...requests,...(primary?[primary]:[]),...options.filter(o=>o!==primary&&!requests.includes(o))];
 const button=(o,mainAction=false)=>{
  const mode=o.key==='select-review'?'review':o.key==='select-auto'?'auto':null,label=bulkLabel(o.label,o.ids.length);
  const scope=`Alcance: ${o.ids.length} de ${jobs.length} ${jobs.length===1?'oferta marcada':'ofertas marcadas'}.`;
  const help=mode==='auto'?' Permite enviar estas ofertas tras las comprobaciones, sin tu aprobación final. El agente usará tu cuenta del portal: algunos portales, como LinkedIn, prohíben la automatización y pueden restringir tu cuenta.':mode==='review'?' Revisarás las solicitudes y autorizarás su envío final.':'';
  return `<button class="${mode?'primary request-button':mainAction?'primary':''}" data-bulk-action="${esc(o.key)}" data-bulk-targets="${esc(JSON.stringify(o.ids))}" data-bulk-total="${jobs.length}" title="${esc(scope+help)}" aria-label="${esc(label+'. '+scope)}"${mode==='auto'?' aria-describedby="bulk-auto-help"':''}>${mode?requestButtonContent(mode,label):esc(label)}</button>`;
 };
 return `<div class="bulk-actions" role="region" aria-label="Acciones para ${jobs.length} ${jobs.length===1?'oferta marcada':'ofertas marcadas'}">${ordered.map(o=>button(o,o===primary)).join('')}${bulkExitButton()}<span id="bulk-auto-help" class="sr-only">Permite enviar estas ofertas tras las comprobaciones, sin tu aprobación final.</span></div>`;
}
async function bulkAction(key,shownIds=null,total=tableSelection.size){
 if(actionBusy)return false;
 const ids=shownIds||eligibleBulkJobs(key).map(j=>j.id);
 if(!ids.length)return false;
 let jobs=ids.map(getJob);
 const valid=()=>jobs.every(j=>j&&tableSelection.has(j.id))&&eligibleBulkJobs(key,jobs).length===ids.length;
 if(!valid())throw new Error('Cambió una de las ofertas indicadas. Revisa la selección antes de continuar.');
 if(['review','responses','change'].includes(key)){
  const params=new URLSearchParams({brief:'1'});ids.forEach(id=>params.append('case',id));
  if(!acceptState(await api('/api/state?'+params)))throw new Error('Actualiza las ofertas antes de continuar.');
  jobs=ids.map(getJob);
  if(actionBusy||!valid())throw new Error('Cambió una de las ofertas indicadas. Revisa la selección antes de continuar.');
 }
 if(key==='review'){bulkReviewSnapshots=structuredClone(jobs);bulkReviewTotal=total;await setScreen('revision-multiple');return true;}
 if(['responses','change'].includes(key)){
  const draftKey='stubbs_jobs-bulk:'+key+':'+jobs.map(j=>j.id).sort().join(','),fingerprints=jobs.map(j=>j.id+':'+j.fingerprint).sort().join('|');
  let saved;try{saved=JSON.parse(draftStorage.getItem(draftKey));}catch{}
  bulkEditor={kind:key,jobs:structuredClone(jobs),total,values:saved?.fingerprints===fingerprints?saved.values:{},draftKey,fingerprints};
  await setScreen('edicion-multiple');return true;
 }
 if(key.startsWith('recovery:')){
  const message=jobs.map(j=>window.StubbsJobsRecovery.taskPrompt(model.workspacePath,j.requests.find(r=>r.id===UI.step(j).requestId))).join('\n\n');
  try{await navigator.clipboard.writeText(message);toast('Petición conjunta copiada. Pégala en el chat del agente.');}catch{await confirmAction('Mensaje para tu agente',message);}return true;
 }
 if(await action({kind:'ui-bulk-action',action:key,targets:jobs.map(j=>({id:j.id})),expectedRevision:model.revision})){
  const resultMessage=finishBulk(ids,total,key==='archive'?'Archivo aplicado a':'Aplicado a');
  changeToast(resultMessage+(key==='select-auto'||key==='select-review'?' Para iniciar la preparación, pide «Continúa con Stubbs Jobs» en el chat del agente.':''));render(true);return true;
 }return false;
}
function flowRecord(j,kind){
 const category=UI.offerState(j);
 const attention=UI.offerAttention(j),tone=attention?'blocked':['archivadas','rechazadas'].includes(category.key)?'past':j.sent?'sent':UI.canChoose(j)?'action':'working';
 const latest=j.lastActivityAt||(model.history||[]).filter(h=>h.opportunityId===j.id).reduce((at,h)=>{const next=tableTimestamp(h.at),previous=tableTimestamp(at);return next!==null&&(previous===null||next>previous)?h.at:at;},'');
 return {j,kind,category,status:category.label,attention,tone,activityAt:latest||j.sent?.at||historicalDate(j.lastActivityLabel),activity:j.historical?j.lastActivityLabel||'—':latest||j.sent?.at?date(latest||j.sent.at):'—'};
}
const fold=window.StubbsJobsFormatting.fold;
const displayCase=window.StubbsJobsFormatting.displayCase;
const formatOptions=()=>({currency:model?.searchContext?.currency||'EUR',timeZone:undefined});
const salaryNumber=value=>window.StubbsJobsFormatting.salaryNumber(value,formatOptions());
const salaryInfo=value=>window.StubbsJobsFormatting.salaryInfo(value,formatOptions());
function salaryTableLabel(info){
 if(info.kind==='missing'||/^no publicad[oa]\b/i.test(info.raw)&&!/[0-9]/.test(info.raw))return '—';
 if(info.kind==='unknown'&&!/[0-9]/.test(info.raw))return 'Sin cifra';
 return info.label;
}
function salaryCell(j){
 const info=salaryInfo(j.salary),label=salaryTableLabel(info),note=info.note&&!['Sin cifra anual comparable','Mínimo desconocido','Máximo desconocido'].includes(info.note)?`<small>${esc(info.note)}</small>`:'';
 return `<div class="salary-cell" title="${esc(info.raw||label)}"><span>${cellText(label)}</span>${note}</div>`;
}
const tableTimestamp=window.StubbsJobsFormatting.tableTimestamp;
const tableDate=value=>window.StubbsJobsFormatting.tableDate(value,formatOptions());
const relativeTime=(value,now=Date.now())=>window.StubbsJobsFormatting.relativeTime(value,now,formatOptions());
const discoveryTime=(value,now=Date.now())=>window.StubbsJobsFormatting.discoveryTime(value,now,formatOptions());
function activityTime(value){return value?`<time data-activity-at="${esc(value)}" datetime="${esc(value)}" title="${esc(date(value))}">${esc(relativeTime(value))}</time>`:'';}
function updateActivityTimes(){main.querySelectorAll('[data-activity-at]').forEach(element=>{element.textContent=relativeTime(element.dataset.activityAt);});main.querySelectorAll('[data-found-at]').forEach(element=>{element.textContent=discoveryTime(element.dataset.foundAt);});}
const historicalDate=window.StubbsJobsFormatting.historicalDate;
const tableText=window.StubbsJobsFormatting.tableText;
const tableDateKeys=new Set(['firstSeen','deadline','activity']);
const firstSeenDay=job=>window.StubbsJobsFormatting.discoveryDay(job.firstSeenAt,formatOptions());
function tableValue(record,key){
 const j=record.j;
 if(key==='company')return j.company||'';
 if(key==='title')return j.title||'';
 if(key==='country')return tableText(j.country,'country');
 if(key==='mode')return tableText(j.workMode||(j.conditions?.['Remoto España']==='Sí'?'Remoto':j.conditions?.['Remoto España']==='Contradicción'?'Por aclarar':null),'mode');
 if(key==='contract')return tableText(j.contract||({Sí:'Indefinido',Contradicción:'Por aclarar'})[j.conditions?.Indefinido],'contract');
 if(key==='schedule'){
  const shown=tableText(j.schedule,'schedule');
  const review=j.scheduleChecks?.[offerProfileFilter||j.searchProfileId];
  if(review==='violation'||!review&&j.minimums?.violations?.some(item=>item.key==='Horario'&&!item.unconfirmed))return 'No cumple';
  // A required schedule that the advertisement does not confirm discards the offer.
  if(review==='unknown'||!review&&j.minimums?.violations?.some(item=>item.key==='Horario'&&item.unconfirmed))return shown==='—'?'Sin confirmar':'Sin confirmar · '+shown;
  return shown==='—'?'Por confirmar':shown;
 }
 if(key==='firstSeen')return discoveryTime(j.firstSeenAt);
 if(key==='salary')return salaryTableLabel(salaryInfo(j.salary));
 if(key==='deadline')return tableDate(j.externalDeadline);
 if(key==='activity')return record.activityAt?relativeTime(record.activityAt):record.activity;
 return record.status;
}
function cellText(value){return value==='—'?'<span class="empty-value" aria-hidden="true">—</span><span class="sr-only">Sin dato</span>':esc(value);}
function tableColumns(){return [['firstSeen','Encontrada'],['company','Empresa'],['title','Puesto'],['country','País'],['mode','Modalidad'],['contract','Contrato'],['schedule','Horario'],['salary','Salario'],['status','Estado']];}
// Preserve any activity filter/order already applied in this open page, with a clearable chip.
function tableFilterColumns(){return [...tableColumns(),['activity','Actividad'],['deadline','Plazo']];}
function tableDateValue(record,key){return key==='firstSeen'?firstSeenDay(record.j):key==='deadline'?record.j.externalDeadline:key==='activity'?record.activityAt:null;}
function tableFilterValue(record,key){
 if(tableDateKeys.has(key)){const at=tableTimestamp(tableDateValue(record,key));if(at!==null)return String(at);}
 return tableValue(record,key);
}
function tableFilterLabel(record,key){
 const value=tableDateValue(record,key);
 return value?date(value):['company','title'].includes(key)?displayCase(tableValue(record,key)):tableValue(record,key);
}
function defaultTableOrder(tab){
 return tab==='solicitar'?({archivadas:'archived','en-espera':'sent','en-proceso':'activity',logradas:'achieved',rechazadas:'rejected'})[flowFilters[tab]]||'firstSeen':'firstSeen';
}
function defaultTableTimestamp(record,key){
 const j=record.j;
 return tableTimestamp(key==='archived'?j.lifecycle?.closure?.at||j.archivedAt||j.discardedAt:key==='discarded'?j.discardedAt||j.archivedAt:key==='sent'?j.sent?.at||j.appliedAt:key==='achieved'?j.lifecycle?.achievedAt:key==='closed'?j.lifecycle?.closure?.at||j.archivedAt:key==='rejected'?j.rejectedAt||(j.archiveOutcome==='rejected'?j.archivedAt:null):j.firstSeenAt);
}
function sortedFilteredRecords(tab,records){
 const state=tableState[tab],columns=tableFilterColumns();
 const visible=records.filter(record=>columns.every(([key])=>!Object.hasOwn(state.filters,key)||state.filters[key].map(value=>key==='salary'&&/^(no publicado|[-—])$/i.test(value)?'—':key==='schedule'&&['Por confirmar','Sin confirmar','No cumple'].includes(value)?value:['country','mode','contract','schedule'].includes(key)?tableText(value,key):value).includes(tableFilterValue(record,key))));
 if(!state.sort){
  const key=defaultTableOrder(tab);
  return visible.sort((a,b)=>{const left=defaultTableTimestamp(a,key),right=defaultTableTimestamp(b,key);return left===null?right===null?0:1:right===null?-1:right-left;});
 }
 const key=state.sort,collator=new Intl.Collator('es',{numeric:true,sensitivity:'base'});
 visible.sort((a,b)=>{
  let left=key==='salary'?salaryNumber(a.j.salary):key==='firstSeen'?tableTimestamp(a.j.firstSeenAt):tableDateKeys.has(key)?tableTimestamp(tableDateValue(a,key)):tableValue(a,key);
  let right=key==='salary'?salaryNumber(b.j.salary):key==='firstSeen'?tableTimestamp(b.j.firstSeenAt):tableDateKeys.has(key)?tableTimestamp(tableDateValue(b,key)):tableValue(b,key);
  if(left===null||left==='')return right===null||right===''?0:1;
  if(right===null||right==='')return -1;
  return (typeof left==='number'?left-right:collator.compare(left,right))*state.direction;
 });
 return visible;
}
function flowRow(record,selectable=bulkSelectionMode){
 const {j,status,tone}=record;
 const state=tableValue(record,'status');
 return `<tr class="flow-table-row" data-tone="${tone}" data-anchor="job-${esc(j.id)}" data-job-row="${esc(j.id)}" data-offer-state="${record.category.key}">${selectable?`<td class="selection-cell"><label class="offer-select-control"><input type="checkbox" id="bulk-offer-${esc(j.id)}" data-bulk-select="${esc(j.id)}" aria-label="Marcar ${esc(j.company)}: ${esc(j.title)}" ${tableSelection.has(j.id)?'checked':''}></label></td>`:''}<td>${firstSeenDay(j)?`<time data-found-at="${esc(j.firstSeenAt)}" datetime="${esc(j.firstSeenAt)}" title="Primera detección: ${esc(date(j.firstSeenAt))}">${esc(tableValue(record,'firstSeen'))}</time>`:cellText('—')}</td><td class="company-cell"><div class="company-selection"><button class="table-job-link company-identity" data-job="${esc(j.id)}" title="${esc(j.company)}" aria-label="Abrir ficha de ${esc(j.company)}: ${esc(j.title)}"><span class="company-name">${esc(displayCase(j.company))}</span>${icon('chevron-right','company-open')}</button></div></td><td title="${esc(j.title)}"><span class="offer-title-text">${esc(displayCase(j.title))}</span></td><td>${cellText(tableValue(record,'country'))}</td><td>${cellText(tableValue(record,'mode'))}</td><td>${cellText(tableValue(record,'contract'))}</td><td title="${esc(j.schedule||'Sin dato')}">${cellText(tableValue(record,'schedule'))}</td><td>${salaryCell(j)}</td><td title="${esc(status)}${record.attention?' · Por atender':''}"><span data-offer-state="${record.category.key}" class="flow-status">${icon(record.category.icon,'offer-state-icon','solid')}${esc(state)}</span>${record.attention?'<span class="offer-attention-indicator">Por atender</span>':''}</td></tr>`;
}
function workflowTable(tab,records,empty){
 const selectable=tab==='solicitar'&&bulkSelectionMode;
 const state=tableState[tab],columns=tableColumns(tab),visible=sortedFilteredRecords(tab,records),limit=Math.max(100,historyLimit),shown=visible.slice(0,limit);
 const effectiveSort=state.sort||(defaultTableOrder(tab)==='firstSeen'?'firstSeen':''),effectiveDirection=state.sort?state.direction:-1;
 if(tab==='solicitar'){const ids=new Set(visible.map(r=>r.j.id));for(const id of tableSelection)if(!ids.has(id))tableSelection.delete(id);}
 state.records=records;state.choices={};
 const emptyMessage=records.length&&!visible.length?'Ninguna oferta coincide con estos filtros.':empty;
 const selectHead=selectable?`<th scope="col" class="selection-cell"><span class="sr-only">Seleccionar ofertas</span><label class="offer-select-control"><input type="checkbox" id="bulk-all" data-bulk-select-all="1" aria-label="Marcar ofertas visibles" ${shown.length&&shown.every(r=>tableSelection.has(r.j.id))?'checked':''} ${shown.length?'':'disabled'}></label></th>`:'';
 const head=columns.map(([key,label])=>{
  const active=Object.hasOwn(state.filters,key),direction=effectiveSort===key&&effectiveDirection===1?-1:1;
  return `<th scope="col" aria-sort="${effectiveSort===key?effectiveDirection===1?'ascending':'descending':'none'}" data-column="${key}"><div class="column-heading"><button type="button" class="column-title" data-table-sort="${key}" data-table-tab="${tab}" data-table-direction="${direction}" aria-label="Ordenar ${label.toLowerCase()} ${direction===1?'en orden ascendente':'en orden descendente'}">${label}${effectiveSort===key?` <span class="sort-indicator" aria-hidden="true">${effectiveDirection===1?'↑':'↓'}</span>`:''}</button><details class="column-menu" data-menu-key="${key}" data-menu-tab="${tab}" data-filtered="${active}"><summary aria-label="Filtrar ${label.toLowerCase()}" title="Filtrar ${label.toLowerCase()}"><svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M3 5h14l-5.5 6v4l-3 2v-6z"/></svg></summary><div class="column-menu-panel" popover="manual"><input type="search" data-table-option-search="1" aria-label="Buscar valores de ${label.toLowerCase()}" placeholder="Buscar valores"><div class="column-select-actions"><button type="button" data-table-select-visible="all" data-table-tab="${tab}" data-table-key="${key}">Seleccionar visibles</button><button type="button" data-table-select-visible="none" data-table-tab="${tab}" data-table-key="${key}">Quitar visibles</button></div><div class="column-menu-values"></div></div></details></div></th>`;
 }).join('');
 const filterColumns=tableFilterColumns(),filters=filterColumns.filter(([key])=>Object.hasOwn(state.filters,key));
 const applied=filters.length||state.sort?`<div class="active-filters" role="group" aria-label="Filtros y orden aplicados">${filters.map(([key,label])=>{const values=state.filters[key],names=values.map(value=>{const record=records.find(record=>tableFilterValue(record,key)===value);return record?tableFilterLabel(record,key):tableDateKeys.has(key)&&Number.isFinite(Number(value))?date(new Date(Number(value)).toISOString()):value;}),description=names.length?names.slice(0,2).join(', ')+(names.length>2?' y '+(names.length-2)+' más':''):'Ningún valor';return `<button type="button" data-clear-column="${key}" data-table-tab="${tab}" title="${esc(names.join(', ')||description)}" aria-label="Quitar filtro de ${label.toLowerCase()}: ${esc(description)}">${esc(label)}: ${esc(description)}<span aria-hidden="true">×</span></button>`;}).join('')}${state.sort?`<button type="button" class="table-order" data-clear-order="${tab}" aria-label="Quitar orden por ${esc(filterColumns.find(([key])=>key===state.sort)?.[1]||state.sort)}">Orden: ${esc(filterColumns.find(([key])=>key===state.sort)?.[1]||state.sort)} ${state.direction===1?'↑':'↓'}<span aria-hidden="true">×</span></button>`:''}</div>`:'';
 return `${applied}<p class="table-scroll-hint">Desliza la tabla. La empresa permanece visible; abre su ficha para ver todos los datos.</p><div class="workflow-table-wrap" role="region" aria-label="Ofertas; desplázate horizontalmente para ver todas las columnas" tabindex="0"><table class="workflow-table${selectable?' workflow-table-selectable':''}"><caption class="sr-only">Ofertas y solicitudes guardadas. Usa las opciones de cada columna para filtrar y ordenar.</caption><thead><tr>${selectHead}${head}</tr></thead><tbody>${shown.length?shown.map(record=>flowRow(record,selectable)).join(''):`<tr><td colspan="${columns.length+(selectable?1:0)}" class="table-empty">${emptyMessage}${filters.length?`<p><button data-clear-table="${tab}">Mostrar todas las ofertas de este estado</button></p>`:''}</td></tr>`}</tbody></table></div><div class="table-footer"><span>${visible.length>shown.length?`${shown.length} de `:''}${visible.length} ${visible.length===1?'oferta':'ofertas'}${visible.length!==records.length?` de ${records.length}`:''}</span>${!state.sort?`<span class="table-default-order">Orden: ${({firstSeen:'búsqueda',archived:'archivo',sent:'solicitud',activity:'actividad',achieved:'puesto ofrecido',rejected:'rechazo'})[defaultTableOrder(tab)]}, de más reciente a más antiguo</span>`:''}${filters.length?`<button class="link-button" data-clear-table="${tab}">Limpiar filtros</button>`:''}${visible.length>limit?'<button data-more-history="1">Cargar más</button>':''}</div>`;
}
function columnMenuFor(element){return element?.closest?.('.column-menu')||element?.closest?.('.column-menu-panel')?._columnMenu||null;}
function columnPanel(menu){return menu?._panel||menu?.querySelector('.column-menu-panel');}
function columnCatalog(tab,key){
 const state=tableState[tab],labels=Object.fromEntries((state.records||[]).map(record=>[tableFilterValue(record,key),tableFilterLabel(record,key)])),collator=new Intl.Collator('es',{numeric:true,sensitivity:'base'});
 for(const value of state.filters[key]||[])if(!Object.hasOwn(labels,value))labels[value]=tableDateKeys.has(key)&&Number.isFinite(Number(value))?date(new Date(Number(value)).toISOString()):value;
 const values=Object.keys(labels).sort((a,b)=>{if(!tableDateKeys.has(key))return collator.compare(a,b);const left=Number(a),right=Number(b);return Number.isFinite(left)?Number.isFinite(right)?left-right:-1:Number.isFinite(right)?1:collator.compare(a,b);});state.choices[key]=values;
 return {values,labels};
}
function populateColumnMenu(menu){
 const panel=columnPanel(menu);if(!panel||panel._catalogReady)return;
 const tab=menu.dataset.menuTab,key=menu.dataset.menuKey,state=tableState[tab],catalog=columnCatalog(tab,key),active=Object.hasOwn(state.filters,key),selected=state.filters[key]||[];
 panel.querySelector('.column-menu-values').innerHTML=catalog.values.map(value=>{const text=catalog.labels[value];return `<label class="column-value" data-option-label="${esc(text)}"><input type="checkbox" aria-label="${esc(text)}" data-table-value="${esc(value)}" data-table-key="${key}" data-table-tab="${tab}" ${!active||selected.includes(value)?'checked':''}><span title="${esc(text)}">${esc(text)}</span></label>`;}).join('')||'<p class="muted">Sin valores</p>';panel._catalogReady=true;
}
function closeColumnMenu(focus=false){
 const menu=openFilterMenu||main.querySelector('.column-menu[open]');if(!menu)return;
 const panel=columnPanel(menu);menu.open=false;
 if(panel?._topLayer){try{panel.hidePopover();}catch{}panel._topLayer=false;}
 if(panel?._detached){menu.appendChild(panel);panel._detached=false;}
 if(focus)menu.querySelector('summary')?.focus({preventScroll:true});openFilterMenu=null;
}
function openColumnMenu(menu,focus=false){
 if(!menu)return;if(openFilterMenu&&openFilterMenu!==menu)closeColumnMenu();
 menu.open=true;openFilterMenu=menu;populateColumnMenu(menu);
 const panel=columnPanel(menu);menu._panel=panel;panel._columnMenu=menu;
 if(panel.showPopover){try{panel.showPopover();panel._topLayer=true;}catch{}}
 if(!panel._topLayer&&document.body?.appendChild){panel.removeAttribute('popover');document.body.appendChild(panel);panel._detached=true;}
 placeColumnMenu(menu);if(focus)panel.querySelector('[data-table-option-search]')?.focus({preventScroll:true});
}
function filterMenuChoices(menu,query){const normalized=fold(query);columnPanel(menu)?.querySelectorAll('[data-option-label]').forEach(label=>{label.hidden=!fold(label.dataset.optionLabel).includes(normalized);});}
function placeColumnMenu(menu){
 if(!menu?.open)return;
 const summary=menu.querySelector('summary'),panel=columnPanel(menu);
 if(!summary||!panel)return;
 const usable=(...values)=>Math.min(...values.filter(value=>Number.isFinite(value)&&value>0));
 const viewportWidth=usable(window.innerWidth,document.documentElement?.clientWidth,window.visualViewport?.width),viewportHeight=usable(window.innerHeight,document.documentElement?.clientHeight,window.visualViewport?.height);
 const left=window.visualViewport?.offsetLeft||0,top=window.visualViewport?.offsetTop||0;
 panel.style.maxWidth=Math.max(0,viewportWidth-24)+'px';panel.style.maxHeight=Math.max(0,viewportHeight-24)+'px';
 const rect=summary.getBoundingClientRect(),panelRect=panel.getBoundingClientRect?.(),width=panelRect?.width||Math.min(260,viewportWidth-24),height=panelRect?.height||Math.min(panel.scrollHeight,viewportHeight-24);
 if(rect.bottom<top||rect.top>top+viewportHeight){closeColumnMenu();return;}
 const below=top+viewportHeight-rect.bottom-12,above=rect.top-top-12;
 panel.style.left=Math.max(left+12,Math.min(rect.left-8,left+viewportWidth-width-12))+'px';
 panel.style.right='auto';
 panel.style.top=Math.max(top+12,Math.min(below>=height||below>=above?rect.bottom+4:rect.top-height-4,top+viewportHeight-height-12))+'px';
}
function applyPage(){
 const all=[...model.opportunities,...UI.archive(model)].filter(j=>!offerProfileFilter||(j.displaySearchProfileId||j.searchProfileId)===offerProfileFilter);
 const stage=j=>UI.flowStage(j);
 const categories=new Map(all.map(j=>[j.id,UI.offerState(j)]));
 const legacy={elegidas:'por-solicitar',preparacion:'por-solicitar',enviando:'por-solicitar',atencion:'todas','sin-elegir':'por-solicitar',enviadas:'en-espera',seguimiento:'en-espera',descartadas:'archivadas',cerradas:'archivadas'};
 flowFilters.solicitar=legacy[flowFilters.solicitar]||flowFilters.solicitar;
 if(!['todas',...UI.offerStates.map(state=>state.key)].includes(flowFilters.solicitar))flowFilters.solicitar='todas';
 const counts=Object.fromEntries(UI.offerStates.map(state=>[state.key,0]));
 for(const category of categories.values())counts[category.key]++;
 const priority=j=>UI.offerAttention(j)?0:stage(j)==='historial'?8:categories.get(j.id).key==='en-proceso'?1:UI.step(j).owner==='you'?2:UI.canChoose(j)?3:stage(j)==='solicitar'?4:stage(j)==='seguir'?6:j.apply==='No'?7:5;
 const visible=all.filter(j=>flowFilters.solicitar==='todas'||categories.get(j.id).key===flowFilters.solicitar).sort((a,b)=>priority(a)-priority(b)||(a.externalDeadline||'9999').localeCompare(b.externalDeadline||'9999')||(a.company||'').localeCompare(b.company||''));
 const records=visible.map(j=>flowRecord(j,stage(j)==='elegir'?'elegir':stage(j)==='solicitar'?'solicitar':'seguir'));
 const choices=[['todas','Todas',all.length],...UI.offerStates.map(state=>[state.key,({archivadas:'Archivadas',rechazadas:'Rechazadas',logradas:'Logradas'})[state.key]||state.label,counts[state.key]])];
  const searchLabel=searchRunLabel(),empty=all.length?'No hay ofertas en este grupo.':`Aún no hay ofertas. Pulsa «${searchLabel}» y pide «Continúa con Stubbs Jobs» en el chat de tu agente.`;
  const table=all.length?workflowTable('solicitar',records,empty):`<div class="empty-state"><p>Aún no hay ofertas. Pulsa «${searchLabel}» y pide «Continúa con Stubbs Jobs» en el chat de tu agente, o añade una oferta.</p></div>`;
  return flowShell('solicitar',`<div class="offers-heading"><div><h1>Ofertas</h1><p class="page-lead">Compara las ofertas, elige dónde solicitar y consulta cada resultado.</p>${searchStatusNote()}</div><div class="offers-heading-actions">${searchRunButton()}<button class="offers-add" data-screen="nueva">${icon('plus')}Añadir oferta</button></div></div>${toolsNotice()}${activityWork()}${offerProfileControls()}${pendingEntriesPanel()}${flowToolbar('solicitar',choices)}${table}`);
}
function followPage(){return applyPage();}
function findResults(){
 const query=fold(filterText.trim());if(!query){tableState.encontrar.records=[];return '';}
 const jobs=[...model.opportunities,...UI.archive(model)].filter(j=>fold(j.company+' '+j.title).includes(query)).sort((a,b)=>{const order={solicitar:0,elegir:1,seguir:2,historial:3};return order[UI.flowStage(a)]-order[UI.flowStage(b)]||a.company.localeCompare(b.company);});
 return workflowTable('encontrar',jobs.map(j=>flowRecord(j,UI.flowStage(j))),'Sin resultados guardados.');
}
function findPage(){return `<div class="flow-view search-results-view"><div class="offer-toolbar search-results-toolbar"><h1>Resultados guardados</h1></div><div id="find-results">${findResults()}</div></div>`;}
function answerList(values,extra=''){
  if(!Object.keys(values).length&&!extra)return '<p class="muted">Sin respuestas de formulario guardadas.</p>';
  return `<dl class="meta">${Object.entries(values).map(([k,v])=>`<div><dt>${esc(fieldLabel(UI.answerTitle((selected?getJob(selected)?.fieldDefinitions?.[k]?.label:null)||model.labels[k]||k)))}</dt><dd>${answerLabel(v)}</dd></div>`).join('')}${extra}</dl>`;
}
function pdfView(cvUrl){
  const previewUrl=cvUrl.replace('/api/document?','/api/preview?');
  return `<img class="cv-preview" alt="Primera página del CV adaptado" src="${previewUrl}"><p class="file-name">Vista previa de la primera página. <a href="${cvUrl}" target="_blank" rel="noopener">Abrir PDF completo en otra pestaña</a></p>`;
}
function returnLabelFor(page){return {buscar:'Mi perfil',agente:'Resumen',elegir:'Ofertas',solicitar:'Ofertas',seguir:'Ofertas',historial:'Ofertas',encontrar:'Resultados',perfil:'Mi perfil',detalle:'la oferta',revisar:'la solicitud',editar:'el borrador',cambio:'la petición',actividad:'Historial',informe:'Resultado',ayuda:'Ayuda'}[page]||'Mi perfil';}
function startOfferTour(id){
 const origin=screen==='encontrar'?'encontrar':'solicitar';
 const records=sortedFilteredRecords(origin,tableState[origin].records||[]);
 const marked=origin==='solicitar'&&tableSelection.has(id),ids=records.filter(r=>!marked||tableSelection.has(r.j.id)).map(r=>r.j.id);
 const state=UI.offerStates.find(state=>state.key===flowFilters.solicitar);
 offerTour=ids.includes(id)?{ids,origin,scope:origin==='encontrar'?'Resultados de búsqueda':marked?'Ofertas marcadas':state?.label||'Ofertas filtradas'}:null;
}
function offerTourIds(){return offerTour?.ids.filter(id=>getJob(id))||[];}
function offerNavigation(j){
 const ids=offerTourIds(),index=ids.indexOf(j.id);if(index<0)return '';
 return `<nav class="offer-navigation" aria-label="Recorrer ${esc(offerTour.scope.toLowerCase())}"><button class="icon-button" data-offer-move="-1" aria-label="Oferta anterior" title="Oferta anterior" ${index===0?'disabled':''}>${icon('chevron-left')}</button><span class="offer-position" role="status" aria-live="polite" aria-atomic="true" aria-label="${index+1} de ${ids.length}: ${esc(j.company)} · ${esc(j.title)}" title="${esc(offerTour.scope)}">${index+1} / ${ids.length}</span><button class="icon-button" data-offer-move="1" aria-label="Oferta siguiente" title="Oferta siguiente" ${index===ids.length-1?'disabled':''}>${icon('chevron-right')}</button></nav>`;
}
function offerHeading(j){
 return `<header class="offer-heading"><div class="offer-identity"><p class="offer-company">${icon('building','company-mark')}${esc(displayCase(j.company))}</p><h1 title="${esc(j.title)}">${isHttpUrl(j.url)?`<a class="offer-title-link" href="${url(j.url)}" target="_blank" rel="noopener" aria-label="Abrir anuncio original: ${esc(j.title)}">${esc(displayCase(j.title))} ${icon('arrow-up-right')}</a>`:esc(displayCase(j.title))}</h1></div><div class="offer-heading-tools">${offerNavigation(j)}</div></header>`;
}
function railBeside(){
 const rail=main.querySelector('.offer-rail');
 return Boolean(rail?.contains&&window.getComputedStyle?.(rail).gridColumnStart==='2');
}
function captureOfferSection(){
 const bottom=main.querySelector('.offer-heading')?.getBoundingClientRect?.().bottom||0,rail=railBeside()?main.querySelector('.offer-rail'):null;
 // In two columns, preserve the reading section rather than the rail's DOM order.
 return [...main.querySelectorAll('[data-offer-section]')].filter(section=>!rail?.contains(section)).find(section=>(section.getBoundingClientRect?.().bottom||0)>bottom+20)?.dataset.offerSection||'status';
}
function restoreOfferSection(section){
 const found=section&&section!=='status'?main.querySelector(`[data-offer-section="${section}"]`):null;
 const target=found&&!(railBeside()&&main.querySelector('.offer-rail')?.contains(found))?found:null;
 const header=main.querySelector('.offer-heading'),site=document.querySelector('.site-header');
 const top=target?.getBoundingClientRect?window.scrollY+target.getBoundingClientRect().top-(header?.getBoundingClientRect?.().height||0)-(site?.getBoundingClientRect?.().height||0)-16:0;
 window.scrollTo({top:Math.max(0,top),behavior:'instant'});
}
async function moveOffer(direction){
 if(![-1,1].includes(direction)||saving||actionBusy||profileSaving)return;
 const ids=offerTourIds(),index=ids.indexOf(selected),next=ids[index+direction];
 if(index<0||!next)return;
 await setScreen('detalle',next,true,null,null,{direction,section:captureOfferSection()});
}
function backDestination(){
 if(['revision-multiple','edicion-multiple'].includes(screen))return {page:'solicitar',id:null};
 if(screen==='configurar'||flowScreens.includes(screen)&&!selected)return null;
 if(screen==='detalle'&&offerTour?.ids.includes(selected))return {page:offerTour.origin||'solicitar',id:null};
 const previous=navigationTrail.at(-1);if(previous)return previous;
 if(screen==='informe')return {page:'agente',id:null};
 if(selected&&screen!=='detalle')return {page:'detalle',id:selected};
 const page=screen==='detalle'?caseReturn:screen==='encontrar'?findReturn:screen==='actividad'?auxReturn:screen==='cambio'?'perfil':screen==='programacion'?'perfil':lastFlowScreen;
 return {page:page===screen?'solicitar':page,id:null};
}
function backButton(target){
 return target?`<button type="button" class="quiet back" data-back="1" aria-label="Volver a ${esc(returnLabelFor(target.page))}">${icon('arrow-left')}<span>Volver a ${esc(returnLabelFor(target.page))}</span></button>`:'';
}
function renderBackNavigation(){
 const slot=document.querySelector('#page-back');if(!slot)return;
 const target=backDestination();slot.hidden=!target;
 slot.innerHTML=backButton(target);
}
async function goBack(){const target=backDestination();if(target)await setScreen(target.page,target.id);}
function offerConditions(j){
 const conditions=j.conditions||{},travel=(j.evidence||[]).filter(e=>e['Condición']==='Viajes').reduce((latest,e)=>!latest||(e.Comprobada||0)>=(latest.Comprobada||0)?e:latest,null);
 const unknown=(value,key)=>!value||['Pendiente','Sin comprobar'].includes(value)||tableText(value,key)==='—'?'Sin concretar':tableText(value,key);
 const sourceDetails=window.StubbsJobsExplanations.sourceDetails(j);
 const condition=(key,value)=>window.StubbsJobsExplanations.conditionValue(key,value,sourceDetails);
 const amount=new Intl.NumberFormat('es-ES'),range=typeof j.fixedSalaryMax==='number'&&Number.isFinite(j.fixedSalaryMax)&&j.fixedSalaryMax>j.fixedSalary?'–'+amount.format(j.fixedSalaryMax):'';
 const fixed=typeof j.fixedSalary==='number'&&Number.isFinite(j.fixedSalary)?amount.format(j.fixedSalary)+range+(j.fixedSalaryCurrency?' '+j.fixedSalaryCurrency:'')+' brutos/año'+(j.fixedSalaryCurrency?'':' · moneda por comprobar'):'Sin desglosar';
 const values=[['Modalidad',condition('mode',unknown(j.workMode||UI.offerMode(j),'mode'))],
  ['Contrato',condition('contract',unknown(j.contract||(conditions.Indefinido==='Sí'?'Indefinido':conditions.Indefinido==='No'?'No indefinido':conditions.Indefinido==='Contradicción'?'Datos contradictorios':'Sin concretar'),'contract'))],...(j.country||sourceDetails.conditions.country?.length?[['País',condition('country',unknown(j.country,'country'))]]:[]),...(j.place?[['Ubicación',j.place]]:[]),['Salario publicado',condition('salary',unknown(j.salary,'salary'))],
  ['Parte fija',fixed],
  ['Desplazamientos',condition('travel',typeof j.minimumTrips==='number'&&Number.isFinite(j.minimumTrips)?'Al menos '+amount.format(j.minimumTrips)+(j.minimumTrips===1?' viaje al mes':' viajes al mes'):travel?.Estado==='Contradicción'?'Datos contradictorios':['Sí','No'].includes(travel?.Estado)&&travel['Texto o motivo']||'Sin concretar')],['Horario',condition('schedule',unknown(j.schedule,'schedule'))],
  ...['experience','technology','functions','education','languages','requirements'].filter(key=>sourceDetails.conditions[key]?.length).map(key=>[window.StubbsJobsExplanations.conditionLabels[key],condition(key,''),true])];
 // Unpublished conditions share one line so the confirmed facts carry the panel.
 const pendingValue=value=>['Sin concretar','Sin desglosar'].includes(value),known=values.filter(([,value])=>!pendingValue(value));
 const pending=values.filter(([,value])=>pendingValue(value)).map(([label])=>label.toLocaleLowerCase('es'));
 const list=new Intl.ListFormat('es',{style:'long',type:'conjunction'});
 return (known.length?'<dl class="meta">'+known.map(([label,value,position])=>`<div${position?' class="condition-position"':''}><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')+'</dl>':'')+
  (pending.length?`<p class="conditions-pending"><span>Por concretar:</span> ${esc(list.format(pending))}.</p>`:'');
}
function offerAssessment(job){return window.StubbsJobsExplanations.assessment(job,{esc,basis:offerProfileBasis(job)});}
const followupResult=check=>({waiting:'Sin novedades',reviewing:'En revisión según el portal',unknown:'No se pudo confirmar',rejected:'Rechazo confirmado',closed:'Cierre confirmado'})[check.outcome]||'Resultado sin confirmar';
function followupStatus(j){
 if(!j.sent)return '';
 const sentAt=j.sent.at||j.lifecycle?.sentAt,check=j.lifecycle?.lastCheck;
 return `<p class="offer-followup-summary">Enviada: ${tableTimestamp(sentAt)!==null?activityTime(sentAt):'Fecha no registrada'}</p><p class="offer-followup-summary">${check&&tableTimestamp(check.observedAt)!==null?`Última comprobación: ${activityTime(check.observedAt)} · ${esc(followupResult(check))}`:'Sin comprobaciones posteriores al envío'}</p>${active(j)&&j.lifecycle?.availability?.outcome==='closed'?'<p class="offer-ad-notice">El anuncio ya no acepta nuevas solicitudes.</p>':''}`;
}
function followupActions(j){
 if(!j.sent||!active(j))return j.lifecycle?.canReopen?`<button class="offer-change" data-offer-outcome="reopen-followup" data-job-id="${esc(j.id)}">Reabrir seguimiento por nueva respuesta</button>`:'';
 const pending=(j.requests||[]).find(r=>r.purpose==='followup'&&['queued','running','blocked','interrupted'].includes(r.status));
 const label=pending?(pending.status==='queued'?'Comprobación pendiente del agente':pending.status==='running'?'Comprobación en curso':'Comprobación pendiente'):'Pedir comprobación';
 return `<button class="offer-change" data-followup-check="${esc(j.id)}"${pending?' disabled':''}>${label}</button>`;
}
function userSentButton(j){return UI.userSentChoices(j,model.cvLibrary)?`<button class="offer-change" data-user-sent="${esc(j.id)}">Ya la he enviado yo</button>`:'';}
// Records a send the person made herself. The writer cancels the agent's pending
// sends and permissions; the record keeps her declaration, never a portal receipt.
async function openUserSent(id){
 const dialog=document.querySelector('#user-sent-dialog'),form=dialog.querySelector('form'),error=form.querySelector('.user-sent-error');
 let job=getJob(id),choices=UI.userSentChoices(job,model.cvLibrary);
 if(!choices){toast('La oferta ha cambiado. Revisa su estado actual.');return;}
 const fill=()=>{
  const select=form.elements.namedItem('cv'),previous=select.value;
  select.innerHTML=(choices.options.length?'<option value="">Elige el CV</option>':'<option value="">Añade el PDF en Currículums</option>')+choices.options.map(o=>`<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('');
  if(choices.options.some(o=>o.value===previous))select.value=previous;else if(choices.options.length===1)select.value=choices.options[0].value;
  const warning=form.querySelector('.user-sent-warning');warning.textContent=choices.warnings.join(' ');warning.hidden=!choices.warnings.length;
  form.querySelector('[data-user-sent-reapply]').hidden=!choices.reapplication;
 };
 form.reset();error.textContent='';fill();
 const sentAt=form.elements.namedItem('sentAt');sentAt.value=window.StubbsJobsFormatting.localInputValue();sentAt.max=sentAt.value;
 const submit=async event=>{
  if(event.submitter?.value!=='ok')return;
  event.preventDefault();error.textContent='';
  const values={cv:form.elements.namedItem('cv').value,sentAt:sentAt.value,note:form.elements.namedItem('note').value,
   duplicatesChecked:form.elements.namedItem('duplicatesChecked').checked,reapplication:form.elements.namedItem('reapplication').checked};
  const plan=UI.userSentOperation(job,choices,values);
  if(plan.error){error.textContent=plan.error;return;}
 if(await action(plan.operation,null,form)){dialog.close('done');changeToast('Envío registrado. La oferta pasa a En espera.');render(true);return;}
  job=getJob(id);const next=job&&UI.userSentChoices(job,model.cvLibrary);
  if(!next){dialog.close('cancel');render(true);return;}
  if(form._conflict){choices=next;fill();error.textContent='La oferta ha cambiado mientras registrabas el envío. Revisa los datos actualizados y vuelve a confirmar.';}
 };
 form.addEventListener('submit',submit);
 dialog.returnValue='cancel';dialog.showModal();sentAt.focus();
 await new Promise(resolve=>dialog.addEventListener('close',resolve,{once:true}));
 form.removeEventListener('submit',submit);
}
function outcomePicker(j){
 const category=UI.offerState(j).key;
 if(!j.sent||category==='logradas'||j.requests.some(r=>r.type==='send'&&r.status==='running'))return '';
 const label=['archivadas','rechazadas'].includes(category)?'Cambiar resultado':'Registrar resultado';
 return `<details id="offer-outcome-${esc(j.id)}" class="offer-outcome-picker"><summary>${label}</summary><div class="offer-outcome-options">${[['achieve','Lograda','logradas'],['mark-rejected','Rechazada','rechazadas'],['close','Cerrar seguimiento','archivadas']].map(([action,text,key])=>`<button data-offer-outcome="${action}" data-job-id="${esc(j.id)}"${category===key?' disabled aria-label="'+text+' (actual)"':''}>${text}</button>`).join('')}</div></details>`;
}
async function openSelectionProgress(id){
 const job=getJob(id),dialog=document.querySelector('#selection-progress-dialog'),form=dialog?.querySelector('form');
 if(!job?.sent||UI.offerState(job).key==='logradas'||!form){toast('Esta candidatura ya no admite ese avance. Actualiza su ficha.');return;}
 const error=form.querySelector('.selection-progress-error'),at=form.elements.namedItem('at');
 form.reset();error.textContent='';at.value=window.StubbsJobsFormatting.localInputValue();at.max=at.value;
 const eventId=crypto.randomUUID();
 const submit=async event=>{
  if(event.submitter?.value!=='ok')return;
  event.preventDefault();error.textContent='';
  const step=form.elements.namedItem('selectionStep').value,proof=form.elements.namedItem('proof').value.trim(),when=window.StubbsJobsFormatting.zonedInstant(at.value);
  if(!['contact','test','interview'].includes(step)||!proof||!when||Date.parse(when)>Date.now()+300000){error.textContent='Indica el avance concreto, cuándo ocurrió y qué te comunicaron.';return;}
  if(Date.parse(when)<Date.parse(job.sent.at)){error.textContent='El avance no puede ser anterior al envío registrado.';return;}
  const recorded={id:eventId,opportunityId:id,type:step==='interview'?'interview':'response',selectionStep:step,
   at:when,proof,actor:'Usuario',reportedBy:'user',scope:'application',channel:'user_reported'};
  if(await action({kind:'event',event:recorded},null,form)){dialog.close('done');changeToast('Avance registrado para esta candidatura.');render(true);}
  else if(form._conflict)error.textContent='La candidatura ha cambiado. Actualiza la ficha y comprueba el avance antes de repetirlo.';
 };
 form.addEventListener('submit',submit);dialog.returnValue='cancel';dialog.showModal();form.elements.namedItem('selectionStep').focus();
 await new Promise(resolve=>dialog.addEventListener('close',resolve,{once:true}));form.removeEventListener('submit',submit);
}
function caseHistory(j){return window.StubbsJobsActivity.caseHistory(j,model);}
// The offer's key milestones read left to right, oldest to newest, above the details.
function offerTimeline(j){
 const items=window.StubbsJobsActivity.milestones(caseHistory(j),model,4).reverse();
 const steps=items.map((item,index)=>{
  const title=historyTitle(item),hasDetail=window.StubbsJobsActivity.details(item,model),undo=(model.undo||[]).some(u=>u.id===item.id);
  const heading=hasDetail?`<button class="link-button activity-event-link" data-report="event:${esc(item.id)}" aria-label="Ver detalle: ${esc(title)}">${esc(title)}</button>`:esc(title);
  return `<li class="offer-timeline-step"${index===items.length-1?' aria-current="step"':''}><span class="offer-timeline-dot" aria-hidden="true"></span><strong>${heading}</strong><small>${activityTime(item.at)} · ${esc(['Usuario','Usuario'].includes(item.actor)?'Tú':item.actor||'Registro')}${undo?` · <button class="link-button" data-undo="${esc(item.id)}">Deshacer</button>`:''}</small></li>`;
 }).join('');
 // Without any record there is nothing to show; older records stay one click away.
 if(!steps&&!caseHistory(j).length)return '';
 return `<section class="offer-timeline" data-offer-section="activity" aria-label="Actividad de la oferta">${steps?`<ol class="offer-timeline-steps">${steps}</ol>`:'<p class="offer-timeline-empty">Sin novedades recientes.</p>'}<button class="link-button offer-timeline-all" data-activity="${esc(j.id)}">Ver todo ${icon('arrow-right')}</button></section>`;
}
function activityRecord(id){
 const original=(model.history||[]).find(item=>String(item.id)===String(id));
 const job=original?.opportunityId?getJob(original.opportunityId):(model.opportunities||[]).find(j=>caseHistory(j).some(h=>String(h.id)===String(id)));
 return groupedActivity(job?caseHistory(job):model.history||[]).find(item=>String(item.id)===String(id))||original;
}
function detail(){
 const j=getJob(selected);if(!j)return top('Solicitud no disponible');
 if(j.historical)return `<div class="detail-wrap offer-detail">${offerHeading(j)}<section class="case-status offer-status" data-offer-section="status" data-offer-state="${UI.offerState(j).key}" aria-label="Situación y acciones"><div class="offer-status-copy"><div class="offer-status-line"><strong data-offer-state="${UI.offerState(j).key}">${icon(UI.offerState(j).icon,'offer-state-icon','solid')}${esc(UI.offerState(j).label)}</strong></div></div><div class="actions offer-actions"><button class="offer-change" data-change="${esc(j.id)}">Pedir cambio</button></div></section><p>Último estado conocido: ${esc(j.originalState)}</p><p>${esc(j.lastActivityLabel)}</p></div>`;
 const step=UI.step(j),category=UI.offerState(j),current=j.packages.find(p=>p.isCurrent),approved=UI.approved(j),sent=j.sentMaterial;
 const material=sent||(j.sent?{answers:{},formAnswerKeys:[],messageUsage:'unknown',legacyIncomplete:true}:{...j.draft,answers:j.answers});
 const sending=j.requests.some(r=>r.type==='send'&&r.status==='running'),canEdit=active(j)&&!j.sent&&!sending;
 const canInvestigate=active(j)&&!j.selection?.selected&&!j.sent&&!j.requests.some(r=>!window.StubbsJobsWorkflow.task(r).superseded&&['queued','running','blocked','interrupted'].includes(r.status))&&j.apply!=='No'&&j.apply!=='Resolver conflicto';
 const action=UI.canChoose(j)?selectionButtons(j):primaryAction(j,step,true)||(canInvestigate?`<button class="primary" data-investigate="${esc(j.id)}">Pedir comprobación</button>`:'');
 // When nobody knows whether a send arrived, saying «I sent it» is one of the two real answers.
 const sendDoubt=Boolean(step.deliveryUnknown&&!step.deliveryChecked);
 const stateDetail=UI.detailMessage(j,step),where=UI.actionPlace(j,step);
 // Only the decision for the current state stays visible; rarer actions live in Más acciones.
 const statusActions=`<div class="offer-status-actions"><div class="actions offer-actions">${action}${sendDoubt?userSentButton(j):''}${followupActions(j)}${j.sent&&category.key!=='logradas'?`<button class="offer-change" data-selection-progress="${esc(j.id)}">Registrar avance</button>`:''}${category.key==='por-solicitar'&&!j.selection?.selected?`<button class="offer-change" data-offer-outcome="discard" data-job-id="${esc(j.id)}">Descartar</button>`:''}${outcomePicker(j)}</div>${where?`<p class="helper offer-where">${esc(where)}</p>`:''}</div>`;
 const contacts=(j.contactDrafts||[]).length?`<details class="case-disclosure"><summary>Borradores de contacto (${j.contactDrafts.length})</summary><p class="helper">No enviados.</p>${j.contactDrafts.map((c,i)=>`<div class="case-piece"><strong>${esc(c.purpose)}</strong><p>${esc(c.recipient)}</p><p class="note-text">${esc(c.message)}</p><button data-copy-contact="${i}">Copiar</button></div>`).reverse().join('')}</details>`:'';
 const formAnswers=UI.formAnswers(material);
 const cvMissing=j.sent?'CV enviado no disponible':'Pendiente de preparar';
 const cvAnswer=`<div class="case-cv-answer"><dt>CV para la oferta</dt><dd><article class="cv-card case-cv-card" aria-label="CV para la oferta"${j.cvUrl?'':' data-cv-state="pending"'}>${icon('file','cv-card-icon')}<h3 class="cv-card-title" title="${esc(j.cvUrl?j.cvLabel||'Currículum.pdf':cvMissing)}">${esc(j.cvUrl?j.cvLabel||'Currículum.pdf':cvMissing)}</h3>${j.cvUrl?`<a class="cv-card-open" href="${esc(j.cvUrl)}" target="_blank" rel="noopener" aria-label="Abrir PDF: ${esc(j.cvLabel||'Currículum.pdf')}">Abrir PDF</a>`:''}</article></dd></div>`;
 const presentationAnswer=UI.presentationVisible(material)?`<div class="case-form-presentation"><dt class="case-answer-heading"><span>Presentación</span>${canEdit?`<button class="link-button" data-edit="${esc(j.id)}" aria-label="Editar presentación">Editar</button>`:''}</dt><dd class="note-text">${esc(material.message)}</dd></div>`:'';
  const answers=answerList(formAnswers,cvAnswer+presentationAnswer),assessment=offerAssessment(j),criteriaActions=offerCriteriaControls(j);
 return `<div class="detail-wrap offer-detail">${offerHeading(j)}${offerTimeline(j)}
  <div class="offer-layout"><div class="offer-columns"><aside class="offer-rail" aria-label="Decisión y condiciones">
  <section class="case-status offer-status" data-offer-section="status" data-offer-state="${UI.offerState(j).key}" aria-label="Situación y acciones"><div class="offer-status-copy"><div class="offer-status-line"><strong data-offer-state="${category.key}">${icon(category.icon,'offer-state-icon','solid')}${esc(category.label)}</strong>${UI.offerAttention(j)?'<span class="offer-attention-indicator">Por atender</span>':''}${j.selection?.selected&&!j.sent?`<span class="offer-selection-mode">${j.selection.mode==='auto'?'Auto-solicitud':'Solicitud con revisión'}</span>`:''}</div>${selectionOrigin(j)}${stateDetail&&stateDetail!==step.label?`<p>${esc(stateDetail)}</p>`:''}${UI.offerAttention(j)&&['archivadas','rechazadas'].includes(category.key)?`<p>${esc(step.detail||'Revisa el paso pendiente en esta oferta.')}</p>`:''}${followupStatus(j)}${!assessment&&j.displaySearchProfileId&&j.displaySearchProfileId!==j.searchProfileId?`<p class="helper offer-profile-placement">${esc(offerProfileBasis(j))}</p>`:''}${UI.nextAction(j)?`<p class="offer-next-action">${esc(UI.nextAction(j))}</p>`:''}${active(j)&&j.externalDeadline?`<p class="offer-deadline">Plazo: ${date(j.externalDeadline)}</p>`:''}</div>${statusActions}</section>
  ${j.integrityError?`<div class="error" role="alert">${esc(j.integrityError)}</div>`:''}
  <section class="case-section offer-conditions" data-offer-section="conditions"><div class="section-heading"><h2>Condiciones</h2></div>${offerConditions(j)}</section>${offerRequirementMatch(j)}
  <details class="case-disclosure case-more" id="offer-more-${esc(j.id)}"><summary>Más acciones</summary><div class="more-links">${category.key!=='logradas'?`<button data-change="${esc(j.id)}">Pedir cambio</button>`:''}${sendDoubt?'':userSentButton(j)}${j.selection?.selected&&!j.sent&&!sending?`<button data-unselect="${esc(j.id)}">Dejar de solicitar</button>`:''}${approved&&!j.sent?`<button data-revoke="${esc(current.id)}">Retirar permiso de envío</button>`:''}</div>${criteriaActions}${offerNotes(j)}</details></aside>
  <div class="case-sections offer-sections">${assessment?`<div class="offer-overview" data-offer-section="overview">${assessment}</div>`:''}
 <section class="case-section case-material" data-offer-section="form"><div class="section-heading"><h2>${isHttpUrl(material.recipient)?`<a href="${url(material.recipient)}" target="_blank" rel="noopener">Formulario de solicitud ${icon('arrow-up-right')}</a>`:'Formulario de solicitud'}</h2>${canEdit?`<button class="link-button" data-answers="${esc(j.id)}" aria-label="Editar respuestas del formulario">Editar</button>`:''}</div>
 ${material.legacyIncomplete?`<p class="muted">${material.reportedBy==='user'?'Enviaste tú esta solicitud. La app conserva el CV que indicaste, pero no las respuestas ni la presentación del portal.':'Este registro antiguo confirma el envío, pero no conserva las respuestas ni la presentación de aquella solicitud.'}</p>`:''}${!isHttpUrl(material.recipient)?material.recipient?`<p>Solicitud por correo: ${esc(material.recipient)}</p>`:j.sent?'':'<p class="muted">Pendiente de comprobar el acceso.</p>':''}${answers}${contacts}</section>
 </div></div></div></div>`;
}
// Packages reviewed since 18/10/2026 declare whether the CV was tailored to the offer.
function cvAdaptationNote(material){
  const label={adapted:'Adaptado a esta oferta',reused:'CV general, sin adaptar a esta oferta'}[material?.cvAdaptation];
  if(!label)return '';
  const reason=String(material.cvReason||'').trim();
  return `<p class="helper cv-adaptation" data-cv-adaptation="${esc(material.cvAdaptation)}"><strong>${label}.</strong>${reason?' '+esc(reason):''}</p>`;
}
function reviewPage(j=reviewSnapshot,bulk=false){
  if(!j)return top('No hay una solicitud para revisar');
  const current=getJob(j.id),pack=j.packages.find(p=>p.id===j.fingerprint),valid=UI.reviewValid(j,current);
  if(!pack)return `<p>El agente debe comprobar la solicitud antes de autorizar el envío.</p>`;
  const material=pack.payload;
  return (bulk?`<h2>${esc(j.company)} · ${esc(j.title)}</h2>`:top('Revisar solicitud',esc(j.company)+' · '+esc(j.title)))+`
    ${!valid?`<div class="error" role="alert">El envío ha cambiado o necesita una nueva comprobación. Esta versión no se puede autorizar.<div class="actions"><button data-review="${esc(j.id)}">Ver versión actual</button><button data-job="${esc(j.id)}">Ver oferta</button></div></div>`:''}
    <div class="review-page"><div class="split review-layout"><section class="panel"><div class="section-heading"><h2>CV adaptado</h2><a href="${pack.cvUrl}&download=1">Descargar</a></div><p class="file-name">${esc(j.cvLabel)}</p>${cvAdaptationNote(material)}${pdfView(pack.cvUrl)}</section>
    <div><section class="panel"><h2>${isHttpUrl(material.recipient)?'Formulario de solicitud':'Destinatario'}</h2><p class="file-name">${isHttpUrl(material.recipient)?`<a href="${url(material.recipient)}" target="_blank" rel="noopener">Abrir formulario de ${esc(j.company)}</a>`:esc(material.recipient)}</p><h2 class="section">Respuestas del formulario</h2>${answerList(UI.formAnswers(material))}${UI.presentationVisible(material)?`<h2 class="section">Presentación</h2><p class="helper">${esc(UI.presentationUsage(material))}</p><p class="note-text">${esc(material.message)}</p>`:''}
     </section></div></div>${bulk?'':`<section class="authorization" aria-label="Acciones de la solicitud"><div class="authorization-actions"><button class="primary" data-approve="${esc(j.id)}" ${valid?'':'disabled'}>Autorizar envío</button><button class="link-button secondary-change" data-change="${esc(j.id)}">Pedir cambio</button></div><p>Solo esta versión · El envío quedará pendiente del agente.</p></section>`}</div>`;
}
function bulkReviewPage(){
 if(!bulkReviewSnapshots.length)return top('No hay solicitudes para revisar');
 const valid=bulkReviewSnapshots.every(j=>UI.reviewValid(j,getJob(j.id)));
 return `<div class="bulk-review">${top('Revisar solicitudes',bulkReviewSnapshots.length+(bulkReviewSnapshots.length===1?' solicitud':' solicitudes')+' · Comprueba el CV, el destino y las respuestas de cada una.')}${bulkReviewSnapshots.map(j=>`<section class="bulk-review-case">${reviewPage(j,true)}</section>`).join('')}<section class="authorization" aria-label="Acciones de las solicitudes"><button class="primary" data-bulk-approve="1" ${valid?'':'disabled'}>Autorizar ${bulkReviewSnapshots.length} ${bulkReviewSnapshots.length===1?'envío':'envíos'}</button><p>Solo las versiones mostradas · Los envíos quedarán pendientes del agente.</p></section></div>`;
}
function bulkEditorFields(){
 const fields=new Map();if(!bulkEditor||bulkEditor.kind!=='responses')return [];
 bulkEditor.jobs.forEach((j,index)=>j.questions.forEach(q=>{
  const def=j.fieldDefinitions[q.key]||q,local=def.scope==='opportunity'||Object.hasOwn(j.answerOverrides||{},q.key),name=(local?'offer-'+index:'global')+':'+q.key;
  if(!fields.has(name))fields.set(name,{name,key:q.key,definition:def,indices:[],value:j.answers[q.key],local});
  fields.get(name).indices.push(index);
 }));return [...fields.values()];
}
function bulkEditorPage(){
 if(!bulkEditor)return top('No hay ofertas para editar');
 const changing=bulkEditor.kind==='change',fields=bulkEditorFields();
 const control=f=>fieldHtml(f.key,f.definition,Object.hasOwn(bulkEditor.values,f.name)?bulkEditor.values[f.name]:f.value).replace(`name="${esc(f.key)}"`,`name="${esc(f.name)}"`);
 const shared=fields.filter(f=>!f.local),local=fields.filter(f=>f.local);
 return `<div class="bulk-editor">${top(changing?'Aclarar ofertas':'Responder solicitudes',esc(bulkEditor.jobs.map(j=>j.company).join(' · ')))}<form data-bulk-form="1">${changing?`<section class="panel"><p>Esta aclaración se guardará para las ${bulkEditor.jobs.length} ofertas marcadas.</p>${fieldHtml('message',{label:'Tu aclaración',type:'longtext',rows:5},bulkEditor.values.message||'')}</section>`:`${shared.length?`<section class="panel"><h2>Respuestas compartidas</h2><p class="helper">Se usan en las ofertas que piden estos datos y se guardan en Mi perfil.</p><div class="form-grid">${shared.map(control).join('')}</div></section>`:''}${bulkEditor.jobs.map((j,index)=>{const own=local.filter(f=>f.indices.includes(index));return own.length?`<section class="panel"><h2>${esc(j.company)} · ${esc(j.title)}</h2><div class="form-grid">${own.map(control).join('')}</div></section>`:'';}).join('')}`}<div class="actions"><button type="submit" class="primary">${changing?'Guardar aclaración':'Guardar respuestas'}</button></div><p class="helper">${changing?'El agente recibirá la aclaración de cada oferta.':'Cada respuesta específica se guarda únicamente en su oferta.'} Guardar no confirma un envío.</p></form></div>`;
}
async function saveBulkEditor(form){
 if(!bulkEditor||actionBusy||form.reportValidity&&!form.reportValidity())return false;
 const fields=bulkEditorFields(),values={};
 for(const [name,value] of new FormData(form)){
  const field=fields.find(f=>f.name===name),type=field?.definition.type;
  values[name]=value===''?null:type==='boolean'?value==='true':type==='number'?Number(value):value;
 }
 bulkEditor.values=values;draftStorage.setItem(bulkEditor.draftKey,JSON.stringify({fingerprints:bulkEditor.fingerprints,values}));
 let targets=bulkEditor.jobs.map(j=>({id:j.id}));
 if(bulkEditor.kind==='responses')targets=bulkEditor.jobs.map((j,index)=>{
  const own=fields.filter(f=>f.indices.includes(index)&&!sameFieldValue(values[f.name],j.answers[f.key]));
  return {id:j.id,fingerprint:j.fingerprint,values:Object.fromEntries(own.map(f=>[f.key,values[f.name]])),expected:Object.fromEntries(own.map(f=>[f.key,j.answers[f.key]??null]))};
 }).filter(item=>Object.keys(item.values).length);
 if(!targets.length){toast('No hay respuestas nuevas para guardar.');return false;}
 const controls=[...(form.elements||[])].map(control=>[control,control.disabled]);controls.forEach(([control])=>control.disabled=true);
 try{
  if(await action({kind:'ui-bulk-action',action:bulkEditor.kind,targets,expectedRevision:model.revision,...(bulkEditor.kind==='change'?{message:values.message||''}:{})})){
   const message=finishBulk(targets.map(j=>j.id),bulkEditor.total,'Cambios guardados en','siguen marcadas');draftStorage.removeItem(bulkEditor.draftKey);bulkEditor=null;dirty=false;toast(message);await setScreen('solicitar');return true;
  }return false;
 }finally{controls.forEach(([control,disabled])=>control.disabled=disabled);}
}
function answerText(v){return v===null||v===undefined||v===''?'No indicado':typeof v==='boolean'?(v?'Sí':'No'):typeof v==='number'&&Number.isFinite(v)?new Intl.NumberFormat('es-ES',{maximumFractionDigits:2}).format(v):String(v);}
function answerLabel(v){return esc(answerText(v));}
const commonWorkDestinations=['España','Unión Europea','Reino Unido','Suiza','Estados Unidos','Canadá','Australia'];
function workAuthorizationValues(value){
 if(Array.isArray(value))return value;
 return model?.profile?.workAuthorizations===undefined&&model?.profile?.workPermitWithoutSponsorship===true&&/\b(españa|spain)\b/i.test(model?.preferences?.location||'')?['España']:[];
}
function workAuthorizationOption(name,checked){return `<label class="permit-option"><input type="checkbox" data-permit-option="${esc(name)}"${checked?' checked':''}><span>${esc(name)}</span></label>`;}
function workAuthorizationOptions(selected){return [...new Set([...commonWorkDestinations,...selected])].map(name=>workAuthorizationOption(name,selected.includes(name))).join('');}
function workAuthorizationField(value,association){
 const selected=workAuthorizationValues(value);
 return `<div class="field"><span id="work-authorizations-label">Puedo trabajar sin patrocinio en</span><input type="hidden" name="workAuthorizations" data-type="multiselect"${association} value="${esc(JSON.stringify(value??null))}"><details class="work-authorizations" data-work-authorizations="1"><summary aria-labelledby="work-authorizations-label work-authorizations-value"><span id="work-authorizations-value">${esc(selected.join(', ')||'Sin especificar')}</span></summary><div class="permit-options" role="group" aria-labelledby="work-authorizations-label">${workAuthorizationOptions(selected)}</div><div class="permit-add"><input type="text" data-permit-other="1" maxlength="100" placeholder="Otro país o zona" aria-label="Otro país o zona con permiso de trabajo"><button type="button" data-permit-add="1" aria-label="Añadir país o zona">+</button></div></details></div>`;
}
function syncWorkAuthorizations(){
 for(const widget of main.querySelectorAll('[data-work-authorizations]')){
  const field=controlForm(widget)?.elements.namedItem('workAuthorizations');if(!field)continue;
  const selected=workAuthorizationValues(JSON.parse(field.value||'null'));
  widget.querySelector('.permit-options').innerHTML=workAuthorizationOptions(selected);
  widget.querySelector('summary span').textContent=selected.join(', ')||'Sin especificar';
 }
}
function saveWorkAuthorizationChoices(widget){
 const form=controlForm(widget),field=form?.elements.namedItem('workAuthorizations');if(!field)return;
 const selected=[...widget.querySelectorAll('[data-permit-option]:checked')].map(input=>input.dataset.permitOption);
 field.value=JSON.stringify(selected);widget.querySelector('summary span').textContent=selected.join(', ')||'Sin especificar';
 form._lastEditedField='workAuthorizations';rememberForm(form);
}
function growField(field){
 if(!field?.style||!field.getBoundingClientRect?.().width)return;
 const top=window.scrollY;
 field.style.height='0px';field.style.height=(field.scrollHeight+(field.offsetHeight-field.clientHeight))+'px';
 if(window.scrollY!==top)window.scrollTo({top,behavior:'instant'});
}
function growProfileFields(){for(const field of main.querySelectorAll('textarea[data-auto-grow]'))growField(field);syncProfileWidgets();}
window.addEventListener('resize',()=>requestAnimationFrame(growProfileFields));
function fieldHtml(key,definition,value){
  const label=fieldLabel(UI.answerTitle(definition.label)),type=definition.type;
  const helpId=definition.help?(definition.descriptionId||'field-'+key+'-help'):definition.descriptionId,labelId=definition.help?helpId+'-label':null;
  const association=(definition.form?` form="${esc(definition.form)}"`:'')+(definition.controlId?` id="${esc(definition.controlId)}"`:'')+(helpId?` aria-describedby="${esc(helpId)}"`:'')+(labelId?` aria-labelledby="${esc(labelId)}"`:'');
  const numberLimits=type==='number'?numberAttributes(key):'',inputType=type==='number'?'number':['email','tel','url'].includes(definition.inputType)?definition.inputType:'text';
  if(type==='multiselect')return workAuthorizationField(value,association);
  const choices=definition.options,raw=key==='demographicSurveyParticipation'&&type==='choice'&&typeof value==='boolean'?surveyMode(value):value===null||value===undefined?'':String(value),known=choices?.some(option=>String(option.value)===raw),legacy=choices&&raw&&!known;
  const choiceInput=choices?`<select name="${esc(key)}"${association} data-type="${esc(type)}"><option value=""${(type==='choice'&&!definition.emptyLabel)||key==='custom_legally_protected_status'?' hidden disabled':''}${!raw?' selected':''}>${type==='choice'?definition.emptyLabel||'Sin decidir':'Sin responder'}</option>${legacy?`<option value="${esc(raw)}" hidden selected>${esc(key==='demographicSurveyParticipation'?(surveyMode(value)==='use_saved'?'Sí, usar mis datos':'Prefiero no responder'):'Respuesta anterior: '+raw)}</option>`:''}${choices.map(option=>`<option value="${esc(option.value)}"${String(option.value)===raw?' selected':''}>${esc(option.label)}</option>`).join('')}</select>`:null;
  const input=choiceInput|| (type==='boolean'?`<select name="${esc(key)}"${association} data-type="boolean"><option value="">Sin responder</option><option value="true" ${value===true?'selected':''}>${esc(definition.trueLabel||'Sí')}</option><option value="false" ${value===false?'selected':''}>${esc(definition.falseLabel||'No')}</option></select>`:type==='longtext'?`<textarea name="${esc(key)}"${association}${definition.autoGrow?' data-auto-grow="1"':''} rows="${definition.rows||10}" maxlength="${definition.maxlength||20000}" ${definition.placeholder?`placeholder="${esc(definition.placeholder)}"`:''}>${esc(value)}</textarea>`:`<input name="${esc(key)}"${association} data-type="${esc(type)}" type="${inputType}" ${numberLimits} value="${esc(value)}" ${definition.autocomplete?`autocomplete="${esc(definition.autocomplete)}"`:''} ${definition.placeholder?`placeholder="${esc(definition.placeholder)}"`:''} maxlength="${definition.maxlength||(key==='noticeDays'?300:5000)}"${definition.suggestions?` list="field-${esc(key)}-options"`:''}>${definition.suggestions?`<datalist id="field-${esc(key)}-options">${definition.suggestions.map(option=>`<option value="${esc(option)}"></option>`).join('')}</datalist>`:''}`);
  return `<label class="field"><span${labelId?` id="${esc(labelId)}"`:''}${definition.labelClass?` class="${esc(definition.labelClass)}"`:''}>${esc(label)}</span>${input}${definition.help?`<small class="helper" id="${esc(helpId)}">${esc(definition.help)}</small>`:''}</label>`;
}

function syncProfileNavigation(){
 for(const link of main.querySelectorAll('[data-profile-section]')){if(link.dataset.profileSection===profileSection)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');}
 main.querySelector('.profile-workspace')?.setAttribute?.('data-profile-active',profileSection);
 const pager=main.querySelector('[data-profile-pager]');if(pager)pager.innerHTML=profilePager();
}
// Next section in the order the person sees them, so the profile can be completed start to finish.
function profilePager(){
 const shown=profileSections.filter(([id])=>id!=='profile-permissions'||Object.keys(model.fieldDefinitions||{}).some(key=>AUTO_PERMISSION_KEYS().has(key))),next=shown[shown.findIndex(([id])=>id===profileSection)+1];
 return next?`<button type="button" class="profile-next" data-profile-next="${next[0]}">Siguiente: ${esc(next[1])}${icon('arrow-right')}</button>`:'';
}
function showProfileSection(id,{focus=true}={}){
 profileSection=canonicalProfileSection(id);
 if(cvDetail){cvDetail=null;rememberAllForms();render(true);}
 syncProfileNavigation();
 try{workspaceSession.setItem('stubbs_jobs-profile-section',profileSection);}catch{}
 const target=document.getElementById(profileSection);target?.scrollIntoView?.({block:'start',behavior:'instant'});
 if(target?.classList){target.classList.remove('profile-card--enter');void target.offsetWidth;target.classList.add('profile-card--enter');}
 if(focus){const heading=target?.querySelector('h2')||target;heading?.setAttribute('tabindex','-1');heading?.focus({preventScroll:true});}
 // A hidden section measures zero: fields that fit their content are sized when it appears.
 growProfileFields();
}
// A control in a closed section cannot show its message: open the section first.
function reportFormValidity(form){
 if(!form.reportValidity)return true;
 // An amount means nothing without its currency: the person chooses it, the app never assumes one.
 const named=name=>Array.from(form.elements||[]).find(control=>control.name===name);
 for(const [amount,currency] of [['minimumFixed','currency'],['salaryExpectationFixed','salaryCurrency'],['currentSalary','currentSalaryCurrency']]){
  const field=named(currency);field?.setCustomValidity?.(String(named(amount)?.value||'').trim()&&!String(field.value||'').trim()?'Indica la moneda de este salario, por ejemplo EUR o USD.':'');
 }
 const invalid=Array.from(form.elements||[]).find(control=>control.willValidate&&!control.checkValidity()),card=invalid?.closest?.('.profile-card');
 if(card?.id&&card.id!==profileSection)showProfileSection(card.id,{focus:false});
 return form.reportValidity();
}
// A draft identical to what is shown or already saved holds no change: it never keeps the save bar open.
function settleIdleDraft(form){
 try{
  const key=draftKey(form),stored=JSON.parse(draftStorage.getItem(key)||'null');if(stored?.attempt)return;
  const values=formValues(form),source=formSource(form.dataset.form),same=target=>Object.keys(values).every(name=>sameFieldValue(values[name],target[name]));
  if(!same(form._shown)&&!same(source))return;
  draftStorage.removeItem(key);form._dirty=false;
  if(!same(form._shown)){form._expected=Object.fromEntries(Object.keys(values).map(name=>[name,source[name]??null]));form._shown={...form._expected};}
 }catch{}
}
function forgetProfileChanges(){
 profileSaveProblem='';
 for(const form of visibleForms().filter(form=>form._dirty)){draftStorage.removeItem(draftKey(form));form._dirty=false;}
 dirty=false;
}
// Mi perfil saves as a whole: leaving it, or changing search profile, settles what is pending first.
async function settleUnsavedProfile(text,saveLabel){
 if(!dirty)return true;
 const dialog=document.querySelector('#unsaved-dialog');if(!dialog?.showModal)return true;
 document.querySelector('#unsaved-text').textContent=text.replace('{sections}',profileChangedSections().join(', ')||'tu perfil');
 document.querySelector('#unsaved-save').textContent=saveLabel;
 dialog.returnValue='stay';dialog.showModal();
 const choice=await new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue),{once:true}));
 if(choice==='save')return await saveProfileChanges();
 if(choice==='discard'){forgetProfileChanges();return true;}
 return false;
}
async function discardProfileChanges(){
 if(!dirty||profileSaving||!await confirmAction('Descartar los cambios',`Se perderá lo que has cambiado en ${profileChangedSections().join(', ')||'tu perfil'} desde la última vez que guardaste.`))return;
 forgetProfileChanges();render();toast('Cambios descartados.');
}
function profileForm(){
 if(!profileSectionRestored){profileSectionRestored=true;try{const saved=workspaceSession.getItem('stubbs_jobs-profile-section');if(profileSections.some(([id])=>id===saved)&&profileSection==='profile-about')profileSection=saved;}catch{}}
 const j=selected?getJob(selected):null;
 if(j){
  const formKeys=Array.isArray(j.draft.formAnswerKeys)?j.draft.formAnswerKeys.filter(key=>Object.hasOwn(j.fieldDefinitions,key)):[];
  const keys=[...new Set(['currentCity','workPermitWithoutSponsorship','salaryExpectationFixed',...j.draft.requiredAnswers,...formKeys])];
  return `<div class="profile-layout"><form data-form="profile" class="panel"><h1>Respuestas para ${esc(j.company)}</h1><div class="form-grid">${keys.map(k=>fieldHtml(k,j.fieldDefinitions[k],j.answers[k])).join('')}</div><p class="helper">Los datos generales se reutilizan; las respuestas de esta oferta quedan aquí.</p>${formErrors()}<button class="primary" type="submit" hidden>Guardar cambios</button>${Object.keys(j.answerOverrides).length?'<button type="button" data-inherit="1">Volver a usar los datos generales</button>':''}</form></div>`;
 }
 const about=formSource('about'),layout=aboutLayout(),defs=sectionDefinitions('about'),search=formSource('search'),owner='profile-about-form';
 const permissionFields=aboutFieldsHtml([...layout.consent,...layout.autoApply],about,defs,owner);
 const personal=[['identity','Sobre ti','Lo básico que piden todos los formularios.',layout.identity],['contact','Contacto','Cómo pueden localizarte y qué enlaces compartes.',layout.contact],['home','Dónde vives','Tu residencia, no dónde quieres trabajar.',layout.home],['work','Disponibilidad y movilidad','Dónde puedes trabajar, cuándo empiezas y cómo te mueves.',layout.work],['situation','Situación laboral','Lo que preguntan algunos formularios sobre tu empleo actual.',layout.salary.filter(key=>key!=='salaryExpectationFixed')],['demographic','Encuestas y datos sensibles','Opcionales. Solo se usan como decidas aquí.',layout.demographic]].map(([id,title,lead,keys])=>{const fields=aboutFieldsHtml(keys,about,defs);return fields.trim()?profilePanel(id,title,lead,`<div class="profile-body">${fields}</div>`):'';}).join('');
 const sections={
  'profile-about':profileCard('profile-about',`<form data-form="about" id="${owner}" class="profile-fields-form">${personal}${formErrors()}</form>`),
  'profile-experience':profileCard('profile-experience',`<form data-form="experience" id="profile-experience-form" class="profile-fields-form">${formErrors()}</form>${profilePanel('career','Mi experiencia','Tus puestos, responsabilidades y logros. Tu agente parte de aquí para adaptar cada CV.',`<div class="profile-body"><div class="profile-field-wide">${fieldHtml('text',{label:'Mi experiencia',labelClass:'sr-only',type:'longtext',rows:10,form:'profile-experience-form'},model.experience)}</div></div>`)}${skillsPanel()}${profilePanel('studies','Formación e idiomas','Tu nivel de estudios y los idiomas que hablas.',`<div class="profile-body">${aboutFieldsHtml(layout.education,about,defs,owner)}<div class="profile-field-wide">${fieldHtml('languages',{...sectionDefinitions('search').languages,form:'profile-search-form'},search.languages)}${languageRows(search.languages)}</div></div>`)}${formErrors('search')}`),
  'profile-work':searchSettingsPanels(),
  'profile-cv':cvLibrary(),
  'profile-answers':profileCard('profile-answers',`${answersPanel()}${layout.answers.length?profilePanel('other-answers','Otras preguntas','Preguntas con un formato fijo que ya has contestado.',`<div class="profile-body">${aboutFieldsHtml(layout.answers,about,defs,owner)}</div>`):''}`),
  'profile-permissions':permissionFields.trim()?profileCard('profile-permissions',permissionFields):''
 };
 const shown=profileSections.filter(([id])=>sections[id]);
 if(!shown.some(([id])=>id===profileSection))profileSection=shown[0][0];
 return `<div class="profile-layout"><div class="profile-workspace" data-profile-active="${profileSection}"><div class="profile-sidebar"><div class="profile-heading"><h1>Mi perfil</h1><p class="page-lead">Todo lo que tu agente necesita para buscar y solicitar por ti.</p></div><nav class="profile-section-nav" aria-label="Secciones de Mi perfil">${shown.map(([id,label])=>`<a href="#${id}" data-profile-section="${id}"${profileSection===id?' aria-current="location"':''}><span>${label}</span>${profileStatusHtml(id)}</a>`).join('')}</nav>${toolsNotice()}</div><div class="profile-content">${legacyRecovery()}
  ${shown.map(([id])=>sections[id]).join('\n  ')}
  <div class="profile-pager" data-profile-pager>${profilePager()}</div></div><form id="profile-knowledge-form" hidden></form></div><aside class="profile-savebar" data-profile-savebar aria-label="Guardar cambios de Mi perfil" hidden><div class="profile-savebar-inner"><span data-profile-pending>Cambios sin guardar</span><small class="shortcut-hint" aria-hidden="true"><kbd>Ctrl</kbd><kbd>S</kbd></small><button type="button" class="quiet" data-discard-profile="1">Descartar</button><button type="button" class="primary" data-save-profile="1" title="Guardar cambios (Ctrl+S)">Guardar cambios</button></div></aside>
 </div>`;
}
// Competencies and saved answers save one by one, apart from the page's unsaved changes.
const SKILL_KINDS={professional:'En el trabajo',personal:'Proyecto propio',training:'Formación'},SKILL_LEVELS={basic:'Básico',intermediate:'Intermedio',advanced:'Avanzado'};
let answersExpanded=false,answerQuery='';
const LANGUAGE_LEVELS=['Nativo','C2','C1','B2','B1','A2','A1'];
function parseLanguages(value){
 return String(value||'').split(/,(?![^()]*\))|;|\n/).map(part=>part.trim()).filter(Boolean).map(part=>{
  const match=part.match(/^(.+?)\s+(nativo|nativa|native|biling[üu]e|[abc][12])\b\s*(?:\((.*)\))?\s*$/i);
  if(!match)return {name:part,level:'',note:''};
  const level=/^[abc][12]$/i.test(match[2])?match[2].toUpperCase():'Nativo';
  return {name:match[1].trim(),level,note:(match[3]||'').trim()};
 });
}
function languageRowHtml(row){
 return `<div class="language-row" data-language-row><input type="text" form="profile-knowledge-form" data-knowledge="1" data-language-name maxlength="60" list="language-options" value="${esc(row.name)}" placeholder="Idioma" aria-label="Idioma"><select form="profile-knowledge-form" data-knowledge="1" data-language-level aria-label="Nivel"><option value="">Nivel</option>${LANGUAGE_LEVELS.map(level=>`<option value="${level}"${row.level===level?' selected':''}>${level}</option>`).join('')}</select><input type="text" form="profile-knowledge-form" data-knowledge="1" data-language-note maxlength="80" value="${esc(row.note)}" placeholder="Certificado (opcional)" aria-label="Certificado"><button type="button" class="link-button knowledge-remove" data-language-remove="1" aria-label="Quitar ${esc(row.name||'idioma')}">Quitar</button></div>`;
}
function languageRows(value){
 return `<div class="language-rows" data-language-rows><datalist id="language-options">${['Español','Inglés','Francés','Alemán','Italiano','Portugués','Catalán','Euskera','Gallego','Árabe','Chino','Neerlandés','Polaco','Rumano','Ruso'].map(name=>`<option value="${name}"></option>`).join('')}</datalist><div data-language-list>${parseLanguages(value).map(languageRowHtml).join('')}</div><button type="button" data-language-add="1">Añadir idioma</button></div>`;
}
function languageRowsText(){
 return [...main.querySelectorAll('[data-language-row]')].map(row=>{
  const name=row.querySelector('[data-language-name]').value.trim(),level=row.querySelector('[data-language-level]').value,note=row.querySelector('[data-language-note]').value.trim();
  if(!name)return '';
  return `${name}${level?` ${level==='Nativo'?'nativo':level}`:''}${note?` (${note})`:''}`;
 }).filter(Boolean).join(', ');
}
function writeLanguageRows(){
 const field=main.querySelector('textarea[name="languages"]');if(!field)return;
 field.value=languageRowsText();const form=controlForm(field);if(form){form._lastEditedField='languages';rememberForm(form);}
}
// A restored draft updates the saved text; rows and dependent fields follow it.
function syncProfileWidgets(){
 const field=main.querySelector?.('textarea[name="languages"]'),list=main.querySelector?.('[data-language-list]');
 if(field&&list&&document.activeElement?.closest?.('[data-language-rows]')==null&&languageRowsText()!==String(field.value||'').trim())list.innerHTML=parseLanguages(field.value).map(languageRowHtml).join('');
 const onsite=main.querySelector?.('#search-field-onsiteLocations'),mode=main.querySelector?.('[name="workMode"]'),zones=main.querySelector?.('[name="onsiteLocations"]');
 // Zones for office work mean nothing to a search that is only remote.
 if(onsite&&mode&&zones)onsite.hidden=/remot/i.test(mode.value)&&!/h[ií]brid|presencial/i.test(mode.value)&&!zones.value.trim();
 syncWherePanel();
}
function skillsPanel(){
 const all=model.skills||[],lacking=all.filter(s=>s.status==='confirmed'&&s.years===0),rows=all.filter(s=>!lacking.includes(s)),pending=rows.filter(s=>s.status!=='confirmed').length,confirmed=rows.length-pending;
 const where=s=>[SKILL_KINDS[s.kind],SKILL_LEVELS[s.level]].filter(Boolean).join(' · ')||'—';
 const row=s=>`<tr data-skill-row="${esc(s.id)}"${s.status==='confirmed'?'':' data-pending="1"'}><th scope="row"><span class="knowledge-name">${esc(s.name)}</span>${s.status==='confirmed'?'':' <span class="knowledge-pending">Por confirmar</span>'}${s.aliases?.length?`<small class="knowledge-aliases">${esc(s.aliases.join(', '))}</small>`:''}</th><td class="knowledge-years"><input type="number" form="profile-knowledge-form" min="0" max="60" step="0.1" value="${s.years??''}" placeholder="Sin indicar" data-knowledge="1" data-skill-years="${esc(s.id)}"${s.status==='confirmed'?'':' data-skill-pending="1"'} aria-label="Años de experiencia con ${esc(s.name)}"></td><td>${esc(where(s))}${s.usedAt?`<small class="knowledge-aliases">${esc(s.usedAt)}</small>`:''}</td><td><div class="knowledge-actions">${s.status!=='confirmed'&&s.years!=null?`<button type="button" class="knowledge-confirm" data-skill-confirm="${esc(s.id)}" aria-label="Confirmar ${esc(s.name)}">Confirmar</button>`:''}<button type="button" class="link-button" data-skill-edit="${esc(s.id)}" aria-label="${s.status==='confirmed'?'Editar':'Revisar'} ${esc(s.name)}">${s.status==='confirmed'?'Editar':'Revisar'}</button><button type="button" class="link-button knowledge-quiet" data-skill-remove="${esc(s.id)}" aria-label="Quitar ${esc(s.name)}">Quitar</button></div></td></tr>`;
 const summary=rows.length?`${pending?`<span class="knowledge-pending">${pending} por confirmar</span> · `:''}${confirmed} ${confirmed===1?'confirmada':'confirmadas'}`:'';
 const none=lacking.length?`<div class="knowledge-lacking"><span>Sin experiencia</span>${lacking.map(s=>`<button type="button" class="knowledge-chip" data-skill-edit="${esc(s.id)}" aria-label="Editar ${esc(s.name)}, sin experiencia">${esc(s.name)}</button>`).join('')}</div>`:'';
 return profilePanel('skills','Competencias',`${summary?summary+'. ':''}${pending?'Escribe los años y pulsa Intro para confirmar y pasar a la siguiente.':'Solo lo confirmado responde formularios y entra en tus CV.'}`,`<div class="knowledge-panel">${rows.length?`<div class="knowledge-scroll"><table class="knowledge-table"><thead><tr><th scope="col">Competencia</th><th scope="col">Años</th><th scope="col">Dónde</th><th scope="col"><span class="sr-only">Acciones</span></th></tr></thead><tbody>${rows.map(row).join('')}</tbody></table></div>`:'<p class="knowledge-empty">Aún no hay ninguna. Pide a tu agente que las proponga a partir de tu CV, o añádelas tú.</p>'}${none}</div>`,{flush:true,action:'<button type="button" data-skill-add="1">Añadir competencia</button>'});
}
function answerNeedsReview(a){return Boolean(a.conflict);}
function answersList(){
 const folded=value=>String(value??'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase(),query=folded(answerQuery).trim();
 const value=v=>v===true?'Sí':v===false?'No':String(v);
 const rows=(model.answerBank||[]).filter(a=>!query||folded(a.question+' '+value(a.value)).includes(query));
 const shown=answersExpanded||query?rows:rows.slice(0,8);
 if(!rows.length)return `<p class="knowledge-empty">Ninguna respuesta coincide con tu búsqueda.</p>`;
 return `<ul class="knowledge-answers">${shown.map(a=>`<li data-answer-row="${esc(a.id)}"><div class="knowledge-question"><strong>${esc(a.question)}</strong>${a.conflict?`<span class="knowledge-pending">Después respondiste «${esc(value(a.laterValue??''))}». ¿Cuál vale?</span>`:''}</div><p class="note-text">${esc(value(a.value))}</p><div class="knowledge-actions">${a.conflict?`<button type="button" class="knowledge-confirm" data-answer-confirm="${esc(a.id)}" aria-label="Mantener la respuesta: ${esc(a.question)}">Mantener</button>`:''}<button type="button" class="link-button" data-answer-edit="${esc(a.id)}" aria-label="Editar: ${esc(a.question)}">Editar</button><button type="button" class="link-button knowledge-quiet" data-answer-remove="${esc(a.id)}" aria-label="Quitar: ${esc(a.question)}">Quitar</button></div></li>`).join('')}</ul>${rows.length>shown.length?`<button type="button" class="link-button" data-answers-more="1">Ver las ${rows.length} respuestas</button>`:''}`;
}
function answersPanel(){
 const rows=model.answerBank||[],add='<button type="button" data-answer-add="1">Añadir respuesta</button>',lead='Lo que has contestado en formularios, para no volver a preguntártelo.';
 if(!rows.length)return profilePanel('answers','Respuestas a formularios',lead,`<div class="knowledge-panel"><p class="knowledge-empty">Solo aparecerá aquí lo que tu perfil no permita responder.</p></div>`,{flush:true,action:add});
 return profilePanel('answers','Respuestas a formularios',lead,`<div class="knowledge-panel">${rows.length>8?`<div class="knowledge-toolbar"><input type="search" class="knowledge-search" form="profile-knowledge-form" data-knowledge="1" data-answer-search="1" value="${esc(answerQuery)}" placeholder="Buscar en tus respuestas" aria-label="Buscar en tus respuestas"></div>`:''}<div id="knowledge-answers-list" aria-live="polite">${answersList()}</div></div>`,{flush:true,action:add});
}
function dialogResult(dialog){dialog.returnValue='cancel';dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='ok'),{once:true}));}
async function knowledgeAction(operation,done){rememberAllForms();if(await action(operation)){renderKeepingKnowledgeInput();toast(done);}}
// The next year may be half typed when an earlier one finishes saving.
function renderKeepingKnowledgeInput(){
 const active=document.activeElement,id=active?.dataset?.skillYears,value=active?.value;
 render(true);
 if(id){const input=main.querySelector?.(`[data-skill-years="${id}"]`);if(input){input.value=value;input.focus?.();}}
}
let skillSaves=Promise.resolve();
function storedSkill(skill){const stored={};for(const key of Object.keys(skill))if(!['formYears','pending'].includes(key))stored[key]=skill[key];return stored;}
function skillValues(skill,changes={}){return {name:skill.name,aliases:skill.aliases||[],years:skill.years??null,level:skill.level??null,kind:skill.kind||'professional',usedAt:skill.usedAt??null,lastUsed:skill.lastUsed??null,...changes};}
function focusNextSkill(current){const pending=[...main.querySelectorAll('[data-skill-pending]')],index=pending.indexOf(current),next=pending[index+1]||pending.find(input=>input!==current);if(next)next.focus();else current.blur();}
function saveSkillYears(input){
 const identifier=input.dataset.skillYears,raw=input.value.trim();
 // Saves run in order: each reads the state the previous one left.
 skillSaves=skillSaves.then(async()=>{
  const skill=(model.skills||[]).find(s=>s.id===identifier);if(!skill)return;
  const years=raw===''?null:Number(raw);
  if(years===(skill.years??null))return;
  if(years===null&&skill.status==='confirmed'&&!(await confirmAction('Quitar los años',`«${skill.name}» dejará de responder preguntas de años hasta que los indiques.`))){const shown=main.querySelector?.(`[data-skill-years="${identifier}"]`);if(shown)shown.value=skill.years??'';return;}
  await knowledgeAction({kind:'ui-skill-save',id:skill.id,expected:storedSkill(skill),values:skillValues(skill,{years})},years===null?`${skill.name}: años quitados.`:`${skill.name}: ${String(years).replace('.',',')} ${years===1?'año':'años'}, confirmada.`);
 }).catch(error=>toast(error?.message||'No se pudo guardar. Vuelve a intentarlo.'));
 return skillSaves;
}
async function editSkill(identifier){
 const current=(model.skills||[]).find(s=>s.id===identifier),dialog=document.querySelector('#skill-dialog'),form=dialog.querySelector('form');
 form.reset();
 for(const key of ['name','years','level','kind','usedAt','lastUsed'])form.elements[key].value=current?.[key]??(key==='kind'?'professional':'');
 form.elements.aliases.value=(current?.aliases||[]).join(', ');
 if(!await dialogResult(dialog))return;
 const text=key=>form.elements[key].value.trim(),years=text('years');
 const stored=current?storedSkill(current):null;
 const values={name:text('name'),aliases:text('aliases').split(',').map(a=>a.trim()).filter(Boolean),years:years===''?null:Number(years.replace(',','.')),level:text('level')||null,kind:text('kind'),usedAt:text('usedAt')||null,lastUsed:text('lastUsed')||null};
 await knowledgeAction({kind:'ui-skill-save',...(current?{id:current.id,expected:stored}:{}),values},'Competencia guardada.');
}
async function editAnswer(identifier){
 const current=(model.answerBank||[]).find(a=>a.id===identifier),dialog=document.querySelector('#answer-dialog'),form=dialog.querySelector('form');
 form.reset();form.elements.question.value=current?.question||'';form.elements.value.value=current?String(current.value===true?'Sí':current.value===false?'No':current.value):'';
 if(!await dialogResult(dialog))return;
 await knowledgeAction({kind:'ui-answer-save',...(current?{id:current.id,expected:{value:current.value,status:current.status}}:{}),question:form.elements.question.value.trim(),value:form.elements.value.value.trim()},'Respuesta guardada.');
}
function offerRequirementMatch(j){
 const m=j.requirementMatch;if(!m)return '';
 if(m.needsSkills)return (model.skills||[]).length||!j.draft?'':`<section class="case-section offer-requirements" data-offer-section="requirements"><div class="section-heading"><h2>Requisitos</h2></div><p class="helper">Confirma tus competencias en Mi perfil para comparar esta oferta con lo que sabes hacer.</p></section>`;
 const years=r=>r.askedYears?` (${r.askedYears} años${r.yourYears!==undefined?`; tú ${r.yourYears}`:''})`:'';
 const groups=[['Cumples',m.met],['Piden más años',m.gaps],['No consta en tus competencias',m.missing],['Por aclarar',m.unclear],['Valorable, no lo tienes',m.niceToHave]].filter(([,rows])=>rows.length);
 if(!groups.length)return '';
 return `<section class="case-section offer-requirements" data-offer-section="requirements"><div class="section-heading"><h2>Requisitos</h2></div><dl class="summary-list">${groups.map(([title,rows])=>`<div><dt>${title}</dt><dd>${rows.map(r=>esc(r.name+years(r))).join(', ')}</dd></div>`).join('')}</dl><p class="helper">Comparación orientativa por palabras: no descarta ofertas ni decide por ti.</p></section>`;
}
const PROFILE_SECTION_LEADS={'profile-about':'Lo que piden los formularios. Las encuestas y los datos sensibles son opcionales.','profile-experience':'La base de cada CV y solicitud. Tu agente solo da por cierto lo que confirmes.','profile-answers':'Lo que tu perfil no permite deducir. Se reutiliza aunque la pregunta cambie de palabras o de idioma.','profile-permissions':'Qué puede hacer tu agente sin volver a preguntarte. Solo tú los concedes; lo que no autorices, te lo pregunta.'};
// Each frame is a subsection: it has a title, says what it is for and holds what is useful together.
function profilePanel(id,title,lead,body,{action='',flush=false}={}){
 return `<div class="profile-panel${flush?' profile-panel--flush':''}" role="group" aria-labelledby="panel-${id}"><div class="profile-panel-head"><div class="profile-panel-title"><h3 id="panel-${id}">${esc(title)}</h3>${lead?`<p>${lead}</p>`:''}</div>${action}</div>${body}</div>`;
}
function profileCard(id,body){
 const title=profileSections.find(([key])=>key===id)[1],lead=PROFILE_SECTION_LEADS[id];
 return `<section class="profile-card" id="${id}"><div class="profile-section-head"><h2>${esc(title)}</h2>${lead?`<p>${esc(lead)}</p>`:''}</div><div class="profile-fields">${body}</div></section>`;
}
// What is left in each section, shown beside its name in the index. Empty when nothing is pending.
function profileStatus(id,live=false){
 const about=formSource('about'),search=formSource('search'),filled=value=>String(value??'').trim()!=='';
 const value=(key,source)=>{const control=live?main.querySelector?.(`[name="${key}"]`):null;return control&&typeof control.value==='string'?control.value:source[key];};
 if(id==='profile-about'){const missing=['name','email','phone'].filter(key=>!filled(value(key,about))).length;return profileMissing(missing);}
 if(id==='profile-experience'){
  const skills=model.skills||[],pending=skills.filter(s=>s.status!=='confirmed'||s.years==null).length;
  if(!filled(value('text',{text:model.experience})))return 'Sin completar';
  return pending?`${pending} por confirmar`:skills.length?'':'Sin competencias';
 }
 if(id==='profile-work'){const missing=['targetRoles','contract','minimumFixed'].filter(key=>!filled(value(key,search))).length+(filled(value('location',search))||filled(search.regions)?0:1);return profileMissing(missing);}
 if(id==='profile-answers'){const review=(model.answerBank||[]).filter(answerNeedsReview).length;return review?`${review} con dudas`:'';}
 if(id==='profile-permissions'){const undecided=(window.StubbsJobsSetup.autoApplyPermissions||[]).filter(item=>[null,undefined,''].includes(value(item.key,model.profile||{}))).length;return undecided?`${undecided} sin decidir`:'';}
 return '';
}
function profileMissing(count){return !count?'':count===1?'Falta 1':`Faltan ${count}`;}
function profileStatusHtml(id,live=false){const text=profileStatus(id,live);return `<small class="profile-nav-status" data-profile-status="${id}">${esc(text)}</small>`;}
function syncProfileOverview(){if(screen!=='perfil'||selected)return;for(const node of main.querySelectorAll?.('[data-profile-status]')||[])if('textContent' in node)node.textContent=profileStatus(node.dataset.profileStatus,true);}
function legacyRecoveryItems(){
 let recovered=[];try{recovered=JSON.parse(draftStorage.getItem('stubbs_jobs-recovered-drafts')||'[]');if(!Array.isArray(recovered))recovered=[];}catch{}
 return window.StubbsJobsDrafts.legacyDrafts(sessionStorage,localStorage).filter(item=>!recovered.includes(JSON.stringify(item)));
}
function legacyRecovery(){
 const items=legacyRecoveryItems();if(!items.length)return '';
 const titles={datos:'Datos personales',experiencia:'Mi experiencia',busqueda:'Mis idiomas y lo que busco',fuentes:'Mis fuentes de búsqueda'};
 return `<details class="profile-card draft-recovery"><summary>Borradores de una versión anterior (${items.length})</summary><p>Comprueba que estos datos son tuyos. Su carpeta de origen no está registrada. Puedes recuperarlos como cambios sin guardar.</p>${items.map((item,index)=>`<section><h3>${titles[item.key.split(':')[1]]}</h3><dl class="summary-list">${Object.entries(item.value.values).map(([key,value])=>`<div><dt>${esc(model.labels?.[key]||window.StubbsJobsSetup.context[key]?.label||key==='text'&&'Experiencia'||key)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl><button type="button" data-recover-draft="${index}">Recuperar este borrador</button></section>`).join('')}</details>`;
}
async function recoverLegacyDraft(index){
 const item=legacyRecoveryItems()[index];if(!item)return;
 if(['busqueda','fuentes'].includes(item.key.split(':')[1])&&model.deletedSearchProfiles?.some(p=>p.id==='search-current')){openDeletedSearchProfiles();toast('Recupera el perfil anterior para incorporar su borrador.');return;}
 if(!await confirmAction('Recuperar borrador','Comprueba que el contenido es tuyo. Se incorporará a esta carpeta como cambios sin guardar para que puedas revisarlo.'))return;
 rememberAllForms();
 const section=item.key.split(':')[1],scoped=model.searchProfiles&&['busqueda','fuentes'].includes(section);
 const target=scoped?{...item,key:'stubbs_jobs-draft:'+section+':profile:search-current'}:item;
 window.StubbsJobsDrafts.recoverLegacy(draftStorage,target);
 if(scoped){
  searchProfileId='search-current';workspaceSession.setItem('stubbs_jobs-search-profile',searchProfileId);
 }
 if(draftStorage.isPersistent(target.key)){
  let recovered=[];try{recovered=JSON.parse(draftStorage.getItem('stubbs_jobs-recovered-drafts')||'[]');if(!Array.isArray(recovered))recovered=[];}catch{}
  draftStorage.setItem('stubbs_jobs-recovered-drafts',JSON.stringify([...recovered,JSON.stringify(item)]));
 }
 render(true);toast('Borrador recuperado. Revisa sus valores antes de guardarlo.');
}
function searchSettingsPanels(){
 const search=formSource('search'),sources=formSource('sources');
 const searchPlace=visibleSearchLocation(search.location,search.workMode,search.regions);search.location=searchPlace.location;search.workMode=searchPlace.workMode;
 const profile=currentSearchProfile(),scope=profile?` data-search-profile-id="${esc(profile.id)}"`:'';
 const lead=profile?'Cada perfil de búsqueda guarda sus propios criterios.':'Los criterios con los que tu agente busca y elige.';
 return `<section class="profile-card" id="profile-work"><div class="profile-section-head"><h2>Lo que busco</h2><p>${lead}</p></div>${profile?`<div class="profile-section-tools">${searchProfileControls()}</div>`:''}<div class="profile-fields"><form data-form="search" id="profile-search-form" class="profile-fields-form"${scope}>
  ${[['roles','Puesto','Lo que tu agente busca.',['targetRoles','keywords']],['place','Ubicación','Dónde quieres trabajar y de qué forma.',['location','workMode','onsiteLocations']],['terms','Requisitos','Si una oferta no los cumple, se archiva.',['contract','minimumFixed','maxTrips','requiredSchedule']],['notes','Preferencias','Orientan a tu agente, pero no descartan ofertas.',['salaryExpectationFixed','searchPriorities',...(profile?['searchNotes']:[]),'previousApplications']]].map(([id,title,panelLead,keys])=>profilePanel(id,title,panelLead,`<div class="profile-body">${searchCriteriaFields(search,keys,null,{flat:true})}</div>`)).join('')}${formErrors('search')}</form>
  <form data-form="sources" class="profile-fields-form"${scope}>${profilePanel('where','Dónde busca tu agente',`<span data-where-summary>${esc(whereSummaryText(sources))}</span>`,`<div class="where-body">${whereBody(sources)}</div>`,{action:whereScope(sources)})}${formErrors()}</form></div></section>`;
}
// Company boards the scanner checks, with what each one has produced for this person.
let sourceScope=null;
const whereProfileKey=()=>currentSearchProfile()?.id||model.defaultSearchProfileId||'';
function whereMap(){return model.whereMap?.[currentSearchProfile()?.id||model.defaultSearchProfileId]||null;}
function sourceScopeNow(sources){return sourceScope?.profile===whereProfileKey()?sourceScope.value:(String(sources.sourceUrls||'').trim()?'exclusive':'open');}
function excludedPortalSet(sources){return new Set(String(sources.excludedPortals||'').split(',').filter(Boolean));}
const whereLines=value=>[...new Set(String(value||'').split('\n').map(line=>line.trim()).filter(Boolean))];
const whereOff=sources=>new Set(String(sources.disabledSources??(model.sourceStats||[]).filter(s=>!s.enabled).map(s=>s.id).join(',')).split(',').filter(Boolean));
function whereLinkLabel(link){try{const parts=new URL(link);return parts.hostname.replace(/^www\.|^jobs\.|^careers\./,'')+(parts.pathname.length>1?parts.pathname.replace(/\/$/,''):'');}catch{return link;}}
const whereCount=(n,one,many)=>`${n} ${n===1?one:many}`;
// Company rows: the boards already checked, plus what was just added and is not saved yet.
function whereCompanies(sources){
 const followed=whereLines(sources.followedSources),stats=model.sourceStats||[],known=new Set(stats.map(s=>s.url).filter(Boolean));
 return [...stats.map(s=>({...s,removable:followed.includes(s.url)})),...followed.filter(link=>!known.has(link)).map(link=>({id:null,url:link,company:whereLinkLabel(link),removable:true,fresh:true}))];
}
function wherePortalTotals(sources){
 const map=whereMap(),excluded=excludedPortalSet(sources),usable=(map?.portals||[]).filter(p=>p.relevant);
 return {on:usable.filter(p=>!excluded.has(p.id)).length,all:usable.length};
}
function whereCompanyTotals(sources){
 const rows=whereCompanies(sources),off=whereOff(sources);
 return {on:rows.filter(row=>row.fresh||!off.has(row.id)).length,all:rows.length};
}
function whereSummaryText(sources){
 if(sourceScopeNow(sources)==='exclusive')return whereLines(sources.sourceUrls).length?'Solo en estas webs.':'Añade una web. Hasta entonces, busca en portales y empresas.';
 const portals=wherePortalTotals(sources).on,companies=whereCompanyTotals(sources).on;
 return `${whereCount(portals,'portal','portales')}, ${whereCount(companies,'empresa','empresas')} y otras webs públicas que encajen.`;
}
function whereScope(sources){
 const current=sourceScopeNow(sources),option=(key,label)=>`<button type="button" role="radio" aria-checked="${current===key}" data-source-scope="${key}">${label}</button>`;
 return `<div class="knowledge-filters where-scope" role="radiogroup" aria-label="Dónde busca">${option('open','Portales y empresas')}${option('exclusive','Solo mis webs')}</div>`;
}
function whereSwitchRow({name,note,warn,badge,input,remove='',off=false}){
 return `<div class="where-row${off?' where-row--off':''}"><label class="where-row-main"><span class="where-row-text"><span class="where-row-name">${esc(name)}${badge?`<span class="source-badge">${esc(badge)}</span>`:''}</span>${warn||note?`<small${warn?' class="where-row-warn"':''}>${esc(warn||note)}</small>`:''}</span>${input}</label>${remove}</div>`;
}
function wherePortalRow(portal,excluded){
 const stats=[portal.found&&whereCount(portal.found,'oferta','ofertas'),portal.sent&&whereCount(portal.sent,'enviada','enviadas')].filter(Boolean).join(' · ');
 const warn=portal.session==='login_required'?'Entra en tu cuenta':portal.session==='blocked'?'Bloqueado':portal.account==='search'&&portal.session!=='ready'?'Necesita tu cuenta':'';
 return whereSwitchRow({name:portal.name,note:portal.relevant?stats||portal.sector||'':'Fuera de tu zona',warn:portal.relevant?warn:'',off:!portal.relevant||excluded.has(portal.id),input:`<input type="checkbox" form="profile-knowledge-form" data-knowledge="1" data-portal-toggle="${esc(portal.id)}"${portal.relevant&&!excluded.has(portal.id)?' checked':''}${portal.relevant?'':' disabled'} aria-label="Buscar en ${esc(portal.name)}">`});
}
function whereHeading(title,counter,totals){return `<div class="where-heading"><span>${title}</span><small data-where-count="${counter}">${totals.on} de ${totals.all}</small></div>`;}
function wherePortals(sources){
 const map=whereMap();if(!map)return '';
 const excluded=excludedPortalSet(sources),rank=p=>!p.relevant?2:p.main||p.sent?0:1,portals=map.portals.map((p,index)=>[p,index]).sort((a,b)=>rank(a[0])-rank(b[0])||a[1]-b[1]).map(([p])=>p);
 return `<div class="where-group">${whereHeading('Portales','portals',wherePortalTotals(sources))}<div class="where-grid">${portals.map(p=>wherePortalRow(p,excluded)).join('')}</div></div>`;
}
function whereRemoveButton(list,link,name){return `<button type="button" class="where-remove" data-where-remove="${esc(link)}" data-where-list="${list}" aria-label="Quitar ${esc(name)}" title="Quitar">${icon('close')}</button>`;}
function whereCompanyRows(sources){
 const off=whereOff(sources);
 return whereCompanies(sources).map(row=>{
  const name=row.company||row.id||whereLinkLabel(row.url),stats=row.fresh?'Nueva':[whereCount(row.offers||0,'oferta','ofertas'),row.sent&&whereCount(row.sent,'enviada','enviadas')].filter(Boolean).join(' · ');
  return whereSwitchRow({name,note:stats,badge:row.lowYield&&!off.has(row.id)?'Poco útil':'',off:!row.fresh&&off.has(row.id),input:row.fresh?'':`<input type="checkbox" form="profile-knowledge-form" data-knowledge="1" data-company-toggle="${esc(row.id)}"${off.has(row.id)?'':' checked'} aria-label="Buscar en ${esc(name)}">`,remove:row.removable?whereRemoveButton('followedSources',row.url,name):''});
 }).join('');
}
function whereSiteRows(sources){
 return whereLines(sources.sourceUrls).map(link=>{const name=whereLinkLabel(link);return `<div class="where-row"><span class="where-row-main"><span class="where-row-text"><span class="where-row-name">${esc(name)}</span></span></span>${whereRemoveButton('sourceUrls',link,name)}</div>`;}).join('');
}
function whereAddRow(list,placeholder){
 return `<div class="where-add"><input type="url" form="profile-knowledge-form" data-knowledge="1" data-where-input="${list}" placeholder="${placeholder}" aria-label="${placeholder}"><button type="button" data-where-add="${list}">Añadir</button></div><p class="where-add-error" data-where-error="${list}" role="alert" hidden></p>`;
}
function whereBody(sources){
 const scope=sourceScopeNow(sources),off=[...whereOff(sources)].sort().join(',');
 const context=model.searchContext||{},platforms=(context.platforms||'').split(',').filter(Boolean);
 const priorities=platforms.length?`<div class="source-priorities"><p>Fuentes priorizadas: ${esc(platforms.map(id=>platformNames[id]||id).join(', '))}</p><button type="button" class="link-button" data-clear-platforms="1">Quitar prioridades</button></div>`:'';
 return `<input type="hidden" name="platforms" value="${esc(context.platforms||'')}"><input type="hidden" name="excludedPortals" value="${esc(sources.excludedPortals||'')}"><input type="hidden" name="followedSources" value="${esc(sources.followedSources||'')}"><input type="hidden" name="sourceUrls" value="${esc(sources.sourceUrls||'')}"><input type="hidden" name="disabledSources" value="${esc(off)}">${priorities}
 <div class="where-panel" data-source-panel="open"${scope==='exclusive'?' hidden':''}>${wherePortals(sources)}<div class="where-group">${whereHeading('Empresas','companies',whereCompanyTotals(sources))}<div class="where-grid" data-where-rows="followedSources">${whereCompanyRows(sources)}</div>${whereAddRow('followedSources','Pega la web de empleo de una empresa')}</div><p class="helper where-help">No necesitas cuenta para empezar: si una oferta la exige, te avisa.</p></div>
 <div class="where-panel" data-source-panel="exclusive"${scope==='exclusive'?'':' hidden'}><div class="where-group"><div class="where-grid" data-where-rows="sourceUrls">${whereSiteRows(sources)}</div>${whereAddRow('sourceUrls','Pega una web donde buscar')}</div></div>`;
}
function whereValues(form){
 const read=name=>form.elements.namedItem(name)?.value??'';
 return {sourceUrls:read('sourceUrls'),followedSources:read('followedSources'),excludedPortals:read('excludedPortals'),disabledSources:read('disabledSources')};
}
function syncWherePanel(){
 const form=main.querySelector?.('form[data-form="sources"]');if(!form?.elements)return;
 const values=whereValues(form),excluded=excludedPortalSet(values),off=whereOff(values);
 for(const box of main.querySelectorAll('[data-portal-toggle]'))if(!box.disabled){box.checked=!excluded.has(box.dataset.portalToggle);box.closest?.('.where-row')?.classList?.toggle('where-row--off',!box.checked);}
 for(const box of main.querySelectorAll('[data-company-toggle]')){box.checked=!off.has(box.dataset.companyToggle);box.closest?.('.where-row')?.classList?.toggle('where-row--off',!box.checked);}
 const scope=sourceScopeNow(values);
 for(const panel of main.querySelectorAll('[data-source-panel]'))panel.hidden=panel.dataset.sourcePanel!==scope;
 for(const button of main.querySelectorAll('[data-source-scope]'))button.setAttribute('aria-checked',String(button.dataset.sourceScope===scope));
 const summary=main.querySelector('[data-where-summary]');if(summary)summary.textContent=whereSummaryText(values);
 const counts={portals:wherePortalTotals(values),companies:whereCompanyTotals(values)};
 for(const [name,totals] of Object.entries(counts)){const label=main.querySelector(`[data-where-count="${name}"]`);if(label)label.textContent=`${totals.on} de ${totals.all}`;}
}
function repaintWhereRows(form){
 const values=whereValues(form),companies=main.querySelector('[data-where-rows="followedSources"]'),sites=main.querySelector('[data-where-rows="sourceUrls"]');
 if(companies)companies.innerHTML=whereCompanyRows(values);if(sites)sites.innerHTML=whereSiteRows(values);
}
function setSourceScope(scope){
 const form=main.querySelector('form[data-form="sources"]');if(!form)return;
 const follow=form.elements.namedItem('followedSources'),only=form.elements.namedItem('sourceUrls');
 // The same list moves with the choice, so changing it never loses what was typed.
 if(scope==='exclusive'&&follow.value.trim()&&!only.value.trim()){only.value=follow.value;follow.value='';}
 if(scope==='open'&&only.value.trim()){follow.value=[follow.value,only.value].filter(item=>item.trim()).join('\n');only.value='';}
 sourceScope={profile:whereProfileKey(),value:scope};form._lastEditedField='sourceUrls';repaintWhereRows(form);syncWherePanel();rememberForm(form);
}
function addWhereLink(list){
 const form=main.querySelector('form[data-form="sources"]'),input=main.querySelector(`[data-where-input="${list}"]`),error=main.querySelector(`[data-where-error="${list}"]`),field=form?.elements.namedItem(list);if(!field||!input)return;
 let link=input.value.trim();if(!link)return;if(!/^https?:\/\//i.test(link))link='https://'+link;
 let valid=false;try{valid=new URL(link).hostname.includes('.');}catch{}
 if(error){error.hidden=valid;error.textContent=valid?'':'Esa dirección no parece una web.';}if(!valid)return;
 field.value=whereLines(field.value+'\n'+link).join('\n');input.value='';form._lastEditedField=list;repaintWhereRows(form);syncWherePanel();rememberForm(form);input.focus?.();
}
function removeWhereLink(list,link){
 const form=main.querySelector('form[data-form="sources"]'),field=form?.elements.namedItem(list);if(!field)return;
 field.value=whereLines(field.value).filter(line=>line!==link).join('\n');form._lastEditedField=list;repaintWhereRows(form);syncWherePanel();rememberForm(form);
}
function currentSearchProfile(){return model.searchProfiles?.find(p=>p.id===searchProfileId)||null;}
function searchProfileIconButton(action,label,name){return `<button type="button" class="profile-action-icon" data-search-profile-action="${action}" aria-label="${label}" title="${label}">${icon(name)}</button>`;}
function searchProfileControls(){
 const profile=currentSearchProfile();if(!profile)return '';
 const archived=!!profile.archivedAt,primary=profile.id===model.defaultSearchProfileId;
 const icons=searchProfileIconButton('create','Crear perfil de búsqueda','plus')+searchProfileIconButton('duplicate','Duplicar perfil de búsqueda','copy')+searchProfileIconButton('rename','Renombrar perfil de búsqueda','pencil');
 const management=archived?'<button type="button" data-search-profile-action="restore">Recuperar</button>':`${primary?'':'<button type="button" data-search-profile-action="default">Usar por defecto</button>'}`;
 return `<div class="search-profile-controls"><label class="field"><span>Perfil de búsqueda</span><select data-search-profile="1"${archived?' aria-describedby="search-profile-help"':''}>${model.searchProfiles.map(p=>`<option value="${esc(p.id)}"${p.id===profile.id?' selected':''}>${esc(p.name)}${p.archivedAt?' · Archivado':p.id===model.defaultSearchProfileId?' · Predeterminado':''}</option>`).join('')}</select></label><div class="actions">${icons}${management}${primary?'':searchProfileIconButton('delete','Eliminar perfil de búsqueda','trash')}</div></div>${archived?'<p class="helper" id="search-profile-help">Perfil archivado de una versión anterior. Recupéralo para editar sus criterios.</p>':''}${model.deletedSearchProfiles?.length?`<button type="button" class="link-button" data-search-profile-trash="1">Papelera (${model.deletedSearchProfiles.length})</button>`:''}`;
}
function openDeletedSearchProfiles(){
 const dialog=document.querySelector('#search-profile-trash-dialog');
 dialog.querySelector('.deleted-search-profiles').innerHTML=(model.deletedSearchProfiles||[]).map(p=>`<li><span>${esc(p.name)}</span><button type="button" data-search-profile-restore="${esc(p.id)}" aria-label="Recuperar ${esc(p.name)}">Recuperar</button></li>`).join('')||'<li>La papelera está vacía.</li>';
 dialog.showModal();
}
async function chooseSearchProfile(identifier){
 if(saving||actionBusy||profileSaving)return;
 if(!model.searchProfiles?.some(p=>p.id===identifier))return;
 const restoreSelector=()=>{const select=main.querySelector?.('[data-search-profile]');if(select){select.value=searchProfileId;select.focus?.();}};
 if(visibleForms().some(form=>form._dirty&&['search','sources'].includes(form.dataset.form))&&!await settleUnsavedProfile('Has cambiado {sections}. ¿Qué quieres hacer antes de cambiar de perfil de búsqueda?','Guardar y cambiar')){restoreSelector();return;}
 rememberAllForms();searchProfileId=identifier;workspaceSession.setItem('stubbs_jobs-search-profile',identifier);
 dirty=false;conflict=null;render(true);restoreSelector();
}
async function searchProfileAction(kind,identifier=searchProfileId){
 const profile=[...(model.searchProfiles||[]),...(model.deletedSearchProfiles||[])].find(p=>p.id===identifier);if(!profile||saving||actionBusy||profileSaving)return;
 if(visibleForms().some(f=>f._dirty)){toast('Guarda los cambios de este perfil antes de modificar su organización.');return;}
 const op={kind:'ui-search-profile',action:kind,id:profile.id,expectedRevision:model.revision};
 if(['create','duplicate','rename'].includes(kind)){
  const dialog=document.querySelector('#search-profile-name-dialog'),input=dialog.querySelector('input');
  dialog.querySelector('h2').textContent={create:'Crear perfil de búsqueda',duplicate:'Duplicar perfil de búsqueda',rename:'Renombrar perfil de búsqueda'}[kind];
  input.value=kind==='rename'?profile.name:kind==='duplicate'?profile.name+' · Copia':'';
  dialog.returnValue='cancel';dialog.showModal();input.focus();
  if(!await new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='ok'),{once:true})))return;
  op.name=input.value.trim();if(!op.name)return;
  if(kind!=='rename')op.newId='search-'+crypto.randomUUID();
 }
 if(kind==='delete'&&!await confirmAction('Eliminar '+profile.name,'Se retirará del selector de perfiles. Las ofertas y solicitudes conservarán sus criterios. Puedes recuperarlo desde Papelera.'))return;
 if(await action(op)){
  if(op.newId)searchProfileId=op.newId;
  if(kind==='restore'){searchProfileId=op.id;const dialog=document.querySelector('#search-profile-trash-dialog');if(dialog?.open)dialog.close();}
  workspaceSession.setItem('stubbs_jobs-search-profile',searchProfileId);
  render(true);toast({create:'Perfil creado. Completa sus criterios.',duplicate:'Perfil duplicado.',rename:'Nombre guardado.',restore:'Perfil recuperado.',default:'Perfil predeterminado guardado.',delete:'Perfil eliminado. Puedes recuperarlo en Papelera.'}[kind]);
 }
}
// Who chose the offer: the person, or the agent following their recorded instruction.
function selectionOrigin(j){
 const choice=j.selection;if(!choice?.selected||j.sent)return '';
 if(choice.mandate)return `<p class="offer-selection-origin">La eligió el agente porque se lo pediste: «${esc(conciseText(choice.mandate.text,160))}»${tableTimestamp(choice.mandate.at)!==null?` · ${esc(date(choice.mandate.at))}`:''}</p>`;
 if(['Agente','Sistema'].includes(choice.actor))return `<p class="offer-selection-origin">La eligió el agente sin que se lo pidieras${choice.mode==='auto'?', así que revisarás la solicitud antes del envío':''}.</p>`;
 return '';
}
function offerProfileControls(){
 if(!model.searchProfiles||model.searchProfiles.length<2)return '';
 const fallback=!offerProfileFilter&&searchRunProfile();
 return `<label class="offer-profile-filter">Perfil de búsqueda <select data-offer-profile="1"><option value="">Todos los perfiles</option>${model.searchProfiles.map(p=>`<option value="${esc(p.id)}"${offerProfileFilter===p.id?' selected':''}>${esc(p.name)}${p.archivedAt?' · Archivado':''}</option>`).join('')}</select>${offerProfileFilter?'<span class="helper">Ofertas agrupadas en este perfil.</span>':fallback?`<span class="helper">Las búsquedas nuevas usan «${esc(fallback.name)}» salvo que elijas otro perfil.</span>`:''}</label>`;
}
// A search is saved as a task for the person's agent, like choosing an offer:
// nothing is copied and no chat starts. Without a chosen profile, the default one is used.
function searchRunProfile(){
 const profiles=(model.searchProfiles||[]).filter(p=>!p.archivedAt);
 return profiles.find(p=>p.id===offerProfileFilter)||profiles.find(p=>p.id===model.defaultSearchProfileId)||null;
}
// A saved search stays visible until the agent finishes it, so the next step is never lost with the toast.
function searchStatusNote(){
 const active=(model.requests||[]).filter(r=>r.type==='discovery'&&['queued','running'].includes(r.status));
 if(!active.length)return '';
 const names=[...new Set(active.map(r=>(model.searchProfiles||[]).find(p=>p.id===(r.searchProfileId||r.round?.searchProfileId))?.name||r.round?.searchProfileName).filter(Boolean))];
 const subject=names.length?' con '+names.map(name=>'«'+name+'»').join(', '):'';
 return `<p class="helper offers-search-status">${esc(active.some(r=>r.status==='running')?`Búsqueda${subject} en curso. Las ofertas nuevas aparecerán aquí.`:`Búsqueda${subject} guardada. Para iniciarla, pide «Continúa con Stubbs Jobs» en el chat de tu agente.`)}</p>`;
}
function searchRunLabel(){
 const profile=searchRunProfile();
 return profile&&offerProfileFilter===profile.id&&model.searchProfiles.length>1?'Buscar con este perfil':'Buscar ofertas nuevas';
}
function searchRunButton(){
 const profile=searchRunProfile();
 const hint=`Guarda una búsqueda${profile?` con «${profile.name}»`:''} para tu agente. Para iniciarla, pide «Continúa con Stubbs Jobs» en su chat.`;
 return `<button class="primary offers-search" data-run-search="${esc(profile?.id||'')}" title="${esc(hint)}">${icon('search')}${searchRunLabel()}</button>`;
}
async function runSearch(profileId){
 const profile=(model.searchProfiles||[]).find(p=>p.id===profileId),name=profile?` con «${profile.name}»`:'';
 if(!await action({kind:'ui-request',type:'discovery',...(profile?{searchProfileId:profile.id}:{})}))return false;
 const search=(model.requests||[]).filter(r=>r.type==='discovery'&&['queued','running','blocked','interrupted'].includes(r.status)&&(!profile||r.searchProfileId===profile.id))
  .sort((a,b)=>String(b.updatedAt||'').localeCompare(String(a.updatedAt||'')))[0];
 toast(search?.status==='running'?`Ya hay una búsqueda${name} en curso. Las ofertas nuevas aparecerán aquí.`
  :search&&search.status!=='queued'?`Hay una búsqueda anterior${name} detenida. Revísala al principio de Ofertas.`
  :search?`Búsqueda${name} guardada para el agente. Para iniciarla, pide «Continúa con Stubbs Jobs» en su chat.`
  :'No consta una búsqueda guardada con este perfil. Actualiza el estado y revisa Ofertas.');
 render(true);return true;
}
// Announcements captured by a search that nobody has screened yet. They are
// not offers: adding one creates an offer for the agent to check; discarding is undoable.
function visiblePendingEntries(){return (model.pendingEntries||[]).filter(e=>!offerProfileFilter||e.searchProfileIds?.includes(offerProfileFilter)||!e.searchProfileIds?.length&&offerProfileFilter===model.defaultSearchProfileId);}
function pendingEntriesPanel(){
 const all=visiblePendingEntries();if(!all.length)return '';
 const names=Object.fromEntries((model.searchProfiles||[]).map(p=>[p.id,p.name])),several=(model.searchProfiles||[]).length>1&&!offerProfileFilter;
 const link=(e,text)=>/^https?:\/\//i.test(e.url||'')?`<a href="${esc(e.url)}" target="_blank" rel="noopener">${text}</a>`:text;
 const rows=all.slice(0,entryLimit).map(e=>{
  const meta=[e.firstSeenAt?'Encontrado '+discoveryTime(e.firstSeenAt).toLowerCase():'',e.location,several?(e.searchProfileIds||[]).map(id=>names[id]).filter(Boolean).join(', '):''].filter(Boolean);
  return `<li><div class="pending-entry-text">${link(e,`<strong>${esc(e.company||'Empresa sin nombre')}</strong> · ${esc(e.title||'Puesto sin título')}`)}${meta.length?`<small>${esc(meta.join(' · '))}</small>`:''}</div><div class="pending-entry-actions"><button class="link-button" data-entry-add="${esc(e.id)}">Añadir a ofertas</button><button class="link-button" data-entry-discard="${esc(e.id)}">Descartar</button></div></li>`;
 }).join('');
 const more=all.length>entryLimit?`<button class="link-button" data-more-entries="1">Ver más (${all.length-entryLimit})</button>`:'';
 return `<details class="pending-entries" id="pending-entries"><summary>${icon('search')}<strong>${all.length} ${all.length===1?'anuncio encontrado sin revisar':'anuncios encontrados sin revisar'}</strong><span class="pending-entries-chevron" aria-hidden="true">${icon('chevron-down')}</span></summary><div class="pending-entries-body"><p class="helper">Las búsquedas los encontraron, pero el agente aún no los ha revisado y no aparecen en la tabla. Los revisará en tu próxima búsqueda. También puedes añadir uno a Ofertas para que lo compruebe, o descartarlo.</p><ol class="pending-entries-list">${rows}</ol><div class="pending-entries-footer">${more}<button data-entries-discard="1">${all.length===1?'Descartar este anuncio':'Descartar los '+all.length+' anuncios'}</button></div></div></details>`;
}
async function discardEntries(ids){
 if(!ids.length)return;
 if(ids.length>1&&!await confirmAction('Descartar anuncios',`Se descartarán ${ids.length} anuncios sin revisar. No se crean ofertas ni solicitudes, y podrás deshacerlo.`))return;
 for(let start=0;start<ids.length;start+=500){
  if(!await action({kind:'ui-entry-decision',decision:'discard',entryIds:ids.slice(start,start+500),expectedRevision:model.revision}))return;
 }
 changeToast(ids.length===1?'Anuncio descartado.':ids.length+' anuncios descartados.');render(true);
}
async function addEntry(id){
 const entry=(model.pendingEntries||[]).find(e=>e.id===id);if(!entry)return;
 if(!await action({kind:'ui-add-opportunity',values:{company:entry.company||'Empresa sin nombre',title:entry.title||'Puesto sin título',url:entry.url},...(entry.searchProfileIds?.length===1?{searchProfileId:entry.searchProfileIds[0]}:{})}))return;
 toast('Oferta añadida para que el agente la compruebe. Para iniciarlo, pide «Continúa con Stubbs Jobs» en su chat.');render(true);
}
function offerProfileBasis(j){
 if(!model.searchProfiles||model.searchProfiles.length<2&&!j.searchProfileDeleted)return '';
 const evaluation=`Perfil de evaluación: ${j.searchProfileName||'búsqueda anterior'}${j.searchProfileDeleted?' (eliminado)':''}`;
 return j.displaySearchProfileId&&j.displaySearchProfileId!==j.searchProfileId
  ?`${evaluation} · En Ofertas: ${j.displaySearchProfileName||'otro perfil'}`:evaluation;
}
// Personal notes live in Más acciones: they never reach the application.
function offerNotes(j){
 return `<form class="offer-notes" data-form="offer-note"><label class="field"><span>Notas de seguimiento</span><textarea name="Notas de seguimiento" rows="3" maxlength="10000">${esc(j.notes||'')}</textarea></label><p class="helper">Solo para ti: no se envían ni cambian la solicitud.</p>${formErrors()}<button type="submit">Guardar nota</button></form>`;
}
function offerCriteriaControls(j){
 if(!model.searchProfiles||j.sent||['Cerrada','Lograda','Rechazada','Oferta'].includes(j.state))return '';
 const available=model.searchProfiles.filter(p=>!p.archivedAt);
 if(!available.length||model.searchProfiles.length<2&&!j.searchProfileDeleted&&j.criteriaScope!=='round')return '';
 // Without a fit summary, the current search profile is named next to the change.
 const basis=!offerAssessment(j)&&offerProfileBasis(j);
 return `<div class="offer-profile-management">${basis?`<p class="helper offer-criteria-basis">${esc(basis)}</p>`:''}<div class="offer-criteria-change"><label>Valorar con otro perfil de búsqueda <select data-offer-criteria-profile="${esc(j.id)}"><option value="">Elige un perfil</option>${available.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></label><button type="button" data-offer-criteria-change="${esc(j.id)}">Ver efecto</button></div><p class="helper">Puede cambiar el encaje de la oferta y obligar a revisar de nuevo la solicitud.</p></div>`;
}
async function changeOfferCriteria(id){
 const input=[...main.querySelectorAll('[data-offer-criteria-profile]')].find(x=>x.dataset.offerCriteriaProfile===id),identifier=input?.value;
 if(!identifier)return;
 const result=await api('/api/criteria-preview',{mode:'current',searchProfileId:identifier,targets:[{id}]});
 const lines=window.StubbsJobsCriteria.lines(result),name=model.searchProfiles.find(p=>p.id===identifier)?.name;
 if(!await confirmAction('Evaluar con '+name,lines.length?lines.join('. ')+'.':'La oferta se evaluará con este perfil.'))return;
 if(await action({kind:'ui-criteria-scope',mode:'current',searchProfileId:identifier,targets:[{id}],expectedRevision:result.revision,
   proof:'La persona cambia explícitamente la base de evaluación a '+name+'.'})){render(true);toast('Criterios de la oferta actualizados.');}
}
function scheduleForm(){
 return `<div class="form-wrap">${top('Búsqueda diaria')}<p>Si quieres repetir la búsqueda cada día, prográmala en tu agente. Stubbs Jobs no controla ni comprueba ese horario.</p></div>`;
}
let backupResult=null;
function backupDrafts(){
 const sections={datos:['Datos personales','profile-about'],experiencia:['Experiencia','profile-experience'],busqueda:['Lo que busco','profile-work'],fuentes:['Lo que busco','profile-work']};
 return window.StubbsJobsDrafts.pending(draftStorage).map(({key})=>{
  const [,page,scope]=key.match(/^stubbs_jobs-draft:([^:]+):(.+)$/),id=scope==='global'?null:scope,job=id&&getJob(id);
  if(scope.startsWith('profile:')&&sections[page]){
   const identifier=scope.slice(8),profile=[...(model.searchProfiles||[]),...(model.deletedSearchProfiles||[])].find(p=>p.id===identifier);
   return {key,label:sections[page][0]+' · '+(profile?.name||'Perfil anterior')+(profile?.deletedAt?' · Perfil eliminado':''),page:'perfil',id:null,section:sections[page][1],searchProfileId:identifier};
  }
  if(sections[page]&&!id){
   if(page==='busqueda'){const draft=JSON.parse(draftStorage.getItem(key)),fields=Object.keys(draft.values).filter(field=>String(draft.values[field]??'')!==String(draft.shown[field]??'')),groupIds=new Set((fields.length?fields:Object.keys(draft.attempt?.operation.values||draft.values)).map(field=>profileFieldSection('search',field))),groups=profileSections.filter(([id])=>groupIds.has(id));if(groups.length)return {key,label:groups.map(([,label])=>label).join(', '),page:'perfil',id:null,section:fields.length===1&&fields[0]==='previousApplications'?'profile-previous':groups[0][0]};}
   return {key,label:sections[page][0],page:'perfil',id:null,section:sections[page][1]};
  }
  const label=({perfil:id?'Respuestas':'Datos de Mi perfil de una versión anterior',editar:'Borrador de solicitud',cambio:'Petición para el agente',nueva:'Oferta por añadir',detalle:'Nota de seguimiento'})[page]||'Borrador de una pantalla anterior';
  const target=['perfil','editar','cambio','nueva','detalle'].includes(page)&&(!id||job)&&!(page==='perfil'&&!id)?page:null;
  const entry={key,label:label+(job?' · '+job.company:''),page:target,id};
  if(!target){const saved=JSON.parse(draftStorage.getItem(key));entry.content=Object.entries(saved.values).map(([field,value])=>[model.labels?.[field]||window.StubbsJobsSetup.context[field]?.label||field,value===null?'Sin respuesta':value===true?'Sí':value===false?'No':String(value)]);}
  return entry;
 });
}
function recoveryPanel(){return window.StubbsJobsExplanations.recovery(model,backupResult,{esc,pendingDrafts:backupDrafts()});}
async function createBackup(button){
 if(dirty||saving||actionBusy||profileSaving)throw new Error('Guarda los cambios pendientes antes de crear la copia.');
 if(backupDrafts().length&&button.dataset.backupSavedOnly!=='1'){render(true);toast('Hay borradores sin guardar. Revisa el aviso antes de crear una copia de los datos guardados.');return;}
 button.disabled=true;
 try{
  const result=await api('/api/backup',{});
  if(!result.download||!result.name||!Number.isInteger(result.files))throw new Error('No se pudo confirmar la copia. Consulta Copias de seguridad para comprobarla con tu agente.');
  backupResult=result;render(true);toast('Copia comprobada. Puedes descargarla o conservarla en esta carpeta.');
 }finally{button.disabled=false;}
}
function backupsPage(){return `<div class="form-wrap backups-view">${top('Copias de seguridad','Conserva tus datos y recupera una copia en una carpeta aparte.')}${recoveryPanel()}${window.StubbsJobsRelease?`<p class="helper release-info">${esc(window.StubbsJobsRelease.label)} · ${esc(window.StubbsJobsRelease.version)} · ${esc(window.StubbsJobsRelease.platform)}</p>`:''}</div>`;}
function changeForm(){
 const j=selected?getJob(selected):null,blocked=j?.requests.find(r=>!window.StubbsJobsWorkflow.task(r).superseded&&r.type!=='change'&&['blocked','interrupted'].includes(r.status));
  const queued=j?.requests.find(r=>r.type==='change'&&r.status==='queued');
  const guidance={contact:{title:'Indicar el contacto',label:'Contacto que conoces',placeholder:'Indica cómo contactar y cómo puede comprobarlo el agente.',hint:'Esto no autoriza mensajes ni invitaciones. Para dar un permiso concreto, díselo al agente en su chat.'},access:{title:'Explicar el acceso',label:'Qué ocurre con el acceso',placeholder:'Por ejemplo: ya inicié sesión, o no tengo cuenta en este portal.',hint:'Nunca escribas contraseñas aquí.'},answers:{title:'Responder',label:'Dato que puedes confirmar',placeholder:'Escribe solo lo que sabes con certeza.',hint:'El agente decidirá cómo usarlo en la solicitud.'},decision:{title:'Decidir',label:'Tu decisión',placeholder:'Explica lo que sabes con certeza; si no lo recuerdas, dilo.',hint:'El agente comprobará que no haya una solicitud duplicada antes de seguir.'},other:{title:'Responder al agente',label:'Lo que puedes aportar',placeholder:'Explica el dato o el paso pendiente.',hint:'El agente lo revisará antes de seguir.'}}[blocked?.need]||null;
  const title=guidance?.title||(j?'Pedir cambio':'Pedir un cambio en Mi perfil'),subtitle=j?esc(displayCase(j.company))+' · '+esc(displayCase(j.title)):'';
  const label=guidance?.label||(j?'Qué quieres cambiar de esta oferta':'Qué quieres cambiar');
  return `<div class="form-wrap">${top(title,subtitle)}${blocked?`<p class="notice">${esc(blocked.summary||'Esta solicitud necesita una aclaración.')}</p>`:j?`<p>${esc(UI.step(j).detail)}</p>`:''}${queued?.instructions?.length?`<section class="section"><h2>Ya le pediste al agente</h2><p class="note-text">${esc(queued.instructions.map(i=>i.text).join('\n'))}</p><p class="helper">Puedes añadir otra aclaración a este trabajo pendiente.</p></section>`:''}<form data-form="change" class="panel"><label class="field"><span>${esc(label)}</span><textarea name="message" rows="5" maxlength="5000" required placeholder="${esc(guidance?.placeholder||'Por ejemplo: revisa cómo encaja mi experiencia con esta oferta.')}"></textarea></label><p class="helper">${esc(guidance?.hint||'Pedir un cambio no reabre la oferta ni autoriza un envío.')}</p><p class="helper">Después, pide «Continúa con Stubbs Jobs» en el chat del agente.</p>${formErrors()}<div class="form-actions"><button class="primary" type="submit">${blocked?'Guardar respuesta':'Guardar petición'}</button><span class="shortcut-hint" aria-hidden="true"><kbd>Ctrl</kbd><kbd>S</kbd></span></div></form></div>`;
}
function editForm(){const j=getJob(selected);return `<div class="form-wrap">${top('Borrador para '+esc(displayCase(j.company)),'Al guardar se revisará el borrador.')}<form data-form="draft" class="panel"><label class="field"><span>Destino</span><input name="recipient" maxlength="15000" value="${esc(j.draft.recipient)}"></label>${UI.presentationVisible(j.draft)?`<p class="helper">${esc(UI.presentationUsage(j.draft))}</p><label class="field"><span>Presentación</span><textarea name="message" rows="6" maxlength="15000">${esc(j.draft.message)}</textarea></label>`:''}${formErrors()}<div class="form-actions"><button class="primary" type="submit">Guardar borrador</button><span class="shortcut-hint" aria-hidden="true"><kbd>Ctrl</kbd><kbd>S</kbd></span></div></form></div>`;}
function cvCardKey(cv,nameCounts){
 if(cv.id)return 'id:'+cv.id;
 if(cv.fingerprint)return 'fingerprint:'+cv.fingerprint+':'+(cv.path||cv.url||'');
 for(const field of ['path','url'])if(cv[field])return field+':'+cv[field];
 if(cv.name&&nameCounts.get(cv.name)===1)return 'name:'+cv.name;
 if(!anonymousCvKeys.has(cv))anonymousCvKeys.set(cv,'view:'+ ++anonymousCvSequence);
 return anonymousCvKeys.get(cv);
}
let cvDetail=null;
function cvEntry(cv,key){
 const recorded=Array.isArray(cv.usage)?cv.usage:null,byOffer=new Map();
 for(const item of recorded||[])if(item&&['prepared','sent'].includes(item.kind)&&item.opportunityId){const previous=byOffer.get(item.opportunityId);if(!previous||previous.kind!=='sent')byOffer.set(item.opportunityId,item);}
 const usage=[...byOffer.values()],own=usage.filter(item=>item.kind==='sent'&&item.reportedBy==='user').length,sent=usage.filter(item=>item.kind==='sent').length-own,prepared=usage.length-sent-own;
 const counts=usage.length?[`${usage.length} ${usage.length===1?'oferta':'ofertas'}`,prepared&&`${prepared} ${prepared===1?'preparado':'preparados'}`,sent&&`${sent} ${sent===1?'envío confirmado':'envíos confirmados'}`,own&&`${own} ${own===1?'enviado por ti':'enviados por ti'}`].filter(Boolean).join(' · '):recorded?.length===0?'Sin ofertas asociadas':'Uso no registrado';
 return {cv,key,recorded,usage,counts,available:cv.available!==false&&Boolean(cv.url)};
}
function cvOpenLink({cv,available}){return available?`<a class="cv-card-open" href="${esc(cv.url)}" target="_blank" rel="noopener" aria-label="Abrir PDF: ${esc(cv.name)}">Abrir PDF</a>`:'<span class="cv-card-unavailable">PDF no disponible</span>';}
function cvDetailPage(entry){
 const {cv,key,recorded,usage,counts,available}=entry;
 const uses=usage.length?`<ul class="cv-usage-list">${usage.map(item=>`<li><a class="cv-usage-offer" id="cv-usage-${encodeURIComponent(key)}-${encodeURIComponent(item.opportunityId)}" href="#detalle/${encodeURIComponent(item.opportunityId)}" data-job="${esc(item.opportunityId)}" data-cv-key="${esc(key)}"><span class="cv-usage-company">${esc(item.company||'Oferta vinculada')}</span>${item.title?`<span class="cv-usage-title">${esc(item.title)}</span>`:''}</a><div class="cv-usage-meta"><span class="cv-usage-state${item.kind==='sent'?' cv-usage-state--sent':''}" data-kind="${item.kind}">${item.kind==='sent'?(item.reportedBy==='user'?'Enviado por ti':'Envío confirmado'):'CV preparado'}</span>${item.at||item.historical?`<small>${item.at?date(item.at):''}${item.at&&item.historical?' · ':''}${item.historical?'Registro anterior':''}</small>`:''}</div></li>`).join('')}</ul>`:`<p class="muted cv-usage-empty">${recorded?.length===0?'Sin solicitudes asociadas.':'Aún no hay usos registrados para este CV.'}</p>`;
 return `<div class="cv-detail"><button type="button" class="quiet back cv-detail-back" data-cv-back="1">${icon('arrow-left')}<span>Currículums</span></button><div class="cv-library-heading"><h2 title="${esc(cv.name)}">${esc(cv.name)}</h2>${cvOpenLink(entry)}</div><p class="helper">${esc(counts)}</p>${available?'':'<p class="muted">Vuelve a añadir el PDF para abrirlo.</p>'}<div class="cv-detail-body"><div class="cv-detail-uses">${profilePanel('cv-uses','Ofertas con este CV','Dónde se ha preparado o enviado este mismo documento.',uses,{flush:true})}</div>${available?`<a class="cv-detail-preview" href="${esc(cv.url)}" target="_blank" rel="noopener" aria-label="Abrir PDF: ${esc(cv.name)}"><img alt="Primera página de ${esc(cv.name)}" loading="lazy" src="${esc(cv.url.replace('/api/document?','/api/preview?'))}"></a>`:''}</div></div>`;
}
function cvLibrary(){
  const cvs=model.cvLibrary||[],nameCounts=new Map();for(const cv of cvs)nameCounts.set(cv.name,(nameCounts.get(cv.name)||0)+1);
  const entries=cvs.map(cv=>cvEntry(cv,cvCardKey(cv,nameCounts))),open=cvDetail?entries.find(entry=>entry.key===cvDetail):null;
  const row=entry=>`<article class="cv-row" data-cv-row="${esc(entry.cv.name.toLowerCase())}"><button type="button" class="cv-row-open" data-cv-open="${esc(entry.key)}">${icon('file','cv-card-icon')}<span class="cv-row-identity"><span class="cv-row-title" title="${esc(entry.cv.name)}">${esc(entry.cv.name)}</span><span class="cv-card-counts">${esc(entry.counts)}</span></span>${icon('chevron-right','cv-row-chevron')}</button>${cvOpenLink(entry)}</article>`;
  const upload='<label class="button upload-label">Añadir PDF<input id="cv-upload" type="file" accept="application/pdf,.pdf" aria-label="Añadir currículum en PDF"></label>';
  const list=`<div class="profile-section-head"><h2>Currículums</h2><p>Los documentos que tu agente adjunta y adapta a cada oferta.</p></div>${profilePanel('cvs','Tus currículums','PDF de hasta 10 MB. Se guarda en este ordenador al añadirlo. Pulsa un currículum para ver las ofertas en las que se ha usado.',`${entries.length>8?`<div class="knowledge-toolbar"><input type="search" class="knowledge-search cv-filter" form="profile-knowledge-form" data-knowledge="1" data-cv-filter="1" placeholder="Buscar en tus currículums" aria-label="Buscar en tus currículums"></div>`:''}${entries.length?`<div class="cv-list">${entries.map(row).join('')}</div>`:'<div class="cv-library-empty"><p>Aún no hay currículums guardados. Puedes añadir un PDF o, si no tienes CV, tu agente prepara uno a partir de tu experiencia y competencias.</p></div>'}`,{flush:true,action:upload})}`;
  const guidelines=profilePanel('cv-guidelines','Indicaciones para tus CV','Qué debe tener en cuenta tu agente al adaptar un CV a una oferta.',`<div class="profile-body"><div class="profile-field-wide">${fieldHtml('cvGuidelines',{...sectionDefinitions('search').cvGuidelines,form:'profile-search-form',labelClass:'sr-only'},formSource('search').cvGuidelines)}</div></div>`);
  return `<section class="profile-card" id="profile-cv">${open?cvDetailPage(open):list}<div class="cv-guidelines"${open?' hidden':''}>${guidelines}</div></section>`;
}
function openCvDetail(key){
 rememberAllForms();cvDetail=key;profileSection='profile-cv';render(true);
 window.history.pushState(null,'','#profile-cv/'+encodeURIComponent(key));
 window.scrollTo?.({top:0,behavior:'instant'});
 const heading=document.getElementById('profile-cv')?.querySelector?.('h2');heading?.setAttribute?.('tabindex','-1');heading?.focus?.({preventScroll:true});
}
function closeCvDetail(push=true){
 const key=cvDetail;rememberAllForms();cvDetail=null;render(true);
 if(push)window.history.pushState(null,'','#perfil');
 [...main.querySelectorAll('[data-cv-open]')].find(button=>button.dataset.cvOpen===key)?.focus?.();
}
function history(){
  const j=selected?getJob(selected):null,items=j?caseHistory(j):model.history;
  const historyIds=new Set(items.map(h=>h.id)),orphanUndo=(model.undo||[]).filter(u=>(!j||u.opportunityId===j.id)&&!historyIds.has(u.id));
  return `<div class="detail-wrap activity-log">${top(j?'Actividad de '+esc(displayCase(j.company)):'Historial')}${searchActivity(items,historyLimit,!j)}${groupedActivity(items).length>historyLimit?'<button data-more-history="1">Cargar anteriores</button>':''}${j&&j.packages.length?`<section class="section"><h2>Versiones conservadas</h2>${j.packages.slice().reverse().map(p=>`<p>${date(p.createdAt)} · ${j.sent?.packageId===p.id?'Enviada':p.isCurrent?'Actual':'Anterior'} · <a href="${p.cvUrl}" target="_blank" rel="noopener">CV adaptado</a>${!UI.presentationVisible(p.payload)?'':` · <a href="${p.messageUrl}" target="_blank" rel="noopener">Presentación</a>`}</p>`).join('')}</section>`:''}${orphanUndo.length?`<section class="section"><h2>Cambios que puedes deshacer</h2>${orphanUndo.slice().reverse().map(u=>`<p>Cambio guardado <button data-undo="${esc(u.id)}">Deshacer</button></p>`).join('')}</section>`:''}</div>`;
}


function formSource(kind){if(kind==='offer-note')return {'Notas de seguimiento':getJob(selected)?.notes??null};if(['about','search','sources'].includes(kind)){const p=currentSearchProfile();return {...model.searchContext,...model.profile,salaryCurrency:model.profile.salaryCurrency??model.searchContext.currency??'',...(p?.searchContext||{}),...(p?.criteria||model.preferences),...(p?.formSalary||{}),...(kind==='sources'?{disabledSources:(model.sourceStats||[]).filter(s=>!s.enabled).map(s=>s.id).sort().join(',')}:{})};}return ['automation','schedule'].includes(kind)?model.automation:kind==='draft'?edit_token():kind==='preferences'?model.preferences:kind==='experience'?{text:model.experience}:kind==='context'?model.searchContext:kind==='new'?{company:'',title:'',url:''}:kind==='change'?{message:''}:selected?getJob(selected).answers:model.profile;}
function syncSourceControls(form){
 if(form?.dataset.form!=='sources')return;
 const priorities=form.querySelector?.('.source-priorities');if(priorities)priorities.hidden=!form.elements.namedItem('platforms')?.value;
}
function syncSalaryCurrency(form){
 const currency=form?.elements.namedItem(form?.dataset.searchProfileId?'salaryCurrency':'currency');if(!currency)return;
 for(const suffix of form.querySelectorAll?.('[data-salary-currency]')||[])suffix.textContent=currency.value||'Por indicar';
}
function formValues(form){const values=Object.fromEntries(new FormData(form));for(const [k,v] of Object.entries(values)){const type=form.elements.namedItem(k).dataset.type;values[k]=type==='multiselect'?JSON.parse(v||'null'):type==='boolean'||type==='choice'&&k==='demographicSurveyParticipation'&&['true','false'].includes(v)?(v===''?null:v==='true'):type==='number'?(v===''?null:Number(v)):v.trim()||null;if(values[k]===null&&['about','search','sources','context'].includes(form.dataset.form)&&Object.hasOwn(window.StubbsJobsSetup.context,k))values[k]='';}return values;}
function changedFormValues(form,values){
 const changed=Object.fromEntries(Object.entries(values).filter(([key,value])=>!sameFieldValue(value,form._shown[key])));
 if(form.dataset.form==='search'&&form.dataset.splitLegacy==='1'&&Object.keys(changed).length){
  for(const key of ['location','workMode'])changed[key]=values[key];
 }
 if(form.dataset.form==='search'&&form.dataset.mergedRegions==='1'&&Object.hasOwn(changed,'location'))changed.regions='';
 return changed;
}
function conflictTarget(op){if(op.kind==='ui-profile-section')return formSource(op.section);if(op.kind==='ui-automation-settings')return model.automation;if(op.kind==='ui-experience')return {};if(op.kind==='ui-search-context')return model.searchContext;return op.kind==='ui-draft'?getJob(selected).draft:op.kind==='ui-preferences'?model.preferences:op.kind==='ui-responses'?getJob(selected).answers:op.scope==='global'?model.profile:getJob(selected).answerOverrides;}

function render(preserve=false){
 if(!model)return;
 rendering=true;try{
 if(model.setupComplete===false&&!['configurar','copias'].includes(screen)){screen='configurar';selected=null;}
 syncUndo();
 document.querySelector('.site-header')?.classList?.toggle('site-header--setup',model.setupComplete===false);
 document.querySelector('header nav').hidden=model.setupComplete===false;document.querySelector('.header-search').hidden=model.setupComplete===false;document.querySelector('.header-help').hidden=false;
 if(screen!=='informe'&&selected&&getJob(selected)&&!getJob(selected).historical&&!getJob(selected).draft){main.innerHTML='<p>Cargando la solicitud… Si tarda, comprueba la conexión con Stubbs Jobs.</p>';return;}
 const anchor=preserve?[...main.querySelectorAll('[data-anchor]')].find(n=>n.getBoundingClientRect().top>=70):null;
 const anchorKey=anchor?.dataset.anchor,anchorTop=anchor?.getBoundingClientRect().top;
 const focus=preserve?captureFocus():null;
 const scroll=viewScroll(),previousScroll=scroll.scroll,tableScroll=preserve?scroll.tableScroll:null,tableTop=preserve?scroll.tableTop:null,disclosures=preserve&&['perfil','configurar','copias','preparado','detalle','solicitar','encontrar','agente'].includes(screen)?Object.fromEntries([...main.querySelectorAll('details[id]')].map(item=>[item.id,item.open])):null;
 const currentMenu=preserve?openFilterMenu||main.querySelector('.column-menu[open]'):null;
 const menuState=currentMenu?{tab:currentMenu.dataset.menuTab,key:currentMenu.dataset.menuKey,query:columnPanel(currentMenu)?.querySelector('[data-table-option-search]')?.value||'',scroll:columnPanel(currentMenu)?.querySelector('.column-menu-values')?.scrollTop||0}:null;
 closeColumnMenu();
 if(screen!=='informe'&&selected&&!getJob(selected)){screen='solicitar';selected=null;}
 if(screen==='revisar'&&!reviewSnapshot)reviewSnapshot=structuredClone(getJob(selected));
 const pages={'edicion-multiple':bulkEditorPage,'revision-multiple':bulkReviewPage,preparado:setupReady,programacion:scheduleForm,copias:backupsPage,configurar:setupForm,nueva:newOpportunityForm,agente:agentPage,solicitar:applyPage,seguir:followPage,encontrar:findPage,detalle:detail,revisar:reviewPage,perfil:profileForm,editar:editForm,actividad:history,cambio:changeForm,informe:activityReport};
 document.querySelector('.shell')?.classList?.toggle('shell--tables',['solicitar','encontrar'].includes(screen));
 main.innerHTML=(pages[screen]||applyPage)();
 syncOfferToolbar();
 // When the timeline is wider than the screen, show its newest step first.
 for(const steps of main.querySelectorAll?.('.offer-timeline-steps')||[])steps.scrollLeft=steps.scrollWidth;
 const allMarked=main.querySelector('#bulk-all');if(allMarked){const rows=[...main.querySelectorAll('[data-bulk-select]')];allMarked.indeterminate=rows.some(row=>row.checked)&&!rows.every(row=>row.checked);}
 if(tableScroll!==null&&tableScroll!==undefined){const table=main.querySelector('.workflow-table-wrap');if(table){table.scrollLeft=tableScroll;table.scrollTop=tableTop||0;}}
 if(disclosures)for(const [id,open] of Object.entries(disclosures)){const item=document.getElementById(id);if(item)item.open=open;}
 if(menuState){const menu=main.querySelector(`.column-menu[data-menu-tab="${menuState.tab}"][data-menu-key="${menuState.key}"]`);if(menu){openColumnMenu(menu);const panel=columnPanel(menu),search=panel.querySelector('[data-table-option-search]');search.value=menuState.query;filterMenuChoices(menu,menuState.query);panel.querySelector('.column-menu-values').scrollTop=menuState.scroll;requestAnimationFrame(()=>placeColumnMenu(menu));}}
 renderBackNavigation();
 const headerSearch=document.querySelector('#global-search');if(headerSearch)headerSearch.value=screen==='encontrar'?filterText:'';
 const offerScreens=['edicion-multiple','revision-multiple','solicitar','detalle','revisar','editar','cambio','nueva'];
 const destination=screen==='informe'?'agente':screen==='encontrar'?findReturn:screen==='actividad'?selected?'solicitar':'agente':screen==='copias'?'copias':screen==='agente'?'agente':screen==='perfil'&&selected||offerScreens.includes(screen)?'solicitar':'perfil';
 document.querySelectorAll('header nav button,.header-help').forEach(b=>{
  if(b.dataset.screen===destination)b.setAttribute('aria-current','page');
  else b.removeAttribute('aria-current');
 });
 if(preserve){const target=anchorKey?[...main.querySelectorAll('[data-anchor]')].find(n=>n.dataset.anchor===anchorKey):null;window.scrollTo(0,target?previousScroll+target.getBoundingClientRect().top-anchorTop:previousScroll);}
 dirty=false;
 for(const form of visibleForms()){const source=formSource(form.dataset.form),keys=[...new FormData(form).keys()];form._expected=Object.fromEntries(keys.map(k=>[k,source[k]??null]));form._shown={...form._expected};projectSurveyShown(form);if(typeof form._shown.noticeDays==='number'&&form.elements.namedItem('noticeDays')?.dataset.type==='text')form._shown.noticeDays=String(form._shown.noticeDays);form._dirty=false;if(form.dataset.form==='search'){const projected=visibleSearchLocation(source.location,source.workMode,source.regions);if(projected.split||projected.mergedRegions){form._shown.location=projected.location;form._shown.workMode=projected.workMode;if(projected.split)form.dataset.splitLegacy='1';if(projected.mergedRegions){form.dataset.mergedRegions='1';form._expected.regions=source.regions;}}}restoreForm(form);syncSourceControls(form);updateSave(form);}
 for(const form of visibleForms())if(form._dirty)settleIdleDraft(form);
 syncDirty();
 syncWorkAuthorizations();
 for(const form of visibleForms())syncProfileOptions(form);
 for(const form of visibleForms())syncSalaryCurrency(form);
 growProfileFields();
 restoreFocus(focus);
 }finally{rendering=false;}
}
function updateSave(form=main.querySelector('form[data-form]')){
 if(!form)return;
 const values=formValues(form),button=form.querySelector('[type=submit]'),changed=Object.keys(values).some(k=>!sameFieldValue(values[k],form._shown[k]));
 if(!button)return;
 const searchSettings=['search','sources'].includes(form.dataset.form),needsSave=changed||form._dirty;
 button.disabled=saving||(!['change','new'].includes(form.dataset.form)&&!needsSave);
 if(searchSettings||form.dataset.form==='profile')button.hidden=!needsSave;
}
function edit_token(){const d=getJob(selected).draft;return {message:d.message,recipient:d.recipient};}
async function criteriaGate(values){
 const Criteria=window.StubbsJobsCriteria,profile=currentSearchProfile();
 const eligibleRounds=[...model.opportunities,...UI.archive(model)].filter(job=>!profile||job.searchProfileId===profile.id||(!job.searchProfileId&&model.searchProfiles.length===1));
 const rounds=Criteria.roundOffers(eligibleRounds);
 let current,moved=null;
 const scope=model.searchProfiles?{searchProfileId}:{};
 try{current=await api('/api/criteria-preview',{values,...scope});if(rounds.length)moved=await api('/api/criteria-preview',{values,...scope,mode:'current',targets:rounds.map(id=>({id}))});}
 catch{return await confirmAction('No se pudo calcular el efecto','No se ha podido comprobar qué ofertas cambiarían. ¿Guardar igualmente tus criterios?')?{rounds:null}:null;}
 const summary=Criteria.summary(current,moved,rounds);
 if(!summary.needed)return {rounds:null,revision:current.revision};
 const dialog=document.querySelector('#criteria-effect'),box=dialog.querySelector('#criteria-effect-rounds'),keep=dialog.querySelector('#criteria-effect-keep');
 dialog.querySelector('#criteria-effect-intro').textContent=summary.intro;
 dialog.querySelector('#criteria-effect-list').innerHTML=summary.lines.map(line=>`<li>${esc(line)}</li>`).join('');
 box.hidden=!summary.rounds;box.querySelector('input').checked=false;
 if(summary.rounds){box.querySelector('.criteria-rounds-label').textContent=summary.rounds.label;box.querySelector('.criteria-rounds-note').textContent=summary.rounds.note;}
 keep.textContent=summary.keep;keep.hidden=!summary.keep;
 dialog.returnValue='cancel';dialog.showModal();
 if(!await new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='ok'),{once:true})))return null;
 return {rounds:summary.rounds&&box.querySelector('input').checked?summary.rounds.ids:null,revision:current.revision};
}
function confirmAction(title,text){const dialog=document.querySelector('#confirm');document.querySelector('#confirm-title').textContent=title;document.querySelector('#confirm-text').textContent=text;dialog.returnValue='cancel';dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='ok'),{once:true}));}
async function selectOpportunity(id,mode){
 const j=getJob(id);if(!j)return false;
 if(!['review','auto'].includes(mode))throw new Error('Selecciona cómo quieres solicitar esta oferta.');
 if(!UI.canChoose(j))throw new Error('Hay que terminar la comprobación de esta oferta antes de solicitarla.');
 if(!await action({kind:'ui-select-opportunity',opportunityId:j.id,selected:true,mode,expected:j.selection||null}))return false;
 changeToast((mode==='auto'?'Oferta seleccionada en modo automático.':'Oferta seleccionada con revisión.')+' Para iniciar la preparación, pide «Continúa con Stubbs Jobs» en el chat del agente.');
 render(true);return true;
}
async function action(operation,id=null,form=null){
 if(actionBusy||profileSaving&&!form){toast('Espera a que termine la acción anterior.');return false;}
 const journalled=id===null;
 const attempt=journalled?actionAttempts.begin(operation,()=>crypto.randomUUID()):{id,operation};
 actionBusy=true;
 mutationSerial++;
 try{const result=await api('/api/action?'+stateParams(),attempt);acceptState(result.state);stateVersion=null;if(journalled)actionAttempts.finish(operation);return true;}
 catch(error){
  if(journalled&&error.status>=400&&error.status<500)actionAttempts.finish(operation);
  if(form)form._actionFailureStatus=error.status||0;
  if(error.state){try{acceptState(error.state);}catch{connection.textContent='No se pudo leer la actualización. Tu trabajo se conserva.';}}
  conflict=error.status===409?{operation,id:attempt.id}:null;
  if(form)form._conflict=conflict;
  const box=formFeedback(form||main.querySelector('form[data-form]'),'.form-error'),association=form?.id?` form="${esc(form.id)}"`:'';
  if(box){box.innerHTML=`<div class="error">${esc(error.message)}${conflict?`<p>Revisa el registro actual antes de decidir.</p><button type="button"${association} data-current="1">Ver datos actuales</button> <button type="button"${association} data-keep="1">Usar mis valores</button>`:''}</div>`;}
  else if(error.state)render(true);
  toast(error.message);return false;
 }finally{actionBusy=false;mutationSerial++;}
}
function closeHeaderMenu(focus=false){const menu=document.querySelector('.header-menu');if(!menu?.open)return;menu.open=false;menu.querySelector('.theme-picker').open=false;if(focus)menu.querySelector('summary').focus();}
document.addEventListener('keydown',async e=>{
 if(e.defaultPrevented)return;
 const key=String(e.key||'').toLowerCase(),shortcut=(e.ctrlKey||e.metaKey)&&!e.altKey;
 if(shortcut&&key==='k'&&model?.setupComplete!==false&&document.querySelector('dialog[open]')?.open!==true){const search=document.querySelector('#global-search');if(search){e.preventDefault();search.focus();search.select?.();}return;}
 if(shortcut&&key==='s'&&document.querySelector('dialog[open]')?.open!==true){
  e.preventDefault();if(saving||actionBusy||profileSaving)return;
  if(screen==='perfil'&&!selected){await saveProfileChanges();return;}
  const form=controlForm(e.target)||visibleForms()[0];if(!form)return;
  if(!['profile','draft','change','new'].includes(form.dataset.form))return;
  try{await saveForm(form);}catch(error){toast(error.message);}return;
 }
 if(key!=='escape'||document.querySelector('dialog[open]')?.open===true)return;
 if(openFilterMenu||main.querySelector('.column-menu[open]')){closeColumnMenu(true);e.preventDefault();return;}
 if(document.querySelector('.header-menu')?.open){closeHeaderMenu(true);e.preventDefault();return;}
 if(bulkSelectionMode&&screen==='solicitar'&&!selected&&!e.target?.closest?.('input:not([type=checkbox]),textarea,select')&&!actionBusy){e.preventDefault();tableSelection.clear();bulkSelectionMode=false;render(true);main.querySelector('[data-bulk-mode]')?.focus({preventScroll:true});}
});
document.querySelector('.skip-link')?.addEventListener?.('click',e=>{e.preventDefault();main.focus();main.scrollIntoView({block:'start'});});
document.addEventListener('click',async e=>{
 const mark=e.target.closest('[data-bulk-select],[data-bulk-select-all]');
 if(mark?.dataset?.bulkSelect!==undefined||mark?.dataset?.bulkSelectAll!==undefined||e.target.closest('.offer-select-control')?.tagName==='LABEL')return;
 const filterSummary=e.target.closest('.column-menu>summary');
 if(filterSummary){e.preventDefault();const filter=filterSummary.parentElement;if(filter===openFilterMenu&&filter.open)closeColumnMenu(true);else openColumnMenu(filter,true);return;}
 if(openFilterMenu&&!openFilterMenu.contains(e.target)&&!columnPanel(openFilterMenu)?.contains(e.target))closeColumnMenu(!e.target.closest('button,a,input,textarea,select,summary,[tabindex]'));
 const sectionLink=e.target.closest('[data-profile-section]');if(sectionLink){e.preventDefault();showProfileSection(sectionLink.dataset.profileSection);return;}
  const cvRow=e.target.closest('[data-cv-open]')?.dataset?.cvOpen;if(cvRow){openCvDetail(cvRow);return;}
  if(e.target.closest('[data-cv-back]')?.dataset?.cvBack){closeCvDetail();return;}
  const nextSection=e.target.closest('[data-profile-next]')?.dataset?.profileNext;if(nextSection){showProfileSection(nextSection);return;}
  if(e.target.closest('[data-discard-profile]')?.dataset?.discardProfile){await discardProfileChanges();return;}
 const b=e.target.closest('button,[data-job-row],a[data-job]'),menu=document.querySelector('.header-menu');if(menu?.open&&(!menu.contains(e.target)||b?.closest?.('.header-menu')))closeHeaderMenu();if(!b)return;try{
 if(b.dataset.searchProfileAction){await searchProfileAction(b.dataset.searchProfileAction);return;}
 if(b.dataset.searchProfileTrash){openDeletedSearchProfiles();return;}
 if(b.dataset.searchProfileRestore){await searchProfileAction('restore',b.dataset.searchProfileRestore);return;}
 if(b.dataset.offerCriteriaChange){await changeOfferCriteria(b.dataset.offerCriteriaChange);return;}
 if(b.dataset.whereAdd){addWhereLink(b.dataset.whereAdd);return;}
 if(b.dataset.whereRemove){removeWhereLink(b.dataset.whereList,b.dataset.whereRemove);return;}
 if(b.dataset.permissionAll){const form=controlForm(b),group=permissionGroups().find(item=>item.id===b.dataset.permissionAll);if(!form||!group)return;for(const item of group.items){const field=form.elements.namedItem(item.key);if(field){field.value=b.dataset.permissionValue;form._lastEditedField=field.name;}}rememberForm(form);syncProfileOptions(form);syncProfileOverview();return;}
 if(b.dataset.permitAdd!==undefined){const widget=b.closest('[data-work-authorizations]'),input=widget.querySelector('[data-permit-other]'),name=input.value.trim();if(!name)return;if(name.length>100){input.reportValidity();return;}let option=[...widget.querySelectorAll('[data-permit-option]')].find(item=>item.dataset.permitOption.toLocaleLowerCase()===name.toLocaleLowerCase());if(!option){widget.querySelector('.permit-options').insertAdjacentHTML('beforeend',workAuthorizationOption(name,true));option=[...widget.querySelectorAll('[data-permit-option]')].find(item=>item.dataset.permitOption===name);}option.checked=true;saveWorkAuthorizationChoices(widget);input.value='';input.focus();return;}
 if(b.dataset.copyRecovery){const request=model.requests.find(r=>r.id===b.dataset.copyRecovery);if(!request)throw new Error('Actualiza el estado para consultar esta tarea.');const message=window.StubbsJobsRecovery.taskPrompt(model.workspacePath,request);try{await navigator.clipboard.writeText(message);toast('Petición copiada. Pégala en el chat del agente.');}catch{await confirmAction('Mensaje para tu agente',message);}return;}
 if(b.dataset.copyBackup!==undefined&&backupResult){const message=window.StubbsJobsRecovery.backupPrompt(model.workspacePath,backupResult.name);try{await navigator.clipboard.writeText(message);toast('Petición copiada. Pégala en el chat del agente.');}catch{await confirmAction('Mensaje para tu agente',message);}return;}
 if(b.dataset.backupDraft){const draft=backupDrafts().find(item=>item.key===b.dataset.backupDraft);if(!draft?.page)throw new Error('Actualiza Copias de seguridad para consultar el borrador pendiente.');if(draft.searchProfileId&&model.deletedSearchProfiles?.some(p=>p.id===draft.searchProfileId)){openDeletedSearchProfiles();toast('Recupera este perfil para revisar su borrador.');return;}if(draft.searchProfileId)await chooseSearchProfile(draft.searchProfileId);await setScreen(draft.page,draft.id,true,draft.section);if(draft.page==='detalle'){const note=main.querySelector('.offer-notes details');if(note){note.open=true;note.querySelector('textarea')?.focus();}}return;}
 if(b.dataset.copyBackupDraft){const draft=backupDrafts().find(item=>item.key===b.dataset.copyBackupDraft);if(!draft?.content)throw new Error('Actualiza Copias de seguridad para consultar el borrador pendiente.');const message='Borrador sin guardar de esta carpeta de Stubbs Jobs: '+(model.workspacePath||'la carpeta actual')+'.\n'+draft.content.map(([label,value])=>label+': '+value).join('\n')+'\nRevisa estos datos conmigo antes de incorporarlos a Mi perfil. No cambies permisos ni inicies búsquedas o envíos por esta copia.';try{await navigator.clipboard.writeText(message);toast('Borrador copiado. Revísalo antes de guardarlo.');}catch{await confirmAction('Datos del borrador',message);}return;}
 if(b.dataset.createBackup!==undefined){await createBackup(b);return;}
 if(b.dataset.recoverDraft!==undefined){await recoverLegacyDraft(Number(b.dataset.recoverDraft));return;}
 if(b.dataset.back){await goBack();return;}
 if(b.dataset.theme){window.StubbsJobsTheme.set(b.dataset.theme);b.closest('.theme-picker').open=false;return;}
 if(b.dataset.refreshState!==undefined){if(b.disabled)return;b.disabled=true;b.setAttribute('aria-busy','true');const was=model?.revision;try{await Promise.all([refresh(true),new Promise(resolve=>setTimeout(resolve,650))]);
  // Reading again never asks the agent to check portals; say plainly whether anything changed.
  if(!connection.textContent)toast(was!==undefined&&model?.revision===was?'Ya estaba al día: no hay cambios desde la última lectura. Para comprobar una candidatura en su portal, ábrela y pulsa Pedir comprobación.':'Estado actualizado con los últimos cambios.');}finally{b.disabled=false;b.removeAttribute('aria-busy');}return;}
 if(b.dataset.bulkMode){bulkSelectionMode=true;render(true);(main.querySelector('[data-bulk-select-all]:not(:disabled)')||main.querySelector('[data-bulk-clear]'))?.focus({preventScroll:true});return;}
 if(b.dataset.bulkClear){tableSelection.clear();bulkSelectionMode=false;render(true);main.querySelector('[data-bulk-mode]')?.focus({preventScroll:true});return;}
 if(b.dataset.bulkAction){await bulkAction(b.dataset.bulkAction,b.dataset.bulkTargets?JSON.parse(b.dataset.bulkTargets):null,Number(b.dataset.bulkTotal)||tableSelection.size);return;}
 if(b.dataset.offerMove){await moveOffer(Number(b.dataset.offerMove));return;}
 if(b.dataset.bulkApprove){
  if(!bulkReviewSnapshots.length||!bulkReviewSnapshots.every(j=>UI.reviewValid(j,getJob(j.id))))throw new Error('Revisa de nuevo las solicitudes antes de autorizar.');
  if(await action({kind:'ui-bulk-action',action:'approve',targets:bulkReviewSnapshots.map(j=>({id:j.id,fingerprint:j.fingerprint})),expectedRevision:model.revision})){
   const message=finishBulk(bulkReviewSnapshots.map(j=>j.id),bulkReviewTotal,'Permisos guardados para');bulkReviewSnapshots=[];toast(message+' Los envíos quedan pendientes del agente.');await setScreen('solicitar');
  }return;
 }
 if(b.dataset.tableSort){const state=tableState[b.dataset.tableTab];if(!state)return;state.direction=Number(b.dataset.tableDirection);state.sort=b.dataset.tableSort;closeColumnMenu();render(true);return;}
 if(b.dataset.tableSelectVisible){const state=tableState[b.dataset.tableTab],key=b.dataset.tableKey,menu=columnMenuFor(b),choices=state.choices[key]||[];const selected=new Set(Object.hasOwn(state.filters,key)?state.filters[key]:choices);columnPanel(menu).querySelectorAll('[data-table-value]').forEach(input=>{if(input.closest('.column-value').hidden)return;if(b.dataset.tableSelectVisible==='all')selected.add(input.dataset.tableValue);else selected.delete(input.dataset.tableValue);});if(selected.size===choices.length)delete state.filters[key];else state.filters[key]=choices.filter(value=>selected.has(value));historyLimit=30;render(true);return;}
 if(b.dataset.clearOrder){tableState[b.dataset.clearOrder].sort='';render(true);return;}
 if(b.dataset.clearTable){tableState[b.dataset.clearTable].filters={};historyLimit=30;render(true);return;}
 if(b.dataset.clearColumn){delete tableState[b.dataset.tableTab].filters[b.dataset.clearColumn];historyLimit=30;render(true);return;}
 if(b.dataset.userSent){await openUserSent(b.dataset.userSent);return;}
 if(b.dataset.selectionProgress){await openSelectionProgress(b.dataset.selectionProgress);return;}
 if(b.dataset.offerOutcome){
  const j=getJob(b.dataset.jobId),outcome=b.dataset.offerOutcome,category=j?UI.offerState(j).key:'';
  const allowed=j&&(outcome==='discard'?category==='por-solicitar'&&!j.selection?.selected:outcome==='reopen-followup'?j.lifecycle?.canReopen&&category!=='logradas':j.sent&&category!=='logradas'&&!j.requests.some(r=>r.type==='send'&&r.status==='running'));
  if(!allowed)throw new Error('La oferta ha cambiado. Revisa su estado actual.');
  if(await action({kind:'ui-bulk-action',action:outcome,targets:[{id:j.id}],expectedRevision:model.revision})){changeToast(({discard:'Oferta descartada.',achieve:'Solicitud lograda.', 'mark-rejected':'Rechazo registrado.',close:'Seguimiento cerrado por ti.', 'reopen-followup':'Seguimiento reabierto; permisos anteriores retirados.'})[outcome]);render(true);}
  return;
 }
 if(b.dataset.flowFilter){tableSelection.clear();flowFilters[b.dataset.filterTab]=b.dataset.flowFilter;historyLimit=30;render(true);return;}
 if(b.dataset.jobRow){if(e.target.closest('a,input,textarea,select,summary,[contenteditable]')||window.getSelection?.()?.toString())return;e.preventDefault();caseReturn=screen;await setScreen('detalle',b.dataset.jobRow);return;}
 if(b.dataset.copyPath){if(!model.workspacePath?.trim()){toast('La ubicación aún no está disponible. Actualiza el estado e inténtalo de nuevo.');return;}try{await navigator.clipboard.writeText(model.workspacePath);toast('Ubicación copiada. Abre esta carpeta en tu agente.');}catch{toast('No se pudo copiar. Selecciona la ubicación visible y cópiala manualmente.');}return;}
 if(b.dataset.copySetup!==undefined){if(!model.workspacePath?.trim()){toast('La ubicación aún no está disponible. Actualiza el estado e inténtalo de nuevo.');return;}try{await navigator.clipboard.writeText(setupAgentPrompt());setupCopiedUntil=Date.now()+2000;clearTimeout(setupCopyTimer);b.textContent='Copiado';setupCopyTimer=setTimeout(()=>{setupCopiedUntil=0;for(const button of new Set([b,...main.querySelectorAll('[data-copy-setup]')]))button.textContent=button.dataset.copyLabel||'Copiar mensaje';},2000);}catch{document.getElementById('setup-message')?.focus();toast('No se pudo copiar. Selecciona el mensaje visible y cópialo manualmente.');}return;}
 if(b.dataset.sourceScope){setSourceScope(b.dataset.sourceScope);return;}
 if(b.dataset.languageAdd!==undefined){const list=main.querySelector('[data-language-list]');list?.insertAdjacentHTML('beforeend',languageRowHtml({name:'',level:'',note:''}));list?.lastElementChild?.querySelector('input')?.focus();return;}
 if(b.dataset.languageRemove!==undefined){b.closest('[data-language-row]')?.remove();writeLanguageRows();return;}
 if(b.dataset.skillConfirm){const s=(model.skills||[]).find(x=>x.id===b.dataset.skillConfirm);if(s)await knowledgeAction({kind:'ui-skill-save',id:s.id,expected:storedSkill(s),values:skillValues(s)},`${s.name}: confirmada.`);return;}
 if(b.dataset.skillAdd!==undefined){await editSkill(null);return;}
 if(b.dataset.skillEdit){await editSkill(b.dataset.skillEdit);return;}
 if(b.dataset.skillRemove){const s=(model.skills||[]).find(x=>x.id===b.dataset.skillRemove);if(s&&await confirmAction('Quitar competencia',`Tu agente dejará de usar «${s.name}» en formularios, CV y encaje.`))await knowledgeAction({kind:'ui-skill-remove',id:s.id},'Competencia retirada.');return;}
 if(b.dataset.answerAdd!==undefined){await editAnswer(null);return;}
 if(b.dataset.answerEdit){await editAnswer(b.dataset.answerEdit);return;}
 if(b.dataset.answerConfirm){const a=(model.answerBank||[]).find(x=>x.id===b.dataset.answerConfirm);if(a)await knowledgeAction({kind:'ui-answer-save',id:a.id,expected:{value:a.value,status:a.status},question:a.question,value:a.value},'Respuesta mantenida.');return;}
 if(b.dataset.answerRemove){const a=(model.answerBank||[]).find(x=>x.id===b.dataset.answerRemove);if(a&&await confirmAction('Quitar respuesta','No se volverá a sugerir, aunque aparezca en otra solicitud.'))await knowledgeAction({kind:'ui-answer-remove',id:a.id},'Respuesta retirada.');return;}
 if(b.dataset.answersMore!==undefined){rememberAllForms();answersExpanded=true;render(true);return;}
 if(b.dataset.copyTools!==undefined){try{await navigator.clipboard.writeText(toolsAgentPrompt());toast('Mensaje copiado. Pégalo en el chat de tu agente.');}catch{toast('No se pudo copiar. Pide a tu agente que te guíe con docs/agent-tools.md.');}return;}
 if(b.dataset.setupRetry!==undefined){if(await action(setupOperation('ui-setup-retry'))){render();toast('Avance conservado. Copia el mensaje de inicio y envíalo en el nuevo chat.');}return;}
 if(b.dataset.setupFinish){if(await action(setupOperation('ui-setup-finish')))await setScreen(b.dataset.setupFinish);return;}
 if(b.dataset.saveProfile!==undefined){await saveProfileChanges();return;}
 if(b.dataset.moreActivity){activityDayLimit+=7;render(true);return;}
 if(b.dataset.searchOffers){await openSearchOffers();return;}
 if(b.dataset.openOfferState){offerProfileFilter='';workspaceSession.setItem('stubbs_jobs-offer-profile','');await openSearchOffers(b.dataset.openOfferState);return;}
 if(b.dataset.copyAgentCommand){b.disabled=true;try{await saveVisibleChangesAndCopy();}finally{b.disabled=false;}return;}
 if(b.dataset.clearPlatforms!==undefined){const form=b.closest('form[data-form="sources"]');form.elements.namedItem('platforms').value='';syncSourceControls(form);rememberForm(form);return;}
 if(b.dataset.followupCheck){
  if(await action({kind:'ui-request',type:'investigate',purpose:'followup',opportunityId:b.dataset.followupCheck})){toast('Comprobación guardada para el agente; aún no ha consultado el portal. Para iniciarla, pide «Continúa con Stubbs Jobs» en el chat del agente.');render(true);}return;
 }
 if(b.dataset.runSearch!==undefined){b.disabled=true;try{await runSearch(b.dataset.runSearch);}finally{b.disabled=false;}return;}
 if(b.dataset.entryAdd){b.disabled=true;try{await addEntry(b.dataset.entryAdd);}finally{b.disabled=false;}return;}
 if(b.dataset.entryDiscard){await discardEntries([b.dataset.entryDiscard]);return;}
 if(b.dataset.entriesDiscard){await discardEntries(visiblePendingEntries().map(e=>e.id));return;}
 if(b.dataset.moreEntries){entryLimit+=50;render(true);return;}
 if(b.dataset.investigate){
   if(await action({kind:'ui-request',type:'investigate',opportunityId:b.dataset.investigate})){toast('Comprobación guardada para el agente. Para iniciarla, pide «Continúa con Stubbs Jobs» en el chat del agente.');render(true);}
   return;
 }
 if(b.dataset.select){
   const buttons=[...main.querySelectorAll('[data-select]')].filter(button=>button.dataset.select===b.dataset.select);
   if(buttons.some(button=>button.disabled))return;
   buttons.forEach(button=>button.disabled=true);
   try{await selectOpportunity(b.dataset.select,b.dataset.selectionMode);}finally{buttons.forEach(button=>button.disabled=false);}
   return;
 }
 if(b.dataset.unselect){
   const j=getJob(b.dataset.unselect);
   if(j&&await action({kind:'ui-select-opportunity',opportunityId:j.id,selected:false,expected:j.selection})){changeToast('Oferta retirada de tu selección.');render(true);}
   return;
 }
 if(b.dataset.copyContact!==undefined){const draft=getJob(selected)?.contactDrafts?.[Number(b.dataset.copyContact)];if(draft){await navigator.clipboard.writeText(draft.message);toast('Borrador copiado. Todavía no se ha enviado.');}return;}
 if(b.dataset.moreHistory){historyLimit=['solicitar','encontrar'].includes(screen)?Math.max(100,historyLimit)+100:historyLimit+30;render(true);return;}
 if(b.dataset.report){setScreen('informe',b.dataset.report);return;}
 if(b.dataset.activity){if(!b.dataset.activity)auxReturn=screen;setScreen('actividad',b.dataset.activity);return;}
 if(b.dataset.change||b.dataset.resolve){const id=b.dataset.change||b.dataset.resolve;setScreen('cambio',id==='global'?null:id);return;}
 if(b.dataset.screen){if(b.dataset.screen==='encontrar'&&screen!=='encontrar')findReturn=screen;if(b.dataset.screen==='actividad'&&screen!=='actividad')auxReturn=screen;setScreen(b.dataset.screen);return;}if(b.dataset.job){if(b.tagName==='A')e.preventDefault();if([...flowScreens,'historial','encontrar'].includes(screen))caseReturn=screen;await setScreen('detalle',b.dataset.job,true,null,b.dataset.cvKey?b:null);return;}if(b.dataset.answers){setScreen('perfil',b.dataset.answers);return;}if(b.dataset.edit){setScreen('editar',b.dataset.edit);return;}
 if(b.dataset.review){setScreen('revisar',b.dataset.review);return;}
 b.disabled=true;
 if(b.dataset.approve){
   const j=reviewSnapshot;
   if(!j||j.id!==b.dataset.approve||!UI.reviewValid(j,getJob(j.id)))throw new Error('El envío necesita revisarse de nuevo.');
   if(await action({kind:'ui-approve',opportunityId:j.id,fingerprint:j.fingerprint})){
     toast('Permiso guardado. El envío aún no está confirmado. Para iniciarlo, pide «Continúa con Stubbs Jobs» en el chat del agente.');setScreen('detalle',j.id);
   }
 }
 if(b.dataset.revoke&&await action({kind:'ui-revoke',packageId:b.dataset.revoke})){toast('Permiso retirado. Si había un envío iniciado, su resultado debe comprobarse.');render();}
 if(b.dataset.cancel&&await action({kind:'ui-request-update',id:b.dataset.cancel,status:'cancelled',proof:'Cancelado por el usuario desde la aplicación.'})){toast('Encargo cancelado.');render();}
 if(b.dataset.retry&&await action({kind:'ui-request-update',id:b.dataset.retry,status:'queued',proof:'El usuario solicita reintentar; comprobar lo ocurrido antes de repetir una acción externa.'})){toast('Tarea guardada: el agente comprobará dónde continuar cuando pidas «Continúa con Stubbs Jobs» en su chat.');render();}
 if(b.dataset.undo&&await action({kind:'ui-undo',id:Number(b.dataset.undo)})){toast('Cambio deshecho.');render(true);}
 if(b.dataset.inherit&&await action({kind:'ui-inherit',opportunityId:selected,expected:getJob(selected).answerOverrides})){draftStorage.removeItem(draftKey());dirty=false;toast('Esta solicitud vuelve a usar tus respuestas generales.');render();}
 const formConflict=controlForm(b)?._conflict;
 if(b.dataset.current&&formConflict){const op=formConflict.operation,info=formFeedback(controlForm(b),'.form-info');if(!info)return;if(op.kind==='ui-experience'){info.textContent='Experiencia actual: '+model.experience;return;}const target=conflictTarget(op);info.textContent='Valores actuales: '+Object.keys(op.values).map(k=>(model.labels[k]||k)+': '+answerText(target[k])).join(' · ');}
 if(b.dataset.keep&&formConflict&&await confirmAction('Guardar tus valores','Sustituirá los campos indicados por tus respuestas actuales. Los demás datos se conservarán.')){
   const form=controlForm(b);if(!form)return;rememberForm(form);if(!reportFormValidity(form))return;const key=draftKey(form),values=formValues(form),op=structuredClone(formConflict.operation),target=conflictTarget(op);
   if(op.kind==='ui-experience'){op.text=values.text;op.expected=model.experience;}
   else{op.values=changedFormValues(form,values);op.expected=Object.fromEntries(Object.keys(op.values).map(k=>[k,target[k]??null]));}
   const stored=JSON.parse(draftStorage.getItem(key));stored.attempt=null;saving=true;
   try{if(await saveAttempt(form,op,stored,key)){changeToast('Cambios guardados.');render();}}finally{saving=false;}
 }
 }catch(error){toast(error.message);}finally{b.disabled=false;}});
document.addEventListener('input',e=>{if(e.target.dataset.tableOptionSearch!==undefined){filterMenuChoices(columnMenuFor(e.target),e.target.value);return;}if(e.target.id==='global-search'){const value=e.target.value;if(screen!=='encontrar'&&model?.setupComplete!==false){findReturn=screen;setScreen('encontrar').catch(error=>{connection.textContent=error.message;});}filterText=value;const results=main.querySelector('#find-results');if(results){closeColumnMenu();results.innerHTML=findResults();syncOfferToolbar();}}});
document.addEventListener('change',e=>{
 if(e.target.dataset.bulkSelect!==undefined){if(!bulkSelectionMode)return;if(e.target.checked)tableSelection.add(e.target.dataset.bulkSelect);else tableSelection.delete(e.target.dataset.bulkSelect);render(true);return;}
 if(e.target.dataset.bulkSelectAll!==undefined){if(!bulkSelectionMode)return;main.querySelectorAll('[data-bulk-select]').forEach(input=>{if(e.target.checked)tableSelection.add(input.dataset.bulkSelect);else tableSelection.delete(input.dataset.bulkSelect);});render(true);return;}
 if(e.target.dataset.tableValue===undefined)return;if(e.target.dataset.tableTab==='solicitar')tableSelection.clear();const state=tableState[e.target.dataset.tableTab],key=e.target.dataset.tableKey,choices=state.choices[key]||[];const selected=new Set(Object.hasOwn(state.filters,key)?state.filters[key]:choices);if(e.target.checked)selected.add(e.target.dataset.tableValue);else selected.delete(e.target.dataset.tableValue);if(selected.size===choices.length)delete state.filters[key];else state.filters[key]=choices.filter(value=>selected.has(value));historyLimit=30;render(true);
});
main.addEventListener('input',e=>{if(e.target.dataset?.cvFilter!==undefined){const query=e.target.value.trim().toLowerCase();for(const row of main.querySelectorAll('[data-cv-row]'))row.hidden=Boolean(query)&&!row.dataset.cvRow.includes(query);return;}
 if(e.target.dataset.answerSearch!==undefined){answerQuery=e.target.value;const list=document.getElementById('knowledge-answers-list');if(list)list.innerHTML=answersList();return;}
 if(e.target.dataset.companyToggle!==undefined){const form=main.querySelector('form[data-form="sources"]'),field=form?.elements.namedItem('disabledSources');if(field){const off=new Set(field.value.split(',').filter(Boolean));if(e.target.checked)off.delete(e.target.dataset.companyToggle);else off.add(e.target.dataset.companyToggle);field.value=[...off].sort().join(',');form._lastEditedField='disabledSources';rememberForm(form);syncWherePanel();}return;}
 if(e.target.dataset.portalToggle!==undefined){const form=main.querySelector('form[data-form="sources"]'),field=form?.elements.namedItem('excludedPortals');if(field){const excluded=excludedPortalSet({excludedPortals:field.value});if(e.target.checked)excluded.delete(e.target.dataset.portalToggle);else excluded.add(e.target.dataset.portalToggle);field.value=[...excluded].sort().join(',');form._lastEditedField='excludedPortals';rememberForm(form);syncWherePanel();}return;}
 if(e.target.closest?.('[data-language-rows]')){writeLanguageRows();return;}
 if(e.target.dataset.knowledge!==undefined)return;
 requestAnimationFrame(syncProfileOverview);
 if(e.target.name==='workMode'||e.target.name==='onsiteLocations')syncProfileWidgets();
 if(e.target.dataset.profilePermission!==undefined){const form=controlForm(e.target),field=form?.elements.namedItem(e.target.dataset.profilePermission);if(field){field.value=String(e.target.checked);form._lastEditedField=field.name;rememberForm(form);syncProfileOptions(form);}return;}
 if(e.target.dataset.autoGrow)growField(e.target);
 if(e.target.dataset.permitOther!==undefined)return;
 if(e.target.dataset.permitOption!==undefined){saveWorkAuthorizationChoices(e.target.closest('[data-work-authorizations]'));return;}
 if(e.target.dataset.tableOptionSearch!==undefined)return;
 const groupForm=e.target.form?.dataset?.bulkForm?e.target.form:e.target.closest?.('form[data-bulk-form]');
 if(groupForm?.dataset?.bulkForm&&bulkEditor){const type=bulkEditorFields().find(f=>f.name===e.target.name)?.definition.type,value=e.target.value;bulkEditor.values[e.target.name]=value===''?null:type==='boolean'?value==='true':type==='number'?Number(value):value;draftStorage.setItem(bulkEditor.draftKey,JSON.stringify({fingerprints:bulkEditor.fingerprints,values:bulkEditor.values}));dirty=true;return;}
 const form=controlForm(e.target);
 if(form){if(['currency','salaryCurrency','currentSalaryCurrency'].includes(e.target.name)){e.target.value=e.target.value.toUpperCase();syncSalaryCurrency(form);}form._lastEditedField=e.target.name;rememberForm(form);}
});
main.addEventListener('toggle',e=>{const card=e.target;if(card.tagName!=='DETAILS'||!main.contains(card))return;const key=card.dataset.activityKey,open=card.dataset.activityKey?openActivityGroups:null;if(!open)return;if(card.open)open.add(key);else open.delete(key);},true);
main.addEventListener('scroll',e=>{if(e.target.classList?.contains('workflow-table-wrap')&&openFilterMenu)requestAnimationFrame(()=>placeColumnMenu(openFilterMenu));},true);
main.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.dataset?.whereInput){e.preventDefault();addWhereLink(e.target.dataset.whereInput);return;}if(['ArrowDown','ArrowUp'].includes(e.key)&&e.target.dataset.profileSection){const links=[...main.querySelectorAll('[data-profile-section]')],next=links[links.indexOf(e.target)+(e.key==='ArrowDown'?1:-1)];if(next){e.preventDefault();showProfileSection(next.dataset.profileSection,{focus:false});next.focus();}return;}if(e.target.dataset.knowledge!==undefined&&e.key==='Enter'){e.preventDefault();if(e.target.dataset.skillYears!==undefined)focusNextSkill(e.target);return;}if(e.target.dataset.permitOther!==undefined&&e.key==='Enter'){e.preventDefault();e.target.closest('[data-work-authorizations]').querySelector('[data-permit-add]').click();return;}const row=e.target.closest('[data-job-row]');if(row&&e.target===row&&['Enter',' '].includes(e.key)){e.preventDefault();caseReturn=screen;setScreen('detalle',row.dataset.jobRow);}});
async function importCv(file){
 if(!file||saving||profileSaving)return;
 if(file.size>10000000){toast('El PDF puede ocupar hasta 10 MB.');return;}
 rememberAllForms();saving=true;syncDirty();mutationSerial++;
 try{
  const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('No se pudo leer el PDF. Vuelve a elegirlo.'));reader.readAsDataURL(file);});
  const result=await api('/api/import-cv?'+stateParams(),{name:file.name,content});
  if(!result.state||!Array.isArray(result.state.opportunities))throw new Error('No se pudo confirmar el guardado del PDF. Actualiza el estado para comprobarlo.');
  rememberAllForms();acceptState(result.state);stateVersion=null;
  saving=false;render(true);toast('CV añadido.');
 }catch(error){toast(error.message||'No se pudo guardar el PDF.');}
 finally{saving=false;mutationSerial++;syncDirty();for(const form of visibleForms())updateSave(form);}
}
main.addEventListener('change',async e=>{
 if(e.target.dataset.skillYears!==undefined){saveSkillYears(e.target);return;}
 if(e.target.dataset.knowledge!==undefined)return;
 if(e.target.dataset.profilePermission!==undefined){const form=controlForm(e.target),field=form?.elements.namedItem(e.target.dataset.profilePermission);if(field){field.value=String(e.target.checked);form._lastEditedField=field.name;rememberForm(form);syncProfileOptions(form);}return;}
 if(e.target.dataset.searchProfile!==undefined){await chooseSearchProfile(e.target.value);return;}
 if(e.target.dataset.offerProfile!==undefined){offerProfileFilter=e.target.value;workspaceSession.setItem('stubbs_jobs-offer-profile',offerProfileFilter);tableSelection.clear();historyLimit=100;render(true);return;}
 if(e.target.dataset.tableValue!==undefined)return;
 if(e.target.id==='cv-upload'){await importCv(e.target.files[0]);return;}const form=controlForm(e.target);if(form){form._lastEditedField=e.target.name;rememberForm(form);syncProfileOptions(form);}});
async function saveAttempt(form,operation,stored,key){
 const attempt=stored.attempt||{id:crypto.randomUUID(),operation:structuredClone(operation),values:stored.values};
 draftStorage.setItem(key,JSON.stringify({...stored,attempt}));
 form._actionFailureStatus=0;
 const success=await action(attempt.operation,attempt.id,form);
 if(!success){
  if(form._actionFailureStatus>=400&&form._actionFailureStatus<500){const latest=JSON.parse(draftStorage.getItem(key));latest.attempt=null;draftStorage.setItem(key,JSON.stringify(latest));}
  return false;
 }
 const latest=JSON.parse(draftStorage.getItem(key)),remaining=window.StubbsJobsDrafts.settle(latest,attempt);
 if(remaining){
  draftStorage.setItem(key,JSON.stringify(remaining));form._expected=remaining.expected;form._shown=remaining.shown;
  form._dirty=true;syncDirty();toast('Guardado anterior confirmado. Pulsa Guardar para aplicar los cambios nuevos.');updateSave(form);return false;
 }
 draftStorage.removeItem(key);form._dirty=false;form._conflict=null;syncDirty();conflict=null;return true;
}
async function saveForm(form,{deferRender=false}={}){
 if(saving||actionBusy)return false;rememberForm(form);form._cancelled=false;
 if(!reportFormValidity(form))return false;
 const key=draftKey(form),stored=JSON.parse(draftStorage.getItem(key)||'{}'),values=formValues(form),kind=form.dataset.form;
 // Company switches are common to all search profiles and have their own writer.
 if(kind==='sources'&&Object.hasOwn(values,'disabledSources')){
  const off=new Set(String(values.disabledSources||'').split(',').filter(Boolean));delete values.disabledSources;
  for(const source of model.sourceStats||[])if(off.has(source.id)===source.enabled&&!await action({kind:'ui-source-toggle',sourceId:source.id,enabled:!off.has(source.id),expected:source.enabled},null,form))return false;
 }
 if(['search','sources'].includes(kind)&&currentSearchProfile()?.archivedAt){toast('Recupera este perfil antes de guardar sus criterios.');return false;}
 let op;
 if(['about','search','sources'].includes(kind)){for(const k of Object.keys(values))if(values[k]===null&&Object.hasOwn(window.StubbsJobsSetup.context,k))values[k]='';op={kind:'ui-profile-section',section:kind,values,expected:form._expected};}
 else if(kind==='context'){for(const k of Object.keys(values))if(values[k]===null)values[k]='';op={kind:'ui-search-context',values,expected:form._expected};}
 else if(kind==='new')op={kind:'ui-add-opportunity',values};
 else if(kind==='change')op={kind:'ui-change',opportunityId:form.dataset.opportunityId||selected,message:values.message};
 else if(kind==='offer-note'){values['Notas de seguimiento']=values['Notas de seguimiento']||'';op={kind:'ui-offer-note',opportunityId:selected,values,expected:form._expected};}
 else if(kind==='experience')op={kind:'ui-experience',text:values.text,expected:form._expected.text};
 else if(kind==='automation'||kind==='schedule')op={kind:'ui-automation-settings',values,expected:form._expected};
 else op={kind:kind==='preferences'?'ui-preferences':kind==='draft'?'ui-draft':selected?'ui-responses':'ui-profile',scope:'global',opportunityId:selected,values,expected:form._expected};
 if(['search','sources'].includes(kind)&&form.dataset.searchProfileId)op.searchProfileId=form.dataset.searchProfileId;
 if(kind==='new'&&currentSearchProfile())op.searchProfileId=searchProfileId;
 if(op.values&&kind!=='new'){op.values=unsavedValues(form,values,stored);op.expected=Object.fromEntries(Object.keys(op.values).map(k=>[k,form._expected[k]??null]));if(!Object.keys(op.values).length&&!stored.attempt){draftStorage.removeItem(key);form._dirty=false;syncDirty();const info=form.querySelector('.form-info');if(info)info.textContent='';updateSave(form);if(!deferRender)toast('Sin cambios.');return true;}}
 const button=form.querySelector('[type=submit]');if(button)button.disabled=true;saving=true;
 try{
  // Criteria changes re-evaluate offers at once; say what changes before saving.
  let gate=null;
  if(kind==='search'&&op.values&&!stored.attempt){gate=await criteriaGate(op.values);if(!gate){form._cancelled=true;return false;}}
  if(Number.isInteger(gate?.revision))op.expectedRevision=gate.revision;
  const complete=await saveAttempt(form,op,stored,key);saving=false;
  if(complete&&gate?.rounds?.length&&!await action({kind:'ui-criteria-scope',mode:'current',targets:gate.rounds.map(id=>({id})),expectedRevision:model.revision,...(op.searchProfileId?{searchProfileId:op.searchProfileId}:{}),
    proof:'La persona aplica los criterios guardados en Lo que busco también a ofertas de búsquedas anteriores.'},null,form))
   toast('Tus criterios se guardaron, pero no se aplicaron a las ofertas de búsquedas anteriores.');
   if(complete&&deferRender){form._shown={...form._shown,...values};form._expected={...form._expected,...(op.values||(kind==='experience'?{text:op.text}:{}))};syncDirty();}
   if(complete&&!deferRender){changeToast(kind==='change'?'Petición guardada para el agente.':'Cambios guardados.');if(!selected&&(screen==='perfil'&&['about','experience','search','sources'].includes(kind))){render(true);}else{const destination=kind==='new'||kind==='automation'?'solicitar':['search','sources'].includes(kind)?'perfil':selected?'detalle':'perfil';await setScreen(destination,selected&&destination==='detalle'?selected:null);}}
   return complete;
 }catch(error){toast('Tu borrador se conserva. '+error.message);return false;}
 finally{saving=false;if(button)button.disabled=false;}
}
async function saveProfileChanges(){
 if(screen!=='perfil'||selected||saving||actionBusy||profileSaving)return false;
 rememberAllForms();
 const forms=visibleForms().filter(form=>form._dirty);
 if(!forms.length){toast('Sin cambios pendientes.');return true;}
 for(const form of forms)if(!reportFormValidity(form))return false;
 const focusSave=document.activeElement?.dataset?.saveProfile!==undefined;
 let saved=0,failed=null;
 profileSaveProblem='';profileSaving=true;syncDirty();
 try{
  for(const form of forms){
   if(!await saveForm(form,{deferRender:true})){failed=form;break;}
   saved++;
  }
 }finally{profileSaving=false;syncDirty();syncUndo();}
 if(failed?._cancelled){failed._cancelled=false;toast((saved?`Se ${saved===1?'guardó una sección':'guardaron '+saved+' secciones'}. `:'')+'No se han guardado tus criterios. Los cambios pendientes se conservan.');return false;}
 if(failed){
  const label=profileChangedSections([failed]).join(', ')||'el perfil';
  const key=Object.keys(formValues(failed)).find(key=>!sameFieldValue(formValues(failed)[key],failed._shown[key]));
  const card=key?document.getElementById(profileFieldSection(failed.dataset.form,key)):null;
  profileSaveProblem=`No se ha guardado ${label}. Revisa el aviso.`;syncDirty();
  if(card?.id)showProfileSection(card.id,{focus:false});else failed.scrollIntoView?.({block:'center',behavior:'smooth'});
  formFeedback(failed,'.form-error')?.scrollIntoView?.({block:'center',behavior:'instant'});
  toast((saved?`Se ${saved===1?'guardó una sección':'guardaron '+saved+' secciones'}. `:'')+`Revisa «${label}». Los cambios pendientes se conservan.`,saved?lastUserUndo()?.id:null);
  return false;
 }
 if(dirty){toast('Hay ediciones nuevas pendientes de guardar.',lastUserUndo()?.id);return false;}
 render(true);if(focusSave)main.focus?.({preventScroll:true});changeToast('Cambios guardados.');return true;
}
async function saveVisibleChangesAndCopy(){
 const work=window.StubbsJobsActivity.work(model);
 if(!work.queued.length&&(!String(model.searchContext?.targetRoles||'').trim()||!String(model.preferences?.location||model.searchContext?.regions||'').trim())){
  toast('Completa los puestos y la zona de búsqueda en Mi perfil.');await setScreen('perfil',null,true,'search-settings-criteria');return;
 }
 if(model.execution?.status==='starting'||UI.progress(model).busy){toast('El agente ya tiene trabajo en curso.');return;}
 const command=work.queued.length?'Continúa con Stubbs Jobs':'Busca ofertas nuevas';
 try{await navigator.clipboard.writeText(command);toast('Mensaje copiado. Pégalo en el chat del agente.');}
 catch{toast('No se pudo copiar. Escribe «'+command+'» en el chat del agente.');}
}
main.addEventListener('submit',async e=>{
 const group=e.target.closest('form[data-bulk-form]');if(group?.dataset?.bulkForm){e.preventDefault();try{await saveBulkEditor(group);}catch(error){toast(error.message);}return;}
 const form=e.target.closest('form[data-form]');if(!form)return;e.preventDefault();if(screen==='perfil'&&!selected)await saveProfileChanges();else await saveForm(form);
});
window.addEventListener('beforeunload',event=>{if(dirty)rememberAllForms();viewMemory[screen+'/'+(selected||'')]={filterText,...viewScroll(),focus:captureFocus(),limit:historyLimit,activityDays:activityDayLimit};workspaceSession.setItem('stubbs_jobs-views',JSON.stringify(viewMemory));if(saving||profileSaving||actionBusy||dirty&&(storageProblem||screen==='perfil'&&!selected)){event.preventDefault();event.returnValue='';}});
window.addEventListener('scroll',()=>{if(openFilterMenu)requestAnimationFrame(()=>placeColumnMenu(openFilterMenu));},{passive:true});
window.addEventListener('resize',()=>{closeColumnMenu();syncOfferToolbar();});
async function start(){const key=new URLSearchParams(location.hash.slice(1)).get('key');if(key){await api('/api/session',{key});window.history.replaceState(null,'',location.pathname);}else if(location.hash.slice(1)!=='perfil'&&flowScreens.includes(location.hash.slice(1)))window.history.replaceState(null,'',location.pathname);await refresh(true);await route();clearTimeout(pollTimer);pollTimer=setTimeout(poll,6000);}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh(true);});
window.addEventListener('hashchange',()=>{if(location.hash.includes('key='))start().catch(e=>{connection.textContent=e.message;});else route().catch(e=>{connection.textContent=e.message;});});
start().catch(error=>{connection.textContent=error.message;main.innerHTML='<div class="empty">Vuelve a abrir Stubbs Jobs desde el acceso de su carpeta.</div>';});
})();
