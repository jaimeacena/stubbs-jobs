"""Exact document associations, receipts, lost files and historical navigation."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import app_workflow as workflow
import stubbs_jobs
import cv_usage
import stubbs_jobs_app as server
from stubbs_jobs_core import digest, identity, now
from workflow_fixtures import WorkflowFixture


class CVUsageTests(WorkflowFixture, unittest.TestCase):
    def test_equivalent_root_can_review_exact_cv_and_still_rejects_an_external_pdf(self):
        root=self.root/'installation';(root/'outputs').mkdir(parents=True)
        (root/'alias').mkdir()
        content=(self.root/'outputs/cv.pdf').read_bytes()
        (root/'outputs/cv.pdf').write_bytes(content)
        (self.root/'outside.pdf').write_bytes(b'%PDF-outside-installation')
        # A non-canonical root models the same comparison as Windows 8.3 names.
        alias=root/'alias'/'..'
        with patch.object(workflow,'ROOT',alias),patch.object(workflow,'DATA',root/'data'),\
             patch.object(stubbs_jobs,'ROOT',alias),patch.object(stubbs_jobs,'DATA',root/'data'):
            self.assertEqual(workflow.cv_bytes(self.row),content)
            self.assertIsNone(workflow.cv_bytes({'CV preparado':'../outside.pdf'}))
            self.review()
            package=workflow.state(self.data)['packages'][-1]
            self.assertEqual(package['payload']['cvHash'],digest(content))
            self.assertEqual(workflow.conserved_package(package)['payload']['cvHash'],digest(content))
            self.assertEqual((root/'data/packages'/package['id']/'cv.pdf').read_bytes(),content)

    def document(self, name='CV de ejemplo.pdf', relative='outputs/cv.pdf'):
        return {'id': digest((self.root / relative).read_bytes()), 'name': name,
                'path': relative, 'url': '/api/document?id=uploaded%3Aexample'}

    def project(self, documents=None):
        return cv_usage.enrich(self.data, documents or [self.document()], self.root, workflow.package_issue)

    def archive(self):
        return workflow.archive(self.data, 'one')

    def receipt(self, package):
        self.data['events'].append({'id': 'receipt', 'type': 'sent', 'opportunityId': 'one',
            'packageId': package['id'], 'cvHash': package['payload']['cvHash'], 'at': now(),
            'confirmation': 'TEST: recibo original de la solicitud ficticia'})

    def test_receipt_replaces_preparation_with_one_direct_offer_link_without_writes(self):
        package = self.archive()
        self.assertEqual(self.project()[0]['usage'][0]['kind'], 'prepared')
        self.receipt(package)
        before = copy.deepcopy(self.data)
        usage = self.project()[0]['usage']
        self.assertEqual(len(usage), 1)
        self.assertEqual((usage[0]['kind'], usage[0]['opportunityId'], usage[0]['packageId']),
                         ('sent', 'one', package['id']))
        self.assertEqual(self.data, before)

    def test_same_name_different_bytes_never_inherits_usage(self):
        self.archive()
        (self.root / 'outputs/other.pdf').write_bytes(b'%PDF-other-version')
        first, other = self.project([self.document(), self.document(relative='outputs/other.pdf')])
        self.assertEqual(first['name'], other['name'])
        self.assertTrue(first['usage'])
        self.assertEqual(other['usage'], [])

    def test_selection_authorization_and_running_are_not_confirmed_sends(self):
        package = self.archive()
        package['approvedAt'] = now()
        self.data['app']['selections']['one'] = {'selected': True, 'mode': 'auto'}
        self.data['app']['requests'].append({'id': 'test', 'opportunityId': 'one',
            'packageId': package['id'], 'type': 'send', 'status': 'running'})
        self.assertEqual(self.project()[0]['usage'][0]['kind'], 'prepared')
        self.data['events'].append({'type': 'sent', 'opportunityId': 'one', 'cvHash': package['payload']['cvHash']})
        self.assertEqual(self.project()[0]['usage'][0]['kind'], 'prepared')

    def test_wrong_offer_or_packet_cannot_turn_preparation_into_a_send(self):
        package = self.archive()
        self.receipt(package)
        self.data['events'][0]['opportunityId'] = 'another'
        self.assertEqual(self.project()[0]['usage'][0]['kind'], 'prepared')
        self.data['events'][0]['opportunityId'] = 'one'
        self.data['events'][0]['packageId'] = 'f' * 64
        self.assertEqual(self.project()[0]['usage'][0]['kind'], 'prepared')

    def test_missing_uploaded_file_retains_its_confirmed_history_and_is_unavailable(self):
        package = self.archive()
        self.receipt(package)
        document = self.document()
        (self.root / 'outputs/cv.pdf').unlink()
        entry = self.project([document])[0]
        self.assertFalse(entry['available'])
        self.assertEqual(entry['usage'][0]['kind'], 'sent')

    def test_damaged_archive_does_not_erase_a_receipt_for_the_unchanged_original_pdf(self):
        package = self.archive()
        self.receipt(package)
        (self.root / 'data/packages' / package['id'] / 'cv.pdf').write_bytes(b'%PDF-damaged')
        self.assertEqual(self.project()[0]['usage'][0]['kind'], 'sent')
        self.data['events'] = []
        self.assertEqual(self.project()[0]['usage'], [])

    def test_historical_hash_and_proof_link_to_history_and_live_canonical_offer(self):
        record = {'id': 'earlier', 'company': 'Example previous', 'title': 'Analyst',
            'state': 'Enviada', 'proof': 'TEST: solicitud anterior comprobada',
            'canonicalKey': identity('https://example.org/jobs/previous'),
            'cvHash': self.document()['id'], 'at': now()}
        self.data['historicalApplications'].append(record)
        self.assertEqual(self.project()[0]['usage'][0]['opportunityId'], 'historical:earlier')
        record['canonicalKey'] = self.row['Clave canónica']
        self.assertEqual(self.project()[0]['usage'][0]['opportunityId'], 'one')
        record.pop('cvHash')
        record['cv'] = 'outputs/cv.pdf'
        self.assertEqual(self.project()[0]['usage'], [])

    def test_unused_legacy_pdf_changes_state_version_and_library_stays_bounded(self):
        # Personal and generic editions retain different legacy filename prefixes.
        # Both aliases are fictional; the catalog must still observe actual bytes.
        legacy = [self.root / 'outputs' / name for name in ('CV-Jaime-TEST.pdf', 'CV-Usuario-TEST.pdf')]
        for path in legacy:
            path.write_bytes(b'%PDF-first')
        with patch.object(server, 'ROOT', self.root):
            first = server.state_version(self.data, brief=True, execution={'status': 'idle'})
            for path in legacy:
                path.write_bytes(b'%PDF-new')
            second = server.state_version(self.data, brief=True, execution={'status': 'idle'})
        self.assertNotEqual(first, second)
        document = self.document()
        document['path'] = '../outside.pdf'
        self.assertFalse(self.project([document])[0]['available'])


if __name__ == '__main__':
    unittest.main()
