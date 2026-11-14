# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in Matter server (a real WebSocket server on this machine) and the entries the integration needs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from aiohttp import web
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
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


SLEEPY, END_DEVICE, ROUTING_END_DEVICE = 2, 4, 5


def node(node_id: int, role: int, *, bridge: bool = False) -> dict:
    """One node as the Matter server lists it (only what the integration reads)."""
    return {"node_id": node_id, "is_bridge": bridge, "available": True, "attributes": {"0/53/1": role}}


class FakeMatterServer:
    """Answers get_nodes and ping_node (`pings` says how each node answers: a dict of address -> bool, "error" or "silent").
    `commands` holds what the event relay sent, `queries` what the reachability check sent."""

    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.pings: dict[int, object] = {}
        self.queries: list[dict] = []
        self.commands: list[dict] = []
        self.connections = 0
        self.url = ""
        self.close_at_once = False
        self._sockets: list[web.WebSocketResponse] = []
        self._relay: web.WebSocketResponse | None = None
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
                command = json.loads(message.data)
                if command["command"] in ("get_nodes", "ping_node"):
                    self.queries.append(command)
                    asyncio.get_running_loop().create_task(self._answer(ws, command))
                else:
                    self.commands.append(command)
                    self._relay = ws
        return ws

    async def _answer(self, ws: web.WebSocketResponse, command: dict) -> None:
        message_id = command["message_id"]
        if command["command"] == "get_nodes":
            await ws.send_str(json.dumps({"message_id": message_id, "result": self.nodes}))
            return
        behaviour = self.pings.get(command["args"]["node_id"], {"fd00::1": True})
        if behaviour == "silent":
            return
        if behaviour == "error":
            await ws.send_str(json.dumps({"message_id": message_id, "error_code": 8, "details": "node not found"}))
            return
        await ws.send_str(json.dumps({"message_id": message_id, "result": behaviour}))

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
        await self._relay.send_str(raw)

    async def drop(self) -> None:
        await self._relay.close()

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


def add_device(hass, matter_entry, node_id: int, name: str, area: str | None = None) -> dr.DeviceEntry:
    """A Matter device in the registry, with the identifier the Matter integration gives it (as seen on a real installation)."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=matter_entry.entry_id,
        identifiers={("matter", f"deviceid_{FABRIC}-{node_id:016X}-MatterNodeDevice")},
        name=name,
    )
    if area:
        device = dr.async_get(hass).async_update_device(device.id, area_id=ar.async_get(hass).async_get_or_create(area).id)
    return device


@pytest.fixture
async def set_up(hass, matter_entry) -> AsyncIterator[Callable[[], Awaitable[MockConfigEntry]]]:
    """Sets Fast Matter switch up (when the test is ready), runs one round of pings and unloads it afterwards."""
    entries: list[MockConfigEntry] = []

    async def _set_up() -> MockConfigEntry:
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        entries.append(entry)
        assert await hass.config_entries.async_setup(entry.entry_id)
        # The relay runs for as long as the entry does, so the tests wait for the pings by asking for them.
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        return entry

    yield _set_up
    for entry in entries:
        await hass.config_entries.async_unload(entry.entry_id)
