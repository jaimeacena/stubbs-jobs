"""Backup and isolated recovery use synthetic data and never read the real registry."""
import copy
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture, fixture
import app_workflow as workflow
import backup
import stubbs_jobs_app as server
import stubbs_jobs_core as core

PROJECT = Path(__file__).resolve().parents[1]


class BackupTests(unittest.TestCase):
    setUp = WorkflowFixture.setUp
    apply = WorkflowFixture.apply
    review = WorkflowFixture.review

    def create(self):
        core.save_store(self.data, self.root / 'data/registry.json')
        return backup.create(self.root)

    def prepare_code(self):
        """A code-only fake installation; the launcher bytes cannot be executed."""
        (self.root / 'LICENSE').write_text('MIT License\nTEST synthetic copyright', encoding='utf-8')
        (self.root / 'Abrir Stubbs Jobs.exe').write_bytes(b'TEST synthetic launcher, not executable')
        for name in ('tools', 'app', 'config'):
            target = self.root / name
            target.mkdir(exist_ok=True)
            for path in (PROJECT / name).glob('*'):
                if path.is_file() and 'conflict' not in path.name.lower() and (name != 'config' or path.name in ('dependencies.json', 'retention.json', 'release.json')):
                    shutil.copy2(path, target / path.name)

    def recovery_destination(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve() / 'recovered-test'

    def test_verified_backup_conserves_profile_and_cv_without_session_data(self):
        (self.root / 'data').mkdir()
        (self.root / 'data/app-instance.json').write_text('TEST private session')
        (self.root / 'data/agent-run.json').write_text('TEST old execution')
        result = self.create()
        verified = backup.verify(Path(result['path']).read_bytes())
        self.assertEqual(verified['data']['profile'], self.data['profile'])
        self.assertEqual(verified['files']['outputs/cv.pdf'], b'%PDF-test-one')
        self.assertNotIn('data/app-instance.json', verified['files'])
        self.assertNotIn('data/agent-run.json', verified['files'])
        self.assertEqual(verified['manifest']['revision'], self.data['revision'])

    def test_backup_preserves_unused_legacy_pdfs_visible_in_personal_or_generic_library(self):
        self.data['sheets']['Oportunidades'] = []
        self.data['app']['cvLibrary'] = []
        self.data['app']['packages'] = []
        self.data['app']['personalized'] = False
        for name in ('CV-Jaime-TEST.pdf', 'CV-Usuario-TEST.pdf'):
            (self.root / 'outputs' / name).write_bytes(b'%PDF-test-one')
        with patch.object(server, 'ROOT', self.root):
            documents = server.cv_library(self.data)
        self.assertTrue(documents)
        self.assertTrue(all(document['usage'] == [] for document in documents))
        verified = backup.verify(Path(self.create()['path']).read_bytes())
        for document in documents:
            self.assertEqual(verified['files'][document['path']], b'%PDF-test-one')
        self.assertNotIn('outputs/cv.pdf', verified['files'])

    def test_mismatched_archive_hash_is_rejected(self):
        result = self.create()
        content = Path(result['path']).read_bytes()
        source = zipfile.ZipFile(io.BytesIO(content))
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as target:
            for name in source.namelist():
                target.writestr(name, b'changed' if name == 'outputs/cv.pdf' else source.read(name))
        with self.assertRaisesRegex(ValueError, 'dañada'):
            backup.verify(out.getvalue())

    def test_archive_with_traversal_or_repeated_case_names_is_rejected(self):
        for names in (('../outside',), ('data/registry.json', 'DATA/REGISTRY.JSON'), ('data/CON.txt',)):
            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as target:
                for name in names:
                    target.writestr(name, '{}')
            with self.assertRaises(ValueError):
                backup.verify(out.getvalue())

    def test_windows_invalid_names_are_rejected_before_creating_a_recovery_folder(self):
        result = self.create()
        valid = backup.verify(Path(result['path']).read_bytes())
        destination = self.recovery_destination()
        for name in ('data/unsafe?.txt', 'data/unsafe*.txt', 'data/unsafe|.txt', 'data/control\x01.txt'):
            files = dict(valid['files'], **{name: b'TEST extra archive'})
            manifest = copy.deepcopy(valid['manifest'])
            manifest['files'][name] = core.digest(files[name])
            content = io.BytesIO()
            with zipfile.ZipFile(content, 'w') as archive:
                for filename, raw in files.items():
                    archive.writestr(filename, raw)
                archive.writestr('stubbs-backup.json', json.dumps(manifest))
            archive_path = self.root / 'TEST-invalid-path.zip'
            archive_path.write_bytes(content.getvalue())
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'rutas'):
                backup.restore(self.root, archive_path, destination)
            self.assertFalse(destination.exists())

    def test_missing_cv_does_not_create_a_partial_backup(self):
        core.save_store(self.data, self.root / 'data/registry.json')
        (self.root / 'outputs/cv.pdf').unlink()
        with self.assertRaisesRegex(ValueError, 'Falta un archivo'):
            backup.create(self.root)
        self.assertFalse((self.root / 'data/backups').exists())

    def test_existing_recovery_destination_and_active_data_are_never_overwritten(self):
        result = self.create()
        original = (self.root / 'data/registry.json').read_bytes()
        destinations = (self.root, self.root.parent, self.root / 'data', self.root / 'data/recovery',
                        self.root / 'app/recovery', self.root / 'config/recovery',
                        self.root / 'runtime/python/recovery', self.root / 'outputs/recovery')
        with patch.object(backup.shutil, 'copytree') as copytree:
            for destination in destinations:
                with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, 'carpeta nueva'):
                    backup.restore(self.root, result['path'], destination)
            copytree.assert_not_called()
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)

    def test_recovery_copy_failure_keeps_diagnostic_without_launcher(self):
        result = self.create()
        self.prepare_code()
        destination = self.recovery_destination()
        original = (self.root / 'data/registry.json').read_bytes()
        with patch.object(backup.shutil, 'copytree', side_effect=OSError('TEST copy failed')):
            with self.assertRaisesRegex(ValueError, 'No abras esa copia'):
                backup.restore(self.root, result['path'], destination)
        self.assertFalse((destination / 'Abrir Stubbs Jobs.exe').exists())
        self.assertIn('TEST copy failed', (destination / 'data/recovery-diagnostic.log').read_text())
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)

    def test_recovery_write_failure_preserves_raw_registry_without_launcher(self):
        result = self.create()
        self.prepare_code()
        destination = self.recovery_destination()
        original = (self.root / 'data/registry.json').read_bytes()
        atomic = backup.atomic_bytes

        def fail_original(path, content):
            if Path(path) == destination / 'data/recovery-original.json':
                raise OSError('TEST original copy failed')
            return atomic(path, content)

        with patch.object(backup, 'atomic_bytes', side_effect=fail_original):
            with self.assertRaisesRegex(ValueError, 'No abras esa copia'):
                backup.restore(self.root, result['path'], destination)
        self.assertEqual((destination / 'data/registry.json').read_bytes(), original)
        self.assertFalse((destination / 'data/recovery-operation.json').exists())
        self.assertFalse((destination / 'Abrir Stubbs Jobs.exe').exists())
        self.assertIn('TEST original copy failed', (destination / 'data/recovery-diagnostic.log').read_text())
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)

    def test_recovery_writer_failure_preserves_evidence_without_launcher(self):
        result = self.create()
        self.prepare_code()
        destination = self.recovery_destination()
        original = (self.root / 'data/registry.json').read_bytes()
        failed = backup.subprocess.CompletedProcess([], 1, stdout='TEST writer output', stderr='TEST writer failure')
        with patch.object(backup.subprocess, 'run', return_value=failed):
            with self.assertRaisesRegex(ValueError, 'No abras esa copia'):
                backup.restore(self.root, result['path'], destination)
        self.assertEqual((destination / 'data/recovery-original.json').read_bytes(), original)
        self.assertTrue((destination / 'data/recovery-operation.json').is_file())
        self.assertFalse((destination / 'Abrir Stubbs Jobs.exe').exists())
        diagnostic = (destination / 'data/recovery-diagnostic.log').read_text()
        self.assertIn('TEST writer output', diagnostic)
        self.assertIn('TEST writer failure', diagnostic)
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)

    def test_recovery_guide_failure_never_publishes_launcher(self):
        result = self.create()
        self.prepare_code()
        destination = self.recovery_destination()
        original = (self.root / 'data/registry.json').read_bytes()
        atomic = backup.atomic_bytes

        def fail_guide(path, content):
            if Path(path) == destination / 'RECUPERACION.txt':
                raise OSError('TEST guide failed')
            return atomic(path, content)

        with patch.object(backup, 'atomic_bytes', side_effect=fail_guide):
            with self.assertRaisesRegex(ValueError, 'No abras esa copia'):
                backup.restore(self.root, result['path'], destination)
        self.assertFalse((destination / 'Abrir Stubbs Jobs.exe').exists())
        self.assertEqual((destination / 'data/recovery-original.json').read_bytes(), original)
        self.assertIn('TEST guide failed', (destination / 'data/recovery-diagnostic.log').read_text())
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)

    def test_recovery_permission_reset_requires_the_original_in_an_isolated_copy(self):
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'copia aislada'):
            self.apply({'kind': 'ui-recover-backup', 'expectedRevision': self.data['revision'], 'proof': 'TEST'})
        self.assertEqual(self.data, before)

    def test_isolated_recovery_preserves_original_and_disarms_old_permissions(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        result = self.create()
        original = (self.root / 'data/registry.json').read_bytes()
        self.prepare_code()
        destination = self.recovery_destination()
        atomic = backup.atomic_bytes

        def verify_activation(path, content):
            if Path(path) == destination / 'Abrir Stubbs Jobs.exe':
                self.assertTrue((destination / 'RECUPERACION.txt').is_file())
                recovered_data = core.read_store(destination / 'data/registry.json')
                self.assertTrue(all(package.get('revokedAt') for package in recovered_data['app']['packages']))
                self.assertTrue(all(item['status'] == 'cancelled' for item in recovered_data['app']['requests'] if item['type'] == 'send'))
                self.assertFalse((destination / 'Abrir Stubbs Jobs.exe').exists())
            return atomic(path, content)

        with patch.object(backup, 'atomic_bytes', side_effect=verify_activation):
            recovered = backup.restore(self.root, result['path'], destination)
        self.assertFalse(recovered['permissionsRestored'])
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)
        self.assertEqual((destination / 'data/recovery-original.json').read_bytes(), original)
        self.assertEqual((destination / 'LICENSE').read_bytes(), (self.root / 'LICENSE').read_bytes())
        data = core.read_store(destination / 'data/registry.json')
        self.assertEqual(data['profile'], self.data['profile'])
        original_rows=self.data['sheets']['Oportunidades']
        restored_rows=data['sheets']['Oportunidades']
        self.assertEqual([row['ID'] for row in restored_rows],[row['ID'] for row in original_rows])
        self.assertEqual([{k:v for k,v in row.items() if k not in ('Estado','Siguiente paso')} for row in restored_rows],
                         [{k:v for k,v in row.items() if k not in ('Estado','Siguiente paso')} for row in original_rows])
        self.assertTrue(all(package.get('revokedAt') for package in data['app']['packages']))
        self.assertNotIn('review',data['app']['drafts']['one'])
        self.assertTrue(data['app']['drafts']['one']['recoveryReviews'])
        self.assertTrue(all(item['status'] == 'cancelled' for item in data['app']['requests'] if item['type'] == 'send'))
        self.assertEqual(data['app']['selections']['one']['mode'], 'review')
        self.assertEqual((destination / 'outputs/cv.pdf').read_bytes(), b'%PDF-test-one')
        self.assertTrue((destination / 'RECUPERACION.txt').is_file())
        self.assertEqual((destination / 'Abrir Stubbs Jobs.exe').read_bytes(), (self.root / 'Abrir Stubbs Jobs.exe').read_bytes())

    def test_restore_preserves_draft_but_requires_access_from_a_new_chat(self):
        app = workflow.state(self.data)
        app.update(setupComplete=False, onboarding={'token': 'old', 'revision': 7, 'status': 'preparing', 'executionId': 'old-chat', 'draft': {'values': {'name': 'TEST'}, 'experience': 'TEST'}})
        core.save_store(self.data,self.root/'data/registry.json')
        original=(self.root/'data/registry.json').read_bytes()
        (self.root/'data/recovery-original.json').write_bytes(original)
        self.apply({'kind': 'ui-recover-backup', 'expectedRevision': self.data['revision'], 'originalHash':core.digest(original),'proof': 'TEST restored copy'})
        setup = workflow.state(self.data)['onboarding']
        self.assertEqual(setup['draft'], {'values': {'name': 'TEST'}, 'experience': 'TEST'})
        self.assertNotEqual(setup['token'], 'old')
        self.assertEqual(setup['revision'], 8)
        self.assertEqual(setup['status'], 'waiting')
        self.assertNotIn('executionId', setup)


if __name__ == '__main__':
    unittest.main()
