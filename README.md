# ROS2 agent

Goal-driven ROS 2 inspection agent with a web UI. It uses Ollama for planning
and tool search, MCP to run read-only ROS 2 queries, SQLite for run state, and
Phoenix for tracing.

## Quick start

Run the app directly on the ROS 2 host. Use Ubuntu 24.04, ROS 2 Jazzy, and
Python 3.10 or newer.

### 1. Install ROS 2

Follow the [ROS 2 Jazzy installation guide](https://docs.ros.org/en/jazzy/Installation.html).
Open a terminal and source ROS 2 before starting the app:

```bash
source /opt/ros/jazzy/setup.bash
ros2 --help
```

The app starts its MCP server as a local subprocess. It inherits this shell's
ROS 2 environment and queries the ROS graph visible to that shell.

### 2. Install the app

From the repository root, create a virtual environment and install the project.
`pyproject.toml` is the dependency source; `pip install -e .` installs it.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

### 3. Install and start Ollama

Install Ollama from [ollama.com](https://ollama.com/download). Keep Ollama
running in its own terminal or as a service. Pull both required models:

```bash
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
curl http://127.0.0.1:11434/api/tags
```

Set `OLLAMA_HOST` if Ollama listens somewhere else.

### 4. Start Phoenix

Phoenix is required for app runs. Install `uv` if needed, then run Phoenix in a
separate terminal:

```bash
python -m pip install uv
uvx arize-phoenix serve
```

Keep it running at <http://127.0.0.1:6006>. Set
`PHOENIX_COLLECTOR_ENDPOINT`, `PHOENIX_HEALTH_URL`, or `PHOENIX_UI_URL` to
change its endpoints.

### 5. Install and start OpenSearch

Install OpenSearch 2.19 or newer using the
[official installation guide](https://docs.opensearch.org/latest/install-and-configure/).
The agent uses OpenSearch k-NN vectors and BM25, fused with reciprocal-rank
fusion. Ollama creates the document and query embeddings. OpenSearch stores the
tool cards, vector index, and search pipeline.

Start OpenSearch and configure its endpoint and credentials. The defaults target
an unauthenticated local service at `http://127.0.0.1:9200`; keep that setup on
localhost only. For secured HTTPS deployments, set the URL, username, password,
and trusted CA certificate as needed:

```bash
export OPENSEARCH_URL=https://localhost:9200
export OPENSEARCH_USERNAME=admin
export OPENSEARCH_PASSWORD='your-local-password'
export OPENSEARCH_CA_CERT=/path/to/root-ca.pem
```

The app creates a versioned index and atomically switches the
`ros2-tool-catalog` alias when the catalog or embedding model changes. It also
creates an RRF search pipeline. Keep an old index until the replacement has
been indexed successfully; the app removes stale catalog indexes after switch.

### 6. Start the web app

In another terminal, source ROS 2 and activate the environment again. Then run:

```bash
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Enter a unique session name and task, review the
plan, then approve it. The local MCP server starts automatically for each run.
For remote MCP, set `ROS_MCP_URL` to its Streamable HTTP `/mcp` endpoint before
starting the app.

### Optional: run MCP over HTTP

Use this only when the app cannot start MCP as a local subprocess. Start the MCP
server in a ROS 2-sourced terminal:

```bash
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python pipelines/ros/mcp_server.py --transport streamable-http --host 127.0.0.1 --port 8001
```

Set `ROS_MCP_URL=http://127.0.0.1:8001/mcp` in the app terminal.

## Check setup

Run the prerequisite checker after starting Ollama, OpenSearch, Phoenix, and the
app. Source ROS 2 first so it can check local ROS discovery.

```bash
source /opt/ros/jazzy/setup.bash
python scripts/check_prerequisites.py
python scripts/check_prerequisites.py --running
```

Run repository checks with the development extra:

```bash
python -m pip install -e '.[dev]'
pytest -q
python -m compileall -q pipelines tests scripts web_app.py
```

## Run data and debugging

Each task is isolated under `data/runs/<name>/`. Files include lifecycle
metadata, validated plan, raw MCP observations, progress events, model-call
metadata, SQLite checkpoints, and exact results. OpenSearch stores the tool
catalog index outside the run-data directory.

Phoenix traces retrieval, planning, validation, approval, MCP execution, and
answer generation. Runs do not start if Phoenix is unavailable. Runtime ROS 2
output is evidence, not RAG memory.

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

See [`pipelines/ros/tool_catalog.md`](pipelines/ros/tool_catalog.md) for the
read-only MCP tools and their arguments.
