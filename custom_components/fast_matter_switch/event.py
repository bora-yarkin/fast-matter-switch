# SPDX-License-Identifier: GPL-3.0-or-later
"""One event entity for each Matter button, reporting it at the first touch.

The entity is named after the Matter integration's own event entity for that button, with "fast" added, and starts in the
same area. It has no device: Home Assistant gives a device to one integration only, and a second device for each switch would
only be a duplicate in the device list. Its event types are ``press`` (the first touch of a press, not the second touch of a double press),
``double_press`` and ``long_press``. An automation uses it with the Event received trigger, which the automation editor
shows with no YAML: pick the entity, then the event types.
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_ENTITY_TYPES, MATTER_DOMAIN, dispatch_signal

UNIQUE_ID_SUFFIX = "-fast"


def is_matter_button(entry: er.RegistryEntry) -> bool:
    """A Matter event entity is a button of the Switch cluster."""
    return entry.platform == MATTER_DOMAIN and entry.domain == "event"


class FastButton(EventEntity):
    """What one button reports at the first touch."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_event_types = EVENT_ENTITY_TYPES

    def __init__(self, button: er.RegistryEntry, device: dr.DeviceEntry | None) -> None:
        self._button_unique_id = button.unique_id
        self._attr_unique_id = button.unique_id + UNIQUE_ID_SUFFIX
        # With no device of its own, the switch's name goes into the entity's.
        switch = (device.name_by_user or device.name) if device else None
        self._attr_name = " ".join(filter(None, [switch, button.original_name or "Button", "fast"]))

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, dispatch_signal(self._button_unique_id), self._reported))

    @callback
    def _reported(self, event_type: str) -> None:
        self._trigger_event(event_type)
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Gives every Matter button an entity, now and when one is added later, and takes it away with the button."""
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    with_entity: set[str] = set()

    @callback
    def follow_matter_buttons(_event: Event | None = None) -> None:
        buttons = {e.unique_id: e for e in entities.entities.values() if is_matter_button(e)}
        for ours in er.async_entries_for_config_entry(entities, entry.entry_id):
            matter_unique_id = ours.unique_id.removesuffix(UNIQUE_ID_SUFFIX)
            if matter_unique_id not in buttons:
                entities.async_remove(ours.entity_id)
                with_entity.discard(matter_unique_id)
        new = [b for unique_id, b in buttons.items() if unique_id not in with_entity]
        with_entity.update(b.unique_id for b in new)
        for button in new:
            device = devices.async_get(button.device_id) if button.device_id else None
            if entities.async_get_entity_id("event", DOMAIN, button.unique_id + UNIQUE_ID_SUFFIX) is None:
                # Registered first so that the entity id follows the Matter entity's, ``event.<button>_fast``, and the
                # area is the switch's (or the button's own).
                created = entities.async_get_or_create(
                    "event",
                    DOMAIN,
                    button.unique_id + UNIQUE_ID_SUFFIX,
                    config_entry=entry,
                    suggested_object_id=f"{button.entity_id.removeprefix('event.')}_fast",
                )
                area_id = button.area_id or (device.area_id if device else None)
                if area_id:
                    entities.async_update_entity(created.entity_id, area_id=area_id)
        async_add_entities(FastButton(b, devices.async_get(b.device_id) if b.device_id else None) for b in new)

    @callback
    def is_event_entity(data: er.EventEntityRegistryUpdatedData) -> bool:
        return data["entity_id"].startswith("event.")

    follow_matter_buttons()
    entry.async_on_unload(hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, follow_matter_buttons, event_filter=is_event_entity))
