# ros-agent

Local ROS2 agent for runtime checks, graph inspection, and demo-node lifecycle. It uses a dedicated MCP client/server pair and live ROS2 CLI output.

## Requirements

- Python 3.10+
- Docker with Colima or Docker Desktop
- ROS2 Jazzy image (built by this project)
- Ollama with `qwen3:0.6b` for complex requests

Official setup: [ROS2](https://docs.ros.org/en/jazzy/Installation.html), [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/), [Colima](https://github.com/abiosoft/colima), [Ollama](https://ollama.com/download).

## Installation

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

For complex, model-planned requests:

```bash
ollama serve
ollama pull qwen3:0.6b
```

## Usage

```bash
python common_app.py
```

Example session:

```text
ROS 2 agent ready. Type exit or quit to stop.
Ask: check ROS2 and give all nodes

[complete] Verified tool output from `list_ros_nodes`:
/ros_agent_demo_node

Ask: show all ROS2 topics

[complete] Verified tool output from `list_ros_topics`:
/parameter_events
/rosout

Ask: what is the weather?

[failed] Cannot complete: request is outside this agent's scope. This agent only handles ROS2 nodes, topics, services, actions, parameters, QoS, and graph inspection.
```

Current capabilities: runtime status, node/topic/service/action listing, entity inspection, graph snapshots, and demo-node start/stop.

## Architecture

```text
CLI → ROS2 agent pipeline → MCP client → MCP server → ros2 CLI → verification
```

MCP is the tool boundary. RAG, memory, web search, filesystem access, and external knowledge are not used. Live ROS2 output is the source of truth.

## Development

Run tests and checks:

```bash
pytest -q
python -m compileall -q pipelines common_app.py tests
git diff --check
```

CI runs pipeline tests and Python compilation without requiring Docker, ROS2, or Ollama. Live integration checks require the `ros-agent` container.

Code standards: [CODE_GUIDELINES.md](CODE_GUIDELINES.md). Contributions are welcome; keep changes focused, documented, and tested.

## License

MIT. See [LICENSE](LICENSE).
