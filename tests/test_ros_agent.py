from unittest.mock import patch

from pipelines.ros_agent import run_with_state


TOOLS = [
    {"function": {"name": name}}
    for name in (
        "list_ros_nodes",
        "list_ros_topics",
        "list_ros_services",
        "list_ros_actions",
        "ros_node_info",
        "ros_topic_info",
        "ros_service_info",
        "ros_action_info",
        "ros_system_snapshot",
        "ros2_runtime_status",
        "start_ros_demo_node",
        "stop_ros_demo_node",
    )
]


class FakeMCP:
    calls = []

    def list_tools(self):
        return TOOLS

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {
            "list_ros_nodes": "/ros_agent_demo_node",
            "list_ros_topics": "/rosout",
            "list_ros_services": "/ros_agent_demo_node/get_parameters",
            "list_ros_actions": "No ROS 2 objects found.",
            "ros_node_info": "/ros_agent_demo_node\n  Publishers: /rosout",
            "ros_topic_info": "Type: rcl_interfaces/msg/Log",
            "ros_service_info": "rcl_interfaces/srv/GetParameters",
            "ros_action_info": "No ROS 2 objects found.",
            "ros_system_snapshot": "NODES:\n/ros_agent_demo_node",
            "ros2_runtime_status": "container_ros2: available",
            "start_ros_demo_node": "Action verified: demo node is running.",
            "stop_ros_demo_node": "Action verified: demo node is stopped.",
        }[name]


def test_supported_ros_requests_route_to_expected_tools():
    cases = {
        "check ROS2 and give all nodes": "list_ros_nodes",
        "show all ROS2 topics": "list_ros_topics",
        "show all ROS2 services": "list_ros_services",
        "show all ROS2 actions": "list_ros_actions",
        "inspect ros_agent_demo_node": "ros_node_info",
        "inspect topic /rosout": "ros_topic_info",
        "check ROS2 setup": "ros2_runtime_status",
        "start the ROS2 demo node": "start_ros_demo_node",
        "stop the ROS2 demo node": "stop_ros_demo_node",
    }
    for request, expected_tool in cases.items():
        FakeMCP.calls = []
        with patch("pipelines.ros_agent.pipeline.MCPRos", FakeMCP):
            state = run_with_state(request)
        assert state.status == "complete"
        assert state.observations[-1]["tool"] == expected_tool


def test_non_ros_request_is_rejected_before_mcp():
    with patch("pipelines.ros_agent.pipeline.MCPRos") as mcp:
        state = run_with_state("list files in this repository")
    assert state.status == "failed"
    assert "outside this agent's scope" in state.answer
    mcp.assert_not_called()


def test_failed_tool_result_is_not_reported_as_success():
    class FailedMCP(FakeMCP):
        def call(self, name, arguments):
            return "Action unavailable: ROS2_DOCKER_CONTAINER is not configured."

    with patch("pipelines.ros_agent.pipeline.MCPRos", FailedMCP):
        state = run_with_state("start the ROS2 demo node")
    assert state.status == "failed"
    assert "not configured" in state.answer


def test_mcp_startup_failure_becomes_pipeline_failure():
    class BrokenMCP:
        def list_tools(self):
            raise OSError("MCP process could not start")

    with patch("pipelines.ros_agent.pipeline.MCPRos", BrokenMCP):
        state = run_with_state("check ROS2 setup")
    assert state.status == "failed"
    assert "MCP server unavailable" in state.answer


def test_ollama_failure_becomes_pipeline_failure():
    class PlanningMCP(FakeMCP):
        def call(self, name, arguments):
            return "No direct result"

    with (
        patch("pipelines.ros_agent.pipeline.MCPRos", PlanningMCP),
        patch("pipelines.ros_agent.pipeline.ollama.chat", side_effect=ConnectionError("offline")),
    ):
        state = run_with_state("which ROS2 nodes publish diagnostic messages?")
    assert state.status == "failed"
    assert "Ollama unavailable" in state.answer
