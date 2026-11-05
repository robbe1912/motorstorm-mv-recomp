"""Headless actual uploader/resources/fences/readback. Requires Windows DX12 + debug layer.
No window, game inputs, driver configuration or desktop control. --adapter selects
hardware or explicit WARP; unsupported setup fails instead of falling back.
"""
import argparse,csv,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/"vendor/ps3recomp"
if os.name=="nt":
    from project import build_environment
    os.environ.update(build_environment())

def function(source,name):
    match=re.search(r'static (?:void|int) '+name+r'\([^\n]*\)\n\{.*?\n\}',source,re.S)
    assert match,f'Missing production definition {name}'
    return match.group()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--adapter',choices=['hardware','warp'],default='hardware');ap.add_argument('--historical-backend',type=Path);args=ap.parse_args()
    assert os.name=='nt','This actual D3D12 test requires Windows; no simulated pass is provided'
    tasks=subprocess.check_output(['tasklist','/FI','IMAGENAME eq ms1_recomp.exe','/FO','CSV','/NH'],text=True)
    assert not any(row and row[0].lower()=='ms1_recomp.exe' for row in csv.reader(tasks.splitlines())),'Stop the owned game before this diagnostic'
    compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl');assert compiler,'Prepare VS compiler environment or set MV_CLANG'
    out=ROOT/'temp/checks'/f'texture-gpu-{time.time_ns()}';out.mkdir(parents=True)
    backend=VENDOR/'libs/video/rsx_d3d12_backend.c';source=backend.read_text()
    public_header=VENDOR/'libs/video/rsx_d3d12_backend.h'
    header,count=re.subn(r'(?m)^(int|void) (rsx_d3d12_backend_\w+\([^;]*;)',r'static \1 \2',public_header.read_text())
    assert count==4,'Backend entry-point interface changed; review fixture linkage'
    paths=[backend,public_header,VENDOR/'libs/video/rsx_d3d12_texture_residency.h',VENDOR/'libs/video/rsx_texture_fingerprint.h',VENDOR/'libs/video/rsx_texture_layout.c',ROOT/'scripts/fixtures/rsx_d3d12_texture_gpu.c',VENDOR/'libs/video/third_party/xxhash/PROVENANCE.json']
    result={'qualification':'Actual production backend function bodies and real DX12 allocation, queue/fence, upload and readback. Four unrelated entry-point declarations become static only for fixture linkage; an unexercised relocation diagnostic boundary aborts visibly. Authored bytes. Production SRV writer tested by actual 2D/cube shader sampling; no whole-game or throughput/FPS proof. Stale-event case signals only an authored blocking gate; the real queue must complete its own target fence.', 'adapter_requested':args.adapter,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'commands':[]}
    env=dict(os.environ)
    for k in list(env):
        if k.startswith(('RSX_','TEX_')):env.pop(k)
    env.update(RSX_TEXTURE_RETENTION='1',RSX_TEXTURE_CACHE_MIB='1',RSX_TEST_ADAPTER=args.adapter)
    def command(cmd,tag,environment=env):
        p=subprocess.run(cmd,cwd=ROOT,env=environment,capture_output=True,text=True,timeout=90)
        result['commands'].append(dict(tag=tag,command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));(out/'result.json').write_text(json.dumps(result,indent=2));return p
    def build(text,tag):
        work=out/tag;work.mkdir();(work/'backend-static.c').write_text(text);(work/'rsx_d3d12_backend.h').write_text(header)
        shutil.copyfile(ROOT/'scripts/fixtures/rsx_d3d12_texture_gpu.c',work/'gpu.c');exe=work/'gpu.exe'
        cmd=[compiler,'/nologo','/TC','/std:c17','/O1','/MDd','/UNDEBUG','/Gy','/Gw','/I'+str(VENDOR/'include'),'/I'+str(ROOT/'runtime'),'/I'+str(VENDOR/'runtime/platform/win32'),'/I'+str(VENDOR/'libs/video'),str(work/'gpu.c'),str(VENDOR/'libs/video/rsx_texture_layout.c'),'/Fo'+str(work)+'/', '/Fe'+str(exe),'/link','/OPT:REF','/INCREMENTAL:NO','dxguid.lib']
        assert command(cmd,tag+'-compile').returncode==0,f'Compilation failed: {out}/result.json'
        result.setdefault('binary_sha256',{})[tag]=hashlib.sha256(exe.read_bytes()).hexdigest();return exe
    exe=build(source,'production')
    for tag,arguments in [('full',[]),('stale-wake',['stale-wake-only']),('descriptor',['descriptor-only'])]:
        p=command([str(exe)]+arguments,tag);assert p.returncode==0,f'{tag}: {out}/result.json';print(p.stdout.strip())
    p=command([str(exe),'growth-only'],'growth',dict(env,RSX_TEXTURE_CACHE_MIB='2'))
    assert p.returncode==0,f'growth: {out}/result.json';print(p.stdout.strip())
    p=command([str(exe),'growth-only'],'reference-growth-red',dict(env,RSX_TEXTURE_RETENTION='0',RSX_TEXTURE_CACHE_MIB='2'))
    assert p.returncode==7 and 'grown==10&&' in p.stderr,f'Expected reference growth failure: {out}/result.json';print('PASS actual reference growth RED')
    for tag,arguments,required in [('reference-red',[],'c==2&&'),('source-reference-red',['source-only'],'v[0]==src[1]'),('cube-reference-red',['cube-only'],'v[0]==src[1]')]:
        p=command([str(exe)]+arguments,tag,dict(env,RSX_TEXTURE_RETENTION='0'))
        assert p.returncode==7 and required in p.stderr,f'Expected reference contract failure: {out}/result.json';print('PASS actual reference RED:',tag)
    if args.historical_backend:
        old=args.historical_backend.read_text();result['historical_sha256']=hashlib.sha256(args.historical_backend.read_bytes()).hexdigest()
        before=function(source,'wait_for_gpu');after=function(old,'wait_for_gpu')
        assert 'static void wait_for_gpu' in after and before!=after,'Historical control must predate completion-recheck fix'
        historical=source.replace(before,after).replace('static int wait_for_gpu(void);','static void wait_for_gpu(void);')
        historical=historical.replace(function(source,'vp_upload_retire'),function(old,'vp_upload_retire'))
        old_exe=build(historical,'historical-wait');p=command([str(old_exe),'stale-wake-only'],'historical-stale-wake-red')
        assert p.returncode==7 and 'retired_ok' in p.stderr,f'Old wait did not fail the stale-wake contract: {out}/result.json';print('PASS actual historical wait RED')
    result['passed']=True;(out/'result.json').write_text(json.dumps(result,indent=2));print(out/'result.json')
if __name__=='__main__':main()
