from blink_device import close_device, find_first, morph_all, pulse_all, set_all
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from sys import argv
import time

script, url = argv
b = find_first()

if b is None:
	print("No BlinkSticks found...")
else:
	try:
		request = Request(url, headers={"User-Agent": "Blink-URL-Check/1.0"})
		try:
			with urlopen(request, timeout=15) as response:
				status = response.getcode()
		except HTTPError as error:
			status = error.code
			error.close()
		except (URLError, TimeoutError) as error:
			status = None
			print(f"URL check failed: {error}")
		if status is not None:
			print(status)
		if status == 200:
			set_all(b, name="green")
		else:
			pulse_all(b, name="red", repeats=10, duration=300)
			morph_all(b, name="red")
		time.sleep(5)
	finally:
		close_device(b)
