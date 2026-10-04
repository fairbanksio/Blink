"""Shared BlinkStick transport and helpers for both Nano LEDs."""

import sys
import time

from blinkstick import blinkstick
from usb.core import NoBackendError

DEVICE_ERRORS = (OSError, blinkstick.BlinkStickException, NoBackendError)
WRITE_INTERVAL = 0.02


class LinuxBlinkStick(blinkstick.BlinkStick):
	def __init__(self, device):
		from usb.util import dispose_resources

		self._is_nano = False
		self._last_write = None
		self.bs_serial = None
		try:
			super().__init__(device=device)
			self._is_nano = self.get_variant() == self.BLINKSTICK_NANO
		except Exception:
			dispose_resources(device)
			raise

	def _usb_get_string(self, device, index):
		if self.bs_serial is None:
			# A failed first serial read must not try to reconnect by an unknown serial.
			from usb.util import get_string

			return get_string(device, index, 1033)
		return super()._usb_get_string(device, index)

	def _usb_ctrl_transfer(self, request_type, request, report_id, interface, data):
		color_write = self._is_nano and request_type == 0x20 and request == 0x09 and report_id in (1, 5)
		if color_write:
			if len(data) != (4 if report_id == 1 else 6):
				raise ValueError("Invalid LED color report length")
			if report_id == 1:
				# The legacy first-LED command can disturb the second Nano LED.
				report_id = 5
				data = bytes([5, 0, 0, *data[-3:]])
			if self._last_write is not None:
				remaining = WRITE_INTERVAL - (time.monotonic() - self._last_write)
				if remaining > 0:
					time.sleep(remaining)
		result = super()._usb_ctrl_transfer(request_type, request, report_id, interface, data)
		if color_write:
			self._last_write = time.monotonic()
		return result


class MacBlinkStick(blinkstick.BlinkStick):
	def __init__(self, path, serial=None, led_count=2):
		import hid

		self.device = hid.device()
		try:
			self.device.open_path(path)
		except OSError:
			self.device.close()
			raise
		self.bs_serial = serial or "Unknown"
		self._led_count = led_count
		self._colors = {index: (0, 0, 0) for index in range(led_count)}
		self._last_write = None

	def _usb_ctrl_transfer(self, request_type, request, report_id, interface, data):
		if request_type != 0x20 or request != 0x09 or report_id not in (1, 5):
			raise NotImplementedError("Only LED color reports are supported")
		if len(data) != (4 if report_id == 1 else 6):
			raise ValueError("Invalid LED color report length")
		channel, index = (0, 0) if report_id == 1 else (data[1], data[2])
		if channel != 0 or index not in self._colors:
			raise NotImplementedError("Unsupported LED channel or index")
		# Use indexed writes for both Nano LEDs instead of mixing report formats.
		if self._led_count == 2:
			report = bytes([5, channel, index, *data[-3:]])
		else:
			report = bytes([report_id, *data[1:]])
		# Give the firmware time to finish an LED update before another write.
		if self._last_write is not None:
			remaining = WRITE_INTERVAL - (time.monotonic() - self._last_write)
			if remaining > 0:
				time.sleep(remaining)
		accepted = self.device.send_feature_report(report)
		self._last_write = time.monotonic()
		if accepted != len(report):
			raise OSError(f"BlinkStick accepted {accepted} of {len(report)} report bytes")
		self._colors[index] = tuple(report[-3:])

	def _get_color_rgb(self, index=0):
		# This is the last successful command, not hardware color readback.
		if index not in self._colors:
			raise NotImplementedError("Unsupported LED index")
		color = self._colors[index]
		return tuple(255 - value for value in color) if self.inverse else color

	def get_color(self, index=0, color_format="rgb"):
		color = self._get_color_rgb(index)
		if color_format == "rgb":
			return color
		if color_format == "hex":
			return "#%02x%02x%02x" % color
		raise ValueError("Unsupported color format")

	def get_serial(self):
		return self.bs_serial

	def get_variant(self):
		return self.BLINKSTICK_NANO if self._led_count == 2 else self.UNKNOWN

	def pulse(self, channel=0, index=0, red=0, green=0, blue=0, name=None, hex=None, repeats=1, duration=1000, steps=50):
		# Upstream pulse() clears index 0 even when another LED was requested.
		rgb = self._determine_rgb(red=red, green=green, blue=blue, name=name, hex=hex)
		self.set_color(channel=channel, index=index)
		for _ in range(repeats):
			self.morph(channel=channel, index=index, red=rgb[0], green=rgb[1], blue=rgb[2], duration=duration, steps=steps)
			self.morph(channel=channel, index=index, duration=duration, steps=steps)

	def close(self):
		self.device.close()


def led_indices(device):
	return (0, 1) if device.get_variant() == blinkstick.BlinkStick.BLINKSTICK_NANO else (0,)


def _open_mac(info):
	is_nano = "nano" in (info.get("product_string") or "").lower() or info.get("release_number") == 0x202
	return MacBlinkStick(info["path"], serial=info.get("serial_number"), led_count=2 if is_nano else 1)


def find_first():
	if sys.platform.startswith("linux"):
		from usb.core import find

		device = find(idVendor=blinkstick.VENDOR_ID, idProduct=blinkstick.PRODUCT_ID)
		return LinuxBlinkStick(device) if device is not None else None
	if sys.platform != "darwin":
		return blinkstick.find_first()
	import hid

	devices = hid.enumerate(blinkstick.VENDOR_ID, blinkstick.PRODUCT_ID)
	return _open_mac(devices[0]) if devices else None


def find_all():
	if sys.platform.startswith("linux"):
		from usb.core import find

		opened = []
		try:
			for device in find(find_all=True, idVendor=blinkstick.VENDOR_ID, idProduct=blinkstick.PRODUCT_ID):
				opened.append(LinuxBlinkStick(device))
		except Exception:
			from usb.util import dispose_resources

			for stick in opened:
				dispose_resources(stick.device)
			raise
		return opened
	if sys.platform != "darwin":
		return blinkstick.find_all()
	import hid

	opened = []
	try:
		for info in hid.enumerate(blinkstick.VENDOR_ID, blinkstick.PRODUCT_ID):
			opened.append(_open_mac(info))
	except DEVICE_ERRORS:
		for device in opened:
			try:
				device.close()
			except DEVICE_ERRORS:
				pass
		raise
	return opened


def set_all(device, **color):
	for index in led_indices(device):
		device.set_color(index=index, **color)


def morph_all(device, **options):
	for index in led_indices(device):
		device.morph(index=index, **options)


def pulse_all(device, repeats=1, duration=1000, **color):
	set_all(device)
	for _ in range(repeats):
		morph_all(device, duration=duration, **color)
		morph_all(device, duration=duration)


def blink_all(device, repeats=1, delay=500, **color):
	for repetition in range(repeats):
		if repetition:
			time.sleep(delay / 1000)
		set_all(device, **color)
		time.sleep(delay / 1000)
		set_all(device)


def close_device(device, turn_off=True):
	first_error = None
	try:
		if turn_off:
			for index in led_indices(device):
				try:
					device.set_color(index=index)
				except DEVICE_ERRORS as error:
					first_error = first_error or error
	finally:
		if isinstance(device, MacBlinkStick):
			device.close()
		else:
			from usb.util import dispose_resources

			dispose_resources(device.device)
	if first_error is not None:
		raise first_error
