"""Exercise actual record-capacity retirement with authored GPU adapters."""
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
ROOT=Path(__file__).resolve().parent.parent
VIDEO=ROOT/'vendor/ps3recomp/libs/video'
FIX=ROOT/'scripts/fixtures'

def compile_c(source, exe, include, cwd):
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        command = [env['MV_CLANG'], '/nologo', '/I' + str(include), str(source),
                   '/Fe' + str(exe), '/Fo' + str(cwd) + os.sep]
    else:
        command = [env.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra',
                   '-Wno-unused-function', '-Werror', '-I' + str(include), str(source), '-o', str(exe)]
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=60)
def main():
    source=(VIDEO/'rsx_d3d12_backend.c').read_text(encoding='utf-8')
    bodies='\n'.join(function(source, 'static void '+name+'(') for name in ('record_batch_retire','submit_record_capacity','ensure_draw_record_capacity'))
    bodies=function(source,'static void wait_for_gpu_required(')+'\n'+bodies
    with tempfile.TemporaryDirectory(prefix='record-retire-') as directory:
        out=Path(directory); unit=out/'test.c'; exe=out/('test.exe' if os.name=='nt' else 'test')
        unit.write_text((FIX/'rsx_record_retire.c.in').read_text().replace('@FUNCTIONS@', bodies))
        compile_c(unit, exe, VIDEO, out)
        for frame in ([],['frame1']):
            for overlap in ([],['overlap']):
                for mode in range(11):
                    r=subprocess.run([str(exe),str(mode),*frame,*overlap],capture_output=True,text=True,timeout=10)
                    if (mode==0 and (r.returncode!=0 or 'PASS:' not in r.stdout)) or (mode!=0 and (r.returncode==0 or 'GPU retirement failed' not in r.stderr)):
                        raise RuntimeError(f'frame={frame} overlap={overlap} mode={mode}: {r.returncode} {r.stdout} {r.stderr}')
        def mutated(name, before, after):
            mutant = bodies.replace(before, after, 1)
            if mutant == bodies:
                raise RuntimeError(name + ': mutation anchor not found')
            unit.write_text((FIX/'rsx_record_retire.c.in').read_text().replace('@FUNCTIONS@', mutant))
            compile_c(unit, exe, VIDEO, out)
        # Negative control: remove the post-drain retirement check. The same
        # failure oracle must reject the resulting silent continuation.
        mutated('post-drain', '    render_frame();\n    if (!drain_overlap()) record_batch_retire();', '    render_frame();\n    /* omitted post-drain check */')
        for frame in ([], ['frame1']):
            r=subprocess.run([str(exe),'5',*frame],capture_output=True,text=True,timeout=10)
            if 'GPU retirement failed' in r.stderr:
                raise RuntimeError('post-drain omission was not exposed')
        # Overlapped drains keep the pre-drain retirement: without it the next
        # replay would start while the previous batch may still run.
        mutated('pre-drain', '    record_batch_retire();\n    int saved', '    int saved')
        for args in (['0'], ['0', 'overlap']):
            r=subprocess.run([str(exe),*args],capture_output=True,text=True,timeout=10)
            if r.returncode == 0:
                raise RuntimeError('pre-drain omission was not exposed: ' + ' '.join(args))
        # RSX_DRAIN_OVERLAP must actually drop the post-drain wait.
        mutated('overlap-ignored', 'if (!drain_overlap()) record_batch_retire();', 'record_batch_retire();')
        r=subprocess.run([str(exe),'0','overlap'],capture_output=True,text=True,timeout=10)
        if r.returncode == 0:
            raise RuntimeError('ignored overlap switch was not exposed')
        print('PASS: actual retirement rejects incomplete/device-error fences before and after drain on both frames, serialized and overlapped; post-drain, pre-drain and ignored-switch controls exposed')
if __name__=='__main__': main()
