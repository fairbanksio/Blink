"""Flash both BlinkStick Nano LEDs red and blue."""

import argparse
import time

import blink_device

FAST_FLASH_SECONDS = 0.055
FAST_GAP_SECONDS = 0.045
SLOW_FLASH_SECONDS = 0.12
SLOW_GAP_SECONDS = 0.07


def police_cycle(device, indices):
	first, second = indices
	device.set_color(index=first, name="black")
	device.set_color(index=second, name="black")

	def flash(index, color, on_seconds, off_seconds):
		device.set_color(index=index, name=color)
		time.sleep(on_seconds)
		device.set_color(index=index, name="black")
		time.sleep(off_seconds)

	# Alternate banks while keeping red and blue on their own sides.
	for _ in range(2):
		for index, color in ((first, "red"), (second, "blue")):
			for _ in range(3):
				flash(index, color, FAST_FLASH_SECONDS, FAST_GAP_SECONDS)
			time.sleep(0.12)
	for _ in range(2):
		flash(first, "red", SLOW_FLASH_SECONDS, SLOW_GAP_SECONDS)
		flash(second, "blue", SLOW_FLASH_SECONDS, SLOW_GAP_SECONDS)
	time.sleep(0.25)


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--once", action="store_true", help="Run one cycle and turn both LEDs off")
	args = parser.parse_args(argv)
	device = None
	try:
		device = blink_device.find_first()
		if device is None:
			print("No BlinkStick found")
			return 1
		indices = tuple(blink_device.led_indices(device))
		if len(indices) != 2:
			print("Police lights require a BlinkStick with two LEDs")
			return 1
		while True:
			police_cycle(device, indices)
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
