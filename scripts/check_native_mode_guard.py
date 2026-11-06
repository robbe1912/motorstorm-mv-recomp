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
    flags = {'--native-pcm-cubic', '--native-visibility', '--native-short-sleep'}
    init = next(n for n in body if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'ap')
    arguments = [n for n in body if isinstance(n, ast.Expr)
                 and isinstance(n.value, ast.Call) and n.value.args
                 and isinstance(n.value.args[0], ast.Constant)
                 and n.value.args[0].value in flags]
    assert len(arguments) == 3
    guard = next(n for n in body if isinstance(n, ast.For)
                 and ast.unparse(n.target) == '(selected, flag, description)')
    environment = [n for n in body if isinstance(n, ast.Assign)
                   and ast.unparse(n.targets[0]) in
                   ('env', "env['MS_NATIVE_PCM_CUBIC']", "env['MS_NATIVE_VISIBILITY']", "env['PS3_NATIVE_SHORT_SLEEP']")]
    assert len(environment) == 4

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
            for pcm, visibility, short_wait in [(p,v,s) for p,v in [('0','0'), ('shadow','0'), ('1','0'),
                                    ('0','shadow'), ('0','1'), ('1','shadow')] for s in ('0','1')]:
                for pcm_build, visibility_build, stale, short_build in [(p,v,s,b) for p,v,s in [
                        (False,False,False), (True,False,False),
                        (False,True,False), (True,True,False), (True,True,True)] for b in (False,True)]:
                    metadata = dict(native_pcm_cubic=pcm_build, native_visibility=visibility_build, native_short_sleep=short_build,
                                    sha256='stale' if stale else digest)
                    (native/'build_identity.json').write_text(json.dumps(metadata))
                    ns = dict(argparse=argparse, __doc__=__doc__, ROOT=sandbox, exe=exe,
                              hashlib=hashlib, json=json,
                              os=SimpleNamespace(environ={'MS_NATIVE_PCM_CUBIC':'1',
                                                         'MS_NATIVE_VISIBILITY':'shadow', 'PS3_NATIVE_SHORT_SLEEP':'1'}))
                    execute([init, *arguments], ns)
                    ns['args'] = ns['ap'].parse_args(['--native-pcm-cubic',pcm,
                                                   '--native-visibility',visibility, '--native-short-sleep',short_wait])
                    expected = (pcm == '0' or pcm_build and not stale) and \
                               (visibility == '0' or visibility_build and not stale) and (short_wait == '0' or short_build and not stale)
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
                        assert ns['env']['PS3_NATIVE_SHORT_SLEEP'] == short_wait
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
                                      ('inherited visibility', guard, [n for n in environment if ast.unparse(n.targets[0])!="env['MS_NATIVE_VISIBILITY']"]),
                                      ('inherited short wait', guard, environment[:-1])]:
            try:
                cases(candidate, env)
            except (AssertionError, KeyError):
                pass
            else:
                raise AssertionError('Accepted actual-source mutant: '+label)
    print(f'PASS actual native-mode parser/build/hash/environment admission; {admitted_cases} combinations, {len(flags)*3} invalid selectors, three mutants rejected')


if __name__ == '__main__':
    main()
