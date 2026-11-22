"""Tests for the scheduler: discover-then-monitor cycles."""
import subprocess
import unittest
from unittest import mock

from src import scheduler


class FakeRun:
    """Record subprocess calls; every call 'succeeds' (returncode 0)."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        return mock.Mock(returncode=0)


class SchedulerCycleTest(unittest.TestCase):
    def test_run_once_discovers_then_monitors(self):
        fake = FakeRun()
        with mock.patch.object(scheduler.subprocess, "run", fake):
            self.assertEqual(scheduler.run_once(), 0)
        self.assertEqual(fake.calls, [
            [scheduler.sys.executable, "-m", "src.discover"],
            [scheduler.sys.executable, "-m", "src.monitor"],
        ])

    def test_no_discover_skips_discovery(self):
        fake = FakeRun()
        with mock.patch.object(scheduler.subprocess, "run", fake):
            scheduler.run_once(discover=False)
        self.assertEqual(fake.calls, [
            [scheduler.sys.executable, "-m", "src.monitor"],
        ])

    def test_discovery_failure_does_not_block_monitor(self):
        def flaky(argv, **kwargs):
            if "src.discover" in argv:
                raise subprocess.TimeoutExpired(cmd=argv, timeout=900)
            return mock.Mock(returncode=0)

        with mock.patch.object(scheduler.subprocess, "run", flaky):
            self.assertEqual(scheduler.run_once(), 0)

    def test_discovery_timeout_returns_nonzero_but_continues(self):
        with mock.patch.object(
                scheduler.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=1)):
            self.assertEqual(scheduler.run_discover(), 1)

    def test_once_flag_with_no_discover(self):
        fake = FakeRun()
        with mock.patch.object(scheduler.subprocess, "run", fake), \
                mock.patch.object(scheduler, "run_once",
                                  wraps=scheduler.run_once) as run_once:
            with self.assertRaises(SystemExit):
                scheduler.main(["--once", "--no-discover"])
        run_once.assert_called_once_with(discover=False)


if __name__ == "__main__":
    unittest.main()
