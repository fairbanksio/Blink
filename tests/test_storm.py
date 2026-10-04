import io
import random
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import storm


class StormTests(unittest.TestCase):
	def run_storm(self, device, indices=(0, 1), argv=("--once",), event_error=None):
		output = io.StringIO()
		with patch.object(storm.blink_device, "find_first", return_value=device), patch.object(storm.blink_device, "led_indices", return_value=indices), patch.object(storm.blink_device, "close_device") as close, patch.object(storm, "storm_event", side_effect=event_error) as event, redirect_stdout(output):
			result = storm.main(argv)
		return result, close, event, output.getvalue()

	def test_schedule_has_independent_offsets_and_restores_blue(self):
		events = storm.lightning_schedule((0, 1), 0.5, random.Random(5))
		by_index = {index: [event for event in events if event[1] == index] for index in (0, 1)}
		self.assertNotEqual([event[0] for event in by_index[0]], [event[0] for event in by_index[1]])
		for flashes in by_index.values():
			self.assertIn(len(flashes), (4, 6, 8))
			for on, off in zip(flashes[::2], flashes[1::2]):
				self.assertEqual(on[2], (128, 128, 128))
				self.assertEqual(off[2], (0, 0, 10))
				self.assertGreater(off[0], on[0])
			self.assertEqual(flashes[-1][2], storm.ambient_color(0.5))

	def test_events_finish_in_blue_with_bounded_duration(self):
		for seed in range(100):
			device = Mock()
			clock = [0.0]
			def sleep(seconds):
				self.assertGreaterEqual(seconds, 0)
				clock[0] += seconds
			with patch.object(storm.time, "sleep", side_effect=sleep), patch.object(storm.time, "monotonic", side_effect=lambda: clock[0]):
				storm.storm_event(device, (0, 1), rng=random.Random(seed))
			self.assertGreaterEqual(clock[0], 3)
			self.assertLessEqual(clock[0], 7)
			state = {}
			for event in device.set_color.call_args_list:
				state[event.kwargs["index"]] = tuple(event.kwargs[channel] for channel in ("red", "green", "blue"))
			self.assertEqual(state, {0: (0, 0, 14), 1: (0, 0, 14)})

	def test_once_runs_exactly_one_event_and_cleans_up(self):
		device = Mock()
		result, close, event, _ = self.run_storm(device, argv=("--once", "--brightness", "0.25"))
		self.assertEqual(result, 0)
		event.assert_called_once_with(device, (0, 1), 0.25)
		close.assert_called_once_with(device, turn_off=True)

	def test_single_led_fallback_uses_only_index_zero(self):
		device = Mock()
		with patch.object(storm.time, "sleep"):
			storm.storm_event(device, (0,), rng=random.Random(1))
		self.assertTrue(device.set_color.called)
		self.assertEqual({event.kwargs["index"] for event in device.set_color.call_args_list}, {0})
		result, close, event, _ = self.run_storm(device, indices=(0,))
		self.assertEqual(result, 0)
		event.assert_called_once_with(device, (0,), storm.DEFAULT_BRIGHTNESS)
		close.assert_called_once_with(device, turn_off=True)

	def test_default_repeats_until_interrupt_and_cleans_up(self):
		device = Mock()
		result, close, event, _ = self.run_storm(device, argv=(), event_error=[None, KeyboardInterrupt()])
		self.assertEqual(result, 0)
		self.assertEqual(event.call_count, 2)
		close.assert_called_once_with(device, turn_off=True)

	def test_usb_failure_cleans_up(self):
		device = Mock()
		result, close, _, output = self.run_storm(device, event_error=OSError("Disconnected"))
		self.assertEqual(result, 1)
		self.assertIn("Disconnected", output)
		close.assert_called_once_with(device, turn_off=True)

	def test_interrupt_during_actual_flash_cleans_up(self):
		device = Mock()
		device.set_color.side_effect = [None, None, KeyboardInterrupt()]
		with patch.object(storm.blink_device, "find_first", return_value=device), patch.object(storm.blink_device, "led_indices", return_value=(0, 1)), patch.object(storm.blink_device, "close_device") as close, patch.object(storm.time, "sleep"):
			self.assertEqual(storm.main(["--once"]), 0)
		self.assertEqual(device.set_color.call_count, 3)
		close.assert_called_once_with(device, turn_off=True)

	def test_cleanup_failure_does_not_mask_interrupt(self):
		with patch.object(storm.blink_device, "find_first", return_value=Mock()), patch.object(storm.blink_device, "led_indices", return_value=(0, 1)), patch.object(storm, "storm_event", side_effect=KeyboardInterrupt()), patch.object(storm.blink_device, "close_device", side_effect=OSError("Disconnected")), redirect_stdout(io.StringIO()) as output:
			self.assertEqual(storm.main(["--once"]), 0)
		self.assertIn("Could not turn off or close", output.getvalue())

	def test_no_device_exits_without_event_or_cleanup(self):
		result, close, event, output = self.run_storm(None)
		self.assertEqual(result, 1)
		self.assertIn("No BlinkStick found", output)
		event.assert_not_called()
		close.assert_not_called()

	def test_invalid_brightness_is_rejected_before_device_access(self):
		for value in ("0", "-0.1", "1.1", "nan", "inf"):
			with self.subTest(value=value), patch.object(storm.blink_device, "find_first") as find, redirect_stdout(io.StringIO()), patch("sys.stderr", new=io.StringIO()):
				with self.assertRaises(SystemExit) as error:
					storm.main(["--brightness", value])
				self.assertEqual(error.exception.code, 2)
				find.assert_not_called()


if __name__ == "__main__":
	unittest.main()
