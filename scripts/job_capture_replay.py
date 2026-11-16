"""Screen-gated capture signals; caller supplies the ownership check."""
import time
import re
from pathlib import Path


def capture_after_target(run, seconds, owned, *, clock=time.monotonic, sleep=time.sleep):
    """Open only after replay confirms its target; wait for the snapshot log.

    Host file-creation times are not guest event timestamps. The caller must
    retain the controller's QPC bounds and inspect the snapshot's loss fields.
    """
    run = Path(run)
    directory = run / 'job-capture'
    owned(run)
    # Start at the current end: only acknowledgments produced by this capture
    # are admissible. Keep the file open and consume new bytes once per poll.
    log = (run / 'native.err').open('rb')
    log.seek(0, 2)
    def read_new():
        if (run / 'native.err').stat().st_size < log.tell():
            raise RuntimeError('Job capture log was truncated')
        return log.read().decode('utf-8', errors='replace')
    try:
        return _capture(run, directory, owned, clock, sleep, seconds, read_new)
    finally:
        log.close()


def _capture(run, directory, owned, clock, sleep, seconds, read_new):
    with (directory / 'open').open('x'):
        pass
    open_requested = clock()
    pending = ''
    while clock() - open_requested < 10:
        owned(run)
        pending += read_new()
        match = re.search(r'\[job-capture\] open result=(\d+) before=(\d+) after=(\d+)\r?\n', pending)
        if match:
            open_result = int(match.group(1))
            if open_result not in (1, 2):
                raise RuntimeError('Job capture window rejected; inspect native.err')
            before, after = int(match.group(2)), int(match.group(3))
            if open_result == 1 and (before <= 0 or after < before):
                raise RuntimeError('Job capture open clock bounds invalid')
            opened = clock()
            break
        pending = pending[-4096:]
        sleep(.05)
    else:
        raise TimeoutError('Job capture window not acknowledged within 10 seconds')
    while clock() - opened < seconds:
        owned(run)
        read_new()
        sleep(.05)
    owned(run)
    read_new()
    with (directory / 'snapshot').open('x'):
        pass
    requested = clock()
    pending = ''
    while clock() - requested < 10:
        owned(run)
        pending += read_new()
        if '[job-capture] snapshot written ' in pending:
            return {'open_request_monotonic': open_requested, 'open_monotonic': opened,
                    'open_result': open_result, 'open_before_qpc': before, 'open_after_qpc': after,
                    'open_clock_valid': open_result == 1, 'snapshot_request_monotonic': requested,
                    'snapshot_log_monotonic': clock()}
        if re.search(r'\[job-capture\] snapshot (?:failed|create failed|fd failed|stream failed)', pending):
            raise RuntimeError('Job capture snapshot failed; inspect native.err')
        pending = pending[-4096:]
        sleep(.05)
    raise TimeoutError('Job capture snapshot not acknowledged within 10 seconds')
