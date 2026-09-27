# ROS 2 agent tool catalog

Agent scope: ROS 2 graph discovery and one safe demo-node lifecycle. No robot behavior.

Server runs over MCP stdio. Client starts this server; tools call live `ros2` commands on host or in `ROS2_DOCKER_CONTAINER`. No RAG or cached knowledge is involved.

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
- `ros2_runtime_status`: whether host/container `ros2`, Docker, and configured container are available.

## Safe demo lifecycle

- `start_ros_demo_node`: starts configured `ROS2_DOCKER_CONTAINER`, then verifies `/ros_agent_demo_node`.
- `stop_ros_demo_node`: stops configured demo container, then verifies node disappears.

Every action returns observed verification. If ROS2 or container config is unavailable, agent reports exact reason.
