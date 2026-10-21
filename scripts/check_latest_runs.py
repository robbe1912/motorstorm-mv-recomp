"""Authored filesystem regressions for explicit count-based retention."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import prune_latest_runs as retention
import check_run_retention as conservative


class LatestRunsTests(unittest.TestCase):
    setUp = conservative.RetentionTests.setUp
    tearDown = conservative.RetentionTests.tearDown
    run_dir = conservative.RetentionTests.run_dir
    def test_only_five_regardless_of_age_or_old_evidence(self):
        (self.old / 'snapshot.bin').write_bytes(b'old diagnostic payload')
        report = retention.plan(self.repo)
        self.assertEqual(len(report['kept']), 5)
        self.assertEqual(len(report['eligible']), 6)
        removed = retention.apply(report)
        self.assertEqual(len(removed), 6)
        self.assertEqual(len(list(self.root.iterdir())), 5)
        with zipfile.ZipFile(removed[-1]['archive']) as archive:
            self.assertIn('launch.json', archive.namelist())
            self.assertNotIn('snapshot.bin', archive.namelist())
            self.assertNotIn('rsx/frame_01/backbuffer.bmp', archive.namelist())

    def test_live_native_disables_count_cleanup(self):
        with patch('prune_runs.native_live', return_value=True), patch.object(retention, 'native_live', return_value=True):
            self.assertEqual(retention.plan(self.repo)['eligible'], [])

    def test_arriving_native_prevents_deletion(self):
        report = retention.plan(self.repo)
        with patch.object(retention, 'native_live', return_value=True):
            self.assertEqual(retention.apply(report), [])
        self.assertTrue(self.old.exists())

    def test_count_must_be_positive_integer(self):
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                retention.plan(self.repo, invalid)

    def test_replay_images_survive_count_cleanup(self):
        reference = self.old / 'rsx/frame_01/backbuffer.bmp'
        original = reference.read_bytes()
        profile = self.repo / 'temp/profile.json'
        profile.write_text(json.dumps({'steps': [{'reference': str(reference), 'reference_variants': [str(reference)]}]}))
        retention.preserve_profile(self.repo, profile)
        retention.apply(retention.plan(self.repo))
        data = json.loads(profile.read_text())['steps'][0]
        self.assertEqual(Path(data['reference']).read_bytes(), original)
        self.assertEqual(data['reference_variants'], [data['reference']])
        self.assertFalse(self.old.exists())

    def test_missing_reference_stops_before_cleanup(self):
        profile = self.repo / 'temp/profile.json'
        profile.write_text(json.dumps({'reference': str(self.old / 'missing.bmp')}))
        with self.assertRaises(FileNotFoundError):
            retention.preserve_profile(self.repo, profile)
        self.assertTrue(self.old.exists())

    def test_local_policy_dispatches_actual_maintenance(self):
        policy = self.repo / 'temp/run-retention-policy.json'
        policy.write_text(json.dumps({'mode': 'latest', 'keep': 5}))
        conservative.retention.automatic(self.repo)
        self.assertEqual(len(list(self.root.iterdir())), 5)

    def test_archive_failure_does_not_delete_count_candidate(self):
        report = retention.plan(self.repo)
        with patch.object(retention.zipfile, 'ZipFile', side_effect=OSError('authored failure')):
            with self.assertRaises(OSError):
                retention.apply(report)
        self.assertTrue((self.old / 'native.log').exists())

    def test_count_junction_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            sentinel = Path(outside) / 'input'
            sentinel.write_text('private input')
            link = self.old / 'outside'
            import os, subprocess
            if os.name == 'nt':
                subprocess.run(['powershell', '-NoProfile', '-Command',
                                "New-Item -ItemType Junction -Path '%s' -Target '%s' | Out-Null" % (link, outside)], check=True)
            else:
                link.symlink_to(outside, target_is_directory=True)
            try:
                with self.assertRaises(ValueError):
                    retention.plan(self.repo)
                self.assertEqual(sentinel.read_text(), 'private input')
            finally:
                link.rmdir() if os.name == 'nt' else link.unlink()


if __name__ == '__main__':
    unittest.main()
