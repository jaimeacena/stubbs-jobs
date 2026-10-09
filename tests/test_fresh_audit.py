"""Reproduced regressions from the fresh audit; fictional isolated state only."""
import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import app_workflow as w
import stubbs_jobs as j
import stubbs_jobs_app as server


class FormAndExportTests(WorkflowFixture, unittest.TestCase):
    def field(self, scope='global'):
        return {'key':'custom_language','label':'Idioma de trabajo','type':'text','scope':scope}

    def test_task_summary_cannot_overwrite_a_newer_summary_in_the_same_second(self):
        w.request(self.data,None,'discovery')
        request=w.state(self.data)['requests'][-1]
        original=request['updatedAt']
        with patch.object(w,'now',return_value=original):
            self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':original,
                        'summary':'Primera instrucción confirmada','need':'other'})
            request=w.state(self.data)['requests'][-1]
            first=request['updatedAt'];self.assertNotEqual(first,original)
            before=copy.deepcopy(self.data)
            with self.assertRaises(w.Conflict):
                self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':original,
                            'summary':'Instrucción obsoleta','need':'access'})
            self.assertEqual(self.data,before)
            self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':first,
                        'summary':'Segunda instrucción actual','need':'other'})
        request=w.state(self.data)['requests'][-1]
        self.assertGreater(request['updatedAt'],first)
        self.assertEqual(request['status'],'queued')
        self.assertNotIn('startedAt',request)
        self.assertNotIn('executionId',request)

    def test_summary_of_legacy_completed_work_preserves_its_activity_date(self):
        w.request(self.data,None,'discovery')
        request=w.state(self.data)['requests'][-1]
        original='2026-09-01T12:00:00+00:00'
        request.update(status='done',updatedAt=original,result='Resultado ficticio acreditado en septiembre')
        request.pop('activityAt',None)
        self.apply({'kind':'ui-request-summary','id':request['id'],'expectedUpdatedAt':original,
                    'summary':'Explicación más clara del resultado anterior','need':'other'})
        request=w.state(self.data)['requests'][-1]
        self.assertEqual(request['activityAt'],original)
        self.assertNotEqual(request['updatedAt'],original)
        self.assertEqual(request['status'],'done')
        self.assertEqual(request['result'],'Resultado ficticio acreditado en septiembre')

    def test_optional_form_answer_is_editable_in_its_declared_scope(self):
        for scope in ('global','opportunity'):
            with self.subTest(scope=scope):
                data=copy.deepcopy(self.data)
                field={**self.field(scope),'key':'custom_optional_'+scope}
                j.apply_batch(data,{'id':'declare-'+scope,'operations':[{'kind':'ui-draft','opportunityId':'one',
                    'values':{'questions':[field],'formAnswerKeys':[field['key']]},
                    'expected':{'questions':None,'formAnswerKeys':None}}]})
                j.apply_batch(data,{'id':'answer-'+scope,'operations':[{'kind':'ui-responses','opportunityId':'one',
                    'values':{field['key']:'Respuesta opcional'},'expected':{field['key']:None}}]})
                target=data['profile'] if scope=='global' else w.draft(data,'one')['answers']
                self.assertEqual(target[field['key']],'Respuesta opcional')
                self.assertEqual(w.payload(data,'one')['answers'][field['key']],'Respuesta opcional')
                self.assertEqual(w.draft(data,'one')['requiredAnswers'],[])
                before=copy.deepcopy(data)
                with self.assertRaises(w.Conflict):
                    j.apply_batch(data,{'id':'stale-'+scope,'operations':[{'kind':'ui-responses','opportunityId':'one',
                        'values':{field['key']:'No debe sobrescribir'},'expected':{field['key']:None}}]})
                self.assertEqual(data,before)

    def test_declared_unused_or_unknown_question_is_not_editable(self):
        field={**self.field('opportunity'),'key':'custom_unused'}
        self.apply({'kind':'ui-draft','opportunityId':'one','values':{'questions':[field]},'expected':{'questions':None}})
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'Pregunta desconocida'):
            self.apply({'kind':'ui-responses','opportunityId':'one','values':{'custom_unused':'Dato no solicitado'},'expected':{'custom_unused':None}})
        self.assertEqual(self.data,before)
        # A malformed legacy key is not made valid by its appearance in the form list.
        w.draft(self.data,'one')['formAnswerKeys']=['custom_undeclared']
        before=copy.deepcopy(self.data)
        with self.assertRaisesRegex(ValueError,'Pregunta desconocida'):
            self.apply({'kind':'ui-responses','opportunityId':'one','values':{'custom_undeclared':'Dato'},'expected':{'custom_undeclared':None}})
        self.assertEqual(self.data,before)

    def test_missing_workbook_is_pending_even_when_last_export_was_current(self):
        path=self.root/'export.json';path.write_text('{"status":"ok"}',encoding='utf-8')
        self.data['workbookContentHash']=j.export_fingerprint(self.data)
        before=copy.deepcopy(self.data)
        with patch.object(server,'EXPORT_STATUS',path),patch.object(server,'WORKBOOK',self.root/'missing.xlsx'):
            result=server.export_view(self.data)
        self.assertEqual(result['status'],'pending')
        self.assertIn('Excel',result['message'])
        self.assertEqual(self.data,before)

class FreshProtocolTests(unittest.TestCase):
    def setUp(self):
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)

    def fetch(self,path,body=None,headers=None):
        request=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
        try:
            with urllib.request.urlopen(request) as response:return response.status,dict(response.headers),response.read()
        except urllib.error.HTTPError as response:
            with response:return response.code,dict(response.headers),response.read()

    def test_non_ascii_invalid_cookie_is_rejected_without_breaking_connection(self):
        status,_,_=self.fetch('/api/state',headers={'Cookie':server.COOKIE+'="\\351"'})
        self.assertEqual(status,401)


if __name__=='__main__':unittest.main()
