'use strict';
// Contextual explanations reuse the same task decisions; rendering never writes data.
(() => {
const Workflow=typeof module!=='undefined'?require('./workflow.js'):window.StubbsJobsWorkflow;
const {icon}=typeof module!=='undefined'?require('./icons.js'):window.StubbsJobsIcons;
const Recovery=typeof module!=='undefined'?require('./recovery.js'):window.StubbsJobsRecovery;
const Formatting=typeof module!=='undefined'?require('./formatting.js'):window.StubbsJobsFormatting;
const conditionLabels={country:'País',mode:'Modalidad',contract:'Contrato',schedule:'Horario',salary:'Salario publicado',travel:'Desplazamientos',technology:'Tecnologías',experience:'Experiencia requerida',functions:'Funciones',education:'Formación',languages:'Idiomas',requirements:'Otros requisitos'};
const factParts=text=>String(text||'').split(/\s*;\s*|\n+|(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜ0-9])/u).map(text=>text.trim().replace(/[.!;]+$/u,'')).filter(Boolean);
const factKey=(text,key)=>Formatting.fold(Formatting.tableText(text,key));
function sourceDetails(job){
 const conditions={},references=[];
 const technologyParts=new Set();
 function addPosition(text,declaredKey){
  if(Formatting.tableText(text,declaredKey)==='—')return;
  const labeled=/^(Tecnolog[ií]as|Herramientas|Experiencia(?: requerida)?|Funciones|Responsabilidades|Formaci[oó]n|Idiomas|Requisitos(?: de la oferta| del puesto)?)\s*:\s*(.+)$/iu.exec(text);
  const label=labeled&&Formatting.fold(labeled[1]),value=labeled?labeled[2]:text;
  const explicit=label?/^tecnologias|^herramientas/.test(label)?'technology':/^experiencia/.test(label)?'experience':/^funciones|^responsabilidades/.test(label)?'functions':/^formacion/.test(label)?'education':/^idiomas/.test(label)?'languages':'requirements':null;
  const normalized=Formatting.tableText(value,'technology');
  const key=explicit||(/\b(?:\d+\s*(?:[-–]\s*\d+\s*)?a[nñ]os?|experiencia (?:previa|profesional|en|con)|years?(?: of experience)?)\b/iu.test(value)?'experience':
   technologyParts.has(factKey(normalized,'technology'))||normalized!==value||/^(?:SAP|ABAP|Power BI|Power Query|SQL|DAX|Python|Tableau|S\/4HANA|OData|CDS|Eclipse\/ADT)\b/iu.test(value)?'technology':declaredKey||'requirements');
  (conditions[key]??=[]).push(Formatting.tableText(value,key));
 }
 for(const text of factParts(job.technologies)){
  technologyParts.add(factKey(text,'technology'));
  addPosition(text,'technology');
 }
 const known=new Map();
 for(const key of ['country','mode','contract','schedule','salary']){
  const value=job[{country:'country',mode:'workMode',contract:'contract',schedule:'schedule',salary:'salary'}[key]];
  for(const part of factParts(value))if(Formatting.tableText(part,key)!=='—')known.set(factKey(part,key),key);
 }
 function classify(text){
  for(const key of ['country','mode','contract','schedule','salary'])if(known.get(factKey(text,key))===key)return key;
  const labeled=/^(?:Pa[ií]s|Zona|Ubicaci[oó]n|Modalidad|Contrato|Horario|Jornada|Salario(?: publicado)?|Sueldo|Retribuci[oó]n|Desplazamientos|Viajes)\s*(?::|—|\s+(?=(?:no |sin |pendiente)))\s*(.+)$/iu.exec(text);
  if(labeled){const label=Formatting.fold(text.slice(0,text.indexOf(labeled[1])).replace(/[:—]/g,'').trim());return /^pa[ií]s|^zona|^ubicacion/.test(label)?'country':label.startsWith('modalidad')?'mode':label.startsWith('contrato')?'contract':/^horario|^jornada/.test(label)?'schedule':/^viajes|^desplazamientos/.test(label)?'travel':'salary';}
  for(const [key,values] of [['mode',['Remoto','Híbrido','Presencial']],['contract',['Indefinido','Temporal','Freelance']],['schedule',['Flexible','Jornada completa','Jornada parcial','Jornada intensiva','Turno de mañana','Turno de tarde','Turno de noche']]]){
   if(values.includes(Formatting.tableText(text,key)))return key;
  }
  if(/^\d{1,2}:[0-5]\d\s*[-–—]\s*\d{1,2}:[0-5]\d(?:\s*h)?(?:\s+(?:habitual|verano|invierno))?$/iu.test(text))return 'schedule';
  if(/^(?:no publicado|salario seg[uú]n experiencia)$/iu.test(text))return 'salary';
  if(/^(?:desde |hasta )?[\d€£$]/u.test(text)&&Formatting.salaryInfo(text).kind!=='unknown'&&/[€£$]|\b(?:EUR|USD|GBP)\b/iu.test(text))return 'salary';
  return null;
 }
 function addFact(text){
   const key=classify(text);
   if(!key){addPosition(text);return;}
   const value=text.replace(/^(?:Pa[ií]s|Zona|Ubicaci[oó]n|Modalidad|Contrato|Horario|Jornada|Salario(?: publicado)?|Sueldo|Retribuci[oó]n|Desplazamientos|Viajes)(?:\s*[:—]\s*|\s+(?=no |sin |pendiente))/iu,'');
   (conditions[key]??=[]).push(value);
 }
 for(const text of factParts(job.requirements))addFact(text);
 if(!job.assessment?.isCurrent)return {conditions,references};
 for(const reference of job.assessment.references||[]){
  for(const text of factParts(reference.text))addFact(text);
  references.push({...reference,text:''});
 }
 return {conditions,references};
}
function conditionValue(key,value,details){
 const extra=details.conditions[key]||[];
 const parts=factParts(value),seen=new Set(parts.map(part=>factKey(part,key)));
 const added=extra.filter(text=>Formatting.tableText(text,key)!=='—'&&!seen.has(factKey(text,key)));
 const unique=[...new Map(added.map(text=>[factKey(text,key),Formatting.tableText(text,key)])).values()];
 if(!unique.length)return value;
 const missing=['Sin concretar','Sin desglosar','—'].includes(value);
 return [missing?'':value,...unique].filter(Boolean).join('; ');
}
// Ofertas shows the work that belongs to no single offer (searches, profile tasks)
// and agent failures. Each offer's own stops appear in that offer, under Por atender.
function work(model,{getJob,esc,date,conciseText}){
 const work=Workflow.work(model),general=request=>!request.opportunityId;
 // Help requests and uncertain effects come first. Stops the agent cannot resolve
 // alone follow, each with a way out: another attempt or cancelling the task.
 const stopped=request=>request.actionOwner==='agent'&&!Workflow.task(request).delivery&&request.status!=='interrupted';
 const blocked=[...work.blocked.filter(request=>general(request)&&!stopped(request)),...work.blocked.filter(request=>general(request)&&stopped(request))];
 const unconfirmedRows=work.unconfirmed.filter(general);
 if(!blocked.length&&!unconfirmedRows.length&&!work.failure)return '';
 const profileName=request=>[...(model.searchProfiles||[]),...(model.deletedSearchProfiles||[])].find(p=>p.id===request.searchProfileId)?.name||request.round?.searchProfileName||'';
 const company=request=>request.opportunityId?getJob(request.opportunityId)?.company:'';
 const task=request=>request.type==='discovery'?['Búsqueda',profileName(request)?'«'+profileName(request)+'»':''].filter(Boolean).join(' '):[Workflow.names[request.type]||'Tarea',company(request)].filter(Boolean).join(' · ');
 // One line per task saying what happened; the agent's explanation stays folded.
 const line=(request,state)=>state.delivery?'envío sin confirmar':state.stale?'sin confirmar si sigue en curso':stopped(request)?'se detuvo':request.actionOwner==='user'?'necesita tu ayuda':'detenida';
 const folded=(summary,text,lastAt)=>`<details class="activity-work-detail"><summary>${summary}<span class="activity-work-more">Ver detalle</span></summary>${text?`<p>${esc(conciseText(text,240))}</p>`:''}${lastAt?`<small>Último registro: ${date(lastAt)}</small>`:''}${!text&&!lastAt?'<p>Resuélvelo en el chat del agente.</p>':''}</details>`;
 const rows=[...blocked,...unconfirmedRows].map(request=>{
  const state=Workflow.task(request),action=state.delivery||state.stale?`data-copy-recovery="${esc(request.id)}"`:request.opportunityId?`data-job="${esc(request.opportunityId)}"`:'';
  const label=state.deliveryRecheckRequired?'Copiar petición para comprobar de nuevo':state.deliveryChecked?'Copiar petición para continuar':state.delivery?'Copiar petición de comprobación':state.stale?'Copiar petición para retomar':request.opportunityId?'Ver oferta':'Ver qué falta';
  // Without an offer (a search), the task itself offers the way out.
  const retry=!state.delivery&&!state.stale&&state.canRetry&&request.type!=='send'&&(stopped(request)||!request.opportunityId)?`<button class="link-button" data-retry="${esc(request.id)}">${request.need==='access'?'Ya he completado el acceso':'Pedir otro intento'}</button>`:'';
  const cancel=!request.opportunityId&&state.canCancel?`<button class="link-button" data-cancel="${esc(request.id)}">Cancelar ${request.type==='discovery'?'búsqueda':'tarea'}</button>`:'';
  const buttons=[retry,action?`<button class="link-button" ${action}>${label} ${icon('arrow-right')}</button>`:'',cancel].filter(Boolean).join('');
  return `<li>${folded(`<strong>${esc(task(request))}</strong> <span>${esc(line(request,state))}</span>`,state.detail,state.lastAt)}${buttons?`<div class="activity-work-actions">${buttons}</div>`:''}</li>`;
 }).join('');
 const unconfirmed=unconfirmedRows.length&&!blocked.length;
 const failure=!rows&&work.failure?`<li>${folded('<strong>El agente se detuvo</strong>',[work.failure.message,'Vuelve al chat del agente para revisarlo.'].filter(Boolean).join(' '),null)}</li>`:'';
 return `<section class="activity-work" data-state="${unconfirmed?'unconfirmed':'blocked'}" aria-label="Tareas del agente sin oferta"><ul class="activity-work-blockers">${rows||failure}</ul></section>`;
}
function assessmentSummary(job){
 // Legacy copy can contain routine context. Remove only complete, known repetitions;
 // a word such as "contrato" or "remoto" must never hide a meaningful qualification.
 const state=/^(?:la\s+)?(?:candidatura|solicitud)\s+(?:ya\s+)?(?:est[aá]\s+)?(?:enviada|presentada)(?:\s+ya)?[.!]?$/iu;
 const genericCondition=/^(?:(?:la\s+)?banda publicada no confirma (?:la\s+)?parte fija(?: ni (?:el\s+)?contrato indefinido)?|(?:(?:el\s+)?(?:sueldo|salario|contrato(?: indefinido)?|fijo|horario|viajes|desplazamientos|presencialidad))(?:,? (?:y |ni )?(?:sueldo|salario|contrato(?: indefinido)?|fijo|horario|viajes|desplazamientos|presencialidad))* (?:todav[ií]a no publicados?|sin (?:confirmar|concretar|publicar)|pendientes?(?: de confirmar)?))$/iu;
 const parts=(job.assessment?.reason||'').trim().split(/(?<=[.!?;])\s+/u);
 const kept=parts.map((text,index)=>({text:text.trim(),index})).filter(({text})=>{
  const clause=text.replace(/[.!?;]$/u,'');
  return clause&&!state.test(clause)&&!genericCondition.test(clause);
 });
 return kept.map(({text,index},position)=>{
  const previous=kept[position-1];
  if(!previous||previous.index!==index-1||/[.!?]$/u.test(previous.text))text=text[0].toLocaleUpperCase('es')+text.slice(1);
  if(text.endsWith(';')&&kept[position+1]?.index!==index+1)text=text.slice(0,-1)+'.';
  return text;
 }).join(' ');
}
function assessment(job,{esc,basis=''}){
 if(job.archivedAt||job.archiveOutcome==='achieved'||['Cerrada','Rechazada','Descartada','Lograda','Oferta'].includes(job.state))return '';
 const assessment=job.assessment;
 if(!assessment)return '';
 const basisLine=basis?`<p class="helper offer-criteria-basis">${esc(basis)}</p>`:'';
 if(!assessment.isCurrent)return `<section class="case-section offer-assessment"><h2>Encaje contigo</h2><p>Valoración pendiente de actualizar: desde entonces cambió la oferta o tu perfil.</p>${basisLine}</section>`;
 const summary=assessmentSummary(job);
 if(!summary)return '';
 const urls=[...new Set(sourceDetails(job).references.map(reference=>reference.url).filter(url=>/^https?:\/\//i.test(url||'')))];
 // One line: when it was checked, where, and with which search profile.
 const link=(url,label,aria='')=>`<a href="${esc(url)}" target="_blank" rel="noopener"${aria?` aria-label="${aria}"`:''}>${label}</a>`;
 const sources=urls.length===1?link(urls[0],'Ver fuente'):urls.length?'Fuentes: '+urls.map((url,index)=>link(url,index+1,'Fuente '+(index+1))).join(', '):'';
 const at=assessment.observedAt||assessment.at;
 const stamp=at&&!Number.isNaN(Date.parse(at))?new Intl.DateTimeFormat('es-ES',{dateStyle:'medium'}).format(new Date(at)):'';
 const line=[stamp?esc((assessment.observedAt?'Comprobado el ':'Valorado el ')+stamp):'',sources,esc(basis)].filter(Boolean).join(' · ');
 return `<section class="case-section offer-assessment"><h2>Encaje contigo</h2><p>${esc(summary)}</p>${line?`<p class="helper offer-criteria-basis">${line}</p>`:''}${assessment.fresh===false?'<p class="helper">Comprobación antigua: el agente volverá a mirar si la oferta sigue abierta antes de solicitar.</p>':''}</section>`;
}
function recovery(model,backupResult,{esc,pendingDrafts=[]}){
 const warning=pendingDrafts.length?`<div class="notice" role="status"><p>Hay borradores sin guardar. No se incluirán en la copia y permanecerán en este navegador. Puedes revisarlos y guardarlos primero:</p><ul>${pendingDrafts.map(draft=>`<li>${draft.page?`<button class="link-button" data-backup-draft="${esc(draft.key)}">${esc(draft.label)}</button>`:draft.content?`<details><summary>${esc(draft.label)}</summary><dl>${draft.content.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd class="note-text">${esc(value)}</dd></div>`).join('')}</dl><p>Puedes copiar estos datos y revisarlos con tu agente antes de incorporarlos a Mi perfil. Copiar no los guarda.</p><button class="link-button" data-copy-backup-draft="${esc(draft.key)}">Copiar datos del borrador</button></details>`:esc(draft.label)}</li>`).join('')}</ul></div>`:'';
 return `<section class="backup-content recovery-panel"><h2>Crear una copia</h2><p>Incluye tu perfil, CV, ofertas, solicitudes y sus pruebas guardadas. Conserva una copia fuera de este ordenador para poder recuperarla si falla.</p>${warning}<button data-create-backup="1"${pendingDrafts.length?' data-backup-saved-only="1"':''}>${pendingDrafts.length?'Crear copia de los datos guardados':'Crear copia de seguridad'}</button>${backupResult?`<p>Copia comprobada: ${backupResult.files} archivos · versión de tus datos ${backupResult.revision}.</p><p><a href="${esc(backupResult.download)}&download=1">Descargar copia</a> · <button class="link-button" data-copy-backup="1">Copiar petición para recuperar</button></p><details><summary>Mensaje para recuperar la copia</summary><p class="note-text">${esc(Recovery.backupPrompt(model.workspacePath,backupResult.name))}</p></details>`:''}<h2 class="backup-restore-heading">Recuperar una copia</h2><p class="helper">Para recuperar o actualizar, pide al agente que trabaje en una carpeta aparte y compare los datos antes de sustituir nada. Una copia recuperada requiere volver a revisar y autorizar los envíos pendientes.</p></section>`;
}
const api={work,assessment,sourceDetails,conditionValue,conditionLabels,recovery};
if(typeof module!=='undefined')module.exports=api;else window.StubbsJobsExplanations=api;
})();
