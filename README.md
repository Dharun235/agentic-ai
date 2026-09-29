# ROS2 agent

Goal-driven ROS2 inspection agent with a web UI. The stack uses LangGraph for
the run lifecycle, Chroma/Ollama for capability retrieval, the project MCP
server for ROS2 execution, SQLite for per-run state, and Phoenix for compulsory
tracing.

## Setup

The supported deployment is deliberately narrow:

```text
native ROS2 + native MCP server + native Ollama + native Phoenix
                                      ↑
                              Docker agent UI
```

Docker runs only the application. ROS2 stays on the host so it can inspect the
user's real ROS graph. The checker is dependency-free and uses only Python's
standard library.

### 1. Install ROS2

Install ROS2 Jazzy using the [official installation guide](https://docs.ros.org/en/jazzy/Installation.html).
The recommended supported host is Ubuntu 24.04. On every shell that runs the
MCP server, source ROS2 first:

```bash
source /opt/ros/jazzy/setup.bash
ros2 --help
```

The MCP server must run on the same host/environment as ROS2. It executes the
actual `ros2` CLI and returns live output.

### 2. Install Python dependencies

Python 3.10 or newer is required. Create the environment and install the
project from the single dependency declaration in `pyproject.toml`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs MCP, LangGraph, Chroma, Ollama's Python client, FastAPI,
Phoenix OpenTelemetry integration, and the remaining application libraries.
ROS2 itself is not a pip dependency; install it from the official ROS2 guide.

### 3. Install and start Ollama

Install Ollama from the [official download page](https://ollama.com/download):

```bash
ollama serve
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
```

Verify it:

```bash
curl http://127.0.0.1:11434/api/tags
```

### 4. Install and start Phoenix

Follow the [official local Phoenix deployment guide](https://arize.com/docs/phoenix/self-hosting/deployments/local).
With `uv`:

```bash
uvx arize-phoenix serve
```

Phoenix must be available at `http://127.0.0.1:6006`.

### 5. Start the native ROS2 MCP server

In a shell where ROS2 is sourced and the virtual environment is active:

```bash
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python pipelines/ros/mcp_server.py \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8001
```

This exposes the official MCP Streamable HTTP endpoint at:
`http://127.0.0.1:8001/mcp`.

### 6. Start the Docker application

Docker Desktop works on macOS and Windows; Docker Engine works on Linux.
Build dependencies are installed inside the app image from `pyproject.toml`.

```bash
./run.sh native
```

Open <http://localhost:8000>. Phoenix is at <http://localhost:6006>.

The `host.docker.internal` mapping is configured in Compose so the container
can reach native Ollama, Phoenix, and the native MCP server. On Linux Docker
Engine, the same mapping is provided through `host-gateway`.

The UI requires a unique name for every task. It creates a plan, validates the
MCP tools and arguments, waits for approval, executes the scheduled plan, and
shows the final answer and saved run directory. `Stop` requests cooperative
cancellation. A terminal run cannot be reused; start a new named session.

Stop the stack while preserving data:

```bash
docker compose down
```

The bind-mounted `data/` directory contains named runs. Ollama and Phoenix keep
their own data according to how those prerequisite services were installed.

## Run data and debugging

Each task is isolated under `data/runs/<name>/`:

```text
manifest.json       lifecycle and final status
plan.json            validated scheduled plan
observations.json    raw MCP evidence by task
events.jsonl         state/component progress events
model_calls.jsonl    model request metadata and bounded responses
state.sqlite         LangGraph checkpoint state
results/task-N.json  exact raw result for each executor task
```

The UI exposes the plan, observations, result, events, debug data, and
observability trace links through its API. Phoenix traces every run, including
RAG, planning, validation, approval, MCP execution, and final joining. A run
does not start when Phoenix is unavailable.

## Architecture

```text
browser → FastAPI → LangGraph plan/validate/approve → DAG scheduler → MCP → ROS2
                    ↘ Chroma/Ollama capability retrieval       ↘ Phoenix traces
```

The application image contains only the Python agent and its Python
dependencies. It does not contain ROS2, Ollama, or Phoenix. Streamable HTTP is
the deployment transport.

The tool catalog at
[`pipelines/ros/tool_catalog.md`](pipelines/ros/tool_catalog.md) is the
planner's capability map; live MCP schemas remain the execution authority.

The supported inspection tools and their exact arguments are documented in the
catalog. Runtime ROS2 output is evidence, not RAG memory. Raw results remain
outside model prompts until the joiner fetches the exact task IDs needed for the
answer. Each question has its own MCP session and SQLite checkpoint.

## HTTP API

```text
GET  /observability
POST /runs
GET  /runs/{name}
GET  /runs/{name}/plan
POST /runs/{name}/approve
POST /runs/{name}/revise
POST /runs/{name}/cancel
GET  /runs/{name}/observations
GET  /runs/{name}/result
GET  /runs/{name}/events
GET  /runs/{name}/debug
GET  /runs/{name}/observability
```

## Development checks

The dependency-free checker reports missing Docker/Compose, files, Compose
validity, agent health, Phoenix, Ollama/models, and the native ROS2 MCP
endpoint (or local ROS2 when no endpoint is configured).

```bash
python scripts/check_prerequisites.py
python scripts/check_prerequisites.py --running
```

For repository-only checks:

```bash
pytest -q
python -m compileall -q pipelines tests scripts web_app.py
git diff --check
docker compose config
```

See [`pipelines/ros/tool_catalog.md`](pipelines/ros/tool_catalog.md) for the
full MCP catalog.
