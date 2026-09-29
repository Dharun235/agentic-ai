"""Read-only ROS 2 command tools.

Uses the native ``ros2`` command from the environment where this server runs.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time


def _command(args: list[str]) -> list[str]:
    return ["ros2", *args]


def run_ros2(args: list[str]) -> str:
    """Run one bounded ROS 2 CLI query and return observed output."""
    executable = _command(args)[0]
    if shutil.which(executable) is None:
        if executable == "ros2":
            return "ROS 2 unavailable: `ros2` command not found."
        return f"ROS 2 unavailable: `{executable}` command not found."
    try:
        result = subprocess.run(
            _command(args),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "ROS 2 query timed out after 15 seconds."
    output = (result.stdout or result.stderr).strip()
    if result.returncode:
        return f"ROS 2 command failed ({result.returncode}): {output}"
    return output or "No ROS 2 objects found."


def _run_local(args: list[str], timeout: int = 15) -> str:
    """Run bounded local command and return observed output."""
    if not args or shutil.which(args[0]) is None:
        return f"Command unavailable: `{args[0] if args else ''}` not found."
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds."
    output = (result.stdout or result.stderr).strip()
    if result.returncode:
        return f"Command failed ({result.returncode}): {output}"
    return output or "No output."


def _run_ros2_process(args: list[str], timeout: int = 15) -> str:
    """Run bounded native ROS 2 process."""
    command = _command(args)
    if shutil.which(command[0]) is None:
        return f"ROS 2 unavailable: `{command[0]}` command not found."
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as error:
        partial = error.stdout or error.stderr or ""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        if partial.strip():
            return f"ROS 2 bounded output before timeout:\n{partial.strip()}"
        return f"ROS 2 query timed out after {timeout} seconds."
    output = (result.stdout or result.stderr).strip()
    if result.returncode:
        return f"ROS 2 command failed ({result.returncode}): {output}"
    return output or "No ROS 2 objects found."


def runtime_status() -> str:
    """Check essential native ROS2 runtime prerequisites."""
    ros2_path = shutil.which("ros2")
    lines = [f"ros2_command: {'available' if ros2_path else 'missing'}"]
    return "\n".join(lines)


def list_nodes() -> str:
    """List currently discovered ROS 2 nodes."""
    return run_ros2(["node", "list"])


def list_topics() -> str:
    """List currently discovered ROS 2 topics."""
    return run_ros2(["topic", "list"])


def list_services() -> str:
    """List currently discovered ROS 2 services."""
    return run_ros2(["service", "list"])


def list_actions() -> str:
    """List currently discovered ROS 2 actions."""
    return run_ros2(["action", "list"])


def node_info(node: str) -> str:
    """Show publishers, subscribers, services, and clients for one node."""
    if not node.startswith("/"):
        node = "/" + node
    return run_ros2(["node", "info", node])


def topic_info(topic: str) -> str:
    """Show type and endpoint information for one topic."""
    return run_ros2(["topic", "info", topic if topic.startswith("/") else "/" + topic])


def service_info(service: str) -> str:
    """Show type information for one service."""
    return run_ros2(["service", "type", service if service.startswith("/") else "/" + service])


def action_info(action: str) -> str:
    """Show type information for one action."""
    return run_ros2(["action", "info", action if action.startswith("/") else "/" + action])


def system_snapshot() -> str:
    """Return one verified snapshot of nodes, topics, services, and actions."""
    return "\n".join([
        "NODES:\n" + list_nodes(),
        "TOPICS:\n" + list_topics(),
        "SERVICES:\n" + list_services(),
        "ACTIONS:\n" + list_actions(),
    ])


# Parameter inspection

def list_node_parameters(node: str) -> str:
    """List parameters declared by one ROS2 node."""
    return run_ros2(["param", "list", node if node.startswith("/") else "/" + node])


def get_node_parameter(node: str, name: str) -> str:
    """Read one parameter value from one ROS2 node."""
    return run_ros2(["param", "get", node if node.startswith("/") else "/" + node, name])


def get_node_parameters(node: str) -> str:
    """Dump all parameters from one ROS2 node."""
    return run_ros2(["param", "dump", node if node.startswith("/") else "/" + node])


def describe_node_parameters(node: str) -> str:
    """Describe parameter types and constraints for one ROS2 node."""
    normalized = node if node.startswith("/") else "/" + node
    names = list_node_parameters(normalized)
    if names.startswith("ROS 2 ") or names == "No ROS 2 objects found.":
        return names
    descriptions = []
    for name in names.splitlines():
        name = name.strip()
        if name:
            descriptions.append(run_ros2(["param", "describe", normalized, name]))
    return "\n\n".join(descriptions) or "No parameters found."


# Topic runtime data

def ros_topic_echo(topic: str, message_count: int = 1) -> str:
    """Read at most ten messages from a topic using bounded one-shot queries."""
    count = max(1, min(int(message_count), 10))
    topic = topic if topic.startswith("/") else "/" + topic
    outputs = [run_ros2(["topic", "echo", topic, "--once"]) for _ in range(count)]
    return "\n--- message boundary ---\n".join(outputs)


def ros_topic_hz(topic: str) -> str:
    """Measure bounded topic publication frequency."""
    return _run_ros2_process(["topic", "hz", topic if topic.startswith("/") else "/" + topic], timeout=20)


def ros_topic_bw(topic: str) -> str:
    """Measure bounded topic bandwidth."""
    return _run_ros2_process(["topic", "bw", topic if topic.startswith("/") else "/" + topic], timeout=20)


def ros_topic_type(topic: str) -> str:
    """Return the ROS2 message type for one topic."""
    normalized = topic if topic.startswith("/") else "/" + topic
    result = run_ros2(["topic", "type", normalized])
    for _ in range(2):
        if not result.startswith("ROS 2 command failed"):
            return result
        time.sleep(0.2)
        result = run_ros2(["topic", "type", normalized])
    if result.startswith("ROS 2 command failed"):
        info = run_ros2(["topic", "info", normalized])
        if not info.startswith("ROS 2 "):
            for line in info.splitlines():
                if line.startswith("Type:"):
                    return line.split(":", 1)[1].strip()
        listed = run_ros2(["topic", "list", "-t"])
        for line in listed.splitlines():
            if line.startswith(normalized + " ") and "[" in line and line.endswith("]"):
                return line.rsplit("[", 1)[1][:-1]
    return result


# Interface inspection

def ros_message_info(type_name: str) -> str:
    """Show a ROS2 message interface definition."""
    return run_ros2(["interface", "show", type_name])


def ros_service_definition(type_name: str) -> str:
    """Show a ROS2 service interface definition."""
    return run_ros2(["interface", "show", type_name])


def ros_action_definition(type_name: str) -> str:
    """Show a ROS2 action interface definition."""
    return run_ros2(["interface", "show", type_name])


# Graph analysis

def ros_node_graph(node: str) -> str:
    """Show graph connections for one ROS2 node."""
    return node_info(node)


def find_topic_publishers(topic: str) -> str:
    """Show publishers for one ROS2 topic."""
    return _topic_endpoints(topic, "PUBLISHER")


def find_topic_subscribers(topic: str) -> str:
    """Show subscribers for one ROS2 topic."""
    return _topic_endpoints(topic, "SUBSCRIPTION")


def _topic_endpoints(topic: str, endpoint_type: str) -> str:
    """Return topic header plus only requested verbose endpoint blocks."""
    normalized = topic if topic.startswith("/") else "/" + topic
    output = run_ros2(["topic", "info", normalized, "--verbose"])
    if output.startswith("ROS 2 ") or output == "No ROS 2 objects found.":
        return output
    lines = output.splitlines()
    blocks = output.split("\n\n")
    topic_type = next((line for line in lines if line.startswith("Type:")), "")
    count_label = "Publisher count:" if endpoint_type == "PUBLISHER" else "Subscription count:"
    count = next((line for line in lines if line.startswith(count_label)), "")
    nodes = [
        line.split(":", 1)[1].strip()
        for block in blocks
        if f"Endpoint type: {endpoint_type}" in block
        for line in block.splitlines()
        if line.startswith("Node name:")
    ]
    if not nodes:
        return "\n".join(line for line in (topic_type, count, f"No {endpoint_type.lower()} endpoints found.") if line)
    unique_nodes = list(dict.fromkeys(nodes))
    label = "Publisher nodes" if endpoint_type == "PUBLISHER" else "Subscriber nodes"
    return "\n".join([line for line in (topic_type, count) if line] + [f"{label}:", *unique_nodes])


def find_unconnected_topics() -> str:
    """Find topics with no publishers or no subscribers from the live graph."""
    topics = list_topics()
    if topics.startswith("ROS 2 ") or topics == "No ROS 2 objects found.":
        return topics
    unconnected = []
    for topic in topics.splitlines():
        topic = topic.strip()
        if not topic:
            continue
        info = run_ros2(["topic", "info", topic])
        if "Publisher count: 0" in info or "Subscription count: 0" in info:
            unconnected.append(f"{topic}\n{info}")
    return "\n\n".join(unconnected) or "No unconnected topics found."


def ros_graph_snapshot() -> str:
    """Return a live ROS2 graph snapshot."""
    return system_snapshot()


# TF2

def list_tf_frames() -> str:
    """List observed TF2 frame data with a bounded query."""
    return run_ros2(["topic", "echo", "/tf", "--once"])


def tf_frame_info(frame: str) -> str:
    """Show bounded TF2 data associated with one frame."""
    result = run_ros2(["topic", "echo", "/tf", "--once"])
    if result.startswith("ROS 2 ") or frame in result:
        return result
    return f"TF frame not observed: {frame}\n{result}"


def tf_transform(source: str, target: str) -> str:
    """Query one bounded TF2 transform."""
    return _run_ros2_process(["run", "tf2_ros", "tf2_echo", source, target], timeout=15)


def tf_tree_snapshot() -> str:
    """Return bounded TF2 tree output."""
    return _run_ros2_process(["run", "tf2_tools", "view_frames"], timeout=15)


# Launch and runtime

def list_processes() -> str:
    """List running local processes."""
    return _run_local(["ps", "-axo", "pid,ppid,comm,args"])


def list_ros_daemons() -> str:
    """Show ROS2 daemon status."""
    return run_ros2(["daemon", "status"])


def ros_domain_id() -> str:
    """Return configured ROS_DOMAIN_ID."""
    return f"ROS_DOMAIN_ID: {os.getenv('ROS_DOMAIN_ID', '0')}"


def ros_environment_status() -> str:
    """Return relevant ROS2 environment settings."""
    names = ("ROS_DISTRO", "ROS_DOMAIN_ID", "ROS_LOCALHOST_ONLY", "RMW_IMPLEMENTATION", "ROS_NAMESPACE")
    return "\n".join(f"{name}: {os.getenv(name, '<unset>')}" for name in names)


def inspect_launch_processes() -> str:
    """List processes likely belonging to ROS2 launch."""
    result = list_processes()
    lines = [line for line in result.splitlines() if "launch" in line.lower() or "ros2" in line.lower()]
    return "\n".join(lines) or "No ROS2 launch processes found."


# Diagnostics

def list_diagnostics() -> str:
    """List diagnostic topic endpoints."""
    topics = run_ros2(["topic", "list", "-t"])
    lines = [line for line in topics.splitlines() if "diagnostic" in line.lower()]
    return "\n".join(lines) or "No diagnostic topics found."


def get_diagnostic_status() -> str:
    """Read one bounded diagnostic message."""
    return run_ros2(["topic", "echo", "/diagnostics", "--once"])


def check_node_health(node: str) -> str:
    """Check whether one node is present and inspect its graph connections."""
    nodes = list_nodes()
    normalized = node if node.startswith("/") else "/" + node
    if normalized not in nodes.splitlines():
        return f"Node unhealthy or absent: {normalized}\n{nodes}"
    return f"Node present: {normalized}\n{node_info(normalized)}"


def check_topic_health(topic: str) -> str:
    """Check topic type and endpoint counts."""
    normalized = topic if topic.startswith("/") else "/" + topic
    return run_ros2(["topic", "info", normalized])


# Simulation and time

def ros_time_status() -> str:
    """Read one bounded ROS2 clock message."""
    return run_ros2(["topic", "echo", "/clock", "--once"])


def clock_topic_status() -> str:
    """Inspect the ROS2 clock topic."""
    return run_ros2(["topic", "info", "/clock"])


def use_sim_time_status(node: str) -> str:
    """Read one node's use_sim_time parameter."""
    return get_node_parameter(node, "use_sim_time")
