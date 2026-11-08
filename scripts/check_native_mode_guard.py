"""Exercise actual launcher mode parsing, build admission and inherited overrides.

Executes only selected AST statements; no config, process or PAD action runs.
"""
import argparse
import ast
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def main():
    root = Path(__file__).resolve().parents[1]
    body = next(n for n in ast.parse((root/'scripts/run.py').read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'main').body
    flags = {'--native-pcm-cubic', '--native-visibility'}
    init = next(n for n in body if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'ap')
    arguments = [n for n in body if isinstance(n, ast.Expr)
                 and isinstance(n.value, ast.Call) and n.value.args
                 and isinstance(n.value.args[0], ast.Constant)
                 and n.value.args[0].value in flags]
    assert len(arguments) == 2
    depth_argument = next(n for n in body if isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Call) and n.value.args
                          and isinstance(n.value.args[0], ast.Constant)
                          and n.value.args[0].value == '--depth-observer')
    guard = next(n for n in body if isinstance(n, ast.For)
                 and ast.unparse(n.target) == '(selected, flag, description)')
    environment = [n for n in body if isinstance(n, ast.Assign)
                   and ast.unparse(n.targets[0]) in
                   ('env', "env['MS_NATIVE_PCM_CUBIC']", "env['MS_NATIVE_VISIBILITY']")]
    assert len(environment) == 3
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
            for pcm, visibility in [('0','0'), ('shadow','0'), ('1','0'),
                                    ('0','shadow'), ('0','1'), ('1','shadow')]:
                for pcm_build, visibility_build, stale in [
                        (False,False,False), (True,False,False),
                        (False,True,False), (True,True,False), (True,True,True)]:
                    metadata = dict(native_pcm_cubic=pcm_build, native_visibility=visibility_build,
                                    sha256='stale' if stale else digest)
                    (native/'build_identity.json').write_text(json.dumps(metadata))
                    ns = dict(argparse=argparse, __doc__=__doc__, ROOT=sandbox, exe=exe,
                              hashlib=hashlib, json=json,
                              os=SimpleNamespace(environ={'MS_NATIVE_PCM_CUBIC':'1',
                                                         'MS_NATIVE_VISIBILITY':'shadow'}))
                    execute([init, *arguments], ns)
                    ns['args'] = ns['ap'].parse_args(['--native-pcm-cubic',pcm,
                                                   '--native-visibility',visibility])
                    expected = (pcm == '0' or pcm_build and not stale) and \
                               (visibility == '0' or visibility_build and not stale)
                    try:
                        execute([selected_guard, *selected_environment], ns)
                        admitted = True
                    except SystemExit as error:
                        assert 'matching --native-' in str(error)
                        admitted = False
                    assert admitted == expected, (pcm, visibility, metadata, admitted)
                    if admitted:
                        assert ns['env']['MS_NATIVE_PCM_CUBIC'] == pcm
                        assert ns['env']['MS_NATIVE_VISIBILITY'] == visibility
                    count += 1
            for flag in flags:
                for invalid in ['2','yes','-1']:
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
        for label, candidate, env in [('missing build flag', mutant, environment),
                                      ('inherited visibility', guard, environment[:-1])]:
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
            execute([init, depth_argument], ns)
            ns['args'] = ns['ap'].parse_args(['--depth-observer'])
            execute([mutant], ns)
        except SystemExit:
            raise AssertionError('Rejected missing observer build after removing its admission guard')
    print(f'PASS actual native-mode parser/build/hash/environment admission; {admitted_cases} combinations, six invalid selectors, three mutants rejected')


if __name__ == '__main__':
    main()
