from _device import close_device, find_first, morph_all

b = find_first()

if b is None:
	print("No BlinkSticks found...")
else:
	try:
		print("Party Time!")
		while True:
			morph_all(b, name="red")
			morph_all(b, name="green")
			morph_all(b, name="blue")
	except KeyboardInterrupt:
		pass
	finally:
		close_device(b)
