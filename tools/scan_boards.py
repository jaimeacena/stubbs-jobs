"""Read-only discovery. Ambiguous locations go to review, never imply eligibility."""
import argparse
import http.client
import html
import ipaddress
import json
import re
import socket
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urljoin, urlsplit
from xml.etree import ElementTree
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler
from stubbs_jobs_core import ROOT, atomic_json, lock, now, identity, canonical_url, digest, parse_json
from state_support import instant
from runtime import configure_stdio
CURRENT_SEARCH=None


def public_destination(url):
    """Resolve and reject local targets before each fetch or redirect."""
    from personalization import validate_public_source_url
    validate_public_source_url(url)
    host=urlsplit(url).hostname
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError('No se pudo resolver la web pública') from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('La web pública apunta a una dirección local o privada')
    return list(dict.fromkeys(item[4][0] for item in addresses))


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        if self._tunnel_host:
            raise ValueError('El captador no utiliza intermediarios de red')
        # Connect to a checked numeric address. TLS still verifies the public
        # hostname, so a later DNS change cannot redirect this connection.
        addresses=public_destination(f'https://{self.host}')
        error=None
        for address in addresses:
            try:
                self.sock=socket.create_connection((address,self.port),self.timeout,self.source_address)
                break
            except OSError as exc:
                error=exc
        else:
            raise error or OSError('No se pudo conectar con la web pública')
        try:
            self.sock=self._context.wrap_socket(self.sock,server_hostname=self.host)
        except Exception:
            self.sock.close()
            raise


class PublicHTTPSHandler(HTTPSHandler):
    def https_open(self,req):
        # HTTPSHandler keeps hostname verification in its TLS context. Newer
        # Python versions no longer expose _check_hostname or accept that
        # separate HTTPSConnection argument.
        return self.do_open(PinnedHTTPSConnection,req,context=self._context)


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if CURRENT_SEARCH and CURRENT_SEARCH.get('sourceUrls','').strip() and urlsplit(req.full_url).hostname.lower().removeprefix('www.')!=urlsplit(newurl).hostname.lower().removeprefix('www.'):
            raise ValueError('La fuente exclusiva redirige a otra web; no se amplía el alcance de búsqueda')
        public_destination(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

TITLE=re.compile(r'\b(data|datos|analytics?|anal[ií]tica|intelligence|inteligencia|automat\w*|ai|ia|llm|copilot|power\s*(?:bi|platform|automate)|bi|fabric|finance systems|business systems|financial systems|revenue operations)\b',re.I)
SPAIN=re.compile(r'\b(spain|españa|espana|madrid|barcelona|cádiz|cadiz|malaga|málaga|valencia|sevilla)\b',re.I)
REGION=re.compile(r'\b(europe|europa|emea|eu|worldwide|global|anywhere)\b',re.I)
OUTSIDE=re.compile(r'\b(united states|usa|us|canada|poland|polska|united kingdom|uk|london|mexico|méxico|brazil|brasil)\b',re.I)
# A listing whose places are all recognised abroad leaves a search for another
# country; unknown places stay for review. Spanish cities are listed so that a
# mixed list such as "Bilbao; Lisbon" keeps its Spanish alternative.
COUNTRY_ALIASES={
    'ES':re.compile(r'\b(spain|españa|espana|madrid|barcelona|cádiz|cadiz|malaga|málaga|valencia|sevilla|seville|bilbao|zaragoza|alicante|murcia|'
                    r'valladolid|vigo|coruña|granada|córdoba|cordoba|palma|mallorca|las palmas|tenerife|san sebastián|san sebastian|'
                    r'donostia|pamplona|santander|oviedo|gijón|gijon|vitoria|almería|almeria|huelva|jerez|sanlúcar|sanlucar|el puerto de santa maría|'
                    r'santiago de compostela|salamanca|burgos|toledo|getafe|alcobendas|pozuelo|tarragona|girona|lleida|castellón|castellon|'
                    r'las rozas|tres cantos|sant cugat|badalona|elche|cartagena|almussafes|irun)\b',re.I),
    'MX':re.compile(r'\b(mexico|méxico|cdmx|ciudad de mexico|ciudad de méxico|guadalajara|monterrey)\b',re.I),
    'US':re.compile(r'\b(us|usa|united states|estados unidos)\b',re.I),
    'GB':re.compile(r'\b(uk|united kingdom|reino unido|london|londres|manchester|edinburgh)\b',re.I),
    'CA':re.compile(r'\b(canada|canadá|toronto|vancouver|montreal)\b',re.I),
    'PL':re.compile(r'\b(poland|polska|polonia|warsaw|varsovia|krakow|kraków|wroclaw|wrocław)\b',re.I),
    'BR':re.compile(r'\b(brazil|brasil|são paulo|sao paulo)\b',re.I),
    'PT':re.compile(r'\b(portugal|lisbon|lisboa|porto|oporto)\b',re.I),
    'FR':re.compile(r'\b(france|francia|paris|parís|lyon|strasbourg|estrasburgo|toulouse)\b',re.I),
    'DE':re.compile(r'\b(germany|alemania|deutschland|berlin|berlín|munich|münchen|múnich|hamburg|frankfurt)\b',re.I),
    'NL':re.compile(r'\b(netherlands|países bajos|paises bajos|holanda|amsterdam|ámsterdam|rotterdam|the hague)\b',re.I),
    'IE':re.compile(r'\b(ireland|irlanda|dublin|dublín)\b',re.I),
    'IT':re.compile(r'\b(italy|italia|milan|milano|milán)\b',re.I),
    'BE':re.compile(r'\b(belgium|bélgica|belgica|brussels|bruselas|bruxelles)\b',re.I),
    'LU':re.compile(r'\b(luxembourg|luxemburgo)\b',re.I),
    'CH':re.compile(r'\b(switzerland|suiza|zurich|zürich|geneva|ginebra)\b',re.I),
    'AT':re.compile(r'\b(austria|vienna|viena)\b',re.I),
    'DK':re.compile(r'\b(denmark|dinamarca|copenhagen|copenhague)\b',re.I),
    'SE':re.compile(r'\b(sweden|suecia|stockholm|estocolmo)\b',re.I),
    'IN':re.compile(r'\b(india|bangalore|bengaluru|hyderabad|pune|mumbai)\b',re.I),
    'AR':re.compile(r'\b(argentina|buenos aires)\b',re.I),
    'CO':re.compile(r'\b(colombia|bogotá|bogota|medellín|medellin)\b',re.I),
}
COUNTRY_CODES={'ES':'ES','ESP':'ES','MX':'MX','MEX':'MX','US':'US','USA':'US','GB':'GB','GBR':'GB','UK':'GB','CA':'CA','CAN':'CA','PL':'PL','POL':'PL','BR':'BR','BRA':'BR',
               'PT':'PT','PRT':'PT','FR':'FR','FRA':'FR','DE':'DE','DEU':'DE','NL':'NL','NLD':'NL','IE':'IE','IRL':'IE','IT':'IT','ITA':'IT',
               'BE':'BE','BEL':'BE','LU':'LU','LUX':'LU','CH':'CH','CHE':'CH','AT':'AT','AUT':'AT','DK':'DK','DNK':'DK','SE':'SE','SWE':'SE',
               'IN':'IN','IND':'IN','AR':'AR','ARG':'AR','CO':'CO','COL':'CO'}
EUROPE={'ES','GB','PL','PT','FR','DE','NL','IE','IT','BE','LU','CH','AT','DK','SE'}

def fetch(url,as_json=True):
    public_destination(url)
    opener=build_opener(ProxyHandler({}),PublicHTTPSHandler(),PublicRedirect())
    for attempt in range(3):
        try:
            with opener.open(Request(url,headers={'User-Agent':'StubbsJobs personal career research/2.0'}),timeout=20) as response:
                raw=response.read(12_000_001)
                if len(raw)>12_000_000: raise ValueError('Respuesta demasiado grande')
                text=raw.decode('utf-8') if as_json else decode_page(raw,response)
                return json.loads(text) if as_json else text
        except (HTTPError,URLError,TimeoutError) as exc:
            retry=not isinstance(exc,HTTPError) or exc.code in (408,429,500,502,503,504)
            if isinstance(exc,HTTPError):exc.close()
            if not retry or attempt==2: raise
            time.sleep(.5*(2**attempt))

def decode_page(raw,response):
    """Valid UTF-8 is read as before; otherwise the charset the page declares is used."""
    try:return raw.decode('utf-8')
    except UnicodeDecodeError as error:
        headers=getattr(response,'headers',None)
        charset=headers.get_content_charset() if hasattr(headers,'get_content_charset') else None
        if not charset:
            declared=re.search(rb'<meta[^>]{0,200}?charset\s*=\s*["\']?([A-Za-z0-9._-]{1,40})',raw[:4096],re.I)
            charset=declared.group(1).decode('ascii') if declared else None
        if not charset:raise
        try:return raw.decode(charset)
        except LookupError:raise error from None  # unknown or non-text codec names

def jobs_payload(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('jobs'),list):
        raise ValueError('Formato inesperado: falta una lista jobs válida')
    return payload['jobs']

def geographic_queue(location,description='',countries=()):
    if any(str(c).upper() in ('ES','ESP','SPAIN','ESPAÑA') for c in countries) or SPAIN.search(location): return True
    if REGION.search(location) or SPAIN.search(description): return True
    return not bool(OUTSIDE.search(location))

def countries_in(value):
    plain=str(value).strip()
    found={code for code,pattern in COUNTRY_ALIASES.items() if pattern.search(plain)}
    if plain.upper() in COUNTRY_CODES:found.add(COUNTRY_CODES[plain.upper()])
    return found

def geographic_queue_for_search(location,countries,regions):
    if re.search(r'\b(worldwide|global|anywhere|cualquier pa[ií]s|todo el mundo)\b',regions,re.I):return True
    requested=countries_in(regions)
    if re.search(r'\b(europe|europa|eu|ue|uni[oó]n europea|emea)\b',regions,re.I):requested|=EUROPE
    if not requested:return True
    offered=countries_in(location)
    for country in countries:
        offered.update(countries_in(country))
    if offered:return bool(requested & offered)
    if re.search(r'\b(worldwide|global|anywhere)\b',location,re.I):return True
    if re.search(r'\b(europe|europa|emea|eu)\b',location,re.I):
        return bool(requested & EUROPE)
    if re.search(r'\b(latam|latin america|latinoam[eé]rica)\b',location,re.I):
        return bool(requested & {'MX','BR','AR','CO'})
    return True

def word_stem(word):
    """Join Spanish gender/number forms and simple plurals: enfermera/enfermeros -> enfermer."""
    if len(word)>=6 and word.endswith(('os','as')):return word[:-2]
    if len(word)>=6 and word.endswith('es') and word[-3] in 'lnrd':return word[:-2]
    if len(word)>=5 and word.endswith('s') and not word.endswith('ss'):word=word[:-1]
    if len(word)>=5 and word[-1] in 'oa':return word[:-1]
    # dependiente/dependienta, asistente/asistenta, gerente/gerenta
    if len(word)>=6 and word[-1]=='e':return word[:-1]
    return word

# Common occupations in Spanish mapped to an English canonical word. Matching is
# still by shared words; this only lets equivalent titles in both languages meet.
OCCUPATIONS={
    'enfermero':'nurse','enfermeria':'nursing','auxiliar':'assistant','asistente':'assistant','ayudante':'assistant',
    'camarero':'waiter','mesero':'waiter','cocinero':'cook','profesor':'teacher','maestro':'teacher','docente':'teacher',
    'conductor':'driver','chofer':'driver','repartidor':'courier','vendedor':'salesperson','ventas':'sales','comercial':'sales',
    'dependiente':'shop','cajero':'cashier','contable':'accountant','contador':'accountant','contabilidad':'accounting',
    'abogado':'lawyer','medico':'doctor','electricista':'electrician','fontanero':'plumber','mecanico':'mechanic',
    'limpieza':'cleaning','limpiador':'cleaner','recepcionista':'receptionist','administrativo':'administrative',
    'almacen':'warehouse','operario':'operator','tecnico':'technician','soldador':'welder','carpintero':'carpenter',
    'peluquero':'hairdresser','cuidador':'caregiver','farmaceutico':'pharmacist','psicologo':'psychologist',
    'fisioterapeuta':'physiotherapist','disenador':'designer','arquitecto':'architect','gerente':'manager',
    'jefe':'lead','jefa':'lead','responsable':'manager','consultor':'consultant','especialista':'specialist',
    'atencion':'service','cliente':'customer','logistica':'logistics','marketing':'marketing','recursos':'resources',
    'humanos':'human','seguridad':'security','vigilante':'guard','educador':'educator','traductor':'translator','cocina':'kitchen','ingles':'english','frances':'french',
    'aleman':'german','espanol':'spanish','sala':'floor','primaria':'primary','secundaria':'secondary',
}
OCCUPATION_STEMS={word_stem(spanish):word_stem(english) for spanish,english in OCCUPATIONS.items()}
GENDER_SUFFIX=re.compile(r'(\w)\s*(?:/|\(|\\)\s*(?:a|o|as|os|es|e)\b\)?')

def role_tokens(value):
    plain=''.join(c for c in unicodedata.normalize('NFD',str(value).casefold()) if not unicodedata.combining(c))
    plain=GENDER_SUFFIX.sub(r'\1',re.sub(r'(\w)@',r'\1o',plain))
    for phrase,canonical in (('business intelligence',' bi '),('inteligencia de negocio',' bi '),
                             ('back end','backend'),('front end','frontend'),
                             ('analista','analyst'),('datos','data'),('analitica','analytics'),
                             ('ingeniero','engineer'),('ingeniera','engineer'),
                             ('desarrollador','developer'),('desarrolladora','developer')):
        plain=plain.replace(phrase,canonical)
    words=set(re.findall(r'[a-z0-9]+',plain))-{'senior','junior','sr','jr','remote','remoto','remota','de','del','of','en','para'}
    if 'engineer' in words:words.remove('engineer');words.add('developer')
    if 'backend' in words or 'frontend' in words:words.add('software')
    return {OCCUPATION_STEMS.get(word_stem(word),word_stem(word)) for word in words}

ROLE_WORDS={'analyst','developer','consultant','architect','specialist','manager','lead','director',
            'assistant','technician','operator','worker','sale'}

CONJUNCTION=re.compile(r'\s+(?:y|e|o|u|and|or)\s+',re.I)

def role_terms(target_roles):
    """Each listed role, plus the roles joined inside a sentence such as
    "Data Engineer junior y puestos mixtos". One-word fragments stay inside
    their original phrase, so "Seguridad y salud" never matches any security job."""
    terms=[]
    for role in re.split('[,;\n]',target_roles):
        if not role.strip():continue
        terms.append(role_tokens(role))
        parts=CONJUNCTION.split(role)
        if len(parts)>1:
            terms.extend(tokens for part in parts if len(tokens:=role_tokens(part))>=2)
    return terms

def role_match(title,description,target_roles):
    """Keep adjacent titles for review while requiring a shared subject area."""
    title_words=role_tokens(title)
    terms=role_terms(target_roles)
    if any(term and term.issubset(title_words) for term in terms):return 'direct'
    description_words=None
    for term in terms:
        if len(term)<2:continue
        shared=term & title_words
        if not (shared-ROLE_WORDS):continue
        if len(shared)>=2:return 'related'
        if description_words is None:description_words=role_tokens(str(description or '')[:10000])
        if term.issubset(description_words):return 'related'
    return None

def published_mode_excluded(title,location):
    """A remote-only search skips listings whose own title or location publish only
    hybrid or on-site work, read exactly as the minimums later read the offer.
    Silence, partial remote quotas or a remote alternative stay for review."""
    from offer_minimums import categories
    if categories(CURRENT_SEARCH.get('workMode') or CURRENT_SEARCH.get('_location',''),'mode',preference=True)!={'remote'}:return False
    published=categories(f'{title} {location}','mode')
    return bool(published) and 'remote' not in published

def candidate(source,title,url,location='',description='',**extra):
    if not title or not url: raise ValueError('Oferta sin título o URL')
    if CURRENT_SEARCH is None:
        if not TITLE.search(title): return None
        if not geographic_queue(location,description,extra.pop('countries',())): return None
        match='direct'
    else:
        # Keywords guide the agent's wider search; they cannot turn an unrelated
        # title into a match. Related titles remain unverified discoveries.
        match=role_match(title,description,CURRENT_SEARCH['targetRoles'])
        if match is None or published_mode_excluded(title,location):return None
        countries=extra.pop('countries',())
        regions=CURRENT_SEARCH.get('regions','')+' '+CURRENT_SEARCH.get('_location','')
        if not geographic_queue_for_search(location,countries,regions):return None
    return dict(id=identity(url),company=source['company'],sourceId=source['id'],title=title,
                url=canonical_url(url),location=location,description=html.unescape(description),
                countryStatus='Pendiente',remoteStatus='Pendiente',roleMatch=match,
                conditionsToVerify='Comprobar contrato, salario, ubicación, desplazamientos y horario con las preferencias actuales',**extra)

def api_board(source,coverage=None):
    kind=source['kind']; board=source['board']
    url=(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true' if kind=='greenhouse'
         else f'https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true')
    payload=fetch(url);jobs=jobs_payload(payload); found=[]; errors=[]
    if any(payload.get(key) for key in ('hasMore','hasNextPage','nextPage','nextCursor')):
        errors.append('La API declara otra página que este adaptador no ha comprobado')
    for j in jobs:
        try:
            if not isinstance(j,dict): raise ValueError('Oferta mal formada')
            if kind=='greenhouse':
                c=candidate(source,j.get('title'),j.get('absolute_url'),(j.get('location') or {}).get('name',''),
                    j.get('content') or '',originalPublishedAt=j.get('first_published'),lastPublishedAt=None,updatedAt=j.get('updated_at'))
            else:
                places=[j.get('location') or '']+[x.get('location') or '' for x in j.get('secondaryLocations') or []]
                countries=[((j.get('address') or {}).get('postalAddress') or {}).get('addressCountry')]
                countries += [(x.get('address') or {}).get('addressCountry') for x in j.get('secondaryLocations') or []]
                c=candidate(source,j.get('title'),j.get('jobUrl'),'; '.join(places),j.get('descriptionPlain') or '',
                    countries=countries,originalPublishedAt=None,lastPublishedAt=j.get('publishedAt'),
                    employmentType=j.get('employmentType'),compensationPublished=j.get('compensation'))
            if c: found.append(c)
        except (TypeError,ValueError,AttributeError,KeyError) as exc: errors.append(str(exc))
    if coverage is not None:
        coverage.update(method='api',scope='Listado recibido de la API; condiciones individuales pendientes de comprobar',
                        pages=[url],completeness='partial' if errors else 'returned_listing')
    return len(jobs),found,errors

PAGE_LIMIT=30
PAGE_SIZE=100

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[]
    def handle_data(self,data):
        self.parts.append(data)

def plain_text(value):
    """Readable text of a published HTML description, for matching and review."""
    if not isinstance(value,str) or not value:return ''
    parser=PlainText();parser.feed(value);parser.close()
    return ' '.join(' '.join(parser.parts).split())

def joined(*values,separator=', '):
    return separator.join(dict.fromkeys(str(v).strip() for v in values if isinstance(v,(str,int)) and str(v).strip()))

def fetch_pages(page_url,read,as_json=True):
    """Follow a paged API until it proves its end. read(payload, received) returns
    (offers, last page, problem); a problem or a failure after the first page keeps
    what was received and leaves the listing partial."""
    items=[];pages=[];errors=[]
    for index in range(PAGE_LIMIT):
        url=page_url(index)
        try:batch,done,problem=read(fetch(url,as_json),len(items))
        except (OSError,ValueError) as exc:
            if not pages:raise
            errors.append(f'{url}: {exc}');return items,pages,errors
        pages.append(url);items.extend(batch)
        if problem:errors.append(problem);return items,pages,errors
        if done:return items,pages,errors
    errors.append('Límite de paginación alcanzado; cobertura parcial')
    return items,pages,errors

def lever_listing(source):
    host='api.eu.lever.co' if source.get('region')=='eu' else 'api.lever.co'
    base=f"https://{host}/v0/postings/{quote(source['board'],safe='')}?mode=json&limit={PAGE_SIZE}"
    def read(payload,received):
        if not isinstance(payload,list):raise ValueError('Formato inesperado: Lever no devolvió una lista de ofertas')
        if len(payload)>PAGE_SIZE:
            return payload,True,'La API devolvió más ofertas que el tamaño de página pedido; no se ha comprobado el resto del listado'
        return payload,len(payload)<PAGE_SIZE,None
    return fetch_pages(lambda index:f'{base}&skip={index*PAGE_SIZE}',read)

def lever_offer(source,j):
    categories=j.get('categories') or {}
    places=categories.get('allLocations') if isinstance(categories.get('allLocations'),list) else []
    places=places or [categories.get('location')]
    lists=' '.join(joined(x.get('text'),plain_text(x.get('content')),separator=' ') for x in j.get('lists') or [] if isinstance(x,dict))
    return candidate(source,j.get('text'),j.get('hostedUrl'),joined(*places,separator='; '),
        joined(j.get('descriptionPlain'),lists,j.get('additionalPlain'),separator='\n'),countries=[j.get('country')],
        originalPublishedAt=None,lastPublishedAt=None,employmentType=categories.get('commitment'))

def smartrecruiters_listing(source):
    base=f"https://api.smartrecruiters.com/v1/companies/{quote(source['board'],safe='')}/postings?limit={PAGE_SIZE}"
    declared={}
    def read(payload,received):
        if not isinstance(payload,dict) or not isinstance(payload.get('content'),list):
            raise ValueError('Formato inesperado: falta una lista content válida')
        batch=payload['content'];total=payload.get('totalFound')
        if type(total) is not int or total<0:
            return batch,True,'La API no declara el total de ofertas; no se ha comprobado el resto del listado'
        declared['total']=total
        return batch,not batch or received+len(batch)>=total,None
    items,pages,errors=fetch_pages(lambda index:f'{base}&offset={index*PAGE_SIZE}',read)
    if not errors and 'total' in declared and len(items)!=declared['total']:
        errors.append(f"Cobertura parcial: {len(items)} de {declared['total']} ofertas declaradas por la API")
    return items,pages,errors

def smartrecruiters_offer(source,j):
    place=j.get('location') or {}
    company=(j.get('company') or {}).get('identifier') or source['board']
    if not re.fullmatch(r'\d+',str(j.get('id') or '')):raise ValueError('Oferta sin identificador')
    return candidate(source,j.get('name'),f"https://jobs.smartrecruiters.com/{quote(company,safe='')}/{j['id']}",
        place.get('fullLocation') or joined(place.get('city'),place.get('region'),place.get('country')),
        countries=[place.get('country')],originalPublishedAt=None,lastPublishedAt=j.get('releasedDate'),
        employmentType=(j.get('typeOfEmployment') or {}).get('label'))

def single_listing(url,key,source_name):
    payload=fetch(url)
    if not isinstance(payload,dict) or not isinstance(payload.get(key),list):
        raise ValueError(f'Formato inesperado: falta una lista {key} válida')
    errors=[]
    if any(payload.get(name) for name in ('hasMore','hasNextPage','nextPage','next','paging','meta')):
        errors.append(f'La API de {source_name} declara otra página que este adaptador no ha comprobado')
    return payload[key],[url],errors

def workable_listing(source):
    return single_listing(f"https://apply.workable.com/api/v1/widget/accounts/{quote(source['board'],safe='')}?details=true",'jobs','Workable')

def workable_offer(source,j):
    places=[joined(x.get('city'),x.get('region'),x.get('country')) for x in j.get('locations') or [] if isinstance(x,dict) and not x.get('hidden')]
    countries=[x.get('countryCode') for x in j.get('locations') or [] if isinstance(x,dict)]
    return candidate(source,j.get('title'),j.get('url') or j.get('shortlink'),
        joined(*places,separator='; ') or joined(j.get('city'),j.get('state'),j.get('country')),plain_text(j.get('description')),
        countries=countries or [j.get('country')],originalPublishedAt=None,lastPublishedAt=j.get('published_on'),
        employmentType=j.get('employment_type'))

def recruitee_listing(source):
    return single_listing(f"https://{source['board']}.recruitee.com/api/offers/",'offers','Recruitee')

def recruitee_instant(value):
    """Recruitee writes '2026-10-15 09:31:36 UTC'; the registry reads ISO dates."""
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) UTC',value or '')
    return f'{match[1]}T{match[2]}+00:00' if match else None

def recruitee_offer(source,j):
    places=[x.get('name') or joined(x.get('city'),x.get('country')) for x in j.get('locations') or [] if isinstance(x,dict)]
    countries=[j.get('country_code')]+[x.get('country_code') for x in j.get('locations') or [] if isinstance(x,dict)]
    return candidate(source,j.get('title'),j.get('careers_url'),joined(j.get('location'),*places,separator='; '),
        joined(plain_text(j.get('description')),plain_text(j.get('requirements')),separator='\n'),countries=countries,
        originalPublishedAt=None,lastPublishedAt=recruitee_instant(j.get('published_at')),employmentType=j.get('employment_type_code'))

def personio_host(source):
    host=(urlsplit(source.get('url') or '').hostname or '').lower()
    return host if host==f"{source['board']}.jobs.personio.com" else f"{source['board']}.jobs.personio.de"

def personio_listing(source):
    url=f'https://{personio_host(source)}/xml'
    text=fetch(url,False)
    # Entities are never expanded: a public feed has no reason to declare them.
    if re.search(r'<!(?:DOCTYPE|ENTITY)',text,re.I):raise ValueError('Formato inesperado: el XML declara entidades o un tipo de documento')
    try:root=ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:raise ValueError('Formato inesperado: XML de Personio no válido') from exc
    if root.tag!='workzag-jobs':raise ValueError('Formato inesperado: falta la lista workzag-jobs')
    def value(node,path):
        return ' '.join((''.join(node.find(path).itertext()) if node.find(path) is not None else '').split())
    offers=[{'id':value(p,'id'),'name':value(p,'name'),'office':value(p,'office'),
             'offices':[' '.join(''.join(o.itertext()).split()) for o in p.findall('additionalOffices/office')],
             'description':joined(*(plain_text(''.join(v.itertext())) for v in p.findall('jobDescriptions/jobDescription/value')),separator='\n'),
             'employmentType':joined(value(p,'employmentType'),value(p,'schedule'))} for p in root.findall('position')]
    return offers,[url],[]

def personio_offer(source,j):
    if not re.fullmatch(r'\d+',j['id']):raise ValueError('Oferta sin identificador')
    return candidate(source,j['name'],f"https://{personio_host(source)}/job/{j['id']}",joined(j['office'],*j['offices'],separator='; '),
        j['description'],originalPublishedAt=None,lastPublishedAt=None,employmentType=j['employmentType'] or None)

PORTALS={'lever':(lever_listing,lever_offer,'id'),'smartrecruiters':(smartrecruiters_listing,smartrecruiters_offer,'id'),
         'workable':(workable_listing,workable_offer,'shortcode'),'recruitee':(recruitee_listing,recruitee_offer,'id'),
         'personio':(personio_listing,personio_offer,'id')}

def portal_board(source,coverage=None):
    """Hosted company job boards with a public listing API."""
    listing,offer,key=PORTALS[source['kind']]
    items,pages,errors=listing(source)
    found=[];seen=set();total=0
    for j in items:
        try:
            if not isinstance(j,dict):raise ValueError('Oferta mal formada')
            if j.get(key) and j[key] in seen:
                errors.append('Una oferta aparece repetida entre páginas: el listado cambió durante la lectura');continue
            if j.get(key):seen.add(j[key])
            total+=1
            c=offer(source,j)
            if c:found.append(c)
        except (TypeError,ValueError,AttributeError,KeyError) as exc:errors.append(str(exc))
    if coverage is not None:
        coverage.update(method='api',scope='Listado recibido de la API; condiciones individuales pendientes de comprobar',
                        pages=pages,completeness='partial' if errors else 'returned_listing')
    return total,found,errors

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.href=None; self.parts=[]; self.text=[]
        self.next_hrefs=set();self.next_links=set();self.button_parts=None;self.dynamic_controls=[];self.anchor_active=False
    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        if tag in ('a','link') and 'next' in (attributes.get('rel') or '').lower().split():
            self.next_hrefs.add(attributes.get('href') or '')
        if tag=='link' and attributes.get('href') and attributes.get('href') in self.next_hrefs:
            self.links.append((attributes['href'],''))
        if tag=='a': self.href=attributes.get('href'); self.parts=[];self.anchor_active=True
        if tag=='button' and 'disabled' not in attributes and attributes.get('aria-disabled')!='true':self.button_parts=[]
    def handle_data(self,data):
        self.text.append(data)
        if self.anchor_active: self.parts.append(data)
        if self.button_parts is not None:self.button_parts.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor_active:
            label=' '.join(' '.join(self.parts).split())
            if self.href:self.links.append((self.href,label))
            elif NEXT_LABEL.search(label):self.dynamic_controls.append(label)
            self.href=None;self.anchor_active=False
        if tag=='button' and self.button_parts is not None:
            text=' '.join(self.button_parts)
            if NEXT_LABEL.search(text):self.dynamic_controls.append(text.strip())
            self.button_parts=None

NEXT_LABEL=re.compile(r'^\s*(?:siguiente|next|ver\s+m[aá]s|mostrar(?:\s+\d+)?\s+m[aá]s|load\s+more)\b',re.I)

def pagination_link(link,label,parser,source):
    parts=urlsplit(link);base=urlsplit(source['url'])
    path=parts.path.rstrip('/');root_path=base.path.rstrip('/')
    paged=any(re.fullmatch(r'(?:page(?:\[[^]]*\])?|p|cursor|offset|start)',key,re.I) for key,_ in parse_qsl(parts.query))
    known_path=path in (root_path,'/jobs','/jobs/show_more') or bool(root_path and path.startswith(root_path+'/'))
    indicated=link in parser.next_links or bool(NEXT_LABEL.search(label))
    return indicated or paged and known_path,known_path

def html_board(source,coverage=None):
    queue=[source['url']]; visited=set(); pages=[];jobs={}; errors=[]; advertised=None;pagination_seen=False
    while queue and len(visited)<30:
        url=queue.pop(0)
        if url in visited: continue
        visited.add(url)
        try:
            parser=Links(); parser.feed(fetch(url,False))
            parser.next_links={urljoin(url,href) for href in parser.next_hrefs}
            pages.append(url)
            if parser.dynamic_controls:errors.append('Paginación dinámica sin enlace comprobable: '+', '.join(parser.dynamic_controls))
            count=re.search(r'(\d+)\s+(?:vacantes|ofertas)', ' '.join(parser.text),re.I)
            if count: advertised=max(advertised or 0,int(count.group(1)))
            for href,label in parser.links:
                link=urljoin(url,href); p=urlsplit(link)
                paged,known_path=pagination_link(link,label,parser,source)
                same_site=(p.hostname or '').lower().removeprefix('www.')==(urlsplit(source['url']).hostname or '').lower().removeprefix('www.')
                if paged:
                    pagination_seen=True
                    if not same_site or p.scheme!='https' or not known_path or p.fragment or canonical_url(link)==canonical_url(url):
                        errors.append('Enlace de paginación no comprobado: '+link)
                        continue
                    if link not in visited and link not in queue: queue.append(link)
                elif same_site and re.match(r'/jobs/[^/?]+',p.path) and not re.search(r'/(?:new|connect|login|apply|show_more)(?:/|$)',p.path):
                    key=canonical_url(link)
                    if label and len(label)>len(jobs.get(key,'')): jobs[key]=label
        except (OSError,ValueError) as exc: errors.append(f'{url}: {exc}')
    if queue: errors.append('Límite de paginación alcanzado; cobertura parcial')
    if not jobs and advertised!=0: errors.append('No se pudieron verificar vacantes ni un listado vacío explícito')
    if advertised is not None and len(jobs)<advertised: errors.append(f'Cobertura parcial: {len(jobs)} de {advertised} anuncios visibles')
    if advertised is not None and len(jobs)>advertised:errors.append('El recuento anunciado no coincide con los enlaces encontrados; comprobar el alcance')
    found=[]
    for url,title in jobs.items():
        c=candidate(source,title,url,originalPublishedAt=None,lastPublishedAt=None)
        if c: found.append(c)
    if coverage is not None:
        coverage.update(method='html',scope='Enlaces de ofertas visibles en las páginas recorridas; condiciones individuales pendientes de comprobar',
                        pages=pages,paginationObserved=pagination_seen,
                        completeness='partial' if errors else 'declared_count' if advertised is not None else 'observed_pages')
    return len(jobs),found,errors

def scan(source):
    from personalization import validate_source_configuration
    validate_source_configuration([source])
    start=time.monotonic()
    from source_reviews import configured_url
    source_url=configured_url(source)
    coverage={'method':source.get('kind'),'scope':'No se ha acreditado un listado de ofertas','pages':[],'completeness':'unsupported'}
    try:
        if source['kind'] in ('ashby','greenhouse'):total,found,errors=api_board(source,coverage)
        elif source['kind'] in PORTALS:total,found,errors=portal_board(source,coverage)
        elif source['kind']=='html':total,found,errors=html_board(source,coverage)
        else:
            return dict(sourceId=source['id'],company=source['company'],sourceUrl=source_url,status='unsupported',candidates=[],
                        errors=['No existe adaptador para este tipo de fuente'],checkedAtUtc=now(),seconds=round(time.monotonic()-start,2),coverage=coverage)
        if coverage['completeness']=='observed_pages':
            errors.append('Se conservaron los enlaces visibles; no se pudo acreditar la totalidad del listado')
            coverage['completeness']='partial'
        return dict(sourceId=source['id'],company=source['company'],sourceUrl=source_url,status='partial' if errors else 'ok',
            totalPosts=total,candidates=found,errors=errors,checkedAtUtc=now(),seconds=round(time.monotonic()-start,2),coverage=coverage)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        coverage['completeness']='error'
        return dict(sourceId=source['id'],company=source['company'],sourceUrl=source_url,status='error',candidates=[],errors=[str(exc)[:500]],checkedAtUtc=now(),seconds=round(time.monotonic()-start,2),coverage=coverage)

def record_source_result(result, previous_path):
    """Keep a damaged success record and report the new attempt independently."""
    previous=None
    try:
        if previous_path.exists():
            previous=parse_json(previous_path.read_bytes())
            if not isinstance(previous,dict) or previous.get('sourceId')!=result['sourceId'] or type(previous.get('totalPosts')) is not int or previous['totalPosts']<0 or instant(previous.get('checkedAtUtc')) is None:
                raise ValueError('Registro anterior incompleto')
    except (OSError,ValueError,TypeError):
        result['errors'].append('No se pudo comprobar el último éxito guardado de esta web. Se conserva el archivo anterior; el agente debe revisarlo.')
        if result['status']=='ok':result['status']='partial'
        previous=None
    if result['status']=='ok' and previous and previous['totalPosts']>10 and result['totalPosts']<previous['totalPosts']*.25:
        result['status']='partial';result['errors'].append('Descenso brusco: comprobar cobertura antes de interpretar cierres')
    result['lastSuccessUtc']=result['checkedAtUtc'] if result['status']=='ok' else (previous or {}).get('checkedAtUtc')
    if result['status']=='ok':atomic_json(previous_path,result)


def main():
    global CURRENT_SEARCH
    configure_stdio()
    ap=argparse.ArgumentParser(); ap.add_argument('--source',action='append'); ap.add_argument('--request'); args=ap.parse_args()
    from stubbs_jobs_core import read_store
    store=read_store()
    import search_profiles
    from personalization import context
    from app_context import criteria
    request=search_profiles.discovery_request(store,args.request)
    if 'searchProfiles' in store.get('app',{}) and not request:
        raise ValueError('Indica --request con una búsqueda autorizada en curso')
    store=search_profiles.discovery_data(store,request)
    CURRENT_SEARCH={**context(store),'_location':criteria(store).get('location','')}
    if store.get('app',{}).get('personalized') and not store['app'].get('setupComplete'):
        raise ValueError('Completa primero tu perfil y los puestos que buscas')
    from personalization import public_sources, validate_source_configuration
    # Validate the entire configuration before opening the network or using an
    # identifier as a filename, including when --source selects only one board.
    configured=validate_source_configuration(public_sources(store))
    sources=[s for s in configured if not args.source or s['id'] in args.source]
    out=ROOT/'outputs/feeds'
    with lock(out):
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(scan,sources))
        for result in results:
            previous_path=out/'last-good'/f"{result['sourceId']}.json"
            record_source_result(result,previous_path)
        payload={'schemaVersion':2,'runId':now().replace(':','-')+'-'+digest(results)[:8],'checkedAtUtc':now(),
            'status':'skipped' if not sources else 'ok' if all(r['status']=='ok' for r in results) else 'partial',
            'reason':'Sin webs públicas configuradas; el agente debe buscar con su navegador y registrar la cobertura real.' if not sources else None,
            'boards':[{k:v for k,v in r.items() if k!='candidates'} for r in results],
            'candidates':[c for r in results for c in r['candidates']]}
        if request:
            payload.update(requestId=request['id'],searchKey=request.get('searchKey'),searchProfileId=request.get('searchProfileId'))
        atomic_json(out/'runs'/f"{payload['runId']}.json",payload); atomic_json(out/'latest.json',payload)
        with (out/'run-log.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({k:v for k,v in payload.items() if k!='candidates'},ensure_ascii=False)+'\n')
    print(json.dumps({'status':payload['status'],'reason':payload['reason'],'candidateCount':len(payload['candidates']),'boards':payload['boards']},ensure_ascii=False))
    return 0 if payload['status']=='ok' else 1

if __name__=='__main__': raise SystemExit(main())
