"""Real XLSX export and reopening from synthetic projections; no registry is read."""
import json
import posixpath
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import personalization
import runtime

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def worksheet_rows(path, name):
    """Reopen the saved XLSX and read its stored labels, values and formulas."""
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheet = next(item for item in workbook.findall('m:sheets/m:sheet', NS) if item.get('name') == name)
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(item.get('Target') for item in relationships if item.get('Id') == sheet.get(REL))
        filename = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(item.itertext()) for item in shared.findall('m:si', NS)]
        document = ET.fromstring(archive.read(filename))
        rows = []
        for row in document.findall('m:sheetData/m:row', NS):
            values = {}
            for cell in row.findall('m:c', NS):
                column = ''.join(character for character in cell.get('r') if character.isalpha())
                value = cell.findtext('m:v', None, NS)
                kind = cell.get('t')
                if kind == 's' and value is not None:
                    value = strings[int(value)]
                elif kind == 'inlineStr':
                    value = ''.join(cell.find('m:is', NS).itertext())
                elif kind == 'b' and value is not None:
                    value = value == '1'
                elif kind not in ('str', 'e', 'd') and value is not None:
                    value = float(value)
                values[column] = value
            rows.append({'number': int(row.get('r')), 'values': values})
        return rows


def worksheet_metadata(path, name):
    """Inspect the saved formatting, including auxiliary column visibility."""
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheet = next(item for item in workbook.findall('m:sheets/m:sheet', NS) if item.get('name') == name)
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(item.get('Target') for item in relationships if item.get('Id') == sheet.get(REL))
        filename = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        document = ET.fromstring(archive.read(filename))
        styles = ET.fromstring(archive.read('xl/styles.xml'))
        formats = {0: 'General', 3: '#,##0'}
        formats.update({int(item.get('numFmtId')): item.get('formatCode') for item in styles.findall('m:numFmts/m:numFmt', NS)})
        cell_formats = [formats.get(int(item.get('numFmtId'))) for item in styles.findall('m:cellXfs/m:xf', NS)]
        return {
            'columns': [item.attrib for item in document.findall('m:cols/m:col', NS)],
            'formats': {cell.get('r'): cell_formats[int(cell.get('s', '0'))]
                        for cell in document.findall('m:sheetData/m:row/m:c', NS)},
        }


class ExportTrackerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not runtime.excel_available(PROJECT):
            raise unittest.SkipTest('XLSX opcional: se necesitan Node y artifact-tool en esta instalación; usa CSV o prepara esas dependencias para comprobar Excel')
        cls.node = runtime.node_path()

    def projection(self):
        data = personalization.blank_store()
        row = {key: None for key in personalization.OPPORTUNITY_FIELDS}
        row.update({'ID': 'TEST-one', 'Empresa': 'TEST Example', 'Puesto': 'TEST Analyst',
                    'Fuente': 'TEST-b', 'Prioridad': 'B', 'Estado': 'Pendiente de empresa',
                    'Apta solicitar': 'Pendiente', 'Apta aceptar': 'Pendiente'})
        data['sheets']['Oportunidades'] = [row]
        return data

    def event(self, key, kind, source, hour):
        return {'id': key, 'at': f'2026-10-02T{hour:02}:00:00+00:00', 'type': kind,
                'opportunityId': 'TEST-one', 'source': source, 'proof': 'TEST synthetic history', 'actor': 'Agente'}

    def export(self, data):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        folder = Path(holder.name)
        projection = folder / 'projection.json'
        output = folder / 'TEST.xlsx'
        projection.write_text(json.dumps(data), encoding='utf-8')
        result = subprocess.run([str(self.node), str(PROJECT / 'tools/export-tracker.mjs'), str(projection), str(output)],
                                cwd=PROJECT, capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:] + result.stdout[-4000:])
        self.assertTrue(output.is_file())
        result_data = json.loads(result.stdout.splitlines()[-1])
        self.assertTrue(result_data['reopened'])
        self.assertEqual(json.loads(projection.read_text(encoding='utf-8')), data)
        return output

    def sources(self, output):
        return {row['values']['A']: row['values'] for row in worksheet_rows(output, 'Fuentes') if row['number'] >= 4}

    def test_search_profiles_preserve_one_application_and_context_in_reopened_xlsx(self):
        import copy
        import search_profiles
        import stubbs_jobs as jobs
        data=self.projection()
        data.setdefault('app',{})['setupComplete']=True
        search_profiles.migrate(data)
        first=data['app']['searchProfiles'][0]
        first['name']='TEST BI remoto'
        second=copy.deepcopy(first)
        second.update(id='search-local',name='TEST técnicos locales')
        data['app']['searchProfiles'].append(second)
        key=data['sheets']['Oportunidades'][0]['ID']
        data['app']['offerSearches']={key:[{'requestId':'TEST-search-one','searchProfileId':first['id']},
                                         {'requestId':'TEST-search-two','searchProfileId':second['id']}]}
        original=copy.deepcopy(data)
        projected=jobs.view(data)
        output=self.export(projected)
        rows=worksheet_rows(output,'Oportunidades')
        headers=next(row['values'] for row in rows if row['number']==3)
        offers=[row['values'] for row in rows if row['number']>=4]
        self.assertEqual(len(offers),1)
        values={label:offers[0].get(column) for column,label in headers.items()}
        self.assertEqual(values['ID'],key)
        self.assertEqual(values['Perfil de búsqueda'],'TEST BI remoto')
        self.assertEqual(values['ID perfil de búsqueda'],first['id'])
        self.assertEqual(values['Búsquedas en que apareció'],'TEST BI remoto; TEST técnicos locales')
        self.assertEqual(data,original)

    def test_personal_closure_remains_closed_after_xlsx_export_and_reopening(self):
        import stubbs_jobs as jobs
        data=self.projection();row=data['sheets']['Oportunidades'][0];key=row['ID']
        row['Estado']='Enviada'
        data['events']=[{'id':'TEST-receipt','type':'sent','opportunityId':key,'at':'2026-10-01T10:00:00Z','proof':'TEST: recibo ficticio'}]
        data.setdefault('app',{})['offerArchives']={key:{'outcome':'closed','at':'2026-10-06T10:00:00Z','reason':'TEST: cierre decidido por la persona'}}
        projected=jobs.view(data);self.assertEqual(projected['sheets']['Oportunidades'][0]['Estado'],'Cerrada')
        output=self.export(projected)
        values=[value for item in worksheet_rows(output,'Oportunidades') if item['number']>=4 for value in item['values'].values()]
        self.assertIn('Cerrada',values);self.assertNotIn('Rechazada',values)
        self.assertEqual(row['Estado'],'Enviada')

    def test_observation_figures_survive_export_reopening_and_legacy_import(self):
        import offer_minimums
        import stubbs_jobs as jobs
        from state_support import instant
        data=self.projection()
        row=data['sheets']['Oportunidades'][0]
        row.update({'Fijo ≥32 k€':'No','Fijo mín. confirmado':None})
        data['profile']['minimumFixed']=35000
        data['sheets']['Evidencias']=[
            {'ID oportunidad':row['ID'],'Condición':'Fijo ≥32 k€','Estado':'Sí','Texto o motivo':'TEST anterior',
             'Fuente':'https://example.org/old','Comprobada':jobs.excel_day(),'minimumFixed':35000,'currency':'EUR',
             'observedAt':'2026-10-08T09:00:00+02:00',
             'numericValues':{'fixed':40000,'fixedMax':45000,'currency':'EUR'}},
            {'ID oportunidad':row['ID'],'Condición':'Fijo ≥32 k€','Estado':'No','Texto o motivo':'TEST corrección',
             'Fuente':'https://example.org/new','Comprobada':jobs.excel_day(),'minimumFixed':35000,'currency':'EUR',
             'observedAt':'2026-10-08T18:00:00+02:00',
             'numericValues':{}}]
        output=self.export(data)
        imported=jobs.read_xlsx(output)
        first,second=imported['Evidencias']
        self.assertEqual(json.loads(first['numericValues'])['fixed'],40000)
        self.assertEqual(json.loads(second['numericValues']),{})
        # Excel normalizes ISO dates to UTC; the observation must retain its
        # exact instant, rather than requiring an identical offset spelling.
        self.assertEqual(instant(first['observedAt']),instant('2026-10-08T09:00:00+02:00'))
        self.assertEqual(instant(second['observedAt']),instant('2026-10-08T18:00:00+02:00'))
        data['sheets']=imported
        current=data['sheets']['Oportunidades'][0]
        self.assertIsNone(offer_minimums.current_numbers(data,current)['Fijo mín. confirmado'])
        self.assertFalse(offer_minimums.view(data,current)['canApply'])

    def test_source_change_keeps_all_events_and_attributes_first_milestone_once(self):
        data = self.projection()
        data['sheets']['Fuentes'] = [{'Fuente': 'TEST-a'}, {'Fuente': 'TEST-b'}]
        data['events'] = [self.event('TEST-sent', 'sent', 'TEST-a', 8),
                          self.event('TEST-response-a', 'response', 'TEST-a', 9),
                          self.event('TEST-response-b', 'response', 'TEST-b', 10),
                          self.event('TEST-interview-a', 'interview', 'TEST-a', 11),
                          self.event('TEST-interview-b', 'interview', 'TEST-b', 12)]
        output = self.export(data)
        sources = self.sources(output)
        self.assertEqual({column: sources['TEST-a'][column] for column in ('K', 'M', 'N')}, {'K': 1, 'M': 1, 'N': 1})
        self.assertEqual({column: sources['TEST-b'][column] for column in ('K', 'M', 'N')}, {'K': 0, 'M': 0, 'N': 0})
        events = [row['values'] for row in worksheet_rows(output, 'Eventos') if row['number'] >= 4]
        self.assertEqual([row['A'] for row in events], [event['id'] for event in data['events']])
        self.assertEqual([row['E'] for row in events], [event['source'] for event in data['events']])
        self.assertEqual([row['K'] for row in events], [1, 1, 0, 1, 0])

    def test_unconfigured_recorded_sources_are_visible_without_invented_coverage(self):
        data = self.projection()
        data['sheets']['Fuentes'] = [{'Fuente': 'TEST-configured'}]
        data['sourceHealth'] = {'TEST-checked': {'company': 'TEST checked source', 'checkedAtUtc': '2026-10-02T08:00:00+00:00',
                                               'lastSuccessUtc': None, 'errors': ['TEST recorded issue']}}
        data['sheets']['Entradas'] = [{'Fuente': 'TEST-entry', 'Estado': 'Duplicada', 'Empresa': 'TEST Entry'}]
        data['sheets']['Oportunidades'][0].update({'Fuente': 'TEST-offer', 'Prioridad': 'A'})
        data['events'] = [dict(self.event('TEST-work', 'work', 'TEST-event', 9), minutes=5)]
        output = self.export(data)
        sources = self.sources(output)
        self.assertEqual(set(sources), {'TEST-configured', 'TEST-checked', 'TEST-entry', 'TEST-offer', 'TEST-event'})
        self.assertEqual(sources['TEST-entry']['H'], 1)
        self.assertEqual(sources['TEST-entry']['I'], 1)
        self.assertEqual(sources['TEST-offer']['J'], 1)
        self.assertEqual(sources['TEST-event']['L'], 5)
        for source in ('TEST-entry', 'TEST-offer', 'TEST-event'):
            self.assertTrue(all(sources[source].get(column) in (None, '') for column in ('B', 'C', 'D', 'E', 'F', 'G')))
        self.assertEqual(sources['TEST-checked']['G'], 'TEST recorded issue')

    def test_source_names_are_literal_case_sensitive_and_counts_survive_reopening(self):
        data = self.projection()
        names = ['=TEST-source', 'TEST*', 'TEST?', 'TEST', 'test']
        base = data['sheets']['Oportunidades'][0]
        data['sheets']['Oportunidades'] = [dict(base, ID=f'TEST-{index}', Fuente=source, Prioridad='A')
                                          for index, source in enumerate(names)]
        data['sheets']['Entradas'] = [{'Fuente': source, 'Estado': 'Duplicada' if index % 2 else 'Nueva'}
                                     for index, source in enumerate(names) for _ in range(index + 1)]
        data['events'] = [dict(self.event(f'TEST-work-{index}', 'work', source, 9),
                               opportunityId=f'TEST-{index}', minutes=index + 1)
                          for index, source in enumerate(names)]
        output = self.export(data)
        sources = self.sources(output)
        self.assertEqual(set(sources), set(names))
        for index, source in enumerate(names):
            self.assertEqual(sources[source]['H'], index + 1)
            self.assertEqual(sources[source]['I'], index + 1 if index % 2 else 0)
            self.assertEqual(sources[source]['J'], 1)
            self.assertEqual(sources[source]['L'], index + 1)
        events = [row['values'] for row in worksheet_rows(output, 'Eventos') if row['number'] >= 4]
        self.assertEqual([row['E'] for row in events], names)
        for sheet in ('Entradas', 'Oportunidades', 'Eventos', 'Fuentes'):
            self.assertTrue(any(column.get('hidden') == '1' or float(column.get('width', 1)) == 0
                                for column in worksheet_metadata(output, sheet)['columns']), sheet)

    def test_later_currency_and_extension_columns_survive_without_profile_inference(self):
        data = self.projection()
        first = data['sheets']['Oportunidades'][0]
        first.pop('Moneda fijo confirmado', None)
        first['Fijo mín. confirmado'] = 32000
        first['Fijo máx. confirmado'] = 35000
        data['sheets']['Oportunidades'].extend([
            dict(first, ID='TEST-usd', **{'Moneda fijo confirmado': 'USD', 'TEST extension': 'TEST preserved USD'}),
            dict(first, ID='TEST-chf', **{'Moneda fijo confirmado': 'CHF', 'TEST extension': 'TEST preserved CHF'}),
        ])
        # No declared header list: the first migrated record predates currency.
        data.pop('opportunityFields', None)
        for profile_currency in ('EUR', 'GBP'):
            with self.subTest(profile_currency=profile_currency):
                data['profile']['currency'] = profile_currency
                data['app']['criteria']['currency'] = profile_currency
                output = self.export(data)
                rows = worksheet_rows(output, 'Oportunidades')
                header = next(row['values'] for row in rows if row['number'] == 3)
                currency_column = next(column for column, name in header.items() if name == 'Moneda fijo confirmado')
                extra_column = next(column for column, name in header.items() if name == 'TEST extension')
                saved = {row['number']: row['values'] for row in rows if row['number'] >= 4}
                self.assertIn(saved[4].get(currency_column), (None, ''))
                self.assertEqual(saved[5][currency_column], 'USD')
                self.assertEqual(saved[6][currency_column], 'CHF')
                self.assertEqual(saved[5][extra_column], 'TEST preserved USD')
                self.assertEqual(saved[6][extra_column], 'TEST preserved CHF')
                metadata = worksheet_metadata(output, 'Oportunidades')
                for name in ('Fijo mín. confirmado', 'Fijo máx. confirmado'):
                    column = next(column for column, value in header.items() if value == name)
                    self.assertEqual(metadata['formats'][f'{column}4'], '#,##0')
                    self.assertEqual(metadata['formats'][f'{column}5'], '#,##0 "USD"')
                    self.assertEqual(metadata['formats'][f'{column}6'], '#,##0 "CHF"')

    def test_declared_columns_keep_later_extensions(self):
        data = self.projection()
        first = data['sheets']['Oportunidades'][0]
        data['opportunityFields'] = list(first)
        data['sheets']['Oportunidades'].append(dict(first, ID='TEST-second', **{'TEST extension': 'TEST later value'}))
        rows = worksheet_rows(self.export(data), 'Oportunidades')
        header = next(row['values'] for row in rows if row['number'] == 3)
        column = next(column for column, name in header.items() if name == 'TEST extension')
        self.assertEqual(next(row['values'][column] for row in rows if row['number'] == 5), 'TEST later value')

    def test_reordered_columns_reopen_using_the_actual_identifier_column(self):
        data = self.projection()
        fields = list(data['sheets']['Oportunidades'][0])
        data['opportunityFields'] = [name for name in fields if name != 'ID'] + ['ID']
        rows = worksheet_rows(self.export(data), 'Oportunidades')
        header = next(row['values'] for row in rows if row['number'] == 3)
        column = next(column for column, name in header.items() if name == 'ID')
        self.assertNotEqual(column, 'A')
        self.assertEqual(next(row['values'][column] for row in rows if row['number'] == 4), 'TEST-one')

    def test_missing_sources_and_auxiliary_header_collision_preserve_original_values(self):
        data = self.projection()
        first = data['sheets']['Oportunidades'][0]
        first.pop('Fuente')
        first['Clave fuente (vista)'] = 'TEST original offer column'
        first['Prioridad'] = 'A'
        data['sheets']['Oportunidades'].extend([
            dict(first, ID='TEST-no-source', Fuente=None), dict(first, ID='TEST-literal-null', Fuente='null'),
        ])
        data['sheets']['Fuentes'] = [{'Fuente': 'TEST'}, {'Fuente': 'null'}]
        data['sheets']['Entradas'] = [
            {'Estado': 'Nueva', 'Clave fuente (vista)': 'TEST original entry column'},
            {'Estado': 'Nueva', 'Fuente': None}, {'Estado': 'Nueva', 'Fuente': 'null'},
            {'Estado': 'Nueva', 'Fuente': 'TEST'},
        ]
        data['events'] = [dict(self.event('TEST-present', 'work', 'TEST', 9), minutes=5),
                          dict(self.event('TEST-null', 'work', None, 10), minutes=9),
                          dict(self.event('TEST-missing', 'work', None, 11), minutes=11),
                          dict(self.event('TEST-literal', 'work', 'null', 12), minutes=13)]
        data['events'][2].pop('source')
        output = self.export(data)
        sources = self.sources(output)
        self.assertEqual(set(sources), {'TEST', 'null'})
        self.assertEqual((sources['TEST']['H'], sources['TEST']['J'], sources['TEST']['L']), (1, 0, 5))
        self.assertEqual((sources['null']['H'], sources['null']['J'], sources['null']['L']), (1, 1, 13))
        for sheet, original in [('Entradas', 'TEST original entry column'), ('Oportunidades', 'TEST original offer column')]:
            rows = worksheet_rows(output, sheet)
            header = next(row['values'] for row in rows if row['number'] == 3)
            self.assertEqual(len(header.values()), len(set(header.values())))
            column = next(column for column, name in header.items() if name == 'Clave fuente (vista)')
            self.assertEqual(next(row['values'][column] for row in rows if row['number'] == 4), original)


if __name__ == '__main__':
    unittest.main()
