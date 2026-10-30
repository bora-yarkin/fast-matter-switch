# SPDX-License-Identifier: GPL-3.0-or-later
"""The event entity of each Matter button: what it reports, where it is, and that it follows the Matter integration's entities."""

from __future__ import annotations

import asyncio

from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.fast_matter_switch.const import DOMAIN

from .conftest import node_event, unique_id


def fast_entity(hass, matter_entity):
    return er.async_get(hass).async_get_entity_id("event", DOMAIN, matter_entity.unique_id + "-fast")


async def reported(hass, entity_id: str, send, wait: float = 0.3) -> list[str]:
    """The event types the entity reports while ``send`` runs."""
    seen: list[str] = []

    @callback
    def record(event):
        state = event.data["new_state"]
        if state is not None and state.attributes.get("event_type"):
            seen.append(state.attributes["event_type"])

    unsubscribe = async_track_state_change_event(hass, entity_id, record)
    await send()
    await asyncio.sleep(wait)
    await hass.async_block_till_done()
    unsubscribe()
    return seen


async def test_every_matter_button_gets_an_event_entity_named_after_it(hass, relay, button):
    entity_id = fast_entity(hass, button)
    assert entity_id == f"{button.entity_id}_fast"
    state = hass.states.get(entity_id)
    assert state is not None and state.attributes["event_types"] == ["press", "double_press", "long_press"]


async def test_the_entity_has_no_device_of_its_own_is_named_after_the_switch_and_starts_in_its_area(hass, matter_entry, matter_server):
    matter = MockConfigEntry(domain="matter", data={"url": matter_server.url})
    matter.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Study")
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(config_entry_id=matter.entry_id, identifiers={("matter", "deviceid_41")}, name="Desk Switch")
    devices.async_update_device(device.id, area_id=area.id)
    button = er.async_get(hass).async_get_or_create(
        "event",
        "matter",
        unique_id(41, 1),
        config_entry=matter,
        device_id=device.id,
        original_name="Button (1)",
        suggested_object_id="desk_switch_button_1",
    )
    devices_before = len(dr.async_entries_for_config_entry(devices, matter.entry_id))
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ours = er.async_get(hass).async_get(fast_entity(hass, button))
    assert ours.device_id is None and ours.area_id == area.id
    assert dr.async_entries_for_config_entry(devices, entry.entry_id) == []  # no second device for the switch
    assert len(dr.async_entries_for_config_entry(devices, matter.entry_id)) == devices_before
    assert hass.states.get(ours.entity_id).attributes["friendly_name"] == "Desk Switch Button (1) fast"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_press_a_double_press_and_a_long_press_are_reported(hass, relay, matter_server, button):
    entity_id = fast_entity(hass, button)

    async def send():
        await matter_server.send(node_event(41, 1, 1))  # first touch
        await matter_server.send(node_event(41, 1, 6, {"totalNumberOfPressesCounted": 2}))
        await matter_server.send(node_event(41, 1, 2))  # long press

    assert await reported(hass, entity_id, send) == ["press", "double_press", "long_press"]


async def test_the_second_touch_of_a_double_press_is_not_a_press_but_a_later_one_is(hass, relay, matter_server, button):
    entity_id = fast_entity(hass, button)

    async def send():
        await matter_server.send(node_event(41, 1, 1))
        await asyncio.sleep(0.15)
        await matter_server.send(node_event(41, 1, 1))  # 150 ms later: the second touch
        await asyncio.sleep(0.9)
        await matter_server.send(node_event(41, 1, 1))  # 900 ms after that: a press of its own

    assert await reported(hass, entity_id, send) == ["press", "press"]


async def test_the_events_that_are_not_presses_report_nothing(hass, relay, matter_server, button):
    entity_id = fast_entity(hass, button)

    async def send():
        for event_id, data in (
            (3, None),
            (4, None),
            (5, {"currentNumberOfPressesCounted": 2}),
            (6, {"totalNumberOfPressesCounted": 3}),
            (6, None),
        ):
            await matter_server.send(node_event(41, 1, event_id, data))

    assert await reported(hass, entity_id, send) == []


async def test_a_button_is_reported_by_its_own_entity_only(hass, relay, matter_server, button):
    other = er.async_get(hass).async_get_or_create("event", "matter", unique_id(41, 2), suggested_object_id="desk_switch_button_2")
    await hass.async_block_till_done()
    first, second = fast_entity(hass, button), fast_entity(hass, other)
    assert first != second
    await matter_server.send(node_event(41, 2, 1))
    await asyncio.sleep(0.3)
    await hass.async_block_till_done()
    assert hass.states.get(first).attributes["event_type"] is None
    assert hass.states.get(second).attributes["event_type"] == "press"


async def test_the_event_received_trigger_of_the_automation_editor_fires_on_a_press(hass, relay, matter_server, button):
    entity_id = fast_entity(hass, button)
    fired = async_capture_events(hass, "test_press_seen")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "triggers": [{"trigger": "event.received", "target": {"entity_id": entity_id}, "options": {"event_type": ["press"]}}],
                "actions": [{"event": "test_press_seen"}],
            }
        },
    )
    await matter_server.send(node_event(41, 1, 2))  # a long press does not match
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    assert fired == []
    await matter_server.send(node_event(41, 1, 1))
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    assert len(fired) == 1


async def test_a_button_added_later_gets_an_entity_and_one_removed_loses_it(hass, relay):
    registry = er.async_get(hass)
    later = registry.async_get_or_create("event", "matter", unique_id(42, 1), suggested_object_id="hall_switch_button_1")
    await hass.async_block_till_done()
    entity_id = fast_entity(hass, later)
    assert entity_id is not None and hass.states.get(entity_id) is not None
    registry.async_remove(later.entity_id)
    await hass.async_block_till_done()
    assert registry.async_get(entity_id) is None and hass.states.get(entity_id) is None


async def test_an_entity_of_a_button_that_went_while_home_assistant_was_stopped_is_removed_when_it_starts(
    hass, matter_entry, matter_server
):
    registry = er.async_get(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    stale = registry.async_get_or_create(
        "event", DOMAIN, unique_id(43, 1) + "-fast", config_entry=entry, suggested_object_id="gone_button_1_fast"
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(stale.entity_id) is None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_the_matter_integrations_own_entities_are_left_alone(hass, relay, button):
    registry = er.async_get(hass)
    assert registry.async_get(button.entity_id) is not None
    assert [e.platform for e in registry.entities.values() if e.entity_id == button.entity_id] == ["matter"]
