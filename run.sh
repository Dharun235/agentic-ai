#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./run.sh check                 Check Docker and repository prerequisites
  ./run.sh native                Start the Docker app against native ROS2 MCP at :8001
  ./run.sh stop                  Stop the Docker app
EOF
}

case "${1:-}" in
  check)
    exec python3 scripts/check_prerequisites.py
    ;;
  native)
    exec env ROS_MCP_URL="${ROS_MCP_URL:-http://host.docker.internal:8001/mcp}" \
      docker compose up --build
    ;;
  stop)
    docker compose down
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
