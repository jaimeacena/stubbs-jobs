"""Complete fictional journeys through the writer, persisted records and recovery.

No portal, real registry, employment operation or executable launcher is used.
"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import test_backup as backup_cases
import agent_runner
import app_context
import app_workflow as w
import backup
import criteria_preview
import offer_quality
import personalization
import stubbs_jobs as jobs
import stubbs_jobs_core as core


class ClosingFlowsTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for module, name, value in ((agent_runner, 'read_state', {'status': 'idle'}),
                                    (agent_runner, 'view', {'status': 'idle'}),
                                    (personalization, 'public_sources', [])):
            replacement = patch.object(module, name, return_value=value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.data['app'].update(setupComplete=True, personalized=True,
                                searchContext={**personalization.CONTEXT, 'name': 'Persona ficticia',
                                               'targetRoles': 'Analista BI', 'workMode': 'Remoto',
                                               'currency': 'EUR'},
                                experience='- Automaticé un informe ficticio con Power Query.')
        self.store = self.root / 'data/registry.json'
        core.save_store(self.data, self.store)
        self.reload()

    def reload(self):
        self.data = core.read_store(self.store)
        self.row = self.data['sheets']['Oportunidades'][0]

    def commit(self, batch):
        # Same lock, writer and compare-before-save as the product, followed by
        # a fresh read. Failures must leave both the registry and packages intact.
        with core.lock(self.root / 'data'):
            current = core.read_store(self.store)
            changed = jobs.apply_batch(current, batch)
            if changed:
                core.save_store(current, self.store)
        self.reload()
        return changed

    def apply(self, operation):
        self.index += 1
        return self.commit({'id': 'TEST-closing-' + str(self.index), 'operations': [operation]})

    def task(self, identifier):
        return next(r for r in self.data['app']['requests'] if r['id'] == identifier)

    def package_files(self):
        base = self.root / 'data/packages'
        return {p.relative_to(base).as_posix(): core.digest(p.read_bytes())
                for p in base.rglob('*') if p.is_file()}

    def reject(self, operation, message=None):
        original = self.store.read_bytes()
        packages = self.package_files()
        with self.assertRaisesRegex(ValueError, message or '.'):
            self.apply(operation)
        self.assertEqual(self.store.read_bytes(), original)
        self.assertEqual(self.package_files(), packages)
        self.reload()

    def choose(self, mode='review'):
        with w.interface_writer():
            self.apply({'kind': 'ui-select-opportunity', 'opportunityId': 'one',
                        'selected': True, 'mode': mode, 'expected': None})
        return next(r['id'] for r in self.data['app']['requests']
                    if r.get('opportunityId') == 'one' and r['status'] == 'queued')

    def draft(self, **values):
        old = w.draft(self.data, 'one')
        self.apply({'kind': 'ui-draft', 'opportunityId': 'one', 'values': values,
                    'expected': {key: old.get(key) for key in values}})

    def prepare(self, mode='review', scoped=False):
        identifier = self.choose(mode)
        with w.execution_owner('TEST-preparation'), w.execution_scope([identifier] if scoped else None):
            self.apply({'kind': 'ui-request-update', 'id': identifier,
                        'status': 'running', 'proof': 'TEST: comienza la preparación ficticia.'})
            self.draft(messageUsage='unused', message='', formAnswerKeys=['custom_weeks'],
                       requiredAnswers=['custom_weeks'],
                       questions=[{'key': 'custom_weeks', 'label': 'Preaviso en semanas (ficticio)',
                                   'type': 'number', 'scope': 'opportunity'}])
            self.apply({'kind': 'ui-responses', 'opportunityId': 'one',
                        'values': {'custom_weeks': 0}, 'expected': {'custom_weeks': None}})
            self.final_review()
            self.apply({'kind': 'ui-request-update', 'id': identifier,
                        'status': 'done', 'proof': 'TEST: CV, destino y formulario ficticios comprobados.'})
        self.assertFalse([r for r in self.data['app']['requests']
                          if r['status'] == 'queued' and r['type'] in ('review', 'investigate')],
                         'La preparación propia terminada no debe dejar otra preparación fantasma.')
        return identifier, self.data['app']['packages'][-1]['id']

    def final_review(self):
        self.apply({'kind': 'ui-review', 'opportunityId': 'one',
                    'fingerprint': w.stamp(self.data, 'one'),
                    'checks': {key: True for key in w.CHECKS},
                    'proof': 'TEST: cinco comprobaciones realizadas en el escenario ficticio.'})

    def approve(self):
        with w.interface_writer():
            self.apply({'kind': 'ui-approve', 'opportunityId': 'one',
                        'fingerprint': w.stamp(self.data, 'one')})
        return next(r['id'] for r in reversed(self.data['app']['requests'])
                    if r['type'] == 'send' and r['status'] == 'queued')

    def delivery(self, identifier, outcome, **values):
        request = self.task(identifier)
        package = next(p for p in self.data['app']['packages'] if p['id'] == request['packageId'])
        return {'kind': 'ui-delivery-check', 'id': identifier, 'expected': request['updatedAt'],
                'packageId': package['id'], 'recipient': package['payload']['recipient'],
                'outcome': outcome, 'proof': 'TEST: resultado del destino ficticio comprobado.', **values}

    def test_profile_assessment_choice_and_criteria_change_keep_their_meaning_after_reopening(self):
        self.apply({'kind': 'ui-search-profiles-migrate', 'expectedRevision': self.data['revision'],
                    'proof': 'TEST: migración de la estrategia ficticia.'})
        self.apply({'kind': 'evidence', 'id': 'one', 'condition': 'Fijo ≥32 k€', 'state': 'Sí',
                    'at': core.now(), 'url': self.row['URL original'], 'fixed': 40000, 'currency': 'EUR',
                    'proof': 'TEST: fijo anual EUR ficticio comprobado.'})
        self.apply({'kind': 'ui-fit-review', 'opportunityId': 'one',
                    'fingerprint': app_context.fit_stamp(self.data, self.row),
                    'apply': True, 'accept': True, 'proof': 'TEST: mínimos ficticios compatibles.'})
        self.apply({'kind': 'ui-offer-assessment', 'opportunityId': 'one',
                    'fingerprint': offer_quality.fingerprint(self.data, self.row),
                    'reason': 'La experiencia ficticia en informes corresponde al requisito de Power Query.',
                    'references': [{'url': self.row['URL original'], 'text': 'Se pide Power Query.'}],
                    'observedAt': core.now(), 'unknowns': ['Equipo aún sin comprobar.'],
                    'proof': 'TEST: requisitos y experiencia ficticios relacionados.'})
        original_assessment = copy.deepcopy(self.data['app']['offerAssessments']['one'])
        _, package_id = self.prepare()
        send = self.approve()
        archived = self.package_files()
        self.apply({'kind': 'ui-search-profile', 'action': 'duplicate', 'id': 'search-current',
                    'newId': 'search-other', 'name': 'Otra estrategia ficticia',
                    'expectedRevision': self.data['revision']})
        self.apply({'kind': 'ui-profile-section', 'section': 'search', 'searchProfileId': 'search-other',
                    'values': {'minimumFixed': 60000}, 'expected': {'minimumFixed': 32000}})
        self.apply({'kind': 'ui-search-profile', 'action': 'default', 'id': 'search-other',
                    'expectedRevision': self.data['revision']})
        self.assertEqual(w.stamp(self.data, 'one'), package_id)
        self.assertEqual(self.task(send)['status'], 'queued')
        before = copy.deepcopy(self.data)
        effect = criteria_preview.preview(self.data, {'searchProfileId': 'search-current',
                                                     'values': {'minimumFixed': 50000}})
        self.assertEqual(self.data, before)
        self.assertEqual(effect['toDiscarded'], ['one'])
        with w.interface_writer():
            self.apply({'kind': 'ui-profile-section', 'section': 'search', 'searchProfileId': 'search-current',
                        'expectedRevision': effect['revision'], 'values': {'minimumFixed': 50000},
                        'expected': {'minimumFixed': 32000}})
        self.assertEqual(self.task(send)['status'], 'cancelled')
        self.assertTrue(next(p for p in self.data['app']['packages'] if p['id'] == package_id)['revokedAt'])
        self.assertEqual(self.data['app']['offerAssessments']['one'], original_assessment)
        self.assertNotEqual(offer_quality.fingerprint(self.data, self.row), original_assessment['fingerprint'])
        self.assertEqual(self.package_files(), archived)
        self.assertFalse(self.data['events'])

    def test_manual_review_change_new_permission_and_confirmed_receipt_use_the_right_version(self):
        _, old_package = self.prepare()
        original = self.package_files()
        old_send = self.approve()
        with w.interface_writer():
            self.apply({'kind': 'ui-responses', 'opportunityId': 'one',
                        'values': {'custom_weeks': 2}, 'expected': {'custom_weeks': 0}})
        self.assertEqual(self.task(old_send)['status'], 'cancelled')
        self.assertEqual(self.package_files(), original)
        self.reject({'kind': 'ui-approve', 'opportunityId': 'one',
                     'fingerprint': old_package}, 'cambiaron|cambió|revisión')
        self.final_review()
        new_package = self.data['app']['packages'][-1]['id']
        self.assertNotEqual(new_package, old_package)
        new_send = self.approve()
        with w.execution_owner('TEST-send'):
            self.apply({'kind': 'ui-request-update', 'id': new_send,
                        'status': 'running', 'proof': 'TEST: comienza el intento ficticio autorizado.'})
            self.apply({'kind': 'event', 'event': {'id': 'TEST-receipt-current', 'type': 'sent',
                        'opportunityId': 'one', 'packageId': new_package,
                        'cv': 'data/packages/' + new_package + '/cv.pdf', 'at': core.now(),
                        'proof': 'TEST: recibo ficticio de la versión actual.',
                        'authorization': 'TEST: permiso ficticio de la persona.',
                        'confirmation': 'TEST: confirmación ficticia 123', 'historyChecked': True}})
            self.apply({'kind': 'ui-request-update', 'id': new_send,
                        'status': 'done', 'proof': 'TEST: recibo ficticio conservado.'})
        (self.root / 'outputs/cv.pdf').write_bytes(b'%PDF-replacement-after-TEST-receipt')
        self.reload()
        event = self.data['events'][0]
        self.assertEqual(event['packageId'], new_package)
        self.assertEqual((self.root / event['cv']).read_bytes(), b'%PDF-test-one')
        self.assertEqual(next(p for p in self.data['app']['packages'] if p['id'] == old_package)['payload']['answers']['custom_weeks'], 0)
        self.assertEqual(next(p for p in self.data['app']['packages'] if p['id'] == new_package)['payload']['answers']['custom_weeks'], 2)
        self.assertEqual(self.task(new_send)['status'], 'done')
        self.reject({'kind': 'ui-approve', 'opportunityId': 'one',
                     'fingerprint': w.stamp(self.data, 'one')}, 'enviada|enviado')

    def test_automatic_preparation_can_continue_only_its_original_snapshot(self):
        root, package = self.prepare(mode='auto', scoped=True)
        send = next(r['id'] for r in self.data['app']['requests'] if r['type'] == 'send')
        with w.execution_owner('TEST-preparation'), w.execution_scope([root]):
            self.assertEqual(w.eligible_continuations(self.data), [send])
            self.apply({'kind': 'ui-request-update', 'id': send, 'status': 'running',
                        'proof': 'TEST: continuación causal ficticia comprobada.'})
        self.assertEqual(self.task(send)['packageId'], package)
        self.assertEqual(self.data['app']['executionScopes']['TEST-preparation']['requestIds'], [root])
        with w.interface_writer():
            self.apply({'kind': 'ui-change', 'opportunityId': 'one', 'message': 'TEST: una instrucción posterior.'})
        later = next(r['id'] for r in reversed(self.data['app']['requests']) if r['type'] == 'change')
        with w.execution_owner('TEST-preparation'), w.execution_scope([root]):
            self.reject({'kind': 'ui-request-update', 'id': later,
                         'status': 'running', 'proof': 'TEST: intento fuera de la tanda.'}, 'instantánea|deriva')
        self.assertEqual(self.task(send)['status'], 'running')
        self.assertFalse(self.data['events'])

    def test_stop_unknown_fresh_check_retry_and_late_receipt_preserve_original_history(self):
        _, package = self.prepare()
        send = self.approve()
        with w.execution_owner('TEST-original'):
            self.apply({'kind': 'ui-request-update', 'id': send,
                        'status': 'running', 'proof': 'TEST: inicio ficticio.'})
        previous = copy.deepcopy(self.task(send))
        with w.execution_owner('TEST-recovery'):
            self.apply({'kind': 'ui-request-interrupt', 'id': send,
                        'expectedUpdatedAt': previous['updatedAt'], 'expectedExecutionId': 'TEST-original',
                        'proof': 'TEST: parada explícita comprobada en el escenario.',
                        'confirmation': 'TEST: la persona ficticia confirma que detuvo el chat.'})
            self.apply(self.delivery(send, 'unknown'))
            self.reject({'kind': 'ui-request-update', 'id': send,
                         'status': 'queued', 'proof': 'TEST: reintento prohibido.'}, 'portal')
            self.apply(self.delivery(send, 'not_sent'))
            check = copy.deepcopy(self.task(send)['deliveryCheck'])
            self.apply({'kind': 'ui-request-update', 'id': send,
                        'status': 'queued', 'proof': 'TEST: ausencia comprobada, pendiente de revalidar.'})
        with w.execution_owner('TEST-original'):
            self.reject({'kind': 'ui-request-update', 'id': send,
                         'status': 'running', 'proof': 'TEST: propietario invalidado.'}, 'retirado')
        with w.execution_owner('TEST-successor'):
            self.apply({'kind': 'ui-request-update', 'id': send,
                        'status': 'running', 'proof': 'TEST: intento revalidado.'})
            self.assertNotIn('deliveryCheck', self.task(send))
            self.apply({'kind': 'ui-request-update', 'id': send,
                        'status': 'interrupted', 'proof': 'TEST: segunda interrupción ficticia.'})
            self.reject({'kind': 'ui-request-update', 'id': send,
                         'status': 'queued', 'proof': 'TEST: no reutilizar la comprobación.'}, 'portal')
            self.apply(self.delivery(send, 'sent', sentAt=core.now(), confirmation='TEST: recibo tardío ficticio.'))
        self.assertEqual(self.task(send)['status'], 'done')
        self.assertEqual(self.task(send)['interruptions'][0]['previousExecutionId'], 'TEST-original')
        self.assertIn('TEST-original', self.task(send)['invalidatedExecutionIds'])
        self.assertEqual(self.data['events'][0]['packageId'], package)
        self.assertEqual(len(self.data['events']), 1)
        self.assertNotEqual(self.task(send)['updatedAt'], check['at'])
        self.assertEqual(len([r for r in self.data['app']['requests'] if r['type'] == 'send']), 1)

    def test_lost_save_response_is_idempotent_and_conflicting_multifield_save_is_atomic(self):
        root, _ = self.prepare()
        operation = {'kind': 'ui-responses', 'opportunityId': 'one',
                     'values': {'custom_weeks': 3}, 'expected': {'custom_weeks': 0}}
        batch = {'id': 'TEST-lost-response', 'operations': [operation]}
        with w.interface_writer():
            self.assertTrue(self.commit(batch))
            original = self.store.read_bytes()
            self.assertFalse(self.commit(batch))
            self.assertEqual(self.store.read_bytes(), original)
            with self.assertRaises(w.Conflict):
                self.commit({**batch, 'operations': [{**operation, 'values': {'custom_weeks': 4}}]})
            self.assertEqual(self.store.read_bytes(), original)
            with self.assertRaises(ValueError):
                self.commit({'id': 'TEST-atomic-rejected', 'operations': [
                    {'kind': 'ui-responses', 'opportunityId': 'one',
                     'values': {'custom_weeks': 5}, 'expected': {'custom_weeks': 3}},
                    {'kind': 'ui-draft', 'opportunityId': 'one',
                     'values': {'recipient': 'https://example.org/new'}, 'expected': {'recipient': 'stale'}}]})
        self.assertEqual(self.store.read_bytes(), original)
        self.reload()
        self.assertEqual(w.answers(self.data, 'one')['custom_weeks'], 3)
        self.assertEqual(self.task(root)['status'], 'done')

    def test_new_human_material_during_preparation_keeps_its_separate_continuation(self):
        root = self.choose()
        with w.execution_owner('TEST-preparation'), w.execution_scope([root]):
            self.apply({'kind': 'ui-request-update', 'id': root, 'status': 'running',
                        'proof': 'TEST: comienza la preparación ficticia.'})
            self.draft(messageUsage='unused', message='', requiredAnswers=[], formAnswerKeys=[])
            self.assertFalse([r for r in self.data['app']['requests'] if r['status'] == 'queued'])
            with w.interface_writer():
                self.draft(messageUsage='form', message='TEST: presentación nueva de la persona ficticia.')
            later = next(r['id'] for r in self.data['app']['requests'] if r['status'] == 'queued')
            self.final_review()
            self.apply({'kind': 'ui-request-update', 'id': root, 'status': 'done',
                        'proof': 'TEST: termina la instantánea original.'})
        self.assertEqual(self.task(later)['status'], 'queued')
        self.assertEqual(self.data['app']['executionScopes']['TEST-preparation']['requestIds'], [root])
        self.assertFalse(self.data['events'])

    def test_investigation_that_prepares_a_cv_does_not_queue_its_own_review(self):
        self.apply({'kind': 'opportunity', 'id': 'one', 'values': {'CV preparado': None},
                    'proof': 'TEST: oferta ficticia todavía sin CV.'})
        root = self.choose()
        self.assertEqual(self.task(root)['type'], 'investigate')
        with w.execution_owner('TEST-investigation'):
            self.apply({'kind': 'ui-request-update', 'id': root, 'status': 'running',
                        'proof': 'TEST: investigación ficticia iniciada.'})
            self.draft(messageUsage='unused', message='', requiredAnswers=[], formAnswerKeys=[])
            self.apply({'kind': 'opportunity', 'id': 'one', 'values': {'CV preparado': 'outputs/cv.pdf'},
                        'proof': 'TEST: documento ficticio preparado durante la investigación.'})
            self.final_review()
            self.apply({'kind': 'ui-request-update', 'id': root, 'status': 'done',
                        'proof': 'TEST: investigación y preparación ficticias completadas.'})
        self.assertFalse([r for r in self.data['app']['requests'] if r['status'] == 'queued'])
        self.assertEqual(len(self.data['app']['packages']), 1)

    def test_backup_restore_compares_later_changes_and_disarms_permissions_without_losing_material(self):
        _, package = self.prepare(mode='auto')
        send = next(r['id'] for r in self.data['app']['requests'] if r['type'] == 'send')
        with w.execution_owner('TEST-original'):
            self.apply({'kind': 'ui-request-update', 'id': send,
                        'status': 'running', 'proof': 'TEST: intento ficticio iniciado.'})
        backup_cases.BackupTests.prepare_code(self)
        result = backup.create(self.root)
        content = Path(result['path']).read_bytes()
        original = copy.deepcopy(backup.verify(content)['data'])
        original_registry = self.store.read_bytes()
        original_files = self.package_files()
        with w.interface_writer():
            self.apply({'kind': 'ui-offer-note', 'opportunityId': 'one',
                        'values': {'Notas de seguimiento': 'TEST: cambio posterior a la copia.'},
                        'expected': {'Notas de seguimiento': None}})
        later = self.store.read_bytes()
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        destination = Path(holder.name) / 'recovered-TEST'
        for bad in (self.root, self.root / 'nested', self.root.parent):
            with self.assertRaisesRegex(ValueError, 'carpeta nueva'):
                backup.restore(self.root, Path(result['path']), bad)
        recovered = backup.restore(self.root, Path(result['path']), destination)
        restored = core.read_store(destination / 'data/registry.json')
        self.assertFalse(recovered['permissionsRestored'])
        self.assertEqual(self.store.read_bytes(), later)
        self.assertEqual((destination / 'data/recovery-original.json').read_bytes(), original_registry)
        self.assertEqual(restored['profile'], original['profile'])
        self.assertEqual(restored['app']['selections']['one']['mode'], 'review')
        restored_package = next(p for p in restored['app']['packages'] if p['id'] == package)
        self.assertTrue(restored_package['revokedAt'])
        self.assertEqual(restored_package['payload'], original['app']['packages'][-1]['payload'])
        restored_send = next(r for r in restored['app']['requests'] if r['id'] == send)
        self.assertEqual(restored_send['status'], 'cancelled')
        self.assertEqual(restored_send['startedAt'], self.task(send)['startedAt'])
        self.assertNotIn('review', restored['app']['drafts']['one'])
        self.assertTrue(restored['app']['drafts']['one']['recoveryReviews'])
        self.assertEqual(self.package_files(), original_files)
        for relative, expected in original_files.items():
            self.assertEqual(core.digest((destination / 'data/packages' / relative).read_bytes()), expected)
        self.assertEqual(self.row['Notas de seguimiento'], 'TEST: cambio posterior a la copia.')
        self.assertNotEqual(restored['sheets']['Oportunidades'][0].get('Notas de seguimiento'), self.row['Notas de seguimiento'])
        self.assertTrue((destination / 'RECUPERACION.txt').is_file())
        self.assertTrue((destination / 'Abrir Stubbs Jobs.exe').is_file())
        self.assertFalse(restored['events'])


if __name__ == '__main__':
    unittest.main()
