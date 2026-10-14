"""Owned PAD_FILE input gated by a recent game-internal frame, never desktop input."""
import argparse
import datetime
import hashlib
import json
import os
import struct
import tempfile
import time
from pathlib import Path

import psutil


def owned(run):
    run = Path(run).resolve()
    launch = json.loads((run / 'launch.json').read_text())
    p = psutil.Process(launch['pid'])
    if p.name().lower() != 'ms1_recomp.exe' or abs(p.create_time() - launch['create_time']) > .01 or Path(p.exe()).resolve() != Path(launch['exe']).resolve():
        raise ValueError('Native ownership changed; do not send input')
    if Path(launch['output']).resolve() != run or (run / 'final.json').exists():
        raise ValueError('Run is not live and owned')
    if Path(launch['environment']['PAD_FILE']).resolve() != run / 'pad.txt':
        raise ValueError('PAD_FILE is not owned by this run')
    return launch


def frame_signature(path, roi, mode='text'):
    """Text mask, grayscale contrast or exact RGB ROI of an internal BMP."""
    if mode not in ('text', 'contrast', 'pixels'):
        raise ValueError('Unknown screen comparison mode')
    b = Path(path).read_bytes()
    if b[:2] != b'BM' or len(b) < 54:
        raise ValueError('Expected complete internal BMP')
    offset = struct.unpack_from('<I', b, 10)[0]
    w, h, planes, bits, compression = struct.unpack_from('<iiHHI', b, 18)
    if w <= 0 or not h or planes != 1 or bits not in (24, 32) or compression != 0:
        raise ValueError('Unsupported internal BMP format')
    x, y, rw, rh = roi
    if min(x, y) < 0 or min(rw, rh) <= 0 or x + rw > w or y + rh > abs(h):
        raise ValueError('Screen ROI is outside internal frame')
    pitch = ((w * bits + 31) // 32) * 4
    if offset + pitch * abs(h) > len(b):
        raise ValueError('Incomplete internal BMP')
    mask = bytearray()
    for iy in range(y, y + rh):
        row = iy if h < 0 else h - iy - 1
        for ix in range(x, x + rw):
            at = offset + row * pitch + ix * (bits // 8)
            if mode == 'pixels':
                mask.extend(b[at:at + 3])
            elif mode == 'contrast':
                blue, green, red = b[at:at + 3]
                mask.append((29 * blue + 150 * green + 77 * red) // 256)
            else:
                mask.append(int(min(b[at:at + 3]) >= 235))
    return bytes(mask)


def similarity(left, right, mode='text'):
    if len(left) != len(right):
        return 0.
    if mode == 'contrast':
        n = len(left)
        sx, sy = sum(left), sum(right)
        vx = n * sum(x*x for x in left) - sx*sx
        vy = n * sum(y*y for y in right) - sy*sy
        if not n or vx < 16*n*n:
            raise ValueError('Reference ROI has no reliable contrast')
        if vy < 4*n*n:
            return 0.
        return (n*sum(x*y for x,y in zip(left,right))-sx*sy) / (vx*vy)**.5
    union = sum(bool(a or b) for a, b in zip(left, right))
    if union < 20:
        raise ValueError('Reference ROI has no reliable text; use a text-bearing ROI')
    return sum(bool(a and b) for a, b in zip(left, right)) / union


def latest_frame(run):
    def completed_bitmap(frame):
        # The producer writes the manifest before exporting the backbuffer.
        # Header/payload length must therefore be complete as well.
        with frame.open('rb') as capture:
            header = capture.read(54)
            size = os.fstat(capture.fileno()).st_size
        if len(header) < 54:
            return False
        if header[:2] != b'BM':
            raise ValueError('Unexpected internal BMP header')
        offset = struct.unpack_from('<I', header, 10)[0]
        w, h, planes, bits, compression = struct.unpack_from('<iiHHI', header, 18)
        if w <= 0 or not h or planes != 1 or bits not in (24, 32) or compression != 0:
            raise ValueError('Unsupported internal BMP format')
        pitch = ((w * bits + 31) // 32) * 4
        return size >= offset + pitch * abs(h)

    frames = (Path(run) / 'rsx').glob('frame_*/backbuffer.bmp')
    complete = [f for f in frames if (f.parent / 'manifest.txt').is_file()
                and completed_bitmap(f)]
    return max(complete, key=lambda f: int(f.parent.name[6:]), default=None)


def send(run, reference, roi, mask, polls, label, timeout=15, mode='text'):
    if mask not in (0x4000, 0x0008, 0x0010, 0x0020, 0x0040, 0x0080) or not 1 <= polls <= 8:
        raise ValueError('Use one normal button with 1..8 polls; no long-hold replay')
    run = Path(run).resolve()
    launch = owned(run)
    frame = latest_frame(run)
    if frame is None or time.time() - frame.stat().st_mtime > 30:
        raise ValueError('Need a fresh completed internal frame before input')
    if frame.stat().st_mtime < launch['create_time']:
        raise ValueError('Frame predates the owned native process')
    journal = run / 'navigation.jsonl'
    if journal.exists():
        previous = json.loads(journal.read_text().splitlines()[-1])
        if previous['observed_frame'] == str(frame):
            raise ValueError('Wait for a new internal frame after the previous input')
    left, right = frame_signature(reference, roi, mode), frame_signature(frame, roi, mode)
    score = float(left == right) if mode == 'pixels' else similarity(left, right, mode)
    if score < .95:
        raise ValueError(f'Unexpected screen ({score:.3f}); no input sent')
    pad = run / 'pad.txt'
    if pad.read_text().strip() not in ('', '0'):
        raise ValueError('PAD_FILE has an unconsumed command')
    log = run / 'native.log'
    offset = log.stat().st_size
    fd, pending = tempfile.mkstemp(prefix='pad-', suffix='.pending', dir=run)
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as f:
            f.write(f'0x{mask:04X} {polls}\n')
        for attempt in range(6):
            owned(run)
            try:
                os.replace(pending, pad)
                break
            except PermissionError:
                if attempt == 5 or not Path(pending).exists():
                    raise
                time.sleep(.2)
    finally:
        if Path(pending).exists():
            Path(pending).unlink()
    receipt = f'[cellPad] PAD_FILE press 0x{mask:04X}'.encode()
    acknowledged = False
    tail = b''
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        owned(run)
        with log.open('rb') as f:
            f.seek(offset)
            chunk = f.read(1024 * 1024)
            offset = f.tell()
        combined = tail + chunk
        tail = combined[-256:]
        if receipt in combined:
            acknowledged = True
            break
        time.sleep(.1)
    event = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), label=label,
                 mask=f'0x{mask:04X}', polls=polls, reference=str(Path(reference).resolve()),
                 roi=list(roi), mode=mode, observed_frame=str(frame), screen_score=score,
                 frame_sha256=hashlib.sha256(frame.read_bytes()).hexdigest(),
                 acknowledged=acknowledged, desktop_control=False)
    with (run / 'navigation.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(event) + '\n')
    if not acknowledged:
        raise TimeoutError('Input receipt missing; do not retry blindly')
    return event


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--roi', required=True, help='x,y,width,height of observed text')
    ap.add_argument('--mask', type=lambda s: int(s, 0), required=True)
    ap.add_argument('--polls', type=int, default=4)
    ap.add_argument('--label', required=True)
    ap.add_argument('--mode', choices=('text', 'contrast', 'pixels'), default='text')
    args = ap.parse_args()
    print(json.dumps(send(args.run, args.reference, tuple(map(int, args.roi.split(','))),
                          args.mask, args.polls, args.label, mode=args.mode), indent=2))


if __name__ == '__main__':
    main()
