FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    ROS_AGENT_RUN_DIR=/workspace/data/runs \
    ROS_AGENT_CHROMA_PATH=/workspace/data/chroma

RUN python -m venv /opt/venv

WORKDIR /workspace
COPY pyproject.toml README.md LICENSE ./
COPY pipelines ./pipelines
COPY web_app.py ./web_app.py
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY . .
COPY docker/entrypoint.sh /usr/local/bin/ros-agent-entrypoint
RUN chmod +x /usr/local/bin/ros-agent-entrypoint

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/ros-agent-entrypoint"]
