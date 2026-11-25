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
 def build(name,source,define=None,extra_include=None,simd=None):
  exe=out/(name+('.exe' if os.name=='nt' else ''));inc=([str(extra_include)] if extra_include else [])+[str(sdk),str(sdk/'include'),str(spu)]
  if msvc:cmd=[cc,'/nologo','/std:c17','/O1','/UNDEBUG','/D_CRT_SECURE_NO_WARNINGS',*['/I'+x for x in inc],*(['/D'+define] if define else []),source,simd or spu/'spu_float_simd.c','/Fe'+str(exe),'/Fo'+str(out)+os.sep]
  else:cmd=[cc,'-std=c17','-O1','-fno-strict-aliasing','-ffp-contract=off','-UNDEBUG',*['-I'+x for x in inc],*(['-D'+define] if define else []),source,simd or spu/'spu_float_simd.c','-lm','-o',exe]
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
 # The scope fixture must reject, each by the named check: host-arithmetic
 # helpers left in the held SPU mode or not returned to it, helpers that leave a
 # caller's own SPU controls outside a scope, a nested entry that replaces the
 # outermost caller, an outermost entry that does not record a caller with SPU
 # controls, and float compares that order -0 below +0 (private source copies).
 rejected={};capture='if (!g_spu_sf_simd_scope) g_spu_sf_host_csr=csr;'
 for name,file,old,new,wrong in [
   ('host-arithmetic-in-spu-mode','spu_float_simd.h','    _mm_setcsr((g_spu_sf_host_csr','    if (0) _mm_setcsr((g_spu_sf_host_csr','host-arithmetic helpers keep caller-environment results inside the scope'),
   ('host-arithmetic-not-restored','spu_float_simd.h','if (held) _mm_setcsr(held);','(void)held;','host-arithmetic helpers return to the held SPU mode'),
   ('host-switch-outside-scope','spu_float_simd.h',' || !g_spu_sf_simd_scope) return 0;',') return 0;','outside a scope a truncating caller truncates'),
   ('nested-capture','spu_float_simd.c',capture,'if (!spu_sf_csr_is_spu(csr)) g_spu_sf_host_csr=csr;',"nested scope keeps the outermost caller's rounding"),
   ('no-capture-of-spu-caller','spu_float_simd.c',capture,capture.replace('scope)','scope && !spu_sf_csr_is_spu(csr))'),'the outermost scope records a caller with SPU controls'),
   ('signed-zero-order','spu_helpers.h','? -(int32_t)(x & 0x7fffffffu) :','? -(int32_t)(x & 0x7fffffffu)-1 :','float compares match host IEEE compares inside the scope')]:
  private=out/(name+'-sources');private.mkdir()   # not out/name: that is the executable on Linux
  for part in ('spu_helpers.h','spu_float_simd.h','spu_float_simd.c'):
   text=(spu/part).read_text(encoding='utf8')
   if part==file:assert text.count(old)==1,(name,part);text=text.replace(old,new)
   (private/part).write_text(text,encoding='utf8')
  m=run([build(name,ROOT/'scripts/fixtures/robbe_float_simd.c',extra_include=private,simd=private/'spu_float_simd.c')],expected=1)
  failed=sorted({x[5:] for x in m.stderr.splitlines() if x.startswith('FAIL ')});assert wrong in failed,(name,failed);rejected[name]=dict(result=m.stdout.strip(),failed=failed)
 # Halt and stack-reset landings of the real spu_run_with_halt. "kept" forces
 # SPU mode at both landings, as a longjmp that keeps the MXCSR leaves it (the
 # Windows x64 one restores it), so each restore is tested on every platform.
 units=['spu_drain.c','spu_lockstep.c','spu_coherency.c','spu_workload.c','spurs_policy.c','spurs_job.c','spu_tsp_weak.c','spu_vm_pagemap.c','spurs_policy_blob_weak.c','spu_interp.c','spu_float_simd.c','spu_task_lifecycle.c']
 runtime=[*[spu/n for n in units],sdk/'runtime/platform/win32_compat.c',sdk/'runtime/memory/guest_read_sync.c',sdk/'runtime/diag/loadtime_trace.c',sdk/'runtime/platform/thread_name.c']
 channels=(spu/'spu_channels.c').read_text(encoding='utf8')
 force='_mm_setcsr(_mm_getcsr() | SPU_SF_CSR_SPU);\n';restore='        spu_sf_simd_leave(sf_mark);\n'
 halt='    case 1:\n';reset='    case 2: {\n'
 halt_at=halt+restore;reset_at=reset+restore;kept_halt=(halt_at,halt+force+restore);kept_reset=(reset_at,reset+force+restore)
 enter='const uint64_t sf_scope = spu_sf_simd_enter();';leave='spu_sf_simd_leave(sf_scope);'
 landings={};cases=['halt','reset','reset-halt','reset-reset','nested']
 for name,edits,wrong in [('landing',[],None),('landing-kept',[kept_halt,kept_reset],None),
                          ('landing-no-halt-restore',[(halt_at,halt)],'halt'),
                          ('landing-kept-no-halt-restore',[(halt_at,halt+force),kept_reset],'halt'),
                          ('landing-kept-no-reset-restore',[kept_halt,(reset_at,reset+force)],'reset'),
                          ('landing-no-reset-enter',[(enter,'const uint64_t sf_scope = sf_mark;')],'reset'),
                          ('landing-no-reset-leave',[(leave,'(void)sf_scope;')],'reset')]:
  target=out/(name+'-build');target.mkdir();text=channels
  for old,new in edits:assert text.count(old)==1,(name,old);text=text.replace(old,new)
  private=target/'spu_channels.c';private.write_text(text,encoding='utf8');exe=target/('test.exe' if os.name=='nt' else 'test')
  sources=[ROOT/'scripts/fixtures/spu_float_landing.c',private,*runtime];inc=[sdk/'include',spu,sdk/'runtime/platform']
  if msvc:run([cc,'/nologo','/TC','/std:c17','/O1','/UNDEBUG','/MDd','/D_CRT_SECURE_NO_WARNINGS',*['/I'+str(x) for x in inc],*sources,'/Fo'+str(target)+os.sep,'/Fe'+str(exe),'/link','Synchronization.lib'])
  else:run([cc,'-std=gnu17','-D_GNU_SOURCE','-O1','-UNDEBUG',*['-I'+str(x) for x in inc],*sources,'-pthread','-lm','-o',exe])
  landings[name]={}
  for case in ([wrong] if wrong else cases):
   m=run([exe,case],expected=1 if wrong else 0)
   lines=[x for x in (m.stderr if wrong else m.stdout).splitlines() if x.startswith('FAIL landing' if wrong else 'PASS '+case)]
   assert lines,(name,case,m.stdout,m.stderr);landings[name][case]=lines[-1]
 result=dict(landings=landings,passed=True,exact_rational_lanes_per_mode=len(expected),modes=['scalar','scoped SIMD'],historical_ieee_multiply_mismatches=bad,scope_result=r.stdout.strip(),rejected_mutants=rejected,game_launched=False,FPSCR_exception_flags_tested=False,source_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [p for p in [spu/'spu_channels.c',ROOT/'scripts/fixtures/spu_float_landing.c',spu/'spu_helpers.h',spu/'spu_float.h',spu/'spu_float_simd.c',spu/'spu_float_simd.h']]})
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result,indent=2));print('Evidence:',out)
if __name__=='__main__':main()
