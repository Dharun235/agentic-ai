# ROS 2 agent tool catalog

Agent scope: ROS 2 graph discovery and one safe demo-node lifecycle. No robot behavior.

The MCP server runs beside ROS 2 and exposes tools over Streamable HTTP when
needed. Tools call the live `ros2` CLI; they do not use a cached graph.

The catalog is the agent's tool map. Chroma and Ollama embeddings retrieve relevant
guidance and candidate MCP schemas for the LLMCompiler planner. The planner emits
an executable DAG; the scheduler executes exact assigned tools and saves raw task
results before the joiner answers. Catalog text describes tool choice; MCP output
supplies live ROS2 truth. Runtime ROS2 facts are never embedded or cached here.

## Read-only graph tools

- `list_ros_nodes`: discovered node names.
- `ros_node_info(node)`: publishers, subscribers, services, clients, actions for node.
- `list_ros_topics`: discovered topic names and types when reported by ROS CLI.
- `ros_topic_info(topic)`: topic type and publisher/subscriber counts.
- `list_ros_services`: discovered service names and types.
- `ros_service_info(service)`: service type.
- `list_ros_actions`: discovered action names and types.
- `ros_action_info(action)`: action servers/clients and type.
- `ros_system_snapshot`: nodes, topics, services, actions in one observation.
- `ros2_runtime_status`: whether the native host ROS2 CLI is available.

## Extended inspection tools

Parameter tools: `list_node_parameters(node)`, `get_node_parameter(node, name)`,
`get_node_parameters(node)`, `describe_node_parameters(node)`, and
`use_sim_time_status(node)`.

Topic runtime tools: `ros_topic_echo(topic, message_count)`,
`ros_topic_hz(topic)`, `ros_topic_bw(topic)`, and `ros_topic_type(topic)`.
Echo is bounded to ten one-shot messages maximum.

Interface tools: `ros_message_info(type)`, `ros_service_definition(type)`, and
`ros_action_definition(type)`.

Graph tools: `ros_node_graph(node)`, `find_topic_publishers(topic)`,
`find_topic_subscribers(topic)`, `find_unconnected_topics()`, and
`ros_graph_snapshot()`.

TF2 tools: `list_tf_frames()`, `tf_frame_info(frame)`,
`tf_transform(source, target)`, and `tf_tree_snapshot()`.

Runtime tools: `list_processes()`, `list_ros_daemons()`, `ros_domain_id()`,
`ros_environment_status()`, and `inspect_launch_processes()`.

Diagnostics: `list_diagnostics()`, `get_diagnostic_status()`,
`check_node_health(node)`, and `check_topic_health(topic)`.

Time tools: `ros_time_status()` and `clock_topic_status()`.
`use_sim_time_status(node)` requires a concrete node named by the user or
returned by an earlier task; never invent a node name. If no node is named,
use the node-independent time tools only.

All inspection commands have bounded execution. Runtime actions remain limited
to the explicitly supported demo-node lifecycle tools.
