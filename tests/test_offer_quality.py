"""Known synthetic cases: eligibility, provenance and incomplete application material."""
import copy
import json
from pathlib import Path
import unittest

from workflow_fixtures import WorkflowFixture, fixture
import app_context
import app_workflow as workflow
import offer_quality
import stubbs_jobs


class QualityBenchmarkTests(unittest.TestCase):
    def test_known_offer_cases_preserve_uncertainty_and_hard_limits(self):
        records = json.loads((Path(__file__).parent / 'quality_cases.json').read_text(encoding='utf-8'))
        for record in records:
            with self.subTest(record['name']):
                data = fixture()
                row = data['sheets']['Oportunidades'][0]
                row.update(record['changes'])
                self.assertEqual(stubbs_jobs.conditions(data, row)[0], record['expected'])
                self.assertFalse(data['events'])

    def test_republication_does_not_become_two_offers_or_a_verified_condition(self):
        data = fixture()
        # This case discovers a new vacancy; existing opportunities are aliases too.
        data['sheets']['Oportunidades'][0]['URL original']='https://example.org/jobs/456-other'
        payload = {'schemaVersion': 2, 'checkedAtUtc': '2026-10-01T10:00:00Z', 'boards': [], 'candidates': [
            {'url': url, 'sourceId': 'synthetic', 'company': 'Example', 'title': 'BI Developer', 'originalPublishedAt': None}
            for url in ('https://example.org/jobs/123-role?utm_source=one', 'https://example.org/jobs/123-role?utm_source=two')]}
        self.assertEqual(stubbs_jobs.ingest(data, payload), 1)
        self.assertEqual(stubbs_jobs.ingest(data, payload), 0)
        self.assertEqual(len(data['sheets']['Entradas']), 1)
        self.assertEqual(data['sheets']['Entradas'][0]['Estado'], 'Nueva')
        self.assertEqual(len(data['sheets']['Oportunidades']), 1)
        self.assertFalse(data['events'])


class OfferAssessmentTests(unittest.TestCase):
    setUp = WorkflowFixture.setUp
    apply = WorkflowFixture.apply
    review = WorkflowFixture.review

    def assessment(self, **values):
        row = self.data['sheets']['Oportunidades'][0]
        return {'observedAt':'2026-10-06T10:00:00+02:00', 'kind': 'ui-offer-assessment', 'opportunityId': 'one', 'fingerprint': offer_quality.fingerprint(self.data, row),
                'reason': 'El trabajo de BI coincide con la experiencia confirmada de esta persona ficticia.',
                'references': [{'url': 'https://example.org/jobs/123-role', 'text': 'El anuncio pide modelos e informes de BI.'}],
                'unknowns': ['Confirmar la parte fija del salario.'], 'proof': 'TEST fictitious advertisement checked', **values}

    def test_reason_and_unknowns_do_not_grant_permission_or_prepare_unselected_offers(self):
        original = workflow.stamp(self.data, 'one')
        self.apply(self.assessment())
        result = offer_quality.view(self.data, self.data['sheets']['Oportunidades'][0])
        self.assertTrue(result['isCurrent'])
        self.assertTrue(result['unknowns'])
        self.assertEqual(workflow.stamp(self.data, 'one'), original)
        self.assertFalse(workflow.state(self.data)['packages'])
        self.assertFalse(workflow.state(self.data)['requests'])

    def test_assessment_is_stale_after_offer_changes(self):
        self.apply(self.assessment())
        self.data['sheets']['Oportunidades'][0]['Fijo mín. confirmado'] = 41000
        self.assertFalse(offer_quality.view(self.data, self.data['sheets']['Oportunidades'][0])['isCurrent'])

    def test_experience_changes_require_a_new_reason_without_rewriting_an_archived_package(self):
        self.apply(self.assessment())
        self.data['app']['experience'] = 'Otra experiencia ficticia confirmada.'
        self.assertFalse(offer_quality.view(self.data, self.data['sheets']['Oportunidades'][0])['isCurrent'])

    def test_invalid_or_unsupported_assessments_preserve_existing_state(self):
        for values in ({'fingerprint': 'old'}, {'reason': ''}, {'references': []}, {'references': [{'url': 'javascript:alert(1)', 'text': 'TEST'}]}, {'unknowns': 'unknown'}):
            before = copy.deepcopy(self.data)
            with self.assertRaises(ValueError):
                self.apply(self.assessment(**values))
            self.assertEqual(self.data, before)

    def test_an_incomplete_form_cannot_become_a_reviewed_application(self):
        draft = workflow.draft(self.data, 'one')
        self.apply({'kind': 'ui-draft', 'opportunityId': 'one', 'values': {'requiredAnswers': ['currentCity']}, 'expected': {'requiredAnswers': draft['requiredAnswers']}})
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'faltan'):
            self.review()
        # review() selects this synthetic offer; the failed review itself conserves material.
        self.assertFalse(workflow.state(self.data)['packages'])
        self.assertFalse(self.data['events'])


if __name__ == '__main__':
    unittest.main()
