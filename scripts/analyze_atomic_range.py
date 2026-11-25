"""Inspect observed atomic stores overlapping a guest range, without inferring jobs.

Input must be job_capture_summary --events JSONL from a validated snapshot.
The provided range is a candidate, not proof of ownership or coverage.
"""
import argparse
import json
import sys


def analyze(lines, start, size):
    if start < 0 or size <= 0 or start + size > 0x100000000:
        raise ValueError('invalid 32-bit guest range')
    end = start + size
    summary = None
    total = 0
    overlap = []
    for line in lines:
        event = json.loads(line)
        if summary is not None:
            raise ValueError('data after summary')
        if event.get('type') == 'summary':
            summary = event
        elif event.get('type') == 'atomic':
            total += 1
            address, length = event['address'], event['size']
            if not isinstance(address, int) or not isinstance(length, int) or address < 0 or length <= 0:
                raise ValueError('invalid atomic extent')
            if address < end and start < address + length:
                flags = event['flags']
                first = max(address, start)
                last = min(address + length, end)
                offset = first - address
                span = last - first
                before = bytes.fromhex(event['before'])
                after = bytes.fromhex(event['after'])
                # Invalid stores and truncated captures may not contain these
                # bytes; zero-filled payload is not evidence in that case.
                available = not (flags & 16) and len(before) >= offset + span and len(after) >= offset + span
                # COMMITTED is the only success indication. Keep attempts,
                # invalid clocks, missing data and unknown contexts visible.
                overlap.append({'index': event['index'], 'address': address,
                                'size': length, 'source': event['source'],
                                'command': event['command'], 'flags': flags,
                                'attempted': bool(flags & 2),
                                'committed': bool(flags & 4),
                                'begin': event['begin'], 'end': event['end'],
                                'thread': event['thread'], 'context': event['context'],
                                'saved_pc': event['saved_pc'], 'return_address': event['return_address'],
                                'record_flags': event['record_flags'], 'host_dispatch': event['host_dispatch'],
                                'payload_truncated': event['payload_truncated'],
                                'overlap_address': first, 'overlap_size': span,
                                'overlap_before': before[offset:offset + span].hex() if available else None,
                                'overlap_after': after[offset:offset + span].hex() if available else None,
                                'before': event['before'], 'after': event['after']})
    if summary is None or not summary.get('run_id') or summary.get('atomic') != total:
        raise ValueError('missing summary or atomic event count mismatch')
    return {'run_id': summary['run_id'], 'ticks_per_second': summary['ticks_per_second'],
            'range_start': start, 'range_size': size,
            'events': overlap, 'excluded_atomic': summary['excluded_atomic_after'],
            'pending': summary['pending'], 'dropped': summary['dropped_after'],
            'attempted_before': summary['attempted_before'],
            'attempted_after': summary['attempted_after'],
            'filter_mask': summary['filter_mask'],
            'append_failures': summary['append_failures_after'],
            'interpretation': 'partial overlapping store observations; ownership, publication and completion are unproven'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events')
    parser.add_argument('start', type=lambda s: int(s, 0))
    parser.add_argument('size', type=lambda s: int(s, 0))
    args = parser.parse_args()
    try:
        with open(args.events, encoding='utf-8') as stream:
            print(json.dumps(analyze(stream, args.start, args.size), sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'atomic range analysis failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
