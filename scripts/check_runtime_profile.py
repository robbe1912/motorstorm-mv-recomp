"""Payload-free #149 checks of profile admission, the build wrapper and launcher.

Run: python scripts/check_runtime_profile.py (psutil from requirements.txt).
Optional historical source check: --historical-runtime PATH_TO_PINNED_TOOLKIT, or
--fetch-historical to fetch just its capability source (explicit skip if unreachable).
Native process creation and compilation are intercepted; no game runs.
"""
import argparse
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import project
import run as launcher
import runtime_profile as profile

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_ROOT = None
HISTORICAL_BLOB = '506da3f99dbfa7576dda3d0d53d9d859643e54fb'
CURATED = 'void authored(void) { if (getenv("SPU_PM_INTERP")) return; }\n'
UNSUPPORTED = 'void authored(void) { return; }\n'


class ExecutionProfileTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'temp/self-tests/runtime-profile'
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='authored-', dir=base)
        self.root = Path(self.tmp.name)
        self.addCleanup(self.cleanup_owned, base.resolve())
        self.exe = self.root / 'build/native/ms1_recomp.exe'
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b'authored inert executable identity; never executed')
        self.cfg = {k: self.root / k for k in ('elf', 'ffmpeg', 'userdata', 'disc', 'generated')}
        self.cfg['elf'].write_bytes(b'authored target identity; no original program')
        self.source = self.root / 'vendor/ps3recomp'
        self.write_source(self.source, CURATED)
        self.record = dict(path=str(self.exe), sha256=hashlib.sha256(self.exe.read_bytes()).hexdigest(),
                           elf_sha256=hashlib.sha256(self.cfg['elf'].read_bytes()).hexdigest(),
                           **profile.runtime_identity(self.source))
        self.save_record()

    def cleanup_owned(self, base):
        if self.root.resolve().parent != base or self.root.is_symlink() or getattr(self.root, 'is_junction', lambda: False)():
            raise RuntimeError('refusing cleanup outside the owned test directory')
        self.tmp.cleanup()

    def write_source(self, root, text):
        path = root / profile.CAPABILITY_SOURCE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def save_record(self):
        (self.exe.parent / 'build_identity.json').write_text(json.dumps(self.record), encoding='utf-8')

    def launch(self, *options):
        self.calls = []
        self.prune = Mock(side_effect=getattr(self, 'prune_effect', None))
        child = SimpleNamespace(pid=2147483647, returncode=0, poll=lambda: 0)
        def boundary(*args, **kwargs):
            self.calls.append((args, kwargs))
            return child
        with ExitStack() as stack:
            for obj, name, value in [
                (launcher, 'ROOT', self.root), (launcher, 'config', lambda: self.cfg),
                (launcher.psutil, 'process_iter', lambda *a: []),
                (launcher.psutil, 'disk_usage', lambda *a: SimpleNamespace(free=32*1024**3)),
                (launcher.psutil, 'Process', lambda *a: SimpleNamespace(create_time=lambda: 123.5)),
                (launcher.subprocess, 'Popen', boundary),
                (launcher.subprocess, 'STARTUPINFO', lambda: SimpleNamespace(dwFlags=0)),
                (launcher.subprocess, 'STARTF_USESHOWWINDOW', 1),
                (launcher.subprocess, 'CREATE_NO_WINDOW', 0),
            ]:
                stack.enter_context(patch.object(obj, name, value, create=True))
            stack.enter_context(patch('prune_runs.automatic', self.prune))
            stack.enter_context(patch('prune_latest_runs.automatic'))
            stack.enter_context(patch.object(sys, 'argv', ['run.py', '--seconds', '1', *options]))
            stack.enter_context(patch.dict(os.environ, {'SPU_PM_INTERP': '1', 'SPU_WP': '1',
                                                      'SPU_PM_UNKNOWN_RESUME': '1', 'FLOW_FSDBG': '1'}))
            with redirect_stdout(io.StringIO()):
                launcher.main()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0][0], [str(self.exe.resolve()), str(self.cfg['elf'])])
        paths = list((self.root / 'temp/runs').glob('*/launch.json'))
        self.assertEqual(len(paths), 1)
        launch = json.loads(paths[0].read_text())
        final = json.loads(paths[0].with_name('final.json').read_text())
        for key in ('execution_profile', 'execution_environment', 'build_identity', 'exe_sha256'):
            self.assertEqual(launch[key], final[key])
        return launch, self.calls[0][1]['env']

    def rejected(self, message, *options):
        with self.assertRaisesRegex(SystemExit, message):
            self.launch(*options)
        self.assertEqual(self.calls, [])
        self.prune.assert_not_called()
        self.assertFalse((self.root / 'temp/runs').exists())

    def test_actual_curated_source_supports_baseline(self):
        self.assertEqual(profile.runtime_capabilities(ROOT / 'vendor/ps3recomp'), {'policy_interpreter': True})

    def test_comments_do_not_advertise_support(self):
        self.write_source(self.source, '// getenv("SPU_PM_INTERP")\n/* getenv("SPU_PM_INTERP") */\n' + UNSUPPORTED)
        self.assertEqual(profile.runtime_capabilities(self.source), {'policy_interpreter': False})

    def test_default_baseline_exact_environment_and_record(self):
        record, env = self.launch()
        expected = {'SPU_PM_INTERP': '1', 'SPU_PROBE_INTERP': '0', **{k: '0' for k in profile.DISABLED_PROBES}}
        self.assertEqual({k: v for k, v in env.items() if k.startswith('SPU_')}, expected)
        self.assertNotIn('FLOW_FSDBG', env)
        self.assertEqual(record['execution_profile'], 'baseline-interpreter')
        self.assertEqual(record['execution_environment'], expected)
        self.assertEqual(record['build_identity'], self.record)
        self.assertEqual(record['exe_sha256'], self.record['sha256'])
        self.assertEqual(record['elf_sha256'], self.record['elf_sha256'])
        self.assertTrue(record['muted'])
        for key, value in expected.items():
            self.assertEqual(record['environment'][key], value)

    def test_unsupported_baseline_rejects_before_pruning_or_launch(self):
        self.record['runtime_capabilities']['policy_interpreter'] = False
        self.save_record()
        self.rejected('does not support.*toolkit-default')

    def test_explicit_toolkit_default_omits_inherited_curated_probes(self):
        self.record['runtime_capabilities']['policy_interpreter'] = False
        self.save_record()
        record, env = self.launch('--execution-profile', 'toolkit-default')
        self.assertEqual(record['execution_profile'], 'toolkit-default')
        self.assertEqual(record['execution_environment'], {})
        self.assertEqual(record['build_identity'], self.record)
        self.assertFalse(any(k.startswith('SPU_') for k in env))
        self.assertFalse(any(k.startswith('SPU_') for k in record['environment']))

    def test_explicit_selection_and_adjacent_identity_for_alternate_executable(self):
        other = self.root / 'separate build/ms1_recomp.exe'
        other.parent.mkdir()
        self.exe.rename(other)
        self.exe = other
        self.record.update(path=str(other), runtime_capabilities={'policy_interpreter': False})
        self.save_record()
        record, _ = self.launch('--executable', str(other), '--execution-profile', 'toolkit-default')
        self.assertEqual(record['exe'], str(other.resolve()))
        self.assertEqual(record['build_identity'], self.record)

    def test_native_mode_guard_reads_the_selected_executables_record(self):
        # The visibility/PCM guards must use the admitted record of the selected
        # executable, never build/native's (which may belong to another build).
        other = self.root / 'separate build/ms1_recomp.exe'
        other.parent.mkdir()
        other.write_bytes(b'authored second inert executable; never executed')
        selected = dict(self.record, path=str(other), sha256=hashlib.sha256(other.read_bytes()).hexdigest(),
                        native_visibility=True)
        (other.parent / 'build_identity.json').write_text(json.dumps(selected), encoding='utf-8')
        self.record['native_visibility'] = False
        self.save_record()
        self.exe = other
        record, env = self.launch('--executable', str(other), '--native-visibility', '1')
        self.assertEqual(env['MS_NATIVE_VISIBILITY'], '1')
        self.assertEqual(record['build_identity'], selected)
        selected['native_visibility'] = False
        (other.parent / 'build_identity.json').write_text(json.dumps(selected), encoding='utf-8')
        runs = len(list((self.root / 'temp/runs').glob('*/launch.json')))
        with self.assertRaisesRegex(SystemExit, 'Visibility mode requires a matching'):
            self.launch('--executable', str(other), '--native-visibility', '1')
        self.assertEqual(self.calls, [])
        self.assertEqual(len(list((self.root / 'temp/runs').glob('*/launch.json'))), runs)

    def test_missing_record_cannot_fall_back_to_current_checkout(self):
        (self.exe.parent / 'build_identity.json').unlink()
        self.rejected('Rebuild.*runtime capabilities')

    def test_missing_capabilities_cannot_fall_back_to_current_checkout(self):
        del self.record['runtime_capabilities']
        self.save_record()
        self.rejected('no valid runtime capabilities')

    def test_truthy_strings_are_not_capability_support(self):
        self.record['runtime_capabilities']['policy_interpreter'] = 'false'
        self.save_record()
        self.rejected('no valid runtime capabilities')

    def test_stale_executable_identity_rejected(self):
        self.exe.write_bytes(b'authored changed build, never executed')
        self.rejected('executable does not match')

    def test_wrong_target_identity_rejected(self):
        self.cfg['elf'].write_bytes(b'authored other target')
        self.rejected('does not match the configured ELF')

    def test_executable_changed_after_admission_cannot_launch(self):
        self.prune_effect = lambda *a: self.exe.write_bytes(b'authored later build')
        with self.assertRaisesRegex(SystemExit, 'changed after profile admission'):
            self.launch()
        self.assertEqual(self.calls, [])
        self.assertFalse(list((self.root / 'temp/runs').glob('*/launch.json')))

    def test_malformed_record_rejected(self):
        (self.exe.parent / 'build_identity.json').write_text('{', encoding='utf-8')
        self.rejected('Rebuild.*runtime capabilities')

    def test_checkout_changes_do_not_change_a_recorded_build(self):
        self.write_source(self.source, UNSUPPORTED)
        record, _ = self.launch()
        self.assertEqual(record['build_identity'], self.record)

    def test_unknown_profile_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown execution profile'):
            profile.execution_environment('implicit-fallback', {'policy_interpreter': True})

    def test_runtime_source_identity_changes_with_source_bytes(self):
        before = profile.runtime_identity(self.source)
        self.write_source(self.source, UNSUPPORTED)
        after = profile.runtime_identity(self.source)
        self.assertNotEqual(before['runtime_capabilities_source_sha256'], after['runtime_capabilities_source_sha256'])
        self.assertEqual(after['runtime_capabilities'], {'policy_interpreter': False})

    def test_toolkit_checkout_records_revision_and_dirty_state(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.source), *args], stderr=subprocess.STDOUT).decode().strip()
        git('init', '--quiet')
        git('add', 'runtime/spu/spu_channels.c')
        git('-c', 'user.name=Authored fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Authored capability fixture')
        before = profile.runtime_identity(self.source)
        self.assertEqual(before['ps3recomp_commit'], git('rev-parse', 'HEAD'))
        self.assertFalse(before['ps3recomp_dirty'])
        self.write_source(self.source, CURATED + '// authored later edit\n')
        after = profile.runtime_identity(self.source)
        self.assertEqual(after['ps3recomp_commit'], before['ps3recomp_commit'])
        self.assertTrue(after['ps3recomp_dirty'])

    def build(self, options=(), change_during_build=False):
        binary = self.root / 'build/native'
        (binary / 'native-world-binding.json').write_text('{"authored":true}', encoding='utf-8')
        helper = self.root / 'src/renderer_optimization.cmake'
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text('# authored renderer-optimization helper identity\n', encoding='utf-8')
        # The wrapper hashes the platform's own output name (ms1_recomp.exe on
        # Windows, ms1_recomp elsewhere). The mocked compiler creates that inert
        # output; the launcher's selected executable fixture is left as it is.
        output = binary / ('ms1_recomp.exe' if os.name == 'nt' else 'ms1_recomp')
        commands = []
        def compile_boundary(command, *args, **kwargs):
            commands.append([str(x) for x in command])
            if command[1] == '-S':
                (binary / 'renderer-optimization.json').write_text('{"enabled":false}', encoding='utf-8')
            if command[1] == '--build':
                if not output.exists():
                    output.write_bytes(b'authored inert build output; never executed')
                if change_during_build:
                    self.write_source(self.source, UNSUPPORTED)
        with patch.object(project, 'ROOT', self.root), patch.object(project, 'config', return_value=self.cfg), \
             patch.object(project, 'build_environment', return_value={}), \
             patch.object(project, 'logged_run', side_effect=compile_boundary), \
             patch.object(project.subprocess, 'run'), \
             patch.object(sys, 'argv', ['project.py', 'build', *options]), redirect_stdout(io.StringIO()):
            project.main()
        return commands, json.loads((self.exe.parent / 'build_identity.json').read_text())

    def test_build_wrapper_records_curated_default_and_capabilities(self):
        commands, record = self.build()
        output = self.root / 'build/native' / ('ms1_recomp.exe' if os.name == 'nt' else 'ms1_recomp')
        self.assertEqual(record['path'], str(output))
        self.assertEqual(record['sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertTrue(self.exe.is_file())
        self.assertIn('-DPS3RECOMP_DIR=' + str(self.source.resolve()), commands[0])
        self.assertEqual(record['runtime_capabilities'], {'policy_interpreter': True})
        self.assertEqual(record['runtime_capabilities_source_sha256'], self.record['runtime_capabilities_source_sha256'])
        self.assertTrue(record['native_world_transforms'])
        self.assertTrue(record['native_job_wait'])

    def test_build_wrapper_records_selected_unsupported_source(self):
        other = self.root / 'selected toolkit'
        self.write_source(other, UNSUPPORTED)
        commands, record = self.build(['--ps3recomp-dir', str(other)])
        self.assertIn('-DPS3RECOMP_DIR=' + str(other.resolve()), commands[0])
        self.assertEqual(record['ps3recomp_dir'], str(other.resolve()))
        self.assertEqual(record['runtime_capabilities'], {'policy_interpreter': False})

    def test_source_change_during_build_cannot_publish_new_identity(self):
        with self.assertRaisesRegex(SystemExit, 'changed during the build'):
            self.build(change_during_build=True)
        self.assertEqual(json.loads((self.exe.parent / 'build_identity.json').read_text()), self.record)

    def test_historical_real_unsupported_source(self):
        if HISTORICAL_ROOT is None:
            self.skipTest('Use --historical-runtime for the pinned real-source check')
        data = (HISTORICAL_ROOT / profile.CAPABILITY_SOURCE).read_bytes()
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), HISTORICAL_BLOB)
        self.record.update(profile.runtime_identity(HISTORICAL_ROOT))
        self.assertEqual(self.record['runtime_capabilities'], {'policy_interpreter': False})
        self.save_record()
        self.rejected('does not support.*toolkit-default')
        record, env = self.launch('--execution-profile', 'toolkit-default')
        self.assertEqual(record['build_identity'], self.record)
        self.assertFalse(any(k.startswith('SPU_') for k in env))


HISTORICAL_URL = 'https://github.com/robbe1912/ps3recomp.git'
HISTORICAL_COMMIT = '39a36296511c445707adabcd312f0b740cfbd694'


def fetch_historical(directory):
    """Fetch only the pinned toolkit commit's capability source (runtime code,
    no game data). Returns its root, or None with the reason printed."""
    git = ['git', '-C', str(directory)]
    try:
        subprocess.run(['git', 'init', '--quiet', str(directory)], check=True, capture_output=True, timeout=60)
        subprocess.run(git + ['fetch', '--quiet', '--depth', '1', '--filter=blob:none', HISTORICAL_URL, HISTORICAL_COMMIT],
                       check=True, capture_output=True, timeout=180)
        subprocess.run(git + ['sparse-checkout', 'set', '--no-cone', profile.CAPABILITY_SOURCE.as_posix()],
                       check=True, capture_output=True, timeout=60)
        subprocess.run(git + ['-c', 'advice.detachedHead=false', 'checkout', '--quiet', 'FETCH_HEAD'],
                       check=True, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as error:
        print(f'historical runtime unavailable ({error}); test_historical_real_unsupported_source will skip')
        return None
    return directory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--historical-runtime', type=Path)
    parser.add_argument('--fetch-historical', action='store_true',
                        help='Fetch the pinned capability source when reachable; otherwise its test skips explicitly')
    options, remaining = parser.parse_known_args()
    with tempfile.TemporaryDirectory(prefix='runtime-profile-history-') as fetched:
        HISTORICAL_ROOT = options.historical_runtime
        if HISTORICAL_ROOT is None and options.fetch_historical:
            HISTORICAL_ROOT = fetch_historical(Path(fetched))
        result = unittest.main(argv=[sys.argv[0], *remaining], verbosity=2, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
