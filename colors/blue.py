from _device import close_device, find_first, set_all

b = find_first()

if b is None:
	print("No BlinkSticks found...")
else:
	try:
		print("Blue")
		set_all(b, name="blue")
	finally:
		close_device(b, turn_off=False)
