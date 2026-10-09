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
let setupCopiedUntil=0,setupCopyTimer=null;
const flowScreens=['perfil','solicitar','agente'];
const flowFilters={solicitar:'todas'};
const tableState={solicitar:{sort:'',direction:1,filters:{},choices:{}},encontrar:{sort:'',direction:1,filters:{},choices:{}}};
const tableSelection=new Set();let bulkSelectionMode=false,bulkReviewSnapshots=[],bulkReviewTotal=0,bulkEditor=null,offerTour=null;
const profileSections=[['profile-about','Sobre mi'],['profile-work','Lo que busco'],['profile-cv','Currículums']];
function canonicalProfileSection(id){return ({'profile-experience':'profile-about','search-settings-criteria':'profile-work','search-settings-sources':'profile-work','profile-previous':'profile-work','perfil-previous':'profile-work'})[id]||id;}
let profileSection='profile-about',openFilterMenu=null;
let searchProfileId=null,offerProfileFilter='';
const openCvCards=new Set(),anonymousCvKeys=new WeakMap();let anonymousCvSequence=0;
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
const date=v=>{if(!v)return 'Sin comprobar';const at=window.StubbsJobsFormatting.tableTimestamp(v);return at===null?'Fecha no válida':new Intl.DateTimeFormat('es-ES',{dateStyle:'medium',timeStyle:String(v).includes('T')?'short':undefined,timeZone:model?.personalized?undefined:'Europe/Madrid'}).format(at);};
const isHttpUrl=value=>/^https?:\/\//i.test(value||'');
const url=value=>isHttpUrl(value)?esc(value):'#';
const getJob=id=>model?.opportunities.find(x=>x.id===id)||(model?UI.archive(model).find(x=>x.id===id):null);
const active=UI.active;
const labels={queued:'Pendiente del agente',running:'En curso',blocked:'Necesita intervención',interrupted:'Interrumpido',done:'Terminado',cancelled:'Cancelado'};
const requestNames={change:'Aplicar tus cambios',review:'Comprobar solicitud',investigate:'Comprobar oferta',send:'Enviar solicitud',mail:'Revisión de correo anterior',discovery:'Buscar ofertas'};
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
 if(kind==='about'||kind==='experience'||key==='languages')return 'profile-about';
 return 'profile-work';
}
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
 const pending=main.querySelector('[data-profile-pending]');if(pending){const changed=profileChangedSections();pending.textContent=changed.length?'Cambios en '+changed.join(', '):profileSaving?'Guardando tus cambios…':'Cambios sin guardar';}
 main.querySelector('.profile-layout')?.classList?.toggle('profile-layout--pending',Boolean(bar&&!bar.hidden));
 const upload=main.querySelector('#cv-upload');if(upload)upload.disabled=profileSaving||saving;
 for(const copy of document.querySelectorAll('[data-copy-agent-command]'))copy.textContent=copy.dataset.copyLabel||'Copiar petición';
}
function rememberForm(form=main.querySelector('form[data-form]')){if(!form)return;const key=draftKey(form),values=Object.fromEntries(new FormData(form));try{const previous=JSON.parse(draftStorage.getItem(key)||'null');const current=formValues(form);const changed=Object.keys(current).some(k=>!sameFieldValue(current[k],form._shown[k]));if(!changed&&!previous?.attempt){draftStorage.removeItem(key);form._dirty=false;const info=formFeedback(form,'.form-info');if(info)info.textContent='';}else{draftStorage.setItem(key,JSON.stringify({values,expected:form._expected,shown:form._shown,attempt:previous?.attempt||null}));form._dirty=true;const info=formFeedback(form,'.form-info');if(info)info.textContent=previous?.attempt?'Guardado pendiente de confirmar. Vuelve a guardar para comprobarlo.':screen==='perfil'&&!selected?'':'Cambios sin guardar.';}}catch{form._dirty=true;}syncDirty();updateSave(form);}
function rememberAllForms(){for(const form of visibleForms())rememberForm(form);}
function restoreForm(form=main.querySelector('form[data-form]')){
 if(!form)return;
 try{
  const stored=JSON.parse(draftStorage.getItem(draftKey(form))||'null');if(!stored)return;
  for(const [key,value] of Object.entries(stored.values)){const field=form.elements.namedItem(key);if(field)field.value=value;}
  form._expected={...form._expected,...stored.expected};form._shown={...form._shown,...stored.shown};
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
async function refresh(force=false,{deferRender=false}={}){
 if(profileSaving||actionBusy||(document.hidden||saving)&&!force)return;
 if(refreshInFlight){await refreshInFlight;if(force)return refresh(true,{deferRender});return;}
 const view=screen+'/'+(selected||'')+'/'+historyLimit,readSerial=mutationSerial;
 const params=new URLSearchParams({brief:'1'});
 if(selected&&screen!=='informe')params.set('case',selected);
 if(screen==='revision-multiple')bulkReviewSnapshots.forEach(j=>params.append('case',j.id));
 if(screen==='edicion-multiple')bulkEditor?.jobs.forEach(j=>params.append('case',j.id));
 if(['agente','actividad','informe'].includes(screen)||selected)params.set('history','1');
 if(screen==='informe'&&selected?.startsWith('event:')){const item=activityRecord(selected.slice(6));if(item?.opportunityId)params.set('case',item.opportunityId);}
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
  if(!deferRender)render(true);
 }catch(error){connection.textContent=error.message;if(!model)main.innerHTML='<div class="empty-state"><h1>No se pudo cargar Stubbs Jobs</h1><p>Abre la app desde el acceso de su carpeta y vuelve a intentarlo.</p><button data-refresh-state="1">Reintentar</button></div>';}})();
 try{await refreshInFlight;}finally{refreshInFlight=null;}
}
async function poll(){await refresh();pollTimer=setTimeout(poll,document.hidden?30000:6000);}
async function setScreen(next,id=null,push=true,targetSection=null,sourceElement=null,move=null){
  if(saving||actionBusy||profileSaving){toast("Espera a que termine de guardar.");return;}
  rememberCvCards();
  const serial=++navigationSerial;
  const offerOrigin=sourceElement||(next==='detalle'&&id&&['solicitar','encontrar'].includes(screen)?[...main.querySelectorAll('[data-job]')].find(button=>button.dataset.job===id):null);
  if(navigationReady)viewMemory[screen+'/'+(selected||'')]={filterText,...viewScroll(),focus:captureFocus(offerOrigin)||captureFocus()||viewMemory[screen+'/'+(selected||'')]?.focus,limit:historyLimit,activityDays:activityDayLimit};
  closeColumnMenu();
  workspaceSession.setItem('stubbs_jobs-views',JSON.stringify(viewMemory));
  if(dirty){rememberAllForms();toast('Borrador conservado.');}
  const profileRoutes=Object.fromEntries([...profileSections.map(([id])=>id),'profile-experience','profile-cv','search-settings-criteria','search-settings-sources','profile-previous','perfil-previous'].map(id=>[id,'perfil']));
  const aliases={hoy:'solicitar',inicio:'solicitar',ofertas:'solicitar',resumen:'agente',buscar:'perfil',candidaturas:'solicitar',elegir:'solicitar',seguir:'solicitar',seguimiento:'solicitar',historial:'solicitar',ajustes:'perfil',salud:'comprobaciones',tabla:'solicitar',cv:'perfil',asistente:'copias',ayuda:'copias',datos:'perfil',busqueda:'perfil',fuentes:'perfil',experiencia:'perfil',contexto:'perfil',preferencias:'perfil',antecedentes:'perfil',autonomia:'solicitar','opciones-solicitud':'solicitar',...profileRoutes};
  const original=next,sectionTargets={buscar:'profile-work',datos:'profile-about',busqueda:'profile-work',fuentes:'profile-work',experiencia:'profile-about',cv:'profile-cv',contexto:'profile-work',preferencias:'profile-work',antecedentes:'profile-previous'};
  const requestedSection=targetSection||sectionTargets[original]||(profileRoutes[original]?original:null),previousTarget=['profile-previous','perfil-previous','search-field-previousApplications'].includes(requestedSection);
  targetSection=canonicalProfileSection(previousTarget?'profile-work':requestedSection);next=aliases[next]||next;
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
  await setScreen(page||(model?.setupComplete===false?'configurar':model?.onboarding?.needsWelcome?'preparado':'solicitar'),decoded,false);
}
function historyTitle(value){return window.StubbsJobsActivity.title(typeof value==='object'?value:{title:value});}
function timeline(items,limit=30,withCompany=true,relative=false){
 if(!items.length)return '<p class="muted">Todavía no hay cambios registrados.</p>';
 return '<ol class="timeline">'+items.slice().reverse().slice(0,limit).map(item=>activityItem(item,withCompany,relative)).join('')+'</ol>';
}
function primaryAction(j,step=UI.step(j),inDetail=false){
  if(inDetail&&step.action==='open')return '';
  if(!step.cta)return '';
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

Sigue INICIO.md y comprueba el acceso a la carpeta y sus herramientas. Retoma el avance guardado y hazme una entrevista breve para confirmar primero los datos esenciales de la búsqueda: ayúdame con los CV que adjunte, pregunta solo por lo necesario ahora y conserva los demás datos como pendientes y confirma qué quiero dejar en blanco.

Muéstrame el resumen antes de guardar solo lo que confirme. Si ya tengo perfil, no repitas la entrevista. No busques ofertas ni envíes solicitudes todavía.`;
}
function setupOperation(kind){const state=model.onboarding;return {kind,workspaceId:state.workspaceId,token:state.token,expected:state.revision};}
function setupForm(){
 const state=model.onboarding||{status:'waiting'},status=state.status;
 const path=typeof model.workspacePath==='string'?model.workspacePath:'',available=Boolean(path.trim());
 const progress={access_checked:'Carpeta comprobada. Continúa en el chat.',preparing:state.coverage?.complete?'Continúa en el chat para revisar el resumen.':'Responde a lo pendiente en el chat; puedes dejar datos en blanco.',awaiting_confirmation:'Revisa el resumen en el chat y confírmalo o pide cambios.',blocked:state.summary||'Consulta el chat para resolver el paso pendiente.'};
 const coverage=state.coverage&&status!=='waiting'?`${state.coverage.provided+state.coverage.blank} de ${state.coverage.total} aspectos del perfil tratados.${state.coverage.blank?` ${state.coverage.blank} dejado${state.coverage.blank===1?'':'s'} en blanco por tu decisión.`:''}`:'';
 const current=progress[status]?`<p class="setup-coverage" role="status">${esc(progress[status])}${coverage?` <span>${esc(coverage)}</span>`:''}</p>`:'';
 return `<div class="welcome-view setup-view"><h1>Empieza con Stubbs Jobs</h1><p class="lead">Encuentra ofertas a tu medida y prepara tus solicitudes con tu agente de IA. Tú decides dónde solicitar.</p>${current}<section class="setup-instructions"><h2><span class="setup-step" aria-hidden="true">1</span> Añade esta carpeta como proyecto en tu agente de IA</h2><div class="copy-line"><code>${esc(available?path:'Cargando ubicación…')}</code><button data-copy-path="1"${available?'':' disabled'}>Copiar ubicación</button></div><h2><span class="setup-step" aria-hidden="true">2</span> Pega este mensaje en un chat dentro de tu nuevo proyecto para empezar el on-boarding</h2><pre id="setup-message" class="setup-message" tabindex="0" aria-label="Mensaje para tu agente">${esc(setupAgentPrompt())}</pre>${setupCopyButton('Copiar mensaje',available)}</section>${state.executionId?`<section class="setup-resume" aria-labelledby="setup-resume-title"><h2 id="setup-resume-title">Si cambias de chat, retoma aquí antes de continuar</h2><p>Conserva tus respuestas y CV y retira al chat anterior el acceso a esta preparación.</p><button data-setup-retry="1">Retomar en otro chat</button></section>`:''}</div>`;
}
function setupReady(){
 return `<div class="welcome-view setup-view"><h1>Tu perfil está preparado</h1><p class="lead">Para encontrar tus primeras ofertas, pide «Busca ofertas nuevas» en el chat de tu agente.</p><div class="setup-actions"><button class="primary" data-setup-finish="solicitar">Ir a Ofertas</button><button data-setup-finish="perfil">Revisar mi perfil</button></div>${!model.searchContext.targetRoles||!model.preferences.location?'<p class="helper">Antes de buscar, concreta los puestos y la zona con tu agente o en Mi perfil.</p>':''}</div>`;
}
function sectionDefinitions(section){
 const context=window.StubbsJobsSetup.context,contact=window.StubbsJobsSetup.contact;
 const preferences={contract:{label:'Contrato',type:'text',placeholder:'Ej.: indefinido'},location:{label:'Zona de búsqueda',type:'text',placeholder:'Países o zonas donde quieres trabajar'},maxTrips:{label:'Viajes al mes (máximo)',type:'number'},minimumFixed:{label:'Salario fijo mínimo bruto anual',type:'number'},keywords:{label:'Palabras clave',type:'text',placeholder:'Términos relevantes para tu sector'},noticeDays:{label:'Preaviso',type:'text',placeholder:'Ej.: 15 días laborables, 3 semanas o inmediato'},searchPriorities:{...context.searchPriorities,label:'Horario que prefiero',placeholder:'Ej.: mañana, flexible o sin turnos de noche'}};
 const keys=section==='about'?['name','email','phone','currentCity','currentCountry','postalCode','address','linkedinUrl','websiteUrl','gender','demographicSurveyParticipation','workAuthorizations','noticeDays',...Object.keys(model.fieldDefinitions||{}).filter(k=>k.startsWith('custom_')&&model.fieldDefinitions[k].scope==='global')]:section==='search'?['targetRoles','keywords','location','workMode','onsiteLocations','contract','minimumFixed','salaryExpectationFixed','salaryCurrency','maxTrips','searchPriorities','searchNotes','languages','previousApplications']:section==='sources'?['sourceUrls','platforms']:[];
 const personal={currentCity:{label:'Ciudad actual',type:'text'},workPermitWithoutSponsorship:{label:'Permiso de trabajo sin patrocinio',type:'boolean'},salaryExpectationFixed:{label:'Salario fijo esperado al año',type:'number'},noticeDays:{label:'Días de preaviso',type:'number'}};
 const defs={...context,...personal,...contact,...window.StubbsJobsSetup.demographics,...model.fieldDefinitions,...preferences,name:{...context.name,label:'Nombre y apellidos',autocomplete:'name'},searchPriorities:{...preferences.searchPriorities,type:'longtext',rows:1,autoGrow:true,maxlength:3000},workAuthorizations:{label:'Permiso de trabajo sin patrocinio en',type:'multiselect'},languages:{...context.languages,type:'longtext',rows:1,autoGrow:true,maxlength:3000}};return Object.fromEntries(keys.map(k=>[k,defs[k]||{label:k,type:'text'}]));
}
function numberAttributes(key){
 if(key.startsWith('custom_'))return 'step="any" min="-1000000" max="1000000"';
 const limits={noticeDays:[0,365],maxTrips:[0,31],minimumFixed:[1,1000000000],salaryExpectationFixed:[1,1000000000]}[key];
 return limits?`step="1" min="${limits[0]}" max="${limits[1]}"`:'step="1" min="0"';
}
function searchCriteriaFields(values,keys,association=null,{flat=false}={}){
 const defs=sectionDefinitions('search');
 const field=key=>`<div${['targetRoles','keywords','searchPriorities','previousApplications'].includes(key)?' class="profile-field-wide"':''} id="search-field-${key}">${['minimumFixed','salaryExpectationFixed'].includes(key)?`<div class="field"><label for="profile-${key}">${key==='minimumFixed'?'Salario fijo mínimo bruto anual':'Salario fijo bruto anual para formularios (opcional)'}</label><span class="amount-input"><input id="profile-${key}" name="${key}" data-type="number" type="number" ${numberAttributes(key)} value="${esc(values[key])}">${key==='minimumFixed'?`<input name="currency" data-type="text" class="currency-input" type="text" value="${esc(values.currency??'')}" maxlength="3" pattern="[A-Z]{3}" placeholder="EUR" aria-label="Moneda del salario, código de tres letras (por ejemplo EUR o USD)"${association?` form="${association}"`:''}>`:`<span data-salary-currency="1">${esc(values.currency??'')||'Por indicar'}</span>`}</span></div>`:fieldHtml(key,{...defs[key],...(['targetRoles','keywords'].includes(key)?{type:'longtext',rows:1,autoGrow:true,maxlength:3000}:key==='previousApplications'?{label:'Empresas a evitar',rows:1,autoGrow:true,maxlength:10000,placeholder:'Empresas a las que no quiero presentarme',controlId:'profile-previousApplications'}:{}),form:association},values[key])}${key==='previousApplications'?formErrors('search'):''}</div>`;
 const fields=keys.map(key=>{
  let html=field(key);
  if(key==='salaryExpectationFixed'&&currentSearchProfile())html=html.replace(/(<span data-salary-currency="1">)[^<]*(<\/span>)/,'$1'+esc(values.salaryCurrency||'Por indicar')+'$2');
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
function searchOptionsControls(sources){
 const context=model.searchContext||{},platforms=(context.platforms||'').split(',').filter(Boolean);
 const priorities=platforms.length?`<div class="source-priorities"><p>Fuentes priorizadas: ${esc(platforms.map(id=>platformNames[id]||id).join(', '))}</p><button type="button" class="link-button" data-clear-platforms="1">Quitar prioridades</button></div>`:'';
 return `<div class="source-controls"><input type="hidden" name="platforms" value="${esc(context.platforms||'')}">${priorities}
  <div class="source-webs"><label class="field profile-field-wide"><span id="profile-sourceUrls-label">Especificar webs de búsqueda (opcional)</span><textarea name="sourceUrls" id="profile-sourceUrls" data-auto-grow="1" aria-labelledby="profile-sourceUrls-label" aria-describedby="profile-sourceUrls-help" rows="1" maxlength="3000" placeholder="Una dirección por línea">${esc(sources.sourceUrls)}</textarea><small class="helper" id="profile-sourceUrls-help">Si indicas webs, buscaré solo en ellas. Si lo dejas vacío, elegiré las fuentes.</small></label></div>
 </div>`;
}
function portalAccessDetails(context=model){
 const platforms=(context.searchContext?.platforms||'').split(',').filter(Boolean),access=context.portalAccess||{};
 const visible=[...new Set([...platforms,...Object.keys(access)])].filter(id=>id!=='glassdoor'&&!mailboxPortal(id));
 if(!visible.length)return '';
 const rows=visible.map(id=>{const record=access[id],state=record?.status==='ready'?'Acceso comprobado':record?.status==='login_required'?'Inicia sesión':record?.status==='blocked'?'Bloqueado':'Sin comprobar';return `<div class="portal-access-row"><strong>${esc(platformNames[id]||id)}</strong><span>${esc(state)}${record?` · ${esc(record.browser)} · ${date(record.checkedAt)}`:''}</span>${record?.proof?`<p>${esc(record.proof)}</p>`:''}</div>`;}).join('');
 return `<section class="section"><h2>Acceso a portales</h2><div class="portal-access-list">${rows}</div></section>`;
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
 if(request.status==='queued')return activityRow({kind:'pending',title:[request.purpose==='followup'?'Comprobar tu candidatura':window.StubbsJobsWorkflow.names[request.type]||'Trabajo guardado',job?.company].filter(Boolean).join(' · '),text:['Pendiente de iniciar',job?.title].filter(Boolean).join(' · '),anchor:reportKey(request),target:job?`data-job="${esc(job.id)}"`:search?'data-screen="solicitar"':'data-screen="perfil"',action:job?'Ver oferta':search?'Ver ofertas':'Ver perfil'});
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
 return activityRow({kind:request.type,title,text,at:window.StubbsJobsWorkflow.taskAt(request),anchor:reportKey(request),target,action});
}
function activityRole(job){return String(job?.title||'').replace(/\s*[|·]\s*100%\s+Remoto\b.*$/i,'').trim();}
function activityRow({kind,title,text,anchor,target,action}){
 const mark=kind==='send'?'check':kind==='discovery'?'search':kind==='interview'?'clock':'arrow-right';
 return `<li class="activity-card" data-kind="${esc(kind)}" data-anchor="activity-${esc(anchor)}"><span class="activity-icon" aria-hidden="true">${icon(mark)}</span><div class="activity-card-body"><strong>${esc(title)}</strong>${text?`<p>${esc(conciseText(text,120))}</p>`:''}</div><div class="activity-card-actions"><button class="link-button" ${target}>${esc(action)} ${icon('arrow-right')}</button></div></li>`;
}
function activityEvent(item){
 const job=item.opportunityId?getJob(item.opportunityId):null;
 const sent=/^(Envío confirmado|Solicitud enviada)/i.test(item.title),ready=/^(Paquete|Solicitud)/i.test(item.title),interview=/^Entrevista/i.test(item.title);
 const title=(sent?'Solicitud enviada':historyTitle(item))+(job?' · '+job.company:'');
 const target=job?`data-job="${esc(job.id)}"`:'data-screen="solicitar"';
 return activityRow({kind:sent?'send':interview?'interview':'review',title,text:activityRole(job),anchor:'event-'+item.id,target,action:sent||ready?'Ver solicitud':'Ver oferta'});
}
function recentActivity(){
 const Activity=window.StubbsJobsActivity,timeZone=model?.personalized?Intl.DateTimeFormat().resolvedOptions().timeZone:'Europe/Madrid';
 const days=Activity.days(Activity.entries(model),timeZone);
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
 return '<ol class="activity-days">'+shown.map(day=>{const title=heading(day);return `<li class="activity-day" data-anchor="day-${esc(day.key)}"><h2 class="activity-day-label"><time datetime="${esc(day.key==='unknown'?'':day.key)}">${esc(title.main)}</time>${title.note?`<span class="activity-weekday">${esc(title.note)}</span>`:''}</h2><ol class="activity-cards">${day.items.map(item=>item.request?activityCard(item.request):activityEvent(item.event)).join('')}</ol></li>`;}).join('')+'</ol>'+(days.length>shown.length?'<button class="activity-older" data-more-activity="1">Ver anteriores</button>':'');
}
function activityWork(){return window.StubbsJobsExplanations.work(model,{getJob,esc,date,conciseText,copyRequestButton});}
function agentPage(){
 const first=UI.recommendation(model),recommendation=first?`<div class="offer-recommendation"><div><span class="eyebrow">Para mirar primero</span><strong>${esc(first.company)}</strong>${first.title?`<span class="offer-recommendation-role"> · ${esc(first.title)}</span>`:''}<p>${esc(conciseText(UI.nextCheck(first),160))}</p></div><button class="link-button" data-job="${esc(first.id)}">Ver oferta ${icon('arrow-right')}</button></div>`:'';
 return flowShell('agente',`<div class="agent-view"><h1 id="agent-activity-title">Resumen</h1>${activityWork()}${recommendation}${recentActivity()}</div>`);
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
function copyRequestButton(label){
 const work=window.StubbsJobsActivity.work(model);
 if(work.busy)return '';
 const command=work.queued.length?'Continúa con Stubbs Jobs':'Busca ofertas nuevas';
 if(work.queued.length&&label==='Copiar petición de búsqueda')label='Copiar petición pendiente';
 const hint=work.queued.length?'Copia la petición para continuar el trabajo guardado y los siguientes pasos permitidos de esas mismas solicitudes en el chat de tu agente':'Copia la petición para pegarla en el chat de tu agente';
 return `<button type="button" class="copy-request" data-copy-agent-command="${esc(command)}" data-copy-label="${esc(label)}" title="${esc(hint)}">${esc(label)}</button>`;
}
async function openSearchOffers(){
 flowFilters.solicitar='todas';tableState.solicitar.filters={};
 viewMemory['solicitar/']={...(viewMemory['solicitar/']||{}),filterText:'',scroll:0};
 await setScreen('solicitar');
}
function flowToolbar(tab,choices){
 return `<div class="offer-toolbar" role="region" aria-label="Filtros y acciones de ofertas"><div class="flow-filter-choices" role="group" aria-label="Filtrar ofertas">${choices.map(([value,label,count])=>`<button data-flow-filter="${value}" data-filter-tab="${tab}" aria-pressed="${flowFilters[tab]===value}">${label} <span class="filter-count">${count}</span></button>`).join('')}</div><div class="offer-toolbar-actions">${bulkToolbar()||`${bulkSelectionMode?bulkExitButton():choices[0]?.[2]===0?'':'<button data-bulk-mode="1" aria-pressed="false">Seleccionar varias</button>'}`}</div></div>`;
}
function bulkExitButton(){return `<button class="icon-button bulk-clear" data-bulk-clear="1" aria-label="Salir de la selección múltiple" title="Salir de la selección múltiple (Esc)">${icon('close')}</button>`;}
function requestButtonContent(mode,label=requestModes[mode].label){return `<span class="request-icon" aria-hidden="true">${icon(requestModes[mode].icon)}</span>${esc(label)}`;}
function selectionButtons(j){return `<button class="primary request-button" data-select="${esc(j.id)}" data-selection-mode="review" title="Revisarás la solicitud y autorizarás su envío final.">${requestButtonContent('review')}</button><button class="primary request-button" data-select="${esc(j.id)}" data-selection-mode="auto" title="Permite enviar esta oferta tras las comprobaciones, sin tu aprobación final." aria-describedby="offer-auto-help-${esc(j.id)}">${requestButtonContent('auto')}</button><span id="offer-auto-help-${esc(j.id)}" class="sr-only">Permite enviar esta oferta tras las comprobaciones, sin tu aprobación final.</span>`;}
function bulkOptions(j){
 if(j.historical)return [];
 const step=UI.step(j),options=[],category=UI.offerState(j).key;
 if(category==='sin-elegir')options.push(['discard','Descartar']);
 if(category==='seguimiento'&&j.sent)options.push(['close','Cerrar seguimiento']);
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
function commonBulkOptions(jobs=bulkJobs()){return jobs.length?bulkOptions(jobs[0]).filter(([key])=>jobs.every(j=>bulkOptions(j).some(([other])=>key===other))):[];}
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
  const help=mode==='auto'?' Permite enviar estas ofertas tras las comprobaciones, sin tu aprobación final.':mode==='review'?' Revisarás las solicitudes y autorizarás su envío final.':'';
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
 const tone=category.key==='atencion'?'blocked':['descartadas','rechazadas'].includes(category.key)?'past':j.sent?'sent':UI.canChoose(j)?'action':'working';
 const latest=j.lastActivityAt||(model.history||[]).filter(h=>h.opportunityId===j.id).reduce((at,h)=>{const next=tableTimestamp(h.at),previous=tableTimestamp(at);return next!==null&&(previous===null||next>previous)?h.at:at;},'');
 return {j,kind,category,status:category.label,tone,activityAt:latest||j.sent?.at||historicalDate(j.lastActivityLabel),activity:j.historical?j.lastActivityLabel||'—':latest||j.sent?.at?date(latest||j.sent.at):'—'};
}
const fold=window.StubbsJobsFormatting.fold;
const displayCase=window.StubbsJobsFormatting.displayCase;
const formatOptions=()=>({currency:model?.searchContext?.currency||'EUR',timeZone:model?.personalized?undefined:'Europe/Madrid'});
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
 if(key==='schedule')return tableText(j.schedule,'schedule');
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
 return tab==='solicitar'?({descartadas:'discarded',seguimiento:'sent',logradas:'achieved',cerradas:'closed',rechazadas:'rejected'})[flowFilters[tab]]||'firstSeen':'firstSeen';
}
function defaultTableTimestamp(record,key){
 const j=record.j;
 return tableTimestamp(key==='discarded'?j.discardedAt||j.archivedAt:key==='sent'?j.sent?.at||j.appliedAt:key==='achieved'?j.lifecycle?.achievedAt:key==='closed'?j.lifecycle?.closure?.at||j.archivedAt:key==='rejected'?j.rejectedAt||(j.archiveOutcome==='rejected'?j.archivedAt:null):j.firstSeenAt);
}
function sortedFilteredRecords(tab,records){
 const state=tableState[tab],columns=tableFilterColumns();
 const visible=records.filter(record=>columns.every(([key])=>!Object.hasOwn(state.filters,key)||state.filters[key].map(value=>key==='salary'&&/^(no publicado|[-—])$/i.test(value)?'—':['country','mode','contract','schedule'].includes(key)?tableText(value,key):value).includes(tableFilterValue(record,key))));
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
 return `<tr class="flow-table-row" data-tone="${tone}" data-anchor="job-${esc(j.id)}" data-job-row="${esc(j.id)}" data-offer-state="${record.category.key}">${selectable?`<td class="selection-cell"><label class="offer-select-control"><input type="checkbox" id="bulk-offer-${esc(j.id)}" data-bulk-select="${esc(j.id)}" aria-label="Marcar ${esc(j.company)}: ${esc(j.title)}" ${tableSelection.has(j.id)?'checked':''}></label></td>`:''}<td>${firstSeenDay(j)?`<time data-found-at="${esc(j.firstSeenAt)}" datetime="${esc(j.firstSeenAt)}" title="Primera detección: ${esc(date(j.firstSeenAt))}">${esc(tableValue(record,'firstSeen'))}</time>`:cellText('—')}</td><td class="company-cell"><div class="company-selection"><button class="table-job-link company-identity" data-job="${esc(j.id)}" title="${esc(j.company)}" aria-label="Abrir ficha de ${esc(j.company)}: ${esc(j.title)}"><span class="company-name">${esc(displayCase(j.company))}</span>${icon('chevron-right','company-open')}</button></div></td><td title="${esc(j.title)}"><span class="offer-title-text">${esc(displayCase(j.title))}</span></td><td>${cellText(tableValue(record,'country'))}</td><td>${cellText(tableValue(record,'mode'))}</td><td>${cellText(tableValue(record,'contract'))}</td><td title="${esc(j.schedule||'Sin dato')}">${cellText(tableValue(record,'schedule'))}</td><td>${salaryCell(j)}</td><td title="${esc(status)}"><span data-offer-state="${record.category.key}" class="flow-status">${icon(record.category.icon,'offer-state-icon','solid')}${esc(state)}</span></td></tr>`;
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
 return `${applied}<p class="table-scroll-hint">Desliza la tabla. La empresa permanece visible; abre su ficha para ver todos los datos.</p><div class="workflow-table-wrap" role="region" aria-label="Ofertas; desplázate horizontalmente para ver todas las columnas" tabindex="0"><table class="workflow-table${selectable?' workflow-table-selectable':''}"><caption class="sr-only">Ofertas y solicitudes guardadas. Usa las opciones de cada columna para filtrar y ordenar.</caption><thead><tr>${selectHead}${head}</tr></thead><tbody>${shown.length?shown.map(record=>flowRow(record,selectable)).join(''):`<tr><td colspan="${columns.length+(selectable?1:0)}" class="table-empty">${emptyMessage}${filters.length?`<p><button data-clear-table="${tab}">Mostrar todas las ofertas de este estado</button></p>`:''}</td></tr>`}</tbody></table></div><div class="table-footer"><span>${visible.length>shown.length?`${shown.length} de `:''}${visible.length} ${visible.length===1?'oferta':'ofertas'}${visible.length!==records.length?` de ${records.length}`:''}</span>${!state.sort?`<span class="table-default-order">Orden: ${({firstSeen:'búsqueda',discarded:'descarte',sent:'solicitud',achieved:'puesto ofrecido',closed:'cierre',rejected:'rechazo'})[defaultTableOrder(tab)]}, de más reciente a más antiguo</span>`:''}${filters.length?`<button class="link-button" data-clear-table="${tab}">Limpiar filtros</button>`:''}${visible.length>limit?'<button data-more-history="1">Cargar más</button>':''}</div>`;
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
 const all=[...model.opportunities,...UI.archive(model)].filter(j=>!offerProfileFilter||j.searchProfileIds?.includes(offerProfileFilter));
 const stage=j=>UI.flowStage(j);
 const categories=new Map(all.map(j=>[j.id,UI.offerState(j)]));
 const legacy={elegidas:'preparacion',enviadas:'seguimiento',archivadas:'descartadas'};
 flowFilters.solicitar=legacy[flowFilters.solicitar]||flowFilters.solicitar;
 if(!['todas',...UI.offerStates.map(state=>state.key)].includes(flowFilters.solicitar))flowFilters.solicitar='todas';
 const counts=Object.fromEntries(UI.offerStates.map(state=>[state.key,0]));
 for(const category of categories.values())counts[category.key]++;
 const priority=j=>categories.get(j.id).key==='atencion'?0:stage(j)==='historial'?8:['Entrevista','Oferta'].includes(j.state)?1:UI.step(j).owner==='you'?2:UI.canChoose(j)?3:stage(j)==='solicitar'?4:stage(j)==='seguir'?6:j.apply==='No'?7:5;
 const visible=all.filter(j=>flowFilters.solicitar==='todas'||categories.get(j.id).key===flowFilters.solicitar).sort((a,b)=>priority(a)-priority(b)||(a.externalDeadline||'9999').localeCompare(b.externalDeadline||'9999')||(a.company||'').localeCompare(b.company||''));
 const records=visible.map(j=>flowRecord(j,stage(j)==='elegir'?'elegir':stage(j)==='solicitar'?'solicitar':'seguir'));
 const choices=[['todas','Todas',all.length],...UI.offerStates.filter(state=>['descartadas','sin-elegir','seguimiento','logradas','cerradas','rechazadas'].includes(state.key)||counts[state.key]>0||flowFilters.solicitar===state.key).map(state=>[state.key,({descartadas:'Descartadas',logradas:'Logradas',cerradas:'Cerradas',rechazadas:'Rechazadas'})[state.key]||state.label,counts[state.key]])];
  const empty=all.length?'No hay ofertas en este grupo.':'Aún no hay ofertas. Pide una búsqueda en el chat de tu agente.';
  const table=all.length?workflowTable('solicitar',records,empty):'<div class="empty-state"><p>Aún no hay ofertas. Pide una búsqueda en el chat de tu agente o añade una oferta.</p></div>';
  return flowShell('solicitar',`<div class="offers-heading"><div><h1>Ofertas</h1><p class="page-lead">Compara las ofertas, elige dónde solicitar y consulta cada resultado.</p></div><button class="primary offers-add" data-screen="nueva">${icon('plus')}Añadir oferta</button></div>${offerProfileControls()}${flowToolbar('solicitar',choices)}${table}`);
}
function followPage(){return applyPage();}
function findResults(){
 const query=fold(filterText.trim());if(!query){tableState.encontrar.records=[];return '';}
 const jobs=[...model.opportunities,...UI.archive(model)].filter(j=>fold(j.company+' '+j.title).includes(query)).sort((a,b)=>{const order={solicitar:0,elegir:1,seguir:2,historial:3};return order[UI.flowStage(a)]-order[UI.flowStage(b)]||a.company.localeCompare(b.company);});
 return workflowTable('encontrar',jobs.map(j=>flowRecord(j,UI.flowStage(j))),'Sin resultados guardados.');
}
function findPage(){return `<div class="flow-view search-results-view"><div class="offer-toolbar search-results-toolbar"><h1>Resultados guardados</h1></div><div id="find-results">${findResults()}</div></div>`;}
function answerList(values,overrides=null,extra=''){
  if(!Object.keys(values).length&&!extra)return '<p class="muted">Sin respuestas de formulario guardadas.</p>';
  return `<dl class="meta">${Object.entries(values).map(([k,v])=>`<div><dt>${esc(fieldLabel(UI.answerTitle((selected?getJob(selected)?.fieldDefinitions?.[k]?.label:null)||model.labels[k]||k)))}</dt><dd>${answerLabel(v)}${overrides&&Object.hasOwn(overrides,k)?' · Solo aquí':''}</dd></div>`).join('')}${extra}</dl>`;
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
function offerAssessment(job){return window.StubbsJobsExplanations.assessment(job,{esc});}
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
function outcomePicker(j){
 const category=UI.offerState(j).key;
 if(!j.sent||category==='logradas'||j.requests.some(r=>r.type==='send'&&r.status==='running'))return '';
 const label=['cerradas','rechazadas'].includes(category)?'Cambiar resultado':'Registrar resultado';
 return `<details id="offer-outcome-${esc(j.id)}" class="offer-outcome-picker"><summary>${label}</summary><div class="offer-outcome-options">${[['achieve','Lograda','logradas'],['mark-rejected','Rechazada','rechazadas'],['close','Cerrada','cerradas']].map(([action,label,key])=>`<button data-offer-outcome="${action}" data-job-id="${esc(j.id)}"${category===key?' disabled aria-label="'+label+' (actual)"':''}>${label}</button>`).join('')}</div></details>`;
}
function caseHistory(j){return window.StubbsJobsActivity.caseHistory(j,model);}
function recentCaseHistory(j){return window.StubbsJobsActivity.recent(caseHistory(j),model).reverse();}
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
 const stateDetail=UI.detailMessage(j,step);
 const contacts=(j.contactDrafts||[]).length?`<details class="case-disclosure"><summary>Borradores de contacto (${j.contactDrafts.length})</summary><p class="helper">No enviados.</p>${j.contactDrafts.map((c,i)=>`<div class="case-piece"><strong>${esc(c.purpose)}</strong><p>${esc(c.recipient)}</p><p class="note-text">${esc(c.message)}</p><button data-copy-contact="${i}">Copiar</button></div>`).reverse().join('')}</details>`:'';
 const formAnswers=UI.formAnswers(material);
 const cvMissing=j.sent?'CV enviado no disponible':'Pendiente de preparar';
 const cvAnswer=`<div class="case-cv-answer"><dt>CV para la oferta</dt><dd><article class="cv-card case-cv-card" aria-label="CV para la oferta"${j.cvUrl?'':' data-cv-state="pending"'}>${icon('file','cv-card-icon')}<h3 class="cv-card-title" title="${esc(j.cvUrl?j.cvLabel||'Currículum.pdf':cvMissing)}">${esc(j.cvUrl?j.cvLabel||'Currículum.pdf':cvMissing)}</h3>${j.cvUrl?`<a class="cv-card-open" href="${esc(j.cvUrl)}" target="_blank" rel="noopener" aria-label="Abrir PDF: ${esc(j.cvLabel||'Currículum.pdf')}">Abrir PDF</a>`:''}</article></dd></div>`;
 const presentationAnswer=UI.presentationVisible(material)?`<div class="case-form-presentation"><dt class="case-answer-heading"><span>Presentación</span>${canEdit?`<button class="link-button" data-edit="${esc(j.id)}" aria-label="Editar presentación">Editar</button>`:''}</dt><dd class="note-text">${esc(material.message)}</dd></div>`:'';
  const answers=answerList(formAnswers,j.sent?null:j.answerOverrides,cvAnswer+presentationAnswer),assessment=offerAssessment(j),criteriaActions=offerCriteriaControls(j),profileBasis=offerProfileBasis(j);
 return `<div class="detail-wrap offer-detail">${offerHeading(j)}
  <div class="offer-layout"><div class="offer-columns"><aside class="offer-rail" aria-label="Decisión y condiciones">
  <section class="case-status offer-status" data-offer-section="status" data-offer-state="${UI.offerState(j).key}" aria-label="Situación y acciones"><div class="offer-status-copy"><div class="offer-status-line"><strong data-offer-state="${category.key}">${icon(category.icon,'offer-state-icon','solid')}${esc(category.label)}</strong>${j.selection?.selected&&!j.sent?`<span class="offer-selection-mode">${j.selection.mode==='auto'?'Auto-solicitud':'Solicitud con revisión'}</span>`:''}</div>${stateDetail&&stateDetail!==step.label?`<p>${esc(stateDetail)}</p>`:''}${followupStatus(j)}${UI.nextAction(j)?`<p class="offer-next-action">${esc(UI.nextAction(j))}</p>`:''}${active(j)&&j.externalDeadline?`<p class="offer-deadline">Plazo: ${date(j.externalDeadline)}</p>`:''}</div><div class="actions offer-actions">${action}${followupActions(j)}${category.key!=='logradas'?`<button class="offer-change" data-change="${esc(j.id)}">Pedir cambio</button>`:''}${category.key==='sin-elegir'?`<button class="offer-change" data-offer-outcome="discard" data-job-id="${esc(j.id)}">Descartar</button>`:''}${outcomePicker(j)}</div></section>
  ${j.integrityError?`<div class="error" role="alert">${esc(j.integrityError)}</div>`:''}
  <section class="case-section offer-conditions" data-offer-section="conditions"><div class="section-heading"><h2>Condiciones</h2></div>${offerConditions(j)}</section>
  ${criteriaActions||j.selection?.selected&&!j.sent||approved&&!j.sent?`<details class="case-disclosure case-more" id="offer-more-${esc(j.id)}"><summary>Más acciones</summary><div class="more-links">${j.selection?.selected&&!j.sent&&!sending?`<button data-unselect="${esc(j.id)}">Retirar selección</button>`:''}${approved&&!j.sent?`<button data-revoke="${esc(current.id)}">Retirar permiso de envío</button>`:''}${criteriaActions}</div></details>`:''}</aside>
  <div class="case-sections offer-sections">${assessment||profileBasis?`<div class="offer-overview" data-offer-section="overview">${assessment}${profileBasis}</div>`:''}
 <section class="case-section case-material" data-offer-section="form"><div class="section-heading"><h2>${isHttpUrl(material.recipient)?`<a href="${url(material.recipient)}" target="_blank" rel="noopener">Formulario de solicitud ${icon('arrow-up-right')}</a>`:'Formulario de solicitud'}</h2>${canEdit?`<button class="link-button" data-answers="${esc(j.id)}" aria-label="Editar respuestas del formulario">Editar</button>`:''}</div>
 ${material.legacyIncomplete?'<p class="muted">Este registro antiguo confirma el envío, pero no conserva las respuestas ni la presentación de aquella solicitud.</p>':''}${!isHttpUrl(material.recipient)?material.recipient?`<p>Solicitud por correo: ${esc(material.recipient)}</p>`:j.sent?'':'<p class="muted">Pendiente de comprobar el acceso.</p>':''}${answers}${contacts}</section>
 <section class="case-section offer-activity" data-offer-section="activity"><div class="section-heading"><h2>Actividad</h2><button class="link-button" data-activity="${esc(j.id)}">Ver historial completo</button></div>${timeline(recentCaseHistory(j),3,false,true)}</section>
 <section class="case-section offer-notes"><details id="offer-notes-${esc(j.id)}"><summary>Notas de seguimiento</summary><form data-form="offer-note"><label class="field"><span>Nota personal</span><textarea name="Notas de seguimiento" rows="3" maxlength="10000">${esc(j.notes||'')}</textarea></label><p class="helper">Estas notas no se incluyen en la solicitud ni cambian sus requisitos. Para corregir la oferta, usa Pedir cambio.</p>${formErrors()}<button type="submit">Guardar nota</button></form></details></section>
 </div></div></div></div>`;
}
function reviewPage(j=reviewSnapshot,bulk=false){
  if(!j)return top('No hay una solicitud para revisar');
  const current=getJob(j.id),pack=j.packages.find(p=>p.id===j.fingerprint),valid=UI.reviewValid(j,current);
  if(!pack)return `<p>El agente debe comprobar la solicitud antes de autorizar el envío.</p>`;
  const material=pack.payload;
  return (bulk?`<h2>${esc(j.company)} · ${esc(j.title)}</h2>`:top('Revisar solicitud',esc(j.company)+' · '+esc(j.title)))+`
    ${!valid?`<div class="error" role="alert">El envío ha cambiado o necesita una nueva comprobación. Esta versión no se puede autorizar.<div class="actions"><button data-review="${esc(j.id)}">Ver versión actual</button><button data-job="${esc(j.id)}">Ver oferta</button></div></div>`:''}
    <div class="review-page"><div class="split review-layout"><section class="panel"><div class="section-heading"><h2>CV adaptado</h2><a href="${pack.cvUrl}&download=1">Descargar</a></div><p class="file-name">${esc(j.cvLabel)}</p>${pdfView(pack.cvUrl)}</section>
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
 return `<div class="field"><span id="work-authorizations-label">Permiso de trabajo sin patrocinio en</span><input type="hidden" name="workAuthorizations" data-type="multiselect"${association} value="${esc(JSON.stringify(value??null))}"><details class="work-authorizations" data-work-authorizations="1"><summary aria-labelledby="work-authorizations-label work-authorizations-value"><span id="work-authorizations-value">${esc(selected.join(', ')||'Sin especificar')}</span></summary><div class="permit-options" role="group" aria-labelledby="work-authorizations-label">${workAuthorizationOptions(selected)}</div><div class="permit-add"><input type="text" data-permit-other="1" maxlength="100" placeholder="Otro país o zona" aria-label="Otro país o zona con permiso de trabajo"><button type="button" data-permit-add="1" aria-label="Añadir país o zona">+</button></div></details></div>`;
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
function growProfileFields(){for(const field of main.querySelectorAll('textarea[data-auto-grow]'))growField(field);}
window.addEventListener('resize',()=>requestAnimationFrame(growProfileFields));
function fieldHtml(key,definition,value){
  const label=fieldLabel(UI.answerTitle(definition.label)),type=definition.type;
  const helpId=definition.help?(definition.descriptionId||'field-'+key+'-help'):definition.descriptionId,labelId=definition.help?helpId+'-label':null;
  const association=(definition.form?` form="${esc(definition.form)}"`:'')+(definition.controlId?` id="${esc(definition.controlId)}"`:'')+(helpId?` aria-describedby="${esc(helpId)}"`:'')+(labelId?` aria-labelledby="${esc(labelId)}"`:'');
  const numberLimits=type==='number'?numberAttributes(key):'',inputType=type==='number'?'number':['email','tel','url'].includes(definition.inputType)?definition.inputType:'text';
  if(type==='multiselect')return workAuthorizationField(value,association);
  const input=type==='boolean'?`<select name="${esc(key)}"${association} data-type="boolean"><option value="">Sin responder</option><option value="true" ${value===true?'selected':''}>Sí</option><option value="false" ${value===false?'selected':''}>No</option></select>`:type==='longtext'?`<textarea name="${esc(key)}"${association}${definition.autoGrow?' data-auto-grow="1"':''} rows="${definition.rows||10}" maxlength="${definition.maxlength||20000}" ${definition.placeholder?`placeholder="${esc(definition.placeholder)}"`:''}>${esc(value)}</textarea>`:`<input name="${esc(key)}"${association} data-type="${esc(type)}" type="${inputType}" ${numberLimits} value="${esc(value)}" ${definition.autocomplete?`autocomplete="${esc(definition.autocomplete)}"`:''} ${definition.placeholder?`placeholder="${esc(definition.placeholder)}"`:''} maxlength="${definition.maxlength||(key==='noticeDays'?300:5000)}">`;
  return `<label class="field"><span${labelId?` id="${esc(labelId)}"`:''}>${esc(label)}</span>${input}${definition.help?`<small class="helper" id="${esc(helpId)}">${esc(definition.help)}</small>`:''}</label>`;
}

function syncProfileNavigation(){
 for(const link of main.querySelectorAll('[data-profile-section]')){if(link.dataset.profileSection===profileSection)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');}
}
function updateProfileSection(){
 if(screen!=='perfil'||selected)return;
 const headerBottom=document.querySelector('.site-header')?.getBoundingClientRect?.().bottom||84;
 let current=profileSections[0][0];
 for(const [id] of profileSections){const section=document.getElementById(id),rect=section?.getBoundingClientRect?.();if(rect&&rect.top<=headerBottom+36)current=id;}
 const scrollRoot=document.scrollingElement||document.documentElement,viewportHeight=document.documentElement?.clientHeight||window.innerHeight||0,scrollHeight=scrollRoot?.scrollHeight||0,scrollTop=window.scrollY??scrollRoot?.scrollTop??0;
 if(viewportHeight>0&&scrollTop>0&&scrollHeight>viewportHeight&&scrollTop+viewportHeight>=scrollHeight-2)current=profileSections.at(-1)[0];
 if(current!==profileSection){profileSection=current;syncProfileNavigation();}
}
function profileForm(){
 const j=selected?getJob(selected):null;
 if(j){
  const formKeys=Array.isArray(j.draft.formAnswerKeys)?j.draft.formAnswerKeys.filter(key=>Object.hasOwn(j.fieldDefinitions,key)):[];
  const keys=[...new Set(['currentCity','workPermitWithoutSponsorship','salaryExpectationFixed',...j.draft.requiredAnswers,...formKeys])];
  return `<div class="profile-layout"><form data-form="profile" class="panel"><h1>Respuestas para ${esc(j.company)}</h1><div class="form-grid">${keys.map(k=>fieldHtml(k,j.fieldDefinitions[k],j.answers[k])).join('')}</div><p class="helper">Los datos generales se reutilizan; las respuestas de esta oferta quedan aquí.</p>${formErrors()}<button class="primary" type="submit" hidden>Guardar cambios</button>${Object.keys(j.answerOverrides).length?'<button type="button" data-inherit="1">Volver a usar los datos generales</button>':''}</form></div>`;
 }
 const about=formSource('about');
 return `<div class="profile-layout"><div class="profile-heading"><h1>Mi perfil</h1><p class="page-lead">Tus datos y preferencias para preparar solicitudes con precisión.</p></div><div class="profile-workspace"><nav class="profile-section-nav" aria-label="Secciones de Mi perfil">${profileSections.map(([id,label])=>`<a href="#${id}" data-profile-section="${id}"${profileSection===id?' aria-current="location"':''}>${label}</a>`).join('')}</nav><div class="profile-content">${legacyRecovery()}
  <section class="profile-card" id="profile-about"><h2>Sobre mi</h2><div class="profile-fields"><form data-form="about" class="profile-fields-form"><div class="form-grid">${Object.entries(sectionDefinitions('about')).map(([key,definition])=>fieldHtml(key,definition,about[key])).join('')}</div>${formErrors()}</form>
  <form data-form="experience" class="profile-fields-form"><div class="form-grid"><div class="profile-field-wide">${fieldHtml('text',{label:'Mi experiencia',type:'longtext',rows:10},model.experience)}</div><div class="profile-field-wide">${fieldHtml('languages',{...sectionDefinitions('search').languages,form:'profile-search-form'},formSource('search').languages)}</div></div>${formErrors()}</form>${formErrors('search')}
  </div></section>
  ${searchSettingsPanels()}
  ${cvLibrary()}
  </div></div><aside class="profile-savebar" data-profile-savebar aria-label="Guardar cambios de Mi perfil" hidden><div class="profile-savebar-inner"><span data-profile-pending>Cambios sin guardar</span><button type="button" class="primary" data-save-profile="1" title="Guardar cambios (Ctrl+S)">Guardar cambios</button></div></aside>
 </div>`;
}
function legacyRecoveryItems(){
 let recovered=[];try{recovered=JSON.parse(draftStorage.getItem('stubbs_jobs-recovered-drafts')||'[]');if(!Array.isArray(recovered))recovered=[];}catch{}
 return window.StubbsJobsDrafts.legacyDrafts(sessionStorage,localStorage).filter(item=>!recovered.includes(JSON.stringify(item)));
}
function legacyRecovery(){
 const items=legacyRecoveryItems();if(!items.length)return '';
 const titles={datos:'Sobre mi',experiencia:'Mi experiencia',busqueda:'Mis idiomas y lo que busco',fuentes:'Mis fuentes de búsqueda'};
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
 return `<section class="profile-card" id="profile-work"><h2>Lo que busco</h2>${searchProfileControls()}${profile?'<hr class="search-profile-separator" aria-hidden="true">':''}<div class="profile-fields"><form data-form="search" id="profile-search-form" class="profile-fields-form"${scope}>
  ${searchCriteriaFields(search,['targetRoles','keywords','searchPriorities',...(profile?['searchNotes']:[]),'location','workMode','onsiteLocations','contract','maxTrips','minimumFixed','salaryExpectationFixed',...(profile?['salaryCurrency']:[])])}${formErrors('search')}</form>
  ${searchCriteriaFields(search,['previousApplications'],'profile-search-form',{flat:true})}
  ${profile?'<p class="helper">Idiomas, empresas a evitar y salario para formularios son comunes a todos los perfiles. El mínimo salarial y su moneda pertenecen a este perfil.</p>':''}
  <form data-form="sources" class="profile-fields-form"${scope}>${searchOptionsControls(sources)}${formErrors()}</form></div></section>`;
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
 rememberAllForms();searchProfileId=identifier;workspaceSession.setItem('stubbs_jobs-search-profile',identifier);
 dirty=false;conflict=null;render(true);
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
function offerProfileControls(){
 if(!model.searchProfiles||model.searchProfiles.length<2)return '';
 return `<label class="offer-profile-filter">Perfil de búsqueda <select data-offer-profile="1"><option value="">Todos los perfiles</option>${model.searchProfiles.map(p=>`<option value="${esc(p.id)}"${offerProfileFilter===p.id?' selected':''}>${esc(p.name)}${p.archivedAt?' · Archivado':''}</option>`).join('')}</select></label>`;
}
function offerProfileBasis(j){
 if(!model.searchProfiles)return '';
 return `<p class="helper offer-criteria-basis">Evaluada con: ${esc(j.searchProfileName||'Búsqueda anterior')}${j.searchProfileDeleted?' · Perfil eliminado':j.criteriaScope==='round'?' · Preferencias guardadas al buscar':''}</p>`;
}
function offerCriteriaControls(j){
 if(!model.searchProfiles||j.sent||['Cerrada','Lograda','Rechazada','Oferta'].includes(j.state))return '';
 const available=model.searchProfiles.filter(p=>!p.archivedAt);
 if(!available.length||model.searchProfiles.length<2&&!j.searchProfileDeleted&&j.criteriaScope!=='round')return '';
 return `<div class="offer-profile-management"><p class="helper">Otro perfil puede cambiar el encaje y los mínimos de esta oferta, y exigir revisar una solicitud preparada.</p><div class="offer-criteria-change"><label>Cambiar perfil de evaluación <select data-offer-criteria-profile="${esc(j.id)}"><option value="">Elige un perfil</option>${available.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></label><button type="button" data-offer-criteria-change="${esc(j.id)}">Ver efecto</button></div></div>`;
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
 const sections={datos:['Sobre mi','profile-about'],experiencia:['Sobre mi','profile-about'],busqueda:['Lo que busco','profile-work'],fuentes:['Lo que busco','profile-work']};
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
  const guidance={contact:{title:'Aclarar el contacto',label:'Canal de contacto que conoces',placeholder:'Indica un canal accesible y cómo puede comprobarlo la IA.',hint:'Esta aclaración no autoriza mensajes ni invitaciones. Si quieres dar un permiso concreto, indícalo a la IA en el chat.'},access:{title:'Aclarar el acceso',label:'Acceso disponible para comprobar',placeholder:'Indica si ya iniciaste sesión y qué historial debe revisar la IA.',hint:'Inicia sesión en tu navegador antes de guardar la aclaración. No escribas contraseñas aquí.'},answers:{title:'Aportar una respuesta',label:'Dato que puedes confirmar',placeholder:'Escribe solo lo que sabes con certeza.',hint:'La IA comprobará cómo usar esta respuesta en la solicitud.'},decision:{title:'Aclarar la decisión pendiente',label:'Tu decisión o antecedente confirmado',placeholder:'Explica qué sabes con certeza; si no lo recuerdas, indícalo.',hint:'La IA comprobará la posible duplicidad antes de continuar.'},other:{title:'Aclarar lo que falta',label:'Información que puedes aportar',placeholder:'Explica qué dato o paso está pendiente.',hint:'La revisión seguirá bloqueada hasta que la IA lo compruebe.'}}[blocked?.need]||null;
  const title=guidance?.title||(j?'Pedir cambio':'Pedir un cambio en Mi perfil'),subtitle=j?esc(displayCase(j.company))+' · '+esc(displayCase(j.title)):'';
  const label=guidance?.label||(j?'Qué quieres cambiar de esta oferta':'Qué quieres cambiar');
  return `<div class="form-wrap">${top(title,subtitle)}${blocked?`<p class="notice">${esc(blocked.summary||'Esta solicitud necesita una aclaración.')}</p>`:j?`<p>${esc(UI.step(j).detail)}</p>`:''}${queued?.instructions?.length?`<section class="section"><h2>Ya guardaste para la IA</h2><p class="note-text">${esc(queued.instructions.map(i=>i.text).join('\n'))}</p><p class="helper">Puedes añadir otra aclaración a este trabajo pendiente.</p></section>`:''}<form data-form="change" class="panel"><label class="field"><span>${esc(label)}</span><textarea name="message" rows="5" maxlength="5000" required placeholder="${esc(guidance?.placeholder||'Por ejemplo: revisa cómo encaja mi experiencia con esta oferta.')}"></textarea></label><p class="helper">${esc(guidance?.hint||'Guarda la petición y continúa en el chat del agente. Pedir una revisión no reabre la oferta ni autoriza un envío.')}</p>${blocked?'<p class="helper">Guardar deja tu aclaración en cola. El bloqueo seguirá vigente hasta que la IA la compruebe.</p>':''}${formErrors()}<div class="form-actions"><button class="primary" type="submit">${blocked?'Guardar aclaración':'Guardar petición'}</button><span class="shortcut-hint" aria-hidden="true"><kbd>Ctrl</kbd><kbd>S</kbd></span></div></form></div>`;
}
function editForm(){const j=getJob(selected);return `<div class="form-wrap">${top('Borrador para '+esc(displayCase(j.company)),'Al guardar se revisará el borrador.')}<form data-form="draft" class="panel"><label class="field"><span>Destino</span><input name="recipient" maxlength="15000" value="${esc(j.draft.recipient)}"></label>${UI.presentationVisible(j.draft)?`<p class="helper">${esc(UI.presentationUsage(j.draft))}</p><label class="field"><span>Presentación</span><textarea name="message" rows="6" maxlength="15000">${esc(j.draft.message)}</textarea></label>`:''}${formErrors()}<div class="form-actions"><button class="primary" type="submit">Guardar borrador</button><span class="shortcut-hint" aria-hidden="true"><kbd>Ctrl</kbd><kbd>S</kbd></span></div></form></div>`;}
const cvSummaryObserver=window.ResizeObserver?new window.ResizeObserver(entries=>{
 for(const {target} of entries)sizeCvCard(target);
}):null;
function sizeCvCard(summary){
 const height=summary.getBoundingClientRect?.().height,card=summary.closest?.('.cv-card');
 if(height>0&&card?.style)card.style.setProperty('--cv-summary-height',height+'px');
}
function syncCvCardLayout(){
 cvSummaryObserver?.disconnect();
 for(const summary of main.querySelectorAll('.cv-card-summary')){sizeCvCard(summary);cvSummaryObserver?.observe(summary);}
}
function rememberCvCards(){
 for(const card of main.querySelectorAll('details[data-cv-key]'))if(card.dataset.cvKey){if(card.open)openCvCards.add(card.dataset.cvKey);else openCvCards.delete(card.dataset.cvKey);}
}
function cvCardKey(cv,nameCounts){
 if(cv.id)return 'id:'+cv.id;
 if(cv.fingerprint)return 'fingerprint:'+cv.fingerprint+':'+(cv.path||cv.url||'');
 for(const field of ['path','url'])if(cv[field])return field+':'+cv[field];
 if(cv.name&&nameCounts.get(cv.name)===1)return 'name:'+cv.name;
 if(!anonymousCvKeys.has(cv))anonymousCvKeys.set(cv,'view:'+ ++anonymousCvSequence);
 return anonymousCvKeys.get(cv);
}
function cvLibrary(){
  const cvs=model.cvLibrary||[],nameCounts=new Map();for(const cv of cvs)nameCounts.set(cv.name,(nameCounts.get(cv.name)||0)+1);
  const card=cv=>{
   const key=cvCardKey(cv,nameCounts),recorded=Array.isArray(cv.usage)?cv.usage:null,byOffer=new Map();
   for(const item of recorded||[])if(item&&['prepared','sent'].includes(item.kind)&&item.opportunityId){const previous=byOffer.get(item.opportunityId);if(!previous||previous.kind!=='sent')byOffer.set(item.opportunityId,item);}
   const usage=[...byOffer.values()],sent=usage.filter(item=>item.kind==='sent').length,prepared=usage.length-sent;
   const counts=usage.length?[`${usage.length} ${usage.length===1?'oferta':'ofertas'}`,prepared&&`${prepared} ${prepared===1?'preparado':'preparados'}`,sent&&`${sent} ${sent===1?'envío confirmado':'envíos confirmados'}`].filter(Boolean).join(' · '):recorded?.length===0?'Sin ofertas asociadas':'Uso no registrado';
   const uses=usage.length?`<ul class="cv-usage-list">${usage.map(item=>`<li><a class="cv-usage-offer" id="cv-usage-${encodeURIComponent(key)}-${encodeURIComponent(item.opportunityId)}" href="#detalle/${encodeURIComponent(item.opportunityId)}" data-job="${esc(item.opportunityId)}" data-cv-key="${esc(key)}"><span class="cv-usage-company">${esc(item.company||'Oferta vinculada')}</span>${item.title?`<span class="cv-usage-title">${esc(item.title)}</span>`:''}</a><div class="cv-usage-meta"><span class="cv-usage-state${item.kind==='sent'?' cv-usage-state--sent':''}" data-kind="${item.kind}">${item.kind==='sent'?'Envío confirmado':'CV preparado'}</span>${item.at||item.historical?`<small>${item.at?date(item.at):''}${item.at&&item.historical?' · ':''}${item.historical?'Registro anterior':''}</small>`:''}</div></li>`).join('')}</ul>`:`<p class="muted cv-usage-empty">${recorded?.length===0?'Sin solicitudes asociadas.':'Aún no hay usos registrados para este CV.'}</p>`;
   const available=cv.available!==false&&Boolean(cv.url);
   return `<article class="cv-card"><details class="cv-card-details" data-cv-key="${esc(key)}"${openCvCards.has(key)?' open':''}><summary class="cv-card-summary" id="cv-summary-${encodeURIComponent(key)}">${icon('file','cv-card-icon')}<div class="cv-card-identity"><h3 class="cv-card-title" title="${esc(cv.name)}">${esc(cv.name)}</h3><p class="cv-card-counts">${esc(counts)}</p></div>${icon('chevron-down','cv-card-chevron')}</summary><div class="cv-card-content">${!available?'<p class="muted">Vuelve a añadir el PDF para abrirlo.</p>':''}${uses}</div></details><div class="cv-card-actions">${available?`<a class="cv-card-open" href="${esc(cv.url)}" target="_blank" rel="noopener" aria-label="Abrir PDF: ${esc(cv.name)}">Abrir PDF</a>`:'<span class="cv-card-unavailable">PDF no disponible</span>'}</div></article>`;
  };
  return `<section class="profile-card" id="profile-cv"><div class="cv-library-heading"><h2>Currículums</h2><label class="button upload-label">Añadir PDF<input id="cv-upload" type="file" accept="application/pdf,.pdf" aria-label="Añadir currículum en PDF"></label></div><p class="helper">PDF de hasta 10 MB. Se guarda en este ordenador al añadirlo. Despliega cada tarjeta para ver las ofertas asociadas a ese mismo PDF.</p>${cvs.length?`<div class="cv-card-grid">${cvs.map(card).join('')}</div>`:'<div class="cv-library-empty"><p>Aún no hay currículums guardados. Puedes añadir un PDF o pedir ayuda al agente para prepararlo.</p></div>'}</section>`;
}
function history(){
  const j=selected?getJob(selected):null,items=j?caseHistory(j):model.history;
  const historyIds=new Set(items.map(h=>h.id)),orphanUndo=(model.undo||[]).filter(u=>(!j||u.opportunityId===j.id)&&!historyIds.has(u.id));
  return `<div class="detail-wrap activity-log">${top(j?'Actividad de '+esc(displayCase(j.company)):'Historial')}${searchActivity(items,historyLimit,!j)}${groupedActivity(items).length>historyLimit?'<button data-more-history="1">Cargar anteriores</button>':''}${j&&j.packages.length?`<section class="section"><h2>Versiones conservadas</h2>${j.packages.slice().reverse().map(p=>`<p>${date(p.createdAt)} · ${j.sent?.packageId===p.id?'Enviada':p.isCurrent?'Actual':'Anterior'} · <a href="${p.cvUrl}" target="_blank" rel="noopener">CV adaptado</a>${!UI.presentationVisible(p.payload)?'':` · <a href="${p.messageUrl}" target="_blank" rel="noopener">Presentación</a>`}</p>`).join('')}</section>`:''}${orphanUndo.length?`<section class="section"><h2>Cambios que puedes deshacer</h2>${orphanUndo.slice().reverse().map(u=>`<p>Cambio guardado <button data-undo="${esc(u.id)}">Deshacer</button></p>`).join('')}</section>`:''}</div>`;
}


function formSource(kind){if(kind==='offer-note')return {'Notas de seguimiento':getJob(selected)?.notes??null};if(['about','search','sources'].includes(kind)){const p=currentSearchProfile();return {...model.searchContext,...model.profile,salaryCurrency:model.profile.salaryCurrency??model.searchContext.currency??'',...(p?.searchContext||{}),...(p?.criteria||model.preferences)};}return ['automation','schedule'].includes(kind)?model.automation:kind==='draft'?edit_token():kind==='preferences'?model.preferences:kind==='experience'?{text:model.experience}:kind==='context'?model.searchContext:kind==='new'?{company:'',title:'',url:''}:kind==='change'?{message:''}:selected?getJob(selected).answers:model.profile;}
function syncSourceControls(form){
 if(form?.dataset.form!=='sources')return;
 const priorities=form.querySelector?.('.source-priorities');if(priorities)priorities.hidden=!form.elements.namedItem('platforms')?.value;
}
function syncSalaryCurrency(form){
 const currency=form?.elements.namedItem(form?.dataset.searchProfileId?'salaryCurrency':'currency');if(!currency)return;
 for(const suffix of form.querySelectorAll?.('[data-salary-currency]')||[])suffix.textContent=currency.value||'Por indicar';
}
function formValues(form){const values=Object.fromEntries(new FormData(form));for(const [k,v] of Object.entries(values)){const type=form.elements.namedItem(k).dataset.type;values[k]=type==='multiselect'?JSON.parse(v||'null'):type==='boolean'?(v===''?null:v==='true'):type==='number'?(v===''?null:Number(v)):v.trim()||null;if(values[k]===null&&['about','search','sources','context'].includes(form.dataset.form)&&Object.hasOwn(window.StubbsJobsSetup.context,k))values[k]='';}return values;}
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
 rememberCvCards();
 rendering=true;try{
 if(model.setupComplete===false&&!['configurar','copias'].includes(screen)){screen='configurar';selected=null;}
 syncUndo();
 document.querySelector('.site-header')?.classList?.toggle('site-header--setup',model.setupComplete===false);
 document.querySelector('header nav').hidden=model.setupComplete===false;document.querySelector('.header-search').hidden=model.setupComplete===false;document.querySelector('.header-help').hidden=false;
 if(screen!=='informe'&&selected&&getJob(selected)&&!getJob(selected).historical&&!getJob(selected).draft){main.innerHTML='<p>Cargando la solicitud… Si tarda, comprueba la conexión con Stubbs Jobs.</p>';return;}
 const anchor=preserve?[...main.querySelectorAll('[data-anchor]')].find(n=>n.getBoundingClientRect().top>=70):null;
 const anchorKey=anchor?.dataset.anchor,anchorTop=anchor?.getBoundingClientRect().top;
 const focus=preserve?captureFocus():null;
 const scroll=viewScroll(),previousScroll=scroll.scroll,tableScroll=preserve?scroll.tableScroll:null,tableTop=preserve?scroll.tableTop:null,disclosures=preserve&&['perfil','configurar','copias','preparado','detalle','solicitar','encontrar'].includes(screen)?Object.fromEntries([...main.querySelectorAll('details[id]')].map(item=>[item.id,item.open])):null;
 const currentMenu=preserve?openFilterMenu||main.querySelector('.column-menu[open]'):null;
 const menuState=currentMenu?{tab:currentMenu.dataset.menuTab,key:currentMenu.dataset.menuKey,query:columnPanel(currentMenu)?.querySelector('[data-table-option-search]')?.value||'',scroll:columnPanel(currentMenu)?.querySelector('.column-menu-values')?.scrollTop||0}:null;
 closeColumnMenu();
 if(screen!=='informe'&&selected&&!getJob(selected)){screen='solicitar';selected=null;}
 if(screen==='revisar'&&!reviewSnapshot)reviewSnapshot=structuredClone(getJob(selected));
 const pages={'edicion-multiple':bulkEditorPage,'revision-multiple':bulkReviewPage,preparado:setupReady,programacion:scheduleForm,copias:backupsPage,configurar:setupForm,nueva:newOpportunityForm,agente:agentPage,solicitar:applyPage,seguir:followPage,encontrar:findPage,detalle:detail,revisar:reviewPage,perfil:profileForm,editar:editForm,actividad:history,cambio:changeForm,informe:activityReport};
 document.querySelector('.shell')?.classList?.toggle('shell--tables',['solicitar','encontrar'].includes(screen));
 main.innerHTML=(pages[screen]||applyPage)();
 syncOfferToolbar();
 syncCvCardLayout();
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
 for(const form of visibleForms()){const source=formSource(form.dataset.form),keys=[...new FormData(form).keys()];form._expected=Object.fromEntries(keys.map(k=>[k,source[k]??null]));form._shown={...form._expected};if(typeof form._shown.noticeDays==='number'&&form.elements.namedItem('noticeDays')?.dataset.type==='text')form._shown.noticeDays=String(form._shown.noticeDays);form._dirty=false;if(form.dataset.form==='search'){const projected=visibleSearchLocation(source.location,source.workMode,source.regions);if(projected.split||projected.mergedRegions){form._shown.location=projected.location;form._shown.workMode=projected.workMode;if(projected.split)form.dataset.splitLegacy='1';if(projected.mergedRegions){form.dataset.mergedRegions='1';form._expected.regions=source.regions;}}}restoreForm(form);syncSourceControls(form);updateSave(form);}
 syncDirty();
 syncWorkAuthorizations();
 for(const form of visibleForms())syncSalaryCurrency(form);
 growProfileFields();
 restoreFocus(focus);
 if(screen==='perfil'&&!selected)requestAnimationFrame(updateProfileSection);
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
 try{const result=await api('/api/action',attempt);acceptState(result.state);stateVersion=null;if(journalled)actionAttempts.finish(operation);return true;}
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
 const sectionLink=e.target.closest('[data-profile-section]');if(sectionLink){e.preventDefault();profileSection=canonicalProfileSection(sectionLink.dataset.profileSection);const target=document.getElementById(profileSection);target?.scrollIntoView({block:'start',behavior:'instant'});const heading=target?.querySelector('h2')||target;heading?.setAttribute('tabindex','-1');heading?.focus({preventScroll:true});syncProfileNavigation();return;}
 const b=e.target.closest('button,[data-job-row],a[data-job]'),menu=document.querySelector('.header-menu');if(menu?.open&&(!menu.contains(e.target)||b?.closest?.('.header-menu')))closeHeaderMenu();if(!b)return;try{
 if(b.dataset.searchProfileAction){await searchProfileAction(b.dataset.searchProfileAction);return;}
 if(b.dataset.searchProfileTrash){openDeletedSearchProfiles();return;}
 if(b.dataset.searchProfileRestore){await searchProfileAction('restore',b.dataset.searchProfileRestore);return;}
 if(b.dataset.offerCriteriaChange){await changeOfferCriteria(b.dataset.offerCriteriaChange);return;}
 if(b.dataset.permitAdd!==undefined){const widget=b.closest('[data-work-authorizations]'),input=widget.querySelector('[data-permit-other]'),name=input.value.trim();if(!name)return;if(name.length>100){input.reportValidity();return;}let option=[...widget.querySelectorAll('[data-permit-option]')].find(item=>item.dataset.permitOption.toLocaleLowerCase()===name.toLocaleLowerCase());if(!option){widget.querySelector('.permit-options').insertAdjacentHTML('beforeend',workAuthorizationOption(name,true));option=[...widget.querySelectorAll('[data-permit-option]')].find(item=>item.dataset.permitOption===name);}option.checked=true;saveWorkAuthorizationChoices(widget);input.value='';input.focus();return;}
 if(b.dataset.copyRecovery){const request=model.requests.find(r=>r.id===b.dataset.copyRecovery);if(!request)throw new Error('Actualiza el estado para consultar esta tarea.');const message=window.StubbsJobsRecovery.taskPrompt(model.workspacePath,request);try{await navigator.clipboard.writeText(message);toast('Petición copiada. Pégala en el chat del agente.');}catch{await confirmAction('Mensaje para tu agente',message);}return;}
 if(b.dataset.copyBackup!==undefined&&backupResult){const message=window.StubbsJobsRecovery.backupPrompt(model.workspacePath,backupResult.name);try{await navigator.clipboard.writeText(message);toast('Petición copiada. Pégala en el chat del agente.');}catch{await confirmAction('Mensaje para tu agente',message);}return;}
 if(b.dataset.backupDraft){const draft=backupDrafts().find(item=>item.key===b.dataset.backupDraft);if(!draft?.page)throw new Error('Actualiza Copias de seguridad para consultar el borrador pendiente.');if(draft.searchProfileId&&model.deletedSearchProfiles?.some(p=>p.id===draft.searchProfileId)){openDeletedSearchProfiles();toast('Recupera este perfil para revisar su borrador.');return;}if(draft.searchProfileId)await chooseSearchProfile(draft.searchProfileId);await setScreen(draft.page,draft.id,true,draft.section);if(draft.page==='detalle'){const note=main.querySelector('.offer-notes details');if(note){note.open=true;note.querySelector('textarea')?.focus();}}return;}
 if(b.dataset.copyBackupDraft){const draft=backupDrafts().find(item=>item.key===b.dataset.copyBackupDraft);if(!draft?.content)throw new Error('Actualiza Copias de seguridad para consultar el borrador pendiente.');const message='Borrador sin guardar de esta carpeta de Stubbs Jobs: '+(model.workspacePath||'la carpeta actual')+'.\n'+draft.content.map(([label,value])=>label+': '+value).join('\n')+'\nRevisa estos datos conmigo antes de incorporarlos a Mi perfil. No cambies permisos ni inicies búsquedas o envíos por esta copia.';try{await navigator.clipboard.writeText(message);toast('Borrador copiado. Revísalo antes de guardarlo.');}catch{await confirmAction('Datos del borrador',message);}return;}
 if(b.dataset.createBackup!==undefined){await createBackup(b);return;}
 if(b.dataset.recoverDraft!==undefined){await recoverLegacyDraft(Number(b.dataset.recoverDraft));return;}
 if(b.dataset.back){await goBack();return;}
 if(b.dataset.theme){window.StubbsJobsTheme.set(b.dataset.theme);b.closest('.theme-picker').open=false;return;}
 if(b.dataset.refreshState!==undefined){if(b.disabled)return;b.disabled=true;b.setAttribute('aria-busy','true');try{await Promise.all([refresh(true),new Promise(resolve=>setTimeout(resolve,650))]);if(!connection.textContent)toast('Estado actualizado.');}finally{b.disabled=false;b.removeAttribute('aria-busy');}return;}
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
 if(b.dataset.offerOutcome){
  const j=getJob(b.dataset.jobId),outcome=b.dataset.offerOutcome,category=j?UI.offerState(j).key:'';
  const allowed=j&&(outcome==='discard'?category==='sin-elegir':outcome==='reopen-followup'?j.lifecycle?.canReopen&&category!=='logradas':j.sent&&category!=='logradas'&&!j.requests.some(r=>r.type==='send'&&r.status==='running'));
  if(!allowed)throw new Error('La oferta ha cambiado. Revisa su estado actual.');
  if(await action({kind:'ui-bulk-action',action:outcome,targets:[{id:j.id}],expectedRevision:model.revision})){changeToast(({discard:'Oferta descartada.',achieve:'Solicitud lograda.', 'mark-rejected':'Rechazo registrado.',close:'Seguimiento cerrado por ti.', 'reopen-followup':'Seguimiento reabierto; permisos anteriores retirados.'})[outcome]);render(true);}
  return;
 }
 if(b.dataset.flowFilter){tableSelection.clear();flowFilters[b.dataset.filterTab]=b.dataset.flowFilter;historyLimit=30;render(true);return;}
 if(b.dataset.jobRow){if(e.target.closest('a,input,textarea,select,summary,[contenteditable]')||window.getSelection?.()?.toString())return;e.preventDefault();caseReturn=screen;await setScreen('detalle',b.dataset.jobRow);return;}
 if(b.dataset.copyPath){if(!model.workspacePath?.trim()){toast('La ubicación aún no está disponible. Actualiza el estado e inténtalo de nuevo.');return;}try{await navigator.clipboard.writeText(model.workspacePath);toast('Ubicación copiada. Abre esta carpeta en tu agente.');}catch{toast('No se pudo copiar. Selecciona la ubicación visible y cópiala manualmente.');}return;}
 if(b.dataset.copySetup!==undefined){if(!model.workspacePath?.trim()){toast('La ubicación aún no está disponible. Actualiza el estado e inténtalo de nuevo.');return;}try{await navigator.clipboard.writeText(setupAgentPrompt());setupCopiedUntil=Date.now()+2000;clearTimeout(setupCopyTimer);b.textContent='Copiado';setupCopyTimer=setTimeout(()=>{setupCopiedUntil=0;for(const button of new Set([b,...main.querySelectorAll('[data-copy-setup]')]))button.textContent=button.dataset.copyLabel||'Copiar mensaje';},2000);}catch{document.getElementById('setup-message')?.focus();toast('No se pudo copiar. Selecciona el mensaje visible y cópialo manualmente.');}return;}
 if(b.dataset.setupRetry!==undefined){if(await action(setupOperation('ui-setup-retry'))){render();toast('Avance conservado. Copia el mensaje de inicio y envíalo en el nuevo chat.');}return;}
 if(b.dataset.setupFinish){if(await action(setupOperation('ui-setup-finish')))await setScreen(b.dataset.setupFinish);return;}
 if(b.dataset.saveProfile!==undefined){await saveProfileChanges();return;}
 if(b.dataset.moreActivity){activityDayLimit+=7;render(true);return;}
 if(b.dataset.searchOffers){await openSearchOffers();return;}
 if(b.dataset.copyAgentCommand){b.disabled=true;try{await saveVisibleChangesAndCopy();}finally{b.disabled=false;}return;}
 if(b.dataset.clearPlatforms!==undefined){const form=b.closest('form[data-form="sources"]');form.elements.namedItem('platforms').value='';syncSourceControls(form);rememberForm(form);return;}
 if(b.dataset.followupCheck){
  if(await action({kind:'ui-request',type:'investigate',purpose:'followup',opportunityId:b.dataset.followupCheck})){toast('Comprobación guardada para el agente; aún no ha consultado el portal.');render(true);}return;
 }
 if(b.dataset.investigate){
   if(await action({kind:'ui-request',type:'investigate',opportunityId:b.dataset.investigate})){toast('Comprobación guardada para el agente.');render(true);}
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
 if(b.dataset.settingsTarget){const target=document.getElementById(b.dataset.settingsTarget);target?.scrollIntoView({block:'start',behavior:'smooth'});(target?.querySelector('input,textarea,select')||target)?.focus({preventScroll:true});return;}
 if(b.dataset.screen){if(b.dataset.screen==='encontrar'&&screen!=='encontrar')findReturn=screen;if(b.dataset.screen==='actividad'&&screen!=='actividad')auxReturn=screen;setScreen(b.dataset.screen);return;}if(b.dataset.job){if(b.tagName==='A')e.preventDefault();if([...flowScreens,'historial','encontrar'].includes(screen))caseReturn=screen;await setScreen('detalle',b.dataset.job,true,null,b.dataset.cvKey?b:null);return;}if(b.dataset.answers){setScreen('perfil',b.dataset.answers);return;}if(b.dataset.edit){setScreen('editar',b.dataset.edit);return;}
 if(b.dataset.review){setScreen('revisar',b.dataset.review);return;}
 b.disabled=true;
 if(b.dataset.approve){
   const j=reviewSnapshot;
   if(!j||j.id!==b.dataset.approve||!UI.reviewValid(j,getJob(j.id)))throw new Error('El envío necesita revisarse de nuevo.');
   if(await action({kind:'ui-approve',opportunityId:j.id,fingerprint:j.fingerprint})){
     toast('Permiso guardado. El envío aún no está confirmado.');setScreen('detalle',j.id);
   }
 }
 if(b.dataset.revoke&&await action({kind:'ui-revoke',packageId:b.dataset.revoke})){toast('Permiso retirado. Si había un envío iniciado, su resultado debe comprobarse.');render();}
 if(b.dataset.cancel&&await action({kind:'ui-request-update',id:b.dataset.cancel,status:'cancelled',proof:'Cancelado por el usuario desde la aplicación.'})){toast('Encargo cancelado.');render();}
 if(b.dataset.retry&&await action({kind:'ui-request-update',id:b.dataset.retry,status:'queued',proof:'El usuario solicita reintentar; comprobar lo ocurrido antes de repetir una acción externa.'})){toast('El agente comprobará dónde continuar.');render();}
 if(b.dataset.seen&&await action({kind:'ui-seen',at:new Date().toISOString()})){toast('Novedades marcadas como vistas. Las tareas siguen pendientes.');render();}
 if(b.dataset.undo&&await action({kind:'ui-undo',id:Number(b.dataset.undo)})){toast('Cambio deshecho.');render(true);}
 if(b.dataset.inherit&&await action({kind:'ui-inherit',opportunityId:selected,expected:getJob(selected).answerOverrides})){draftStorage.removeItem(draftKey());dirty=false;toast('Esta solicitud vuelve a usar tus respuestas generales.');render();}
 const formConflict=controlForm(b)?._conflict;
 if(b.dataset.current&&formConflict){const op=formConflict.operation,info=formFeedback(controlForm(b),'.form-info');if(!info)return;if(op.kind==='ui-experience'){info.textContent='Experiencia actual: '+model.experience;return;}const target=conflictTarget(op);info.textContent='Valores actuales: '+Object.keys(op.values).map(k=>(model.labels[k]||k)+': '+answerText(target[k])).join(' · ');}
 if(b.dataset.keep&&formConflict&&await confirmAction('Guardar tus valores','Sustituirá los campos indicados por tus respuestas actuales. Los demás datos se conservarán.')){
   const form=controlForm(b);if(!form)return;rememberForm(form);if(form.reportValidity&&!form.reportValidity())return;const key=draftKey(form),values=formValues(form),op=structuredClone(formConflict.operation),target=conflictTarget(op);
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
main.addEventListener('input',e=>{
 if(e.target.dataset.autoGrow)growField(e.target);
 if(e.target.dataset.permitOther!==undefined)return;
 if(e.target.dataset.permitOption!==undefined){saveWorkAuthorizationChoices(e.target.closest('[data-work-authorizations]'));return;}
 if(e.target.dataset.tableOptionSearch!==undefined)return;
 const groupForm=e.target.form?.dataset?.bulkForm?e.target.form:e.target.closest?.('form[data-bulk-form]');
 if(groupForm?.dataset?.bulkForm&&bulkEditor){const type=bulkEditorFields().find(f=>f.name===e.target.name)?.definition.type,value=e.target.value;bulkEditor.values[e.target.name]=value===''?null:type==='boolean'?value==='true':type==='number'?Number(value):value;draftStorage.setItem(bulkEditor.draftKey,JSON.stringify({fingerprints:bulkEditor.fingerprints,values:bulkEditor.values}));dirty=true;return;}
 const form=controlForm(e.target);
 if(form){if(['currency','salaryCurrency'].includes(e.target.name)){e.target.value=e.target.value.toUpperCase();syncSalaryCurrency(form);}form._lastEditedField=e.target.name;rememberForm(form);}
});
main.addEventListener('toggle',e=>{const card=e.target;if(card.tagName!=='DETAILS'||!card.dataset.cvKey||!main.contains(card))return;if(card.open)openCvCards.add(card.dataset.cvKey);else openCvCards.delete(card.dataset.cvKey);},true);
main.addEventListener('scroll',e=>{if(e.target.classList?.contains('workflow-table-wrap')&&openFilterMenu)requestAnimationFrame(()=>placeColumnMenu(openFilterMenu));},true);
main.addEventListener('keydown',e=>{if(e.target.dataset.permitOther!==undefined&&e.key==='Enter'){e.preventDefault();e.target.closest('[data-work-authorizations]').querySelector('[data-permit-add]').click();return;}const row=e.target.closest('[data-job-row]');if(row&&e.target===row&&['Enter',' '].includes(e.key)){e.preventDefault();caseReturn=screen;setScreen('detalle',row.dataset.jobRow);}});
async function importCv(file){
 if(!file||saving||profileSaving)return;
 if(file.size>10000000){toast('El PDF puede ocupar hasta 10 MB.');return;}
 rememberAllForms();saving=true;syncDirty();mutationSerial++;
 try{
  const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('No se pudo leer el PDF. Vuelve a elegirlo.'));reader.readAsDataURL(file);});
  const result=await api('/api/import-cv',{name:file.name,content});
  if(!result.state||!Array.isArray(result.state.opportunities))throw new Error('No se pudo confirmar el guardado del PDF. Actualiza el estado para comprobarlo.');
  rememberAllForms();acceptState(result.state);stateVersion=null;
  saving=false;render(true);toast('CV añadido.');
 }catch(error){toast(error.message||'No se pudo guardar el PDF.');}
 finally{saving=false;mutationSerial++;syncDirty();for(const form of visibleForms())updateSave(form);}
}
main.addEventListener('change',async e=>{
 if(e.target.dataset.searchProfile!==undefined){await chooseSearchProfile(e.target.value);return;}
 if(e.target.dataset.offerProfile!==undefined){offerProfileFilter=e.target.value;workspaceSession.setItem('stubbs_jobs-offer-profile',offerProfileFilter);tableSelection.clear();historyLimit=100;render(true);return;}
 if(e.target.dataset.tableValue!==undefined)return;
 if(e.target.id==='cv-upload'){await importCv(e.target.files[0]);return;}const form=controlForm(e.target);if(form){form._lastEditedField=e.target.name;rememberForm(form);}});
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
 if(form.reportValidity&&!form.reportValidity())return false;
 const key=draftKey(form),stored=JSON.parse(draftStorage.getItem(key)||'{}'),values=formValues(form),kind=form.dataset.form;
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
 if(op.values&&kind!=='new'){op.values=changedFormValues(form,values);op.expected=Object.fromEntries(Object.keys(op.values).map(k=>[k,form._expected[k]??null]));if(!Object.keys(op.values).length&&!stored.attempt){draftStorage.removeItem(key);form._dirty=false;syncDirty();const info=form.querySelector('.form-info');if(info)info.textContent='';updateSave(form);if(!deferRender)toast('Sin cambios.');return true;}}
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
 for(const form of forms)if(form.reportValidity&&!form.reportValidity())return false;
 const focusSave=document.activeElement?.dataset?.saveProfile!==undefined;
 let saved=0,failed=null;
 profileSaving=true;syncDirty();
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
  (card||failed).scrollIntoView?.({block:'center',behavior:'smooth'});
  toast((saved?`Se ${saved===1?'guardó una sección':'guardaron '+saved+' secciones'}. `:'')+`Revisa «${label}». Los cambios pendientes se conservan.`,saved?lastUserUndo()?.id:null);
  return false;
 }
 if(dirty){toast('Hay ediciones nuevas pendientes de guardar.',lastUserUndo()?.id);return false;}
 render(true);if(focusSave)main.focus?.({preventScroll:true});changeToast('Cambios guardados.');return true;
}
async function saveVisibleChangesAndCopy(){
 const work=window.StubbsJobsActivity.work(model);
 if(!work.queued.length&&(!String(model.searchContext?.targetRoles||'').trim()||!String(model.preferences?.location||'').trim())){
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
window.addEventListener('beforeunload',event=>{if(dirty)rememberAllForms();viewMemory[screen+'/'+(selected||'')]={filterText,...viewScroll(),focus:captureFocus(),limit:historyLimit,activityDays:activityDayLimit};workspaceSession.setItem('stubbs_jobs-views',JSON.stringify(viewMemory));if(saving||profileSaving||actionBusy||dirty&&storageProblem){event.preventDefault();event.returnValue='';}});
window.addEventListener('scroll',()=>{if(openFilterMenu)requestAnimationFrame(()=>placeColumnMenu(openFilterMenu));if(screen==='perfil'&&!selected)requestAnimationFrame(updateProfileSection);},{passive:true});
window.addEventListener('resize',()=>{closeColumnMenu();syncOfferToolbar();syncCvCardLayout();if(screen==='perfil'&&!selected)requestAnimationFrame(updateProfileSection);});
async function start(){const key=new URLSearchParams(location.hash.slice(1)).get('key');if(key){await api('/api/session',{key});window.history.replaceState(null,'',location.pathname);}else if(flowScreens.includes(location.hash.slice(1)))window.history.replaceState(null,'',location.pathname);await refresh(true);await route();clearTimeout(pollTimer);pollTimer=setTimeout(poll,6000);}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh(true);});
window.addEventListener('hashchange',()=>{if(location.hash.includes('key='))start().catch(e=>{connection.textContent=e.message;});else route().catch(e=>{connection.textContent=e.message;});});
start().catch(error=>{connection.textContent=error.message;main.innerHTML='<div class="empty">Vuelve a abrir Stubbs Jobs desde el acceso de su carpeta.</div>';});
})();
