from blink_device import DEVICE_ERRORS, blink_all, close_device, find_first, morph_all, pulse_all, set_all
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from urllib3.exceptions import HTTPError
import sys
import time

POLL_INTERVAL = 10
REQUEST_TIMEOUT = (3, 7)
PRESSURE_CONDITIONS = {"MemoryPressure", "DiskPressure", "PIDPressure"}
API_ERRORS = (ApiException, HTTPError, OSError)


def node_is_ready(node):
	return any(
		condition.type == "Ready" and condition.status == "True"
		for condition in (node.status.conditions or [])
	)


def cluster_state(nodes):
	if not nodes:
		return "red", "No nodes found."
	unhealthy = sorted(node.metadata.name for node in nodes if not node_is_ready(node))
	if unhealthy:
		return "red", f"Nodes not ready: {', '.join(unhealthy)}"
	pressure = sorted(
		f"{node.metadata.name}: {condition.type}"
		for node in nodes
		for condition in (node.status.conditions or [])
		if condition.type in PRESSURE_CONDITIONS and condition.status == "True"
	)
	if pressure:
		return "amber", f"Node pressure: {'; '.join(pressure)}"
	return "green", "All nodes ready; no pressure warnings."


def display(device, color, changed=True):
	if color == "green":
		blink_all(device, name="green", delay=25)
	elif color == "amber":
		set_all(device, hex="#ffbf00")
	elif color == "purple":
		set_all(device, name="purple")
	elif changed:
		pulse_all(device, name="red", repeats=5, duration=200)
		morph_all(device, name="red")
	else:
		set_all(device, name="red")


def monitor(api):
	device = None
	displayed = None
	retry_delay = 2
	last_messages = {}

	def log_change(kind, message):
		if last_messages.get(kind) != message:
			print(message, flush=True)
			last_messages[kind] = message

	def release(turn_off):
		nonlocal device, displayed
		if device is not None:
			try:
				close_device(device, turn_off=turn_off)
			except DEVICE_ERRORS:
				pass
			device = None
			displayed = None

	print("Monitoring nodes with a 10-second pause between checks. Press Ctrl+C to exit.", flush=True)
	try:
		while True:
			if device is None:
				try:
					device = find_first()
				except DEVICE_ERRORS:
					device = None
				if device is None:
					log_change("usb", "Waiting for a BlinkStick. Reconnect the device to resume its light.")
				else:
					log_change("usb", "BlinkStick connected.")

			delay = POLL_INTERVAL
			try:
				state = cluster_state(api.list_node(_request_timeout=REQUEST_TIMEOUT).items)
				retry_delay = 2
			except API_ERRORS as error:
				detail = f"HTTP {error.status}" if isinstance(error, ApiException) and error.status else type(error).__name__
				state = "purple", f"Cluster API unavailable ({detail}). Retrying."
				delay = retry_delay
				retry_delay = min(retry_delay * 2, 30)
			log_change("cluster", state[1])

			if device is not None:
				try:
					# Refresh steady colors too, so an unplug is detected without a status change.
					display(device, state[0], changed=state != displayed)
					displayed = state
				except DEVICE_ERRORS:
					release(turn_off=False)
					log_change("usb", "Waiting for a BlinkStick. Reconnect the device to resume its light.")
			time.sleep(delay)
	except KeyboardInterrupt:
		print("\nMonitoring stopped.", flush=True)
	finally:
		release(turn_off=True)
	return 0


def main():
	settings = client.Configuration()
	config.load_kube_config(client_configuration=settings)
	# The monitor owns retries, so each request gets one bounded attempt.
	settings.retries = 0
	with client.ApiClient(settings) as api_client:
		return monitor(client.CoreV1Api(api_client))


if __name__ == "__main__":
	sys.exit(main())
