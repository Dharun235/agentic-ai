"""LLMCompiler-style ROS2 agent: planner/scheduler plus joiner."""

from __future__ import annotations

import asyncio
import json
import operator
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Annotated, Literal, TypedDict

import aiosqlite
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, RetryPolicy, interrupt
from ollama import Client
from pydantic import BaseModel, ConfigDict, ValidationError

from .catalog import catalog
from .config import settings
from .mcp_client import MCPRos
from .state import AgentState
from .storage import RunStore, request_cancel, safe_name
from . import telemetry


MAX_TASKS = 8
MAX_REPLANS = 2
MAX_PLAN_REPAIRS = 2
REFERENCE_PATTERN = re.compile(r"\$\{?(\d+)\}?")
RUNTIME_IDENTIFIER_FIELDS = frozenset({"node", "topic", "service", "action", "frame", "source", "target", "type", "name"})
ollama = Client(host=settings["ollama_host"], timeout=60)


@asynccontextmanager
async def _state_checkpointer(path: Path):
    """Open persistent SQLite with busy retry instead of immediate lock failure."""
    async with aiosqlite.connect(str(path), timeout=30) as connection:
        yield AsyncSqliteSaver(connection)


class GraphState(TypedDict, total=False):
    run_name: str
    goal: str
    feedback: str | None
    plan: list[dict]
    observations: list[dict]
    events: Annotated[list[dict], operator.add]
    answer: str | None
    status: str
    error: str | None
    replan_count: int
    approved: bool


class JoinDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["final", "replan"]
    response: str = ""
    feedback: str = ""


class PlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tool: str
    arguments: dict[str, Any] = {}
    depends_on: list[int] = []


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[PlanTask]


@dataclass(slots=True)
class CompilerTask:
    idx: int
    tool: str
    arguments: dict[str, Any]
    dependencies: list[int]


@dataclass(slots=True)
class RunContext:
    mcp: MCPRos
    catalog: Any
    ollama: Any
    store: RunStore


JOIN_SCHEMA = JoinDecision.model_json_schema()
PLAN_SCHEMA = ExecutionPlan.model_json_schema()
FETCH_RESULT_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_task_result",
        "description": "Fetch one exact raw MCP result by task ID from this run.",
        "parameters": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
}


PLANNER_PROMPT = """/no_think
You are a generic LLMCompiler planner.
Return only JSON matching the supplied plan schema.
Use only supplied capabilities and exact tool schemas.
Create the smallest complete dependency-aware plan for the goal.
Prefer the narrowest capability that directly answers each requested part;
do not use an aggregate or snapshot capability when a narrower capability is
available, unless the user explicitly asks for a snapshot or full overview.
Do not add adjacent information not requested. Do not invent tools, identifiers,
arguments, or facts. Every static node/topic/service/action/frame/type/name
argument must appear in the user goal; otherwise obtain it from a prior task
using `$N` or `${N}`. Use `$N` or `${N}` in arguments to reference task N output;
include N in that task's depends_on list. Independent tasks have no dependency.
The runtime executes tasks and performs final joining after the plan.
"""


JOINER_PROMPT = """You are the LLMCompiler joiner for an MCP agent.
You receive a compact index of exact task results. Call fetch_task_result for
every result needed to answer the goal. The runtime returns the unchanged raw
MCP output. After fetching, return JSON matching the schema.

Choose action=final when the user request is answered. Put a compact evidence-
grounded answer in response. Choose action=replan only when required evidence is
missing or a task failed. Put an exact description of the missing work in feedback.
Answer only requested categories. Ignore extra fetched results that are outside
the goal; never broaden a nodes-only answer into a topics answer (or vice versa).
When one tool returns multiple categories, copy only categories requested by the
goal and omit all other sections.
Treat one-line or one-item raw output as valid evidence; do not call it
incomplete merely because it contains one result.
For list or lookup requests, response must contain only the direct answer and
preserve raw values. Do not mention fetched results, task IDs, raw output,
missing lists, reprocessing, or instructions to the user.
Never invent ROS2 entities or claim an unobserved result.
"""


class RunCancelled(Exception):
    """Cooperative user cancellation."""


def _event(state: GraphState, kind: str, **data) -> list[dict]:
    return [{"kind": kind, **data}]


def _ensure_active(store: RunStore | None) -> None:
    if store is None:
        return
    if store.cancelled():
        raise RunCancelled("cancel requested by user")


def _failure_marker(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in (
        "mcp error:", "tool error:", "error executing tool", "validation error",
        "field required", "ros 2 unavailable:", "ros 2 command failed",
        "action unavailable:", "action failed:", "action uncertain:", "timed out",
    ))


def _stream_text(response: Any) -> str:
    parts: list[str] = []
    for chunk in response if not isinstance(response, str) else [response]:
        message = getattr(chunk, "message", None)
        if message is not None:
            parts.append(getattr(message, "content", "") or "")
        elif isinstance(chunk, dict):
            parts.append(chunk.get("message", {}).get("content", ""))
    return "".join(parts)


def _parse_plan(text: str, tools: list[dict]) -> list[CompilerTask]:
    """Validate typed planner JSON and convert it to scheduler tasks."""
    available = {tool["function"]["name"] for tool in tools}
    plan = ExecutionPlan.model_validate_json(text)
    if not plan.tasks:
        raise ValueError("plan contains no executable tasks")
    if len(plan.tasks) > MAX_TASKS:
        raise ValueError(f"plan exceeds maximum of {MAX_TASKS} executable tasks")
    ids = {task.id for task in plan.tasks}
    if len(ids) != len(plan.tasks):
        raise ValueError("duplicate task ID")
    tasks = []
    for item in plan.tasks:
        if item.tool not in available:
            raise ValueError(f"planner selected unknown tool `{item.tool}`")
        references = {int(value) for value in REFERENCE_PATTERN.findall(json.dumps(item.arguments))}
        dependencies = set(item.depends_on)
        if not references.issubset(dependencies):
            raise ValueError(f"task {item.id} omits referenced dependency")
        if any(dep not in ids or dep >= item.id for dep in dependencies):
            raise ValueError(f"invalid dependency for task {item.id}")
        tasks.append(CompilerTask(item.id, item.tool, item.arguments, sorted(dependencies)))
    return tasks


def _validate_arguments(task: CompilerTask, tools: list[dict], goal: str) -> None:
    schema = next(
        tool["function"].get("parameters") or {}
        for tool in tools
        if tool["function"]["name"] == task.tool
    )
    missing = set(schema.get("required", [])) - set(task.arguments)
    if missing:
        raise ValueError(f"missing arguments for `{task.tool}`: {sorted(missing)}")
    static_arguments = {
        key: value for key, value in task.arguments.items()
        if not (isinstance(value, str) and REFERENCE_PATTERN.fullmatch(value))
    }
    if static_arguments:
        try:
            validate_json(static_arguments, {**schema, "required": []})
        except JsonSchemaValidationError as error:
            raise ValueError(f"invalid arguments for `{task.tool}`: {error.message}") from error
        goal_text = goal.casefold()
        for field, value in static_arguments.items():
            if field not in RUNTIME_IDENTIFIER_FIELDS or not isinstance(value, str):
                continue
            identifier = value.strip().lstrip("/").casefold()
            if identifier and identifier not in goal_text:
                raise ValueError(
                    f"ungrounded `{field}` argument for `{task.tool}`: `{value}`; "
                    "use only identifiers stated by the user or supplied by a dependency"
                )


def _needs_user_input(error: Exception) -> bool:
    message = str(error)
    return message.startswith("missing arguments for") or message.startswith("ungrounded ")


def _validate_plan(tasks: list[CompilerTask], tools: list[dict], goal: str) -> None:
    """Preflight validator: live MCP inventory, schemas, identifiers, dependencies."""
    available = {tool["function"]["name"] for tool in tools}
    for task in tasks:
        if task.tool not in available:
            raise ValueError(f"planner selected unknown live MCP tool `{task.tool}`")
        _validate_arguments(task, tools, goal)


def _substitute(value: Any, results: dict[int, str]) -> Any:
    if isinstance(value, str):
        match = REFERENCE_PATTERN.fullmatch(value)
        if match:
            return results[int(match.group(1))]
        return REFERENCE_PATTERN.sub(lambda m: results[int(m.group(1))], value)
    if isinstance(value, list):
        return [_substitute(item, results) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, results) for key, item in value.items()}
    return value


def _task_state(task: CompilerTask, status: str, result: str | None = None) -> dict:
    return {"id": task.idx, "tool": task.tool, "arguments": task.arguments, "depends_on": task.dependencies, "status": status, "result": result}


async def _schedule(tasks: list[CompilerTask], mcp: MCPRos, store: RunStore | None = None) -> tuple[list[dict], list[dict]]:
    results: dict[int, str] = {}
    states = {task.idx: _task_state(task, "pending") for task in tasks}
    observations: list[dict] = []
    remaining = {task.idx: task for task in tasks}
    while remaining:
        _ensure_active(store)
        ready = [task for task in remaining.values() if all(dep in results for dep in task.dependencies)]
        if not ready:
            raise ValueError("task dependency deadlock")
        for task in ready:
            states[task.idx]["status"] = "running"

        async def execute(task: CompilerTask) -> tuple[CompilerTask, dict]:
            with telemetry.span("mcp.tool", **{"task.id": task.idx, "tool.name": task.tool}):
                output = await mcp.call_many([(task.tool, _substitute(task.arguments, results))])
            return task, output[0]

        completed = await asyncio.gather(*(execute(task) for task in ready))
        for task, output in completed:
            text = output["output"]
            states[task.idx]["status"] = "failed" if _failure_marker(text) else "complete"
            states[task.idx]["result"] = text
            results[task.idx] = text
            observations.append({
                "task_id": task.idx,
                "tool": task.tool,
                "output": text,
                "content_type": "text",
                "bytes": len(text.encode("utf-8")),
                "status": states[task.idx]["status"],
            })
            del remaining[task.idx]
            if store is not None:
                store.event("scheduler", "task_completed", task_id=task.idx, tool=task.tool, status=states[task.idx]["status"], bytes=len(text.encode("utf-8")))
    return [states[index] for index in sorted(states)], observations


def _catalog_context(goal: str, tools: list[dict], context: RunContext) -> tuple[str, list[dict]]:
    names = {tool["function"]["name"] for tool in tools}
    with telemetry.span("agent.rag", **{"goal.length": len(goal), "mcp.tool_count": len(names)}):
        cards = context.catalog.retrieve(goal, names, top_k=min(4, len(names)))
    if not cards:
        raise ValueError("No relevant MCP tools found in catalog.")
    selected = {card["tool"] for card in cards}
    relevant_tools = [tool for tool in tools if tool["function"]["name"] in selected]
    by_name = {tool["function"]["name"]: tool for tool in relevant_tools}
    capability_cards = []
    for card in cards:
        tool = by_name[card["tool"]]
        capability_cards.append({
            "name": card["tool"],
            "purpose": tool["function"].get("description", ""),
            "inputs": tool["function"].get("parameters", {}),
            "catalog": card["content"],
        })
    return json.dumps(capability_cards, ensure_ascii=False), relevant_tools


async def _plan_and_schedule(state: GraphState, runtime: Runtime[RunContext]) -> GraphState:
    try:
        context = runtime.context
        _ensure_active(context.store)
        tools = await context.mcp.list_tools()
        prompt = PLANNER_PROMPT
        if state.get("feedback"):
            prompt += f"\nCorrect the previous attempt using this feedback:\n{state['feedback']}\n"
        catalog_text, relevant_tools = _catalog_context(state["goal"], tools, context)
        context.store.event("rag", "capabilities_retrieved", count=len(relevant_tools), tools=[tool["function"]["name"] for tool in relevant_tools])
        prompt += "\n\nRetrieved capability cards:\n" + catalog_text
        compact_schemas = [
            {"name": tool["function"]["name"], "parameters": tool["function"].get("parameters", {})}
            for tool in relevant_tools
        ]
        prompt += "\n\nExact input schemas:\n" + json.dumps(compact_schemas, ensure_ascii=False)
        prompt += "\n\nRequired plan JSON schema:\n" + json.dumps(PLAN_SCHEMA)
        last_error: Exception | None = None
        for attempt in range(MAX_PLAN_REPAIRS):
            try:
                messages = [{"role": "system", "content": prompt}, {"role": "user", "content": state["goal"]}]
                context.store.model_call("planner", messages, model=settings["chat_model"], attempt=attempt + 1, context_tokens=settings["planner_context"])
                with telemetry.span("agent.planner", **{"model.name": settings["chat_model"], "planner.attempt": attempt + 1}):
                    response = context.ollama.chat(
                        model=settings["chat_model"],
                        messages=messages,
                        stream=True,
                        format=PLAN_SCHEMA,
                        keep_alive=0,
                        options={"temperature": 0, "num_ctx": settings["planner_context"]},
                    )
                plan_text = _stream_text(response)
                context.store.model_call("planner", {}, response=plan_text, model=settings["chat_model"], attempt=attempt + 1)
                tasks = _parse_plan(plan_text, tools)
                with telemetry.span("agent.validator", **{"plan.task_count": len(tasks), "mcp.tool_count": len(tools)}):
                    _validate_plan(tasks, tools, state["goal"])
                context.store.event("validator", "preflight_passed", task_count=len(tasks), tools=[task.tool for task in tasks])
                context.store.event("planner", "plan_validated", attempt=attempt + 1, task_count=len(tasks))
                plan = [_task_state(task, "pending") for task in tasks]
                context.store.event("planner", "plan_ready_for_approval", task_count=len(plan), plan=plan)
                return {"plan": plan, "status": "awaiting_approval", "events": _event(state, "plan_ready_for_approval", plan=plan)}
            except (ValueError, ValidationError, JsonSchemaValidationError, json.JSONDecodeError) as error:
                last_error = error
                if _needs_user_input(error):
                    return {
                        "status": "needs_input",
                        "error": f"Required user input missing. {error}",
                        "events": _event(state, "needs_input", reason=str(error)),
                    }
                prompt += (
                    "\nThe previous plan was rejected by runtime validation. "
                    f"Repair it exactly. Validation error: {error}\n"
                )
        raise ValueError(f"planner could not produce a valid plan after {MAX_PLAN_REPAIRS} attempts: {last_error}")
    except (ValueError, ValidationError, JsonSchemaValidationError, json.JSONDecodeError) as error:
        return {"status": "failed", "error": f"LLMCompiler failed: {error}", "events": _event(state, "compiler_failed", reason=str(error))}
    except RunCancelled as error:
        return {"status": "cancelled", "error": str(error), "events": _event(state, "cancelled", component="planner")}


def _evidence(state: GraphState) -> str:
    return json.dumps(state.get("observations", []), ensure_ascii=False, indent=2)


def _result_index(state: GraphState) -> str:
    return json.dumps(
        [
            {
                "task_id": item["task_id"],
                "tool": item["tool"],
                "bytes": len(item["output"].encode("utf-8")),
            }
            for item in state.get("observations", [])
        ],
        ensure_ascii=False,
    )


def _fetch_result(state: GraphState, task_id: int) -> dict:
    for item in state.get("observations", []):
        if item["task_id"] == task_id:
            # Keep execution metadata in checkpoint state, but expose only
            # stable evidence fields to the model.
            return {"task_id": item["task_id"], "tool": item["tool"], "output": item["output"]}
    raise ValueError(f"unknown task result ID `{task_id}`")


def _requested_result_ids(response: Any) -> list[int]:
    ids: list[int] = []
    for call in getattr(getattr(response, "message", None), "tool_calls", None) or []:
        function = call.function
        arguments = function.arguments
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if function.name != "fetch_task_result":
            raise ValueError(f"joiner selected unknown tool `{function.name}`")
        ids.append(int(arguments["task_id"]))
    return ids


def _answer_covers_results(answer: str, results: list[dict]) -> bool:
    """Reject joiner summaries that silently drop one fetched result."""
    normalized = answer.casefold()
    for result in results:
        lines = [line.strip() for line in result["output"].splitlines() if line.strip()]
        if lines and not any(line.casefold() in normalized for line in lines[:2]):
            return False
    return True


def _raw_result_answer(results: list[dict]) -> str:
    return "\n\n".join(
        f"[{result['tool']}]\n{result['output']}" for result in results
    )


def _join(state: GraphState, runtime: Runtime[RunContext]) -> GraphState:
    try:
        _ensure_active(runtime.context.store)
        failed = [item for item in state.get("observations", []) if item.get("status") == "failed"]
        if failed:
            reason = "; ".join(f"task {item['task_id']} ({item['tool']}): {item['output']}" for item in failed)
            if state.get("replan_count", 0) < MAX_REPLANS:
                runtime.context.store.event("joiner", "replan_after_tool_failure", reason=reason)
                return {
                    "feedback": f"Previous tool execution failed. Choose a different valid capability or request required input. Evidence: {reason}",
                    "replan_count": state.get("replan_count", 0) + 1,
                    "status": "replanning",
                    "events": _event(state, "join_replan", feedback=reason),
                }
            return {"status": "failed", "error": f"Tool execution failed after {MAX_REPLANS} replans: {reason}", "events": _event(state, "join_failed", reason=reason)}
        observations = state.get("observations", [])
        if len(observations) == 1:
            result = _fetch_result(state, observations[0]["task_id"])
            runtime.context.store.model_call(
                "joiner.answer",
                {"goal": state["goal"], "fetched_result_ids": [result["task_id"]]},
                response=result["output"],
                deterministic=True,
            )
            return {
                "answer": result["output"],
                "status": "complete",
                "events": _event(
                    state,
                    "join_final",
                    fetched_result_ids=[result["task_id"]],
                    deterministic=True,
                ),
            }
        with telemetry.span("agent.joiner.index", **{"model.name": settings["chat_model"], "result.count": len(state.get("observations", []))}):
            index_response = runtime.context.ollama.chat(
                model=settings["chat_model"],
                messages=[
                    {"role": "system", "content": JOINER_PROMPT},
                    {"role": "user", "content": f"Goal: {state['goal']}\nExact result index:\n{_result_index(state)}"},
                ],
                tools=[FETCH_RESULT_TOOL],
                keep_alive=0,
                options={"temperature": 0, "num_ctx": settings["joiner_context"]},
            )
        runtime.context.store.model_call("joiner.index", {"goal": state["goal"], "result_index": _result_index(state)}, model=settings["chat_model"], context_tokens=settings["joiner_context"])
        requested = _requested_result_ids(index_response)
        # If the small local model does not issue a fetch call, fetch every
        # indexed result deterministically; no evidence is summarized or lost.
        ids = requested or [item["task_id"] for item in state.get("observations", [])]
        exact_results = [_fetch_result(state, task_id) for task_id in dict.fromkeys(ids)]
        fetched_ids = [item["task_id"] for item in exact_results]
        final_messages = [
            {"role": "system", "content": JOINER_PROMPT},
            {"role": "user", "content": f"Goal: {state['goal']}\nFetched exact raw results:\n{json.dumps(exact_results, ensure_ascii=False, indent=2)}"},
        ]
        runtime.context.store.model_call("joiner.answer", final_messages, model=settings["chat_model"], context_tokens=settings["joiner_context"])
        with telemetry.span("agent.joiner.answer", **{"model.name": settings["chat_model"], "result.count": len(exact_results)}):
            response = runtime.context.ollama.chat(
                model=settings["chat_model"],
                messages=final_messages,
                format=JOIN_SCHEMA,
                keep_alive=0,
                options={"temperature": 0, "num_ctx": settings["joiner_context"]},
            )
        runtime.context.store.model_call("joiner.answer", {}, response=getattr(response.message, "content", ""), model=settings["chat_model"])
        decision = JoinDecision.model_validate_json(response.message.content or "")
        if decision.action == "replan" and state.get("replan_count", 0) < MAX_REPLANS:
            return {"feedback": decision.feedback, "replan_count": state.get("replan_count", 0) + 1, "status": "replanning", "events": _event(state, "join_replan", feedback=decision.feedback, fetched_result_ids=fetched_ids)}
        if decision.action == "replan":
            return {"status": "failed", "error": f"Joiner could not complete goal: {decision.feedback}"}
        if not _answer_covers_results(decision.response, exact_results):
            fallback = _raw_result_answer(exact_results)
            runtime.context.store.event("joiner", "coverage_fallback", fetched_result_ids=fetched_ids)
            return {"answer": fallback, "status": "complete", "events": _event(state, "join_final", fetched_result_ids=fetched_ids, deterministic=True, coverage_fallback=True)}
        return {"answer": decision.response, "status": "complete", "events": _event(state, "join_final", fetched_result_ids=fetched_ids)}
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        return {"status": "failed", "error": f"Joiner failed: {error}", "events": _event(state, "join_failed", reason=str(error))}
    except RunCancelled as error:
        return {"status": "cancelled", "error": str(error), "events": _event(state, "cancelled", component="joiner")}


def _route_after_compile(state: GraphState) -> str:
    return "finish" if state.get("status") in {"failed", "needs_input", "cancelled"} else "approval"


def _approval(state: GraphState, runtime: Runtime[RunContext]) -> GraphState:
    try:
        _ensure_active(runtime.context.store)
        with telemetry.span("agent.approval", **{"run.name": state["run_name"]}):
            decision = interrupt({
                "type": "plan_approval",
                "run_name": state["run_name"],
                "goal": state["goal"],
                "plan": state.get("plan", []),
            })
        if not isinstance(decision, dict):
            raise ValueError("approval response must be an object")
        action = str(decision.get("action", "")).lower()
        if action == "approve":
            runtime.context.store.event("approval", "approved", plan=state.get("plan", []))
            return {"approved": True, "status": "approved", "events": _event(state, "plan_approved")}
        if action == "revise":
            feedback = str(decision.get("feedback", "")).strip()
            if not feedback:
                raise ValueError("revision feedback is required")
            runtime.context.store.event("approval", "revision_requested", feedback=feedback)
            return {"approved": False, "feedback": feedback, "status": "replanning", "events": _event(state, "plan_revision_requested", feedback=feedback)}
        if action in {"cancel", "reject"}:
            runtime.context.store.event("approval", "rejected")
            return {"status": "cancelled", "error": "Plan rejected by user.", "events": _event(state, "plan_rejected")}
        raise ValueError("approval action must be approve, revise, or cancel")
    except RunCancelled as error:
        return {"status": "cancelled", "error": str(error), "events": _event(state, "cancelled", component="approval")}


async def _execute_plan(state: GraphState, runtime: Runtime[RunContext]) -> GraphState:
    try:
        _ensure_active(runtime.context.store)
        tasks = [
            CompilerTask(item["id"], item["tool"], item.get("arguments", {}), item.get("depends_on", []))
            for item in state.get("plan", [])
        ]
        plan, observations = await _schedule(tasks, runtime.context.mcp, runtime.context.store)
        return {"plan": plan, "observations": observations, "status": "running", "events": _event(state, "plan_executed", plan=plan)}
    except RunCancelled as error:
        return {"status": "cancelled", "error": str(error), "events": _event(state, "cancelled", component="executor")}


def _route_after_join(state: GraphState) -> str:
    return "plan_and_schedule" if state.get("status") == "replanning" else "finish"


def _build_graph(state_path: Path):
    builder = StateGraph(GraphState, context_schema=RunContext)
    builder.add_node("plan_and_schedule", _plan_and_schedule, retry_policy=RetryPolicy(initial_interval=0.2, max_attempts=2))
    builder.add_node("approval", _approval)
    builder.add_node("execute_plan", _execute_plan)
    builder.add_node("join", _join)
    builder.add_node("finish", lambda state: {})
    builder.add_edge(START, "plan_and_schedule")
    builder.add_conditional_edges("plan_and_schedule", _route_after_compile, {"approval": "approval", "finish": "finish"})
    builder.add_conditional_edges("approval", lambda state: "execute" if state.get("status") == "approved" else ("plan" if state.get("status") == "replanning" else "finish"), {"execute": "execute_plan", "plan": "plan_and_schedule", "finish": "finish"})
    builder.add_edge("execute_plan", "join")
    builder.add_conditional_edges("join", _route_after_join, {"plan_and_schedule": "plan_and_schedule", "finish": "finish"})
    builder.add_edge("finish", END)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    return builder, state_path


def _agent_state(result: dict, command: str, run_name: str) -> AgentState:
    state = AgentState(task=command, run_name=run_name, max_steps=MAX_TASKS)
    state.tasks = result.get("plan", [])
    state.current_step = len([task for task in state.tasks if task["status"] in {"complete", "failed"}])
    state.observations = result.get("observations", [])
    state.tool_calls = len(state.observations)
    state.steps = result.get("events", [])
    state.phase = result.get("status", "failed")
    state.status = result.get("status", "failed")
    state.answer = result.get("answer") or result.get("error") or "No answer."
    state.failure_reason = result.get("error")
    state.verification = "Task results supplied to joiner." if state.tasks else result.get("error")
    return state


async def _invoke_run(run_name: str, command: str | None = None, resume: dict | None = None) -> AgentState:
    telemetry.require_available()
    with telemetry.span("agent.run", **{"run.name": safe_name(run_name), "goal.length": len(command or "") or None}):
        return await _invoke_run_inner(run_name, command=command, resume=resume)


async def _invoke_run_inner(run_name: str, command: str | None = None, resume: dict | None = None) -> AgentState:
    name = safe_name(run_name)
    root = Path(settings["run_dir"])
    store = RunStore(root, name, command or "", existing=command is None)
    if resume is not None and store.status in {"complete", "failed", "cancelled", "needs_input"}:
        raise ValueError(f"session `{name}` is finished; start a new named session")
    mcp = MCPRos()
    builder, state_path = _build_graph(store.state_path)
    result: dict = {"status": "failed", "error": "run did not reach graph execution"}
    try:
        async with mcp:
            context = RunContext(mcp=mcp, catalog=catalog, ollama=ollama, store=store)
            store.event("observability", "trace_started", trace_id=telemetry.current_trace_id(), phoenix_url=telemetry.PHOENIX_UI, project=telemetry.PHOENIX_PROJECT)
            async with _state_checkpointer(state_path) as checkpointer:
                graph = builder.compile(checkpointer=checkpointer)
                try:
                    config = {"configurable": {"thread_id": name}}
                    if resume is None:
                        result = await graph.ainvoke(
                            {"run_name": name, "goal": command, "feedback": None, "replan_count": 0, "events": []},
                            config=config,
                            context=context,
                        )
                    else:
                        result = await graph.ainvoke(Command(resume=resume), config=config, context=context)
                except Exception as error:
                    result = {"status": "failed", "error": f"Graph execution failed: {error}"}
    except Exception as error:
        result = {"status": "failed", "error": f"Run setup failed: {error}"}
    if result.get("status") in {"awaiting_approval", "approved", "replanning"}:
        store.checkpoint(result, result["status"])
    else:
        store.finalize(result)
    return _agent_state(result, command, name)


async def _run_with_state(command: str, run_name: str) -> AgentState:
    """Generate and validate plan, then pause for explicit approval."""
    return await _invoke_run(run_name, command=command)


def run_with_state(command: str, run_name: str) -> AgentState:
    return asyncio.run(_run_with_state(command, run_name))


def start_run(command: str, run_name: str) -> AgentState:
    """Create plan and pause before execution for explicit user approval."""
    return asyncio.run(_invoke_run(run_name, command=command))


def resume_run(run_name: str, *, approve: bool | None = None, feedback: str | None = None) -> AgentState:
    """Resume paused run with approval, revision feedback, or cancellation."""
    if approve is True:
        decision = {"action": "approve"}
    elif approve is False:
        decision = {"action": "cancel"}
    elif feedback:
        decision = {"action": "revise", "feedback": feedback}
    else:
        raise ValueError("resume requires approve=True/False or feedback")
    return asyncio.run(_invoke_run(run_name, resume=decision))


def run(command: str, run_name: str) -> str:
    return run_with_state(command, run_name).answer or "No answer."


def cancel(run_name: str) -> Path:
    """Request cooperative stop for an active named run."""
    return request_cancel(Path(settings["run_dir"]), run_name)
