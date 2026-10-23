#!/usr/bin/env python3
"""Extract MS1's symtab-named embedded SPU inputs from a user-supplied debug EBOOT.

The plain SPU ELF scan (vendor/ps3recomp/tools/extract_spu_images.py) only
finds images 1-2. The debug EBOOT also embeds, named by its .symtab:

  * ten WWS C0DEC0DE job binaries (stable ids 210-219):
      _binary_<stem>_wwsjob_image_start/_size, plus the two STT_OBJECT blobs
      mp3StereoJobCode / mp3SurroundJobCode;
  * the jobmanager policy-module template (_binary_jobmanager_file_start),
    registered as id 3 after appending 16 zero bytes and wrapping it as an
    SPU ELF at base/entry 0xA00;
  * the 672-byte jobbootstrap blob, which has no registration and is emitted
    for completeness only.

Every image is mapped through its containing PT_LOAD (file = p_offset + EA -
p_vaddr), checked against the committed identities in jobmod_meta.json and
written to an ignored output tree. Section sh_size includes alignment padding
and is never used as an image size. Any identity mismatch, missing symbol or
unexpected header exits non-zero before publishing output: a silently different
module would register
under a fingerprint the game never stages.

Outputs (under --out):
  jobmods/jobmod_<sha256-12>_e<entryOffset>.bin   raw images for lift_ms1_jobmods.py
  jobmod_meta.json                                copy of the committed stable ids
  spu_0002_policy_10135e00.elf                    wrapped PM (id 3); also copied to
                                                  --images when given
  jobbootstrap.bin                                unregistered, informational
  named_manifest.json                             offsets, sizes, entries, identities

Usage:
  python scripts/spu/extract_ms1_named.py --elf EBOOT.elf --out build/extracted/named
                                          [--images build/extracted/spu]

--out must be absent or empty. Existing --images policy files are preserved.
All inputs are validated before any files are published. Failed publication
removes only the files/directories created by this invocation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, '..', '..', 'vendor', 'ps3recomp', 'tools'))
sys.path.insert(0, TOOLS)
from wrap_spu_elf import wrap  # noqa: E402

META = os.path.join(HERE, 'jobmod_meta.json')
PT_LOAD = 1
SHT_SYMTAB = 2
STT_OBJECT = 1
SHN_ABS = 0xFFF1
EM_PPC64 = 21
JOB_KINDS = ('wwsjob_image',)
PM_STEM, PM_PAD, PM_BASE = 'jobmanager_file', 16, 0xA00
PM_NAME = 'spu_0002_policy_10135e00'
BOOTSTRAP_STEM = 'jobbootstrap_file'


def fnv1a64(data):
    h = 1469598103934665603
    for x in data:
        h = ((h ^ x) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


class Elf:
    """Minimal big-endian ELF64 reader: program headers, sections, .symtab."""

    def __init__(self, data):
        if data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 2:
            raise SystemExit('Input is not a big-endian ELF64 executable')
        machine = struct.unpack_from('>H', data, 0x12)[0]
        if machine != EM_PPC64:
            raise SystemExit(f'Input e_machine {machine} is not EM_PPC64')
        self.data = data
        phoff, shoff = struct.unpack_from('>QQ', data, 0x20)
        phentsize, phnum, shentsize, shnum = struct.unpack_from('>HHHH', data, 0x36)
        self.loads = []
        for i in range(phnum):
            o = phoff + i * phentsize
            p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz = struct.unpack_from('>IIQQQQ', data, o)
            if p_type == PT_LOAD and p_filesz:
                self.loads.append((p_vaddr, p_offset, p_filesz))
        self.sections = []
        for i in range(shnum):
            o = shoff + i * shentsize
            name, sh_type, _flags, _addr, off, size, link = struct.unpack_from('>IIQQQQI', data, o)
            self.sections.append(dict(name=name, type=sh_type, offset=off, size=size, link=link))
        symtabs = [s for s in self.sections if s['type'] == SHT_SYMTAB]
        if not symtabs:
            raise SystemExit('No .symtab: a stripped/retail EBOOT cannot drive the named extraction')
        symtab = symtabs[0]
        strtab = self.sections[symtab['link']]
        strings = data[strtab['offset']:strtab['offset'] + strtab['size']]
        self.symbols = {}
        for o in range(symtab['offset'], symtab['offset'] + symtab['size'], 24):
            st_name, st_info, _other, st_shndx, st_value, st_size = struct.unpack_from('>IBBHQQ', data, o)
            end = strings.find(b'\0', st_name)
            name = strings[st_name:end].decode('ascii', 'replace')
            if name:
                self.symbols.setdefault(name, dict(value=st_value, size=st_size,
                                                    type=st_info & 0xF, shndx=st_shndx))

    def file_offset(self, ea):
        for vaddr, offset, filesz in self.loads:
            if vaddr <= ea < vaddr + filesz:
                return offset + (ea - vaddr)
        raise SystemExit(f'EA 0x{ea:X} lies outside every file-backed PT_LOAD')

    def binary_blob(self, stem):
        start = self.symbols.get(f'_binary_{stem}_start')
        size = self.symbols.get(f'_binary_{stem}_size')
        if not start or not size:
            raise SystemExit(f'Missing _binary_{stem}_start/_size symbols')
        if size['shndx'] != SHN_ABS:
            raise SystemExit(f'_binary_{stem}_size is not an absolute symbol')
        return start['value'], size['value']


def job_header(raw, label):
    if len(raw) < 0x30 or raw[0x20:0x24] != b'\xC0\xDE\xC0\xDE':
        raise SystemExit(f'{label}: no C0DEC0DE marker at +0x20')
    if raw[0] not in (0x42, 0x43):
        raise SystemExit(f'{label}: leading word is not an ila marker')
    entry_off, image_size, bss = struct.unpack_from('>III', raw, 0x10)
    link = struct.unpack_from('>I', raw, 0x28)[0]
    if not link or link % 0x400:
        raise SystemExit(f'{label}: implausible link base 0x{link:X}')
    if not 0x30 <= entry_off < image_size:
        raise SystemExit(f'{label}: entry offset 0x{entry_off:X} outside image 0x{image_size:X}')
    return entry_off, image_size, bss, link


def job_candidates(elf):
    """(stem, symbol, EA, symtab size) for every named job image."""
    found = []
    for name, sym in elf.symbols.items():
        for kind in JOB_KINDS:
            suffix = f'_{kind}_start'
            if name.startswith('_binary_') and name.endswith(suffix):
                stem = name[len('_binary_'):-len('_start')]
                ea, size = elf.binary_blob(stem)
                found.append((name[len('_binary_'):-len(suffix)], name, ea, size))
        if (sym['type'] == STT_OBJECT and 0x400 <= sym['size'] <= 0x40000
                and sym['value'] % 16 == 0 and sym['value']):
            try:
                off = elf.file_offset(sym['value'])
            except SystemExit:
                continue
            if elf.data[off + 0x20:off + 0x24] == b'\xC0\xDE\xC0\xDE':
                found.append((name, name, sym['value'], sym['size']))
    unique = {}
    for candidate in found:
        unique.setdefault(candidate[2], candidate)
    return sorted(unique.values(), key=lambda c: c[2])


def sweep_unnamed(elf, named_offsets):
    """C0DEC0DE headers in file-backed LOADs that no symbol names."""
    extra = []
    for _vaddr, offset, filesz in elf.loads:
        pos = elf.data.find(b'\xC0\xDE\xC0\xDE', offset, offset + filesz)
        while pos >= 0:
            start = pos - 0x20
            if start >= offset and start % 16 == 0 and start not in named_offsets \
                    and elf.data[start] in (0x42, 0x43):
                extra.append(start)
            pos = elf.data.find(b'\xC0\xDE\xC0\xDE', pos + 4, offset + filesz)
    return extra


def check_destinations(out, images):
    """The named tree is never merged; class-A images keep their other files."""
    if os.path.lexists(out):
        if out.is_symlink() or not out.is_dir():
            raise SystemExit(f'{out} is not an empty output directory; move it aside before regeneration')
        if any(out.iterdir()):
            raise SystemExit(f'{out} is not empty; move it aside before regeneration')
    if images is not None:
        policy = images / (PM_NAME + '.elf')
        if os.path.lexists(policy):
            raise SystemExit(f'{policy} already exists; preserve it before regeneration')


def publish_outputs(out, images, files):
    """Publish validated bytes without replacing existing files; undo owned writes.

    Input/header validation must finish before this function is called. This is
    exception-safe publication, not an atomic transaction across directories.
    """
    check_destinations(out, images)
    targets = {out / name: data for name, data in files.items()}
    if images is not None:
        # --images may name --out itself, including through a directory alias.
        policy = images / (PM_NAME + '.elf')
        if policy.resolve() != (out / (PM_NAME + '.elf')).resolve():
            targets[policy] = files[PM_NAME + '.elf']
    created_files, created_dirs = [], []

    def ensure_directory(path):
        if path.is_dir():
            return
        ensure_directory(path.parent)
        try:
            path.mkdir()
        except FileExistsError:
            if not path.is_dir():
                raise
        else:
            created_dirs.append(path)

    try:
        for path, data in targets.items():
            ensure_directory(path.parent)
            with path.open('xb') as f:
                created_files.append(path)
                f.write(data)
    except BaseException:
        # Never recursively remove a caller's existing root or another file.
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass  # A directory populated by another writer is not ours.
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--elf', required=True, help='user-supplied named debug EBOOT (ELF64)')
    ap.add_argument('--out', required=True, help='ignored output directory')
    ap.add_argument('--images', help='also place the wrapped PM ELF beside the class-A SPU ELFs')
    ap.add_argument('--meta', default=META, help='stable ids/names/identities (default: committed copy)')
    args = ap.parse_args()

    out = Path(args.out)
    images = Path(args.images) if args.images else None
    check_destinations(out, images)
    meta_bytes = Path(args.meta).read_bytes()
    meta = json.loads(meta_bytes)
    expected = meta['identities']
    elf = Elf(Path(args.elf).read_bytes())

    errors, manifest, files = [], [], {}
    stems = {}
    for stem, symbol, ea, sym_size in job_candidates(elf):
        off = elf.file_offset(ea)
        entry_off, image_size, bss, link = job_header(elf.data[off:off + 0x30], symbol)
        if image_size != sym_size + 0x20:
            errors.append(f'{symbol}: header imageSize 0x{image_size:X} != symtab size 0x{sym_size:X} + 0x20')
            continue
        raw = elf.data[off:off + image_size]
        sha = hashlib.sha256(raw).hexdigest()
        name = f'jobmod_{sha[:12]}_e{entry_off:x}'
        staged = fnv1a64(raw[:image_size - 0x20])
        want = expected.get(name)
        if not want:
            errors.append(f'{symbol}: {name} has no committed identity')
        elif int(want['staged_fnv'], 16) != staged or want['symbol'] != symbol:
            errors.append(f'{name}: expected {want["symbol"]} staged {want["staged_fnv"]}, '
                          f'got {symbol} {staged:016X}')
        stems[off] = name
        files['jobmods/' + name + '.bin'] = raw
        manifest.append(dict(name=name, kind='wwsjob', symbol=symbol, stem=stem,
                             id=meta['ids'].get(name), reg_name=meta['names'].get(name),
                             guest_ea=f'0x{ea:08X}', file_offset=f'0x{off:08X}',
                             image_size=image_size, entry_offset=f'0x{entry_off:X}',
                             entry=f'0x{link + entry_off:X}', link_base=f'0x{link:X}',
                             bss_size=f'0x{bss:X}', staged_fnv=f'{staged:016X}', sha256=sha))
    missing = sorted(set(expected) - set(m['name'] for m in manifest) - {PM_NAME})
    if missing:
        errors.append('Committed identities not found in this EBOOT: ' + ', '.join(missing))
    extra = sweep_unnamed(elf, set(stems))
    if extra:
        print('WARNING: unnamed C0DEC0DE headers at file offsets ' +
              ', '.join(f'0x{o:X}' for o in extra))

    ea, size = elf.binary_blob(PM_STEM)
    off = elf.file_offset(ea)
    payload = elf.data[off:off + size] + b'\0' * PM_PAD
    pm = wrap(payload, base=PM_BASE, entry=PM_BASE)
    want = expected[PM_NAME]
    pm_whole, pm_text = fnv1a64(pm), fnv1a64(payload)
    if (pm_whole, pm_text) != (int(want['whole_fnv'], 16), int(want['text_fnv'], 16)):
        errors.append(f'{PM_NAME}: expected whole {want["whole_fnv"]} text {want["text_fnv"]}, '
                      f'got {pm_whole:016X} {pm_text:016X}')
    manifest.append(dict(name=PM_NAME, kind='policy', symbol=f'_binary_{PM_STEM}_start', id=3,
                         guest_ea=f'0x{ea:08X}', file_offset=f'0x{off:08X}', template_size=size,
                         wrap_base=f'0x{PM_BASE:X}', whole_fnv=f'{pm_whole:016X}',
                         text_fnv=f'{pm_text:016X}', sha256=hashlib.sha256(pm).hexdigest()))

    ea, size = elf.binary_blob(BOOTSTRAP_STEM)
    off = elf.file_offset(ea)
    bootstrap = elf.data[off:off + size]
    manifest.append(dict(name='jobbootstrap', kind='unregistered', symbol=f'_binary_{BOOTSTRAP_STEM}_start',
                         guest_ea=f'0x{ea:08X}', file_offset=f'0x{off:08X}', size=size,
                         whole_fnv=f'{fnv1a64(bootstrap):016X}'))

    if errors:
        raise SystemExit('Named SPU extraction rejected:\n  ' + '\n  '.join(errors))

    files[PM_NAME + '.elf'] = pm
    files['jobbootstrap.bin'] = bootstrap
    # lift_ms1_jobmods.py may append ids; its copy stays in ignored output.
    files['jobmod_meta.json'] = meta_bytes
    files['named_manifest.json'] = (json.dumps(dict(
        elf_sha256=hashlib.sha256(elf.data).hexdigest(), images=manifest), indent=2) + '\n').encode('utf-8')
    jobs = [m for m in manifest if m['kind'] == 'wwsjob']
    # Prepare even the report before publication: malformed metadata must not
    # turn a successful write into a late formatting failure.
    report = [f"  id {m['id']} {m['reg_name']:18} {m['name']:30} staged {m['staged_fnv']}" for m in jobs]
    publish_outputs(out, images, files)
    for line in report:
        print(line)
    print(f'PASS: {len(jobs)} job images, policy module and bootstrap match committed identities; '
          f'output {args.out}')


if __name__ == '__main__':
    main()
