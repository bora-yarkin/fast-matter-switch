# Fast Matter switch

A Home Assistant custom integration. The Matter integration reports a button that supports multi-press (for example the
IKEA BILRESA) only after the double-press window has run out, and drops its "initial press" event. This integration
opens a second connection to the same Matter server and fires every Matter Generic Switch event on the event bus as
`fast_matter_switch_event`, so an automation can react at the first touch.

## Install

Copy `custom_components/fast_matter_switch` to `/config/custom_components/`, restart Home Assistant, then add
**Fast Matter switch** under Settings, Devices & services. It needs the Matter integration and uses its server address.

## Event entities

Each Matter button gets an event entity, `event.<the Matter button's name>_fast`, in the same area as the switch. It reports `press` (the first touch of a press), `double_press` and `long_press`. A touch within 800 ms
of the previous touch of the same button is the second touch of a double press, or a press the switch reported twice, and is not reported as a `press`. In the automation editor use the **Event received** trigger,
pick the entity, then the event types; no YAML is needed. The entity has no device of its own (Home Assistant gives a device to one integration only); it is added when a Matter button appears and removed when it goes.

## Event

`fast_matter_switch_event` with `event_type` (`initial_press`, `short_release`, `long_press`, `long_release`,
`multi_press_ongoing`, `multi_press_complete`), `entity_id` and `device_id` of the button's Matter event entity,
`node_id`, `endpoint_id`, `presses` for the multi-press events, and `since_last_press_ms` on `initial_press` (milliseconds since the same button's previous initial press, `None` the first time) so an automation can act once on a double press or a press reported twice.

```yaml
triggers:
  - trigger: event
    event_type: fast_matter_switch_event
    event_data:
      entity_id: event.boras_bedroom_desk_switch_button_1
      event_type: initial_press
```

## How it behaves

- It opens one extra connection to the Matter server the Matter integration already uses, asks for events (`start_listening`) and ignores everything that is not a
  Generic Switch event. The first answer carries every node and is a few hundred kilobytes; messages up to 16 MB are accepted.
- If the connection drops it tries again after 1 second, then 2, 4, up to 30 seconds; a connection that held for 30 seconds or more starts the count again.
- A message it cannot read is logged and skipped; the next one is served.
- `entity_id` and `device_id` are `None` when the Matter integration has no event entity for that button.

## Tests

`tests/` runs the integration against a real WebSocket server standing in for the Matter server. Not measured: how many milliseconds it saves compared with the Matter
integration's own event, which depends on the switch.

## Licence

GPL-3.0-or-later. See `LICENSE`. Contributions: see `.github/CONTRIBUTING.md`.
