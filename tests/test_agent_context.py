"""Decision context keeps blockers and provenance while remaining a pure query."""
import contextlib
import copy
import io
import json
import sys
from unittest.mock import patch
import unittest

from workflow_fixtures import WorkflowFixture
import agent_context
import agent_runner
import app_workflow as w
import personalization
import offer_quality
import stubbs_jobs as j
import stubbs_jobs_app as app
from stubbs_jobs_core import now


class AgentContextTests(unittest.TestCase):
    apply = WorkflowFixture.apply
    review = WorkflowFixture.review

    def setUp(self):
        WorkflowFixture.setUp(self)
        self.data.update(createdAt=now(),updatedAt=now())
        (self.root/'config').mkdir()
        (self.root/'config/sources.json').write_text('[]',encoding='utf-8')
        for module in (agent_context,app,personalization):
            p=patch.object(module,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        p=patch.object(agent_runner,'STATE',self.root/'data/agent-run.json');p.start();self.addCleanup(p.stop)
        p=patch.object(agent_runner,'LEASE',self.root/'data/agent-execution');p.start();self.addCleanup(p.stop)

    def test_compact_view_preserves_original_and_keeps_blocking_next_step(self):
        self.apply({'kind':'ui-request','type':'discovery'})
        request=self.data['app']['requests'][-1]
        request.update(status='blocked',result='TEST: falta iniciar sesión en el navegador',need='access')
        before=copy.deepcopy(self.data)
        result=agent_context.view(self.data)
        self.assertEqual(self.data,before)
        self.assertEqual(result['requests'][0]['need'],'access')
        self.assertIn('iniciar sesión',result['requests'][0]['summary'])
        self.assertNotIn('draft',result['opportunities'][0])
        self.assertTrue(result['viewOnly'])
        self.assertFalse(result['queuedSnapshot'])

    def test_compact_request_separates_a_summary_edit_from_retained_activity(self):
        self.apply({'kind':'ui-request','type':'discovery'})
        request=self.data['app']['requests'][-1]
        old='2020-01-01T12:00:00+00:00'
        request['updatedAt']=old;request.pop('activityAt',None)
        self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':old,
                    'summary':'TEST clarification without new work','need':'other'})
        before=copy.deepcopy(self.data)
        result=agent_context.view(self.data)
        current=result['requests'][0]
        self.assertEqual(current['activityAt'],old)
        self.assertGreater(current['updatedAt'],old)
        self.assertEqual(current['status'],'queued')
        self.assertNotIn('startedAt',current)
        self.assertEqual(result['queuedSnapshot'],[request['id']])
        self.assertEqual(self.data,before)

    def test_cancelled_started_uncertain_delivery_survives_compaction(self):
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        request=self.data['app']['requests'][-1]
        with w.execution_owner('TEST-owner'):
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST started'})
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'interrupted','proof':'TEST result unknown'})
        self.apply({'kind':'ui-revoke','packageId':request['packageId']})
        result=agent_context.view(self.data)
        self.assertTrue(result['requests'][0]['deliveryUnresolved'])
        self.assertEqual(result['requests'][0]['status'],'cancelled')
        detail=agent_context.view(self.data,request_id=request['id'])
        self.assertEqual(detail['request']['packageId'],request['packageId'])
        self.assertIn('startedAt',detail['request'])

    def test_case_history_retains_previous_assessment_grounds(self):
        for index in range(2):
            self.data['changes'].append({'id':'TEST-assessment-'+str(index),'at':now(),'operations':[
                {'observedAt':'2026-10-06T10:00:00+02:00', 'kind':'ui-offer-assessment','opportunityId':'one','proof':'TEST proof '+str(index),
                 'references':[{'url':self.row['URL original'],'text':'TEST source '+str(index)}]}]})
        result=agent_context.view(self.data,case='one',history=True,limit=1)
        knowledge=result['knowledgeHistory']
        self.assertEqual(knowledge['total'],2)
        self.assertEqual(knowledge['remaining'],1)
        self.assertEqual(knowledge['records'][0]['operation']['proof'],'TEST proof 1')
        self.assertEqual(knowledge['records'][0]['operation']['references'][0]['text'],'TEST source 1')

    def test_confirmed_example_is_available_for_current_preparation_and_retained_in_history(self):
        example='TEST: automaticé informes de una empresa ficticia con Power Query.'
        self.data['app']['experience']=example
        self.apply({'observedAt':'2026-10-06T10:00:00+02:00', 'kind':'ui-offer-assessment','opportunityId':'one',
                    'fingerprint':offer_quality.fingerprint(self.data,self.row),'reason':'TEST: encaje comprobado',
                    'references':[{'url':self.row['URL original'],'text':'TEST: piden automatización de informes.'}],
                    'bestArgument':{'experienceQuote':example,'referenceIndex':0},'proof':'TEST: fuente ficticia comprobada'})
        before=copy.deepcopy(self.data)
        compact=agent_context.view(self.data)
        self.assertEqual(compact['opportunities'][0]['assessment']['bestArgument']['experienceQuote'],example)
        case=agent_context.view(self.data,case='one',history=True)
        self.assertEqual(case['case']['assessment']['bestArgument']['sourceUrl'],self.row['URL original'])
        self.assertEqual(case['knowledgeHistory']['records'][0]['operation']['bestArgument']['experienceQuote'],example)
        self.assertEqual(self.data,before)
        self.data['app']['experience']='TEST: experiencia corregida después de la valoración.'
        self.assertNotIn('bestArgument',agent_context.view(self.data)['opportunities'][0]['assessment'])

    def test_since_reports_unchanged_or_complete_current_scope(self):
        first=agent_context.view(self.data)
        self.assertEqual(agent_context.view(self.data,since=first['version']),
                         {'unchanged':True,'version':first['version']})
        changed=copy.deepcopy(self.data);changed['revision']+=1
        self.assertIn('opportunities',agent_context.view(changed,since=first['version']))

    def test_since_cannot_hide_a_change_of_execution_owner(self):
        with w.execution_owner('TEST-first-owner'):
            first=agent_context.view(self.data)
        with w.execution_owner('TEST-second-owner'):
            second=agent_context.view(self.data,since=first['version'])
        self.assertNotEqual(first['version'],second['version'])
        self.assertNotIn('unchanged',second)

    def test_previous_application_text_is_available_on_explicit_profile_expansion(self):
        self.data['app']['searchContext']={'previousApplications':'TEST: candidatura anterior ficticia'}
        compact=agent_context.view(self.data)
        self.assertTrue(compact['previousApplicationsAvailable'])
        self.assertNotIn('previousApplications',compact['searchContext'])
        full=agent_context.view(self.data,profile_detail=True)
        self.assertIn('candidatura anterior',full['searchContext']['previousApplications'])

    def test_invalid_detail_does_not_fall_back_to_another_case(self):
        for values in ({'case':'missing'},{'request_id':'missing'},{'limit':0}):
            with self.subTest(values),self.assertRaises(ValueError):agent_context.view(self.data,**values)

    def test_scoped_queries_omit_other_offers_but_keep_foreign_owners_and_uncertain_sends(self):
        other=copy.deepcopy(self.row);other.update(ID='two',Empresa='TEST Otra',**{'Clave canónica':'TEST:two'})
        self.data['sheets']['Oportunidades'].append(other)
        self.apply({'kind':'ui-change','opportunityId':'one','message':'TEST revisar una sola oferta'})
        own=self.data['app']['requests'][-1]
        self.data['app']['requests'].append({'id':'TEST-foreign','type':'send','opportunityId':'two',
            'status':'running','executionId':'TEST-other-owner','startedAt':now(),'updatedAt':now(),
            'packageId':'TEST-package','result':'TEST pendiente de conciliar'})
        before=copy.deepcopy(self.data)
        for args in ({'case':'one'},{'request_id':own['id']}):
            with self.subTest(args=args):
                result=agent_context.view(self.data,**args)
                self.assertEqual([o['id'] for o in result['opportunities']],['one'])
                self.assertEqual(result['case']['id'],'one')
                self.assertEqual(result['scope']['omittedOpportunities'],1)
                foreign=next(r for r in result['requests'] if r['id']=='TEST-foreign')
                self.assertEqual(foreign['executionId'],'TEST-other-owner')
                self.assertTrue(foreign['deliveryUnresolved'])
                self.assertIn(own['id'],result['queuedSnapshot'])
                self.assertTrue(agent_context.view(self.data,since=result['version'],**args)['unchanged'])
                self.assertNotIn('unchanged',agent_context.view(self.data,since=result['version']))
        profile=agent_context.view(self.data,profile_detail=True)
        self.assertEqual(profile['opportunities'],[])
        self.assertEqual(profile['scope']['omittedOpportunities'],2)
        self.assertEqual(self.data,before)

    def test_retained_request_without_its_offer_remains_readable_and_explicit(self):
        self.apply({'kind':'ui-change','opportunityId':'one','message':'TEST antecedente conservado'})
        request=self.data['app']['requests'][-1]
        self.data['sheets']['Oportunidades']=[]
        self.data['app']['undo']=[]
        result=agent_context.view(self.data,request_id=request['id'])
        self.assertEqual(result['request']['opportunityId'],'one')
        self.assertTrue(result['scope']['opportunityUnavailable'])
        self.assertEqual(result['opportunities'],[])
        self.assertNotIn('case',result)

    def test_active_legacy_tracking_query_does_not_create_a_lease(self):
        state={'status':'running','updatedAt':now(),'startedAt':now(),'id':'TEST-legacy','message':'TEST: presencia sin comprobar'}
        with patch.object(agent_runner,'read_state',return_value=state):
            result=agent_context.view(self.data)
        self.assertEqual(result['execution']['status'],'running')
        self.assertTrue(result['execution']['presenceUnconfirmed'])
        self.assertEqual(result['execution']['message'],'TEST: presencia sin comprobar')
        self.assertFalse((self.root/'data/agent-execution').exists())

    def test_cli_agent_status_never_reconciles_export_or_acquires_writer(self):
        output=io.StringIO()
        with patch.object(sys,'argv',['stubbs_jobs.py','agent-status']),\
             patch.object(j,'read_store',return_value=copy.deepcopy(self.data)),\
             patch.object(j,'recover_export',side_effect=AssertionError('query wrote')) as recovery,\
             patch.object(j,'lock',side_effect=AssertionError('query locked')) as locking,\
             contextlib.redirect_stdout(output):
            j.main()
        self.assertTrue(json.loads(output.getvalue())['viewOnly'])
        recovery.assert_not_called();locking.assert_not_called()


if __name__=='__main__':unittest.main()
