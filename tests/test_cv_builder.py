"""CV adapted to one offer from the confirmed profile (build-cv). Fictional data only."""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_fixtures import WorkflowFixture
import app_workflow as w
import build_cv
import stubbs_jobs
import stubbs_jobs_core as core

PROFILE = '''Perfil profesional
Analista de datos ficticio con experiencia en BI comercial y automatización de informes.

Habilidades
Técnicas: Power BI, Power Query, SQL, Excel y Python básico.

Experiencia profesional
Analista de datos sénior | Acme Analytics
Marzo de 2023 – actualidad
Business Intelligence para Ventas y Logística.
- Diseñé 14 informes de Power BI para Ventas y Logística.
- Automaticé el cierre mensual con Power Query y redujo el trabajo manual en tres días.
- Coordinación con equipos de Chile y Portugal.
- Formación interna en SQL a nuevos analistas.

Consultor junior | Nube Consultores
Enero de 2020 – febrero de 2023
- Cuadros de mando en Excel para pymes del sector turístico.
- Limpieza de datos de facturación con SQL.

Proyectos personales
Faro – Panel de calidad del aire con Python y datos abiertos.
Brújula – Planificador de rutas en bicicleta. (oculto)

Proyectos ocultos
Secreto – Prototipo privado de reconocimiento de voz.

Formación
Grado en Matemáticas – Universidad Ficticia | 2015–2019

Certificaciones
Certificado ficticio de SQL | 2022

Idiomas
Español: nativo · Inglés: B2
'''

REASON = 'TEST: resumen y viñetas de Power BI y SQL ordenados según el anuncio ficticio.'


def spec(**changes):
    value = {
        'language': 'es', 'cvReason': REASON,
        'summary': 'Analista de datos con experiencia en Power BI, Power Query y SQL para Ventas y Logística.',
        'highlights': ['Power BI', 'Power Query', 'SQL', 'Excel'],
        'experience': [
            {'title': 'Analista de datos sénior', 'company': 'Acme Analytics', 'dates': 'Marzo de 2023 – actualidad',
             'bullets': ['Diseñé 14 informes de Power BI para Ventas y Logística.',
                         'Formación interna en SQL a nuevos analistas.']},
            {'title': 'Consultor junior', 'company': 'Nube Consultores', 'dates': 'Enero de 2020 – febrero de 2023',
             'bullets': ['Limpieza de datos de facturación con SQL.']}],
        'projects': [{'name': 'Faro', 'text': 'Panel de calidad del aire con Python y datos abiertos.'}],
        'education': ['Grado en Matemáticas – Universidad Ficticia | 2015–2019'],
        'certifications': ['Certificado ficticio de SQL | 2022'],
        'languages': 'Español: nativo · Inglés: B2'}
    value.update(changes)
    return value


class ValidationTests(unittest.TestCase):
    def rejects(self, pattern, **changes):
        with self.assertRaisesRegex(ValueError, pattern):
            build_cv.validate(spec(**changes), PROFILE)

    def test_accepts_facts_from_the_profile_in_the_chosen_order(self):
        content = build_cv.validate(spec(experience=list(reversed(spec()['experience']))), PROFILE)
        self.assertEqual([r['company'] for r in content['experience']], ['Nube Consultores', 'Acme Analytics'])

    def test_rejects_skills_tools_metrics_and_roles_not_in_the_profile(self):
        self.rejects('Tableau', highlights=['Power BI', 'Tableau'])
        self.rejects('Snowflake', summary='Analista con experiencia en Power BI y Snowflake.')
        self.rejects('10', summary='Analista con 10 años de experiencia en Power BI.')
        role = dict(spec()['experience'][0], title='Directora de datos')
        self.rejects('no consta en el perfil con ese título', experience=[role])
        role = dict(spec()['experience'][0], bullets=['Lideré un equipo de ocho personas en Acme Analytics.'])
        self.rejects('no consta', experience=[role])

    def test_bullets_come_from_their_own_role_and_condensing_adds_nothing(self):
        role = dict(spec()['experience'][1], bullets=['Diseñé 14 informes de Power BI para Ventas y Logística.'])
        self.rejects('para este puesto', experience=[role])
        own = 'Automaticé el cierre mensual con Power Query y redujo el trabajo manual en tres días.'
        role = dict(spec()['experience'][0], bullets=[{'from': own, 'text': 'Cierre mensual automatizado con Power Query: cinco días menos.'}])
        self.rejects('5', experience=[role])
        role = dict(spec()['experience'][0], bullets=[{'from': own, 'text': 'Cierre mensual automatizado con Power Query y Airflow.'}])
        self.rejects('Airflow', experience=[role])
        role = dict(spec()['experience'][0], bullets=[{'from': own, 'text': 'Cierre mensual automatizado con Power Query: tres días menos.'}])
        build_cv.validate(spec(experience=[role]), PROFILE)

    def test_at_most_six_bullets_per_role(self):
        bullet = 'Coordinación con equipos de Chile y Portugal.'
        role = dict(spec()['experience'][0], bullets=[bullet] * 7)
        self.rejects('máximo es 6', experience=[role])

    def test_hidden_projects_are_never_used(self):
        self.rejects('no consta', projects=[{'name': 'Brújula'}])
        self.rejects('no consta', projects=[{'name': 'Secreto'}])
        self.rejects('oculto «Secreto»', summary='Analista de datos; prototipo Secreto con Python.')
        with self.assertRaisesRegex(ValueError, 'oculto «Bloque»'):
            build_cv.validate(spec(summary='Analista de datos; proyecto Bloque.'), PROFILE + '\nBloque – Juego. (hidden)\n')
        markdown = '## Proyectos ocultos\n\n- Bloque – Juego.\n- Nido: app privada.\n\n## Otros\nFaro – visible.\n'
        self.assertEqual(build_cv.Profile(markdown).hidden, ['Bloque', 'Nido'])
        self.assertIn('Faro – visible.', build_cv.Profile(markdown).text)
        # Hidden in private/profile.md although the app's experience still lists it.
        with self.assertRaisesRegex(ValueError, 'oculto «Faro»'):
            build_cv.validate(spec(), PROFILE, extra_hidden=('Faro',))

    def test_english_translation_needs_a_declared_source_for_new_names(self):
        role = {'title': {'from': 'Analista de datos sénior', 'text': 'Senior Data Analyst'},
                'company': 'Acme Analytics', 'dates': {'from': 'Marzo de 2023 – actualidad', 'text': 'March 2023 – Present'},
                'bullets': [{'from': 'Diseñé 14 informes de Power BI para Ventas y Logística.',
                             'text': 'Designed 14 Power BI reports for Sales and Logistics.'}]}
        english = dict(language='en', experience=[role], summary='Data analyst with Power BI and SQL.', projects=[],
                       education=[], certifications=[], languages={'from': 'Español: nativo · Inglés: B2', 'text': 'Spanish: native · English: B2'})
        with self.assertRaisesRegex(ValueError, 'Sales'):
            build_cv.validate(spec(**english), PROFILE)
        glossary = {'Data': 'datos', 'Analyst': 'Analista', 'Sales': 'Ventas', 'Logistics': 'Logística', 'English': 'Inglés'}
        content = build_cv.validate(spec(glossary=glossary, **english), PROFILE)
        self.assertEqual(content['experience'][0]['dates'], 'March 2023 – Present')
        with self.assertRaisesRegex(ValueError, 'Python'):
            build_cv.validate(spec(**{**english, 'glossary': {**glossary, 'Python': 'Power BI'},
                                      'highlights': [{'from': 'SQL', 'text': 'Python'}]}), PROFILE)

    def test_reason_language_and_unknown_fields_are_required(self):
        self.rejects('cvReason', cvReason='Adaptado.')
        self.rejects('language', language='fr')
        self.rejects('no admitidos', salary='40 k€')


class RegistryTests(WorkflowFixture, unittest.TestCase):
    def setUp(self):
        WorkflowFixture.setUp(self)
        replacement = patch.object(build_cv, 'ROOT', self.root)
        replacement.start()
        self.addCleanup(replacement.stop)
        w.state(self.data)['experience'] = PROFILE
        w.state(self.data)['searchContext'] = {'name': 'Alex Ficticio'}
        self.data['profile'].update(email='alex@example.org', phone='+34 600 000 000', currentCity='Ciudad Ficticia')
        other = copy.deepcopy(self.row)
        other.update({'ID': 'two', 'Empresa': 'Otra Ficticia', 'Clave canónica': core.identity('https://example.org/jobs/456-other'),
                      'URL original': 'https://example.org/jobs/456-other'})
        self.data['sheets']['Oportunidades'].append(other)
        w.draft(self.data, 'two')
        self.data['sheets']['Oportunidades'][0]['CV preparado'] = 'outputs/cv.pdf'

    def test_registers_a_one_page_pdf_assigns_it_and_declares_adapted(self):
        result = build_cv.register(self.data, 'one', spec())
        row = w.row_for(self.data, 'one')
        self.assertEqual(row['CV preparado'], result['cv'])
        self.assertTrue(result['cv'].startswith('outputs/cv/') and (self.root / result['cv']).is_file())
        library = self.data['app']['cvLibrary']
        self.assertEqual([item['path'] for item in library], [result['cv']])
        self.assertEqual(library[0]['name'], 'CV Alex Ficticio - Example.pdf')
        d = w.draft(self.data, 'one')
        self.assertEqual((d['cvAdaptation'], d['cvReason']), ('adapted', REASON))
        self.assertIsNone(w.cv_adaptation_issue(self.data, 'one'))
        # No «review the CV you added» change: it comes from the confirmed profile.
        self.assertFalse([r for r in self.data['app']['requests'] if r['type'] == 'change'])
        import pypdfium2
        pdf = pypdfium2.PdfDocument((self.root / result['cv']).read_bytes())
        try:
            self.assertEqual(len(pdf), 1)
            text = pdf[0].get_textpage().get_text_range()
        finally:
            pdf.close()
        self.assertIn('Alex Ficticio', text)
        self.assertIn('Diseñé 14 informes', text)
        self.assertNotIn('Brújula', text)

    def test_each_offer_gets_its_own_pdf_and_repeating_is_idempotent(self):
        first = build_cv.register(self.data, 'one', spec())
        again = build_cv.register(self.data, 'one', spec())
        self.assertEqual(first['cvHash'], again['cvHash'])
        self.assertFalse(again['changed'])
        second = build_cv.register(self.data, 'two', spec())
        self.assertNotEqual(first['cvHash'], second['cvHash'])
        self.assertEqual(len(self.data['app']['cvLibrary']), 2)
        self.assertIsNone(w.cv_adaptation_issue(self.data, 'two'))

    def test_rejected_adaptation_changes_nothing(self):
        before = copy.deepcopy(self.data)
        with self.assertRaises(ValueError):
            build_cv.register(self.data, 'one', spec(highlights=['Tableau']))
        self.assertEqual(self.data, before)
        self.assertFalse((self.root / 'outputs/cv').exists())

    def test_sent_or_closed_offers_keep_their_cv(self):
        self.data['events'].append({'type': 'sent', 'opportunityId': 'one'})
        with self.assertRaisesRegex(ValueError, 'enviada'):
            build_cv.register(self.data, 'one', spec())
        w.row_for(self.data, 'two')['Estado'] = 'Cerrada'
        with self.assertRaisesRegex(ValueError, 'cerrada'):
            build_cv.register(self.data, 'two', spec())

    def test_bullets_longer_than_one_line_and_overflowing_pages_are_rejected(self):
        long = {'from': 'Automaticé el cierre mensual con Power Query y redujo el trabajo manual en tres días.',
                'text': 'Automaticé el cierre mensual con Power Query y redujo el trabajo manual en tres días, ' * 2}
        role = dict(spec()['experience'][0], bullets=[long])
        with self.assertRaisesRegex(ValueError, 'una línea'):
            build_cv.build(self.data, 'one', spec(experience=[role]))
        roles = [dict(spec()['experience'][0], bullets=['Coordinación con equipos de Chile y Portugal.'] * 6)] * 1
        many = spec(experience=roles, education=['Grado en Matemáticas – Universidad Ficticia | 2015–2019'] * 60)
        with self.assertRaisesRegex(ValueError, 'páginas'):
            build_cv.build(self.data, 'one', many)

    def test_missing_name_is_not_guessed(self):
        w.state(self.data)['searchContext'] = {'name': ''}
        with self.assertRaisesRegex(ValueError, 'nombre'):
            build_cv.build(self.data, 'one', spec())

    def test_command_preview_writes_only_the_chosen_file(self):
        folder = self.root / 'cli'
        (folder / 'tools').mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / 'tools'
        for path in source.glob('*.py'):
            if 'conflict' not in path.name.lower():
                (folder / 'tools' / path.name).write_bytes(path.read_bytes())
        (folder / 'data').mkdir()
        data = copy.deepcopy(self.data)
        (folder / 'data/registry.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        (folder / 'adaptacion.json').write_text(json.dumps(spec(), ensure_ascii=False), encoding='utf-8')
        before = (folder / 'data/registry.json').read_bytes()
        # The portable runtime ignores the script folder (python._pth): put the copy first
        # so the command never reads the real registry.
        bootstrap = ("import runpy,sys;sys.path.insert(0,sys.argv[1]);script=sys.argv[2];"
                     "sys.argv=[script,*sys.argv[3:]];runpy.run_path(script,run_name='__main__')")
        result = subprocess.run([sys.executable, '-B', '-c', bootstrap, str(folder / 'tools'),
                                 str(folder / 'tools/stubbs_jobs.py'), 'build-cv', '--case', 'one',
                                 '--file', str(folder / 'adaptacion.json'), '--preview', str(folder / 'vista.pdf')],
                                cwd=folder, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['registered'])
        self.assertTrue((folder / 'vista.pdf').read_bytes().startswith(b'%PDF-'))
        self.assertEqual((folder / 'data/registry.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
