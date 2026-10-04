from blink_device import close_device, find_first, set_all
import psutil

b = find_first()

if b is None:
	print("No BlinkSticks found...")
else:
	print("Displaying CPU usage (Green = 0%, Amber = 50%, Red = 100%)")
	print("Press Ctrl+C to exit")
	try:
		while True:
			cpu = psutil.cpu_percent(interval=1)
			intensity = int(255 * cpu / 100)
			set_all(b, red=intensity, green=255 - intensity, blue=0)
	except KeyboardInterrupt:
		print("\nCPU monitoring stopped.")
	finally:
		close_device(b)
