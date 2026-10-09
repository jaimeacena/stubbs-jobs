"""Regression scenarios for the October 6 review, using isolated fictional data."""
import copy
import unittest
from unittest.mock import patch
from workflow_fixtures import WorkflowFixture,interview_choices
import app_context as context
import app_workflow as workflow
import offer_actions
import offer_minimums
import offer_quality
import personalization
import profile_interview
import stubbs_jobs as jobs
import stubbs_jobs_core as core


class IntegralCorrectionsTests(WorkflowFixture,unittest.TestCase):
    def test_categorical_details_and_exclusive_preferences_use_the_same_writer_guard(self):
        for preferred,published,kind in [('100 % remoto','Híbrido (2 días por semana)','mode'),
                                        ('Solo presencial','Remoto','mode'),
                                        ('Solo temporal','Indefinido','contract'),
                                        ('Indefinido','Temporal (6 meses)','contract')]:
            with self.subTest(preferred=preferred,published=published):
                self.setUp()
                self.data['app']['criteria']={'location':'España','contract':preferred if kind=='contract' else 'Sin preferencia'}
                self.data['app']['searchContext']={'workMode':preferred if kind=='mode' else 'Sin preferencia'}
                self.apply({'kind':'opportunity','id':'one','values':{'Modalidad' if kind=='mode' else 'Contrato':published},'proof':'TEST categoría explícita y detalle del anuncio.'})
                row=workflow.row_for(self.data,'one')
                self.assertFalse(offer_minimums.view(self.data,row)['canApply'])
                self.assertTrue(workflow.archived(self.data,'one'))
                self.assertNotIn('select-auto',offer_actions.available(self.data,'one',workflow))

    def test_alternatives_missing_categories_and_preferences_do_not_become_false_rejections(self):
        self.data['app']['criteria']={'location':'España','contract':'Sin preferencia'}
        self.data['app']['searchContext']={'workMode':'100 % remoto'}
        for value in [None,'Remoto o híbrido, a elegir','Sin concretar','No remoto']:
            self.row['Modalidad']=value
            decision=offer_minimums.view(self.data,self.row)
            self.assertTrue(decision['canApply'])
            self.assertIn('Remoto España',decision['unknowns'])
        self.data['app']['searchContext']['workMode']='Preferiblemente remoto'
        self.row['Modalidad']='Presencial'
        self.assertTrue(offer_minimums.view(self.data,self.row)['canApply'])

    def test_final_review_requires_declared_form_usage_and_never_exports_the_internal_minimum(self):
        workflow.state(self.data)['selections']['one']={'selected':True,'mode':'review'}
        fingerprint=workflow.stamp(self.data,'one')
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'formAnswerKeys'):
            self.apply({'kind':'ui-review','opportunityId':'one','fingerprint':fingerprint,
                        'checks':{k:True for k in workflow.CHECKS},'proof':'TEST complete review without field mapping.'})
        self.assertEqual(self.data,before)
        with self.assertRaises(ValueError):
            self.apply({'kind':'ui-draft','opportunityId':'one','values':{'formAnswerKeys':['minimumFixed']},'expected':{'formAnswerKeys':None}})

    def test_withdrawing_an_inflight_permission_preserves_owner_start_and_receipt(self):
        self.review();key=workflow.stamp(self.data,'one')
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':key})
        request=next(r for r in workflow.state(self.data)['requests'] if r['type']=='send')
        with patch('agent_runner.view',return_value={'status':'idle'}),patch('agent_runner.read_state',return_value={'status':'idle'}),workflow.execution_owner('TEST-owner'):
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST attempt started.'})
            started=copy.deepcopy(next(r for r in workflow.state(self.data)['requests'] if r['id']==request['id']))
            self.assertIn('revoke',offer_actions.available(self.data,'one',workflow))
            self.apply({'kind':'ui-revoke','packageId':key,'actor':'Usuario'})
            current=next(r for r in workflow.state(self.data)['requests'] if r['id']==request['id'])
            for field in ['executionId','startedAt','authorizationAt','status']:self.assertEqual(current[field],started[field])
            with self.assertRaises(ValueError):workflow.approved_package(self.data,'one',key)
            self.apply({'kind':'event','event':{'id':'TEST-receipt','type':'sent','opportunityId':'one','packageId':key,
                'at':core.now(),'proof':'TEST original receipt found; no repeat submission.','confirmation':'TEST portal receipt 12345.',
                'authorization':'TEST original start permission.','historyChecked':True,'cv':'outputs/cv.pdf'}})
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'done','proof':'TEST original receipt recorded.'})
        self.assertEqual(len(self.data['events']),1)
        self.assertTrue(workflow.state(self.data)['packages'][0]['revokedAt'])

    def test_linkedin_locales_and_slugs_keep_one_vacancy_and_preserve_legacy_ids(self):
        urls=['https://www.linkedin.com/jobs/view/1234567890/',
              'https://es.linkedin.com/jobs/view/analista-1234567890/?trk=test',
              'https://uk.linkedin.com/jobs/view/1234567890/?utm_source=test']
        self.assertEqual({core.identity(u) for u in urls},{'linkedin:1234567890'})
        self.row.update({'URL original':urls[0],'Clave canónica':'url:legacy-original'})
        before=copy.deepcopy(self.row)
        feed={'schemaVersion':2,'checkedAtUtc':core.now(),'boards':[],
              'candidates':[{'url':u,'sourceId':'TEST','company':'TEST Example','title':'TEST Analyst','originalPublishedAt':None} for u in urls]}
        self.assertEqual(jobs.ingest(self.data,feed),0)
        self.assertEqual(self.row,before)
        self.assertFalse(self.data['sheets']['Entradas'])
        self.assertIn('url:legacy-original',self.data['observations'])

    def test_a_second_legacy_alias_cannot_start_after_a_confirmed_submission(self):
        self.row['URL original']='https://www.linkedin.com/jobs/view/1234567890'
        alias={**self.row,'ID':'two','Clave canónica':'url:legacy-alias','URL original':'https://es.linkedin.com/jobs/view/test-1234567890'}
        self.data['sheets']['Oportunidades'].append(alias)
        self.review();key=workflow.stamp(self.data,'one')
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':key})
        self.data['events'].append({'id':'TEST-previous','type':'sent','opportunityId':'two','at':core.now()})
        with self.assertRaisesRegex(ValueError,'misma vacante'):workflow.approved_package(self.data,'one',key)

    def test_notes_do_not_change_material_but_explicit_requirements_do(self):
        self.review();before=(context.fit_stamp(self.data,self.row),context.cv_stamp(self.data,'one'),workflow.stamp(self.data,'one'))
        self.apply({'kind':'ui-offer-note','opportunityId':'one','values':{'Notas de seguimiento':'TEST preguntar por el siguiente paso.'},'expected':{'Notas de seguimiento':None}})
        row=workflow.row_for(self.data,'one')
        self.assertEqual(before,(context.fit_stamp(self.data,row),context.cv_stamp(self.data,'one'),workflow.stamp(self.data,'one')))
        self.apply({'kind':'ui-offer-context','opportunityId':'one',
                    'values':{'Requisitos de la oferta':'TEST SQL avanzado obligatorio.','Notas de seguimiento':row['Notas de seguimiento']},
                    'expected':{'Requisitos de la oferta':None,'Notas de seguimiento':row['Notas de seguimiento'],'Observaciones':row.get('Observaciones')},
                    'proof':'TEST fuente cotejada: el requisito de SQL se conserva separado del recordatorio.'})
        row=workflow.row_for(self.data,'one')
        self.assertNotEqual(before[0],context.fit_stamp(self.data,row));self.assertNotEqual(before[1],context.cv_stamp(self.data,'one'));self.assertNotEqual(before[2],workflow.stamp(self.data,'one'))

    def test_progressive_profile_does_not_turn_absent_optional_fields_into_human_answers(self):
        data=personalization.blank_store();values={'targetRoles':'TEST Analyst','location':'TEST Country','experience':'TEST first job.'}
        all_choices=interview_choices(data,values)
        choices={k:v for k,v in all_choices.items() if k in profile_interview.ESSENTIAL}
        saved=profile_interview.decisions(data,values,{},choices)
        coverage=profile_interview.require_complete(data,values,saved)
        self.assertTrue(coverage['complete']);self.assertFalse(coverage['allComplete'])
        self.assertGreater(coverage['optionalPending'],0)
        self.assertEqual(next(f['status'] for f in coverage['fields'] if f['key']=='email'),'pending')
        values['email']='test@example.org'
        with self.assertRaises(ValueError):profile_interview.require_complete(data,values,saved)

    def test_new_assessments_require_a_real_source_date_without_claiming_semantic_verification(self):
        op={'kind':'ui-offer-assessment','opportunityId':'one','fingerprint':offer_quality.fingerprint(self.data,self.row),
            'reason':'TEST coincide con el perfil ficticio.','proof':'TEST fuente ficticia consultada.',
            'references':[{'url':'https://example.org/jobs/123-role','text':'TEST informes de BI.'}]}
        with self.assertRaisesRegex(ValueError,'observedAt'):self.apply(op)
        self.apply({**op,'observedAt':core.now()})
        self.assertTrue(offer_quality.view(self.data,workflow.row_for(self.data,'one'))['observedAt'])
        self.assertFalse(self.data['events'])


if __name__=='__main__':unittest.main()
