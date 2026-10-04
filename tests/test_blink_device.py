import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import blink_device


class MacTransportTests(unittest.TestCase):
	def setUp(self):
		self.handle = Mock()
		self.handle.send_feature_report.side_effect = lambda report: len(report)
		self.hid = SimpleNamespace(device=Mock(return_value=self.handle))
		self.hid_patch = patch.dict("sys.modules", {"hid": self.hid})
		self.hid_patch.start()
		self.addCleanup(self.hid_patch.stop)
		self.sleep_patch = patch.object(blink_device.time, "sleep")
		self.sleep = self.sleep_patch.start()
		self.addCleanup(self.sleep_patch.stop)
		self.stick = blink_device.MacBlinkStick(b"mock-device", serial="BS000001-3.0")

	def test_adjacent_led_writes_wait_for_firmware_and_later_write_does_not(self):
		with patch.object(blink_device.time, "monotonic", side_effect=[100, 100.005, 100.02, 100.1, 100.1]):
			self.stick.set_color(index=0, red=10)
			self.sleep.assert_not_called()
			self.stick.set_color(index=1, green=20)
			self.sleep.assert_called_once()
			self.assertAlmostEqual(self.sleep.call_args.args[0], 0.015)
			self.stick.set_color(index=0, blue=30)
		self.assertEqual(self.sleep.call_count, 1)
		self.assertEqual(self.handle.send_feature_report.call_args_list, [
			call(bytes([5, 0, 0, 10, 0, 0])),
			call(bytes([5, 0, 1, 0, 20, 0])),
			call(bytes([5, 0, 0, 0, 0, 30])),
		])

	def test_led_colors_are_independent_and_use_exact_hid_reports(self):
		self.stick.set_color(index=0, red=12, green=34, blue=56)
		self.stick.set_color(index=1, red=78, green=90, blue=123)
		self.assertEqual(self.handle.send_feature_report.call_args_list, [
			call(bytes([5, 0, 0, 12, 34, 56])),
			call(bytes([5, 0, 1, 78, 90, 123])),
		])
		self.assertEqual(self.stick._get_color_rgb(0), (12, 34, 56))
		self.assertEqual(self.stick._get_color_rgb(1), (78, 90, 123))
		self.stick.set_color(index=1, blue=255)
		self.assertEqual(self.stick._get_color_rgb(0), (12, 34, 56))
		self.assertEqual(self.stick.get_color(index=1), (0, 0, 255))
		self.assertEqual(self.stick.get_color(index=1, color_format="hex"), "#0000ff")
		self.handle.get_feature_report.assert_not_called()

	def test_morph_and_pulse_on_second_led_leave_first_led_unchanged(self):
		self.stick.set_color(index=0, red=11, green=22, blue=33)
		self.stick.set_color(index=1, red=100)
		self.handle.send_feature_report.reset_mock()
		with patch.object(blink_device.blinkstick.time, "sleep"):
			self.stick.morph(index=1, blue=80, duration=0, steps=2)
			self.assertEqual(self.stick._get_color_rgb(1), (0, 0, 80))
			self.stick.pulse(index=1, green=70, repeats=2, duration=0, steps=2)
		self.assertEqual(self.stick._get_color_rgb(0), (11, 22, 33))
		self.assertEqual(self.stick._get_color_rgb(1), (0, 0, 0))
		for write in self.handle.send_feature_report.call_args_list:
			self.assertEqual(write.args[0][:3], bytes([5, 0, 1]))

	def test_short_write_does_not_update_either_cached_color(self):
		self.stick.set_color(index=0, red=10)
		self.stick.set_color(index=1, green=20)
		self.handle.send_feature_report.side_effect = lambda report: len(report) - 1
		for index in (0, 1):
			with self.subTest(index=index), self.assertRaises(OSError):
				self.stick.set_color(index=index, blue=30)
		self.assertEqual(self.stick._get_color_rgb(0), (10, 0, 0))
		self.assertEqual(self.stick._get_color_rgb(1), (0, 20, 0))

	def test_rejects_malformed_reports_without_writing(self):
		for report_id, data in ((1, b"\0\1\2"), (1, b"\0\1\2\3\4"), (5, b"\5\0\1\2\3"), (5, b"\5\0\1\2\3\4\5")):
			with self.subTest(report_id=report_id, data=data), self.assertRaises(ValueError):
				self.stick._usb_ctrl_transfer(0x20, 0x09, report_id, 0, data)
		self.handle.send_feature_report.assert_not_called()

	def test_single_led_transport_preserves_legacy_report(self):
		stick = blink_device.MacBlinkStick(b"single-led", led_count=1)
		stick.set_color(red=12, green=34, blue=56)
		self.handle.send_feature_report.assert_called_once_with(bytes([1, 12, 34, 56]))

	def test_nano_indexed_writes_preserve_inverse_colors(self):
		self.stick.inverse = True
		self.stick.set_color(index=0, red=12, green=34, blue=56)
		self.stick.set_color(index=1, red=78, green=90, blue=123)
		self.assertEqual(self.handle.send_feature_report.call_args_list, [
			call(bytes([5, 0, 0, 243, 221, 199])),
			call(bytes([5, 0, 1, 177, 165, 132])),
		])
		self.assertEqual(self.stick.get_color(index=0), (12, 34, 56))
		self.assertEqual(self.stick.get_color(index=1), (78, 90, 123))

	def test_single_led_transport_rejects_second_led(self):
		stick = blink_device.MacBlinkStick(b"single-led", led_count=1)
		with self.assertRaises(NotImplementedError):
			stick.set_color(index=1, red=255)
		self.handle.send_feature_report.assert_not_called()
		self.assertEqual(blink_device.led_indices(stick), (0,))

	def test_rejects_unsupported_leds_and_channels_without_writing(self):
		for channel, index in ((1, 0), (1, 1), (0, 2)):
			with self.subTest(channel=channel, index=index), self.assertRaises(NotImplementedError):
				self.stick.set_color(channel=channel, index=index, red=255)
		self.handle.send_feature_report.assert_not_called()

	def test_shutdown_clears_both_leds_and_closes_handle(self):
		blink_device.close_device(self.stick)
		self.assertEqual(self.handle.send_feature_report.call_args_list, [
			call(bytes([5, 0, 0, 0, 0, 0])),
			call(bytes([5, 0, 1, 0, 0, 0])),
		])
		self.handle.close.assert_called_once_with()

	def test_shutdown_attempts_second_led_and_releases_after_first_write_fails(self):
		self.handle.send_feature_report.side_effect = [OSError("Disconnected"), 6]
		with self.assertRaises(OSError):
			blink_device.close_device(self.stick)
		self.assertEqual(self.handle.send_feature_report.call_count, 2)
		self.assertEqual(self.handle.send_feature_report.call_args.args[0], bytes([5, 0, 1, 0, 0, 0]))
		self.handle.close.assert_called_once_with()

	def test_cleanup_without_turning_off_performs_no_writes(self):
		blink_device.close_device(self.stick, turn_off=False)
		self.handle.send_feature_report.assert_not_called()
		self.handle.close.assert_called_once_with()


class AllLedTests(unittest.TestCase):
	def test_all_helpers_mirror_nano_but_preserve_single_led_behavior(self):
		for variant, indices in ((blink_device.blinkstick.BlinkStick.BLINKSTICK_NANO, (0, 1)), (blink_device.blinkstick.BlinkStick.BLINKSTICK, (0,))):
			for helper_name, method_name in (("set_all", "set_color"), ("morph_all", "morph")):
				with self.subTest(variant=variant, helper=helper_name):
					device = Mock()
					device.get_variant.return_value = variant
					getattr(blink_device, helper_name)(device, name="red")
					self.assertEqual(getattr(device, method_name).call_args_list, [call(index=index, name="red") for index in indices])

	def test_pulse_all_clears_both_leds_and_repeats_each_color_phase(self):
		for variant, indices in ((blink_device.blinkstick.BlinkStick.BLINKSTICK_NANO, (0, 1)), (blink_device.blinkstick.BlinkStick.BLINKSTICK, (0,))):
			with self.subTest(variant=variant):
				device = Mock()
				device.get_variant.return_value = variant
				blink_device.pulse_all(device, name="red", repeats=2, duration=20)
				self.assertEqual(device.set_color.call_args_list, [call(index=index) for index in indices])
				expected = [call(index=index, duration=20, name="red") for index in indices]
				expected += [call(index=index, duration=20) for index in indices]
				self.assertEqual(device.morph.call_args_list, expected * 2)
				device.pulse.assert_not_called()

	def test_blink_all_lights_and_clears_each_led_on_every_repeat(self):
		for variant, indices in ((blink_device.blinkstick.BlinkStick.BLINKSTICK_NANO, (0, 1)), (blink_device.blinkstick.BlinkStick.BLINKSTICK, (0,))):
			with self.subTest(variant=variant), patch.object(blink_device.time, "sleep"):
				device = Mock()
				device.get_variant.return_value = variant
				blink_device.blink_all(device, name="red", repeats=2, delay=20)
				expected = [call(index=index, name="red") for index in indices]
				expected += [call(index=index) for index in indices]
				self.assertEqual(device.set_color.call_args_list, expected * 2)

	def test_non_mac_cleanup_clears_each_nano_led_and_disposes_usb_resources(self):
		device = Mock()
		device.get_variant.return_value = blink_device.blinkstick.BlinkStick.BLINKSTICK_NANO
		with patch("usb.util.dispose_resources") as dispose:
			blink_device.close_device(device)
		self.assertEqual(device.set_color.call_args_list, [call(index=0), call(index=1)])
		dispose.assert_called_once_with(device.device)


class LinuxTransportTests(unittest.TestCase):
	def setUp(self):
		self.device = Mock(bcdDevice=0x202)
		self.device.is_kernel_driver_active.return_value = False
		self.device.ctrl_transfer.side_effect = lambda request_type, request, report, interface, data: len(data)
		for active_patch in (patch.object(blink_device.sys, "platform", "linux"), patch("usb.util.get_string", return_value="BS000001-3.0"), patch.object(blink_device.time, "sleep")):
			active_patch.start()
			self.addCleanup(active_patch.stop)
		self.stick = blink_device.LinuxBlinkStick(self.device)

	def test_both_nano_leds_use_indexed_pyusb_reports(self):
		self.stick.set_color(index=0, red=12, green=34, blue=56)
		self.stick.set_color(index=1, red=78, green=90, blue=123)
		self.assertEqual(self.device.ctrl_transfer.call_args_list, [
			call(0x20, 0x09, 5, 0, bytes([5, 0, 0, 12, 34, 56])),
			call(0x20, 0x09, 5, 0, bytes([5, 0, 1, 78, 90, 123])),
		])

	def test_nano_inverse_colors_and_shutdown_use_indexed_reports(self):
		self.stick.inverse = True
		self.stick.set_color(index=0, red=10, green=20, blue=30)
		self.assertEqual(self.device.ctrl_transfer.call_args, call(0x20, 0x09, 5, 0, bytes([5, 0, 0, 245, 235, 225])))
		self.stick.inverse = False
		with patch("usb.util.dispose_resources") as dispose:
			blink_device.close_device(self.stick)
		self.assertEqual(self.device.ctrl_transfer.call_args_list[-2:], [
			call(0x20, 0x09, 5, 0, bytes([5, 0, 0, 0, 0, 0])),
			call(0x20, 0x09, 5, 0, bytes([5, 0, 1, 0, 0, 0])),
		])
		dispose.assert_called_once_with(self.device)

	def test_other_variants_and_feature_reads_keep_original_reports(self):
		self.device.bcdDevice = 0x200
		other = blink_device.LinuxBlinkStick(self.device)
		other.set_color(red=12)
		self.assertEqual(self.device.ctrl_transfer.call_args, call(0x20, 0x09, 1, 0, bytes([0, 12, 0, 0])))
		self.device.ctrl_transfer.side_effect = None
		self.device.ctrl_transfer.return_value = b"readback"
		self.assertEqual(self.stick._usb_ctrl_transfer(0xa0, 1, 1, 0, 4), b"readback")
		self.assertEqual(self.device.ctrl_transfer.call_args, call(0xa0, 1, 1, 0, 4))

	def test_nano_writes_keep_firmware_spacing(self):
		with patch.object(blink_device.time, "monotonic", side_effect=[100, 100.005, 100.02]), patch.object(blink_device.time, "sleep") as sleep:
			self.stick.set_color(index=0, red=10)
			self.stick.set_color(index=1, green=20)
		sleep.assert_called_once()
		self.assertAlmostEqual(sleep.call_args.args[0], 0.015)


class DiscoveryTests(unittest.TestCase):
	def test_mac_discovery_opens_every_device_and_detects_nano_metadata(self):
		handles = [Mock(), Mock(), Mock()]
		hid = SimpleNamespace(device=Mock(side_effect=handles), enumerate=Mock(return_value=[
			{"path": b"nano-release", "serial_number": "BS000001-3.0", "release_number": 0x202},
			{"path": b"nano-name", "serial_number": "BS000002-3.0", "product_string": "BlinkStick Nano"},
			{"path": b"classic", "serial_number": "BS000003-1.0", "release_number": 0x100},
		]))
		with patch.object(blink_device.sys, "platform", "darwin"), patch.dict("sys.modules", {"hid": hid}):
			devices = blink_device.find_all()
		self.assertEqual(len(devices), 3)
		self.assertEqual([tuple(blink_device.led_indices(device)) for device in devices], [(0, 1), (0, 1), (0,)])
		self.assertEqual([device.get_serial() for device in devices], ["BS000001-3.0", "BS000002-3.0", "BS000003-1.0"])
		hid.enumerate.assert_called_once_with(blink_device.blinkstick.VENDOR_ID, blink_device.blinkstick.PRODUCT_ID)
		for handle, path in zip(handles, (b"nano-release", b"nano-name", b"classic")):
			handle.open_path.assert_called_once_with(path)

	def test_partial_discovery_failure_closes_every_opened_handle(self):
		first, failed = Mock(), Mock()
		failed.open_path.side_effect = OSError("Cannot open second device")
		hid = SimpleNamespace(device=Mock(side_effect=[first, failed]), enumerate=Mock(return_value=[
			{"path": b"first", "release_number": 0x202},
			{"path": b"second", "release_number": 0x202},
		]))
		with patch.object(blink_device.sys, "platform", "darwin"), patch.dict("sys.modules", {"hid": hid}), self.assertRaises(OSError):
			blink_device.find_all()
		first.close.assert_called_once_with()
		failed.close.assert_called_once_with()
		first.send_feature_report.assert_not_called()

	def test_non_mac_discovery_uses_upstream_backend(self):
		devices = [Mock(), Mock()]
		with patch.object(blink_device.sys, "platform", "win32"), patch.object(blink_device.blinkstick, "find_all", return_value=devices) as find:
			self.assertIs(blink_device.find_all(), devices)
		find.assert_called_once_with()

	def test_linux_discovery_uses_adapter_for_first_and_all_devices(self):
		first, second = Mock(), Mock()
		with patch.object(blink_device.sys, "platform", "linux"), patch("usb.core.find", return_value=first) as find, patch.object(blink_device, "LinuxBlinkStick") as adapter:
			self.assertIs(blink_device.find_first(), adapter.return_value)
			adapter.assert_called_once_with(first)
			find.assert_called_once_with(idVendor=blink_device.blinkstick.VENDOR_ID, idProduct=blink_device.blinkstick.PRODUCT_ID)
		with patch.object(blink_device.sys, "platform", "linux"), patch("usb.core.find", return_value=[first, second]), patch.object(blink_device, "LinuxBlinkStick", side_effect=["first", "second"]) as adapter:
			self.assertEqual(blink_device.find_all(), ["first", "second"])
			self.assertEqual(adapter.call_args_list, [call(first), call(second)])

	def test_linux_missing_device_returns_none(self):
		with patch.object(blink_device.sys, "platform", "linux"), patch("usb.core.find", return_value=None), patch.object(blink_device, "LinuxBlinkStick") as adapter:
			self.assertIsNone(blink_device.find_first())
		adapter.assert_not_called()

	def test_linux_partial_discovery_failure_releases_opened_device(self):
		first, failed = Mock(), Mock()
		with patch.object(blink_device.sys, "platform", "linux"), patch("usb.core.find", return_value=[first, failed]), patch.object(blink_device, "LinuxBlinkStick", side_effect=[SimpleNamespace(device=first), OSError("Cannot open")]), patch("usb.util.dispose_resources") as dispose:
			with self.assertRaises(OSError):
				blink_device.find_all()
		dispose.assert_called_once_with(first)

	def test_linux_adapter_initialization_failure_releases_usb_device(self):
		device = Mock()
		device.is_kernel_driver_active.return_value = True
		from usb.core import USBError

		device.detach_kernel_driver.side_effect = USBError("Access denied")
		with patch.object(blink_device.sys, "platform", "linux"), patch("usb.util.dispose_resources") as dispose:
			with self.assertRaises(blink_device.blinkstick.BlinkStickException):
				blink_device.LinuxBlinkStick(device)
		dispose.assert_called_once_with(device)

	def test_linux_initial_serial_read_failure_remains_a_device_error(self):
		from usb.core import USBError

		device = Mock()
		device.is_kernel_driver_active.return_value = False
		with patch.object(blink_device.sys, "platform", "linux"), patch("usb.util.get_string", side_effect=USBError("Disconnected")), patch("usb.util.dispose_resources") as dispose, patch.object(blink_device.blinkstick.BlinkStick, "_refresh_device") as refresh:
			with self.assertRaises(blink_device.DEVICE_ERRORS):
				blink_device.LinuxBlinkStick(device)
		refresh.assert_not_called()
		dispose.assert_called_once_with(device)


if __name__ == "__main__":
	unittest.main()
