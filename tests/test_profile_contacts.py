"""International, visible contact facts with immutable reviewed material."""
import copy
import unittest
from workflow_fixtures import WorkflowFixture, interview_choices
import app_context as c
import app_workflow as w
import personalization as p
import profile_interview
import view_cache

class ProfileContactsTests(WorkflowFixture,unittest.TestCase):
    def setUp(self):
        WorkflowFixture.setUp(self)
        self.facts={'email':'fictional@example.org','phone':'+81 90 1234 5678',
                    'currentCountry':'Japón','postalCode':'001-0001',
                    'address':'Dirección ficticia 1','linkedinUrl':'https://www.linkedin.com/in/fictional/',
                    'websiteUrl':'https://example.org/portfolio'}

    def save(self,values):
        self.apply({'kind':'ui-profile-section','section':'about','values':values,
                    'expected':{k:self.data['profile'].get(k) for k in values}})

    def test_all_contact_facts_are_global_optional_editable_and_undoable(self):
        old=copy.deepcopy(self.data['profile'])
        self.save(self.facts)
        self.assertTrue(all(self.data['profile'][k]==v for k,v in self.facts.items()))
        self.assertTrue(all(c.definitions(self.data)[k]['scope']=='global' for k in self.facts))
        self.assertEqual(w.state(self.data)['requests'],[])
        self.apply({'kind':'ui-undo','id':w.state(self.data)['undo'][-1]['id']})
        self.assertTrue(all(self.data['profile'].get(k)==old.get(k) for k in self.facts))

    def test_invalid_or_stale_contacts_leave_the_whole_section_unchanged(self):
        for values in ({'email':'not-an-email'},{'email':'name@example.org other'},
                       {'phone':'sin número'},{'phone':123456},{'postalCode':1234},
                       {'websiteUrl':'javascript:alert(1)'},{'websiteUrl':'https://name:secret@example.org'},
                       {'currentCountry':'x'*101},{'address':True}):
            before=copy.deepcopy(self.data)
            with self.assertRaises(ValueError):self.save({'currentCity':'Otro dato',**values})
            self.assertEqual(self.data,before)
        self.save({'email':self.facts['email']});before=copy.deepcopy(self.data)
        with self.assertRaises(w.Conflict):self.apply({'kind':'ui-profile-section','section':'about','values':{'email':'new@example.org'},'expected':{'email':None}})
        self.assertEqual(self.data,before)

    def test_empty_fields_keep_legacy_material_identity_and_never_become_required(self):
        before=w.stamp(self.data,'one');cv=c.cv_stamp(self.data,'one')
        self.data['profile'].update(dict.fromkeys(w.CONTACT_FIELDS))
        with view_cache.snapshot():
            self.assertEqual(w.stamp(self.data,'one'),before)
            self.assertEqual(c.cv_stamp(self.data,'one'),cv)
            self.assertFalse(set(self.facts)&set(w.answers(self.data,'one')))
        self.assertFalse(w.draft(self.data,'one')['requiredAnswers'])

    def test_only_declared_contact_answers_go_to_a_form_and_local_overrides_keep_global_facts(self):
        self.save(self.facts)
        self.apply({'kind':'ui-draft','opportunityId':'one','values':{'formAnswerKeys':['email','phone'],'requiredAnswers':['email']},'expected':{'formAnswerKeys':None,'requiredAnswers':[]}})
        self.assertEqual(w.answers(self.data,'one')['email'],self.facts['email'])
        self.assertNotIn('address',w.answers(self.data,'one'))
        self.apply({'kind':'ui-profile','opportunityId':'one','scope':'opportunity','values':{'email':'other@example.org'},'expected':{'email':None}})
        self.assertEqual(w.answers(self.data,'one')['email'],'other@example.org')
        self.assertEqual(self.data['profile']['email'],self.facts['email'])
        self.apply({'kind':'ui-responses','opportunityId':'one','values':{'phone':'+55 11 1234 5678'},'expected':{'phone':self.facts['phone']}})
        self.assertEqual(self.data['profile']['phone'],'+55 11 1234 5678')

    def test_editing_contacts_invalidates_cv_and_reviewed_package_without_rewriting_history(self):
        self.save({'email':self.facts['email']});self.review()
        old_package=copy.deepcopy(w.state(self.data)['packages'][0]);old_cv=c.cv_stamp(self.data,'one')
        self.save({'email':'updated@example.org'})
        self.assertNotEqual(w.stamp(self.data,'one'),old_package['id'])
        self.assertNotEqual(c.cv_stamp(self.data,'one'),old_cv)
        self.assertEqual(w.state(self.data)['packages'][0]['payload'],old_package['payload'])
        self.assertIn('Revisión final del agente',w.missing(self.data,'one'))
        self.assertEqual(self.data['events'],[])

    def test_residence_is_independent_of_search_zone_and_requires_fit_revalidation(self):
        before=c.fit_stamp(self.data,w.row_for(self.data,'one'));old=c.criteria(self.data)
        self.save({'currentCountry':'Japón'})
        self.assertEqual(c.criteria(self.data),old)
        self.assertNotEqual(c.fit_stamp(self.data,w.row_for(self.data,'one')),before)

    def test_contact_change_suspends_an_old_queued_send_permission(self):
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        old=copy.deepcopy(w.state(self.data)['packages'][0])
        self.save({'phone':self.facts['phone']})
        sends=[r for r in w.state(self.data)['requests'] if r['type']=='send']
        self.assertTrue(sends)
        self.assertTrue(all(r['status']=='cancelled' for r in sends))
        self.assertTrue(w.state(self.data)['packages'][0]['revokedAt'])
        self.assertEqual(w.state(self.data)['packages'][0]['payload'],old['payload'])

    def test_contact_edit_during_an_actual_send_is_rejected_atomically(self):
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
        request=next(r for r in w.state(self.data)['requests'] if r['type']=='send')
        request.update(status='running',startedAt=w.now())
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'envío en curso'):self.save({'phone':self.facts['phone']})
        self.assertEqual(self.data,before)

    def test_first_interview_requires_contact_decisions_and_accepts_explicit_blanks(self):
        data=p.blank_store();values={'name':'Persona ficticia','experience':'Experiencia ficticia',**self.facts}
        p.validate_initial(values,data)
        choices=interview_choices(data,values)
        saved=profile_interview.decisions(data,values,{},choices)
        self.assertTrue(profile_interview.require_complete(data,values,saved)['complete'])
        self.assertTrue(set(self.facts)<=set(profile_interview.fields(data)))
        with self.assertRaises(ValueError):profile_interview.require_complete(data,values,{k:v for k,v in saved.items() if k!='email'})
        blank={k:None for k in self.facts}
        decisions=profile_interview.decisions(data,blank,{},interview_choices(data,blank))
        self.assertTrue(profile_interview.require_complete(data,blank,decisions)['complete'])
