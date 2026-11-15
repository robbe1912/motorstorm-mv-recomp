"""Game-free checks for prompt flip completion (GCM_FLIP_PROMPT, GCM_FLIP_AT_TAKE).

Compiles the vendored cellGcmSys.c with scripts/fixtures/gcm_flip_prompt.c in
four processes (both switches off, each alone, both on; they are read once):
- off: the waiter leaves delivery to HLE boundaries and presents complete
  nothing, as before;
- prompt: a published completion is delivered by the waiting thread itself;
- take: taking a frame for present completes the wait it belongs to, never
  a newer one, never with nothing waiting, and not within one vblank period
  of the last completion; direct and FIFO flip requests both qualify;
- with either switch, the real FIFO walker holds at a flip with the next frame
  queued behind it until that frame is taken, and the frame is presented on
  its own (no merged frames); off, the get == put gate is unchanged;
- take: beats leave a direct flip that is still waiting to be taken to the
  take, each flip's wait for its take starts at its own first beat, and a flip
  left untaken past the fallback is completed by the beat; off, beats complete
  it as before.
Eighteen source mutants must build and fail on both platforms; Windows also
rejects a removed publication doorbell. Real producer/waiter, generation and
latency-reporting threads cover Win32 events and POSIX threading.
No game input; no performance claim."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PS3 = ROOT / 'vendor/ps3recomp'
SOURCE = PS3 / 'libs/video/cellGcmSys.c'
FIXTURE = ROOT / 'scripts/fixtures/gcm_flip_prompt.c'
MODES = {'off': {}, 'prompt': {'GCM_FLIP_PROMPT': '1'}, 'take': {'GCM_FLIP_AT_TAKE': '1'},
         'both': {'GCM_FLIP_PROMPT': '1', 'GCM_FLIP_AT_TAKE': '1'}}
MUTANTS = {  # name: (original, replacement, mode that must fail)
    'waiter-does-not-pump': ('        if (prompt) { ppu_gcm_pump(); if (!gcm_flip_waiting(generation)) break; }\n', '', 'prompt'),
    'older-frame-completes': ('    if (s_flip_present_gen != s_flip_wait_gen) return 0;   /* an older frame */\n', '', 'take'),
    'no-vblank-cap': ('    if (now - s_flip_last_complete_ns < min_interval_ns) return 0;   /* keep the vblank cap */\n', '', 'take'),
    'completes-without-wait': ('    if (s_flip_status != CELL_GCM_FLIP_STATUS_WAITING) return 0;\n    if (s_flip_present_gen', '    if (s_flip_present_gen', 'take'),
    'direct-flip-not-drained': ('        s_current_display_buffer_id = bufferId;\n        s_flip_drained_gen = s_flip_wait_gen;\n',
                                '        s_current_display_buffer_id = bufferId;\n', 'take'),
    'take-does-not-complete': ('    gcm_flip_complete_taken(GCM_VBLANK_PERIOD_NS);\n', '', 'take'),
    'drain-ignores-hold': ('    if (s_flip_hold && s_flip_pending && gcm_flip_hold_enabled()) return;\n', '', 'prompt'),
    'present-needs-caught-up': ('if (get != put && !(gcm_flip_hold_enabled() && s_flip_hold)) return 0;', 'if (get != put) return 0;', 'take'),
    'hold-without-switch': ('static int gcm_flip_hold_enabled(void) { return gcm_flip_prompt() || gcm_flip_at_take(); }',
                            'static int gcm_flip_hold_enabled(void) { return 1; }', 'off'),
    'stale-hold-kept': ('    if (s_flip_hold && !s_flip_pending) s_flip_hold = 0;   /* that flip was not accepted */\n', '', 'take'),
    'beat-completes-untaken': ('        if (!gcm_flip_beat_waits_for_take(now)) {', '        if (1) {', 'take'),
    'beat-defers-without-switch': ('    if (!gcm_flip_at_take() || !s_flip_pending) return 0;\n    if (!s_flip_beat_deferred_ns)',
                                   '    if (!s_flip_pending) return 0;\n    if (!s_flip_beat_deferred_ns)', 'off'),
    'no-beat-fallback': ('    return now - s_flip_beat_deferred_ns < GCM_FLIP_BEAT_FALLBACK_NS;\n', '    return 1;\n', 'take'),
    'take-keeps-deferral': ('    s_flip_beat_deferred_ns = 0;\n    s_flip_present_gen = s_flip_drained_gen;\n',
                            '    s_flip_present_gen = s_flip_drained_gen;\n', 'take'),
    'waiter-clears-newer-wait': ('    if (s_flip_wait_gen == generation) s_flip_status = CELL_GCM_FLIP_STATUS_DONE;',
                                '    s_flip_status = CELL_GCM_FLIP_STATUS_DONE;', 'prompt'),
    'untagged-delivery': ('    int current = s_flip_completion_pending && s_flip_pending_gen == s_flip_wait_gen;',
                         '    int current = 1;', 'take'),
    'reset-without-lock': ('    AcquireSRWLockExclusive(&s_flip_lock);\n    if (flip_lat_on()) flip_lat_edge(&s_fl_reset, get_timestamp_ns());\n    gcm_flip_wait_opened();\n    ReleaseSRWLockExclusive(&s_flip_lock);',
                           '    if (flip_lat_on()) flip_lat_edge(&s_fl_reset, get_timestamp_ns());\n    gcm_flip_wait_opened();', 'off'),
    'diagnostics-without-lock': ('    AcquireSRWLockExclusive(&s_flip_lat_lock);\n    s_fl.iter += ns; s_fl.iter_n++;\n    if (ns > s_fl.iter_max) s_fl.iter_max = ns;\n    ReleaseSRWLockExclusive(&s_flip_lat_lock);',
                                 '    s_fl.iter += ns; s_fl.iter_n++;\n    if (ns > s_fl.iter_max) s_fl.iter_max = ns;', 'off'),
}


if os.name == 'nt':
    MUTANTS['publication-no-doorbell'] = (
        '    HANDLE ev = gcm_flip_done_event();\n    if (ev) SetEvent(ev);',
        '    /* Publication doorbell omitted. */', 'prompt')


def build(out, label, source_text):
    d = out / label
    d.mkdir()
    src = d / 'cellGcmSys.c'
    src.write_text(source_text, encoding='utf-8')
    exe = d / ('fixture.exe' if os.name == 'nt' else 'fixture')
    includes = [PS3 / 'include', PS3 / 'libs/video']
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/std:c17', '/O1', '/Gy',
               '/D_CRT_SECURE_NO_WARNINGS', *('/I' + str(p) for p in includes),
               '/DGCM_SOURCE="' + src.as_posix() + '"', str(FIXTURE),
               '/Fe' + str(exe), '/Fo' + str(d) + os.sep, '/link', '/OPT:REF']
    else:
        cc = env.get('CC') or shutil.which('cc')
        cmd = [cc, '-std=gnu17', '-O1', '-Wall', '-ffunction-sections', '-fdata-sections',
               *('-I' + str(p) for p in includes), f'-DGCM_SOURCE="{src}"',
               str(FIXTURE), '-pthread', '-Wl,--gc-sections', '-o', str(exe)]
    b = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    (d / 'build.log').write_text(b.stdout + b.stderr, encoding='utf-8')
    (d / 'command.json').write_text(json.dumps(cmd, indent=2), encoding='utf-8')
    if b.returncode:
        return None, (b.stdout + b.stderr)[-1500:]
    return exe, ''


def run(exe, mode, latency=True):
    env = {k: v for k, v in os.environ.items() if k not in ('GCM_FLIP_PROMPT', 'GCM_FLIP_AT_TAKE')}
    env.update(MODES[mode])
    if latency: env['FLIP_LAT'] = '1'
    else: env.pop('FLIP_LAT', None)
    r = subprocess.run([str(exe), mode], capture_output=True, text=True, timeout=120, env=env)
    (exe.parent / (mode + ('-lat' if latency else '-quiet') + '.run.log')).write_text(r.stdout + r.stderr, encoding='utf-8')
    return r.returncode, r.stdout.strip().splitlines()[-1:] or r.stderr.strip().splitlines()[-1:] or ['']


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('gcm-flip-prompt-' + stamp)
    out.mkdir(parents=True)
    report = dict(game_inputs=False)
    ok = True
    source = SOURCE.read_text(encoding='utf-8')
    exe, log = build(out, 'production', source)
    if not exe:
        print('BUILD FAILED\n' + log)
        return 1
    report['production'] = {}
    for mode in MODES:
        rc, last = run(exe, mode)
        report['production'][mode] = dict(returncode=rc, output=last[0])
        print(f'{mode}: {last[0]}')
        ok &= rc == 0
    rc, last = run(exe, 'both', latency=False)
    report['diagnostics_off'] = dict(returncode=rc, output=last[0])
    print(f'diagnostics off: {last[0]}')
    ok &= rc == 0
    report['mutants'] = {}
    for name, (old, new, mode) in MUTANTS.items():
        assert source.count(old) == (2 if name == "waiter-does-not-pump" else 1), name
        exe, log = build(out, 'mutant-' + name, source.replace(old, new))
        if not exe:
            report['mutants'][name] = dict(killed=False, build_log=log)
            print(f'mutant {name}: BUILD FAILED')
            ok = False
            continue
        rc, last = run(exe, mode)
        killed = rc != 0
        report['mutants'][name] = dict(killed=killed, mode=mode, output=last[0])
        print(f'mutant {name} ({mode}): {"killed: " + last[0] if killed else "SURVIVED"}')
        ok &= killed
    (out / 'result.json').write_text(json.dumps(report, indent=2))
    print('PASS' if ok else 'FAIL', out)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
