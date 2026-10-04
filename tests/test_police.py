import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

import police


class PoliceTests(unittest.TestCase):
	def run_police(self, device, indices=(0, 1), argv=("--once",), sleep_errors=None):
		output = io.StringIO()
		with patch.object(police.blink_device, "find_first", return_value=device), patch.object(police.blink_device, "led_indices", return_value=indices), patch.object(police.blink_device, "close_device") as close, patch.object(police.time, "sleep", side_effect=sleep_errors) as sleep, redirect_stdout(output):
			result = police.main(argv)
		return result, close, sleep, output.getvalue()

	def test_once_alternates_triple_bursts_then_slower_single_flashes(self):
		device = Mock()
		result, close, sleep, _ = self.run_police(device)
		flashes = [(event.kwargs["index"], event.kwargs["name"]) for event in device.set_color.call_args_list if event.kwargs["name"] != "black"]
		self.assertEqual(flashes, ([(0, "red")] * 3 + [(1, "blue")] * 3) * 2 + [(0, "red"), (1, "blue")] * 2)
		state = {0: "black", 1: "black"}
		for event in device.set_color.call_args_list:
			state[event.kwargs["index"]] = event.kwargs["name"]
			self.assertLessEqual(sum(color != "black" for color in state.values()), 1)
		self.assertEqual(state, {0: "black", 1: "black"})
		self.assertEqual(result, 0)
		self.assertIn(call(0.055), sleep.call_args_list)
		self.assertIn(call(0.12), sleep.call_args_list)
		self.assertEqual(sleep.call_args_list[-1], call(0.25))
		close.assert_called_once_with(device, turn_off=True)

	def test_default_repeats_cycles_until_interrupt(self):
		device = Mock()
		with patch.object(police, "police_cycle", side_effect=[None, KeyboardInterrupt()]) as cycle:
			result, close, _, _ = self.run_police(device, argv=())
		self.assertEqual(result, 0)
		self.assertEqual(cycle.call_count, 2)
		close.assert_called_once_with(device, turn_off=True)

	def test_interrupt_during_on_pulse_requests_both_leds_off(self):
		device = Mock()
		result, close, _, _ = self.run_police(device, sleep_errors=KeyboardInterrupt())
		self.assertEqual(result, 0)
		self.assertEqual(device.set_color.call_args_list, [call(index=0, name="black"), call(index=1, name="black"), call(index=0, name="red")])
		close.assert_called_once_with(device, turn_off=True)

	def test_write_failure_requests_both_leds_off(self):
		device = Mock()
		device.set_color.side_effect = [None, OSError("Disconnected")]
		result, close, _, output = self.run_police(device)
		self.assertEqual(result, 1)
		self.assertIn("Disconnected", output)
		close.assert_called_once_with(device, turn_off=True)

	def test_unexpected_exception_still_requests_both_leds_off(self):
		device = Mock()
		with patch.object(police.blink_device, "find_first", return_value=device), patch.object(police.blink_device, "led_indices", return_value=(0, 1)), patch.object(police.blink_device, "close_device") as close, patch.object(police.time, "sleep", side_effect=RuntimeError("Unexpected")):
			with self.assertRaisesRegex(RuntimeError, "Unexpected"):
				police.main(["--once"])
		close.assert_called_once_with(device, turn_off=True)

	def test_no_device_exits_without_writes_or_cleanup(self):
		result, close, sleep, output = self.run_police(None)
		self.assertEqual(result, 1)
		self.assertIn("No BlinkStick found", output)
		close.assert_not_called()
		sleep.assert_not_called()

	def test_one_led_device_is_rejected_and_closed(self):
		device = Mock()
		result, close, sleep, output = self.run_police(device, indices=(0,))
		self.assertEqual(result, 1)
		self.assertIn("two LEDs", output)
		device.set_color.assert_not_called()
		sleep.assert_not_called()
		close.assert_called_once_with(device, turn_off=True)

	def test_cleanup_failure_does_not_mask_interrupt(self):
		device = Mock()
		with patch.object(police.blink_device, "find_first", return_value=device), patch.object(police.blink_device, "led_indices", return_value=(0, 1)), patch.object(police.blink_device, "close_device", side_effect=OSError("Disconnected")), patch.object(police.time, "sleep", side_effect=KeyboardInterrupt()), redirect_stdout(io.StringIO()):
			self.assertEqual(police.main(["--once"]), 0)


if __name__ == "__main__":
	unittest.main()
