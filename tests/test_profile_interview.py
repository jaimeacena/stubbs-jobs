"""Dynamic first interview: omission, explicit blanks, recovery and exact confirmation."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import agent_context
import app_context
import app_workflow as workflow
import assistant_flow
import onboarding
import personalization
import profile_interview as interview
import stubbs_jobs
from workflow_fixtures import interview_choices


class ProfileInterviewTests(unittest.TestCase):
    def setUp(self):
        self.data = personalization.blank_store()
        self.serial = 0
        self.owner = patch.dict(os.environ, {'STUBBS_JOBS_EXECUTION_ID': 'TEST-interview-one'})
        self.owner.start()
        self.addCleanup(self.owner.stop)
        self.values = {'name': 'Persona ficticia', 'targetRoles': 'Analista', 'location': 'España',
                       'experience': 'Formación y proyectos ficticios de análisis.'}

    def apply(self, operation):
        self.serial += 1
        return stubbs_jobs.apply_batch(self.data, {'id': 'TEST-interview-'+str(self.serial), 'operations': [operation]})

    def progress(self, status='preparing', **changes):
        state = onboarding.view(self.data)
        return self.apply({'kind': 'ui-setup-progress', 'workspaceId': state['workspaceId'], 'token': state['token'],
                           'expected': state['revision'], 'agent': 'TEST Agente', 'summary': 'Entrevista ficticia.',
                           'proof': 'TEST comprobación local.', 'status': status, **changes})

    def access(self):
        self.progress('access_checked')

    def prepare(self, values=None):
        values = self.values if values is None else values
        self.access()
        self.progress('awaiting_confirmation', values=values, fieldDecisions=interview_choices(self.data, values))

    def confirmation(self, values=None):
        state = onboarding.view(self.data)
        return {'kind': 'ui-onboarding', 'expected': False, 'workspaceId': state['workspaceId'], 'token': state['token'],
                'expectedSetupRevision': state['revision'], 'values': state['draft'] if values is None else values,
                'proof': 'TEST: la persona ficticia confirma el resumen completo y sus vacíos.'}

    def coverage(self):
        return onboarding.view(self.data)['coverage']

    def statuses(self):
        return {field['key']: field['status'] for field in self.coverage()['fields']}

    def test_inventory_covers_all_current_fields_including_cv_but_not_retired_mail(self):
        active = set(personalization.CONTEXT) - {'checkMail'}
        active.update(workflow.CONTACT_FIELDS)
        active.update(workflow.DEMOGRAPHIC_FIELDS)
        active.update({'experience', 'currentCity', 'workAuthorizations', 'salaryExpectationFixed',
                       'contract', 'location', 'maxTrips', 'minimumFixed', 'noticeDays', 'cv'})
        self.assertEqual(set(interview.fields(self.data)), active)
        self.assertEqual(self.coverage()['total'], 32)

    def test_new_or_inherited_defaults_are_pending_and_view_does_not_write(self):
        self.data['app']['searchContext']['currency'] = 'EUR'  # Old incomplete installation.
        before = copy.deepcopy(self.data)
        self.assertEqual(self.coverage()['pending'], 32)
        self.assertEqual(self.coverage()['blank'], 0)
        self.assertEqual(self.coverage()['provided'], 0)
        self.assertEqual(self.data, before)

    def test_four_old_required_answers_cannot_hide_optional_omissions(self):
        self.access()
        before = copy.deepcopy(self.data)
        choices = {key: {'status': 'provided', 'proof': 'TEST: dato confirmado.'} for key in self.values}
        with self.assertRaisesRegex(ValueError, 'campos por tratar'):
            self.progress('awaiting_confirmation', values=self.values, fieldDecisions=choices)
        self.assertEqual(self.data, before)
        self.assertFalse(self.data['app']['setupComplete'])

    def test_a_filled_draft_does_not_count_as_human_confirmation(self):
        self.access()
        self.progress(values=self.values)
        self.assertEqual(self.coverage()['pending'], 32)
        self.assertTrue(all(field['status'] == 'pending' for field in self.coverage()['fields']))

    def test_related_answers_merge_and_only_missing_fields_drive_next_questions(self):
        self.access()
        proof = 'TEST: quiero ser analista en España y prefiero dejar las otras zonas vacías.'
        first = {'targetRoles': {'status': 'provided', 'proof': proof},
                 'location': {'status': 'provided', 'proof': proof}, 'regions': {'status': 'blank', 'proof': proof}}
        self.progress(values=self.values, fieldDecisions=first)
        self.progress(fieldDecisions={'name': {'status': 'provided', 'proof': 'TEST: confirmo el nombre ficticio.'}})
        self.assertEqual(self.coverage()['provided'], 3)
        self.assertEqual(self.coverage()['blank'], 1)
        pending = {field['key'] for group in self.coverage()['nextQuestions'] for field in group['fields']}
        self.assertFalse(pending & set(first))
        self.assertNotIn('name', pending)
        self.assertIn('workMode', pending)
        self.assertEqual(onboarding.view(self.data)['draft'], self.values)

    def test_invalid_status_unknown_field_and_unproven_decisions_roll_back(self):
        self.access()
        invalid = ({'name': {'status': 'provided'}}, {'name': {'status': 'provided', 'proof': '  '}},
                   {'name': {'status': 'provided', 'proof': 'x'*2001}}, {'name': {'status': 'skipped', 'proof': 'TEST'}},
                   {'checkMail': {'status': 'blank', 'proof': 'TEST'}}, {'invented': {'status': 'blank', 'proof': 'TEST'}},
                   {'name': {'status': 'provided', 'proof': 'TEST', 'fingerprint': 'forged'}}, [], {'name': None})
        for decisions in invalid:
            with self.subTest(decisions=decisions):
                before = copy.deepcopy(self.data)
                with self.assertRaises(ValueError):self.progress(values=self.values, fieldDecisions=decisions)
                self.assertEqual(self.data, before)

    def test_blank_with_value_and_provided_without_value_are_rejected(self):
        self.access()
        for key, status in (('name', 'blank'), ('maxTrips', 'provided'), ('cv', 'provided')):
            before = copy.deepcopy(self.data)
            with self.assertRaisesRegex(ValueError, 'no coincide'):
                self.progress(values=self.values, fieldDecisions={key: {'status': status, 'proof': 'TEST'}})
            self.assertEqual(self.data, before)

    def test_false_and_zero_are_provided_not_missing_or_blank(self):
        values = {**self.values, 'workAuthorizations': ['Canadá'], 'noticeDays': 0, 'maxTrips': 0}
        self.prepare(values)
        statuses = self.statuses()
        for key in ('workAuthorizations', 'noticeDays', 'maxTrips'):self.assertEqual(statuses[key], 'provided')
        self.apply(self.confirmation())
        self.assertIsNone(self.data['profile']['workPermitWithoutSponsorship'])
        self.assertEqual(self.data['profile']['workAuthorizations'], ['Canadá'])
        self.assertEqual(self.data['profile']['noticeDays'], 0)
        self.assertEqual(app_context.criteria(self.data)['maxTrips'], 0)

    def test_completed_summary_saves_explicit_blanks_without_personal_defaults_or_job_work(self):
        self.prepare()
        self.assertTrue(self.coverage()['complete'])
        self.apply(self.confirmation())
        self.assertTrue(self.data['app']['setupComplete'])
        self.assertEqual(self.data['app']['searchContext']['currency'], '')
        self.assertEqual(self.data['app']['criteria']['contract'], '')
        self.assertIsNone(self.data['profile']['salaryExpectationFixed'])
        self.assertIsNone(self.data['profile']['noticeDays'])
        self.assertFalse(self.data['app']['requests'])
        self.assertFalse(self.data['app']['packages'])
        self.assertFalse(self.data['events'])
        self.assertEqual(self.coverage()['blank'], 28)

    def test_even_essential_fields_can_be_consciously_blank_but_search_requires_roles_and_location(self):
        self.prepare({})
        self.apply(self.confirmation())
        self.assertEqual(self.coverage()['blank'], 32)
        self.assertEqual(self.data['app']['experience'], '')
        with self.assertRaisesRegex(ValueError, 'puestos y la zona'):assistant_flow.plan(self.data)
        self.assertFalse(self.data['app']['requests'])
        # Unchanged blank essentials must not block editing an unrelated field.
        self.apply({'kind': 'ui-profile-section', 'section': 'about', 'values': {'name': '', 'currentCity': 'Ciudad ficticia'},
                    'expected': {'name': '', 'currentCity': None}})
        self.assertEqual(self.data['profile']['currentCity'], 'Ciudad ficticia')

    def test_salary_requires_confirmed_currency_and_never_assumes_eur(self):
        self.access()
        values = {**self.values, 'minimumFixed': 30000}
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'moneda'):
            self.progress('awaiting_confirmation', values=values, fieldDecisions=interview_choices(self.data, values))
        self.assertEqual(self.data, before)
        values['currency'] = 'USD'
        self.progress('awaiting_confirmation', values=values, fieldDecisions=interview_choices(self.data, values))
        self.apply(self.confirmation())
        self.assertEqual(self.data['app']['searchContext']['currency'], 'USD')
        self.assertEqual(self.data['profile']['minimumFixed'], 30000)

    def test_changed_answer_reopens_only_its_decision_and_requires_new_summary(self):
        self.prepare()
        stale = self.confirmation()
        values = {**self.values, 'location': 'Portugal'}
        self.progress(values=values)
        self.assertEqual(self.coverage()['pending'], 1)
        self.assertEqual(self.statuses()['location'], 'pending')
        self.assertEqual(self.statuses()['targetRoles'], 'provided')
        with self.assertRaises(ValueError):self.apply(stale)
        with self.assertRaisesRegex(ValueError, 'campos por tratar'):self.progress('awaiting_confirmation')
        self.progress('awaiting_confirmation', fieldDecisions={'location': {'status': 'provided', 'proof': 'TEST: confirmo Portugal.'}})
        self.apply(self.confirmation())
        self.assertEqual(self.data['app']['criteria']['location'], 'Portugal')

    def test_changing_currency_requires_reconfirming_amounts_with_their_new_meaning(self):
        values = {**self.values, 'currency': 'EUR', 'minimumFixed': 30000, 'salaryExpectationFixed': 35000}
        self.prepare(values)
        self.progress(values={**values, 'currency': 'USD'}, fieldDecisions={
            'currency': {'status': 'provided', 'proof': 'TEST: quiero expresar el sueldo en USD.'}})
        self.assertEqual(self.coverage()['pending'], 2)
        self.assertEqual(self.statuses()['minimumFixed'], 'pending')
        self.assertEqual(self.statuses()['salaryExpectationFixed'], 'pending')
        with self.assertRaises(ValueError):self.progress('awaiting_confirmation')

    def test_changing_search_country_preserves_confirmed_permissions_without_expanding_them(self):
        values = {**self.values, 'workAuthorizations': ['España']}
        self.prepare(values)
        self.progress(values={**values, 'location': 'Portugal'}, fieldDecisions={
            'location': {'status': 'provided', 'proof': 'TEST: confirmo Portugal como nuevo destino.'}})
        self.assertEqual(self.coverage()['pending'], 0)
        self.assertEqual(self.statuses()['workAuthorizations'], 'provided')
        self.assertEqual(self.data['app']['onboarding']['draft']['workAuthorizations'], ['España'])
        self.assertEqual(self.statuses()['currentCity'], 'blank')

    def test_add_remove_or_change_cv_after_summary_requires_review_again(self):
        for library in ([{'id': 'TEST-cv', 'name': 'Ficticio.pdf', 'path': 'outputs/cv/test.pdf'}],
                        [{'id': 'TEST-second', 'name': 'Ficticio.pdf', 'path': 'outputs/cv/test.pdf'}]):
            self.data = personalization.blank_store()
            self.prepare()
            self.data['app']['cvLibrary'] = library
            self.assertEqual(onboarding.view(self.data)['status'], 'preparing')
            self.assertEqual(self.coverage()['pending'], 1)
            self.assertEqual(self.statuses()['cv'], 'pending')
            with self.assertRaises(ValueError):self.apply(self.confirmation())
            self.progress('awaiting_confirmation', fieldDecisions={'cv': {'status': 'provided', 'proof': 'TEST: confirmo el PDF ficticio.'}})
            self.data['app']['cvLibrary'] = []
            self.assertEqual(self.statuses()['cv'], 'pending')

    def test_cv_order_alone_does_not_repeat_confirmed_document_choice(self):
        self.data['app']['cvLibrary'] = [{'id': 'a', 'name': 'A.pdf', 'path': 'outputs/cv/a.pdf'},
                                       {'id': 'b', 'name': 'B.pdf', 'path': 'outputs/cv/b.pdf'}]
        self.prepare()
        self.data['app']['cvLibrary'].reverse()
        self.assertEqual(self.statuses()['cv'], 'provided')
        self.assertTrue(self.coverage()['complete'])

    def test_resume_preserves_decisions_and_cvs_and_invalidates_previous_owner(self):
        self.access()
        self.progress(values=self.values, fieldDecisions={'name': {'status': 'provided', 'proof': 'TEST: nombre confirmado.'}})
        self.data['app']['cvLibrary'] = [{'id': 'TEST-cv', 'name': 'Ficticio.pdf', 'path': 'outputs/cv/test.pdf'}]
        before = onboarding.view(self.data)
        stale = self.confirmation()
        self.apply({'kind': 'ui-setup-retry', 'workspaceId': before['workspaceId'], 'token': before['token'], 'expected': before['revision']})
        after = onboarding.view(self.data)
        self.assertEqual(after['fieldDecisions'], before['fieldDecisions'])
        self.assertEqual(after['draft'], before['draft'])
        self.assertEqual(self.statuses()['name'], 'provided')
        self.assertEqual(len(self.data['app']['cvLibrary']), 1)
        with self.assertRaises(workflow.Conflict):self.apply(stale)
        with patch.dict(os.environ, {'STUBBS_JOBS_EXECUTION_ID': 'TEST-interview-two'}):self.access()
        with self.assertRaises(workflow.Conflict):self.progress()

    def test_current_custom_global_fields_are_included_and_keep_types_and_meaning(self):
        self.data['app']['questionCatalogInitialized'] = True
        self.data['app']['questionCatalog'] = {
            'custom_relocation': {'key': 'custom_relocation', 'label': '¿Aceptas mudarte?', 'type': 'boolean', 'scope': 'global'},
            'custom_one_offer': {'key': 'custom_one_offer', 'label': 'Una pregunta de oferta', 'type': 'text', 'scope': 'opportunity'}}
        self.assertIn('custom_relocation', interview.fields(self.data))
        self.assertNotIn('custom_one_offer', interview.fields(self.data))
        self.prepare({**self.values, 'custom_relocation': False})
        self.assertEqual(self.statuses()['custom_relocation'], 'provided')
        self.data['app']['questionCatalog']['custom_relocation']['label'] = 'Un significado distinto'
        self.assertEqual(self.statuses()['custom_relocation'], 'pending')

    def test_custom_global_response_is_saved_with_profile_without_new_job_tasks(self):
        self.data['app']['questionCatalogInitialized'] = True
        self.data['app']['questionCatalog'] = {
            'custom_relocation': {'key': 'custom_relocation', 'label': '¿Aceptas mudarte?', 'type': 'boolean', 'scope': 'global'}}
        self.prepare({**self.values, 'custom_relocation': False})
        self.apply(self.confirmation())
        self.assertIs(self.data['profile']['custom_relocation'], False)
        self.assertFalse(self.data['app']['requests'])

    def test_absent_optional_global_question_stays_pending_after_initial_confirmation(self):
        self.prepare()
        self.data['app']['questionCatalogInitialized'] = True
        self.data['app']['questionCatalog'] = {
            'custom_relocation': {'key': 'custom_relocation', 'label': '¿Aceptas mudarte?', 'type': 'boolean', 'scope': 'global'}}
        self.assertEqual(self.coverage()['pending'], 1)
        self.assertTrue(self.coverage()['complete'])
        self.apply(self.confirmation())
        self.assertIsNone(self.data['profile'].get('custom_relocation'))
        self.assertEqual(self.statuses()['custom_relocation'],'pending')

    def test_existing_prepared_profiles_and_documents_remain_available_without_interview(self):
        self.data['app'].pop('onboarding')
        self.data['app']['setupComplete'] = True
        self.data['app']['cvLibrary'] = [{'id': 'TEST-existing', 'path': 'outputs/cv/existing.pdf'}]
        before = copy.deepcopy(self.data)
        state = onboarding.view(self.data)
        self.assertEqual(state['status'], 'ready')
        self.assertIsNone(state['coverage'])
        self.assertEqual(self.data, before)

    def test_old_incomplete_summary_requires_coverage_without_losing_original_draft(self):
        self.data['app']['onboarding'].update(status='awaiting_confirmation', draft=self.values,
                                              checkedAt='2026-10-01T10:00:00Z')
        self.data['app']['onboarding'].pop('fieldDecisions')
        before = copy.deepcopy(self.data)
        state = onboarding.view(self.data)
        self.assertEqual(state['status'], 'preparing')
        self.assertEqual(state['coverage']['pending'], 32)
        self.assertEqual(state['draft'], self.values)
        self.assertEqual(self.data, before)

    def test_completed_coverage_does_not_reopen_when_person_edits_their_ready_profile(self):
        self.prepare()
        self.apply(self.confirmation())
        finished = copy.deepcopy(self.coverage())
        self.apply({'kind': 'ui-profile-section', 'section': 'search', 'values': {'location': 'Portugal'}, 'expected': {'location': 'España'}})
        self.assertEqual(self.coverage(), finished)
        self.assertEqual(onboarding.view(self.data)['status'], 'ready')
        self.assertFalse(self.data['app']['requests'])

    def test_agent_compact_and_full_views_expose_pending_questions_without_writing(self):
        before = copy.deepcopy(self.data)
        for detailed in (False, True):
            shown = agent_context.view(self.data, profile_detail=detailed)
            self.assertEqual(shown['onboarding']['coverage']['pending'], 32)
            self.assertTrue(shown['onboarding']['coverage']['nextQuestions'])
            self.assertFalse(shown['queuedSnapshot'])
        self.assertEqual(self.data, before)


if __name__ == '__main__':
    unittest.main()
