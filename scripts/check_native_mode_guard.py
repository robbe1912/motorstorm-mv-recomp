"""Exercise actual launcher mode parsing, build admission and inherited overrides.

Executes only selected AST statements; no config, process or PAD action runs.
"""
import argparse
import ast
import contextlib
import copy
import hashlib
import io
from itertools import product
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def main():
    root = Path(__file__).resolve().parents[1]
    body = next(n for n in ast.parse((root/'scripts/run.py').read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'main').body
    flags = {'--native-pcm-cubic', '--native-visibility', '--native-visibility-batch',
             '--native-particle-thresholds', '--native-particle-collisions', '--native-particle-random'}
    init = next(n for n in body if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'ap')
    arguments = [n for n in body if isinstance(n, ast.Expr)
                 and isinstance(n.value, ast.Call) and n.value.args
                 and isinstance(n.value.args[0], ast.Constant)
                 and n.value.args[0].value in flags]
    assert len(arguments) == len(flags)
    depth_argument = next(n for n in body if isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Call) and n.value.args
                          and isinstance(n.value.args[0], ast.Constant)
                          and n.value.args[0].value == '--depth-observer')
    guard = next(n for n in body if isinstance(n, ast.For)
                 and ast.unparse(n.target) == '(selected, flag, description)')
    environment = [n for n in body if isinstance(n, ast.Assign)
                   and ast.unparse(n.targets[0]) in
                   ('env', "env['MS_NATIVE_PCM_CUBIC']", "env['MS_NATIVE_PARTICLE_THRESHOLDS']", "env['MS_NATIVE_PARTICLE_COLLISIONS']", "env['MS_NATIVE_VISIBILITY']",
                    "env['MS_NATIVE_VISIBILITY_BATCH']", "env['MS_NATIVE_PARTICLE_RANDOM']")]
    assert len(environment) == len(flags) + 1
    depth_guard = next(n for n in body if isinstance(n, ast.If)
                       and ast.unparse(n.test) == 'args.depth_observer')
    depth_environment = next(n for n in body if isinstance(n, ast.Assign)
                             and ast.unparse(n.targets[0]) == "env['MS_DEPTH_OBSERVER']")

    def execute(nodes, namespace):
        tree = ast.fix_missing_locations(ast.Module(body=copy.deepcopy(nodes), type_ignores=[]))
        exec(compile(tree, str(root/'scripts/run.py'), 'exec'), namespace)

    count = 0
    out = root/'temp/checks'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-mode-guard-', dir=out) as directory:
        sandbox = Path(directory)
        assert sandbox.resolve().parent == out.resolve()
        native = sandbox/'build/native'
        native.mkdir(parents=True)
        exe = native/'authored-guard-input.bin'
        exe.write_bytes(b'Only hash admission is tested; never executed.')
        digest = hashlib.sha256(exe.read_bytes()).hexdigest()

        def cases(selected_guard, selected_environment):
            nonlocal count
            for pcm, visibility, batch, particle, collision, random in product(
                    ('0', 'shadow', '1'), ('0', 'shadow', '1'), ('0', 'shadow', '1'), ('0', 'shadow', '1'), ('0', 'shadow', '1'), ('0', 'shadow', '1')):
                for pcm_build, visibility_build, batch_build, particle_build, collision_build, random_build, stale in product((False, True), repeat=7):
                    metadata = dict(native_pcm_cubic=pcm_build, native_visibility=visibility_build,
                                    native_visibility_batch=batch_build,
                                    native_particle_thresholds=particle_build,
                                    native_particle_collisions=collision_build,
                                    native_particle_random=random_build,
                                    sha256='stale' if stale else digest)
                    (native/'build_identity.json').write_text(json.dumps(metadata))
                    ns = dict(argparse=argparse, __doc__=__doc__, ROOT=sandbox, exe=exe,
                              hashlib=hashlib, json=json,
                              os=SimpleNamespace(environ={'MS_NATIVE_PCM_CUBIC':'1',
                                                         'MS_NATIVE_PARTICLE_THRESHOLDS':'1',
                                                         'MS_NATIVE_PARTICLE_COLLISIONS':'1',
                                                         'MS_NATIVE_PARTICLE_RANDOM':'1',
                                                         'MS_NATIVE_VISIBILITY':'shadow',
                                                         'MS_NATIVE_VISIBILITY_BATCH':'1'}))
                    # run.py admits the selected executable's adjacent record
                    # first; the guard reads that admitted record.
                    ns['admitted'] = dict(build_identity=json.loads((native/'build_identity.json').read_text()),
                                          exe_sha256=digest)
                    execute([init, *arguments], ns)
                    ns['args'] = ns['ap'].parse_args([
                        '--native-pcm-cubic', pcm, '--native-visibility', visibility,
                        '--native-visibility-batch', batch,
                        '--native-particle-thresholds', particle,
                        '--native-particle-collisions', collision,
                        '--native-particle-random', random,
                    ])
                    expected = all(mode == '0' or built and not stale for mode, built in (
                        (pcm, pcm_build), (visibility, visibility_build), (batch, batch_build),
                        (particle, particle_build), (collision, collision_build),
                        (random, random_build),
                    ))
                    try:
                        execute([selected_guard, *selected_environment], ns)
                        admitted = True
                    except SystemExit as error:
                        assert 'matching --native-' in str(error)
                        admitted = False
                    assert admitted == expected, (pcm, visibility, batch, particle, collision, random, metadata, admitted)
                    if admitted:
                        assert ns['env']['MS_NATIVE_PCM_CUBIC'] == pcm
                        assert ns['env']['MS_NATIVE_PARTICLE_THRESHOLDS'] == particle
                        assert ns['env']['MS_NATIVE_PARTICLE_COLLISIONS'] == collision
                        assert ns['env']['MS_NATIVE_VISIBILITY'] == visibility
                        assert ns['env']['MS_NATIVE_VISIBILITY_BATCH'] == batch
                        assert ns['env']['MS_NATIVE_PARTICLE_RANDOM'] == random
                    count += 1
            for flag in flags:
                invalid_modes = ['2', 'yes', '-1']
                for invalid in invalid_modes:
                    with contextlib.redirect_stderr(io.StringIO()):
                        try:
                            ns['ap'].parse_args([flag, invalid])
                        except SystemExit as error:
                            assert error.code == 2
                        else:
                            raise AssertionError('Invalid mode accepted')

        cases(guard, environment)
        admitted_cases = count
        mutant = ast.parse(ast.unparse(guard).replace('not identity.get(flag) or ', '', 1)).body[0]
        for label, candidate, env in [
                ('missing build flag', mutant, environment),
                ('inherited visibility', guard, environment[:-2] + environment[-1:]),
                ('inherited particle thresholds', guard,
                 [n for n in environment if ast.unparse(n.targets[0]) != "env['MS_NATIVE_PARTICLE_THRESHOLDS']"]),
                ('inherited particle collisions', guard,
                 [n for n in environment if ast.unparse(n.targets[0]) != "env['MS_NATIVE_PARTICLE_COLLISIONS']"]),
                ('inherited visibility batch', guard, environment[:-1])]:
            try:
                cases(candidate, env)
            except (AssertionError, KeyError):
                pass
            else:
                raise AssertionError('Accepted actual-source mutant: '+label)
        for selected in (False, True):
            for built, stale in ((False, False), (True, False), (True, True)):
                metadata = dict(depth_observer=built, sha256='stale' if stale else digest)
                (native/'build_identity.json').write_text(json.dumps(metadata))
                ns = dict(argparse=argparse, __doc__=__doc__, ROOT=sandbox, exe=exe,
                          hashlib=hashlib, json=json,
                          os=SimpleNamespace(environ={'MS_DEPTH_OBSERVER':'1'}))
                ns['admitted'] = dict(
                    build_identity=json.loads((native/'build_identity.json').read_text()),
                    exe_sha256=digest)
                execute([init, depth_argument], ns)
                ns['args'] = ns['ap'].parse_args(['--depth-observer'] if selected else [])
                ns['env'] = {}
                try:
                    execute([depth_guard, depth_environment], ns)
                    admitted = True
                except SystemExit as error:
                    assert 'matching --depth-observer build' in str(error)
                    admitted = False
                assert admitted == (not selected or built and not stale), (selected, metadata, admitted)
                if admitted:
                    assert ns['env']['MS_DEPTH_OBSERVER'] == ('1' if selected else '0')
                count += 1
        mutant = copy.deepcopy(depth_guard)
        missing_build_guard = next(n for n in ast.walk(mutant) if isinstance(n, ast.If)
                                   and "identity.get('depth_observer')" in ast.unparse(n.test))
        missing_build_guard.test = ast.Constant(value=False)
        try:
            metadata = dict(depth_observer=False, sha256=digest)
            (native/'build_identity.json').write_text(json.dumps(metadata))
            ns = dict(argparse=argparse, __doc__=__doc__, ROOT=sandbox, exe=exe,
                      hashlib=hashlib, json=json, os=SimpleNamespace(environ={}))
            ns['admitted'] = dict(build_identity=metadata, exe_sha256=digest)
            execute([init, depth_argument], ns)
            ns['args'] = ns['ap'].parse_args(['--depth-observer'])
            execute([mutant], ns)
        except SystemExit:
            raise AssertionError('Rejected missing observer build after removing its admission guard')
        native_argument = next(n for n in body if isinstance(n, ast.Expr)
                               and isinstance(n.value, ast.Call) and n.value.args
                               and isinstance(n.value.args[0], ast.Constant)
                               and n.value.args[0].value == '--native-depth')
        native_guard = next(n for n in body if isinstance(n, ast.If)
                            and ast.unparse(n.test) == "args.native_depth != '0'")
        native_environment = next(n for n in body if isinstance(n, ast.Assign)
                                  and ast.unparse(n.targets[0]) == "env['MS_NATIVE_DEPTH']")

        def native_cases(candidate, setting):
            for mode in ('0', '1'):
                for observer in (False, True):
                    for built in (False, True):
                        for stale in (False, True):
                            (native/'build_identity.json').write_text(json.dumps(dict(
                                depth_observer=True, native_depth_query=built,
                                sha256='stale' if stale else digest)))
                            ns = dict(argparse=argparse, __doc__=__doc__, ROOT=sandbox,
                                      exe=exe, hashlib=hashlib, json=json,
                                      env={'MS_NATIVE_DEPTH': '1'})
                            ns['admitted'] = dict(
                                build_identity=json.loads((native/'build_identity.json').read_text()),
                                exe_sha256=digest)
                            execute([init, depth_argument, native_argument], ns)
                            argv = ['--native-depth', mode] + (['--depth-observer'] if observer else [])
                            ns['args'] = ns['ap'].parse_args(argv)
                            try:
                                execute([candidate, *setting], ns)
                                admitted = True
                            except SystemExit as error:
                                assert 'Native depth requires' in str(error)
                                admitted = False
                            assert admitted == (mode == '0' or observer and built and not stale)
                            if admitted:
                                assert ns['env']['MS_NATIVE_DEPTH'] == mode

        native_cases(native_guard, [native_environment])
        missing_flag = ast.parse(ast.unparse(native_guard).replace(
            "not identity.get('native_depth_query') or ", '', 1)).body[0]
        for candidate, setting in ((missing_flag, [native_environment]), (native_guard, [])):
            try:
                native_cases(candidate, setting)
            except AssertionError:
                pass
            else:
                raise AssertionError('Native depth admission mutant escaped')
    print(f'PASS native-mode admission; {admitted_cases} mode combinations plus 16 native-query combinations, unsafe mutants rejected')


if __name__ == '__main__':
    main()
