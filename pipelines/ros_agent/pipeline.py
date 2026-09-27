"""Goal-oriented ROS2 agent pipeline."""

import json
import re

from ollama import Client, ResponseError

from .config import settings
from .mcp_client import MCPRos
from .state import AgentState


MAX_STEPS = 8
ollama = Client(host=settings["ollama_host"], timeout=20)
ROS_SCOPE = re.compile(
    r"\b(?:ros|ros2|ros\s*2|node|topic|service|action|publisher|subscriber|"
    r"message|interface|rclpy|rclcpp|dds|qos|launch|parameter|namespace|"
    r"callback|executor|spin|demo|docker|colima|[a-zA-Z0-9_]+_node)\b",
    re.IGNORECASE,
)


SYSTEM_PROMPT = """You are a goal-oriented ROS 2 graph agent.
Turn user request into a small plan, use MCP tools, inspect each result, and continue
until goal is verified or impossible.
Answer only using observed MCP results.
Do not use external knowledge. If ROS2 evidence is missing, say it is unavailable.
Use ROS inspection tools for ROS 2 questions: list_ros_nodes, list_ros_topics,
list_ros_services, list_ros_actions, ros_node_info, ros_topic_info,
ros_service_info, ros_action_info, ros_system_snapshot, start_ros_demo_node,
stop_ros_demo_node, and ros2_runtime_status.
Actions are allowed only through named MCP tools. Never invent successful actions.
After every action, verify its result with an inspection tool or tool's verification output.
If a tool says unavailable, failed, uncertain, or timed out, report exact reason and stop.
Never invent paths or file contents.
After each tool result, verify that observed output answers the request.
If output is incomplete, call another tool.
Never claim goal completion without observed verification.
Give concise answers with ROS2 names and observed values.
"""


def _run_tool(mcp, name, arguments):
    try:
        return mcp.call(name, arguments)
    except (TypeError, ValueError, OSError, RuntimeError) as error:
        return f"Tool error: {error}"


def _initial_observation(command: str, mcp):
    """Handle clear ROS2 intents before model planning."""
    if _is_ros2_scope(command):
        if re.search(r"\b(?:start|launch|run)\b.*\b(?:demo|node)\b", command, re.IGNORECASE):
            return "start_ros_demo_node", _run_tool(mcp, "start_ros_demo_node", {})
        if re.search(r"\b(?:stop|kill)\b.*\b(?:demo|node)\b", command, re.IGNORECASE):
            return "stop_ros_demo_node", _run_tool(mcp, "stop_ros_demo_node", {})
        node_match = re.search(r"(?:inspect|info|details? on|about)\s+([/a-zA-Z0-9_.-]+)", command, re.IGNORECASE)
        if node_match and "topic" not in command.lower() and "service" not in command.lower():
            return "ros_node_info", _run_tool(mcp, "ros_node_info", {"node": node_match.group(1)})
        topic_match = re.search(r"(?:inspect|info|details? on|about)\s+(?:topic\s+)?([/a-zA-Z0-9_.-]+)", command, re.IGNORECASE)
        if "topic" in command.lower() and topic_match:
            return "ros_topic_info", _run_tool(mcp, "ros_topic_info", {"topic": topic_match.group(1)})
        service_match = re.search(r"(?:inspect|info|details? on|about)\s+(?:service\s+)?([/a-zA-Z0-9_.-]+)", command, re.IGNORECASE)
        if "service" in command.lower() and service_match:
            return "ros_service_info", _run_tool(mcp, "ros_service_info", {"service": service_match.group(1)})
        if re.search(r"snapshot|everything|ros graph", command, re.IGNORECASE):
            return "ros_system_snapshot", _run_tool(mcp, "ros_system_snapshot", {})
        if re.search(r"\b(?:status|setup|health|available|installed|prerequisite|requirements?)\b", command, re.IGNORECASE):
            return "ros2_runtime_status", _run_tool(mcp, "ros2_runtime_status", {})
        list_intent = re.search(r"\b(?:list|show|give|check|what\s+(?:are|is))\b", command, re.IGNORECASE)
        if re.search(r"action", command, re.IGNORECASE) and list_intent:
            return "list_ros_actions", _run_tool(mcp, "list_ros_actions", {})
        if re.search(r"node", command, re.IGNORECASE) and list_intent:
            return "list_ros_nodes", _run_tool(mcp, "list_ros_nodes", {})
        if re.search(r"topic", command, re.IGNORECASE) and list_intent:
            return "list_ros_topics", _run_tool(mcp, "list_ros_topics", {})
        if re.search(r"service", command, re.IGNORECASE) and list_intent:
            return "list_ros_services", _run_tool(mcp, "list_ros_services", {})

    return None


def _failed_observation(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in (
        "tool error:",
        "ros 2 unavailable:",
        "action unavailable:",
        "action failed:",
        "action uncertain:",
        "timed out",
    ))


def _is_ros2_scope(command: str) -> bool:
    """Reject unrelated requests before model/tool planning."""
    return bool(ROS_SCOPE.search(command))


def run_with_state(command: str) -> AgentState:
    """Run command and return complete execution state."""
    state = AgentState(task=command, max_steps=MAX_STEPS)
    if not _is_ros2_scope(command):
        state.fail(
            "Cannot complete: request is outside this agent's scope. "
            "This agent only handles ROS2 nodes, topics, services, actions, "
            "parameters, QoS, and graph inspection."
        )
        return state

    state.record("plan", action="discover ROS2 tools through MCP")
    mcp = MCPRos()
    try:
        mcp_tools = mcp.list_tools()
    except Exception as error:
        state.fail(f"Cannot complete: ROS2 MCP server unavailable: {error}")
        return state
    state.record("tools_ready", tools=[tool["function"]["name"] for tool in mcp_tools])

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {"role": "user", "content": command},
    ]

    observation = _initial_observation(command, mcp)
    if observation:
        tool_name, result = observation
        state.observe(tool_name, result)
        passed = bool(result.strip()) and not _failed_observation(result)
        state.verify(passed, f"Direct MCP result answers deterministic `{tool_name}` request.")
        if passed:
            state.finish(f"Verified tool output from `{tool_name}`:\n{result}")
        else:
            state.fail(f"Goal not achieved: {result}")
        return state

    state.phase = "executing"
    for step in range(MAX_STEPS):
        state.current_step = step + 1
        state.record("model_step", step=step + 1)
        try:
            response = ollama.chat(
                model=settings["chat_model"],
                messages=messages,
                tools=mcp_tools,
                options={"temperature": 0},
            )
        except (ConnectionError, ResponseError, OSError) as error:
            state.fail(
                "Cannot complete: Ollama unavailable. Start Ollama and run: "
                f"ollama pull {settings['chat_model']}. Details: {error}"
            )
            return state

        message = response.message
        messages.append(message)
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            content = (message.content or "").strip()
            if content:
                failed = any(_failed_observation(item["output"]) for item in state.observations)
                state.verify(
                    bool(state.observations) and not failed,
                    "Final answer follows verified MCP observations." if not failed
                    else "Tool observation reports an unavailable or failed operation.",
                )
                if state.observations and not failed:
                    state.finish(content)
                else:
                    state.fail(
                        state.verification
                        or "No MCP evidence collected; goal cannot be verified."
                    )
                return state
            state.fail("Model returned no answer.")
            return state

        for tool_call in tool_calls:
            name = tool_call.function.name
            arguments = tool_call.function.arguments
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as error:
                    state.fail(f"Cannot complete: model produced invalid tool arguments: {error}")
                    return state
            output = _run_tool(mcp, name, arguments)
            state.observe(name, output)
            messages.append({"role": "tool", "content": output})

    state.fail(f"Goal not achieved after {MAX_STEPS} reasoning steps; verification incomplete.")
    return state


def run(command: str) -> str:
    """Run command and return final answer text."""
    return run_with_state(command).answer or "No answer."
