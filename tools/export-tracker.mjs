import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile, FileBlob } from '@oai/artifact-tool';

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Uso: export-tracker.mjs projection.json salida.xlsx');
const data=JSON.parse(await fs.readFile(input,'utf8'));
const wb=Workbook.create();
const names=['Resumen','Oportunidades','Entradas','Evidencias','Actividad','Fuentes','Eventos','Historial previo'];
for(const name of names) wb.worksheets.add(name);
const col=n=>{let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
const columnOf=(headers,name)=>{const index=headers.indexOf(name);if(index<0)throw new Error(`Falta la columna ${name}`);return col(index);};
const safe=v=>typeof v==='string'&&/^[\s\u0000-\u001f]*[=+@-]/.test(v)?"'"+v:v!==null&&typeof v==='object'?JSON.stringify(v):v??null;
const previews=[];

function sheet(name,headers,rows,widths){
 const s=wb.worksheets.getItem(name), end=Math.max(4,rows.length+3), letter=col(headers.length-1);
 s.showGridLines=false;
 s.getRange('A1').values=[[name==='Resumen'?'Búsqueda de empleo · próximas decisiones':name]];
 s.getRange('A2').values=[[`Vista del registro · revisión ${data.revision} · ${data.updatedAt.slice(0,10)}. Actualizar mediante el procedimiento; los cambios externos se detectan.`]];
 s.getRange(`A3:${letter}3`).values=[headers];
 if(rows.length)s.getRange(`A4:${letter}${rows.length+3}`).values=rows.map(r=>headers.map(h=>safe(r[h])));
 s.getRange(`A1:${letter}${end}`).format.font={name:'Arial',size:10,color:'#162232'};
 s.getRange('A1').format.font={name:'Arial',size:17,bold:true,color:'#163A5F'};
 s.getRange(`A3:${letter}3`).format={fill:'#163A5F',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:36,wrapText:true,verticalAlignment:'center'};
 s.getRange(`A4:${letter}${end}`).format.rowHeight=name==='Resumen'?78:64;
 s.getRange(`A4:${letter}${end}`).format.wrapText=true;
 s.getRange(`A4:${letter}${end}`).format.verticalAlignment='center';
 for(let i=0;i<headers.length;i++)s.getRange(`${col(i)}:${col(i)}`).format.columnWidth=widths?.[i]??24;
 s.freezePanes.freezeRows(3);
 if(rows.length)s.tables.add(`A3:${letter}${end}`,true,`Tabla${names.indexOf(name)}`);
 previews.push([name,`A1:${col(Math.min(headers.length,6)-1)}${Math.min(end,9)}`]);
 return s;
}
const opp=data.sheets.Oportunidades;
const events=data.events.map((e,i,all)=>({
 'ID evento':e.id,'Fecha':e.at,'Tipo':e.type,'ID oportunidad':e.opportunityId,'Fuente':e.source,'Familia':e.family,'CV':e.cv,'Huella CV':e.cvHash,
 'Prueba':e.proof,'Minutos':e.minutes,'Primer hito':all.findIndex(x=>x.type===e.type&&x.opportunityId===e.opportunityId)===i?1:0,'Responsable':e.actor,'Cohorte envío':(all.find(x=>x.type==='sent'&&x.opportunityId===e.opportunityId)?.at??e.at).slice(0,7)
}));
sheet('Eventos',['ID evento','Fecha','Tipo','ID oportunidad','Fuente','Familia','CV','Huella CV','Prueba','Minutos','Primer hito','Responsable','Cohorte envío'],events,[25,24,16,27,20,25,40,30,65,12,12,15,18]);
const eventEnd=Math.max(4,events.length+3);
wb.worksheets.getItem('Eventos').getRange(`B4:B${eventEnd}`).setNumberFormat('dd/mm/yyyy hh:mm');
const open=data.blocks.filter(b=>b.status==='open');
const summary=opp.filter(r=>r.Prioridad==='A').map(r=>({'Empresa':r.Empresa,'Puesto':r.Puesto,'Situación':r.Estado,'Siguiente decisión':r['Siguiente paso'],'Pendiente de':open.filter(b=>b.opportunityId===r.ID).map(b=>b.owner).join(', '),'CV preparado':r['CV preparado']}));
if(data.historicalApplications.length||data.historicalReconciliation.expectedCount!=null)
 summary.push({'Empresa':'Historial previo','Puesto':`${data.historicalApplications.length} registros visibles identificados`,'Situación':data.historicalReconciliation.status==='complete'?'Conciliado':'Pendiente','Siguiente decisión':data.historicalReconciliation.status==='complete'?'Consultar antes de repetir solicitudes. Los procesos anteriores no inflan las métricas nuevas.':'Comprobar candidaturas anteriores antes de repetir solicitudes.','Pendiente de':data.historicalReconciliation.status==='complete'?'—':'Agente'});
sheet('Resumen',['Empresa','Puesto','Situación','Siguiente decisión','Pendiente de','CV preparado'],summary,[23,42,25,66,22,40]);
// Preserve declared order and extensions present only in later, migrated rows.
const oh=[...new Set([...(data.opportunityFields||[]),...opp.flatMap(Object.keys)])];
if(!oh.length)oh.push('ID','Empresa','Puesto','Prioridad','Estado','Apta solicitar','Apta aceptar');
const main=sheet('Oportunidades',oh,opp,[27,23,45,13,24,22,20,65,17,55,20,16,16,24,20,20,20,20,22,22,45,32,15,50,27,45,18,50,75]);
const opportunityColumn=name=>columnOf(oh,name);
const opportunityCell=(name,row)=>`${opportunityColumn(name)}${row}`;
if(data.app?.criteria){const labels={'Remoto España':'Ubicación (dato anterior)','Indefinido':'Contrato (dato anterior)','Viajes ≤1/mes':'Viajes (dato anterior)','Fijo ≥32 k€':'Sueldo (indicador anterior)'};main.getRange(`A3:${col(oh.length-1)}3`).values=[oh.map(h=>labels[h]||h)];}
// Eligibility is evaluated once by the shared registry writer for all stores.
// Excel preserves that projection; source/outcome metrics remain recalculable formulas.
for(const name of ['Fecha objetivo','Publicada','Revisada','Fecha candidatura'])if(oh.includes(name)){const c=opportunityColumn(name);main.getRange(`${c}4:${c}${Math.max(4,opp.length+3)}`).setNumberFormat('dd/mm/yyyy');}
for(const name of ['Fijo mín. confirmado','Fijo máx. confirmado'])if(oh.includes(name)){
 const c=opportunityColumn(name);main.getRange(`${c}4:${c}${Math.max(4,opp.length+3)}`).setNumberFormat('#,##0');
 for(let i=0;i<opp.length;i++){
  const currency=opp[i]['Moneda fijo confirmado'];
  if(typeof currency==='string'&&/^[A-Z]{3}$/.test(currency))main.getRange(`${c}${i+4}`).setNumberFormat(`#,##0 "${currency}"`);
 }
}
if(oh.includes('Estado')){const c=opportunityColumn('Estado');main.getRange(`${c}4:${c}${Math.max(4,opp.length+3)}`).dataValidation={rule:{type:'list',values:['Investigar','Preparar','Lista para revisión','Pendiente de ti','Pendiente de Usuario','Pendiente de empresa','Enviada','Entrevista','Oferta','Lograda','Rechazada','Descartada','Cerrada']}};}
for(const name of ['Remoto España','Indefinido','Viajes ≤1/mes','Fijo ≥32 k€'])if(oh.includes(name)){const c=opportunityColumn(name);main.getRange(`${c}4:${c}${Math.max(4,opp.length+3)}`).dataValidation={rule:{type:'list',values:['Sí','No','Pendiente','Contradicción']}};}
const entryRows=data.sheets.Entradas;
const entryHeaders=entryRows.length?[...new Set(entryRows.flatMap(Object.keys))]:['ID entrada','Fuente','Empresa','Puesto','URL','Primera vista','Publicada','Estado'];
for(const name of ['Entradas','Evidencias','Actividad']){
 const rows=data.sheets[name]; const headers=name==='Entradas'?entryHeaders:rows.length?[...new Set(rows.flatMap(Object.keys))]:({Evidencias:['ID oportunidad','Condición','Estado','Texto o motivo','Fuente','Comprobada'],Actividad:['Fecha','ID oportunidad','Acción','Resultado / prueba']}[name]);
 const s=sheet(name,headers,rows,name==='Evidencias'?[28,23,20,75,65,17]:name==='Actividad'?[17,28,32,24,24,40,75,65]:[30,20,25,55,65,17,17,20,28,75,45,20]);
 for(const h of ['Fecha','Primera vista','Publicada','Última publicación','Comprobada'])if(headers.includes(h)&&rows.length){const c=col(headers.indexOf(h));s.getRange(`${c}4:${c}${rows.length+3}`).setNumberFormat('dd/mm/yyyy');}
}
const sourceRows=data.sheets.Fuentes.map(r=>({...r}));
for(const [id,h]of Object.entries(data.sourceHealth)){
 let row=sourceRows.find(r=>r.Fuente===id);
 if(!row){row={'Fuente':id};sourceRows.push(row);}
 Object.assign(row,{'Tipo':h.company,'Cuenta':'Consulta pública','Alertas':'Captación automática','Última revisión':h.checkedAtUtc,'Último éxito':h.lastSuccessUtc,'Error actual':h.errors.join('; ')});
}
// Historical sources remain visible even when no current configuration or check exists.
// Their presence records attribution only; it does not imply access or coverage.
const knownSources=new Set(sourceRows.map(row=>row.Fuente));
for(const source of [...data.events.map(event=>event.source),...data.sheets.Entradas.map(row=>row.Fuente),...opp.map(row=>row.Fuente)]){
 if(typeof source!=='string'||!source.trim()||knownSources.has(source))continue;
 sourceRows.push({'Fuente':source});knownSources.add(source);
}
const sourceHeaders=['Fuente','Tipo','Cuenta','Alertas','Última revisión','Último éxito','Error actual','Anuncios registrados','Duplicados','Oportunidades A','Enviadas','Minutos invertidos','Respuestas (procesos)','Entrevistas (procesos)'];
const sources=sheet('Fuentes',sourceHeaders,sourceRows,[22,27,50,40,23,23,65,18,16,18,16,18,22,22]);
sources.getRange(`E4:F${Math.max(4,sourceRows.length+3)}`).setNumberFormat('dd/mm/yyyy');
sources.getRange(`H4:N${Math.max(4,sourceRows.length+3)}`).format.horizontalAlignment='center';
const inEnd=Math.max(4,data.sheets.Entradas.length+3),opEnd=Math.max(4,opp.length+3);
// Spreadsheet criteria interpret wildcards and compare text without case. Exact
// numeric identities keep original labels and attribution intact in this view.
const sourceKeys=new Map(sourceRows.map((row,index)=>[row.Fuente,index+1]));
function sourceKeyColumn(name,index,rows,sourceOf){
 const column=col(index),s=wb.worksheets.getItem(name);
 const existing=new Set(s.getRange(`A3:${col(index-1)}3`).values[0]);
 let label='Clave fuente (vista)',suffix=2;
 while(existing.has(label))label=`Clave fuente (vista ${suffix++})`;
 s.getRange(`${column}3`).values=[[label]];
 if(rows.length)s.getRange(`${column}4:${column}${rows.length+3}`).values=rows.map(row=>[sourceKeys.get(sourceOf(row))||0]);
 s.getRange(`${column}:${column}`).format.columnWidth=0;
 return column;
}
const entriesSource=sourceKeyColumn('Entradas',entryHeaders.length,entryRows,row=>row.Fuente);
const offersSource=sourceKeyColumn('Oportunidades',oh.length,opp,row=>row.Fuente);
const eventSource=sourceKeyColumn('Eventos',13,events,row=>row.Fuente);
const sourceKey=sourceKeyColumn('Fuentes',sourceHeaders.length,sourceRows,row=>row.Fuente);
for(let i=0;i<sourceRows.length;i++){
 const r=i+4;
 const entriesState=columnOf(entryHeaders,'Estado'),offersPriority=opportunityColumn('Prioridad');
 const key=`${sourceKey}${r}`;
 sources.getRange(`H${r}`).formulas=[[`=COUNTIFS(Entradas!$${entriesSource}$4:$${entriesSource}$${inEnd},${key})`]];
 sources.getRange(`I${r}`).formulas=[[`=COUNTIFS(Entradas!$${entriesSource}$4:$${entriesSource}$${inEnd},${key},Entradas!$${entriesState}$4:$${entriesState}$${inEnd},"Duplicada")`]];
 sources.getRange(`J${r}`).formulas=[[`=COUNTIFS(Oportunidades!$${offersSource}$4:$${offersSource}$${opEnd},${key},Oportunidades!$${offersPriority}$4:$${offersPriority}$${opEnd},"A")`]];
 for(const [c,type]of [['K','sent'],['M','response'],['N','interview']])sources.getRange(`${c}${r}`).formulas=[[`=SUMIFS(Eventos!$K$4:$K$${eventEnd},Eventos!$${eventSource}$4:$${eventSource}$${eventEnd},${key},Eventos!$C$4:$C$${eventEnd},"${type}")`]];
 sources.getRange(`L${r}`).formulas=[[`=IF(COUNTIFS(Eventos!$${eventSource}$4:$${eventSource}$${eventEnd},${key},Eventos!$C$4:$C$${eventEnd},"work")=0,"Sin medir",SUMIFS(Eventos!$J$4:$J$${eventEnd},Eventos!$${eventSource}$4:$${eventSource}$${eventEnd},${key},Eventos!$C$4:$C$${eventEnd},"work"))`]];
}
sheet('Historial previo',['ID','Empresa','Puesto','URL','Estado','Última actividad visible','Categoría','Prueba'],data.historicalApplications.map(h=>({'ID':h.id,'Empresa':h.company,'Puesto':h.title,'URL':h.url,'Estado':h.state,'Última actividad visible':h.lastActivityLabel,'Categoría':h.category,'Prueba':h.proof})),[27,30,52,75,25,25,18,75]);
wb.recalculate();
for(let i=0;i<sourceRows.length;i++){
 const src=sourceRows[i].Fuente;
 const counts={H:data.sheets.Entradas.filter(r=>r.Fuente===src).length,I:data.sheets.Entradas.filter(r=>r.Fuente===src&&r.Estado==='Duplicada').length,J:opp.filter(r=>r.Fuente===src&&r.Prioridad==='A').length};
 for(const [c,expected]of Object.entries(counts))if(sources.getRange(`${c}${i+4}`).values[0][0]!==expected)throw new Error(`Recuento incorrecto: ${src} ${c}`);
 for(const [c,type]of [['K','sent'],['M','response'],['N','interview']]){
   const expected=events.filter(e=>e.Fuente===src&&e.Tipo===type&&e['Primer hito']===1).length;
  if(sources.getRange(`${c}${i+4}`).values[0][0]!==expected)throw new Error(`Métrica incorrecta: ${src} ${type}`);
 }
}
for(let i=0;i<opp.length;i++){
 const apply=main.getRange(`${opportunityColumn('Apta solicitar')}${i+4}`).values[0][0];
 const accept=main.getRange(`${opportunityColumn('Apta aceptar')}${i+4}`).values[0][0];
 if(apply!==opp[i]['Apta solicitar']||accept!==opp[i]['Apta aceptar'])throw new Error(`Discordancia de decisiones: ${opp[i].ID}`);
}
for(const [name,range]of [['Oportunidades',`${opportunityColumn('Apta solicitar')}4:${opportunityColumn('Apta solicitar')}${opEnd}`],['Oportunidades',`${opportunityColumn('Apta aceptar')}4:${opportunityColumn('Apta aceptar')}${opEnd}`],['Fuentes',`H4:N${Math.max(4,sourceRows.length+3)}`]]){
 for(const value of wb.worksheets.getItem(name).getRange(range).values.flat()){
  if(typeof value==='string'&&/^#(REF!|DIV\/0!|VALUE!|NAME\?|NUM!|NULL!|SPILL!|CALC!|N\/A)$/.test(value))throw new Error(`${name}: ${value}`);
 }
}
await fs.mkdir(path.dirname(output),{recursive:true});
await(await SpreadsheetFile.exportXlsx(wb)).save(output);
const reopened=await SpreadsheetFile.importXlsx(await FileBlob.load(output));
const reopenedId=opportunityColumn('ID');
if(reopened.worksheets.getItem('Oportunidades').getRange(`${reopenedId}4:${reopenedId}${opEnd}`).values.flat().join('|')!==opp.map(x=>x.ID).join('|'))throw new Error('Identificadores perdidos al exportar');
const reopenedSources=reopened.worksheets.getItem('Fuentes');
for(let i=0;i<sourceRows.length;i++){
 if(reopenedSources.getRange(`A${i+4}`).values[0][0]!==sources.getRange(`A${i+4}`).values[0][0])throw new Error('Fuente perdida al exportar');
 for(const column of ['H','I','J','K','L','M','N']){
  if(reopenedSources.getRange(`${column}${i+4}`).values[0][0]!==sources.getRange(`${column}${i+4}`).values[0][0])throw new Error(`Recuento alterado al exportar: ${sourceRows[i].Fuente} ${column}`);
 }
}
const qa=path.join(path.dirname(input),'previews');await fs.mkdir(qa,{recursive:true});
for(const [name,range]of previews){const img=await wb.render({sheetName:name,range,scale:1.2,format:'png'});await fs.writeFile(path.join(qa,`${name}.png`),new Uint8Array(await img.arrayBuffer()));}
const metricsImage=await wb.render({sheetName:'Fuentes',range:`H3:N${Math.min(sourceRows.length+3,12)}`,scale:1.2,format:'png'});
await fs.writeFile(path.join(qa,'Metricas.png'),new Uint8Array(await metricsImage.arrayBuffer()));
if(oh.includes('Perfil de búsqueda')&&oh.includes('Búsquedas en que apareció')){
 const range=`${opportunityColumn('Perfil de búsqueda')}3:${opportunityColumn('Búsquedas en que apareció')}${Math.min(opEnd,9)}`;
 const image=await wb.render({sheetName:'Oportunidades',range,scale:1.2,format:'png'});
 await fs.writeFile(path.join(qa,'Perfiles.png'),new Uint8Array(await image.arrayBuffer()));
}
console.log(JSON.stringify({opportunities:opp.length,entries:data.sheets.Entradas.length,events:events.length,formulaChecks:'OK',reopened:true}));
