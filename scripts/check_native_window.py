"""Regression for a running renderer whose owned window was actually hidden."""
import unittest
from native_window import is_ready_window


class WindowReadinessTests(unittest.TestCase):
    def test_real_hidden_trial_is_rejected_then_visible_state_is_accepted(self):
        # Trial 20261011T151137.499215Z: PID25184, native HWND902F0.
        state = dict(pid=25184, hwnd=0x902F0, class_name='ps3recomp_d3d12',
                     rect=[234, 234, 1530, 993], visible=False, minimized=False)
        desktop = (0, 0, 2560, 1440)
        self.assertFalse(is_ready_window(state, 25184, desktop))
        state['visible'] = True
        self.assertTrue(is_ready_window(state, 25184, desktop))
        self.assertFalse(is_ready_window(state, 9756, desktop))
        state['minimized'] = True
        self.assertFalse(is_ready_window(state, 25184, desktop))

    def test_offscreen_or_unrelated_windows_do_not_count(self):
        state = dict(pid=1, class_name='ps3recomp_d3d12', rect=[5000, 0, 6000, 800],
                     visible=True, minimized=False)
        self.assertFalse(is_ready_window(state, 1, (0, 0, 2560, 1440)))
        state['rect'] = [0, 0, 1000, 800]; state['class_name'] = 'Default IME'
        self.assertFalse(is_ready_window(state, 1, (0, 0, 2560, 1440)))


if __name__ == '__main__':
    unittest.main()
