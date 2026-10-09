"""Display translations do not change advertised requirements or reviewed materials."""
import copy
import unittest
from unittest.mock import patch
from workflow_fixtures import WorkflowFixture
import app_context as c
import app_workflow as w
import personalization as p
import offer_minimums
import stubbs_jobs_app as app
import view_cache

class OfferDisplayTests(WorkflowFixture,unittest.TestCase):
    def setUp(self):
        WorkflowFixture.setUp(self)
        self.data['updatedAt']=w.now()

    def test_a_checked_translation_changes_only_reading_and_preserves_original_material(self):
        row=w.row_for(self.data,'one');row['Puesto']='Analista de Dados - Trabalho Remoto'
        self.review()
        original=row['Puesto'];before=copy.deepcopy(self.data)
        material=w.stamp(self.data,'one');fit=c.fit_stamp(self.data,row);cv=c.cv_stamp(self.data,'one');minimums=offer_minimums.view(self.data,row)
        self.apply({'kind':'opportunity','id':'one','values':{'Puesto traducido':'Analista de datos — trabajo remoto'},'proof':'TEST: traducción fiel del título; no contiene requisitos de idioma.'})
        row=w.row_for(self.data,'one')
        self.assertEqual(row['Puesto'],original)
        self.assertEqual(w.stamp(self.data,'one'),material)
        self.assertEqual(c.fit_stamp(self.data,row),fit)
        self.assertEqual(c.cv_stamp(self.data,'one'),cv)
        self.assertEqual(offer_minimums.view(self.data,row),minimums)
        self.assertEqual(self.data['app']['packages'],before['app']['packages'])
        self.assertEqual(self.data['app']['requests'],before['app']['requests'])
        self.assertEqual(self.data['events'],before['events'])
        with patch.object(app,'ROOT',self.root),patch.object(app,'WORKBOOK',self.root/'none.xlsx'),patch.object(p,'public_sources',return_value=[]),view_cache.snapshot():
            state=app.build_state(copy.deepcopy(self.data),include_export=False,include_instructions=False)
        self.assertEqual(state['opportunities'][0]['title'],'Analista de datos — trabajo remoto')
        self.assertEqual(state['opportunities'][0]['originalTitle'],original)
        self.apply({'kind':'opportunity','id':'one','values':{'Puesto traducido':None},'proof':'TEST: retirar la traducción de presentación sin alterar la fuente.'})
        self.assertEqual(p.display_title(w.row_for(self.data,'one')),original)

    def test_invalid_display_translations_or_missing_proof_are_atomic(self):
        for value,proof in [('Analista',None),('Analista',True),('', 'TEST'),('   ','TEST'),(True,'TEST'),('x'*301,'TEST')]:
            before=copy.deepcopy(self.data)
            with self.assertRaises(ValueError):self.apply({'kind':'opportunity','id':'one','values':{'Puesto traducido':value,'País':'Otro país'},'proof':proof})
            self.assertEqual(self.data,before)

    def test_changed_offer_facts_invalidate_legacy_approval_without_rewriting_the_package(self):
        self.row.update({'País':'Canadá','Modalidad':'Remoto','Contrato':'Indefinido'})
        self.review()
        fingerprint=w.stamp(self.data,'one')
        self.apply({'kind':'ui-approve','opportunityId':'one','fingerprint':fingerprint})
        package=copy.deepcopy(self.data['app']['packages'][0])
        folder=self.root/'data/packages'/package['id']
        files={p.name:p.read_bytes() for p in folder.iterdir()}
        self.apply({'kind':'opportunity','id':'one','values':{'País':'Estados Unidos'},'proof':'TEST: el anuncio limita ahora el puesto a Estados Unidos.'})
        self.assertNotEqual(w.stamp(self.data,'one'),fingerprint)
        self.assertIn('Revisión final del agente',w.readiness(self.data,'one'))
        send=next(r for r in self.data['app']['requests'] if r['type']=='send')
        self.assertEqual(send['status'],'cancelled')
        self.assertEqual(self.data['app']['packages'][0]['payload'],package['payload'])
        self.assertEqual({p.name:p.read_bytes() for p in folder.iterdir()},files)

    def test_explicit_offer_facts_affect_material_but_absent_fields_preserve_legacy_payload(self):
        original=w.stamp(self.data,'one')
        for key,value in [('País','Canadá'),('Modalidad','Remoto'),('Contrato','Temporal')]:
            self.row[key]=value
            self.assertNotEqual(w.stamp(self.data,'one'),original,key)
            del self.row[key]
        self.assertEqual(w.stamp(self.data,'one'),original)

    def test_promotion_cannot_bypass_the_display_translation_contract(self):
        self.data['sheets']['Entradas'].append({'ID entrada':'new','ID oportunidad':None,'Clave canónica':'new','Empresa':'Empresa ficticia','Puesto':'Original','URL':'https://example.org/jobs/new','Fuente':'test'})
        before=copy.deepcopy(self.data)
        with self.assertRaises(ValueError):self.apply({'kind':'promote','entryId':'new','values':{'Prioridad':'B','Siguiente paso':'Comprobar','Puesto traducido':True},'reason':'TEST fuente comprobada','proof':'TEST traducción.'})
        self.assertEqual(self.data,before)
