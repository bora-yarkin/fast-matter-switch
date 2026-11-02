# SPDX-License-Identifier: GPL-3.0-or-later
"""Constants for Fast Matter switch."""

DOMAIN = "fast_matter_switch"
MATTER_DOMAIN = "matter"

# Fired on the Home Assistant event bus for every Matter Generic Switch event.
EVENT_NAME = "fast_matter_switch_event"

# The Matter Switch cluster, and its events as the Matter server numbers them.
SWITCH_CLUSTER_ID = 59
SWITCH_EVENT_TYPES = {
    0: "switch_latched",
    1: "initial_press",
    2: "long_press",
    3: "short_release",
    4: "long_release",
    5: "multi_press_ongoing",
    6: "multi_press_complete",
}

# What each button's event entity reports (see event.py).
PRESS = "press"
DOUBLE_PRESS = "double_press"
LONG_PRESS = "long_press"
EVENT_ENTITY_TYPES = [PRESS, DOUBLE_PRESS, LONG_PRESS]

# A touch that follows the previous touch of the same button within this time is the second touch of a double press (or a
# press the switch reported twice), not a press of its own.
DOUBLE_TOUCH_MS = 800


def dispatch_signal(button_unique_id: str) -> str:
    """The signal the relay sends to the event entity of one Matter button."""
    return f"{DOMAIN}_{button_unique_id}"
