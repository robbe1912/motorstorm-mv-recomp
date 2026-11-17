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
# Test-only seeding exercises counters near saturation without impractical loops.
exclusion_fixture = root / 'scripts/fixtures/job_capture_exclusions.cpp'
seed = r"""
extern "C" void fixture_seed_exclusions(job_capture* c, bool single) {
    initialize(c->excluded_atomic);
    if (single) {
        const auto index = UINT64_C(11400714819323198485) >> 58;
        c->excluded_atomic.shards[index].value.store(UINT64_MAX, std::memory_order_relaxed);
    } else {
        c->excluded_atomic.shards[0].value.store(UINT64_MAX - 1, std::memory_order_relaxed);
        c->excluded_atomic.shards[1].value.store(3, std::memory_order_relaxed);
    }
}
extern "C" unsigned fixture_used_exclusion_shards(job_capture* c) {
    unsigned used = 0;
    for (const auto& shard : c->excluded_atomic.shards)
        used += shard.value.load(std::memory_order_relaxed) != 0;
    return used;
}
"""
original_fixture = fixture
fixture = exclusion_fixture
exclusion_source = out / 'exclusion-source.cpp'
exclusion_source.write_text(source.read_text(encoding='utf-8') + seed, encoding='utf-8')
result = run(exclusion_source, 'exclusions')
assert result.returncode == 0, result.stdout + result.stderr
print('PASS concurrent exclusion shards, collisions, unknown IDs and saturation')
if args.mutants:
    controls = {
        'one-hot-counter': ('const auto index = (thread * UINT64_C(11400714819323198485)) >> 58;',
            'const auto index = thread * UINT64_C(0);'),
        'missed-shards': ('for (const auto& shard : counter.shards) {',
            'for (unsigned i = 0; i < 1; ++i) { const auto& shard = counter.shards[i];'),
        'wrapped-total': ('if (value > UINT64_MAX - result) return UINT64_MAX;', ''),
        'wrapped-increment': ('previous != UINT64_MAX && !counter.compare_exchange_weak(',
            '!counter.compare_exchange_weak('),
    }
    actual = source.read_text(encoding='utf-8')
    for name, (old, new) in controls.items():
        assert actual.count(old) == 1, name
        changed = out / (name + '.cpp')
        changed.write_text(actual.replace(old, new) + seed, encoding='utf-8')
        result = run(changed, name)
        assert result.returncode != 0, name + ' survived'
        print('PASS rejected ' + name)
fixture = original_fixture

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
cmd += (['/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(include), '/I'+str(out), '/I'+str(source.parent), '/Fe'+str(exe)] + ['/D'+d for d in defs]
        if msvc else ['-std=c++17', '-O2', '-UNDEBUG', '-pthread', '-I'+str(include), '-I'+str(out), '-I'+str(source.parent), '-o', str(exe)] + ['-D'+d for d in defs])
result = command(cmd, 'integration-build')
assert result.returncode == 0, result.stdout + result.stderr
result = command([str(exe)], 'integration-run')
assert result.returncode == 0, result.stdout + result.stderr
print('PASS execution, scheduler and queue-call observer integration')

if args.mutants:
    window_source = source.parent / 'job_capture_window.h'
    window_text = window_source.read_text(encoding='utf-8')
    window_copy = out / window_source.name
    history_controls = {
        'drops-startup-history': ('retain_queue_history(queue_history)', 'retain_queue_history(false)'),
        'admits-startup-publications': (
            '(event->operation != job_queue_operation::reset &&\n                 event->operation != job_queue_operation::init)',
            '(false && event->operation != job_queue_operation::init)'),
        'history-ignores-filter': (
            'return !w.original.accept_queue_call ||\n            w.original.accept_queue_call(w.original.user, event);',
            'return 1;'),
    }
    try:
        for name, (old, new) in history_controls.items():
            assert window_text.count(old) == 1, name
            window_copy.write_text(window_text.replace(old, new), encoding='utf-8')
            built = command(cmd, name + '-build')
            assert built.returncode == 0, built.stdout + built.stderr
            ran = command([str(exe)], name + '-run')
            assert ran.returncode != 0, name + ' survived'
            print('PASS rejected ' + name)
    finally:
        window_copy.unlink(missing_ok=True)

filter_source = root / 'src/motorstorm/job_capture_execution_filter.h'
filter_fixture = root / 'scripts/fixtures/job_capture_execution_filter.cpp'

def run_filter(text, name):
    directory = out / name
    directory.mkdir(exist_ok=True)
    (directory / filter_source.name).write_text(text, encoding='utf-8')
    filter_exe = directory / ('fixture.exe' if os.name == 'nt' else 'fixture')
    cmd = [compiler, str(filter_fixture)]
    cmd += (['/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(directory), '/Fe'+str(filter_exe)]
            if msvc else ['-std=c++17', '-O2', '-UNDEBUG', '-I'+str(directory), '-o', str(filter_exe)])
    built = command(cmd, name+'-build')
    assert built.returncode == 0, built.stdout + built.stderr
    return command([str(filter_exe)], name+'-run')

filter_text = filter_source.read_text(encoding='utf-8')
filtered = run_filter(filter_text, 'execution-filter')
assert filtered.returncode == 0, filtered.stdout + filtered.stderr
if args.mutants:
    filter_mutants = {
        'filter-admits-all': ('if (!count) return true;', 'if (count <= maximum_pcs) return true;'),
        'filter-source-only': ('pcs[i] == source_pc || pcs[i] == target_pc', 'pcs[i] == source_pc'),
        'filter-target-only': ('pcs[i] == source_pc || pcs[i] == target_pc', 'pcs[i] == target_pc'),
        'filter-outside-store': ('pc > 0x3fffcu || (pc & 3u)', '(pc & 3u)'),
        'filter-trailing-token': ('specification.remove_prefix(separator + 1);',
                                  'specification.remove_prefix(separator + 1); if (specification.empty()) { *this = parsed; return true; }'),
        'filter-over-limit': ('if (parsed.count == maximum_pcs) return false;',
                             'if (parsed.count == maximum_pcs) { *this = parsed; return true; }'),
        'filter-rejects-full': ('if (!count) return true;', 'if (!count) return false;'),
    }
    for name, (old, new) in filter_mutants.items():
        assert filter_text.count(old) == 1, name
        result = run_filter(filter_text.replace(old, new), name)
        assert result.returncode != 0, name+' survived'
print('PASS execution PC filtering and parser controls')
if args.mutants:
    original = source.read_text()
    old = 'exclude(c, c->excluded_queue_call); return;'
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
                 '/UNDEBUG', '/DPORT_QUEUE_CALL_OBSERVATION=1', '/DPS3_ATOMIC_OBSERVATION=1', '/I'+str(include), '/I'+str(out), '/I'+str(root/'scripts/fixtures'), '/I'+str(source.parent), '/Fe'+str(queue_control)]
    result = command(queue_cmd, 'queue-control-build')
    assert result.returncode == 0, result.stdout + result.stderr
    if args.mutants:
        control_source = root / 'src/motorstorm/job_capture_control.cpp'
        actual_control = control_source.read_text(encoding='utf-8')
        needle = 'window(select_execution(config, &execution_filter), true)'
        assert actual_control.count(needle) == 1
        changed_control = out / 'controller-no-history.cpp'
        changed_control.write_text(actual_control.replace(needle,
            'window(select_execution(config, &execution_filter), false)'), encoding='utf-8')
        changed_command = [str(changed_control) if part == str(control_source) else part
                           for part in queue_cmd]
        built = command(changed_command, 'controller-no-history-build')
        assert built.returncode == 0, built.stdout + built.stderr
        with tempfile.TemporaryDirectory(dir=out) as mutant_directory:
            ran = command([str(queue_control), mutant_directory, 'run'], 'controller-no-history-run')
            assert ran.returncode != 0 and 'controller omitted startup lifecycle' in ran.stdout + ran.stderr
        print('PASS rejected controller startup-history omission')
        built = command(queue_cmd, 'queue-control-restored-build')
        assert built.returncode == 0, built.stdout + built.stderr
    with tempfile.TemporaryDirectory(dir=out) as directory:
        with tempfile.TemporaryDirectory(dir=out) as filtered_directory:
            result = command([str(queue_control), filtered_directory, 'filtered'], 'queue-control-filtered')
            assert result.returncode == 0, result.stdout + result.stderr
        result = command([str(queue_control), directory, 'invalid-filter'], 'queue-control-invalid-filter')
        assert result.returncode == 0, result.stdout + result.stderr
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
        'hidden-exclusions': ('exclude(c, c->excluded_atomic); return 0;', 'return 0;',
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
