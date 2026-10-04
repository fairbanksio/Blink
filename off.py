from blink_device import close_device, find_all, set_all

for b in find_all():
	try:
		set_all(b)
		print(f"{b.get_serial()} turned off")
	finally:
		close_device(b, turn_off=False)
