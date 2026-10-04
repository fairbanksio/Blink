"""Expose the shared device helpers when color scripts run directly."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blink_device import (
	blink_all,
	close_device,
	find_all,
	find_first,
	led_indices,
	morph_all,
	pulse_all,
	set_all,
)
