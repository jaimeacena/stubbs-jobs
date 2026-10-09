"""Confirmed examples stay grounded, current and separate from sending permission."""
import copy
import unittest

from workflow_fixtures import WorkflowFixture
import app_workflow as workflow
import offer_quality


class BestArgumentTests(unittest.TestCase):
    apply = WorkflowFixture.apply
    review = WorkflowFixture.review

    def setUp(self):
        WorkflowFixture.setUp(self)
        self.example = 'Automaticé el informe mensual con Power Query y datos unificados.'
        self.limited = 'Conozco la interfaz de Fabric, sin experiencia en pipelines complejos.'
        self.data['app']['experience'] = '# Experiencia ficticia confirmada\n\n- ' + self.example + '\n- ' + self.limited

    def operation(self, **values):
        return {'observedAt':'2026-10-06T10:00:00+02:00', 'kind': 'ui-offer-assessment', 'opportunityId': 'one',
                'fingerprint': offer_quality.fingerprint(self.data, self.row),
                'reason': 'La automatización de informes es un ejemplo pertinente para este puesto ficticio.',
                'references': [{'url': self.row['URL original'], 'text': 'El puesto pide Power Query y reporting corporativo.'}],
                'unknowns': [], 'proof': 'TEST: anuncio ficticio y experiencia confirmada comprobados.',
                'bestArgument': {'experienceQuote': self.example, 'referenceIndex': 0}, **values}

    def test_existing_offer_gets_a_grounded_example_without_material_or_permission_changes(self):
        material = copy.deepcopy(workflow.payload(self.data, 'one'))
        self.apply(self.operation())
        argument = offer_quality.current_argument(self.data, self.row)
        self.assertEqual(argument['experienceQuote'], self.example)
        self.assertEqual(argument['requirement'], self.operation()['references'][0]['text'])
        self.assertEqual(argument['sourceUrl'], self.row['URL original'])
        self.assertEqual(workflow.payload(self.data, 'one'), material)
        for key in ('packages', 'requests', 'selections'):
            self.assertFalse(self.data['app'][key])
        self.assertFalse(self.data['events'])

    def test_whitespace_normalization_keeps_the_complete_example(self):
        self.apply(self.operation(bestArgument={'experienceQuote': '  ' + self.example.replace(' ', '  ') + '  ', 'referenceIndex': 0}))
        self.assertEqual(offer_quality.current_argument(self.data, self.row)['experienceQuote'], self.example)

    def test_invented_shortened_or_heading_examples_are_rejected_atomically(self):
        self.apply(self.operation())
        for quote in ('Automaticé el informe mensual con Python y ahorré el 80 %.',
                      'Conozco la interfaz de Fabric', 'Experiencia ficticia confirmada', '', 42):
            before = copy.deepcopy(self.data)
            with self.subTest(quote), self.assertRaises(ValueError):
                self.apply(self.operation(bestArgument={'experienceQuote': quote, 'referenceIndex': 0}))
            self.assertEqual(self.data, before)

    def test_a_qualification_cannot_be_dropped_but_the_complete_statement_is_kept(self):
        self.apply(self.operation(bestArgument={'experienceQuote': self.limited, 'referenceIndex': 0}))
        self.assertIn('sin experiencia', offer_quality.current_argument(self.data, self.row)['experienceQuote'])

    def test_an_argument_cannot_cite_an_unchecked_source_or_silently_accept_extra_fields(self):
        for value in ({'experienceQuote': self.example, 'referenceIndex': index} for index in (-1, 1, True, '0')):
            with self.subTest(value), self.assertRaises(ValueError):
                self.apply(self.operation(bestArgument=value))
        for value in ({'experienceQuote': self.example, 'referenceIndex': 0, 'result': 'Inventado'}, {}, 'ejemplo'):
            with self.subTest(value), self.assertRaises(ValueError):
                self.apply(self.operation(bestArgument=value))

    def test_a_long_requirement_is_not_presented_as_a_short_argument(self):
        with self.assertRaisesRegex(ValueError, '180'):
            self.apply(self.operation(references=[{'url': self.row['URL original'], 'text': 'a' * 181}]))

    def test_legacy_assessment_and_explicit_absence_keep_the_previous_payload_identity(self):
        original = workflow.stamp(self.data, 'one')
        for value in (None,):
            self.apply(self.operation(bestArgument=value))
            self.assertIsNone(offer_quality.current_argument(self.data, self.row))
            self.assertEqual(workflow.stamp(self.data, 'one'), original)
        operation = self.operation()
        operation.pop('bestArgument')
        self.apply(operation)
        self.assertNotIn('bestArgument', offer_quality.view(self.data, self.row))

    def test_replacing_a_valuation_without_an_example_does_not_reuse_the_old_one(self):
        self.apply(self.operation())
        self.apply(self.operation(bestArgument=None))
        self.assertIsNone(offer_quality.current_argument(self.data, self.row))

    def test_current_argument_is_a_copy_not_a_write_to_the_record(self):
        self.apply(self.operation())
        argument = offer_quality.current_argument(self.data, self.row)
        argument['experienceQuote'] = 'TEST altered projection'
        self.assertEqual(offer_quality.current_argument(self.data, self.row)['experienceQuote'], self.example)

    def test_offer_experience_or_criteria_changes_hide_the_example(self):
        self.apply(self.operation())
        for change in ('experience', 'requirements', 'criteria'):
            changed = copy.deepcopy(self.data)
            if change == 'experience':
                changed['app']['experience'] += '\nCorrección confirmada posterior.'
            elif change == 'requirements':
                changed['sheets']['Oportunidades'][0]['Tecnologías'] = 'Otra herramienta'
            else:
                changed['profile']['minimumFixed'] = 39000
            with self.subTest(change):
                self.assertIsNone(offer_quality.current_argument(changed, changed['sheets']['Oportunidades'][0]))
                self.assertEqual(changed['app']['offerAssessments']['one']['bestArgument']['experienceQuote'], self.example)

    def test_preparation_preserves_context_without_rewriting_existing_packages(self):
        self.apply(self.operation())
        self.review()
        package = self.data['app']['packages'][0]
        archived = copy.deepcopy(package)
        self.assertEqual(package['preparationArgument']['experienceQuote'], self.example)
        self.assertNotIn('bestArgument', package['payload'])
        self.assertNotIn('preparationArgument', package['payload'])
        self.apply(self.operation(bestArgument={'experienceQuote': self.limited, 'referenceIndex': 0}))
        self.assertEqual(self.data['app']['packages'][0], archived)
        self.assertEqual(workflow.stamp(self.data, 'one'), package['id'])
        self.assertFalse(package.get('approvedAt'))

    def test_a_previous_package_keeps_its_identity_and_has_no_invented_context(self):
        self.review()
        original = copy.deepcopy(self.data['app']['packages'][0])
        self.apply(self.operation())
        self.assertEqual(self.data['app']['packages'][0], original)
        self.assertEqual(workflow.archive(self.data, 'one'), original)
        self.assertNotIn('preparationArgument', original)


if __name__ == '__main__':
    unittest.main()
