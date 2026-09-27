"""Minimal ROS 2 node used for smoke testing the MCP tools."""

import rclpy
from rclpy.node import Node


class AgenticDemoNode(Node):
    def __init__(self):
        super().__init__("agentic_demo_node")
        self.timer = self.create_timer(2.0, self._tick)

    def _tick(self):
        self.get_logger().info("agentic ROS 2 demo node alive")


def main():
    rclpy.init()
    node = AgenticDemoNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

