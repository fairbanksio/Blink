# Blink

Status monitors and light patterns for BlinkStick devices, with support for both Nano LEDs.

## Setup

Use Python 3.13 or newer and uv. Install the dependencies with `uv sync`, then run a script with `uv run`.

On macOS, USB access uses native HID without sudo. Linux needs a libusb backend and USB permissions for the account running the scripts. The Kubernetes monitor also needs a kubeconfig with permission to list nodes.

## Kubernetes Monitor

Run `uv run kube.py`. The monitor checks node health, then waits ten seconds before checking again. Requests and status animations add time. It waits for a BlinkStick if none is connected. Both Nano LEDs show the same status.

| Color | Meaning |
| --- | --- |
| Green flash | All nodes are ready, with no pressure warnings |
| Amber | A ready node reports memory, disk, or PID pressure |
| Red | At least one node is not ready, or no nodes were returned |
| Purple | The Kubernetes API check failed; current node health is unknown |

Requests use three-second connection and seven-second read timeouts. Failed checks retry after 2, 4, 8, 16, then 30 seconds, capped at 30. A successful check restores normal polling. Readiness failures take priority over pressure warnings.

USB discovery and writes retry during polling. Reconnecting the device restores the latest status. Logs print when the cluster status or USB connection changes. Ctrl+C stops monitoring and attempts to turn both Nano LEDs off.

Run the monitor tests with `uv run python -m unittest discover -s tests -v`.

## Two-LED Nano Support

All device scripts use the shared transport in `blink_device.py`. On macOS, it uses native HID without sudo. The color, random, RGB, CPU, URL, and Kubernetes scripts mirror their output on both Nano LEDs. `off.py` clears both LEDs on every connected Nano. Other BlinkStick variants retain their single notification LED behavior.

```sh
uv run colors/blue.py
uv run colors/rand.py
uv run colors/rgb.py
uv run cpu.py
uv run url-check.py https://fairbanks.io
uv run off.py
```

Static and random colors stay on after the script exits. RGB and CPU monitoring clear both LEDs on Ctrl+C. The macOS transport keeps each LED's last commanded color separately for animations; this is not hardware readback. On macOS and Linux, both Nano LEDs use indexed color reports, with writes spaced at least 20 ms apart to let the firmware finish updating. Linux uses PyUSB and requires USB device permissions and a libusb backend.

## Police Lights

`police.py` keeps red and blue on separate LEDs. It alternates rapid triple bursts, follows with slower single flashes, then pauses before repeating. It requires a two-LED Nano and clears both LEDs when stopped.

```sh
uv run police.py          # Repeat until Ctrl+C
uv run police.py --once   # Run one cycle and turn both LEDs off
```

## Rainbow Gradient

`rainbow.py` fades the LEDs in opposite directions through all 138 distinct named colors, ordered by hue. Black, white, gray, and darker shades are included. The loop fades smoothly back to its first color.

Use `--saturated` for a rainbow without the dark or neutral shades.

```sh
uv run rainbow.py
uv run rainbow.py --fade 2  # Slower, two-second transitions
uv run rainbow.py --once    # One palette cycle, then fade off
uv run rainbow.py --saturated  # Only saturated rainbow colors
```

LED 0 starts at the first palette color and moves forward. LED 1 starts at the last and moves backward. Their gradients may cross at the same color. Both LEDs receive each intermediate frame before the next frame starts. Timing accounts for USB writes. Ctrl+C clears both LEDs and closes the device.

## Fireplace and Storm

`fireplace.py` gives each LED its own smooth orange and amber flicker, with occasional dim red embers. `storm.py` keeps dim blue ambience between staggered white lightning bursts.

```sh
uv run fireplace.py
uv run fireplace.py --brightness 0.4
uv run storm.py
uv run storm.py --brightness 0.3
```

Both run until Ctrl+C and clear the LEDs when stopped. Add `--once` for a 10-second fireplace sample or one storm event. Single-LED devices also work.

## Ping Monitor

`ping.py` uses the system ping command to check an IPv4 address or hostname every two seconds. LED 0 is green when a reply arrives and red when no reply arrives. LED 1 shows latency: green below 50 ms, orange from 50 to below 200 ms, and red at 200 ms or higher. It turns off when no reply arrives; purple means a reply arrived without readable timing. A missing reply can also mean ICMP is blocked.

```sh
uv run ping.py                     # Check 1.1.1.1
uv run ping.py example.com
uv run ping.py 127.0.0.1 --once     # Check once and briefly show the result
uv run ping.py example.com --interval 5 --timeout 3 --warn-ms 100 --critical-ms 300
```

Each check prints its result. Ctrl+C clears both LEDs. Single-LED devices show connectivity only. `--once` returns 0 for a reply and 1 for no reply or a monitor error.
