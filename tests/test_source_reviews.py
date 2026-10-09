"""Fictional browser coverage, written only to an isolated fixture."""
import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import agent_runner
import app_workflow as workflow
import source_reviews


class SourceReviewTests(unittest.TestCase):
    apply = WorkflowFixture.apply

    def setUp(self):
        WorkflowFixture.setUp(self)
        for name, value in (('read_state', {'status': 'idle'}), ('view', {'status': 'idle'})):
            replacement = patch.object(agent_runner, name, return_value=value)
            replacement.start()
            self.addCleanup(replacement.stop)
        replacement = patch.object(workflow, 'now', return_value='2026-10-02T10:00:00+00:00')
        replacement.start()
        self.addCleanup(replacement.stop)
        # Keep the actual recording clock fixed alongside the existing fixture
        # clock, so future-date and start-boundary checks remain meaningful.
        clock=patch.object(source_reviews,'datetime')
        clock.start().now.side_effect=lambda *args:datetime.fromisoformat(workflow.now())
        self.addCleanup(clock.stop)
        self.apply({'kind': 'ui-request', 'type': 'discovery'})
        self.request_id = workflow.state(self.data)['requests'][-1]['id']
        with workflow.execution_owner('test-browser'):
            self.apply({'kind': 'ui-request-update', 'id': self.request_id, 'status': 'running', 'proof': 'TEST actual discovery start'})

    def request(self):
        return next(item for item in self.data['app']['requests'] if item['id'] == self.request_id)

    def test_browser_review_cannot_expand_the_users_exclusive_sites(self):
        self.request()['round']['searchContext']['sourceUrls']='https://allowed.org/jobs'
        self.data['app']['searchContext']={'sourceUrls':'https://example.org/careers'}
        before=copy.deepcopy(self.data)
        with workflow.execution_owner('test-browser'):
            with self.assertRaisesRegex(ValueError,'fuentes exclusivas'):self.apply(self.operation())
        self.assertEqual(self.data,before)

    def operation(self, **values):
        return {'kind': 'ui-source-review', 'id': 'test-browser-check', 'requestId': self.request_id,
                'expectedUpdatedAt': self.request()['updatedAt'], 'expectedExecutionId': 'test-browser',
                'sourceUrl': 'https://example.org/careers', 'name': 'TEST careers',
                'checkedAt': '2026-10-02T10:00:00+00:00', 'scope': 'TEST filter BI and all two visible listing pages',
                'outcome': 'reviewed', 'issues': [], 'proof': 'TEST actual visible list, two pages checked', **values}

    def save(self, **values):
        with workflow.execution_owner('test-browser'):
            self.apply(self.operation(**values))

    def test_official_write_keeps_scope_owner_and_proof_without_changing_source_health(self):
        before_health = copy.deepcopy(self.data['sourceHealth'])
        self.save()
        review = self.data['app']['sourceReviews'][0]
        self.assertEqual((review['requestId'], review['executionId']), (self.request_id, 'test-browser'))
        self.assertEqual(review['scope'], self.operation()['scope'])
        self.assertEqual(review['proof'], self.operation()['proof'])
        self.assertEqual(self.data['sourceHealth'], before_health)
        self.assertEqual(self.request()['status'], 'running')
        self.assertEqual(self.data['app']['history'][-1]['requestId'], self.request_id)

    def test_current_subsecond_review_survives_completion_in_that_same_second(self):
        recorded=datetime(2026,10,2,10,0,0,900000,tzinfo=timezone.utc)
        finished=recorded.replace(microsecond=950000)
        checked=recorded.replace(microsecond=750000).isoformat()
        with patch.object(source_reviews,'datetime') as clock:
            clock.now.return_value=recorded
            self.save(checkedAt=checked)
        review=self.data['app']['sourceReviews'][0]
        self.assertEqual(review['recordedAt'],recorded.isoformat(timespec='microseconds'))
        self.assertEqual(review['checkedAt'],checked)
        with patch.object(workflow,'datetime') as clock,patch('personalization.public_sources',return_value=[]),workflow.execution_owner('test-browser'):
            clock.now.return_value=finished
            self.apply({'kind':'ui-request-update','id':self.request_id,'status':'done','proof':'TEST subsecond result completed'})
        result=self.request()['activityResult']
        self.assertEqual(result['at'],finished.isoformat(timespec='microseconds'))
        self.assertEqual(result['manualReviews'][0]['checkedAt'],checked)
        self.assertEqual(result['health'][0]['checkedAtUtc'],checked)
        self.assertEqual(result['newOfferCount'],0)
        self.assertEqual(self.request()['activityAt'],result['at'])

    def test_precise_clock_rejects_a_future_microsecond_and_an_invalid_start(self):
        recorded=datetime(2026,10,2,10,0,0,900000,tzinfo=timezone.utc)
        checked=recorded.replace(microsecond=750000).isoformat()
        baseline=copy.deepcopy(self.data)
        cases=((None,recorded.replace(microsecond=900001).isoformat()),
               ('TEST invalid legacy start',checked),('2026-10-02T10:00:00.800000+00:00',checked))
        for started,checked_at in cases:
            with self.subTest(started=started,checkedAt=checked_at):
                self.data=copy.deepcopy(baseline)
                if started is not None:self.request()['startedAt']=started
                before=copy.deepcopy(self.data)
                with patch.object(source_reviews,'datetime') as clock,self.assertRaisesRegex(ValueError,'fecha comprobada'):
                    clock.now.return_value=recorded
                    self.save(checkedAt=checked_at)
                self.assertEqual(self.data,before)
                self.assertNotIn('sourceReviews',self.data['app'])

    def test_foreign_missing_or_invalidated_owner_cannot_record_a_review(self):
        baseline = copy.deepcopy(self.data)
        for owner in ('different-chat', None):
            with self.subTest(owner=owner), workflow.execution_owner(owner), patch.dict('os.environ', {}, clear=True):
                with self.assertRaises(ValueError):
                    self.apply(self.operation())
                self.assertEqual(self.data, baseline)
        self.request()['invalidatedExecutionIds'] = ['test-browser']
        before = copy.deepcopy(self.data)
        with workflow.execution_owner('test-browser'), self.assertRaisesRegex(ValueError, 'retirado'):
            self.apply(self.operation())
        self.assertEqual(self.data, before)

    def test_queued_done_and_non_discovery_are_not_real_browser_review_owners(self):
        baseline = copy.deepcopy(self.data)
        for field, value in (('status', 'queued'), ('status', 'done'), ('type', 'change')):
            self.data = copy.deepcopy(baseline)
            self.request()[field] = value
            before = copy.deepcopy(self.data)
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'realmente iniciado'):
                self.save()
            self.assertEqual(self.data, before)

    def test_rejects_stale_request_and_incomplete_checked_dates_atomically(self):
        invalid = ({'expectedUpdatedAt': 'old'}, {'expectedExecutionId': 'wrong'},
                   {'checkedAt': '2026-10-02T09:59:59+00:00'}, {'checkedAt': '2026-10-02T10:00:01+00:00'},
                   {'checkedAt': '2026-10-02T10:00:00'}, {'checkedAt': 'unknown'})
        for values in invalid:
            before = copy.deepcopy(self.data)
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.save(**values)
            self.assertEqual(self.data, before)
        for key in ('expectedUpdatedAt', 'expectedExecutionId'):
            operation = self.operation()
            operation.pop(key)
            before = copy.deepcopy(self.data)
            with workflow.execution_owner('test-browser'), self.assertRaises(ValueError):
                self.apply(operation)
            self.assertEqual(self.data, before)

    def test_rejects_false_clean_results_and_bad_urls(self):
        invalid = ({'scope': ''}, {'proof': ''}, {'issues': None}, {'outcome': 'partial'},
                   {'outcome': 'unsupported'}, {'outcome': 'reviewed', 'issues': ['TEST omitted page']},
                   {'sourceUrl': 'https://user:password@example.org/careers'},
                   {'sourceUrl': 'https://localhost/careers'})
        for values in invalid:
            before = copy.deepcopy(self.data)
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.save(**values)
            self.assertEqual(self.data, before)

    def test_record_id_is_immutable_and_duplicate_identical_content_is_not_another_check(self):
        self.save()
        self.save()
        self.assertEqual(len(self.data['app']['sourceReviews']), 1)
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'otro contenido'):
            self.save(scope='TEST changed scope under the same check ID')
        self.assertEqual(self.data, before)

    def test_snapshot_includes_unconfigured_browser_source_and_preserves_prior_incidents(self):
        self.save(outcome='partial', issues=['TEST second page failed'])
        self.save(id='test-second-check')
        snapshot = source_reviews.snapshot(self.data, self.request(), workflow.now())
        self.assertEqual(len(snapshot['reviews']), 2)
        self.assertEqual(snapshot['reviews'][0]['issues'], ['TEST second page failed'])
        self.assertEqual(snapshot['health'][0]['status'], 'ok')
        self.assertEqual(snapshot['health'][0]['scope'], self.operation()['scope'])
        self.assertEqual(snapshot['publicSources'][0]['url'], 'https://example.org/careers')
        frozen = copy.deepcopy(snapshot)
        self.data['app']['sourceReviews'][0]['issues'].append('TEST later in-memory modification')
        self.assertEqual(snapshot, frozen)

    def test_snapshot_links_configured_source_and_excludes_other_requests_and_later_checks(self):
        self.save()
        other = copy.deepcopy(self.data['app']['sourceReviews'][0])
        other['id'] = 'test-other-request'
        other['requestId'] = 'different-request'
        later = copy.deepcopy(other)
        later.update(id='test-later', requestId=self.request_id, checkedAt='2026-10-02T11:00:00+00:00')
        self.data['app']['sourceReviews'].extend([other, later])
        snapshot = source_reviews.snapshot(self.data, self.request(), workflow.now(), configuredSources=[
            {'id': 'configured-example', 'company': 'TEST configured', 'url': 'https://example.org/careers'}])
        self.assertEqual(len(snapshot['reviews']), 1)
        self.assertEqual(snapshot['health'][0]['sourceId'], 'configured-example')
        self.assertEqual(snapshot['publicSources'][0]['id'], 'configured-example')

    def test_api_sources_without_configured_url_match_manual_board_urls(self):
        self.save(sourceUrl='https://boards.greenhouse.io/test-company')
        snapshot = source_reviews.snapshot(self.data, self.request(), workflow.now(), configuredSources=[
            {'id': 'test-api', 'company': 'TEST company', 'kind': 'greenhouse', 'board': 'test-company'}])
        self.assertEqual(snapshot['health'][0]['sourceId'], 'test-api')

    def test_partial_later_check_keeps_the_previous_manual_success_and_its_scope(self):
        self.save()
        with patch.object(workflow, 'now', return_value='2026-10-02T12:00:00+00:00'):
            self.save(id='test-later-partial', checkedAt='2026-10-02T11:00:00+00:00',
                      outcome='partial', issues=['TEST changed portal prevents checking page 2'])
            snapshot = source_reviews.snapshot(self.data, self.request(), workflow.now())
        self.assertEqual(snapshot['health'][0]['status'], 'partial')
        self.assertEqual(snapshot['health'][0]['lastSuccessUtc'], '2026-10-02T10:00:00+00:00')
        self.assertEqual(len(snapshot['reviews']), 2)
        self.assertEqual(snapshot['reviews'][0]['scope'], self.operation()['scope'])

    def test_profile_not_confirmed_cannot_add_ordinary_search_work(self):
        self.data['app']['setupComplete'] = False
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'perfil inicial'):
            self.save()
        self.assertEqual(self.data, before)

    def test_discovery_completion_freezes_manual_coverage_without_later_rewriting_it(self):
        self.save(outcome='blocked', issues=['TEST login required for the declared filter'])
        with patch('personalization.public_sources', return_value=[]), workflow.execution_owner('test-browser'):
            self.apply({'kind': 'ui-request-update', 'id': self.request_id, 'status': 'done', 'proof': 'TEST partial search completed with stated access limit'})
        frozen = copy.deepcopy(self.request()['activityResult'])
        self.assertEqual(frozen['health'][0]['status'], 'blocked')
        self.assertEqual(frozen['manualReviews'][0]['proof'], self.operation()['proof'])
        self.data['app']['sourceReviews'].clear()
        self.assertEqual(self.request()['activityResult'], frozen)


if __name__ == '__main__':
    unittest.main()
