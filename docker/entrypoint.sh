#!/usr/bin/env bash
set -euo pipefail

exec uvicorn web_app:app --host 0.0.0.0 --port 8000
