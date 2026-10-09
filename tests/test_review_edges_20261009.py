"""Fresh audit regressions, with fictional profiles and isolated documents."""
import copy
import unittest
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import app_context as context
import app_workflow as workflow
import criteria_preview
import offer_quality
import stubbs_jobs_app as server
from stubbs_jobs_core import digest


class ReviewEdgesTests(WorkflowFixture, unittest.TestCase):
    def legacy_receipt(self):
        original = self.root / 'outputs/original-sent.pdf'
        original.write_bytes(b'%PDF-original-sent-version')
        self.data['updatedAt'] = workflow.now()
        self.data['events'].append({'id': 'TEST-receipt', 'type': 'sent', 'opportunityId': 'one',
            'at': workflow.now(), 'confirmation': 'TEST: recibo ficticio anterior a los paquetes',
            'cv': 'outputs/original-sent.pdf', 'cvHash': digest(original.read_bytes())})
        workflow.draft(self.data, 'one').update(messageUsage='form', formAnswerKeys=['noticeDays'])
        context.definitions(self.data, 'one')
        for name, value in (('ROOT', self.root), ('DATA', self.root / 'data'), ('read_store', lambda: self.data)):
            replacement = patch.object(server, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        return original

    def projected_offer(self):
        with patch.object(server.personalization, 'public_sources', return_value=[]):
            return server.build_state(self.data, include_export=False, include_instructions=False,
                                      execution={'status': 'idle'})['opportunities'][0]

    def test_legacy_sent_offer_shows_only_the_original_document_and_known_material(self):
        original = self.legacy_receipt()
        before = copy.deepcopy(self.data)
        offer = self.projected_offer()
        self.assertEqual(offer['cv'], 'outputs/original-sent.pdf')
        self.assertEqual(offer['cvUrl'], server.document_url('sent:one'))
        self.assertEqual(server.doc_path('sent:one'), original)
        self.assertEqual(offer['sentMaterial']['answers'], {})
        self.assertEqual(offer['sentMaterial']['messageUsage'], 'unknown')
        self.assertEqual(self.data, before)

    def test_legacy_receipt_without_document_hash_does_not_claim_a_current_cv_was_sent(self):
        self.legacy_receipt()
        self.data['events'][0].pop('cvHash')
        offer = self.projected_offer()
        self.assertIsNone(offer['cvUrl'])
        self.assertIsNone(offer['cv'])
        self.assertTrue(offer['integrityError'])

    def test_changed_legacy_sent_document_refreshes_the_view_and_cannot_be_opened(self):
        original = self.legacy_receipt()
        first = server.state_version(self.data, brief=True, execution={'status': 'idle'})
        original.write_bytes(b'%PDF-changed-after-sending')
        second = server.state_version(self.data, brief=True, execution={'status': 'idle'})
        self.assertNotEqual(first, second)
        self.assertIsNone(self.projected_offer()['cvUrl'])
        with self.assertRaisesRegex(ValueError, 'original'):
            server.doc_path('sent:one')

    def test_legacy_sent_document_route_rejects_an_unregistered_package_and_an_unsafe_path(self):
        self.legacy_receipt()
        self.data['events'][0]['packageId'] = 'f' * 64
        self.assertIsNone(self.projected_offer()['cvUrl'])
        with self.assertRaises(ValueError):
            server.doc_path('sent:one')
        self.data['events'][0].pop('packageId')
        self.data['events'][0]['cv'] = '../outside.pdf'
        self.assertIsNone(self.projected_offer()['cvUrl'])
        with self.assertRaises(ValueError):
            server.doc_path('sent:one')

    def survey(self, global_choice, local_choice):
        self.data['profile'].update(gender='Dato ficticio', demographicSurveyParticipation=global_choice)
        draft = workflow.draft(self.data, 'one')
        draft['formAnswerKeys'] = ['gender', 'demographicSurveyParticipation']
        draft['answers']['demographicSurveyParticipation'] = local_choice
        return workflow.answers(self.data, 'one')

    def test_specific_survey_refusal_does_not_disclose_the_inherited_gender(self):
        answers = self.survey(True, False)
        self.assertIs(answers['demographicSurveyParticipation'], False)
        self.assertEqual(answers['gender'], 'Prefiero no responder')

    def test_pending_specific_survey_choice_does_not_inherit_global_permission(self):
        answers = self.survey(True, None)
        self.assertIsNone(answers['gender'])

    def test_specific_survey_agreement_can_use_the_confirmed_inherited_gender(self):
        answers = self.survey(False, True)
        self.assertEqual(answers['gender'], 'Dato ficticio')
        self.assertIs(answers['demographicSurveyParticipation'], True)

    def test_explicit_specific_gender_keeps_its_own_confirmed_answer(self):
        self.survey(False, False)
        workflow.draft(self.data, 'one')['answers']['gender'] = 'Respuesta expresa para esta oferta'
        self.assertEqual(workflow.answers(self.data, 'one')['gender'], 'Respuesta expresa para esta oferta')

    def prepared_round(self):
        app = workflow.state(self.data)
        app['searchContext'] = {'workMode': 'Remoto', 'currency': 'EUR'}
        app['criteria'] = dict(context.DEFAULT_CRITERIA)
        request = {'id': 'TEST-original-round', 'type': 'discovery', 'status': 'done',
                   'opportunityId': None, 'round': workflow.search_round(self.data),
                   'createdAt': workflow.now(), 'updatedAt': workflow.now()}
        app['requests'].append(request)
        app['offerRounds'] = {'one': request['id']}
        self.row['Estado'] = 'Lista para revisión'
        app['fitReviews'] = {'one': {'fingerprint': context.fit_stamp(self.data, self.row),
                                   'apply': True, 'accept': False, 'proof': 'TEST'}}
        app['offerAssessments'] = {'one': {'fingerprint': offer_quality.fingerprint(self.data, self.row)}}
        draft = workflow.draft(self.data, 'one')
        draft.update(messageUsage='unused', formAnswerKeys=[], checks={k: True for k in workflow.CHECKS})
        fingerprint = workflow.stamp(self.data, 'one')
        draft['review'] = {'fingerprint': fingerprint, 'at': workflow.now()}
        package = workflow.archive(self.data, 'one')
        package['approvedAt'] = workflow.now()
        return {'values': {'workMode': 'Remoto, Híbrido'}, 'mode': 'current',
                'targets': [{'id': 'one'}]}

    def test_combined_preview_counts_invalidated_material_after_the_final_scope_change(self):
        request = self.prepared_round()
        original = copy.deepcopy(self.data)
        candidate = criteria_preview._simulate(self.data, request)
        self.assertNotEqual(workflow.stamp(self.data, 'one'), workflow.stamp(candidate, 'one'))
        result = criteria_preview.preview(self.data, request)
        for key in ('assessments', 'fitReviews', 'packages', 'authorizedPackages'):
            self.assertEqual(result[key], ['one'], key)
        self.assertEqual(self.data, original)
