# SPDX-License-Identifier: GPL-3.0-or-later
"""What a button's Matter events become on the Home Assistant event bus."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.fast_matter_switch import MatterEventRelay
from custom_components.fast_matter_switch.const import DOMAIN, EVENT_NAME

from .conftest import node_event


async def settle(hass, events, count, seconds=3):
    for _ in range(int(seconds * 100)):
        if len(events) >= count:
            return
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()
    raise AssertionError(f"expected {count} events, got {len(events)}")


async def test_the_integration_asks_the_matter_server_for_events(relay, matter_server):
    assert matter_server.commands == [{"message_id": "fast_matter_switch", "command": "start_listening"}]


async def test_every_switch_event_type_is_fired_with_the_buttons_entity(hass, relay, matter_server, button):
    events = async_capture_events(hass, EVENT_NAME)
    for event_id in (1, 2, 3, 4, 5, 6):
        await matter_server.send(node_event(41, 1, event_id))
    await settle(hass, events, 6)
    assert [e.data["event_type"] for e in events] == [
        "initial_press",
        "long_press",
        "short_release",
        "long_release",
        "multi_press_ongoing",
        "multi_press_complete",
    ]
    assert all(e.data["entity_id"] == button.entity_id and e.data["node_id"] == 41 and e.data["endpoint_id"] == 1 for e in events)


async def test_presses_are_reported_for_multi_press_events_only_when_the_server_counts_them(hass, relay, matter_server, button):
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.send(node_event(41, 1, 5, {"currentNumberOfPressesCounted": 2}))
    await matter_server.send(node_event(41, 1, 6, {"totalNumberOfPressesCounted": 3}))
    await matter_server.send(node_event(41, 1, 3, {}))
    await matter_server.send(node_event(41, 1, 6, {"totalNumberOfPressesCounted": "three"}))
    await settle(hass, events, 4)
    assert [e.data.get("presses") for e in events] == [2, 3, None, None]


async def test_a_second_touch_says_how_long_after_the_first(hass, relay, matter_server, button):
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.send(node_event(41, 1, 1))
    await asyncio.sleep(0.15)
    await matter_server.send(node_event(41, 1, 1))
    await matter_server.send(node_event(41, 2, 1))  # another button has its own clock
    await settle(hass, events, 3)
    first, second, other = (e.data["since_last_press_ms"] for e in events)
    assert first is None and 100 <= second < 1000 and other is None


async def test_only_an_initial_press_carries_the_time_since_the_last_one(hass, relay, matter_server, button):
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.send(node_event(41, 1, 3))
    await settle(hass, events, 1)
    assert "since_last_press_ms" not in events[0].data


async def test_the_button_is_found_for_node_numbers_with_letters_in_their_hex_form(hass, relay, matter_server):
    from homeassistant.helpers import entity_registry as er

    from .conftest import unique_id

    entity = er.async_get(hass).async_get_or_create("event", "matter", unique_id(171, 2), suggested_object_id="hall_switch_button_2")
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.send(node_event(171, 2, 1))  # 171 is 00000000000000AB
    await settle(hass, events, 1)
    assert events[0].data["entity_id"] == entity.entity_id


async def test_a_button_the_registry_does_not_know_is_still_reported(hass, relay, matter_server):
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.send(node_event(99, 3, 1))
    await settle(hass, events, 1)
    assert events[0].data["entity_id"] is None and events[0].data["device_id"] is None and events[0].data["node_id"] == 99


@pytest.mark.parametrize(
    "raw",
    [
        node_event(41, 1, 1, cluster=6),  # another cluster (an on/off switch)
        node_event(41, 1, 77),  # an event number nobody defined
        node_event(True, 1, 1),  # not a node number
        node_event("41", 1, 1),
        '{"event": "node_event", "data": ["not", "a", "dict"]}',
        '["node_event"]',
        "node_event but not json",
        '{"event": "attribute_updated", "data": {}}',
        "{}",
    ],
)
async def test_what_is_not_a_readable_switch_event_fires_nothing_and_does_not_stop_the_relay(hass, relay, matter_server, button, raw):
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.send(raw)
    await matter_server.send(node_event(41, 1, 3))  # a good one after it
    await settle(hass, events, 1)
    assert [e.data["event_type"] for e in events] == ["short_release"]


async def test_a_payload_that_is_not_a_dict_is_ignored_but_the_press_still_counts(hass, relay, matter_server, button):
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.send(
        '{"event": "node_event", "data": {"cluster_id": 59, "event_id": 1, "node_id": 41, "endpoint_id": 1, "data": "text"}}'
    )
    await settle(hass, events, 1)
    assert events[0].data["event_type"] == "initial_press" and "presses" not in events[0].data


async def test_a_message_that_makes_the_relay_raise_is_logged_and_the_next_one_is_still_served(
    hass, relay, matter_server, button, caplog, monkeypatch
):
    events = async_capture_events(hass, EVENT_NAME)
    real = MatterEventRelay._handle
    calls = []

    def flaky(self, raw):
        calls.append(raw)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(self, raw)

    monkeypatch.setattr(MatterEventRelay, "_handle", flaky)
    await matter_server.send(node_event(41, 1, 1))
    await matter_server.send(node_event(41, 1, 3))
    await settle(hass, events, 1)
    assert [e.data["event_type"] for e in events] == ["short_release"]
    assert "Could not read a Matter server message" in caplog.text


async def test_the_relay_reconnects_after_the_server_drops_it(hass, relay, matter_server, button, monkeypatch):
    events = async_capture_events(hass, EVENT_NAME)
    await matter_server.drop()
    for _ in range(600):
        if matter_server.connections >= 2:
            break
        await asyncio.sleep(0.01)
    assert matter_server.connections == 2, "the relay did not come back"
    for _ in range(300):
        if len(matter_server.commands) >= 2:
            break
        await asyncio.sleep(0.01)
    await matter_server.send(node_event(41, 1, 1))
    await settle(hass, events, 1)
    assert events[0].data["event_type"] == "initial_press"


async def test_a_server_that_closes_at_once_is_retried_more_and_more_slowly(hass, matter_entry, matter_server, monkeypatch):
    sleeps = []
    real_sleep = asyncio.sleep

    async def record(delay):
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("custom_components.fast_matter_switch.asyncio.sleep", record)
    matter_server.close_at_once = True
    relay = MatterEventRelay(hass)
    task = hass.async_create_task(relay.run())
    for _ in range(300):
        if len(sleeps) >= 5:
            break
        await real_sleep(0.01)
    task.cancel()
    assert sleeps[:5] == [2, 4, 8, 16, 30]


async def test_unloading_stops_the_relay_and_the_connection(hass, relay, matter_server):
    assert await hass.config_entries.async_unload(relay.entry_id)
    assert relay.state is ConfigEntryState.NOT_LOADED
    await asyncio.sleep(0.1)
    assert matter_server._sockets[-1].closed


async def test_without_the_matter_integration_setup_waits(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
