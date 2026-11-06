"""Authored exact-rational oracle for the native depth interpolation kernel.

This does not prove GPU snapshot ownership, original query ABI or frame rate.
"""
from fractions import Fraction
from pathlib import Path
import hashlib,json,os,random,shutil,struct,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'temp/checks'/f'deformation-depth-{time.time_ns()}'
OUT.mkdir(parents=True)
commands=[]

def run(args,expect=0):
    p=subprocess.run([str(x) for x in args],cwd=OUT,capture_output=True,text=True,timeout=120)
    commands.append(dict(command=[str(x) for x in args],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
    (OUT/'result.json').write_text(json.dumps(dict(commands=commands),indent=2))
    assert p.returncode==expect, f'Command failed; inspect {OUT}/result.json'

def value(bits):
    sign=-1 if bits>>31 else 1
    exponent=(bits>>23)&255;mantissa=bits&0x7fffff
    assert exponent!=255
    return sign*Fraction(mantissa+(0x800000 if exponent else 0))*Fraction(2)**((exponent or 1)-150)

def rounded(x,precision=24,minimum=-126):
    if not x:return Fraction(0)
    sign=-1 if x<0 else 1;x=abs(x)
    exponent=x.numerator.bit_length()-x.denominator.bit_length()
    if x<Fraction(2)**exponent:exponent-=1
    unit=Fraction(2)**(max(exponent,minimum)-precision+1)
    ratio=x/unit;q,r=divmod(ratio.numerator,ratio.denominator)
    if 2*r>ratio.denominator or (2*r==ratio.denominator and q&1):q+=1
    return sign*q*unit

def oracle(samples,x,y,mode):
    scale=value(0x3b808081);a,b,c,d=[rounded(n*scale) for n in samples]
    if not mode:return a
    x,y=value(x),value(y);inverse_x=rounded(1-x);inverse_y=rounded(1-y)
    multiply=lambda u,v:rounded(u*v)
    fused=lambda u,v,w:rounded(rounded(u*v+w,53,-1022))
    right_top=multiply(x,b);right_bottom=multiply(x,d)
    top=fused(multiply(a,inverse_x),inverse_y,multiply(inverse_y,right_top))
    return fused(y,right_bottom,fused(y,multiply(c,inverse_x),top))

cases=[]
def add(samples,x,y,mode=1,valid=True):cases.append((samples,x,y,mode,valid))
for n in range(256):
    for mode in (0,1):add([n]*4,0x3eaaaaab,0x3f234567,mode)
for x in (0,0x80000000,1,0x7fffff,0x800000,0x3f000000,0x3f7fffff,0x3f800000):
    for y in (0,1,0x80000000,0x3eaaaaab,0x3f800000):add([0,255,127,253],x,y)
rng=random.Random(302)
for _ in range(750):add([rng.randrange(256) for _ in range(4)],rng.randrange(0x3f800001),rng.randrange(0x3f800001))
for bits in (0x7fc00001,0x7f800001,0x7f800000,0xff800000,0xbf000000,0x80000001,0x3f800001):
    add([1,2,3,4],bits,0,valid=False);add([1,2,3,4],0,bits,valid=False)
add([1,2,3,4],0,0,99,False)
inputs=struct.pack('<I',len(cases))+b''.join(bytes(a)+struct.pack('<III',x,y,m) for a,x,y,m,_ in cases)
(OUT/'input.bin').write_bytes(inputs)
expected=b''.join(struct.pack('<II',0,struct.unpack('<I',struct.pack('<f',float(oracle(a,x,y,m))))[0]) if valid else struct.pack('<II',1,0xcdcdcdcd) for a,x,y,m,valid in cases)
(OUT/'expected.bin').write_bytes(expected)
if os.name=='nt':
    from project import build_environment
    os.environ.update(build_environment())
cxx=os.environ.get('CXX') or shutil.which('clang-cl' if os.name=='nt' else 'c++')
assert cxx,'No C++ compiler'
source=ROOT/'src/motorstorm/deformation_depth.cpp';fixture=ROOT/'scripts/fixtures/deformation_depth.cpp'

def build(path,name):
    exe=OUT/(name+('.exe' if os.name=='nt' else ''))
    if os.name=='nt':args=[cxx,'/nologo','/std:c++20','/O2','/MDd','/EHsc','/UNDEBUG','/fp:strict','/clang:-ffp-contract=off','/clang:-fno-strict-aliasing','/I'+str(source.parent),str(path),str(fixture),'/Fe:'+str(exe)]
    else:args=[cxx,'-std=c++20','-O2','-UNDEBUG','-frounding-math','-ffp-contract=off','-fno-strict-aliasing','-I'+str(source.parent),str(path),str(fixture),'-o',str(exe),'-lm']
    run(args);return exe

exe=build(source,'depth')
for setting in range(16):
    output=OUT/f'output-{setting}.bin';run([exe,OUT/'input.bin',output,setting]);assert output.read_bytes()==expected,f'Oracle/FP mismatch at setting{setting}'
mutants={
 'lost-single-rounds':('return static_cast<float>(value);','return value;'),
 'wrong-corner':('multiply(patch.samples[2], scale)','multiply(patch.samples[3], scale)'),
 'ignored-filter':('if (mode == DepthSampleMode::point)','if (true)'),
 'lost-caller-csr':('_mm_setcsr(csr_);','_mm_setcsr(0x1f80u);'),
}
for name,(old,new) in mutants.items():
    text=source.read_text();assert old in text;path=OUT/(name+'.cpp');path.write_text(text.replace(old,new));bad=build(path,name);output=OUT/(name+'.bin')
    p=subprocess.run([str(bad),str(OUT/'input.bin'),str(output),'15'],cwd=OUT,capture_output=True,text=True,timeout=120)
    commands.append(dict(command=[str(bad),'input.bin',str(output),'15'],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
    assert p.returncode!=0 or output.read_bytes()!=expected,f'Mutant accepted:{name}'
report=dict(cases=len(cases),caller_fp_modes=16,mutants=list(mutants),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),commands=commands,qualification=__doc__)
(OUT/'result.json').write_text(json.dumps(report,indent=2));print(f'PASS depth exact oracle: {len(cases)} cases x16 FP modes, four real-source mutants; {OUT}')
