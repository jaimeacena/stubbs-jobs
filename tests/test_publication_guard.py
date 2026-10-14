"""Shared packages never carry values from a personal installation: fictional data only."""
import json
import runpy
import tempfile
import unittest
from pathlib import Path

SHARE = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'tools/build-share.py'))


class PublicationGuard(unittest.TestCase):
    def test_terms_come_from_registry_and_private_denylist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'private').mkdir()
            (root / 'data/registry.json').write_text(json.dumps({
                'profile': {'email': 'persona.ficticia@example.org', 'phone': '+34 600 000 000', 'address': ''},
                'app': {'searchContext': {'name': 'Ana Ficticia Prueba'}}}), encoding='utf-8')
            (root / 'private/publication-denylist.txt').write_text('# comentario\nEMPRESA-INTERNA-42\n', encoding='utf-8')
            terms = SHARE['personal_terms'](root)
            self.assertIn('persona.ficticia@example.org', terms)
            self.assertIn('Ficticia', terms)
            self.assertIn('EMPRESA-INTERNA-42', terms)
            self.assertNotIn('Ana', terms)

    def test_guard_rejects_leaks_and_allows_public_author_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            (package / 'docs').mkdir()
            (package / 'runtime').mkdir()
            (package / 'README.md').write_text('Creado por [jaimeacena](https://github.com/jaimeacena).', encoding='utf-8')
            (package / 'runtime/ignored.txt').write_text('Ficticia', encoding='utf-8')
            self.assertEqual(SHARE['assert_no_personal_data'](package, ['Ficticia', 'jaimeacena@example.org']), [])
            (package / 'docs/guide.md').write_text('Contacto: Ficticia', encoding='utf-8')
            with self.assertRaises(ValueError):
                SHARE['assert_no_personal_data'](package, ['Ficticia'])
            # Words containing a term are not leaks of that term.
            (package / 'docs/guide.md').write_text('Ficticiamente', encoding='utf-8')
            self.assertEqual(SHARE['assert_no_personal_data'](package, ['Ficticia']), [])

    def test_private_replacements_are_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(SHARE['replace_private']('Texto', 'tools', Path(tmp)), 'Texto')
            (Path(tmp) / 'private').mkdir()
            (Path(tmp) / 'private/publication-replacements.json').write_text('{"app": {"Persona": "Usuario"}}', encoding='utf-8')
            self.assertEqual(SHARE['replace_private']('Pendiente de Persona', 'app', Path(tmp)), 'Pendiente de Usuario')


if __name__ == '__main__':
    unittest.main()
