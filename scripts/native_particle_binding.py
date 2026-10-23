"""Generate a private exact-code guard for the verified particle scan leaf."""
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class Contract:
    elf_sha256: str
    offset: int
    address: int
    size: int
    code_sha256: str


PARTICLE = Contract(
    '3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706',
    16163640, 0x12338, 200,
    '5f1bd3b01065d3231696cd0a652ca85fd8ecd53987b7f3824a1883efed009228')


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def reparse(path):
    return path.is_symlink() or bool(path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def prepare(elf, output, contract=PARTICLE):
    elf, output = Path(elf).resolve(), Path(output).absolute()
    if reparse(output) or output.resolve() == elf or output.resolve() in elf.parents:
        raise ValueError('Binding output must be separate from original input')
    if digest(elf) != contract.elf_sha256:
        raise ValueError('Unsupported original ELF identity')
    if contract.offset < 0 or contract.size <= 0 or contract.address < 0 or contract.address + contract.size > 0x40000:
        raise ValueError('Invalid code extent')
    with elf.open('rb') as source:
        source.seek(contract.offset)
        code = source.read(contract.size)
    if len(code) != contract.size or hashlib.sha256(code).hexdigest() != contract.code_sha256:
        raise ValueError('Original code identity/extent mismatch')
    generated = ('// Generated privately from verified original input; do not commit.\n'
                 '#include "spu_context.h"\n#include <cstring>\n'
                 'extern "C" int game_particle_threshold_code_matches(const spu_context* ctx) {\n'
                 ' static const unsigned char expected[] = {' + ','.join(f'0x{x:02x}' for x in code) + '};\n'
                 f' return ctx && ctx->ls == ctx->ls_store && !std::memcmp(ctx->ls+{contract.address},expected,sizeof(expected));\n'
                 '}\n').encode()
    identity = dict(elf_sha256=contract.elf_sha256, offset=contract.offset, address=contract.address,
                    bytes=contract.size, code_sha256=contract.code_sha256,
                    generated_sha256=hashlib.sha256(generated).hexdigest())
    files = {'particle_code_identity.cpp': generated,
             'identity.json': (json.dumps(identity, indent=2) + '\n').encode()}
    if output.exists():
        if not output.is_dir() or {p.name for p in output.iterdir()} != set(files):
            raise ValueError('Refusing occupied or incomplete binding output')
        for name, expected in files.items():
            path = output / name
            if reparse(path) or not path.is_file() or path.read_bytes() != expected:
                raise ValueError('Refusing modified binding output')
        return identity
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.particle-binding-', dir=output.parent) as scratch:
        for name, data in files.items():
            (Path(scratch) / name).write_bytes(data)
        os.rename(scratch, output)
    return identity


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.elf, args.output), indent=2))
