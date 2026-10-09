"""Create an allowlisted, empty Windows distribution. Never copies operational data."""
import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODULES=('stubbs_jobs.py','stubbs_jobs_core.py','stubbs_jobs_app.py','window_icon.py','cv_usage.py','app_workflow.py','app_context.py','assistant_flow.py','agent_runner.py','agent_context.py','source_reviews.py','personalization.py','onboarding.py','profile_interview.py','runtime.py','maintenance.py','backup.py','request_workflow.py','offer_quality.py','view_cache.py','state_support.py','scan_boards.py','export-tracker.mjs')
MODULES+=('offer_actions.py','offer_minimums.py','application_lifecycle.py','search_profiles.py','criteria_preview.py')
APP_FILES=('index.html','app.js','icons.js','client.js','formatting.js','activity.js','workflow.js','recovery.js','explanations.js','presentation.js','drafts.js','setup.js','theme.js','release.js','redesign.css','criteria.js')
APP_ASSETS=('stubbs.png','stubbs.ico')
DOCUMENTS=('AGENTS.md','estrategia.md','INICIO.md','OPERACION.md','profile-template.md','PROGRAMACION.md','README.md','TERCEROS.md','CHANGELOG.md','LIMITES.md','AUTORIA.md','RECUPERACION.md','SISTEMA.md','AGENTE.md','PLAN-SISTEMA.md','algoritmo-busqueda.md','LICENSE','DESARROLLO.md')
SOURCE_TESTS=('test_distribution.py','test_distribution_runtime.py','test_review_20261002.py','test_workflow_fresh_audit.py','test_window_icon.py','test_cv_usage.py','test_fresh_audit.py','test_export_tracker.py','test_client.cjs','test_recovery.cjs','test_activity.cjs','test_presentation.cjs','test_browser_flow.cjs','test_workflow.cjs','workflow_fixtures.py','test_profile_interview.py','test_delivery_recovery.py','test_request_continuity.py','test_system_contracts.py','test_backup.py','test_offer_quality.py','test_best_argument.py','test_agent_context.py','test_source_reviews.py','test_source_scan.py','quality_cases.json')
SOURCE_TESTS+=('test_bulk_actions.py','test_minimums.py','test_profile_contacts.py','test_offer_display.py','test_review_corrections.py')
SOURCE_TESTS+=('test_integral_corrections.py','test_preservation_edges.py','test_application_lifecycle.py','test_profile_demographics.py')
SOURCE_TESTS+=('test_search_profiles.py','test_search_rounds.py','test_criteria_preview.py','test_criteria_effect.cjs')
SOURCE_TESTS+=('test_broken_connections.py',)
SOURCE_TESTS+=('test_review_edges_20261009.py',)
SOURCE_TESTS+=('test_exhaustive_review_20261009.py','test_salary_review_20261009.cjs')
SOURCE_TESTS+=('test_closing_flows_20261009.py',)
SOURCE_BUILD_TOOLS=('build-share.py','build-source.py','check-quality.py','launcher.cs','build-launcher.ps1')
SOURCE_PROJECT_FILES=('requirements.txt','.github/workflows/quality.yml')
PORTABLE_PYTHON_VERSION='3.14.7'


def inspect_portable_runtime(runtime):
    """Reject incomplete or differently labelled runtimes before creating a bundle."""
    python=runtime/'python.exe'
    if not python.is_file() or not (runtime/'pythonw.exe').is_file():
        raise ValueError('Faltan los ejecutables del runtime portátil verificado')
    probe="import json,sys,sysconfig; print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),'platform':sysconfig.get_platform()}))"
    try:
        result=subprocess.run([str(python),'-I','-S','-B','-c',probe],capture_output=True,text=True,encoding='utf-8',timeout=10)
        details=json.loads(result.stdout) if not result.returncode else None
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        raise ValueError('No se pudo comprobar la identidad del runtime portátil') from exc
    if details!={'version':PORTABLE_PYTHON_VERSION,'platform':'win-amd64'}:
        raise ValueError('El runtime debe coincidir con Python '+PORTABLE_PYTHON_VERSION+' Windows x64 declarado en TERCEROS.md')
    return details['version']


def source_input_hashes():
    names=['tools/'+name for name in MODULES+SOURCE_BUILD_TOOLS]
    names+=['app/'+name for name in APP_FILES]+['app/assets/'+name for name in APP_ASSETS]+['APLICACION.md','Abrir Stubbs Jobs.exe']
    names+=['distribution/'+name for name in DOCUMENTS+('README-CODIGO.md',)]
    names+=['config/'+name for name in ('dependencies.json','retention.json','release.json')]
    names+=['tests/'+name for name in SOURCE_TESTS]
    names+=list(SOURCE_PROJECT_FILES)
    # A portable-only input tree may omit public-source build inputs. Their absence
    # is part of its identity and cannot subsequently pass as the full source tree.
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() if (ROOT/name).is_file() else None
            for name in sorted(set(names))}


def source_identity(inputs=None):
    """Identity of all shared build inputs, without exporting any personal data."""
    hashes=source_input_hashes() if inputs is None else inputs
    return hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def release_metadata(reader=None):
    reader=reader or (lambda name:(ROOT/name).read_text(encoding='utf-8'))
    info=json.loads(reader('config/release.json'))
    number=r'(?:0|[1-9][0-9]*)'
    version=info.get('version','')
    version_valid=isinstance(version,str) and (
        (info.get('channel')=='stable' and re.fullmatch(number+r'\.'+number+r'\.'+number,version)) or
        (info.get('channel')=='beta' and re.fullmatch(number+r'\.'+number+r'\.'+number+r'-beta\.'+number,version)))
    if (info.get('schemaVersion')!=1 or info.get('name')!='Stubbs Jobs' or
            not version_valid or info.get('platform')!='Windows x64' or info.get('license')!='MIT' or
            not isinstance(info.get('label'),str) or not info['label'].strip()):
        raise ValueError('La identidad de esta entrega no es válida')
    date.fromisoformat(info['releaseDate'])
    expected='window.StubbsJobsRelease = Object.freeze('+json.dumps(info,ensure_ascii=False,separators=(',',':'))+');\n'
    if reader('app/release.js')!=expected:
        raise ValueError('La versión visible no coincide con config/release.json')
    return info

def render_document(text,info):
    for key,value in {'RELEASE_LABEL':info['label'],'RELEASE_VERSION':info['version'],'RELEASE_DATE':info['releaseDate']}.items():
        text=text.replace('{{'+key+'}}',value)
    if re.search(r'\{\{RELEASE_[A-Z]+\}\}',text):raise ValueError('Hay un dato de publicación sin resolver')
    return text

def replace_function(text,name,replacement):
    function=next(node for node in ast.parse(text).body if isinstance(node,ast.FunctionDef) and node.name==name)
    lines=text.splitlines(keepends=True)
    return ''.join(lines[:function.lineno-1])+replacement+'\n'+''.join(lines[function.end_lineno:])

def build(destination,runtime):
    destination=destination.resolve()
    runtime=runtime.resolve()
    archive=Path(str(destination)+'.zip')
    if destination.exists() or archive.exists():raise ValueError('Usa una carpeta y un nombre de ZIP nuevos para no tocar copias existentes')
    if not runtime.is_dir():raise ValueError('Falta el runtime portátil verificado')
    if destination.is_relative_to(runtime):raise ValueError('La copia no puede crearse dentro del runtime original')
    python_version=inspect_portable_runtime(runtime)
    source_hashes=source_input_hashes()
    source_fingerprint=source_identity(source_hashes)
    def source_bytes(name):
        raw=(ROOT/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source_hashes.get(name):
            raise ValueError('El código cambió durante la construcción: '+name)
        return raw
    def source_text(name):
        return source_bytes(name).decode('utf-8').replace('\r\n','\n')
    info=release_metadata(source_text)
    if not (ROOT/'distribution/LICENSE').is_file():raise ValueError('Falta elegir la licencia de la edición pública')
    if not source_text('distribution/LICENSE').startswith('MIT License\n'):
        raise ValueError('La licencia no coincide con la identidad de esta entrega')
    destination.mkdir(parents=True)
    for name in MODULES:
        text=source_text('tools/'+name)
        # Only historical personal initialization is excluded. Live protocols are shared.
        if name=='stubbs_jobs.py':
            text=replace_function(text,'migrate',"def migrate():\n    raise ValueError('Esta copia empieza con init; no importa datos históricos de otra persona')")
        if name=='app_workflow.py':
            text=replace_function(text,'seed',"def seed(data):\n    app=state(data)\n    retire_mail(data)\n    automation(data)\n    app.setdefault('legacyImported',True)\n    for row in data['sheets']['Oportunidades']:draft(data,row['ID'])\n    return app")
        if name=='stubbs_jobs_core.py':
            text=re.sub(r"^WORKBOOK = ROOT / '[^']+'$","WORKBOOK = ROOT / 'outputs/busqueda-empleo.xlsx'",text,flags=re.M)
            # City names in the scanner are geographic rules, not private profile data.
        target=destination/'tools'/name;target.parent.mkdir(exist_ok=True);target.write_text(text,encoding='utf-8')
    for name in APP_FILES:
        target=destination/'app'/name;target.parent.mkdir(exist_ok=True)
        target.write_text(source_text('app/'+name).replace('Jaime','Usuario'),encoding='utf-8')
    for name in APP_ASSETS:
        target=destination/'app/assets'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(source_bytes('app/assets/'+name))
    for name in DOCUMENTS:
        source=ROOT/'distribution'/name
        target=destination/'perfil.md' if source.name=='profile-template.md' else destination/source.name
        target.write_text(render_document(source_text('distribution/'+name),info),encoding='utf-8')
    application=source_text('APLICACION.md')
    offer_states=application.split('## Estado común de las ofertas',1)[1].split('## Organización',1)[0]
    interface=application.split('## Detalles del contrato de interfaz',1)[1].split('## Contrato del agente',1)[0]
    contract=application.split('## Contrato del agente',1)[1].split('## Conservación y funcionamiento',1)[0]
    current_actions='## Selección múltiple en Ofertas'+application.split('## Selección múltiple en Ofertas',1)[1]
    (destination/'APLICACION.md').write_text('# Contrato de Stubbs Jobs\n\nLee README.md para el uso cotidiano e INICIO.md para el primer inicio. La IA preselecciona ofertas y la persona elige cuáles solicitar. El agente trabaja desde su chat y consulta el estado actual antes de actuar; guardar en la app no inicia tareas. Si se desea una búsqueda diaria, se programa en ese agente. Al actualizar un encargo en curso mediante apply, usa su --execution-id propio.\n\n## Estado común de las ofertas\n'+offer_states.replace('Jaime','la persona')+'\n## Detalles del contrato de interfaz\n'+interface.replace('Jaime','la persona')+'\n## Contrato del agente\n'+contract.replace('Jaime','la persona')+'\n## Conservación y funcionamiento\n\nLos datos pertenecen a esta instalación. Conserva el registro, los CV y los paquetes; consulta OPERACION.md para el procedimiento.\n\n'+current_actions.replace('Jaime','la persona'),encoding='utf-8')
    (destination/'CLAUDE.md').write_text('Lee AGENTS.md e INICIO.md antes de trabajar. Consulta tools/stubbs_jobs.py agent-status y amplía el caso, encargo o perfil antes de buscar, solicitar o atender cambios. La entrevista inicial guiada por la IA guarda el perfil en el mismo registro que muestra la app. Guardar en la app no inicia tareas.\n',encoding='utf-8')
    (destination/'config').mkdir()
    for name in ('dependencies.json','retention.json'):(destination/'config'/name).write_bytes(source_bytes('config/'+name))
    dependencies=json.loads((destination/'config/dependencies.json').read_text(encoding='utf-8'))
    dependencies['testedVersions']['Python']=python_version
    dependencies['runtime']='runtime/python, Windows x64 portable'
    dependencies['installation']='Included. Node and artifact-tool are optional for XLSX; CSV is always available.'
    (destination/'config/dependencies.json').write_text(json.dumps(dependencies,indent=2),encoding='utf-8')
    (destination/'config/distribution.json').write_text(json.dumps({'version':1,'platform':'Windows x64','initialProfile':'empty','defaultAssistant':'external'}),encoding='utf-8')
    (destination/'config/release.json').write_bytes(source_bytes('config/release.json'))
    (destination/'config/sources.json').write_text('[]',encoding='utf-8')
    (destination/'config/source-provenance.json').write_text(json.dumps({'schemaVersion':1,'sourceFingerprint':source_fingerprint},indent=2),encoding='utf-8')
    (destination/'Abrir Stubbs Jobs.exe').write_bytes(source_bytes('Abrir Stubbs Jobs.exe'))
    shutil.copytree(runtime,destination/'runtime/python',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for empty in ('data','outputs'):(destination/empty).mkdir()
    # No absolute build-machine paths survive wheel entry points.
    scripts=destination/'runtime/python/Lib/site-packages/bin'
    if scripts.exists():
        for file in scripts.iterdir():
            if file.is_file():file.unlink()
        scripts.rmdir()
    if source_identity()!=source_fingerprint:raise ValueError('El código cambió durante la construcción; conserva esta carpeta como diagnóstico y crea una copia nueva')
    manifest={str(p.relative_to(destination)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'config/files.sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    forbidden=('registry.json','app-instance.json','agent-run.json')
    assert not any(p.name in forbidden for p in destination.rglob('*'))
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in destination.rglob('*'):
            if file.is_file():z.write(file,Path(destination.name)/file.relative_to(destination))
    return archive

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);p.add_argument('--runtime',type=Path,default=ROOT/'outputs/distribution-runtime/python')
    args=p.parse_args();print(build(args.destination,args.runtime))
