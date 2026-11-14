# SPDX-License-Identifier: GPL-3.0-or-later
"""The Reachable sensors of the sleepy Matter devices: which devices get one, what makes it on or off, and what happens when the Matter server cannot be asked."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fast_matter_switch.const import DOMAIN

from .conftest import END_DEVICE, ROUTING_END_DEVICE, SLEEPY, add_device, node


def state_of(hass, entity_id: str):
    return hass.states.get(entity_id)


async def refresh(hass, entry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_only_sleepy_devices_are_pinged_and_get_a_sensor(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY), node(11, ROUTING_END_DEVICE), node(12, END_DEVICE), node(13, SLEEPY, bridge=True)]
    for node_id, name in ((10, "Upper Switch"), (11, "Light C"), (12, "Entrance Light L"), (13, "Bridge")):
        add_device(hass, matter_entry, node_id, name, "Staircase")
    await set_up()
    pinged = sorted({c["args"]["node_id"] for c in matter_server.queries if c["command"] == "ping_node"})
    assert pinged == [10]
    sensors = [e for e in er.async_get(hass).entities.values() if e.platform == DOMAIN and e.domain == "binary_sensor"]
    assert [e.unique_id for e in sensors] == [f"{DOMAIN}-reachable-10"]


async def test_a_device_that_answers_is_on_and_one_that_does_not_is_off(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY), node(11, SLEEPY)]
    matter_server.pings = {10: {"fd00::1": True}, 11: {"fd00::2": False}}
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    add_device(hass, matter_entry, 11, "Lower Switch", "Staircase")
    await set_up()
    assert state_of(hass, "binary_sensor.staircase_upper_switch_reachable").state == "on"
    assert state_of(hass, "binary_sensor.staircase_lower_switch_reachable").state == "off"


async def test_one_answering_address_is_enough(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY)]
    matter_server.pings = {10: {"fd00::1": False, "fd00::2": True}}
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    await set_up()
    assert state_of(hass, "binary_sensor.staircase_upper_switch_reachable").state == "on"


async def test_a_server_error_or_silence_means_not_reachable(hass, matter_entry, matter_server, monkeypatch, set_up):
    monkeypatch.setattr("custom_components.fast_matter_switch.server.PING_DEADLINE_S", 0.5)
    matter_server.nodes = [node(10, SLEEPY), node(11, SLEEPY)]
    matter_server.pings = {10: "error", 11: "silent"}
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    add_device(hass, matter_entry, 11, "Lower Switch", "Staircase")
    await set_up()
    assert state_of(hass, "binary_sensor.staircase_upper_switch_reachable").state == "off"
    assert state_of(hass, "binary_sensor.staircase_lower_switch_reachable").state == "off"


async def test_it_comes_back_on_and_remembers_when_it_last_answered(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY)]
    matter_server.pings = {10: {"fd00::1": False}}
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    entry = await set_up()
    off = state_of(hass, "binary_sensor.staircase_upper_switch_reachable")
    assert off.state == "off" and off.attributes["last_reachable"] is None
    matter_server.pings = {10: {"fd00::1": True}}
    await refresh(hass, entry)
    on = state_of(hass, "binary_sensor.staircase_upper_switch_reachable")
    assert on.state == "on" and on.attributes["last_reachable"] is not None
    matter_server.pings = {10: {"fd00::1": False}}
    await refresh(hass, entry)
    again = state_of(hass, "binary_sensor.staircase_upper_switch_reachable")
    assert again.state == "off" and again.attributes["last_reachable"] == on.attributes["last_reachable"]


async def test_a_server_that_cannot_be_asked_makes_sensors_unavailable_not_off(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY)]
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    entry = await set_up()
    assert state_of(hass, "binary_sensor.staircase_upper_switch_reachable").state == "on"
    await matter_server.stop()
    await refresh(hass, entry)
    assert state_of(hass, "binary_sensor.staircase_upper_switch_reachable").state == "unavailable"


async def test_a_device_that_joins_later_gets_its_sensor_at_the_next_update(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY)]
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    entry = await set_up()
    matter_server.nodes = [node(10, SLEEPY), node(11, SLEEPY)]
    add_device(hass, matter_entry, 11, "Lower Switch", "Staircase")
    await refresh(hass, entry)
    assert state_of(hass, "binary_sensor.staircase_lower_switch_reachable").state == "on"


async def test_a_sleepy_node_without_a_home_assistant_device_gets_no_sensor_until_it_has_one(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY)]
    entry = await set_up()
    assert not [e for e in er.async_get(hass).entities.values() if e.platform == DOMAIN and e.domain == "binary_sensor"]
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    await refresh(hass, entry)
    assert state_of(hass, "binary_sensor.staircase_upper_switch_reachable").state == "on"


async def test_without_the_matter_integration_setup_is_retried(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_the_sensor_is_linked_to_the_matter_device_without_changing_it(hass, matter_entry, matter_server, set_up):
    matter_server.nodes = [node(10, SLEEPY)]
    device = add_device(hass, matter_entry, 10, "BILRESA scroll wheel", "Staircase")
    dr.async_get(hass).async_update_device(device.id, name_by_user="Upper Switch")
    await set_up()
    after = dr.async_get(hass).async_get(device.id)
    assert (after.name, after.name_by_user, after.config_entry_id) == ("BILRESA scroll wheel", "Upper Switch", matter_entry.entry_id)
    assert len(list(dr.async_get(hass).devices)) == 1
    sensor = er.async_get(hass).async_get("binary_sensor.staircase_upper_switch_reachable")
    assert sensor is not None and sensor.device_id == device.id


async def test_a_device_of_another_integration_with_a_longer_identifier_does_not_break_the_lookup(
    hass, matter_entry, matter_server, set_up
):
    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id, identifiers={("other", "a", "b")}, name="Odd device")
    matter_server.nodes = [node(10, SLEEPY)]
    add_device(hass, matter_entry, 10, "Upper Switch", "Staircase")
    await set_up()
    assert state_of(hass, "binary_sensor.staircase_upper_switch_reachable").state == "on"
