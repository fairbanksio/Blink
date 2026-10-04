import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError

import kube


def node(name, ready="True", pressure=()):
	conditions = [] if ready is None else [NS(type="Ready", status=ready)]
	conditions += [NS(type=kind, status="True") for kind in pressure]
	return NS(metadata=NS(name=name), status=NS(conditions=conditions))


class MonitorTests(unittest.TestCase):
	def run_monitor(self, results, devices, sleeps, display_errors=None):
		api = Mock()
		api.list_node.side_effect = [NS(items=result) if isinstance(result, list) else result for result in results]
		output = io.StringIO()
		with patch.object(kube, "find_first", side_effect=devices) as find, patch.object(kube, "close_device") as close, patch.object(kube, "display", side_effect=display_errors) as display, patch.object(kube.time, "sleep", side_effect=sleeps) as sleep, redirect_stdout(output):
			self.assertEqual(kube.monitor(api), 0)
		return api, find, close, display, sleep, output.getvalue()

	def test_pressure_and_readiness_priority(self):
		for pressure in kube.PRESSURE_CONDITIONS:
			with self.subTest(pressure=pressure):
				self.assertEqual(kube.cluster_state([node("a", pressure=[pressure])])[0], "amber")
		for ready in ("False", "Unknown", None):
			self.assertEqual(kube.cluster_state([node("a", ready, ["DiskPressure"]), node("b")])[0], "red")
		self.assertEqual(kube.cluster_state([])[0], "red")
		self.assertEqual(kube.cluster_state([node("a")])[0], "green")

	def test_condition_and_node_order_do_not_change_status(self):
		nodes = [node("b", pressure=["PIDPressure", "DiskPressure"]), node("a", pressure=["MemoryPressure"])]
		expected = kube.cluster_state(nodes)
		for item in nodes:
			item.status.conditions.reverse()
		self.assertEqual(kube.cluster_state(nodes[::-1]), expected)

	def test_api_failure_recovery_backoff_and_changed_logs(self):
		stick = Mock()
		failure = MaxRetryError(None, "", "Unavailable")
		results = [failure, failure, [node("a")], failure]
		api, _, close, display, sleep, output = self.run_monitor(results, [stick], [None, None, None, KeyboardInterrupt()])
		self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 10, 2])
		self.assertEqual([call.args[1] for call in display.call_args_list], ["purple", "purple", "green", "purple"])
		self.assertEqual(output.count("Cluster API unavailable"), 2)
		for call in api.list_node.call_args_list:
			self.assertEqual(call.kwargs["_request_timeout"], (3, 7))
		close.assert_called_once_with(stick, turn_off=True)

	def test_http_error_shows_purple(self):
		_, _, _, display, _, output = self.run_monitor([ApiException(status=403)], [Mock()], [KeyboardInterrupt()])
		self.assertEqual(display.call_args.args[1], "purple")
		self.assertIn("HTTP 403", output)

	def test_retry_delay_is_capped_and_repeated_failure_logs_once(self):
		failure = ApiException(status=503)
		_, _, _, _, sleep, output = self.run_monitor([failure] * 7, [Mock()], [None] * 6 + [KeyboardInterrupt()])
		self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8, 16, 30, 30, 30])
		self.assertEqual(output.count("Cluster API unavailable"), 1)

	def test_main_disables_client_retries(self):
		settings = kube.client.Configuration()
		with patch.object(kube.client, "Configuration", return_value=settings), patch.object(kube.config, "load_kube_config"), patch.object(kube.client, "ApiClient"), patch.object(kube.client, "CoreV1Api"), patch.object(kube, "monitor", return_value=0):
			self.assertEqual(kube.main(), 0)
		self.assertEqual(settings.retries, 0)

	def test_waits_and_recovers_from_discovery_error(self):
		stick = Mock()
		_, find, close, display, _, output = self.run_monitor([[node("a")]] * 3, [None, OSError("Open failed"), stick], [None, None, KeyboardInterrupt()])
		self.assertEqual(find.call_count, 3)
		self.assertEqual(output.count("Waiting for a BlinkStick"), 1)
		self.assertEqual(output.count("All nodes ready"), 1)
		display.assert_called_once_with(stick, "green", changed=True)
		close.assert_called_once_with(stick, turn_off=True)

	def test_reconnect_restores_unchanged_warning(self):
		first, second = Mock(), Mock()
		warning = [node("a", pressure=["DiskPressure"])]
		_, _, close, display, _, output = self.run_monitor([warning, warning], [first, second], [None, KeyboardInterrupt()], [OSError("Unplugged"), None])
		self.assertEqual([call.args for call in display.call_args_list], [(first, "amber"), (second, "amber")])
		self.assertEqual(close.call_args_list[0].kwargs, {"turn_off": False})
		self.assertEqual(close.call_args_list[1].kwargs, {"turn_off": True})
		self.assertEqual(output.count("Node pressure:"), 1)

	def test_unplug_during_each_steady_warning_reconnects(self):
		for result, color in (([node("a", "False")], "red"), ([node("a", pressure=["DiskPressure"])], "amber"), (ApiException(status=503), "purple")):
			with self.subTest(color=color):
				first, second = Mock(), Mock()
				_, _, close, display, _, _ = self.run_monitor([result] * 3, [first, second], [None, None, KeyboardInterrupt()], [None, OSError("Unplugged"), None])
				self.assertEqual([call.args for call in display.call_args_list], [(first, color), (first, color), (second, color)])
				self.assertEqual([call.kwargs["changed"] for call in display.call_args_list], [True, False, True])
				self.assertEqual(close.call_args_list[0].kwargs, {"turn_off": False})

	def test_keyboard_interrupt_without_device_exits_cleanly(self):
		_, _, close, display, _, _ = self.run_monitor([[node("a")]], [None], [KeyboardInterrupt()])
		close.assert_not_called()
		display.assert_not_called()

	def test_cleanup_failure_does_not_mask_interrupt(self):
		with patch.object(kube, "find_first", return_value=Mock()), patch.object(kube, "close_device", side_effect=OSError("Disconnected")), patch.object(kube, "display"), patch.object(kube.time, "sleep", side_effect=KeyboardInterrupt()), redirect_stdout(io.StringIO()):
			api = Mock()
			api.list_node.return_value.items = [node("a")]
			self.assertEqual(kube.monitor(api), 0)

	def test_amber_uses_explicit_rgb_and_unknown_is_purple(self):
		stick = Mock()
		kube.display(stick, "amber")
		stick.set_color.assert_called_once_with(index=0, hex="#ffbf00")
		stick.reset_mock()
		kube.display(stick, "purple")
		stick.set_color.assert_called_once_with(index=0, name="purple")
		stick.reset_mock()
		kube.display(stick, "red", changed=False)
		stick.set_color.assert_called_once_with(index=0, name="red")
		stick.pulse.assert_not_called()


if __name__ == "__main__":
	unittest.main()
