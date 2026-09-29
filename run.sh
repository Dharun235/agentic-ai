#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./run.sh app                   Start the local web app (source ROS 2 first)
  ./run.sh mcp                   Start the local MCP server over HTTP
  ./run.sh check                 Check repository prerequisites
EOF
}

case "${1:-}" in
  check)
    exec python3 scripts/check_prerequisites.py
    ;;
  app)
    exec .venv/bin/uvicorn web_app:app --host 127.0.0.1 --port 8000
    ;;
  mcp)
    exec .venv/bin/python pipelines/ros/mcp_server.py \
      --transport streamable-http --host 127.0.0.1 --port 8001
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
