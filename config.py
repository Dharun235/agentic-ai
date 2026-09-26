import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def load():
    with CONFIG_PATH.open(encoding="utf-8") as file:
        config = json.load(file)

    for key in ("knowledge_path", "chroma_path"):
        path = Path(config[key])
        config[key] = path if path.is_absolute() else ROOT / path

    return config


settings = load()
