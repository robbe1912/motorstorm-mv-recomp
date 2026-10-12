"""Replay observed native menu states through normal input; never jump guest scenes."""
import json
import time
from pathlib import Path

from native_pad import frame_signature, latest_frame, owned, send, similarity


def load_profile(path):
    p = json.loads(Path(path).read_text())
    if not isinstance(p, dict) or p.get('schema') != 1 or not p.get('elf_sha256'):
        raise ValueError('Use a screen-gated profile with schema/elf_sha256, not a timed press list')
    if not isinstance(p.get('steps'), list) or not p['steps'] or not isinstance(p.get('target'), dict):
        raise ValueError('Profile requires observed steps and a target screen')
    for n, step in enumerate(p['steps'] + [p['target']]):
        if not step.get('reference') or not step.get('label') or not isinstance(step.get('roi'), list) or len(step['roi']) != 4:
            raise ValueError(f'Step {n} requires an internal reference/ROI/label; no blind replay')
        frame_signature(step['reference'], step['roi'], step.get('mode', 'text'))
        for extra in step.get('checks', []):
            frame_signature(extra['reference'], extra['roi'], extra.get('mode', 'text'))
        if n < len(p['steps']):
            if step.get('mask') not in (0x4000, 8, 16, 32, 64, 128) or not 1 <= step.get('polls', 0) <= 8:
                raise ValueError('Profile uses invalid button/hold')
    return p


def matches(frame, state):
    mode = state.get('mode', 'text')
    left = frame_signature(state['reference'], state['roi'], mode)
    right = frame_signature(frame, state['roi'], mode)
    primary = left == right if mode == 'pixels' else similarity(left, right) >= .95
    return primary and all(matches(frame, check) for check in state.get('checks', []))


def replay(run, profile_path, timeout=480):
    run = Path(run).resolve()
    profile = load_profile(profile_path)
    launch = owned(run)
    if launch['elf_sha256'] != profile['elf_sha256']:
        raise ValueError('Profile executable identity differs; do not replay another game target')
    deadline = time.monotonic() + timeout
    index = 0
    last_input_frame = None
    result = dict(profile=str(Path(profile_path).resolve()), target_observed=False,
                  graphics_correctness_verified=False, desktop_control=False, inputs=0)
    try:
        while time.monotonic() < deadline:
            owned(run)
            if (run / 'stop.txt').exists():
                raise RuntimeError('Owned stop requested before replay target')
            frame = latest_frame(run)
            if frame and frame != last_input_frame and time.time() - frame.stat().st_mtime <= 30:
                try:
                    if matches(frame, profile['target']):
                        result.update(target_observed=True, frame=str(frame), inputs=index)
                        (run / 'draw-arm.txt').write_text('observed target\n')
                        return result
                    if index < len(profile['steps']) and matches(frame, profile['steps'][index]):
                        step = profile['steps'][index]
                        event = send(run, step['reference'], step['roi'], step['mask'], step['polls'],
                                     step['label'], mode=step.get('mode', 'text'))
                        last_input_frame = Path(event['observed_frame'])
                        index += 1
                except ValueError as exc:
                    # A concurrently completed frame can invalidate the pre-send screen gate.
                    if 'Unexpected screen' not in str(exc) and 'new internal frame' not in str(exc):
                        raise
            time.sleep(.2)
        raise TimeoutError(f'Replay stopped at observed step {index}; target not reached, no blind retry')
    except Exception as exc:
        result.update(error=str(exc), inputs=index)
        raise
    finally:
        (run / 'menu-replay.json').write_text(json.dumps(result, indent=2))
