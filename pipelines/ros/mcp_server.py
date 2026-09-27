"""MCP stdio server exposing safe ROS 2 inspection tools."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server import MCPServer

from pipelines.ros.tools import list_nodes as _list_nodes
from pipelines.ros.tools import list_services as _list_services
from pipelines.ros.tools import list_actions as _list_actions
from pipelines.ros.tools import list_topics as _list_topics
from pipelines.ros.tools import node_info as _node_info
from pipelines.ros.tools import topic_info as _topic_info
from pipelines.ros.tools import service_info as _service_info
from pipelines.ros.tools import action_info as _action_info
from pipelines.ros.tools import system_snapshot as _system_snapshot
from pipelines.ros.tools import runtime_status as _runtime_status
from pipelines.ros.tools import start_demo_node as _start_demo_node
from pipelines.ros.tools import stop_demo_node as _stop_demo_node


mcp = MCPServer("ros2-inspection")


@mcp.tool()
def list_ros_nodes() -> str:
    """List currently discovered ROS 2 nodes."""
    return _list_nodes()


@mcp.tool()
def list_ros_topics() -> str:
    """List currently discovered ROS 2 topics."""
    return _list_topics()


@mcp.tool()
def list_ros_services() -> str:
    """List currently discovered ROS 2 services."""
    return _list_services()


@mcp.tool()
def list_ros_actions() -> str:
    """List currently discovered ROS 2 actions."""
    return _list_actions()


@mcp.tool()
def ros_node_info(node: str) -> str:
    """Inspect one ROS 2 node's connections."""
    return _node_info(node)


@mcp.tool()
def ros_topic_info(topic: str) -> str:
    """Inspect one ROS 2 topic."""
    return _topic_info(topic)


@mcp.tool()
def ros_service_info(service: str) -> str:
    """Inspect one ROS 2 service type."""
    return _service_info(service)


@mcp.tool()
def ros_action_info(action: str) -> str:
    """Inspect one ROS 2 action."""
    return _action_info(action)


@mcp.tool()
def ros_system_snapshot() -> str:
    """Return nodes, topics, services, and actions in one snapshot."""
    return _system_snapshot()


@mcp.tool()
def ros2_runtime_status() -> str:
    """Check ros2, Docker, and configured ROS2 container prerequisites."""
    return _runtime_status()


@mcp.tool()
def start_ros_demo_node() -> str:
    """Start and verify the configured safe ROS demo node."""
    return _start_demo_node()


@mcp.tool()
def stop_ros_demo_node() -> str:
    """Stop and verify the configured safe ROS demo node."""
    return _stop_demo_node()


if __name__ == "__main__":
    mcp.run()
