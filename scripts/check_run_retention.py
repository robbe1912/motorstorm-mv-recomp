"""Authored retention safety checks; never touches real runs."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import psutil
import prune_runs as retention


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / '.git').mkdir()
        self.root = self.repo / 'temp/runs'
        self.root.mkdir(parents=True)
        self.old = self.run_dir('20200101T000000.000000Z')
        self.new = self.run_dir('20990101T000000.000000Z')
        self.live = patch.object(retention, 'native_live', return_value=False)
        self.live.start()

    def tearDown(self):
        self.live.stop()
        self.tmp.cleanup()

    def run_dir(self, name):
        p = self.root / name
        p.mkdir()
        (p / 'launch.json').write_text(json.dumps(dict(pid=2147483647,create_time=0,exe_sha256='0'*64,elf_sha256='1'*64)))
        (p / 'final.json').write_text(json.dumps(dict(reason='explicit stop marker')))
        (p / 'native.log').write_text('authored fixture log\n')
        (p / 'rsx/frame_01').mkdir(parents=True)
        (p / 'rsx/frame_01/backbuffer.bmp').write_bytes(b'authored disposable capture fixture')
        (p / 'rsx/frame_01/manifest.txt').write_text('authored metadata\n')
        return p

    def plan(self):
        return retention.plan(self.repo)

    def eligible(self):
        return {x['run'] for x in self.plan()['eligible']}

    def test_default_keeps_newest_ten(self):
        self.assertFalse(self.eligible())

    def old_plan(self):
        return retention.plan(self.repo, keep=1)

    def test_dry_run_does_not_remove(self):
        self.assertEqual([x['run'] for x in self.old_plan()['eligible']], [self.old.name])
        self.assertTrue(self.old.exists())

    def test_archive_metadata_before_pruning(self):
        receipts = retention.apply(self.old_plan())
        self.assertFalse(self.old.exists())
        self.assertTrue(self.new.exists())
        with zipfile.ZipFile(receipts[0]['metadata_archive']) as z:
            self.assertEqual(z.read('native.log').decode().splitlines(), ['authored fixture log'])
            self.assertIn('rsx/frame_01/manifest.txt', z.namelist())
            self.assertNotIn('rsx/frame_01/backbuffer.bmp', z.namelist())
            self.assertIsNone(z.testzip())

    def test_doc_reference(self):
        (self.repo / 'docs').mkdir()
        (self.repo / 'docs/proof.md').write_text(f'temp/runs/{self.old.name}/rsx/frame_01/backbuffer.bmp')
        self.assertFalse(self.old_plan()['eligible'])

    def test_root_readme_reference(self):
        (self.repo / 'README.md').write_text(self.old.name)
        self.assertFalse(self.old_plan()['eligible'])

    def test_authored_source_not_disposable(self):
        (self.old / 'analysis.py').write_text('# authored source\n')
        self.assertFalse(self.old_plan()['eligible'])

    def test_profile_reference(self):
        (self.repo / 'temp/profile.json').write_text(json.dumps(dict(steps=[dict(reference=str(self.old / 'rsx/frame_01/backbuffer.bmp'))])))
        self.assertFalse(self.old_plan()['eligible'])

    def test_keep_marker(self):
        (self.old / '.keep').write_text('needed')
        self.assertFalse(self.old_plan()['eligible'])

    def test_unique_dump(self):
        (self.old / 'snapshot.dmp').write_bytes(b'authored')
        self.assertFalse(self.old_plan()['eligible'])

    def test_external_profile_pin(self):
        report = retention.plan(self.repo, keep=1, extra_pins=[self.old.name])
        self.assertFalse(report['eligible'])

    def test_unexpected_exit(self):
        (self.old / 'final.json').write_text(json.dumps(dict(reason='guest process exited; inspect logs for outcome')))
        self.assertFalse(self.old_plan()['eligible'])

    def test_fatal_evidence(self):
        (self.old / 'native.err').write_text('FATAL ERROR: authored fixture')
        self.assertFalse(self.old_plan()['eligible'])

    def test_failed_replay(self):
        (self.old / 'menu-replay.json').write_text(json.dumps(dict(error='authored failure')))
        self.assertFalse(self.old_plan()['eligible'])

    def test_unfinalized(self):
        (self.old / 'final.json').unlink()
        self.assertFalse(self.old_plan()['eligible'])

    def test_live_native(self):
        with patch.object(retention, 'native_live', return_value=True):
            self.assertFalse(self.old_plan()['eligible'])

    def test_live_recorded_pid(self):
        data = json.loads((self.old / 'launch.json').read_text())
        data.update(pid=os.getpid(), create_time=psutil.Process().create_time())
        (self.old / 'launch.json').write_text(json.dumps(data))
        self.assertFalse(self.old_plan()['eligible'])

    def test_new_pin_invalidates_stale_plan(self):
        report = self.old_plan()
        (self.old / '.keep').write_text('new pin')
        self.assertEqual(retention.apply(report), [])
        self.assertTrue(self.old.exists())

    def test_archive_failure_never_prunes(self):
        with patch.object(retention.zipfile, 'ZipFile', side_effect=OSError('authored archive failure')):
            with self.assertRaises(OSError):
                retention.apply(self.old_plan())
        self.assertTrue((self.old / 'native.log').exists())

    def test_junction_or_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            sentinel = Path(outside) / 'source.txt'
            sentinel.write_text('must survive')
            link = self.old / 'external'
            if os.name == 'nt':
                command = "New-Item -ItemType Junction -Path '%s' -Target '%s' | Out-Null" % (str(link).replace("'", "''"), outside.replace("'", "''"))
                subprocess.run(['powershell', '-NoProfile', '-Command', command], check=True)
            else:
                link.symlink_to(outside, target_is_directory=True)
            try:
                self.assertFalse(self.old_plan()['eligible'])
                self.assertEqual(sentinel.read_text(), 'must survive')
            finally:
                if os.name == 'nt':
                    link.rmdir()
                else:
                    link.unlink()


if __name__ == '__main__':
    unittest.main()
