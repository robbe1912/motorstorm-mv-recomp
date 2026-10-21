"""Authored progress/ABI checks and independent bad-completion/order/cooperation controls."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name=='nt' else 'c++')
    if not compiler:
        raise SystemExit('Set MV_CLANG/CXX to the native compiler')
    out = ROOT/'build/self-tests/native-job-wait'
    out.mkdir(parents=True, exist_ok=True)
    source, fixture = ROOT/'src/motorstorm', ROOT/'scripts/fixtures'
    flags = (['/nologo','/std:c++17','/O2','/UNDEBUG','/EHsc','/DMOTORSTORM_JOB_WAIT_FIXTURE',
              '/I'+str(source),'/I'+str(fixture),'/Fo'+str(out)+os.sep] if os.name=='nt' else
             ['-std=c++17','-O2','-UNDEBUG','-pthread','-DMOTORSTORM_JOB_WAIT_FIXTURE','-I'+str(source),'-I'+str(fixture)])

    def run(core, name, reference=False):
        exe = out/(name+('.exe' if os.name=='nt' else ''))
        command = [compiler,*flags,str(core),str(source/'job_wait_adapter.cpp'),str(fixture/'native_job_wait.cpp')]
        command += ['/Fe'+str(exe)] if os.name=='nt' else ['-o',str(exe)]
        built = subprocess.run(command,cwd=out,capture_output=True,text=True)
        (out/(name+'-build.log')).write_text(built.stdout+built.stderr)
        if built.returncode:
            raise SystemExit(built.stdout+built.stderr)
        result = subprocess.run([str(exe),*(['reference'] if reference else [])],env=dict(os.environ,MS_NATIVE_JOB_WAIT='0' if reference else '1'),capture_output=True,text=True,timeout=10)
        (out/(name+'-run.log')).write_text(result.stdout+result.stderr)
        return result

    actual = source/'job_wait.cpp'
    for reference in (False,True):
        result = run(actual,'reference' if reference else 'positive',reference)
        assert result.returncode==0, result.stdout+result.stderr
        print(result.stdout.strip())
    text = actual.read_text()
    block = '''const auto start = source.begin(source.user);
        result.owner = start.owner;
        result.minimum = start.taken;
        source.full_barrier(source.user);'''
    controls = [
        ('early', 'if (result.minimum >= marker)', 'if (true)', 'All active lanes must complete'),
        ('order', block, '''source.full_barrier(source.user);
        const auto start = source.begin(source.user);
        result.owner = start.owner;
        result.minimum = start.taken;''', 'Taken/barrier/lane order'),
        ('cooperation', 'source.cooperate(source.user);', '(void)source.user;', 'Cooperation for blocked work')]
    for name, before, after, message in controls:
        assert text.count(before)==1
        mutant = out/(name+'.cpp')
        mutant.write_text(text.replace(before,after))
        result = run(mutant,name)
        assert result.returncode==1 and 'FAIL: '+message in result.stderr, result.stdout+result.stderr
    print('PASS independent premature-completion, barrier-order and missing-cooperation controls')


if __name__=='__main__':
    main()
