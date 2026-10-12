"""Game-free regressions for the formerly human/timed menu reproduction loop."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from menu_replay import load_profile, matches, replay
from native_pad import owned


def synthetic_bmp(path, left):
    w, h = 80, 40
    data = bytearray(w * h * 3)
    for y in range(10, 13):
        for x in range(left, left + 20):
            at = ((h - y - 1) * w + x) * 3
            data[at:at + 3] = b'\xff\xff\xff'
    head = struct.pack('<2sIHHI', b'BM', 54 + len(data), 0, 0, 54)
    info = struct.pack('<IiiHHIIIIII', 40, w, h, 1, 24, 0, len(data), 0, 0, 0, 0)
    path.write_bytes(head + info + data)


class MenuReplayTests(unittest.TestCase):
    def test_historical_blind_six_press_recipe_is_rejected(self):
        # OPERATIONS' historical "7-press" recipe was actually six timed presses.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'old.json'
            p.write_text(json.dumps([{'mask': m, 'delay': 15} for m in [0x4000] * 4 + [0x40, 0x4000]]))
            with self.assertRaisesRegex(ValueError, 'not a timed press list'):
                load_profile(p)

    def test_wrong_screen_cannot_match_and_missing_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, b = root / 'a.bmp', root / 'b.bmp'
            synthetic_bmp(a, 10)
            synthetic_bmp(b, 45)
            state = dict(reference=str(a), roi=[0, 0, 80, 40], label='authored synthetic state')
            self.assertTrue(matches(a, state))
            self.assertFalse(matches(b, state))
            route = dict(schema=1, elf_sha256='synthetic identity',
                         steps=[dict(state, mask=0x4000, polls=4)], target=state)
            p = root / 'route.json'
            p.write_text(json.dumps(route))
            self.assertEqual(len(load_profile(p)['steps']), 1)
            route['steps'][0].pop('reference')
            p.write_text(json.dumps(route))
            with self.assertRaisesRegex(ValueError, 'no blind replay'):
                load_profile(p)

    def test_reused_pid_or_closed_run_rejects_input_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            exe = root / 'ms1_recomp.exe'
            launch = dict(pid=1, create_time=100., exe=str(exe), output=str(root),
                          environment={'PAD_FILE': str(root / 'pad.txt')})
            (root / 'launch.json').write_text(json.dumps(launch))
            (root / 'pad.txt').write_text('0\n')
            with patch('native_pad.psutil.Process') as factory:
                p = factory.return_value
                p.name.return_value = 'ms1_recomp.exe'
                p.exe.return_value = str(exe)
                p.create_time.return_value = 101.
                with self.assertRaisesRegex(ValueError, 'ownership changed'):
                    owned(root)
                p.create_time.return_value = 100.
                self.assertEqual(owned(root)['pid'], 1)
                (root / 'final.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'not live'):
                    owned(root)
            self.assertEqual((root / 'pad.txt').read_text(), '0\n')

    def test_replay_advances_only_through_matching_observed_states(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            states = []
            for n, left in enumerate((10, 40, 60)):
                p = root / f'{n}.bmp'
                synthetic_bmp(p, left)
                states.append(dict(reference=str(p), roi=[0, 0, 80, 40], label=f'synthetic {n}'))
            profile = dict(schema=1, elf_sha256='synthetic identity',
                           steps=[dict(states[0], mask=0x4000, polls=4),
                                  dict(states[1], mask=0x40, polls=4)], target=states[2])
            path = root / 'route.json'
            path.write_text(json.dumps(profile))
            masks = []
            def acknowledged(run, reference, roi, mask, polls, label, **kwargs):
                masks.append(mask)
                return {'observed_frame': str(reference)}
            with patch('menu_replay.owned', return_value={'elf_sha256': 'synthetic identity'}), \
                 patch('menu_replay.latest_frame', side_effect=[Path(s['reference']) for s in states]), \
                 patch('menu_replay.send', side_effect=acknowledged), patch('menu_replay.time.sleep'):
                result = replay(root, path)
            self.assertEqual(masks, [0x4000, 0x40])
            self.assertTrue(result['target_observed'])
            self.assertFalse(result['graphics_correctness_verified'])
            self.assertTrue((root / 'draw-arm.txt').exists())


if __name__ == '__main__':
    unittest.main()
