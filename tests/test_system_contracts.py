"""Fictional writer-level regressions for scope, delivery and causal continuation."""
import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

from workflow_fixtures import WorkflowFixture
import agent_runner
import app_workflow as w
import app_context as c
import offer_quality
import request_workflow
import stubbs_jobs_core as core
import stubbs_jobs


class SystemContractsTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        WorkflowFixture.setUp(self)
        for name in ('read_state','view'):
            replacement=patch.object(agent_runner,name,return_value={'status':'idle'})
            replacement.start();self.addCleanup(replacement.stop)

    def send_interrupted(self):
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        request=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
        with w.execution_owner('original'):
            self.update(request,'running')
            self.update(request,'interrupted')
        return self.live(request)

    def live(self,request):
        return next(item for item in w.state(self.data)['requests'] if item['id']==request['id'])

    def test_preavisos_are_form_answers_and_internal_salary_limit_is_not(self):
        self.apply({'kind':'ui-draft','opportunityId':'one',
                    'values':{'requiredAnswers':['noticeDays'],'formAnswerKeys':['noticeDays']},
                    'expected':{'requiredAnswers':[],'formAnswerKeys':None}})
        self.assertEqual(w.payload(self.data,'one')['answers']['noticeDays'],15)
        self.assertNotIn('Días de preaviso',w.missing(self.data,'one'))
        self.review()
        packet=w.state(self.data)['packages'][-1]
        self.assertEqual(packet['payload']['formAnswerKeys'],['noticeDays'])
        self.assertEqual(packet['payload']['answers']['noticeDays'],15)
        self.assert_rejected_unchanged({'kind':'ui-draft','opportunityId':'one',
                    'values':{'formAnswerKeys':['minimumFixed']},
                    'expected':{'formAnswerKeys':['noticeDays']}},'formulario')

    def test_optional_custom_form_answers_use_only_their_confirmed_scope(self):
        fields=[{'key':'custom_optional','label':'TEST optional language','type':'text','scope':'global'},
                {'key':'custom_local','label':'TEST local question','type':'text','scope':'opportunity'}]
        self.apply({'kind':'ui-draft','opportunityId':'one',
                    'values':{'questions':fields,'formAnswerKeys':['custom_optional','custom_local']},
                    'expected':{'questions':None,'formAnswerKeys':None}})
        self.apply({'kind':'ui-profile','opportunityId':'one','scope':'global',
                    'values':{'custom_optional':'TEST confirmed global'},'expected':{'custom_optional':None}})
        self.assertEqual(w.answers(self.data,'one')['custom_optional'],'TEST confirmed global')
        self.assertNotIn('custom_local',w.answers(self.data,'one'))
        self.apply({'kind':'ui-profile','opportunityId':'one','scope':'opportunity',
                    'values':{'custom_optional':'TEST override','custom_local':'TEST local'},
                    'expected':{'custom_optional':None,'custom_local':None}})
        self.assertEqual(w.payload(self.data,'one')['answers']['custom_optional'],'TEST override')
        self.assertEqual(w.payload(self.data,'one')['answers']['custom_local'],'TEST local')
        self.assertEqual(self.data['profile']['custom_optional'],'TEST confirmed global')
        self.apply({'kind':'ui-draft','opportunityId':'one','values':{'answers':{},'formAnswerKeys':[]},
                    'expected':{'answers':copy.deepcopy(w.draft(self.data,'one')['answers']),
                                'formAnswerKeys':['custom_optional','custom_local']}})
        self.assertNotIn('custom_optional',w.answers(self.data,'one'))

    def test_changing_an_optional_global_form_answer_retires_the_exact_queued_package(self):
        self.apply({'kind':'ui-draft','opportunityId':'one',
                    'values':{'questions':[{'key':'custom_optional','label':'TEST optional answer','type':'text','scope':'global'}],
                              'formAnswerKeys':['custom_optional']},
                    'expected':{'questions':None,'formAnswerKeys':None}})
        self.apply({'kind':'ui-responses','opportunityId':'one','values':{'custom_optional':'TEST original'},
                    'expected':{'custom_optional':None}})
        self.review();self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        package=copy.deepcopy(w.state(self.data)['packages'][-1])
        send=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
        self.apply({'kind':'ui-responses','opportunityId':'one','values':{'custom_optional':'TEST revised'},
                    'expected':{'custom_optional':'TEST original'}})
        kept=next(item for item in w.state(self.data)['packages'] if item['id']==package['id'])
        self.assertNotEqual(w.stamp(self.data,'one'),package['id'])
        self.assertEqual(kept['payload'],package['payload'])
        self.assertEqual(kept['approvedAt'],package['approvedAt'])
        self.assertTrue(kept['revokedAt'])
        self.assertEqual(self.live(send)['status'],'cancelled')
        self.assertFalse(any(item['type']=='send' and item['status']=='queued' for item in w.state(self.data)['requests']))
        self.assertIn('Revisión final del agente',w.readiness(self.data,'one'))

    def test_optional_local_answer_cannot_change_during_actual_sending(self):
        self.apply({'kind':'ui-draft','opportunityId':'one',
                    'values':{'questions':[{'key':'custom_optional','label':'TEST optional answer','type':'text','scope':'opportunity'}],
                              'formAnswerKeys':['custom_optional']},
                    'expected':{'questions':None,'formAnswerKeys':None}})
        self.apply({'kind':'ui-responses','opportunityId':'one','values':{'custom_optional':'TEST local'},
                    'expected':{'custom_optional':None}})
        self.review();self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        send=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
        with w.execution_owner('TEST sender'):self.update(send,'running')
        self.assert_rejected_unchanged({'kind':'ui-responses','opportunityId':'one',
                    'values':{'custom_optional':'TEST changed'},'expected':{'custom_optional':'TEST local'}},'en curso')
        self.assertEqual(w.draft(self.data,'one')['answers']['custom_optional'],'TEST local')
        self.assertEqual(self.live(send)['status'],'running')

    def test_removing_an_optional_question_requires_retiring_its_form_use_together(self):
        field={'key':'custom_optional','label':'TEST local optional answer','type':'text','scope':'opportunity'}
        self.apply({'kind':'ui-draft','opportunityId':'one',
                    'values':{'questions':[field],'formAnswerKeys':['custom_optional']},
                    'expected':{'questions':None,'formAnswerKeys':None}})
        self.apply({'kind':'ui-responses','opportunityId':'one','values':{'custom_optional':'TEST preserved answer'},
                    'expected':{'custom_optional':None}})
        self.review()
        original=copy.deepcopy(w.state(self.data)['packages'][-1])
        archive=self.root/'data/packages'/original['id']/'package.json'
        raw=archive.read_bytes()
        self.assert_rejected_unchanged({'kind':'ui-draft','opportunityId':'one','values':{'questions':[]},
                    'expected':{'questions':[field]}},'formulario')
        self.apply({'kind':'ui-draft','opportunityId':'one','values':{'questions':[],'formAnswerKeys':[]},
                    'expected':{'questions':[field],'formAnswerKeys':['custom_optional']}})
        self.assertEqual(w.draft(self.data,'one')['answers']['custom_optional'],'TEST preserved answer')
        self.assertEqual(c.question_catalog(self.data)['custom_optional'],field)
        self.assertNotIn('custom_optional',c.definitions(self.data,'one'))
        self.assertEqual(w.payload(self.data,'one')['formAnswerKeys'],[])
        self.assertEqual(w.state(self.data)['packages'][-1]['payload'],original['payload'])
        self.assertEqual(archive.read_bytes(),raw)
        self.assert_rejected_unchanged({'kind':'ui-responses','opportunityId':'one',
                    'values':{'custom_optional':'TEST unrequested change'},'expected':{'custom_optional':'TEST preserved answer'}},'desconocida')

    def update(self,request,status):
        self.apply({'kind':'ui-request-update','id':request['id'],'status':status,'proof':'TEST fictional step'})

    def check(self,request,outcome):
        request=self.live(request)
        package=next(item for item in w.state(self.data)['packages'] if item['id']==request['packageId'])
        self.apply({'kind':'ui-delivery-check','id':request['id'],'expected':request['updatedAt'],
                    'packageId':package['id'],'recipient':package['payload']['recipient'],
                    'outcome':outcome,'proof':'TEST fictional portal result'})

    def new_material(self):
        d=w.draft(self.data,'one')
        self.apply({'kind':'ui-draft','opportunityId':'one','values':{'message':'TEST changed application'},
                    'expected':{'message':d['message']}})

    def assert_rejected_unchanged(self,operation,reason):
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,reason):self.apply(operation)
        self.assertEqual(self.data,before)

    def test_revoke_reapprove_cannot_erase_an_unresolved_attempt(self):
        request=self.send_interrupted()
        self.apply({'kind':'ui-revoke','packageId':request['packageId']})
        self.assert_rejected_unchanged({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')},'anterior')
        self.assertEqual(self.live(request)['status'],'cancelled')
        self.assertEqual(len([item for item in w.state(self.data)['requests'] if item['type']=='send']),1)

    def test_new_packet_manual_or_auto_cannot_erase_unknown_delivery(self):
        request=self.send_interrupted()
        self.new_material();self.review()
        self.assert_rejected_unchanged({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')},'anterior')
        # A saved automatic selection must obey the same guard as manual approval.
        w.state(self.data)['selections']['one']['mode']='auto'
        self.assert_rejected_unchanged({'kind':'ui-review','opportunityId':'one','fingerprint':w.stamp(self.data,'one'),
            'checks':{key:True for key in w.CHECKS},'proof':'TEST automatic review'},'anterior')
        self.assertIsNone(self.live(request).get('deliveryCheck'))

    def test_old_queued_duplicate_cannot_start_after_guard_upgrade(self):
        request=self.send_interrupted()
        # A legacy duplicate is a fixture, not a mutation of a real record.
        duplicate={**copy.deepcopy(request),'id':'TEST-legacy-duplicate','status':'queued'}
        for key in ('startedAt','executionId','authorizationAt'):duplicate.pop(key,None)
        w.state(self.data)['requests'].append(duplicate)
        with w.execution_owner('replacement'):
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':duplicate['id'],'status':'running','proof':'TEST'},'anterior')

    def test_cancelled_absence_allows_one_fresh_attempt_but_not_another_unknown(self):
        request=self.send_interrupted()
        self.apply({'kind':'ui-revoke','packageId':request['packageId']})
        self.check(request,'not_sent')
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        second=next(item for item in w.state(self.data)['requests'] if item['type']=='send' and item['id']!=request['id'])
        with w.execution_owner('replacement'):
            self.update(second,'running');self.update(second,'interrupted')
        self.assertEqual(self.live(request)['deliveryCheck']['consumedByRequestId'],second['id'])
        self.assertEqual(w.superseded_sends(self.data),{request['id']:second['id']})
        self.apply({'kind':'ui-revoke','packageId':second['packageId']})
        self.assert_rejected_unchanged({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')},'anterior')
        self.check(second,'not_sent')
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})

    def test_absence_caducity_or_unknown_does_not_allow_new_approval(self):
        request=self.send_interrupted();self.apply({'kind':'ui-revoke','packageId':request['packageId']})
        self.check(request,'unknown')
        self.assert_rejected_unchanged({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')},'anterior')
        self.check(request,'not_sent')
        self.live(request)['deliveryCheck']['at']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        self.assert_rejected_unchanged({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')},'anterior')

    def test_cancelled_queued_successor_does_not_consume_portal_absence(self):
        request=self.send_interrupted();self.apply({'kind':'ui-revoke','packageId':request['packageId']})
        self.check(request,'not_sent')
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        second=next(item for item in w.state(self.data)['requests'] if item['type']=='send' and item['id']!=request['id'])
        self.assertNotIn('consumedByRequestId',self.live(request)['deliveryCheck'])
        self.apply({'kind':'ui-revoke','packageId':second['packageId']})
        self.assertNotIn('startedAt',self.live(second))
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        third=next(item for item in w.state(self.data)['requests'] if item['type']=='send' and item['status']=='queued')
        with w.execution_owner('new-actual-attempt'):self.update(third,'running')
        self.assertEqual(self.live(request)['deliveryCheck']['consumedByRequestId'],third['id'])

    def test_consuming_portal_absence_invalidates_older_checks_without_changing_their_proof_date(self):
        request=self.send_interrupted();self.apply({'kind':'ui-revoke','packageId':request['packageId']})
        self.check(request,'not_sent')
        original=copy.deepcopy(self.live(request))
        package=next(p for p in w.state(self.data)['packages'] if p['id']==request['packageId'])
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        successor=next(item for item in w.state(self.data)['requests'] if item['type']=='send' and item['status']=='queued')
        self.assertEqual(self.live(request)['updatedAt'],original['updatedAt'])
        with w.execution_owner('successor'):self.update(successor,'running')
        current=self.live(request)
        self.assertGreater(current['updatedAt'],original['updatedAt'])
        self.assertEqual(current['deliveryCheck']['at'],original['deliveryCheck']['at'])
        self.assertEqual(current['deliveryCheck']['proof'],original['deliveryCheck']['proof'])
        self.assertEqual(current['deliveryCheck']['consumedByRequestId'],successor['id'])
        self.assert_rejected_unchanged({'kind':'ui-delivery-check','id':request['id'],'expected':original['updatedAt'],
                    'packageId':package['id'],'recipient':package['payload']['recipient'],
                    'outcome':'not_sent','proof':'TEST obsolete check'},'cambió')

    def test_broken_legacy_consumption_pointer_does_not_hide_uncertainty(self):
        request=self.send_interrupted();self.check(request,'not_sent')
        self.live(request)['deliveryCheck']['consumedByRequestId']='TEST-nonexistent-successor'
        self.assertFalse(w.superseded_sends(self.data))
        self.assertEqual([item['id'] for item in w.unresolved_sends(self.data,'one')],[request['id']])
        self.assert_rejected_unchanged({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')},'anterior')
        self.check(request,'not_sent')
        self.assertFalse(w.unresolved_sends(self.data,'one'))

    def test_handoff_and_report_exclude_superseded_attempt_with_legacy_queued_state(self):
        original=self.send_interrupted()
        self.apply({'kind':'ui-revoke','packageId':original['packageId']})
        self.check(original,'not_sent')
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        successor=next(item for item in w.state(self.data)['requests'] if item['type']=='send' and item['id']!=original['id'])
        with w.execution_owner('TEST-actual-successor'):self.update(successor,'running')
        # Simulate a retained legacy status; the validated absence and real successor
        # were recorded through the writer and must remain the governing evidence.
        self.live(original)['status']='queued'
        absence=copy.deepcopy(self.live(original)['deliveryCheck'])
        self.assertEqual(w.superseded_sends(self.data),{original['id']:successor['id']})
        self.apply({'kind':'ui-request','type':'discovery'})
        discovery=next(item for item in w.state(self.data)['requests'] if item['type']=='discovery')
        snapshot=agent_runner.external_prompt(self.data)
        self.assertNotIn(original['id'],snapshot)
        self.assertIn(discovery['id'],snapshot)
        pending=stubbs_jobs.report(self.data)['pendingRequests']
        self.assertNotIn(original['id'],{item['id'] for item in pending})
        self.assertEqual({item['id'] for item in pending},{successor['id'],discovery['id']})
        self.assertEqual(self.live(original)['deliveryCheck'],absence)
        self.assertEqual(self.live(original)['status'],'queued')

    def test_creation_and_retry_cannot_bypass_another_unresolved_send(self):
        request=self.send_interrupted()
        self.check(request,'not_sent')
        other={**copy.deepcopy(self.live(request)),'id':'TEST-another-old-attempt'}
        other.pop('deliveryCheck')
        w.state(self.data)['requests'].append(other)
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'anterior'):w.request(self.data,'one','send',request['packageId'])
        self.assertEqual(self.data,before)
        self.assert_rejected_unchanged({'kind':'ui-request-update','id':request['id'],'status':'queued','proof':'TEST retry'},'anterior')

    def test_invalid_legacy_start_is_not_treated_as_no_attempt(self):
        request=self.send_interrupted();self.apply({'kind':'ui-revoke','packageId':request['packageId']})
        self.live(request)['startedAt']='TEST invalid legacy date'
        self.assertTrue(w.unresolved_sends(self.data,'one'))
        self.assert_rejected_unchanged({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')},'anterior')

    def test_discovery_sources_do_not_change_application_or_decision_inputs(self):
        w.state(self.data)['searchContext']={'sourceUrls':'','platforms':'','targetRoles':'BI'}
        self.review();self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        fingerprints=(w.stamp(self.data,'one'),c.fit_stamp(self.data,self.row),c.cv_stamp(self.data,'one'))
        original=copy.deepcopy(w.state(self.data)['packages'])
        self.apply({'kind':'ui-search-context','values':{'sourceUrls':'https://example.org/jobs','platforms':'linkedin'},
                    'expected':{'sourceUrls':'','platforms':''}})
        self.assertEqual(fingerprints,(w.stamp(self.data,'one'),c.fit_stamp(self.data,self.row),c.cv_stamp(self.data,'one')))
        self.assertEqual(w.state(self.data)['packages'],original)
        self.assertTrue(any(item['type']=='send' and item['status']=='queued' for item in w.state(self.data)['requests']))

    def test_recorded_requirements_invalidate_review_assessment_and_send(self):
        self.review();self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        prior=(w.stamp(self.data,'one'),c.fit_stamp(self.data,self.row),c.cv_stamp(self.data,'one'),offer_quality.fingerprint(self.data,self.row))
        original=copy.deepcopy(w.state(self.data)['packages'][0])
        archived=(self.root/'data/packages'/original['id']/'package.json').read_bytes()
        self.apply({'kind':'opportunity','id':'one','values':{'Tecnologías':'TEST Rust required','Observaciones':'TEST five years required'}})
        row=w.row_for(self.data,'one')
        current=(w.stamp(self.data,'one'),c.fit_stamp(self.data,row),c.cv_stamp(self.data,'one'),offer_quality.fingerprint(self.data,row))
        self.assertTrue(all(left!=right for left,right in zip(prior,current)))
        self.assertIn('Revisión final del agente',w.readiness(self.data,'one'))
        package=w.state(self.data)['packages'][0]
        self.assertEqual(package['payload'],original['payload']);self.assertEqual(package['approvedAt'],original['approvedAt'])
        self.assertTrue(package.get('revokedAt'))
        self.assertEqual((self.root/'data/packages'/original['id']/'package.json').read_bytes(),archived)
        self.assertFalse(any(item['type']=='send' and item['status']=='queued' for item in w.state(self.data)['requests']))

    def test_legacy_archive_is_not_rewritten_to_claim_new_semantics(self):
        self.review()
        legacy=copy.deepcopy(w.payload(self.data,'one'))
        legacy['searchContext']={'sourceUrls':'https://example.org/old','platforms':'linkedin','checkMail':False}
        key=core.digest(legacy)
        w.publish_package(key,legacy,b'%PDF-test-one')
        package={'id':key,'opportunityId':'one','payload':legacy,'approvedAt':core.now(),'createdAt':core.now()}
        w.state(self.data)['packages'].append(package)
        w.draft(self.data,'one')['review']['fingerprint']=key
        archive=self.root/'data/packages'/key/'package.json'
        raw=archive.read_bytes();before=copy.deepcopy(package)
        self.assertIn('Revisión final del agente',w.readiness(self.data,'one'))
        with self.assertRaisesRegex(ValueError,'revalidación'):w.approved_package(self.data,'one',key)
        self.assertEqual(package,before);self.assertEqual(archive.read_bytes(),raw)

    def test_requirement_change_during_actual_send_is_atomic(self):
        self.review();self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        request=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
        with w.execution_owner('sender'):self.update(request,'running')
        self.assert_rejected_unchanged({'kind':'opportunity','id':'one','values':{'Observaciones':'TEST new mandatory requirement'}},'en curso')

    def declare(self,key='one'):
        self.apply({'kind':'ui-draft','opportunityId':key,'values':{'questions':[{'key':'custom_language','label':'Idioma de trabajo','type':'text','scope':'opportunity'}],
                    'requiredAnswers':['custom_language']},'expected':{'questions':None,'requiredAnswers':[]}})

    def test_custom_opportunity_response_cannot_be_saved_globally(self):
        self.declare()
        self.assert_rejected_unchanged({'kind':'ui-profile','scope':'global','opportunityId':'one','values':{'custom_language':'TEST English'},
                                      'expected':{'custom_language':None}},'pertenece a una oferta')

    def test_old_wrong_global_custom_value_is_preserved_but_never_inherited(self):
        self.declare();self.data['profile']['custom_language']='TEST legacy bad global answer'
        second_url='https://example.org/jobs/test-second'
        self.data['sheets']['Oportunidades'].append({**copy.deepcopy(self.row),'ID':'two','URL original':second_url,'Clave canónica':core.identity(second_url)})
        self.declare('two')
        self.assertIsNone(w.answers(self.data,'one').get('custom_language'))
        self.assertIsNone(w.answers(self.data,'two').get('custom_language'))
        self.assertIn('Idioma de trabajo',w.missing(self.data,'two'))
        self.assertEqual(self.data['profile']['custom_language'],'TEST legacy bad global answer')
        self.apply({'kind':'ui-responses','opportunityId':'one','values':{'custom_language':'TEST local English'},'expected':{'custom_language':None}})
        self.assertEqual(w.answers(self.data,'one')['custom_language'],'TEST local English')
        self.assertIsNone(w.answers(self.data,'two').get('custom_language'))

    def auto_root(self):
        self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':True,'mode':'auto','expected':None})
        return next(item for item in w.state(self.data)['requests'] if item['type']=='review')

    def derived(self,root,finish=True):
        self.update(root,'running');self.review()
        if finish:self.update(root,'done')
        return next(item for item in w.state(self.data)['requests'] if item['type']=='send')

    def test_auto_send_can_continue_from_finished_root_in_original_snapshot(self):
        root=self.auto_root()
        with w.execution_owner('agent'),w.execution_scope([root['id']]):
            send=self.derived(root)
            self.assertEqual(send['continuation']['rootRequestId'],root['id'])
            identity=w.selection(self.data,'one')['id']
            self.assertEqual(send['continuation']['selectionId'],identity)
            self.assertEqual(w.state(self.data)['executionScopes']['agent']['rootSelectionIds'][root['id']],identity)
            package=next(p for p in w.state(self.data)['packages'] if p['id']==send['packageId'])
            self.assertEqual(package['selectionId'],identity)
            self.assertEqual(w.eligible_continuations(self.data),[send['id']])
            self.update(send,'running');self.update(send,'running')
        self.assertEqual(self.live(send)['executionId'],'agent')

    def test_reselection_in_the_same_second_cannot_join_the_original_scope(self):
        at=core.now()
        with patch.object(w,'now',return_value=at):
            root=self.auto_root()
            with w.execution_owner('agent'),w.execution_scope([root['id']]):
                self.update(root,'running')
                previous=copy.deepcopy(w.selection(self.data,'one'))
                self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':False,'expected':previous})
                self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':True,'mode':'auto','expected':None})
                choice=w.selection(self.data,'one')
                self.assertEqual(choice['at'],previous['at'])
                self.assertNotEqual(choice['id'],previous['id'])
                self.review();self.update(root,'done')
                send=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
                self.assertNotIn('continuation',send)
                self.assertFalse(w.eligible_continuations(self.data))
                self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'no deriva')
            # The new permission remains usable through a new explicit snapshot.
            with w.execution_owner('new-snapshot'),w.execution_scope([send['id']]):self.update(send,'running')

    def test_legacy_scope_and_selection_continue_only_while_that_legacy_choice_survives(self):
        at=core.now()
        with patch.object(w,'now',return_value=at):
            root=self.auto_root()
            # Retained records from before selection IDs existed.
            w.selection(self.data,'one').pop('id')
            with w.execution_owner('legacy-scope'),w.execution_scope([root['id']]):
                self.update(root,'running')
                w.state(self.data)['executionScopes']['legacy-scope'].pop('rootSelectionIds')
                self.review();self.update(root,'done')
                send=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
                self.assertNotIn('selectionId',send['continuation'])
                self.assertEqual(w.eligible_continuations(self.data),[send['id']])
                package=next(p for p in w.state(self.data)['packages'] if p['id']==send['packageId'])
                archived=copy.deepcopy(package['payload'])
                self.assertEqual(w.approved_package(self.data,'one',package['id']),package)
                previous=copy.deepcopy(w.selection(self.data,'one'))
                self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':False,'expected':previous})
                self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':True,'mode':'auto','expected':None})
                self.assertEqual(w.selection(self.data,'one')['at'],previous['at'])
                self.review()
                newest=next(item for item in w.state(self.data)['requests'] if item['type']=='send' and item['status']=='queued')
                self.assertNotIn('continuation',newest)
                self.assertFalse(w.eligible_continuations(self.data))
                self.assertEqual(package['payload'],archived)
                self.assert_rejected_unchanged({'kind':'ui-request-update','id':newest['id'],'status':'running','proof':'TEST'},'no deriva')

    def test_running_legacy_root_does_not_adopt_a_new_selection_with_the_same_date(self):
        at=core.now()
        with patch.object(w,'now',return_value=at):
            root=self.auto_root()
            w.selection(self.data,'one').pop('id')
            with w.execution_owner('legacy-root'),w.execution_scope([root['id']]):
                self.update(root,'running')
                w.state(self.data)['executionScopes']['legacy-root'].pop('rootSelectionIds')
                old_choice=copy.deepcopy(w.selection(self.data,'one'))
                self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':False,'expected':old_choice})
                self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':True,'mode':'auto','expected':None})
                self.assertEqual(w.selection(self.data,'one')['at'],old_choice['at'])
                self.assertTrue(w.selection(self.data,'one')['id'])
                self.review();self.update(root,'done')
                send=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
                self.assertNotIn('continuation',send)
                self.assertFalse(w.eligible_continuations(self.data))
                self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'no deriva')

    def test_unchanged_legacy_selection_can_finish_its_old_scope(self):
        root=self.auto_root()
        w.selection(self.data,'one').pop('id')
        with w.execution_owner('legacy-root'),w.execution_scope([root['id']]):
            self.update(root,'running')
            w.state(self.data)['executionScopes']['legacy-root'].pop('rootSelectionIds')
            self.review();self.update(root,'done')
            send=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
            self.assertEqual(w.eligible_continuations(self.data),[send['id']])
            self.update(send,'running')
            self.assertEqual(self.live(send)['executionId'],'legacy-root')

    def test_undo_selection_has_a_new_identity_and_manual_approval_has_its_own_authority(self):
        at=core.now()
        with patch.object(w,'now',return_value=at):
            self.auto_root();self.review()
            original=copy.deepcopy(w.selection(self.data,'one'))
            package=copy.deepcopy(w.state(self.data)['packages'][-1])
            archive=self.root/'data/packages'/package['id']/'package.json'
            archive_bytes=archive.read_bytes()
            self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':False,'expected':original})
            withdrawal=w.state(self.data)['undo'][-1]['id']
            self.apply({'kind':'ui-undo','id':withdrawal})
            recovered=w.selection(self.data,'one')
            self.assertEqual(recovered['mode'],'review')
            self.assertEqual(recovered['at'],original['at'])
            self.assertNotEqual(recovered['id'],original['id'])
            self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':package['id']})
            approved=w.approved_package(self.data,'one',package['id'])
            self.assertEqual(approved['approvalSource'],'manual')
            self.assertEqual(approved['payload'],package['payload'])
            self.assertEqual(archive.read_bytes(),archive_bytes)
            send=next(item for item in w.state(self.data)['requests'] if item['type']=='send' and item['status']=='queued')
            with w.execution_owner('manual-snapshot'),w.execution_scope([send['id']]):self.update(send,'running')

    def test_previous_automatic_approval_requires_its_exact_selection_identity(self):
        at=core.now()
        with patch.object(w,'now',return_value=at):
            self.auto_root();self.review()
            package=w.state(self.data)['packages'][-1]
            original=copy.deepcopy(w.selection(self.data,'one'))
            self.assertEqual(w.approved_package(self.data,'one',package['id']),package)
            # A historical permit cannot be reused by another choice even when
            # its timestamp matches. Official withdrawal additionally revokes it.
            w.selection(self.data,'one')['id']='TEST-different-selection'
            with self.assertRaisesRegex(ValueError,'selección'):
                w.approved_package(self.data,'one',package['id'])
            self.assertEqual(package['selectionId'],original['id'])

    def test_derived_send_cannot_start_before_root_done_or_adopt_foreign_scope(self):
        root=self.auto_root()
        with w.execution_owner('agent'),w.execution_scope([root['id']]):
            send=self.derived(root,finish=False)
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'no deriva')
            self.update(root,'done')
        with w.execution_owner('other-chat'),w.execution_scope([root['id']]):
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'actualmente en cola')
        # A new explicit snapshot can take an already queued send as ordinary work.
        with w.execution_owner('new-explicit'),w.execution_scope([send['id']]):self.update(send,'running')

    def test_new_instructions_cannot_expand_scope_or_inherit_auto_continuation(self):
        root=self.auto_root()
        with w.execution_owner('agent'),w.execution_scope([root['id']]):
            send=self.derived(root)
            self.apply({'kind':'ui-change','opportunityId':'one','message':'TEST new human instruction','actor':'Usuario'})
            change=next(item for item in w.state(self.data)['requests'] if item['type']=='change')
            self.assertFalse(w.eligible_continuations(self.data))
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':change['id'],'status':'running','proof':'TEST'},'no deriva')
        with w.execution_owner('agent'),w.execution_scope([root['id'],change['id']]):
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':change['id'],'status':'running','proof':'TEST'},'ya está fijada')
        with w.execution_owner('agent'):
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':change['id'],'status':'running','proof':'TEST'},'request-ids')
        self.assertEqual(self.live(send)['status'],'cancelled')

    def test_legacy_review_without_snapshot_does_not_create_automatic_continuation(self):
        root=self.auto_root()
        with w.execution_owner('legacy-agent'):
            send=self.derived(root)
        self.assertNotIn('continuation',send)
        self.assertFalse(w.eligible_continuations(self.data,'legacy-agent'))

    def test_derived_send_requires_original_scope_flag_and_same_permission(self):
        root=self.auto_root()
        with w.execution_owner('agent'),w.execution_scope([root['id']]):send=self.derived(root)
        with w.execution_owner('agent'):
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'request-ids')
        package=next(item for item in w.state(self.data)['packages'] if item['id']==send['packageId'])
        package['approvedAt']=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        with w.execution_owner('agent'),w.execution_scope([root['id']]):
            self.assertFalse(w.eligible_continuations(self.data))
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'no deriva')

    def test_scope_first_claim_is_rolled_back_when_batch_fails(self):
        root=self.auto_root();before=copy.deepcopy(self.data)
        operations=[{'kind':'ui-request-update','id':root['id'],'status':'running','proof':'TEST actual start'},
                    {'kind':'ui-profile','scope':'global','values':{'currentCity':123},'expected':{'currentCity':None}}]
        with w.execution_owner('agent'),w.execution_scope([root['id']]),self.assertRaises(ValueError):
            stubbs_jobs.apply_batch(self.data,{'id':'TEST failed scoped claim','operations':operations})
        self.assertEqual(self.data,before)
        self.assertNotIn('agent',w.state(self.data).get('executionScopes',{}))

    def test_review_selection_does_not_derive_send_from_later_automatic_mode(self):
        self.apply({'kind':'ui-select-opportunity','opportunityId':'one','selected':True,'mode':'review','expected':None})
        root=next(item for item in w.state(self.data)['requests'] if item['type']=='review')
        with w.execution_owner('agent'),w.execution_scope([root['id']]):
            self.update(root,'running')
            # Legacy records may have changed mode; scope still preserves the original choice.
            w.state(self.data)['selections']['one']['mode']='auto'
            self.review();self.update(root,'done')
            send=next(item for item in w.state(self.data)['requests'] if item['type']=='send')
            self.assertNotIn('continuation',send)
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'no deriva')

    def test_explicit_interruption_invalidates_root_causal_eligibility(self):
        root=self.auto_root()
        with w.execution_owner('agent'),w.execution_scope([root['id']]):
            send=self.derived(root,finish=False)
        with w.execution_owner('admin'):
            current=self.live(root)
            self.apply({'kind':'ui-request-interrupt','id':root['id'],'expectedUpdatedAt':current['updatedAt'],
                        'expectedExecutionId':'agent','proof':'TEST previous chat checked stopped','confirmation':'TEST human stopped previous chat'})
        self.assertFalse(w.eligible_continuations(self.data,'agent'))
        with w.execution_owner('agent'),w.execution_scope([root['id']]):
            self.assert_rejected_unchanged({'kind':'ui-request-update','id':send['id'],'status':'running','proof':'TEST'},'no deriva')
