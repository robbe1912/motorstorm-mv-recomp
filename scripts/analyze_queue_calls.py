"""Pair observed queue calls; this does not infer queue generations or jobs.

Input is validated snapshot output from job_capture_summary --events. The
snapshot is live and partial: even a clean pair is only a call observation.
"""
import argparse
import json
import sys


def analyze(lines):
    calls = {}
    summary = None
    count = 0
    unknown_threads = 0
    for line in lines:
        event = json.loads(line)
        if summary is not None:
            raise ValueError('data after summary')
        if event.get('type') == 'summary':
            summary = event
        elif event.get('type') == 'queue_call':
            count += 1
            unknown_threads += bool(event['record_flags'] & 1)
            call_id = event['call_id']
            phase = event['phase']
            if not isinstance(call_id, int) or call_id <= 0 or phase not in (1, 2):
                raise ValueError('invalid queue call identity or phase')
            if event['operation'] not in (1, 2, 3) or not event['tick']:
                raise ValueError('invalid queue operation or clock')
            pair = calls.setdefault(call_id, {})
            if phase in pair:
                raise ValueError('duplicate queue call phase')
            pair[phase] = event
    if summary is None or not summary.get('run_id') or summary.get('queue_call') != count:
        raise ValueError('missing summary or queue event count mismatch')
    paired = entry_only = return_only = inconsistent = 0
    init_candidates = []
    reset_candidates = []
    add_job_candidates = []
    for pair in calls.values():
        if 1 not in pair:
            return_only += 1
        elif 2 not in pair:
            entry_only += 1
        else:
            before, after = pair[1], pair[2]
            same = all(before[k] == after[k] for k in ('thread', 'context', 'object', 'argument', 'operation', 'header', 'entry_lr'))
            if same and before['tick'] <= after['tick']:
                paired += 1
                if before['operation'] == 1:
                    reset_candidates.append({'call_id': before['call_id'], 'object': before['object'],
                                             'entry_tick': before['tick'], 'return_tick': after['tick'],
                                             'thread': before['thread'], 'context': before['context'],
                                             'entry_lr': before['entry_lr'],
                                             'entry_flags': before['record_flags'], 'return_flags': after['record_flags']})
                elif before['operation'] == 2:
                    init_candidates.append({'call_id': before['call_id'],
                                            'object': before['object'],
                                            'backing_argument': before['argument'],
                                            'entry_tick': before['tick'], 'return_tick': after['tick'],
                                            'thread': before['thread'], 'context': before['context'],
                                             'entry_lr': before['entry_lr'],
                                            'entry_flags': before['record_flags'], 'return_flags': after['record_flags']})
                elif before['operation'] == 3:
                    add_job_candidates.append({'call_id': before['call_id'],
                                               'result_pointer': before['object'],
                                               'queue_argument': before['argument'],
                                               'header': before['header'],
                                               'entry_lr': before['entry_lr'],
                                               'thread': before['thread'],
                                               'context': before['context'],
                                               'entry_flags': before['record_flags'],
                                               'return_flags': after['record_flags'],
                                               'entry_tick': before['tick'],
                                               'return_tick': after['tick']})
            else:
                inconsistent += 1
    return {'run_id': summary['run_id'], 'paired_calls': paired, 'entry_only': entry_only,
            'return_only': return_only, 'inconsistent_pairs': inconsistent,
            'unknown_thread_events': unknown_threads,
            'paired_reset_candidates': reset_candidates,
            'paired_init_argument_candidates': init_candidates,
            'paired_add_job_argument_candidates': add_job_candidates,
            'excluded_queue_call': summary['excluded_queue_call_after'],
            'attempted_before': summary['attempted_before'],
            'attempted_after': summary['attempted_after'],
            'pending': summary['pending'], 'dropped': summary['dropped_after'],
            'unexpected_append_failures': summary['append_failures_after'],
            'interpretation': 'partial call observations; queue generations and job completions remain unknown'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', help='JSONL output of job_capture_summary --events')
    args = parser.parse_args()
    try:
        with open(args.events, encoding='utf-8') as stream:
            print(json.dumps(analyze(stream), sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'queue analysis failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
