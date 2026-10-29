# SPDX-License-Identifier: GPL-3.0-or-later
"""Adding the integration: needs the Matter integration, and only once."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fast_matter_switch.const import DOMAIN


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_without_matter_there_is_nothing_to_add(hass):
    result = await start(hass)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "no_matter"


async def test_it_is_added_after_one_confirmation_and_only_once(hass, matter_entry):
    result = await start(hass)
    assert result["type"] is FlowResultType.FORM
    done = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert done["type"] is FlowResultType.CREATE_ENTRY and done["title"] == "Fast Matter switch"
    again = await start(hass)
    assert again["type"] is FlowResultType.ABORT and again["reason"] == "single_instance_allowed"


async def test_an_existing_entry_blocks_a_second(hass, matter_entry):
    MockConfigEntry(domain=DOMAIN, data={}).add_to_hass(hass)
    assert (await start(hass))["reason"] == "single_instance_allowed"
