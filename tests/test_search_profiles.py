"""Independent strategies, shared applications and lossless migration; fictional only."""
import copy
import unittest
from unittest.mock import patch
import app_context as context
import app_workflow as w
import criteria_preview
import personalization
import search_profiles as profiles
import stubbs_jobs as j
from workflow_fixtures import WorkflowFixture


class SearchProfilesTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.data['app']['searchContext']={**personalization.CONTEXT,'targetRoles':'Analista BI','workMode':'Remoto','currency':'EUR'}
        self.data['updatedAt']=w.now()
        self.migrate()

    def migrate(self):
        self.apply({'kind':'ui-search-profiles-migrate','expectedRevision':self.data['revision'],'proof':'TEST: migración ficticia'})

    def manage(self, action, **values):
        self.apply({'kind':'ui-search-profile','action':action,'expectedRevision':self.data['revision'],**values})

    def duplicate(self):
        self.manage('duplicate',id=profiles.LEGACY_ID,newId='search-two',name='Técnicos locales')

    def test_implicit_single_profile_save_keeps_its_scope_for_undo_after_adding_profiles(self):
        old=personalization.context(self.data)['searchPriorities']
        self.apply({'kind':'ui-profile-section','section':'search',
                    'values':{'searchPriorities':'TEST: mañana'},'expected':{'searchPriorities':old}})
        undo=next(item for item in reversed(self.data['app']['undo']) if item['kind']=='section')
        self.duplicate()
        self.edit('search-two',searchPriorities='TEST: otra preferencia')
        self.manage('default',id='search-two')
        other=copy.deepcopy(profiles.get(self.data,'search-two'))
        self.assertTrue(w.undo_available(self.data,undo))
        self.apply({'kind':'ui-undo','id':undo['id'],'actor':'Usuario'})
        self.assertEqual(personalization.context(self.data,profiles.LEGACY_ID)['searchPriorities'],old)
        self.assertEqual(profiles.get(self.data,'search-two'),other)
        self.assertEqual(profiles.default_id(self.data),'search-two')

    def edit(self, identifier=profiles.LEGACY_ID, **values):
        old={**personalization.context(self.data,identifier),**self.data['profile'],**context.criteria(self.data,identifier)}
        self.apply({'kind':'ui-profile-section','section':'search','searchProfileId':identifier,'values':values,'expected':{k:old.get(k) for k in values}})

    def queue(self, identifier=profiles.LEGACY_ID):
        self.apply({'kind':'ui-request','type':'discovery','searchProfileId':identifier})
        return self.data['app']['requests'][-1]

    def start(self, request):
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'running','proof':'TEST: inicio ficticio'})
        return next(r for r in self.data['app']['requests'] if r['id']==request['id'])

    def test_migration_preserves_material_selection_packages_and_history(self):
        data=copy.deepcopy(self.data)
        for key in ('searchProfiles','searchProfilesVersion','defaultSearchProfileId','searchProfilesMigratedAt','offerCriteria'):
            data['app'].pop(key,None)
        before=w.material_versions(data)
        originals={key:copy.deepcopy(data[key]) for key in ('events','historicalApplications','observations','sheets')}
        self.assertTrue(profiles.migrate(data))
        self.assertEqual(w.material_versions(data),before)
        for key,value in originals.items():self.assertEqual(data[key],value)
        self.assertFalse(profiles.migrate(data))

    def test_duplicate_edits_do_not_change_first_strategy_or_common_answers(self):
        self.data['profile']['salaryExpectationFixed']=35000
        self.duplicate()
        before=copy.deepcopy(profiles.get(self.data,profiles.LEGACY_ID))
        stamp=w.stamp(self.data,'one')
        self.edit('search-two',workMode='Híbrido',minimumFixed=50000,currency='USD',searchNotes='TEST: otra orientación')
        self.assertEqual(profiles.get(self.data,profiles.LEGACY_ID),before)
        self.assertEqual(w.stamp(self.data,'one'),stamp)
        self.assertEqual(w.answers(self.data,'one')['minimumFixed'],32000)
        self.assertEqual(context.definitions(self.data)['salaryExpectationFixed']['label'],'Salario deseado (bruto anual, EUR)' if self.data['app'].get('personalized') else w.LABELS['salaryExpectationFixed'])

    def test_common_salary_currency_changes_material_without_changing_search_minimum(self):
        self.data['profile']['salaryExpectationFixed']=35000
        before=w.stamp(self.data,'one')
        self.edit(salaryCurrency='USD')
        self.assertNotEqual(w.stamp(self.data,'one'),before)
        self.assertEqual(w.payload(self.data,'one')['salaryExpectationCurrency'],'USD')
        self.assertEqual(personalization.context(self.data)['currency'],'EUR')
        self.assertEqual(context.scoped_criteria(self.data,'one')['minimumFixed'],32000)

    def test_legacy_pending_search_is_bound_at_migration_before_switching_default(self):
        data=copy.deepcopy(self.data)
        for key in ('searchProfiles','searchProfilesVersion','defaultSearchProfileId','searchProfilesMigratedAt','offerCriteria'):
            data['app'].pop(key,None)
        data['app']['requests']=[{'id':'TEST-old-search','type':'discovery','status':'blocked'}]
        profiles.migrate(data)
        request=data['app']['requests'][0]
        self.assertEqual(request['roundOrigin'],'legacy-migration')
        self.assertEqual(request['searchProfileId'],profiles.LEGACY_ID)
        frozen=copy.deepcopy(request['round'])
        data['app']['searchContext']['workMode']='Presencial'
        self.assertEqual(request['round'],frozen)
        self.assertEqual(request['round']['searchContext']['workMode'],'Remoto')

    def test_blank_search_profile_is_editable_but_cannot_start_a_search(self):
        self.manage('create',newId='search-empty',name='TEST por completar')
        with self.assertRaisesRegex(ValueError,'puestos y la zona'):self.queue('search-empty')
        self.assertEqual(self.data['app']['requests'],[])

    def test_malformed_archive_metadata_is_rejected(self):
        bad=copy.deepcopy(self.data)
        bad['app']['searchProfiles'][0]['archivedAt']=True
        with self.assertRaisesRegex(ValueError,'fecha'):profiles.profiles(bad)

    def test_unknown_profile_references_are_rejected_before_backup_or_write(self):
        bad=copy.deepcopy(self.data)
        bad['app']['offerCriteria']['one']={'searchProfileId':'search-missing'}
        with self.assertRaisesRegex(ValueError,'inexistente'):profiles.validate_model(bad)

    def test_initial_interview_must_finish_before_search_profile_migration(self):
        data=personalization.blank_store();original=copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError,'preparación inicial'):profiles.migrate(data)
        self.assertEqual(data,original)

    def test_default_switch_rename_and_delete_do_not_change_candidate_material(self):
        self.duplicate();self.edit('search-two',minimumFixed=50000,currency='USD')
        before=w.stamp(self.data,'one')
        self.manage('default',id='search-two')
        self.manage('rename',id=profiles.LEGACY_ID,name='BI remoto')
        self.manage('delete',id=profiles.LEGACY_ID)
        self.assertEqual(w.stamp(self.data,'one'),before)
        self.assertEqual(self.data['profile']['minimumFixed'],50000)
        self.assertEqual(w.answers(self.data,'one')['minimumFixed'],32000)

    def test_retired_archive_action_rejects_without_changes(self):
        self.duplicate()
        before=copy.deepcopy(self.data)
        for identifier in (profiles.LEGACY_ID,'search-two'):
            with self.assertRaisesRegex(ValueError,'retirado'):self.manage('archive',id=identifier)
            self.assertEqual(self.data,before)

    def test_legacy_archived_profile_remains_recoverable(self):
        self.duplicate()
        profiles.get(self.data,'search-two')['archivedAt']=w.now()
        with self.assertRaisesRegex(ValueError,'Recupera'):self.queue('search-two')
        self.manage('restore',id='search-two');self.queue('search-two')

    def test_missing_identifier_is_rejected_for_ambiguous_legacy_edits(self):
        self.duplicate();before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'searchProfileId'):
            self.apply({'kind':'ui-search-context','values':{'workMode':'Híbrido'},'expected':{'workMode':'Remoto'}})
        self.assertEqual(self.data,before)

    def test_same_field_conflict_is_per_profile_and_undo_uses_original_profile(self):
        self.duplicate();self.edit('search-two',workMode='Híbrido')
        undo=self.data['app']['undo'][-1]
        self.manage('default',id='search-two')
        self.apply({'kind':'ui-undo','id':undo['id']})
        self.assertEqual(personalization.context(self.data,'search-two')['workMode'],'Remoto')
        self.assertEqual(personalization.context(self.data,profiles.LEGACY_ID)['workMode'],'Remoto')
        with self.assertRaises(w.Conflict):
            self.apply({'kind':'ui-profile-section','section':'search','searchProfileId':'search-two',
                        'values':{'workMode':'Presencial'},'expected':{'workMode':'Híbrido'}})

    def test_request_freezes_at_queue_and_survives_edit_switch_and_retry(self):
        request=self.queue();frozen=copy.deepcopy(request['round'])
        self.edit(workMode='Híbrido');self.duplicate();self.manage('default',id='search-two')
        request=self.start(request)
        self.assertEqual(request['round'],frozen)
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'blocked','proof':'TEST: acceso','summary':'TEST acceso pendiente','need':'access'})
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'queued','proof':'TEST: acceso recuperado'})
        self.assertEqual(self.start(request)['round'],frozen)

    def test_blocked_strategy_does_not_prevent_another_and_renaming_does_not_duplicate(self):
        request=self.start(self.queue())
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'blocked','proof':'TEST: acceso','summary':'TEST acceso pendiente','need':'access'})
        self.manage('rename',id=profiles.LEGACY_ID,name='BI remoto')
        self.queue();self.assertEqual(len(self.data['app']['requests']),1)
        self.duplicate();self.queue('search-two')
        self.assertEqual(len(self.data['app']['requests']),2)

    def test_legacy_retry_with_baseline_but_no_snapshot_is_completed(self):
        request=self.start(self.queue())
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'blocked','proof':'TEST','summary':'TEST acceso pendiente','need':'access'})
        current=self.data['app']['requests'][-1];current.pop('round')
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'queued','proof':'TEST'})
        self.assertIn('round',self.start(request))
        self.assertEqual(self.data['app']['requests'][-1]['roundOrigin'],'legacy-start')

    def test_request_and_case_agent_context_explain_the_effective_criteria(self):
        import agent_context
        request=self.queue();self.edit(minimumFixed=50000)
        with patch('personalization.public_sources',return_value=[]):
            request_view=agent_context.view(self.data,request_id=request['id'])
        self.assertEqual(request_view['preferences']['minimumFixed'],32000)
        self.assertEqual(request_view['searchContext']['workMode'],'Remoto')

    def test_manual_offers_are_bound_immediately_even_when_the_search_blocks(self):
        request=self.start(self.queue());self.edit(workMode='Híbrido')
        self.apply({'kind':'ui-add-opportunity','values':{'company':'TEST','title':'TEST','url':'https://example.org/test-two'}})
        key=self.data['sheets']['Oportunidades'][-1]['ID']
        self.assertEqual(context.scoped_search(self.data,key)['workMode'],'Remoto')
        self.assertEqual(self.data['app']['offerRounds'][key],request['id'])
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'blocked','proof':'TEST','summary':'TEST acceso pendiente','need':'access'})
        self.assertEqual(context.scoped_search(self.data,key)['workMode'],'Remoto')

    def test_same_vacancy_records_two_appearances_with_one_row_and_one_basis(self):
        request=self.start(self.queue())
        profiles.associate(self.data,'one',request,new=False)
        self.apply({'kind':'ui-request-update','id':request['id'],'status':'blocked','proof':'TEST','summary':'TEST acceso pendiente','need':'access'})
        self.duplicate();second=self.start(self.queue('search-two'))
        profiles.associate(self.data,'one',second,new=False)
        self.assertEqual(len(self.data['sheets']['Oportunidades']),1)
        self.assertEqual(len(self.data['app']['offerSearches']['one']),2)
        self.assertEqual(self.data['app']['offerRounds']['one'],request['id'])
        self.assertEqual(profiles.offer_info(self.data,'one')['searchProfileIds'],[profiles.LEGACY_ID,'search-two'])

    def test_sources_use_request_snapshot_and_reject_wrong_owner_and_feed(self):
        self.edit(sourceUrls='https://example.org/jobs')
        with w.execution_owner('TEST-owner'):
            request=self.start(self.queue())
            self.edit(sourceUrls='https://second.example.org/jobs')
            scoped=profiles.discovery_data(self.data,request)
            self.assertTrue(personalization.source_allowed(scoped,'https://example.org/123'))
            self.assertFalse(personalization.source_allowed(scoped,'https://second.example.org/123'))
            payload={'schemaVersion':2,'requestId':request['id'],'searchKey':request['searchKey'],'checkedAtUtc':w.now(),'boards':[{'sourceId':'s','sourceUrl':'https://second.example.org/jobs'}],'candidates':[]}
            with self.assertRaisesRegex(ValueError,'exclusivas'):j.ingest(self.data,payload)
            payload['boards'][0]['sourceUrl']='https://example.org/jobs';payload['searchKey']='wrong'
            with self.assertRaisesRegex(ValueError,'búsqueda'):j.ingest(self.data,payload)
        with w.execution_owner('TEST-other'),self.assertRaises(ValueError):profiles.discovery_request(self.data,request['id'])

    def test_change_does_not_revoke_a_package_with_frozen_unrelated_criteria(self):
        request=self.start(self.queue());self.data['app'].setdefault('offerRounds',{})['one']=request['id'];self.data['app']['offerCriteria'].pop('one')
        self.select_for_request()
        self.apply({'kind':'ui-fit-review','opportunityId':'one','fingerprint':context.fit_stamp(self.data,w.row_for(self.data,'one')),
                    'apply':True,'accept':False,'proof':'TEST: encaje ficticio'})
        self.review()
        pack=self.data['app']['packages'][-1];pack['approvedAt']=w.now();self.queue_send(pack)
        stamp=w.stamp(self.data,'one')
        self.edit(minimumFixed=50000)
        self.assertEqual(w.stamp(self.data,'one'),stamp)
        saved=next(p for p in self.data['app']['packages'] if p['id']==pack['id'])
        self.assertIsNone(saved.get('revokedAt'))
        self.assertEqual(next(r for r in self.data['app']['requests'] if r['type']=='send')['status'],'queued')

    def queue_send(self,pack):
        # Synthetic fixture already reviewed; no send is started or transmitted.
        w.request(self.data,'one','send',pack['id'])

    def test_preview_and_explicit_basis_change_are_profile_scoped(self):
        self.duplicate();self.edit('search-two',minimumFixed=50000)
        before=copy.deepcopy(self.data)
        result=criteria_preview.preview(self.data,{'searchProfileId':'search-two','values':{'minimumFixed':60000}})
        self.assertEqual(self.data,before);self.assertEqual(result['counts']['packages'],0)
        self.apply({'kind':'ui-criteria-scope','mode':'current','searchProfileId':'search-two','targets':[{'id':'one'}],
                    'expectedRevision':self.data['revision'],'proof':'TEST: elección explícita'})
        self.assertEqual(context.scoped_criteria(self.data,'one')['minimumFixed'],50000)

    def test_moving_an_offer_requires_an_explicit_profile_when_there_are_several(self):
        self.duplicate();before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'searchProfileId'):
            self.apply({'kind':'ui-criteria-scope','mode':'current','targets':[{'id':'one'}],
                        'expectedRevision':self.data['revision'],'proof':'TEST'})
        self.assertEqual(self.data,before)

    def test_planning_an_explicit_strategy_does_not_use_or_change_the_default(self):
        import assistant_flow
        self.duplicate();self.edit('search-two',minimumFixed=50000,currency='USD')
        self.manage('default',id='search-two')
        operations=assistant_flow.plan(self.data,profiles.LEGACY_ID)
        discovery=next(op for op in operations if op['type']=='discovery')
        self.assertEqual(discovery['searchProfileId'],profiles.LEGACY_ID)
        self.assertEqual(profiles.default_id(self.data),'search-two')
        self.apply(discovery)
        self.assertEqual(self.data['app']['requests'][-1]['round']['criteria']['minimumFixed'],32000)
        self.assertEqual(self.data['app']['requests'][-1]['round']['searchContext']['currency'],'EUR')

    def test_planning_cannot_request_a_deleted_search_strategy(self):
        import assistant_flow
        self.duplicate();self.manage('delete',id='search-two')
        with self.assertRaisesRegex(ValueError,'Recupera'):assistant_flow.plan(self.data,'search-two')
        self.assertEqual(self.data['app']['requests'],[])

    def test_native_feed_cannot_silently_inherit_the_only_running_request(self):
        self.start(self.queue())
        payload={'schemaVersion':2,'checkedAtUtc':w.now(),'boards':[],'candidates':[]}
        with self.assertRaisesRegex(ValueError,'requestId y searchKey'):j.ingest(self.data,payload)

    def test_delete_is_recoverable_and_preserves_historical_material_and_requests(self):
        from agent_context import view
        self.duplicate()
        pending=self.queue()
        pending=self.start(pending)
        self.apply({'kind':'ui-request-update','id':pending['id'],'status':'blocked','summary':'TEST acceso pendiente',
                    'need':'access','proof':'TEST sin acceso'})
        self.manage('default',id='search-two')
        before=copy.deepcopy(self.data)
        material=w.material_versions(before)
        original=copy.deepcopy(profiles.get(self.data,profiles.LEGACY_ID))
        self.manage('delete',id=profiles.LEGACY_ID)
        self.assertEqual([p['id'] for p in profiles.visible_profiles(self.data)],['search-two'])
        self.assertEqual(profiles.deleted_profiles(self.data)[0]['id'],profiles.LEGACY_ID)
        self.assertEqual(w.material_versions(self.data),material)
        for key in ('sheets','events','observations','historicalApplications'):self.assertEqual(self.data[key],before[key])
        for key in ('packages','selections','requests','drafts'):self.assertEqual(self.data['app'][key],before['app'][key])
        self.assertEqual(context.scoped_criteria(self.data,'one')['minimumFixed'],original['criteria']['minimumFixed'])
        self.assertTrue(profiles.offer_info(self.data,'one')['searchProfileDeleted'])
        state=view(self.data)
        self.assertEqual([p['id'] for p in state['searchProfiles']],['search-two'])
        self.assertEqual(state['deletedSearchProfiles'][0]['id'],profiles.LEGACY_ID)
        self.manage('restore',id=profiles.LEGACY_ID)
        restored=profiles.get(self.data,profiles.LEGACY_ID)
        for key in ('id','name','searchContext','criteria','revision'):self.assertEqual(restored[key],original[key])
        self.assertEqual(profiles.default_id(self.data),'search-two')
        self.assertEqual(profiles.deleted_profiles(self.data),[])
        self.assertEqual(w.material_versions(self.data),material)

    def test_delete_guards_default_and_searches_with_pending_or_running_work(self):
        with self.assertRaisesRegex(ValueError,'predeterminado'):self.manage('delete',id=profiles.LEGACY_ID)
        self.duplicate()
        pending=self.queue('search-two')
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'búsqueda pendiente'):self.manage('delete',id='search-two')
        self.assertEqual(self.data,before)
        self.start(pending)
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'búsqueda pendiente'):self.manage('delete',id='search-two')
        self.assertEqual(self.data,before)

    def test_deleted_profiles_reject_edits_duplicates_and_new_searches_without_retargeting(self):
        self.duplicate();self.manage('delete',id='search-two')
        before=copy.deepcopy(self.data)
        for action in (lambda:self.edit('search-two',minimumFixed=50000),
                       lambda:self.queue('search-two'),
                       lambda:self.manage('duplicate',id='search-two',newId='search-three',name='TEST copia'),
                       lambda:self.manage('default',id='search-two')):
            with self.assertRaisesRegex(ValueError,'Recupera'):action()
            self.assertEqual(self.data,before)

    def test_deleted_metadata_is_validated_before_accepting_the_record(self):
        self.duplicate()
        for deleted,archived in ((True,w.now()),('sin fecha',w.now()),(w.now(),None)):
            bad=copy.deepcopy(self.data)
            bad['app']['searchProfiles'][1].update(deletedAt=deleted,archivedAt=archived)
            with self.assertRaisesRegex(ValueError,'eliminación'):profiles.validate_model(bad)

    def test_search_result_does_not_borrow_global_coverage_or_another_search_offers(self):
        request=self.start(self.queue())
        request=next(r for r in self.data['app']['requests'] if r['id']==request['id'])
        source={'id':'TEST-source','company':'TEST source'}
        self.data['sourceHealth']={'TEST-source':{'sourceId':'TEST-source','status':'ok','checkedAtUtc':w.now(),'errors':[]}}
        self.data['sheets']['Oportunidades'].append({**self.data['sheets']['Oportunidades'][0],'ID':'TEST-other-search'})
        with patch('personalization.public_sources',return_value=[source]):
            result=w.discovery_result(self.data,request,w.now())
        self.assertEqual(result['scanChecks'],[])
        self.assertEqual(result['health'],[])
        self.assertEqual(result['newOpportunityIds'],[])
        self.assertEqual(result['newOfferCount'],0)
