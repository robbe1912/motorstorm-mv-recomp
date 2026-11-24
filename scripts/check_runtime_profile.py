"""Payload-free #149 checks of profile admission, the build wrapper and launcher.

Run: python scripts/check_runtime_profile.py (psutil from requirements.txt).
Optional historical source check: --historical-runtime PATH_TO_PINNED_TOOLKIT, or
--fetch-historical to fetch just its capability source (explicit skip if unreachable).
Native process creation and compilation are intercepted; no game runs.
"""
import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
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

    def test_wait_profile_default_clears_inherited_selectors(self):
        with patch.dict(os.environ, {'MS_NATIVE_JOB_WAIT_PROFILE': '1',
                                     'MS_NATIVE_JOB_WAIT': '0'}):
            launch, env = self.launch()
        self.assertIsNone(env.get('MS_NATIVE_JOB_WAIT_PROFILE'))
        self.assertIsNone(env.get('MS_NATIVE_JOB_WAIT'))
        self.assertFalse(launch['profile_job_waits'])

    def test_wait_profile_records_selected_capability(self):
        self.record.update(native_job_wait=True, native_job_wait_profile=True)
        self.save_record()
        launch, env = self.launch('--profile-job-waits')
        self.assertEqual(env['MS_NATIVE_JOB_WAIT_PROFILE'], '1')
        self.assertEqual(env['MS_NATIVE_JOB_WAIT'], '1')
        self.assertEqual(launch['environment']['MS_NATIVE_JOB_WAIT_PROFILE'], '1')
        self.assertTrue(launch['profile_job_waits'])

    def test_wait_profile_requires_selected_capability(self):
        self.record.update(native_job_wait=True)
        self.save_record()
        self.rejected('Job wait profiling requires', '--profile-job-waits')

    def test_wait_profile_admits_verified_legacy_adapter(self):
        self.record.update(native_job_wait=True, native_world_sources_sha256={
            'src\\motorstorm\\job_wait_adapter.cpp':
                '130a5ecc9913fbdcfce80080643aa403e0c4c86bc2e9e62fc2e7f2c5e32bc1f1'})
        self.save_record()
        launch, env = self.launch('--profile-job-waits')
        self.assertEqual(env['MS_NATIVE_JOB_WAIT_PROFILE'], '1')
        self.assertTrue(launch['profile_job_waits'])

    def test_wait_profile_rejects_disabled_or_unknown_adapter(self):
        baseline = self.record.copy()
        for metadata in (
                dict(native_job_wait=False, native_job_wait_profile=True),
                dict(native_job_wait=True, native_job_wait_profile=False),
                dict(native_job_wait=True, native_world_sources_sha256={
                    'src/motorstorm/job_wait_adapter.cpp': '0' * 64})):
            self.record = dict(baseline, **metadata)
            self.save_record()
            self.rejected('Job wait profiling requires', '--profile-job-waits')

    def test_capture_disabled_clears_inherited_directory(self):
        with patch.dict(os.environ, {'MS_JOB_CAPTURE_DIR': 'unowned-directory',
                                     'MS_JOB_CAPTURE_EXECUTION_PCS': '0x30b0'}):
            launch, env = self.launch()
        self.assertNotIn('MS_JOB_CAPTURE_DIR', env)
        self.assertNotIn('MS_JOB_CAPTURE_EXECUTION_PCS', env)
        self.assertFalse(launch['capture_jobs'])

    def test_capture_execution_filter_records_selected_pcs(self):
        self.record.update(job_capture=True, queue_call_observation=True,
                           job_capture_execution_filter=True)
        self.save_record()
        with patch.dict(os.environ, {'MS_JOB_CAPTURE_EXECUTION_PCS': '0x4'}):
            launch, env = self.launch('--capture-jobs', '--job-capture-execution-pc', '0x30b0',
                                      '--job-capture-execution-pc', '0x3180')
        expected = '0x30b0,0x3180'
        self.assertEqual(env['MS_JOB_CAPTURE_EXECUTION_PCS'], expected)
        self.assertEqual(launch['environment']['MS_JOB_CAPTURE_EXECUTION_PCS'], expected)
        self.assertEqual(launch['job_capture_execution_pcs'], [0x30b0, 0x3180])

    def test_capture_execution_filter_requires_capability(self):
        self.record.update(job_capture=True, queue_call_observation=True)
        self.save_record()
        self.rejected('Execution PC filter requires', '--capture-jobs',
                      '--job-capture-execution-pc', '0x3180')

    def test_capture_execution_filter_rejects_invalid_selection(self):
        for pc in ('-4', '3', '0x40000'):
            self.rejected('Execution PC selection requires', '--capture-jobs',
                          '--job-capture-execution-pc', pc)
        self.rejected('Execution PC selection requires', '--job-capture-execution-pc', '4')
        self.rejected('Execution PC selection requires', '--capture-jobs',
                      *['--job-capture-execution-pc=4'] * 33)

    def test_capture_requires_selected_build(self):
        self.rejected('Job capture requires a matching', '--capture-jobs')

    def test_capture_records_owned_directory(self):
        self.record.update(job_capture=True, queue_call_observation=True)
        self.save_record()
        with patch.dict(os.environ, {'MS_JOB_CAPTURE_DIR': 'unowned-directory'}):
            launch, env = self.launch('--capture-jobs')
        expected = str(Path(launch['output']) / 'job-capture')
        self.assertEqual(env['MS_JOB_CAPTURE_DIR'], expected)
        self.assertEqual(launch['environment']['MS_JOB_CAPTURE_DIR'], expected)
        self.assertTrue(launch['capture_jobs'])
        self.assertTrue(Path(expected).is_dir())

    def test_capture_requires_queue_binding(self):
        self.record['job_capture'] = True
        self.save_record()
        self.rejected('Job capture requires a matching', '--capture-jobs')

    def test_capture_duration_requires_replay(self):
        self.rejected('job-capture-seconds requires', '--capture-jobs', '--job-capture-seconds', '0.1')

    def rejected(self, message, *options):
        with self.assertRaisesRegex(SystemExit, message):
            self.launch(*options)
        self.assertEqual(self.calls, [])
        self.prune.assert_not_called()
        self.assertFalse((self.root / 'temp/runs').exists())

    def test_actual_curated_source_supports_baseline(self):
        self.assertIs(profile.runtime_capabilities(ROOT / 'vendor/ps3recomp')['policy_interpreter'], True)

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

    def check_flip_selection(self, prompt=False, profile=False):
        keys = ('GCM_FLIP_PROMPT', 'GCM_FLIP_AT_TAKE', 'FLIP_LAT')
        options = (['--prompt-flip'] if prompt else []) + (['--profile-flip'] if profile else [])
        with patch.dict(os.environ, dict.fromkeys(keys, '1')):
            record, env = self.launch(*options)
        for key, enabled in zip(keys, (prompt, prompt, profile)):
            expected = '1' if enabled else None
            self.assertEqual(env.get(key), expected)
            self.assertEqual(record['environment'].get(key), expected)

    def test_flip_default(self):
        self.check_flip_selection()

    def test_flip_wait_only(self):
        self.check_flip_selection(prompt=True)

    def test_flip_diagnostics_only(self):
        self.check_flip_selection(profile=True)

    def test_flip_wait_and_diagnostics(self):
        self.check_flip_selection(prompt=True, profile=True)

    def check_surface_prompt_selection(self, mode):
        with patch.dict(os.environ, {'RSX_CPU_SURFACE_PROMPT': 'inherited'}):
            record, env = self.launch('--cpu-surface-prompt', mode)
        expected = None if mode == 'default' else mode
        self.assertEqual(env.get('RSX_CPU_SURFACE_PROMPT'), expected)
        self.assertEqual(record['environment'].get('RSX_CPU_SURFACE_PROMPT'), expected)

    def test_surface_prompt_default_clears_inherited_selection(self):
        self.check_surface_prompt_selection('default')

    def test_surface_prompt_disabled_selection_is_recorded(self):
        self.check_surface_prompt_selection('0')

    def test_surface_prompt_enabled_selection_is_recorded(self):
        self.check_surface_prompt_selection('1')

    def test_jobmod_dispatch_log_default_clears_inherited_selection(self):
        with patch.dict(os.environ, {'SPU_JOBMOD_DISPATCH_LOG': '1'}):
            record, env = self.launch()
        self.assertNotIn('SPU_JOBMOD_DISPATCH_LOG', env)
        self.assertNotIn('SPU_JOBMOD_DISPATCH_LOG', record['environment'])

    def test_jobmod_dispatch_log_selection_is_recorded(self):
        record, env = self.launch('--jobmod-dispatch-log')
        self.assertEqual(env.get('SPU_JOBMOD_DISPATCH_LOG'), '1')
        self.assertEqual(record['environment'].get('SPU_JOBMOD_DISPATCH_LOG'), '1')

    def check_surface_prefetch(self, mode):
        with patch.dict(os.environ, {'RSX_CPU_SURFACE_PREFETCH': 'inherited'}):
            record, env = self.launch('--surface-prefetch', mode)
        expected = '01A80500,00A80500,02A30480' if mode == '1' else None
        self.assertEqual(env.get('RSX_CPU_SURFACE_PREFETCH'), expected)
        self.assertEqual(record['environment'].get('RSX_CPU_SURFACE_PREFETCH'), expected)

    def test_surface_prefetch_default_clears_inherited_list(self):
        self.check_surface_prefetch('0')

    def test_surface_prefetch_enabled_lists_race_surfaces(self):
        self.check_surface_prefetch('1')

    def check_eager_surface_submit(self, mode):
        with patch.dict(os.environ, {'RSX_CPU_SURFACE_EAGER': 'inherited'}):
            record, env = self.launch('--eager-surface-submit', mode)
        expected = '02A30480' if mode == '1' else None
        self.assertEqual(env.get('RSX_CPU_SURFACE_EAGER'), expected)
        self.assertEqual(record['environment'].get('RSX_CPU_SURFACE_EAGER'), expected)

    def test_eager_surface_submit_default_clears_inherited_list(self):
        self.check_eager_surface_submit('0')

    def test_eager_surface_submit_enabled_lists_exposure_target(self):
        self.check_eager_surface_submit('1')

    def check_cpu_surface_fast(self, mode):
        with patch.dict(os.environ, {'RSX_CPU_SURFACE_FAST': '0'}):
            record, env = self.launch('--cpu-surface-fast', mode)
        expected = '0' if mode == '0' else None
        self.assertEqual(env.get('RSX_CPU_SURFACE_FAST'), expected)
        self.assertEqual(record['environment'].get('RSX_CPU_SURFACE_FAST'), expected)

    def test_cpu_surface_fast_default_clears_inherited_switch(self):
        self.check_cpu_surface_fast('1')

    def test_cpu_surface_fast_off_queues_every_read(self):
        self.check_cpu_surface_fast('0')

    def check_cpu_surface_snapshot_fast(self, mode):
        with patch.dict(os.environ, {'RSX_CPU_SURFACE_SNAPSHOT_FAST': '1'}):
            record, env = self.launch('--cpu-surface-snapshot-fast', mode)
        expected = '1' if mode == '1' else None
        self.assertEqual(env.get('RSX_CPU_SURFACE_SNAPSHOT_FAST'), expected)
        self.assertEqual(record['environment'].get('RSX_CPU_SURFACE_SNAPSHOT_FAST'), expected)

    def test_cpu_surface_snapshot_fast_default_clears_inherited_switch(self):
        self.check_cpu_surface_snapshot_fast('0')

    def test_cpu_surface_snapshot_fast_enabled(self):
        self.check_cpu_surface_snapshot_fast('1')

    def check_spurs_kernel_notify(self, mode):
        with patch.dict(os.environ, {'SPURS_KERNEL_NOTIFY': '1'}):
            record, env = self.launch('--spurs-kernel-notify', mode)
        expected = '1' if mode == '1' else None
        self.assertEqual(env.get('SPURS_KERNEL_NOTIFY'), expected)
        self.assertEqual(record['environment'].get('SPURS_KERNEL_NOTIFY'), expected)

    def test_spurs_kernel_notify_default_clears_inherited_switch(self):
        self.check_spurs_kernel_notify('0')

    def test_spurs_kernel_notify_enabled(self):
        self.check_spurs_kernel_notify('1')

    def check_spurs_lanes(self, lanes, expected):
        with patch.dict(os.environ, {'SPURS_LANES': '6'}):
            record, env = self.launch('--spurs-lanes', lanes)
        self.assertEqual(env.get('SPURS_LANES'), expected)
        self.assertEqual(record['environment'].get('SPURS_LANES'), expected)

    def test_spurs_lanes_default_clears_inherited_switch(self):
        self.check_spurs_lanes('0', None)

    def test_spurs_lanes_six(self):
        self.check_spurs_lanes('6', '6')

    def test_spurs_lanes_rejects_seven(self):
        with self.assertRaises(SystemExit):
            self.launch('--spurs-lanes', '7')

    def check_ppu_wait_profile(self, options):
        with patch.dict(os.environ, {'PPU_WAIT_PROFILE': '1'}):
            record, env = self.launch(*options)
        expected = '1' if '--profile-ppu-waits' in options else None
        self.assertEqual(env.get('PPU_WAIT_PROFILE'), expected)
        self.assertEqual(record['environment'].get('PPU_WAIT_PROFILE'), expected)
        self.assertEqual(record['profile_ppu_waits'], expected == '1')

    def test_ppu_wait_profile_default_clears_inherited_switch(self):
        self.check_ppu_wait_profile(())

    def test_ppu_wait_profile_enabled(self):
        self.check_ppu_wait_profile(('--profile-ppu-waits',))

    def test_rsx_switch_sets_and_records_runtime_keys(self):
        record, env = self.launch('--rsx-switch', 'RSX_DEFORM_CAPTURE=1', '--rsx-switch', 'RSX_DEFORM_TARGETS=00A80500')
        self.assertEqual((env.get('RSX_DEFORM_CAPTURE'), env.get('RSX_DEFORM_TARGETS')), ('1', '00A80500'))
        self.assertEqual({k: v for k, v in record['environment'].items() if k.startswith('RSX_DEFORM')},
                         {'RSX_DEFORM_CAPTURE': '1', 'RSX_DEFORM_TARGETS': '00A80500'})

    def test_rsx_switch_absent_clears_inherited_key(self):
        with patch.dict(os.environ, {'RSX_DEFORM_CAPTURE': '1'}):
            record, env = self.launch()
        self.assertNotIn('RSX_DEFORM_CAPTURE', env)
        self.assertNotIn('RSX_DEFORM_CAPTURE', record['environment'])

    def test_rsx_switch_rejects_malformed_and_launcher_owned_keys(self):
        for switch in ('DEFORM_CAPTURE=1', 'RSX_DEFORM_CAPTURE', 'RSX_deform=1', 'RSX_TEX_MIPS=0'):
            with self.subTest(switch=switch), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.launch('--rsx-switch', switch)

    def test_owned_jobs_rejected_on_capture_build(self):
        self.record['job_capture'] = True
        self.save_record()
        self.rejected('--native-owned-jobs has no effect', '--native-owned-jobs')

    def test_eager_surface_extra_lists_both_targets(self):
        with patch.dict(os.environ, {'RSX_CPU_SURFACE_EAGER': 'inherited'}):
            record, env = self.launch('--eager-surface-submit', '1', '--eager-surface', '01A80500', '--eager-surface', '0x00A80500')
        expected = '02A30480,01A80500,00A80500'
        self.assertEqual(env.get('RSX_CPU_SURFACE_EAGER'), expected)
        self.assertEqual(record['environment'].get('RSX_CPU_SURFACE_EAGER'), expected)

    def test_eager_surface_extra_requires_submit(self):
        with self.assertRaises(SystemExit):
            self.launch('--eager-surface', '01A80500')

    def test_eager_surface_rejects_bad_values(self):
        for offsets in (['0'], ['123456789'], ['01A80500', '0x1A80500'], ['1', '2', '3', '4'], ['02A30480']):
            options = ['--eager-surface-submit', '1'] + [item for offset in offsets for item in ('--eager-surface', offset)]
            with self.subTest(offsets=offsets), self.assertRaises(SystemExit):
                self.launch(*options)

    def test_pm_native_services_default_clears_inherited_selection(self):
        with patch.dict(os.environ, {'SPU_PM_NATIVE_SVC': '1', 'SPU_PM_SVC_VERIFY': '1'}):
            record, env = self.launch('--native-owned-jobs')
        for key in ('SPU_PM_NATIVE_SVC', 'SPU_PM_SVC_VERIFY'):
            self.assertNotIn(key, env)
            self.assertNotIn(key, record['environment'])

    def test_pm_native_services_selection_is_recorded(self):
        record, env = self.launch('--native-owned-jobs', '--pm-native-services')
        self.assertEqual(env.get('SPU_PM_NATIVE_SVC'), '1')
        self.assertEqual(env.get('SPU_NATIVE_OWNED_JOBS'), '1')
        self.assertEqual(record['environment'].get('SPU_PM_NATIVE_SVC'), '1')

    def test_pm_native_services_require_owned_jobs(self):
        self.rejected('Native policy services require --native-owned-jobs', '--pm-native-services')

    def test_owned_image_requires_owned_jobs(self):
        self.rejected('requires --native-owned-jobs', '--native-owned-image', '210')

    def test_owned_image_rejects_unmatched_build(self):
        self.rejected('requires a matching image-scope build', '--native-owned-jobs', '--native-owned-image', '210')

    def test_owned_image_rejects_other_execution_modes(self):
        for mode in ('--pm-native-services', '--capture-jobs'):
            self.rejected('requires policy services and job capture to be off',
                          '--native-owned-jobs', '--native-owned-image', '210', mode)

    def test_owned_image_rejects_wrong_range(self):
        for image in ('0', '2147483648'):
            self.rejected('image ID in 1..2147483647', '--native-owned-jobs', '--native-owned-image', image)

    def test_owned_image_selection_is_recorded(self):
        self.write_source(self.source, CURATED + 'void image(void) { getenv("SPU_NATIVE_OWNED_IMAGE"); }\n')
        self.record.update(profile.runtime_identity(self.source))
        self.save_record()
        with patch.dict(os.environ, {'SPU_NATIVE_OWNED_IMAGE': '25'}):
            record, env = self.launch('--native-owned-jobs', '--native-owned-image', '210')
        self.assertEqual(env['SPU_NATIVE_OWNED_IMAGE'], '210')
        self.assertEqual(record['environment']['SPU_NATIVE_OWNED_IMAGE'], '210')

    def test_owned_image_default_clears_inherited_selection(self):
        with patch.dict(os.environ, {'SPU_NATIVE_OWNED_IMAGE': '210'}):
            record, env = self.launch('--native-owned-jobs')
        self.assertNotIn('SPU_NATIVE_OWNED_IMAGE', env)
        self.assertNotIn('SPU_NATIVE_OWNED_IMAGE', record['environment'])

    def check_surface_batch_selection(self, flush, overlap):
        keys = {'RSX_CPU_SURFACE_FLUSH': flush, 'RSX_DRAIN_OVERLAP': overlap}
        with patch.dict(os.environ, {key: 'inherited' for key in keys}):
            record, env = self.launch('--cpu-surface-flush', flush, '--drain-overlap', overlap)
        for key, mode in keys.items():
            expected = None if mode == 'default' else mode
            self.assertEqual(env.get(key), expected)
            self.assertEqual(record['environment'].get(key), expected)

    def test_surface_batch_defaults_clear_inherited_selections(self):
        self.check_surface_batch_selection('default', 'default')

    def test_surface_batch_disabled_selections_are_recorded(self):
        self.check_surface_batch_selection('0', '0')

    def test_surface_batch_enabled_selections_are_recorded(self):
        self.check_surface_batch_selection('1', '1')

    def test_surface_flush_and_serialized_drain_are_independent(self):
        self.check_surface_batch_selection('1', '0')

    def test_surface_flush_disabled_and_overlap_are_independent(self):
        self.check_surface_batch_selection('0', '1')

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
        self.assertTrue(record['native_job_wait_profile'])
        self.assertFalse(record['replay_backbuffer_capture'])
        self.assertFalse(record['native_visibility_batch'])
        self.assertFalse(record['job_capture'])
        self.assertFalse(record['job_capture_execution_filter'])
        self.assertFalse(record['job_capture_queue_history'])
        self.assertFalse(record['job_capture_policy_state'])
        self.assertFalse(record['job_capture_module_identity'])
        self.assertIn('-DPORT_ENABLE_JOB_CAPTURE=OFF', commands[0])
        self.assertIn('-DPORT_QUEUE_CALL_OBSERVATION=OFF', commands[0])

    def test_build_without_native_wait_has_no_profile_capability(self):
        commands, record = self.build(['--no-native-job-wait'])
        self.assertFalse(record['native_job_wait'])
        self.assertFalse(record['native_job_wait_profile'])
        self.assertIn('-DPORT_NATIVE_JOB_WAIT=OFF', commands[0])

    def test_build_records_backbuffer_capability_and_visibility_batch(self):
        backend = self.source / 'libs/video/rsx_d3d12_backend.c'
        backend.parent.mkdir(parents=True)
        backend.write_text('/* authored fixture */\ngetenv("RSX_CAP_BACKBUFFER_ONLY");\n',
                           encoding='utf-8')
        commands, record = self.build(['--native-visibility-batch'])
        self.assertEqual(record['replay_backbuffer_capture'], os.name == 'nt')
        self.assertTrue(record['native_visibility_batch'])
        self.assertIn('-DPORT_NATIVE_VISIBILITY_BATCH=ON', commands[0])

    def test_wait_profile_legacy_paths_and_strict_capability(self):
        digest = '130a5ecc9913fbdcfce80080643aa403e0c4c86bc2e9e62fc2e7f2c5e32bc1f1'
        for path in ('src/motorstorm/job_wait_adapter.cpp',
                     'src\\motorstorm\\job_wait_adapter.cpp'):
            identity = dict(native_job_wait=True, native_world_sources_sha256={path: digest})
            self.assertTrue(profile.supports_job_wait_profile(identity))
            identity['native_job_wait_profile'] = False
            self.assertFalse(profile.supports_job_wait_profile(identity))
        for capability in (False, None, 1, '1'):
            self.assertFalse(profile.supports_job_wait_profile(dict(
                native_job_wait=True, native_job_wait_profile=capability)))

    def test_capture_build_records_all_observers(self):
        commands, record = self.build(['--capture-jobs'])
        for option in ('PORT_ENABLE_JOB_CAPTURE', 'PORT_QUEUE_CALL_OBSERVATION',
                       'PS3RECOMP_ATOMIC_OBSERVATION', 'PS3RECOMP_EXECUTION_OBSERVATION',
                       'PS3RECOMP_SPURS_SCHEDULER_OBSERVATION'):
            self.assertIn('-D' + option + '=ON', commands[0])
        self.assertIn('-DPORT_CAPTURE_ALLOW_UNLIFTED=OFF', commands[0])
        self.assertTrue(record['job_capture'])
        self.assertTrue(record['queue_call_observation'])
        self.assertTrue(record['job_capture_execution_filter'])
        self.assertTrue(record['job_capture_queue_history'])
        self.assertTrue(record['job_capture_policy_state'])
        self.assertTrue(record['job_capture_module_identity'])

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


    def test_menu_build_rejects_original_replay_before_launch(self):
        self.record['menu_boot'] = True
        self.save_record()
        with patch('menu_replay.load_profile', return_value={'elf_sha256': self.record['elf_sha256']}), patch.object(launcher, 'require_worktree_private_replay'):
            self.rejected('Replay startup differs', '--menu-replay', str(self.root / 'profile.json'))

    def test_menu_build_accepts_menu_replay(self):
        self.record['menu_boot'] = True
        self.save_record()
        profile = {'elf_sha256': self.record['elf_sha256'], 'startup': 'menu'}
        with patch('menu_replay.load_profile', return_value=profile), patch.object(launcher, 'require_worktree_private_replay'):
            record, env = self.launch('--menu-replay', str(self.root / 'profile.json'))
        self.assertEqual(env['MS_BOOT_MENU'], '1')

    def test_menu_boot_uses_selected_capability(self):
        self.record['menu_boot'] = True
        self.save_record()
        with patch.dict(os.environ, {'MS_BOOT_MENU': '0'}):
            record, env = self.launch()
        self.assertEqual(env['MS_BOOT_MENU'], '1')
        self.assertEqual(record['environment']['MS_BOOT_MENU'], '1')

    def test_original_intro_selection(self):
        self.record['menu_boot'] = True
        self.save_record()
        with patch.dict(os.environ, {'MS_BOOT_MENU': '1'}):
            record, env = self.launch('--original-intro')
        self.assertEqual(env['MS_BOOT_MENU'], '0')
        self.assertEqual(record['environment']['MS_BOOT_MENU'], '0')

    def test_legacy_build_sanitizes_boot_selection(self):
        with patch.dict(os.environ, {'MS_BOOT_MENU': '1'}):
            record, env = self.launch()
        self.assertEqual(env['MS_BOOT_MENU'], '0')
        self.assertEqual(record['environment']['MS_BOOT_MENU'], '0')



    def test_selected_depth_capability_is_independent_of_default_build(self):
        default_identity = self.exe.parent / 'build_identity.json'
        self.exe = self.root / 'selected/ms1_recomp.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(b'authored inert executable identity; never executed')
        self.record.update(path=str(self.exe), depth_observer=True, native_depth_query=True)
        self.save_record()
        default_identity.write_text(json.dumps(dict(self.record, depth_observer=False,
                                                    native_depth_query=False)))
        launch, env = self.launch('--executable', str(self.exe), '--depth-observer',
                                  '--native-depth', '1')
        self.assertEqual(launch['build_identity'], self.record)
        self.assertEqual(env['MS_DEPTH_OBSERVER'], '1')
        self.assertEqual(env['MS_NATIVE_DEPTH'], '1')

    def test_default_build_cannot_admit_unsupported_selected_depth(self):
        default_identity = self.exe.parent / 'build_identity.json'
        self.exe = self.root / 'selected/ms1_recomp.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(b'authored inert executable identity; never executed')
        self.record.update(path=str(self.exe), depth_observer=False, native_depth_query=False)
        self.save_record()
        default_identity.write_text(json.dumps(dict(self.record, depth_observer=True,
                                                    native_depth_query=True)))
        self.rejected('matching --depth-observer build', '--executable', str(self.exe),
                      '--depth-observer', '--native-depth', '1')

    def test_havok_threads_default_is_game_count_and_rejects_unmatched_build(self):
        for count in ('-1', '7'):
            self.rejected('Havok thread count must be 0 \\(game count\\) or 1\\.\\.6',
                          '--havok-threads', count)
        self.rejected('requires a matching --havok-threads build', '--havok-threads', '4')
        with patch.dict(os.environ, {'MS_HAVOK_THREADS': '4'}):
            record, env = self.launch()
        self.assertEqual(env['MS_HAVOK_THREADS'], '0')
        self.assertEqual(record['environment']['MS_HAVOK_THREADS'], '0')

    def test_havok_threads_selection_is_recorded(self):
        # The flag must come from the record of the selected executable, not
        # build/native's (the pattern of the depth observer test above).
        default_identity = self.exe.parent / 'build_identity.json'
        self.exe = self.root / 'selected/ms1_recomp.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(b'authored inert executable identity; never executed')
        self.record.update(path=str(self.exe), havok_threads=False)
        self.save_record()
        default_identity.write_text(json.dumps(dict(self.record, havok_threads=True)))
        self.rejected('requires a matching --havok-threads build', '--executable', str(self.exe),
                      '--havok-threads', '4')
        self.record['havok_threads'] = True
        self.save_record()
        with patch.dict(os.environ, {'MS_HAVOK_THREADS': '2'}):
            record, env = self.launch('--executable', str(self.exe), '--havok-threads', '4')
        self.assertEqual(env['MS_HAVOK_THREADS'], '4')
        self.assertEqual(record['environment']['MS_HAVOK_THREADS'], '4')
        self.assertIs(record['build_identity']['havok_threads'], True)


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
