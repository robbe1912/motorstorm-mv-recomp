#!/usr/bin/env python3
"""lift_coverage.py -- constant targets of indirect branches in MS1's SPU job
modules, and the state of their lift.

A lifted module hands each indirect transfer (bi, biz, binz, bihz, bihnz, bisl)
to the run-time dispatcher. The dispatcher serves a target only when a lifted
function STARTS at that local-store address. When the branch register holds a
constant at the site, the target is one fixed address, so the lift can cover it
in advance. Without a lifted function there, the run time gives the job to the
interpreter.

`report` reads the image bytes and the generated tree. For each job module it
prints each indirect transfer whose target register holds a constant at the
site: the site, the target, and the lift state.

The report tracks values along decoded paths. A new entry starts with unknown
registers. The inventory depends on the entry set of the tree. Loads use the
initial image bytes, not live local store. The report does not count runtime
fallbacks or prove that every reachable target has a lifted function.

`diff` compares the generated C of two trees, function by function.
`list` prints the disassembly of an address range of one image.

Usage:
    python scripts/spu/lift_coverage.py [report] [--tree DIR] [--jobmods DIR]
                                         [--all] [--check] [--json FILE]
    python scripts/spu/lift_coverage.py diff OLD NEW [--check] [--all]
    python scripts/spu/lift_coverage.py list --image ID FIRST LAST [--tree DIR]
"""
import argparse
import bisect
import collections
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TOOLS = os.path.join(ROOT, "vendor", "ps3recomp", "tools")
sys.path.insert(0, TOOLS)
from spu_disasm import disassemble_spu  # noqa: E402
from find_spu_functions import (  # noqa: E402
    collect_computed_branch_targets, collect_duff_targets,
    collect_function_pointer_tables, collect_ila_continuation_targets,
    collect_jump_table_targets, collect_link_register_targets)
from lift_jobmods import manual_link_targets, switch_table_targets  # noqa: E402
from spu_lifter import compute_bi_r0_jumps, compute_link_returns  # noqa: E402

INDIRECT = ("bi", "biz", "binz", "bihz", "bihnz", "bisl")
UNCOND_DIRECT = ("br", "bra")
COND_DIRECT = ("brz", "brnz", "brhz", "brhnz")
CALLS = ("brsl", "brasl")
TERMINALS = ("stop", "stopd", "iret", ".word")
# Instructions whose first register operand is a source: they write no register.
NO_WRITE = frozenset((
    "stop", "stopd", "lnop", "nop", "sync", "syncc", "dsync", "iret",
    "bi", "biz", "binz", "bihz", "bihnz", "bih", "bihn", "binth",
    "br", "bra", "brz", "brnz", "brhz", "brhnz",
    "hbr", "hbra", "hbrr", "hbrp",
    "stqd", "stqa", "stqr", "stqx", "stqxb", "stqdi",
    "wrch", "mtspr", ".word",
))
# Arithmetic that builds word 0 of rt from known words or an immediate.
_ARITH = {
    "a": lambda x, y: x + y,          # rt = ra + rb
    "sf": lambda x, y: x - y,         # rt = ra - rb
    "ai": lambda x, y: x + y,         # rt = ra + i10
    "sfi": lambda x, y: y - x,        # rt = i10 - ra
}
MASK32 = 0xFFFFFFFF
FUNC = re.compile(r"^void (\w+)_spu_func_([0-9A-F]{8})\(spu_context\* ctx\) \{$")
TABLE = re.compile(r'^\s*\{\s*0x([0-9A-Fa-f]+)u,\s*\w+,\s*"\w+"\s*\},?\s*$')
TAIL = re.compile(r"^\s*\{ ctx->pc = 0x([0-9A-F]+); "
                  r"g_spu_trampoline_fn = \w+_spu_func_([0-9A-F]+); return; \}$")
DEFAULT_TREE = "build/generated/dx12-profile-verified-us"
DEFAULT_JOBMODS = "build/extracted/named/jobmods"


# --------------------------------------------------------------------------- #
# Image and instruction helpers
# --------------------------------------------------------------------------- #
def _ops(ins):
    return [t.strip() for t in ins.operands.split(",") if t.strip()]


def _reg(token):
    if token.startswith("$r") and token[2:].isdigit():
        return int(token[2:])
    return None


def _branch_target(ins):
    for t in reversed(_ops(ins)):
        if t.startswith("0x"):
            return int(t, 16)
    return None


def _target_register(ins):
    """The register that holds the target of an indirect transfer."""
    ops = _ops(ins)
    return _reg(ops[0] if ins.mnemonic == "bi" else ops[-1])


def parse_header(raw, path="<image>"):
    """Return (entry_off, link) of a C0DEC0DE job image."""
    if len(raw) < 0x30 or raw[0x20:0x24] != b"\xC0\xDE\xC0\xDE":
        raise ValueError(f"{path}: not a C0DEC0DE job image")
    entry_off = struct.unpack_from(">I", raw, 0x10)[0]
    link = struct.unpack_from(">I", raw, 0x28)[0]
    return entry_off, link


class Image:
    """One C0DEC0DE job image: its bytes, its link base and its disassembly."""

    def __init__(self, raw, link, name=""):
        self.name = name
        self.raw = raw
        self.link = link
        self.lo = link + 0x30          # first code address (after the header)
        self.hi = link + len(raw)      # end of the image in local store
        self.entry = link + struct.unpack_from(">I", raw, 0x10)[0]   # the job entry
        self.insns = disassemble_spu(raw[0x30:], self.lo)
        self.by_addr = {i.addr: i for i in self.insns}

    def word(self, addr):
        """Word 0 of the quadword that `lqa` reads at `addr`, or None."""
        off = (addr & ~0xF) - self.link
        if not 0 <= off <= len(self.raw) - 4:
            return None
        return struct.unpack_from(">I", self.raw, off)[0]


class Site:
    """An indirect transfer whose target register holds one constant."""

    __slots__ = ("addr", "mn", "reg", "target", "origin")

    def __init__(self, addr, mn, reg, target, origin):
        self.addr = addr
        self.mn = mn
        self.reg = reg
        self.target = target
        self.origin = origin


def _known_word(ins, st, img):
    """(word 0, origin) that `ins` writes to its first register operand, or
    (None, None). Only an immediate, a load from the image bytes and arithmetic
    on known words give a known word. `origin` names the instructions that
    built the word: (mnemonic, address[, source address | source origins])."""
    mn, ops = ins.mnemonic, _ops(ins)
    d = _reg(ops[0])
    at = (mn, ins.addr)
    if mn in ("ila", "il"):
        return int(ops[1], 0), at
    if mn == "ilh":                               # one halfword in both halves
        v = int(ops[1], 0) & 0xFFFF
        return (v << 16) | v, at
    if mn == "ilhu":
        return (int(ops[1], 0) & 0xFFFF) << 16, at
    if mn == "iohl" and d in st:                  # or into the low halfword
        v, org = st[d]
        return v | (int(ops[1], 0) & 0xFFFF), ("iohl", ins.addr, org)
    if mn in ("lqa", "lqr"):                      # load from the staged bytes
        a = int(ops[1], 0)
        w = img.word(a)
        return (None, None) if w is None else (w, (mn, ins.addr, a))
    if mn in ("a", "sf"):
        ra, rb = _reg(ops[1]), _reg(ops[2])
        if ra in st and rb in st:
            return (_ARITH[mn](st[ra][0], st[rb][0]),
                    (mn, ins.addr, st[ra][1], st[rb][1]))
    if mn in ("ai", "sfi"):
        ra = _reg(ops[1])
        if ra in st:
            return (_ARITH[mn](st[ra][0], int(ops[2], 0)),
                    (mn, ins.addr, st[ra][1]))
    if mn == "fsmbi":                             # one bit selects one byte
        bits = int(ops[1], 0) & 0xFFFF
        word = sum(0xFF << (24 - 8 * i) for i in range(4) if bits & (1 << (15 - i)))
        return word, at
    return None, None


def _step(ins, st, img):
    """Register state after `ins`. A state maps a register number to
    (word 0, origin). A register that is not in the state has an unknown word."""
    mn, ops = ins.mnemonic, _ops(ins)
    st = dict(st)
    d = _reg(ops[0]) if ops else None
    if mn in CALLS:                               # rt = return address
        if d is not None:
            st[d] = ((ins.addr + 4) & MASK32, (mn, ins.addr))
        return st
    if mn in NO_WRITE or d is None:
        return st
    try:
        word, org = _known_word(ins, st, img)
    except (IndexError, ValueError):
        word = org = None
    if word is None:
        st.pop(d, None)
    else:
        st[d] = (word & MASK32, org)
    return st


def _origin_text(origin):
    mn, addr = origin[0], origin[1]
    if mn in ("lqa", "lqr"):
        return f"{mn}@0x{addr:X}(word@0x{origin[2]:X})"
    inner = [o for o in origin[2:] if isinstance(o, tuple)]
    if inner:
        return f"{mn}@0x{addr:X}(" + ", ".join(_origin_text(o) for o in inner) + ")"
    return f"{mn}@0x{addr:X}"


def _idiom(origin):
    """The load instructions at the root of an origin, for example 'ila' or
    'a+ila+il'."""
    out = {origin[0]}
    for o in origin[2:]:
        if isinstance(o, tuple):
            out.update(_idiom(o))
    return "+".join(sorted(out))


# --------------------------------------------------------------------------- #
# Constant propagation
# --------------------------------------------------------------------------- #
def entry_addresses(img):
    """Addresses at which control can arrive with unknown register contents.

    Every direct branch target is one. So is every address that the vendor
    discovery (find_spu_functions.py) or the jobmod seeder (lift_jobmods.py)
    names as a function seed: an indirect transfer with a run-time target can
    go to each of them."""
    out = {img.entry, img.lo}
    for ins in img.insns:
        if ins.mnemonic in UNCOND_DIRECT + COND_DIRECT + CALLS:
            t = _branch_target(ins)
            if t is not None:
                out.add(t)
    lo, hi, code = img.lo, img.hi, img.raw[0x30:]
    out |= collect_link_register_targets(img.insns)
    out |= collect_computed_branch_targets(img.insns)
    out |= collect_jump_table_targets(img.insns, code, lo, hi)
    out |= collect_ila_continuation_targets(img.insns, lo, hi)
    out |= collect_duff_targets(img.insns, lo, hi)
    out |= collect_function_pointer_tables(
        img.raw, [{"type": 1, "off": 0x30, "vaddr": lo, "filesz": len(code)}],
        lo, hi, img.by_addr)
    out |= set(manual_link_targets(img.raw, imm_base=img.link))
    out |= set(switch_table_targets(img.raw, imm_base=img.link))
    return out


def analyze(img, extra_entries=()):
    """Return ({address: Site or None}, reached) for one image.

    The dict holds each indirect transfer that a path reaches. The value is a
    Site when the target register holds one constant value on every path to the
    transfer, else None. `reached` is the set of instructions that the job entry
    reaches through direct branches and through the constant indirect transfers;
    it is a lower bound, because a transfer with a run-time target adds edges.
    `extra_entries` adds entries with unknown registers (the lifted function
    starts of a tree, or the seeds of a driver run)."""
    by = img.by_addr
    entries = {a for a in entry_addresses(img) | set(extra_entries) if a in by}
    start = img.entry
    state = {a: {} for a in entries}
    settled = {}
    reached = {start}
    propagated = set()
    sites = {}
    work = collections.deque(sorted(entries))

    def drain():
        while work:
            a = work.popleft()
            st = state[a]
            live = a in reached
            if settled.get(a) == st and (not live or a in propagated):
                continue
            settled[a] = st
            if live:
                propagated.add(a)
            ins = by[a]
            mn = ins.mnemonic
            after = st
            succs = ()
            if mn in UNCOND_DIRECT:
                t = _branch_target(ins)
                succs = (t,) if t is not None else ()
            elif mn in COND_DIRECT:
                t = _branch_target(ins)
                succs = ((t,) if t is not None else ()) + (a + 4,)
            elif mn in CALLS:
                t = _branch_target(ins)
                succs = ((t,) if t is not None else ()) + (a + 4,)
                after = _step(ins, st, img)
            elif mn in INDIRECT:
                r = _target_register(ins)
                site = None
                if r in st:
                    value, org = st[r]
                    site = Site(a, mn, r, value, org)
                    if value in by:
                        succs += (value,)
                sites[a] = site
                if mn != "bi":                    # conditional and bisl continue
                    succs += (a + 4,)
                after = _step(ins, st, img)
            elif mn in TERMINALS:
                pass
            else:
                if a + 4 in by:
                    succs = (a + 4,)
                after = _step(ins, st, img)
            for s in succs:
                if s not in by:                  # a target outside the image
                    continue
                if s not in state:
                    state[s] = after
                    work.append(s)
                else:
                    merged = {k: v for k, v in state[s].items()
                              if after.get(k, (None,))[0] == v[0]}
                    if merged != state[s]:
                        state[s] = merged
                        work.append(s)
                if live and s not in reached:
                    reached.add(s)
                    work.append(s)

    drain()
    # An instruction that no path reached can be the target of a transfer with a
    # run-time target. It is an entry with unknown registers.
    for a in sorted(by):
        if a not in state:
            state[a] = {}
            work.append(a)
    drain()
    return sites, reached


def constant_branch_targets(raw, link, entries=()):
    """Local-store addresses of one image that a constant indirect transfer can
    reach. `lift_ms1_jobmods.py` seeds each of them as a function bound.
    `entries` are addresses that control can enter with unknown registers."""
    img = Image(raw, link)
    sites, _ = analyze(img, entries)
    return sorted({s.target for s in sites.values()
                   if s and img.lo <= s.target < img.hi and s.target % 4 == 0})


# --------------------------------------------------------------------------- #
# Generated tree
# --------------------------------------------------------------------------- #
def local_tree():
    """Generated tree that config/local.json selects, else the default tree."""
    path = os.path.join(ROOT, "config", "local.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        g = c.get("generated")
        if g:
            return g if os.path.isabs(g) else os.path.join(ROOT, g)
    return os.path.join(ROOT, DEFAULT_TREE)


def image_ids():
    """{job module name: image id} from the committed stable ids."""
    with open(os.path.join(HERE, "jobmod_meta.json"), encoding="utf-8") as f:
        return json.load(f)["ids"]


def read_functions(path):
    """{start address: body lines} of the lifted functions in one spu_recomp.c."""
    funcs = {}
    lines = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            m = FUNC.match(line)
            if m:
                lines = []
                funcs.setdefault(int(m.group(2), 16), lines)
            elif lines is not None:
                if line == "}":
                    lines = None
                else:
                    lines.append(line)
    return funcs


def function_starts(path):
    """Start addresses in the registration table of one spu_recomp.c."""
    starts = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TABLE.match(line)
            if m:
                starts.append(int(m.group(1), 16))
    return sorted(set(starts))


def tail_address(line):
    """Address of the fall-through transfer when `line` is one, else None."""
    m = TAIL.match(line)
    return int(m.group(1), 16) if m else None


def _containing(starts, addr):
    """Start of the lifted function that contains `addr`, or None."""
    i = bisect.bisect_right(starts, addr) - 1
    return starts[i] if i >= 0 else None


def classify(old, new, s):
    """'same', 'split' or 'changed' for the old function that starts at `s`.

    A split keeps every old line, in order, and adds only the transfer from one
    piece to the next piece. Each next piece starts at a new function address."""
    o = old[s]
    if s not in new:
        return "removed", []
    if old[s] == new[s]:
        return "same", [s]
    pieces = []
    pos, cur = 0, s
    while True:
        n = new[cur]
        t = tail_address(n[-1]) if n else None
        split_here = t is not None and t > cur and t not in old and t in new
        body = n[:-1] if split_here else n
        if o[pos:pos + len(body)] != body:
            return "changed", pieces
        pos += len(body)
        pieces.append(cur)
        if not split_here:
            break
        cur = t
    return ("split" if pos == len(o) else "changed"), pieces


def data_tail(raw, link, code_end):
    """First address of the trailing const/data region of one image: the value
    that the manifest records, else what the driver's rule computes."""
    if code_end:
        return code_end
    import lift_ms1_jobmods as driver
    entry_off, _ = parse_header(raw)
    return driver.data_tail_boundary(raw, link, link + entry_off, ()) or link + len(raw)


def site_reasons(site, img, starts, br0, linkret, tail):
    """(form, reasons) for one constant site.

    `form` is how the lift translates the site: "indirect" (the dispatcher
    serves the target), "return" (a host return: the target is never served),
    "call" (bisl) or "none" (no lifted function contains the site). `reasons`
    lists why the target is not covered; an empty list means covered."""
    a, t = site.addr, site.target
    if site.mn == "bisl":
        form = "call"
    elif _containing(starts, a) is None:
        form = "none"
    elif (site.reg == 0 and a not in br0) or a in linkret:
        form = "return"
    else:
        form = "indirect"
    reason = {"none": "site-not-lifted", "return": "site-is-host-return"}.get(form)
    reasons = [reason] if reason else []
    if not img.lo <= t < img.hi or t % 4:
        reasons.append("target-outside-image")
    elif t >= tail:
        reasons.append("target-in-data-tail")
    elif form != "return" and t not in starts:
        holder = _containing(starts, t)
        reasons.append(f"target-not-lifted-inside-0x{holder:X}" if holder
                       else "target-not-lifted-gap")
    return form, reasons


def report(args):
    tree = os.path.abspath(args.tree or local_tree())
    jobmods = os.path.abspath(args.jobmods or os.path.join(ROOT, DEFAULT_JOBMODS))
    spu = os.path.join(tree, "spu")
    with open(os.path.join(spu, "jobmods_manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    ids = image_ids()
    if args.check:
        expected = {name for name in ids if name.startswith("jobmod_")}
        modules = [m for m in manifest if m["name"].startswith("jobmod_")]
        found = collections.Counter(m["name"] for m in modules)
        if found != collections.Counter(expected):
            raise SystemExit("incomplete or duplicate job module inventory")
        if any(m["unsupported"] or not m["funcs"] for m in modules):
            raise SystemExit("job module has no lift or contains unsupported instructions")
    result = []
    bad_tail = 0
    for m in manifest:
        name = m["name"]
        if not name.startswith("jobmod_"):
            continue
        path = os.path.join(jobmods, name + ".bin")
        with open(path, "rb") as f:
            raw = f.read()
        _, link = parse_header(raw, path)
        img = Image(raw, link, name)
        c_path = os.path.join(spu, name, "spu_recomp.c")
        starts = function_starts(c_path)
        if args.check and (len(starts) != m["funcs"] or img.entry not in starts):
            raise SystemExit(f"{name}: registration table does not match the lift")
        bounds = list(zip(starts, starts[1:] + [img.hi]))
        sites, reached = analyze(img, starts)
        br0 = compute_bi_r0_jumps(img.insns, bounds)
        linkret = compute_link_returns(img.insns, bounds)
        tail = data_tail(raw, link, m.get("code_end", 0))
        rows = []
        for a in sorted(sites):
            site = sites[a]
            if site is None:
                continue
            form, reasons = site_reasons(site, img, starts, br0, linkret, tail)
            rows.append({"site": a, "mn": site.mn, "reg": site.reg, "target": site.target,
                         "idiom": _idiom(site.origin), "origin": _origin_text(site.origin),
                         "form": form, "reasons": reasons, "reached": a in reached})
        in_tail = [s for s in starts if s >= tail]
        bad_tail += len(in_tail)
        unit = {"name": name, "id": ids.get(name), "functions": len(starts),
                "code_end": tail, "functions_in_data_tail": in_tail,
                "indirect": sum(1 for i in img.insns if i.mnemonic in INDIRECT),
                "rows": rows}
        result.append(unit)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"tree": tree, "units": result}, f, indent=1)
            f.write("\n")
    total = collections.Counter()
    for u in result:
        miss = [r for r in u["rows"] if r["reasons"]]
        reasons = collections.Counter(x for r in miss for x in r["reasons"])
        idioms = collections.Counter(r["idiom"] for r in u["rows"])
        print(f"{u['id']} {u['name']}: functions={u['functions']} indirect={u['indirect']} "
              f"constant={len(u['rows'])} covered={len(u['rows']) - len(miss)} miss={len(miss)} "
              f"reached-miss={sum(1 for r in miss if r['reached'])}")
        print("    idioms: " + " ".join(f"{k}={v}" for k, v in sorted(idioms.items())))
        if reasons:
            print("    reasons: " + " ".join(f"{k}={v}" for k, v in sorted(reasons.items())))
        if u["functions_in_data_tail"]:
            print(f"    lifted functions in the data tail: "
                  + " ".join("0x%X" % s for s in u["functions_in_data_tail"]))
        for r in u["rows"]:
            if r["reasons"] or args.all:
                print(f"    site 0x{r['site']:05X} {r['mn']:<5} $r{r['reg']:<3} -> 0x{r['target']:05X} "
                      f"{r['idiom']:<14} {r['origin']:<48} form={r['form']:<8} "
                      f"{'ok' if not r['reasons'] else '+'.join(r['reasons'])}"
                      f"{'' if r['reached'] else ' (not reached)'}")
        total["constant"] += len(u["rows"])
        total["miss"] += len(miss)
        total["functions_in_data_tail"] += len(u["functions_in_data_tail"])
    print(f"total: constant={total['constant']} miss={total['miss']} "
          f"functions_in_data_tail={total['functions_in_data_tail']} tree={tree}")
    failed = total["miss"] > 0 or bad_tail > 0
    if args.check:
        print("CHECK FAILED" if failed else "CHECK PASSED")
        return 1 if failed else 0
    return 0


def diff(args):
    """Compare the generated C of every job module in the old manifest."""
    failed = False
    grand = collections.Counter()
    with open(os.path.join(args.old, "spu", "jobmods_manifest.json"), encoding="utf-8") as f:
        names = [m["name"] for m in json.load(f) if m["name"].startswith("jobmod_")]
    if not names:
        raise SystemExit("the old manifest contains no job modules")
    with open(os.path.join(args.new, "spu", "jobmods_manifest.json"), encoding="utf-8") as f:
        new_names = {m["name"] for m in json.load(f)}
    missing = set(names) - new_names
    if missing:
        raise SystemExit("missing job modules: " + ", ".join(sorted(missing)))
    for name in names:
        old = read_functions(os.path.join(args.old, "spu", name, "spu_recomp.c"))
        new = read_functions(os.path.join(args.new, "spu", name, "spu_recomp.c"))
        if not old or not new:
            raise SystemExit(f"{name}: no function bodies found")
        kinds = collections.Counter()
        for s in sorted(old):
            kind, pieces = classify(old, new, s)
            kinds[kind] += 1
            if kind in ("split", "changed", "removed") and (args.all or kind != "split"):
                print(f"  {name} 0x{s:05X} {kind}"
                      + (" -> " + " ".join("0x%X" % p for p in pieces) if pieces else ""))
        added = sorted(set(new) - set(old))
        kinds["added"] = len(added)
        if added:
            shown = added if args.all else added[:24]
            print(f"  {name} added {len(added)}: "
                  + " ".join("0x%X" % a for a in shown) + (" ..." if len(shown) != len(added) else ""))
        print(f"{name}: same={kinds['same']} split={kinds['split']} changed={kinds['changed']} "
              f"removed={kinds['removed']} added={kinds['added']}")
        grand.update(kinds)
        failed = failed or kinds["changed"] > 0 or kinds["removed"] > 0
    print(f"total: same={grand['same']} split={grand['split']} changed={grand['changed']} "
          f"removed={grand['removed']} added={grand['added']}")
    if args.check:
        print("CHECK FAILED" if failed else "CHECK PASSED")
        return 1 if failed else 0
    return 0


def list_range(args):
    """Print the disassembly of one address range of one image."""
    name = next(n for n, i in image_ids().items() if i == args.image and n.startswith("jobmod_"))
    jobmods = os.path.abspath(args.jobmods or os.path.join(ROOT, DEFAULT_JOBMODS))
    with open(os.path.join(jobmods, name + ".bin"), "rb") as f:
        raw = f.read()
        _, link = parse_header(raw, name)
        img = Image(raw, link, name)
    starts = function_starts(os.path.join(args.tree or local_tree(), "spu", name, "spu_recomp.c")) \
        if not args.raw else []
    bounds = list(zip(starts, starts[1:] + [img.hi]))
    br0 = compute_bi_r0_jumps(img.insns, bounds) if starts else set()
    linkret = compute_link_returns(img.insns, bounds) if starts else set()
    sites, reached = analyze(img, starts)
    for a in range(args.first & ~3, args.last + 1, 4):
        ins = img.by_addr.get(a)
        if ins is None:
            break
        marks = []
        if a in starts:
            marks.append("FUNC")
        if a in sites:
            s = sites[a]
            marks.append("const->0x%X (%s)" % (s.target, _origin_text(s.origin)) if s else "indirect")
        if a in br0:
            marks.append("bi-r0-jump")
        if a in linkret:
            marks.append("link-return")
        if a in reached:
            marks.append("reached")
        print(f"{ins}{'  ; ' + ' '.join(marks) if marks else ''}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("report", help="constant indirect targets and their lift state (default)")
    r.add_argument("--tree", help=f"generated tree (default: config/local.json, else {DEFAULT_TREE})")
    r.add_argument("--jobmods", help=f"directory of jobmod_*.bin (default: {DEFAULT_JOBMODS})")
    r.add_argument("--all", action="store_true", help="print every constant site")
    r.add_argument("--check", action="store_true", help="exit 1 on a miss or on a function in the data tail")
    r.add_argument("--json", help="also write the full result to this file")
    d = sub.add_parser("diff", help="compare the generated C of two trees")
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("--check", action="store_true", help="exit 1 when an old function changed or was removed")
    d.add_argument("--all", action="store_true", help="print each split and each added function")
    l = sub.add_parser("list", help="disassemble an address range")
    l.add_argument("--image", type=int, required=True, help="image id, for example 210")
    l.add_argument("first", type=lambda x: int(x, 0))
    l.add_argument("last", type=lambda x: int(x, 0))
    l.add_argument("--tree", help="generated tree whose function starts mark the listing")
    l.add_argument("--jobmods", help="directory of jobmod_*.bin")
    l.add_argument("--raw", action="store_true", help="no tree marks: only the disassembly")
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-"):
        argv = ["report"] + argv
    args = p.parse_args(argv)
    if args.cmd == "report":
        return report(args)
    if args.cmd == "diff":
        return diff(args)
    return list_range(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
