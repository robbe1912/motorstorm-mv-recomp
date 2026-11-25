"""Compile authored targets with the actual checked flags and runtime-wide O2 policy."""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[1]
HEADER='''#include <assert.h>
#ifdef NDEBUG
#error Assertions must remain enabled
#endif
#ifdef __FAST_MATH__
#error Fast math must remain disabled
#endif
'''
RUNTIME=['rsx_d3d12_backend.c','cellGcmSys.c','spu_float_simd.c','runtime_unit.cpp']

def main():
    env=os.environ.copy()
    if os.name=='nt':
        from project import build_environment
        env=build_environment()
    cc=env.get('MV_CLANG') or shutil.which('clang') or shutil.which('cc')
    cxx=cc if os.name=='nt' else shutil.which('clang++') or shutil.which('c++')
    if not cc or not cxx or not shutil.which('cmake',path=env.get('PATH')) or not shutil.which('ninja',path=env.get('PATH')):
        raise SystemExit('Requires CMake, Ninja and configured C/C++ compiler')
    out=ROOT/'temp/checks'/f'runtime-optimization-{time.time_ns()}';out.mkdir(parents=True)
    fixture=out/'source';sdk=fixture/'sdk';sdk.mkdir(parents=True)
    helper=(ROOT/'src/runtime_optimization.cmake').read_text()
    cmake=(ROOT/'CMakeLists.txt').read_text()
    checked=cmake[cmake.index('# Preserve Debug symbols/assertions'):cmake.index('# Prefer Ninja')]
    for i,name in enumerate(RUNTIME):
        (sdk/name).write_text(HEADER+f'int authored_{i}(int x){{assert(x);return x+{i};}}\n')
    for name in ('authored_app.cpp','authored_ppu.c','authored_spu.c'):
        (fixture/name).write_text(HEADER+f'int {Path(name).stem}(int x){{assert(x);return x;}}\n')
    # The toolkit's own rule: plain -O2 outside Debug, which /clang:-O1 overrides under clang-cl.
    (sdk/'CMakeLists.txt').write_text('add_library(ps3recomp_runtime STATIC '+' '.join(RUNTIME)+')\n'
        'target_compile_options(ps3recomp_runtime PRIVATE -fno-strict-aliasing -ffp-contract=off $<$<CONFIG:Release,RelWithDebInfo>:-O2>)\n')
    (fixture/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(authored_runtime C CXX)\n'+checked+'''
add_subdirectory(sdk)
include("${CMAKE_CURRENT_SOURCE_DIR}/runtime.cmake")
motorstorm_configure_runtime_optimization()
add_library(application STATIC authored_app.cpp authored_ppu.c authored_spu.c)
if(MSVC)
 set_source_files_properties(authored_spu.c PROPERTIES COMPILE_OPTIONS "/clang:-O2")
else()
 set_source_files_properties(authored_spu.c PROPERTIES COMPILE_OPTIONS "-O2")
endif()
''')
    report=dict(qualification='Authored compile/configuration fixture, not native GPU, guest-numeric or performance proof.',commands=[],results=[],
                sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'CMakeLists.txt',ROOT/'src/runtime_optimization.cmake',ROOT/'scripts/project.py']})
    def run(cmd,success=True):
        p=subprocess.run(list(map(str,cmd)),env=env,capture_output=True,text=True,timeout=120)
        report['commands'].append(list(map(str,cmd)));report['results'].append(dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        (out/'result.json').write_text(json.dumps(report,indent=2))
        if success and p.returncode:raise AssertionError(f'Command failed; see {out}/result.json')
        return p
    def configure(active,policy=helper,native=True,kind='Debug',success=True):
        (fixture/'runtime.cmake').write_text(policy);build=out/('build-'+kind)
        p=run(['cmake','-S',fixture,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE='+kind,'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
               f'-DCMAKE_C_COMPILER={cc}',f'-DCMAKE_CXX_COMPILER={cxx}',
               '-DPORT_OPTIMIZE_NATIVE='+('ON' if native else 'OFF'),'-DPORT_OPTIMIZE_RUNTIME='+('ON' if active else 'OFF')],success)
        return p,build
    def commands(build):
        return {Path(row['file']).name:row['command'] for row in json.loads((build/'compile_commands.json').read_text())}
    def effective(cmd):
        # clang-cl forwards /clang: arguments after its own, so the last one wins.
        forwarded=re.findall(r'/clang:(-O[0-3])',cmd)
        return forwarded[-1] if forwarded else re.findall(r'\s(-O[0-3])\b',cmd)[-1]
    def verify(active,build,baseline):
        actual=commands(build)
        assert json.loads((build/'runtime-optimization.json').read_text())==dict(enabled=active,target='ps3recomp_runtime')
        assert set(actual)==set(baseline)
        added=' /clang:-O2 /Ob2' if os.name=='nt' else ' -O2'
        for name,cmd in actual.items():
            if not (active and name in RUNTIME):
                assert cmd==baseline[name],('Unrelated command changed',name);continue
            assert effective(cmd)=='-O2',(name,cmd)
            if os.name!='nt' and cmd==baseline[name] and effective(baseline[name])=='-O2':
                continue  # The toolkit's -O2 already applies there and CMake drops the duplicate.
            # Same command with exactly the level added: nothing lost or reordered.
            places=[m.start() for m in re.finditer(re.escape(added)+r'(?=\s)',cmd)]
            assert any(cmd[:i]+cmd[i+len(added):]==baseline[name] for i in places),('More than the level changed',name,cmd,baseline[name])
            if os.name=='nt':
                assert re.findall(r'/Ob[012]',cmd)[-1]=='/Ob2' and '/UNDEBUG' in cmd
            assert '-ffp-contract=off' in cmd and '-fno-strict-aliasing' in cmd
    kinds=['Debug','RelWithDebInfo']
    for kind in kinds:
        _,build=configure(False,kind=kind);baseline=commands(build);verify(False,build,baseline);run(['cmake','--build',build])
        # -O1 everywhere, except where the toolkit's -O2 follows it (non-Debug without clang-cl).
        expected='-O2' if os.name!='nt' and kind!='Debug' else '-O1'
        assert all(effective(baseline[name])==expected for name in RUNTIME),('Unexpected level without the option',kind)
        configure(True,kind=kind);verify(True,build,baseline);run(['cmake','--build',build])
        configure(False,kind=kind);verify(False,build,baseline);run(['cmake','--build',build])
    assert configure(True,native=False,success=False)[0].returncode
    assert configure(True,kind='Release',success=False)[0].returncode
    _,build=configure(False);baseline=commands(build)
    mutants={
        'directory-scope':helper.replace('target_compile_options(ps3recomp_runtime PRIVATE','add_compile_options('),
        'interface-scope':helper.replace('ps3recomp_runtime PRIVATE','ps3recomp_runtime INTERFACE'),
        'wrong-level':helper.replace('/clang:-O2','/clang:-O1').replace('PRIVATE -O2','PRIVATE -O1'),
        'missing-inlining':helper.replace('/Ob2','/Ob1').replace('PRIVATE -O2','PRIVATE -O2 -fno-inline'),
        'fast-math':helper.replace('/Ob2)','/Ob2 /clang:-ffast-math)').replace('PRIVATE -O2','PRIVATE -O2 -ffast-math')}
    if os.name=='nt':  # A plain level has no effect after /clang:-O1.
        mutants['plain-level']=helper.replace('/clang:-O2','-O2')
    for label,mutant in mutants.items():
        assert mutant!=helper,label
        configure(True,mutant)
        try:verify(True,build,baseline)
        except AssertionError:pass
        else:raise AssertionError('Accepted actual-source mutant '+label)
    # Execute only the actual build-option command append; no native config or process.
    tree=ast.parse((ROOT/'scripts/project.py').read_text())
    append=next(n for n in ast.walk(tree) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                and 'command.append' in ast.unparse(n) and 'PORT_OPTIMIZE_RUNTIME=' in ast.unparse(n))
    from types import SimpleNamespace
    for active in [False,True]:
        ns=dict(command=[],args=SimpleNamespace(optimize_runtime=active));exec(compile(ast.Module(body=[append],type_ignores=[]),'actual-option','exec'),ns)
        assert ns['command']==['-DPORT_OPTIMIZE_RUNTIME='+('ON' if active else 'OFF')]
    # Check the actual argument guard without calling the game build wrapper.
    import argparse,contextlib,io
    guard=next(n for n in ast.walk(tree) if isinstance(n,ast.If)
               and 'args.optimize_runtime' in ast.unparse(n.test))
    for active in [False,True]:
        for native in [False,True]:
            errors=io.StringIO()
            ns=dict(args=SimpleNamespace(cmd='build',optimize_runtime=active,optimize=native),
                    ap=argparse.ArgumentParser())
            with contextlib.redirect_stderr(errors):
                try:exec(compile(ast.Module(body=[guard],type_ignores=[]),'actual-guard','exec'),ns)
                except SystemExit as error:
                    assert active and not native and error.code==2
                    assert '--optimize-runtime requires --optimize' in errors.getvalue()
                else:assert not (active and not native)
    report['passed']=dict(build_types=kinds,compiled_modes=['off','on','off-again'],mutants=list(mutants),unrelated_commands_unchanged=True,invalid_options_rejected=3)
    (out/'result.json').write_text(json.dumps(report,indent=2))
    print(f'PASS actual checked compiler flags, target scoping, off/on/off builds in {len(kinds)} build types, {len(mutants)} mutants and CLI wiring:',out/'result.json')

if __name__=='__main__':main()
