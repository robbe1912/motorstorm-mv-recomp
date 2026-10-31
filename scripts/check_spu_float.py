"""Authored exact-rational SPU value and SIMD-scope regression; no game input."""
import argparse,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
import robbe_float_oracle as oracle
ROOT=Path(__file__).resolve().parents[1]
def main():
 if os.name=='nt' and not (os.environ.get('INCLUDE') and os.environ.get('LIB')):
  from project import build_environment
  os.environ.update(build_environment())
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',default=os.environ.get('MV_CLANG') or os.environ.get('CC') or ('clang-cl' if os.name=='nt' else 'clang'));a=ap.parse_args()
 cc=shutil.which(a.compiler) or a.compiler;msvc=Path(cc).name.lower() in ('cl','cl.exe','clang-cl','clang-cl.exe')
 out=ROOT/'temp/checks'/('spu-float-'+str(time.time_ns()));out.mkdir(parents=True);sdk=ROOT/'vendor/ps3recomp';spu=sdk/'runtime/spu';records=[]
 def run(cmd,input=None,expected=0):
  r=subprocess.run(list(map(str,cmd)),input=input,cwd=ROOT,capture_output=True,text=True,errors='replace',timeout=120);records.append(dict(command=list(map(str,cmd)),returncode=r.returncode,stdout=r.stdout if input is None else 'lane output retained separately',stderr=r.stderr));(out/'commands.json').write_text(json.dumps(records,indent=2),encoding='utf8');assert r.returncode==expected,(cmd,r.stdout[-2000:],r.stderr[-2000:]);return r
 def build(name,source,define=None,extra_include=None):
  exe=out/(name+('.exe' if os.name=='nt' else ''));inc=([str(extra_include)] if extra_include else [])+[str(sdk),str(sdk/'include'),str(spu)]
  if msvc:cmd=[cc,'/nologo','/std:c17','/O1','/UNDEBUG','/D_CRT_SECURE_NO_WARNINGS',*['/I'+x for x in inc],*(['/D'+define] if define else []),source,spu/'spu_float_simd.c','/Fe'+str(exe),'/Fo'+str(out)+os.sep]
  else:cmd=[cc,'-std=c17','-O1','-fno-strict-aliasing','-ffp-contract=off','-UNDEBUG',*['-I'+x for x in inc],*(['-D'+define] if define else []),source,spu/'spu_float_simd.c','-lm','-o',exe]
  run(cmd);return exe
 rows=[];expected=[]
 for op,group in oracle.cases():
  rows.append(str(op)+' '+' '.join(f'{group[lane][operand]:08x}' for operand in range(3) for lane in range(4)));expected.extend(oracle.reference(op,*v) for v in group)
 payload='\n'.join(rows)+'\n';driver=ROOT/'scripts/fixtures/robbe_float_driver.c'
 def mismatches(name,exe):
  r=run([exe],input=payload);(out/(name+'-lanes.txt')).write_text(r.stdout,encoding='ascii');actual=[int(w,16) for w in r.stdout.split()];assert len(actual)==len(expected);return sum(x!=y for x,y in zip(actual,expected))
 for name,define in [('scalar',None),('simd','SPU_FLOAT_SIMD_TEST')]:assert mismatches(name,build(name,driver,define))==0
 # Reintroduce only historical IEEE multiplication in a private header copy.
 # The exact-rational oracle, including exponent255 and zero normalization,
 # must identify the wrong value rather than a compiler/link/setup failure.
 old=out/'ieee/runtime/spu';old.mkdir(parents=True)
 text=(spu/'spu_helpers.h').read_text(encoding='utf8');pattern=r'static inline u128 spu_fm\(u128 a, u128 b\) \{[^\n]*\}'
 text,n=re.subn(pattern,'static inline u128 spu_fm(u128 a, u128 b) { u128 r; for(int i=0;i<4;i++) r._f32[i]=a._f32[i]*b._f32[i]; return r; }',text);assert n==1
 (old/'spu_helpers.h').write_text(text,encoding='utf8');bad=mismatches('historical-ieee-mul',build('historical-ieee-mul',driver,extra_include=out/'ieee'));assert bad>0
 r=run([build('scope',ROOT/'scripts/fixtures/robbe_float_simd.c')]);assert 'failures=0' in r.stdout;print(r.stdout.strip())
 result=dict(passed=True,exact_rational_lanes_per_mode=len(expected),modes=['scalar','scoped SIMD'],historical_ieee_multiply_mismatches=bad,scope_result=r.stdout.strip(),game_launched=False,FPSCR_exception_flags_tested=False,source_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [p for p in [spu/'spu_helpers.h',spu/'spu_float.h',spu/'spu_float_simd.c',spu/'spu_float_simd.h']]})
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result,indent=2));print('Evidence:',out)
if __name__=='__main__':main()
