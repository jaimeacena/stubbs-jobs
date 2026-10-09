"""Reproductions from the 09/10 audit. Fictional records, no employment effects."""
import copy
import os
import unittest
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import app_workflow as workflow
import stubbs_jobs as jobs


class BrokenConnectionsTests(WorkflowFixture, unittest.TestCase):
    def historical_operation(self):
        return {'kind':'historical','record':{'id':'TEST-old','company':'Empresa ficticia',
                'url':'https://example.org/jobs/456-role','state':'Enviada','proof':'TEST: recibo anterior'}}

    def test_derived_historical_fields_do_not_mutate_the_batch_or_break_exact_replay(self):
        batch={'id':'TEST-immutable','operations':[self.historical_operation()]}
        original=copy.deepcopy(batch)
        self.assertTrue(jobs.apply_batch(self.data,batch))
        self.assertEqual(batch,original)
        self.assertEqual(self.data['changes'][-1]['operations'],original['operations'])
        self.assertIn('canonicalKey',self.data['historicalApplications'][0])
        saved=copy.deepcopy(self.data)
        self.assertFalse(jobs.apply_batch(self.data,copy.deepcopy(original)))
        self.assertEqual(self.data,saved)

    def test_failed_batch_preserves_its_original_operations_as_well_as_the_registry(self):
        batch={'id':'TEST-failure','operations':[self.historical_operation(),{'kind':'not-supported'}]}
        original=copy.deepcopy(batch);saved=copy.deepcopy(self.data)
        with self.assertRaises(ValueError):jobs.apply_batch(self.data,batch)
        self.assertEqual(self.data,saved)
        self.assertEqual(batch,original)

    def test_new_search_clears_old_offer_facts_but_preserves_personal_context(self):
        app = workflow.state(self.data)
        stores = ('availabilityChecks', 'followupChecks', 'followupPlans', 'offerAssessments')
        for name in stores:
            app[name] = {'one': {'proof': 'TEST: facts from the old search'}}
        app['sourceReviews'] = [{'id': 'old-review', 'requestId': 'old-search'}]
        app['executionScopes'] = {'old-owner': {'requestIds': ['old-search']}}
        app['questionCatalog'] = {'custom_example': {'label': 'TEST: reusable personal question'}}
        profile = copy.deepcopy(self.data['profile'])
        questions = copy.deepcopy(app['questionCatalog'])
        with patch('agent_runner.view', return_value={'status': 'idle'}):
            jobs.clear_opportunities(self.data, self.data['revision'])
        for name in stores:
            self.assertEqual(app[name], {}, name)
        self.assertEqual(app['sourceReviews'], [])
        self.assertEqual(app['executionScopes'], {})
        self.assertEqual(self.data['profile'], profile)
        self.assertEqual(app['questionCatalog'], questions)

    def test_new_search_cannot_erase_an_unresolved_started_send(self):
        app = workflow.state(self.data)
        for status in ('blocked', 'interrupted', 'cancelled'):
            with self.subTest(status=status):
                app['requests'] = [{'id': 'attempt', 'type': 'send', 'opportunityId': 'one',
                                    'packageId': 'original', 'status': status,
                                    'startedAt': '2026-10-01T10:00:00Z'}]
                before = copy.deepcopy(self.data)
                with patch('agent_runner.view', return_value={'status': 'idle'}):
                    with self.assertRaisesRegex(ValueError, 'envío.*sin resolver'):
                        jobs.clear_opportunities(self.data, self.data['revision'])
                self.assertEqual(self.data, before)

    def test_own_change_uses_the_same_execution_identity_as_task_ownership(self):
        app = workflow.state(self.data)
        app['requests'] = [{'id': 'change', 'type': 'change', 'opportunityId': 'one',
                            'status': 'running', 'executionId': 'owner'}]
        for variable in ('STUBBS_JOBS_RUN_ID', 'STUBBS_JOBS_EXECUTION_ID', 'CODEX_THREAD_ID'):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: 'owner'}, clear=True):
                self.assertEqual(workflow.execution_id(), 'owner')
                self.assertFalse(workflow.pending_change(self.data, 'one', exclude_owner=True))
                self.assertTrue(workflow.pending_change(self.data, 'one'))
        with patch.dict(os.environ, {'CODEX_THREAD_ID': 'another-owner'}, clear=True):
            self.assertTrue(workflow.pending_change(self.data, 'one', exclude_owner=True))
        with workflow.interface_writer(), patch.dict(os.environ, {'CODEX_THREAD_ID': 'owner'}, clear=True):
            self.assertTrue(workflow.pending_change(self.data, 'one', exclude_owner=True))

    def test_followup_request_does_not_reuse_a_running_preparation_investigation(self):
        self.data['events'] = [{'id': 'receipt', 'type': 'sent', 'opportunityId': 'one',
                                'at': '2026-10-01T10:00:00Z', 'proof': 'TEST: original receipt'}]
        self.row['Estado'] = 'Enviada'
        original = {'id': 'preparation', 'type': 'investigate', 'opportunityId': 'one',
                    'packageId': None, 'status': 'running', 'executionId': 'original-owner'}
        workflow.state(self.data)['requests'] = [copy.deepcopy(original)]
        self.apply({'kind': 'ui-request', 'type': 'investigate', 'purpose': 'followup',
                    'opportunityId': 'one'})
        requests = workflow.state(self.data)['requests']
        self.assertEqual(requests[0], original)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]['purpose'], 'followup')
        self.assertEqual(requests[1]['status'], 'queued')
        self.apply({'kind': 'ui-request', 'type': 'investigate', 'purpose': 'followup',
                    'opportunityId': 'one'})
        self.assertEqual(len(workflow.state(self.data)['requests']), 2)
