from _device import close_device, find_first, set_all

b = find_first()

if b is None:
	print("No BlinkSticks found...")
else:
	try:
		print("Red")
		set_all(b, name="red")
	finally:
		close_device(b, turn_off=False)
