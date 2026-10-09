"""Optional survey decisions on fictional profiles, separate from recruitment consent."""
import copy
import unittest
from workflow_fixtures import WorkflowFixture, interview_choices
import app_context as c
import app_workflow as w
import personalization as p
import profile_interview
import view_cache


class ProfileDemographicsTests(WorkflowFixture, unittest.TestCase):
    def save(self, values):
        self.apply({'kind':'ui-profile-section','section':'about','values':values,
                    'expected':{k:self.data['profile'].get(k) for k in values}})

    def form(self):
        d=w.draft(self.data,'one')
        self.apply({'kind':'ui-draft','opportunityId':'one',
                    'values':{'formAnswerKeys':['gender','demographicSurveyParticipation'],
                              'requiredAnswers':['gender']},
                    'expected':{'formAnswerKeys':d.get('formAnswerKeys'),'requiredAnswers':d['requiredAnswers']}})

    def test_optional_fields_save_false_and_undo_without_job_work(self):
        self.save({'gender':'No binario','demographicSurveyParticipation':False})
        self.assertEqual(self.data['profile']['gender'],'No binario')
        self.assertIs(self.data['profile']['demographicSurveyParticipation'],False)
        self.assertTrue(all(c.definitions(self.data)[key]['scope']=='global' for key in w.DEMOGRAPHIC_FIELDS))
        self.assertEqual(w.state(self.data)['requests'],[])
        self.assertEqual(self.data['events'],[])
        self.apply({'kind':'ui-undo','id':w.state(self.data)['undo'][-1]['id']})
        self.assertIsNone(self.data['profile'].get('gender'))
        self.assertIsNone(self.data['profile'].get('demographicSurveyParticipation'))

    def test_invalid_and_stale_values_rollback_the_complete_save(self):
        for invalid in ({'gender':True},{'gender':'x'*101},{'gender':' '},
                        {'demographicSurveyParticipation':1},{'demographicSurveyParticipation':'yes'}):
            before=copy.deepcopy(self.data)
            with self.assertRaises(ValueError):self.save({'currentCity':'Ciudad ficticia',**invalid})
            self.assertEqual(self.data,before)
        self.save({'gender':'Prefiero no responder'})
        before=copy.deepcopy(self.data)
        with self.assertRaises(w.Conflict):
            self.apply({'kind':'ui-profile-section','section':'about','values':{'gender':'Mujer'},'expected':{'gender':None}})
        self.assertEqual(self.data,before)

    def test_legacy_profiles_and_unrelated_packages_keep_their_identity(self):
        before=w.stamp(self.data,'one');cv=c.cv_stamp(self.data,'one')
        original=copy.deepcopy(self.data)
        with view_cache.snapshot():c.definitions(self.data)
        self.assertEqual(self.data,original)
        self.save({'gender':'Mujer','demographicSurveyParticipation':True})
        self.assertEqual(w.stamp(self.data,'one'),before)
        self.assertEqual(c.cv_stamp(self.data,'one'),cv)
        self.assertFalse(set(w.DEMOGRAPHIC_FIELDS)&set(w.answers(self.data,'one')))
        self.assertEqual(w.state(self.data)['requests'],[])

    def test_declared_survey_uses_only_confirmed_participation_and_local_answers(self):
        self.save({'gender':'Hombre'})
        self.form()
        self.assertIsNone(w.answers(self.data,'one')['gender'])
        self.save({'demographicSurveyParticipation':True})
        self.assertEqual(w.answers(self.data,'one')['gender'],'Hombre')
        self.save({'demographicSurveyParticipation':False})
        self.assertEqual(w.answers(self.data,'one')['gender'],'Prefiero no responder')
        self.assertEqual(self.data['profile']['gender'],'Hombre')
        self.apply({'kind':'ui-profile','opportunityId':'one','scope':'opportunity',
                    'values':{'gender':'Respuesta específica'},'expected':{'gender':None}})
        self.assertEqual(w.answers(self.data,'one')['gender'],'Respuesta específica')
        self.assertEqual(self.data['profile']['gender'],'Hombre')

    def test_survey_preference_cannot_answer_a_portals_recruitment_consent(self):
        self.save({'gender':'Mujer','demographicSurveyParticipation':True})
        self.apply({'kind':'ui-draft','opportunityId':'one',
                    'values':{'questions':[{'key':'custom_recruitment_consent','label':'Consentimiento de selección por 365 días',
                                           'type':'boolean','scope':'opportunity'}],
                              'formAnswerKeys':['custom_recruitment_consent'],'requiredAnswers':['custom_recruitment_consent']},
                    'expected':{'questions':None,'formAnswerKeys':None,'requiredAnswers':[]}})
        self.assertIsNone(w.answers(self.data,'one').get('custom_recruitment_consent'))
        self.assertIn('Consentimiento de selección por 365 días',w.missing(self.data,'one'))

    def test_changed_declared_survey_revokes_old_permission_and_preserves_its_package(self):
        self.save({'gender':'Mujer','demographicSurveyParticipation':True});self.form();self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        old=copy.deepcopy(w.state(self.data)['packages'][0])
        self.save({'demographicSurveyParticipation':False})
        self.assertEqual(w.state(self.data)['packages'][0]['payload'],old['payload'])
        self.assertTrue(w.state(self.data)['packages'][0]['revokedAt'])
        self.assertNotEqual(w.stamp(self.data,'one'),old['id'])
        self.assertTrue(all(r['status']=='cancelled' for r in w.state(self.data)['requests'] if r['type']=='send'))
        self.assertEqual(self.data['events'],[])

    def test_initial_interview_keeps_unasked_fields_optional_and_requires_confirmation_when_provided(self):
        data=p.blank_store()
        fields=profile_interview.fields(data)
        self.assertTrue(set(w.DEMOGRAPHIC_FIELDS)<=set(fields))
        values={'gender':'Prefiero no responder','demographicSurveyParticipation':False}
        p.validate_initial(values,data)
        choices=interview_choices(data,values)
        saved=profile_interview.decisions(data,values,{},choices)
        self.assertEqual(saved['demographicSurveyParticipation']['status'],'provided')
        self.assertFalse(set(w.DEMOGRAPHIC_FIELDS)&profile_interview.ESSENTIAL)
        with self.assertRaises(ValueError):
            profile_interview.require_complete(data,values,{key:value for key,value in saved.items() if key!='gender'})
