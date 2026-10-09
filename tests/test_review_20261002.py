"""Fresh audit regressions. Synthetic files and records only."""
import copy
import inspect
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext
import xml.etree.ElementTree as ET

from workflow_fixtures import WorkflowFixture, fixture
import stubbs_jobs as j
import stubbs_jobs_core as core
import stubbs_jobs_app as server
import runtime
import app_workflow as workflow
import agent_runner


class WorkRecordTests(WorkflowFixture, unittest.TestCase):
    def test_generic_user_can_record_measured_work_without_personal_name(self):
        self.data['app']['personalized'] = True
        self.apply({'kind': 'event', 'event': {'id': 'TEST-work', 'type': 'work',
                    'opportunityId': 'one', 'at': core.now(), 'proof': 'TEST measured five minutes',
                    'minutes': 5, 'actor': 'Usuario'}})
        self.assertEqual(self.data['events'][0]['actor'], 'Usuario')
        self.assertEqual(self.data['events'][0]['minutes'], 5)

    def test_unknown_work_actor_and_unmeasured_time_still_rejected(self):
        for actor, minutes in [('Empresa', 5), ('Usuario', -1), ('Agente', None)]:
            with self.subTest(actor=actor, minutes=minutes):
                before = copy.deepcopy(self.data)
                with self.assertRaises(ValueError):
                    self.apply({'kind': 'event', 'event': {'id': 'TEST-invalid', 'type': 'work',
                                'opportunityId': 'one', 'at': core.now(), 'proof': 'TEST',
                                'minutes': minutes, 'actor': actor}})
                self.assertEqual(self.data, before)


class InterfaceOwnershipTests(WorkflowFixture, unittest.TestCase):
    def test_ui_write_does_not_inherit_a_fixed_agent_snapshot(self):
        with patch.object(agent_runner, 'read_state', return_value={'status': 'idle'}), \
             patch.object(agent_runner, 'view', return_value={'status': 'idle'}):
            self.apply({'kind': 'ui-request', 'type': 'discovery'})
            request_id = workflow.state(self.data)['requests'][-1]['id']
            with workflow.execution_owner('TEST-owner'), workflow.execution_scope([request_id]):
                self.apply({'kind': 'ui-request-update', 'id': request_id,
                            'status': 'running', 'proof': 'TEST agent started'})
            baseline = copy.deepcopy(workflow.state(self.data)['requests'])
            for variable in ('CODEX_THREAD_ID', 'STUBBS_JOBS_EXECUTION_ID', 'STUBBS_JOBS_RUN_ID'):
                with self.subTest(variable=variable), \
                     patch.dict(os.environ, {variable: 'TEST-owner'}), \
                     patch.object(server, 'lock', side_effect=nullcontext), \
                     patch.object(server, 'read_store', side_effect=lambda: copy.deepcopy(self.data)), \
                     patch.object(j, 'recover_export'), patch.object(server, 'save_store'):
                    result = server.transact({'id': 'TEST-interface-' + variable,
                        'operations': [{'kind': 'ui-seen', 'at': core.now(), 'actor': 'Usuario'}]})
                    self.assertEqual(workflow.state(result)['requests'], baseline)
                    self.assertIsNotNone(workflow.state(result)['seenAt'])
                    self.assertEqual(workflow.execution_id(), 'TEST-owner')
                    # Merely claiming to be Usuario must not bypass the agent writer.
                    with self.assertRaisesRegex(ValueError, 'instantánea'):
                        self.apply({'kind': 'ui-seen', 'at': core.now(), 'actor': 'Usuario'})


class LegacyWorkbookTests(unittest.TestCase):
    def workbook(self, root, opportunity_header=5, missing=None):
        main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        package = 'http://schemas.openxmlformats.org/package/2006/relationships'
        book = ET.Element('workbook', xmlns=main)
        sheets = ET.SubElement(book, 'sheets')
        links = ET.Element('Relationships', xmlns=package)
        path = root / 'TEST-migration.xlsx'
        names = ['Fuentes', 'Actividad', 'Evidencias', 'Entradas', 'Oportunidades']
        with zipfile.ZipFile(path, 'w') as archive:
            for index, name in enumerate(names):
                if name == missing:
                    continue
                reference = f'TEST-r{index}'
                target = f'worksheets/TEST-{index}.xml'
                ET.SubElement(sheets, 'sheet', name=name, sheetId=str(index + 1),
                              attrib={f'{{{rel}}}id': reference})
                # Exercise both absolute package paths and relative relationships.
                ET.SubElement(links, 'Relationship', Id=reference,
                              Target='/xl/' + target if index % 2 else target,
                              Type=rel + '/worksheet')
                sheet = ET.Element('worksheet', xmlns=main)
                grid = ET.SubElement(sheet, 'sheetData')
                header = opportunity_header if name == 'Oportunidades' else 3
                fields = {'Oportunidades': ['Empresa', 'ID', 'URL original', 'Prioridad', 'Estado'],
                          'Entradas': ['Empresa', 'ID entrada', 'URL', 'Fuente'],
                          'Evidencias': ['Texto o motivo', 'ID oportunidad', 'Condición'],
                          'Actividad': ['Resultado / prueba', 'Fecha', 'Acción'],
                          'Fuentes': ['Tipo', 'Fuente']}[name]
                for row_number, values in [(header, fields), (header + 1, [None, 'TEST-' + name] + ['TEST'] * (len(fields) - 2))]:
                    row = ET.SubElement(grid, 'row', r=str(row_number))
                    for column, value in enumerate(values):
                        if value is None:
                            continue
                        cell = ET.SubElement(row, 'c', r=chr(65 + column) + str(row_number), t='inlineStr')
                        ET.SubElement(ET.SubElement(cell, 'is'), 't').text = value
                archive.writestr('xl/' + target, ET.tostring(sheet))
            archive.writestr('xl/workbook.xml', ET.tostring(book))
            archive.writestr('xl/_rels/workbook.xml.rels', ET.tostring(links))
        return path

    def test_named_sheets_and_rows_survive_reordering_and_empty_first_column(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for header in (3, 5):
                with self.subTest(header=header):
                    result = j.read_xlsx(self.workbook(root, header))
                    self.assertEqual(result['Oportunidades'][0]['ID'], 'TEST-Oportunidades')
                    self.assertIsNone(result['Oportunidades'][0]['Empresa'])
                    self.assertEqual(result['Entradas'][0]['ID entrada'], 'TEST-Entradas')
                    self.assertEqual(result['Fuentes'][0]['Fuente'], 'TEST-Fuentes')
                    self.assertEqual(result['Actividad'][0]['Fecha'], 'TEST-Actividad')
                    self.assertEqual(len(result['Evidencias']), 1)

    def test_missing_named_sheet_has_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Evidencias'):
                j.read_xlsx(self.workbook(Path(directory), missing='Evidencias'))


class ExportRecoveryTests(unittest.TestCase):
    def test_externally_emptied_workbook_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / 'TEST.xlsx'
            book.write_bytes(b'')
            data = fixture()
            data.update(workbookHash=core.digest(b'TEST previously exported workbook'))
            with patch.object(j, 'ROOT', root), patch.object(j, 'DATA', root / 'data'), \
                 patch.object(j, 'WORKBOOK', book), patch.object(j, 'lock', side_effect=nullcontext), \
                 patch.object(j, 'read_store', side_effect=lambda: copy.deepcopy(data)), \
                 patch.object(j, 'recover_export'), \
                 patch.object(j.subprocess, 'run', side_effect=AssertionError('No debe iniciarse la exportación')) as run:
                with self.assertRaisesRegex(ValueError, 'cambió externamente'):
                    j.export()
                run.assert_not_called()
            self.assertEqual(book.read_bytes(), b'')

    def test_expected_empty_workbook_is_archived_before_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / 'TEST.xlsx'
            book.write_bytes(b'')
            data = fixture()
            data.update(createdAt=core.now(), updatedAt=core.now(),
                        workbookHash=core.digest(b''), workbookRevision=0)
            def render(arguments, **kwargs):
                Path(arguments[-1]).write_bytes(b'TEST rendered workbook')
            with patch.object(j, 'ROOT', root), patch.object(j, 'DATA', root / 'data'), \
                 patch.object(j, 'WORKBOOK', book), patch.object(j, 'lock', side_effect=nullcontext), \
                 patch.object(j, 'read_store', side_effect=lambda: copy.deepcopy(data)), \
                 patch.object(j, 'recover_export'), patch.object(j, 'save_store'), \
                 patch.object(j.subprocess, 'run', side_effect=render):
                j.export()
            backup = root / 'data/workbook-backups' / (core.digest(b'') + '.xlsx')
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.read_bytes(), b'')
            self.assertEqual(book.read_bytes(), b'TEST rendered workbook')

    def test_completed_export_recovers_its_content_version_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / 'TEST.xlsx'
            book.write_bytes(b'TEST exported workbook')
            data = fixture()
            data.update(revision=4, workbookHash='TEST-old', workbookContentHash='TEST-old-content')
            fingerprint = j.export_fingerprint(data)
            core.atomic_json(root / 'export-receipt.json',
                             {'revision': 4, 'newHash': core.digest(book.read_bytes()),
                              'contentHash': fingerprint})
            def save(value):
                value['revision'] += 1
            with patch.object(j, 'DATA', root), patch.object(j, 'WORKBOOK', book), \
                 patch.object(j, 'save_store', side_effect=save) as saved:
                j.recover_export(data)
                j.recover_export(data)
            self.assertEqual(saved.call_count, 1)
            self.assertEqual(data['workbookContentHash'], fingerprint)
            self.assertEqual(data['workbookRevision'], 5)
            with patch.object(server, 'EXPORT_STATUS', root / 'no-status.json'), \
                 patch.object(server, 'WORKBOOK', book):
                self.assertEqual(server.export_view(data)['status'], 'ok')


# The generic edition starts with init and deliberately disables the personal Excel migration.
PERSONAL_MIGRATION = 'datos históricos de otra persona' not in inspect.getsource(j.migrate)


@unittest.skipUnless(PERSONAL_MIGRATION, 'La edición genérica empieza con init; no migra un Excel personal')
class MigrationValidationTests(unittest.TestCase):
    def test_invalid_workbook_is_preserved_and_never_published_as_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / 'TEST-invalid.xlsx'
            original = b'TEST original workbook'
            book.write_bytes(original)
            sheets = fixture()['sheets']
            sheets['Oportunidades'][0]['Prioridad'] = 'B'
            sheets['Oportunidades'].append(copy.deepcopy(sheets['Oportunidades'][0]))
            with patch.object(j, 'DATA', root / 'data'), patch.object(j, 'STORE', root / 'data/registry.json'), \
                 patch.object(j, 'WORKBOOK', book), patch.object(j, 'read_xlsx', return_value=sheets), \
                 patch.object(j, 'save_store') as save:
                with self.assertRaisesRegex(ValueError, 'duplicados'):
                    j.migrate()
                save.assert_not_called()
            self.assertEqual(book.read_bytes(), original)
            self.assertEqual((root / 'data/migration' / (core.digest(original) + '.xlsx')).read_bytes(), original)

    def test_real_fictional_export_reopens_and_migrates_without_losing_records(self):
        project = Path(__file__).resolve().parents[1]
        if not runtime.excel_available(project):
            self.skipTest('La integración Excel requiere Node y artifact-tool disponibles')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = fixture()
            data.update(createdAt=core.now(), updatedAt=core.now())
            data['sheets']['Oportunidades'][0]['Prioridad'] = 'B'
            data['sheets']['Oportunidades'][0]['Fuente'] = 'TEST-web'
            data['sheets']['Entradas'] = [{'ID entrada': 'TEST-entry', 'Fuente': 'TEST-web',
                'Empresa': 'TEST empresa', 'Puesto': 'TEST puesto', 'URL': 'https://example.org/jobs/456-test',
                'Primera vista': j.excel_day(), 'Publicada': None, 'Estado': 'Nueva',
                'Clave canónica': core.identity('https://example.org/jobs/456-test')}]
            data['sheets']['Evidencias'] = [{'ID oportunidad': 'one', 'Condición': 'Indefinido',
                'Estado': 'Pendiente', 'Texto o motivo': 'TEST sin confirmar',
                'Fuente': 'https://example.org/jobs/123-role', 'Comprobada': j.excel_day()}]
            data['sheets']['Actividad'] = [{'Fecha': j.excel_day(), 'ID oportunidad': 'one',
                'Acción': 'TEST consulta ficticia', 'Resultado / prueba': 'TEST sin efecto externo'}]
            data['sheets']['Fuentes'] = [{'Fuente': 'TEST-web', 'Tipo': 'TEST pública'}]
            projection = j.view(data)
            source = root / 'TEST-projection.json'
            source.write_text(json.dumps(projection), encoding='utf-8')
            book = root / 'TEST.xlsx'
            result = subprocess.run([str(runtime.node_path()), str(project / 'tools/export-tracker.mjs'),
                                     str(source), str(book)], cwd=project, capture_output=True,
                                    text=True, encoding='utf-8', timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            self.assertTrue(json.loads(result.stdout.splitlines()[-1])['reopened'])
            raw = book.read_bytes()
            extracted = j.read_xlsx(book)
            for name, original in projection['sheets'].items():
                self.assertEqual(len(extracted[name]), len(original), name)
                for expected, actual in zip(original, extracted[name]):
                    for key, value in expected.items():
                        if value == '' and not isinstance(value, bool):
                            self.assertIn(actual.get(key), (None, ''), (name, key))
                        else:
                            self.assertEqual(actual.get(key), value, (name, key))
            with patch.object(j, 'ROOT', root), patch.object(j, 'DATA', root / 'data'), \
                 patch.object(j, 'STORE', root / 'data/registry.json'), patch.object(j, 'WORKBOOK', book), \
                 patch.object(j, 'save_store', side_effect=lambda value: core.save_store(value, root / 'data/registry.json')):
                migrated = j.migrate()
            saved = core.read_store(root / 'data/registry.json')
            self.assertEqual(saved['sheets'], migrated['sheets'])
            for name in ('Entradas', 'Evidencias', 'Actividad', 'Fuentes'):
                self.assertEqual(migrated['sheets'][name], extracted[name])
            self.assertEqual(migrated['sheets']['Oportunidades'][0]['ID'], 'one')
            self.assertEqual(migrated['sheets']['Oportunidades'][0]['Empresa'], 'Example')
            self.assertEqual(book.read_bytes(), raw)
            self.assertEqual((root / 'data/migration' / (core.digest(raw) + '.xlsx')).read_bytes(), raw)
            self.assertEqual(json.loads((root / 'data/migration/original-sheets.json').read_text(encoding='utf-8')), extracted)
            self.assertEqual(len(list((root / 'previews').glob('*.png'))), 9)


if __name__ == '__main__':
    unittest.main()
