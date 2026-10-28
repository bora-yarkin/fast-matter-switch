# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup flow for Fast Matter switch: a single confirmation, no settings."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, MATTER_DOMAIN


class FastMatterSwitchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Adds the integration once, when the Matter integration is set up."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if not self.hass.config_entries.async_entries(MATTER_DOMAIN):
            return self.async_abort(reason="no_matter")
        if user_input is not None:
            return self.async_create_entry(title="Fast Matter switch", data={})
        return self.async_show_form(step_id="user")
