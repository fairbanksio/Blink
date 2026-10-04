from random import randint

from _device import close_device, find_all, set_all

for b in find_all():
	try:
		red, green, blue = (randint(0, 255) for _ in range(3))
		set_all(b, red=red, green=green, blue=blue)
		print(f"{b.get_serial()} was set to Hex: #{red:02x}{green:02x}{blue:02x}")
	finally:
		close_device(b, turn_off=False)
