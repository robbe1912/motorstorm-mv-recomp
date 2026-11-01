#!/usr/bin/env python3
"""Exercise generated SPURS registration through the production PPU HLE bridge.

Uses exact production initializer/wrapper bodies and authored stubs for unrelated
imports. The full cellSpurs translation unit is covered by the scheduler fixture.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
toolkit = root/'vendor/ps3recomp'
parser = argparse.ArgumentParser()
parser.add_argument('--compiler', default=os.environ.get('CXX') or shutil.which('clang-cl' if os.name == 'nt' else 'c++'))
parser.add_argument('--output', type=Path, default=root/'build/self-tests/spurs-attribute-hle')
parser.add_argument('--mutants', action='store_true')
args = parser.parse_args()
assert args.compiler
env = {k:v for k,v in os.environ.items() if not k.startswith(('PS3_', 'SPURS_', 'SPU_', 'YDKJ_', 'FLOW_'))}
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
source = (toolkit/'libs/spurs/cellSpurs.c').read_text()

def function(signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[start:end]

enum_end = source.index('};', source.index('WKATTR_REVISION')) + 2
enum_start = source.rindex('enum {', 0, enum_end)
slice_source = ('#include "cellSpurs.h"\n#include "ppu_memory.h"\n#include <stdio.h>\n' +
                source[enum_start:enum_end] + '\n' +
                function('s32 _cellSpursWorkloadAttributeInitialize(') + '\n' +
                function('void ps3_spurs_workload_attribute_initialize(') + '\n')
(out/'attribute.c').write_text(slice_source)
(out/'ppu_recomp.h').write_text('#include "ppu_context.h"\n')
subprocess.run([sys.executable, str(root/'scripts/gen_hle_nids.py'), 'cellSpurs', '--out', str(out/'nids.cpp')],
               check=True, timeout=20)
nids = (out/'nids.cpp').read_text()
assert nids.count('ps3_hle_register_ctx(0xEFEB2679u,') == 1
assert 'ps3_hle_register(0xEFEB2679u,' not in nids
names = re.findall(r'^    void (\w+)\(void\);$', nids, re.M)
stubs = '#include <stdlib.h>\nextern "C" {\n' + ''.join(
    'void '+name+'(void) { abort(); }\n' for name in names if name != '_cellSpursWorkloadAttributeInitialize') + '}\n'
(out/'stubs.cpp').write_text(stubs)
includes = [toolkit/'include', toolkit/'runtime/ppu', toolkit/'libs/spurs', out]
if os.name == 'nt':
    common = ['/nologo','/O2','/UNDEBUG'] + ['/I'+str(p) for p in includes]
    ccmd = [args.compiler, '/std:c17', '/TC', '/c', *common, str(out/'attribute.c'), '/Fo'+str(out/'attribute.obj')]
    cmd = [args.compiler, '/std:c++17', *common, str(root/'scripts/fixtures/spurs_attribute_hle.cpp'),
           str(toolkit/'runtime/ppu/ppu_hle.cpp'), str(toolkit/'runtime/memory/guest_read_sync.c'),
           str(out/'nids.cpp'), str(out/'stubs.cpp'), str(out/'attribute.obj'), '/Fe'+str(out/'test.exe')]
    exe = out/'test.exe'
else:
    inc = ['-I'+str(p) for p in includes]
    ccmd = [os.environ.get('CC','cc'), '-std=gnu17','-O2','-UNDEBUG',*inc,'-c',str(out/'attribute.c'),'-o',str(out/'attribute.o')]
    cmd = [args.compiler,'-std=c++17','-O2','-UNDEBUG',*inc,str(root/'scripts/fixtures/spurs_attribute_hle.cpp'),
           str(toolkit/'runtime/ppu/ppu_hle.cpp'),str(toolkit/'runtime/memory/guest_read_sync.c'),
           str(out/'nids.cpp'),str(out/'stubs.cpp'),str(out/'attribute.o'),'-o',str(out/'test')]
    exe = out/'test'
for label, command in [('compile',ccmd),('link',cmd),('run',[str(exe)])]:
    result = subprocess.run(command, cwd=out, env=env, capture_output=True, text=True, timeout=120)
    (out/(label+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode:
        raise SystemExit(label+' failed; see '+str(out/(label+'.log')))
    print(result.stdout, end='')
if args.mutants:
    registration = re.search(r'^    ps3_hle_register_ctx\(0xEFEB2679u,.*\);$', nids, re.M)
    assert registration
    (out/'nids.cpp').write_text(nids[:registration.start()] + nids[registration.end():])
    result = subprocess.run(cmd, cwd=out, env=env, capture_output=True, text=True, timeout=120)
    (out/'missing-registration-link.log').write_text(result.stdout+result.stderr)
    assert result.returncode == 0, 'missing-registration mutant must compile'
    result = subprocess.run([str(exe)], cwd=out, env=env, capture_output=True, text=True, timeout=20)
    (out/'missing-registration-run.log').write_text(result.stdout+result.stderr)
    assert result.returncode != 0 and 'ps3_hle_has(0xefeb2679)' in result.stderr, 'missing-registration mutant escaped'
    print('PASS missing context registration rejected by actual HLE bridge')
