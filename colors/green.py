from _device import close_device, find_first, set_all

bstick = find_first()

if bstick is None:
	print("No BlinkSticks found...")
else:
	try:
		print("Green")
		set_all(bstick, name="green")
	finally:
		close_device(bstick, turn_off=False)
