"""Prepare a private generated-input copy and bind a verified native game entry."""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil

IGNORED_CACHES = {'.neuronav', '__pycache__', '.cache', '.git'}


@dataclass(frozen=True)
class Contract:
    elf_sha256: str
    body_sha256: str
    symbol: str = 'func_006BEAE0'
    original: str = 'game_original_scene_list_evaluate'
    native: str = 'motorstorm_scene_evaluate'


# Identities only: original/generated program bytes never belong in Git.
PRODUCTION = Contract(
    '3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706',
    '7b23ca3b8caa320386fb2eb0bca6bcacafce4c1941aaecb706f4f55439bf9939')


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def definition(source, symbol):
    pattern = rb'\bvoid\s+(?P<symbol>' + re.escape(symbol.encode()) + rb')\s*\(\s*ppu_context\s*\*\s*ctx\s*\)\s*\{'
    matches = list(re.finditer(pattern, source))
    if len(matches) != 1:
        raise ValueError(f'Expected one definition of {symbol}, found {len(matches)}')
    match = matches[0]
    depth, pos = 1, match.end()
    while pos < len(source):
        if source[pos:pos+2] == b'//':
            end = source.find(b'\n', pos+2)
            pos = len(source) if end < 0 else end+1
        elif source[pos:pos+2] == b'/*':
            end = source.find(b'*/', pos+2)
            if end < 0:
                raise ValueError('Unterminated reference comment')
            pos = end+2
        elif source[pos] in (34, 39):
            quote = source[pos]
            pos += 1
            while pos < len(source) and source[pos] != quote:
                pos += 2 if source[pos] == 92 else 1
            pos += 1
        else:
            depth += (source[pos] == 123) - (source[pos] == 125)
            pos += 1
            if not depth:
                return match, pos
    raise ValueError('Unterminated reference body')


def transform(source, contract):
    for symbol in (contract.symbol, contract.original, contract.native):
        if not re.fullmatch(r'[A-Za-z_]\w*', symbol):
            raise ValueError('Invalid binding symbol')
    match, end = definition(source, contract.symbol)
    body = source[match.start():end].replace(b'\r\n', b'\n')
    if hashlib.sha256(body).hexdigest() != contract.body_sha256:
        raise ValueError('Reference body identity changed; verify it before binding')
    if re.search(rb'\b' + contract.original.encode() + rb'\b', source):
        raise ValueError('Reference symbol already present')
    renamed = source[:match.start('symbol')] + contract.original.encode() + source[match.end('symbol'):]
    wrapper = (f'\n// Handwritten game entry; preserve direct and registered callers.\n'
               f'void {contract.native}(ppu_context*);\n'
               f'void {contract.symbol}(ppu_context* ctx) {{ {contract.native}(ctx); }}\n').encode()
    return renamed + wrapper


def prepare(generated, output, elf, manifest, contract=PRODUCTION):
    generated, output, elf, manifest = map(lambda p: Path(p).resolve(), (generated, output, elf, manifest))
    if output.is_relative_to(generated) or generated.is_relative_to(output) or manifest.is_relative_to(generated):
        raise ValueError('Binding outputs must be separate from original inputs')
    if digest(elf) != contract.elf_sha256:
        raise ValueError('Unsupported original ELF identity for native game binding')
    files = {}
    for path in sorted(generated.rglob('*')):
        if IGNORED_CACHES.intersection(path.relative_to(generated).parts):
            continue
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Generated input contains a reparse point')
        if path.is_file():
            files[path.relative_to(generated)] = digest(path)
    if not files or not (generated/'ppu/ppu_recomp.h').is_file():
        raise ValueError('Expected the selected generated tree with ppu/ppu_recomp.h')
    candidates = []
    for relative in files:
        if relative.parent == Path('ppu') and relative.suffix in {'.c', '.cpp'}:
            source = (generated/relative).read_bytes()
            if re.search(rb'\bvoid\s+' + contract.symbol.encode() + rb'\s*\(', source):
                candidates.append((relative, source))
    # Declarations in a TU are legal; only the unique full definition binds.
    definitions = []
    for relative, source in candidates:
        if re.search(rb'\bvoid\s+' + contract.symbol.encode() + rb'\s*\(\s*ppu_context\s*\*\s*ctx\s*\)\s*\{', source):
            definitions.append((relative, source))
    if len(definitions) != 1:
        raise ValueError('Expected exactly one defining generated translation unit')
    relative, source = definitions[0]
    changed = transform(source, contract)
    if not output.exists():
        shutil.copytree(generated, output, ignore=shutil.ignore_patterns(*IGNORED_CACHES))
    for path in output.rglob('*'):
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Prepared input copy contains a reparse point')
    for entry, sha in files.items():
        destination = output/entry
        expected = hashlib.sha256(changed).hexdigest() if entry == relative else sha
        actual = digest(destination)
        if actual != expected and not (entry == relative and actual == sha):
            raise ValueError(f'Prepared input copy changed or stale: {entry}')
    destination = output/relative
    if destination.read_bytes() != changed:
        destination.write_bytes(changed)
    if any(digest(generated/entry) != sha for entry, sha in files.items()):
        raise ValueError('Original inputs changed during preparation')
    result = dict(original_tu=(generated/relative).as_posix(), copied_tu=destination.as_posix(),
                  elf_sha256=contract.elf_sha256, reference_body_sha256=contract.body_sha256,
                  copied_tu_sha256=digest(destination), input_files={str(p): sha for p, sha in files.items()})
    encoded = json.dumps(result, indent=2)+'\n'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if not manifest.exists() or manifest.read_text() != encoded:
        manifest.write_text(encoded)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('generated', 'output', 'elf', 'manifest'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.generated, args.output, args.elf, args.manifest)
    print('Verified native hierarchy binding:', result['copied_tu_sha256'])


if __name__ == '__main__':
    main()
