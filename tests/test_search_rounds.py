"""Search rounds: each search keeps the criteria it ran with; fictional data only."""
import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from workflow_fixtures import WorkflowFixture
import app_workflow as workflow


class SearchRoundTests(unittest.TestCase):
    apply = WorkflowFixture.apply

    def setUp(self):
        WorkflowFixture.setUp(self)
        patcher = patch.object(workflow, 'datetime', wraps=datetime)
        clock = patcher.start()
        self.addCleanup(patcher.stop)
        clock.now.return_value = datetime(2026, 9, 30, 7, 30, tzinfo=timezone.utc)
        self.n = 0

    def start(self):
        self.apply({'kind': 'ui-request', 'type': 'discovery'})
        request = workflow.state(self.data)['requests'][-1]
        self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'Inicio ficticio'})
        return workflow.state(self.data)['requests'][-1]

    def find(self, request, key):
        row = copy.deepcopy(self.row)
        row['ID'] = key
        row['Clave canónica'] = key
        self.data['sheets']['Oportunidades'].append(row)

    def finish(self, request):
        with patch('personalization.public_sources', return_value=[]):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'done', 'proof': 'Resultado ficticio'})

    def test_snapshot_is_taken_when_the_search_starts_and_never_rewritten(self):
        self.data['app']['searchContext'] = {**self.data['app'].get('searchContext', {}), 'workMode': 'Remoto'}
        request = self.start()
        frozen = copy.deepcopy(request['round'])
        self.assertEqual(frozen['searchContext']['workMode'], 'Remoto')
        self.assertIn('minimumFixed', frozen['criteria'])
        self.data['app']['searchContext']['workMode'] = 'Híbrido'
        self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'Actividad ficticia'})
        self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'blocked', 'proof': 'Acceso ficticio', 'summary': 'Acceso ficticio pendiente', 'need': 'access'})
        self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'queued', 'proof': 'Reintento ficticio'})
        self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'Reanudada'})
        self.assertEqual(workflow.state(self.data)['requests'][-1]['round'], frozen)

    def test_new_offers_are_tagged_with_their_round_and_rounds_report_what_changed(self):
        self.data['app']['searchContext'] = {**self.data['app'].get('searchContext', {}), 'workMode': 'Remoto'}
        first = self.start()
        self.find(first, 'a1')
        self.find(first, 'a2')
        self.finish(first)
        self.data['app']['searchContext']['workMode'] = 'Remoto, Híbrido'
        self.data['app']['searchContext']['onsiteLocations'] = 'Villa Norte'
        second = self.start()
        self.find(second, 'b1')
        self.finish(second)
        tags = workflow.state(self.data)['offerRounds']
        self.assertEqual(tags, {'a1': first['id'], 'a2': first['id'], 'b1': second['id']})
        one, two = workflow.rounds(self.data)
        self.assertEqual((one['newOffers'], two['newOffers']), (2, 1))
        self.assertEqual(one['changed'], [])
        self.assertEqual(two['changed'], ['searchContext.onsiteLocations', 'searchContext.workMode'])

    def test_rounds_report_current_eligibility_of_each_round(self):
        self.data['app']['searchContext'] = {**self.data['app'].get('searchContext', {}), 'workMode': 'Remoto, Híbrido',
                                             'onsiteLocations': 'Villa Norte'}
        request = self.start()
        self.find(request, 'near')
        self.find(request, 'far')
        for row in self.data['sheets']['Oportunidades']:
            if row['ID'] in ('near', 'far'):
                row['Modalidad'] = 'Híbrido'
                row['Ubicación'] = 'Villa Norte' if row['ID'] == 'near' else 'Madrid'
        self.finish(request)
        summary, = workflow.rounds(self.data)
        self.assertEqual((summary['newOffers'], summary['eligibleNow']), (2, 1))

    def test_requests_without_a_snapshot_are_ignored(self):
        workflow.state(self.data)['requests'] = [{'id': 'legacy', 'type': 'discovery', 'status': 'done',
                                                   'opportunityId': None, 'createdAt': '2026-09-28T09:00:00+02:00'}]
        self.assertEqual(workflow.rounds(self.data), [])

    def hybrid_round(self):
        """A remote-only round finds a hybrid offer; the next round will accept hybrid."""
        self.data['app']['searchContext'] = {**self.data['app'].get('searchContext', {}), 'workMode': 'Remoto'}
        request = self.start()
        self.find(request, 'old')
        next(r for r in self.data['sheets']['Oportunidades'] if r['ID'] == 'old')['Modalidad'] = 'Híbrido'
        self.finish(request)
        return request

    def row_of(self, key):
        return next(r for r in self.data['sheets']['Oportunidades'] if r['ID'] == key)

    def test_offers_keep_their_rounds_criteria_when_global_criteria_change(self):
        import offer_minimums
        import app_context
        self.hybrid_round()
        self.assertIsNotNone(workflow.archived(self.data, 'old'))
        stamp = app_context.fit_stamp(self.data, self.row_of('old'))
        self.data['app']['searchContext']['workMode'] = 'Remoto, Híbrido'
        self.data['profile']['minimumFixed'] = 50000
        self.find(None, 'fresh')
        self.row_of('fresh')['Modalidad'] = 'Híbrido'
        self.assertFalse(offer_minimums.view(self.data, self.row_of('old'))['canApply'])
        self.assertTrue(offer_minimums.view(self.data, self.row_of('fresh'))['canApply'])
        self.assertEqual(app_context.fit_stamp(self.data, self.row_of('old')), stamp)
        self.assertEqual(app_context.scoped_criteria(self.data, 'old')['minimumFixed'],
                         self.data['app']['requests'][-1]['round']['criteria']['minimumFixed'])

    def test_unchanged_criteria_leave_fingerprints_as_before_rounds_existed(self):
        import app_context
        self.data['app']['searchContext'] = {**self.data['app'].get('searchContext', {}), 'workMode': 'Remoto'}
        request = self.start()
        self.find(request, 'plain')
        before = app_context.fit_stamp(self.data, self.row_of('plain'))
        self.finish(request)
        self.assertIn('plain', workflow.state(self.data)['offerRounds'])
        self.assertEqual(app_context.fit_stamp(self.data, self.row_of('plain')), before)

    def test_adopting_current_criteria_is_explicit_reversible_and_recovers_the_archive(self):
        import offer_minimums
        self.hybrid_round()
        self.data['app']['searchContext']['workMode'] = 'Remoto, Híbrido'
        self.apply({'kind': 'ui-criteria-scope', 'targets': [{'id': 'old'}], 'mode': 'current',
                    'expectedRevision': self.data['revision'], 'proof': 'TEST: la oferta se juzga con los criterios actuales.'})
        self.assertEqual(self.data['app']['currentCriteria'], ['old'])
        self.assertTrue(offer_minimums.view(self.data, self.row_of('old'))['canApply'])
        self.assertIsNone(workflow.archived(self.data, 'old'))
        self.apply({'kind': 'ui-criteria-scope', 'targets': [{'id': 'old'}], 'mode': 'round',
                    'expectedRevision': self.data['revision'], 'proof': 'TEST: vuelve a los criterios de su ronda.'})
        self.assertEqual(self.data['app']['currentCriteria'], [])
        self.assertIsNotNone(workflow.archived(self.data, 'old'))

    def test_scope_change_can_target_a_whole_round_and_rejects_invalid_requests(self):
        request = self.hybrid_round()
        base = {'kind': 'ui-criteria-scope', 'mode': 'current', 'expectedRevision': self.data['revision']}
        before = copy.deepcopy(self.data)
        for bad, message in (({'targets': [{'id': 'old'}]}, 'Explica'),
                             ({'targets': [], 'proof': 'TEST.'}, 'Indica'),
                             ({'targets': [{'id': 'missing'}], 'proof': 'TEST.'}, 'desconocidas'),
                             ({'targets': [{'id': 'one'}], 'mode': 'round', 'proof': 'TEST.'}, 'ninguna ronda')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.apply({**base, **bad})
        self.assertEqual(self.data, before)
        self.apply({**base, 'round': request['id'], 'proof': 'TEST: toda la ronda.'})
        self.assertEqual(self.data['app']['currentCriteria'], ['old'])
