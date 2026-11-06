"""FPS_STATS CSV persistence (#275): compile the production rsx_fps_stats.c
against an authored clock and fflush faults, and check what an owned abrupt
termination, a normal exit, a buffer-sized burst and a failed flush leave in
the CSV. The historical buffered source (git object below) must reproduce the
lost/partial tail; mutants of each persistence rule must fail."""
import os
from pathlib import Path
import hashlib
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
INCLUDE = ROOT / 'vendor/ps3recomp/include'
SOURCE = VIDEO / 'rsx_fps_stats.c'
FIXTURE = ROOT / 'scripts/fixtures/fps_csv_persistence.c'
# The buffered source before #275 (93f8614:vendor/ps3recomp/libs/video/rsx_fps_stats.c), kept as a
# hash-pinned fixture: CI checkouts are shallow, so the git object is not available there.
HISTORICAL = ROOT / 'scripts/fixtures/rsx_fps_stats_historical.c'
HISTORICAL_SHA256 = '2f89d2580e768bf78694e0acef076a5c5b3c42f1d12715fb490c517340e9c2a3'
HEADER = 'frame,t_ms,dt_ms,flips_since_prev_present'
ROW = re.compile(r'^(\d+),(\d+\.\d{3}),(\d+\.\d{3}),(\d+)$')


def compiler():
    if os.name == 'nt':
        if 'MV_CLANG' not in os.environ:
            from project import build_environment
            os.environ.update(build_environment())
        return os.environ['MV_CLANG']
    return os.environ.get('CC', 'cc')


def build(out, name, source, seams):
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    defines = ['RSX_FPS_STATS_TEST_SEAMS'] if seams else []
    if os.name == 'nt':
        cmd = [compiler(), '/nologo', '/O2', '/W3', '/I' + str(INCLUDE), '/I' + str(VIDEO),
               *['/D' + d for d in defines], str(FIXTURE), str(source),
               '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
    else:
        cmd = [compiler(), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D_POSIX_C_SOURCE=200809L',
               '-I' + str(INCLUDE), '-I' + str(VIDEO), *['-D' + d for d in defines],
               str(FIXTURE), str(source), '-o', str(exe)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'{name}: compile failed\n{r.stdout}{r.stderr}')
    return exe


def run(exe, out, tag, mode, presents, step_us, fail_after=None, csv=True, enabled=True, partial=False):
    path = out / f'{tag}.csv'
    if path.exists(): path.unlink()
    env = dict(os.environ)
    env.pop('FPS_STATS', None); env.pop('FPS_STATS_CSV', None)
    if enabled: env['FPS_STATS'] = '1'
    if csv: env['FPS_STATS_CSV'] = str(path)
    env.pop('FPS_TEST_PARTIAL', None)
    if partial: env['FPS_TEST_PARTIAL'] = '1'
    args = [str(exe), mode, str(presents), str(step_us)] + ([str(fail_after)] if fail_after is not None else [])
    r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=120)
    (out / f'{tag}.stderr').write_text(r.stderr)
    return r, path


def read_csv(path):
    """(complete rows, partial trailing text) -- a partial row is never parsed."""
    if not path.exists():
        return None, ''
    data = path.read_text()
    lines = data.split('\n')
    tail = lines.pop()                       # text after the last newline
    if lines and lines[0] == HEADER:
        lines = lines[1:]
    elif lines:
        raise AssertionError('missing header')
    rows = []
    for line in lines:
        m = ROW.match(line)
        if not m: raise AssertionError('malformed complete row: ' + line)
        rows.append(m.groups())
    return rows, tail


def last_mark(stderr):
    marks = re.findall(r'csv_persisted=(\d+)@(\d+\.\d{3})', stderr)
    return (int(marks[-1][0]), marks[-1][1]) if marks else None


def check(exe, out, label):
    failures = []
    def expect(ok, what):
        if not ok: failures.append(what)

    # 1. Owned abrupt termination at 60 Hz for 4.5 s: every acknowledged
    #    row is on disk, complete and contiguous; nothing partial.
    r, path = run(exe, out, label + '-terminate', 'terminate', 270, 16667)
    rows, tail = read_csv(path)
    mark = last_mark(r.stderr)
    expect(r.returncode == 0, 'terminate run exits cleanly')
    expect(mark is not None and mark[0] > 0, 'window lines acknowledge persisted rows')
    expect(rows is not None and tail == '', 'no partial trailing row after termination')
    if mark and rows is not None:
        expect(len(rows) == mark[0], f'file holds exactly the acknowledged rows ({len(rows)} vs {mark[0]})')
        expect(rows and rows[-1][1] == mark[1], 'acknowledged t_ms is the last durable row')
        expect([int(x[0]) for x in rows] == list(range(len(rows))), 'rows contiguous from frame 0')
        expect(270 - len(rows) <= 60, 'loss bounded by one report window')

    # 2. Normal exit: every row, summary acknowledges all of them.
    r, path = run(exe, out, label + '-normal', 'normal', 270, 16667)
    rows, tail = read_csv(path)
    expect(rows is not None and len(rows) == 270 and tail == '', 'normal exit keeps all 270 rows')
    expect('[FPS] csv rows=270 persisted=270' in r.stderr, 'summary acknowledges all rows')

    # 3. Burst far beyond the buffer inside one window, then terminate:
    #    stdio must never have written a partial row on its own.
    #    20000 presents 100 us apart: about 250 KB in the first window alone.
    r, path = run(exe, out, label + '-burst', 'terminate', 20000, 100)
    rows, tail = read_csv(path)
    mark = last_mark(r.stderr)
    expect(rows is not None and tail == '', 'burst leaves no partial row')
    expect(bool(rows) and mark is not None and len(rows) >= mark[0] >= 10000,
           f'burst keeps at least the acknowledged rows ({len(rows or [])}, mark {mark})')
    if rows:
        expect([int(x[0]) for x in rows] == list(range(len(rows))), 'burst rows contiguous')

    # 4. Flush failure after the header and two windows: visible, coverage
    #    reported, CSV closed, presents keep counting.
    r, path = run(exe, out, label + '-fail', 'normal', 270, 16667, fail_after=3)
    rows, tail = read_csv(path)
    m = re.search(r'\[FPS\] FPS_STATS_CSV write failed after (\d+) rows: persisted (\d+) complete rows through t_ms=(\d+\.\d{3});', r.stderr)
    expect(m is not None, 'flush failure reported with coverage')
    if m and rows is not None:
        expect(len(rows) == int(m.group(2)) and tail == '', 'file holds exactly the reported persisted rows')
    expect('[FPS] summary presents=270' in r.stderr, 'presents still counted after CSV failure')
    expect('[FPS] csv rows=' not in r.stderr, 'no success summary for a failed CSV')

    # 4b. Partial write at the device limit: the incomplete bytes are reported
    #     and are exactly what follows the persisted rows.
    r, path = run(exe, out, label + '-partial', 'normal', 270, 16667, fail_after=3, partial=True)
    rows, tail = read_csv(path)
    m = re.search(r'persisted (\d+) complete rows through t_ms=\d+\.\d{3}, followed by (\d+) bytes of an incomplete write', r.stderr)
    expect(m is not None, 'partial write reported with its byte count')
    if m and rows is not None and path.exists():
        persisted = int(m.group(1))
        body = path.read_text().split('\n', 1)[1]
        durable = ''.join(l + '\n' for l in body.split('\n')[:persisted])
        expect(len(body) - len(durable) == int(m.group(2)), 'reported incomplete bytes match the file')

    # 5. Disabled mode: no file, no output.
    r, path = run(exe, out, label + '-disabled', 'normal', 270, 16667, enabled=False)
    expect(not path.exists() and r.stderr == '', 'disabled mode writes nothing')
    # 6. Enabled without CSV: window lines unchanged (no persistence field).
    r, path = run(exe, out, label + '-nocsv', 'normal', 270, 16667, csv=False)
    expect('csv_persisted' not in r.stderr and r.stderr.count('[FPS] t=') == 4, 'no-CSV report format unchanged')
    return failures


def main():
    with tempfile.TemporaryDirectory(prefix='fps-csv-') as d:
        out = Path(d)
        exe = build(out, 'production', SOURCE, True)
        failures = check(exe, out, 'production')
        if failures:
            raise SystemExit('FAIL production:\n  ' + '\n  '.join(failures))
        print('production: termination, normal exit, burst, flush failure, disabled and no-CSV cases pass')

        # Historical control: the old buffered source loses the tail under
        # the same owned termination (real clock; no flush before exit).
        if hashlib.sha256(HISTORICAL.read_bytes()).hexdigest() != HISTORICAL_SHA256:
            raise SystemExit('FAIL historical fixture changed; it must stay the pre-#275 source')
        hist = build(out, 'historical', HISTORICAL, False)
        r, path = run(hist, out, 'historical-terminate', 'terminate', 2000, 16667)
        rows, tail = read_csv(path)
        rows = rows or []
        if len(rows) >= 2000:
            raise SystemExit('FAIL historical control kept every row; the loss is not reproduced')
        print(f'historical: terminate kept {len(rows)}/2000 complete rows, partial tail {len(tail)} bytes')

        src = SOURCE.read_text()
        mutants = [
            ('no-window-flush', '    if (s_csv && fps_csv_flush() == 0)\n        fprintf(stderr, " csv_persisted',
             '    if (0)\n        fprintf(stderr, " csv_persisted'),
            ('no-capacity-flush', '    if (s_csv_pending_bytes + FPS_CSV_ROW_MAX_BYTES > FPS_CSV_BUFFER_BYTES &&\n        fps_csv_flush() != 0)\n        return -1;\n    memcpy',
             '    if (s_csv_pending_bytes + FPS_CSV_ROW_MAX_BYTES > FPS_CSV_BUFFER_BYTES)\n        s_csv_pending_bytes = 0;   /* overwrite instead of writing */\n    memcpy'),
            ('silent-failure', '    fprintf(stderr,\n            "[FPS] FPS_STATS_CSV %s failed',
             '    if (0) fprintf(stderr,\n            "[FPS] FPS_STATS_CSV %s failed'),
            ('stdio-buffered', 'setvbuf(s_csv, NULL, _IONBF, 0)', 'setvbuf(s_csv, NULL, _IOFBF, 4096)'),
            ('ack-before-write', '    if (s_csv_pending_bytes) {\n        written',
             '    s_csv_persisted_rows += s_csv_pending_rows; s_csv_pending_rows = 0;\n    if (s_csv_pending_bytes) {\n        written'),
        ]
        for name, before, after in mutants:
            assert src.count(before) == 1, name
            m = out / f'mutant_{name}.c'
            m.write_text(src.replace(before, after))
            failures = check(build(out, 'mutant-' + name, m, True), out, 'mutant-' + name)
            if not failures:
                raise SystemExit(f'FAIL mutant {name} was not detected')
            print(f'mutant {name} rejected: {failures[0]}')

        # Matched host cost: 1 us authored steps keep the production run inside
        # one report window (no stderr lines), like the historical run on its
        # real clock; both write every row. Informational, not asserted.
        for runs in range(3):
            prod = run(exe, out, 'overhead-new', 'overhead', 200000, 1)[0].stdout.strip()
            histo = run(hist, out, 'overhead-old', 'overhead', 200000, 1)[0].stdout.strip()
            print(f'overhead trial {runs + 1} (200000 presents with CSV): production {prod}, historical {histo}')
    print('PASS: bounded FPS CSV persistence, acknowledged coverage, visible failures, historical loss and mutants')


if __name__ == '__main__':
    main()
