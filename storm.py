"""Keep dim blue ambience between randomized white lightning bursts."""

import argparse
import math
import random
import time

import blink_device

DEFAULT_BRIGHTNESS = 0.7


def ambient_color(brightness):
	return (0, 0, max(1, round(20 * brightness)))


def lightning_schedule(indices, brightness, rng=random):
	"""Build separate flash timing for each LED, ending each flash in blue."""
	blue = ambient_color(brightness)
	white = (max(1, round(255 * brightness)),) * 3
	events = []
	for position, index in enumerate(indices):
		moment = position * 0.05 + rng.uniform(0, 0.15)
		for _ in range(rng.randint(2, 4)):
			events.append((moment, index, white))
			moment += rng.uniform(0.04, 0.10)
			events.append((moment, index, blue))
			moment += rng.uniform(0.06, 0.18)
	return sorted(events)


def storm_event(device, indices, brightness=DEFAULT_BRIGHTNESS, rng=random):
	blue = ambient_color(brightness)
	for index in indices:
		device.set_color(index=index, red=blue[0], green=blue[1], blue=blue[2])
	time.sleep(rng.uniform(2, 4))
	started = time.monotonic()
	for moment, index, rgb in lightning_schedule(indices, brightness, rng):
		remaining = moment - (time.monotonic() - started)
		if remaining > 0:
			time.sleep(remaining)
		device.set_color(index=index, red=rgb[0], green=rgb[1], blue=rgb[2])
	time.sleep(rng.uniform(0.7, 1))


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--once", action="store_true", help="Run one storm event and turn the LEDs off")
	parser.add_argument("--brightness", type=float, default=DEFAULT_BRIGHTNESS, metavar="LEVEL", help="Brightness above 0 through 1 (default: 0.7)")
	args = parser.parse_args(argv)
	if not math.isfinite(args.brightness) or not 0 < args.brightness <= 1:
		parser.error("--brightness must be a finite number above 0 through 1")

	device = None
	try:
		device = blink_device.find_first()
		if device is None:
			print("No BlinkStick found")
			return 1
		indices = tuple(blink_device.led_indices(device))
		while True:
			storm_event(device, indices, args.brightness)
			if args.once:
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
