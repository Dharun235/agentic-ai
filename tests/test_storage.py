import json

import pytest

from pipelines.ros_agent.storage import RunStore, request_cancel
from pipelines.ros_agent.run_service import RunRepository


def test_named_run_artifacts_and_cancel_marker(tmp_path):
    store = RunStore(tmp_path / "runs", "nodes-check", "List nodes")
    store.event("planner", "plan_validated", task_count=1)
    store.finalize({
        "status": "complete",
        "plan": [{"id": 1}],
        "observations": [{"task_id": 1, "tool": "list_ros_nodes", "output": "/demo"}],
        "answer": "/demo",
    })
    assert json.loads((store.path / "manifest.json").read_text())["status"] == "complete"
    assert json.loads((store.path / "results/task-1.json").read_text())["output"] == "/demo"
    assert "plan_validated" in (store.path / "events.jsonl").read_text()
    request_cancel(tmp_path / "runs", "nodes-check")
    assert store.cancelled()


def test_named_run_is_unique(tmp_path):
    RunStore(tmp_path / "runs", "same-name", "one")
    with pytest.raises(FileExistsError):
        RunStore(tmp_path / "runs", "same-name", "two")


def test_run_repository_exposes_state_views(tmp_path):
    store = RunStore(tmp_path / "runs", "debug-run", "List nodes")
    store.event("planner", "plan_validated", task_count=1)
    store.finalize({
        "status": "complete",
        "plan": [{"id": 1, "tool": "list_ros_nodes", "status": "complete"}],
        "observations": [{"task_id": 1, "tool": "list_ros_nodes", "output": "/demo", "status": "complete"}],
        "answer": "/demo",
    })
    repo = RunRepository(tmp_path / "runs")
    assert repo.status("debug-run")["completed_tasks"] == 1
    assert repo.plan("debug-run")[0]["tool"] == "list_ros_nodes"
    assert repo.observations("debug-run")[0]["output"] == "/demo"
    assert repo.debug("debug-run")["manifest"]["answer"] == "/demo"
