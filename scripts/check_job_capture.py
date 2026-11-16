"""Exercise the actual game capture owner with authored observer dependencies."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler', default=os.environ.get('CC') or
                    (shutil.which('clang-cl') if os.name == 'nt' else None) or shutil.which('cc'))
parser.add_argument('--mutants', action='store_true')
args = parser.parse_args()
assert args.compiler
msvc = Path(args.compiler).stem.lower() in ('cl', 'clang-cl')
out = root / 'build/self-tests/job-capture-owner'
out.mkdir(parents=True, exist_ok=True)
include = root / 'vendor/ps3recomp/include'
source = root / 'src/motorstorm/job_capture.cpp'
fixture = root / 'scripts/fixtures/job_capture_owner.cpp'
storage = root / 'vendor/ps3recomp/runtime/diag/sized_trace.c'
snapshot_source = root / 'src/motorstorm/job_capture_snapshot.cpp'

def command(cmd, label):
    (out / (label + '-command.json')).write_text(json.dumps(cmd, indent=2))
    result = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=60)
    (out / (label + '.log')).write_text(result.stdout + result.stderr)
    return result

obj = out / ('sized.obj' if msvc else 'sized.o')
cc = [args.compiler, str(storage)] + (['/nologo', '/std:c17', '/O2', '/c', '/I'+str(include), '/Fo'+str(obj)]
    if msvc else ['-std=c17', '-O2', '-c', '-I'+str(include), '-o', str(obj)])
result = command(cc, 'storage-build')
assert result.returncode == 0, result.stdout + result.stderr

def run(src, name, snapshot=snapshot_source):
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    compiler = args.compiler if msvc else (shutil.which('c++') or args.compiler)
    cmd = [compiler, str(src), str(snapshot), str(fixture), str(obj)]
    if msvc:
        cmd += ['/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(include),
                '/I'+str(source.parent), '/Fe'+str(exe)]
    else:
        cmd += ['-std=c++17', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-pthread',
                '-I'+str(include), '-I'+str(source.parent), '-o', str(exe)]
    built = command(cmd, name + '-build')
    assert built.returncode == 0, built.stdout + built.stderr
    return command([str(exe)], name + '-run')

result = run(source, 'actual')
assert result.returncode == 0, result.stdout + result.stderr
print('PASS capture owner, concurrent records, rollback, loss and partial visits')
defs = ['PS3_EXECUTION_OBSERVATION=1', 'PS3_SPURS_SCHEDULER_OBSERVATION=1']
objects = []
for name in ('spu_execution_observer', 'spurs_scheduler_observer'):
    observer = root / ('vendor/ps3recomp/runtime/diag/' + name + '.c')
    observer_obj = out / (name + ('.obj' if msvc else '.o'))
    cc = [args.compiler, str(observer)] + (
        ['/nologo', '/std:c17', '/O2', '/c', '/I'+str(include), '/Fo'+str(observer_obj)] + ['/D'+d for d in defs]
        if msvc else ['-std=c17', '-O2', '-c', '-I'+str(include), '-o', str(observer_obj)] + ['-D'+d for d in defs])
    result = command(cc, name + '-build')
    assert result.returncode == 0, result.stdout + result.stderr
    objects.append(observer_obj)
exe = out / ('integration.exe' if os.name == 'nt' else 'integration')
compiler = args.compiler if msvc else (shutil.which('c++') or args.compiler)
(out/'ppu_recomp.h').write_text('#pragma once\n#include <stdint.h>\nstruct ppu_context { uint64_t gpr[32]; uint32_t reserve_addr; uint64_t lr; };\n')
cmd = [compiler, str(source), str(snapshot_source), str(root/'src/motorstorm/job_queue_lifecycle.cpp'), str(root/'scripts/fixtures/job_capture_integration.cpp'), str(obj)] + list(map(str, objects))
cmd += (['/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(include), '/I'+str(out), '/Fe'+str(exe)] + ['/D'+d for d in defs]
        if msvc else ['-std=c++17', '-O2', '-UNDEBUG', '-pthread', '-I'+str(include), '-I'+str(out), '-o', str(exe)] + ['-D'+d for d in defs])
result = command(cmd, 'integration-build')
assert result.returncode == 0, result.stdout + result.stderr
result = command([str(exe)], 'integration-run')
assert result.returncode == 0, result.stdout + result.stderr
print('PASS execution, scheduler and queue-call observer integration')
if args.mutants:
    original = source.read_text()
    old = 'increment(c->excluded_queue_call); return;'
    assert original.count(old) == 1
    mutant = out / 'queue-hidden-exclusion.cpp'
    mutant.write_text(original.replace(old, 'return;'))
    mutant_exe = out / ('queue-mutant.exe' if os.name == 'nt' else 'queue-mutant')
    mutant_cmd = [str(mutant) if part == str(source) else str(mutant_exe) if part == '/Fe'+str(exe) else part for part in cmd]
    if msvc:
        mutant_cmd = ['/Fe'+str(mutant_exe) if part == str(mutant_exe) else part for part in mutant_cmd]
    else:
        mutant_cmd = [str(mutant_exe) if part == str(exe) else part for part in mutant_cmd]
    mutant_cmd.append(('/I' if msvc else '-I') + str(source.parent))
    built = command(mutant_cmd, 'queue-mutant-build')
    assert built.returncode == 0, built.stdout + built.stderr
    result = command([str(mutant_exe)], 'queue-mutant-run')
    assert result.returncode != 0 and 'metadata.excluded_queue_call == 2' in result.stdout + result.stderr
    print('PASS rejected hidden queue exclusions')
if os.name == 'nt' and msvc:
    summary = out / 'job_capture_summary.exe'
    cmd = [args.compiler, str(root/'scripts/job_capture_summary.cpp'), str(snapshot_source),
           '/nologo', '/std:c++17', '/EHsc', '/O2', '/DJOB_CAPTURE_READER_ONLY',
           '/I'+str(include), '/Fe'+str(summary)]
    result = command(cmd, 'summary-build')
    assert result.returncode == 0, result.stdout + result.stderr
    exe = out / 'control.exe'
    cmd = [args.compiler, str(source), str(snapshot_source),
           str(root/'src/motorstorm/job_capture_control.cpp'),
           str(root/'scripts/fixtures/job_capture_control.cpp'), str(obj),
           '/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(include), '/Fe'+str(exe)]
    result = command(cmd, 'control-build')
    assert result.returncode == 0, result.stdout + result.stderr
    queue_control = out / 'control-queue.exe'
    ppu_source = (root/'vendor/ps3recomp/runtime/ppu/ppu_loader.cpp').read_text()
    start = ppu_source.index('extern "C" int ppu_stdcx64(')
    opening = ppu_source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (ppu_source[end] == '{') - (ppu_source[end] == '}')
        end += 1
    actual_store = ppu_source[start:end]
    template = (root/'scripts/fixtures/job_capture_control.cpp').read_text()
    scaffold = r'''
#ifdef PORT_QUEUE_CALL_OBSERVATION
alignas(8) static uint8_t memory[512]{};
static uint8_t* vm_base = memory;
static ppu_context* g_active_ctx;
static const ps3_atomic_observer* s_ppu_atomic_observer;
static int resv_off(){return 1;} static int resv_diag(){return 0;}
static void resv_check_reg(ppu_context*){} static volatile LONG* resv_slot(uint64_t){static LONG x; return &x;}
static void resv_lock(volatile LONG*){} static void resv_unlock(volatile LONG*){}
static int spu_coh_is_reserved(uint32_t){return 0;} static void spu_lockline_lock(){} static void spu_lockline_unlock(){}
static void spu_coh_notify_write(uint32_t){} static void ppu_resv_break(uint64_t){}
static uint32_t g_ww_lo, g_ww_hi;
static void wp_hit(uint32_t,uint32_t,uint32_t,const char*,void*){}
static void ppu_ww_note_atomic(uint32_t,uint32_t,int,void*){}
''' + actual_store + r'''
static void fixture_real_store(ppu_context* ctx) {
    g_active_ctx = ctx; s_ppu_atomic_observer = ppu;
    static unsigned calls;
    assert(ppu_stdcx64(0x100, 0, ctx->gpr[5]) == (calls++ == 0));
}
#endif
'''
    assert template.count('/* FIXTURE_REAL_PPU_STORE */') == 1
    queue_fixture = out/'queue-control-fixture.cpp'
    template = template.replace('"job_capture_owner.cpp"', '"'+str(root/'scripts/fixtures/job_capture_owner.cpp').replace('\\', '/')+'"')
    template = template.replace('"../../src/motorstorm/job_capture_control.h"', '"'+str(root/'src/motorstorm/job_capture_control.h').replace('\\', '/')+'"')
    queue_fixture.write_text(template.replace('/* FIXTURE_REAL_PPU_STORE */', scaffold))
    queue_cmd = [args.compiler, str(source), str(snapshot_source),
                 str(root/'src/motorstorm/job_capture_control.cpp'), str(root/'src/motorstorm/job_queue_lifecycle.cpp'),
                 str(queue_fixture), str(obj), '/nologo', '/std:c++17', '/EHsc', '/O2',
                 '/UNDEBUG', '/DPORT_QUEUE_CALL_OBSERVATION=1', '/DPS3_ATOMIC_OBSERVATION=1', '/I'+str(include), '/I'+str(out), '/I'+str(root/'scripts/fixtures'), '/Fe'+str(queue_control)]
    result = command(queue_cmd, 'queue-control-build')
    assert result.returncode == 0, result.stdout + result.stderr
    with tempfile.TemporaryDirectory(dir=out) as directory:
        result = command([str(queue_control), directory, 'conflict'], 'queue-control-conflict')
        assert result.returncode == 0, result.stdout + result.stderr
        with tempfile.TemporaryDirectory(dir=out) as queue_directory:
            result = command([str(queue_control), queue_directory, 'run'], 'queue-control-run')
            assert result.returncode == 0, result.stdout + result.stderr
            result = command([str(summary), str(Path(queue_directory)/'snapshot.bin'), '--events'], 'queue-summary-events')
            assert result.returncode == 0, result.stdout + result.stderr
            from analyze_add_job_candidates import analyze as analyze_add_job
            joined = analyze_add_job(result.stdout.splitlines(), 0x100, 8)
            assert len(joined['candidates']) == 1 and joined['candidates'][0]['header'] == 0x123456789abcdef0
            assert joined['candidates'][0]['queue_argument'] == 0x200
        for name, path, mode in [('disabled', directory, 'disabled'),
                                 ('missing', str(Path(directory)/'missing'), 'invalid')]:
            result = command([str(exe), path, mode], 'control-' + name)
            assert result.returncode == 0, result.stdout + result.stderr
        stale = Path(directory)/'snapshot.bin'
        stale.write_bytes(b'sentinel')
        result = command([str(exe), directory, 'invalid'], 'control-stale')
        assert result.returncode == 0 and stale.read_bytes() == b'sentinel', result.stdout + result.stderr
        stale.unlink()
        result = command([str(exe), directory, 'run'], 'control-run')
        assert result.returncode == 0, result.stdout + result.stderr
        result = command([str(summary), str(Path(directory)/'snapshot.bin')], 'summary-run')
        assert result.returncode == 0, result.stdout + result.stderr
        info = json.loads(result.stdout)
        assert info['run_id'] and info['atomic'] == 1 and info['dropped_after'] == 0
        assert info['atomic_attempted'] == info['atomic_committed'] == 1
        assert info['atomic_clock_invalid'] == info['atomic_context_unknown'] == 1
        result = command([str(summary), str(Path(directory)/'snapshot.bin'), '--atomic-events'], 'summary-events')
        assert result.returncode == 0, result.stdout + result.stderr
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(lines) == 2 and lines[0]['type'] == 'atomic' and lines[1]['type'] == 'summary'
        assert lines[0]['address'] == 42 and lines[0]['before'] == '12000000' and lines[0]['after'] == 'ab000000'
        result = command([str(summary), str(Path(directory)/'snapshot.bin'), '--events'], 'summary-all-events')
        assert result.returncode == 0, result.stdout + result.stderr
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        assert [line['type'] for line in lines] == ['atomic', 'execution', 'scheduler', 'queue_call', 'summary']
        assert lines[1]['tick'] == 77 and lines[1]['context'] == 123 and lines[1]['target_pc'] == 456
        assert lines[2]['dispatch'] == 42 and lines[2]['workload_generation'] == 7
        assert lines[2]['tick_begin'] == 80 and lines[2]['tick_end'] == 81
        assert lines[3]['call_id'] == 99 and lines[3]['context'] == 123 and lines[3]['object'] == 456
        assert lines[3]['argument'] == 789 and lines[3]['operation'] == 2 and lines[3]['phase'] == 1
        assert 'record_flags' in lines[3] and 'host_dispatch' in lines[3]
        assert lines[3]['entry_lr'] == 0x87b83c
        assert lines[-1]['queue_call'] == 1 and lines[-1]['queue_clock_invalid'] == 0 and lines[-1]['queue_id_invalid'] == 0
        from analyze_queue_calls import analyze
        queue_analysis = analyze(result.stdout.splitlines())
        assert queue_analysis['entry_only'] == 1 and queue_analysis['paired_calls'] == 0
        from analyze_atomic_range import analyze as analyze_atomic
        atomic_analysis = analyze_atomic(result.stdout.splitlines(), 42, 4)
        assert len(atomic_analysis['events']) == 1
        assert atomic_analysis['events'][0]['after'] == 'ab000000'
        truncated = Path(directory)/'truncated.bin'
        truncated.write_bytes((Path(directory)/'snapshot.bin').read_bytes()[:-1])
        assert command([str(summary), str(truncated)], 'summary-truncated').returncode != 0
    print('PASS Windows control trigger and live snapshot')
if args.mutants:
    original = source.read_text()
    variants = {
        'rollback': ('clear_spu:\n    (void)ps3_atomic_observer_install_spu(nullptr);', 'clear_spu:',
                     '!ppu && !spu && !execution && !scheduler'),
        'thread-identity': ('r.flags = r.thread ? 0 : JOB_CAPTURE_THREAD_UNKNOWN;', 'r.flags = 0;',
                            'r.flags == JOB_CAPTURE_THREAD_UNKNOWN'),
        'payload': ('    r.value.atomic = *e;', '    r.value.atomic.context = e->context;',
                    'r.value.atomic.after[j] == static_cast<uint8_t>(~r.value.atomic.before[j])'),
        'visitor-failure': ('snapshot.consumer_failed = 1;', 'snapshot.consumer_failed = 0;',
                            'visited == 7 && snapshot.consumer_failed && snapshot.examined == 7 && snapshot.delivered == 6'),
        'append-failure': ('int result = ps3_sized_trace_append(c->trace, &r, sizeof(r));',
                           '(void)r; int result = PS3_SIZED_TRACE_INVALID;', 'info.unexpected_append_failures == 0'),
        'hidden-exclusions': ('increment(c->excluded_atomic); return 0;', 'return 0;',
                              'info.filter_mask == 7 && info.excluded_atomic == 4001'),
    }
    for name, (old, new, expected) in variants.items():
        assert original.count(old) == 1
        mutant = out / (name + '.cpp')
        mutant.write_text(original.replace(old, new))
        result = run(mutant, name)
        assert result.returncode != 0 and expected in result.stdout + result.stderr, (name, result.stdout, result.stderr)
        print('PASS rejected ' + name)
    original = snapshot_source.read_text()
    variants = {
        'snapshot-header': ('memcmp(header.magic, "MSJOB001", 8)', '0',
            '!job_capture_read_snapshot(file, read_record, &read_count, &loaded) && read_count == 0'),
        'snapshot-consumer': ('!consumer(user, index, &record)', '(static_cast<void>(consumer(user, index, &record)), 0)',
            '!job_capture_read_snapshot(file, reject_record, nullptr, &loaded)'),
    }
    for name, (old, new, expected) in variants.items():
        assert original.count(old) == 1
        mutant = out / (name + '.cpp')
        mutant.write_text(original.replace(old, new))
        result = run(source, name, mutant)
        assert result.returncode != 0 and expected in result.stdout + result.stderr, (name, result.stdout, result.stderr)
        print('PASS rejected ' + name)
