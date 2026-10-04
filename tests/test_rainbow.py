import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

import blink_device
import rainbow


class RainbowTests(unittest.TestCase):
	def test_palette_contains_every_distinct_supported_named_color(self):
		palette = rainbow.named_colors()
		expected = {tuple(int(value[offset:offset + 2], 16) for offset in (1, 3, 5)) for value in blink_device.blinkstick.BlinkStick._names_to_hex.values()}
		self.assertEqual(set(palette), expected)
		self.assertEqual(len(palette), len(expected))
		self.assertIn((255, 0, 0), palette)
		self.assertIn((0, 0, 255), palette)

	def test_saturated_rainbow_keeps_a_full_brightness_channel_through_both_directions(self):
		palette = rainbow.rainbow_colors()
		device = Mock()
		with patch.object(rainbow.time, "sleep"):
			for position in range(len(palette)):
				start = {0: palette[position - 1], 1: palette[-position % len(palette)]}
				end = {0: palette[position], 1: palette[-position - 1]}
				rainbow.fade_to(device, start, end, 0.2)
		for event in device.set_color.call_args_list:
			self.assertEqual(max(event.kwargs[key] for key in ("red", "green", "blue")), 255)

	def test_named_palette_is_available_explicitly(self):
		device = Mock()
		with patch.object(blink_device, "find_first", return_value=device), patch.object(blink_device, "close_device"), patch.object(rainbow, "named_colors", return_value=[(10, 10, 10)]) as named, patch.object(rainbow, "rainbow_colors") as wheel, patch.object(rainbow, "fade_to"), redirect_stdout(io.StringIO()):
			self.assertEqual(rainbow.main(["--once", "--named-colors"]), 0)
		named.assert_called_once_with()
		wheel.assert_not_called()

	def test_full_named_palette_is_the_default_and_saturated_is_optional(self):
		for arguments, use_named in ((["--once"], True), (["--once", "--saturated"], False)):
			with self.subTest(arguments=arguments), patch.object(blink_device, "find_first", return_value=Mock()), patch.object(blink_device, "close_device"), patch.object(rainbow, "named_colors", return_value=[(10, 10, 10)]) as named, patch.object(rainbow, "rainbow_colors", return_value=[(255, 0, 0)]) as wheel, patch.object(rainbow, "fade_to"), redirect_stdout(io.StringIO()):
				self.assertEqual(rainbow.main(arguments), 0)
				self.assertEqual(named.call_count, int(use_named))
				self.assertEqual(wheel.call_count, int(not use_named))

	def test_fade_has_intermediate_frames_without_a_black_reset(self):
		device = Mock()
		with patch.object(rainbow.time, "sleep"):
			rainbow.fade_to(device, {0: (255, 0, 0)}, {0: (0, 0, 255)}, 0.2)
		frames = [(event.kwargs["red"], event.kwargs["green"], event.kwargs["blue"]) for event in device.set_color.call_args_list]
		self.assertEqual(len(frames), 4)
		self.assertEqual(frames[-1], (0, 0, 255))
		self.assertTrue(all(red + blue >= 254 and green == 0 for red, green, blue in frames))
		self.assertGreater(frames[0][0], 0)
		self.assertGreater(frames[0][2], 0)

	def test_each_frame_reaches_both_leds_before_the_next_frame(self):
		device = Mock()
		device.get_variant.return_value = blink_device.blinkstick.BlinkStick.BLINKSTICK_NANO
		with patch.object(rainbow.time, "sleep"):
			rainbow.fade_to(device, {0: (255, 0, 0), 1: (0, 255, 0)}, {0: (0, 0, 255), 1: (255, 0, 0)}, 0.1)
		writes = device.set_color.call_args_list
		self.assertEqual(len(writes), 4)
		for first, second in zip(writes[::2], writes[1::2]):
			self.assertEqual(first.kwargs["index"], 0)
			self.assertEqual(second.kwargs["index"], 1)
			self.assertNotEqual(first.kwargs["blue"], second.kwargs["blue"])
		self.assertEqual(writes[-2], call(index=0, red=0, green=0, blue=255))
		self.assertEqual(writes[-1], call(index=1, red=255, green=0, blue=0))

	def test_frame_timing_accounts_for_usb_write_time(self):
		with patch.object(rainbow.time, "monotonic", side_effect=[1.0, 1.04]), patch.object(rainbow.time, "sleep") as sleep:
			rainbow.fade_to(Mock(), {0: (0, 0, 0)}, {0: (255, 0, 0)}, 0.05)
		sleep.assert_called_once()
		self.assertAlmostEqual(sleep.call_args.args[0], 0.01)

	def test_once_fades_through_palette_then_to_black_and_closes(self):
		device = Mock()
		device.get_variant.return_value = blink_device.blinkstick.BlinkStick.BLINKSTICK_NANO
		palette = [(255, 0, 0), (0, 0, 255)]
		with patch.object(blink_device, "find_first", return_value=device), patch.object(blink_device, "close_device") as close, patch.object(rainbow, "named_colors", return_value=palette), patch.object(rainbow, "fade_to") as fade, redirect_stdout(io.StringIO()):
			self.assertEqual(rainbow.main(["--once"]), 0)
		self.assertEqual(fade.call_args_list, [call(device, {0: (0, 0, 0), 1: (0, 0, 0)}, {0: palette[0], 1: palette[1]}, 1.0), call(device, {0: palette[0], 1: palette[1]}, {0: palette[1], 1: palette[0]}, 1.0), call(device, {0: palette[1], 1: palette[0]}, {0: (0, 0, 0), 1: (0, 0, 0)}, 1.0)])
		close.assert_called_once_with(device)

	def test_repeat_wraps_smoothly_without_resetting_to_black(self):
		device = Mock()
		device.get_variant.return_value = blink_device.blinkstick.BlinkStick.BLINKSTICK_NANO
		palette = [(255, 0, 0), (0, 0, 255)]
		with patch.object(blink_device, "find_first", return_value=device), patch.object(blink_device, "close_device") as close, patch.object(rainbow, "named_colors", return_value=palette), patch.object(rainbow, "fade_to", side_effect=[None, None, KeyboardInterrupt()]) as fade, redirect_stdout(io.StringIO()):
			self.assertEqual(rainbow.main([]), 0)
		self.assertEqual(fade.call_args_list[-1], call(device, {0: palette[-1], 1: palette[0]}, {0: palette[0], 1: palette[-1]}, 1.0))
		close.assert_called_once_with(device)

	def test_missing_device_exits_without_writes(self):
		with patch.object(blink_device, "find_first", return_value=None), patch.object(blink_device, "close_device") as close, redirect_stdout(io.StringIO()):
			self.assertEqual(rainbow.main([]), 1)
		close.assert_not_called()

	def test_usb_failure_cleans_up_and_returns_failure(self):
		device = Mock()
		with patch.object(blink_device, "find_first", return_value=device), patch.object(blink_device, "close_device") as close, patch.object(rainbow, "fade_to", side_effect=OSError("Disconnected")), redirect_stdout(io.StringIO()):
			self.assertEqual(rainbow.main([]), 1)
		close.assert_called_once_with(device)

	def test_invalid_fade_is_rejected_before_usb_discovery(self):
		for value in ("0", "-1", "nan", "inf"):
			with self.subTest(value=value), patch.object(blink_device, "find_first") as find, redirect_stdout(io.StringIO()), patch("sys.stderr", new=io.StringIO()):
				with self.assertRaises(SystemExit):
					rainbow.main(["--fade", value])
				find.assert_not_called()


if __name__ == "__main__":
	unittest.main()
