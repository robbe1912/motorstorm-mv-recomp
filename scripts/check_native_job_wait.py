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

    def run(core, name, reference=False, profile=False, clock='known', adapter=None):
        exe = out/(name+('.exe' if os.name=='nt' else ''))
        command = [compiler,*flags,str(core),str(adapter or source/'job_wait_adapter.cpp'),str(fixture/'native_job_wait.cpp')]
        command += ['/Fe'+str(exe)] if os.name=='nt' else ['-o',str(exe)]
        built = subprocess.run(command,cwd=out,capture_output=True,text=True)
        (out/(name+'-build.log')).write_text(built.stdout+built.stderr)
        if built.returncode:
            raise SystemExit(built.stdout+built.stderr)
        result = subprocess.run([str(exe),*(['reference'] if reference else [])],env=dict(os.environ,
            MS_NATIVE_JOB_WAIT='0' if reference else '1', MS_NATIVE_JOB_WAIT_PROFILE='1' if profile else '0',
            MS_JOB_WAIT_FIXTURE_CLOCK=clock),capture_output=True,text=True,timeout=10)
        (out/(name+'-run.log')).write_text(result.stdout+result.stderr)
        return result

    actual = source/'job_wait.cpp'
    for reference in (False,True):
        result = run(actual,'reference' if reference else 'positive',reference)
        assert result.returncode==0, result.stdout+result.stderr
        assert '[NATIVE_JOB_WAIT_PROFILE]' not in result.stderr, result.stderr
        print(result.stdout.strip())

    def records(result):
        assert result.returncode==0, result.stdout+result.stderr
        return [dict(field.split('=',1) for field in line.split()[1:])
                for line in result.stderr.splitlines() if line.startswith('[NATIVE_JOB_WAIT_PROFILE] ')]

    def known_profile(result):
        rows=records(result)
        assert [r['status'] for r in rows]==['complete','complete','original','original'], rows
        for index,r in enumerate(rows[:2]):
            def number(key): return int(r[key],0)
            expected={'thread':0x334455,'caller':0x123456789abcdef,'object':0x1000,
                      'owner':0x5000 if index==0 else 0x4000,'marker':3 if index==0 else 0,
                      'minimum':3 if index==0 else 1,'polls':85 if index==0 else 1,
                      'cooperations':21 if index==0 else 0,'frequency':1000000,'ticks':70,
                      'started':1234000000070+140*index,'finished':1234000000140+140*index}
            assert all(number(k)==v for k,v in expected.items()), (r,expected)
            assert number('finished')-number('started')==number('ticks'), r
    known_profile(run(actual,'profile',profile=True))
    reference_rows=records(run(actual,'profile-reference',reference=True,profile=True))
    assert len(reference_rows)==1 and reference_rows[0]['status']=='reference', reference_rows
    for clock in ('start-fail','end-fail','backward','frequency','zero-frequency'):
        rows=records(run(actual,'profile-'+clock,profile=True,clock=clock))
        assert [r['status'] for r in rows]==['clock_error','clock_error','original','original'], rows
        assert all('ticks' not in r for r in rows), rows
    adapter_text=(source/'job_wait_adapter.cpp').read_text()
    duration='static_cast<unsigned long long>(finish.value - start.value)'
    assert adapter_text.count(duration)==1
    adapter_mutant=out/'wrong-duration-adapter.cpp'
    adapter_mutant.write_text(adapter_text.replace(duration,'static_cast<unsigned long long>(0)'))
    rejected=False
    try: known_profile(run(actual,'wrong-duration',profile=True,adapter=adapter_mutant))
    except AssertionError: rejected=True
    assert rejected,'Independent timing oracle admitted a fabricated duration'
    print('PASS exact caller/queue/timing profile, disabled zero-clock path, clock failures and duration mutant')
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
