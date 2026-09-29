import asyncio
from unittest.mock import patch

from pipelines.ros import tools
from pipelines.ros_agent.mcp_client import MCPRos
from pipelines.ros_agent.catalog import ToolCatalog


REQUESTED_TOOLS = {
    "list_node_parameters", "get_node_parameter", "get_node_parameters",
    "describe_node_parameters", "ros_topic_echo", "ros_topic_hz", "ros_topic_bw",
    "ros_topic_type", "ros_message_info", "ros_service_definition",
    "ros_action_definition", "ros_node_graph", "find_topic_publishers",
    "find_topic_subscribers", "find_unconnected_topics", "ros_graph_snapshot",
    "list_tf_frames", "tf_frame_info", "tf_transform", "tf_tree_snapshot",
    "list_processes", "list_ros_daemons", "ros_domain_id", "ros_environment_status",
    "inspect_launch_processes", "list_diagnostics", "get_diagnostic_status",
    "check_node_health", "check_topic_health", "ros_time_status", "clock_topic_status",
    "use_sim_time_status",
}


def test_mcp_exposes_all_requested_tools():
    async def discover():
        async with MCPRos() as mcp:
            return await mcp.list_tools()

    actual = {item["function"]["name"] for item in asyncio.run(discover())}
    assert REQUESTED_TOOLS <= actual


def test_mcp_client_uses_http_when_configured_and_stdio_otherwise():
    with patch.dict("os.environ", {"ROS_MCP_URL": "http://localhost:8001/mcp"}, clear=False):
        with patch("pipelines.ros_agent.mcp_client.settings", {"ros_mcp_url": "http://localhost:8001/mcp"}):
            remote = MCPRos()
    assert remote.transport == "streamable-http"
    assert remote.endpoint == "http://localhost:8001/mcp"

    with patch("pipelines.ros_agent.mcp_client.settings", {"ros_mcp_url": ""}):
        local = MCPRos()
    assert local.transport == "stdio"
    assert local.server is not None


def test_catalog_parser_creates_tool_cards_without_embedding_placeholders(tmp_path):
    path = tmp_path / "catalog.md"
    path.write_text(
        "# Topics\n\n- `ros_topic_type(topic)`: Return topic type.\n"
        "- `ROS_AGENT_CONFIG`: config only.\n",
        encoding="utf-8",
    )
    cards = ToolCatalog(path=path)._cards()
    assert [card["tool"] for card in cards] == ["ros_topic_type"]
    assert "Return topic type" in cards[0]["content"]


def test_parameter_tools_use_ros2_param_commands():
    with patch.object(tools, "run_ros2", return_value="ok") as run:
        tools.list_node_parameters("demo")
        tools.get_node_parameter("demo", "use_sim_time")
        tools.get_node_parameters("demo")
        with patch.object(tools, "list_node_parameters", return_value="use_sim_time"):
            tools.describe_node_parameters("demo")
    assert run.call_args_list[0].args[0] == ["param", "list", "/demo"]
    assert run.call_args_list[1].args[0] == ["param", "get", "/demo", "use_sim_time"]
    assert run.call_args_list[2].args[0] == ["param", "dump", "/demo"]
    assert run.call_args_list[3].args[0] == ["param", "describe", "/demo", "use_sim_time"]


def test_topic_echo_is_bounded_and_caps_message_count():
    with patch.object(tools, "run_ros2", return_value="message") as run:
        result = tools.ros_topic_echo("chatter", 99)
    assert result.split("\n--- message boundary ---\n").count("message") == 10
    assert run.call_count == 10
    assert all(call.args[0] == ["topic", "echo", "/chatter", "--once"] for call in run.call_args_list)


def test_interface_graph_and_runtime_tools_are_wired_to_expected_adapters():
    with patch.object(tools, "run_ros2", return_value="ok") as run:
        tools.ros_message_info("std_msgs/msg/String")
        tools.ros_service_definition("example_interfaces/srv/AddTwoInts")
        tools.ros_action_definition("example_interfaces/action/Fibonacci")
        tools.ros_topic_type("chatter")
        tools.find_topic_publishers("chatter")
        tools.find_topic_subscribers("chatter")
    assert run.call_args_list[0].args[0] == ["interface", "show", "std_msgs/msg/String"]
    assert run.call_args_list[1].args[0] == ["interface", "show", "example_interfaces/srv/AddTwoInts"]
    assert run.call_args_list[2].args[0] == ["interface", "show", "example_interfaces/action/Fibonacci"]
    assert run.call_args_list[3].args[0] == ["topic", "type", "/chatter"]
    assert run.call_args_list[4].args[0] == ["topic", "info", "/chatter", "--verbose"]


def test_environment_tools_do_not_require_ros_runtime():
    with patch.dict("os.environ", {"ROS_DOMAIN_ID": "42"}, clear=False):
        assert tools.ros_domain_id() == "ROS_DOMAIN_ID: 42"
        assert "ROS_DOMAIN_ID: 42" in tools.ros_environment_status()


def test_health_and_sim_time_tools_return_observed_output():
    with patch.object(tools, "list_nodes", return_value="/demo"), patch.object(
        tools, "node_info", return_value="node info"
    ):
        assert "Node present: /demo" in tools.check_node_health("demo")
    with patch.object(tools, "get_node_parameter", return_value="Boolean value is: True"):
        assert tools.use_sim_time_status("demo") == "Boolean value is: True"
