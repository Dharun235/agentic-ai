# ros-agent

Small local agent for ROS2 fundamentals: runtime checks, nodes, topics, services, actions, graph inspection, and one demo-node lifecycle.

Links: [ROS2 installation](https://docs.ros.org/en/jazzy/Installation.html) · [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) · [Ollama](https://ollama.com/download) · [Colima](https://github.com/abiosoft/colima)

Project name: `ros-agent`.

## Setup: macOS container mode

```bash
brew install colima docker
colima start
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker build -t ros-agent:jazzy ros
docker rm -f ros-agent 2>/dev/null || true
docker run -d --name ros-agent --network host ros-agent:jazzy
export ROS2_DOCKER_CONTAINER=ros-agent
```

For free-form planning:

```bash
ollama serve
ollama pull qwen3:0.6b
```

Run:

```bash
python common_app.py
```

## Example asks

```text
check ROS2 setup
check ROS2 and give all nodes
show all ROS2 topics
show all ROS2 services
show all ROS2 actions
inspect ros_agent_demo_node
show ROS2 graph snapshot
start the ROS2 demo node
stop the ROS2 demo node
```

Clear requests route directly to MCP tools. Complex ROS2 requests use Ollama planning. Non-ROS requests are rejected before MCP startup.

## Architecture

```text
common_app.py
  -> ros_agent pipeline
  -> MCP client (stdio)
  -> own ROS2 MCP server
  -> ros2 CLI on host or inside ros-agent
  -> observed output and verification
```

MCP is the tool boundary. The model sees only named ROS2 tools. RAG is not used: no knowledge files, embeddings, vector database, or external search. ROS2 state comes from live CLI observations.

## Tools

`ros2_runtime_status`, node/topic/service/action listing and inspection, `ros_system_snapshot`, plus verified start/stop for `/ros_agent_demo_node`.

Own server: [pipelines/ros/mcp_server.py](pipelines/ros/mcp_server.py). Own client/loop: [pipelines/ros_agent/](pipelines/ros_agent/). Full tool contract: [pipelines/ros/tool_catalog.md](pipelines/ros/tool_catalog.md).

To replicate the setup, install prerequisites, build the same `ros/` image, use container name `ros-agent`, export `ROS2_DOCKER_CONTAINER`, and run the same CLI command above. No hidden repo files or runtime indexes are required.

## Limits

No robot control, arbitrary shell, filesystem access, web search, package installation, unrestricted publishing, or actuation. Missing `ros2`, Docker, container, or Ollama returns an explicit failure/status message.

## Local ROS2 mode

If host has ROS2, source its setup file, unset `ROS2_DOCKER_CONTAINER`, then run the agent. Container mode is recommended on macOS.

## Tests

Run offline routing/scope tests:

```bash
pytest
```

CI runs these pipeline tests and Python compilation. Tests mock changing MCP internals; live checks require running `ros-agent` and use the commands in Setup.

## Next 3

1. Add parameter and QoS inspection.
2. Add bounded topic echo.
3. Add launch/package discovery.

Code practices: [CODE_GUIDELINES.md](CODE_GUIDELINES.md). Contributions welcome; keep changes focused and tested.
