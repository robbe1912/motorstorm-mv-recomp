#!/usr/bin/env python3
"""Replay archived Windows x64 stacks. No target process or desktop access."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
from project import ROOT, build_environment

class Module(C.Structure):
    _fields_ = [('base', C.c_uint64), ('size', C.c_uint64), ('path', C.c_wchar_p)]
class Frame(C.Structure):
    _fields_ = [('ip', C.c_uint64), ('sp', C.c_uint64), ('displacement', C.c_uint64),
                ('symbol_type', C.c_uint32), ('symbol', C.c_char * 256)]

class ModuleIdentity(C.Structure):
    _fields_ = [('symbol_type',C.c_uint32),('age',C.c_uint32),('guid',C.c_ubyte*16),('pdb',C.c_char*260)]

def codeview_identity(path):
    data=Path(path).read_bytes();nt=int.from_bytes(data[60:64],'little')
    import struct
    sections=struct.unpack_from('<H',data,nt+6)[0];optional=struct.unpack_from('<H',data,nt+20)[0]
    rva,size=struct.unpack_from('<II',data,nt+24+112+6*8)
    for i in range(sections):
        offset=nt+24+optional+40*i
        virtual,va,raw,pointer=struct.unpack_from('<IIII',data,offset+8)
        if va<=rva and rva+size<=va+raw:
            directory=pointer+rva-va
            for record in range(directory,directory+size,28):
                kind,length,_,file_offset=struct.unpack_from('<IIII',data,record+12)
                if kind==2 and length>=24 and data[file_offset:file_offset+4]==b'RSDS':
                    return dict(guid=data[file_offset+4:file_offset+20].hex(),age=struct.unpack_from('<I',data,file_offset+20)[0])
    raise ValueError('No admitted RSDS CodeView record')

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def compile_reader(output, chain=False, reader_source=None):
    if os.name != 'nt' or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('Actual Windows x64 execution is required; no skipped pass')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    env = build_environment(); compiler = env.get('MV_CLANG', 'clang-cl')
    commands = []; sources = []
    names = ['native_stack_reader'] + (['native_stack_chain'] if chain else [])
    for name in names:
        source = Path(reader_source) if reader_source and name.endswith('reader') else ROOT/'scripts/fixtures'/f'{name}.c'
        sources.append(source)
        target = output/(name + ('.dll' if name.endswith('reader') else '.exe'))
        command = [compiler, '/nologo', '/std:c17', '/O2', '/Ob2', '/Zi', '/UNDEBUG',
                   str(source), '/Fo'+str(output)+os.sep,
                   '/Fe'+str(target)]
        if name.endswith('reader'): command += ['/LD']
        command += ['/link', '/DEBUG', '/INCREMENTAL:NO', '/OPT:REF',
                    '/PDB:'+str(target.with_suffix('.pdb'))]
        if name.endswith('reader'): command += ['dbghelp.lib']
        commands.append(command)
        ran = subprocess.run(command, env=env, cwd=output, capture_output=True, timeout=90)
        (output/(name+'-build.log')).write_bytes(ran.stdout+ran.stderr)
        (output/'commands.json').write_text(json.dumps(commands, indent=2), encoding='utf-8')
        if ran.returncode:
            raise RuntimeError((ran.stdout+ran.stderr).decode('utf-8', errors='replace'))
    (output/'source-hashes.json').write_text(json.dumps({str(source):sha(source) for source in sources}, indent=2), encoding='utf-8')
    return output/'native_stack_reader.dll'

class Replay:
    def __init__(self, library, modules, symbols):
        self.lib = C.CDLL(str(library)); self.modules = modules
        self.lib.stack_open.argtypes = [C.POINTER(Module), C.c_uint32, C.c_wchar_p]
        self.lib.stack_open.restype = C.c_int
        self.lib.stack_error.restype = C.c_char_p
        self.lib.stack_frame_size.restype = C.c_uint32
        self.lib.stack_module_identity.argtypes=[C.c_uint64,C.POINTER(ModuleIdentity),C.c_uint32]
        self.lib.stack_module_identity.restype=C.c_int
        self.lib.stack_walk.argtypes = [C.c_void_p,C.c_uint32,C.c_uint64,C.c_void_p,C.c_uint32,
                                       C.POINTER(Frame),C.c_uint32,C.POINTER(C.c_uint32),
                                       C.POINTER(C.c_uint32),C.POINTER(C.c_uint64)]
        self.lib.stack_walk.restype = C.c_int
        assert self.lib.stack_frame_size() == C.sizeof(Frame)
        self.inputs = (Module*len(modules))(*(Module(m['base'],m['size'],str(Path(m['path']).resolve())) for m in modules))
        if self.lib.stack_open(self.inputs,len(modules),str(Path(symbols).resolve())):
            error = self.lib.stack_error().decode(); self.lib.stack_close(); raise RuntimeError(error)
    def module_identity(self, base):
        info=ModuleIdentity()
        if self.lib.stack_module_identity(base,C.byref(info),C.sizeof(info)):
            raise ValueError('Loaded symbol identity unavailable')
        return dict(symbol_type=info.symbol_type,age=info.age,guid=bytes(info.guid).hex(),pdb=info.pdb.decode('utf-8',errors='strict'))
    def close(self): self.lib.stack_close()
    def walk(self, context, stack_base, stack, capacity=64):
        ctx = C.create_string_buffer(context); memory = C.create_string_buffer(stack)
        frames = (Frame*capacity)(); reason=C.c_uint32(); misses=C.c_uint32(); missing=C.c_uint64()
        count=self.lib.stack_walk(ctx,len(context),stack_base,memory,len(stack),frames,capacity,
                                 C.byref(reason),C.byref(misses),C.byref(missing))
        if count < 0: raise ValueError('Context, image-base or stack admission rejected')
        names = {0:'end',1:'missing saved memory',2:'unwind stopped',3:'depth limit',4:'invalid progression',5:'unmapped image'}
        return dict(frames=[dict(ip=f.ip,sp=f.sp,symbol=f.symbol.decode('utf-8',errors='replace'),
                                displacement=f.displacement,symbol_type=f.symbol_type) for f in frames[:count]],
                    diagnostic=self.lib.stack_error().decode(),reason=names[reason.value],missing_reads=misses.value,missing_address=missing.value)
