"""Game-free regressions for the formerly human/timed menu reproduction loop."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from menu_replay import load_profile, matches, replay
from native_pad import latest_frame, owned


def synthetic_bmp(path, left, color=b'\xff\xff\xff'):
    w, h = 80, 40
    data = bytearray(w * h * 3)
    for y in range(10, 13):
        for x in range(left, left + 20):
            at = ((h - y - 1) * w + x) * 3
            data[at:at + 3] = color
    head = struct.pack('<2sIHHI', b'BM', 54 + len(data), 0, 0, 54)
    info = struct.pack('<IiiHHIIIIII', 40, w, h, 1, 24, 0, len(data), 0, 0, 0, 0)
    path.write_bytes(head + info + data)


class MenuReplayTests(unittest.TestCase):
    def test_latest_completed_frame_orders_numeric_sequence_past_99(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for number in (9, 10, 98, 99, 100, 101, 200):
                directory = root / 'rsx' / f'frame_{number}'
                directory.mkdir(parents=True)
                synthetic_bmp(directory / 'backbuffer.bmp', 25)
                if number != 200:
                    (directory / 'manifest.txt').write_text('authored fixture')
            self.assertEqual(latest_frame(root).parent.name, 'frame_101')
            (root / 'rsx/frame_200/manifest.txt').write_text('authored fixture')
            self.assertEqual(latest_frame(root).parent.name, 'frame_200')

    def test_manifest_does_not_make_a_partially_written_bitmap_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for number in (99, 100):
                directory = root / 'rsx' / f'frame_{number}'
                directory.mkdir(parents=True)
                synthetic_bmp(directory / 'backbuffer.bmp', 25)
                (directory / 'manifest.txt').write_text('authored fixture')
            bitmap = root / 'rsx/frame_100/backbuffer.bmp'
            complete = bitmap.read_bytes()
            for partial in (b'', b'BM', complete[:54], complete[:-1]):
                bitmap.write_bytes(partial)
                self.assertEqual(latest_frame(root).parent.name, 'frame_99')
            bitmap.write_bytes(complete)
            self.assertEqual(latest_frame(root).parent.name, 'frame_100')

    def test_observed_target_takes_priority_over_optional_skip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frame = root / 'target.bmp'
            synthetic_bmp(frame, 25)
            state = dict(reference=str(frame), roi=[0, 0, 80, 40], label='synthetic target')
            route = dict(schema=1, elf_sha256='synthetic identity',
                         steps=[dict(state, mask=0x4000, polls=4)], target=state,
                         optional_actions=[dict(state, mask=8, polls=4, after_step=0)])
            path = root / 'route.json'
            path.write_text(json.dumps(route))
            with patch('menu_replay.owned', return_value={'elf_sha256': 'synthetic identity'}), \
                 patch('menu_replay.latest_frame', return_value=frame), patch('menu_replay.send') as send:
                result = replay(root, path)
            send.assert_not_called()
            self.assertTrue(result['target_observed'])
            self.assertEqual(result['optional_inputs'], [])

    def test_intro_contrast_matches_faded_caption_and_rejects_wrong_or_blank_screen(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            reference, faded, wrong, blank = [root / f'{n}.bmp' for n in range(4)]
            synthetic_bmp(reference, 25, b'\x70\xaa\xfa')
            synthetic_bmp(faded, 25, b'\x38\x55\x7d')
            synthetic_bmp(wrong, 45, b'\x70\xaa\xfa')
            synthetic_bmp(blank, 25, b'\x00\x00\x00')
            state = dict(reference=str(reference), roi=[0, 0, 80, 40],
                         label='synthetic colored intro caption', mode='contrast')
            self.assertTrue(matches(faded, state))
            self.assertFalse(matches(wrong, state))
            self.assertFalse(matches(blank, state))
            with self.assertRaisesRegex(ValueError, 'no reliable contrast'):
                matches(blank, dict(state, reference=str(blank)))

    def test_invalid_optional_intro_actions_are_rejected_before_input(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frame = root / 'state.bmp'
            synthetic_bmp(frame, 25)
            state = dict(reference=str(frame), roi=[0, 0, 80, 40], label='synthetic state')
            step = dict(state, mask=0x4000, polls=4)
            action = dict(step, after_step=1)
            route = dict(schema=1, elf_sha256='synthetic identity', steps=[step], target=state)
            path = root / 'route.json'
            for invalid in ('blind press', dict(action, after_step=True),
                            dict(action, after_step=-1), dict(action, after_step=2),
                            dict(action, reference=''), dict(action, mask=0), dict(action, polls=9)):
                with self.subTest(action=invalid):
                    path.write_text(json.dumps(dict(route, optional_actions=[invalid])))
                    with self.assertRaises(ValueError):
                        load_profile(path)

    def test_optional_intro_skip_is_acknowledged_once_without_blocking_menu(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frames = []
            for n, left in enumerate((5, 25, 25, 45, 60)):
                p = root / f'{n}.bmp'
                synthetic_bmp(p, left, b'\x70\xaa\xfa' if n in (1, 2) else b'\xff\xff\xff')
                frames.append(p)
            def state(n, **kw):
                return dict(reference=str(frames[n]), roi=[0, 0, 80, 40], label=f'state{n}', **kw)
            profile = dict(schema=1, elf_sha256='synthetic identity',
                           steps=[state(0, mask=0x4000, polls=4), state(3, mask=0x40, polls=4)],
                           optional_actions=[state(1, mode='contrast', mask=8, polls=4, after_step=1)],
                           target=state(4))
            path = root/'route.json'
            path.write_text(json.dumps(profile))
            calls = []
            def acknowledged(run, reference, roi, mask, polls, label, **kwargs):
                calls.append(mask)
                return dict(observed_frame=str(reference), acknowledged=True)
            with patch('menu_replay.owned', return_value={'elf_sha256': 'synthetic identity'}), \
                 patch('menu_replay.latest_frame', side_effect=frames), \
                 patch('menu_replay.send', side_effect=acknowledged), patch('menu_replay.time.sleep'):
                result = replay(root, path)
            self.assertEqual(calls, [0x4000, 8, 0x40])
            self.assertEqual(len(result['optional_inputs']), 1)
            self.assertEqual(result['inputs'], 2)
            # Intro absent: no speculative skip and no mandatory intro wait.
            calls.clear()
            with patch('menu_replay.owned', return_value={'elf_sha256': 'synthetic identity'}), \
                 patch('menu_replay.latest_frame', side_effect=[frames[0], frames[3], frames[4]]), \
                 patch('menu_replay.send', side_effect=acknowledged), patch('menu_replay.time.sleep'):
                result = replay(root, path)
            self.assertEqual(calls, [0x4000, 0x40])
            self.assertEqual(result['optional_inputs'], [])

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
