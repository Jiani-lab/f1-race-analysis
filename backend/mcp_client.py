"""Thin client for Luci's local screen-memory MCP server.

Talks JSON-RPC 2.0 directly over the HTTP transport (no SSE/session
handshake needed -- verified empirically: the server answers `tools/call`
requests standalone, statelessly, without a prior `initialize`).
"""

import itertools
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

LUCI_MCP_URL = os.environ["LUCI_MCP_URL"]
LUCI_MCP_TOKEN = os.environ["LUCI_MCP_TOKEN"]

_id_counter = itertools.count(1)


class LuciMCPError(RuntimeError):
    pass


def call_tool(name: str, arguments: dict, timeout: float = 30.0) -> dict:
    """Call one Luci MCP tool and return its parsed JSON result.

    Raises LuciMCPError on transport-level or tool-level failure.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": next(_id_counter),
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    headers = {
        "Authorization": f"Bearer {LUCI_MCP_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = httpx.post(LUCI_MCP_URL, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()

    if "error" in body:
        raise LuciMCPError(f"{name} failed: {body['error']}")

    content = body["result"]["content"]
    # Luci wraps tool output as a single text block containing JSON.
    text = content[0]["text"]
    import json

    return json.loads(text)
