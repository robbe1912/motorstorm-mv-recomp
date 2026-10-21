"""Explicit count-based capture retention; dry-run unless --apply is supplied.

Unlike the conservative archival policy, this discards old diagnostics. Keep
reusable replay references outside temp/runs before enabling this policy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import zipfile

from prune_runs import STAMP, contained, files, native_live


def plan(repo, keep=5):
    if type(keep) is not int or keep < 1:
        raise ValueError('keep must be a positive integer')
    repo = Path(repo).absolute()
    root = repo / 'temp/runs'
    if not (repo / '.git').exists() or not root.is_dir():
        raise ValueError('Expected repository with temp/runs')
    contained(root, repo)
    runs = sorted((p for p in root.iterdir() if STAMP.fullmatch(p.name)), reverse=True)
    for run in runs:
        contained(run, root)
        if not run.is_dir():
            raise ValueError('Run timestamp must identify a directory')
    selected = [] if native_live() else runs[keep:]
    items = []
    for run in selected:
        payload = list(files(run))  # Refuse every nested reparse point before planning.
        items.append(dict(run=run.name, files=len(payload), logical_bytes=sum(p.stat().st_size for p in payload)))
    return dict(repo=str(repo), keep=keep, kept=[p.name for p in runs[:keep]], eligible=items)


def apply(report):
    repo = Path(report['repo'])
    root = repo / 'temp/runs'
    receipts = []
    for item in report['eligible']:
        # Recheck both ownership and newest-count selection before each deletion.
        current = plan(repo, report['keep'])
        if item['run'] not in {p['run'] for p in current['eligible']}:
            continue
        run = root / item['run']
        payload = list(files(run))
        for p in payload:
            contained(p, root)
        archive_root = repo / 'temp/run-receipts'
        archive_root.mkdir(exist_ok=True)
        contained(archive_root, repo)
        archive = archive_root / f'{run.name}-{time.time_ns()}.zip'
        receipt = dict(item, archive=str(archive), capture_data_in_archive=False,
                       diagnostic_payloads_discarded=True)
        # Bound receipts: retain top-level JSON identities/gates, not old raw
        # payloads, giant logs or capture trees under a different directory name.
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for p in payload:
                if p.parent == run and p.suffix == '.json' and p.stat().st_size <= 1024**2:
                    z.write(p, p.name)
            z.writestr('RETENTION_RECEIPT.json', json.dumps(receipt, indent=2))
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise RuntimeError('Receipt CRC failed; no deletion')
        if native_live():
            raise RuntimeError('Native process started; no deletion')
        for p in payload:
            contained(p, root)
            p.unlink()
        # Only remove individually checked empty directories, never recursive rm.
        directories = []
        stack = [run]
        while stack:
            directory = stack.pop()
            contained(directory, root)
            directories.append(directory)
            for child in directory.iterdir():
                contained(child, root)
                if not child.is_dir():
                    raise RuntimeError('Run changed during cleanup')
                stack.append(child)
        for directory in reversed(directories):
            contained(directory, root)
            directory.rmdir()
        receipts.append(receipt)
    return receipts


def preserve_profile(repo, profile):
    """Keep exact replay image bytes independent of disposable capture trees."""
    repo, profile = Path(repo).absolute(), Path(profile)
    root = repo / 'temp/runs'
    data = json.loads(profile.read_text())
    changed = False

    def reference(value):
        nonlocal changed
        source = Path(value).absolute()
        if not source.is_relative_to(root):
            return value
        contained(source, root)
        payload = source.read_bytes()  # A missing input aborts before cleanup.
        digest = hashlib.sha256(payload).hexdigest()
        directory = repo / 'temp/menu-references'
        directory.mkdir(exist_ok=True)
        contained(directory, repo)
        target = directory / (digest + source.suffix)
        if target.exists():
            contained(target, repo)
            if target.read_bytes() != payload:
                raise RuntimeError('Existing replay reference differs')
        else:
            target.write_bytes(payload)
        changed = True
        return str(target)

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == 'reference':
                    value[key] = reference(item)
                elif key == 'reference_variants':
                    value[key] = [reference(p) for p in item]
                else:
                    visit(item)
    visit(data)
    if changed:
        profile.write_text(json.dumps(data, indent=2))


def automatic(repo, profile=None):
    repo = Path(repo)
    policy = repo / 'temp/run-retention-policy.json'
    if not policy.exists() or not (repo / 'temp/runs').exists():
        return
    config = json.loads(policy.read_text())
    if config.get('mode') != 'latest':
        raise ValueError('Unknown local run-retention policy')
    if profile:
        preserve_profile(repo, profile)
    report = plan(repo, config['keep'])
    report['removed'] = apply(report)
    receipt = repo / 'temp' / f'latest-run-retention-{time.time_ns()}.json'
    receipt.write_text(json.dumps(report, indent=2))
    print(f"Latest-run retention: kept {report['keep']}; removed {len(report['removed'])}; {receipt}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--keep', type=int, default=5)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    report = plan(args.repo, args.keep)
    if args.apply:
        report['removed'] = apply(report)
    print(json.dumps(report, indent=2))
