"""Reject the historically unsupported policy request before launch (#149)."""
import unittest
from runtime_profile import execution_environment


class ExecutionProfileTests(unittest.TestCase):
    def test_current_fork_rejects_silently_ignored_baseline(self):
        with self.assertRaisesRegex(ValueError,'does not support'):
            execution_environment('baseline-interpreter',{'policy_interpreter':False})

    def test_explicit_default_omits_curated_probes(self):
        self.assertEqual({},execution_environment('toolkit-default',{'policy_interpreter':False}))

    def test_curated_baseline_retains_policy_and_disabled_probes(self):
        env=execution_environment('baseline-interpreter',{'policy_interpreter':True})
        self.assertEqual('1',env.pop('SPU_PM_INTERP'))
        self.assertTrue(env)
        self.assertEqual({'0'},set(env.values()))


if __name__=='__main__':unittest.main()
