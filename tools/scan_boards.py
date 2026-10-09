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
from urllib.parse import parse_qsl, urljoin, urlsplit
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
COUNTRY_ALIASES={
    'ES':re.compile(r'\b(spain|españa|espana|madrid|barcelona|cádiz|cadiz|malaga|málaga|valencia|sevilla)\b',re.I),
    'MX':re.compile(r'\b(mexico|méxico|cdmx|ciudad de mexico|ciudad de méxico)\b',re.I),
    'US':re.compile(r'\b(us|usa|united states|estados unidos)\b',re.I),
    'GB':re.compile(r'\b(uk|united kingdom|reino unido|london|londres)\b',re.I),
    'CA':re.compile(r'\b(canada|canadá)\b',re.I),
    'PL':re.compile(r'\b(poland|polska|polonia)\b',re.I),
    'BR':re.compile(r'\b(brazil|brasil)\b',re.I),
}
COUNTRY_CODES={'ES':'ES','ESP':'ES','MX':'MX','MEX':'MX','US':'US','USA':'US','GB':'GB','GBR':'GB','UK':'GB','CA':'CA','CAN':'CA','PL':'PL','POL':'PL','BR':'BR','BRA':'BR'}

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
    requested=countries_in(regions)
    if not requested:return True
    offered=countries_in(location)
    for country in countries:
        offered.update(countries_in(country))
    if offered:return bool(requested & offered)
    if re.search(r'\b(worldwide|global|anywhere)\b',location,re.I):return True
    if re.search(r'\b(europe|europa|emea|eu)\b',location,re.I):
        return bool(requested & {'ES','GB','PL'})
    if re.search(r'\b(latam|latin america|latinoam[eé]rica)\b',location,re.I):
        return bool(requested & {'MX','BR'})
    return True

def role_tokens(value):
    plain=''.join(c for c in unicodedata.normalize('NFD',str(value).casefold()) if not unicodedata.combining(c))
    for phrase,canonical in (('business intelligence',' bi '),('inteligencia de negocio',' bi '),
                             ('back end','backend'),('front end','frontend'),
                             ('analista','analyst'),('datos','data'),('analitica','analytics'),
                             ('ingeniero','engineer'),('ingeniera','engineer'),
                             ('desarrollador','developer'),('desarrolladora','developer')):
        plain=plain.replace(phrase,canonical)
    words=set(re.findall(r'[a-z0-9]+',plain))-{'senior','junior','sr','jr','remote','remoto','remota','de','del','of','en','para'}
    if 'engineer' in words:words.remove('engineer');words.add('developer')
    if 'backend' in words or 'frontend' in words:words.add('software')
    return words

ROLE_WORDS={'analyst','developer','consultant','architect','specialist','manager','lead','director'}

def role_match(title,description,target_roles):
    """Keep adjacent titles for review while requiring a shared subject area."""
    title_words=role_tokens(title)
    terms=[role_tokens(role) for role in re.split('[,;\n]',target_roles) if role.strip()]
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
        if match is None:return None
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
