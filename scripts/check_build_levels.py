"""Compile an authored fixture with the actual build-level options: native game O2 and the release CRT."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[1]
HEADER='''#include <assert.h>
#ifdef NDEBUG
#error Assertions must remain enabled
#endif
'''
GAME=['src/motorstorm/kernel.c','src/motorstorm/adapter.cpp']
OTHER=['src/guest_lifted.c','sdk/runtime.c']
TAIL='''
add_subdirectory(sdk)
add_library(fixture_game STATIC '''+' '.join(GAME+OTHER[:1])+''')
include("${CMAKE_CURRENT_SOURCE_DIR}/native_game.cmake")
motorstorm_configure_native_game_optimization(fixture_game)
'''

def main():
    env=os.environ.copy()
    if os.name=='nt':
        from project import build_environment
        env=build_environment()
    cc=env.get('MV_CLANG') or shutil.which('clang') or shutil.which('cc')
    cxx=cc if os.name=='nt' else shutil.which('clang++') or shutil.which('c++')
    if not cc or not cxx or not shutil.which('cmake',path=env.get('PATH')) or not shutil.which('ninja',path=env.get('PATH')):
        raise SystemExit('Requires CMake, Ninja and a configured C/C++ compiler')
    out=ROOT/'temp/checks'/f'build-levels-{time.time_ns()}';out.mkdir(parents=True)
    fixture=out/'source';build=out/'build'
    cmake=(ROOT/'CMakeLists.txt').read_text()
    # The real option blocks: checked native optimization, native game O2 and the CRT.
    levels=cmake[cmake.index('# Preserve Debug symbols/assertions'):cmake.index('# Prefer Ninja')]
    for i,name in enumerate(GAME+OTHER):
        target=fixture/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(HEADER+f'int authored_{i}(void){{assert(1);return 0;}}\n')
    helper=(ROOT/'src/native_game_optimization.cmake').read_text()
    (fixture/'sdk/CMakeLists.txt').write_text('add_library(fixture_runtime STATIC runtime.c)\n')
    report=dict(qualification='Authored compile/configuration fixture, not a performance proof.',commands=[],results=[],
                sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'CMakeLists.txt',ROOT/'src/native_game_optimization.cmake',ROOT/'scripts/project.py']})
    def run(cmd,success=True):
        p=subprocess.run(list(map(str,cmd)),env=env,capture_output=True,text=True,timeout=180)
        report['commands'].append(list(map(str,cmd)));report['results'].append(dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        (out/'result.json').write_text(json.dumps(report,indent=2))
        if success and p.returncode:raise AssertionError(f'Command failed; see {out}/result.json')
        return p
    def configure(game,crt,policy=helper,native=True,success=True):
        (fixture/'native_game.cmake').write_text(policy)
        return run(['cmake','-S',fixture,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Debug','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
               f'-DCMAKE_C_COMPILER={cc}',f'-DCMAKE_CXX_COMPILER={cxx}',
               '-DPORT_OPTIMIZE_NATIVE='+('ON' if native else 'OFF'),'-DPORT_OPTIMIZE_NATIVE_GAME='+('ON' if game else 'OFF'),
               '-DPORT_RELEASE_CRT='+('ON' if crt else 'OFF')],success)
    def configure_levels(text):
        (fixture/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(authored_levels C CXX)\n'+text+TAIL)
    def commands():
        return {row['file'].replace('\\','/').split('/source/')[-1]:row['command'] for row in json.loads((build/'compile_commands.json').read_text())}
    def effective(cmd):
        forwarded=re.findall(r'/clang:(-O[0-3])',cmd)
        return forwarded[-1] if forwarded else re.findall(r'\s(-O[0-3])\b',cmd)[-1]
    def crt_flags(cmd):
        return bool(re.search(r'\s-MDd\b',cmd)),bool(re.search(r'\s-MD\b',cmd))
    def verify(game,crt,baseline):
        actual=commands()
        assert set(actual)==set(GAME+OTHER),sorted(actual)
        assert json.loads((build/'native-game-optimization.json').read_text())==dict(enabled=game,target='fixture_game',sources=len(GAME) if game else 0)
        assert json.loads((build/'crt.json').read_text())==dict(release=crt)
        for name,cmd in actual.items():
            if os.name=='nt':
                # One CRT flag in the game target and in the library of the subdirectory.
                assert crt_flags(cmd)==((not crt),crt),('Wrong CRT',name,cmd)
            if game and name in GAME:
                assert effective(cmd)=='-O2' and '/UNDEBUG' in cmd and '-ffp-contract=off' in cmd and '-fno-strict-aliasing' in cmd,('Native game source without O2',name,cmd)
                if os.name=='nt':assert re.findall(r'/Ob[012]',cmd)[-1]=='/Ob2',('Native game source without inlining',name,cmd)
            else:
                assert cmd==baseline[name],('Unrelated command changed',name,cmd,baseline.get(name))
    base={};checks=0
    for crt in [False,True]:
        configure_levels(levels);configure(False,crt);base[crt]=commands()
        assert all(effective(base[crt][n])=='-O1' for n in base[crt]),('Unexpected level without the option',crt)
        configure(True,crt);verify(True,crt,base[crt]);checks+=1;run(['cmake','--build',build,'-j','1'])
        configure(False,crt);verify(False,crt,base[crt]);checks+=1;run(['cmake','--build',build,'-j','1'])
    # The option without checked native optimization is a configuration error.
    configure(True,False,native=False,success=False);checks+=1
    configure_levels(levels);configure(False,False)
    mutants={
        'all-target-sources':lambda h,l:(h.replace('if(position EQUAL 0 AND source_abs MATCHES','if(source_abs MATCHES'),l),
        'wrong-level':lambda h,l:(h.replace('/clang:-O2 /Ob2','/clang:-O1 /Ob2').replace('set(options -O2)','set(options -O1)'),l),
        'target-scope':lambda h,l:(h.replace('set_property(SOURCE ${native_sources} TARGET_DIRECTORY ${game_target}\n                     APPEND PROPERTY COMPILE_OPTIONS ${options})',
                                           'target_compile_options(${game_target} PRIVATE ${options})'),l),
        'crt-report-lies':lambda h,l:(h,l.replace('set(port_release_crt false)','set(port_release_crt true)')),
    }
    if os.name=='nt':
        mutants['missing-inlining']=lambda h,l:(h.replace('/clang:-O2 /Ob2','/clang:-O2 /Ob1'),l)
        mutants['debug-crt-kept']=lambda h,l:(h,l.replace('set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")','set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDebugDLL")'))
        mutants['crt-not-set']=lambda h,l:(h,l.replace('    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")\n',''))
    rejected=[]
    for label,make in mutants.items():
        policy,text=make(helper,levels)
        assert (policy,text)!=(helper,levels),label
        configure_levels(text);accepted=True
        for game,crt in [(True,True),(False,False)]:
            configure(game,crt,policy=policy)
            try:verify(game,crt,base[crt])
            except (AssertionError,KeyError,StopIteration,IndexError):accepted=False;break
        assert not accepted,'Accepted actual-source mutant '+label
        rejected.append(label);checks+=1
    # The actual argument guard, before any build step: the wrapper refuses the option alone.
    p=subprocess.run([sys.executable,str(ROOT/'scripts/project.py'),'build','--optimize-native-game'],capture_output=True,text=True)
    assert p.returncode==2 and '--optimize-native-game requires --optimize' in p.stderr,(p.returncode,p.stderr[-300:]);checks+=1
    print('build level checks=%d mutants rejected=%d failures=0'%(checks,len(rejected)))
    print('results:',out)

if __name__=='__main__':main()
