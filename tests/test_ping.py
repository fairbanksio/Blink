import io
import subprocess
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import ping


class PingTests(unittest.TestCase):
	def test_probe_parses_reply_and_uses_bounded_system_command(self):
		result = SimpleNamespace(returncode=0, stdout="64 bytes: time=12.345 ms", stderr="")
		with patch.object(ping.shutil, "which", return_value="/sbin/ping"), patch.object(ping.subprocess, "run", return_value=result) as run:
			self.assertEqual(ping.probe("example.com", 2), (True, 12.345, ""))
		self.assertEqual(run.call_args.args[0], ["/sbin/ping", "-n", "-c", "1", "example.com"])
		self.assertEqual(run.call_args.kwargs["timeout"], 2)
		self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")

	def test_probe_timeout_and_failed_ping_are_unreachable(self):
		with patch.object(ping.shutil, "which", return_value="/sbin/ping"), patch.object(ping.subprocess, "run", side_effect=subprocess.TimeoutExpired("ping", 2)):
			self.assertEqual(ping.probe("example.com", 2), (False, None, "Timed out"))
		with patch.object(ping.shutil, "which", return_value="/sbin/ping"), patch.object(ping.subprocess, "run", return_value=SimpleNamespace(returncode=2, stdout="", stderr="Unknown host\nMore detail")):
			self.assertEqual(ping.probe("example.com", 2), (False, None, "Unknown host"))

	def test_reply_without_timing_is_connected_with_unknown_latency(self):
		with patch.object(ping.shutil, "which", return_value="/sbin/ping"), patch.object(ping.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="Reply", stderr="")):
			self.assertEqual(ping.probe("example.com", 2), (True, None, ""))
		self.assertEqual(ping.latency_color(None, 50, 200), "purple")

	def test_latency_threshold_boundaries(self):
		for milliseconds, color in ((0, "green"), (49.99, "green"), (50, "orange"), (199.99, "orange"), (200, "red")):
			self.assertEqual(ping.latency_color(milliseconds, 50, 200), color)

	def test_once_displays_connectivity_and_latency_then_cleans_up(self):
		for reply, expected, exit_code in (((True, 80, ""), ("green", "orange"), 0), ((False, None, "No reply"), ("red", "black"), 1)):
			device = Mock()
			with self.subTest(reply=reply), patch.object(ping.blink_device, "find_first", return_value=device), patch.object(ping.blink_device, "led_indices", return_value=(0, 1)), patch.object(ping.blink_device, "close_device") as close, patch.object(ping, "probe", return_value=reply), patch.object(ping.time, "sleep"), redirect_stdout(io.StringIO()):
				self.assertEqual(ping.main(["localhost", "--once"]), exit_code)
			self.assertEqual(device.set_color.call_args_list, [call(index=0, name=expected[0]), call(index=1, name=expected[1])])
			close.assert_called_once_with(device)

	def test_interrupt_and_device_error_release_handle(self):
		for error, code in ((KeyboardInterrupt(), 0), (OSError("Disconnected"), 1)):
			device = Mock()
			with self.subTest(error=error), patch.object(ping.blink_device, "find_first", return_value=device), patch.object(ping.blink_device, "close_device") as close, patch.object(ping, "probe", side_effect=error), redirect_stdout(io.StringIO()):
				self.assertEqual(ping.main([]), code)
			close.assert_called_once_with(device)

	def test_missing_device_exits_without_network_probe(self):
		with patch.object(ping.blink_device, "find_first", return_value=None), patch.object(ping, "probe") as probe, redirect_stdout(io.StringIO()):
			self.assertEqual(ping.main([]), 1)
		probe.assert_not_called()

	def test_invalid_arguments_are_rejected_before_discovery(self):
		for argv in (("-invalid",), ("--timeout", "nan"), ("--interval", "0"), ("--warn-ms", "200"), ("--critical-ms", "-1")):
			with self.subTest(argv=argv), patch.object(ping.blink_device, "find_first") as find, patch("sys.stderr", new=io.StringIO()):
				with self.assertRaises(SystemExit):
					ping.main(argv)
			find.assert_not_called()


if __name__ == "__main__":
	unittest.main()
