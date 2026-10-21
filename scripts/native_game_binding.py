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
JOB_WAIT = Contract(PRODUCTION.elf_sha256,
    'ab53a9f3f0d538a07d6333eb2b45d78a2dd40e2a3dcbe317e08109f96fad5fca',
    'func_00C5C424', 'game_original_job_marker_wait', 'motorstorm_job_marker_wait')


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


def prepare(generated, output, elf, manifest, contract=PRODUCTION, *, contracts=None, known_contracts=None):
    generated, output, elf, manifest = map(lambda p: Path(p).resolve(), (generated, output, elf, manifest))
    if output.is_relative_to(generated) or generated.is_relative_to(output) or manifest.is_relative_to(generated):
        raise ValueError('Binding outputs must be separate from original inputs')
    selected = tuple(contracts) if contracts is not None else (contract,)
    if not selected or len({c.symbol for c in selected}) != len(selected):
        raise ValueError('Expected nonempty unique native bindings')
    elf_sha = digest(elf)
    if any(elf_sha != c.elf_sha256 for c in selected):
        raise ValueError('Unsupported original ELF identity for native game binding')
    known = tuple(known_contracts) if known_contracts is not None else (
        (PRODUCTION, JOB_WAIT) if elf_sha == PRODUCTION.elf_sha256 else selected)
    known = tuple(dict.fromkeys((*known, *selected)))
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
    definitions = {}
    for relative in files:
        if relative.parent == Path('ppu') and relative.suffix in {'.c', '.cpp'}:
            source = (generated/relative).read_bytes()
            for entry in known:
                if re.search(rb'\bvoid\s+' + entry.symbol.encode() + rb'\s*\(\s*ppu_context\s*\*\s*ctx\s*\)\s*\{', source):
                    definitions.setdefault(entry, []).append((relative, source))
    changes, allowed, bindings = {}, {}, []
    for entry in known:
        candidates = definitions.get(entry, [])
        if len(candidates) != 1:
            if entry in selected:
                raise ValueError('Expected exactly one defining generated translation unit')
            continue
        relative, source = candidates[0]
        try:
            changed = transform(source, entry)
        except ValueError:
            if entry in selected:
                raise
            continue
        sha = hashlib.sha256(changed).hexdigest()
        allowed.setdefault(relative, set()).add(sha)
        if entry in selected:
            if relative in changes:
                raise ValueError('Multiple bindings in one TU require a combined verified transform')
            changes[relative] = changed
            bindings.append(dict(symbol=entry.symbol, original_tu=(generated/relative).as_posix(),
                copied_tu=(output/relative).as_posix(), reference_body_sha256=entry.body_sha256,
                copied_tu_sha256=sha))
    if not output.exists():
        shutil.copytree(generated, output, ignore=shutil.ignore_patterns(*IGNORED_CACHES))
    for path in output.rglob('*'):
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Prepared input copy contains a reparse point')
    for entry, sha in files.items():
        destination = output/entry
        expected = hashlib.sha256(changes[entry]).hexdigest() if entry in changes else sha
        actual = digest(destination)
        if actual not in {expected, sha, *allowed.get(entry, ())}:
            raise ValueError(f'Prepared input copy changed or stale: {entry}')
    # Feature changes may restore only a known, identity-verified transform.
    # Unknown edits still fail before any copy is written.
    for entry in allowed:
        destination = output/entry
        expected = changes.get(entry)
        if expected is None:
            expected = (generated/entry).read_bytes()
        if destination.read_bytes() != expected:
            destination.write_bytes(expected)
    if any(digest(generated/entry) != sha for entry, sha in files.items()):
        raise ValueError('Original inputs changed during preparation')
    result = dict(bindings[0], elf_sha256=elf_sha, bindings=bindings,
                  input_files={str(p): sha for p, sha in files.items()})
    encoded = json.dumps(result, indent=2)+'\n'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if not manifest.exists() or manifest.read_text() != encoded:
        manifest.write_text(encoded)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('generated', 'output', 'elf', 'manifest'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--without-world-transforms', action='store_true')
    parser.add_argument('--job-wait', action='store_true')
    args = parser.parse_args()
    selected = ([] if args.without_world_transforms else [PRODUCTION]) + ([JOB_WAIT] if args.job_wait else [])
    result = prepare(args.generated, args.output, args.elf, args.manifest, contracts=selected)
    print('Verified native game bindings:', ', '.join(b['symbol'] for b in result['bindings']))


if __name__ == '__main__':
    main()
