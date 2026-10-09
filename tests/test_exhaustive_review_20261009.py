"""Adversarial writer regressions, using fictional records and isolated files."""
import copy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import app_workflow as workflow
import offer_minimums
import personalization
import search_profiles
import stubbs_jobs
import stubbs_jobs_app as server


class EvidenceChronologyTests(WorkflowFixture, unittest.TestCase):
    def evidence(self, at, state, **values):
        self.apply({'kind': 'evidence', 'id': 'one', 'condition': 'Fijo ≥32 k€',
                    'state': state, 'at': at, 'url': self.row['URL original'],
                    'proof': 'TEST: condición observada a las ' + at, **values})

    def test_earlier_check_on_the_same_day_does_not_replace_later_salary(self):
        self.evidence('2026-10-08T18:00:00+02:00', 'No', fixed=25000)
        newer = copy.deepcopy(self.data['sheets']['Evidencias'][-1])
        self.evidence('2026-10-08T09:00:00+02:00', 'Sí', fixed=40000)
        row = stubbs_jobs.get_op(self.data, 'one')
        self.assertEqual(row['Fijo ≥32 k€'], 'No')
        self.assertEqual(row['Fijo mín. confirmado'], 25000)
        self.assertEqual(offer_minimums.latest_evidence(self.data, row, 'Fijo ≥32 k€'), newer)
        self.assertFalse(offer_minimums.view(self.data, row)['canApply'])
        self.assertEqual(len(self.data['sheets']['Evidencias']), 2)

    def test_offsets_are_compared_as_real_instants_across_calendar_days(self):
        self.evidence('2026-10-08T23:30:00Z', 'No', fixed=25000)
        self.evidence('2026-10-09T00:05:00+02:00', 'Sí', fixed=40000)
        row = stubbs_jobs.get_op(self.data, 'one')
        self.assertEqual(row['Fijo ≥32 k€'], 'No')
        self.assertFalse(offer_minimums.view(self.data, row)['canApply'])

    def test_new_evidence_keeps_the_exact_observation_time(self):
        at = '2026-10-08T18:00:00+02:00'
        self.evidence(at, 'Sí', fixed=40000)
        self.assertEqual(self.data['sheets']['Evidencias'][-1].get('observedAt'), at)

    def test_acceptance_projection_uses_the_same_exact_chronology(self):
        for condition in ('Remoto España', 'Indefinido', 'Viajes ≤1/mes'):
            self.apply({'kind': 'evidence', 'id': 'one', 'condition': condition, 'state': 'Sí',
                        'at': '2026-10-08T16:00:00Z', 'url': self.row['URL original'], 'proof': 'TEST'})
        self.evidence('2026-10-08T18:00:00Z', 'Sí', fixed=40000)
        self.evidence('2026-10-08T09:00:00Z', 'No', fixed=25000)
        row = stubbs_jobs.get_op(self.data, 'one')
        row['Vigencia'] = 'Vacante confirmada'
        self.assertTrue(offer_minimums.view(self.data, row)['confirmed'])
        self.assertEqual(stubbs_jobs.conditions(self.data, row), ('Sí, aclarar', 'Sí', True))

    def test_legacy_batches_recover_hours_without_rewriting_the_records(self):
        self.evidence('2026-10-08T18:00:00+02:00', 'No', fixed=25000)
        self.evidence('2026-10-08T09:00:00+02:00', 'Sí', fixed=40000)
        for record in self.data['sheets']['Evidencias']:
            record.pop('observedAt')
        before = copy.deepcopy(self.data)
        row = stubbs_jobs.get_op(self.data, 'one')
        self.assertEqual(offer_minimums.latest_evidence(self.data, row, 'Fijo ≥32 k€')['Estado'], 'No')
        self.assertEqual(self.data, before)

    def test_legacy_condition_indicators_cannot_override_the_newest_proof(self):
        for condition in ('Indefinido', 'Fijo ≥32 k€'):
            with self.subTest(condition=condition):
                self.apply({'kind': 'evidence', 'id': 'one', 'condition': condition, 'state': 'No',
                            'at': '2026-10-08T18:00:00Z', 'url': self.row['URL original'], 'proof': 'TEST actual'})
                self.apply({'kind': 'evidence', 'id': 'one', 'condition': condition, 'state': 'Sí',
                            'at': '2026-10-08T09:00:00Z', 'url': self.row['URL original'], 'proof': 'TEST anterior'})
                for record in self.data['sheets']['Evidencias']:
                    record.pop('observedAt', None)
                    record.pop('numericValues', None)
                row = stubbs_jobs.get_op(self.data, 'one')
                row[condition] = 'Sí'  # Legacy writer kept the last arrival, not the newest observation.
                self.data['updatedAt'] = '2026-10-09T08:00:00Z'
                before = copy.deepcopy(self.data)
                decision = offer_minimums.view(self.data, row)
                self.assertIn(condition, [item['key'] for item in decision['violations']])
                exported = stubbs_jobs.view(self.data)['sheets']['Oportunidades'][0]
                self.assertEqual(exported[condition], 'No')
                with patch.object(server, 'ROOT', self.root), patch.object(server, 'DATA', self.root / 'data'), \
                        patch.object(server.personalization, 'public_sources', return_value=[]):
                    shown = server.build_state(copy.deepcopy(self.data), include_export=False,
                                               include_instructions=False, execution={'status': 'idle', 'available': False})
                self.assertEqual(shown['opportunities'][0]['conditions'][condition], 'No')
                self.assertEqual(self.data, before)

    def test_ambiguous_legacy_batches_do_not_invent_an_observation_hour(self):
        self.evidence('2026-10-08T18:00:00+02:00', 'No', fixed=25000)
        record = self.data['sheets']['Evidencias'][-1]
        record.pop('observedAt')
        operation = copy.deepcopy(self.data['changes'][-1]['operations'][0])
        operation['at'] = '2026-10-08T09:00:00+02:00'
        self.data['changes'].append({'operations': [operation]})
        self.assertIsNone(offer_minimums.evidence_times(self.data)[id(record)])

    def test_missing_timezone_future_dates_and_invalid_source_are_atomic_errors(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        for at, url in [('2026-10-08T18:00:00', self.row['URL original']),
                        (future, self.row['URL original']),
                        ('2026-10-08T18:00:00Z', 'not a source')]:
            with self.subTest(at=at, url=url):
                before = copy.deepcopy(self.data)
                with self.assertRaises(ValueError):
                    self.apply({'kind': 'evidence', 'id': 'one', 'condition': 'Fijo ≥32 k€',
                                'state': 'Sí', 'at': at, 'url': url, 'proof': 'TEST', 'fixed': 40000})
                self.assertEqual(self.data, before)


class IncompleteSearchProfileTests(WorkflowFixture, unittest.TestCase):
    def test_saved_strategy_can_clear_roles_but_cannot_start_a_search(self):
        app = workflow.state(self.data)
        app.update(setupComplete=True, searchContext={'targetRoles': 'BI Developer', 'currency': 'EUR'})
        search_profiles.migrate(self.data)
        self.apply({'kind': 'ui-profile-section', 'section': 'search',
                    'searchProfileId': search_profiles.LEGACY_ID,
                    'values': {'targetRoles': ''}, 'expected': {'targetRoles': 'BI Developer'}})
        self.assertEqual(personalization.context(self.data)['targetRoles'], '')
        self.assertFalse(workflow.state(self.data)['requests'])
        before = copy.deepcopy(self.data)
        with self.assertRaises(ValueError):
            self.apply({'kind': 'ui-request', 'type': 'discovery',
                        'searchProfileId': search_profiles.LEGACY_ID})
        self.assertEqual(self.data, before)


class BlockedTaskContractTests(WorkflowFixture, unittest.TestCase):
    def start(self):
        self.apply({'kind': 'ui-request', 'opportunityId': 'one', 'type': 'investigate'})
        request = workflow.state(self.data)['requests'][-1]
        self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST start'})
        return request['id']

    def test_block_requires_explanation_and_named_need_without_losing_owner(self):
        with patch('agent_runner.read_state', return_value={'status': 'idle'}), \
                patch('agent_runner.view', return_value={'status': 'idle'}), workflow.execution_owner('TEST-owner'):
            identifier = self.start()
            started = copy.deepcopy(self.data)
            for fields in ({}, {'summary': 'TEST access'}, {'need': 'access'},
                           {'summary': '   ', 'need': 'access'}):
                with self.subTest(fields=fields):
                    self.data = copy.deepcopy(started)
                    before = copy.deepcopy(self.data)
                    with self.assertRaises(ValueError):
                        self.apply({'kind': 'ui-request-update', 'id': identifier,
                                    'status': 'blocked', 'proof': 'TEST detailed result', **fields})
                    self.assertEqual(self.data, before)
            self.apply({'kind': 'ui-request-update', 'id': identifier, 'status': 'blocked',
                        'proof': 'TEST portal unavailable', 'summary': '  TEST inicia sesión  ', 'need': 'access'})
            request = workflow.state(self.data)['requests'][-1]
            self.assertEqual(request['summary'], 'TEST inicia sesión')
            self.assertEqual(request['need'], 'access')
            self.assertEqual(request['executionId'], 'TEST-owner')
