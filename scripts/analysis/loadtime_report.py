"""Report observed load boundaries; no critical-path or minimum-FPS inference.

Completed calls are assigned by their event timestamp. Wait intervals use measured
entry/return times, including host/probe overhead. Concurrent/nested samples overlap.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

SPU_KINDS = ('spu_task_run', 'spu_async', 'spu_dispatch', 'spurs_job')


def parse_detail(text):
    matches = list(re.finditer(r'(?:^| )([A-Za-z_][A-Za-z_0-9]*)=', text))
    return {m[1]: text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip()
            for i, m in enumerate(matches)}


def load_events(run, legacy=False):
    path = run / 'loadtime.jsonl'
    events = []
    with path.open(encoding='utf-8') as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            if legacy:
                line = re.sub(r'"kind":""', '"kind":"', line)
            try:
                e = json.loads(line)
                if legacy:
                    e['kind'] = e.get('kind', '').strip('"')
                if type(e.get('t_us')) is not int or e['t_us'] < 0:
                    raise ValueError('t_us must be a nonnegative integer')
                if not isinstance(e.get('kind'), str) or not e['kind']:
                    raise ValueError('kind must be a nonempty string')
                if not isinstance(e.get('detail', ''), str):
                    raise ValueError('detail must be a string')
                if events and e['t_us'] < events[-1]['us']:
                    raise ValueError('trace timestamps moved backwards')
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise ValueError(f'{path}:{line_no}: {exc}') from exc
            e['us'] = e['t_us']
            e['_detail'] = parse_detail(e.get('detail', ''))
            events.append(e)
    if not events:
        raise ValueError(f'{path}: empty trace')
    return events


def boundaries(run, events):
    origin = events[0]['us']
    marks = [('trace-start', origin, 'observer anchor; VM allocation may precede it')]
    seen = set()
    stages = {'elf_loaded': 'elf', 'services_ready': 'services', 'entry_dispatch': 'entry'}
    for e in events:
        k, us, d = e['kind'], e['us'], e['_detail']
        stage = d.get('stage') if k == 'boot' else k
        if stage in stages and stage not in seen:
            seen.add(stage)
            marks.append((stages[stage], us, 'emitted boot boundary'))
        elif k == 'first_present' and k not in seen:
            seen.add(k)
            marks.append(('first-present', us, 'same trace clock; content unverified'))
        elif k == 'pad_press':
            marks.append(('press ' + d.get('mask', '?'), us, 'PAD_FILE consumed; screen identity needs input log'))
        elif k == 'havok_stage' and d.get('stage') == 'fatal177' and 'fatal' not in seen:
            seen.add('fatal')
            marks.append(('Havok fatal 177', us, 'fatal observer boundary; cause unresolved'))
    marks.sort(key=lambda x: x[1])
    return origin, marks


def wait_union(events, lo, hi, tid=None):
    """Union of measured returned syscall intervals, clipped to [lo,hi)."""
    spans = []
    for e in events:
        if not (e['kind'].startswith('wait_') and e['kind'].endswith('_end')):
            continue
        if tid is not None and e.get('tid') != tid:
            continue
        d = e['_detail']
        start, end = int(d['start_us']), int(d['end_us'])
        if end < start:
            raise ValueError('wait return precedes entry')
        a, b = max(lo, start), min(hi, end)
        if b > a:
            spans.append((a, b))
    total, edge = 0, lo
    for a, b in sorted(spans):
        total += max(0, b - max(a, edge))
        edge = max(edge, b)
    return total


def stage_totals(events, lo, hi):
    durations, counts = defaultdict(int), defaultdict(int)
    fd_paths, reads = {}, defaultdict(int)
    for e in events:
        if e['us'] >= hi:
            break
        k, d = e['kind'], e['_detail']
        if k == 'fs_open':
            fd_paths[int(d['fd'])] = e.get('path', f'<fd {d["fd"]}: unstructured legacy path, opened at {e["us"]} us>')
        elif k == 'fs_close':
            fd_paths.pop(int(d['fd']), None)
        if e['us'] < lo:
            continue
        counts[k] += 1
        if k in ('fs_read', 'fs_sdata_decrypt', 'fs_edat_decrypt') + SPU_KINDS:
            durations[k] += int(d.get('dur_us', 0))
        if k == 'fs_read':
            fd = int(d['fd'])
            reads[fd_paths.get(fd, f'<fd {fd}: open not observed>')] += int(d.get('got', 0))
    return durations, counts, sum(reads.values()), sorted(((v, k) for k, v in reads.items()), reverse=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run', type=Path)
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--legacy', action='store_true', help='Explicit conversion of old malformed kind labels; results remain historical')
    args = ap.parse_args()
    events = load_events(args.run, args.legacy)
    origin, marks = boundaries(args.run, events)
    end = events[-1]['us']
    truncated = any(e['kind'] == 'trace_truncated' for e in events)
    print(f'Load-stage report: {args.run.name}; events={len(events)}; span={(end-origin)/1e6:.3f}s')
    print('Observed intervals include probe overhead; concurrent/nested samples overlap.')
    print('Interpreter/PPU work is not fully covered. No bottleneck, useful-work residual or FPS verdict follows.')
    if args.legacy:
        print('LEGACY CONVERSION enabled; historical observations only.')
    if truncated:
        print('INCOMPLETE: trace event budget exhausted.')
    print('| Boundary | Elapsed s | Stage s | Completed reads/bytes | Returned wait calls | SPU samples by kind |')
    print('|---|---:|---:|---|---:|---|')
    prev = origin
    for name, us, note in marks[1:] + [('last-event', end+1, 'trace end; not race readiness')]:
        durations, counts, nbytes, files = stage_totals(events, prev, us)
        returned = sum(v for k, v in counts.items() if k.startswith('wait_') and k.endswith('_end'))
        spu = '; '.join(f'{k}={counts[k]} calls/{durations[k]/1000:.2f}ms' for k in SPU_KINDS if counts[k]) or 'none observed'
        print(f'| {name} | {(min(us,end)-origin)/1e6:.3f} | {(us-prev)/1e6:.3f} | {counts["fs_read"]}/{nbytes} | {returned} | {spu} |')
        for nbytes, path in files[:args.top]:
            print(f'  resource: {path!r}: {nbytes} bytes')
        print('  boundary note:', note)
        prev = us
    begins = sum(e['kind'].startswith('wait_') and e['kind'].endswith('_begin') for e in events)
    returned = sum(e['kind'].startswith('wait_') and e['kind'].endswith('_end') for e in events)
    old_requests = sum(e['kind'] in ('wait_usleep','wait_sleep','wait_event') for e in events)
    print(f'Wait begin/end records={begins}/{returned}; unmatched={begins-returned}; historical timeout-only records={old_requests} (duration unknown).')
    for tid in sorted({e.get('tid', 0) for e in events if e['kind'].startswith('wait_')}):
        print(f'host thread {tid}: returned wait syscall union={wait_union(events,origin,end+1,tid)/1e6:.6f}s; not a critical-path measurement')
    if (args.run/'final.json').is_file():
        final = json.loads((args.run/'final.json').read_text(encoding='utf-8'))
        print('Launcher outcome:', final.get('reason'), 'exit=', final.get('returncode'), 'guard=', final.get('terminated_by_guard'))
    if truncated:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
