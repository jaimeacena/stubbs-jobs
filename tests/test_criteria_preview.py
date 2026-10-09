"""Preview of a criteria change: counts only, never a write. Fictional data only."""
import copy
import unittest
import app_context
import app_workflow as workflow
import criteria_preview
import offer_quality
import test_search_rounds as rounds


class CriteriaPreviewTests(unittest.TestCase):
    setUp = rounds.SearchRoundTests.setUp
    apply = rounds.SearchRoundTests.apply
    start = rounds.SearchRoundTests.start
    find = rounds.SearchRoundTests.find
    finish = rounds.SearchRoundTests.finish
    hybrid_round = rounds.SearchRoundTests.hybrid_round
    row_of = rounds.SearchRoundTests.row_of

    def preview(self, request):
        before = copy.deepcopy(self.data)
        result = criteria_preview.preview(self.data, request)
        self.assertEqual(self.data, before, 'La vista previa no debe modificar los datos')
        return result

    def test_unchanged_or_new_empty_criteria_change_nothing(self):
        self.hybrid_round()
        context = self.data['app']['searchContext']
        for values in ({'workMode': context['workMode']}, {'onsiteLocations': ''},
                       {'minimumFixed': self.data['profile']['minimumFixed']}):
            with self.subTest(values=values):
                result = self.preview({'values': values})
                self.assertEqual(set(result['counts'].values()) - {0}, set(), result)
                self.assertEqual(result['revision'], self.data['revision'])

    def test_new_criteria_reach_offers_without_round_but_not_offers_of_earlier_rounds(self):
        self.hybrid_round()
        self.find(None, 'loose')
        self.row_of('loose')['Modalidad'] = 'Híbrido'
        result = self.preview({'values': {'workMode': 'Remoto, Híbrido'}})
        self.assertEqual(result['toEligible'], ['loose'])
        self.assertNotIn('old', result['toEligible'])
        # Moving the round to the new criteria as well recovers its offer.
        request = self.data['app']['requests'][-1]['id']
        both = self.preview({'values': {'workMode': 'Remoto, Híbrido'}, 'mode': 'current', 'round': request})
        self.assertEqual(both['toEligible'], ['old'])
        self.assertEqual(both['offers'], 1)

    def test_moving_offers_to_current_or_back_to_their_round(self):
        request = self.hybrid_round()
        self.data['app']['searchContext']['workMode'] = 'Remoto, Híbrido'
        result = self.preview({'mode': 'current', 'targets': [{'id': 'old'}]})
        self.assertEqual((result['toEligible'], result['toDiscarded']), (['old'], []))
        self.apply({'kind': 'ui-criteria-scope', 'targets': [{'id': 'old'}], 'mode': 'current',
                    'expectedRevision': self.data['revision'], 'proof': 'TEST: criterios actuales.'})
        back = self.preview({'mode': 'round', 'round': request['id']})
        self.assertEqual((back['toEligible'], back['toDiscarded']), ([], ['old']))

    def test_valuations_and_packages_that_would_stop_matching_are_counted(self):
        row = self.row_of('one')
        self.apply({'kind': 'ui-fit-review', 'opportunityId': 'one', 'fingerprint': app_context.fit_stamp(self.data, row),
                    'apply': True, 'accept': True, 'proof': 'TEST: encaje ficticio.'})
        self.data['app'].setdefault('offerAssessments', {})['one'] = {'fingerprint': offer_quality.fingerprint(self.data, row)}
        # Final review and an authorized package of the current material.
        workflow.draft(self.data, 'one')['review'] = {'fingerprint': workflow.stamp(self.data, 'one'), 'at': workflow.now()}
        package = workflow.archive(self.data, 'one')
        package['approvedAt'] = workflow.now()
        result = self.preview({'values': {'minimumFixed': self.data['profile']['minimumFixed'] + 1000}})
        for key in ('assessments', 'fitReviews', 'packages', 'authorizedPackages'):
            self.assertEqual(result[key], ['one'], key)

    def test_sent_closed_and_personally_discarded_offers_are_left_out(self):
        self.find(None, 'sent')
        self.find(None, 'mine')
        for key in ('sent', 'mine'):
            self.row_of(key)['Modalidad'] = 'Híbrido'
        self.data['events'].append({'id': 'TEST-sent', 'type': 'sent', 'opportunityId': 'sent', 'at': workflow.now(), 'proof': 'TEST'})
        self.apply({'kind': 'ui-bulk-action', 'action': 'archive', 'targets': [{'id': 'mine'}], 'expectedRevision': self.data['revision']})
        result = self.preview({'values': {'workMode': 'Remoto'}})
        self.assertIn('sent', result['excluded'])
        self.assertIn('mine', result['excluded'])
        self.assertNotIn('mine', result['toDiscarded'])

    def test_invalid_requests_are_rejected_like_the_real_operation(self):
        self.hybrid_round()
        for request, message in (({}, 'Indica'), ({'values': {}}, 'Indica'), ({'mode': 'later', 'targets': [{'id': 'old'}]}, 'Elige'),
                                 ({'mode': 'current', 'targets': [{'id': 'missing'}]}, 'desconocidas'),
                                 ({'mode': 'round', 'targets': [{'id': 'one'}]}, 'ninguna ronda'),
                                 ({'values': {'name': 'Otra'}}, 'sección')):
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, message):
                self.preview(request)
