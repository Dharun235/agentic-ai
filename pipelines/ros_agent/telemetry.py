"""Compulsory Phoenix observability for every agent run."""

from __future__ import annotations

import os
from urllib.request import urlopen
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode


PHOENIX_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006/v1/traces")
PHOENIX_UI = os.getenv("PHOENIX_UI_URL", "http://127.0.0.1:6006")
PHOENIX_HEALTH = os.getenv("PHOENIX_HEALTH_URL", PHOENIX_UI)
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT_NAME", "ros-agent")

_provider = None
_startup_error: str | None = None

try:
    from phoenix.otel import register

    _provider = register(endpoint=PHOENIX_ENDPOINT, project_name=PHOENIX_PROJECT)
except Exception as error:  # startup check reports this; runs must not hide it
    _startup_error = str(error)

tracer = (_provider or trace.get_tracer_provider()).get_tracer("ros-agent")


def status() -> dict:
    reachable = False
    reachability_error = None
    if _provider is not None:
        try:
            with urlopen(PHOENIX_HEALTH, timeout=1):
                reachable = True
        except Exception as error:
            reachability_error = str(error)
    return {
        "required": True,
        "available": _provider is not None,
        "reachable": reachable,
        "endpoint": PHOENIX_ENDPOINT,
        "ui_url": PHOENIX_UI,
        "health_url": PHOENIX_HEALTH,
        "project": PHOENIX_PROJECT,
        "error": _startup_error or reachability_error,
    }


def require_available() -> None:
    if _provider is None:
        raise RuntimeError(
            "Phoenix observability is required but unavailable. "
            f"Start Phoenix at {PHOENIX_UI}. Details: {_startup_error}"
        )
    try:
        with urlopen(PHOENIX_HEALTH, timeout=1):
            return
    except Exception as error:
        raise RuntimeError(
            "Phoenix observability is required but its server is unreachable. "
            f"Start Phoenix at {PHOENIX_UI}. Details: {error}"
        ) from error


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")


@contextmanager
def span(name: str, **attributes) -> Iterator[Span]:
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value if isinstance(value, (str, int, float, bool)) else str(value))
        try:
            yield current
        except Exception as error:
            current.record_exception(error)
            current.set_status(Status(StatusCode.ERROR, str(error)))
            raise
