# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast Matter switch.

Home Assistant's Matter integration reports a button that supports multi-press only once the double-press window has
run out, and drops its "initial press" event. This integration opens a second connection to the same Matter server,
reads the Switch cluster events as they arrive and fires them on the event bus as `fast_matter_switch_event`, so an
automation can react at the first touch.

The event data:
  event_type   initial_press, short_release, long_press, long_release, multi_press_ongoing or multi_press_complete
  entity_id    the Matter event entity of that button (None when it is not known)
  device_id    its device
  node_id, endpoint_id   where the event came from
  presses      the number of presses counted (multi_press_ongoing and multi_press_complete only)
  since_last_press_ms   initial_press only: milliseconds since the same button last reported an initial press, or
               None for the first one. An automation uses it to act once on a double press (the second touch
               follows the first within about half a second) and on a press that a switch reports twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from aiohttp import ClientError, WSMsgType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    EVENT_NAME,
    MATTER_DOMAIN,
    SWITCH_CLUSTER_ID,
    SWITCH_EVENT_TYPES,
)

_LOGGER = logging.getLogger(__name__)

RETRY_START_S = 1
RETRY_MAX_S = 30
HEARTBEAT_S = 30
# The first message after start_listening carries every node, which is a few hundred kilobytes.
MAX_MESSAGE_BYTES = 16 * 1024 * 1024


def _is_number(value: object) -> bool:
    """A whole number from the server (a boolean is not one)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _matter_url(hass: HomeAssistant) -> str | None:
    """The address of the Matter server, as the Matter integration has it."""
    for entry in hass.config_entries.async_entries(MATTER_DOMAIN):
        url = entry.data.get("url")
        if url:
            return url
    return None


def _button_entity(hass: HomeAssistant, node_id: int, endpoint_id: int):
    """The Matter event entity of one button, found by the node and endpoint in its unique id."""
    marker = f"-{node_id:016X}-MatterNodeDevice-{endpoint_id}-"
    for entry in er.async_get(hass).entities.values():
        if entry.platform == MATTER_DOMAIN and entry.domain == "event" and marker in entry.unique_id:
            return entry
    return None


class MatterEventRelay:
    """Keeps a connection to the Matter server and turns Switch events into bus events."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        # When each button (node, endpoint) last reported an initial press, on the monotonic clock.
        self._last_press: dict[tuple[int, int], float] = {}

    async def run(self) -> None:
        delay = RETRY_START_S
        while True:
            started = time.monotonic()
            try:
                await self._listen()
            except (ClientError, OSError, TimeoutError) as err:
                _LOGGER.warning("Lost the Matter server connection (%s); trying again in %s s", err, delay)
            # A connection that held for a while was healthy, so the next try is quick; one that dropped at once backs off.
            delay = RETRY_START_S if time.monotonic() - started >= HEARTBEAT_S else min(delay * 2, RETRY_MAX_S)
            await asyncio.sleep(delay)

    async def _listen(self) -> None:
        url = _matter_url(self._hass)
        if url is None:
            raise OSError("the Matter integration has no server address")
        session = async_get_clientsession(self._hass)
        async with session.ws_connect(url, heartbeat=HEARTBEAT_S, max_msg_size=MAX_MESSAGE_BYTES) as ws:
            await ws.send_json({"message_id": "fast_matter_switch", "command": "start_listening"})
            _LOGGER.info("Listening to Matter switch events on %s", url)
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        self._handle(msg.data)
                    except Exception:  # one message that cannot be read must not stop every button
                        _LOGGER.exception("Could not read a Matter server message")
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.ERROR):
                    break

    def _handle(self, raw: str) -> None:
        # Most messages are not switch events; skip parsing them.
        if '"node_event"' not in raw:
            return
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict) or message.get("event") != "node_event":
            return
        data = message.get("data")
        if not isinstance(data, dict) or data.get("cluster_id") != SWITCH_CLUSTER_ID:
            return
        event_type = SWITCH_EVENT_TYPES.get(data.get("event_id"))
        node_id, endpoint_id = data.get("node_id"), data.get("endpoint_id")
        if event_type is None or not _is_number(node_id) or not _is_number(endpoint_id):
            return
        payload = data.get("data")
        payload = payload if isinstance(payload, dict) else {}
        button = _button_entity(self._hass, node_id, endpoint_id)
        fired = {
            "event_type": event_type,
            "node_id": node_id,
            "endpoint_id": endpoint_id,
            "entity_id": button.entity_id if button else None,
            "device_id": button.device_id if button else None,
        }
        if event_type == "initial_press":
            now = time.monotonic()
            before = self._last_press.get((node_id, endpoint_id))
            self._last_press[(node_id, endpoint_id)] = now
            fired["since_last_press_ms"] = None if before is None else round((now - before) * 1000)
        presses = payload.get("totalNumberOfPressesCounted") or payload.get("currentNumberOfPressesCounted")
        if _is_number(presses) and presses:
            fired["presses"] = presses
        self._hass.bus.async_fire(EVENT_NAME, fired)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if _matter_url(hass) is None:
        raise ConfigEntryNotReady("The Matter integration is not set up yet")
    entry.async_create_background_task(hass, MatterEventRelay(hass).run(), "fast_matter_switch relay")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # The relay is a background task of the entry and is cancelled with it.
    return True
