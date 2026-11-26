"""Prepare a private generated-input copy and bind a verified native game entry."""
import argparse
from dataclasses import dataclass, replace
import hashlib
import itertools
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
    context: str = 'ppu_context'
    directory: str = 'ppu'
    matcher: str = ''
    windows: tuple = ()  # (ELF file offset, local-store offset, byte count)
    byte_observer: str = ''


# Identities only: original/generated program bytes never belong in Git.
PRODUCTION = Contract(
    '3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706',
    '7b23ca3b8caa320386fb2eb0bca6bcacafce4c1941aaecb706f4f55439bf9939')
JOB_WAIT = Contract(PRODUCTION.elf_sha256,
    'ab53a9f3f0d538a07d6333eb2b45d78a2dd40e2a3dcbe317e08109f96fad5fca',
    'func_00C5C424', 'game_original_job_marker_wait', 'motorstorm_job_marker_wait')
QUEUE_RESET = Contract(PRODUCTION.elf_sha256,
    '71b5a619bc898c6c0feca5256696075311122ee31439896da4e4dc395aaf16c9',
    'func_00C5BF38', 'game_original_queue_reset', 'motorstorm_observe_queue_reset')
QUEUE_RESET_MULTI = Contract(PRODUCTION.elf_sha256,
    '8018cd6ea22c22adf260a4eae47a1ed2056a9fabb3cac57fe21e16e93a8f0ce1',
    'func_00C5D4C0', 'game_original_queue_reset_multi', 'motorstorm_observe_queue_reset_multi')
QUEUE_INIT = Contract(PRODUCTION.elf_sha256,
    'fe86f9867d35717633192c4208b308d59f6910d3673572d3f5d8b5f8a1790c63',
    'func_00C5D1C0', 'game_original_queue_init', 'motorstorm_observe_queue_init')
QUEUE_ADD_JOB = Contract(PRODUCTION.elf_sha256,
    'f072ed2dccd0c49c7124e3274ad16be055ce487c965f761e5ec09aeb16b324c2',
    'func_00C5C6A0', 'game_original_add_job', 'motorstorm_observe_add_job')
MENU_VIDEO = Contract(PRODUCTION.elf_sha256,
    '851fe7b89535f0309c489318fc5be5756103557363de0f18c73e2ccb0b735d25',
    'func_0050C9E8', 'game_original_start_video', 'motorstorm_boot_start_video')
MENU_LANGUAGE = Contract(PRODUCTION.elf_sha256,
    'a2ec3a9e721fa5f60a201e579af96d2e4405404b50a7ebf352803f9e38cb5d79',
    'func_00530A88', 'game_original_language_event', 'motorstorm_boot_language_event')
HAVOK_THREADS = Contract(PRODUCTION.elf_sha256,
    '9a263a15562ae116cbd6d9c252383733477e82c9811a7f8b7f27bc74622e443e',
    'func_00A01220', 'game_original_init_multithreading', 'motorstorm_havok_threads')
# Direct lifted callers bypass registry-only observation.
DEPTH_OBSERVER = Contract(PRODUCTION.elf_sha256,
    'c1569b155b7ff33025877349e330a5a8c8b9c2adc0f62b946d2bcbd5408f6064',
    'func_0029C684', 'game_original_deformation_depth', 'motorstorm_observe_deformation_depth',
    byte_observer='motorstorm_observe_depth_byte')
VISIBILITY = Contract(PRODUCTION.elf_sha256,
    '035be34da5f4b00d47d7c7c0637aeaf93635b53ef209e4033f2ada6f918f7bbf',
    'jobmod_056ac0eea1a6_e12270_spu_func_000083A0',
    'game_original_visibility_box', 'motorstorm_visibility_planes',
    context='spu_context', directory='spu/jobmod_056ac0eea1a6_e12270',
    matcher='game_visibility_code_matches',
    windows=((0xf7b320, 0x83a0, 596), (0xf893f0, 0x16470, 16)))
# Second contract of the same unit: the lifted visibility batch entry 0x88F8.
VISIBILITY_BATCH = Contract(PRODUCTION.elf_sha256,
    'e7f7e87fabf5fbe1b5ee8c48648e4ed4f180d74b39e95007fa7c6dd025b144f1',
    'jobmod_056ac0eea1a6_e12270_spu_func_000088F8', 'game_original_visibility_batch',
    'motorstorm_visibility_batch', context='spu_context',
    directory='spu/jobmod_056ac0eea1a6_e12270', matcher='game_visibility_batch_code_matches',
    windows=((0xf76f80, 0x4000, 0x12580), (0xf89510, 0x16590, 0xb0)))
PCM_CUBIC = Contract(PRODUCTION.elf_sha256,
    'b05fee5d4213b0ff372550313a07ad170788714135bbe979fbecfa86f4999d4f',
    'spu_0000_at_00EDE500_spu_func_00009D5C',
    'game_original_pcm_cubic', 'motorstorm_pcm_cubic',
    context='spu_context', directory='spu/spu_0000_at_00EDE500',
    matcher='game_pcm_cubic_code_matches',
    windows=((0xee535c, 0x9d5c, 1140), (0xeeafc0, 0xf9c0, 368)))
# Particle ports of SPU image 213 (jobmod_556b30b5e654_e12e20).
PARTICLE_RANDOM = Contract(PRODUCTION.elf_sha256,
    '84dc7ff8a5a43c9eafed59de63a9e0a61a96fab485ec6a054b7159d0811e99aa',
    'jobmod_556b30b5e654_e12e20_spu_func_000170D0',
    'game_original_particle_random_run', 'motorstorm_particle_random_run',
    context='spu_context', directory='spu/jobmod_556b30b5e654_e12e20',
    matcher='game_particle_random_code_matches',
    windows=((0xf6f0d0, 0x170d0, 0x18c),))
PARTICLE_RANDOM_INIT = Contract(PRODUCTION.elf_sha256,
    '03e488010c467f00db6fcb7a1915d9fc2ce3c6899a8e70aaed7f41a1e8cd9edf',
    'jobmod_556b30b5e654_e12e20_spu_func_00017248',
    'game_original_particle_random_init', 'motorstorm_particle_random_init',
    context='spu_context', directory='spu/jobmod_556b30b5e654_e12e20',
    matcher='game_particle_random_init_code_matches',
    windows=((0xf6f248, 0x17248, 0x14),))
PARTICLE_COLLISION = Contract(PRODUCTION.elf_sha256,
    '43aa4cfcc5b35189c616de02afa7e761cb329e415057b5c156c5fa2a8a4abe7f',
    'jobmod_556b30b5e654_e12e20_spu_func_0000A87C',
    'game_original_particle_collision_loop', 'motorstorm_particle_collision_batch',
    context='spu_context', directory='spu/jobmod_556b30b5e654_e12e20',
    matcher='game_particle_collision_code_matches',
    windows=((0xf62700, 0xa700, 0x4ec), (0xf6f360, 0x17360, 0x50),))


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def definition(source, symbol, context='ppu_context'):
    pattern = rb'\bvoid\s+(?P<symbol>' + re.escape(symbol.encode()) + rb')\s*\(\s*' + re.escape(context.encode()) + rb'\s*\*\s*ctx\s*\)\s*\{'
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


def transform(source, contract, windows=()):
    for symbol in (contract.symbol, contract.original, contract.native, contract.context):
        if not re.fullmatch(r'[A-Za-z_]\w*', symbol):
            raise ValueError('Invalid binding symbol')
    if bool(contract.matcher) != bool(contract.windows) or len(windows) != len(contract.windows):
        raise ValueError('Expected all verified code/data windows')
    match, end = definition(source, contract.symbol, contract.context)
    body = source[match.start():end].replace(b'\r\n', b'\n')
    if hashlib.sha256(body).hexdigest() != contract.body_sha256:
        raise ValueError('Reference body identity changed; verify it before binding')
    if re.search(rb'\b' + contract.original.encode() + rb'\b', source):
        raise ValueError('Reference symbol already present')
    renamed_body = source[match.start():match.start('symbol')] + contract.original.encode() + source[match.end('symbol'):end]
    if contract.byte_observer:
        if contract.context != 'ppu_context' or not re.fullmatch(r'[A-Za-z_]\w*', contract.byte_observer):
            raise ValueError('Invalid PPU byte observer')
        # Preserve this TU's actual fast/slow memory policy before temporarily
        # observing calls inside the exact verified function body only.
        reader = contract.original + '_read8'
        prefix = (f'\nuint8_t {contract.byte_observer}(uint64_t, uint8_t (*)(uint64_t));\n'
                  f'static uint8_t {reader}(uint64_t address) {{ return vm_read8(address); }}\n'
                  '#pragma push_macro("vm_read8")\n#undef vm_read8\n'
                  f'#define vm_read8(address) {contract.byte_observer}((address), {reader})\n').encode()
        renamed_body = prefix + renamed_body + b'\n#pragma pop_macro("vm_read8")\n'
    renamed = source[:match.start()] + renamed_body + source[end:]
    wrapper = (f'\n// Handwritten game entry; preserve direct and registered callers.\n'
               f'void {contract.native}({contract.context}*);\n'
               f'void {contract.symbol}({contract.context}* ctx) {{ {contract.native}(ctx); }}\n').encode()
    if contract.matcher:
        if not re.fullmatch(r'[A-Za-z_]\w*', contract.matcher) or contract.context != 'spu_context':
            raise ValueError('Invalid local-store matcher')
        if re.search(rb'\b' + contract.matcher.encode() + rb'\b', source):
            raise ValueError('Matcher symbol already present')
        guard = ['\n#include <string.h>\n', f'int {contract.matcher}(const spu_context* ctx) {{\n']
        conditions = ['ctx', 'ctx->ls']
        for i, ((_, address, count), data) in enumerate(zip(contract.windows, windows)):
            if len(data) != count:
                raise ValueError('Truncated verified window')
            guard.append(f'    static const unsigned char window_{i}[] = {{' + ','.join(f'0x{b:02x}' for b in data) + '};\n')
            conditions.extend([f'{address}u + sizeof(window_{i}) <= sizeof(ctx->ls_store)',
                f'memcmp(ctx->ls + {address}u, window_{i}, sizeof(window_{i})) == 0'])
        guard.append('    return ' + ' &&\n        '.join(conditions) + ';\n}\n')
        wrapper += ''.join(guard).encode()
    return renamed + wrapper


def read_windows(elf, contract):
    result = []
    with Path(elf).open('rb') as source:
        for offset, address, count in contract.windows:
            if offset < 0 or address < 0 or count <= 0 or address + count > 0x40000:
                raise ValueError('Invalid verified window bounds')
            source.seek(offset)
            data = source.read(count)
            if len(data) != count:
                raise ValueError('Truncated original ELF window')
            result.append(data)
    return result


def source_root(roots, relative):
    """The generated tree that holds one relative path."""
    return next(root for root in roots if (root/relative).is_file())


def prepare(generated, output, elf, manifest, contract=PRODUCTION, *, contracts=None, known_contracts=None,
            spu_generated=None):
    generated, output, elf, manifest = map(lambda p: Path(p).resolve(), (generated, output, elf, manifest))
    roots = (generated,) if spu_generated is None else (generated, Path(spu_generated).resolve())
    if any(output.is_relative_to(root) or root.is_relative_to(output) or manifest.is_relative_to(root)
           for root in roots):
        raise ValueError('Binding outputs must be separate from original inputs')
    selected = tuple(contracts) if contracts is not None else (contract,)
    if not selected or len({c.symbol for c in selected}) != len(selected):
        raise ValueError('Expected nonempty unique native bindings')
    elf_sha = digest(elf)
    if any(elf_sha != c.elf_sha256 for c in selected):
        raise ValueError('Unsupported original ELF identity for native game binding')
    known = tuple(known_contracts) if known_contracts is not None else (
        (PRODUCTION, JOB_WAIT, VISIBILITY, VISIBILITY_BATCH, PCM_CUBIC, PARTICLE_RANDOM, PARTICLE_RANDOM_INIT, PARTICLE_COLLISION,
         DEPTH_OBSERVER, QUEUE_RESET, QUEUE_RESET_MULTI, QUEUE_INIT, QUEUE_ADD_JOB, MENU_VIDEO, MENU_LANGUAGE, HAVOK_THREADS) if elf_sha == PRODUCTION.elf_sha256 else selected)
    # Older observer copies used the same verified body without byte tracing.
    # Admit only that exact legacy recipe when enabling/disabling this feature.
    known = tuple(dict.fromkeys((*known, *selected,
        *(replace(c, byte_observer='') for c in (*known, *selected) if c.byte_observer))))
    directories = {Path(entry.directory) for entry in known}
    if any(path.is_absolute() or '..' in path.parts for path in directories):
        raise ValueError('Binding directories must stay inside generated inputs')
    files = {}
    for root in roots:
        for path in sorted(root.rglob('*')):
            if IGNORED_CACHES.intersection(path.relative_to(root).parts):
                continue
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Generated input contains a reparse point')
            if path.is_file():
                relative = path.relative_to(root)
                if relative in files:
                    raise ValueError(f'Duplicate generated input: {relative}')
                files[relative] = digest(path)
    if not files or not (generated/'ppu/ppu_recomp.h').is_file():
        raise ValueError('Expected the selected generated tree with ppu/ppu_recomp.h')
    definitions = {}
    for relative in files:
        if relative.parent in directories and relative.suffix in {'.c', '.cpp'}:
            source = (source_root(roots, relative)/relative).read_bytes()
            for entry in known:
                if relative.parent == Path(entry.directory) and re.search(rb'\bvoid\s+' + entry.symbol.encode() + rb'\s*\(\s*' + re.escape(entry.context.encode()) + rb'\s*\*\s*ctx\s*\)\s*\{', source):
                    definitions.setdefault(entry, []).append((relative, source))
    changes, allowed, bindings, grouped = {}, {}, [], {}
    for entry in known:
        candidates = definitions.get(entry, [])
        if len(candidates) != 1:
            if entry in selected:
                raise ValueError('Expected exactly one defining generated translation unit')
            continue
        relative, source = candidates[0]
        try:
            changed = transform(source, entry, read_windows(elf, entry))
        except ValueError:
            if entry in selected:
                raise
            continue
        grouped.setdefault(relative, {}).setdefault(entry.symbol, []).append(entry)
    selected_symbols = {entry.symbol: entry for entry in selected}
    for relative, symbols in grouped.items():
        if len(symbols) > 8:
            raise ValueError('Too many bindings in one translation unit')
        source = (source_root(roots, relative)/relative).read_bytes()
        # Legacy and current recipes for the same symbol are alternatives.
        # Each combination applies at most one verified recipe per function.
        choices = [(None, *recipes) for recipes in symbols.values()]
        wanted = tuple(selected_symbols.get(symbol) for symbol in symbols)
        for combination in itertools.product(*choices):
            changed = source
            for entry in combination:
                if entry is not None:
                    changed = transform(changed, entry, read_windows(elf, entry))
            sha = hashlib.sha256(changed).hexdigest()
            allowed.setdefault(relative, set()).add(sha)
            if combination == wanted and any(wanted):
                changes[relative] = changed
                for entry in combination:
                    if entry is None:
                        continue
                    binding = dict(symbol=entry.symbol,
                        original_tu=(source_root(roots, relative)/relative).as_posix(),
                        copied_tu=(output/relative).as_posix(),
                        reference_body_sha256=entry.body_sha256,
                        copied_tu_sha256=sha, context=entry.context)
                    if entry.byte_observer:
                        binding['byte_observer'] = entry.byte_observer
                    bindings.append(binding)
    order = {entry.symbol: index for index, entry in enumerate(selected)}
    bindings.sort(key=lambda binding: order[binding['symbol']])
    if not output.exists():
        for root in roots:
            shutil.copytree(root, output, ignore=shutil.ignore_patterns(*IGNORED_CACHES),
                            dirs_exist_ok=root is not roots[0])
    for path in output.rglob('*'):
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Prepared input copy contains a reparse point')
    # A copy made before a second root was read holds no file of that root.
    # Copy each missing file from its root; the loop below then checks its identity.
    for entry in files:
        if not (output/entry).exists():
            (output/entry).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root(roots, entry)/entry, output/entry)
    for entry, sha in files.items():
        destination = output/entry
        expected = hashlib.sha256(changes[entry]).hexdigest() if entry in changes else sha
        actual = digest(destination)
        if actual not in {expected, sha, *allowed.get(entry, ())}:
            raise ValueError(f'Prepared input copy changed or stale: {entry}. '
                             'The generated tree changed, or an edit touched the copy. '
                             f'Move {output} away and configure again.')
    # Feature changes may restore only a known, identity-verified transform.
    # Unknown edits still fail before any copy is written.
    for entry in allowed:
        destination = output/entry
        expected = changes.get(entry)
        if expected is None:
            expected = (source_root(roots, entry)/entry).read_bytes()
        if destination.read_bytes() != expected:
            destination.write_bytes(expected)
    if any(digest(source_root(roots, entry)/entry) != sha for entry, sha in files.items()):
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
    parser.add_argument('--visibility', action='store_true')
    parser.add_argument('--visibility-batch', action='store_true')
    parser.add_argument('--pcm-cubic', action='store_true')
    parser.add_argument('--depth-observer', action='store_true')
    parser.add_argument('--menu-boot', action='store_true')
    parser.add_argument('--havok-threads', action='store_true')
    parser.add_argument('--queue-call-observation', action='store_true',
                        help='Observe verified queue reset/init/publication calls')
    parser.add_argument('--particle-random', action='store_true',
                        help='Bind the verified particle random generator of SPU image 213')
    parser.add_argument('--particle-collisions', action='store_true',
                        help='Bind the verified particle-box collision loop of SPU image 213')
    parser.add_argument('--spu-generated', type=Path,
                        help='Second generated tree that holds the lifted SPU images')
    args = parser.parse_args()
    selected = ([] if args.without_world_transforms else [PRODUCTION]) + ([JOB_WAIT] if args.job_wait else []) + ([VISIBILITY] if args.visibility else []) + ([PCM_CUBIC] if args.pcm_cubic else []) + ([VISIBILITY_BATCH] if args.visibility_batch else [])
    if args.menu_boot:
        selected.extend((MENU_VIDEO, MENU_LANGUAGE))
    if args.havok_threads:
        selected.append(HAVOK_THREADS)
    if args.depth_observer:
        selected.append(DEPTH_OBSERVER)
    if args.queue_call_observation:
        selected.extend((QUEUE_RESET, QUEUE_RESET_MULTI, QUEUE_INIT, QUEUE_ADD_JOB))
    if args.particle_random:
        selected.extend((PARTICLE_RANDOM, PARTICLE_RANDOM_INIT))
    if args.particle_collisions:
        selected.append(PARTICLE_COLLISION)
    result = prepare(args.generated, args.output, args.elf, args.manifest, contracts=selected,
                     spu_generated=args.spu_generated)
    print('Verified native game bindings:', ', '.join(b['symbol'] for b in result['bindings']))


if __name__ == '__main__':
    main()
