"""Bounded registry history: fictional copies in a temporary folder only."""
import gzip
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import stubbs_jobs_core as core


def copy(folder, index, age_days):
    name = f'{index:064x}.json.gz'
    path = folder / name
    path.write_bytes(gzip.compress(b'{}'))
    moment = time.time() - age_days * 86400
    os.utime(path, (moment, moment))
    return name


class SnapshotRetention(unittest.TestCase):
    def test_keeps_recent_daily_referenced_and_conflict_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'snapshots'
            folder.mkdir()
            # Twenty copies today, then three per day for older days.
            today = [copy(folder, index, index / 10000) for index in range(20)]
            older = {day: [copy(folder, 1000 + day * 10 + n, day + n / 100) for n in range(3)] for day in range(1, 6)}
            ancient = copy(folder, 9000, 400)
            referenced = copy(folder, 9001, 401)
            conflict = folder / 'abc [conflicted].json.gz'
            conflict.write_bytes(b'x')
            current = json.dumps({'lastOpportunityReset': {'backupSha256': referenced[:64]}}).encode()
            removed = set(core.prune_snapshots(tmp, current, {'keepRecent': 5, 'keepDailyDays': 90}))
            remaining = {p.name for p in folder.iterdir()}
            self.assertTrue(set(today[:5]) <= remaining)
            for copies in older.values():
                self.assertIn(copies[0], remaining)
                self.assertTrue(set(copies[1:]) <= removed)
            self.assertIn(ancient, removed)
            self.assertIn(referenced, remaining)
            self.assertIn(conflict.name, remaining)

    def test_save_store_bounds_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / 'registry.json'
            core.atomic_json(store, {'schemaVersion': 2, 'revision': 0})
            data = core.read_store(store)
            for _ in range(130):
                data['value'] = data['revision']
                core.save_store(data, store)
            copies = [p for p in (Path(tmp) / 'snapshots').iterdir()]
            self.assertLessEqual(len(copies), core.snapshot_policy()['keepRecent'] + 1)
            self.assertEqual(core.read_store(store)['revision'], 130)


if __name__ == '__main__':
    unittest.main()
