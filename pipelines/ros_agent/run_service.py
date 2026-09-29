"""Read-only API view of named run state and debug artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings
from .storage import safe_name


class RunNotFound(FileNotFoundError):
    pass


class RunRepository:
    """Expose persisted run artifacts without touching graph execution."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings["run_dir"])

    def path(self, name: str) -> Path:
        path = self.root / safe_name(name)
        if not (path / "manifest.json").exists():
            raise RunNotFound(f"run not found: {safe_name(name)}")
        return path

    @staticmethod
    def _json(path: Path, default: Any):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def manifest(self, name: str) -> dict:
        return self._json(self.path(name) / "manifest.json", {})

    def plan(self, name: str) -> list[dict]:
        return self._json(self.path(name) / "plan.json", [])

    def observations(self, name: str) -> list[dict]:
        return self._json(self.path(name) / "observations.json", [])

    def events(self, name: str) -> list[dict]:
        path = self.path(name) / "events.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def model_calls(self, name: str) -> list[dict]:
        path = self.path(name) / "model_calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def status(self, name: str) -> dict:
        manifest = self.manifest(name)
        plan = self.plan(name)
        observations = self.observations(name)
        events = self.events(name)
        return {
            "name": manifest["name"],
            "goal": manifest["goal"],
            "status": manifest["status"],
            "started_at": manifest.get("started_at"),
            "updated_at": manifest.get("updated_at"),
            "completed_at": manifest.get("completed_at"),
            "plan_tasks": len(plan),
            "completed_tasks": sum(item.get("status") == "complete" for item in plan),
            "failed_tasks": sum(item.get("status") == "failed" for item in plan),
            "observations": len(observations),
            "events": len(events),
            "last_event": events[-1] if events else None,
            "error": manifest.get("error"),
        }

    def debug(self, name: str) -> dict:
        return {
            "status": self.status(name),
            "manifest": self.manifest(name),
            "plan": self.plan(name),
            "observations": self.observations(name),
            "events": self.events(name),
            "model_calls": self.model_calls(name),
        }
