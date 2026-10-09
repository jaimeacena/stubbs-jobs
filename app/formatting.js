'use strict';
// Deterministic display values shared by sorting, filters and table cells.
(() => {
const fold=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es');
const cleanText=value=>String(value??'').trim().replace(/\s+/gu,' ');
const missingText=/^(?:[-—–]|n\/?a|no (?:publicad[oa]|especificad[oa]|concretad[oa]|indicad[oa])(?: en el anuncio)?|sin (?:dato|datos|publicar|especificar|concretar|confirmar|comprobar)|pendiente(?: de confirmar)?|por confirmar|unknown|not (?:specified|published|disclosed))$/i;
const aliases={
 mode:{'Remoto':['100% remoto','100 % remoto','Remoto 100%','Remoto 100 %','Remoto (100%)','Remoto al 100 %','Remoto al 100%','Trabajo remoto','En remoto','Teletrabajo','100% teletrabajo','Teletrabajo 100%','Totalmente remoto','Remote','Fully remote','Full remote','100% remote'],
       'Híbrido':['Hibrido','Hybrid'],'Presencial':['On-site','Onsite','On site','In person']},
 contract:{'Indefinido':['Contrato indefinido','Permanent','Permanent contract','Permanente'],
           'Temporal':['Contrato temporal','Fixed-term','Fixed term','Temporary'],
           'Freelance':['Autónomo','Autonomo','Autónoma','Autonoma','Self-employed']},
 country:{'España':['Spain','ES'],'Polonia':['Poland','PL'],'Portugal':['PT'],'Francia':['France','FR'],
          'Alemania':['Germany','DE'],'Italia':['Italy','IT'],'Irlanda':['Ireland','IE'],
          'Reino Unido':['United Kingdom','UK','GB'],'Estados Unidos':['United States','USA','US','EE. UU.','EEUU'],
          'Canadá':['Canada','CA'],'Unión Europea':['Union Europea','European Union','UE','EU'],
          'Europa':['Europe'],'Global':['Worldwide','Mundial','Todo el mundo'],
          'Latinoamérica':['Latinoamerica','Latin America','LATAM']},
 schedule:{'Flexible':['Horario flexible','Flexible schedule','Flexible hours'],
           'Jornada completa':['Full-time','Full time'],'Jornada parcial':['Part-time','Part time'],
           'Jornada intensiva':['Jornada continua'],'Turno de mañana':['Mañana','Morning shift'],
           'Turno de tarde':['Tarde','Afternoon shift'],'Turno de noche':['Noche','Night shift']},
 technology:{'Power BI':['PowerBI','Microsoft Power BI','MS Power BI'],'Power Query':['PowerQuery'],
             'Power Automate':['PowerAutomate','Microsoft Power Automate'],'SQL':[],'DAX':[],
             'SAP ABAP':['ABAP'],'SAP PM':[],'S/4HANA':['SAP S/4HANA'],'OData':[],'CDS':[],
             'Eclipse/ADT':['Eclipse / ADT'],'Python':[],'Tableau':[],'Microsoft Fabric':['MS Fabric'],
             'Azure Data Factory':[],'Azure Databricks':[]}
};
const aliasMaps=Object.fromEntries(Object.entries(aliases).map(([key,groups])=>[key,new Map(Object.entries(groups).flatMap(([label,values])=>[label,...values].map(value=>[fold(value),label])))]));
function tableText(value,key){
 const text=cleanText(value);
 if(!text||missingText.test(text))return '—';
 const alias=aliasMaps[key]?.get(fold(text));if(alias)return alias;
 if(key==='country'&&/[;,]/.test(text)){
  // Multiple countries remain a multiple-country scope, independent of their written order.
  return [...new Set(text.split(/[;,]/).map(part=>tableText(part,'country')))].sort((a,b)=>a.localeCompare(b,'es')).join('; ');
 }
 if(key==='schedule')return text.replace(/\b([01]?\d|2[0-3]):([0-5]\d)\s*(?:h\s*)?[-–—]\s*([01]?\d|2[0-3]):([0-5]\d)(?:\s*h\b)?/gi,(_,h1,m1,h2,m2)=>`${h1.padStart(2,'0')}:${m1}–${h2.padStart(2,'0')}:${m2}`);
 // Only complete aliases are equivalent. Qualifiers, alternatives and uncertainty keep their meaning.
 return text;
}
const currencyCodes=new Set('EUR USD GBP CAD CHF AUD JPY CNY HKD SGD NZD INR KRW MXN BRL ARS CLP COP PEN UYU RUB NOK SEK DKK PLN CZK HUF RON TRY AED SAR QAR ILS ZAR THB MYR IDR PHP VND TWD BTC XBT ETH USDT'.split(' '));
if(typeof Intl.supportedValuesOf==='function')Intl.supportedValuesOf('currency').forEach(code=>currencyCodes.add(code));
function publishedCurrency(raw,fallback){
 const found=new Set([...raw.matchAll(/(?:^|[^a-z]|\d+k)([a-z]{3,4})(?![a-z])/gi)].map(match=>match[1].toUpperCase()).filter(code=>currencyCodes.has(code)));
 if(/€|\beuros?\b/i.test(raw))found.add('EUR');
 if(/£/u.test(raw))found.add('GBP');
 if(/US\$/i.test(raw))found.add('USD');
 const symbols=raw.match(/\p{Sc}/gu)||[];
 const uncertainSymbol=symbols.some(symbol=>!['€','£','$'].includes(symbol)||symbol==='$'&&!found.has('USD'))||/(?:^|[^a-z])(?:CA?|AU?|NZ|HK|SG?|NT)\$/i.test(raw);
 const otherDollars=/\b(?:d[oó]lares?|dollars?)\s+(?:canadienses?|australianos?|neozelandeses?|de\s+(?:Canad[aá]|Australia|Nueva\s+Zelanda|Singapur|Hong\s+Kong))\b|\b(?:Canadian|Australian|New\s+Zealand|Singapore|Hong\s+Kong)\s+dollars?\b/i.test(raw);
 const uncertainName=otherDollars||/\b(?:yen(?:es)?|yuan(?:es)?|francos?|francs?|rupias?|rupees?|pesos?|reales?|rublos?|rubles?|won)\b/i.test(raw)||/\b(?:d[oó]lares?|dollars?)\b/i.test(raw)&&!found.has('USD')||/\b(?:pounds?|libras?)\b/i.test(raw)&&!found.has('GBP');
 if(found.size>1||uncertainSymbol||uncertainName)return null;
 const currency=[...found][0];
 return currency&&!['EUR','USD','GBP'].includes(currency)?null:currency||fallback||'EUR';
}
function salaryNumber(value,options={}){
 const info=salaryInfo(value,options);return ['range','point','floor'].includes(info.kind)?info.low:null;
}
function salaryInfo(value,options={}){
 const raw=String(value||'').trim();
 if(!raw||/^(No publicado|Pendiente)$/i.test(raw))return {kind:'missing',label:'—',raw};
 const currency=publishedCurrency(raw,options.currency);
 const nonAnnual=/\b(?:mensual(?:es)?|semanal(?:es)?|diari[oa]s?|quincenal(?:es)?|trimestral(?:es)?|semestral(?:es)?|monthly|weekly|daily|hourly|fortnightly)\b|(?:\/\s*|\bpor\s+|\bal\s+|\bper\s+|\beach\s+|\ba\s+|\ban\s+)(?:horas?|mes|semana|d[ií]a|quincena|trimestre|semestre|hours?|month|week|day|hr|mo|h)\b/i.test(raw);
 if(currency===null||nonAnnual)return {kind:'unknown',label:raw,raw,note:'Sin cifra anual comparable'};
 const suffix=currency==='EUR'?'€':currency;
 const format=n=>new Intl.NumberFormat('es-ES',{maximumFractionDigits:0}).format(n);
 const token='(?:\\d{1,3}(?:[.,]\\d{3})+|\\d+(?:[.,]\\d+)?)';
 const money='(?:EUR|USD|GBP|euros?|pounds?|€|£|US\\$|\\$)';
 const range=new RegExp(`(${token})\\s*(k)?\\s*(?:${money}\\s*)?(?:[-–—−]|\\b(?:a|y|to|and)\\b)\\s*(?:${money}\\s*)?(${token})\\s*(k)?`,'i').exec(raw);
 const single=new RegExp(`(${token})\\s*(k)?`,'i').exec(raw);
 const amount=(text,k)=>{const number=k?Number(text.replace(',','.'))*1000:Number(text.replace(/[.,]/g,''));return Number.isFinite(number)&&number>=1000?Math.round(number):null;};
 // A single k can describe both small endpoints (35–45k). Full amounts
 // retain their own unit (40000–50k), independent of currency or spacing.
 const unit=(text,k)=>k||range&&(range[2]||range[4])&&
  !/^\d{1,3}(?:[.,]\d{3})+$/.test(text)&&Number(text.replace(',','.'))<1000;
 let low=range?amount(range[1],unit(range[1],range[2])):single?amount(single[1],single[2]):null;
 let high=range?amount(range[3],unit(range[3],range[4])):low;
 if(low!==null&&high!==null&&low>high)[low,high]=[high,low];
 if(low===null||high===null)return {kind:'unknown',label:raw,raw,note:'Sin cifra anual comparable'};
 let kind=range&&low!==high?'range':'point';
 // A limit on a later bonus must not change the first published amount.
 const prefix=raw.slice(0,(range||single).index);
 if(/\b(?:hasta|up to|at most)\b/i.test(prefix)){kind='ceiling';low=null;}
 else if(/\b(?:desde|a partir de|from|starting at)\b/i.test(prefix)&&!range){kind='floor';high=null;}
 if(/\bcontradic/i.test(raw))kind='ambiguous';
 const label=kind==='ceiling'?`Hasta ${format(high)} ${suffix}`:kind==='floor'?`Desde ${format(low)} ${suffix}`:low===high?`${format(low)} ${suffix}`:`${format(low)}–${format(high)} ${suffix}`;
 const note=kind==='ambiguous'?'Cifras contradictorias':kind==='unknown'?'Sin cifra anual comparable':kind==='ceiling'?'Mínimo desconocido':kind==='floor'?'Máximo desconocido':/fijo sin especificar|fijo por confirmar|fijo sin confirmar/i.test(raw)?'Fijo sin confirmar':/tipo de compensaci[oó]n por confirmar/i.test(raw)?'Compensación sin confirmar':/variable/i.test(raw)?'Incluye variable':'';
 return {kind,label:kind==='unknown'?raw:label,raw,low,high,currency,note};
}

function tableTimestamp(value){
 if(typeof value!=='string'||!value)return null;
 const match=/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?$/.exec(value);
 if(!match)return null;
 const [year,month,day]=match.slice(1,4).map(Number);
 const calendar=new Date(0);calendar.setUTCFullYear(year,month-1,day);calendar.setUTCHours(0,0,0,0);
 if(calendar.getUTCFullYear()!==year||calendar.getUTCMonth()!==month-1||calendar.getUTCDate()!==day||
    match[4]!==undefined&&(Number(match[4])>23||Number(match[5])>59||Number(match[6]||0)>59))return null;
 const at=new Date(value.includes('T')?value:value+'T12:00:00');
 return Number.isNaN(at.getTime())?null:at.getTime();
}
function tableDate(value,options={}){
 if(!value)return '—';
 const at=tableTimestamp(value),hasTime=String(value).includes('T');
 if(at===null)return 'Fecha no válida';
 const parts=Object.fromEntries(new Intl.DateTimeFormat('es-ES',{day:'numeric',month:'short',hour:hasTime?'2-digit':undefined,minute:hasTime?'2-digit':undefined,hourCycle:'h23',timeZone:options.timeZone}).formatToParts(at).map(p=>[p.type,p.value]));
 const month=parts.month.replace(/\.$/,'').replace(/^sept$/,'sep');
 return `${parts.day} ${month}${hasTime?` ${parts.hour}:${parts.minute} h`:''}`;
}
function discoveryDay(value,options={}){
 const at=tableTimestamp(value);
 if(at===null)return null;
 if(!String(value).includes('T'))return value;
 const parts=Object.fromEntries(new Intl.DateTimeFormat('es-ES',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:options.timeZone}).formatToParts(at).map(part=>[part.type,part.value]));
 return `${parts.year}-${parts.month}-${parts.day}`;
}
function discoveryTime(value,now=Date.now(),options={}){
 const at=tableTimestamp(value);if(at===null||!Number.isFinite(now))return '—';
 const precise=String(value).includes('T'),elapsed=now-at;
 const calendar=new Intl.DateTimeFormat('en-GB',{year:'numeric',month:'numeric',day:'numeric',hour:'numeric',minute:'numeric',second:'numeric',hourCycle:'h23',timeZone:options.timeZone});
 const parts=time=>Object.fromEntries(calendar.formatToParts(time).filter(part=>part.type!=='literal').map(part=>[part.type,Number(part.value)]));
 const today=parts(now),found=precise?parts(at):{year:Number(value.slice(0,4)),month:Number(value.slice(5,7)),day:Number(value.slice(8,10))};
 const dayNumber=({year,month,day})=>{const dayAt=new Date(0);dayAt.setUTCFullYear(year,month-1,day);return dayAt.getTime()/86400000;};
 const days=dayNumber(today)-dayNumber(found);
 if(days<0||precise&&elapsed<0)return relativeTime(value,now,options);
 if(precise&&elapsed<86400000){
  if(elapsed<60000)return 'Ahora';
  return elapsed<3600000?`Hace ${Math.floor(elapsed/60000)} min`:`Hace ${Math.floor(elapsed/3600000)} h`;
 }
 if(!days)return 'Hoy';
 const monthEnd=(year,month)=>{const end=new Date(0);end.setUTCFullYear(year,month,0);return end.getUTCDate();};
 const anniversary={year:found.year+1,month:found.month,day:Math.min(found.day,monthEnd(found.year+1,found.month))};
 // The anniversary day retains "Hace 1 año"; older calendar dates use month/year.
 if(dayNumber(today)>dayNumber(anniversary))return `${['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][found.month-1]} ${found.year}`;
 const clock=parts=>parts.hour*3600+parts.minute*60+parts.second;
 const anniversaryReached=today.day>Math.min(found.day,monthEnd(today.year,today.month))||today.day===Math.min(found.day,monthEnd(today.year,today.month))&&(!precise||clock(today)>=clock(found));
 const months=(today.year-found.year)*12+today.month-found.month-(anniversaryReached?0:1);
 if(months>=12)return 'Hace 1 año';
 if(months>0)return `Hace ${months} ${months===1?'mes':'meses'}`;
 const elapsedDays=precise?Math.max(1,Math.floor(elapsed/86400000)):days;
 return `Hace ${elapsedDays} ${elapsedDays===1?'día':'días'}`;
}
function relativeTime(value,now=Date.now(),options={}){
 const at=tableTimestamp(value);if(at===null||!Number.isFinite(now))return '—';
 const precise=String(value).includes('T'),future=at>now;
 const calendar=new Intl.DateTimeFormat('en-GB',{year:'numeric',month:'numeric',day:'numeric',hour:'numeric',minute:'numeric',second:'numeric',hourCycle:'h23',timeZone:options.timeZone});
 const parts=time=>Object.fromEntries(calendar.formatToParts(time).filter(part=>part.type!=='literal').map(part=>[part.type,Number(part.value)]));
 const today=parts(now),then=precise?parts(at):{year:Number(value.slice(0,4)),month:Number(value.slice(5,7)),day:Number(value.slice(8,10))};
 const first=future?today:then,last=future?then:today;
 const monthEnd=new Date(0);monthEnd.setUTCFullYear(last.year,last.month,0);
 const anniversary=Math.min(first.day,monthEnd.getUTCDate()),clock=p=>p.hour*3600+p.minute*60+p.second;
 const complete=last.day>anniversary||last.day===anniversary&&(!precise||clock(last)>=clock(first));
 const months=(last.year-first.year)*12+last.month-first.month-(complete?0:1);
 if(months>0){const unit=months>=12?'year':'month',amount=(months>=12?Math.floor(months/12):months)*(future?1:-1),text=new Intl.RelativeTimeFormat('es',{numeric:'always'}).format(amount,unit);return text[0].toUpperCase()+text.slice(1);}
 if(/^\d{4}-\d{2}-\d{2}$/.test(String(value))){
  const [year,month,day]=String(value).split('-').map(Number);
  const today=Object.fromEntries(new Intl.DateTimeFormat('es-ES',{year:'numeric',month:'numeric',day:'numeric',timeZone:options.timeZone}).formatToParts(now).map(part=>[part.type,part.value]));
  const days=(Date.UTC(year,month-1,day)-Date.UTC(Number(today.year),Number(today.month)-1,Number(today.day)))/86400000;
  if(days===0)return 'Hoy';
  const text=new Intl.RelativeTimeFormat('es',{numeric:'always'}).format(days,'day');return text[0].toUpperCase()+text.slice(1);
 }
 const difference=at-now,elapsed=Math.abs(difference);
 if(elapsed<60000)return difference<=0?'Ahora':'En unos instantes';
 const unit=elapsed>=86400000?'day':elapsed>=3600000?'hour':'minute';
 const amount=Math.floor(elapsed/({day:86400000,hour:3600000,minute:60000}[unit]))*(difference<=0?-1:1);
 const text=new Intl.RelativeTimeFormat('es',{numeric:'always'}).format(amount,unit);
 return text[0].toUpperCase()+text.slice(1);
}

function historicalDate(label){
 const match=String(label||'').match(/(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\s+(\d{4})/i);
 if(!match)return '';
 const month={ene:'01',feb:'02',mar:'03',abr:'04',may:'05',jun:'06',jul:'07',ago:'08',sep:'09',oct:'10',nov:'11',dic:'12'}[match[2].toLowerCase()];
 return `${match[3]}-${month}-${match[1].padStart(2,'0')}`;
}

// Sources sometimes publish names entirely in capitals. Display them in normal case while
// keeping acronyms (SAP, BI, S.L.) and the stored text untouched.
const minorWords=new Set('a al con de del e el en la las los o para por u y and for of the'.split(' '));
function displayCase(value){
 const text=String(value??'');
 if(/\p{Ll}/u.test(text)||(text.match(/\p{Lu}/gu)||[]).length<6)return text;
 let first=true;
 return text.replace(/[\p{L}\p{M}.]+/gu,word=>{
  const start=first;first=false;
  if(word.includes('.'))return word;
  const lower=word.toLocaleLowerCase('es');
  if(minorWords.has(lower))return start?lower[0].toLocaleUpperCase('es')+lower.slice(1):lower;
  if(word.length<=3||!/[AEIOUÁÉÍÓÚÜY]/u.test(word))return word;
  return lower[0].toLocaleUpperCase('es')+lower.slice(1);
 });
}

const api={fold,tableText,salaryNumber,salaryInfo,tableTimestamp,tableDate,discoveryDay,discoveryTime,relativeTime,historicalDate,displayCase};
if(typeof module!=='undefined')module.exports=api;else window.StubbsJobsFormatting=api;
})();
