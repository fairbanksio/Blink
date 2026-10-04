import io
import random
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import fireplace


class FireplaceTests(unittest.TestCase):
	def test_palette_has_warm_flames_and_occasional_dim_red_embers(self):
		rng = random.Random(42)
		samples = [fireplace.flame_target(rng, 1.0) for _ in range(1000)]
		embers = [rgb for rgb, _ in samples if rgb[0] < 100]
		self.assertGreater(len(embers), 50)
		self.assertLess(len(embers), 200)
		for (red, green, blue), seconds in samples:
			self.assertEqual(blue, 0)
			self.assertGreater(red, green)
			self.assertLessEqual(red, 255)
			self.assertGreater(seconds, 0)
			self.assertLessEqual(green, red * 0.42 + 1)
		for red, green, _ in embers:
			self.assertLessEqual(green, red * 0.07 + 1)

	def test_brightness_scales_the_same_flame_without_changing_timing(self):
		full, timing = fireplace.flame_target(random.Random(10), 1.0)
		dim, dim_timing = fireplace.flame_target(random.Random(10), 0.25)
		self.assertEqual(timing, dim_timing)
		for bright, dark in zip(full, dim):
			self.assertAlmostEqual(dark, bright * 0.25, delta=1)

	def test_sample_is_finite_smooth_and_independent_on_both_leds(self):
		frames = []
		with patch.object(fireplace, "fade_to", side_effect=lambda device, start, end, seconds: frames.append((start, end, seconds))):
			fireplace.fireplace(Mock(), (0, 1), duration=10, rng=random.Random(42))
		self.assertAlmostEqual(sum(seconds for _, _, seconds in frames), 10)
		self.assertLessEqual(len(frames), 201)
		self.assertTrue(any(end[0] != end[1] for _, end, _ in frames))
		for position, (start, end, _) in enumerate(frames):
			self.assertEqual(set(end), {0, 1})
			if position:
				self.assertEqual(start, frames[position - 1][1])
			for index in end:
				self.assertLess(abs(end[index][0] - start[index][0]), 100)

	def run_main(self, args, device, error=None, indices=(0, 1)):
		with patch.object(fireplace.blink_device, "find_first", return_value=device), patch.object(fireplace.blink_device, "led_indices", return_value=indices), patch.object(fireplace.blink_device, "close_device") as close, patch.object(fireplace, "fireplace", side_effect=error) as effect, redirect_stdout(io.StringIO()):
			result = fireplace.main(args)
		return result, close, effect

	def test_once_uses_ten_second_sample_and_single_led_fallback(self):
		device = Mock()
		result, close, effect = self.run_main(["--once", "--brightness", "0.5"], device, indices=(0,))
		self.assertEqual(result, 0)
		effect.assert_called_once_with(device, (0,), 0.5, 10.0)
		close.assert_called_once_with(device, turn_off=True)

	def test_default_is_continuous_and_interrupt_cleans_up(self):
		device = Mock()
		result, close, effect = self.run_main([], device, error=KeyboardInterrupt())
		self.assertEqual(result, 0)
		effect.assert_called_once_with(device, (0, 1), 1.0, None)
		close.assert_called_once_with(device, turn_off=True)

	def test_usb_failure_cleans_up(self):
		device = Mock()
		result, close, _ = self.run_main([], device, error=OSError("Disconnected"))
		self.assertEqual(result, 1)
		close.assert_called_once_with(device, turn_off=True)

	def test_missing_device_is_graceful(self):
		result, close, effect = self.run_main([], None)
		self.assertEqual(result, 1)
		close.assert_not_called()
		effect.assert_not_called()

	def test_invalid_brightness_is_rejected_before_discovery(self):
		for value in ("0", "-0.5", "1.1", "nan", "inf"):
			with self.subTest(value=value), patch.object(fireplace.blink_device, "find_first") as find, patch("sys.stderr", new=io.StringIO()):
				with self.assertRaises(SystemExit):
					fireplace.main(["--brightness", value])
				find.assert_not_called()


if __name__ == "__main__":
	unittest.main()
