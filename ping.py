"""Show connectivity on LED 0 and ping latency on LED 1."""

import argparse
import math
import os
import re
import shutil
import subprocess
import time

import blink_device


def probe(host, timeout):
	command = shutil.which("ping")
	if command is None:
		raise OSError("The system ping command was not found")
	try:
		result = subprocess.run([command, "-n", "-c", "1", host], capture_output=True, text=True, timeout=timeout, env={**os.environ, "LC_ALL": "C"})
	except subprocess.TimeoutExpired:
		return False, None, "Timed out"
	if result.returncode != 0:
		lines = result.stderr.strip().splitlines()
		message = lines[0] if lines else "No reply"
		return False, None, message
	match = re.search(r"time\s*[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms", result.stdout)
	return True, float(match.group(1)) if match else None, ""


def latency_color(milliseconds, warn_ms, critical_ms):
	if milliseconds is None:
		return "purple"
	if milliseconds >= critical_ms:
		return "red"
	return "orange" if milliseconds >= warn_ms else "green"


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("host", nargs="?", default="1.1.1.1", help="IPv4 address or hostname (default: 1.1.1.1)")
	parser.add_argument("--once", action="store_true", help="Check once, briefly show the result, and turn off")
	parser.add_argument("--interval", type=float, default=2, help="Seconds between checks (default: 2)")
	parser.add_argument("--timeout", type=float, default=2, help="Seconds allowed for each ping (default: 2)")
	parser.add_argument("--warn-ms", type=float, default=50, help="Orange latency threshold (default: 50 ms)")
	parser.add_argument("--critical-ms", type=float, default=200, help="Red latency threshold (default: 200 ms)")
	args = parser.parse_args(argv)
	if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", args.host):
		parser.error("host must be an IPv4 address or hostname")
	if any(not math.isfinite(value) or value <= 0 for value in (args.interval, args.timeout, args.warn_ms, args.critical_ms)):
		parser.error("timing and latency thresholds must be positive, finite numbers")
	if args.warn_ms >= args.critical_ms:
		parser.error("--warn-ms must be less than --critical-ms")
	device = None
	try:
		device = blink_device.find_first()
		if device is None:
			print("No BlinkStick found")
			return 1
		indices = blink_device.led_indices(device)
		print(f"Pinging {args.host}. Press Ctrl+C to stop.", flush=True)
		while True:
			started = time.monotonic()
			connected, milliseconds, error = probe(args.host, args.timeout)
			device.set_color(index=indices[0], name="green" if connected else "red")
			if len(indices) > 1:
				device.set_color(index=indices[1], name=latency_color(milliseconds, args.warn_ms, args.critical_ms) if connected else "black")
			status = f"{milliseconds:g} ms" if milliseconds is not None else "Reply received; latency unavailable"
			print(f"{args.host}: {status if connected else error}", flush=True)
			if args.once:
				time.sleep(args.interval)
				return 0 if connected else 1
			time.sleep(max(0, args.interval - (time.monotonic() - started)))
	except KeyboardInterrupt:
		return 0
	except blink_device.DEVICE_ERRORS as error:
		print(f"Ping monitor error: {error}")
		return 1
	finally:
		if device is not None:
			try:
				blink_device.close_device(device)
			except blink_device.DEVICE_ERRORS as error:
				print(f"Could not turn off or close the BlinkStick: {error}")


if __name__ == "__main__":
	raise SystemExit(main())
