# Code guidelines

- Keep agent behavior in `pipelines/ros_agent/`; keep ROS2 tool adapters in `pipelines/ros/`.
- Add one-line module docstrings to every Python module.
- Add docstrings to every public function, tool, and class; state inputs, output, and side effects.
- Use type hints for public function parameters and return values.
- Test user-visible pipeline behavior, not MCP implementation details.
- Keep tools narrow, bounded, and explicit. No arbitrary shell commands.
- Every action must return observed verification or a clear failure.
- Keep ROS2 scope enforcement before model/tool planning.
- Prefer small functions, type hints, and names matching ROS2 terminology.
- Do not add external knowledge or silent fallbacks to unrelated tasks.
- Update `README.md` and `tool_catalog.md` when public behavior or tools change.
- Add tests for success, missing prerequisites, tool failure, and out-of-scope input.
- Run `pytest -q`, `python -m compileall`, and `git diff --check` before review.

Contributions are welcome. Keep pull requests focused, tested, and within ROS2 scope.
