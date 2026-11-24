"""Configure authored targets with the actual guest compile option helper and the actual build option lines.

Fixture: one lifted unit and one runtime unit. The helper under src/guest_optimization.cmake and the
checked O1 block of CMakeLists.txt are the real files. The check asserts the compile commands through
compile_commands.json. It is a configuration check, not a performance proof.
"""
from pathlib import Path
from types import SimpleNamespace
import ast, hashlib, json, os, re, shutil, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'src' / 'guest_optimization.cmake'
LIFTED, RUNTIME = 'ppu_recomp_000.cpp', 'authored_runtime.c'


def main():
    env = os.environ.copy()
    if os.name == 'nt':
        sys.path.insert(0, str(ROOT / 'scripts'))
        from project import build_environment
        env = build_environment()
    cc = env.get('MV_CLANG') or shutil.which('clang') or shutil.which('cc')
    cxx = cc if os.name == 'nt' else shutil.which('clang++') or shutil.which('c++')
    for name in ('cmake', 'ninja'):
        if not shutil.which(name, path=env.get('PATH')):
            raise SystemExit(f'Requires {name}')
    if not cc or not cxx:
        raise SystemExit('Requires a configured C/C++ compiler')
    out = ROOT / 'temp' / 'checks' / f'guest-optimization-{time.time_ns()}'
    fixture = out / 'source'
    (fixture / 'generated').mkdir(parents=True)
    cmake_text = (ROOT / 'CMakeLists.txt').read_text()
    checked = cmake_text[cmake_text.index('# Preserve Debug symbols/assertions'):cmake_text.index('# Prefer Ninja')]
    helper = HELPER.read_text()
    header = '#include <assert.h>\n#ifdef NDEBUG\n#error Assertions must remain enabled\n#endif\n#ifdef __FAST_MATH__\n#error Fast math must remain disabled\n#endif\n'
    if os.name == 'nt':
        header += '#ifndef _DEBUG\n#error Debug CRT setting must remain enabled\n#endif\n'
    (fixture / 'generated' / LIFTED).write_text(header + 'int lifted_unit(int x){assert(x);return x+1;}\n')
    (fixture / RUNTIME).write_text(header + 'int runtime_unit(int x){assert(x);return x;}\n')
    (fixture / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(authored_guest C CXX)\n' + checked + '''
file(GLOB lifted "${CMAKE_CURRENT_SOURCE_DIR}/generated/*.cpp")
add_library(application STATIC ${lifted} ''' + RUNTIME + ''')
include("${CMAKE_CURRENT_SOURCE_DIR}/guest_optimization.cmake")
motorstorm_guest_compile_options("${lifted}")
''')
    build = out / 'build'
    report = dict(qualification='Authored configuration fixture, not a performance proof.', commands=[], results=[],
                  sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (ROOT / 'CMakeLists.txt', HELPER, ROOT / 'scripts/project.py')})

    def run(cmd, success=True):
        p = subprocess.run(list(map(str, cmd)), env=env, capture_output=True, text=True, timeout=180)
        report['commands'].append(list(map(str, cmd)))
        report['results'].append(dict(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr))
        (out / 'result.json').write_text(json.dumps(report, indent=2))
        if success and p.returncode:
            raise AssertionError(f'Command failed; see {out}/result.json')
        return p

    def configure(active, policy=helper, native=True):
        (fixture / 'guest_optimization.cmake').write_text(policy)
        return run(['cmake', '-S', fixture, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Debug',
                    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', f'-DCMAKE_C_COMPILER={cc}', f'-DCMAKE_CXX_COMPILER={cxx}',
                    '-DPORT_OPTIMIZE_NATIVE=' + ('ON' if native else 'OFF'),
                    '-DPORT_OPTIMIZE_GUEST=' + ('ON' if active else 'OFF')], success=native or not active)

    def commands():
        return {Path(row['file']).name: row['command'] for row in json.loads((build / 'compile_commands.json').read_text())}

    def last_level(cmd):
        levels = re.findall(r'(?:/clang:)?-O[0-3s]', cmd)
        assert levels, 'no optimization flag in the command'
        return levels[-1]

    def verify(active, baseline):
        actual = commands()
        lifted, runtime = actual[LIFTED], actual[RUNTIME]
        assert runtime == baseline[RUNTIME], 'The runtime command changed'
        for cmd in (lifted, runtime):
            assert '-ffp-contract=off' in cmd and '-fno-strict-aliasing' in cmd
            assert '-fno-inline' not in cmd
            assert not re.search(r'[-/]DNDEBUG|[-/]ffast-math', cmd)
        expected = ('/clang:-O2' if os.name == 'nt' else '-O2') if active else last_level(runtime)
        assert last_level(lifted) == expected, ('Lifted optimization level', last_level(lifted), expected)
        assert ('-O2' not in lifted) or active
        if os.name == 'nt':
            assert re.findall(r'/Ob[012]', lifted)[-1] == ('/Ob2' if active else '/Ob1')
            assert re.search(r'/w(?:\s|$)', lifted) and re.search(r'/bigobj(?:\s|$)', lifted)
            assert re.search(r'[-/]MDd(?:\s|$)', lifted)
        else:
            assert re.search(r'-w(?:\s|$)', lifted)
        assert lifted != runtime

    configure(False)
    baseline = commands()
    verify(False, baseline)
    run(['cmake', '--build', build])
    configure(True)
    verify(True, baseline)
    run(['cmake', '--build', build])
    configure(False)
    verify(False, baseline)
    rejected = configure(True, native=False)
    assert rejected.returncode and 'requires PORT_OPTIMIZE_NATIVE' in rejected.stdout + rejected.stderr

    mutants = {
        'guest-at-o1': helper.replace('/clang:-O2;/Ob2', '/clang:-O1;/Ob1').replace('"-w;-ffp-contract=off;-O2"', '"-w;-ffp-contract=off;-O1"'),
        'always-o2': helper.replace('COMPILE_OPTIONS "/w;/bigobj")', 'COMPILE_OPTIONS "/w;/bigobj;/clang:-O2;/Ob2")').replace(
            'COMPILE_OPTIONS "-w;-ffp-contract=off")', 'COMPILE_OPTIONS "-w;-ffp-contract=off;-O2")'),
        'runtime-gets-flags': helper.replace('set_source_files_properties(${sources}', 'set_source_files_properties(authored_runtime.c'),
    }
    if os.name == 'nt':
        mutants['lost-bigobj'] = helper.replace('"/w;/bigobj;/clang:-O2;/Ob2"', '"/w;/clang:-O2;/Ob2"')
    else:
        mutants['contraction-on'] = helper.replace('"-w;-ffp-contract=off;-O2"', '"-w;-O2"')
    for label, mutant in mutants.items():
        assert mutant != helper, label
        accepted = True
        for active in (True, False):
            configure(active, mutant)
            try:
                verify(active, baseline)
            except AssertionError:
                accepted = False
        assert not accepted, 'Accepted actual-source mutant ' + label
    guard = re.sub(r'    if\(PORT_OPTIMIZE_GUEST AND NOT PORT_OPTIMIZE_NATIVE\)\n.*?\n\s*endif\(\)\n', '', helper, flags=re.S)
    assert guard != helper
    assert configure(True, guard, native=False).returncode == 0, 'The guard is not the helper guard'

    # The build option of CMakeLists.txt is declared once and used only through the helper.
    assert cmake_text.count('PORT_OPTIMIZE_GUEST') == 1
    assert 'option(PORT_OPTIMIZE_GUEST "Use O2 and automatic inlining for the lifted guest units; requires PORT_OPTIMIZE_NATIVE" OFF)' in cmake_text
    assert cmake_text.count('include("${CMAKE_CURRENT_SOURCE_DIR}/src/guest_optimization.cmake")') == 1
    assert cmake_text.count('motorstorm_guest_compile_options("${RECOMP_SOURCES}")') == 1
    assert not re.search(r'set_source_files_properties\(\$\{RECOMP_SOURCES\}', cmake_text)

    # Execute only the actual build-option statements; no configure and no build runs.
    launcher = (ROOT / 'scripts/project.py').read_text()

    def audit(text):
        found = {}
        for node in ast.walk(ast.parse(text)):
            unparsed = ast.unparse(node)
            if isinstance(node, ast.Expr) and 'PORT_OPTIMIZE_GUEST=' in unparsed and 'command.append' in unparsed:
                found['append'] = node
            if unparsed == "identity['guest_optimization'] = args.optimize_guest":
                found['identity'] = node
        assert set(found) == {'append', 'identity'}, found.keys()
        assert "if args.cmd=='build' and args.optimize_guest and not args.optimize:" in text
        assert "ap.error('--optimize-guest requires --optimize')" in text
        for active in (False, True):
            ns = dict(command=[], args=SimpleNamespace(optimize_guest=active), identity={})
            exec(compile(ast.Module(body=[found['append'], found['identity']], type_ignores=[]), 'actual-option', 'exec'), ns)
            assert ns['command'] == ['-DPORT_OPTIMIZE_GUEST=' + ('ON' if active else 'OFF')]
            assert ns['identity'] == {'guest_optimization': active}

    audit(launcher)
    launcher_mutants = {
        'always-off': launcher.replace('"ON" if args.optimize_guest else "OFF"', '"OFF"'),
        'identity-always-on': launcher.replace("identity['guest_optimization']=args.optimize_guest", "identity['guest_optimization']=True"),
        'no-requirement': launcher.replace("if args.cmd=='build' and args.optimize_guest and not args.optimize:", "if False:"),
        'other-message': launcher.replace("'--optimize-guest requires --optimize'", "'--optimize-guest needs --optimize'"),
    }
    for label, mutant in launcher_mutants.items():
        assert mutant != launcher, label
        try:
            audit(mutant)
        except AssertionError:
            pass
        else:
            raise AssertionError('Accepted launcher mutant ' + label)
    p = run([sys.executable, ROOT / 'scripts/project.py', 'build', '--optimize-guest', '--configure-only'], success=False)
    assert p.returncode and '--optimize-guest requires --optimize' in p.stderr
    p = run([sys.executable, ROOT / 'scripts/project.py', 'build', '--help'], success=False)
    assert '--optimize-guest' in p.stdout
    mutants.update(launcher_mutants)
    report['passed'] = dict(compiled_modes=['off', 'on', 'off-again'], mutants=list(mutants), guard=True,
                            unrelated_command_unchanged=True, invalid_option_rejected=True)
    (out / 'result.json').write_text(json.dumps(report, indent=2))
    print('PASS actual checked compiler flags, lifted units only, off/on/off builds,', len(mutants), 'mutants, guard and CLI wiring:', out / 'result.json')


if __name__ == '__main__':
    main()
