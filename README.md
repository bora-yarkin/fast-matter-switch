# Fast Matter switch

A Home Assistant custom integration. The Matter integration reports a button that supports multi-press (for example the
IKEA BILRESA) only after the double-press window has run out, and drops its "initial press" event. This integration
opens a second connection to the same Matter server and fires every Matter Generic Switch event on the event bus as
`fast_matter_switch_event`, so an automation can react at the first touch.

## Install

Copy `custom_components/fast_matter_switch` to `/config/custom_components/`, restart Home Assistant, then add
**Fast Matter switch** under Settings, Devices & services. It needs the Matter integration and uses its server address.

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
