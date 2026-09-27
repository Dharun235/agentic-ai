"""Small ROS2-agent configuration surface."""

import os


settings = {
    "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    "chat_model": os.getenv("ROS_AGENT_CHAT_MODEL", "qwen3:0.6b"),
}
