"""Authored binding fixtures; never load original game inputs in CI."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
from native_game_binding import Contract, definition, digest, prepare, transform

ROOT = Path(__file__).resolve().parents[1]


def rejects(action, text):
    try:
        action()
    except ValueError as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError('Expected rejection: '+text)


def main():
    out = ROOT/'build/self-tests/native-game-binding'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as temporary:
        base = Path(temporary)
        source = base/'input'
        (source/'ppu').mkdir(parents=True)
        (source/'ppu/ppu_recomp.h').write_text('// Authored context and declaration fixture\nstruct ppu_context { int value; };\nvoid func_006BEAE0(ppu_context*);\n')
        # Braces inside comments/strings must not terminate the reference body.
        body = b'void func_006BEAE0(ppu_context* ctx) { /* } */ if(ctx) { const char* s="}"; ++ctx->value; } }'
        code = b'#include "ppu_recomp.h"\n'+body+b'\nvoid direct(ppu_context* ctx) { func_006BEAE0(ctx); }\nauto table_entry = &func_006BEAE0;\n'
        tu = source/'ppu/authored.cpp'
        tu.write_bytes(code)
        (source/'ppu/other.cpp').write_text('// Unrelated source\n')
        elf = base/'authored-input'
        elf.write_bytes(b'Authored identity fixture; not a game executable')
        contract = Contract(digest(elf), hashlib.sha256(body).hexdigest())
        output, manifest = base/'copy', base/'binding.json'
        result = prepare(source, output, elf, manifest, contract)
        changed = Path(result['copied_tu']).read_bytes()
        assert tu.read_bytes() == code
        assert (output/'ppu/other.cpp').read_bytes() == (source/'ppu/other.cpp').read_bytes()
        assert b'void game_original_scene_list_evaluate(ppu_context* ctx)' in changed
        assert b'void direct(ppu_context* ctx) { func_006BEAE0(ctx); }' in changed
        assert b'auto table_entry = &func_006BEAE0;' in changed
        assert b'void func_006BEAE0(ppu_context* ctx) { motorstorm_scene_evaluate(ctx); }' in changed
        harness = base/'caller.cpp'
        harness.write_text('#include "ppu_recomp.h"\nvoid direct(ppu_context*);\nextern void (*table_entry)(ppu_context*);\nvoid game_original_scene_list_evaluate(ppu_context*);\nvoid motorstorm_scene_evaluate(ppu_context* ctx) { ctx->value=20; }\nint main() {\n ppu_context ctx{0};direct(&ctx);if(ctx.value!=20)return 1;\n ctx.value=0;table_entry(&ctx);if(ctx.value!=20)return 2;\n game_original_scene_list_evaluate(&ctx);return ctx.value==21?0:3;\n}\n')
        compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name=='nt' else 'c++')
        assert compiler, 'Set MV_CLANG/CXX for the native caller fixture'
        exe = base/('caller.exe' if os.name=='nt' else 'caller')
        command = [compiler, str(output/'ppu/authored.cpp'),str(harness)]
        command += ['/nologo','/std:c++17','/O2','/UNDEBUG','/I'+str(output/'ppu'),'/Fo'+str(base)+os.sep,'/Fe'+str(exe)] if os.name=='nt' else ['-std=c++17','-O2','-UNDEBUG','-I'+str(output/'ppu'),'-o',str(exe)]
        built = subprocess.run(command,cwd=base,capture_output=True,text=True)
        (out/'caller-build.log').write_text(built.stdout+built.stderr)
        assert built.returncode==0, built.stdout+built.stderr
        ran = subprocess.run([str(exe)],capture_output=True,text=True)
        assert ran.returncode==0, 'Direct/table/reference caller fixture failed: '+str(ran.returncode)
        mutant = base/'bad-caller.cpp'
        forward = b'{ motorstorm_scene_evaluate(ctx); }'
        assert changed.count(forward)==1
        mutant.write_bytes(changed.replace(forward,b'{ game_original_scene_list_evaluate(ctx); }'))
        bad_exe = base/('bad-caller.exe' if os.name=='nt' else 'bad-caller')
        bad_command = list(command)
        bad_command[1] = str(mutant)
        if os.name=='nt':
            bad_command[-1] = '/Fe'+str(bad_exe)
        else:
            bad_command[-1] = str(bad_exe)
        built = subprocess.run(bad_command,cwd=base,capture_output=True,text=True)
        (out/'caller-mutant-build.log').write_text(built.stdout+built.stderr)
        assert built.returncode==0, built.stdout+built.stderr
        assert subprocess.run([str(bad_exe)]).returncode==1, 'Wrong direct-call binding must fail the independent caller oracle'
        stamp = Path(result['copied_tu']).stat().st_mtime_ns
        prepare(source, output, elf, manifest, contract)
        assert Path(result['copied_tu']).stat().st_mtime_ns == stamp
        rejects(lambda: transform(code.replace(b'if(ctx)', b'if(!ctx)'), contract), 'body identity')
        rejects(lambda: transform(code+body, contract), 'one definition')
        rejects(lambda: definition(b'void func_006BEAE0(ppu_context* ctx) {', contract.symbol), 'Unterminated')
        rejects(lambda: prepare(source, source/'bad', elf, manifest, contract), 'separate')
        wrong = base/'wrong-input'
        wrong.write_text('wrong identity')
        rejects(lambda: prepare(source, base/'wrong-copy', wrong, manifest, contract), 'ELF identity')
        assert not (base/'wrong-copy').exists()
        (output/'ppu/other.cpp').write_text('Changed private copy')
        rejects(lambda: prepare(source, output, elf, manifest, contract), 'changed or stale')
        (output/'ppu/other.cpp').write_bytes((source/'ppu/other.cpp').read_bytes())
        # A junction inside an existing copy must never redirect a write into inputs.
        redirected = base/'redirected'
        redirected.mkdir()
        link = redirected/'ppu'
        if os.name == 'nt':
            from _winapi import CreateJunction
            CreateJunction(str(source/'ppu'), str(link))
        else:
            link.symlink_to(source/'ppu', target_is_directory=True)
        try:
            rejects(lambda: prepare(source, redirected, elf, manifest, contract), 'reparse point')
            assert tu.read_bytes() == code
        finally:
            if link.is_symlink():
                link.unlink()
            else:
                link.rmdir()
        # Independent bindings may be enabled/disabled without stale native
        # entries or rebuilding an unrelated copied TU.
        second_body=b'void func_00111110(ppu_context* ctx) { ctx->value+=2; }'
        second=Contract(contract.elf_sha256,hashlib.sha256(second_body).hexdigest(),
                        'func_00111110','original_second','native_second')
        header=source/'ppu/ppu_recomp.h'
        header.write_text(header.read_text()+'void func_00111110(ppu_context*);\n')
        second_code=b'#include "ppu_recomp.h"\n'+second_body+b'\nauto second_table=&func_00111110;\n'
        (source/'ppu/second.cpp').write_bytes(second_code)
        multi=base/'multi'
        catalog=(contract,second)
        result=prepare(source,multi,elf,base/'multi.json',contracts=catalog)
        assert [b['symbol'] for b in result['bindings']]==[c.symbol for c in catalog]
        first_stamp=(multi/'ppu/authored.cpp').stat().st_mtime_ns
        second_stamp=(multi/'ppu/second.cpp').stat().st_mtime_ns
        caller=base/'multi-caller.cpp'
        caller.write_text('#include "ppu_recomp.h"\nvoid original_second(ppu_context*);\n'
            'void game_original_scene_list_evaluate(ppu_context*);\n'
            'void motorstorm_scene_evaluate(ppu_context* c){c->value=20;}\n'
            'void native_second(ppu_context* c){c->value=40;}\n'
            'int main(){ppu_context c{};func_006BEAE0(&c);if(c.value!=20)return 1;'
            'func_00111110(&c);if(c.value!=40)return 2;original_second(&c);'
            'game_original_scene_list_evaluate(&c);return c.value==43?0:3;}\n')
        multi_exe=base/('multi.exe' if os.name=='nt' else 'multi')
        command=[compiler,str(multi/'ppu/authored.cpp'),str(multi/'ppu/second.cpp'),str(caller)]
        command += ['/nologo','/std:c++17','/O2','/UNDEBUG','/I'+str(multi/'ppu'),'/Fo'+str(base)+os.sep,'/Fe'+str(multi_exe)] if os.name=='nt' else ['-std=c++17','-O2','-UNDEBUG','-I'+str(multi/'ppu'),'-o',str(multi_exe)]
        built=subprocess.run(command,cwd=base,capture_output=True,text=True)
        (out/'multi-build.log').write_text(built.stdout+built.stderr)
        assert built.returncode==0,built.stdout+built.stderr
        assert subprocess.run([str(multi_exe)]).returncode==0,'Both direct bindings and references must execute'
        prepare(source,multi,elf,base/'multi.json',contracts=catalog)
        assert (multi/'ppu/second.cpp').stat().st_mtime_ns==second_stamp
        prepare(source,multi,elf,base/'multi.json',contracts=(contract,),known_contracts=catalog)
        assert (multi/'ppu/second.cpp').read_bytes()==second_code
        assert (multi/'ppu/authored.cpp').stat().st_mtime_ns==first_stamp
        result=prepare(source,multi,elf,base/'multi.json',contracts=(second,),known_contracts=catalog)
        assert (multi/'ppu/authored.cpp').read_bytes()==code
        assert result['symbol']==second.symbol
        (multi/'ppu/second.cpp').write_bytes(b'// Unknown change\n'+(multi/'ppu/second.cpp').read_bytes())
        rejects(lambda:prepare(source,multi,elf,base/'multi.json',contracts=catalog),'changed or stale')
        assert (multi/'ppu/authored.cpp').read_bytes()==code,'Rejected copy must not partially enable another binding'
        assert tu.read_bytes()==code
    print('PASS native binding: exact identities, direct/table callers, unchanged originals, stable copy, duplicate/stale/junction rejection')


if __name__ == '__main__':
    main()
