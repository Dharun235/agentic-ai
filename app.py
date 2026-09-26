from rag import build, ask

print("Loading knowledge...")
build()

print("\nReady.\n")

while True:
    q = input("Ask: ").strip()

    if q.lower() in {"exit", "quit"}:
        break

    if q:
        print("\n" + ask(q))
        print()