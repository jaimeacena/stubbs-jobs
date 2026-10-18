"""The person's own send, with fictional offers and PDFs: no portal, form or real data."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import unittest

from workflow_fixtures import WorkflowFixture
import agent_runner
import app_workflow as workflow
import application_lifecycle
import cv_usage
import request_workflow
import stubbs_jobs
import stubbs_jobs_app as server
import user_submission
from stubbs_jobs_core import digest, now


def moment(minutes=-30):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).astimezone().isoformat(timespec='seconds')


class UserSentTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for name, result in (('read_state', {'status': 'idle'}), ('view', {'status': 'idle'})):
            replacement = patch.object(agent_runner, name, return_value=result)
            replacement.start()
            self.addCleanup(replacement.stop)
        (self.root / 'outputs/cv').mkdir()
        (self.root / 'outputs/cv/general.pdf').write_bytes(b'%PDF-test-general')
        self.library = {'id': digest(b'%PDF-test-general'), 'name': 'general.pdf', 'path': 'outputs/cv/general.pdf'}
        workflow.state(self.data)['cvLibrary'] = [self.library]

    @property
    def live(self):
        return workflow.row_for(self.data, 'one')

    def person(self, operation):
        with workflow.interface_writer():
            self.apply({**operation, 'actor': 'Usuario'})

    def report(self, **values):
        operation = {'kind': 'ui-user-sent', 'opportunityId': 'one', 'sentAt': moment(),
                     'cv': {'source': 'library', 'path': self.library['path'], 'fingerprint': self.library['id']},
                     'duplicatesChecked': True,
                     'expected': user_submission.view(self.data, self.live, workflow)['conciliation']}
        operation.update(values)
        return operation

    def sends(self):
        return [r for r in workflow.state(self.data)['requests'] if r['type'] == 'send']

    def approved(self):
        self.review()
        self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})
        return self.sends()[-1]

    def blocked(self):
        request = self.approved()
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST inicio'})
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'blocked', 'proof': 'TEST CAPTCHA del portal',
                        'summary': 'El portal pide resolver un CAPTCHA.', 'need': 'access'})
        return request

    def test_records_the_persons_send_without_a_receipt_or_agent_delivery(self):
        self.person(self.report(note='Referencia TEST-123'))
        event = next(e for e in self.data['events'] if e['type'] == 'sent')
        self.assertEqual((event['reportedBy'], event['actor'], event['note'], event['cvSource']),
                         ('user', 'Usuario', 'Referencia TEST-123', 'library'))
        for absent in ('packageId', 'confirmation', 'authorization', 'recovered'):
            self.assertNotIn(absent, event)
        self.assertEqual(event['cvHash'], self.library['id'])
        self.assertEqual(self.live['Estado'], 'Enviada')
        self.assertEqual(self.live['CV usado'], self.library['path'])
        history = workflow.state(self.data)['history'][-1]
        self.assertEqual((history['title'], history['actor'], history['eventId'], history['at']),
                         ('Solicitud enviada', 'Usuario', event['id'], event['at']))
        self.assertEqual(self.data['sheets']['Actividad'][-1]['Acción'], 'sent')
        undo = [u for u in workflow.state(self.data)['undo'] if u['kind'] == 'user-sent']
        self.assertTrue(undo and workflow.undo_available(self.data, undo[-1]))
        self.assertIsNone(user_submission.view(self.data, self.live, workflow))
        view = application_lifecycle.history_view(self.data, {'one'})
        self.assertEqual(next(h for h in view if h.get('eventId') == event['id'])['activity']['reportedBy'], 'user')
        usage = cv_usage.enrich(self.data, [{**self.library}], self.root, workflow.package_issue)[0]['usage']
        self.assertEqual((usage[0]['kind'], usage[0]['reportedBy']), ('sent', 'user'))

    def test_cancels_the_queued_send_and_retires_its_permission_using_the_package_cv(self):
        request = self.approved()
        package = next(p for p in workflow.state(self.data)['packages'] if p['id'] == request['packageId'])
        report = user_submission.view(self.data, self.live, workflow)
        self.assertEqual((report['packageCv']['packageId'], report['pendingSends']), (package['id'], 1))
        self.person(self.report(cv={'source': 'package', 'packageId': package['id']}))
        self.assertEqual(self.sends()[0]['status'], 'cancelled')
        package = next(p for p in workflow.state(self.data)['packages'] if p['id'] == request['packageId'])
        self.assertTrue(package['revokedAt'])
        event = next(e for e in self.data['events'] if e['type'] == 'sent')
        self.assertEqual((event['cv'], event['cvHash'], event['cvPackageId']),
                         ('data/packages/' + package['id'] + '/cv.pdf', package['payload']['cvHash'], package['id']))
        self.assertEqual(event['conciliation']['cancelledRequestIds'], [request['id']])
        self.assertEqual(event['conciliation']['revokedPackageIds'], [package['id']])
        with self.assertRaisesRegex(ValueError, 'ya está enviada|ya enviada'):
            self.apply({'kind': 'ui-approve', 'opportunityId': 'one', 'fingerprint': workflow.stamp(self.data, 'one')})

    def test_a_blocked_portal_attempt_is_closed_without_inventing_its_result(self):
        request = self.blocked()
        report = user_submission.view(self.data, self.live, workflow)
        self.assertEqual(report['uncertainAttempts'], 1)
        self.person(self.report())
        live = self.sends()[0]
        self.assertEqual(live['status'], 'cancelled')
        self.assertNotIn('deliveryCheck', live)
        self.assertNotIn('need', live)
        event = next(e for e in self.data['events'] if e['type'] == 'sent')
        self.assertEqual(event['conciliation']['uncertainAttemptIds'], [request['id']])
        self.assertEqual(request_workflow.unresolved_attempts(self.data, 'one'), [])
        # The agent cannot add its own receipt or retry the form afterwards.
        with self.assertRaisesRegex(ValueError, 'ya tiene un envío registrado'):
            self.apply({'kind': 'ui-delivery-check', 'id': request['id'], 'expected': live['updatedAt'],
                        'packageId': request['packageId'], 'recipient': workflow.draft(self.data, 'one')['recipient'],
                        'outcome': 'sent', 'proof': 'TEST', 'sentAt': moment(-5), 'confirmation': 'TEST'})

    def test_a_running_send_or_an_agent_actor_cannot_record_it(self):
        request = self.approved()
        with workflow.execution_owner('original'):
            self.apply({'kind': 'ui-request-update', 'id': request['id'], 'status': 'running', 'proof': 'TEST inicio'})
        self.assertFalse(user_submission.view(self.data, self.live, workflow)['available'])
        report = self.report()
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'El agente está enviando'):
            self.person(report)
        self.assertEqual(self.data, before)
        with self.assertRaisesRegex(ValueError, 'Solo la persona'), workflow.execution_owner('agent'):
            self.apply({**report, 'actor': 'Usuario'})
        self.assertEqual(self.data, before)

    def test_requires_real_time_duplicate_check_known_cv_and_current_conciliation(self):
        base = self.report()
        before = copy.deepcopy(self.data)
        for values, message in (({'duplicatesChecked': False}, 'única solicitud'),
                                ({'sentAt': moment(60)}, 'sin fechas futuras'),
                                ({'sentAt': '2026-10-01T10:00:00'}, 'zona horaria'),
                                ({'note': 'x' * 2001}, '2000'),
                                ({'cv': {'source': 'library', 'path': 'outputs/cv/general.pdf', 'fingerprint': 'f' * 64}}, 'cambiado'),
                                ({'cv': {'source': 'library', 'path': 'outputs/otro.pdf', 'fingerprint': 'f' * 64}}, 'Currículums'),
                                ({'cv': {'source': 'upload', 'path': 'x.pdf'}}, 'CV que enviaste')):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, message):
                self.person({**base, **values})
            self.assertEqual(self.data, before)
        stale = self.report()
        self.approved()
        with self.assertRaises(workflow.Conflict):
            self.person(stale)

    def test_an_earlier_application_needs_an_explicit_new_one(self):
        self.data['historicalApplications'].append({'id': 'old-1', 'company': 'Example', 'title': 'BI Developer',
            'url': self.live['URL original'], 'state': 'Enviada', 'proof': 'TEST historial'})
        with self.assertRaisesRegex(ValueError, 'candidatura anterior'):
            self.person(self.report())
        self.person(self.report(reapplication=True))
        event = next(e for e in self.data['events'] if e['type'] == 'sent')
        self.assertEqual((event['reapplication'], event['conciliation']['historicalIds']), (True, ['old-1']))

    def test_undo_withdraws_the_record_without_restoring_sends_or_permissions(self):
        request = self.approved()
        before_state = self.live['Estado']
        self.person(self.report())
        item = next(u for u in workflow.state(self.data)['undo'] if u['kind'] == 'user-sent')
        self.person({'kind': 'ui-undo', 'id': item['id']})
        self.assertFalse(any(e['type'] == 'sent' for e in self.data['events']))
        retracted = workflow.state(self.data)['retractedEvents'][-1]
        self.assertEqual((retracted['reportedBy'], retracted['retractedBy']), ('user', 'Usuario'))
        self.assertEqual(self.live['Estado'], before_state)
        self.assertIsNone(self.live['Fecha candidatura'])
        self.assertEqual(self.sends()[0]['status'], 'cancelled')
        package = next(p for p in workflow.state(self.data)['packages'] if p['id'] == request['packageId'])
        self.assertTrue(package['revokedAt'])
        view = application_lifecycle.history_view(self.data, {'one'})
        self.assertTrue(next(h for h in view if h.get('eventId') == retracted['id'])['activity']['retracted'])
        self.assertTrue(user_submission.view(self.data, self.live, workflow)['available'])

    def test_undo_is_unavailable_after_later_news(self):
        self.person(self.report())
        item = next(u for u in workflow.state(self.data)['undo'] if u['kind'] == 'user-sent')
        self.apply({'kind': 'ui-followup-check', 'opportunityId': 'one', 'outcome': 'waiting', 'observedAt': moment(-1),
                    'sourceUrl': 'https://example.org/account', 'vacancyUrl': self.live['URL original'], 'proof': 'TEST sin novedades'})
        self.assertFalse(workflow.undo_available(self.data, item))
        with self.assertRaises(ValueError):
            self.person({'kind': 'ui-undo', 'id': item['id']})

    def test_closed_offers_and_existing_sends_are_refused(self):
        repeated = self.report()
        self.person(repeated)
        with self.assertRaisesRegex(ValueError, 'ya consta como enviada'):
            self.person(repeated)
        with self.assertRaisesRegex(ValueError, 'Candidatura ya enviada'):
            self.apply({'kind': 'event', 'event': {'id': 'agent-sent', 'type': 'sent', 'opportunityId': 'one',
                        'at': moment(-1), 'proof': 'TEST', 'packageId': 'x'}})

    def test_the_detail_state_offers_it_and_the_server_accepts_only_the_user_writer(self):
        self.data['updatedAt'] = now()
        with patch.object(server, 'ROOT', self.root):
            row = server.build_state(self.data, include_export=False, include_instructions=False)['opportunities'][0]
        self.assertTrue(row['selfReport']['available'])
        self.assertEqual(row['selfReport']['conciliation'], self.report()['expected'])
        self.person(self.report())
        with patch.object(server, 'ROOT', self.root):
            row = server.build_state(self.data, include_export=False, include_instructions=False)['opportunities'][0]
        self.assertIsNone(row['selfReport'])
        self.assertEqual((row['sent']['reportedBy'], row['sentMaterial']['reportedBy']), ('user', 'user'))
        self.assertTrue(row['cvUrl'])
        source = Path(server.__file__).read_text(encoding='utf-8')
        self.assertIn("'ui-user-sent'", source)


if __name__ == '__main__':
    unittest.main()
