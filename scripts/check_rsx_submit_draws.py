"""Compile the production RSX_SUBMIT_DRAWS parser against authored values."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    clean = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", lambda m: ' ' * len(m[0]), text)
    depth, i = 1, opening + 1
    while depth:
        depth += (clean[i] == '{') - (clean[i] == '}')
        i += 1
    return text[start:i]
ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
FIXTURE = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint32_t u32;
#define MAX_DRAWS 2048
static const char* env_value;
static const char* rsx_env_once(const char* name) { (void)name; return env_value; }
@FUNCTION@
int main(int argc, char** argv) {
    env_value = argc > 1 ? argv[1] : NULL;
    u32 first = submit_draws_cap(), second = submit_draws_cap();
    if (first != second) return 3;   /* parsed once */
    printf("cap=%u\n", first);
    return 0;
}
'''
def compile_c(source, exe, cwd):
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        command = [env['MV_CLANG'], '/nologo', str(source), '/Fe' + str(exe), '/Fo' + str(cwd) + os.sep]
    else:
        command = [env.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(exe)]
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=60)
def main():
    source = (VIDEO / 'rsx_d3d12_backend.c').read_text(encoding='utf-8')
    body = function(source, 'static u32 submit_draws_cap(void)')
    capacity = function(source, 'static void ensure_draw_record_capacity(void)')
    assert capacity.index('cpu_surface_flush_recorded(0);') < capacity.index('submit_draws_cap()') < capacity.index('rsx_record_batch_room(')
    with tempfile.TemporaryDirectory(prefix='submit-draws-') as directory:
        out = Path(directory); unit = out / 'test.c'; exe = out / ('test.exe' if os.name == 'nt' else 'test')
        unit.write_text(FIXTURE.replace('@FUNCTION@', body))
        compile_c(unit, exe, out)
        accepted = {None: 0, '16': 16, '256': 256, '0256': 256, '2048': 2048}
        for value, cap in accepted.items():
            r = subprocess.run([str(exe)] + ([] if value is None else [value]), capture_output=True, text=True, timeout=10)
            if r.returncode != 0 or r.stdout.strip() != f'cap={cap}':
                raise RuntimeError(f'{value!r}: {r.returncode} {r.stdout} {r.stderr}')
            if cap and 'RSX_SUBMIT_DRAWS=' not in r.stderr:
                raise RuntimeError(f'{value!r}: enabled cap not announced')
        # A bad value keeps the process running: cap off, reported once.
        rejected = ('', '0', '15', '2049', '4096', '99999999999', '256x', ' 256', '-16', '0x100')
        def off(value):
            r = subprocess.run([str(exe), value], capture_output=True, text=True, timeout=10)
            return (r.returncode == 0 and r.stdout.strip() == 'cap=0' and r.stderr.count('RSX_SUBMIT_DRAWS') == 1
                    and 'RSX_SUBMIT_DRAWS must be' in r.stderr and 'the cap is off' in r.stderr), r
        for value in rejected:
            ok, r = off(value)
            if not ok:
                raise RuntimeError(f'{value!r} did not leave the cap off: {r.returncode} {r.stdout} {r.stderr}')
        bad_exit = 'the cap is off\\n", (unsigned)MAX_DRAWS, value);\n        return 0;'
        assert body.count(bad_exit) == 1
        for name, replacement in (('abort', 'abort();'), ('use-value', '')):
            unit.write_text(FIXTURE.replace('@FUNCTION@', body.replace(bad_exit, bad_exit.replace('return 0;', replacement))))
            compile_c(unit, exe, out)
            if any(off(value)[0] for value in ('15', '2049', '256x')):
                raise RuntimeError(name + ' mutant was not exposed')
    print(f'PASS: RSX_SUBMIT_DRAWS parses {len(accepted)} values (unset = off); {len(rejected)} malformed or out-of-range values leave it off without stopping the process; 2 mutants exposed')
if __name__ == '__main__':
    main()
