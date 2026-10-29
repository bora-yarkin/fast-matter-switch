# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in Matter server (a real WebSocket server on this machine) and the entries the integration needs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from aiohttp import web
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fast_matter_switch.const import DOMAIN

FABRIC = "568A3663ECE8D5FD"


def unique_id(node: int, endpoint: int) -> str:
    """The unique id the Matter integration gives a button's event entity (as seen on a real installation)."""
    return f"{FABRIC}-{node:016X}-MatterNodeDevice-{endpoint}-GenericSwitch-59-1"


def node_event(node: int, endpoint: int, event_id: int, data: dict | None = None, cluster: int = 59) -> str:
    return json.dumps(
        {
            "event": "node_event",
            "data": {"node_id": node, "endpoint_id": endpoint, "cluster_id": cluster, "event_id": event_id, "data": data},
        }
    )


class FakeMatterServer:
    def __init__(self) -> None:
        self.commands: list[dict] = []
        self.connections = 0
        self.url = ""
        self.close_at_once = False
        self._sockets: list[web.WebSocketResponse] = []
        self._runner: web.AppRunner | None = None

    async def _handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections += 1
        self._sockets.append(ws)
        if self.close_at_once:
            await ws.close()
            return ws
        async for message in ws:
            if message.type == web.WSMsgType.TEXT:
                self.commands.append(json.loads(message.data))
        return ws

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/ws", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.url = f"ws://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/ws"

    async def listening(self, seconds: float = 5) -> None:
        """Waits until the integration has asked for events."""
        for _ in range(int(seconds * 100)):
            if self.commands:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("the integration never sent start_listening")

    async def send(self, raw: str) -> None:
        await self._sockets[-1].send_str(raw)

    async def drop(self) -> None:
        await self._sockets[-1].close()

    async def stop(self) -> None:
        for ws in self._sockets:
            await ws.close()
        if self._runner:
            await self._runner.cleanup()


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations, socket_enabled):
    yield


@pytest.fixture
async def matter_server() -> AsyncIterator[FakeMatterServer]:
    server = FakeMatterServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def matter_entry(hass, matter_server) -> MockConfigEntry:
    entry = MockConfigEntry(domain="matter", data={"url": matter_server.url})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def button(hass, matter_entry):
    """The event entity of one Matter button (node 41, endpoint 1)."""
    return er.async_get(hass).async_get_or_create("event", "matter", unique_id(41, 1), suggested_object_id="desk_switch_button_1")


@pytest.fixture
async def relay(hass, matter_entry, matter_server):
    """Fast Matter switch set up against the stand-in server, listening."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await matter_server.listening()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
