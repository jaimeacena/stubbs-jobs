"""Synthetic regressions for the critical review of 6 October; no live writes."""
import copy
import unittest

from workflow_fixtures import WorkflowFixture
import app_workflow as workflow
import app_context as context
import offer_minimums
import stubbs_jobs as jobs


class ReviewCorrectionsTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.data['profile']['minimumFixed'] = 35000
        self.data['app']['criteria'] = {'contract':'Indefinido', 'location':'España', 'maxTrips':1}
        self.data['app']['searchContext'] = {'workMode':'100 % remoto', 'currency':'EUR'}
        self.row['Estado'] = 'Investigar'

    def evidence(self, condition, state, **values):
        self.apply({'kind':'evidence', 'id':'one', 'condition':condition, 'state':state,
                    'proof':'TEST: observación ficticia '+str(self.index),
                    'url':'https://example.org/jobs/123-role', 'at':'2026-10-06T10:00:00+02:00', **values})

    def test_new_observation_retires_old_numbers_in_both_directions_and_uncertain_states(self):
        for personalized in (False, True):
            for condition, field, good, bad in (
                ('Fijo ≥32 k€','fixed',40000,30000), ('Viajes ≤1/mes','trips',1,2)):
                for old_state, value, new_state in (
                    ('Sí',good,'No'), ('No',bad,'Sí'), ('No',bad,'Pendiente'), ('No',bad,'Contradicción')):
                    with self.subTest(personalized=personalized,condition=condition,new_state=new_state):
                        self.setUp()
                        self.data['app'].update(personalized=personalized,setupComplete=True)
                        self.evidence(condition,old_state,**{field:value},**({'currency':'EUR'} if field=='fixed' else {}))
                        first = copy.deepcopy(self.data['sheets']['Evidencias'][-1])
                        self.evidence(condition,new_state)
                        row = jobs.get_op(self.data,'one')
                        decision = offer_minimums.view(self.data,row)
                        self.assertEqual(decision['canApply'],new_state!='No')
                        self.assertEqual(bool(workflow.archived(self.data,'one')),new_state=='No')
                        self.assertEqual(self.data['sheets']['Evidencias'][0],first)
                        self.assertEqual(first['numericValues'][field],value)
                        self.assertEqual(self.data['changes'][0]['operations'][0][field],value)
                        self.assertIsNone(row['Fijo mín. confirmado' if field=='fixed' else 'Viajes mín. al mes'])
                        self.assertFalse((workflow.selection(self.data,'one') or {}).get('selected'))
                        self.assertFalse(self.data['app']['packages'])
                        self.assertFalse(self.data['events'])

    def test_salary_band_and_currency_are_replaced_together(self):
        self.evidence('Fijo ≥32 k€','Pendiente',fixed=30000,fixedMax=40000,currency='EUR')
        self.evidence('Fijo ≥32 k€','No')
        row=jobs.get_op(self.data,'one')
        for key in ('Fijo mín. confirmado','Fijo máx. confirmado','Moneda fijo confirmado'):
            self.assertIsNone(row[key])
        self.assertFalse(offer_minimums.view(self.data,row)['canApply'])

    def test_replacement_suspends_queued_permission_and_preserves_package_files(self):
        self.evidence('Fijo ≥32 k€','Sí',fixed=40000)
        self.apply({'kind':'ui-fit-review','opportunityId':'one','fingerprint':context.fit_stamp(self.data,jobs.get_op(self.data,'one')),
                    'apply':True,'accept':False,'proof':'TEST mínimos actuales comprobados'})
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':workflow.stamp(self.data,'one')})
        package=copy.deepcopy(self.data['app']['packages'][-1])
        files={p:p.read_bytes() for p in (self.root/'data/packages').rglob('*') if p.is_file()}
        self.evidence('Fijo ≥32 k€','No')
        self.assertEqual(self.data['app']['requests'][-1]['status'],'cancelled')
        self.assertTrue(self.data['app']['packages'][-1].get('revokedAt'))
        self.assertEqual(self.data['app']['packages'][-1]['payload'],package['payload'])
        self.assertTrue(files)
        for path,raw in files.items():self.assertEqual(path.read_bytes(),raw)
        self.assertFalse(self.data['events'])

    def test_replacement_cannot_modify_material_of_a_running_send(self):
        self.evidence('Fijo ≥32 k€','Sí',fixed=40000)
        self.apply({'kind':'ui-fit-review','opportunityId':'one','fingerprint':context.fit_stamp(self.data,jobs.get_op(self.data,'one')),
                    'apply':True,'accept':False,'proof':'TEST mínimos actuales comprobados'})
        self.review()
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':workflow.stamp(self.data,'one')})
        request=self.data['app']['requests'][-1]
        with workflow.execution_owner('TEST-running-owner'):
            self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST inicio ficticio'})
            before=copy.deepcopy(self.data)
            with self.assertRaises(ValueError):self.evidence('Fijo ≥32 k€','No')
        self.assertEqual(self.data,before)

    def test_legacy_superseded_figures_are_projected_from_retained_batches_without_migration(self):
        self.evidence('Fijo ≥32 k€','Sí',fixed=40000)
        self.evidence('Fijo ≥32 k€','No')
        for evidence in self.data['sheets']['Evidencias']:evidence.pop('numericValues')
        row=jobs.get_op(self.data,'one')
        row['Fijo mín. confirmado']=40000
        before=copy.deepcopy(self.data)
        self.assertFalse(offer_minimums.view(self.data,row)['canApply'])
        projected=jobs.view(self.data)['sheets']['Oportunidades'][0]
        self.assertIsNone(projected['Fijo mín. confirmado'])
        self.assertEqual(self.data,before)
        # A migrated sheet with no batch provenance keeps its confirmed figures.
        self.data['changes']=[]
        self.assertEqual(offer_minimums.current_numbers(self.data,row)['Fijo mín. confirmado'],40000)

    def test_older_source_date_cannot_resurrect_a_superseded_observation(self):
        self.evidence('Fijo ≥32 k€','No')
        self.apply({'kind':'evidence','id':'one','condition':'Fijo ≥32 k€','state':'Sí','fixed':40000,
                    'proof':'TEST: comprobación anterior recuperada', 'url':self.row['URL original'],
                    'at':'2026-10-05T10:00:00+02:00'})
        row=jobs.get_op(self.data,'one')
        self.assertEqual(row['Fijo ≥32 k€'],'No')
        self.assertIsNone(row['Fijo mín. confirmado'])
        self.assertFalse(offer_minimums.view(self.data,row)['canApply'])
        self.assertFalse(jobs.conditions(self.data,row)[2])
        self.assertEqual(len(self.data['sheets']['Evidencias']),2)

    def test_legacy_provenance_remains_current_after_backfilling_an_older_check(self):
        self.evidence('Fijo ≥32 k€','No')
        self.data['sheets']['Evidencias'][0].pop('numericValues')
        jobs.get_op(self.data,'one')['Fijo mín. confirmado']=40000
        self.apply({'kind':'evidence','id':'one','condition':'Fijo ≥32 k€','state':'Sí','fixed':40000,
                    'proof':'TEST anterior recuperada','url':self.row['URL original'],'at':'2026-10-05T10:00:00+02:00'})
        row=jobs.get_op(self.data,'one')
        self.assertIsNone(offer_minimums.current_numbers(self.data,row)['Fijo mín. confirmado'])
        self.assertFalse(offer_minimums.view(self.data,row)['canApply'])

    def entry(self):
        self.data['sheets']['Entradas'].append({'ID entrada':'two','Clave canónica':'TEST:two',
            'Empresa':'TEST Empresa','Puesto':'TEST Puesto','URL':'https://example.org/jobs/456-role',
            'Fuente':'web','Estado':'Nueva'})

    def promotion(self, **values):
        return {'kind':'promote','entryId':'two','values':{'Prioridad':'B','Siguiente paso':'TEST revisar',**values},
                'reason':'TEST anuncio pertinente','proof':'TEST datos explícitos del anuncio'}

    def test_promotion_rejects_invalid_or_unproved_facts_atomically(self):
        self.entry()
        before=copy.deepcopy(self.data)
        for field in ('País','Modalidad','Contrato'):
            for value in ({'invalid':True},17,True,'', 'x'*301):
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                    self.apply(self.promotion(**{field:value}))
                self.assertEqual(self.data,before)
            op=self.promotion(**{field:'TEST confirmado'});op.pop('proof')
            with self.assertRaises(ValueError):self.apply(op)
            self.assertEqual(self.data,before)
        for field in ('Fijo mín. confirmado','Fijo máx. confirmado','Moneda fijo confirmado','Viajes mín. al mes'):
            with self.subTest(field=field),self.assertRaises(ValueError):self.apply(self.promotion(**{field:1}))
            self.assertEqual(self.data,before)

    def test_valid_promotion_preserves_explicit_facts_and_no_permissions(self):
        self.entry()
        self.apply(self.promotion(**{'País':'España','Modalidad':'Remoto','Contrato':'Indefinido'}))
        row=jobs.get_op(self.data,'two')
        self.assertEqual(row['País'],'España')
        self.assertEqual(row['Modalidad'],'Remoto')
        self.assertEqual(self.data['sheets']['Entradas'][0]['ID oportunidad'],'two')
        self.assertFalse((workflow.selection(self.data,'two') or {}).get('selected'))

    def test_historical_change_with_optional_title_keeps_interpretation_scope(self):
        self.apply({'kind':'historical','record':{'id':'TEST-old','company':'TEST Empresa',
                    'url':'https://example.org/jobs/789-role','state':'Cerrada','proof':'TEST confirmado'}})
        old=copy.deepcopy(self.data['historicalApplications'])
        self.apply({'kind':'ui-change','opportunityId':'historical:TEST-old','message':'TEST corregir interpretación'})
        self.assertEqual(self.data['historicalApplications'],old)
        request=self.data['app']['requests'][-1]
        self.assertTrue(request['interpretationOnly'])
        self.assertNotIn('None',request['instructions'])
        self.assertFalse(self.data['events'])


if __name__=='__main__':unittest.main()
