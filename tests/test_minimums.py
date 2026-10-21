"""Minimum conditions, honest uncertainty, bulk permissions and reversible archives."""
import copy
import json
import unittest
from workflow_fixtures import WorkflowFixture
import app_context as context
import app_workflow as workflow
import offer_actions
import offer_minimums
import stubbs_jobs as jobs
from stubbs_jobs_core import digest


class MinimumsTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.data['profile']['minimumFixed'] = 35000
        self.data['app']['criteria'] = {'contract': 'Indefinido', 'location': 'España', 'maxTrips': 1}
        self.data['app']['searchContext'] = {'workMode': '100 % remoto', 'currency': 'EUR'}
        self.row['Estado'] = 'Investigar'

    def evidence(self, condition, value, **extra):
        self.apply({'kind': 'evidence', 'id': 'one', 'condition': condition, 'state': value,
                    'proof': 'TEST: dato explícito del anuncio ficticio.',
                    'url': self.row['URL original'], 'at': '2026-10-06T10:00:00+02:00', **extra})

    def test_renaming_the_offer_filter_does_not_rewrite_old_automatic_archives(self):
        self.data['app']['searchContext']['requiredSchedule']='morning'
        self.apply({'kind':'ui-minimum-reconcile','expectedRevision':self.data['revision'],
                    'proof':'TEST: criterio de horario de la persona ficticia'})
        archive=workflow.archived(self.data,'one')
        archive['reason']=archive['reason'].replace('Por solicitar','Por decidir')
        for reason in archive['violations']:
            reason['reason']=reason['reason'].replace('Por solicitar','Por decidir')
        before=copy.deepcopy(archive);history_count=len(self.data['app']['history'])
        self.apply({'kind':'ui-seen','at':workflow.now()})
        self.assertEqual(workflow.archived(self.data,'one'),before)
        self.assertEqual(len(self.data['app']['history']),history_count)

    def test_guarded_repair_restores_only_a_verified_label_drift(self):
        self.data['app']['searchContext']['requiredSchedule']='morning'
        self.apply({'kind':'ui-minimum-reconcile','expectedRevision':self.data['revision'],
                    'proof':'TEST: criterio de horario de la persona ficticia'})
        archive=workflow.archived(self.data,'one')
        archive['reason']=archive['reason'].replace('Por solicitar','Por decidir')
        for reason in archive['violations']:
            reason['reason']=reason['reason'].replace('Por solicitar','Por decidir')
        old=copy.deepcopy(self.data);old.pop('_baseHash',None)
        raw=json.dumps(old,ensure_ascii=False).encode('utf-8');old_hash=digest(raw)
        folder=self.root/'data'/'snapshots';folder.mkdir(parents=True)
        (folder/f'{old_hash}.json').write_bytes(raw)
        current=copy.deepcopy(self.data);current['revision']+=1;current['_baseHash']='TEST-current-hash'
        current['app']['offerArchives']['one']['reason']=archive['reason'].replace('Por decidir','Por solicitar')
        current['app']['offerArchives']['one']['violations'][0]['reason']=archive['violations'][0]['reason'].replace('Por decidir','Por solicitar')
        contact={'id':'TEST-contact','opportunityId':'one','type':'response','selectionStep':'contact',
                 'at':'2026-10-02T10:00:00Z','proof':'TEST: contacto','actor':'Usuario','reportedBy':'user'}
        current['events'].append(contact)
        current['sheets']['Actividad'].append({'Acción':'response'})
        current['app']['history'].append({'id':len(old['app']['history'])+1,'title':'Contacto de selección registrado',
                                           'eventId':'TEST-contact','actor':'Agente','opportunityId':'one'})
        current['app']['history'].append({'id':len(old['app']['history'])+2,'title':'Descartada por requisitos mínimos',
                                           'actor':'Sistema','opportunityId':'one'})
        operation={'kind':'repair-selection-reconciliation','snapshotHash':old_hash,'expectedHash':'TEST-current-hash',
                   'expectedRevision':current['revision'],'eventId':'TEST-contact','proof':'TEST: reparación verificada'}
        jobs.apply_batch(current,{'id':'TEST-repair','operations':[operation]})
        self.assertEqual(current['app']['offerArchives'],old['app']['offerArchives'])
        self.assertEqual(len(current['app']['history']),len(old['app']['history'])+1)
        self.assertEqual(current['app']['history'][-1]['actor'],'Usuario')
        self.assertEqual(current['events'][-1],contact)

    def test_missing_conditions_and_negative_legacy_technical_review_allow_choice(self):
        self.row['Prioridad'] = 'C'
        self.data['app']['fitReviews'] = {'one': {'fingerprint': context.fit_stamp(self.data, self.row),
                                                'apply': False, 'accept': False, 'proof': 'TEST SQL avanzado no acreditado.'}}
        self.assertEqual(jobs.conditions(self.data, self.row)[0], 'Sí, aclarar')
        self.assertIn('select-auto', offer_actions.available(self.data, 'one', workflow))
        self.apply({'kind': 'ui-bulk-action', 'action': 'select-auto', 'targets': [{'id': 'one'}],
                    'expectedRevision': self.data['revision']})
        self.assertEqual(workflow.selection(self.data, 'one')['mode'], 'auto')
        self.assertFalse(any(r['type'] == 'send' for r in self.data['app']['requests']))
        self.assertEqual(self.data['events'], [])

    def test_new_technical_rejection_cannot_be_recorded_as_a_minimum_failure(self):
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError, 'dudas técnicas'):
            self.apply({'kind': 'ui-fit-review', 'opportunityId': 'one',
                        'fingerprint': context.fit_stamp(self.data, self.row),
                        'apply': False, 'accept': False, 'proof': 'TEST SQL avanzado no acreditado.'})
        self.assertEqual(self.data, before)

    def test_new_table_facts_cannot_bypass_minimums_even_when_legacy_checks_are_missing(self):
        for field,value in (('Modalidad','Híbrido'),('Contrato','Temporal')):
            with self.subTest(field=field):
                self.setUp()
                self.apply({'kind':'opportunity','id':'one','values':{field:value},'proof':'TEST categoría explícita del anuncio.'})
                self.assertIsNotNone(workflow.archived(self.data,'one'))
                self.assertNotIn('select-auto',offer_actions.available(self.data,'one',workflow))
        self.setUp();self.row['Modalidad']='Remoto o híbrido, a elegir'
        self.assertTrue(offer_minimums.view(self.data,self.row)['canApply'])
        self.data['app']['searchContext']['workMode']='Fully remote'
        self.data['app']['criteria']['contract']='Permanent'
        self.row['Modalidad']='Hybrid'
        self.assertFalse(offer_minimums.view(self.data,self.row)['canApply'])

    def test_mercantile_contract_cannot_satisfy_a_permanent_only_search(self):
        self.apply({'kind':'opportunity','id':'one','values':{'Contrato':'Contrato mercantil'},
                    'proof':'TEST: anuncio ficticio ofrece contrato mercantil, sin alternativa laboral.'})
        self.assertFalse(offer_minimums.view(self.data,workflow.row_for(self.data,'one'))['canApply'])
        self.assertEqual(workflow.archived(self.data,'one')['source'],'minimums')
        self.assertNotIn('select-auto',offer_actions.available(self.data,'one',workflow))

    def test_permanent_or_mercantile_remains_an_unconfirmed_alternative(self):
        self.row['Contrato']='Indefinido o mercantil'
        self.row['Indefinido']='Sí'  # An earlier check cannot choose the current alternative.
        decision=offer_minimums.view(self.data,self.row)
        self.assertTrue(decision['canApply'])
        self.assertIn('Indefinido',decision['unknowns'])
        self.assertFalse(decision['confirmed'])
        self.assertEqual(offer_minimums.categories('No mercantil','contract'),set())

    def test_explicit_remote_contract_travel_and_salary_failures_archive(self):
        for condition, extra in [('Remoto España', {}), ('Indefinido', {}),
                                 ('Viajes ≤1/mes', {'trips': 2}), ('Fijo ≥32 k€', {'fixed': 34000})]:
            with self.subTest(condition=condition):
                self.setUp()
                self.evidence(condition, 'No', **extra)
                record = workflow.archived(self.data, 'one')
                self.assertEqual(record['source'], 'minimums')
                self.assertTrue(record['reason'])
                self.assertEqual(jobs.conditions(self.data, self.row)[0], 'No')
                self.assertNotIn('select-review', offer_actions.available(self.data, 'one', workflow))
                with self.assertRaises(ValueError):
                    self.apply({'kind': 'ui-select-opportunity', 'opportunityId': 'one',
                                'selected': True, 'mode': 'auto', 'expected': None,'actor':'Usuario'})

    def test_range_crossing_the_minimum_remains_selectable_but_not_confirmed(self):
        self.evidence('Fijo ≥32 k€', 'Pendiente', fixed=30000, fixedMax=40000)
        self.assertEqual(jobs.conditions(self.data, self.row)[:2], ('Sí, aclarar', 'Pendiente'))
        self.assertIsNone(workflow.archived(self.data, 'one'))
        self.evidence('Fijo ≥32 k€', 'No', fixed=30000, fixedMax=34000)
        self.assertIsNotNone(workflow.archived(self.data, 'one'))

    def test_unspecified_total_band_is_not_guessed_as_fixed_pay(self):
        self.row['Banda publicada'] = '30.000–40.000 EUR incluyendo variable'
        self.assertTrue(offer_minimums.view(self.data, self.row)['canApply'])
        self.assertFalse(offer_minimums.view(self.data, self.row)['confirmed'])
        self.data['app']['personalized'] = True
        self.data['app']['searchContext']['currency'] = 'CAD'
        self.row['Fijo mín. confirmado'] = 34000
        self.row['Moneda fijo confirmado'] = 'EUR'
        self.assertTrue(offer_minimums.view(self.data, self.row)['canApply'])

    def test_a_pending_investigation_does_not_block_bulk_choice_or_duplicate_work(self):
        workflow.request(self.data, 'one', 'investigate')
        request_id = self.data['app']['requests'][0]['id']
        self.apply({'kind': 'ui-bulk-action', 'action': 'select-review', 'targets': [{'id': 'one'}],
                    'expectedRevision': self.data['revision']})
        self.assertEqual(len(self.data['app']['requests']), 1)
        self.assertEqual(self.data['app']['requests'][0]['id'], request_id)

    def test_archiving_cancels_future_work_and_correction_never_restores_permissions(self):
        self.apply({'kind': 'ui-select-opportunity', 'opportunityId': 'one', 'selected': True, 'mode': 'auto', 'expected': None,'actor':'Usuario'})
        self.evidence('Remoto España', 'No')
        self.assertIsNone(workflow.selection(self.data, 'one'))
        self.assertTrue(all(r['status'] == 'cancelled' for r in self.data['app']['requests']))
        self.evidence('Remoto España', 'Sí')
        self.assertIsNone(workflow.archived(self.data, 'one'))
        self.assertIsNone(workflow.selection(self.data, 'one'))
        self.assertFalse(any(r['status'] == 'queued' for r in self.data['app']['requests']))

    def test_manual_archive_and_confirmed_submission_are_preserved(self):
        self.apply({'kind': 'ui-bulk-action', 'action': 'archive', 'targets': [{'id': 'one'}],
                    'expectedRevision': self.data['revision']})
        archived = copy.deepcopy(workflow.archived(self.data, 'one'))
        self.evidence('Remoto España', 'No')
        self.evidence('Remoto España', 'Sí')
        self.assertEqual(workflow.archived(self.data, 'one'), archived)
        self.data['app']['offerArchives'].pop('one')
        self.data['events'].append({'type': 'sent', 'opportunityId': 'one', 'at': '2026-10-01'})
        self.evidence('Remoto España', 'No')
        self.assertIsNone(workflow.archived(self.data, 'one'))
        self.assertEqual(jobs.conditions(self.data, self.row)[0], 'Ya enviada')

    def test_explicit_archiving_of_an_automatic_archive_keeps_the_human_decision(self):
        self.evidence('Remoto España', 'No')
        self.assertEqual(workflow.archived(self.data, 'one')['source'], 'minimums')
        self.apply({'kind': 'ui-bulk-action', 'action': 'archive', 'targets': [{'id': 'one'}],
                    'expectedRevision': self.data['revision'], 'actor': 'Usuario'})
        self.evidence('Remoto España', 'Sí')
        self.assertEqual(workflow.archived(self.data, 'one')['actor'], 'Usuario')
        self.assertNotIn('source', workflow.archived(self.data, 'one'))

    def test_changing_minimum_reclassifies_and_does_not_restore_a_choice(self):
        self.evidence('Fijo ≥32 k€', 'No', fixed=34000)
        self.apply({'kind': 'ui-preferences', 'values': {'minimumFixed': 33000}, 'expected': {'minimumFixed': 35000}})
        self.assertIsNone(workflow.archived(self.data, 'one'))
        self.assertIsNone(workflow.selection(self.data, 'one'))
        self.assertEqual(jobs.conditions(self.data, self.row)[0], 'Sí, aclarar')

    def test_bands_and_trip_frequency_change_material_identity(self):
        before = workflow.stamp(self.data, 'one')
        self.evidence('Fijo ≥32 k€', 'Pendiente', fixed=30000, fixedMax=40000)
        self.assertNotEqual(before, workflow.stamp(self.data, 'one'))
        current = workflow.stamp(self.data, 'one')
        self.evidence('Viajes ≤1/mes', 'Sí', trips=1)
        self.assertNotEqual(current, workflow.stamp(self.data, 'one'))

    def test_unknowns_do_not_skip_review_of_current_criteria_before_delivery(self):
        self.assertIn('Comprobar la oferta con los criterios actuales', workflow.readiness(self.data, 'one'))
        self.apply({'kind': 'ui-fit-review', 'opportunityId': 'one', 'fingerprint': context.fit_stamp(self.data, self.row),
                    'apply': True, 'accept': False, 'proof': 'TEST: mínimos desconocidos, capacidades por contrastar.'})
        self.assertNotIn('Comprobar la oferta con los criterios actuales', workflow.readiness(self.data, 'one'))
        self.assertTrue(workflow.readiness(self.data, 'one'))

    def test_atomic_batch_does_not_leave_an_archive_after_a_later_error(self):
        before = copy.deepcopy(self.data)
        with self.assertRaises(ValueError):
            jobs.apply_batch(self.data, {'id': 'invalid', 'operations': [
                {'kind': 'evidence', 'id': 'one', 'condition': 'Remoto España', 'state': 'No',
                 'proof': 'TEST híbrida.', 'url': self.row['URL original'], 'at': '2026-10-06T10:00:00+02:00'},
                {'kind': 'unknown-invalid'}]})
        self.assertEqual(self.data, before)

    def test_explicit_reclassification_rejects_a_stale_snapshot(self):
        before = copy.deepcopy(self.data)
        with self.assertRaises(workflow.Conflict):
            self.apply({'kind': 'ui-minimum-reconcile', 'expectedRevision': self.data['revision'] + 1,
                        'proof': 'TEST: actualizar únicamente esta instantánea.'})
        self.assertEqual(self.data, before)

    def test_minimum_archive_preserves_started_delivery_and_its_owner(self):
        request = {'id': 'started', 'type': 'send', 'status': 'running', 'opportunityId': 'one',
                   'executionId': 'OTHER-OWNER', 'packageId': 'old', 'startedAt': '2026-10-01T10:00:00+02:00'}
        self.data['app']['requests'].append(request)
        self.row['Remoto España'] = 'No'
        before = copy.deepcopy(request)
        # The policy archives future work; it does not pretend to stop an external effect.
        self.apply({'kind': 'ui-minimum-reconcile', 'expectedRevision': self.data['revision'],
                    'proof': 'TEST: hecho ya registrado, comprobar el envío iniciado.'})
        self.assertIsNotNone(workflow.archived(self.data, 'one'))
        self.assertEqual(self.data['app']['requests'][0], before)

    def test_view_is_pure_even_when_a_minimum_failure_would_archive(self):
        self.row['Remoto España'] = 'No'
        before = copy.deepcopy(self.data)
        self.assertFalse(offer_minimums.view(self.data, self.row)['canApply'])
        self.assertEqual(self.data, before)

    def test_plain_lists_of_modalities_are_alternatives_but_prose_is_not(self):
        cats = offer_minimums.categories
        self.assertEqual(cats('Remoto, Híbrido, Presencial', 'mode', preference=True), {'remote', 'hybrid', 'onsite'})
        self.assertEqual(cats('Remoto, híbrido y presencial', 'mode'), {'remote', 'hybrid', 'onsite'})
        self.assertEqual(cats('Remote and hybrid', 'mode'), {'remote', 'hybrid'})
        # Descriptive prose between two labels is still not an alternative.
        self.assertEqual(cats('Híbrido, 3 días presencial', 'mode'), {'hybrid'})
        self.assertEqual(cats('Remoto, con viajes al centro presencial', 'mode'), {'remote'})

    def test_partial_remote_wording_is_hybrid_but_keeps_real_alternatives(self):
        cats = offer_minimums.categories
        for text in ('Semi-remoto', 'Semipresencial', 'Teletrabajo parcial', 'Remoto parcial', 'Parcialmente remoto',
                     'Remoto 2 días a la semana', 'Teletrabajo 3 días', 'Remoto con 2 días presenciales',
                     'Remote, 3 days in the office', 'Remoto (1 día a la semana en oficina)'):
            with self.subTest(text=text):
                self.assertEqual(cats(text, 'mode'), {'hybrid'})
        # Occasional monthly or yearly visits remain a travel question, not hybrid work.
        for text in ('Remoto, 1 día presencial al mes', 'Remote 4 days a year onsite', 'Remoto con visitas puntuales'):
            with self.subTest(text=text):
                self.assertEqual(cats(text, 'mode'), {'remote'})
        self.assertEqual(cats('Remoto o semipresencial', 'mode'), {'remote', 'hybrid'})
        self.assertEqual(cats('Presenciales', 'mode'), {'onsite'})
        self.row['Modalidad'] = 'Teletrabajo parcial'
        decision = offer_minimums.view(self.data, self.row)
        self.assertFalse(decision['canApply'])
        self.assertEqual(decision['violations'][0]['key'], 'Remoto España')
        self.row['Modalidad'] = 'Remoto o semipresencial'
        self.assertTrue(offer_minimums.view(self.data, self.row)['canApply'])

    def setup_places(self, accepted='Villa Norte; Puerto Sur'):
        self.data['app']['searchContext'] = {'workMode': 'Remoto, Híbrido, Presencial', 'currency': 'EUR',
                                             'onsiteLocations': accepted}

    def test_hybrid_and_onsite_offers_must_be_in_accepted_zones(self):
        self.setup_places()
        for mode in ('Híbrido', 'Presencial'):
            with self.subTest(mode=mode):
                self.row['Modalidad'] = mode
                self.row['Ubicación'] = 'Villa Norte (Cádiz)'
                self.assertTrue(offer_minimums.view(self.data, self.row)['canApply'])
                self.row['Ubicación'] = 'Madrid'
                decision = offer_minimums.view(self.data, self.row)
                self.assertFalse(decision['canApply'])
                self.assertIn('Madrid', decision['violations'][0]['reason'])
                self.assertIn('Villa Norte', decision['violations'][0]['reason'])

    def test_hybrid_without_recorded_location_is_not_eligible_but_remote_is_unaffected(self):
        self.setup_places()
        self.row['Modalidad'] = 'Híbrido'
        self.row.pop('Ubicación', None)
        decision = offer_minimums.view(self.data, self.row)
        self.assertFalse(decision['canApply'])
        self.assertIn('no consta su ubicación', decision['violations'][0]['reason'])
        for mode in ('Remoto', 'Remoto o híbrido, a elegir', ''):
            with self.subTest(mode=mode):
                self.row['Modalidad'] = mode
                self.row['Ubicación'] = 'Madrid'
                self.assertTrue(offer_minimums.view(self.data, self.row)['canApply'])

    def test_without_configured_zones_nothing_changes(self):
        self.data['app']['searchContext'] = {'workMode': 'Remoto, Híbrido, Presencial', 'currency': 'EUR'}
        self.row['Modalidad'] = 'Híbrido'
        self.row['Ubicación'] = 'Madrid'
        self.assertTrue(offer_minimums.view(self.data, self.row)['canApply'])

    def test_zone_change_recovers_automatic_archive_and_keeps_manual_ones(self):
        self.setup_places()
        self.row['Modalidad'] = 'Híbrido'
        self.row['Ubicación'] = 'Madrid'
        self.apply({'kind': 'ui-minimum-reconcile', 'expectedRevision': self.data['revision'],
                    'proof': 'TEST: aplicar zonas aceptadas.'})
        self.assertIsNotNone(workflow.archived(self.data, 'one'))
        self.apply({'kind': 'ui-search-context', 'values': {'onsiteLocations': 'Madrid'},
                    'expected': {'onsiteLocations': self.data['app']['searchContext']['onsiteLocations']}})
        self.apply({'kind': 'ui-minimum-reconcile', 'expectedRevision': self.data['revision'],
                    'proof': 'TEST: zona ampliada.'})
        self.assertIsNone(workflow.archived(self.data, 'one'))

    def test_location_is_an_offer_fact_that_needs_proof(self):
        self.setup_places()
        with self.assertRaises(ValueError):
            self.apply({'kind': 'opportunity', 'id': 'one', 'values': {'Ubicación': 'Villa Norte'}})
        self.apply({'kind': 'opportunity', 'id': 'one', 'values': {'Ubicación': 'Villa Norte'},
                    'proof': 'TEST ubicación explícita del anuncio.'})
        stored = next(r for r in self.data['sheets']['Oportunidades'] if r['ID'] == 'one')
        self.assertEqual(stored['Ubicación'], 'Villa Norte')


class NeutralConditionNameTests(WorkflowFixture, unittest.TestCase):
    """Any country's agent can record and read conditions without the first edition's names."""
    def setUp(self):
        super().setUp()
        self.data['profile']['minimumFixed'] = 35000
        self.data['app']['criteria'] = {'contract': 'Indefinido', 'location': 'España', 'maxTrips': 1}
        self.data['app']['searchContext'] = {'workMode': '100 % remoto', 'currency': 'EUR'}
        self.row['Estado'] = 'Investigar'
        self.data.update(createdAt=jobs.now(), updatedAt=jobs.now())

    def stored(self):
        return next(r for r in self.data['sheets']['Oportunidades'] if r['ID'] == 'one')

    def test_neutral_name_records_the_same_condition_as_the_stored_key(self):
        MinimumsTests.evidence(self, 'Cumple salario mínimo', 'No', fixed=30000, fixedMax=34000)
        self.assertEqual(self.stored()['Fijo ≥32 k€'], 'No')
        self.assertEqual(self.stored()['Fijo mín. confirmado'], 30000)
        self.assertEqual(self.data['sheets']['Evidencias'][-1]['Condición'], 'Fijo ≥32 k€')
        self.assertEqual(offer_minimums.current_numbers(self.data, self.stored())['Fijo máx. confirmado'], 34000)
        MinimumsTests.evidence(self, 'Cumple viajes', 'Sí', trips=0)
        self.assertEqual(self.stored()['Viajes ≤1/mes'], 'Sí')
        with self.assertRaises(ValueError):
            MinimumsTests.evidence(self, 'Cumple otra cosa', 'Sí')

    def test_agent_views_show_neutral_condition_names(self):
        import agent_context
        from unittest.mock import patch
        import personalization, stubbs_jobs_app
        (self.root/'config').mkdir()
        (self.root/'config/sources.json').write_text('[]', encoding='utf-8')
        for module in (agent_context, stubbs_jobs_app, personalization):
            p = patch.object(module, 'ROOT', self.root); p.start(); self.addCleanup(p.stop)
        MinimumsTests.evidence(self, 'Fijo ≥32 k€', 'No', fixed=30000, fixedMax=34000)
        listed = agent_context.view(self.data, offers='all')['opportunities'][0]['minimums']
        self.assertIn('Cumple salario mínimo', [v['key'] for v in listed['violations']])
        case = agent_context.view(self.data, case='one')['case']
        self.assertIn('Cumple salario mínimo', case['conditions'])
        self.assertNotIn('Fijo ≥32 k€', case['conditions'])
        self.assertEqual(case['evidence'][-1]['Condición'], 'Cumple salario mínimo')
        self.assertEqual(self.stored()['Fijo ≥32 k€'], 'No')
