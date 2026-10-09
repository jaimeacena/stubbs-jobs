"""Synthetic receipts only: never open a portal, submit a form or change real data."""
import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

from workflow_fixtures import WorkflowFixture
import agent_runner
import app_workflow as workflow
import request_workflow
import stubbs_jobs_core as core


class DeliveryRecoveryTests(unittest.TestCase):
    apply = WorkflowFixture.apply
    review = WorkflowFixture.review

    def setUp(self):
        WorkflowFixture.setUp(self)
        for name, result in (('read_state', {'status': 'idle'}), ('view', {'status': 'idle'})):
            replacement = patch.object(agent_runner, name, return_value=result)
            replacement.start()
            self.addCleanup(replacement.stop)

    def interrupted(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        request = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST start'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'interrupted', 'proof': 'TEST response lost'})
        return next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')

    def check(self, request, outcome, **values):
        package = next(item for item in workflow.state(self.data)['packages'] if item['id'] == request['packageId'])
        return {'kind': 'ui-delivery-check', 'id': request['id'], 'expected': request['updatedAt'],
                'packageId': package['id'], 'recipient': package['payload']['recipient'], 'outcome': outcome,
                'proof': 'TEST synthetic portal receipt', **values}

    def live(self, request):
        return next(item for item in workflow.state(self.data)['requests'] if item['id'] == request['id'])

    def revoke(self, request):
        self.apply({'kind': 'ui-revoke', 'packageId': request['packageId']})
        return self.live(request)

    def test_retry_without_portal_check_keeps_everything(self):
        request = self.interrupted()
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'compruebe el portal'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST retry'})
        self.assertEqual(self.data, before)

    def test_a_portal_check_allows_one_revalidated_attempt_and_running_updates(self):
        request = self.interrupted()
        self.apply(self.check(request, 'not_sent'))
        self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST resume'})
        with workflow.execution_owner('new'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST resumed'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST progress'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'interrupted', 'proof': 'TEST second interruption'})
        with self.assertRaisesRegex(ValueError, 'compruebe el portal'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST retry'})

    def test_a_late_confirmation_records_the_original_package_without_a_new_send(self):
        request = self.interrupted()
        self.apply(self.check(request, 'sent', sentAt=core.now(), confirmation='TEST application receipt 1'))
        self.assertEqual(len(self.data['events']), 1)
        self.assertEqual(self.data['events'][0]['packageId'], request['packageId'])
        self.assertTrue(self.data['events'][0]['recovered'])
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['Estado'], 'Enviada')
        self.assertEqual(next(item for item in workflow.state(self.data)['requests'] if item['id'] == request['id'])['status'], 'done')
        self.assertEqual(len([item for item in workflow.state(self.data)['requests'] if item['type'] == 'send']), 1)

    def test_normal_receipts_reject_impossible_dates_and_unproven_original_start(self):
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':workflow.stamp(self.data,'one')})
        request=next(item for item in workflow.state(self.data)['requests'] if item['type']=='send')
        with workflow.execution_owner('original'):
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST actual start'})
        baseline=copy.deepcopy(self.data)
        at=datetime.now(timezone.utc)
        event={'id':'TEST normal receipt','type':'sent','opportunityId':'one','packageId':request['packageId'],
               'cv':'outputs/cv.pdf','at':core.now(),'proof':'TEST synthetic receipt',
               'authorization':'TEST explicit permission','confirmation':'TEST receipt number','historyChecked':True}
        invalid=((None,None,(at-timedelta(days=1)).isoformat()),(None,None,(at+timedelta(minutes=6)).isoformat()),
                 ('startedAt',None,event['at']),('startedAt','TEST invalid start',event['at']),
                 ('authorizationAt',None,event['at']),('authorizationAt',(at+timedelta(minutes=1)).isoformat(),event['at']))
        for field,value,sent_at in invalid:
            with self.subTest(field=field,value=value,sent_at=sent_at):
                self.data=copy.deepcopy(baseline)
                if field:self.live(request)[field]=value
                before=copy.deepcopy(self.data)
                with workflow.execution_owner('original'),self.assertRaisesRegex(ValueError,'fecha real|inicio real autorizado'):
                    self.apply({'kind':'event','event':{**event,'at':sent_at}})
                self.assertEqual(self.data,before)
                self.assertFalse(self.data['events'])
        self.data=copy.deepcopy(baseline)
        with workflow.execution_owner('original'):
            self.apply({'kind':'event','event':event})
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'done','proof':'TEST completed'})
        self.assertEqual(self.data['events'][0]['authorizationAt'],self.live(request)['authorizationAt'])
        self.assertEqual(self.data['events'][0]['authorization'],event['authorization'])
        self.assertEqual(self.live(request)['status'],'done')

    def test_normal_legacy_receipt_uses_only_approval_that_preceded_its_actual_start(self):
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':workflow.stamp(self.data,'one')})
        request=next(item for item in workflow.state(self.data)['requests'] if item['type']=='send')
        with workflow.execution_owner('original'):
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST actual legacy start'})
        self.live(request).pop('authorizationAt')
        baseline=copy.deepcopy(self.data)
        event={'id':'TEST normal legacy receipt','type':'sent','opportunityId':'one','packageId':request['packageId'],
               'cv':'outputs/cv.pdf','at':core.now(),'proof':'TEST receipt','authorization':'TEST legacy permission',
               'confirmation':'TEST legacy receipt','historyChecked':True}
        package=next(item for item in workflow.state(self.data)['packages'] if item['id']==request['packageId'])
        package['approvedAt']=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
        before=copy.deepcopy(self.data)
        with workflow.execution_owner('original'),self.assertRaisesRegex(ValueError,'inicio real autorizado'):
            self.apply({'kind':'event','event':event})
        self.assertEqual(self.data,before)
        self.data=copy.deepcopy(baseline)
        with workflow.execution_owner('original'):self.apply({'kind':'event','event':event})
        self.assertEqual(self.data['events'][0]['authorizationAt'],baseline['app']['packages'][-1]['approvedAt'])

    def test_unknown_result_never_permits_retry(self):
        request = self.interrupted()
        self.apply(self.check(request, 'unknown'))
        self.assertFalse(self.data['events'])
        self.assertFalse(request_workflow.delivery_checked(workflow.state(self.data)['requests'][-1], request['packageId']))

    def test_a_stale_portal_check_is_rejected_even_when_the_clock_does_not_advance(self):
        fixed=datetime.now(timezone.utc)
        with patch.object(workflow,'datetime') as clock,patch.object(workflow,'now',return_value=fixed.isoformat(timespec='seconds')):
            clock.now.return_value=fixed
            request=self.interrupted()
            old_check=self.check(request,'not_sent')
            self.apply(self.check(request,'unknown'))
            current=self.live(request)
            self.assertGreater(current['updatedAt'],old_check['expected'])
            before=copy.deepcopy(self.data)
            with self.assertRaises(workflow.Conflict):self.apply(old_check)
            self.assertEqual(self.data,before)
            self.assertEqual(self.live(request)['deliveryCheck']['outcome'],'unknown')
            self.apply(self.check(current,'not_sent'))
            self.assertGreater(self.live(request)['updatedAt'],current['updatedAt'])
            self.assertTrue(request_workflow.delivery_checked(self.live(request),request['packageId']))

    def test_recovered_receipt_keeps_the_archived_cv_hash_and_export_date(self):
        from stubbs_jobs import excel_day
        request = self.revoke(self.interrupted())
        package = next(item for item in workflow.state(self.data)['packages'] if item['id'] == request['packageId'])
        (self.root/'outputs/cv.pdf').write_bytes(b'%PDF-replaced-after-original-send')
        sent_at = core.now()
        self.apply(self.check(request, 'sent', sentAt=sent_at, confirmation='TEST original archived receipt'))
        archived = 'data/packages/' + package['id'] + '/cv.pdf'
        event = self.data['events'][0]
        self.assertEqual(event['cv'], archived)
        self.assertEqual(event['archivedCV'], archived)
        self.assertEqual(event['cvHash'], package['payload']['cvHash'])
        self.assertEqual(event['source'], self.data['sheets']['Oportunidades'][0]['Fuente'])
        self.assertEqual(event['family'], self.data['sheets']['Oportunidades'][0]['Familia'])
        self.assertEqual(event['cohort'], sent_at[:7])
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['CV usado'], archived)
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['Fecha candidatura'], excel_day(sent_at))

    def test_an_invalidated_execution_cannot_change_delivery_check_or_claim_a_receipt(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        request = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST start'})
        live = next(item for item in workflow.state(self.data)['requests'] if item['id'] == request['id'])
        with workflow.execution_owner('replacement'):
            self.apply({'kind': 'ui-request-interrupt', 'id': live['id'], 'expectedUpdatedAt': live['updatedAt'],
                        'expectedExecutionId': 'original', 'proof': 'TEST checked stop',
                        'confirmation': 'TEST person confirmed previous chat stopped'})
        live = next(item for item in workflow.state(self.data)['requests'] if item['id'] == request['id'])
        for outcome in ('not_sent', 'sent'):
            before = copy.deepcopy(self.data)
            with workflow.execution_owner('original'), self.assertRaisesRegex(ValueError, 'retirado'):
                self.apply(self.check(live, outcome, sentAt=core.now(), confirmation='TEST old execution receipt'))
            self.assertEqual(self.data, before)

    def test_wrong_destination_or_stale_expected_state_does_not_record_a_receipt(self):
        request = self.interrupted()
        for values in ({'recipient': 'https://example.org/different'}, {'expected': 'old'}):
            before = copy.deepcopy(self.data)
            with self.assertRaises(ValueError):
                self.apply(self.check(request, 'sent', sentAt=core.now(), confirmation='TEST', **values))
            self.assertEqual(self.data, before)

    def test_expired_portal_check_does_not_permit_retry(self):
        request = self.interrupted()
        self.apply(self.check(request, 'not_sent'))
        live = next(item for item in workflow.state(self.data)['requests'] if item['id'] == request['id'])
        live['deliveryCheck']['at'] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with self.assertRaisesRegex(ValueError, 'compruebe el portal'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST'})

    def test_a_late_receipt_can_preserve_history_after_a_permission_was_revoked(self):
        request = self.revoke(self.interrupted())
        self.assertEqual(request['status'], 'cancelled')
        package = copy.deepcopy(workflow.state(self.data)['packages'][0])
        requests_before = len(workflow.state(self.data)['requests'])
        self.apply(self.check(request, 'sent', sentAt=core.now(), confirmation='TEST actual past receipt'))
        self.assertEqual(len(self.data['events']), 1)
        self.assertEqual(self.data['events'][0]['authorization'], package['approvedAt'])
        self.assertEqual(self.data['events'][0]['packageId'], package['id'])
        self.assertEqual(self.live(request)['status'], 'done')
        self.assertEqual(workflow.state(self.data)['packages'][0]['revokedAt'], package['revokedAt'])
        self.assertEqual(len(workflow.state(self.data)['requests']), requests_before)
        self.assertEqual(len(workflow.state(self.data)['packages']), 1)
        with self.assertRaisesRegex(ValueError, 'ya está enviada'):
            self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        before = copy.deepcopy(self.data)
        with self.assertRaises(ValueError):
            self.apply(self.check(self.live(request), 'sent', sentAt=core.now(), confirmation='TEST duplicate receipt'))
        self.assertEqual(self.data, before)

    def test_cancelled_not_sent_and_unknown_never_resume_or_revive_permission(self):
        request = self.revoke(self.interrupted())
        revoked = workflow.state(self.data)['packages'][0]['revokedAt']
        for outcome in ('not_sent', 'unknown'):
            with self.subTest(outcome=outcome):
                self.apply(self.check(self.live(request), outcome))
                live = self.live(request)
                self.assertEqual(live['status'], 'cancelled')
                self.assertIn('sigue cancelado', live['summary'])
                self.assertFalse(request_workflow.delivery_checked(live, request['packageId']))
                self.assertFalse(self.data['events'])
                self.assertEqual(workflow.state(self.data)['packages'][0]['revokedAt'], revoked)
                before = copy.deepcopy(self.data)
                with self.assertRaisesRegex(ValueError, 'Transición'):
                    self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'TEST forbidden resume'})
                self.assertEqual(self.data, before)

    def test_cancelled_before_real_start_cannot_claim_any_portal_outcome(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        request = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send')
        request = self.revoke(request)
        for outcome in ('sent', 'not_sent', 'unknown'):
            with self.subTest(outcome=outcome):
                before = copy.deepcopy(self.data)
                with self.assertRaisesRegex(ValueError, 'inicio real autorizado'):
                    self.apply(self.check(request, outcome, sentAt=core.now(), confirmation='TEST no started send'))
                self.assertEqual(self.data, before)

    def test_cancelled_check_rejects_changed_package_destination_and_expected_state(self):
        request = self.revoke(self.interrupted())
        for values in ({'packageId': 'different-package'}, {'recipient': 'https://example.org/different'}, {'expected': 'old'}):
            with self.subTest(values=values):
                before = copy.deepcopy(self.data)
                with self.assertRaises(ValueError):
                    self.apply(self.check(request, 'sent', sentAt=core.now(), confirmation='TEST receipt', **values))
                self.assertEqual(self.data, before)

    def test_cancelled_receipt_needs_original_authorized_start_and_valid_receipt_date(self):
        request = self.revoke(self.interrupted())
        baseline = copy.deepcopy(self.data)
        now = datetime.now(timezone.utc)
        invalid = (
            ('startedAt', None), ('startedAt', 'without date'),
            ('startedAt', (now + timedelta(minutes=6)).isoformat()),
            ('authorizationAt', None), ('authorizationAt', (now + timedelta(minutes=6)).isoformat()),
        )
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                self.data = copy.deepcopy(baseline)
                self.live(request)[field] = value
                before = copy.deepcopy(self.data)
                with self.assertRaisesRegex(ValueError, 'inicio real autorizado'):
                    self.apply(self.check(self.live(request), 'sent', sentAt=core.now(), confirmation='TEST bad history'))
                self.assertEqual(self.data, before)
        for sent_at in ((now - timedelta(minutes=6)).isoformat(), (now + timedelta(minutes=6)).isoformat(), '2026-10-01'):
            with self.subTest(sent_at=sent_at):
                self.data = copy.deepcopy(baseline)
                before = copy.deepcopy(self.data)
                with self.assertRaisesRegex(ValueError, 'fecha real'):
                    self.apply(self.check(self.live(request), 'sent', sentAt=sent_at, confirmation='TEST bad receipt date'))
                self.assertEqual(self.data, before)

    def test_legacy_started_request_requires_an_approval_before_its_start(self):
        request = self.revoke(self.interrupted())
        self.live(request).pop('authorizationAt')
        baseline = copy.deepcopy(self.data)
        for approval in (None, (datetime.now(timezone.utc) + timedelta(minutes=6)).isoformat()):
            with self.subTest(approval=approval):
                self.data = copy.deepcopy(baseline)
                workflow.state(self.data)['packages'][0]['approvedAt'] = approval
                before = copy.deepcopy(self.data)
                with self.assertRaisesRegex(ValueError, 'inicio real autorizado'):
                    self.apply(self.check(self.live(request), 'sent', sentAt=core.now(), confirmation='TEST legacy bad history'))
                self.assertEqual(self.data, before)
        self.data = copy.deepcopy(baseline)
        self.apply(self.check(self.live(request), 'sent', sentAt=core.now(), confirmation='TEST legacy approved receipt'))
        self.assertEqual(len(self.data['events']), 1)

    def test_reapproval_does_not_replace_original_authorization_or_leave_a_duplicate_queued(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with patch.object(workflow, 'now', return_value=past):
            request = self.interrupted()
        original_authorization = request['authorizationAt']
        request = self.revoke(request)
        self.apply(self.check(self.live(request), 'not_sent'))
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        duplicate = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send' and item['id'] != request['id'])
        self.assertEqual(duplicate['status'], 'queued')
        self.assertNotEqual(workflow.state(self.data)['packages'][0]['approvedAt'], original_authorization)
        self.apply(self.check(self.live(request), 'sent', sentAt=past, confirmation='TEST original receipt despite reapproval'))
        self.assertEqual(self.data['events'][0]['authorization'], original_authorization)
        self.assertEqual(self.live(duplicate)['status'], 'cancelled')
        self.assertIn('original se confirmó', self.live(duplicate)['result'])
        self.assertTrue(workflow.state(self.data)['packages'][0]['revokedAt'])
        self.assertFalse(any(item['type'] == 'send' and item['status'] == 'queued' for item in workflow.state(self.data)['requests']))
        self.assertEqual(len(self.data['events']), 1)

    def test_new_running_send_must_stop_before_original_receipt_is_conciled(self):
        request = self.revoke(self.interrupted())
        self.apply(self.check(self.live(request), 'not_sent'))
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        duplicate = next(item for item in workflow.state(self.data)['requests'] if item['type'] == 'send' and item['id'] != request['id'])
        with workflow.execution_owner('new-send'):
            self.apply({'kind': 'ui-request-update', 'id': duplicate['id'], 'status': 'running', 'proof': 'TEST new actual attempt'})
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'Detén ese intento'):
            self.apply(self.check(self.live(request), 'sent', sentAt=core.now(), confirmation='TEST receipt with other running send'))
        self.assertEqual(self.data, before)
        with workflow.execution_owner('new-send'):
            self.apply({'kind': 'ui-request-update', 'id': duplicate['id'], 'status': 'interrupted', 'proof': 'TEST stopped newer attempt without sending'})
        self.apply(self.check(self.live(request), 'sent', sentAt=core.now(), confirmation='TEST original receipt after stop'))
        self.assertEqual(len(self.data['events']), 1)
        self.assertFalse(any(item['status'] == 'running' for item in workflow.state(self.data)['requests']))

    def test_changed_material_or_removed_selection_does_not_replace_past_receipt(self):
        request = self.interrupted()
        baseline = copy.deepcopy(self.data)
        cases = (
            {'kind': 'ui-select-opportunity', 'opportunityId': 'one', 'selected': False,
             'expected': copy.deepcopy(workflow.state(self.data)['selections']['one'])},
            {'kind': 'ui-change', 'opportunityId': 'one', 'message': 'TEST revise material', 'actor': 'Persona'},
        )
        for operation in cases:
            with self.subTest(operation=operation['kind']):
                self.data = copy.deepcopy(baseline)
                self.apply(operation)
                revoked = workflow.state(self.data)['packages'][0]['revokedAt']
                self.apply(self.check(self.live(request), 'sent', sentAt=core.now(), confirmation='TEST original receipt'))
                self.assertEqual(self.data['events'][0]['packageId'], request['packageId'])
                self.assertEqual(workflow.state(self.data)['packages'][0]['revokedAt'], revoked)
                self.assertEqual(len([item for item in workflow.state(self.data)['requests'] if item['type'] == 'send']), 1)

    def test_recovered_copy_records_past_receipt_without_restoring_permission(self):
        request = self.interrupted()
        core.save_store(self.data, self.root / 'data/registry.json')
        original = (self.root / 'data/registry.json').read_bytes()
        (self.root / 'data/recovery-original.json').write_bytes(original)
        self.apply({'kind': 'ui-recover-backup', 'expectedRevision': self.data['revision'],
                    'originalHash': core.digest(original), 'proof': 'TEST recovered isolated copy'})
        request = self.live(request)
        self.assertEqual(request['status'], 'cancelled')
        revoked = workflow.state(self.data)['packages'][0]['revokedAt']
        self.apply(self.check(request, 'sent', sentAt=core.now(), confirmation='TEST original receipt after restore'))
        self.assertEqual(self.live(request)['status'], 'done')
        self.assertEqual(workflow.state(self.data)['packages'][0]['revokedAt'], revoked)
        self.assertEqual(workflow.state(self.data)['selections']['one']['mode'], 'review')
        self.assertEqual(len(self.data['events']), 1)
        self.assertEqual((self.root / 'data/registry.json').read_bytes(), original)

    def test_missing_receipt_date_or_confirmation_never_claims_delivery(self):
        request = self.interrupted()
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'fecha real'):
            self.apply(self.check(request, 'sent'))
        self.assertEqual(self.data, before)


if __name__ == '__main__':
    unittest.main()
