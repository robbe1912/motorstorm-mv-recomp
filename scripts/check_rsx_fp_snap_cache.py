"""Game-free checks for fragment-program snapshot identity reuse.

Compiles the production snapshot ring (vp_fp_snap_take/for/entry/bytes) and
the PSO-identity selection from rsx_d3d12_backend.c with the production
rsx_fp_decompiler.c and rsx_fp_snapshot.h, against authored bytecode only.
Checks that a verified snapshot's stored hash and size equal a fresh hash and
extent of its own bytes, that bytes past every slot's program stay zero across
ring reuse, that malformed or racing programs leave the ring untouched, that
the one-walk sized hash agrees with the two separate walks, and that an
unverified snapshot falls back to hashing live memory. Eight compiled mutants
and nine consumer-bound controls must fail.
Windows also compiles the authored HLSL with FXC ps_5_0/O3.
No GPU execution, game input or performance claim."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
BACKEND = VIDEO / 'rsx_d3d12_backend.c'
DECOMPILER = VIDEO / 'rsx_fp_decompiler.c'
RING_BEGIN = '#define VP_FPSNAP_MAX 512'
RING_END = 'static ID3D12PipelineState* vp_get_fp_pso('
PSO_BEGIN = '    const VPFP_snap* snap = vp_fp_snap_entry(snap_idx, off);'
PSO_END = '    s_perf_pso_hashbytes += (int)usize;'

FIXTURE = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ps3emu/ps3types.h"
#include "rsx_fp_decompiler.h"
#include "rsx_fp_snapshot.h"
#define CHECK(c) do{if(!(c)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c);exit(1);}}while(0)
uint8_t* vm_base;
u32 cellGcmResolveLocated(int local, u32 offset){(void)local;return offset;}
@RING@
static int s_perf_pso_hashbytes;
/* The production PSO-identity selection, extracted verbatim. */
static const void* pso_select(u32 snap_idx, u32 off, u32* size_out, u64* hash_out){
@PSO@
    *size_out = usize; *hash_out = uhash; return size_out;
}
static u64 pso_identity(u32 snap_idx, u32 off, u32* size_out){
    u64 h = 0; *size_out = 0;
    return pso_select(snap_idx, off, size_out, &h) ? h : 0;
}
static void word(u8*p,u32 w){w=(w<<16)|(w>>16);p[0]=(u8)(w>>24);p[1]=(u8)(w>>16);p[2]=(u8)(w>>8);p[3]=(u8)w;}
/* Authored program: n instructions, END on the last; every k-th carries an
 * inline CONST slot (k = 0: none). Returns its byte length. */
static u32 program(u8* at,unsigned n,unsigned k,unsigned salt){
    u32 off=0;
    for(unsigned i=0;i<n;i++){
        int c=k&&(i%k==0);
        word(at+off,0x01001E00u|(i+1==n));
        word(at+off+4,(c?2u:1u)|0x1C9DC000u);word(at+off+8,0);word(at+off+12,0);off+=16;
        if(c){for(int j=0;j<16;j++)at[off+j]=(u8)(i*13+j+salt);off+=16;}
    }
    return off;
}
static void tail_zero_everywhere(void){
    for(unsigned i=0;i<VP_FPSNAP_MAX;i++){const VPFP_snap*s=&s_fp_snap[i];
        for(u32 b=s->size;b<sizeof s->bytes;b++)CHECK(s->bytes[b]==0);}
}
static void identity_holds(u32 idx,u32 off){
    const VPFP_snap*s=vp_fp_snap_entry(idx,off);CHECK(s);
    CHECK(s->hash==rsx_fp_structural_hash(s->bytes,VP_FP_UCODE_MAX,0));
    CHECK(s->size==rsx_fp_program_size(s->bytes,VP_FP_UCODE_MAX));
    CHECK(!memcmp(s->bytes,vm_base+off,s->size));
}
void check_fp_program_bound(u32 bound);
int main(void){
    vm_base=calloc(1,2u<<20);CHECK(vm_base);
    check_fp_program_bound(VP_FP_UCODE_MAX);
    /* Real ring and live PSO identity admit programs beyond the old bound. */
    const unsigned long_counts[] = {193, 210, 1024};
    const unsigned long_periods[] = {3, 4, 0};
    for (unsigned p = 0; p < 3; ++p) {
        u32 at = 0x40000u + p * 0x8000u;
        u32 length = program(vm_base + at, long_counts[p], long_periods[p], p);
        CHECK(length > 4096 && length <= VP_FP_UCODE_MAX);
        u32 slot = vp_fp_snap_for(at | 1u);
        CHECK(slot);
        identity_holds(slot, at);
        u32 extent = 0;
        CHECK(pso_identity(0, at, &extent) == s_fp_snap[slot - 1].hash);
        CHECK(extent == length);
    }
    u32 long_off = 0x60000u;
    u32 long_length = program(vm_base + long_off, 210, 4, 7);
    u32 before_edit = vp_fp_snap_for(long_off | 1u);
    CHECK(before_edit);
    CHECK(long_length - 32 > 4096);
    vm_base[long_off + long_length - 32] ^= 0x5a;
    u32 after_edit = vp_fp_snap_for(long_off | 1u);
    CHECK(after_edit && after_edit != before_edit);
    CHECK(s_fp_snap[after_edit - 1].hash == s_fp_snap[before_edit - 1].hash);
    identity_holds(after_edit, long_off);
    u32 old_head = s_fp_snap_head;
    program(vm_base + 0x70000u, 1025, 0, 0);
    CHECK(vp_fp_snap_take(0x70000u) == 0 && s_fp_snap_head == old_head);

    /* One-walk hash and extent agree with the separate walks. */
    for(unsigned n=1;n<=96;n+=5)for(unsigned k=0;k<4;k++){
        u8 buf[VP_FP_UCODE_MAX]={0};u32 len=program(buf,n,k,n);
        for(u32 cap=len>64?len-64:0;cap<=VP_FP_UCODE_MAX;cap+=(cap<len+64?16:997)){
            u32 sz=77;u64 h=rsx_fp_structural_hash_sized(buf,cap,0,&sz);
            CHECK(h==rsx_fp_structural_hash(buf,cap,0));
            CHECK(h?sz==rsx_fp_program_size(buf,cap)&&sz==len:sz==0);
        }
    }
    { u32 sz=5;CHECK(!rsx_fp_structural_hash_sized(NULL,VP_FP_UCODE_MAX,0,&sz)&&sz==0); }
    /* Fresh snapshots: stored identity equals the bytes'. */
    u32 first=0;
    for(unsigned p=0;p<40;p++){
        u32 off=0x1000u*(p+1);u32 len=program(vm_base+off,1+p*3%90,p%4,p);
        u32 idx=vp_fp_snap_for(off|1u);CHECK(idx);identity_holds(idx,off);CHECK(s_fp_snap[idx-1].size==len);
        if(!p)first=idx;
    }
    tail_zero_everywhere();
    /* In-place constant edit: refreshed snapshot, same identity, new bytes. */
    u32 off=0x1000u;u32 len=program(vm_base+off,1,0,0);(void)len;
    off=0x30000u;len=program(vm_base+off,12,2,9);
    u32 a=vp_fp_snap_for(off|1u);CHECK(a);identity_holds(a,off);
    vm_base[off+16]^=0x5A;                                   /* first inline constant */
    u32 b=vp_fp_snap_for(off|1u);CHECK(b&&b!=a);identity_holds(b,off);
    CHECK(s_fp_snap[b-1].hash==s_fp_snap[a-1].hash);
    /* Structural rewrite at the same address keeps the bound program. */
    u8 keep[VP_FP_UCODE_MAX];memcpy(keep,s_fp_snap[b-1].bytes,sizeof keep);
    vm_base[off+2]^=0x10;
    CHECK(vp_fp_snap_for(off|1u)==b&&!memcmp(keep,s_fp_snap[b-1].bytes,sizeof keep));
    vm_base[off+2]^=0x10;
    /* Malformed programs (no END; a CONST slot past the window) take no slot. */
    u32 head=s_fp_snap_head;
    u32 bad=0x100000u;for(u32 i=0;i<VP_FP_UCODE_MAX;i+=16)word(vm_base+bad+i,0x01001E00u);
    CHECK(vp_fp_snap_take(bad)==0&&s_fp_snap_head==head);
    u32 edge=0x110000u;memset(vm_base+edge,0,VP_FP_UCODE_MAX);
    for(u32 i=0;i<VP_FP_UCODE_MAX-16;i+=16){word(vm_base+edge+i,0x01001E00u);word(vm_base+edge+i+4,0x1C9DC001u);}
    word(vm_base+edge+VP_FP_UCODE_MAX-16,0x01001E01u);word(vm_base+edge+VP_FP_UCODE_MAX-12,0x1C9DC002u);
    CHECK(vp_fp_snap_take(edge)==0&&s_fp_snap_head==head);
    /* Ring reuse: long, then short programs in the same slots; tails stay zero. */
    for(unsigned round=0;round<3;round++)for(unsigned p=0;p<VP_FPSNAP_MAX;p++){
        u32 o=0xA0000u+0x1000u*(p%96);
        program(vm_base+o,round==0?100:round==1?1+(p%7):20+(p%50),round==1?0:3,p+round);
        u32 idx=vp_fp_snap_take(o);CHECK(idx);identity_holds(idx,o);
    }
    tail_zero_everywhere();
    /* PSO identity: a verified snapshot's stored values; otherwise live bytes. */
    off=0xA0000u;u32 idx=vp_fp_snap_for(off|1u);CHECK(idx);
    u32 sz=0;u64 h=pso_identity(idx,off,&sz);
    CHECK(h==s_fp_snap[idx-1].hash&&sz==s_fp_snap[idx-1].size);
    u32 other=0xA0000u+0x1000u*3;
    CHECK(rsx_fp_structural_hash(vm_base+other,VP_FP_UCODE_MAX,0)!=s_fp_snap[idx-1].hash);  /* distinct programs */
    h=pso_identity(idx,other,&sz);                          /* recycled: off mismatch */
    CHECK(h==rsx_fp_structural_hash(vm_base+other,VP_FP_UCODE_MAX,0)&&sz==rsx_fp_program_size(vm_base+other,VP_FP_UCODE_MAX));
    h=pso_identity(0,other,&sz);
    CHECK(h==rsx_fp_structural_hash(vm_base+other,VP_FP_UCODE_MAX,0));
    (void)first;
    puts("PASS one-walk hash/extent, stored snapshot identity, constant refresh, structural keep, malformed no-slot, tail-zero ring reuse, PSO identity selection");
    return 0;
}
'''

MUTANTS = {
    'old-program-bound': ('backend', '#define VP_FP_UCODE_MAX 16384u', '#define VP_FP_UCODE_MAX 4096u'),
    'short-snapshot-bound': ('backend', 'rsx_fp_program_size(src, VP_FP_UCODE_MAX)', 'rsx_fp_program_size(src, 4096)'),
    'short-live-bound': ('backend', 'rsx_fp_structural_hash_sized(uc, VP_FP_UCODE_MAX, 0, &usize)', 'rsx_fp_structural_hash_sized(uc, 4096, 0, &usize)'),
    'short-refresh-bound': ('backend', 'rsx_fp_snapshot_check(win, s->bytes, s->size, VP_FP_UCODE_MAX, s->hash)', 'rsx_fp_snapshot_check(win, s->bytes, s->size, 4096, s->hash)'),
    'stale-tail': ('backend', '    if (previous > size) memset(s->bytes + size, 0, previous - size);\n', '    (void)previous;\n'),
    'sized-extent-off': ('decompiler', '            if (out_size)\n                *out_size = off;',
                         '            if (out_size)\n                *out_size = off - 16;'),
    'unverified-entry': ('backend', '    if (snap && snap <= VP_FPSNAP_MAX && s_fp_snap[snap - 1].off == off\n        && s_fp_snap[snap - 1].hash)\n        return &s_fp_snap[snap - 1];',
                         '    if (snap && snap <= VP_FPSNAP_MAX && s_fp_snap[snap - 1].hash)\n        return &s_fp_snap[snap - 1];'),
    'hash-live-not-copy': ('backend', '    u64 h = rsx_fp_structural_hash_sized(copy, size, 0, &copied);',
                           '    u64 h = rsx_fp_structural_hash_sized(copy, size, 0, &copied); h ^= 1;'),
}


# The executable checks parser behavior. These controls bind that behavior to
# every actual D3D12 call site, including consumers outside the extracted ring.
CONSUMERS = {
    'snapshot extent': ('backend', 'rsx_fp_program_size(src, VP_FP_UCODE_MAX)'),
    'snapshot comparison': ('backend', 'rsx_fp_snapshot_check(win, s->bytes, s->size, VP_FP_UCODE_MAX, s->hash)'),
    'live identity': ('backend', 'rsx_fp_structural_hash_sized(uc, VP_FP_UCODE_MAX, 0, &usize)'),
    'canonical prefetch': ('backend', 'rsx_fp_canonical_program(uc,VP_FP_UCODE_MAX,program,sizeof(program))'),
    'native depth decompile': ('backend', 'rsx_fp_decompile_buffered_native_depth(uc, VP_FP_UCODE_MAX, fp_ctrl, cube_mask, dr->depth_view,'),
    'decompile': ('backend', 'rsx_fp_decompile_buffered_ex(uc, VP_FP_UCODE_MAX, fp_ctrl, cube_mask,'),
    'FP_PICK': ('backend', 'rsx_fp_program_size(vm_base + off, VP_FP_UCODE_MAX)'),
    'b1 constants': ('backend', 'rsx_fp_collect_constants(uc, VP_FP_UCODE_MAX, &blk)'),
    'native depth texture mask': ('native_depth', 'rsx_fp_texture_units(uc ? uc : vm_base + off, VP_FP_UCODE_MAX)'),
}


def audit_consumers(sources):
    for name, (where, signature) in CONSUMERS.items():
        assert sources[where].count(signature) == 1, name


def extract(backend):
    ring = backend[backend.index(RING_BEGIN):backend.index(RING_END)]
    a = backend.index(PSO_BEGIN)
    pso = backend[a:backend.index(PSO_END, a) + len(PSO_END)]
    pso = pso.replace('vm_base + off', 'vm_base + off')
    return ring, pso


def run(out, label, backend, decompiler):
    d = out / label
    d.mkdir()
    ring, pso = extract(backend)
    (d / 'check.c').write_text(FIXTURE.replace('@RING@', ring).replace('@PSO@', pso), encoding='utf-8')
    (d / 'rsx_fp_decompiler.c').write_text(decompiler, encoding='utf-8')
    bound_fixture = d / 'fp_program_bound.c'
    bound_fixture.write_bytes((ROOT / 'scripts/fixtures/rsx_fp_program_bound.c.in').read_bytes())
    exe = d / ('check.exe' if os.name == 'nt' else 'check')
    inc = [d, VIDEO, ROOT / 'vendor/ps3recomp/include']
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS', '/O2', *('/I' + str(p) for p in inc),
               str(d / 'check.c'), str(d / 'rsx_fp_decompiler.c'), str(bound_fixture), '/Fe' + str(exe), '/Fo' + str(d) + os.sep, '/link', 'd3dcompiler.lib']
    else:
        # The fixture builds with -Werror; the production decompiler keeps its
        # own (warning-tolerant) settings and is linked as an object.
        cc = env.get('CC') or shutil.which('cc')
        obj = d / 'rsx_fp_decompiler.o'
        pre = subprocess.run([cc, '-std=gnu11', '-O2', '-UNDEBUG', *('-I' + str(p) for p in inc), '-c',
                              str(d / 'rsx_fp_decompiler.c'), '-o', str(obj)], env=env, capture_output=True,
                             text=True, timeout=180)
        if pre.returncode:
            return dict(build=pre.returncode, log=(pre.stdout + pre.stderr)[-2500:])
        cmd = [cc, '-std=gnu11', '-O2', '-UNDEBUG', '-Wall', '-Werror', '-Wno-unused-function',
               *('-I' + str(p) for p in inc), '-o', str(exe), str(d / 'check.c'), str(bound_fixture), str(obj), '-lm']
    b = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180)
    if b.returncode:
        return dict(build=b.returncode, log=(b.stdout + b.stderr)[-2500:])
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    return dict(build=0, returncode=r.returncode, output=(r.stdout + r.stderr).strip())


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-fp-snap-cache-' + stamp)
    out.mkdir(parents=True)
    backend, decompiler = BACKEND.read_text(encoding='utf-8'), DECOMPILER.read_text(encoding='utf-8')
    native_depth = (VIDEO / 'rsx_d3d12_native_depth.inc').read_text(encoding='utf-8')
    sources = dict(backend=backend, native_depth=native_depth)
    audit_consumers(sources)
    report = dict(game_inputs=False, mutants={}, consumer_controls=[])
    for name, (where, signature) in CONSUMERS.items():
        changed = dict(sources)
        changed[where] = sources[where].replace(signature, signature.replace('VP_FP_UCODE_MAX', '4096'))
        try:
            audit_consumers(changed)
        except AssertionError as error:
            assert str(error) == name
        else:
            raise AssertionError('Old 4 KiB consumer survived: ' + name)
        report['consumer_controls'].append(name)
    print('PASS nine consumer-bound omission controls')
    prod = run(out, 'production', backend, decompiler)
    report['production'] = prod
    print(prod.get('output') or prod.get('log'))
    ok = prod.get('build') == 0 and prod.get('returncode') == 0
    for name, (where, old, new) in MUTANTS.items():
        src = backend if where == 'backend' else decompiler
        assert src.count(old) == 1, name
        mutated = src.replace(old, new)
        rec = run(out, 'mutant-' + name, mutated if where == 'backend' else backend,
                  mutated if where == 'decompiler' else decompiler)
        killed = rec.get('build') == 0 and rec.get('returncode') != 0
        report['mutants'][name] = dict(killed=killed, record=rec)
        print(f'mutant {name}: {"killed" if killed else "BUILD FAILED" if rec.get("build") else "SURVIVED"}')
        ok &= killed
    (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS' if ok else 'FAIL', out)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
