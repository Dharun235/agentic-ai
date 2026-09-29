"""Check host and live Compose prerequisites without third-party packages."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "Dockerfile",
    "docker-compose.yml",
    "pyproject.toml",
    "pipelines/ros/tool_catalog.md",
)


def command(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a short prerequisite command and capture its output."""
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=20, check=check)


def report(label: str, passed: bool, detail: str) -> bool:
    """Print one check and return its result."""
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {detail}")
    return passed


def check_host() -> bool:
    """Check Docker, Compose, repository files, and Compose syntax."""
    ok = True
    docker = shutil.which("docker")
    ok &= report("docker command", docker is not None, docker or "not found")
    if not docker:
        return False

    version = command(["docker", "version", "--format", "{{.Server.Version}}"])
    ok &= report("Docker daemon", version.returncode == 0, (version.stdout or version.stderr).strip())

    compose = command(["docker", "compose", "version"])
    ok &= report("Docker Compose", compose.returncode == 0, (compose.stdout or compose.stderr).strip())

    for relative in REQUIRED_FILES:
        path = ROOT / relative
        ok &= report(f"required file {relative}", path.is_file(), "present" if path.is_file() else "missing")

    config = command(["docker", "compose", "config", "--quiet"])
    ok &= report("Compose configuration", config.returncode == 0, "valid" if config.returncode == 0 else config.stderr.strip())
    return bool(ok)


def check_url(label: str, url: str) -> bool:
    """Check an HTTP endpoint."""
    try:
        with urlopen(url, timeout=3) as response:
            return report(label, 200 <= response.status < 500, f"HTTP {response.status}")
    except Exception as error:
        return report(label, False, str(error))


def local_url(value: str, default: str) -> str:
    """Map the container-only host alias to the host loopback for checks."""
    value = value or default
    return value.replace("host.docker.internal", "127.0.0.1")


def check_ollama() -> bool:
    """Check Ollama and the two models required by the planner and RAG."""
    url = local_url(os.getenv("OLLAMA_HOST", ""), "http://127.0.0.1:11434").rstrip("/")
    try:
        with urlopen(f"{url}/api/tags", timeout=3) as response:
            payload = json.load(response)
        names = {item.get("name", "") for item in payload.get("models", [])}
        required = {"qwen3:0.6b", "qwen3-embedding:0.6b"}
        return report("Ollama models", required <= names, ", ".join(sorted(names)) or "none")
    except Exception as error:
        return report("Ollama", False, str(error))


def check_mcp_endpoint(url: str) -> bool:
    """Perform an MCP initialize and tools/list handshake without the SDK."""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ros-agent-checker", "version": "1"},
        },
    }
    try:
        request = Request(url, data=json.dumps(initialize).encode(), headers=headers, method="POST")
        with urlopen(request, timeout=5) as response:
            body = response.read().decode(errors="replace")
            session = response.headers.get("Mcp-Session-Id")
        if "serverInfo" not in body and '"result"' not in body:
            return report("ROS MCP handshake", False, body[:200])

        listed = {**headers, "Mcp-Session-Id": session} if session else headers
        tools_request = Request(
            url,
            data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode(),
            headers=listed,
            method="POST",
        )
        with urlopen(tools_request, timeout=5) as response:
            tools_body = response.read().decode(errors="replace")
        return report("ROS MCP tools", '"tools"' in tools_body, tools_body[:200])
    except Exception as error:
        return report("ROS MCP handshake", False, str(error))


def check_ros() -> bool:
    """Check the configured native MCP endpoint or local ROS2."""
    mcp_url = os.getenv("ROS_MCP_URL", "").strip()
    if mcp_url:
        return check_mcp_endpoint(mcp_url)

    ros2 = shutil.which("ros2")
    if not ros2:
        return report("ROS2 command", False, "ros2 not found; set ROS_MCP_URL")
    result = command([ros2, "node", "list"])
    return report("ROS2 discovery", result.returncode == 0, (result.stdout or result.stderr).strip())


def check_running() -> bool:
    """Check the app and native ROS2, Ollama, and Phoenix services."""
    ok = True
    ps = command(["docker", "compose", "ps", "--format", "json"])
    if ps.returncode != 0:
        ok &= report("Compose stack", False, ps.stderr.strip())
    else:
        rows = []
        for line in ps.stdout.splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        row = next((item for item in rows if item.get("Service") == "agent"), {})
        state = row.get("State", "not running")
        health = row.get("Health", "")
        ok &= report(
            "agent service",
            state == "running" and health in {"", "healthy"},
            f"{state} {health}".strip(),
        )

    ok &= check_url("agent UI", "http://127.0.0.1:8000/observability")
    ok &= check_url("Phoenix", local_url(os.getenv("PHOENIX_HEALTH_URL", ""), "http://127.0.0.1:6006") + "/v1/healthz")
    ok &= check_ollama()
    ok &= check_ros()
    return bool(ok)


def main() -> int:
    """Run prerequisite checks and return a shell-friendly exit code."""
    parser = argparse.ArgumentParser(description="Check ROS2 agent prerequisites")
    parser.add_argument("--running", action="store_true", help="also require the Compose stack to be running")
    args = parser.parse_args()

    print("ROS2 agent prerequisite check")
    ok = check_host()
    if args.running:
        ok &= check_running()
    elif not args.running:
        print("INFO  live services: skipped; use --running after docker compose up")
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
