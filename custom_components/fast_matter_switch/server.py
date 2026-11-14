# SPDX-License-Identifier: GPL-3.0-or-later
"""Talks to the Matter server: its address, and a WebSocket that lists the sleepy nodes and pings them all at once."""

from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp import ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

from .const import MATTER_DOMAIN, MAX_MESSAGE_BYTES, PING_DEADLINE_S, ROUTING_ROLE_ATTRIBUTE, SLEEPY_END_DEVICE

_LOGGER = logging.getLogger(__name__)

GET_NODES_ID = "fast_matter_switch-nodes"


def matter_url(hass: HomeAssistant) -> str | None:
    """The address of the Matter server, as the Matter integration has it."""
    for entry in hass.config_entries.async_entries(MATTER_DOMAIN):
        url = entry.data.get("url")
        if url:
            return url
    return None


def is_sleepy(node: object) -> bool:
    """Whether a node from the server's node list is a battery device that sleeps between its polls."""
    if not isinstance(node, dict) or node.get("is_bridge"):
        return False
    attributes = node.get("attributes")
    return isinstance(attributes, dict) and attributes.get(ROUTING_ROLE_ATTRIBUTE) == SLEEPY_END_DEVICE


async def _answers(ws, wanted: set[str], deadline_s: float) -> dict[str, dict[str, Any]]:
    """Reads messages until every wanted message id has been answered or the deadline passes; returns what arrived."""
    answers: dict[str, dict[str, Any]] = {}
    end = time.monotonic() + deadline_s
    while len(answers) < len(wanted):
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        try:
            message = await ws.receive(timeout=remaining)
        except TimeoutError:
            break
        if message.type != WSMsgType.TEXT:
            raise ConnectionError("the Matter server closed the connection")
        try:
            data = message.json()
        except ValueError:
            continue
        message_id = data.get("message_id") if isinstance(data, dict) else None
        if message_id in wanted:
            answers[message_id] = data
    return answers


async def ping_sleepy_nodes(session: ClientSession, url: str) -> dict[int, bool]:
    """Pings every sleepy node and says, for each, whether any of its addresses answered."""
    async with session.ws_connect(url, max_msg_size=MAX_MESSAGE_BYTES) as ws:
        await ws.send_json({"message_id": GET_NODES_ID, "command": "get_nodes"})
        listed = (await _answers(ws, {GET_NODES_ID}, PING_DEADLINE_S)).get(GET_NODES_ID)
        if listed is None or not isinstance(listed.get("result"), list):
            raise ConnectionError("the Matter server did not list its nodes")
        node_ids = [node["node_id"] for node in listed["result"] if is_sleepy(node) and isinstance(node.get("node_id"), int)]
        message_ids = {f"fast_matter_switch-ping-{node_id}": node_id for node_id in node_ids}
        for message_id, node_id in message_ids.items():
            await ws.send_json({"message_id": message_id, "command": "ping_node", "args": {"node_id": node_id}})
        answers = await _answers(ws, set(message_ids), PING_DEADLINE_S)
    reachable: dict[int, bool] = {}
    for message_id, node_id in message_ids.items():
        answer = answers.get(message_id)
        if answer is None:
            _LOGGER.debug("Node %s did not answer its ping within %s s", node_id, PING_DEADLINE_S)
            reachable[node_id] = False
        elif "error_code" in answer:
            _LOGGER.warning("The Matter server could not ping node %s: %s", node_id, answer.get("details"))
            reachable[node_id] = False
        else:
            result = answer.get("result")
            reachable[node_id] = isinstance(result, dict) and any(value is True for value in result.values())
    return reachable
