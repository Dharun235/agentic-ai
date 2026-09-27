FROM ros:jazzy-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends python3-pip && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY demo_node.py /workspace/demo_node.py
CMD ["bash", "-lc", "source /opt/ros/jazzy/setup.bash && python3 /workspace/demo_node.py"]
