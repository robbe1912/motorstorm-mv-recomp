"""Check real guard policy against retained host admission and failure boundaries."""
import argparse
from native_resource_guard import GIB, commit_reserve, limits, first_breach


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
    print('PASS: historical admission, bounded reserve, all four stop causes, exact boundaries and invalid options')


if __name__=='__main__': main()
