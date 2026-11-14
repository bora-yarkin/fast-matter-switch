# SPDX-License-Identifier: GPL-3.0-or-later
"""Pings the sleepy Matter devices on a schedule and keeps when each last answered."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SCAN_INTERVAL
from .server import matter_url, ping_sleepy_nodes

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeReachability:
    reachable: bool
    last_reachable: datetime | None


class ReachabilityCoordinator(DataUpdateCoordinator[dict[int, NodeReachability]]):
    """One entry per sleepy Matter node (by node id); a failed update means the Matter server itself could not be asked."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[int, NodeReachability]:
        url = matter_url(self.hass)
        if url is None:
            raise UpdateFailed("The Matter integration has no server address")
        try:
            reachable = await ping_sleepy_nodes(async_get_clientsession(self.hass), url)
        except (ClientError, OSError, TimeoutError) as err:
            raise UpdateFailed(f"Could not ask the Matter server: {err}") from err
        now = dt_util.utcnow()
        before = self.data or {}
        return {
            node_id: NodeReachability(
                ok,
                now if ok else (before[node_id].last_reachable if node_id in before else None),
            )
            for node_id, ok in reachable.items()
        }
