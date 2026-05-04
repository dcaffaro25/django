"""Stdio transport for the Sysnord MCP server.

Wraps :mod:`mcp_server.tools` in the official MCP protocol so any MCP-aware
agent (Claude Code, Cursor, custom Anthropic SDK) can connect over stdio.

Run via the management command::

    python manage.py run_mcp_server
"""
from __future__ import annotations

import json
import logging
from typing import Any

from . import tools

log = logging.getLogger(__name__)


def _build_server():
    """Build and return an :class:`mcp.server.Server` configured with all
    Sysnord tools. Imported lazily so the rest of the codebase doesn't pay
    the import cost when MCP isn't being used."""
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError as exc:
        raise RuntimeError(
            "The 'mcp' package is required to run the MCP server. "
            "Install it with: pip install 'mcp>=1.2,<2.0'"
        ) from exc

    server = Server("sysnord-mcp")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.input_schema,
            )
            for t in tools.TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            result = tools.call_tool(name, arguments or {})
        except KeyError:
            payload = {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            log.exception("MCP tool %s failed: %s", name, exc)
            payload = {"error": f"{type(exc).__name__}: {exc}"}
        else:
            payload = result

        return [TextContent(type="text", text=json.dumps(payload, default=str))]

    return server


async def run_stdio() -> None:
    """Run the MCP server over stdio. Blocks until the client disconnects."""
    from mcp.server.stdio import stdio_server

    server = _build_server()
    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)
