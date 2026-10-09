"""Ephemeral identification of this app's Windows window; no operational data."""
import hashlib
import json
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

MODE = 'StubbsJobs.WindowIcon.v1'
TITLE = 'Stubbs Jobs'
LIFETIME = 120
MAX_PENDING = 32
_lock = threading.Lock()
_launches = {}


def diagnostic(directory, code):
    """Only fixed, non-sensitive codes; never log arguments, URLs or exceptions."""
    allowed = {'helper_unavailable', 'helper_start_failed', 'window_not_found',
               'window_icon_api', 'window_icon_ready', 'window_icon_closed'}
    if code not in allowed:
        code = 'window_icon_api'
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'app-window.log').open('a', encoding='utf-8') as file:
            file.write(json.dumps({'at': time.time(), 'code': code}) + '\n')
    except OSError:
        pass


def _prune():
    now = time.monotonic()
    for token, entry in list(_launches.items()):
        if now - entry['at'] > LIFETIME:
            _launches.pop(token, None)


def launch(edge, address, launcher, project, directory, spawn):
    """Spawn an asynchronous helper; absence/failure leaves browser fallback usable."""
    try:
        parsed = urlsplit(address)
        key = parse_qs(parsed.fragment).get('key', [''])[0]
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path != '/' or
                parsed.username or parsed.password or not parsed.port or not key or
                not re.fullmatch(r'[a-f0-9]{24}', project)):
            return False
        if not launcher.is_file() or MODE.encode('utf-16le') not in launcher.read_bytes():
            diagnostic(directory, 'helper_unavailable')
            return False
        token = secrets.token_hex(16)
        with _lock:
            _prune()
            if len(_launches) >= MAX_PENDING:
                diagnostic(directory, 'helper_unavailable')
                return False
            _launches[token] = {'at': time.monotonic(), 'status': 'pending', 'directory': directory}
        query = parse_qs(parsed.query)
        query['window-icon'] = [token]
        target = urlunsplit(parsed._replace(query=urlencode(query, doseq=True)))
        spawn([str(launcher), MODE, str(edge), target, token, 'StubbsJobs.Desktop.' + project])
        return True
    except (OSError, ValueError):
        if 'token' in locals():
            with _lock:
                _launches.pop(token, None)
        diagnostic(directory, 'helper_start_failed')
        return False


def status(token):
    with _lock:
        _prune()
        entry = _launches.get(token)
        return entry['status'] if entry else 'expired'


def register(token, directory):
    """The serving process owns the marker, including reuse of an existing service."""
    if not re.fullmatch(r'[a-f0-9]{32}', token or ''):
        return False
    with _lock:
        _prune()
        if token in _launches:
            return _launches[token]['status'] == 'pending'
        if len(_launches) >= MAX_PENDING:
            return False
        _launches[token] = {'at': time.monotonic(), 'status': 'pending', 'directory': directory}
    return True


def acknowledge(token, result):
    if result not in ('ready', 'window_not_found', 'window_icon_api', 'window_icon_closed'):
        return False
    with _lock:
        _prune()
        entry = _launches.get(token)
        if not entry:
            return False
        entry['status'] = 'ready' if result == 'ready' else 'failed'
        directory = entry['directory']
    diagnostic(directory, 'window_icon_ready' if result == 'ready' else result)
    return True


def html(text, assets, token=None):
    """Fresh favicon identity and a temporary title only for a registered opening."""
    icon = assets / 'stubbs.ico'
    if icon.is_file():
        version = hashlib.sha256(icon.read_bytes()).hexdigest()[:20]
        text = text.replace('href="/assets/stubbs.ico"', 'href="/assets/stubbs.ico?v=' + version + '"')
    if token and status(token) == 'pending':
        title = TITLE + ' · ' + token
        text = text.replace('<title>Stubbs Jobs</title>', '<title>' + title + '</title>')
        text = text.replace('</head>', '<script src="/window-icon.js?token=' + token + '" defer></script>\n</head>')
    return text


def script(token):
    """A same-origin script removes the marker after native confirmation or timeout."""
    if not re.fullmatch(r'[a-f0-9]{32}', token or '') or status(token) == 'expired':
        return None
    return """'use strict';
(async()=>{
 const marker=%s,deadline=Date.now()+22000;
 while(Date.now()<deadline){
  try{const response=await fetch('/window-icon-status?token='+marker,{cache:'no-store'});
   const result=await response.json();if(result.status!=='pending')break;
  }catch{}
  await new Promise(resolve=>setTimeout(resolve,250));
 }
 document.title='Stubbs Jobs';
 const address=new URL(location.href);address.searchParams.delete('window-icon');
 history.replaceState(null,'',address.pathname+address.search+address.hash);
})();
""" % json.dumps(token)
