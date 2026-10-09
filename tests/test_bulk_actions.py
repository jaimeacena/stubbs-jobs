import copy
import unittest
from unittest.mock import patch
from workflow_fixtures import WorkflowFixture
import app_workflow as workflow
import offer_actions
import stubbs_jobs as jobs


class BulkActionsTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        second = copy.deepcopy(self.row)
        second.update({'ID': 'two', 'Clave canónica': 'two', 'Empresa': 'Second',
                       'URL original': 'https://example.org/jobs/two'})
        self.data['sheets']['Oportunidades'].append(second)
        workflow.draft(self.data, 'two')['requiredAnswers'] = []

    def bulk(self, action, keys=('one', 'two'), **extra):
        self.apply({'kind': 'ui-bulk-action', 'action': action,
                    'targets': [{'id': key} for key in keys],
                    'expectedRevision': self.data['revision'], 'actor': 'Usuario', **extra})

    def test_positive_outcome_is_terminal_and_preserves_sent_material(self):
        self.review();package=self.data['app']['packages'][0];package['approvedAt']=workflow.now()
        self.data['events'].append({'id':'receipt','type':'sent','opportunityId':'one','packageId':package['id'],
                                  'at':'2026-10-01T10:00:00Z','proof':'TEST: original enviado'})
        workflow.row_for(self.data,'one')['Estado']='Enviada'
        self.data['app']['requests'].append({'id':'pending-check','type':'investigate','purpose':'followup','opportunityId':'one','status':'queued'})
        packages=copy.deepcopy(self.data['app']['packages']);events=copy.deepcopy(self.data['events'])
        self.bulk('achieve',('one',))
        self.assertEqual(workflow.archived(self.data,'one')['outcome'],'achieved')
        self.assertEqual(jobs.view(self.data)['sheets']['Oportunidades'][0]['Estado'],'Lograda')
        self.assertEqual(self.data['events'],events);self.assertEqual(self.data['app']['packages'],packages)
        self.assertEqual(self.data['app']['requests'][-1]['status'],'cancelled')
        self.assertFalse(workflow.selection(self.data,'one'));self.assertEqual(offer_actions.available(self.data,'one',workflow),set())
        undo=self.data['app']['undo'][-1];self.assertFalse(workflow.undo_available(self.data,undo))
        before=copy.deepcopy(self.data)
        for action in ('close','mark-rejected','reopen-followup','archive','achieve'):
            with self.assertRaises(workflow.Conflict):self.bulk(action,('one',))
            self.assertEqual(self.data,before)
        with self.assertRaises(ValueError):self.apply({'kind':'ui-undo','id':undo['id']})
        self.assertEqual(self.data,before)

    def test_personal_results_require_submission_and_do_not_invent_employer_events(self):
        before=copy.deepcopy(self.data)
        for action in ('achieve','mark-rejected','close'):
            with self.assertRaises(workflow.Conflict):self.bulk(action,('one',))
            self.assertEqual(self.data,before)
        receipt={'id':'receipt','type':'sent','opportunityId':'one','at':'2026-10-01T10:00:00Z','proof':'TEST: original'}
        self.data['events'].append(receipt);workflow.row_for(self.data,'one')['Estado']='Enviada'
        before=copy.deepcopy(self.data)
        with self.assertRaises(workflow.Conflict):self.bulk('achieve',('one','two'))
        self.assertEqual(self.data,before)
        for action, outcome, label in [('mark-rejected','rejected','Rechazada'),('close','closed','Cerrada'),('achieve','achieved','Lograda')]:
            self.bulk(action,('one',))
            self.assertEqual(workflow.archived(self.data,'one')['outcome'],outcome)
            self.assertEqual(workflow.archived(self.data,'one')['source'],'user_reported')
            self.assertEqual(jobs.view(self.data)['sheets']['Oportunidades'][0]['Estado'],label)
            self.assertEqual(self.data['events'],[receipt])
            self.assertFalse(workflow.selection(self.data,'one'))

    def test_agent_cannot_claim_a_manual_positive_or_negative_result(self):
        self.data['events'].append({'id':'receipt','type':'sent','opportunityId':'one','at':'2026-10-01T10:00:00Z','proof':'TEST: original'})
        workflow.row_for(self.data,'one')['Estado']='Enviada';before=copy.deepcopy(self.data)
        for action in ('achieve','mark-rejected'):
            with self.assertRaisesRegex(ValueError,'persona'):self.bulk(action,('one',),actor='Agente')
            self.assertEqual(self.data,before)

    def test_choice_is_atomic_and_keeps_each_mode_and_request_separate(self):
        with patch.object(jobs, 'conditions', return_value=('Sí', 'Pendiente', False)):
            self.bulk('select-review')
        self.assertEqual({workflow.selection(self.data, key)['mode'] for key in ('one', 'two')}, {'review'})
        self.assertEqual({r['opportunityId'] for r in self.data['app']['requests']}, {'one', 'two'})
        self.assertTrue(all(r['status'] == 'queued' and r['type'] != 'send' for r in self.data['app']['requests']))
        self.assertEqual(len(self.data['appliedBatches']), 1)

    def test_discard_and_reject_have_distinct_scopes_and_keep_original_receipts(self):
        receipt={'id':'sent-test','type':'sent','opportunityId':'two','at':workflow.now(),'proof':'TEST: solicitud original confirmada.'}
        self.data['events'].append(receipt)
        workflow.row_for(self.data,'two')['Estado']='Enviada'
        before=copy.deepcopy(self.data)
        for action,keys in [('reject',('one',)),('discard',('two',)),('discard',('one','two'))]:
            with self.assertRaises(workflow.Conflict):self.bulk(action,keys)
            self.assertEqual(self.data,before)
        self.bulk('discard',('one',))
        self.bulk('reject',('two',))
        self.assertEqual(workflow.archived(self.data,'one')['outcome'],'discarded')
        self.assertEqual(workflow.archived(self.data,'two')['outcome'],'closed')
        self.assertEqual(self.data['events'],[receipt])
        self.assertEqual(workflow.row_for(self.data,'two')['Estado'],'Enviada')
        self.assertIn('por ti',workflow.archived(self.data,'two')['reason'])
        undo=self.data['app']['undo'][-1]
        self.apply({'kind':'ui-undo','id':undo['id']})
        self.assertFalse(workflow.archived(self.data,'two'))
        self.assertEqual(self.data['events'],[receipt])
        self.assertIsNone(workflow.selection(self.data,'two'))

    def test_interpretation_changes_are_available_after_discard_without_reopening(self):
        self.bulk('discard',('one',))
        archive=copy.deepcopy(workflow.archived(self.data,'one'))
        self.apply({'kind':'ui-change','opportunityId':'one','message':'TEST: revisa el requisito de experiencia.'})
        request=next(r for r in self.data['app']['requests'] if r['type']=='change')
        self.assertTrue(request['interpretationOnly'])
        self.assertEqual(request['status'],'queued')
        self.assertEqual(workflow.archived(self.data,'one'),archive)
        self.assertIsNone(workflow.selection(self.data,'one'))
        self.assertFalse(workflow.pending_change(self.data,'one'))
        with self.assertRaises(ValueError):self.apply({'kind':'ui-request','opportunityId':'one','type':'investigate'})
        self.apply({'kind':'ui-undo','id':self.data['app']['undo'][-1]['id']})
        self.assertEqual(next(r for r in self.data['app']['requests'] if r['id']==request['id'])['status'],'cancelled')
        self.assertEqual(workflow.archived(self.data,'one'),archive)

    def test_interpretation_change_preserves_a_submitted_package_and_its_authorization(self):
        self.review()
        package=copy.deepcopy(self.data['app']['packages'][0])
        self.data['app']['packages'][0]['approvedAt']=workflow.now()
        self.data['events'].append({'id':'sent-test','type':'sent','opportunityId':'one','packageId':package['id'],'at':workflow.now(),'proof':'TEST: original enviado.'})
        workflow.row_for(self.data,'one')['Estado']='Enviada'
        self.bulk('reject',('one',))
        packages=copy.deepcopy(self.data['app']['packages']);events=copy.deepcopy(self.data['events'])
        self.apply({'kind':'ui-change','opportunityId':'one','message':'TEST: revisa mi encaje con la oferta.'})
        self.assertEqual(self.data['app']['packages'],packages)
        self.assertEqual(self.data['events'],events)
        self.assertTrue(workflow.archived(self.data,'one'))
        self.assertTrue(self.data['app']['requests'][-1]['interpretationOnly'])

    def test_undoing_a_discard_allows_a_new_choice_without_reviving_permissions(self):
        self.bulk('discard',('one',))
        closure=next(item for item in self.data['app']['undo'] if item['kind']=='offer-archive')
        self.apply({'kind':'ui-change','opportunityId':'one','message':'TEST: revisa la interpretación.'})
        self.apply({'kind':'ui-undo','id':closure['id']})
        self.assertFalse(workflow.archived(self.data,'one'))
        self.assertIsNone(workflow.selection(self.data,'one'))
        self.assertIn('select-review',offer_actions.available(self.data,'one',workflow))
        self.bulk('select-review',('one',))
        self.assertEqual({r['type'] for r in self.data['app']['requests'] if r['status']=='queued'},{'change','review'})
        self.assertFalse(any(p.get('approvedAt') for p in self.data['app']['packages']))

    def test_interpretation_request_during_sending_does_not_modify_or_take_the_running_send(self):
        self.review();package=self.data['app']['packages'][0];package['approvedAt']=workflow.now()
        running={'id':'running-test','type':'send','status':'running','opportunityId':'one','packageId':package['id'],'executionId':'original-owner','startedAt':workflow.now(),'updatedAt':workflow.now()}
        self.data['app']['requests'].append(running)
        packages=copy.deepcopy(self.data['app']['packages']);before=copy.deepcopy(running)
        self.apply({'kind':'ui-change','opportunityId':'one','message':'TEST: revisa después la lectura de esta oferta.'})
        self.assertEqual(self.data['app']['packages'],packages)
        self.assertEqual(next(r for r in self.data['app']['requests'] if r['id']==running['id']),before)
        self.assertFalse(workflow.pending_change(self.data,'one'))
        self.assertTrue(self.data['app']['requests'][-1]['interpretationOnly'])

    def test_historical_interpretation_keeps_global_changes_separate_and_does_not_revoke(self):
        self.data['historicalApplications'].append({'id':'old','company':'Old','title':'Analyst','category':'Laboral','state':'Rechazada','url':'https://example.org/old','proof':'TEST histórico.'})
        self.apply({'kind':'ui-change','message':'TEST: cambio general pendiente.'})
        original=copy.deepcopy(self.data['app']['requests'][0])
        self.apply({'kind':'ui-change','opportunityId':'historical:old','message':'TEST: revisa esta interpretación.'})
        self.assertEqual(self.data['app']['requests'][0],original)
        self.assertEqual(len(self.data['app']['requests']),2)
        request=self.data['app']['requests'][-1]
        self.assertTrue(request['interpretationOnly'])
        self.assertIsNone(request['opportunityId'])
        self.assertIn('historical:old',request['instructions'][0]['text'])

    def test_second_ineligible_offer_rolls_back_the_entire_set(self):
        self.data['app']['requests'].append({'id': 'busy', 'type': 'investigate', 'status': 'blocked', 'opportunityId': 'two'})
        before = copy.deepcopy(self.data)
        with patch.object(jobs, 'conditions', return_value=('Sí', 'Pendiente', False)), self.assertRaises(workflow.Conflict):
            self.bulk('select-auto')
        self.assertEqual(self.data, before)

    def test_explicit_compatible_subset_does_not_mutate_the_other_offer(self):
        request = {'id': 'busy', 'type': 'investigate', 'status': 'blocked', 'opportunityId': 'two'}
        self.data['app']['requests'].append(request)
        with patch.object(jobs, 'conditions', return_value=('Sí', 'Pendiente', False)):
            workflow.reconcile(self.data)
            other_row = copy.deepcopy(workflow.row_for(self.data, 'two'))
            other_draft = copy.deepcopy(workflow.draft(self.data, 'two'))
            self.bulk('select-review', ('one',))
        self.assertTrue(workflow.selection(self.data, 'one')['selected'])
        self.assertIsNone(workflow.selection(self.data, 'two'))
        self.assertEqual(workflow.row_for(self.data, 'two'), other_row)
        self.assertEqual(workflow.draft(self.data, 'two'), other_draft)
        self.assertIn(request, self.data['app']['requests'])

    def test_stale_revision_unknown_duplicate_and_unsupported_actions_do_not_write(self):
        for action, keys, extra in [('archive', ('one', 'one'), {}), ('archive', ('one', 'missing'), {}),
                                    ('archive', ('one',), {'expectedRevision': -1}), ('send', ('one',), {})]:
            before = copy.deepcopy(self.data)
            with self.assertRaises((ValueError, workflow.Conflict)):
                self.bulk(action, keys, **extra)
            self.assertEqual(self.data, before)

    def test_archive_preserves_receipts_and_running_owner_but_revokes_future_permissions(self):
        app = self.data['app']
        app['selections'] = {key: {'selected': True, 'mode': 'auto', 'at': workflow.now()} for key in ('one', 'two')}
        app['packages'] = [{'id': 'p-one', 'opportunityId': 'one', 'approvedAt': workflow.now()},
                           {'id': 'p-two', 'opportunityId': 'two', 'approvedAt': workflow.now()}]
        app['requests'] = [{'id': 'queued', 'opportunityId': 'one', 'type': 'send', 'status': 'queued', 'packageId': 'p-one'},
                           {'id': 'running', 'opportunityId': 'two', 'type': 'send', 'status': 'running',
                            'startedAt': workflow.now(), 'executionId': 'owner-original', 'packageId': 'p-two'}]
        running = copy.deepcopy(app['requests'][1])
        rows = copy.deepcopy(self.data['sheets']['Oportunidades'])
        self.bulk('archive')
        app = self.data['app']
        self.assertEqual(app['requests'][1], running)
        self.assertEqual(self.data['sheets']['Oportunidades'], rows)
        self.assertEqual(app['selections'], {})
        self.assertTrue(all(p.get('revokedAt') for p in app['packages']))
        self.assertEqual(app['requests'][0]['status'], 'cancelled')
        for key in ('one', 'two'):
            self.assertTrue(workflow.archived(self.data, key))
            with self.assertRaises(ValueError):
                self.apply({'kind': 'ui-request', 'type': 'investigate', 'opportunityId': key})
        undo = next(item for item in app['undo'] if item['kind'] == 'offer-archive')
        self.apply({'kind': 'ui-undo', 'id': undo['id'], 'actor': 'Usuario'})
        self.assertFalse(workflow.archived(self.data, 'one'))
        self.assertEqual(self.data['app']['selections'], {})
        self.assertTrue(all(p.get('revokedAt') for p in self.data['app']['packages']))
        self.assertEqual(self.data['app']['requests'][1], running)

    def test_sent_closed_and_historical_can_be_archived_together_without_losing_facts(self):
        self.data['events'].append({'type': 'sent', 'opportunityId': 'one', 'packageId': 'p-one', 'at': workflow.now(), 'proof': 'TEST receipt'})
        self.data['app']['packages'].append({'id': 'p-one', 'opportunityId': 'one', 'approvedAt': workflow.now()})
        self.data['sheets']['Oportunidades'][1]['Estado'] = 'Cerrada'
        self.data['historicalApplications'].append({'id': 'old', 'state': 'Rechazada'})
        receipt = copy.deepcopy(self.data['events'][0])
        self.bulk('archive', ('one', 'two', 'historical:old'))
        self.assertEqual(self.data['events'][0], receipt)
        self.assertNotIn('revokedAt', self.data['app']['packages'][0])
        self.assertTrue(workflow.archived(self.data, 'one'))
        self.assertEqual(self.data['historicalApplications'], [{'id': 'old', 'state': 'Rechazada'}])
        self.assertEqual(jobs.view(self.data)['sheets']['Oportunidades'][0]['Estado'], 'Cerrada')

    def test_completed_batch_replay_is_idempotent(self):
        operation = {'kind': 'ui-bulk-action', 'action': 'archive', 'targets': [{'id': 'one'}],
                     'expectedRevision': 0, 'actor': 'Usuario'}
        batch = {'id': 'same-attempt', 'operations': [operation]}
        self.assertTrue(jobs.apply_batch(self.data, batch))
        before = copy.deepcopy(self.data)
        self.assertFalse(jobs.apply_batch(self.data, batch))
        self.assertEqual(self.data, before)

    def test_automatic_choices_remain_individual_and_do_not_queue_sends_before_review(self):
        with patch.object(jobs, 'conditions', return_value=('Sí', 'Pendiente', False)):
            self.bulk('select-auto')
        self.assertEqual({workflow.selection(self.data, key)['mode'] for key in ('one', 'two')}, {'auto'})
        self.assertEqual({r['type'] for r in self.data['app']['requests']}, {'review'})
        self.assertFalse(any(p.get('approvedAt') for p in self.data['app']['packages']))

    def response_targets(self, second_city='TEST Ciudad'):
        for key in ('one', 'two'):
            draft = workflow.draft(self.data, key)
            draft['requiredAnswers'] = ['currentCity', 'custom_tool']
            draft['questions'] = [{'key': 'custom_tool', 'label': 'Herramienta', 'type': 'text', 'scope': 'opportunity'}]
        return [{'id': key, 'fingerprint': workflow.stamp(self.data, key),
                 'values': {'currentCity': 'TEST Ciudad' if key == 'one' else second_city, 'custom_tool': 'TEST ' + key},
                 'expected': {'currentCity': None, 'custom_tool': None}} for key in ('one', 'two')]

    def test_shared_and_specific_answers_keep_their_scope_in_one_batch(self):
        targets = self.response_targets()
        self.bulk('responses', targets=targets)
        self.assertEqual(self.data['profile']['currentCity'], 'TEST Ciudad')
        self.assertNotIn('custom_tool', self.data['profile'])
        for key in ('one', 'two'):
            self.assertEqual(workflow.draft(self.data, key)['answers']['custom_tool'], 'TEST ' + key)
        writes = [event for event in self.data['app']['history'] if event['title'] == 'Respuestas guardadas']
        self.assertEqual(len(writes), 2)

    def test_conflicting_shared_answers_and_stale_case_rollback_without_partial_updates(self):
        for city, stale in [('TEST Distinta', False), ('TEST Ciudad', True)]:
            targets = self.response_targets(city)
            if stale:
                targets[1]['fingerprint'] = 'stale'
            before = copy.deepcopy(self.data)
            with self.assertRaises((ValueError, workflow.Conflict)):
                self.bulk('responses', targets=targets)
            self.assertEqual(self.data, before)

    def test_group_approval_checks_every_frozen_package_and_never_records_a_send(self):
        workflow.draft(self.data, 'one')['requiredAnswers'] = []
        workflow.draft(self.data, 'two').update(messageUsage='unused',formAnswerKeys=[])
        with patch.object(jobs, 'conditions', return_value=('Sí', 'Pendiente', False)):
            self.review()
            self.data['app']['selections']['two'] = {'selected': True, 'mode': 'review', 'at': workflow.now()}
            self.apply({'kind': 'ui-review', 'opportunityId': 'two',
                        'checks': {key: True for key in workflow.CHECKS}, 'proof': 'TEST revisión de los cinco requisitos.',
                        'fingerprint': workflow.stamp(self.data, 'two')})
            targets = [{'id': key, 'fingerprint': workflow.stamp(self.data, key)} for key in ('one', 'two')]
            stale = copy.deepcopy(targets)
            stale[1]['fingerprint'] = 'old-package'
            before = copy.deepcopy(self.data)
            with self.assertRaises(workflow.Conflict):
                self.bulk('approve', targets=stale)
            self.assertEqual(self.data, before)
            self.bulk('approve', targets=targets)
        self.assertEqual({r['opportunityId'] for r in self.data['app']['requests'] if r['type'] == 'send'}, {'one', 'two'})
        self.assertTrue(all(r['status'] == 'queued' for r in self.data['app']['requests']))
        self.assertFalse(any(e['type'] == 'sent' for e in self.data['events']))

    def test_brief_multi_case_view_contains_full_answers_only_for_requested_cases(self):
        import stubbs_jobs_app as server
        third = copy.deepcopy(self.row)
        third['ID'] = 'third'
        self.data['sheets']['Oportunidades'].append(third)
        self.data['updatedAt'] = workflow.now()
        workflow.seed(self.data)
        with patch.object(server, 'ROOT', self.root), patch.object(server, 'DATA', self.root / 'data'), \
             patch.object(server.agent_runner, 'peek', return_value={'status': 'idle'}):
            view = server.state_view(self.data, brief=True, case=['one', 'two'], pure=True)
        rows = {row['id']: row for row in view['opportunities']}
        self.assertIn('answers', rows['one'])
        self.assertIn('answers', rows['two'])
        self.assertNotIn('answers', rows['third'])

    def test_archived_uncertain_send_can_record_original_receipt_without_restoring_permission(self):
        import agent_runner
        from test_delivery_recovery import DeliveryRecoveryTests
        with patch.object(agent_runner, 'read_state', return_value={'status': 'idle'}), \
             patch.object(agent_runner, 'view', return_value={'status': 'idle'}):
            request = DeliveryRecoveryTests.interrupted(self)
            self.bulk('archive', ('one',))
            check = DeliveryRecoveryTests.check(self, request, 'sent',
                    sentAt=workflow.now(), confirmation='TEST: recibo original ficticio')
            with workflow.execution_owner('receipt-checker'):
                self.apply(check)
        self.assertTrue(workflow.archived(self.data, 'one'))
        self.assertEqual(len(self.data['events']), 1)
        self.assertEqual(self.data['events'][0]['packageId'], request['packageId'])
        self.assertTrue(self.data['app']['packages'][0].get('revokedAt'))
        self.assertFalse(workflow.selection(self.data, 'one'))


if __name__ == '__main__':
    unittest.main()
