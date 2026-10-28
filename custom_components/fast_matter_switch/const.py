"""Constants for Fast Matter switch."""

DOMAIN = "fast_matter_switch"
MATTER_DOMAIN = "matter"

# Fired on the Home Assistant event bus for every Matter Generic Switch event.
EVENT_NAME = "fast_matter_switch_event"

# The Matter Switch cluster, and its events as the Matter server numbers them.
SWITCH_CLUSTER_ID = 59
SWITCH_EVENT_TYPES = {
    1: "initial_press",
    2: "long_press",
    3: "short_release",
    4: "long_release",
    5: "multi_press_ongoing",
    6: "multi_press_complete",
}
