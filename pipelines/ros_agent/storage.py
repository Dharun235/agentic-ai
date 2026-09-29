"""Named, inspectable artifacts for one goal-driven agent run."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(name: str) -> str:
    value = NAME_PATTERN.sub("-", name.strip()).strip(".-")
    if not value:
        raise ValueError("run name must contain letters or numbers")
    if value in {".", ".."}:
        raise ValueError("invalid run name")
    return value[:120]


class RunStore:
    """Filesystem artifact store; SQLite remains LangGraph's durable state."""

    def __init__(self, root: Path, name: str, goal: str, *, existing: bool = False):
        self.name = safe_name(name)
        self.goal = goal
        self.path = root / self.name
        if self.path.exists() and not existing:
            raise FileExistsError(f"run name already exists: {self.name}")
        root.mkdir(parents=True, exist_ok=True)
        if not existing:
            self.path.mkdir(parents=True, exist_ok=False)
            (self.path / "results").mkdir()
        self.cancel_file = self.path / "cancel.requested"
        self.state_path = self.path / "state.sqlite"
        self.manifest_path = self.path / "manifest.json"
        self.events_path = self.path / "events.jsonl"
        self.model_calls_path = self.path / "model_calls.jsonl"
        if existing:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self.goal = manifest["goal"]
            self.started_at = manifest["started_at"]
            self.status = manifest["status"]
        else:
            self.started_at = _utc()
            self.status = "running"
            self.events_path.touch()
            self.model_calls_path.touch()
            self._write_manifest("running")

    @classmethod
    def open_existing(cls, root: Path, name: str) -> "RunStore":
        return cls(root, name, "", existing=True)

    def _write_json(self, path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    def _write_manifest(self, status: str, **extra: Any) -> None:
        artifacts = {
            "state": "state.sqlite",
            "plan": "plan.json",
            "observations": "observations.json",
            "events": "events.jsonl",
            "model_calls": "model_calls.jsonl",
        }
        if self.cancel_file.exists():
            artifacts["cancellation"] = "cancel.requested"
        self._write_json(self.manifest_path, {
            "name": self.name,
            "goal": self.goal,
            "status": status,
            "started_at": self.started_at,
            "updated_at": _utc(),
            "artifacts": artifacts,
            **extra,
        })

    def event(self, component: str, kind: str, **data: Any) -> None:
        record = {"at": _utc(), "component": component, "kind": kind, **data}
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def model_call(self, component: str, request: Any, response: Any = None, **data: Any) -> None:
        """Persist one isolated model exchange for reproducible debugging."""
        record = {"at": _utc(), "component": component, "request": request, **data}
        if response is not None:
            record["response"] = response
        with self.model_calls_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def cancelled(self) -> bool:
        return self.cancel_file.exists()

    def request_cancel(self) -> None:
        self.cancel_file.write_text("requested\n", encoding="utf-8")
        self.event("control", "cancel_requested")

    def finalize(self, result: dict) -> None:
        status = result.get("status", "failed")
        self._write_json(self.path / "plan.json", result.get("plan", []))
        self._write_json(self.path / "observations.json", result.get("observations", []))
        for observation in result.get("observations", []):
            task_id = observation.get("task_id", "unknown")
            self._write_json(self.path / "results" / f"task-{task_id}.json", observation)
        for event in result.get("events", []):
            component = event.get("component", "graph")
            data = {k: v for k, v in event.items() if k not in {"kind", "component"}}
            self.event(component, event.get("kind", "event"), **data)
        self._write_manifest(
            status,
            answer=result.get("answer"),
            error=result.get("error"),
            completed_at=_utc(),
            cancelled=self.cancelled(),
        )

    def checkpoint(self, result: dict, status: str) -> None:
        """Persist resumable graph state without marking run complete."""
        self._write_json(self.path / "plan.json", result.get("plan", []))
        self._write_json(self.path / "observations.json", result.get("observations", []))
        self._write_manifest(status, answer=result.get("answer"), error=result.get("error"))


def request_cancel(root: Path, name: str) -> Path:
    """Request cooperative cancellation for named run without touching state."""
    run_path = root / safe_name(name)
    if not run_path.is_dir():
        raise FileNotFoundError(f"active run not found: {safe_name(name)}")
    marker = run_path / "cancel.requested"
    marker.write_text("requested\n", encoding="utf-8")
    return marker
