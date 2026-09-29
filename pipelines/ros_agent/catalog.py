"""Chroma-backed retrieval for the ROS2 MCP tool catalog."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import chromadb
from ollama import Client

from .config import settings


CATALOG_PATH = Path(__file__).parents[1] / "ros" / "tool_catalog.md"
COLLECTION_NAME = "ros2_tool_catalog"
TOP_K = 5
MAX_DISTANCE = 0.95


class ToolCatalog:
    """Index and retrieve MCP tool cards from Markdown using Chroma and Ollama."""

    def __init__(self, path: Path = CATALOG_PATH):
        self.path = path
        self.ollama = Client(host=settings["ollama_host"], timeout=60)
        self.db = chromadb.PersistentClient(path=settings["chroma_path"])

    def _cards(self) -> list[dict[str, str]]:
        """Convert catalog tool mentions into searchable tool cards."""
        text = self.path.read_text(encoding="utf-8")
        cards: dict[str, dict[str, str]] = {}
        heading = "ROS2 MCP tool catalog"
        context: list[str] = []
        pattern = re.compile(r"`([a-zA-Z][a-zA-Z0-9_-]*)(?:\([^`]*\))?`")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("# ").strip()
                context = [heading]
                continue
            if stripped:
                context.append(stripped)
                context = context[-4:]
            for name in pattern.findall(line):
                if name.isupper():
                    continue
                cards.setdefault(name, {"tool": name, "content": ""})["content"] = (
                    f"Tool: {name}\nCategory: {heading}\n" + "\n".join(context)
                )
        return list(cards.values())

    def _collection(self):
        """Return collection, rebuilding it when catalog source changes."""
        cards = self._cards()
        source_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        try:
            collection = self.db.get_collection(COLLECTION_NAME)
            if collection.metadata.get("catalog_hash") != source_hash:
                self.db.delete_collection(COLLECTION_NAME)
                collection = None
        except Exception:
            collection = None
        if collection is None:
            collection = self.db.create_collection(
                COLLECTION_NAME, metadata={"catalog_hash": source_hash}
            )
            embeddings = self.ollama.embed(
                model=settings["embedding_model"],
                input=[card["content"] for card in cards],
                keep_alive=0,
            )["embeddings"]
            collection.add(
                ids=[card["tool"] for card in cards],
                embeddings=embeddings,
                documents=[card["content"] for card in cards],
                metadatas=[{"tool": card["tool"]} for card in cards],
            )
        return collection

    def retrieve(
        self, query: str, available_tools: set[str], top_k: int = TOP_K
    ) -> list[dict]:
        """Retrieve relevant catalog cards whose tools are available through MCP."""
        collection = self._collection()
        query_embedding = self.ollama.embed(
            model=settings["embedding_model"], input=query, keep_alive=0
        )["embeddings"][0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=collection.count(),
            include=["documents", "metadatas", "distances"],
        )
        query_words = set(re.findall(r"[a-z0-9_]+", query.lower()))
        ranked = []
        for document, metadata, distance in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            tool = metadata["tool"]
            tool_words = set(re.findall(r"[a-z0-9]+", tool.lower()))
            exact_overlap = sum(1 for word in query_words if len(word) > 3 and word in tool.lower())
            query_parts = {
                part
                for word in query_words
                for part in word.split("_")
                if len(part) > 2
            }
            tool_overlap = sum(
                1
                for query_word in query_parts
                if query_word in tool_words
                or any(query_word.startswith(word) or word.startswith(query_word) for word in tool_words)
            )
            if tool in available_tools and (distance <= MAX_DISTANCE or tool_overlap > 0):
                document_words = set(re.findall(r"[a-z0-9_]+", document.lower()))
                lexical_overlap = len(query_words & document_words)
                ranked.append((exact_overlap, tool_overlap, lexical_overlap, distance, {"tool": tool, "content": document, "distance": distance}))
        ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
        return [item[4] for item in ranked[:top_k]]


catalog = ToolCatalog()
