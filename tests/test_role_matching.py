"""Role matching for any profession: fictional titles, no network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import scan_boards as s


class RoleMatching(unittest.TestCase):
    def assertMatches(self, roles, titles):
        for title in titles:
            with self.subTest(title=title):
                self.assertIsNotNone(s.role_match(title, '', roles))

    def assertRejects(self, roles, titles):
        for title in titles:
            with self.subTest(title=title):
                self.assertIsNone(s.role_match(title, '', roles))

    def test_spanish_gender_and_number_forms(self):
        self.assertMatches('Enfermera general', ['Enfermero/a general', 'Enfermero(a) general', 'ENFERMEROS GENERALES', 'Enfermer@ general'])
        self.assertMatches('Camarera', ['Camarero/a', 'Camarero de sala', 'Camareros'])
        self.assertMatches('Profesora de inglés', ['Profesor/a de Inglés', 'Profesores de inglés'])

    def test_common_occupations_across_languages(self):
        self.assertMatches('Auxiliar de enfermería', ['Nursing Assistant'])
        self.assertMatches('Camarera', ['Waiter'])
        self.assertMatches('Contable', ['Accountant', 'Contador público'])
        self.assertMatches('Profesora de inglés', ['English Teacher'])
        self.assertMatches('Ayudante de cocina', ['Kitchen Assistant'])

    def test_unrelated_titles_stay_out(self):
        self.assertRejects('Enfermera general', ['Auxiliar administrativo', 'Licenciada en Derecho'])
        self.assertRejects('Camarera', ['Cocinero', 'Dependiente/a'])
        self.assertRejects('Auxiliar de enfermería', ['Auxiliar administrativo', 'Sales Assistant'])

    def test_technical_roles_keep_their_behaviour(self):
        self.assertEqual(s.role_match('Analista de datos', '', 'Data Analyst'), 'direct')
        self.assertEqual(s.role_match('Backend Developer', '', 'Ingeniero de software'), 'direct')
        self.assertIsNone(s.role_match('Data Entry Clerk', 'Enter customer records.', 'Data Analyst'))


if __name__ == '__main__':
    unittest.main()
