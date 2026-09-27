"""Interactive ROS 2 agent CLI."""

from pipelines.ros_agent import run_with_state


print("ROS 2 agent ready. Type exit or quit to stop.")

while True:
    question = input("Ask: ").strip()
    if question.lower() in {"exit", "quit"}:
        break
    if question:
        state = run_with_state(question)
        print(f"\n[{state.status}] {state.answer or 'No answer.'}\n")
