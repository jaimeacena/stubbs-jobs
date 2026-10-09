"""Verified local backups and isolated recovery. Never replaces the active folder."""
import io
import json
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from stubbs_jobs_core import atomic_bytes, digest, lock, now, parse_json, read_store
from cv_usage import legacy_paths

DOCUMENTS = ('perfil.md', 'estrategia.md', 'fuentes-y-empresas.md', 'portales-y-cuentas.md', 'respuestas-candidaturas.md')
ARCHIVES = ('packages', 'package-recovery', 'package-staging', 'snapshots', 'migration', 'workbook-backups')
MAX_FILES = 20000
MAX_BYTES = 1_000_000_000


def personal_document(name):
    return name in DOCUMENTS or any(name.startswith(Path(original).stem + ' [conflicted') and name.endswith('.md') for original in DOCUMENTS)


def safe_name(name):
    if not isinstance(name, str) or not name or re.search(r'[\\:<>"|?*\x00-\x1f]', name):
        return False
    path = PurePosixPath(name)
    return (not path.is_absolute() and not any(part in ('', '.', '..') for part in name.split('/')) and
            not any(part.endswith(('.', ' ')) or re.fullmatch(r'(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part) for part in path.parts))


def source_file(root, relative):
    if not safe_name(relative):
        raise ValueError('La copia contiene una ruta no válida: ' + str(relative))
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or any(parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(root)):
        raise ValueError('La copia no puede incluir enlaces a archivos de otra carpeta')
    if not path.is_file():
        raise ValueError('Falta un archivo necesario para recuperar tus datos: ' + relative)
    return path


def references(data):
    files = {entry['path'] for entry in data.get('app', {}).get('cvLibrary', [])}
    for row in data['sheets']['Oportunidades']:
        files.update(row[field] for field in ('CV preparado', 'CV usado') if row.get(field))
    for record in [*data.get('events', []), *data.get('historicalApplications', [])]:
        files.update(record[field] for field in ('cv', 'archivedCV') if record.get(field))
    for package in data.get('app', {}).get('packages', []):
        key = package['id']
        if not isinstance(key, str) or not re.fullmatch('[a-f0-9]{64}', key):
            raise ValueError('La copia conservada tiene un identificador no válido')
        files.update('data/packages/' + key + '/' + name for name in ('package.json', 'cv.pdf', 'presentacion.txt'))
        if package['payload'].get('cv'):
            files.add(package['payload']['cv'])
    return files


def create(root):
    root = Path(root).resolve()
    with lock(root / 'data'):
        data = read_store(root / 'data/registry.json')
        files = {'data/registry.json', *references(data)}
        files.update(path.relative_to(root).as_posix() for path in legacy_paths(data, root))
        files.update(path.name for path in root.glob('*.md') if path.is_file() and personal_document(path.name))
        files.update('config/' + name for name in ('sources.json', 'release.json') if (root / 'config' / name).is_file())
        for folder in ARCHIVES:
            base = root / 'data' / folder
            if base.is_symlink():
                raise ValueError('La carpeta de copias contiene un enlace. Conserva el original y pide al agente que lo compruebe.')
            if base.exists():
                files.update(path.relative_to(root).as_posix() for path in base.rglob('*') if path.is_file())
        if len(files) > MAX_FILES:
            raise ValueError('La copia supera el tamaño admitido. Pide al agente que prepare una copia completa sin borrar archivos.')
        buffer = io.BytesIO()
        manifest = {'schemaVersion': 1, 'createdAt': now(), 'revision': data['revision'], 'files': {}}
        size = 0
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(files):
                content = source_file(root, name).read_bytes()
                size += len(content)
                if size > MAX_BYTES:
                    raise ValueError('La copia supera el tamaño admitido. Pide al agente que prepare una copia completa sin borrar archivos.')
                archive.writestr(name, content)
                manifest['files'][name] = digest(content)
            archive.writestr('stubbs-backup.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        content = buffer.getvalue()
        verify(content)
        filename = 'Stubbs-Jobs-copia-' + now().replace(':', '').replace('+', '_') + '-' + uuid.uuid4().hex[:8] + '.zip'
        path = root / 'data/backups' / filename
        atomic_bytes(path, content)
        return {'name': filename, 'path': str(path), 'revision': data['revision'], 'files': len(files), 'sha256': digest(content)}


def verify(content):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) > MAX_FILES + 1 or len(set(name.casefold() for name in names)) != len(names) or sum(item.file_size for item in infos) > MAX_BYTES:
                raise ValueError('La copia tiene archivos repetidos o supera el tamaño admitido')
            if any(not safe_name(item.filename) or item.is_dir() or item.flag_bits & 1 or (item.external_attr >> 16) & 0o170000 == 0o120000 for item in infos):
                raise ValueError('La copia contiene rutas, enlaces o archivos no admitidos')
            manifest = parse_json(archive.read('stubbs-backup.json'))
            if not isinstance(manifest, dict) or manifest.get('schemaVersion') != 1 or not isinstance(manifest.get('files'), dict):
                raise ValueError('No se reconoce esta copia de Stubbs Jobs')
            if set(names) != {*manifest['files'], 'stubbs-backup.json'}:
                raise ValueError('La lista de archivos de la copia no coincide con su contenido')
            files = {name: archive.read(name) for name in manifest['files']}
            if any(digest(value) != manifest['files'][name] for name, value in files.items()):
                raise ValueError('La copia ha cambiado o está dañada. Conserva el archivo y utiliza otra copia comprobada.')
            data = parse_json(files['data/registry.json'])
            if (not isinstance(data, dict) or data.get('schemaVersion') != 2 or type(data.get('revision')) is not int or
                    data['revision'] != manifest.get('revision') or not isinstance(data.get('profile'), dict) or
                    not isinstance(data.get('sheets'), dict) or
                    any(not isinstance(data['sheets'].get(key), list) for key in ('Oportunidades', 'Entradas', 'Evidencias', 'Actividad', 'Fuentes'))):
                raise ValueError('El registro de la copia no coincide con su versión')
            if 'searchProfiles' in data.get('app',{}):
                from search_profiles import validate_model
                validate_model(data)
            if not references(data).issubset(files):
                raise ValueError('La copia no conserva todos los CV y materiales registrados')
            for entry in data.get('app', {}).get('cvLibrary', []):
                if digest(files[entry['path']]) != entry['id']:
                    raise ValueError('Un CV de la copia no coincide con el original registrado')
            for package in data.get('app', {}).get('packages', []):
                base = 'data/packages/' + package['id'] + '/'
                payload = parse_json(files[base + 'package.json'])
                if (payload != package['payload'] or digest(payload) != package['id'] or
                        digest(files[base + 'cv.pdf']) != payload['cvHash'] or
                        files[base + 'presentacion.txt'] != payload['message'].encode('utf-8')):
                    raise ValueError('Un paquete de la copia no conserva su material original')
            return {'manifest': manifest, 'data': data, 'files': files}
    except (zipfile.BadZipFile, OSError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('No se pudo comprobar la copia. Conserva el archivo y pide al agente que revise otra copia.') from exc


def restore(root, archive_path, destination):
    root, archive_path, destination = Path(root).resolve(), Path(archive_path).resolve(), Path(destination).resolve()
    if destination.exists() or root.is_relative_to(destination) or destination.is_relative_to(root):
        raise ValueError('Elige una carpeta nueva, fuera de la instalación actual. La recuperación nunca sustituye la instalación activa.')
    if not archive_path.is_file() or archive_path.stat().st_size > MAX_BYTES:
        raise ValueError('Elige una copia ZIP disponible de Stubbs Jobs')
    verified = verify(archive_path.read_bytes())
    # Only validated data paths may enter a recovery, never tools or executable code from a ZIP.
    files = verified['files']
    if any(not (personal_document(name) or name == 'data/registry.json' or name.startswith(('data/', 'outputs/')) or name in ('config/sources.json', 'config/release.json')) for name in files):
        raise ValueError('La copia contiene archivos ajenos a los datos de Stubbs Jobs')
    if any(name.startswith(('data/app-instance', 'data/agent-run', 'data/app-error', 'data/.')) for name in files):
        raise ValueError('La copia contiene información de una sesión que no debe recuperarse')
    import stubbs_jobs
    stubbs_jobs.validate(verified['data'])
    destination.mkdir(parents=True)
    result = None
    try:
        for folder in ('app', 'config'):
            shutil.copytree(root / folder, destination / folder, ignore=shutil.ignore_patterns('*conflict*', '__pycache__'))
        (destination / 'tools').mkdir()
        for path in (root / 'tools').glob('*'):
            if path.is_file() and path.suffix in ('.py', '.mjs', '.ps1', '.cs') and 'conflict' not in path.name.lower():
                shutil.copy2(path, destination / 'tools' / path.name)
        for path in root.glob('*.md'):
            if 'conflict' not in path.name.lower():
                shutil.copy2(path, destination / path.name)
        for path in (root / 'LICENSE', root / 'runtime/python'):
            if path.is_dir():
                shutil.copytree(path, destination / path.relative_to(root), ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            elif path.is_file():
                shutil.copy2(path, destination / path.name)
        for name, content in files.items():
            if name == 'config/release.json':
                continue  # Restored data uses the installed code's version, not a stale label.
            atomic_bytes(destination / name, content)
        atomic_bytes(destination / 'data/recovery-original.json', files['data/registry.json'])
        operation = {'id': 'recover-' + uuid.uuid4().hex, 'operations': [{'kind': 'ui-recover-backup',
                     'expectedRevision': verified['data']['revision'],
                     'originalHash': digest(files['data/registry.json']),
                     'proof': 'Copia verificada recuperada en otra carpeta. Permisos antiguos retirados; confirmar el último paso antes de continuar.'}]}
        batch = destination / 'data/recovery-operation.json'
        atomic_bytes(batch, json.dumps(operation, ensure_ascii=False).encode('utf-8'))
        # Embedded Python's ._pth may point to the caller's tools, even for another
        # script path. Pin imports to the recovered folder before loading its writer.
        bootstrap = "import runpy,sys; tools=sys.argv.pop(1); sys.path.insert(0,tools); sys.argv[0]=tools+'/stubbs_jobs.py'; runpy.run_path(sys.argv[0],run_name='__main__')"
        result = subprocess.run([sys.executable, '-B', '-c', bootstrap, str(destination / 'tools'), 'apply', '--file', str(batch)], capture_output=True, text=True, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('No se pudo comprobar el registro recuperado mediante su escritor.')
        guide = ('Copia recuperada en una carpeta aparte. La instalación original se conserva.\n'
                 'Abre esta carpeta en tu agente y compara los datos con la instalación actual antes de utilizarla.\n'
                 'Los permisos antiguos de envío se han retirado. Las selecciones vuelven a revisión.\n'
                 'Comprueba los portales para solicitudes interrumpidas; no repitas un formulario por restaurar una copia.\n'
                 'data/recovery-original.json conserva el registro original completo.\n')
        atomic_bytes(destination / 'RECUPERACION.txt', guide.encode('utf-8'))
        # Publish the normal entry point only after data, safeguards and guidance are complete.
        launcher = root / 'Abrir Stubbs Jobs.exe'
        if launcher.is_file():
            atomic_bytes(destination / launcher.name, launcher.read_bytes())
    except BaseException as exc:
        diagnostic = type(exc).__name__ + ': ' + str(exc) + '\n'
        if result is not None:
            diagnostic += result.stdout + '\n' + result.stderr
        try:
            atomic_bytes(destination / 'data/recovery-diagnostic.log', diagnostic.encode('utf-8'))
        except OSError:
            pass  # A full or inaccessible destination must not hide the original failure.
        if not isinstance(exc, Exception):
            raise
        raise ValueError('Los archivos se conservaron en la carpeta de recuperación, pero falta completar su comprobación. No abras esa copia; pide al agente que revise data/recovery-diagnostic.log y conserve el original.') from exc
    return {'destination': str(destination), 'originalRevision': verified['data']['revision'], 'files': len(files), 'permissionsRestored': False}
