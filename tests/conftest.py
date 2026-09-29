"""Keep unit tests independent of live Phoenix availability."""

from contextlib import contextmanager

import pytest


@pytest.fixture(autouse=True)
def disable_external_observability_check(monkeypatch):
    monkeypatch.setattr(
        "pipelines.ros_agent.telemetry.require_available",
        lambda: None,
    )

    @contextmanager
    def local_span(*_args, **_kwargs):
        yield None

    monkeypatch.setattr("pipelines.ros_agent.telemetry.span", local_span)
