"""Read-only ROS 2 command tools.

Uses local ``ros2`` when available. Set ``ROS2_DOCKER_CONTAINER`` to run the
same commands inside a ROS 2 Docker container.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time


def _command(args: list[str]) -> list[str]:
    container = os.getenv("ROS2_DOCKER_CONTAINER", "").strip()
    if container:
        ros_setup = os.getenv("ROS2_SETUP", "/opt/ros/jazzy/setup.bash")
        ros_command = shlex.join(["ros2", *args])
        script = f"source {shlex.quote(ros_setup)} && {ros_command}"
        return ["docker", "exec", container, "bash", "-lc", script]
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


def runtime_status() -> str:
    """Check essential local/container ROS2 runtime prerequisites."""
    ros2_path = shutil.which("ros2")
    docker_path = shutil.which("docker")
    container = os.getenv("ROS2_DOCKER_CONTAINER", "").strip()
    lines = [f"ros2_command: {'available' if ros2_path else 'missing'}"]
    lines.append(f"docker_command: {'available' if docker_path else 'missing'}")
    lines.append(f"container_configured: {'yes' if container else 'no'}")

    if container and docker_path:
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", container],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            status = (result.stdout or result.stderr).strip()
            lines.append(f"container_status: {status or 'unknown'}")
            if status == "running":
                setup = os.getenv("ROS2_SETUP", "/opt/ros/jazzy/setup.bash")
                ros_result = subprocess.run(
                    [
                        "docker", "exec", container, "bash", "-lc",
                        f"source {shlex.quote(setup)} && command -v ros2",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                lines.append(
                    "container_ros2: available"
                    if ros_result.returncode == 0
                    else "container_ros2: missing"
                )
        except subprocess.TimeoutExpired:
            lines.append("container_status: timeout")
    elif container:
        lines.append("container_status: unavailable (docker missing)")
    else:
        lines.append("container_status: not configured")

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


def _docker(args: list[str]) -> str:
    """Run a bounded Docker lifecycle command for configured ROS container."""
    container = os.getenv("ROS2_DOCKER_CONTAINER", "").strip()
    if not container:
        return "Action unavailable: ROS2_DOCKER_CONTAINER is not configured."
    if shutil.which("docker") is None:
        return "Action unavailable: `docker` command not found."
    try:
        result = subprocess.run(
            ["docker", *args, container],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "Action failed: Docker command timed out after 20 seconds."
    output = (result.stdout or result.stderr).strip()
    if result.returncode:
        return f"Action failed ({result.returncode}): {output}"
    return output or f"Docker action completed: {' '.join(args)} {container}"


def start_demo_node() -> str:
    """Start configured demo ROS container and verify its node appears."""
    result = _docker(["start"])
    if result.startswith("Action "):
        return result
    time.sleep(1)
    nodes = list_nodes()
    if "/agentic_demo_node" not in nodes.splitlines():
        return f"Action uncertain: container started but demo node was not observed.\n{nodes}"
    return f"Action verified: demo node is running.\n{nodes}"


def stop_demo_node() -> str:
    """Stop configured demo ROS container and verify its node disappears."""
    result = _docker(["stop"])
    if result.startswith("Action "):
        return result
    time.sleep(1)
    nodes = list_nodes()
    if "/agentic_demo_node" in nodes.splitlines():
        return f"Action uncertain: container stopped but demo node remains visible.\n{nodes}"
    return "Action verified: demo node is stopped."
