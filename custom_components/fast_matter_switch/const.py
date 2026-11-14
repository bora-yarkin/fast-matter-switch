# SPDX-License-Identifier: GPL-3.0-or-later
"""Constants for Fast Matter switch."""

from datetime import timedelta

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


# ---- reachability of sleepy devices (binary_sensor.py) ----

# How often every sleepy Matter device is pinged. A battery device answers a ping only when it next polls its parent, so one
# ping takes several seconds; a device that stays silent for the whole deadline is reported unreachable.
SCAN_INTERVAL = timedelta(minutes=10)
PING_DEADLINE_S = 90

# The Matter server sends every node in one message, which is a few hundred kilobytes.
MAX_MESSAGE_BYTES = 16 * 1024 * 1024

# A Thread device reports how it takes part in the mesh in the Thread Network Diagnostics cluster (53), attribute RoutingRole (1).
# 2 is a sleepy end device: a battery device that wakes to poll its parent. These are the devices whose availability in Home
# Assistant says little, because nothing is heard from them between button presses.
ROUTING_ROLE_ATTRIBUTE = "0/53/1"
SLEEPY_END_DEVICE = 2
