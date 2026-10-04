"""Flicker warm flames and dim red embers on each BlinkStick LED."""

import argparse
import math
import random

import blink_device
from rainbow import FRAME_SECONDS, fade_to

SAMPLE_SECONDS = 10.0


def flame_target(rng, brightness):
	if rng.random() < 0.12:
		red = rng.uniform(30, 85)
		green = red * rng.uniform(0.01, 0.07)
		seconds = rng.uniform(0.7, 1.3)
	else:
		red = rng.uniform(140, 255)
		green = red * rng.uniform(0.12, 0.42)
		seconds = rng.uniform(0.15, 0.6)
	return (round(red * brightness), round(green * brightness), 0), seconds


def fireplace(device, indices, brightness=1.0, duration=None, rng=None):
	rng = rng or random.Random()
	current = {index: (0, 0, 0) for index in indices}
	transitions = {}
	elapsed = 0.0
	while duration is None or elapsed < duration:
		seconds = FRAME_SECONDS if duration is None else min(FRAME_SECONDS, duration - elapsed)
		colors = {}
		for index in indices:
			if index not in transitions:
				target, length = flame_target(rng, brightness)
				transitions[index] = (current[index], target, length, 0.0)
			start, target, length, progress = transitions[index]
			progress = min(length, progress + seconds)
			# Each LED has its own target and timing, with soft starts and stops.
			fraction = progress / length
			fraction = fraction * fraction * (3 - 2 * fraction)
			colors[index] = tuple(round(before + (after - before) * fraction) for before, after in zip(start, target))
			if progress >= length:
				del transitions[index]
			else:
				transitions[index] = (start, target, length, progress)
		fade_to(device, current, colors, seconds)
		current = colors
		elapsed += seconds


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--once", action="store_true", help="Run a 10-second sample and turn the LEDs off")
	parser.add_argument("--brightness", type=float, default=1.0, help="Brightness from above 0 to 1 (default: 1)")
	args = parser.parse_args(argv)
	if not math.isfinite(args.brightness) or not 0 < args.brightness <= 1:
		parser.error("--brightness must be a finite number above 0 and at most 1")
	device = None
	try:
		device = blink_device.find_first()
		if device is None:
			print("No BlinkStick found")
			return 1
		fireplace(device, blink_device.led_indices(device), args.brightness, SAMPLE_SECONDS if args.once else None)
		return 0
	except KeyboardInterrupt:
		return 0
	except blink_device.DEVICE_ERRORS + (NotImplementedError,) as error:
		print(f"BlinkStick error: {error}")
		return 1
	finally:
		if device is not None:
			try:
				blink_device.close_device(device, turn_off=True)
			except blink_device.DEVICE_ERRORS + (NotImplementedError,) as error:
				print(f"Could not turn off or close the BlinkStick: {error}")


if __name__ == "__main__":
	raise SystemExit(main())
