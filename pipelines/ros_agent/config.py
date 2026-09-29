"""Small ROS2-agent configuration surface."""

import os


settings = {
    "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    "ros_mcp_url": os.getenv("ROS_MCP_URL", "").strip(),
    "chat_model": os.getenv("ROS_AGENT_CHAT_MODEL", "qwen3:0.6b"),
    "embedding_model": os.getenv(
        "ROS_AGENT_EMBEDDING_MODEL", "qwen3-embedding:0.6b"
    ),
    "chroma_path": os.getenv("ROS_AGENT_CHROMA_PATH", "data/chroma"),
    "run_dir": os.getenv("ROS_AGENT_RUN_DIR", "data/runs"),
    "planner_context": int(os.getenv("ROS_AGENT_PLANNER_CONTEXT", "8192")),
    "joiner_context": int(os.getenv("ROS_AGENT_JOINER_CONTEXT", "8192")),
}
