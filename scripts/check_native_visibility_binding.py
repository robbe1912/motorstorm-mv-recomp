"""Exercise the real SPU binder/compiler with authored C inputs only."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from native_game_binding import Contract, digest, prepare
from check_native_game_binding import rejects

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/'build/self-tests/native-visibility-binding'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as temporary:
        base = Path(temporary)
        source = base/'input'
        (source/'ppu').mkdir(parents=True)
        (source/'ppu/ppu_recomp.h').write_text('// Authored unused PPU header\n')
        ppu_body = b'void unused_entry(ppu_context* ctx) { (void)ctx; }'
        (source/'ppu/unused.cpp').write_bytes(ppu_body)
        module = source/'spu/authored'
        module.mkdir(parents=True)
        (module/'spu_recomp.h').write_text('''#ifndef AUTHORED_SPU_H
#define AUTHORED_SPU_H
typedef struct { int value; unsigned char ls_store[512]; unsigned char* ls; } spu_context;
void authored_entry(spu_context*);
#endif
''')
        body = b'void authored_entry(spu_context* ctx) { /* } */ ++ctx->value; }'
        code = (b'#include "spu_recomp.h"\n' + body +
                b'\nvoid direct(spu_context* ctx) { authored_entry(ctx); }\n'
                b'void (*table_entry)(spu_context*) = &authored_entry;\n')
        tu = module/'spu_recomp.c'
        tu.write_bytes(code)
        elf = base/'authored-input'
        elf.write_bytes(bytes(range(256))*2)
        contract = Contract(digest(elf), hashlib.sha256(body).hexdigest(),
            'authored_entry', 'retained_entry', 'native_entry',
            context='spu_context', directory='spu/authored', matcher='code_matches',
            windows=((32, 16, 4), (120, 96, 3)))
        other = Contract(digest(elf), hashlib.sha256(ppu_body).hexdigest(),
            'unused_entry', 'retained_unused', 'native_unused')
        output, manifest = base/'copy', base/'binding.json'
        known = (contract, other)
        def bind(selected=(contract,)):
            return prepare(source, output, elf, manifest, contracts=selected, known_contracts=known)
        result = bind()
        copied = Path(result['copied_tu'])
        changed = copied.read_bytes()
        assert result['bindings'][0]['context'] == 'spu_context'
        assert tu.read_bytes() == code
        assert b'void direct(spu_context* ctx) { authored_entry(ctx); }' in changed
        assert b'void (*table_entry)(spu_context*) = &authored_entry;' in changed
        harness = base/'harness.c'
        harness.write_text('''#include "spu_recomp.h"
#include <string.h>
void direct(spu_context*);
extern void (*table_entry)(spu_context*);
void retained_entry(spu_context*);
int code_matches(const spu_context*);
static int reference;
void native_entry(spu_context* ctx) { if(reference) retained_entry(ctx); else ctx->value+=7; }
int main(void) {
    spu_context ctx = {0}; ctx.ls=ctx.ls_store;
    const unsigned char code[]={32,33,34,35}, table[]={120,121,122};
    memcpy(ctx.ls+16,code,sizeof(code)); memcpy(ctx.ls+96,table,sizeof(table));
    direct(&ctx); if(ctx.value!=7)return 1;
    table_entry(&ctx); if(ctx.value!=14)return 2;
    reference=1; direct(&ctx); if(ctx.value!=15)return 3;
    retained_entry(&ctx); if(ctx.value!=16)return 4;
    if(!code_matches(&ctx))return 5;
    ctx.ls[17]^=1; if(code_matches(&ctx))return 6; ctx.ls[17]^=1;
    ctx.ls[97]^=1; if(code_matches(&ctx))return 7; ctx.ls[97]^=1;
    ctx.ls[0]^=1; if(!code_matches(&ctx))return 8;
    ctx.ls=0; if(code_matches(&ctx)||code_matches(0))return 9;
    return 0;
}
''')
        compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name=='nt' else 'cc')
        assert compiler, 'Set MV_CLANG/CXX for the authored C binding test'
        def run(name, data, expected):
            test_source = base/(name+'.c')
            test_source.write_bytes(data)
            exe = base/(name+('.exe' if os.name=='nt' else ''))
            command = [compiler, str(test_source), str(harness)]
            command += (['/nologo','/TC','/std:c17','/O2','/UNDEBUG','/I'+str(output/'spu/authored'),
                '/Fo'+str(base)+os.sep, '/Fe'+str(exe)] if os.name=='nt' else
                ['-x','c','-std=c11','-O2','-UNDEBUG','-I'+str(output/'spu/authored'),'-o',str(exe)])
            built = subprocess.run(command,cwd=base,capture_output=True,text=True)
            (out/(name+'-build.log')).write_text(built.stdout+built.stderr)
            assert built.returncode == 0, built.stdout+built.stderr
            assert subprocess.run([str(exe)]).returncode == expected, name
        run('production', changed, 0)
        forward = b'{ native_entry(ctx); }'
        assert changed.count(forward) == 1
        run('wrong-forward', changed.replace(forward,b'{ retained_entry(ctx); }'), 1)
        table_check = b'memcmp(ctx->ls + 96u, window_1, sizeof(window_1)) == 0'
        assert changed.count(table_check) == 1
        run('missing-table-guard', changed.replace(table_check,b'1'), 7)
        stamp = copied.stat().st_mtime_ns
        bind()
        assert copied.stat().st_mtime_ns == stamp
        bind((other,))
        assert copied.read_bytes() == code  # reference restoration
        bind()
        assert copied.read_bytes() == changed
        assert (output/'ppu/unused.cpp').read_bytes() == ppu_body
        copied.write_bytes(changed+b'\n// unverified edit\n')
        rejects(bind, 'changed or stale')
        copied.write_bytes(changed)
        for bad, message in (
            (replace(contract, windows=((510,16,4),)), 'Truncated original ELF'),
            (replace(contract, windows=((32,0x3ffff,4),)), 'window bounds'),
            (replace(contract, windows=()), 'verified code/data windows'),
            (replace(contract, directory='../spu/authored'), 'inside generated'),
        ):
            rejects(lambda: prepare(source, base/'bad-copy', elf, manifest, bad), message)
            assert not (base/'bad-copy').exists()
        assert tu.read_bytes() == code
    print('PASS SPU binding: actual C direct/table/reference calls, code+data guards, stable/reversible copy; forwarding/guard mutants rejected')


if __name__ == '__main__':
    main()
