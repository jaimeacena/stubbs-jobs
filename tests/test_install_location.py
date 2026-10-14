"""Cloud-synced installation folders are reported, never blocked: fictional paths only."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import runtime


class InstallLocation(unittest.TestCase):
    def test_known_sync_folders_are_named(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            for variable in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
                os.environ.pop(variable, None)
            for folder, name in (('OneDrive - Empresa', 'OneDrive'), ('Dropbox', 'Dropbox'), ('Google Drive', 'Google Drive')):
                path = Path(tmp) / folder / 'Stubbs Jobs'
                path.mkdir(parents=True)
                self.assertEqual(runtime.synced_folder(path), name)
            local = Path(tmp) / 'StubbsJobs'
            local.mkdir()
            self.assertIsNone(runtime.synced_folder(local))
            self.assertIsNone(runtime.synced_folder(Path(tmp) / 'Megaproyecto'))

    def test_onedrive_environment_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'Personal'
            (base / 'Escritorio' / 'Stubbs Jobs').mkdir(parents=True)
            with patch.dict(os.environ, {'OneDrive': str(base)}):
                self.assertEqual(runtime.synced_folder(base / 'Escritorio' / 'Stubbs Jobs'), 'OneDrive')

    def test_doctor_reports_warning_without_failing(self):
        root = Path(__file__).resolve().parents[1]
        with patch.object(runtime, 'synced_folder', return_value='Dropbox'):
            report = runtime.doctor(root)
        self.assertEqual(report['syncedFolder'], 'Dropbox')
        self.assertTrue(report['warnings'])


if __name__ == '__main__':
    unittest.main()
