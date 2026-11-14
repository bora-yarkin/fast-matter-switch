# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast Matter switch.

Home Assistant's Matter integration reports a button that supports multi-press only once the double-press window has
run out, and drops its "initial press" event. This integration opens a second connection to the same Matter server,
reads the Switch cluster events as they arrive and fires them on the event bus as `fast_matter_switch_event`, so an
automation can react at the first touch.

The event data:
  event_type   switch_latched (a latching switch, such as a rocker, changed position), initial_press, short_release,
               long_press, long_release, multi_press_ongoing or multi_press_complete
  entity_id    the Matter event entity of that button (None when it is not known)
  device_id    its device
  node_id, endpoint_id   where the event came from
  position     switch_latched only: the position the switch moved to
  fast_event_type   what the button's event entity reports for this event (press, double_press or long_press), present
               only when it reports something; the second touch of a double press has none
  presses      the number of presses counted (multi_press_ongoing and multi_press_complete only)
  since_last_press_ms   initial_press only: milliseconds since the same button last reported an initial press, or
               None for the first one. An automation uses it to act once on a double press (the second touch
               follows the first within about half a second) and on a press that a switch reports twice.

Each Matter button also gets an event entity (event.py) that reports ``press``, ``double_press`` and ``long_press``
with that rule already applied, for automations built in the editor.

A battery-powered Matter device (the IKEA BILRESA remote, a door sensor...) sleeps between presses, so Home Assistant hears
nothing from it for hours and keeps showing it as available even when it has left the network. The integration pings every
such device every few minutes through the same connection address and gives each a "Reachable" binary sensor (binary_sensor.py):
on when it answered, off when it did not. The dashboard's device-offline notification watches these sensors.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from aiohttp import ClientError, WSMsgType
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOUBLE_PRESS,
    DOUBLE_TOUCH_MS,
    EVENT_NAME,
    LONG_PRESS,
    MATTER_DOMAIN,
    MAX_MESSAGE_BYTES,
    PRESS,
    SWITCH_CLUSTER_ID,
    SWITCH_EVENT_TYPES,
    dispatch_signal,
)
from .coordinator import ReachabilityCoordinator
from .server import matter_url

_LOGGER = logging.getLogger(__name__)

RETRY_START_S = 1
RETRY_MAX_S = 30
HEARTBEAT_S = 30

PLATFORMS = [Platform.EVENT, Platform.BINARY_SENSOR]

type FastMatterSwitchConfigEntry = ConfigEntry[ReachabilityCoordinator]


def _fast_event_type(event_type: str, since_last_press_ms: int | None, presses: int | None) -> str | None:
    """What the button's event entity reports for a Switch event, or None when it reports nothing."""
    if event_type == "initial_press":
        return PRESS if since_last_press_ms is None or since_last_press_ms > DOUBLE_TOUCH_MS else None
    if event_type == "multi_press_complete":
        return DOUBLE_PRESS if presses == 2 else None
    if event_type == "long_press":
        return LONG_PRESS
    return None


def _is_number(value: object) -> bool:
    """A whole number from the server (a boolean is not one)."""
    return isinstance(value, int) and not isinstance(value, bool)


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
        url = matter_url(self._hass)
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
        position = payload.get("newPosition")
        if event_type == "switch_latched" and _is_number(position):
            fired["position"] = position
        fast = _fast_event_type(event_type, fired.get("since_last_press_ms"), fired.get("presses"))
        if fast is not None:
            fired["fast_event_type"] = fast
        self._hass.bus.async_fire(EVENT_NAME, fired)
        if button is not None and fast is not None:
            async_dispatcher_send(self._hass, dispatch_signal(button.unique_id), fast)


async def async_setup_entry(hass: HomeAssistant, entry: FastMatterSwitchConfigEntry) -> bool:
    if matter_url(hass) is None:
        raise ConfigEntryNotReady("The Matter integration is not set up yet")
    coordinator = ReachabilityCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(hass, MatterEventRelay(hass).run(), "fast_matter_switch relay")
    # The first round of pings takes several seconds per sleeping device, so it must not hold up Home Assistant's startup.
    entry.async_create_background_task(hass, coordinator.async_refresh(), "fast_matter_switch first reachability refresh")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FastMatterSwitchConfigEntry) -> bool:
    # The relay is a background task of the entry and is cancelled with it.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
