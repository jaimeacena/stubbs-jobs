import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from workflow_fixtures import WorkflowFixture
import application_lifecycle as life
import app_workflow as w
import stubbs_jobs as jobs
import stubbs_jobs_app as ui


class LifecycleTests(WorkflowFixture, unittest.TestCase):
    def test_company_offer_is_final_even_if_later_closure_or_rejection_is_recorded(self):
        receipt=copy.deepcopy(self.sent())
        for kind, at, extra in [('offer','2026-10-02T10:00:00Z',{}),
                                ('rejected','2026-10-03T10:00:00Z',{}),
                                ('closed','2026-10-04T10:00:00Z',{'scope':'application','reason':'filled',
                                  'sourceUrl':self.row['URL original'],'applicationReference':'TEST: misma candidatura'})]:
            self.apply({'kind':'event','event':{'id':kind,'type':kind,'opportunityId':'one','at':at,
                        'proof':'TEST: comunicación conservada',**extra}})
        row=self.data['sheets']['Oportunidades'][0]
        self.assertEqual(row['Estado'],'Oferta')
        view=life.view(self.data,row)
        self.assertEqual(view['closure']['reason'],'achieved');self.assertEqual(view['achievedAt'],'2026-10-02T10:00:00Z')
        self.assertIsNone(view['nextCheckAt']);self.assertFalse(view['canReopen'])
        self.assertEqual(jobs.view(self.data)['sheets']['Oportunidades'][0]['Estado'],'Lograda')
        self.data['updatedAt']=w.now()
        with patch.object(ui,'ROOT',self.root):projected=ui.build_state(self.data)['opportunities'][0]
        self.assertEqual(projected['archiveOutcome'],'achieved');self.assertEqual(self.data['events'][0],receipt)
        self.assertEqual([e['type'] for e in self.data['events']],['sent','offer','rejected','closed'])

    def test_backfilled_offer_ends_the_cycle_without_rewriting_legacy_closure(self):
        self.sent();self.row['Estado']='Rechazada'
        self.data['app']['offerArchives']={'one':{'outcome':'closed','at':'2026-10-04T10:00:00Z','reason':'TEST: cierre antiguo'}}
        archive=copy.deepcopy(w.archived(self.data,'one'))
        for kind, at in [('rejected','2026-10-03T10:00:00Z'),('offer','2026-10-02T10:00:00Z')]:
            self.apply({'kind':'event','event':{'id':kind,'type':kind,'opportunityId':'one','at':at,'proof':'TEST: comunicación fechada'}})
        before=copy.deepcopy(self.data)
        projected=jobs.view(self.data)['sheets']['Oportunidades'][0]
        self.assertEqual(projected['Estado'],'Lograda');self.assertEqual(projected['Siguiente paso'],'La empresa te ofrece el puesto.')
        self.assertEqual(life.view(self.data,self.data['sheets']['Oportunidades'][0])['closure']['reason'],'achieved')
        self.assertEqual(w.archived(self.data,'one'),archive);self.assertEqual(self.data,before)

    def test_achieved_application_rejects_new_work_and_checks_atomically(self):
        self.sent()
        self.apply({'kind':'ui-bulk-action','action':'achieve','targets':[{'id':'one'}],'expectedRevision':self.data['revision']})
        before=copy.deepcopy(self.data)
        for operation in [{'kind':'ui-request','type':'investigate','purpose':'followup','opportunityId':'one'},
                          {'kind':'ui-change','opportunityId':'one','message':'TEST: continuar seguimiento'},
                          {'kind':'ui-followup-check','opportunityId':'one'},
                          {'kind':'ui-followup-plan','opportunityId':'one'}]:
            with self.assertRaisesRegex(ValueError,'lograda'):self.apply(operation)
            self.assertEqual(self.data,before)

    def test_interview_and_response_are_not_achievement(self):
        self.sent()
        for kind in ('response','interview'):
            self.apply({'kind':'event','event':{'id':kind,'type':kind,'opportunityId':'one','at':'2026-10-02T10:00:00Z','proof':'TEST: comunicación'}})
            self.assertIsNone(life.achievement(self.data,self.data['sheets']['Oportunidades'][0]))
            self.assertIsNotNone(life.view(self.data,self.data['sheets']['Oportunidades'][0])['nextCheckAt'])

    def test_history_projects_each_legacy_check_without_changing_the_store(self):
        self.sent()
        for outcome, at in [('waiting','2026-10-06T08:00:00Z'),('reviewing','2026-10-06T10:00:00Z')]:
            self.apply({'kind':'ui-followup-check','opportunityId':'one','outcome':outcome,'observedAt':at,
                        'sourceUrl':self.row['URL original'],'vacancyUrl':self.row['URL original'],
                        'applicationReference':'TEST: candidatura 123','proof':'TEST: prueba repetida'})
        for h in self.data['app']['history']:
            h.pop('checkId',None)
        before=copy.deepcopy(self.data)
        rows=[h for h in life.history_view(self.data) if h['title']=='Seguimiento comprobado']
        self.assertEqual([h['activity']['outcome'] for h in rows],['waiting','reviewing'])
        self.assertEqual([h['at'] for h in rows],['2026-10-06T08:00:00Z','2026-10-06T10:00:00Z'])
        self.assertEqual(self.data,before)

    def test_unmatched_legacy_checks_remain_unknown_and_missing_facts_are_projected(self):
        self.sent();self.check('open',observedAt='2026-10-06T10:00:00Z')
        row=self.data['app']['history'][-1];row.pop('checkId');row['detail']='TEST: otra prueba antigua'
        before=copy.deepcopy(self.data);rows=life.history_view(self.data)
        self.assertNotIn('activity',next(h for h in rows if h['id']==row['id']))
        facts=[h for h in rows if h.get('activity',{}).get('kind')=='availability']
        self.assertEqual(len(facts),1);self.assertEqual(facts[0]['activity']['outcome'],'open')
        self.assertEqual(self.data,before)

    def test_requested_check_has_identity_but_no_result_until_it_is_done(self):
        self.sent();self.apply({'kind':'ui-request','type':'investigate','purpose':'followup','opportunityId':'one'})
        history=life.history_view(self.data);request=self.data['app']['requests'][0]
        self.assertEqual(history[-1]['requestId'],request['id'])
        self.assertEqual(history[-1]['activity'],{'kind':'task','type':'investigate','purpose':'followup'})
        self.assertNotIn('outcome',history[-1]['activity']);self.assertEqual(request['status'],'queued')

    def check(self, outcome='closed', **extra):
        operation={'kind':'ui-availability-check','opportunityId':'one','outcome':outcome,
                   'observedAt':w.now(),'sourceUrl':'https://example.org/jobs/123-role',
                   'vacancyUrl':self.row['URL original'],'signal':'not_accepting','reason':'not_accepting',
                   'proof':'TEST: esta misma publicación indica que ya no acepta solicitudes.'}
        operation.update(extra);self.apply(operation)

    def sent(self):
        event={'id':'fictional-receipt','type':'sent','opportunityId':'one','at':'2026-10-01T10:00:00Z','proof':'TEST: recibo confirmado'}
        self.data['events'].append(event);self.row['Estado']='Enviada'
        return event

    def test_sent_application_does_not_resolve_a_new_followup_access_block(self):
        receipt=copy.deepcopy(self.sent())
        block={'id':'TEST-followup-access','opportunityId':'one','owner':'Agente',
               'question':'TEST: iniciar sesión para consultar esta candidatura','status':'open'}
        self.apply({'kind':'block','block':copy.deepcopy(block)})
        self.assertEqual(self.data['blocks'][0],block)
        self.apply({'kind':'ui-offer-note','opportunityId':'one','values':{'Notas de seguimiento':'TEST: nota independiente'},
                    'expected':{'Notas de seguimiento':None}})
        self.assertEqual(self.data['blocks'][0],block)
        self.assertEqual(jobs.view(self.data)['sheets']['Oportunidades'][0]['Bloqueos abiertos'],
                         'Agente: '+block['question'])
        self.assertEqual(self.data['events'][0],receipt)

    def test_sent_application_resolves_known_preparation_blocks_and_closure_resolves_followup(self):
        self.sent()
        self.data['blocks']=[{'id':key,'opportunityId':'one','owner':'Agente','question':'TEST', 'status':'open'}
                             for key in ('ui-answers-one','send-one','TEST-followup-access')]
        life.reconcile(self.data,w)
        self.assertEqual([b['status'] for b in self.data['blocks']],['resolved','resolved','open'])
        self.apply({'kind':'ui-bulk-action','action':'close','targets':[{'id':'one'}],
                    'expectedRevision':self.data['revision'],'actor':'Usuario'})
        self.assertTrue(all(b['status']=='resolved' for b in self.data['blocks']))

    def test_unavailable_prospect_closes_and_resolves_obsolete_work(self):
        self.select_for_request()
        w.state(self.data)['requests'].append({'id':'blocked','type':'investigate','opportunityId':'one','status':'blocked','need':'other','updatedAt':w.now()})
        self.check()
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['Estado'],'Cerrada')
        self.assertEqual(self.data['app']['requests'][0]['status'],'cancelled')
        self.assertFalse(w.selection(self.data,'one'))
        self.assertEqual(life.view(self.data,self.data['sheets']['Oportunidades'][0])['closure']['label'],'Anuncio cerrado a nuevas solicitudes')

    def test_error_login_absence_and_partial_search_are_not_closure(self):
        for signal in ('404','login','network_error','not_found','partial_search'):
            before=copy.deepcopy(self.data)
            with self.assertRaises(ValueError):self.check(signal=signal)
            self.assertEqual(self.data,before)

    def test_closed_ad_after_submission_does_not_close_application(self):
        receipt=copy.deepcopy(self.sent())
        self.check()
        row=self.data['sheets']['Oportunidades'][0];f=life.view(self.data,row)
        self.assertEqual(row['Estado'],'Enviada');self.assertIsNone(f['closure'])
        self.assertEqual(f['availability']['outcome'],'closed');self.assertEqual(self.data['events'][0],receipt)

    def test_failed_access_keeps_uncertainty_without_closing(self):
        self.check('unknown',signal='login',reason=None)
        self.assertNotEqual(self.data['sheets']['Oportunidades'][0]['Estado'],'Cerrada')
        self.assertEqual(life.view(self.data,self.row)['availability']['outcome'],'unknown')
        followup=life.view(self.data,self.data['sheets']['Oportunidades'][0])
        self.assertIsNotNone(followup['nextCheckAt']);self.assertEqual(followup['owner'],'agent')

    def test_check_requires_exact_vacancy_date_and_source(self):
        for values in ({'vacancyUrl':'https://example.org/jobs/456'}, {'observedAt':'2026-10-07'},
                       {'sourceUrl':'file:///test'}, {'observedAt':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}):
            with self.assertRaises(ValueError):self.check(**values)

    def test_old_availability_observation_cannot_replace_new_one(self):
        self.check('open',observedAt='2026-10-06T10:00:00Z')
        self.check('closed',observedAt='2026-10-02T10:00:00Z')
        self.assertEqual(life.view(self.data,self.row)['availability']['outcome'],'open')
        self.assertNotEqual(self.data['sheets']['Oportunidades'][0]['Estado'],'Cerrada')

    def test_backfilled_response_does_not_replace_later_rejection(self):
        self.sent()
        for kind,at in [('rejected','2026-10-06T10:00:00Z'),('response','2026-10-02T10:00:00Z')]:
            self.apply({'kind':'event','event':{'id':kind,'type':kind,'opportunityId':'one','at':at,'proof':'TEST: comunicación de empresa'}})
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['Estado'],'Rechazada')
        self.assertEqual([h['at'] for h in self.data['app']['history'] if h.get('eventId')],['2026-10-06T10:00:00Z','2026-10-02T10:00:00Z'])

    def test_legacy_manual_rejection_is_a_personal_closure(self):
        self.sent();self.data['app']['offerArchives']={'one':{'outcome':'rejected','at':w.now(),'reason':'Marcada como rechazada por ti.'}}
        self.assertEqual(life.archive_outcome(self.data,self.row),'closed')
        self.assertEqual(jobs.view(self.data)['sheets']['Oportunidades'][0]['Estado'],'Cerrada')

    def test_obsolete_preparation_resolves_but_running_and_uncertain_sends_survive(self):
        self.sent();app=self.data['app']
        app['requests']=[{'id':str(i),'type':kind,'opportunityId':'one','status':status,'updatedAt':w.now(),'executionId':'original'}
                         for i,(kind,status) in enumerate([('review','queued'),('investigate','blocked'),('review','running'),('send','blocked')])]
        preserved=copy.deepcopy(app['requests'][2:]);life.reconcile(self.data,w)
        self.assertEqual([r['status'] for r in app['requests'][:2]],['cancelled','cancelled'])
        self.assertEqual(app['requests'][2:],preserved)

    def test_followup_task_is_distinct_from_duplicate_preparation(self):
        self.sent()
        with self.assertRaises(ValueError):self.apply({'kind':'ui-request','type':'review','opportunityId':'one'})
        self.apply({'kind':'ui-request','type':'investigate','purpose':'followup','opportunityId':'one'})
        self.assertEqual(self.data['app']['requests'][0]['purpose'],'followup')
        self.assertEqual(self.data['app']['requests'][0]['status'],'queued')

    def test_followup_needs_application_reference_to_confirm_rejection(self):
        self.sent()
        op={'kind':'ui-followup-check','opportunityId':'one','outcome':'rejected','observedAt':w.now(),
            'sourceUrl':self.row['URL original'],'vacancyUrl':self.row['URL original'],'proof':'TEST: el portal muestra rechazo'}
        with self.assertRaises(ValueError):self.apply(op)
        op['applicationReference']='TEST: candidatura 123 del usuario';self.apply(op)
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['Estado'],'Rechazada')

    def test_silence_only_sets_a_dated_review_without_work_or_rejection(self):
        self.sent();f=life.view(self.data,self.row)
        self.assertEqual(f['label'],'Sin respuesta conocida');self.assertEqual(f['nextCheckAt'],'2026-10-08T10:00:00+00:00')
        self.assertFalse(f['monitoring']);self.assertEqual(self.data['app']['requests'],[])

    def test_date_plan_keeps_receipt_and_does_not_start_work(self):
        receipt=copy.deepcopy(self.sent());at=(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()
        self.apply({'kind':'ui-followup-plan','opportunityId':'one','nextCheckAt':at,'expected':None,'proof':'TEST: fecha elegida'})
        self.assertEqual(life.view(self.data,self.row)['nextCheckAt'],at);self.assertEqual(self.data['events'][0],receipt)
        self.assertEqual(self.data['app']['requests'],[])

    def test_current_questions_replace_stale_summary_without_overwriting_history(self):
        self.data['app']['drafts']['one']['requiredAnswers']=['currentCity']
        req={'id':'old','opportunityId':'one','status':'blocked','need':'answers','summary':'Faltan ciudad y otra encuesta'}
        original=copy.deepcopy(req);projected=life.request_view(self.data,req,w)
        self.assertNotIn('encuesta',projected['summary']);self.assertEqual(req,original)
        self.data['profile']['currentCity']='TEST: ciudad'
        self.assertEqual(life.request_view(self.data,req,w)['actionOwner'],'agent')

    def test_old_availability_and_portal_states_are_marked_old(self):
        self.sent();self.check('open',observedAt='2026-10-01T10:00:00Z')
        f=life.view(self.data,self.row,datetime(2026,10,20,tzinfo=timezone.utc))
        self.assertFalse(f['availability']['fresh']);self.assertTrue(f['checkDue'])

    def test_reopen_after_new_reply_does_not_restore_selection_or_permission(self):
        self.sent();self.data['app']['offerArchives']={'one':{'outcome':'closed','at':'2026-10-02T10:00:00Z','closureReason':'user'}}
        self.apply({'kind':'event','event':{'id':'reply','type':'response','opportunityId':'one','at':'2026-10-06T10:00:00Z','proof':'TEST: nueva respuesta'}})
        self.apply({'kind':'ui-bulk-action','action':'reopen-followup','targets':[{'id':'one'}],'expectedRevision':self.data['revision']})
        self.assertFalse(w.archived(self.data,'one'));self.assertFalse(w.selection(self.data,'one'))
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['Estado'],'Pendiente de empresa')

    def test_closed_raw_event_cannot_hide_which_entity_closed(self):
        with self.assertRaises(ValueError):
            self.apply({'kind':'event','event':{'id':'ambiguous','type':'closed','opportunityId':'one','at':w.now(),'proof':'TEST: cierre sin ámbito'}})

    def test_expired_final_review_cannot_transmit_approved_package(self):
        self.select_for_request()
        with patch.object(jobs,'conditions',return_value=('Sí','Sí',True)):
            self.review();self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':w.stamp(self.data,'one')})
            package=self.data['app']['packages'][0]
            w.draft(self.data,'one')['review']['at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
            with self.assertRaisesRegex(ValueError,'24 horas'):w.approved_package(self.data,'one',package['id'])

    def test_rejection_after_personal_closure_is_not_an_invitation_to_reopen(self):
        self.sent();self.data['app']['offerArchives']={'one':{'outcome':'closed','at':'2026-10-02T10:00:00Z'}}
        self.apply({'kind':'event','event':{'id':'new-rejection','type':'rejected','opportunityId':'one','at':'2026-10-06T10:00:00Z','proof':'TEST: rechazo posterior'}})
        self.assertEqual(life.archive_outcome(self.data,self.row),'rejected')
        self.assertEqual(jobs.view(self.data)['sheets']['Oportunidades'][0]['Estado'],'Rechazada')
        view=life.view(self.data,self.data['sheets']['Oportunidades'][0])
        self.assertFalse(view['canReopen']);self.assertEqual(view['closure']['label'],'Rechazo comunicado por la empresa')

    def test_new_portal_review_after_rejection_updates_followup_without_permission(self):
        self.sent()
        self.apply({'kind':'event','event':{'id':'rejection','type':'rejected','opportunityId':'one','at':'2026-10-02T10:00:00Z','proof':'TEST: rechazo anterior'}})
        self.apply({'kind':'ui-followup-check','opportunityId':'one','outcome':'reviewing','observedAt':'2026-10-06T10:00:00Z','sourceUrl':self.row['URL original'],'vacancyUrl':self.row['URL original'],'applicationReference':'TEST: misma candidatura 123','proof':'TEST: el portal comunica revisión posterior'})
        row=self.data['sheets']['Oportunidades'][0]
        self.assertEqual(row['Estado'],'Pendiente de empresa');self.assertEqual(life.view(self.data,row)['label'],'Estado actualizado por el portal')
        self.assertFalse(w.selection(self.data,'one'));self.assertFalse(any(r['type']=='send' for r in self.data['app']['requests']))

    def test_receipt_recovered_after_ad_closure_does_not_close_the_application(self):
        self.check(observedAt='2026-10-06T10:00:00Z')
        self.data['events'].append({'id':'recovered','type':'sent','opportunityId':'one','at':'2026-10-01T10:00:00Z','proof':'TEST: recibo original recuperado'})
        w.reconcile(self.data);row=self.data['sheets']['Oportunidades'][0]
        self.assertEqual(row['Estado'],'Enviada');self.assertIsNone(life.view(self.data,row)['closure'])
        self.assertFalse(w.selection(self.data,'one'))

    def test_new_explicit_ad_availability_allows_reconsideration_without_restoring_permission(self):
        self.select_for_request();self.check(observedAt='2026-10-02T10:00:00Z')
        self.check('open',observedAt='2026-10-06T10:00:00Z')
        row=self.data['sheets']['Oportunidades'][0]
        self.assertEqual(row['Estado'],'Investigar');self.assertIsNone(life.view(self.data,row)['closure'])
        self.assertFalse(w.selection(self.data,'one'));self.assertFalse(any(r['status']=='queued' for r in self.data['app']['requests']))

    def test_later_recovered_receipt_also_separates_ad_and_application(self):
        self.check(observedAt='2026-10-06T10:00:00Z')
        self.data['events'].append({'id':'recovered','type':'sent','opportunityId':'one','at':'2026-10-06T11:00:00Z','proof':'TEST: recibo original recuperado después del cierre público'})
        w.reconcile(self.data)
        self.assertEqual(self.data['sheets']['Oportunidades'][0]['Estado'],'Enviada')

    def test_raw_state_edit_cannot_bypass_closure_evidence(self):
        before=copy.deepcopy(self.data)
        with self.assertRaises(ValueError):self.apply({'kind':'opportunity','id':'one','values':{'Estado':'Cerrada'},'proof':'TEST: sin ámbito ni prueba del cierre'})
        self.assertEqual(self.data,before)

    def test_explicit_personal_closure_does_not_require_guessing_its_reason(self):
        self.sent()
        self.apply({'kind':'ui-followup-check','opportunityId':'one','outcome':'closed','observedAt':w.now(),'sourceUrl':self.row['URL original'],'vacancyUrl':self.row['URL original'],'applicationReference':'TEST: candidatura personal 123','proof':'TEST: el portal confirma cierre de esta candidatura sin explicar la causa'})
        row=self.data['sheets']['Oportunidades'][0];self.assertEqual(row['Estado'],'Cerrada')
        self.assertEqual(life.view(self.data,row)['closure']['label'],'Proceso cerrado por la empresa; motivo no indicado')

    def test_automatic_minimum_discard_shows_its_reason_not_a_personal_choice(self):
        self.data['app']['searchContext']={'workMode':'Remoto, Híbrido, Presencial','currency':'EUR','onsiteLocations':'Villa Norte'}
        self.row['Modalidad']='Presencial';self.row.pop('Ubicación',None)
        self.apply({'kind':'ui-minimum-reconcile','expectedRevision':self.data['revision'],'proof':'TEST: aplicar zonas aceptadas.'})
        row=self.data['sheets']['Oportunidades'][0]
        closure=life.view(self.data,row)['closure']
        self.assertIn('no consta su ubicación',closure['label'])
        self.assertNotIn('por ti',closure['label'])
        # A discard by the person keeps its personal wording.
        self.data['app']['offerArchives'].pop('one');self.data['app']['searchContext']['onsiteLocations']=''
        self.apply({'kind':'ui-bulk-action','action':'discard','targets':[{'id':'one'}],'expectedRevision':self.data['revision']})
        self.assertEqual(life.view(self.data,row)['closure']['label'],'Oferta descartada por ti')
