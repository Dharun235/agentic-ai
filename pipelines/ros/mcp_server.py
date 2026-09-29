"""MCP server exposing safe ROS2 inspection tools over stdio or HTTP."""

import argparse
import os
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
from pipelines.ros.tools import list_node_parameters as _list_node_parameters
from pipelines.ros.tools import get_node_parameter as _get_node_parameter
from pipelines.ros.tools import get_node_parameters as _get_node_parameters
from pipelines.ros.tools import describe_node_parameters as _describe_node_parameters
from pipelines.ros.tools import ros_topic_echo as _ros_topic_echo
from pipelines.ros.tools import ros_topic_hz as _ros_topic_hz
from pipelines.ros.tools import ros_topic_bw as _ros_topic_bw
from pipelines.ros.tools import ros_topic_type as _ros_topic_type
from pipelines.ros.tools import ros_message_info as _ros_message_info
from pipelines.ros.tools import ros_service_definition as _ros_service_definition
from pipelines.ros.tools import ros_action_definition as _ros_action_definition
from pipelines.ros.tools import ros_node_graph as _ros_node_graph
from pipelines.ros.tools import find_topic_publishers as _find_topic_publishers
from pipelines.ros.tools import find_topic_subscribers as _find_topic_subscribers
from pipelines.ros.tools import find_unconnected_topics as _find_unconnected_topics
from pipelines.ros.tools import ros_graph_snapshot as _ros_graph_snapshot
from pipelines.ros.tools import list_tf_frames as _list_tf_frames
from pipelines.ros.tools import tf_frame_info as _tf_frame_info
from pipelines.ros.tools import tf_transform as _tf_transform
from pipelines.ros.tools import tf_tree_snapshot as _tf_tree_snapshot
from pipelines.ros.tools import list_processes as _list_processes
from pipelines.ros.tools import list_ros_daemons as _list_ros_daemons
from pipelines.ros.tools import ros_domain_id as _ros_domain_id
from pipelines.ros.tools import ros_environment_status as _ros_environment_status
from pipelines.ros.tools import inspect_launch_processes as _inspect_launch_processes
from pipelines.ros.tools import list_diagnostics as _list_diagnostics
from pipelines.ros.tools import get_diagnostic_status as _get_diagnostic_status
from pipelines.ros.tools import check_node_health as _check_node_health
from pipelines.ros.tools import check_topic_health as _check_topic_health
from pipelines.ros.tools import ros_time_status as _ros_time_status
from pipelines.ros.tools import clock_topic_status as _clock_topic_status
from pipelines.ros.tools import use_sim_time_status as _use_sim_time_status


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
    """Check the native host ROS2 CLI prerequisites."""
    return _runtime_status()


@mcp.tool()
def list_node_parameters(node: str) -> str:
    """List node parameters."""
    return _list_node_parameters(node)


@mcp.tool()
def get_node_parameter(node: str, name: str) -> str:
    """Get one node parameter."""
    return _get_node_parameter(node, name)


@mcp.tool()
def get_node_parameters(node: str) -> str:
    """Dump all node parameters."""
    return _get_node_parameters(node)


@mcp.tool()
def describe_node_parameters(node: str) -> str:
    """Describe node parameters."""
    return _describe_node_parameters(node)


@mcp.tool()
def ros_topic_echo(topic: str, message_count: int = 1) -> str:
    """Read bounded topic messages."""
    return _ros_topic_echo(topic, message_count)


@mcp.tool()
def ros_topic_hz(topic: str) -> str:
    """Measure topic frequency."""
    return _ros_topic_hz(topic)


@mcp.tool()
def ros_topic_bw(topic: str) -> str:
    """Measure topic bandwidth."""
    return _ros_topic_bw(topic)


@mcp.tool()
def ros_topic_type(topic: str) -> str:
    """Get topic type."""
    return _ros_topic_type(topic)


@mcp.tool()
def ros_message_info(type_name: str) -> str:
    """Show message definition."""
    return _ros_message_info(type_name)


@mcp.tool()
def ros_service_definition(type_name: str) -> str:
    """Show service definition."""
    return _ros_service_definition(type_name)


@mcp.tool()
def ros_action_definition(type_name: str) -> str:
    """Show action definition."""
    return _ros_action_definition(type_name)


@mcp.tool()
def ros_node_graph(node: str) -> str:
    """Show node graph connections."""
    return _ros_node_graph(node)


@mcp.tool()
def find_topic_publishers(topic: str) -> str:
    """Find topic publishers."""
    return _find_topic_publishers(topic)


@mcp.tool()
def find_topic_subscribers(topic: str) -> str:
    """Find topic subscribers."""
    return _find_topic_subscribers(topic)


@mcp.tool()
def find_unconnected_topics() -> str:
    """Find unconnected topics."""
    return _find_unconnected_topics()


@mcp.tool()
def ros_graph_snapshot() -> str:
    """Return graph snapshot."""
    return _ros_graph_snapshot()


@mcp.tool()
def list_tf_frames() -> str:
    """List TF frames."""
    return _list_tf_frames()


@mcp.tool()
def tf_frame_info(frame: str) -> str:
    """Inspect TF frame."""
    return _tf_frame_info(frame)


@mcp.tool()
def tf_transform(source: str, target: str) -> str:
    """Query TF transform."""
    return _tf_transform(source, target)


@mcp.tool()
def tf_tree_snapshot() -> str:
    """Return TF tree snapshot."""
    return _tf_tree_snapshot()


@mcp.tool()
def list_processes() -> str:
    """List local processes."""
    return _list_processes()


@mcp.tool()
def list_ros_daemons() -> str:
    """Show ROS daemon status."""
    return _list_ros_daemons()


@mcp.tool()
def ros_domain_id() -> str:
    """Show ROS domain ID."""
    return _ros_domain_id()


@mcp.tool()
def ros_environment_status() -> str:
    """Show ROS environment."""
    return _ros_environment_status()


@mcp.tool()
def inspect_launch_processes() -> str:
    """Inspect launch processes."""
    return _inspect_launch_processes()


@mcp.tool()
def list_diagnostics() -> str:
    """List diagnostic endpoints."""
    return _list_diagnostics()


@mcp.tool()
def get_diagnostic_status() -> str:
    """Get diagnostic status."""
    return _get_diagnostic_status()


@mcp.tool()
def check_node_health(node: str) -> str:
    """Check node health."""
    return _check_node_health(node)


@mcp.tool()
def check_topic_health(topic: str) -> str:
    """Check topic health."""
    return _check_topic_health(topic)


@mcp.tool()
def ros_time_status() -> str:
    """Read ROS clock status."""
    return _ros_time_status()


@mcp.tool()
def clock_topic_status() -> str:
    """Inspect clock topic."""
    return _clock_topic_status()


@mcp.tool()
def use_sim_time_status(node: str) -> str:
    """Read node simulation-time setting."""
    return _use_sim_time_status(node)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ROS2 MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8001")))
    args = parser.parse_args()
    try:
        if args.transport == "stdio":
            mcp.run()
        else:
            mcp.run(
                transport="streamable-http",
                host=args.host,
                port=args.port,
                streamable_http_path="/mcp",
                stateless_http=False,
            )
    except KeyboardInterrupt:
        pass
