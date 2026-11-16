"""Exercise capture acknowledgments without launching a game."""
import tempfile
from pathlib import Path
from job_capture_replay import capture_after_target


def exercise(open_line, snapshot_line, *, stale='', split=False, split_at=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root/'job-capture').mkdir()
        log = root/'native.err'
        log.write_text(stale)
        now = [10.0]
        sent = set()
        def clock(): return now[0]
        def owned(run): assert run == root
        def sleep(seconds):
            now[0] += seconds
            opening = (root/'job-capture/open').exists()
            snapshot = (root/'job-capture/snapshot').exists()
            key = 'snapshot' if snapshot else 'open' if opening else None
            line = snapshot_line if snapshot else open_line
            if key and line and key not in sent and key+'-part' not in sent:
                with log.open('a') as stream:
                    if split:
                        middle = len(line)//2 if split_at is None else split_at
                        stream.write(line[:middle]); stream.flush()
                    else:
                        stream.write(line + '\n')
                if split:
                    sent.add(key+'-part')
                else:
                    sent.add(key)
            elif key and key+'-part' in sent and key not in sent:
                with log.open('a') as stream:
                    middle = len(line)//2 if split_at is None else split_at
                    stream.write(line[middle:]+'\n')
                sent.add(key)
        return capture_after_target(root, .1, owned, clock=clock, sleep=sleep)

ok = '[job-capture] open result=1 before=100 after=101'
written = '[job-capture] snapshot written (live partial view)'
result = exercise(ok, written, split=True, stale=ok+'\n'+written+'\n')
assert result['open_clock_valid'] and result['snapshot_request_monotonic'] - result['open_monotonic'] >= .1
result = exercise(ok, written, split=True, split_at=len(ok)-1)
assert result['open_before_qpc'] == 100 and result['open_after_qpc'] == 101
assert result['open_monotonic'] >= 10.1
assert exercise(ok+'\n'+'x'*10000, written+'\n'+'x'*10000)['open_clock_valid']
assert not exercise('[job-capture] open result=2 before=0 after=0', written)['open_clock_valid']
for open_line, snapshot_line, message in [
    ('[job-capture] open result=0 before=0 after=0', None, 'window rejected'),
    ('[job-capture] open result=1 before=100 after=99', written, 'clock bounds invalid'),
    (None, None, 'window not acknowledged'),
    *[(ok, '[job-capture] snapshot '+failure, 'snapshot failed') for failure in
      ('failed', 'create failed', 'fd failed', 'stream failed')],
    (ok, None, 'snapshot not acknowledged'),
]:
    try:
        exercise(open_line, snapshot_line, stale=ok+'\n'+written+'\n')
        raise AssertionError('stale or failed acknowledgment accepted')
    except (RuntimeError, TimeoutError) as error:
        assert message in str(error), str(error)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); (root/'job-capture').mkdir(); (root/'native.err').write_text('')
    def lost(run): raise RuntimeError('ownership lost')
    try: capture_after_target(root, .1, lost)
    except RuntimeError as error: assert str(error) == 'ownership lost'
    else: raise AssertionError('lost ownership accepted')
    assert not (root/'job-capture/open').exists()
    (root/'job-capture/open').touch()
    try: capture_after_target(root, .1, lambda run: None)
    except FileExistsError: pass
    else: raise AssertionError('pre-existing capture signal accepted')
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); (root/'job-capture').mkdir(); log = root/'native.err'; log.write_text('x'*100)
    now = [0.0]
    def truncate(seconds):
        now[0] += seconds
        log.write_text('')
    try: capture_after_target(root, .1, lambda run: None, clock=lambda: now[0], sleep=truncate)
    except RuntimeError as error: assert 'log was truncated' in str(error)
    else: raise AssertionError('truncated capture log accepted')
print('PASS screen-gated capture signaling and ownership')
