# Fast Matter switch

[![CI](https://github.com/bora-yarkin/fast-matter-switch/actions/workflows/ci.yml/badge.svg)](https://github.com/bora-yarkin/fast-matter-switch/actions/workflows/ci.yml)
[![Add to HACS](https://img.shields.io/badge/HACS-custom%20repository-41BDF5.svg)](#install-with-hacs)

A Home Assistant custom integration that reacts to a Matter button **at the first touch**.

The Matter integration reports a button that supports multi-press (the IKEA BILRESA, for example) only after the
double-press window has run out, and it drops the switch's "initial press" event. Press once and the light waits
for the switch to be sure you are not pressing twice. Fast Matter switch listens to the same Matter server
directly and reports every touch the moment the switch sends it.

It works with **any Matter switch or button** (any device with the Matter Generic Switch / Switch cluster): nothing
in it is specific to one brand or model. It has no settings.

## What you get

For every Matter button, an **event entity** named after it with "fast" added, in the same area as the switch:

| Switch | Event entity | Reports |
|---|---|---|
| IKEA BILRESA, button 1 | `event.<switch name>_button_1_fast` | `press`, `double_press`, `long_press` |

and a bus event, `fast_matter_switch_event`, for automations that need every detail.

- `press` is sent at the first touch, not after the double-press window.
- `double_press` is sent when the switch reports two presses.
- `long_press` is sent when the switch reports a long press.
- The second touch of a double press (and a press a switch reports twice) is **not** reported as a `press`: a touch
  within 800 ms of the previous touch of the same button is treated as the second touch. A deliberate second press
  after more than 800 ms is a new `press`.
- The entity follows the Matter button: it is added when a button appears and removed when the button goes.
- The entity has no device of its own (Home Assistant gives a device to one integration only), so it is listed under
  the entities of the area it starts in.

## Requirements

- Home Assistant with the **Matter** integration set up and working, with a Matter server (the Matter Server app or
  any `python-matter-server`). Fast Matter switch reads the server address from the Matter integration.
- One or more Matter switches or buttons already added to Matter.
- Developed and tested on Home Assistant 2026.10, with IKEA BILRESA buttons. Other switches should work the same way
  because they use the same Matter cluster, but only the BILRESA has been tried on real hardware.

## Install with HACS

Fast Matter switch is not in the default HACS list; add it as a custom repository.

1. In Home Assistant open **HACS**, then the three-dot menu, then **Custom repositories**.
2. Repository: `https://github.com/bora-yarkin/fast-matter-switch`, type: **Integration**. Add it.
3. Find **Fast Matter switch** in HACS, download it, and **restart Home Assistant**.
4. Go to **Settings, Devices & services, Add integration**, choose **Fast Matter switch** and confirm. There is nothing
   to configure.

## Install by hand

Copy the folder `custom_components/fast_matter_switch` of this repository into `/config/custom_components/` (so that
`/config/custom_components/fast_matter_switch/manifest.json` exists), restart Home Assistant, and add the integration
as in step 4 above.

## Use it in an automation

### In the automation editor (no YAML)

Add a trigger **Event received**, pick the entity
(for example `event.living_room_remote_button_1_fast`), then the event types you want: `press`, `double_press` or
`long_press`.

### In YAML

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.living_room_remote_button_1_fast
    options:
      event_type: [press]
```

Or, with the bus event, which also carries the node and the press count:

```yaml
triggers:
  - trigger: event
    event_type: fast_matter_switch_event
    event_data:
      entity_id: event.living_room_remote_button_1_fast
      event_type: initial_press
```

(The bus event's `entity_id` is the *Matter integration's own* event entity of the button, not the `_fast` one; look it
up in the event's data in **Developer tools, Events** by listening to `fast_matter_switch_event` and pressing the
button.)

## The bus event

`fast_matter_switch_event` is fired for every event of the Matter Switch cluster. Its data:

| Field | Meaning |
|---|---|
| `event_type` | `switch_latched`, `initial_press`, `short_release`, `long_press`, `long_release`, `multi_press_ongoing` or `multi_press_complete` |
| `entity_id` | the Matter integration's event entity of the button, or `None` if it has none |
| `device_id` | that entity's device, or `None` |
| `node_id`, `endpoint_id` | where the event came from on the Matter fabric |
| `presses` | the number of presses counted, on `multi_press_ongoing` and `multi_press_complete` |
| `since_last_press_ms` | on `initial_press` only: milliseconds since the same button's previous `initial_press`, `None` the first time |
| `position` | on `switch_latched` only: the position a latching switch (a rocker) moved to |

Latching switches (rockers that stay in a position) report `switch_latched` on the bus event only; they get no event
entity yet. That path follows the Matter specification and has not been tried on a real latching switch.

## How it works

- It opens one extra connection to the Matter server the Matter integration already uses, asks for events
  (`start_listening`) and ignores everything that is not a Switch cluster event. The first answer carries every node and
  is a few hundred kilobytes; messages up to 16 MB are accepted.
- If the connection drops it tries again after 1 second, then 2, 4, up to 30 seconds. A connection that held for 30
  seconds or more starts the count again.
- A message it cannot read is logged and skipped; the next one is served.
- It reads the Matter integration's entity registry to find which entity belongs to which button, using the node and
  endpoint in the entity's unique id. If a Home Assistant update changes that id format, buttons are still reported on
  the bus with `entity_id: None` and get no event entity until the integration is updated.
- Nothing leaves your network: the only address it contacts is your Matter server's.

## Troubleshooting

- **The integration says Matter is missing**: set up the Matter integration first.
- **No `_fast` entity for a button**: restart Home Assistant after adding the integration, and check that the Matter
  integration shows an event entity for that button (Settings, Devices & services, Matter).
- **Nothing happens on a press**: enable debug logging for `custom_components.fast_matter_switch` and press the
  button; "Listening to Matter switch events" in the log confirms the connection. Listen to
  `fast_matter_switch_event` in Developer tools, Events to see what arrives.
- **A press is reported as a double press and a press**: report it with the log lines; a switch that reports its first
  press twice is handled by the 800 ms rule.

## Not measured

How many milliseconds this saves compared with the Matter integration's own event depends on the switch.

## Development

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python pytest-homeassistant-custom-component ruff
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The tests run the integration against a real WebSocket server standing in for the Matter server. See
[`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md).

## Licence

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
