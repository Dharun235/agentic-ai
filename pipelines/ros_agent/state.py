"""Explicit state for one goal-oriented agent run."""

from dataclasses import dataclass, field


@dataclass
class AgentState:
    task: str
    max_steps: int = 8
    status: str = "running"
    phase: str = "planning"
    goal: str | None = None
    current_step: int = 0
    tool_calls: int = 0
    steps: list[dict] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    verification: str | None = None
    failure_reason: str | None = None
    answer: str | None = None

    def __post_init__(self):
        self.goal = self.task

    def record(self, kind: str, **data):
        self.steps.append({"kind": kind, **data})

    def observe(self, tool: str, output: str):
        self.tool_calls += 1
        self.observations.append({"tool": tool, "output": output})
        self.record("observation", tool=tool, output=output)

    def verify(self, passed: bool, reason: str):
        self.verification = reason
        self.record("verification", passed=passed, reason=reason)
        if not passed:
            self.status = "needs_retry"

    def finish(self, answer: str):
        self.answer = answer
        self.phase = "complete"
        self.status = "complete"
        return answer

    def fail(self, reason: str):
        self.verification = reason
        self.failure_reason = reason
        self.phase = "failed"
        self.status = "failed"
        self.answer = reason
        return reason
