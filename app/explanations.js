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
function work(model,{getJob,esc,date,conciseText}){
 const work=Workflow.work(model);
 if(!work.busy&&!work.blocked.length&&!work.failure)return '';
 const company=request=>request.opportunityId?getJob(request.opportunityId)?.company:'';
 const task=request=>[Workflow.names[request.type]||'Trabajo guardado',company(request)].filter(Boolean).join(' · ');
 const waiting=work.queued.length?`${work.queued.length} ${work.queued.length===1?'tarea pendiente de iniciar':'tareas pendientes de iniciar'}`:'';
 const running=work.running[0],unconfirmed=work.unconfirmed.length&&work.unconfirmed.length===work.running.length;
 const ongoing={discovery:'Buscando ofertas',review:'Revisando solicitud',investigate:'Comprobando oferta',change:'Aplicando tus cambios',send:'Enviando solicitud'};
 const title=unconfirmed?'Actividad pendiente de confirmar':work.starting?'El agente se está iniciando':work.busy?running?[ongoing[running.type]||'El agente está trabajando',company(running)].filter(Boolean).join(' · '):'El agente está trabajando':work.blocked.length||work.failure?work.blocked.some(r=>r.actionOwner==='user')?work.blocked.some(r=>r.actionOwner==='agent')?'Acciones pendientes':'Necesita tu ayuda':'Comprobaciones pendientes del agente':waiting;
 const at=running&&Workflow.taskAt(running)||model.execution?.updatedAt;
 const detail=unconfirmed?'Vuelve al chat del agente para comprobar el último paso.':work.busy?[at?'Último registro: '+date(at):'',waiting].filter(Boolean).join(' · '):work.blocked.length?waiting:work.failure?[model.execution.message,waiting].filter(Boolean).join(' · '):'Guardado para el agente. Para iniciar este trabajo, pídele que continúe en su chat.';
 const rows=[...work.blocked,...work.unconfirmed].map(request=>{
  const state=Workflow.task(request),action=state.delivery||state.stale?`data-copy-recovery="${esc(request.id)}"`:request.opportunityId?`data-job="${esc(request.opportunityId)}"`:'';
  const label=state.deliveryRecheckRequired?'Copiar petición para comprobar de nuevo':state.deliveryChecked?'Copiar petición para continuar':state.delivery?'Copiar petición de comprobación':state.stale?'Copiar petición para retomar':request.opportunityId?'Ver oferta':'Ver qué falta';
  return `<li><div><strong>${esc(task(request))}</strong>${request.actionOwner?`<small>${request.actionOwner==='user'?'Necesita una acción tuya':'Pendiente del agente'}</small>`:''}<p>${esc(conciseText(state.detail,240))}</p>${state.lastAt?`<small>Último registro: ${date(state.lastAt)}</small>`:''}${!action?'<p class="helper">Resuélvelo en el chat del agente.</p>':''}</div>${action?`<button class="link-button" ${action}>${label} ${icon('arrow-right')}</button>`:''}</li>`;
 }).join('');
 const button=work.failure?'<p class="helper">Vuelve al chat del agente para revisar este problema.</p>':'';
 return `<section class="activity-work" data-state="${unconfirmed?'unconfirmed':work.busy?'running':'blocked'}" aria-label="Trabajo pendiente"><div class="activity-work-heading"><div><h2>${esc(title)}</h2>${detail?`<p>${esc(detail)}</p>`:''}</div>${button}</div>${rows?`<ul class="activity-work-blockers">${rows}</ul>`:''}</section>`;
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
function assessment(job,{esc}){
 if(job.archivedAt||job.archiveOutcome==='achieved'||['Cerrada','Rechazada','Descartada','Lograda','Oferta'].includes(job.state))return '';
 const assessment=job.assessment;
 if(!assessment)return '';
 if(!assessment.isCurrent)return '<section class="case-section offer-assessment"><h2>Encaje contigo</h2><p>Esta valoración necesita actualizarse porque han cambiado la oferta, tus preferencias o tu experiencia.</p></section>';
 const summary=assessmentSummary(job);
 if(!summary)return '';
 const urls=[...new Set(sourceDetails(job).references.map(reference=>reference.url).filter(url=>/^https?:\/\//i.test(url||'')))];
 const sources=urls.map((url,index)=>`<a href="${esc(url)}" target="_blank" rel="noopener"${index?` aria-label="Fuente consultada ${index+1}"`:''}>${index?`fuente ${index+1}`:'Fuentes consultadas'}</a>`).join(', ');
 const at=assessment.observedAt||assessment.at;
 const stamp=at&&!Number.isNaN(Date.parse(at))?new Intl.DateTimeFormat('es-ES',{dateStyle:'medium',timeStyle:'short'}).format(new Date(at)):'';
 const consulted=sources||(assessment.observedAt?'Fuentes consultadas':'');
 const stampText=stamp?assessment.observedAt?`${consulted?': ':''}${esc(stamp)}`:`${consulted?' · ':''}Valoración registrada: ${esc(stamp)}`:'';
 return `<section class="case-section offer-assessment"><h2>Encaje contigo</h2><p>${esc(summary)}</p>${consulted||stamp?`<p class="helper">${consulted}${stampText}</p>`:''}${assessment.fresh===false?'<p class="helper">Consulta antigua: el agente debe comprobar de nuevo la disponibilidad antes de solicitar.</p>':''}</section>`;
}
function recovery(model,backupResult,{esc,pendingDrafts=[]}){
 const warning=pendingDrafts.length?`<div class="notice" role="status"><p>Hay borradores sin guardar. No se incluirán en la copia y permanecerán en este navegador. Puedes revisarlos y guardarlos primero:</p><ul>${pendingDrafts.map(draft=>`<li>${draft.page?`<button class="link-button" data-backup-draft="${esc(draft.key)}">${esc(draft.label)}</button>`:draft.content?`<details><summary>${esc(draft.label)}</summary><dl>${draft.content.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd class="note-text">${esc(value)}</dd></div>`).join('')}</dl><p>Puedes copiar estos datos y revisarlos con tu agente antes de incorporarlos a Mi perfil. Copiar no los guarda.</p><button class="link-button" data-copy-backup-draft="${esc(draft.key)}">Copiar datos del borrador</button></details>`:esc(draft.label)}</li>`).join('')}</ul></div>`:'';
 return `<section class="backup-content recovery-panel"><h2>Crear una copia</h2><p>Incluye tu perfil, CV, ofertas, solicitudes y sus pruebas guardadas. Conserva una copia fuera de este ordenador para poder recuperarla si falla.</p>${warning}<button data-create-backup="1"${pendingDrafts.length?' data-backup-saved-only="1"':''}>${pendingDrafts.length?'Crear copia de los datos guardados':'Crear copia de seguridad'}</button>${backupResult?`<p>Copia comprobada: ${backupResult.files} archivos · versión de tus datos ${backupResult.revision}.</p><p><a href="${esc(backupResult.download)}&download=1">Descargar copia</a> · <button class="link-button" data-copy-backup="1">Copiar petición para recuperar</button></p><details><summary>Mensaje para recuperar la copia</summary><p class="note-text">${esc(Recovery.backupPrompt(model.workspacePath,backupResult.name))}</p></details>`:''}<h2 class="backup-restore-heading">Recuperar una copia</h2><p class="helper">Para recuperar o actualizar, pide al agente que trabaje en una carpeta aparte y compare los datos antes de sustituir nada. Una copia recuperada requiere volver a revisar y autorizar los envíos pendientes.</p></section>`;
}
const api={work,assessment,sourceDetails,conditionValue,conditionLabels,recovery};
if(typeof module!=='undefined')module.exports=api;else window.StubbsJobsExplanations=api;
})();
