"""Find possible AddJob descriptor stores in a validated capture summary.

The supplied range is a candidate descriptor region, not a proven queue.
Matches are not ownership, publication, generation or completion evidence.
"""
import argparse
import json
import sys

from analyze_atomic_range import analyze as analyze_atomic
from analyze_queue_calls import analyze as analyze_calls


def analyze(lines, start, size):
    lines = list(lines)
    calls = analyze_calls(lines)
    stores = analyze_atomic(lines, start, size)
    matches = []
    queue_history = []
    context_unknown = context_mismatch = 0
    for call in calls['paired_add_job_argument_candidates']:
        history = []
        for kind, events in (('init', calls['paired_init_argument_candidates']),
                             ('reset', calls['paired_reset_candidates'])):
            for event in events:
                if event['object'] != call['queue_argument']:
                    continue
                if event['return_tick'] < call['entry_tick']:
                    relation = 'before'
                elif event['entry_tick'] > call['return_tick']:
                    relation = 'after'
                else:
                    relation = 'overlap_or_touch'
                history.append({'operation': kind, 'relation': relation, **event})
        history.sort(key=lambda e: (e['entry_tick'], e['call_id']))
        queue_history.append({'call_id': call['call_id'], 'queue_argument': call['queue_argument'],
                              'observed_history': history})
        # Unknown host-thread identities cannot support even a candidate link.
        if not call['thread'] or (call['entry_flags'] | call['return_flags']) & 1:
            continue
        header = call['header'].to_bytes(8, 'big').hex()
        for store in stores['events']:
            if (store['source'] != 2 or store['size'] != 8 or not store['committed']
                    or not store['attempted'] or store['flags'] & (1 | 8 | 16 | 64) or store['record_flags'] & 1
                    or store['thread'] != call['thread'] or store['overlap_size'] != 8
                    or store['overlap_before'] != '0000000000000000'
                    or store['after'].lower() != header
                    or not (call['entry_tick'] <= store['begin'] <= store['end'] <= call['return_tick'])):
                continue
            if store['flags'] & 32 or not store['context'] or not call['context']:
                context_unknown += 1
                continue
            if store['context'] != call['context']:
                context_mismatch += 1
                continue
            matches.append({'call_id': call['call_id'], 'store_index': store['index'],
                            'address': store['address'], 'header': call['header'],
                            'queue_argument': call['queue_argument']})
    return {'run_id': calls['run_id'], 'candidates': matches, 'queue_history': queue_history,
            'context_unknown_pairs': context_unknown, 'context_mismatch_pairs': context_mismatch,
            'call_coverage': calls, 'atomic_coverage': {k: v for k, v in stores.items() if k != 'events'},
            'interpretation': 'candidate matches only; ownership, uniqueness, publication and completion are unproven'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events')
    parser.add_argument('start', type=lambda s: int(s, 0))
    parser.add_argument('size', type=lambda s: int(s, 0))
    args = parser.parse_args()
    try:
        with open(args.events, encoding='utf-8') as stream:
            print(json.dumps(analyze(stream, args.start, args.size), sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        print(f'AddJob candidate analysis failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
