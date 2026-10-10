"""Stage-time report for issue #11: load time by resource and job boundary.

Reads one owned run directory (scripts/run.py --loadtime-trace) and prints a
markdown table of stage durations between observed boundaries, with per-resource
subtotals (file I/O, decryption, SPU jobs, waits) inside each stage.

Usage: python scripts/analysis/loadtime_report.py temp/runs/<RUN> [--origin first-event]

Boundaries (each named stage runs from the previous boundary to this one):
  boot            first traced event (VM allocation)
  elf             ELF loaded into guest memory
  services        HLE/syscall/filesystem registration complete
  entry           guest entry point dispatched
  press <mask>    observed pad press (mask + poll count); user-acked input
  first-frame     first row in frames.csv (first presented frame)
  last-event      final trace event (kill/exit flush)

All times are microseconds since the first traced event unless --origin is
given. Waits are guest-requested sleeps/event blocking, counted separately from
useful work; the trace itself is observer-only and adds one line per event.
"""
import argparse, json
from collections import defaultdict
from pathlib import Path

PRESS_MASKS = {0x0008: 'START', 0x4000: 'CROSS', 0x0010: 'UP', 0x0020: 'RIGHT', 0x0040: 'DOWN', 0x0080: 'LEFT'}

def parse_detail(text):
    out = {}
    for part in text.split():
        if '=' in part:
            k, v = part.split('=', 1)
            out[k] = v
    return out

def load_events(run):
    path = run / 'loadtime.jsonl'
    if not path.is_file():
        raise SystemExit(f'No loadtime.jsonl in {run}')
    events = []
    with path.open(encoding='utf-8', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            e['_detail'] = parse_detail(e.get('detail', ''))
            events.append(e)
    if not events:
        raise SystemExit('loadtime.jsonl contained no events')
    return events

def boundaries(run, events):
    origin = events[0]['us']
    marks = [('boot', origin, 'VM alloc')]
    seen = set()
    for e in events:
        k, us = e['kind'], e['us']
        if k == 'elf_loaded' and 'elf' not in seen:
            seen.add('elf'); marks.append(('elf', us, 'ELF mapped'))
        elif k == 'services_ready' and 'svc' not in seen:
            seen.add('svc'); marks.append(('services', us, 'HLE+FS+syscalls registered'))
        elif k == 'entry_dispatch' and 'entry' not in seen:
            seen.add('entry'); marks.append(('entry', us, 'guest entry dispatched'))
        elif k == 'pad_press':
            mask = int(e['_detail'].get('mask', '0'), 0) & 0xFFFF
            polls = e['_detail'].get('polls', '?')
            names = '+'.join(nm for bit, nm in PRESS_MASKS.items() if mask & bit) or hex(mask)
            marks.append((f'press {names}', us, f'pad ack mask={hex(mask)} polls={polls} tid={e.get("tid")}'))
    frames = run / 'frames.csv'
    if frames.is_file():
        first = None
        for line in frames.open(encoding='utf-8', errors='replace'):
            parts = line.split(',')
            if parts and parts[0].replace('.', '', 1).isdigit():
                first = float(parts[0]); break
        if first is not None:
            marks.append(('first-frame', origin + int(first * 1e6), 'frames.csv row 1'))
    marks.sort(key=lambda m: m[1])
    return origin, marks

def stage_totals(events, lo, hi):
    t = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))
    read_by_fd = {}
    fd_path = {}
    for e in events:
        if not lo <= e['us'] <= hi:
            continue
        k = e['kind']; d = e['_detail']
        if k == 'fs_read':
            fd = int(d.get('fd', '-1'))
            got = float(d.get('got', 0)); dur = float(d.get('dur_us', 0))
            t['fs']['read_us'] += dur; counts['fs']['reads'] += 1
            read_by_fd[fd] = read_by_fd.get(fd, 0) + got
        elif k == 'fs_open':
            fd = int(d.get('fd', '-1')); fd_path[fd] = d.get('path', '?')
            counts['fs']['opens'] += 1
        elif k == 'fs_stat':
            counts['fs']['stats'] += 1
        elif k in ('fs_sdata_decrypt', 'fs_edat_decrypt'):
            t['fs']['decrypt_us'] += float(d.get('dur_us', 0)); counts['fs']['decrypts'] += 1
        elif k in ('spu_task_run', 'spu_async', 'spu_dispatch', 'spurs_job'):
            t['spu']['run_us'] += float(d.get('dur_us', 0)); counts['spu'][k] += 1
        elif k == 'wait_sleep':
            t['wait'][k] += float(d.get('sec', 0)) * 1e6
            counts['wait'][k] += 1
        elif k in ('wait_usleep', 'wait_event'):
            t['wait'][k] += float(d.get('dur_us', d.get('usec', d.get('timeout', 0))))
            counts['wait'][k] += 1
        elif k == 'havok_raw_ctor':
            counts['havok']['raw_ctors'] += 1
        elif k == 'spu_dispatch' or k == 'boot' or k in ('fs_close', 'fs_open_fail'):
            pass
    bytes_total = sum(read_by_fd.values())
    files = sorted(((read_by_fd.get(fd, 0), fd_path.get(fd, f'fd{fd}')) for fd in read_by_fd), reverse=True)
    return t, counts, bytes_total, files

def fmt(us):
    if us >= 1e6:
        return f'{us/1e6:.2f}s'
    if us >= 1e3:
        return f'{us/1e3:.1f}ms'
    return f'{us:.0f}us'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run', type=Path)
    ap.add_argument('--top', type=int, default=5, help='top files per stage')
    args = ap.parse_args()
    run = args.run
    events = load_events(run)
    origin, marks = boundaries(run, events)
    end_us = events[-1]['us']
    print(f'# Load-stage report: {run.name}')
    print(f'Events: {len(events)}; trace span: {fmt(end_us-origin)}; boundaries: {len(marks)}')
    print()
    print('| Stage boundary | t (from boot) | Stage Δ | fs read | decrypt | SPU job | waits | note |')
    print('|---|---|---|---|---|---|---|---|')
    prev_name, prev_us = '(run start)', origin
    for name, us, note in marks:
        t, counts, nbytes, files = stage_totals(events, prev_us, us)
        fs_read = fmt(t['fs']['read_us']); dec = fmt(t['fs']['decrypt_us'])
        spu = fmt(t['spu']['run_us'])
        wait_sum = sum(t['wait'].values())
        waits = fmt(wait_sum)
        print(f'| {name} | {fmt(us-origin)} | {fmt(us-prev_us)} | {nbytes/1048576:.1f}MB in {fs_read} | {dec} ({counts["fs"]["decrypts"]}) | {spu} ({sum(counts["spu"].values())} runs) | {waits} | {note} |')
        prev_name, prev_us = name, us
    # Tail: after final boundary to last event
    if end_us > prev_us:
        t, counts, nbytes, files = stage_totals(events, prev_us, end_us)
        wait_sum = sum(t['wait'].values())
        print(f'| (tail after {prev_name}) | {fmt(end_us-origin)} | {fmt(end_us-prev_us)} | {nbytes/1048576:.1f}MB in {fmt(t["fs"]["read_us"])} | {fmt(t["fs"]["decrypt_us"])} ({counts["fs"]["decrypts"]}) | {fmt(t["spu"]["run_us"])} ({sum(counts["spu"].values())} runs) | {fmt(wait_sum)} | to last event |')
    print()
    print('## Top files per stage')
    prev_us = origin
    for name, us, note in marks:
        t, counts, nbytes, files = stage_totals(events, prev_us, us)
        if files:
            top = ', '.join(f'{p} ({b/1048576:.1f}MB)' for b, p in files[:args.top])
            print(f'- **{name}** ({fmt(us-prev_us)}): {top}')
        prev_us = us
    # Whole-run totals
    t, counts, nbytes, files = stage_totals(events, origin, end_us)
    print()
    print('## Whole-run totals (trace span)')
    print(f'- Guest file reads: {counts["fs"]["reads"]} reads, {nbytes/1048576:.1f}MB, {fmt(t["fs"]["read_us"])} in cellFsRead')
    print(f'- Decryption (sdata/edat): {counts["fs"]["decrypts"]} files, {fmt(t["fs"]["decrypt_us"])}')
    spu_runs = sum(counts['spu'].values())
    print(f'- SPU job dispatches: {spu_runs} ({dict(counts["spu"]) or "none"}), {fmt(t["spu"]["run_us"])}')
    for wk, wv in sorted(t['wait'].items()):
        print(f'- Waits {wk}: {counts["wait"][wk]} calls, {fmt(wv)}')
    print(f'- Havok raw constructions observed: {counts["havok"]["raw_ctors"]}')
    # Resource sampler summary
    res = run / 'resources.jsonl'
    if res.is_file():
        rows = [json.loads(l) for l in res.open(encoding='utf-8', errors='replace') if l.strip()]
        if rows:
            def col(key):
                vals = [r[key] for r in rows if r.get(key, -1) != -1]
                return vals
            cpu = col('cpu_percent'); thr = col('threads'); io = col('io_read_bytes')
            line = f'- Host sampler ({len(rows)} samples every ~2s): '
            if cpu: line += f'guest CPU mean {sum(cpu)/len(cpu):.0f}% (max {max(cpu):.0f}%); '
            if thr: line += f'threads {min(thr)}..{max(thr)}; '
            if io and len(io) > 1:
                rate = (io[-1]-io[0])/(rows[-1]['elapsed']-rows[0]['elapsed'] or 1)
                line += f'process disk read {rate/1048576:.1f}MB/s avg ({(io[-1]-io[0])/1048576:.0f}MB total)'
            print(line)

if __name__ == '__main__':
    main()
