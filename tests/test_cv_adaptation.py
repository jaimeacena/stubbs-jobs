"""A reviewed package says whether its CV was tailored to the offer. Fictional only."""
import copy
import unittest
import app_workflow as w
import stubbs_jobs_core as core
from workflow_fixtures import WorkflowFixture

REASON = 'TEST: resumen y orden adaptados a los requisitos del anuncio ficticio.'


class CVAdaptationTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        WorkflowFixture.setUp(self)
        d = w.draft(self.data, 'one')
        d.update(messageUsage='form', formAnswerKeys=[], requiredAnswers=[], cvReason=w.PENDING_CV_REASON)
        w.state(self.data)['selections']['one'] = {'selected': True, 'mode': 'review', 'at': core.now(), 'actor': 'Persona'}

    def review_operation(self):
        return {'kind': 'ui-review', 'opportunityId': 'one', 'checks': {key: True for key in w.CHECKS},
                'proof': 'TEST: oferta, destino, CV, formulario y duplicados comprobados.',
                'fingerprint': w.stamp(self.data, 'one')}

    def draft(self, **values):
        old = w.draft(self.data, 'one')
        self.apply({'kind': 'ui-draft', 'opportunityId': 'one', 'values': values,
                    'expected': {key: old.get(key) for key in values}})

    def test_review_requires_a_declared_adaptation_and_a_real_reason(self):
        with self.assertRaisesRegex(ValueError, 'cvAdaptation'):
            self.apply(self.review_operation())
        self.draft(cvAdaptation='reused')
        with self.assertRaisesRegex(ValueError, 'cvReason'):
            self.apply(self.review_operation())
        self.assertFalse(w.state(self.data)['packages'])
        with self.assertRaises(ValueError):
            self.draft(cvAdaptation='maybe')

    def test_reused_general_cv_is_allowed_with_its_reason_and_frozen_in_the_package(self):
        self.draft(cvAdaptation='reused', cvReason='TEST: el CV general ficticio ya cubre todos los requisitos.')
        self.apply(self.review_operation())
        package = w.state(self.data)['packages'][0]
        self.assertEqual(package['payload']['cvAdaptation'], 'reused')

    def test_an_adapted_cv_cannot_be_the_pdf_of_another_offer(self):
        other = copy.deepcopy(self.row)
        other.update({'ID': 'two', 'Clave canónica': core.identity('https://example.org/jobs/456-other'),
                      'URL original': 'https://example.org/jobs/456-other'})
        self.data['sheets']['Oportunidades'].append(other)
        self.draft(cvAdaptation='adapted', cvReason=REASON)
        with self.assertRaisesRegex(ValueError, 'otra oferta'):
            self.apply(self.review_operation())
        (self.root / 'outputs/cv-one.pdf').write_bytes(b'%PDF-test-adapted-one')
        # A rejected batch restores the registry, so read the current row again.
        w.row_for(self.data, 'one')['CV preparado'] = 'outputs/cv-one.pdf'
        self.apply(self.review_operation())
        self.assertEqual(w.state(self.data)['packages'][0]['payload']['cvAdaptation'], 'adapted')

    def test_older_packages_keep_their_fingerprint_without_the_field(self):
        before = w.stamp(self.data, 'one')
        self.assertNotIn('cvAdaptation', w.payload(self.data, 'one'))
        self.draft(cvAdaptation='reused')
        self.assertNotEqual(w.stamp(self.data, 'one'), before)


if __name__ == '__main__':
    unittest.main()
