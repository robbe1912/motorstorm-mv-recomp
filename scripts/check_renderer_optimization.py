"""Compile authored targets using actual checked flags and renderer source policy."""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[1]
NAMES=['cellGcmSys.c','rsx_d3d12_backend.c','rsx_dispatch.c','rsx_vertex_fetch.c',
       'rsx_vertex_compact.c','rsx_texture_layout.c','rsx_vp_decompiler.c','rsx_fp_decompiler.c']

def main():
    env=os.environ.copy()
    if os.name=='nt':
        from project import build_environment
        env=build_environment()
    cc=env.get('MV_CLANG') or shutil.which('clang') or shutil.which('cc')
    cxx=cc if os.name=='nt' else shutil.which('clang++') or shutil.which('c++')
    if not cc or not cxx or not shutil.which('cmake',path=env.get('PATH')) or not shutil.which('ninja',path=env.get('PATH')):
        raise SystemExit('Requires CMake, Ninja and configured C/C++ compiler')
    out=ROOT/'temp/checks'/f'renderer-optimization-{time.time_ns()}';out.mkdir(parents=True)
    fixture=out/'source';video=fixture/'sdk/libs/video';video.mkdir(parents=True)
    helper=(ROOT/'src/renderer_optimization.cmake').read_text()
    cmake=(ROOT/'CMakeLists.txt').read_text()
    checked=cmake[cmake.index('# Preserve Debug symbols/assertions'):cmake.index('# Prefer Ninja')]
    header='#include <assert.h>\n#ifdef NDEBUG\n#error Assertions must remain enabled\n#endif\n#ifdef __FAST_MATH__\n#error Fast math must remain disabled\n#endif\n'
    if os.name=='nt':header+='#ifndef _DEBUG\n#error Debug CRT setting must remain enabled\n#endif\n'
    for i,name in enumerate(NAMES):
        (video/name).write_text(header+f'int authored_{i}(int x){{assert(x);return x+{i};}}\n')
    (fixture/'sdk/unrelated.c').write_text(header+'int unrelated(int x){assert(x);return x;}\n')
    (fixture/'authored_app.cpp').write_text(header+'int application(int x){assert(x);return x;}\n')
    (fixture/'authored_spu.c').write_text(header+'int separate_unit(int x){assert(x);return x;}\n')
    (fixture/'sdk/CMakeLists.txt').write_text('file(GLOB input "${CMAKE_CURRENT_SOURCE_DIR}/libs/video/*.c")\nadd_library(ps3recomp_runtime STATIC ${input} unrelated.c)\n')
    (fixture/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(authored_renderer C CXX)\n'+checked+'''
add_subdirectory(sdk)
include("${CMAKE_CURRENT_SOURCE_DIR}/renderer.cmake")
motorstorm_configure_renderer_optimization("${CMAKE_CURRENT_SOURCE_DIR}/sdk")
add_library(application STATIC authored_app.cpp authored_spu.c)
if(MSVC)
 set_source_files_properties(authored_spu.c PROPERTIES COMPILE_OPTIONS "/clang:-O2")
else()
 set_source_files_properties(authored_spu.c PROPERTIES COMPILE_OPTIONS "-O2")
endif()
''')
    build=out/'build';report=dict(qualification='Authored compile/configuration fixture, not native GPU or performance proof.',commands=[],results=[],sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'CMakeLists.txt',ROOT/'src/renderer_optimization.cmake',ROOT/'scripts/project.py']})
    def run(cmd,success=True):
        p=subprocess.run(list(map(str,cmd)),env=env,capture_output=True,text=True,timeout=120)
        report['commands'].append(list(map(str,cmd)));report['results'].append(dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        (out/'result.json').write_text(json.dumps(report,indent=2))
        if success and p.returncode:raise AssertionError(f'Command failed; see {out}/result.json')
        return p
    def configure(active,policy=helper,native=True):
        (fixture/'renderer.cmake').write_text(policy)
        return run(['cmake','-S',fixture,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Debug',
                    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',f'-DCMAKE_C_COMPILER={cc}',f'-DCMAKE_CXX_COMPILER={cxx}',
                    '-DPORT_OPTIMIZE_NATIVE='+('ON' if native else 'OFF'),'-DPORT_OPTIMIZE_RENDERER='+('ON' if active else 'OFF')],success=native or not active)
    def commands():
        return {Path(row['file']).name:row['command'] for row in json.loads((build/'compile_commands.json').read_text())}
    def verify(active,baseline):
        actual=commands();manifest=json.loads((build/'renderer-optimization.json').read_text())
        assert manifest==dict(enabled=active,sources=NAMES if active else [])
        for name,cmd in actual.items():
            if active and name in NAMES:
                optimization=re.findall(r'(?:/clang:)?-O[0-3]',cmd)
                expected='/clang:-O2' if os.name=='nt' else '-O2'
                assert optimization and optimization[-1]==expected
                if os.name=='nt':
                    assert re.findall(r'/Ob[012]',cmd)[-1]=='/Ob2'
                    assert re.search(r'[-/]MDd(?:\s|$)',cmd)
                assert '-ffp-contract=off' in cmd and '-fno-strict-aliasing' in cmd
                assert '-fno-inline' not in cmd
                assert not re.search(r'[-/]DNDEBUG|[-/]ffast-math',cmd)
            else:assert cmd==baseline[name],('Unrelated command changed',name)
    configure(False);baseline=commands();verify(False,baseline);run(['cmake','--build',build])
    configure(True);verify(True,baseline);run(['cmake','--build',build])
    configure(False);verify(False,baseline);run(['cmake','--build',build])
    assert configure(True,native=False).returncode!=0
    mutants={
        'wrong-directory':helper.replace(' TARGET_DIRECTORY ps3recomp_runtime',''),
        'whole-target':helper.replace('SOURCE "${source}" TARGET_DIRECTORY ps3recomp_runtime','TARGET ps3recomp_runtime'),
        'wrong-level':helper.replace('-O2','-O1'),
        'missing-inlining':helper.replace('/Ob2','/Ob1').replace('set(options -O2)','set(options -O2 -fno-inline)'),
        'lost-checks':helper.replace('set(options /clang:-O2 /Ob2)','set(options /clang:-O2 /Ob2 /DNDEBUG)').replace('set(options -O2)','set(options -O2 -DNDEBUG)')}
    for label,mutant in mutants.items():
        assert mutant!=helper
        configure(True,mutant)
        try:verify(True,baseline)
        except AssertionError:pass
        else:raise AssertionError('Accepted actual-source mutant '+label)
    # Execute only the actual build-option command append; no native config or process.
    tree=ast.parse((ROOT/'scripts/project.py').read_text())
    append=next(n for n in ast.walk(tree) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                and 'command.append' in ast.unparse(n) and 'PORT_OPTIMIZE_RENDERER=' in ast.unparse(n))
    from types import SimpleNamespace
    for active in [False,True]:
        ns=dict(command=[],args=SimpleNamespace(optimize_renderer=active));exec(compile(ast.Module(body=[append],type_ignores=[]),'actual-option','exec'),ns)
        assert ns['command']==['-DPORT_OPTIMIZE_RENDERER='+('ON' if active else 'OFF')]
    p=run([sys.executable,ROOT/'scripts/project.py','build','--optimize-renderer','--configure-only'],success=False)
    assert p.returncode and '--optimize-renderer requires --optimize' in p.stderr
    report['passed']=dict(compiled_modes=['off','on','off-again'],mutants=list(mutants),unrelated_commands_unchanged=True,invalid_option_rejected=True)
    (out/'result.json').write_text(json.dumps(report,indent=2));print('PASS actual checked compiler flags, source-directory scoping, off/on/off builds, five mutants and CLI wiring:',out/'result.json')

if __name__=='__main__':main()
