#!/usr/bin/env python3
"""Game-free checks for the SPU lane trace gate (SPU_LANE_TRACE).

The nine gated print kinds must stay silent in a default run and must
print with SPU_LANE_TRACE=1. The inline local store accessors must return
and store the same bytes as the scalar rule, and each armed probe must
still fire. Each planted defect must make at least one case fail. No game
data is read and no speed is claimed."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
SDK = ROOT / 'vendor/ps3recomp'
SPU = SDK / 'runtime/spu'
FIXTURE = ROOT / 'scripts/fixtures/spu_lane_trace.c'
# One private copy of these trees per variant: the mutants change headers.
TREES = ['runtime/spu', 'runtime/platform', 'runtime/memory', 'runtime/diag', 'runtime/ppu', 'libs/spurs', 'include',
         'runtime/ps3_log.h', 'runtime/syscalls/sys_semaphore.c', 'runtime/syscalls/sys_semaphore.h',
         'runtime/syscalls/ppu_wait_profile.h', 'runtime/syscalls/sys_timer.h', 'runtime/syscalls/lv2_syscall_table.h',
         'runtime/syscalls/spu_ea_alias.c']
NAMES = ['spu_channels.c', 'spu_drain.c', 'spu_lockstep.c', 'spu_coherency.c', 'spu_workload.c', 'spurs_policy.c',
         'spurs_job.c', 'spu_tsp_weak.c', 'spu_vm_pagemap.c', 'spurs_policy_blob_weak.c', 'spu_interp.c',
         'spu_float_simd.c', 'spu_task_lifecycle.c']
EXTRA = ['runtime/platform/win32_compat.c', 'runtime/memory/guest_read_sync.c', 'runtime/diag/spu_execution_observer.c',
         'runtime/diag/loadtime_trace.c', 'runtime/platform/thread_name.c', 'runtime/syscalls/sys_semaphore.c']
# Line kinds behind SPU_LANE_TRACE. A default run must not print one of them.
GATED = ['[pm-fetch]', '[spurs-pm] poll', '[pm-fill]', '[modspan-w]', '[spurs-pm] DMA', '[taskset] built',
         '[spu_workload] dispatch HIT', '[spu_workload] async image=', '[WAIT] semaphore']
# The three probe lines: each prints only when its own switch is on.
PROBES = ['[spu-lowread]', '[spu-SMC]', '[spu-watch']
QUIET = ['[wws-res]', '[wws-code]']
LANE = {'LBP_SPU_SERIAL': '1'}   # the async thread holds the serial lock until after its RETURNED line
# The lane mode, trace on: every gated line kind, with its count.
LANE_LINES = [('[spurs-pm] poll #1', 1), ('[spurs-pm] DMA cmd=0x40 lsa=0x04000', 1),
              ('[spurs-pm] DMA cmd=0x40 lsa=0x01000', 1), ('[spurs-pm] DMA cmd=0x40 lsa=0x02000', 1),
              ('[pm-fetch] GET img=2 tag=8 src=0x00020000 dst=0x04000 sz=0x80 rc=0', 1),
              ('[modspan-w] cmd=0x40 pc=0x00000 lsa=0x01000 ea=0x00020100 sz=0x80', 1),
              ('[pm-fill] dma-get pc=0x00000 lsa=0x01000:', 1),
              ('[pm-fetch] POLL tag=8 src=0x00020200 dst=0x02000', 1),
              ('[spu_workload] dispatch HIT fp=', 1), ('[spu_workload] dispatch HIT (async)', 2),
              ('[spu_workload] async image=77 RETURNED', 2),
              ('[taskset] built SpursTasksetContext image=77 taskset=0x00030000 task=0', 1),
              ('[WAIT] semaphore_wait(sem=1 timeout=0)', 1)]
POLL_OFF = [k for k in GATED if k != '[spurs-pm] poll']   # the poll line prints in this case
# mode, environment additions, (line, count) that must print, line kinds that must not print
CASES = [('edge', {}, [], GATED + PROBES + QUIET),
         ('edge', {'SPU_LANE_TRACE': '0'}, [], GATED + PROBES + QUIET),
         ('poll', {}, [], GATED + PROBES + QUIET),
         ('poll', {'SPU_LANE_TRACE': '1'}, [('[spurs-pm] poll #1', 1), ('[wws-res]', 1), ('[wws-code]', 1)],
          POLL_OFF + PROBES),
         ('edge', {'SPU_LS_LOWREAD': '1'}, [('[spu-lowread] img=77 read LS 0x000', 1)], GATED + PROBES[1:] + QUIET),
         ('edge', {'SPU_SMC_WATCH': '77'}, [('[spu-SMC] img=77 WROTE CODE @0x01230', 1)],
          GATED + PROBES[:1] + PROBES[2:] + QUIET),
         ('edge', {'SPU_LS_WATCH': '0x1230'}, [('[spu-watch rd 0x01230', 1), ('[spu-watch WR 0x01230', 1)],
          GATED + PROBES[:2] + QUIET),
         ('lane', LANE, [], GATED + PROBES + QUIET),
         ('lane', dict(LANE, SPU_LANE_TRACE='0'), [], GATED + PROBES + QUIET),
         ('lane', dict(LANE, SPU_LANE_TRACE='1'), LANE_LINES, PROBES)]
# name -> (file, before, after): one planted defect each. The text must hit once.
MUTANTS = {
    'gate-inverted': ('runtime/spu/spu_context.h',
                      '    if (__builtin_expect(g_spu_ls_gate != 0, 0))\n        return spu_ls_read_probes(ctx, lsa);',
                      '    if (__builtin_expect(g_spu_ls_gate == 0, 0))\n        return spu_ls_read_probes(ctx, lsa);'),
    'mask-lost': ('runtime/spu/spu_context.h',
                  '    return spu_ls_load16(&ctx->ls[lsa & SPU_LS_MASK & ~0xFu]);',
                  '    return spu_ls_load16(&ctx->ls[lsa]);'),
    'probe-lost-when-armed': ('runtime/spu/spu_context.h',
                              '    if (g_spu_ls_gate & SPU_LS_GATE_SMC)\n        spu_ls_write_probe_smc(ctx, lsa, p);',
                              '    if (0)\n        spu_ls_write_probe_smc(ctx, lsa, p);'),
    'probe-fired-when-not-armed': ('runtime/spu/spu_context.h',
                                   '    if (g_spu_ls_gate & SPU_LS_GATE_LOWREAD) {', '    if (g_spu_ls_gate) {'),
    'lowread-lost-when-armed': ('runtime/spu/spu_context.h',
                                '    if (g_spu_ls_gate & SPU_LS_GATE_LOWREAD) {', '    if (0) {'),
    'watch-read-lost-when-armed': ('runtime/spu/spu_context.h',
                                   '    if (g_spu_ls_gate & SPU_LS_GATE_WATCH)\n        spu_ls_watch_hit2(lsa, 0, p,',
                                   '    if (0)\n        spu_ls_watch_hit2(lsa, 0, p,'),
    'watch-write-lost-when-armed': ('runtime/spu/spu_context.h',
                                    '    if (g_spu_ls_gate & SPU_LS_GATE_WATCH)\n        spu_ls_watch_hit2(lsa, 1, p,',
                                    '    if (0)\n        spu_ls_watch_hit2(lsa, 1, p,'),
    'load-byte-order-turned': ('runtime/spu/spu_context.h',
                               '    v._u32[0] = SPU_BSWAP32(w0); v._u32[1] = SPU_BSWAP32(w1);',
                               '    v._u32[0] = w0; v._u32[1] = SPU_BSWAP32(w1);'),
    'store-byte-order-turned': ('runtime/spu/spu_context.h',
                                '    uint32_t w2 = SPU_BSWAP32(val._u32[2]), w3 = SPU_BSWAP32(val._u32[3]);',
                                '    uint32_t w2 = SPU_BSWAP32(val._u32[2]), w3 = val._u32[3];'),
    'trace-always-on': ('runtime/spu/spu_context.h',
                        '    g_spu_lane_trace = (e && *e && strcmp(e, "0")) ? 1 : 0;', '    g_spu_lane_trace = 1;'),
    'poll-line-unconditional': ('runtime/spu/spu_channels.c',
                                '            if (spu_lane_trace() && (n <= 4 || (n % 4096) == 0))',
                                '            if (n <= 4 || (n % 4096) == 0)'),
    'fill-line-unconditional': ('runtime/spu/spu_channels.c', '    if (!spu_lane_trace()) return;', '    if (0) return;'),
    'sync-dispatch-line-unconditional': ('runtime/spu/spu_workload.c',
                                         '    if (spu_lane_trace())\n        fprintf(stderr,\n'
                                         '            "[spu_workload] dispatch HIT fp=',
                                         '    if (1)\n        fprintf(stderr,\n'
                                         '            "[spu_workload] dispatch HIT fp='),
    'taskset-line-unconditional': ('runtime/spu/spu_workload.c',
                                   '                    if (spu_lane_trace()) {\n'
                                   '                        fprintf(stderr, "[taskset] built',
                                   '                    if (1) {\n                        fprintf(stderr, "[taskset] built'),
    'async-returned-line-unconditional': ('runtime/spu/spu_workload.c',
                                          '            if (spu_lane_trace())\n'
                                          '                fprintf(stderr, "[spu_workload] async image=%d RETURNED',
                                          '            if (1)\n'
                                          '                fprintf(stderr, "[spu_workload] async image=%d RETURNED'),
    'async-dispatch-line-unconditional': ('runtime/spu/spu_workload.c',
                                          '    if (spu_lane_trace())\n        fprintf(stderr,\n'
                                          '            "[spu_workload] dispatch HIT (async)',
                                          '    if (1)\n        fprintf(stderr,\n'
                                          '            "[spu_workload] dispatch HIT (async)'),
    'dma-line-unconditional': ('runtime/spu/spu_dma.h', '    if (spu->policy_mode && spu_lane_trace()) {',
                               '    if (spu->policy_mode) {'),
    'wait-line-unconditional': ('runtime/syscalls/sys_semaphore.c',
                                '      else if (!getenv("SEMTID") && spu_lane_trace())',
                                '      else if (!getenv("SEMTID"))'),
    'fetch-poll-line-unconditional': ('runtime/spu/spu_dma.h',
                                      '              if (spu->policy_mode && spu_lane_trace() && '
                                      '((cmd & 0xF0u) == 0x40u) && vm_base',
                                      '              if (spu->policy_mode && ((cmd & 0xF0u) == 0x40u) && vm_base'),
    'fetch-get-line-unconditional': ('runtime/spu/spu_dma.h',
                                     '        if (spu->policy_mode && spu_lane_trace() && ((cmd & 0xF0u) == 0x40u)\n'
                                     '            && (lsa & SPU_LS_MASK) >= 0x4000u',
                                     '        if (spu->policy_mode && ((cmd & 0xF0u) == 0x40u)\n'
                                     '            && (lsa & SPU_LS_MASK) >= 0x4000u'),
    'modspan-line-unconditional': ('runtime/spu/spu_dma.h',
                                   '          if (spu->policy_mode && spu_lane_trace() && g_ms_last_size',
                                   '          if (spu->policy_mode && g_ms_last_size')}


def lifted_header():
    """The four guest jobs as the SPU lifter emits them."""
    sys.path.insert(0, str(SDK / 'tools'))
    from spu_lifter import SPULifter, LiftedFunction
    from spu_disasm import spu_decode

    def i10(op, rt, ra, imm10):
        return (op << 24) | ((imm10 & 0x3FF) << 14) | (ra << 7) | rt

    def ri16(op9, rt, imm16):
        return (op9 << 23) | ((imm16 & 0xFFFF) << 7) | rt

    def wrch(rt, channel):
        return (0x10D << 21) | (channel << 7) | rt

    IL, ILHU, IOHL, AI, LQD, STQD = 0b010000001, 0b010000010, 0b011000001, 0x1C, 0x34, 0x24
    # ILHU clears the low halfword and IOHL sets it: ilhu+iohl builds a 32-bit value.
    edge = [ri16(IL, 3, 0), ri16(ILHU, 4, 4), i10(AI, 5, 4, -16), ri16(IL, 6, 0), ri16(IOHL, 6, 0x1235),
            i10(AI, 7, 5, 0x45), i10(AI, 8, 6, 5), ri16(ILHU, 10, 0x1122), ri16(IOHL, 10, 0x3344),
            ri16(ILHU, 12, 0x5566), ri16(IOHL, 12, 0x7788), i10(LQD, 3, 3, 0), i10(LQD, 4, 4, 0),
            i10(LQD, 5, 5, 0), i10(LQD, 6, 6, 0), i10(STQD, 10, 7, 0), i10(STQD, 12, 8, 0),
            ri16(IL, 0, 0x240), 0x35000000]
    poll = [ri16(IL, 2, 0x9D0), 0x35200100, ri16(IL, 5, 0x1320), ri16(IL, 6, 0xDF0), ri16(IL, 10, 0x5A5A),
            i10(STQD, 10, 5, 0), i10(LQD, 9, 6, 0), ri16(IL, 0, 0x240), 0x35000000]

    # One MFC GET through the channels: LSA 16, EAH 17, EAL 18, size 19, tag 20, command 21.
    def get(lsa, ea, size):
        return [ri16(IL, 4, lsa), wrch(4, 16), ri16(IL, 4, 0), wrch(4, 17), ri16(ILHU, 5, ea >> 16),
                ri16(IOHL, 5, ea & 0xFFFF), wrch(5, 18), ri16(IL, 4, size), wrch(4, 19), ri16(IL, 4, 8),
                wrch(4, 20), ri16(IL, 4, 0x40), wrch(4, 21)]

    dma = [*get(0x4000, 0x20000, 0x80), *get(0x1000, 0x20100, 0x80), *get(0x2000, 0x20200, 0), ri16(IL, 0, 0x240),
           0x35000000]
    lane = [ri16(IL, 5, 0x30), i10(LQD, 12, 5, 0), ri16(IL, 10, 0x1234), ri16(ILHU, 13, 0xABCD), ri16(IOHL, 13, 0xEF01),
            i10(STQD, 13, 5, 0), i10(LQD, 13, 5, 0), ri16(IL, 0, 0x240), 0x35000000]

    def body(words, pc):
        lines = []
        for word in words:
            lines += SPULifter()._translate(spu_decode(word, pc),
                                            LiftedFunction(name='probe', start_addr=pc, end_addr=pc + 4)).split('\n')
            pc += 4
        return '\n'.join(lines)

    return ('/* Lifted by scripts/check_spu_lane_trace.py. Do not edit. */\n'
            'static void lifted_edge_job(spu_context* c) { spu_context* ctx = c;\n' + body(edge, 0x4000) + '\n}\n'
            'static void lifted_poll_job(spu_context* c) { spu_context* ctx = c;\n' + body(poll, 0x5000) + '\n}\n'
            'static void lifted_dma_job(spu_context* c) { spu_context* ctx = c;\n' + body(dma, 0x6000) + '\n}\n'
            'static void lifted_lane_job(spu_context* c) { spu_context* ctx = c;\n' + body(lane, 0x7000) + '\n}\n')


def crlf(text):
    return text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8', errors='surrogateescape')


def read(path):
    return path.read_bytes().decode('utf-8', errors='surrogateescape').replace('\r\n', '\n')


def stage(out, label, changes=()):
    """Copy the runtime, plant the defect, write the lifted header. Return the copy root."""
    src = out / label / 'src'
    shutil.rmtree(out / label, ignore_errors=True)   # a second run into the same directory starts from a clean copy
    for rel in TREES:
        if (SDK / rel).is_dir():
            shutil.copytree(SDK / rel, src / rel, ignore=shutil.ignore_patterns('__pycache__'))
        else:
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SDK / rel, src / rel)
    for rel, before, after in changes:
        path = src / rel
        text = read(path)
        assert text.count(before) == 1, (label, rel, text.count(before), before[:48])
        path.write_bytes(crlf(text.replace(before, after)))
    (src / 'runtime/spu/tests').mkdir(parents=True, exist_ok=True)
    (src / 'runtime/spu/tests/spu_lane_trace_call.h').write_bytes(crlf(lifted_header()))
    return src


def build(src, out, label, changes):
    target = out / label
    spu = src / 'runtime/spu'
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        compiler = env.get('MV_CLANG') or shutil.which('clang-cl')
        if not compiler:
            raise SystemExit('clang-cl plus the Visual Studio developer environment is required')
    else:
        env = os.environ.copy()
        compiler = env.get('CC') or shutil.which('cc')
    identity = subprocess.run([compiler, '--version'], capture_output=True, text=True, timeout=10)
    clang = 'clang' in identity.stdout.lower()
    sources = [FIXTURE, *[spu / n for n in NAMES], *[src / p for p in EXTRA]]
    if clang:
        sources.append(spu / 'spu_dispatch_mt.c')
    includes = [spu / 'tests', src / 'include', spu, src / 'runtime/platform', src / 'runtime/syscalls']
    (target / 'obj').mkdir()
    binary = target / ('test.exe' if os.name == 'nt' else 'test')
    if os.name == 'nt':
        command = [compiler, '/nologo', '/TC', '/std:c17', '/O1', '/UNDEBUG', '/MDd', '/D_CRT_SECURE_NO_WARNINGS',
                   '/DSPU_LANE_TRACE_GAME', *['/I' + str(p) for p in includes], *map(str, sources),
                   '/Fo' + str(target / 'obj') + os.sep, '/Fe' + str(binary), '/link', 'Synchronization.lib']
    else:
        command = [compiler, '-std=gnu17', '-O1', '-UNDEBUG', '-D_GNU_SOURCE', '-DSPU_LANE_TRACE_GAME',
                   *['-I' + str(p) for p in includes], *map(str, sources), '-pthread', '-lm', '-o', str(binary)]
    started = time.time()
    result = subprocess.run(command, capture_output=True, text=True, timeout=600, env=env)
    (target / 'build.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        print('\n'.join([x for x in (result.stdout + result.stderr).splitlines() if 'error' in x.lower()][-12:]))
    entry = dict(label=label, compiler=identity.stdout.splitlines()[0], returncode=result.returncode,
                 seconds=round(time.time() - started, 1),
                 mutated_sha256={rel: hashlib.sha256((src / rel).read_bytes()).hexdigest() for rel, _, _ in changes},
                 executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest() if binary.exists() else None,
                 runs=[])
    return binary, entry


def run(binary, entry, mode, env_extra, expect, absent):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('SPU_', 'SPURS_', 'YDKJ_', 'LBP_', 'GH3_', 'SEMTID', 'PS3_'))}
    env.update(env_extra)
    r = subprocess.run([str(binary), mode], cwd=binary.parent, env=env, capture_output=True, text=True, timeout=60)
    wrong = [k for k, n in expect if r.stderr.count(k) != n]
    leaked = [k for k in absent if k in r.stderr]
    ok = r.returncode == 0 and 'PASS' in r.stdout and not wrong and not leaked
    record = dict(mode=mode, env=env_extra, returncode=r.returncode, ok=ok, stdout=r.stdout.strip(),
                  wrong_count=wrong, leaked=leaked, stderr=r.stderr)
    entry['runs'].append(record)
    return ok, record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--production-only', action='store_true', help='Skip the source mutants')
    ap.add_argument('--only', nargs='*', help='Build these variants only: production, or mutant names')
    args = ap.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = (args.output or ROOT / 'temp/checks' / ('spu-lane-trace-' + stamp)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = dict(game_inputs=False, fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  lifter_sha256=hashlib.sha256((SDK / 'tools/spu_lifter.py').read_bytes()).hexdigest(),
                  variants=[])
    variants = [('production', ())]
    if not args.production_only:
        variants += [('mutant-' + name, [change]) for name, change in MUTANTS.items()]
    if args.only:
        wanted = {'production' if n == 'production' else 'mutant-' + n for n in args.only}
        assert wanted <= {label for label, _ in variants}, ('unknown variant', wanted)
        variants = [v for v in variants if v[0] in wanted]
    ok = True
    for label, changes in variants:
        src = stage(out, label, changes)
        binary, entry = build(src, out, label, changes)
        report['variants'].append(entry)
        if entry['returncode']:
            print('BUILD FAILED ' + label)
            ok = False
        else:
            failed = []
            for mode, env_extra, expect, absent in CASES:
                passed, record = run(binary, entry, mode, env_extra, expect, absent)
                note = '' if passed else ': wrong count ' + str(record['wrong_count']) + ', leaked ' + str(record['leaked'])
                if not passed:
                    failed.append(mode)
                print(('PASS ' if passed else 'FAIL ') + label + ' ' + mode + ' ' + str(env_extra) + note, flush=True)
            if changes:
                entry['killed'] = bool(failed)
                print(('KILLED ' if failed else 'SURVIVED ') + label + ' ' + str(failed), flush=True)
            ok &= bool(failed) if changes else not failed
        (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(('PASS ' if ok else 'FAIL ') + str(out / 'result.json'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
