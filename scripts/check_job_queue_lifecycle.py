"""Compile the provisional queue-call adapter against an authored context."""
import argparse
import json
import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from native_game_binding import Contract, transform

args_parser = argparse.ArgumentParser(description=__doc__)
args_parser.add_argument('--mutants', action='store_true')
args = args_parser.parse_args()

root = Path(__file__).resolve().parents[1]
out = root / 'build/self-tests/job-queue-lifecycle'
out.mkdir(parents=True, exist_ok=True)
compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name == 'nt' else 'c++')
assert compiler, 'Set MV_CLANG/CXX for the fixture'
msvc = Path(compiler).stem.lower() in ('cl', 'clang-cl')
report = {'mutants': [], 'commands': [], 'source_sha256': hashlib.sha256((root/'src/motorstorm/job_queue_lifecycle.cpp').read_bytes()).hexdigest(),
          'fixture_sha256': {name: hashlib.sha256((root/'scripts/fixtures'/name).read_bytes()).hexdigest()
                             for name in ('job_queue_lifecycle.cpp', 'job_queue_lifecycle_threads.cpp')}}
with tempfile.TemporaryDirectory(dir=out) as directory:
    base = Path(directory)
    (base/'ppu_recomp.h').write_text('#pragma once\n#include <stdint.h>\nstruct ppu_context { uint64_t gpr[32]; uint64_t lr; };\nvoid guest_reset(ppu_context*);\nvoid guest_init(ppu_context*);\nvoid guest_add(ppu_context*);\n')
    fixture = base/'queue_fixture.cpp'
    shutil.copyfile(root/'scripts/fixtures/job_queue_lifecycle.cpp', fixture)
    exe = base/('test.exe' if os.name == 'nt' else 'test')
    cmd = [compiler, str(root/'src/motorstorm/job_queue_lifecycle.cpp'),
           str(fixture)]
    if msvc:
        cmd += ['/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(base),
                '/I'+str(root/'src/motorstorm'), '/Fo'+str(base)+os.sep, '/Fe'+str(exe)]
    else:
        cmd += ['-std=c++17', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
                '-I'+str(base), '-I'+str(root/'src/motorstorm'), '-o', str(exe)]
    subprocess.run(cmd, cwd=base, check=True)
    subprocess.run([str(exe)], check=True)
    production = (root/'src/motorstorm/job_queue_lifecycle.cpp').read_text(encoding='utf-8')
    exposed = production + '\nvoid queue_fixture_set_id(uint64_t value) { next_id.store(value); }\n'
    threaded_source = base/'threaded-source.cpp'
    threaded_source.write_text(exposed, encoding='utf-8')
    threads = root/'scripts/fixtures/job_queue_lifecycle_threads.cpp'
    threaded_command = [compiler, str(threaded_source), str(threads)] + cmd[3:]
    if not msvc:
        threaded_command.append('-pthread')
    subprocess.run(threaded_command, cwd=base, check=True)
    subprocess.run([str(exe)], check=True)
    if args.mutants:
        variants = {
            'wrong-object': ('static_cast<std::uint32_t>(ctx->gpr[3])', 'static_cast<std::uint32_t>(ctx->gpr[4])'),
            'wrong-entry-lr': ('0, ctx->lr};', '0, (ctx->lr ^ UINT64_C(1))};'),
            'wrong-header': ('? ctx->gpr[5] : 0', '? UINT64_C(1) : 0'),
            'reused-call-id': ('return current;', 'return 1;'),
            'post-call-arguments': ('event.phase = job_queue_phase::returned;',
                                    'event.object = static_cast<std::uint32_t>(ctx->gpr[3]); event.phase = job_queue_phase::returned;'),
            'false-return': ('    original(ctx);\n    event.phase = job_queue_phase::returned;\n    target->event(target->user, event);',
                             '    event.phase = job_queue_phase::returned;\n    target->event(target->user, event);\n    original(ctx);'),
            'disabled-observation': ('if (!target) {', 'if (true) {'),
            'exhaustion-reuses-id': ('return current;', 'return current ? current : 1;'),
        }
        for label, (old, new) in variants.items():
            assert exposed.count(old) == 1, label
            mutant = out/(label+'.cpp')
            mutant.write_text(exposed.replace(old, new), encoding='utf-8')
            test_fixture = threads if label == 'exhaustion-reuses-id' else fixture
            mutant_command = [compiler, str(mutant), str(test_fixture)] + cmd[3:]
            if not msvc:
                mutant_command.append('-pthread')
            built = subprocess.run(mutant_command, cwd=base, capture_output=True, text=True)
            (out/(label+'-build.log')).write_text(built.stdout+built.stderr, encoding='utf-8')
            assert built.returncode == 0, built.stdout+built.stderr
            ran = subprocess.run([str(exe)], cwd=base, capture_output=True, text=True)
            (out/(label+'-run.log')).write_text(ran.stdout+ran.stderr, encoding='utf-8')
            assert ran.returncode != 0, label
            report['mutants'].append(label)
            report['commands'].append({'command': mutant_command, 'build': built.returncode, 'run': ran.returncode})
    # Exercise the real binding transformation and adapter together, including
    # direct and address-taken dispatch, using only authored source.
    reset = b'void guest_reset(ppu_context* ctx) { ctx->gpr[3] += 10; }'
    init = b'void guest_init(ppu_context* ctx) { ctx->gpr[4] += 20; }'
    add = b'void guest_add(ppu_context* ctx) { ctx->gpr[5] += 1; }'
    source = b'#include "ppu_recomp.h"\n'+reset+b'\n'+init+b'\n'+add+b'\nauto reset_table=&guest_reset;\n'
    a = Contract('authored', hashlib.sha256(reset).hexdigest(), 'guest_reset',
                 'game_original_queue_reset', 'motorstorm_observe_queue_reset')
    b = Contract('authored', hashlib.sha256(init).hexdigest(), 'guest_init',
                 'game_original_queue_init', 'motorstorm_observe_queue_init')
    c = Contract('authored', hashlib.sha256(add).hexdigest(), 'guest_add',
                 'game_original_add_job', 'motorstorm_observe_add_job')
    bound = base/'bound.cpp'
    bound.write_bytes(transform(transform(transform(source, a), b), c))
    caller = base/'bound_caller.cpp'
    caller.write_text('''#include "ppu_recomp.h"
#include "job_queue_lifecycle.h"
#include <cassert>
void guest_init(ppu_context*);
extern void (*reset_table)(ppu_context*);
static job_queue_event events[6]; static int count;
static void observe(void*, const job_queue_event& e) noexcept { events[count++] = e; }
int main() { ppu_context c{}; c.gpr[3]=3; c.gpr[4]=4;
  job_queue_observer owner{nullptr,observe}; assert(job_queue_observer_install(&owner));
  c.gpr[5]=0x123456789abcdef0ULL; reset_table(&c); guest_init(&c); guest_add(&c);
  assert(c.gpr[3]==13 && c.gpr[4]==24 && count==6 && c.gpr[5]==0x123456789abcdef1ULL);
  assert(events[4].operation==job_queue_operation::add_job && events[4].header==0x123456789abcdef0ULL && events[5].header==events[4].header);
  assert(events[0].operation==job_queue_operation::reset && events[0].call_id==events[1].call_id);
  assert(events[2].operation==job_queue_operation::init && events[2].call_id==events[3].call_id);
  assert(events[0].call_id!=events[2].call_id && events[0].phase==job_queue_phase::enter);
  assert(events[1].phase==job_queue_phase::returned); }
''')
    combined_cmd = [compiler, str(root/'src/motorstorm/job_queue_lifecycle.cpp'), str(bound), str(caller)] + cmd[3:]
    subprocess.run(combined_cmd, cwd=base, check=True)
    subprocess.run([str(exe)], check=True)
(out/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('PASS queue-call observation, concurrent IDs, interrupted calls, exhaustion and', len(report['mutants']), 'mutants')
