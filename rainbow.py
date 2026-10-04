"""Fade Nano LEDs through the full named palette in opposite directions."""

import argparse
import colorsys
import math
import time

import blink_device

FRAME_SECONDS = 0.05


def rainbow_colors():
	# Include each primary/secondary boundary so RGB fades keep a full channel.
	return [tuple(round(component * 255) for component in colorsys.hsv_to_rgb(step / 24, 1, 1)) for step in range(24)]


def named_colors():
	colors = {
		tuple(int(value[offset:offset + 2], 16) for offset in (1, 3, 5))
		for value in blink_device.blinkstick.BlinkStick._names_to_hex.values()
	}

	def hue_order(rgb):
		hue, saturation, value = colorsys.rgb_to_hsv(*(component / 255 for component in rgb))
		return (saturation == 0, hue, saturation, value)

	return sorted(colors, key=hue_order)


def fade_to(device, start, end, seconds):
	steps = max(1, math.ceil(seconds / FRAME_SECONDS))
	for step in range(1, steps + 1):
		frame_start = time.monotonic()
		for index in start:
			rgb = tuple(round(before + (after - before) * step / steps) for before, after in zip(start[index], end[index]))
			device.set_color(index=index, red=rgb[0], green=rgb[1], blue=rgb[2])
		remaining = seconds / steps - (time.monotonic() - frame_start)
		if remaining > 0:
			time.sleep(remaining)


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--once", action="store_true", help="Run one palette cycle and turn the LEDs off")
	parser.add_argument("--fade", type=float, default=1.0, metavar="SECONDS", help="Seconds per color transition (default: 1)")
	palette_options = parser.add_mutually_exclusive_group()
	palette_options.add_argument("--named-colors", dest="named_colors", action="store_true", default=True, help="Use the full named palette (default)")
	palette_options.add_argument("--saturated", dest="named_colors", action="store_false", help="Use only the saturated rainbow")
	args = parser.parse_args(argv)
	if not math.isfinite(args.fade) or args.fade <= 0:
		parser.error("--fade must be a positive, finite number")

	device = None
	try:
		device = blink_device.find_first()
		if device is None:
			print("No BlinkStick found")
			return 1
		palette = named_colors() if args.named_colors else rainbow_colors()
		print(f"Fading through {len(palette)} colors. Press Ctrl+C to stop.", flush=True)
		indices = blink_device.led_indices(device)
		black = {index: (0, 0, 0) for index in indices}
		current = black
		while True:
			for position in range(len(palette)):
				colors = {index: palette[position if index == 0 else -position - 1] for index in indices}
				fade_to(device, current, colors, args.fade)
				current = colors
			if args.once:
				fade_to(device, current, black, args.fade)
				return 0
	except KeyboardInterrupt:
		return 0
	except blink_device.DEVICE_ERRORS as error:
		print(f"BlinkStick error: {error}")
		return 1
	finally:
		if device is not None:
			try:
				blink_device.close_device(device)
			except blink_device.DEVICE_ERRORS as error:
				print(f"Could not turn off or close the BlinkStick: {error}")


if __name__ == "__main__":
	raise SystemExit(main())
