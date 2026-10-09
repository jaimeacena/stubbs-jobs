"""Prepare generic source from a verified empty distribution; never copy Git history."""
import argparse
import ast
import hashlib
import json
import runpy
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SHARE=runpy.run_path(str(ROOT/'tools/build-share.py'))
TESTS=SHARE['SOURCE_TESTS']
BUILD_TOOLS=SHARE['SOURCE_BUILD_TOOLS']

def generic_builder(text):
    function=next(node for node in ast.parse(text).body if isinstance(node,ast.FunctionDef) and node.name=='build')
    lines=[]
    for index,line in enumerate(text.splitlines(),1):
        if function.lineno<=index<=function.end_lineno and line.lstrip().startswith(('text=text.replace(',"if name!='scan_boards.py':")):
            continue
        lines.append(line)
    result='\n'.join(lines)+'\n'
    ast.parse(result)
    return result

def build(portable,destination):
    portable=portable.resolve();destination=destination.resolve();archive=Path(str(destination)+'.zip')
    if destination.exists() or archive.exists():raise ValueError('Usa una carpeta y un ZIP nuevos para el código público')
    if destination.is_relative_to(portable):raise ValueError('El código no se puede preparar dentro de la copia portable')
    manifest=json.loads((portable/'config/files.sha256.json').read_text(encoding='utf-8'))
    for name,expected in manifest.items():
        path=(portable/name).resolve()
        if not path.is_relative_to(portable) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('La copia portable no coincide con sus huellas: '+name)
    info=SHARE['release_metadata']()
    if json.loads((portable/'config/release.json').read_text(encoding='utf-8'))!=info:
        raise ValueError('El código y la descarga deben usar la misma versión')
    provenance_path=portable/'config/source-provenance.json'
    if not provenance_path.is_file() or 'config/source-provenance.json' not in manifest:
        raise ValueError('Esta copia no acredita su revisión de origen; reconstruye primero el portable vigente')
    provenance=json.loads(provenance_path.read_text(encoding='utf-8'))
    source_hashes=SHARE['source_input_hashes']()
    source_fingerprint=SHARE['source_identity'](source_hashes)
    if provenance.get('schemaVersion')!=1 or provenance.get('sourceFingerprint')!=source_fingerprint:
        raise ValueError('El portable pertenece a otra revisión del código; reconstruye ambos desde el mismo estado')
    names=['app/'+name for name in SHARE['APP_FILES']]+['app/assets/'+name for name in SHARE['APP_ASSETS']]
    names+=['tools/'+name for name in SHARE['MODULES']]
    names+=['AGENTS.md','APLICACION.md','CLAUDE.md','INICIO.md','OPERACION.md','PROGRAMACION.md','perfil.md','estrategia.md','CHANGELOG.md','LIMITES.md','AUTORIA.md','LICENSE','TERCEROS.md','SISTEMA.md','AGENTE.md','PLAN-SISTEMA.md','algoritmo-busqueda.md','RECUPERACION.md','DESARROLLO.md']
    names+=['config/'+name for name in ('dependencies.json','retention.json','sources.json','distribution.json','release.json','source-provenance.json')]
    def portable_bytes(name):
        if name not in manifest:raise ValueError('El manifiesto portable no acredita este archivo: '+name)
        path=(portable/name).resolve()
        if not path.is_relative_to(portable):raise ValueError('Ruta portable no válida: '+name)
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest[name]:raise ValueError('La copia portable cambió durante la construcción: '+name)
        return raw
    def source_text(name):
        raw=(ROOT/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source_hashes.get(name):raise ValueError('El código cambió durante la construcción: '+name)
        return raw.decode('utf-8').replace('\r\n','\n')
    for name in names:
        if name not in manifest:raise ValueError('El manifiesto portable no acredita este archivo: '+name)
    destination.mkdir(parents=True)
    for name in names:
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(portable_bytes(name))
    for name in BUILD_TOOLS:
        text=source_text('tools/'+name)
        if name=='build-share.py':
            # Public source is already generic; do not ship personal sanitization rules.
            text=generic_builder(text)
        (destination/'tools'/name).write_text(text,encoding='utf-8')
    for name in SHARE['DOCUMENTS']+('README-CODIGO.md',):
        target=destination/'distribution'/name;target.parent.mkdir(exist_ok=True)
        target.write_text(SHARE['render_document'](source_text('distribution/'+name),info),encoding='utf-8')
    # The shared templates link to these generated documents by their public names.
    # These reading copies are not build inputs; the root documents remain canonical.
    for name in ('APLICACION.md','CLAUDE.md','perfil.md'):
        notice=f'Copia generada para consultar las plantillas. El documento editable es [{name}](../{name}). Esta copia no se utiliza al construir la aplicación.\n\n'
        (destination/'distribution'/name).write_text(notice+portable_bytes(name).decode('utf-8').replace('\r\n','\n'),encoding='utf-8')
    readme=SHARE['render_document'](source_text('distribution/README-CODIGO.md'),info)
    # This template also ships in distribution/, where its manual link is local.
    readme=readme.replace('[manual de uso](README.md)','[manual de uso](distribution/README.md)')
    (destination/'README.md').write_text(readme,encoding='utf-8')
    for name in TESTS:
        target=destination/'tests'/name;target.parent.mkdir(exist_ok=True)
        # The generic interface names the legacy owner state as the portable build does.
        target.write_text(source_text('tests/'+name).replace('Pendiente de Jaime','Pendiente de Usuario'),encoding='utf-8')
    for name in SHARE['SOURCE_PROJECT_FILES']:
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(source_text(name),encoding='utf-8')
    (destination/'.gitignore').write_text('/data/\n/outputs/\n/runtime/\n/auditoria/\n/tmp/\n/.venv/\n.env\n.env.*\n/Abrir Stubbs Jobs.exe\n**/__pycache__/\n*.pyc\n/tools/node_modules/\n',encoding='utf-8')
    if SHARE['source_identity']()!=source_fingerprint:raise ValueError('El código cambió durante la construcción; conserva el diagnóstico y prepara una copia nueva')
    hashes={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination/'config/source-files.sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(destination.rglob('*')):
            if path.is_file():z.write(path,Path(destination.name)/path.relative_to(destination))
    return archive

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('portable',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();print(build(args.portable,args.destination))
