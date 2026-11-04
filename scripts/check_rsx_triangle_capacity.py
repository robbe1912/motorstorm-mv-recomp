"""Compile actual draw callbacks with authored storage/submission adapters."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def expand(source):
    start = source.index('typedef struct {')
    end = source.index('} D3D12DrawRecord;', start) + len('} D3D12DrawRecord;')
    first = source.index('static void d3d12_draw_arrays(')
    last = source.index('static void d3d12_bind_texture(', first)
    helper = source.find('static int vp_triangle_can_merge(')
    functions = source[helper if helper >= 0 else first:last]
    template = (ROOT / 'scripts/fixtures/rsx_triangle_capacity.c.in').read_text()
    return template.replace('@RECORD@', source[start:end]).replace('@HELPER@', '').replace('@CALLBACKS@', functions)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cc', default=None)
    parser.add_argument('--baseline')
    args = parser.parse_args()
    env = None
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
    args.cc = args.cc or (env['MV_CLANG'] if env else os.environ.get('CC', 'cc'))
    current = (ROOT / 'vendor/ps3recomp/libs/video/rsx_d3d12_backend.c').read_text()
    cases = [('current', current, False)]
    # An unconditional capacity reservation restores the original ordering defect.
    import re
    mutant, substitutions = re.subn(r'    if \(![^\n]*vp_triangle_can_merge[^\n]*\n        ensure_draw_record_capacity\(\);', '    ensure_draw_record_capacity();', current)
    if substitutions != 2:
        raise RuntimeError('preflight control did not modify source')
    cases.append(('reservation-before-merge', mutant, True))
    if args.baseline:
        old = subprocess.check_output(['git', 'show', args.baseline + ':vendor/ps3recomp/libs/video/rsx_d3d12_backend.c'], cwd=ROOT).decode()
        cases.append(('baseline', old, True))
    with tempfile.TemporaryDirectory(prefix='triangle-capacity-') as directory:
        out = Path(directory)
        for capacity in (4, 2048):
            for name, source, reject in cases:
                src = out / (name + '.c')
                exe = out / (name + ('.exe' if os.name == 'nt' else ''))
                src.write_text(expand(source))
                if Path(args.cc).name.lower() in ('clang-cl', 'clang-cl.exe', 'cl', 'cl.exe'):
                    command = [args.cc, '/nologo', '/std:c11', '/I' + str(ROOT / 'vendor/ps3recomp/include'), '/I' + str(ROOT / 'vendor/ps3recomp/libs/video'), '/DMAX_DRAWS=' + str(capacity), str(src), '/Fe' + str(exe), '/Fo' + str(out / (name + '.obj'))]
                else:
                    command = [args.cc, '-std=gnu11', '-I' + str(ROOT / 'vendor/ps3recomp/include'), '-I' + str(ROOT / 'vendor/ps3recomp/libs/video'), '-DMAX_DRAWS=' + str(capacity), str(src), '-o', str(exe)]
                subprocess.run(command, cwd=out, env=env, check=True, text=True, timeout=120)
                for indexed in (0, 1):
                    result = subprocess.run([str(exe), str(indexed)], capture_output=True, text=True, timeout=20)
                    if reject:
                        if result.returncode == 0 or 'FAIL' not in result.stderr:
                            raise RuntimeError(name + ' did not expose triangle loss: ' + result.stdout + result.stderr)
                    elif result.returncode or 'PASS exact triangle output' not in result.stdout:
                        raise RuntimeError(result.stdout + result.stderr)
                    print(f'{name}: capacity={capacity} indexed={indexed} ' + ('expected rejection' if reject else 'PASS'))


if __name__ == '__main__':
    main()
