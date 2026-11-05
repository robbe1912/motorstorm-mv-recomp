#!/usr/bin/env python3
"""lift_ms1_jobmods.py -- lift MS1's embedded WWS job binaries and register them.

MS1 embeds its WWS job modules directly in the EBOOT as C0DEC0DE images:

    +0x00  4 x ila marker words        (0x42../0x43.. top byte)
    +0x10  entryOffset                 (u32 BE, from image start)
    +0x14  imageSize                   (u32 BE, == file size)
    +0x18  bssSize                     (the CRT clears [end, end+bssSize))
    +0x20  C0DEC0DE marker
    +0x28  LINK BASE                   (observed 0x4000 on every MS1 image)

The link base is load-bearing: the CRT entry's position probe is
    ila $r2, link+entry+0x38 ; brsl $r126, .+0 ; sf $r126, $r2, $r126
so $r126 (delta) is 0 exactly when the module sits at its link base -- which is
where the img-200 WWS policy module stages it (LS 0x4000, entry 0x4000+entryOff).
A naive base-0 lift makes every absolute ila/lqa immediate wrong by the link
base, and the module-relative seed windows reject all of them, so the lift
silently misses whole functions. Lifting AT the link base (header excluded, so
the header's metadata words cannot masquerade as a function-pointer table) makes
every static address in the lifted C the staged local-store address.

Registration: spu_workload_dispatch_job stages C0DEC0DE images at LS 0, which is
NOT their link base, so that path cannot serve them (a 0x4000-linked binary's
absolute refs would all miss). The PM path is the real one: the policy module
GETs the image into LS 0x4000.. in 0x4000-byte bursts, the runtime's
[pm-jobmod] staging hook (spu_channels.c spu_overlay_note_get) FNV-hashes the
staged bytes and looks the image up here. The PM stages imageSize-0x20 bytes
(the image minus its 0x20-byte trailer -- verified against a live staging of
0x12540 bytes from a 0x12560-byte image), so each module registers under
fnv64(raw[:imageSize-0x20]) with its lifted CRT entry, tagged with the lift base
so the hook's resolver translation is exact:

    spu_workload_register_img_at(fnv64, <prefix>spu_func_<entry>, 210+i,
                                 LINK_BASE, name)

Vendor seed heuristics (first function at +0x30, ila+a link-register targets,
switch tables) are reused with their imm_base (absolute-window) mode, plus two
C0DEC0DE-specific seeders: delta-relocated pointer tables named by
`ila $rT, tbl ; a $rT, $rT, $r126` (the CRT's ctor/dtor walks dispatch through
them; no branch ever names their entries), and an explicit code/data boundary
(--code-end) derived from the const tail so data words that decode as branches
cannot seed phantom functions (5 `.word` failures on the mstream module without
it).

Usage:
    python lift_ms1_jobmods.py [--jobmods DIR] [--out DIR] [--register FILE]
                               [--register-fn NAME]
"""
import argparse, glob, hashlib, json, os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", "..", "vendor", "ps3recomp", "tools"))
sys.path.insert(0, TOOLS)
from wrap_spu_elf import wrap                       # noqa: E402
from lift_jobmods import manual_link_targets, switch_table_targets  # noqa: E402

LIFTER = os.path.join(TOOLS, "spu_lifter.py")
IMAGE_BASE = 210           # 200 is the wwsjob PM itself; jobmods must not share
                           # its id or spu_lookup dispatches the wrong program's
                           # function at the same LS address.


def fnv1a64(b):
    h = 1469598103934665603
    for x in b:
        h = ((h ^ x) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def parse_header(raw, path):
    """Validate the C0DEC0DE image header and return (entry_off, size, link)."""
    if len(raw) < 0x30:
        sys.exit(f"{path}: too small for a C0DEC0DE image header")
    entry_off, size, bss = struct.unpack_from(">III", raw, 0x10)
    link = struct.unpack_from(">I", raw, 0x28)[0]
    if raw[0x20:0x24] != b"\xC0\xDE\xC0\xDE":
        sys.exit(f"{path}: no C0DEC0DE marker at +0x20")
    if size != len(raw):
        sys.exit(f"{path}: header imageSize 0x{size:X} != file size 0x{len(raw):X}")
    if raw[0] not in (0x42, 0x43):
        sys.exit(f"{path}: leading word is not an ila marker")
    if link == 0 or link % 0x400 != 0:
        sys.exit(f"{path}: implausible link base 0x{link:X} at +0x28")
    return entry_off, size, link


def data_tail_boundary(raw, link, floor_addr, ptr_values=()):
    """Find the start of the trailing const/data region, as a link-base LS
    address, by scanning words from the image end backward while they are all
    "data-like": zeros, -1 sentinels, ascending byte ladders (prev-w ==
    0x04040404), shuffle masks, float constants, small integers that cannot be
    code addresses at this link base, or code pointers stored in a table
    (ptr_values: the CRT's ctor/dtor tables hold real function addresses, but
    they sit between -1 sentinels in the tail, so the surrounding data -- not
    the pointed-to code -- owns them). Real code is dense with non-constant
    instruction words, so the first code word walking back stops the scan.

    Returns 0 when no run of at least 0x40 bytes qualifies (no cap): the cap
    must never cut an address at or below floor_addr (the highest address any
    deliberate seed named)."""
    def data_like(w, prev):
        if w in (0, 0xFFFFFFFF, 0x80808080):
            return True
        if prev is not None and (prev - w) & 0xFFFFFFFF == 0x04040404:
            return True                      # 00010203/04050607/... ladder
        if not (w & 0x80000000) and 0x38000000 <= (w & 0x7F800000) <= 0x47000000:
            return True                      # float constants (~1.4e-3 .. 3e4)
        if w < link + 0x30:
            return True                      # cannot be code at this link base
        if w in ptr_values:
            return True                      # function pointer inside a table
        return False

    run_end = len(raw) & ~3
    i = run_end - 4
    prev = None
    while i >= 0x30:
        w = struct.unpack_from(">I", raw, i)[0]
        if not data_like(w, prev):
            break
        prev = w
        i -= 4
    run_start = i + 4
    if run_end - run_start >= 0x40:
        boundary = link + run_start
        if boundary > floor_addr:
            return boundary
    return 0


def relocated_table_targets(raw, link):
    """Entries of delta-relocated pointer tables. The CRT (and C++ code) walks
    tables of absolute-at-link-base code pointers reached via
        ila $rT, tbl ; a $rT, $rT, $r126   ($r126 = delta, 0 at the link base)
        lqd/rotqby <entry> ; a $r3, $r3, $r126 ; bisl $r0, $r3
    No branch or link-register pattern ever names the entries, so every code
    scanner misses them. Scan a bounded window around each ila-named table base
    for words that are plausible code addresses at the link base. A stray seed
    is harmless (spu_lifter only splits a function that really spans it); a
    missing ctor/dtor entry is a dispatch-to-nothing at run time."""
    out = set()
    for off in range(0x30, len(raw) - 8, 4):
        w = struct.unpack_from(">I", raw, off)[0]
        if (w >> 25) & 0x7F != 0x21:                      # ila $rT, i18
            continue
        imm = (w >> 7) & 0x3FFFF
        rt = w & 0x7F
        if not (link + 0x30 <= imm < link + len(raw)):
            continue
        w2 = struct.unpack_from(">I", raw, off + 4)[0]
        if (w2 >> 21) & 0x7FF != 0x0C0:                   # a $rT, $rT, $rX
            continue
        if (w2 & 0x7F) != rt or ((w2 >> 7) & 0x7F) != rt:
            continue
        fo = imm - link                                   # table file offset
        for o in range(max(0x30, fo - 0x10), min(len(raw), fo + 0x40), 4):
            v = struct.unpack_from(">I", raw, o)[0]
            if v % 4 == 0 and link + 0x30 <= v < link + len(raw):
                out.add(v)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobmods", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--register", default=None)
    ap.add_argument("--register-fn", default="ms1_jobmods_register_all")
    ap.add_argument("--meta", default=None,
                    help="jobmod_meta.json with stable registration ids and "
                         "pretty names (default: <jobmods>/../jobmod_meta.json). "
                         "Ids never renumber: live logs and the knowledge base "
                         "reference them; newly registrable modules append "
                         "after the highest assigned id and the file is "
                         "updated in place.")
    args = ap.parse_args()
    register_c = args.register or os.path.join(args.out, "jobmods_register.c")
    meta_path = args.meta or os.path.normpath(
        os.path.join(args.jobmods, "..", "jobmod_meta.json"))
    meta = {"ids": {}, "names": {}}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta.setdefault("ids", {}), meta.setdefault("names", {})

    mods = sorted(glob.glob(os.path.join(args.jobmods, "jobmod_*.bin")))
    if not mods:
        sys.exit(f"no jobmod_*.bin in {args.jobmods}")
    os.makedirs(args.out, exist_ok=True)
    manifest = []
    tmp_elf = os.path.join(args.out, "_tmp.elf")
    for path in mods:
        raw = open(path, "rb").read()
        name = os.path.splitext(os.path.basename(path))[0]
        reg_name = meta["names"].get(name, name)
        entry_off, image_size, link = parse_header(raw, path)
        entry = link + entry_off
        base = link + 0x30                     # code starts after the 0x30 hdr
        prefix = f"{name}_"
        outsub = os.path.join(args.out, name)

        seeds = {base}                                   # first function at +0x30
        seeds |= set(manual_link_targets(raw, imm_base=link))
        seeds |= set(switch_table_targets(raw, imm_base=link))
        tbl = set(relocated_table_targets(raw, link))
        seeds |= tbl
        code_end = data_tail_boundary(raw, link, max(seeds | {entry}), tbl)
        if code_end:
            seeds = {s for s in seeds if s < code_end}

        # Wrap MODULE-RELATIVE (PT_LOAD vaddr 0): --base is an additive ELF
        # load bias, applied before discovery. Relative branches, entry and
        # symbols use execution addresses; absolute instruction/table values
        # remain unchanged. An absolute-vaddr wrap plus this bias would still
        # place the image twice as high. e_entry is
        # likewise wrap-space: the image start (LS link) sits at -0x30 here
        # because the wrap payload starts at image+0x30, so an entryOff
        # passed raw lands 0x30 high and the true CRT entry never lifts
        # (undefined symbol in jobmods_register.c).
        elf = wrap(raw[0x30:image_size], base=0, entry=entry_off - 0x30)
        with open(tmp_elf, "wb") as f:
            f.write(elf)
        cmd = [sys.executable, LIFTER, "--auto-functions", tmp_elf,
               "--base", hex(base), "--symbol-prefix", prefix, "-o", outsub,
               "--source-name", "spu_recomp.c", "--header-name", "spu_recomp.h",
               "--extra-funcs", ",".join(hex(a) for a in sorted(seeds)),
               # undecodable .word slots are data-in-text (ASCII strings the
               # linker placed between functions): guarded, not blocking
               "--data-in-text"]
        if code_end:
            cmd += ["--code-end", hex(code_end)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAIL {name}\n{r.stderr}", file=sys.stderr)
            continue
        funcs = unsup = data_words = 0
        for line in r.stdout.splitlines():
            s = line.strip()
            if s.endswith("function(s) lifted"):
                funcs = int(s.split()[0])
            if "unsupported instruction(s)" in s:
                unsup = int(s.split()[0])
            if "data-in-text word(s)" in s:
                data_words = int(s.split()[0])
        manifest.append({"name": name, "reg_name": reg_name,
                         "prefix": prefix, "link_base": link,
                         "entry": entry, "image_size": image_size,
                         "code_end": code_end,
                         "staged_fnv": fnv1a64(raw[:image_size - 0x20]),
                         "funcs": funcs, "unsupported": unsup,
                         "data_words": data_words})
        flag = "  <-- UNSUPPORTED (left unregistered)" if unsup else ""
        print(f"  {name:40} [{reg_name}] funcs={funcs:3} unsup={unsup:3} "
              f"datawords={data_words:3} link=0x{link:X} "
              f"entry=0x{entry:X} code_end="
              f"{'0x%X' % code_end if code_end else '-'}{flag}")
    if os.path.exists(tmp_elf):
        os.remove(tmp_elf)

    with open(os.path.join(args.out, "jobmods_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    clean = [m for m in manifest if m["unsupported"] == 0]
    # Stable ids: meta ids win; new registrants append after the highest one.
    used = set(meta["ids"].values())
    nxt = max(used | {IMAGE_BASE - 1})
    for m in clean:
        if m["name"] in meta["ids"]:
            m["id"] = meta["ids"][m["name"]]
            continue
        nxt += 1
        while nxt in used:
            nxt += 1
        m["id"] = nxt
        meta["ids"][m["name"]] = nxt
        used.add(nxt)
        print(f"  new image id {nxt}: {m['name']} [{m['reg_name']}]")
    with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    L = []
    L.append("/* jobmods_register.c -- GENERATED by recomp/spu/lift_ms1_jobmods.py.")
    L.append(" * MS1's WWS job binaries (C0DEC0DE images, raw bytes under")
    L.append(" * the --jobmods dir, fingerprints in jobmods_manifest.json).")
    L.append(" * Each image is linked at the base declared at header +0x28")
    L.append(" * (0x4000) and the WWS policy module stages it right there, so")
    L.append(" * the lift uses those very addresses and the staging hook's")
    L.append(" * resolver needs no translation. Registered under the FNV-1a-64")
    L.append(" * of the staged span (imageSize-0x20 bytes): what")
    L.append(" * spu_overlay_note_get's [pm-jobmod] accumulator hashes.")
    L.append(" * Image ids are STABLE (jobmod_meta.json): live logs and the")
    L.append(" * knowledge base reference them; new modules append, never")
    L.append(" * renumber. Registration names are the module's real name when")
    L.append(" * identified (debug EBOOT symtab _binary_*_wwsjob_image_start),")
    L.append(" * else the hash stem. Undecodable .word slots are data-in-text")
    L.append(" * constants: guarded, not registration-blocking. */")
    L.append('#include "spu_workload.h"')
    L.append("")
    L.append("extern void spu_begin_image(int image_id);")
    L.append("")
    for m in clean:
        L.append(f"extern void {m['prefix']}spu_func_{m['entry']:08X}(spu_context*);")
        L.append(f"extern void {m['prefix']}spu_recomp_register(void);")
    L.append("")
    L.append(f"void {args.register_fn}(void)")
    L.append("{")
    for m in clean:
        img = m["id"]
        L.append(f"    spu_begin_image({img}); {m['prefix']}spu_recomp_register();")
        L.append(f"    spu_workload_register_img_at(0x{m['staged_fnv']:016X}ULL, "
                 f"{m['prefix']}spu_func_{m['entry']:08X}, {img}, "
                 f"0x{m['link_base']:X}u, \"{m['reg_name']}\");")
    L.append("}")
    L.append("")
    L.append(f"__attribute__((constructor)) static void {args.register_fn}_ctor(void)")
    L.append("{")
    L.append(f"    {args.register_fn}();")
    L.append("}")
    L.append("")
    with open(register_c, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    skipped = len(manifest) - len(clean)
    print(f"\nLifted {len(manifest)} module(s); registered {len(clean)} "
          f"({skipped} left unregistered: unsupported instructions -- the "
          f"interpreter keeps serving those); register: {register_c}")


if __name__ == "__main__":
    main()
