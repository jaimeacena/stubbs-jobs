"""Portable runtime identity checks use synthetic executables and never run them."""
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
SHARE = runpy.run_path(str(PROJECT / 'tools/build-share.py'))


class DistributionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name) / 'runtime'
        self.runtime.mkdir()
        for name in ('python.exe', 'pythonw.exe'):
            (self.runtime / name).write_bytes(b'TEST synthetic executable; must never run')

    def probe(self, details=None, code=0):
        return subprocess.CompletedProcess([], code, stdout=json.dumps(details), stderr='TEST diagnostic')

    def test_runtime_metadata_is_checked_without_importing_application_or_dependencies(self):
        details = {'version': SHARE['PORTABLE_PYTHON_VERSION'], 'platform': 'win-amd64'}
        with patch.object(SHARE['subprocess'], 'run', return_value=self.probe(details)) as process:
            self.assertEqual(SHARE['inspect_portable_runtime'](self.runtime), details['version'])
        command = process.call_args.args[0]
        self.assertEqual(command[:5], [str(self.runtime / 'python.exe'), '-I', '-S', '-B', '-c'])
        self.assertEqual(process.call_args.kwargs['timeout'], 10)

    def test_incomplete_runtime_is_rejected_before_starting_a_probe_or_creating_destination(self):
        (self.runtime / 'pythonw.exe').unlink()
        destination = Path(self.temp.name) / 'portable'
        with patch.object(SHARE['subprocess'], 'run') as process:
            with self.assertRaisesRegex(ValueError, 'ejecutables'):
                SHARE['build'](destination, self.runtime)
            process.assert_not_called()
        self.assertFalse(destination.exists())

    def test_wrong_version_architecture_failed_or_malformed_probe_never_creates_a_bundle(self):
        cases = [self.probe({'version': '3.12.14', 'platform': 'win-amd64'}),
                 self.probe({'version': SHARE['PORTABLE_PYTHON_VERSION'], 'platform': 'win32'}),
                 self.probe({'version': SHARE['PORTABLE_PYTHON_VERSION'], 'platform': 'win-arm64'}),
                 self.probe(None, code=1), subprocess.CompletedProcess([], 0, stdout='TEST not JSON', stderr='')]
        for index, result in enumerate(cases):
            destination = Path(self.temp.name) / ('portable-' + str(index))
            with self.subTest(index=index), patch.object(SHARE['subprocess'], 'run', return_value=result):
                with self.assertRaises(ValueError):
                    SHARE['build'](destination, self.runtime)
            self.assertFalse(destination.exists())
            self.assertFalse(Path(str(destination) + '.zip').exists())

    def test_runtime_probe_timeout_or_unavailable_process_is_an_explicit_error(self):
        for error in (subprocess.TimeoutExpired('TEST', 10), OSError('TEST unavailable process')):
            with self.subTest(error=type(error).__name__), patch.object(SHARE['subprocess'], 'run', side_effect=error):
                with self.assertRaisesRegex(ValueError, 'comprobar la identidad'):
                    SHARE['inspect_portable_runtime'](self.runtime)

    def test_public_generic_builder_keeps_the_runtime_identity_guard(self):
        source = runpy.run_path(str(PROJECT / 'tools/build-source.py'))
        text = source['generic_builder']((PROJECT / 'tools/build-share.py').read_text(encoding='utf-8'))
        namespace = {'__file__': str(PROJECT / 'tools/build-share.py'), '__name__': 'TEST_generic_builder'}
        exec(compile(text, 'TEST generic builder', 'exec'), namespace)
        details = {'version': SHARE['PORTABLE_PYTHON_VERSION'], 'platform': 'win-amd64'}
        with patch.object(namespace['subprocess'], 'run', return_value=self.probe(details)):
            self.assertEqual(namespace['inspect_portable_runtime'](self.runtime), details['version'])
        (self.runtime / 'pythonw.exe').unlink()
        with self.assertRaisesRegex(ValueError, 'ejecutables'):
            namespace['inspect_portable_runtime'](self.runtime)


if __name__ == '__main__':
    unittest.main()
