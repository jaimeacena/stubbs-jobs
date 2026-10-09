"""Shared fictional records and writer helpers; no real registry or personal answers."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import app_workflow as workflow
import stubbs_jobs
import stubbs_jobs_core as core


def interview_choices(data, values):
    """A fictional person confirms the sample and explicitly declines all other fields."""
    import profile_interview
    return {key: {'status': 'provided' if profile_interview.has_value(profile_interview.value(data, values, field)) else 'blank',
                  'proof': 'TEST: la persona ficticia confirma «'+field['label']+'» o decide dejar ese dato en blanco.'}
            for key, field in profile_interview.fields(data).items()}


def fixture():
    row = {'ID': 'one', 'Clave canónica': core.identity('https://example.org/jobs/123-role'),
           'Empresa': 'Example', 'Puesto': 'BI Developer', 'Prioridad': 'A', 'Estado': 'Lista para revisión',
           'URL original': 'https://example.org/jobs/123-role', 'Fuente': 'web', 'Familia': 'BI',
           'Vigencia': 'Sin comprobar', 'Fijo mín. confirmado': None,
           **{condition: 'Pendiente' for condition in stubbs_jobs.CONDITIONS}}
    return {'schemaVersion': 2, 'revision': 0,
            'sheets': {'Oportunidades': [row], 'Entradas': [], 'Evidencias': [], 'Actividad': [], 'Fuentes': []},
            'events': [], 'observations': {}, 'sourceHealth': {}, 'blocks': [], 'historicalApplications': [],
            'historicalReconciliation': {'status': 'pending'}, 'cycles': [], 'profile': {},
            'appliedBatches': [], 'changes': []}


class WorkflowFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'outputs').mkdir()
        (self.root / 'outputs/cv.pdf').write_bytes(b'%PDF-test-one')
        for module in (workflow, stubbs_jobs):
            for name, value in (('ROOT', self.root), ('DATA', self.root / 'data')):
                replacement = patch.object(module, name, value)
                replacement.start()
                self.addCleanup(replacement.stop)
        self.data = fixture()
        self.data['profile'] = {'currentCity': None, 'workPermitWithoutSponsorship': None,
                                'salaryExpectationFixed': None, 'noticeDays': 15, 'minimumFixed': 32000}
        self.row = self.data['sheets']['Oportunidades'][0]
        self.row['CV preparado'] = 'outputs/cv.pdf'
        workflow.seed(self.data)
        workflow.draft(self.data, 'one')['message']='Texto comprobable'
        self.index = 0

    def apply(self, operation):
        self.index += 1
        stubbs_jobs.apply_batch(self.data, {'id': str(self.index), 'operations': [operation]})

    def review(self):
        # The fictional portal explicitly asks the questions used by each case.
        d=workflow.draft(self.data,'one')
        d.setdefault('messageUsage','form')
        d.setdefault('formAnswerKeys',list(d['requiredAnswers']))
        workflow.state(self.data)['selections'].setdefault('one', {'selected': True, 'mode': 'review', 'at': core.now(), 'actor': 'Persona'})
        self.apply({'kind': 'ui-review', 'opportunityId': 'one', 'checks': {key: True for key in workflow.CHECKS},
                    'proof': 'Oferta, destino, CV, formulario y duplicados comprobados.',
                    'fingerprint': workflow.stamp(self.data, 'one')})

    def select_for_request(self):
        workflow.state(self.data)['selections']['one'] = {'selected': True, 'mode': 'review', 'at': core.now(), 'actor': 'Persona'}
