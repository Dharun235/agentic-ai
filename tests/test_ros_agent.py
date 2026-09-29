import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from pipelines.ros_agent import resume_run, start_run
from pipelines.ros_agent.pipeline import _parse_plan, _schedule


def run_test(command):
    run_name = f"test-{uuid.uuid4().hex}"
    state = start_run(command, run_name)
    while state.status == "awaiting_approval":
        state = resume_run(run_name, approve=True)
    return state


TOOLS = [
    {"function": {"name": "list_ros_nodes", "description": "List ROS2 nodes", "parameters": {}}},
    {"function": {"name": "list_ros_topics", "description": "List ROS2 topics", "parameters": {}}},
    {
        "function": {
            "name": "ros_topic_info",
            "description": "Inspect one topic",
            "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        }
    },
]


class FakeMCP:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def list_tools(self):
        return TOOLS

    async def call_many(self, calls):
        outputs = []
        for name, arguments in calls:
            if name == "list_ros_nodes":
                output = "/ros_agent_demo_node"
            elif name == "list_ros_topics":
                output = "/parameter_events\n/rosout"
            elif name == "ros_topic_info":
                output = f"type for {arguments['topic']}"
            else:
                output = f"Tool error: {name}"
            outputs.append({"tool": name, "output": output})
        return outputs


def streamed(content):
    return [SimpleNamespace(message=SimpleNamespace(content=content))]


def response(content):
    return SimpleNamespace(message=SimpleNamespace(content=content))


def cards_for(query, *_args, **_kwargs):
    return [{"tool": tool["function"]["name"], "content": tool["function"]["description"], "distance": 0.1} for tool in TOOLS]


def test_parser_derives_dependencies_and_requires_join():
    tasks = _parse_plan(
        '{"tasks":[{"id":1,"tool":"list_ros_topics","arguments":{},"depends_on":[]},{"id":2,"tool":"ros_topic_info","arguments":{"topic":"$1"},"depends_on":[1]}]}',
        TOOLS,
    )
    assert [(task.idx, task.tool, task.dependencies) for task in tasks] == [
        (1, "list_ros_topics", []),
        (2, "ros_topic_info", [1]),
    ]


def test_scheduler_substitutes_results_before_dependent_execution():
    tasks = _parse_plan(
        '{"tasks":[{"id":1,"tool":"list_ros_topics","arguments":{},"depends_on":[]},{"id":2,"tool":"ros_topic_info","arguments":{"topic":"$1"},"depends_on":[1]}]}',
        TOOLS,
    )
    states, observations = asyncio.run(_schedule(tasks, FakeMCP()))
    assert [state["status"] for state in states] == ["complete", "complete"]
    assert observations[1]["output"] == "type for /parameter_events\n/rosout"


def test_llmcompiler_runs_independent_tasks_then_joiner():
    planner = '{"tasks":[{"id":1,"tool":"list_ros_nodes","arguments":{},"depends_on":[]},{"id":2,"tool":"list_ros_topics","arguments":{},"depends_on":[]}]} '
    joiner = '{"action":"final","response":"Nodes: /ros_agent_demo_node; Topics: /parameter_events, /rosout","feedback":""}'
    with (
        patch("pipelines.ros_agent.pipeline.MCPRos", FakeMCP),
        patch("pipelines.ros_agent.pipeline.catalog.retrieve", side_effect=cards_for),
        patch("pipelines.ros_agent.pipeline.ollama.chat", side_effect=[streamed(planner), response(joiner), response(joiner)]),
    ):
        state = run_test("Check which ROS2 nodes and topics are present.")
    assert state.status == "complete"
    assert {item["tool"] for item in state.observations} == {"list_ros_nodes", "list_ros_topics"}
    assert "Nodes:" in state.answer


def test_joiner_replans_with_bounded_feedback():
    planner = '{"tasks":[{"id":1,"tool":"list_ros_nodes","arguments":{},"depends_on":[]},{"id":2,"tool":"list_ros_topics","arguments":{},"depends_on":[]}]} '
    replan = '{"action":"replan","response":"","feedback":"The topic list is missing."}'
    corrected_planner = '{"tasks":[{"id":1,"tool":"list_ros_topics","arguments":{},"depends_on":[]},{"id":2,"tool":"list_ros_nodes","arguments":{},"depends_on":[]}]} '
    final = '{"action":"final","response":"Topics observed.","feedback":""}'
    with (
        patch("pipelines.ros_agent.pipeline.MCPRos", FakeMCP),
        patch("pipelines.ros_agent.pipeline.catalog.retrieve", side_effect=cards_for),
        patch(
            "pipelines.ros_agent.pipeline.ollama.chat",
            side_effect=[streamed(planner), response(replan), response(replan), streamed(corrected_planner), response(final), response(final)],
        ),
    ):
        state = run_test("Show nodes and topics.")
    assert state.status == "complete"
    assert "/parameter_events" in state.answer
    assert "/ros_agent_demo_node" in state.answer


def test_out_of_scope_request_fails_before_planning():
    with (
        patch("pipelines.ros_agent.pipeline.MCPRos", FakeMCP),
        patch("pipelines.ros_agent.pipeline.catalog.retrieve", return_value=[]),
        patch("pipelines.ros_agent.pipeline.ollama.chat") as chat,
    ):
        state = run_test("What is the weather?")
    assert state.status == "failed"
    assert "No relevant MCP tools" in state.answer
    chat.assert_not_called()


def test_plan_pauses_for_approval_before_mcp_execution():
    planner = '{"tasks":[{"id":1,"tool":"list_ros_nodes","arguments":{},"depends_on":[]}]} '
    joiner = '{"action":"final","response":"/ros_agent_demo_node","feedback":""}'
    run_name = f"test-approval-{uuid.uuid4().hex}"
    with (
        patch("pipelines.ros_agent.pipeline.MCPRos", FakeMCP),
        patch("pipelines.ros_agent.pipeline.catalog.retrieve", side_effect=cards_for),
        patch("pipelines.ros_agent.pipeline.ollama.chat", side_effect=[streamed(planner), response(joiner), response(joiner)]),
    ):
        planned = start_run("List ROS2 nodes.", run_name)
        assert planned.status == "awaiting_approval"
        assert planned.observations == []
        assert planned.tasks[0]["tool"] == "list_ros_nodes"
        completed = resume_run(run_name, approve=True)
    assert completed.status == "complete"
    assert completed.answer == "/ros_agent_demo_node"


def test_plan_revision_returns_to_planner_before_execution():
    planner = '{"tasks":[{"id":1,"tool":"list_ros_nodes","arguments":{},"depends_on":[]}]} '
    joiner = '{"action":"final","response":"/ros_agent_demo_node","feedback":""}'
    run_name = f"test-revision-{uuid.uuid4().hex}"
    with (
        patch("pipelines.ros_agent.pipeline.MCPRos", FakeMCP),
        patch("pipelines.ros_agent.pipeline.catalog.retrieve", side_effect=cards_for),
        patch("pipelines.ros_agent.pipeline.ollama.chat", side_effect=[streamed(planner), streamed(planner), response(joiner), response(joiner)]),
    ):
        planned = start_run("List ROS2 nodes.", run_name)
        revised = resume_run(run_name, feedback="Use the node listing tool.")
        assert revised.status == "awaiting_approval"
        assert revised.observations == []
        completed = resume_run(run_name, approve=True)
    assert completed.status == "complete"
