"""Fresh boundary cases: fictional offers and documents in isolated folders."""
import copy
import unittest
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import app_workflow as workflow
import backup
import cv_usage
import offer_minimums
import personalization
import stubbs_jobs_core as core
import stubbs_jobs_app as server


class PreservationEdgesTests(WorkflowFixture, unittest.TestCase):
    def test_schedule_separators_do_not_turn_explicit_minimum_failures_into_options(self):
        for field, value in (
            ('Modalidad', 'Híbrido — 2 días/semana en oficina, 3 remoto'),
            ('Modalidad', 'Híbrido con turno de mañana o tarde y trabajo remoto 2 días'),
            ('Modalidad', 'Híbrido: 3 días presencial / remoto 2 días'),
            ('Modalidad', 'Híbrido (3 días presencial / remoto 2 días)'),
            ('Modalidad', 'Presencial — trabajo remoto posible más adelante'),
            ('Contrato', 'Temporal — 6 meses / posibilidad de indefinido'),
            ('Contrato', 'Temporal (6 meses) / indefinido al terminar'),
            ('Contrato', 'Temporal / indefinido al terminar los 6 meses'),
        ):
            with self.subTest(field=field, value=value):
                self.setUp()
                self.data['app']['searchContext'] = {'workMode': '100 % remoto'}
                self.data['app']['criteria'] = {'contract': 'Indefinido'}
                self.apply({'kind': 'opportunity', 'id': 'one', 'values': {field: value},
                            'proof': 'TEST: categoría y detalle explícitos en el anuncio ficticio.'})
                decision = offer_minimums.view(self.data, workflow.row_for(self.data, 'one'))
                self.assertFalse(decision['canApply'])
                self.assertEqual(workflow.archived(self.data, 'one')['source'], 'minimums')

    def test_actual_categorical_alternatives_remain_available(self):
        for value, kind in (
            ('Remoto / Híbrido', 'mode'), ('Remoto desde España o híbrido en Madrid', 'mode'),
            ('Remoto (España) / Híbrido (Madrid)', 'mode'),
            ('Remoto desde España, 100 % remoto o híbrido en Madrid', 'mode'),
            ('Indefinido o temporal', 'contract'), ('Temporal / Indefinido', 'contract'),
        ):
            with self.subTest(value=value):
                self.assertEqual(len(offer_minimums.categories(value, kind)), 2)

    def test_only_connected_current_categories_form_the_options(self):
        self.assertEqual(offer_minimums.categories('Híbrido o presencial. Posible remoto en el futuro', 'mode'),
                         {'hybrid', 'onsite'})
        self.assertEqual(offer_minimums.categories('Temporal / indefinido tras 6 meses', 'contract'),
                         {'temporary'})

    def test_backup_preserves_previous_sent_and_historical_document_references(self):
        paths = ['outputs/previous-sent.pdf', 'outputs/previous-archived.pdf',
                 'outputs/historical.pdf']
        for index, name in enumerate(paths):
            (self.root / name).write_bytes(b'%PDF-fictional-' + str(index).encode())
        self.row['CV usado'] = paths[0]
        self.data['events'] = [{'id': 'TEST-old-receipt', 'type': 'sent', 'opportunityId': 'one',
                                'cv': paths[0], 'archivedCV': paths[1], 'at': core.now(),
                                'confirmation': 'TEST original receipt', 'proof': 'TEST'}]
        self.data['historicalApplications'] = [{'id': 'TEST-history', 'company': 'TEST prior',
            'url': 'https://example.org/prior', 'state': 'Enviada', 'proof': 'TEST', 'cv': paths[2]}]
        core.save_store(self.data, self.root / 'data/registry.json')
        original = (self.root / 'data/registry.json').read_bytes()
        result = backup.create(self.root)
        verified = backup.verify((self.root / 'data/backups' / result['name']).read_bytes())
        for name in paths:
            self.assertEqual(verified['files'][name], (self.root / name).read_bytes())
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)

    def test_backup_explains_a_missing_previously_sent_document(self):
        self.row['CV usado'] = 'outputs/missing-sent.pdf'
        core.save_store(self.data, self.root / 'data/registry.json')
        with self.assertRaisesRegex(ValueError, 'missing-sent.pdf'):
            backup.create(self.root)

    def test_generic_legacy_pdf_is_visible_openable_and_backed_up(self):
        name = 'CV-Usuario-ficticio.pdf'
        (self.root / 'outputs' / name).write_bytes(b'%PDF-TEST generic legacy')
        core.save_store(self.data, self.root / 'data/registry.json')
        with patch.object(server, 'ROOT', self.root), patch.object(server, 'read_store', return_value=self.data):
            library = server.cv_library(self.data)
            self.assertIn(name, [document['name'] for document in library])
            self.assertEqual(server.doc_path('library:' + name).read_bytes(), b'%PDF-TEST generic legacy')
        result = backup.create(self.root)
        verified = backup.verify((self.root / 'data/backups' / result['name']).read_bytes())
        self.assertIn('outputs/' + name, verified['files'])

    def test_manual_addition_rejects_a_legacy_linkedin_alias_without_adding_work(self):
        self.row.update({'Clave canónica': 'url:TEST-legacy',
                         'URL original': 'https://www.linkedin.com/jobs/view/1234567890'})
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'ya está guardada'):
            self.apply({'kind': 'ui-add-opportunity', 'values': {'company': 'TEST Example',
                        'title': 'TEST Analyst', 'url': 'https://es.linkedin.com/jobs/view/test-1234567890/'}})
        self.assertEqual(self.data, before)

    def test_history_alias_uses_the_current_offer_without_rewriting_saved_identity(self):
        self.row.update({'Clave canónica': 'url:TEST-legacy',
                         'URL original': 'https://www.linkedin.com/jobs/view/1234567890'})
        self.data['updatedAt'] = core.now()
        self.data['historicalApplications'] = [{'id': 'TEST-history', 'company': 'TEST Example',
            'title': 'TEST Analyst', 'state': 'Enviada', 'proof': 'TEST receipt',
            'url': 'https://es.linkedin.com/jobs/view/test-1234567890/',
            'canonicalKey': 'url:TEST-another-legacy', 'cvHash': core.digest(b'%PDF-test-one')}]
        before = copy.deepcopy(self.data)
        with patch.object(server, 'ROOT', self.root), patch.object(personalization, 'public_sources', return_value=[]):
            projected = server.build_state(copy.deepcopy(self.data), include_export=False,
                                           include_instructions=False, execution={'status': 'idle'})
        self.assertEqual(projected['opportunities'][0]['canonicalKey'], projected['historical'][0]['canonicalKey'])
        documents = [{'name': 'TEST', 'path': 'outputs/cv.pdf'}]
        usage = cv_usage.enrich(self.data, documents, self.root, lambda package: None)[0]['usage']
        self.assertEqual([item['opportunityId'] for item in usage], ['one'])
        self.assertEqual(self.data, before)
