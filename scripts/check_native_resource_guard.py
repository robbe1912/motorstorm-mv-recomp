"""Check real guard policy against retained host admission and failure boundaries."""
import argparse
import ast
from pathlib import Path
import sys
from unittest.mock import patch
from native_resource_guard import GIB, commit_reserve, physical_reserve, limits, first_breach


def launcher_policy(argv, old_wiring=False):
    """Execute actual parser/budget statements without launching a process."""
    tree=ast.parse(Path(__file__).with_name('run.py').read_text())
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    selected=[]
    for node in main.body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in ('ap','args','resource_policy'): selected.append(node)
        elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            call=node.value
            if call.args and isinstance(call.args[0],ast.Constant) and call.args[0].value in ('--min-free-commit-gib','--min-free-physical-gib'):
                selected.append(node)
    if old_wiring:
        # Exact previous production assignment (one commit reserve argument).
        selected[-1]=ast.parse('resource_policy=limits(args.min_free_commit_gib)').body[0]
    env=dict(argparse=argparse,commit_reserve=commit_reserve,physical_reserve=physical_reserve,limits=limits)
    with patch.object(sys,'argv',['run.py',*argv]):
        exec(compile(ast.Module(body=selected,type_ignores=[]),'run.py','exec'),env)
    return env['resource_policy']


def main():
    sample=dict(private=1904955392,physical_available=12761083904,commit_available=12771143680,disk_available=127139672064)
    assert first_breach(sample,limits()) == dict(metric='commit_available',actual_bytes=12771143680,limit_bytes=12*GIB,kind='minimum')
    assert first_breach(sample,limits(6)) is None
    for metric, value in [('private',14*GIB+1),('physical_available',4*GIB-1),('commit_available',6*GIB-1),('disk_available',8*GIB-1)]:
        changed=dict(sample);changed[metric]=value
        result=first_breach(changed,limits(6));assert result and result['metric']==metric
    boundary=dict(private=14*GIB,physical_available=4*GIB,commit_available=6*GIB,disk_available=8*GIB)
    assert first_breach(boundary,limits(6)) is None
    for value in ['nan','inf','-inf','x','3.999','12.001',0,None]:
        try: limits(value)
        except argparse.ArgumentTypeError: pass
        else: raise AssertionError(f'Accepted invalid reserve {value!r}')
    for value in ['4','6','12','6.5']:
        assert limits(value)['commit_available']['minimum']==int(float(value)*GIB)
    assert commit_reserve(12)==12
    # Actual resource-stop sample from the concurrent-host diagnostic run.
    observed=dict(private=1409699840,physical_available=4255191040,commit_available=8580882432,disk_available=117147635712)
    assert first_breach(observed,limits(4))['metric']=='physical_available'
    assert first_breach(observed,limits(4,1)) is None
    for value in ['nan','inf','-inf','x','0.999','4.001',0,None]:
        try: limits(4,value)
        except argparse.ArgumentTypeError: pass
        else: raise AssertionError(f'Accepted invalid physical reserve {value!r}')
    for value in ['1','1.5','4']:
        policy=launcher_policy(['--min-free-commit-gib','4','--min-free-physical-gib',value])
        assert policy==limits(4,float(value))
        for metric,rule in policy.items():
            kind,bound=next(iter(rule.items()))
            at={key:next(iter(bounds.values())) for key,bounds in policy.items()}
            assert first_breach(at,policy) is None
            at[metric]=bound+(-1 if kind=='minimum' else 1)
            assert first_breach(at,policy)['metric']==metric
    assert launcher_policy([])==limits()
    old=launcher_policy(['--min-free-commit-gib','4','--min-free-physical-gib','1'],old_wiring=True)
    assert first_breach(observed,old)['metric']=='physical_available', 'Old CLI omission did not reproduce the stop'
    print('PASS: two historical admissions, default/explicit launcher policies, old omission RED, finite bounds and all four exact stop boundaries')


if __name__=='__main__': main()
