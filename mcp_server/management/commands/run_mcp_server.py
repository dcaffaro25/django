"""Run the Sysnord MCP server over stdio.

This is what an MCP client (Claude Code, Cursor, etc.) launches as a
subprocess. The transport is JSON-RPC over stdin/stdout; logs go to stderr.

Configuration:
- The server has tenant scoping enforced **per tool call** via the
  ``company_id`` argument. There is no global tenant binding; this lets a
  single MCP session work across tenants for accounting-team operators.
- Authentication of the calling agent is delegated to the OS / sandbox
  layer that spawned this process. If you need cross-network access, run
  the agent through Django HTTP endpoints instead and use the existing
  ``api_meta`` token middleware.

Example MCP client config (Claude Code)::

    {
      "mcpServers": {
        "sysnord": {
          "command": "python",
          "args": ["manage.py", "run_mcp_server"],
          "cwd": "/path/to/django"
        }
      }
    }
"""
from __future__ import annotations

import asyncio

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the Sysnord MCP server over stdio."

    def handle(self, *args, **options):
        from mcp_server.stdio import run_stdio

        # Run the asyncio event loop until the MCP client disconnects.
        asyncio.run(run_stdio())
