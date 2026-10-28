"""Authored Windows shader storage/recovery checks; no game inputs or launch."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def function(text,name):
 masked=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda m:' '*len(m[0]),text,flags=re.S)
 found=re.search(r'\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked);assert found,name
 start=masked.rfind('\n',0,found.start())+1;brace=masked.index('{',found.start());depth=1;end=brace+1
 while depth:depth+=(masked[end]=='{')-(masked[end]=='}');end+=1
 return text[start:end]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--cc',default='clang');ap.add_argument('--output',type=Path,default=ROOT/'temp/checks'/('shader-storage-'+str(time.time_ns())));a=ap.parse_args()
 if os.name!='nt':raise SystemExit('These Windows/FXC checks require Windows.')
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 consumer=(ROOT/'vendor/ps3recomp').is_dir();video=ROOT/('vendor/ps3recomp/libs/video' if consumer else 'libs/video');fixtures=ROOT/('scripts/fixtures' if consumer else 'tests/fixtures')
 sdk=video.parents[1];records=[];cl=Path(a.cc).stem.lower() in ('cl','clang-cl')
 def run(command,expect=0):
  command=list(map(str,command));q=subprocess.run(command,cwd=out,env=dict(os.environ,TEMP=str(out),TMP=str(out),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,errors='replace',timeout=180)
  records.append(dict(command=command,exit=q.returncode,stdout=q.stdout,stderr=q.stderr));(out/'commands.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
  if q.returncode!=expect:raise RuntimeError(q.stdout[-4000:]+q.stderr[-4000:])
  if q.stdout:print(q.stdout.strip(),flush=True)
  return q
 def build(source,name,libraries=(),first=(),syntax=False,sources=()):
  exe=out/(name+'.exe')
  includes=[*first,video,sdk/'include']
  if cl:
   command=[a.cc,'/nologo','/TC','/std:c17','/Od','/UNDEBUG','/D_CRT_SECURE_NO_WARNINGS','/D_WIN32_WINNT=0x0A00','/arch:AVX2',*['/I'+str(p) for p in includes],source,*sources]
   command+=['/Zs'] if syntax else ['/Fe'+str(exe),'/link',*[lib+'.lib' for lib in libraries]]
  else:
   command=[a.cc,'-std=c17','-O1','-UNDEBUG','-D_CRT_SECURE_NO_WARNINGS','-D_WIN32_WINNT=0x0A00','-mavx2',*['-I'+str(p) for p in includes],source,*sources]
   command+=['-fsyntax-only'] if syntax else ['-o',exe,*['-l'+lib for lib in libraries]]
  run(command);return exe
 exe=build(fixtures/'rsx_shader_disk_cache.c','storage',['d3dcompiler','bcrypt']);cache=out/'storage-cache';cache.mkdir();run([exe,cache])
 exe=build(fixtures/'shader_disk_backend.c','adapter',['d3dcompiler','bcrypt'])
 with exe.open('ab') as f:f.truncate(65*1024*1024)
 cache=out/'adapter-cache'/'nested';run([exe,cache,'cold'])
 other=out/'adapter-other.exe';shutil.copyfile(exe,other)
 with other.open('ab') as f:f.write(b'different authored executable')
 run([other,cache,'warm'])
 blocked=out/'blocked';blocked.write_text('authored obstruction',encoding='utf-8')
 q=run([exe,blocked/'cache','blocked']);assert q.stderr.count('[SHADERCACHE] first store failure')==1 and 'GetLastError=' in q.stderr
 q=run([exe,out/'removed-cache'/'nested','store-blocked']);assert q.stderr.count('[SHADERCACHE] first store failure')==1 and 'stage=store' in q.stderr
 q=run([exe,'0','disabled']);assert '[SHADERCACHE]' not in q.stderr
 # Reproduce the exact old import-thunk defect in a large authored executable.
 mutant=out/'mutant-thunk';mutant.mkdir();h=(video/'rsx_shader_disk_backend.h').read_text(encoding='utf-8')
 needle='rsx_shader_disk_export_id(D3DCOMPILER_DLL_W,"D3DCompile",compiler)';assert needle in h
 (mutant/'rsx_shader_disk_backend.h').write_text(h.replace(needle,'rsx_shader_disk_compiler_id((const void*)D3DCompile,compiler)'),encoding='utf-8')
 broken=build(fixtures/'shader_disk_backend.c','broken-thunk',['d3dcompiler','bcrypt'],first=[mutant])
 with broken.open('ab') as f:f.truncate(65*1024*1024)
 run([broken,out/'thunk-cache','cold'],1)
 mutant=out/'mutant-integrity';mutant.mkdir();h=(video/'rsx_shader_disk_cache.h').read_text(encoding='utf-8');needle='memcmp(check,header+56,32)';assert needle in h
 (mutant/'rsx_shader_disk_cache.h').write_text(h.replace(needle,'0'),encoding='utf-8')
 broken=build(fixtures/'rsx_shader_disk_cache.c','broken-integrity',['d3dcompiler','bcrypt'],first=[mutant]);cache=out/'integrity-cache';cache.mkdir();run([broken,cache],1)
 # Actual Windows workers, shutdown/leases and exact bounded prefetch identities.
 exe=build(fixtures/'rsx_fxc_pool.c','pool');run([exe])
 exe=build(fixtures/'rsx_prefetch_seen.c','prefetch',sources=[video/'rsx_fp_decompiler.c']);run([exe])
 mutant=out/'mutant-prefetch';mutant.mkdir();h=(video/'rsx_prefetch_seen.h').read_text(encoding='utf-8')
 needle=' && !memcmp(s->bytes+p->offset,key,size)';assert needle in h
 (mutant/'rsx_prefetch_seen.h').write_text(h.replace(needle,''),encoding='utf-8')
 exe=build(fixtures/'rsx_prefetch_seen.c','broken-prefetch',first=[mutant],sources=[video/'rsx_fp_decompiler.c']);run([exe],1)
 backend=(video/'rsx_d3d12_backend.c').read_text(encoding='utf-8')
 worker=(video/'rsx_shader_pool_backend.h').read_text(encoding='utf-8')
 compile_body=function(worker,'shader_worker_compile');release_body=function(worker,'shader_worker_release')
 for forbidden in ('s_d3d','CreateGraphicsPipelineState','shader_disk_','rsx_shader_cache_','rsx_prefetch_'):
  assert forbidden not in compile_body+release_body,forbidden
 pso=function(backend,'vp_get_fp_pso');call=pso.index('fp_compile_cached(')
 assert pso.index('if(shader_prefetch_active)',call)<pso.index('shader_create_pso(')
 assert 'shader_prepare_draw(dr,shader_prefetch_pass);' in backend
 assert 'shader_compile_draw(dr);' in backend[backend.index('if(shader_prefetch_pass){', backend.index('shader_prepare_draw(dr,shader_prefetch_pass);')):]
 draw=function(backend,'shader_compile_draw');prepare=function(backend,'shader_prepare_draw')
 single='#define HAS_SINGLE_PSO 1\n'+function(backend,'single_pso_on') if consumer else '#define HAS_SINGLE_PSO 0'
 owner=(fixtures/'shader_owner_pool.c.in').read_text(encoding='utf-8').replace('@OWNER_DRAW@',draw).replace('@PREPARE_DRAW@',prepare).replace('@SINGLE_PSO@',single)
 source=out/'owner.c';source.write_text(owner,encoding='utf-8')
 exe=build(source,'owner',['d3dcompiler','bcrypt']);default_owner=run([exe]);run([exe,'disabled'])
 default_prefetch_exercised='SKIP' not in default_owner.stdout
 if default_prefetch_exercised:assert 'queued=0 claimed=0' not in default_owner.stdout
 if consumer:
  for mode in ['legacy-default','legacy-duplicate','legacy-single']:run([exe,mode])
 if default_prefetch_exercised:
  # Restore the exact original consumer gate. The default fixture must fail
  # specifically because no work was queued, before any owner-resolution pass.
  before='if (dr->fp_addr)'
  assert before in draw
  gate='if (dr->fp_addr && !single_pso_on())' if consumer else 'if (dr->fp_addr && !shader_prefetch_active)'
  broken_owner=owner.replace(draw,draw.replace(before,gate,1))
  broken_source=out/'owner-blocked.c';broken_source.write_text(broken_owner,encoding='utf-8')
  broken=build(broken_source,'owner-blocked',['d3dcompiler','bcrypt'])
  rejected=run([broken],1);assert 'shader_queued>0' in rejected.stderr
  result=run([exe,'wrong-owner'],1);assert '!wrong_device_thread' in result.stderr
 # Execute actual owner coordinator functions with authored COM/compiler/device objects.
 b=(video/'rsx_shader_bytecode_backend.h').read_text(encoding='utf-8');wrapper=b[b.index('static rsx_shader_cache s_fp_bytecode;'):b.index('static size_t s_vs_disk_source_bytes;')]
 wrapper+='\n#define RSX_VS_DISK_SOURCE_MAX (32u*1024u*1024u)\n'+function(b,'shader_compile_vs')+'\n'+function(b,'shader_forget_vs_source')
 b=(video/'rsx_shader_pso_recovery.h').read_text(encoding='utf-8');retry=function(b,'shader_retry_vs_disk')+'\n'+function(b,'shader_create_pso')
 template=(fixtures/'shader_cache_backend.c.in').read_text(encoding='utf-8');source=out/'recovery.c';source.write_text(template.replace('@WRAPPER@',wrapper).replace('@RETRY@',retry),encoding='utf-8')
 exe=build(source,'recovery');run([exe])
 needle='if(SUCCEEDED(hr) || (!fp_disk && !vs_disk)';assert needle in retry
 source.write_text(template.replace('@WRAPPER@',wrapper).replace('@RETRY@',retry.replace(needle,'if(1 || SUCCEEDED(hr) || (!fp_disk && !vs_disk)')),encoding='utf-8')
 exe=build(source,'broken-recovery');run([exe],1)
 backend=(video/'rsx_d3d12_backend.c').read_text(encoding='utf-8')
 assert '#include "rsx_shader_bytecode_backend.h"' in backend and '#include "rsx_shader_pso_recovery.h"' in backend
 assert 'fp_compile_cached(fp_addr' in backend and 'shader_create_pso(&pd,hlsl,vs_idx' in backend
 build(video/'rsx_d3d12_backend.c','backend',syntax=True)
 files=[p for p in video.glob('rsx_shader*.h')]+list(fixtures.glob('*shader*'))
 files += [video/name for name in ['rsx_fxc_pool.h','rsx_prefetch_seen.h','rsx_fp_decompiler.c','rsx_fp_decompiler.h','rsx_d3d12_backend.c']]+[fixtures/'rsx_fxc_pool.c',fixtures/'rsx_prefetch_seen.c',Path(__file__)]
 result=dict(passed=True,consumer=consumer,default_prefetch_exercised=default_prefetch_exercised,default_owner_output=default_owner.stdout,commands=len(records),game_build=False,game_launch=False,private_game_inputs=False,inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()})
 (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print('PASS shader cache/recovery; evidence:',out)
if __name__=='__main__':main()
