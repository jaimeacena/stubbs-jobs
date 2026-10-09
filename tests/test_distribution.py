"""Safety checks for creating a portable copy without touching existing files."""
import runpy
import ast
import re
import json
import hashlib
import shutil
import struct
from unittest.mock import patch,Mock
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SHARE = runpy.run_path(str(PROJECT / 'tools/build-share.py'))
BUILD = SHARE['build']
SOURCE = runpy.run_path(str(PROJECT / 'tools/build-source.py'))


class ReleaseIdentityTests(unittest.TestCase):
    def read_identity(self, version, channel):
        info=json.loads((PROJECT/'config/release.json').read_text(encoding='utf-8'))
        info.update(version=version,channel=channel)
        files={'config/release.json':json.dumps(info),
               'app/release.js':'window.StubbsJobsRelease = Object.freeze('+json.dumps(info,ensure_ascii=False,separators=(',',':'))+');\n'}
        return SHARE['release_metadata'](files.__getitem__)

    def test_stable_and_historical_beta_keep_matching_visible_identity(self):
        for version,channel in [('1.0.0','stable'),('0.1.0-beta.4','beta')]:
            with self.subTest(version=version):
                self.assertEqual(self.read_identity(version,channel)['version'],version)

    def test_mismatched_channels_and_malformed_versions_cannot_be_distributed(self):
        for version,channel in [('1.0.0','beta'),('1.0.0-beta.1','stable'),('01.0.0','stable'),
                                ('1.0.0-extra','stable'),('1.0','stable'),(None,'stable'),('1.0.0','other')]:
            with self.subTest(version=version,channel=channel):
                with self.assertRaisesRegex(ValueError,'identidad'):
                    self.read_identity(version,channel)


class SourceDependencyTests(unittest.TestCase):
    def test_public_tests_include_their_local_python_dependencies(self):
        shipped = {Path(name).stem for name in SHARE['SOURCE_TESTS'] if name.endswith('.py')}
        local = {path.stem for path in (PROJECT / 'tests').glob('*.py')}
        for name in shipped:
            tree = ast.parse((PROJECT / 'tests' / (name + '.py')).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                imports = ([item.name.split('.')[0] for item in node.names] if isinstance(node, ast.Import)
                           else [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
                for dependency in imports:
                    if dependency in local:
                        self.assertIn(dependency, shipped, name + ' imports ' + dependency)

def synthetic_source(destination):
    """Only packaging inputs, with a test notice instead of a real license choice."""
    names=['tools/'+name for name in SHARE['MODULES']]
    names+=['app/'+name for name in SHARE['APP_FILES']]+['app/assets/'+name for name in SHARE['APP_ASSETS']]
    names+=['distribution/'+name for name in SHARE['DOCUMENTS'] if name!='LICENSE']
    names+=['APLICACION.md','Abrir Stubbs Jobs.exe','config/dependencies.json','config/retention.json','config/release.json']
    for name in names:
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PROJECT/name,target)
    notice=(PROJECT/'distribution/LICENSE').read_text(encoding='utf-8')
    notice=notice.replace('jaimeacena (https://github.com/jaimeacena)','Persona ficticia de prueba')
    (destination/'distribution/LICENSE').write_text(notice,encoding='utf-8')
    return destination


def ico_images(raw):
    reserved,kind,count=struct.unpack_from('<HHH',raw)
    if reserved!=0 or kind!=1 or not count:raise ValueError('No es un icono ICO válido')
    images=[]
    for index in range(count):
        width,height,colors,reserved,planes,bits,size,offset=struct.unpack_from('<BBBBHHII',raw,6+16*index)
        if reserved or offset<6+16*count or size==0 or offset+size>len(raw):
            raise ValueError('Imagen ICO fuera del archivo')
        images.append({'width':width or 256,'height':height or 256,'bytes':raw[offset:offset+size]})
    return images


def pe_resources(raw):
    """Read Windows resources as bytes without starting the executable."""
    if raw[:2]!=b'MZ':raise ValueError('No es un ejecutable Windows')
    pe=struct.unpack_from('<I',raw,0x3c)[0]
    if raw[pe:pe+4]!=b'PE\x00\x00':raise ValueError('Cabecera PE no válida')
    section_count=struct.unpack_from('<H',raw,pe+6)[0]
    optional_size=struct.unpack_from('<H',raw,pe+20)[0]
    optional=pe+24
    magic=struct.unpack_from('<H',raw,optional)[0]
    directory=optional+{0x10b:96,0x20b:112}[magic]
    resource_rva,resource_size=struct.unpack_from('<II',raw,directory+16)
    if not resource_rva or not resource_size:return {}
    sections=[]
    for index in range(section_count):
        at=optional+optional_size+index*40
        virtual_size,address,size,pointer=struct.unpack_from('<IIII',raw,at+8)
        sections.append((address,max(virtual_size,size),pointer))
    def file_offset(rva):
        for address,size,pointer in sections:
            if address<=rva<address+size:return pointer+rva-address
        raise ValueError('Recurso fuera de las secciones PE')
    resource=file_offset(resource_rva)
    result={}
    def visit(relative,path):
        if relative>=resource_size or len(path)>3:raise ValueError('Directorio de recursos no válido')
        named,numbered=struct.unpack_from('<HH',raw,resource+relative+12)
        for index in range(named+numbered):
            name,target=struct.unpack_from('<II',raw,resource+relative+16+index*8)
            if name&0x80000000:
                at=resource+(name&0x7fffffff);length=struct.unpack_from('<H',raw,at)[0]
                name=raw[at+2:at+2+length*2].decode('utf-16le')
            child=path+(name,)
            if target&0x80000000:visit(target&0x7fffffff,child)
            else:
                rva,size=struct.unpack_from('<II',raw,resource+target)
                start=file_offset(rva)
                if start+size>len(raw):raise ValueError('Contenido de recurso truncado')
                result[child]=raw[start:start+size]
    visit(0,())
    return result


class DistributionSafetyTests(unittest.TestCase):
    def setUp(self):
        # These fixtures exercise packaging with an intentionally empty runtime.
        # Runtime identity is tested separately with the real probe contract.
        runtime_check=patch.dict(BUILD.__globals__,{'inspect_portable_runtime':Mock(return_value='3.14.7')})
        runtime_check.start()
        self.addCleanup(runtime_check.stop)

    def test_generated_python_tests_preserve_valid_line_continuations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            runtime = root / 'runtime'
            runtime.mkdir()
            portable = root / 'portable'
            BUILD(portable, runtime)
            SOURCE['build'](portable, root / 'source')
            for path in (root / 'source/tests').glob('*.py'):
                with self.subTest(file=path.name):
                    self.assertFalse(b'\r\r\n' in path.read_bytes(), 'Saltos de línea duplicados: ' + path.name)
                    ast.parse(path.read_text(encoding='utf-8'), filename=path.name)

    def test_launcher_embeds_the_current_multisize_icon_without_running(self):
        images=ico_images((PROJECT/'app/assets/stubbs.ico').read_bytes())
        self.assertEqual({(item['width'],item['height']) for item in images},
                         {(size,size) for size in (16,20,24,32,40,48,64,128,256)})
        resources=pe_resources((PROJECT/'Abrir Stubbs Jobs.exe').read_bytes())
        groups=[raw for key,raw in resources.items() if key[0]==14]
        self.assertTrue(groups,'El ejecutable no contiene un icono Windows')
        for group in groups:
            self.assertEqual(struct.unpack_from('<HHH',group),(0,1,len(images)))
            embedded=[]
            for index in range(len(images)):
                width,height,colors,reserved,planes,bits,size,identifier=struct.unpack_from('<BBBBHHIH',group,6+14*index)
                candidates=[raw for key,raw in resources.items() if key[:2]==(3,identifier)]
                self.assertEqual(len(candidates),1)
                self.assertEqual(len(candidates[0]),size)
                embedded.append({'width':width or 256,'height':height or 256,'bytes':candidates[0]})
            self.assertEqual(embedded,images,'El EXE conserva un logo distinto al ICO distribuido')

    def test_generated_document_reading_copies_preserve_original_newlines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';BUILD(portable,runtime)
            source=root/'source';SOURCE['build'](portable,source)
            for name in ('APLICACION.md','CLAUDE.md','perfil.md'):
                reading=source/'distribution'/name
                with self.subTest(file=name):
                    self.assertNotIn(b'\r\r\n',reading.read_bytes())
                    self.assertEqual(reading.read_text(encoding='utf-8').split('\n\n',1)[1],
                                     (portable/name).read_text(encoding='utf-8'))

    def test_icon_changes_origin_identity_and_rejects_old_portable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';BUILD(portable,runtime)
            identity=SOURCE['SHARE']['source_identity']
            other=root/'another-source-tree'
            for name,value in SHARE['source_input_hashes']().items():
                if value is not None:
                    target=other/name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes((PROJECT/name).read_bytes())
            original=identity()
            icon=other/'app/assets/stubbs.ico'
            icon.write_bytes(icon.read_bytes()+b'TEST: icon changed')
            with patch.dict(identity.__globals__,{'ROOT':other}):
                self.assertNotEqual(identity(),original)
                with self.assertRaisesRegex(ValueError,'otra revisión'):
                    SOURCE['build'](portable,root/'source')
            self.assertFalse((root/'source').exists())

    def test_portable_and_source_preserve_exact_icon_and_logo(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';archive=BUILD(portable,runtime)
            source=root/'source';source_archive=SOURCE['build'](portable,source)
            for bundle,directory in ((archive,portable),(source_archive,source)):
                with zipfile.ZipFile(bundle) as zipped:
                    for name in ('stubbs.png','stubbs.ico'):
                        expected=(PROJECT/'app/assets'/name).read_bytes()
                        self.assertEqual((directory/'app/assets'/name).read_bytes(),expected)
                        self.assertEqual(zipped.read(directory.name+'/app/assets/'+name),expected)
                manifest_name='files.sha256.json' if directory==portable else 'source-files.sha256.json'
                manifest=json.loads((directory/'config'/manifest_name).read_text())
                self.assertEqual(manifest['app/assets/stubbs.ico'],hashlib.sha256((PROJECT/'app/assets/stubbs.ico').read_bytes()).hexdigest())

    def test_transient_source_change_cannot_claim_the_original_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            source=synthetic_source(root/'source')
            original=Path.read_bytes;reads=0
            def changing_read(path):
                nonlocal reads
                raw=original(path)
                if path==source/'tools/app_workflow.py':
                    reads+=1
                    # The origin is unchanged again at the final identity check.
                    if reads==2:return raw+b'\n# TEST transient revision\n'
                return raw
            with patch.dict(BUILD.__globals__,{'ROOT':source}),patch.object(Path,'read_bytes',changing_read):
                with self.assertRaisesRegex(ValueError,'cambió durante'):
                    BUILD(root/'portable',runtime)
            self.assertFalse(Path(str(root/'portable')+'.zip').exists())

    def test_unlisted_portable_input_is_never_copied_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';BUILD(portable,runtime)
            path=portable/'config/files.sha256.json'
            manifest=json.loads(path.read_text());manifest.pop('app/app.js');path.write_text(json.dumps(manifest))
            (portable/'app/app.js').write_text('TEST: unverified input')
            with self.assertRaisesRegex(ValueError,'no acredita este archivo'):
                SOURCE['build'](portable,root/'source')
            self.assertFalse((root/'source').exists())

    def test_portable_change_between_validation_and_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';BUILD(portable,runtime)
            original=Path.read_bytes;reads=0
            def changing_read(path):
                nonlocal reads
                raw=original(path)
                if path==portable/'app/app.js':
                    reads+=1
                    if reads>1:return raw+b'\nTEST changed during copy\n'
                return raw
            with patch.object(Path,'read_bytes',changing_read):
                with self.assertRaisesRegex(ValueError,'portable cambió durante'):
                    SOURCE['build'](portable,root/'source')
            self.assertFalse(Path(str(root/'source')+'.zip').exists())

    def test_source_builder_requires_the_exact_origin_revision_not_just_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable'
            BUILD(portable,runtime)
            source_build=SOURCE['build']
            identity=SOURCE['SHARE']['source_identity']
            other=root/'another-source-tree'
            for name,value in SHARE['source_input_hashes']().items():
                if value is not None:
                    target=other/name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes((PROJECT/name).read_bytes())
            path=other/'tools/app_workflow.py'
            path.write_bytes(path.read_bytes()+b'\n# TEST: another source revision, same release\n')
            with patch.dict(identity.__globals__,{'ROOT':other}):
                with self.assertRaisesRegex(ValueError,'otra revisión'):
                    source_build(portable,root/'source')
            self.assertFalse((root/'source').exists())

    def test_source_builder_rejects_legacy_without_origin_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';BUILD(portable,runtime)
            path=portable/'config/source-provenance.json';path.unlink()
            manifest_path=portable/'config/files.sha256.json'
            manifest=json.loads(manifest_path.read_text());manifest.pop('config/source-provenance.json')
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'revisión de origen'):
                SOURCE['build'](portable,root/'source')
            self.assertFalse((root/'source').exists())

    def test_portable_and_source_share_origin_and_all_public_protocols(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';BUILD(portable,runtime)
            SOURCE['build'](portable,root/'source')
            provenance=json.loads((portable/'config/source-provenance.json').read_text())
            self.assertEqual(provenance,json.loads((root/'source/config/source-provenance.json').read_text()))
            for name in ('AGENTE.md','SISTEMA.md','PLAN-SISTEMA.md','algoritmo-busqueda.md'):
                self.assertEqual((portable/name).read_bytes(),(root/'source'/name).read_bytes())
            interface=(PROJECT/'APLICACION.md').read_text(encoding='utf-8').split('## Detalles del contrato de interfaz',1)[1].split('## Contrato del agente',1)[0].replace('Jaime','la persona')
            for bundle in (portable,root/'source'):
                contract=(bundle/'APLICACION.md').read_text(encoding='utf-8')
                self.assertIn(interface,contract)
                self.assertIn('## Estado común de las ofertas',contract)
                self.assertIn('## Cierre y revisión de ofertas',contract)
                self.assertIn('## Vigencia de cifras y pruebas',contract)
                self.assertIn('interpretationOnly',contract)
            self.assertTrue((root/'source/tests/test_system_contracts.py').is_file())
            self.assertTrue((root/'source/tests/test_fresh_audit.py').is_file())
            self.assertTrue((root/'source/tests/test_export_tracker.py').is_file())
            self.assertTrue((root/'source/tests/test_review_corrections.py').is_file())
            self.assertTrue((root/'source/tests/test_minimums.py').is_file())
            for document in (root/'source').rglob('*.md'):
                name=document.relative_to(root/'source').as_posix()
                links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',document.read_text(encoding='utf-8'))
                for link in links:
                    if '://' not in link and not link.startswith('#'):
                        self.assertTrue((document.parent/link.split('#')[0]).is_file(),(name,link))

    def test_source_change_during_copy_is_not_published_as_another_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            portable=root/'portable';BUILD(portable,runtime)
            identity=SOURCE['SHARE']['source_identity']
            original=identity()
            with patch.dict(SOURCE['SHARE'],{'source_identity':Mock(side_effect=[original,'changed'])}):
                with self.assertRaisesRegex(ValueError,'cambió durante'):
                    SOURCE['build'](portable,root/'source')
            self.assertFalse(Path(str(root/'source')+'.zip').exists())

    def test_public_builder_preserves_release_rendering(self):
        text=SOURCE['generic_builder']((PROJECT/'tools/build-share.py').read_text(encoding='utf-8'))
        namespace={'__file__':str(PROJECT/'tools/build-share.py'),'__name__':'generic_builder_test'}
        exec(compile(text,'generic-build-share.py','exec'),namespace)
        self.assertEqual(namespace['render_document']('{{RELEASE_VERSION}}',SHARE['release_metadata']()),SHARE['release_metadata']()['version'])

    def test_initial_interview_instructions_match_portable_source(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / 'INICIO.md').read_text(encoding='utf-8'),
                         (root / 'distribution/INICIO.md').read_text(encoding='utf-8'))

    def test_existing_zip_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            runtime = root / 'runtime'
            runtime.mkdir()
            destination = root / 'share'
            archive = destination.with_suffix('.zip')
            archive.write_bytes(b'existing copy')
            with self.assertRaisesRegex(ValueError, 'ZIP nuevos'):
                BUILD(destination, runtime)
            self.assertEqual(archive.read_bytes(), b'existing copy')
            self.assertFalse(destination.exists())

    def test_destination_cannot_be_inside_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'runtime'
            runtime.mkdir()
            destination = runtime / 'share'
            with self.assertRaisesRegex(ValueError, 'dentro del runtime'):
                BUILD(destination, runtime)
            self.assertFalse(destination.exists())

    def test_versioned_zip_name_keeps_version_and_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();runtime=root/'runtime';runtime.mkdir()
            source=synthetic_source(root/'source')
            destination=root/'Stubbs-Jobs-0.1.0-beta.1-Windows-x64'
            with patch.dict(BUILD.__globals__,{'ROOT':source}):
                archive=BUILD(destination,runtime)
            self.assertEqual(archive.name,destination.name+'.zip')
            self.assertTrue(archive.is_file())

    def test_portable_copy_only_contains_approved_interface_and_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            runtime = root / 'runtime'
            runtime.mkdir()
            source = synthetic_source(root / 'source')
            with patch.dict(BUILD.__globals__,{'ROOT':source}):
                archive = BUILD(root / 'share', runtime)
            with zipfile.ZipFile(archive) as file:
                names = set(file.namelist())
                manifest = json.loads(file.read('share/config/files.sha256.json'))
                self.assertTrue(all(hashlib.sha256(file.read('share/'+name)).hexdigest()==value for name,value in manifest.items()))
                release = json.loads(file.read('share/config/release.json'))
                self.assertIn(release['version'],file.read('share/README.md').decode())
                self.assertIn(release['version'],file.read('share/CHANGELOG.md').decode())
                self.assertNotIn('{{RELEASE_',file.read('share/README.md').decode())
                self.assertIn("WORKBOOK = ROOT / 'outputs/busqueda-empleo.xlsx'",file.read('share/tools/stubbs_jobs_core.py').decode())
            self.assertIn('share/app/redesign.css', names)
            self.assertIn('share/app/release.js', names)
            self.assertIn('share/LICENSE', names)
            self.assertIn('share/LIMITES.md', names)
            self.assertIn('share/perfil.md', names)
            self.assertNotIn('share/app/app.css', names)
            self.assertNotIn('share/profile-template.md', names)
            self.assertFalse(any('[conflicted' in name for name in names))


if __name__ == '__main__':
    unittest.main()
