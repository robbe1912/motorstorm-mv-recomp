"""Independent binary32 oracle for #302's recovered GetDepth sampling plan."""
from pathlib import Path
import hashlib,json,os,random,shutil,struct,subprocess,time

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'temp/checks'/f'deformation-depth-plan-{time.time_ns()}'
OUT.mkdir(parents=True); commands=[]
def f32(value): return struct.unpack('<f',struct.pack('<f',value))[0]
def bits(value): return struct.unpack('<I',struct.pack('<f',value))[0]
def valid(bits_): return bits_ <= 0x3f800000 or bits_ == 0x80000000
def oracle(x_bits,y_bits,width,height,bpp):
    if not valid(x_bits) or not valid(y_bits) or not width or not height or not bpp or width>0x7fffffff or height>0x7fffffff:
        return (1,(0,0,0,0),0,0)
    limit=(1<<64)-1
    if width>limit//bpp or height>=limit//(width*bpp) or width*bpp>limit-bpp:
        return (1,(0,0,0,0),0,0)
    x=f32(struct.unpack('<f',struct.pack('<I',x_bits))[0]*f32(float(width)))
    y=f32(f32(1.0-struct.unpack('<f',struct.pack('<I',y_bits))[0])*f32(float(height)))
    ix=min(int(x),width-1); iy=min(int(y),height-1); row=width*bpp; base=iy*row+ix*bpp
    return (0,(base,base+bpp,base+row,base+row+bpp),bits(f32(x-f32(float(ix)))),bits(f32(y-f32(float(iy)))))
cases=[]
for width,height,bpp in ((1,1,1),(1,9,4),(9,1,4),(7,11,1),(257,127,4)):
    for x in (0,0x80000000,0x3eaaaaab,0x3f7fffff,0x3f800000):
        for y in (0,0x80000000,0x3f000000,0x3f7fffff,0x3f800000): cases.append((x,y,width,height,bpp))
rng=random.Random(302)
for _ in range(900): cases.append((rng.randrange(0x3f800001),rng.randrange(0x3f800001),rng.randrange(1,2048),rng.randrange(1,2048),rng.choice((1,2,4))))
for bad in (0x7fc00001,0x7f800000,0xbf000000,0x3f800001): cases.append((bad,0,4,4,1)); cases.append((0,bad,4,4,1))
cases += [(0,0,0,4,1),(0,0,4,0,1),(0,0,4,4,0),(0,0,0x80000000,1,1),(0,0,0x7fffffff,0x7fffffff,4)]
input_data=struct.pack('<I',len(cases))+b''.join(struct.pack('<IIIII',*case) for case in cases)
expected=b''.join(struct.pack('<IQQQQII',status,*offsets,xf,yf) for status,offsets,xf,yf in map(lambda c:oracle(*c),cases))
(OUT/'input.bin').write_bytes(input_data); (OUT/'expected.bin').write_bytes(expected)
if os.name=='nt':
    from project import build_environment; os.environ.update(build_environment())
cxx=os.environ.get('CXX') or shutil.which('clang-cl' if os.name=='nt' else 'c++'); assert cxx
source=ROOT/'src/motorstorm/deformation_depth.cpp'; fixture=ROOT/'scripts/fixtures/deformation_depth_plan.cpp'
def build(path,name):
    exe=OUT/(name+('.exe' if os.name=='nt' else ''))
    args=[cxx,'/nologo','/std:c++20','/O2','/MDd','/EHsc','/UNDEBUG','/fp:strict','/clang:-ffp-contract=off','/I'+str(source.parent),str(path),str(fixture),'/Fe:'+str(exe)] if os.name=='nt' else [cxx,'-std=c++20','-O2','-frounding-math','-ffp-contract=off','-I'+str(source.parent),str(path),str(fixture),'-o',str(exe)]
    p=subprocess.run([str(v) for v in args],cwd=OUT,capture_output=True,text=True,timeout=120); commands.append(dict(command=[str(v) for v in args],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)); assert not p.returncode; return exe
def check(path,name,expect_match):
    exe=build(path,name)
    for setting in range(16):
        output=OUT/(f'{name}-{setting}.bin'); p=subprocess.run([str(exe),str(OUT/'input.bin'),str(output),str(setting)],cwd=OUT,capture_output=True,text=True,timeout=120); commands.append(dict(command=[str(exe),'input.bin',str(output),str(setting)],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        if not expect_match and p.returncode: continue
        assert not p.returncode; assert (output.read_bytes()==expected)==expect_match
check(source,'plan',True)
mutants={'lost-v-inversion':('single(1.0) - normalized_y','normalized_y'),'wrong-x-clamp':('clamped_index(x_product, width)','clamped_index(x_product, width - 1)'),'aliased-right-neighbor':'top_left + bytes_per_pixel, top_left + row_bytes','lost-caller-csr':('_mm_setcsr(csr_);','_mm_setcsr(0x1f80u);')}
for name,change in mutants.items():
    text=source.read_text()
    if isinstance(change,tuple): old,new=change
    else: old,new=change,'top_left, top_left + row_bytes'
    assert old in text; path=OUT/(name+'.cpp'); path.write_text(text.replace(old,new)); check(path,name,False)
report=dict(cases=len(cases),caller_fp_modes=16,mutants=list(mutants),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),commands=commands,qualification=__doc__)
(OUT/'result.json').write_text(json.dumps(report,indent=2)); print(f'PASS recovered depth plan: {len(cases)} cases x16 FP modes, {len(mutants)} real-source mutants; {OUT}')
