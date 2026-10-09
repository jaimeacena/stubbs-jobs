"""Fresh backend regressions use only fictional records in temporary folders."""
import copy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import app_context as context
import app_workflow as workflow
import agent_runner
import stubbs_jobs
import stubbs_jobs_app as server
import personalization


class DraftUndoTests(WorkflowFixture, unittest.TestCase):
    def add_question(self):
        field = {'key': 'custom_schedule', 'label': 'Horario disponible',
                 'type': 'text', 'scope': 'opportunity'}
        self.apply({'kind': 'ui-draft', 'opportunityId': 'one',
                    'values': {'questions': [field], 'formAnswerKeys': [field['key']],
                               'messageUsage': 'unused'},
                    'expected': {'questions': None, 'formAnswerKeys': None, 'messageUsage': None}})
        undo = next(item for item in workflow.state(self.data)['undo']
                    if item['kind'] == 'draft')
        return field, undo

    def assert_restored(self, original, field):
        self.assertEqual(workflow.draft(self.data, 'one'), original)
        self.assertNotIn(field['key'], context.definitions(self.data, 'one'))
        self.assertEqual(context.question_catalog(self.data)[field['key']], field)
        self.assertIsInstance(workflow.stamp(self.data, 'one'), str)

    def test_undo_first_question_restores_absent_fields_without_breaking_the_draft(self):
        original = copy.deepcopy(workflow.draft(self.data, 'one'))
        field, undo = self.add_question()
        self.apply({'kind': 'ui-undo', 'id': undo['id']})
        # updatedAt is the retained edit timestamp, while all material is restored.
        original['updatedAt'] = workflow.draft(self.data, 'one')['updatedAt']
        self.assert_restored(original, field)

    def test_legacy_undo_without_absence_metadata_also_restores_optional_fields(self):
        original = copy.deepcopy(workflow.draft(self.data, 'one'))
        field, undo = self.add_question()
        undo.pop('absent', None)
        self.apply({'kind': 'ui-undo', 'id': undo['id']})
        original['updatedAt'] = workflow.draft(self.data, 'one')['updatedAt']
        self.assert_restored(original, field)


class AutoReviewContinuityTests(WorkflowFixture, unittest.TestCase):
    def test_rechecking_identical_material_preserves_the_causal_send_authorization(self):
        at = datetime.now(timezone.utc)
        with patch.object(agent_runner, 'read_state', return_value={'status': 'idle'}), \
                patch.object(agent_runner, 'view', return_value={'status': 'idle'}):
            self.apply({'kind': 'ui-select-opportunity', 'opportunityId': 'one',
                        'selected': True, 'mode': 'auto', 'expected': None})
            root = workflow.state(self.data)['requests'][-1]
            with workflow.execution_owner('TEST-original'), workflow.execution_scope([root['id']]):
                self.apply({'kind': 'ui-request-update', 'id': root['id'], 'status': 'running',
                            'proof': 'TEST preparation started'})
                workflow.draft(self.data,'one').update(messageUsage='form',formAnswerKeys=[])
                review = {'kind': 'ui-review', 'opportunityId': 'one',
                          'fingerprint': workflow.stamp(self.data, 'one'),
                          'checks': {key: True for key in workflow.CHECKS},
                          'proof': 'TEST all materials checked'}
                with patch.object(workflow, 'now', return_value=at.isoformat(timespec='seconds')):
                    self.apply(review)
                send = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')
                original_authorization = send['continuation']['authorizationAt']
                with patch.object(workflow, 'now', return_value=(at + timedelta(seconds=1)).isoformat(timespec='seconds')):
                    self.apply({**review, 'proof': 'TEST same materials checked again'})
                    self.apply({'kind': 'ui-request-update', 'id': root['id'], 'status': 'done',
                                'proof': 'TEST preparation completed'})
                package = next(item for item in workflow.state(self.data)['packages'] if item['id'] == send['packageId'])
                self.assertEqual(package['approvedAt'], original_authorization)
                self.assertEqual(workflow.eligible_continuations(self.data), [send['id']])
                self.assertEqual(len([item for item in workflow.state(self.data)['requests'] if item['type'] == 'send']), 1)


class ExecutionScopeWriteTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for name in ('read_state', 'view'):
            replacement = patch.object(agent_runner, name, return_value={'status': 'idle'})
            replacement.start()
            self.addCleanup(replacement.stop)
        self.apply({'kind': 'ui-request', 'type': 'discovery'})
        self.request_id = workflow.state(self.data)['requests'][-1]['id']
        self.start_batch = {'id': 'TEST-scoped-start', 'operations': [
            {'kind': 'ui-request-update', 'id': self.request_id, 'status': 'running',
             'proof': 'TEST scoped work started'}]}
        with workflow.execution_owner('TEST-fixed'), workflow.execution_scope([self.request_id]):
            self.assertTrue(stubbs_jobs.apply_batch(self.data, self.start_batch))

    def test_heartbeat_and_completion_reject_changed_or_missing_snapshot(self):
        baseline = copy.deepcopy(self.data)
        for request_ids in (None, [self.request_id, 'TEST-new-task']):
            for status in ('running', 'done'):
                with self.subTest(request_ids=request_ids, status=status):
                    self.data = copy.deepcopy(baseline)
                    with workflow.execution_owner('TEST-fixed'), workflow.execution_scope(request_ids):
                        with self.assertRaisesRegex(ValueError, 'instantánea'):
                            self.apply({'kind': 'ui-request-update', 'id': self.request_id,
                                        'status': status, 'proof': 'TEST newer update'})
                    self.assertEqual(self.data, baseline)

    def test_material_edit_also_rejects_a_different_snapshot(self):
        baseline = copy.deepcopy(self.data)
        with workflow.execution_owner('TEST-fixed'), workflow.execution_scope(['TEST-new-task']):
            with self.assertRaisesRegex(ValueError, 'instantánea'):
                self.apply({'kind': 'ui-draft', 'opportunityId': 'one',
                            'values': {'message': 'TEST changed draft'},
                            'expected': {'message': workflow.draft(self.data, 'one')['message']}})
        self.assertEqual(self.data, baseline)

    def test_exact_snapshot_can_complete_and_applied_batch_can_be_reconciled_without_flags(self):
        baseline = copy.deepcopy(self.data)
        with workflow.execution_owner('TEST-fixed'):
            self.assertFalse(stubbs_jobs.apply_batch(self.data, copy.deepcopy(self.start_batch)))
        self.assertEqual(self.data, baseline)
        with workflow.execution_owner('TEST-fixed'), workflow.execution_scope([self.request_id]):
            self.apply({'kind': 'ui-request-update', 'id': self.request_id,
                        'status': 'done', 'proof': 'TEST scoped work finished'})
        self.assertEqual(next(item for item in workflow.state(self.data)['requests']
                              if item['id'] == self.request_id)['status'], 'done')


class SourceConfigurationTests(WorkflowFixture, unittest.TestCase):
    def source(self, **changes):
        return {'id': 'TEST-board', 'company': 'Empresa ficticia', 'kind': 'html',
                'url': 'https://example.org/jobs', 'enabled': True, **changes}

    def test_malformed_configuration_is_diagnostic_and_keeps_the_app_readable(self):
        directory = self.root / 'config'
        directory.mkdir()
        self.data['updatedAt'] = workflow.now()
        for value in (None, 'bad', {}, {'sources': None}, {'sources': {}},
                      [None], ['bad'], [self.source(company=None)], [self.source(enabled='yes')],
                      [self.source(kind=None)], [self.source(url=None)], [self.source(), self.source()]):
            with self.subTest(value=value):
                (directory / 'sources.json').write_text(json.dumps(value), encoding='utf-8')
                with patch.object(personalization, 'ROOT', self.root), patch.object(server, 'ROOT', self.root):
                    with self.assertRaises(ValueError):
                        personalization.public_sources(self.data)
                    shown = server.build_state(copy.deepcopy(self.data), include_export=False,
                                               include_instructions=False, execution={'status': 'idle'})
                self.assertEqual(shown['publicSources'], [])
                self.assertIn('config/sources.json', shown['sourceConfigurationError'])
                self.assertEqual(shown['profile'], self.data['profile'])
                self.assertEqual(len(shown['opportunities']), 1)

    def test_path_escapes_reserved_names_and_case_collisions_are_rejected(self):
        for identifier in ('../outside', '..\\outside', '/absolute', 'C:\\absolute',
                           'CON', 'nul.json', 'LPT9', 'trailing.', '.', '..'):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                personalization.validate_source_configuration([self.source(id=identifier)])
        with self.assertRaisesRegex(ValueError, 'compartir identificador'):
            personalization.validate_source_configuration([self.source(id='same'), self.source(id='SAME')])

    def test_valid_configurations_keep_unknown_adapter_diagnostics_and_all_original_fields(self):
        value = [self.source(priority=2), self.source(id='TEST-api', kind='greenhouse', board='company-2026'),
                 self.source(id='TEST-unsupported', kind='new-adapter')]
        self.assertIs(personalization.validate_source_configuration(value), value)
        self.assertIs(personalization.validate_source_configuration({'sources': value}), value)
        self.assertEqual(value[0]['priority'], 2)


if __name__ == '__main__':
    unittest.main()
