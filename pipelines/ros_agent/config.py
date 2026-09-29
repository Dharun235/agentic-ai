"""Small ROS2-agent configuration surface."""

import os


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


settings = {
    "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    "ros_mcp_url": os.getenv("ROS_MCP_URL", "").strip(),
    "chat_model": os.getenv("ROS_AGENT_CHAT_MODEL", "qwen3:0.6b"),
    "embedding_model": os.getenv(
        "ROS_AGENT_EMBEDDING_MODEL", "qwen3-embedding:0.6b"
    ),
    "opensearch_url": os.getenv("OPENSEARCH_URL", "http://127.0.0.1:9200"),
    "opensearch_index": os.getenv("OPENSEARCH_INDEX", "ros2-tool-catalog"),
    "opensearch_username": os.getenv("OPENSEARCH_USERNAME", ""),
    "opensearch_password": os.getenv("OPENSEARCH_PASSWORD", ""),
    "opensearch_verify_certs": _env_bool("OPENSEARCH_VERIFY_CERTS"),
    "opensearch_ca_cert": os.getenv("OPENSEARCH_CA_CERT", ""),
    "opensearch_min_vector_score": float(
        os.getenv("OPENSEARCH_MIN_VECTOR_SCORE", "0.525")
    ),
    "run_dir": os.getenv("ROS_AGENT_RUN_DIR", "data/runs"),
    "planner_context": int(os.getenv("ROS_AGENT_PLANNER_CONTEXT", "8192")),
    "joiner_context": int(os.getenv("ROS_AGENT_JOINER_CONTEXT", "8192")),
}
