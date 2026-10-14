"""Fictional CV retirement: prospective use, historical bytes and conflicts."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import app_workflow as workflow
import backup
import cv_retirement
import cv_usage
import stubbs_jobs
import stubbs_jobs_app as server
from stubbs_jobs_core import digest, now
from workflow_fixtures import WorkflowFixture


class CVRetirementTests(WorkflowFixture, unittest.TestCase):
    def register(self, path='outputs/cv.pdf'):
        content = (self.root / path).read_bytes()
        registered_path = 'outputs/cv/' + digest(content) + '.pdf'
        (self.root / registered_path).parent.mkdir(exist_ok=True)
        (self.root / registered_path).write_bytes(content)
        self.row['CV preparado'] = registered_path
        entry = {'id': digest(content), 'name': Path(path).name, 'path': registered_path}
        self.data['app'].setdefault('cvLibrary', []).append(entry)
        return entry

    def operation(self, entry):
        return {'kind': 'ui-cv-retire', 'expectedRevision': self.data['revision'],
                'documents': [{'path': entry['path'], 'fingerprint': entry['id']}],
                'reason': 'TEST: sustituido por el nuevo CV confirmado'}

    def test_retirement_removes_prospective_document_but_preserves_exact_history(self):
        entry = self.register()
        package = workflow.archive(self.data, 'one')
        self.data['events'].append({'id': 'TEST-receipt', 'type': 'sent', 'opportunityId': 'one',
            'packageId': package['id'], 'cvHash': entry['id'], 'at': now(), 'confirmation': 'TEST receipt'})
        original_package = copy.deepcopy(package)
        original_bytes = (self.root / entry['path']).read_bytes()
        self.apply(self.operation(entry))
        self.assertEqual(self.data['app']['packages'][0], original_package)
        self.assertEqual((self.root / entry['path']).read_bytes(), original_bytes)
        self.assertIn(entry['path'], backup.references(self.data))
        with patch.object(server, 'ROOT', self.root), patch.object(server, 'DATA', self.root / 'data'), patch.object(server, 'read_store', return_value=self.data):
            self.assertEqual(server.cv_library(self.data), [])
            self.assertEqual(server.doc_path('uploaded:' + entry['id']).read_bytes(), original_bytes)
            self.assertEqual(server.doc_path('package:' + package['id']).read_bytes(), original_bytes)
        history = cv_usage.enrich(self.data, [entry], self.root, workflow.package_issue)
        self.assertEqual(history[0]['usage'][0]['kind'], 'sent')
        self.assertIn('Sustituir el CV retirado por una versión vigente', workflow.missing(self.data, 'one'))
        with self.assertRaisesRegex(ValueError, 'retirado'):
            workflow.archive(self.data, 'one')

    def test_exact_legacy_document_is_hidden_without_losing_read_access_or_backup(self):
        path = 'outputs/CV-Usuario-TEST-old.pdf'
        (self.root / path).write_bytes(b'%PDF-TEST-old')
        entry = {'id': digest((self.root / path).read_bytes()), 'path': path}
        self.apply(self.operation(entry))
        self.assertIn(path, backup.references(self.data))
        with patch.object(server, 'ROOT', self.root), patch.object(server, 'read_store', return_value=self.data):
            self.assertFalse(any(d['path'] == path for d in server.cv_library(self.data)))
            self.assertEqual(server.doc_path('library:' + Path(path).name), self.root / path)

    def test_restore_is_explicit_and_never_recovers_old_sending_permission(self):
        entry = self.register()
        package = workflow.archive(self.data, 'one')
        package['approvedAt'] = now()
        self.data['app']['requests'].append({'id': 'TEST-send', 'type': 'send', 'status': 'queued',
                                            'packageId': package['id'], 'opportunityId': 'one'})
        self.apply(self.operation(entry))
        self.assertTrue(self.data['app']['packages'][0]['revokedAt'])
        self.assertEqual(self.data['app']['requests'][0]['status'], 'cancelled')
        with patch('pypdfium2.PdfDocument') as reader:
            reader.return_value.__len__.return_value = 1
            with self.assertRaisesRegex(ValueError, 'retirado'):
                stubbs_jobs.import_cv(self.data, 'TEST.pdf', b'%PDF-test-one')
        revoked = self.data['app']['packages'][0]['revokedAt']
        self.apply({'kind': 'ui-cv-restore', 'expectedRevision': self.data['revision'],
                    'fingerprints': [entry['id']], 'reason': 'TEST: recuperación expresa'})
        self.assertFalse(cv_retirement.retired(self.data, entry['id']))
        self.assertEqual(self.data['app']['packages'][0]['revokedAt'], revoked)
        self.assertEqual(self.data['app']['requests'][0]['status'], 'cancelled')

    def test_conflict_unknown_path_and_changed_bytes_roll_back_entire_operation(self):
        entry = self.register()
        for modification in [lambda op: op.update(expectedRevision=99),
                             lambda op: op['documents'][0].update(path='../outside.pdf'),
                             lambda op: op['documents'][0].update(fingerprint='f' * 64)]:
            op = self.operation(entry)
            modification(op)
            before = copy.deepcopy(self.data)
            with self.assertRaises(ValueError):
                self.apply(op)
            self.assertEqual(self.data, before)
        (self.root / entry['path']).write_bytes(b'%PDF-changed')
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'ha cambiado'):
            self.apply(self.operation(entry))
        self.assertEqual(self.data, before)

    def test_running_send_protects_all_cv_changes_and_retirement_does_not_start_work(self):
        entry = self.register()
        self.data['app']['requests'].append({'id': 'TEST-running', 'type': 'send', 'status': 'running'})
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'envío en curso'):
            self.apply(self.operation(entry))
        self.assertEqual(self.data, before)
        self.data['app']['requests'] = []
        self.apply(self.operation(entry))
        self.assertEqual(self.data['app']['requests'], [])
        self.assertEqual(self.data['events'], [])

    def test_absent_retirement_metadata_needs_no_migration_or_profile_write(self):
        entry = self.register()
        before = copy.deepcopy(self.data)
        with patch.object(server, 'ROOT', self.root):
            self.assertEqual(server.cv_library(self.data)[0]['id'], entry['id'])
        cv_retirement.validate(self.data)
        self.assertEqual(self.data, before)


if __name__ == '__main__':
    unittest.main()
