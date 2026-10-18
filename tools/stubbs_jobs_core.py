"""Shared identities and crash-safe single-writer storage, using the standard library."""
import gzip
import hashlib
import json
import math
import os
import re
import tempfile
import time
from contextlib import contextmanager
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = os.name == 'nt'
DATA = ROOT / 'data'
STORE = DATA / 'registry.json'
WORKBOOK = ROOT / 'outputs/busqueda-empleo.xlsx'

if (ROOT/'config/distribution.json').is_file():WORKBOOK=ROOT/'outputs/busqueda-empleo.xlsx'

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def digest(value):
    if not isinstance(value, bytes): value = json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(value).hexdigest()

def canonical_url(url):
    p = urlsplit(url)
    if p.scheme.lower() not in ('http','https') or not p.hostname:
        raise ValueError('La oferta necesita un enlace http o https válido')
    host = p.hostname.lower()
    netloc = f'[{host}]' if ':' in host else host
    if p.port is not None: netloc += f':{p.port}'
    # Keep unknown query keys: on some boards ``ref`` or ``source`` is the vacancy ID.
    query = [(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('trk','tracking_id')]
    return urlunsplit((p.scheme.lower(), netloc, p.path.rstrip('/'), urlencode(sorted(query)), ''))

@lru_cache(maxsize=8192)
def identity(url):
    """Pure function of the text: views compare every offer and entry, so remember it."""
    u = canonical_url(url); p = urlsplit(u); parts = p.path.strip('/').split('/')
    host = p.hostname.removeprefix('www.')
    if host == 'boards.greenhouse.io': host = 'job-boards.greenhouse.io'
    site = host + (f':{p.port}' if p.port is not None else '')
    if (host == 'linkedin.com' or host.endswith('.linkedin.com')) and p.port in (None,443):
        match = re.fullmatch(r'/jobs/view/(?:[^/]*-)?(\d+)', p.path)
        if match:return 'linkedin:'+match.group(1)
    if host == 'job-boards.greenhouse.io' and len(parts)>=3 and parts[1]=='jobs':
        return f'greenhouse:{parts[0]}:{parts[2]}'
    if host == 'jobs.ashbyhq.com' and len(parts)>=2:
        return f'ashby:{parts[0]}:{parts[1]}'
    if p.port is None:
        # Hosted company boards: the same vacancy keeps one identity on every
        # host alias, with or without its title slug or /apply suffix.
        if host in ('jobs.lever.co','jobs.eu.lever.co') and len(parts)>=2 and re.fullmatch(r'[0-9a-fA-F-]{36}',parts[1]):
            return f'lever:{parts[0].lower()}:{parts[1].lower()}'
        match = re.fullmatch(r'/(?:[^/]+/)?j/([A-Za-z0-9]+)(?:/.*)?', p.path)
        if host == 'apply.workable.com' and match:return 'workable:'+match.group(1)
        board = re.fullmatch(r'([a-z0-9-]+)\.jobs\.personio\.(?:de|com)', host)
        match = re.fullmatch(r'/job/(\d+)(?:/.*)?', p.path)
        if board and match:return f'personio:{board.group(1)}:{match.group(1)}'
        if host == 'jobs.smartrecruiters.com' and len(parts)>=2 and (match:=re.match(r'(\d+)(?:-|$)', parts[1])):
            return f'smartrecruiters:{parts[0].lower()}:{match.group(1)}'
        board = re.fullmatch(r'([a-z0-9-]+)\.recruitee\.com', host)
        match = re.fullmatch(r'/o/([^/]+)(?:/.*)?', p.path)
        if board and match:return f'recruitee:{board.group(1)}:{match.group(1)}'
    offer=re.search(r'/of-i([a-zA-Z0-9]+)',p.path)
    if host=='infojobs.net' and offer: return 'infojobs:'+offer.group(1)
    match = re.match(r'/jobs/(\d+)(?:-|$)', p.path)
    if match: return f'web:{site}:{match.group(1)}'
    return 'url:' + digest(urlunsplit(('https',site,p.path,p.query,'')))[:24]


def vacancy_key(record):
    """Compare current URLs while keeping legacy IDs, packages and history intact."""
    url = record.get('URL original') or record.get('URL') or record.get('url')
    if url:
        try:return identity(url)
        except ValueError:pass
    return record.get('Clave canónica') or record.get('canonicalKey')

@contextmanager
def lock(directory=DATA):
    """OS-owned lock, automatically released on exit/crash. Never delete this file."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'.writer.lock').open('a+b') as handle:
        handle.seek(0,2)
        if not handle.tell(): handle.write(b'0'); handle.flush()
        handle.seek(0)
        if os.name=='nt':
            import msvcrt
            try: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc: raise RuntimeError('Otra ejecución está actualizando el registro.') from exc
        else:
            import fcntl
            # Same contract on every platform: callers retry on RuntimeError.
            try: fcntl.flock(handle, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise RuntimeError('Otra ejecución está actualizando el registro.') from exc
        try: yield
        finally:
            handle.seek(0)
            if os.name=='nt': msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(handle,fcntl.LOCK_UN)

def atomic_bytes(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.pending',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def replace(source,target,attempts=20):
    """Windows refuses a replacement while another reader has the file open."""
    for attempt in range(attempts):
        try: return os.replace(source,target)
        except PermissionError:
            if not WINDOWS or attempt==attempts-1: raise
            time.sleep(.05)

def atomic_json(path,data):
    atomic_bytes(path,(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))

def parse_json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Los datos contienen un campo repetido; conserva el original y revisa su contenido')
            result[key]=value
        return result
    def invalid(value):
        raise ValueError('Los datos contienen una cantidad no válida: '+value)
    def finite(value):
        number=float(value)
        if not math.isfinite(number):invalid(value)
        return number
    return json.loads(raw,object_pairs_hook=unique,parse_constant=invalid,parse_float=finite)

def read_store(path=STORE):
    raw=Path(path).read_bytes(); data=parse_json(raw)
    if not isinstance(data,dict) or data.get('schemaVersion')!=2: raise ValueError('Versión de registro desconocida')
    data['_baseHash']=digest(raw)
    return data

def snapshot_path(key,directory=DATA):
    """Exact previous registry: legacy plain copy or gzip copy (decompress to read)."""
    for name in (f'{key}.json',f'{key}.json.gz'):
        candidate=Path(directory)/'snapshots'/name
        if candidate.is_file(): return candidate
    return None

def snapshot_bytes(key,directory=DATA):
    path=snapshot_path(key,directory)
    if path is None: return None
    raw=path.read_bytes()
    return gzip.decompress(raw) if path.suffix=='.gz' else raw

def save_store(data,path=STORE):
    path=Path(path)
    if path.exists():
        old=path.read_bytes(); key=digest(old)
        if data.get('_baseHash') and key!=data['_baseHash']: raise ValueError('El registro cambió fuera del escritor local; conciliar antes de guardar')
        # Every revision keeps an exact previous copy. New copies are compressed:
        # the registry grows with its history and full copies grew quadratically.
        if snapshot_path(key,path.parent) is None:
            atomic_bytes(path.parent/'snapshots'/f'{key}.json.gz',gzip.compress(old,compresslevel=3,mtime=0))
    data['revision']+=1; data['updatedAt']=now()
    data.pop('_baseHash',None)
    atomic_json(path,data); data['_baseHash']=digest(path.read_bytes())
    try:prune_snapshots(path.parent,path.read_bytes())
    except OSError:pass  # Retention is best effort; a saved registry is never undone.

SNAPSHOT_NAME=re.compile(r'^([0-9a-f]{64})\.json(?:\.gz)?$')

def snapshot_policy(root=ROOT):
    """Bounded history: recent revisions plus one copy per day. Defaults apply without config."""
    policy={'keepRecent':100,'keepDailyDays':90}
    try:
        configured=json.loads((Path(root)/'config/retention.json').read_text(encoding='utf-8')).get('snapshots',{})
        for name in policy:
            if type(configured.get(name)) is int and configured[name]>=1:policy[name]=configured[name]
    except (OSError,ValueError,AttributeError):pass
    return policy

def prune_snapshots(directory=DATA,current=b'',policy=None):
    """Remove only exact registry copies outside the policy and never one the registry references.

    Conflict copies, unknown files and copies named by the registry (for example a
    reset backup) are always kept. Returns the removed file names."""
    folder=Path(directory)/'snapshots'
    if not folder.is_dir():return []
    policy=policy or snapshot_policy()
    referenced=set(re.findall(rb'[0-9a-f]{64}',current))
    copies=[]
    for item in folder.iterdir():
        match=SNAPSHOT_NAME.match(item.name)
        if item.is_file() and not item.is_symlink() and match:copies.append((item.stat().st_mtime,item,match[1].encode()))
    copies.sort(key=lambda entry:entry[0],reverse=True)
    keep=set(index for index in range(min(policy['keepRecent'],len(copies))))
    cutoff=time.time()-policy['keepDailyDays']*86400;days=set()
    for index,(mtime,_,_) in enumerate(copies):
        day=datetime.fromtimestamp(mtime,timezone.utc).date()
        if mtime>=cutoff and day not in days:days.add(day);keep.add(index)
    removed=[]
    for index,(_,item,key) in enumerate(copies):
        if index in keep or key in referenced:continue
        item.unlink();removed.append(item.name)
    return removed
