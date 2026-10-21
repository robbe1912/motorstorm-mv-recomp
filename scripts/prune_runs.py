"""Conservative, auditable retention for completed native runs. Dry-run by default."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import time
import zipfile

import psutil

STAMP = re.compile(r"20\d{6}T\d{6}\.\d{6}Z")
OMIT = {'.git', 'runs', 'run-archives', 'legacy', 'deps', 'research', 'checks', 'builds', '__pycache__'}
UNIQUE = {'.dmp', '.mdmp', '.raw', '.bin', '.hlsl', '.dxbc', '.elf', '.pdb', '.exe',
          '.c', '.cpp', '.h', '.rs', '.py', '.ps1', '.cmd', '.sfo', '.rpk', '.rib', '.dat', '.cnk'}
FATAL = re.compile(rb'FATAL|access violation|0xc0000005|out of memory|unsupported sampler|Traceback \(most recent call last\)', re.IGNORECASE)


def reparse(path):
    s = Path(path).lstat()
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, 'st_file_attributes', 0) & 0x400)


def contained(path, boundary):
    path, boundary = Path(path), Path(boundary)
    if not path.absolute().is_relative_to(boundary.absolute()):
        raise ValueError('Cleanup path outside declared boundary')
    p = path
    while True:
        if reparse(p):
            raise ValueError(f'Reparse point refused: {p}')
        if p == boundary:
            break
        p = p.parent
    if not path.resolve().is_relative_to(boundary.resolve()):
        raise ValueError('Resolved cleanup path escaped boundary')


def files(path):
    """Never follow a directory junction, including on Windows."""
    stack = [Path(path)]
    while stack:
        p = stack.pop()
        if reparse(p):
            raise ValueError(f'Reparse point refused: {p}')
        if p.is_dir():
            stack.extend(p.iterdir())
        else:
            yield p


def pins(repo):
    result = set()
    for p in repo.glob('*.md'):
        if not reparse(p) and p.stat().st_size <= 4 * 1024**2:
            result.update(STAMP.findall(p.read_text(encoding='utf-8', errors='replace')))
    for base in [repo / 'docs', repo / 'scripts', repo / 'temp']:
        if not base.exists() or reparse(base):
            continue
        for directory, names, names_files in os.walk(base, followlinks=False):
            names[:] = [n for n in names if n not in OMIT and not reparse(Path(directory) / n)]
            for name in names_files:
                p = Path(directory) / name
                if p.suffix not in ('.md', '.py', '.json') or reparse(p) or p.stat().st_size > 4 * 1024**2:
                    continue
                text = p.read_text(encoding='utf-8', errors='replace')
                if p.suffix == '.json':
                    try:
                        data = json.loads(text)
                    except ValueError:
                        continue
                    if not isinstance(data, dict) or not ('steps' in data or 'retention_pins' in data):
                        continue
                result.update(STAMP.findall(text))
    return result


def native_live():
    # Never clean while any native owner is running. No process is stopped.
    return any((p.info.get('name') or '').lower() == 'ms1_recomp.exe'
               for p in psutil.process_iter(['name']))


def reason(run, protected, cutoff, newest):
    if run.name in protected:
        return 'referenced by documentation/profile/pin'
    if (run / '.keep').exists():
        return 'explicit .keep'
    if run.name in newest:
        return 'newest runs'
    if dt.datetime.strptime(run.name, '%Y%m%dT%H%M%S.%fZ').replace(tzinfo=dt.timezone.utc).timestamp() >= cutoff:
        return 'younger than retention age'
    try:
        launch = json.loads((run / 'launch.json').read_text())
        final = json.loads((run / 'final.json').read_text())
        if not launch.get('exe_sha256') or not launch.get('elf_sha256') or not final.get('reason'):
            return 'incomplete identity/finalization'
        if final['reason'] not in ('explicit stop marker', 'bounded duration elapsed', 'menu replay target observed; graphics verdict separate'):
            return 'unexpected termination evidence'
        p = psutil.Process(launch['pid'])
        if p.is_running() and abs(p.create_time() - launch['create_time']) < .01:
            return 'live recorded process'
    except psutil.NoSuchProcess:
        pass
    except (OSError, ValueError, KeyError, psutil.Error):
        return 'identity/finalization unavailable'
    replay = run / 'menu-replay.json'
    if replay.exists() and json.loads(replay.read_text()).get('error'):
        return 'failed replay evidence'
    for p in files(run):
        if p.suffix.lower() in UNIQUE:
            return 'unique dump/shader/binary evidence'
        if p.name in ('native.err', 'native.log'):
            with p.open('rb') as f:
                tail = b''
                while chunk := f.read(1024 * 1024):
                    if FATAL.search(tail + chunk):
                        return 'fatal/error evidence'
                    tail = chunk[-256:]
    return None


def plan(repo, days=14, keep=10, now=None, extra_pins=()):
    repo = Path(repo).absolute()
    if days < 14 or keep < 10:
        raise ValueError('Approved minimum retention is 14 days and newest 10 runs')
    root = repo / 'temp/runs'
    if not (repo / '.git').exists() or not root.is_dir():
        raise ValueError('Expected repository with temp/runs')
    contained(root, repo)
    protected = pins(repo) | set(extra_pins)
    runs = sorted((r for r in root.iterdir() if STAMP.fullmatch(r.name)), reverse=True)
    newest = {r.name for r in runs[:keep]}
    result = dict(repo=str(repo),days=days,keep=keep,extra_pins=sorted(extra_pins),eligible=[],skipped=[],logical_bytes=0)
    live = native_live()
    for run in runs:
        try:
            contained(run, root)
            why = 'native process active' if live else reason(run, protected, (time.time() if now is None else now) - days * 86400, newest)
            if why:
                result['skipped'].append(dict(run=run.name, reason=why))
            else:
                payload = list(files(run))
                size = sum(p.stat().st_size for p in payload)
                result['eligible'].append(dict(run=run.name,logical_bytes=size,files=len(payload)))
                result['logical_bytes'] += size
        except (OSError, ValueError, KeyError) as exc:
            result['skipped'].append(dict(run=run.name,reason=f'unsafe/unreadable: {exc}'))
    return result


def apply(report):
    """Re-evaluate protection, archive metadata, then unlink only checked files."""
    repo = Path(report['repo'])
    current = plan(repo, report['days'], report['keep'], extra_pins=report.get('extra_pins', []))
    allowed = {r['run'] for r in current['eligible']}
    receipts = []
    for item in report['eligible']:
        if item['run'] not in allowed:
            continue
        if native_live():
            raise RuntimeError('Native started during maintenance; stop cleanup')
        root = repo / 'temp/runs'
        run = root / item['run']
        payload = list(files(run))
        for p in payload:
            contained(p, root)
        archive_dir = repo / 'temp/run-archives'
        archive_dir.mkdir(exist_ok=True)
        contained(archive_dir, repo)
        archive = archive_dir / f'{run.name}-{time.time_ns()}.zip'
        receipt = dict(run=run.name, capture_data_in_archive=False, original_files=len(payload), logical_bytes=item['logical_bytes'])
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for p in payload:
                if p.suffix.lower() != '.bmp' or p.relative_to(run).parts[0] not in ('rsx', 'present'):
                    z.write(p, str(p.relative_to(run)))
            z.writestr('RETENTION_RECEIPT.json', json.dumps(receipt, indent=2))
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise RuntimeError('Metadata archive failed CRC verification; do not delete')
        if native_live() or reason(run, pins(repo) | set(report.get('extra_pins', [])), time.time() - report['days'] * 86400, set()):
            raise RuntimeError('Run protection changed during archival; do not delete')
        for p in payload:
            contained(p, root)
            p.unlink()
        for directory, names, _ in os.walk(run, topdown=False):
            for name in names:
                p = Path(directory) / name
                contained(p, root)
                p.rmdir()
        contained(run, root)
        run.rmdir()
        receipt['metadata_archive'] = str(archive)
        receipts.append(receipt)
    return receipts


def automatic(repo, profile=None):
    """User-approved launcher maintenance; no background agent or scheduler."""
    repo = Path(repo)
    if (repo / 'temp/run-retention-policy.json').exists():
        from prune_latest_runs import automatic as latest
        return latest(repo, profile)
    if not (repo / 'temp/runs').exists():
        return
    extra = STAMP.findall(Path(profile).read_text(encoding='utf-8')) if profile else []
    report = plan(repo, extra_pins=extra)
    report['removed'] = apply(report)
    receipt = repo / 'temp' / f'run-retention-{time.time_ns()}.json'
    receipt.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if native_live():
        raise RuntimeError('Another native owner arrived during maintenance; refuse startup')
    print(f"Run retention: removed {len(report['removed'])} expired runs; report {receipt}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--days', type=int, default=14)
    ap.add_argument('--keep', type=int, default=10)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    report = plan(args.repo, args.days, args.keep)
    if args.apply:
        report['removed'] = apply(report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
