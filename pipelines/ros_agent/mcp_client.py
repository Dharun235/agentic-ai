"""Question-scoped bridge over the official MCP client."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

from .config import settings

ROS_SERVER = Path(__file__).parents[1] / "ros" / "mcp_server.py"


class MCPRos:
    """Keep one official MCP client session for one agent question."""

    def __init__(self):
        self.endpoint = settings["ros_mcp_url"]
        self.server = None if self.endpoint else StdioServerParameters(
            command=sys.executable,
            args=[str(ROS_SERVER)],
            env=os.environ.copy(),
        )
        self.transport = "streamable-http" if self.endpoint else "stdio"
        self.client = None
        self._tools = []

    @staticmethod
    def _as_tool(tool):
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }

    async def __aenter__(self):
        self.client = Client(self.endpoint or self.server)
        await self.client.__aenter__()
        await self.refresh_tools()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.client is not None:
            await self.client.__aexit__(exc_type, exc_value, traceback)
        self.client = None
        self._tools = []

    async def list_tools(self):
        """Refresh and return current tools exposed by the MCP server."""
        await self.refresh_tools()
        return self._tools

    async def refresh_tools(self):
        """Re-read server capabilities so catalog/planner never use stale tools."""
        if self.client is None:
            raise RuntimeError("MCP session is not open")
        result = await self.client.list_tools()
        self._tools = [self._as_tool(tool) for tool in result.tools]
        return self._tools

    async def call_many(self, calls):
        """Execute calls through the question's shared MCP session."""
        if self.client is None:
            raise RuntimeError("MCP session is not open")
        available = {tool["function"]["name"] for tool in self._tools}
        outputs = []
        for name, arguments in calls:
            if name not in available:
                outputs.append({"tool": name, "output": f"Tool error: unknown MCP tool `{name}`."})
                continue
            result = await self.client.call_tool(name, arguments=arguments)
            texts = [item.text for item in result.content if hasattr(item, "text")]
            outputs.append({"tool": name, "output": "\n".join(texts) or "No tool output."})
        return outputs
