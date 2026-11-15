"""Game-free checks for read-once renderer/FIFO switches (rsx_env_once.h).

1. Compiles the production header with an authored fixture: unset/set values,
   values fixed at first lookup (later setenv/unsetenv do not change them), a
   private copy, distinct names, table overflow falling back to getenv, and
   concurrent first lookups. Three header mutants must fail.
2. Audits the per-draw, per-bind, per-upload, per-present and per-FIFO-pass
   functions of rsx_d3d12_backend.c and cellGcmSys.c: a raw getenv there must
   sit behind an existing one-time guard. A reintroduced raw read must fail.
No game input; no performance claim."""
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
HEADER = VIDEO / 'rsx_env_once.h'
HOT = {
    'rsx_d3d12_backend.c': ['vp_get_vs', 'compile_vp', 'vp_get_fp_pso', 'vp_upload_tex_slot_impl', 'vp_record_fp_b1',
                            'vp_serve_pso_consts', 'vp_record_cb', 'composite_present', 'guest_fb_present',
                            'render_frame', 'd3d12_clear', 'vp_attrs_dbg', 'upload_quads_vp', 'upload_tris_vp',
                            'upload_quads_vp_indexed', 'd3d12_draw_arrays', 'd3d12_bind_texture', 'subvp_capture',
                            'rsx_capture_frame'],
    'cellGcmSys.c': ['cellGcmResetFlipStatus', 'cellGcmGetFlipStatus', 'nv3089_blit', 'gcm_fifo_dump_around',
                     'gcm_rsx_process_fifo_unlocked', 'cellGcm_fifo_recycle', 'gcm_flip_request'],
}
# One-time guards that already make a raw getenv cheap.
GUARDED = [r'\(const char\*\)\s*-?1\b', r'== -2\)', r'\bvw == 1\b', r'_\w+\+\+ < \d+ && getenv', r'_cinit', r'== 0xFFFFFFFFu',
           r'static[^;]*=\s*-1', r'< 0\)']

FIXTURE = r'''
#define _GNU_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_env_once.h"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static const char* NAMES[8]={"RSXENV_T0","RSXENV_T1","RSXENV_T2","RSXENV_T3","RSXENV_T4","RSXENV_T5","RSXENV_T6","RSXENV_T7"};
static atomic_int first_ready, first_go;
static void* worker(void* arg){
    (void)arg;
    atomic_fetch_add(&first_ready, 1);
    while(!atomic_load(&first_go)) {}
    for(int r=0;r<20000;r++){const char* v=rsx_env_once(NAMES[r&7]);
        if((r&7)%2){if(v)return (void*)1;}else{if(!v||strcmp(v,"on"))return (void*)1;}}
    return NULL;
}
int main(void){
    unsetenv("RSXENV_UNSET");setenv("RSXENV_SET","abc",1);
    CHECK(rsx_env_once("RSXENV_UNSET")==NULL);
    const char* v=rsx_env_once("RSXENV_SET");CHECK(v&&!strcmp(v,"abc"));
    CHECK(v!=getenv("RSXENV_SET"));                         /* a private copy */
    setenv("RSXENV_SET","changed",1);setenv("RSXENV_UNSET","late",1);
    CHECK(!strcmp(rsx_env_once("RSXENV_SET"),"abc"));        /* fixed at first lookup */
    CHECK(rsx_env_once("RSXENV_UNSET")==NULL);
    unsetenv("RSXENV_SET");CHECK(!strcmp(rsx_env_once("RSXENV_SET"),"abc"));
    setenv("RSXENV_OTHER","xyz",1);CHECK(!strcmp(rsx_env_once("RSXENV_OTHER"),"xyz"));  /* distinct name */
    /* Exercise first publication while the cache still has free slots. */
    for(int i=0;i<8;i++)if(i%2==0)setenv(NAMES[i],"on",1);else unsetenv(NAMES[i]);
    pthread_t t[8];for(int i=0;i<8;i++)CHECK(!pthread_create(&t[i],NULL,worker,NULL));
    while(atomic_load(&first_ready)!=8) {}
    atomic_store(&first_go, 1);
    for(int i=0;i<8;i++){void* r;CHECK(!pthread_join(t[i],&r));CHECK(r==NULL);}
    for(int i=0;i<8;i++){
        unsigned matches=0;
        for(unsigned slot=0;slot<RSX_ENV_ONCE_SLOTS;slot++)
            matches += atomic_load(&s_rsx_env_once[slot].key)==NAMES[i];
        CHECK(matches==1);
    }
    /* Table overflow: heap-allocated names are distinct keys; past the table
     * every lookup still answers correctly through getenv. */
    for(unsigned i=0;i<RSX_ENV_ONCE_SLOTS+64;i++){
        char* name=malloc(32);snprintf(name,32,"RSXENV_N%u",i);
        if(i%3==0)setenv(name,"y",1);
        const char* got=rsx_env_once(name);CHECK((i%3==0)?(got&&!strcmp(got,"y")):(got==NULL));
    }
    CHECK(!strcmp(rsx_env_once("RSXENV_OTHER"),"xyz"));       /* earlier entries survive */
    puts("PASS read-once values, private copy, overflow fallback and concurrent first lookups");
    return 0;
}
'''

MUTANTS = {
    'no-copy': ('                    memcpy(copy, v, n);\n                }\n                s->value = copy;',
                '                    memcpy(copy, v, n);\n                }\n                free(copy); copy = (char*)v;\n                s->value = copy;'),
    'key-ignored': ('        if (key != name) continue;\n', ''),
    'rereads-env': ('        if (atomic_load_explicit(&s->state, memory_order_acquire) == 2) return s->value;\n', ''),
}


def function_body(text, name):
    m = re.search(r'^[^\n;]*\b' + re.escape(name) + r'\s*\([^;{]*\)\s*\{', text, re.M)
    if not m:
        return None
    i = m.end(); depth = 1; n = len(text)
    while depth and i < n:            # skip comments and string/char literals
        c = text[i]
        if text.startswith('//', i):
            i = text.find('\n', i); i = n if i < 0 else i
        elif text.startswith('/*', i):
            i = text.find('*/', i + 2) + 2
        elif c in '"\'':
            i += 1
            while i < n and text[i] != c:
                i += 2 if text[i] == '\\' else 1
            i += 1
        else:
            depth += (c == '{') - (c == '}'); i += 1
    return text[m.start():i]


def audit(sources):
    raw = []
    for fn, funcs in HOT.items():
        text = sources[fn]
        for f in funcs:
            body = function_body(text, f)
            if body is None:
                raw.append(f'{fn}:{f}: function not found')
                continue
            lines = body.split('\n')
            for k, line in enumerate(lines):
                if 'getenv(' not in line:
                    continue
                ctx = ' '.join(lines[max(0, k - 2):k + 1])
                if not any(re.search(g, ctx) for g in GUARDED):
                    raw.append(f'{fn}:{f}: {line.strip()[:100]}')
    return raw


def run_fixture(out, label, header):
    d = out / label
    d.mkdir()
    (d / 'rsx_env_once.h').write_text(header)
    (d / 'check.c').write_text(FIXTURE)
    exe = d / 'check'
    cc = os.environ.get('CC') or shutil.which('cc')
    b = subprocess.run([cc, '-std=gnu11', '-O2', '-Wall', '-Werror', '-I' + str(d), '-o', str(exe), str(d / 'check.c'), '-pthread'],
                       capture_output=True, text=True, timeout=120)
    if b.returncode:
        return dict(build=b.returncode, log=(b.stdout + b.stderr)[-1500:])
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    return dict(build=0, returncode=r.returncode, output=(r.stdout + r.stderr).strip())


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-env-once-' + stamp)
    out.mkdir(parents=True)
    sources = {fn: (VIDEO / fn).read_text() for fn in HOT}
    report = dict(game_inputs=False)
    ok = True
    raw = audit(sources)
    report['audit_raw'] = raw
    print('audit: ' + ('no raw hot-path getenv' if not raw else 'RAW ' + '; '.join(raw)))
    ok &= not raw
    bad = sources['rsx_d3d12_backend.c'].replace('float ref = rsx_env_once("NO_ALPHATEST")', 'float ref = getenv("NO_ALPHATEST")', 1)
    assert bad != sources['rsx_d3d12_backend.c']
    caught = bool(audit(dict(sources, **{'rsx_d3d12_backend.c': bad})))
    report['audit_mutant_caught'] = caught
    print('audit mutant reintroduced-raw-read: ' + ('caught' if caught else 'MISSED'))
    ok &= caught
    if os.name == 'nt':
        print('fixture: POSIX threads/setenv fixture runs on Linux/macOS CI')
    else:
        header = HEADER.read_text()
        prod = run_fixture(out, 'production', header)
        report['production'] = prod
        print(prod.get('output') or prod.get('log'))
        ok &= prod.get('build') == 0 and prod.get('returncode') == 0
        report['mutants'] = {}
        for name, (old, new) in MUTANTS.items():
            assert header.count(old) == 1, name
            rec = run_fixture(out, 'mutant-' + name, header.replace(old, new))
            killed = rec.get('build') == 0 and rec.get('returncode') != 0
            report['mutants'][name] = dict(killed=killed, record=rec)
            print(f'mutant {name}: {"killed" if killed else "BUILD FAILED" if rec.get("build") else "SURVIVED"}')
            ok &= killed
    (out / 'result.json').write_text(json.dumps(report, indent=2))
    print('PASS' if ok else 'FAIL', out)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
