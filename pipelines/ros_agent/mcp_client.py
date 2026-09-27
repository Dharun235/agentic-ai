"""Synchronous client for the local ROS2 MCP server."""

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROS_SERVER = Path(__file__).parents[1] / "ros" / "mcp_server.py"


class MCPRos:
    """Synchronous bridge to the ROS2 MCP server."""

    def __init__(self):
        self.servers = [StdioServerParameters(
            command=sys.executable,
            args=[str(ROS_SERVER)],
            env=os.environ.copy(),
        )]

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

    async def _list_tools(self):
        tools = []
        for server in self.servers:
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    tools.extend(self._as_tool(tool) for tool in result.tools)
        return tools

    async def _call(self, name, arguments):
        for server in self.servers:
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    if name not in {tool.name for tool in result.tools}:
                        continue
                    result = await session.call_tool(name, arguments=arguments)
                    texts = [item.text for item in result.content if hasattr(item, "text")]
                    return "\n".join(texts) or "No tool output."
        return f"Tool error: unknown MCP tool `{name}`."

    def list_tools(self):
        return asyncio.run(self._list_tools())

    def call(self, name, arguments):
        return asyncio.run(self._call(name, arguments))

