"""Isolated ownership and interruption scenarios; no real chat or registry."""
import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

from workflow_fixtures import WorkflowFixture
import agent_runner
import app_workflow as workflow
import request_workflow
import stubbs_jobs


class RequestContinuityTests(unittest.TestCase):
    apply = WorkflowFixture.apply
    review = WorkflowFixture.review

    def setUp(self):
        WorkflowFixture.setUp(self)
        for name, result in (('read_state', {'status': 'idle'}), ('view', {'status': 'idle'})):
            replacement = patch.object(agent_runner, name, return_value=result)
            replacement.start()
            self.addCleanup(replacement.stop)

    def live(self, request):
        return next(item for item in workflow.state(self.data)['requests'] if item['id'] == request['id'])

    def start(self, kind='discovery'):
        operation = {'kind': 'ui-request', 'type': kind}
        if kind != 'discovery':
            operation['opportunityId'] = 'one'
        self.apply(operation)
        request = workflow.state(self.data)['requests'][-1]
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST last verified step'})
        return self.live(request)

    def interruption(self, request, **values):
        return {'kind': 'ui-request-interrupt', 'id': request['id'],
                'expectedUpdatedAt': request.get('updatedAt'), 'expectedExecutionId': request.get('executionId'),
                'proof': 'TEST checked last step and explicit stop',
                'confirmation': 'TEST person confirmed they stopped the previous chat', **values}

    def test_successful_resumption_does_not_keep_the_previous_block_as_its_result(self):
        request=self.start('change')
        def update(status,proof,**fields):
            self.apply({'kind':'ui-request-update','id':request['id'],'status':status,'proof':proof,**fields})
        with workflow.execution_owner('original'):
            update('blocked','TEST portal was unavailable',summary='TEST previous access block',need='access')
            blocked=copy.deepcopy(self.data['changes'][-1])
            update('queued','TEST verified access restored')
            self.assertNotIn('summary',self.live(request));self.assertNotIn('need',self.live(request))
            update('running','TEST resumed work',summary='TEST current work',need='other')
            update('running','TEST activity recorded')
            self.assertEqual(self.live(request)['summary'],'TEST current work')
            update('done','TEST completed successfully')
        self.assertEqual(self.live(request)['result'],'TEST completed successfully')
        self.assertNotIn('summary',self.live(request));self.assertNotIn('need',self.live(request))
        self.assertIn(blocked,self.data['changes'])
        self.assertTrue(any(item['detail']=='TEST portal was unavailable' for item in workflow.state(self.data)['history']))

    def test_same_clock_summary_and_heartbeat_never_restore_a_stale_interruption_token(self):
        fixed=datetime.now(timezone.utc)
        with patch.object(workflow,'datetime') as clock,patch.object(workflow,'now',return_value=fixed.isoformat(timespec='seconds')):
            clock.now.return_value=fixed
            request=self.start('change')
            started=copy.deepcopy(self.live(request))
            with workflow.execution_owner('original'):
                self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':started['updatedAt'],
                            'summary':'TEST current phase','need':'other'})
                summarized=copy.deepcopy(self.live(request))
                self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST new activity'})
            current=self.live(request)
            self.assertGreater(current['updatedAt'],summarized['updatedAt'])
            self.assertGreater(summarized['updatedAt'],started['updatedAt'])
            self.assertEqual(current['startedAt'],started['startedAt'])
            self.assertEqual(current['createdAt'],started['createdAt'])
            self.assertEqual(current['summary'],'TEST current phase')
            before=copy.deepcopy(self.data)
            with workflow.execution_owner('replacement'),self.assertRaises(workflow.Conflict):
                self.apply(self.interruption(current,expectedUpdatedAt=summarized['updatedAt']))
            self.assertEqual(self.data,before)
            self.assertNotIn('invalidatedExecutionIds',self.live(request))
            with workflow.execution_owner('replacement'):self.apply(self.interruption(current))
            interrupted=self.live(request)
            self.assertGreater(interrupted['updatedAt'],current['updatedAt'])
            self.assertEqual(interrupted['interruptions'][-1]['previousUpdatedAt'],current['updatedAt'])
            self.assertEqual(interrupted['invalidatedExecutionIds'],['original'])

    def test_summary_of_a_legacy_completed_task_does_not_rewrite_its_activity_date(self):
        request=self.start('change')
        with workflow.execution_owner('original'):
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'done','proof':'TEST actual completed result'})
        # A retained completion from a previous release, without activityAt.
        old='2020-01-01T12:00:00+00:00'
        legacy=self.live(request)
        legacy.update(createdAt=old,startedAt=old,updatedAt=old)
        legacy.pop('activityAt',None)
        before=copy.deepcopy(legacy)
        history=copy.deepcopy(workflow.state(self.data)['history'])
        with workflow.execution_owner('summary-author'):
            self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':old,
                        'summary':'TEST clearer explanation of the old result','need':'other'})
        current=self.live(request)
        self.assertEqual(current['activityAt'],old)
        self.assertGreater(current['updatedAt'],old)
        self.assertEqual(current['result'],before['result'])
        self.assertEqual(current['createdAt'],old);self.assertEqual(current['startedAt'],old)
        self.assertEqual(current['status'],'done')
        self.assertEqual(workflow.state(self.data)['history'],history)

    def test_summary_changes_the_token_but_only_real_owner_activity_refreshes_activity_date(self):
        request=self.start('change')
        old='2020-01-01T12:00:00+00:00'
        self.live(request).update(updatedAt=old,activityAt=old)
        fixed=datetime.now(timezone.utc)
        with patch.object(workflow,'datetime') as clock,workflow.execution_owner('original'):
            clock.now.return_value=fixed
            self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':old,
                        'summary':'TEST last retained step explained','need':'other'})
            summarized=copy.deepcopy(self.live(request))
            self.assertEqual(summarized['activityAt'],old)
            self.assertGreater(summarized['updatedAt'],old)
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST actual new progress'})
        current=self.live(request)
        self.assertEqual(current['activityAt'],fixed.isoformat(timespec='microseconds'))
        self.assertGreater(current['updatedAt'],summarized['updatedAt'])
        self.assertEqual(current['startedAt'],summarized['startedAt'])
        self.assertEqual(current['executionId'],'original')

    def test_old_activity_does_not_release_owner_during_another_profile_write(self):
        request = self.start()
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        self.live(request)['updatedAt'] = old
        self.apply({'kind': 'ui-profile', 'values': {'currentCity': 'TEST city'}, 'expected': {'currentCity': None}})
        live = self.live(request)
        self.assertEqual((live['status'], live['executionId'], live['updatedAt']), ('running', 'original', old))
        queued_id = self.start_queued_change()
        before = copy.deepcopy(self.data)
        with workflow.execution_owner('new-chat'), self.assertRaisesRegex(ValueError, 'Otra IA'):
            self.apply({'kind': 'ui-request-update', 'id': queued_id, 'status': 'running', 'proof': 'TEST forbidden competing work'})
        self.assertEqual(self.data, before)
        self.assertEqual(self.live(request), live)

    def start_queued_change(self):
        self.apply({'kind': 'ui-change', 'message': 'TEST later instruction', 'actor': 'Persona'})
        return workflow.state(self.data)['requests'][-1]['id']

    def test_explicit_interruption_preserves_owner_and_records_previous_progress(self):
        request = self.start()
        previous = copy.deepcopy(request)
        with workflow.execution_owner('new-chat'):
            self.apply(self.interruption(request))
        live = self.live(request)
        self.assertEqual(live['status'], 'interrupted')
        self.assertEqual(live['executionId'], 'original')
        self.assertEqual(live['startedAt'], previous['startedAt'])
        self.assertEqual(live['invalidatedExecutionIds'], ['original'])
        entry = live['interruptions'][0]
        self.assertEqual(entry['previousResult'], previous['result'])
        self.assertEqual(entry['previousUpdatedAt'], previous['updatedAt'])
        self.assertEqual(entry['previousExecutionId'], 'original')
        self.assertEqual(entry['byExecutionId'], 'new-chat')
        self.assertEqual(entry['confirmation'], self.interruption(request)['confirmation'])
        self.assertEqual(workflow.state(self.data)['history'][-1]['interruption'], entry)

    def test_same_owner_can_record_stop_but_needs_new_id_for_continuation(self):
        request = self.start()
        operation = self.interruption(request)
        operation.pop('confirmation')
        with workflow.execution_owner('original'):
            self.apply(operation)
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'retirado'):
                self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST stale owner'})
            self.assertEqual(self.data, before)
        with workflow.execution_owner('new-chat'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST checked continuation'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST actual continuation'})
        self.assertEqual(self.live(request)['executionId'], 'new-chat')

    def test_foreign_owner_requires_human_stop_confirmation_and_current_preconditions(self):
        request = self.start()
        invalid = ({'confirmation': None}, {'confirmation': ''}, {'expectedUpdatedAt': 'old'},
                   {'expectedExecutionId': 'another'}, {'proof': ''})
        for values in invalid:
            with self.subTest(values=values), workflow.execution_owner('new-chat'):
                before = copy.deepcopy(self.data)
                with self.assertRaises(ValueError):
                    self.apply(self.interruption(request, **values))
                self.assertEqual(self.data, before)
        for name in ('expectedUpdatedAt', 'expectedExecutionId'):
            operation = self.interruption(request)
            operation.pop(name)
            with self.subTest(missing=name), workflow.execution_owner('new-chat'):
                before = copy.deepcopy(self.data)
                with self.assertRaisesRegex(ValueError, 'propietario exactos'):
                    self.apply(operation)
                self.assertEqual(self.data, before)

    def test_interruption_requires_own_execution_id(self):
        request = self.start()
        with patch.object(workflow, 'execution_id', return_value=None):
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'execution-id'):
                self.apply(self.interruption(request))
            self.assertEqual(self.data, before)

    def test_legacy_running_without_ready_profile_keeps_invalid_previous_date(self):
        request = self.start()
        request.pop('executionId')
        request['updatedAt'] = 'unknown legacy date'
        workflow.state(self.data)['setupComplete'] = False
        before = copy.deepcopy(self.data)
        with workflow.execution_owner('new-chat'), self.assertRaisesRegex(ValueError, 'instrucción humana'):
            self.apply(self.interruption(request, confirmation=None))
        self.assertEqual(self.data, before)
        with workflow.execution_owner('new-chat'):
            self.apply(self.interruption(request))
        live = self.live(request)
        self.assertEqual(live['status'], 'interrupted')
        self.assertNotIn('executionId', live)
        self.assertEqual(live['interruptions'][0]['previousUpdatedAt'], 'unknown legacy date')
        self.assertIsNone(live['interruptions'][0]['previousExecutionId'])
        self.assertFalse(workflow.state(self.data)['setupComplete'])

    def test_active_previous_execution_or_legacy_unknown_owner_cannot_be_interrupted(self):
        request = self.start()
        baseline = copy.deepcopy(self.data)
        for previous_owner, active_owner in (('original', 'original'), (None, 'legacy-active')):
            with self.subTest(owner=previous_owner):
                self.data = copy.deepcopy(baseline)
                request = self.live(request)
                if previous_owner is None:
                    request.pop('executionId')
                with patch.object(agent_runner, 'view', return_value={'status': 'running'}), \
                     patch.object(agent_runner, 'read_state', return_value={'status': 'running', 'id': active_owner}), \
                     workflow.execution_owner('new-chat'):
                    before = copy.deepcopy(self.data)
                    with self.assertRaisesRegex(ValueError, 'sigue activa'):
                        self.apply(self.interruption(request))
                    self.assertEqual(self.data, before)

    def test_invalidated_owner_cannot_queue_run_change_summary_or_interrupt_new_owner(self):
        request = self.start()
        with workflow.execution_owner('new-chat'):
            self.apply(self.interruption(request))
        with workflow.execution_owner('original'):
            for status in ('queued', 'running', 'cancelled'):
                before = copy.deepcopy(self.data)
                with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'retirado'):
                    self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': status, 'proof': 'TEST invalidated update'})
                self.assertEqual(self.data, before)
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'retirado'):
                self.apply({'kind': 'ui-request-summary', 'id': request['id'], 'expectedUpdatedAt': self.live(request)['updatedAt'],
                            'summary': 'TEST stale summary', 'need': 'other'})
            self.assertEqual(self.data, before)
        with workflow.execution_owner('new-chat'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST checked restart'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST actual restart'})
        with workflow.execution_owner('original'):
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'retirado'):
                self.apply(self.interruption(self.live(request)))
            self.assertEqual(self.data, before)

    def test_many_running_requests_stop_atomically_without_requeue(self):
        first, second = self.start(), self.start('change')
        operations = [self.interruption(first), self.interruption(second, expectedUpdatedAt='stale')]
        before = copy.deepcopy(self.data)
        with workflow.execution_owner('new-chat'), self.assertRaises(ValueError):
            stubbs_jobs.apply_batch(self.data, {'id': 'TEST failed stop batch', 'operations': operations})
        self.assertEqual(self.data, before)
        operations[1] = self.interruption(second)
        with workflow.execution_owner('new-chat'):
            stubbs_jobs.apply_batch(self.data, {'id': 'TEST complete stop batch', 'operations': operations})
        self.assertEqual([self.live(item)['status'] for item in (first, second)], ['interrupted', 'interrupted'])
        self.assertFalse(any(item['status'] == 'queued' for item in workflow.state(self.data)['requests']))

    def test_interrupted_send_still_requires_portal_check_then_permission_revalidation(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        request = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST actual send start'})
        request = self.live(request)
        package = copy.deepcopy(workflow.state(self.data)['packages'][0])
        with workflow.execution_owner('new-chat'):
            self.apply(self.interruption(request))
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'compruebe el portal'):
                self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST forbidden resend'})
            self.assertEqual(self.data, before)
            self.apply({'kind': 'ui-delivery-check', 'id': request['id'], 'expected': self.live(request)['updatedAt'],
                        'packageId': package['id'], 'recipient': package['payload']['recipient'],
                        'outcome': 'not_sent', 'proof': 'TEST portal proves original request not sent'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST checked continuation'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST revalidated send start'})
        self.assertEqual(len([item for item in workflow.state(self.data)['requests'] if item['type'] == 'send']), 1)
        self.assertEqual(workflow.state(self.data)['packages'][0]['approvedAt'], package['approvedAt'])
        self.assertFalse(self.data['events'])

    def test_legacy_silence_interruption_cannot_drop_owner_without_explicit_stop(self):
        request = self.start()
        request.update(status='interrupted', result='No se ha recibido actividad durante dos horas. Revisar antes de reintentar.')
        previous = copy.deepcopy(request)
        with workflow.execution_owner('new-chat'):
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'ui-request-interrupt'):
                self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST unchecked continuation'})
            self.assertEqual(self.data, before)
            self.apply(self.interruption(request))
            live = self.live(request)
            self.assertEqual(live['status'], 'interrupted')
            self.assertEqual(live['executionId'], 'original')
            self.assertEqual(live['interruptions'][0]['previousResult'], previous['result'])
            self.assertFalse(request_workflow.interruption_unconfirmed(live))
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST stop checked continuation'})
        self.assertEqual(self.live(request)['status'], 'queued')

    def test_legacy_silent_send_needs_stop_and_portal_check_before_resume(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        request = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST actual send start'})
        request = self.live(request)
        request.update(status='interrupted', result='No se ha recibido actividad durante dos horas. Revisar antes de reintentar.')
        package = workflow.state(self.data)['packages'][0]
        with workflow.execution_owner('new-chat'):
            self.apply({'kind': 'ui-delivery-check', 'id': request['id'], 'expected': request['updatedAt'],
                        'packageId': package['id'], 'recipient': package['payload']['recipient'],
                        'outcome': 'not_sent', 'proof': 'TEST portal check while previous chat status unknown'})
            self.assertFalse(request_workflow.delivery_checked(self.live(request), package['id']))
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'ui-request-interrupt'):
                self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST not stopped owner'})
            self.assertEqual(self.data, before)
            previous_check = copy.deepcopy(self.live(request)['deliveryCheck'])
            self.apply(self.interruption(self.live(request)))
            self.assertEqual(self.live(request)['interruptions'][0]['previousDeliveryCheck'], previous_check)
            self.assertNotIn('deliveryCheck', self.live(request))
            self.assertFalse(request_workflow.delivery_checked(self.live(request), package['id']))
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'compruebe el portal'):
                self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST stale portal proof after stop'})
            self.assertEqual(self.data, before)
            self.apply({'kind': 'ui-delivery-check', 'id': request['id'], 'expected': self.live(request)['updatedAt'],
                        'packageId': package['id'], 'recipient': package['payload']['recipient'],
                        'outcome': 'not_sent', 'proof': 'TEST new portal check after previous chat stopped'})
            self.assertTrue(request_workflow.delivery_checked(self.live(request), package['id']))
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST stopped and checked'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST authorized new start'})
        self.assertFalse(self.data['events'])
        self.assertEqual(self.live(request)['executionId'], 'new-chat')

    def test_legacy_silence_can_record_original_sent_effect_without_retrying(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        request = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST actual original start'})
        request = self.live(request)
        request.update(status='interrupted', result='No se ha recibido actividad durante dos horas. Revisar antes de reintentar.')
        package = workflow.state(self.data)['packages'][0]
        self.apply({'kind': 'ui-delivery-check', 'id': request['id'], 'expected': request['updatedAt'],
                    'packageId': package['id'], 'recipient': package['payload']['recipient'], 'outcome': 'sent',
                    'sentAt': workflow.now(), 'confirmation': 'TEST actual original receipt', 'proof': 'TEST no new send'})
        self.assertEqual(self.live(request)['status'], 'done')
        self.assertEqual(len(self.data['events']), 1)
        self.assertNotIn('interruptions', self.live(request))


if __name__ == '__main__':
    unittest.main()
