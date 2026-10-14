"""Resolve supported local dependencies without installing or changing them."""
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys

def configure_stdio():
    for stream in (sys.stdout,sys.stderr):
        if stream is not None and hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')

def node_path():
    configured=os.environ.get('STUBBS_JOBS_NODE')
    choices=[configured] if configured else []
    choices.extend([str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'),shutil.which('node')])
    for value in choices:
        if value and Path(value).is_file():return Path(value)
    raise ValueError('No se encuentra Node. Configura STUBBS_JOBS_NODE con su ruta o repara las dependencias de Codex.')

SYNC_PROVIDERS=(('onedrive','OneDrive'),('dropbox','Dropbox'),('google drive','Google Drive'),('googledrive','Google Drive'),
                ('pcloud','pCloud'),('icloud','iCloud'),('box sync','Box'),('mega','MEGA'),('sync.com','Sync.com'))

def synced_folder(root):
    """Name of a cloud sync service that appears to own this folder, or None.

    Sync clients can create conflict copies of data/registry.json and hold its lock;
    the app keeps working, but the person is told to move it to a local folder."""
    resolved=Path(root).resolve()
    parts=[part.casefold() for part in resolved.parts]
    for marker,name in SYNC_PROVIDERS:
        if any(part==marker or part.startswith(marker+' ') or part.startswith(marker+'-') for part in parts):return name
    for variable in ('OneDrive','OneDriveConsumer','OneDriveCommercial'):
        base=os.environ.get(variable)
        if base:
            try:
                if resolved.is_relative_to(Path(base).resolve()):return 'OneDrive'
            except (OSError,ValueError):pass
    return None

def doctor(root):
    manifest=json.loads((root/'config/dependencies.json').read_text(encoding='utf-8'))
    minimum=tuple(int(part) for part in manifest['pythonMinimum'].split('.'))
    checks=[{'name':'Python','available':sys.version_info>=minimum,'version':sys.version.split()[0],'path':sys.executable}]
    try:checks.append({'name':'Node','available':True,'path':str(node_path())})
    except ValueError as exc:checks.append({'name':'Node','available':False,'detail':str(exc)})
    for name in manifest['pythonPackages']:
        try:checks.append({'name':name,'available':True,'version':importlib.metadata.version(name)})
        except importlib.metadata.PackageNotFoundError:checks.append({'name':name,'available':False})
    package=root/'tools/node_modules/@oai/artifact-tool/package.json'
    checks.append({'name':'@oai/artifact-tool','available':package.is_file(),'version':json.loads(package.read_text(encoding='utf-8')).get('version') if package.is_file() else None})
    synced=synced_folder(root)
    warnings=[f'La carpeta está dentro de {synced}. Muévela a una carpeta local sin sincronizar (por ejemplo C:\\StubbsJobs) para evitar copias en conflicto del registro.'] if synced else []
    return {'ok':all(c['available'] for c in checks if c['name'] not in ('Node','@oai/artifact-tool')),'excelAvailable':excel_available(root),'checks':checks,'syncedFolder':synced,'warnings':warnings}

def excel_available(root):
    if not (root/'tools/node_modules/@oai/artifact-tool/package.json').is_file():return False
    try:node_path();return True
    except ValueError:return False
