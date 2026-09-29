"""OpenSearch hybrid retrieval for the ROS 2 MCP tool catalog."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from ollama import Client
from opensearchpy import OpenSearch

from .config import settings


LOGGER = logging.getLogger(__name__)
CATALOG_PATH = Path(__file__).parents[1] / "ros" / "tool_catalog.md"
INDEX_ALIAS = settings["opensearch_index"]
SEARCH_PIPELINE = f"{INDEX_ALIAS}-rrf"
TOP_K = 5
VECTOR_CANDIDATES = 30


class ToolCatalog:
    """Index capability cards and retrieve them with BM25 + dense vectors."""

    def __init__(self, path: Path = CATALOG_PATH, client=None, ollama_client=None):
        self.path = path
        self.ollama = ollama_client or Client(
            host=settings["ollama_host"], timeout=180
        )
        parsed = urlparse(settings["opensearch_url"])
        auth = None
        username = settings["opensearch_username"]
        password = settings["opensearch_password"]
        if username or password:
            if not username or not password:
                raise ValueError(
                    "OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD must be set together"
                )
            auth = (username, password)
        options = {
            "hosts": [settings["opensearch_url"]],
            "http_auth": auth,
            "use_ssl": parsed.scheme == "https",
            "verify_certs": settings["opensearch_verify_certs"],
            "ssl_show_warn": settings["opensearch_verify_certs"],
            "timeout": 30,
            "max_retries": 3,
            "retry_on_timeout": True,
        }
        if settings["opensearch_ca_cert"]:
            options["ca_certs"] = settings["opensearch_ca_cert"]
        self.db = client or OpenSearch(**options)
        self._lock = threading.RLock()
        self._pipeline_ready = False

    def _cards(self) -> list[dict[str, str]]:
        """Convert tool mentions in Markdown into searchable capability cards."""
        text = self.path.read_text(encoding="utf-8")
        cards: dict[str, dict[str, str]] = {}
        heading = "ROS 2 MCP tool catalog"
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
                cards[name] = {
                    "tool": name,
                    "category": heading,
                    "content": f"Tool: {name}\nCategory: {heading}\n" + "\n".join(context),
                }
        return list(cards.values())

    def _embed(self, texts: list[str]) -> list[list[float]]:
        result = self.ollama.embed(
            model=settings["embedding_model"], input=texts, keep_alive=0
        )
        vectors = result.get("embeddings") or []
        if len(vectors) != len(texts) or not vectors:
            raise RuntimeError("Ollama returned an invalid catalog embedding batch")
        dimension = len(vectors[0])
        if dimension == 0 or any(len(vector) != dimension for vector in vectors):
            raise RuntimeError("Ollama returned inconsistent embedding dimensions")
        return vectors

    @staticmethod
    def _mapping(source_hash: str, dimension: int) -> dict:
        return {
            "settings": {"index": {"knn": True}},
            "mappings": {
                "_meta": {
                    "catalog_hash": source_hash,
                    "embedding_model": settings["embedding_model"],
                },
                "properties": {
                    "tool": {"type": "keyword"},
                    "tool_text": {"type": "text"},
                    "category": {"type": "keyword"},
                    "content": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": dimension,
                        "space_type": "cosinesimil",
                        "method": {
                            "name": "hnsw",
                            "engine": "lucene",
                            "parameters": {"m": 16, "ef_construction": 100},
                        },
                    },
                },
            },
        }

    def _alias_indices(self) -> list[str]:
        try:
            result = self.db.indices.get_alias(name=INDEX_ALIAS)
        except Exception as error:
            if getattr(error, "status_code", None) == 404:
                return []
            raise
        return list(result)

    def _activate_index(self, index_name: str) -> None:
        old_indices = self._alias_indices()
        if old_indices == [index_name]:
            return
        actions = [
            {"remove": {"index": old, "alias": INDEX_ALIAS}}
            for old in old_indices
        ]
        actions.append({"add": {"index": index_name, "alias": INDEX_ALIAS}})
        self.db.indices.update_aliases(body={"actions": actions})
        for old in old_indices:
            if old != index_name and old.startswith(f"{INDEX_ALIAS}-"):
                try:
                    self.db.indices.delete(index=old)
                except Exception:
                    LOGGER.warning("Could not remove stale catalog index %s", old)

    def _ensure_search_pipeline(self) -> None:
        if self._pipeline_ready:
            return
        body = {
            "description": "Reciprocal-rank fusion for ROS agent hybrid retrieval",
            "phase_results_processors": [
                {
                    "score-ranker-processor": {
                        "combination": {
                            "technique": "rrf",
                            "rank_constant": 60,
                        }
                    }
                }
            ],
        }
        self.db.transport.perform_request(
            "PUT", f"/_search/pipeline/{SEARCH_PIPELINE}", body=body
        )
        self._pipeline_ready = True

    def _ensure_index(self) -> list[dict[str, str]]:
        cards = self._cards()
        if not cards:
            raise RuntimeError(f"No tool cards found in {self.path}")
        source_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        index_name = f"{INDEX_ALIAS}-{source_hash[:16]}"
        with self._lock:
            if self.db.indices.exists(index=index_name):
                mapping = self.db.indices.get_mapping(index=index_name)[index_name]["mappings"]
                metadata = mapping.get("_meta", {})
                count = self.db.count(index=index_name).get("count", 0)
                if (
                    metadata.get("catalog_hash") == source_hash
                    and metadata.get("embedding_model") == settings["embedding_model"]
                    and count == len(cards)
                ):
                    self._activate_index(index_name)
                    self._ensure_search_pipeline()
                    return cards
                self.db.indices.delete(index=index_name)

            vectors = self._embed([card["content"] for card in cards])
            dimension = len(vectors[0])
            self.db.indices.create(
                index=index_name,
                body=self._mapping(source_hash, dimension),
            )
            bulk_body = []
            for card, vector in zip(cards, vectors):
                bulk_body.extend(
                    [
                        {"index": {"_index": index_name, "_id": card["tool"]}},
                        {
                            **card,
                            "tool_text": card["tool"].replace("_", " "),
                            "embedding": vector,
                        },
                    ]
                )
            response = self.db.bulk(body=bulk_body, refresh=True)
            if response.get("errors"):
                self.db.indices.delete(index=index_name)
                raise RuntimeError("OpenSearch failed to index all catalog cards")
            self._activate_index(index_name)
            self._ensure_search_pipeline()
        return cards

    @staticmethod
    def _keyword_query(query: str, available_tools: list[str]) -> dict:
        return {
            "bool": {
                "filter": [{"terms": {"tool": available_tools}}],
                "should": [
                    {"term": {"tool": {"value": query.strip(), "boost": 8}}},
                    {"match": {"tool_text": {"query": query, "boost": 4}}},
                    {"match": {"content": {"query": query}}},
                ],
                "minimum_should_match": 1,
            }
        }

    def retrieve(
        self, query: str, available_tools: set[str], top_k: int = TOP_K
    ) -> list[dict]:
        """Fuse BM25 and k-NN ranks, then return only live MCP tools."""
        if top_k <= 0 or not query.strip() or not available_tools:
            return []
        cards = self._ensure_index()
        by_name = {card["tool"]: card for card in cards}
        allowed = sorted(available_tools & by_name.keys())
        if not allowed:
            return []

        query_vector = self._embed([query])[0]
        candidate_count = min(max(top_k * 5, VECTOR_CANDIDATES), len(allowed))
        vector_query = {
            "knn": {
                "embedding": {
                    "vector": query_vector,
                    "k": candidate_count,
                    "filter": {"terms": {"tool": allowed}},
                }
            }
        }
        probe = self.db.search(
            index=INDEX_ALIAS,
            body={"size": 1, "query": vector_query},
        )
        probe_hits = probe.get("hits", {}).get("hits", [])
        best_vector_score = probe_hits[0].get("_score", 0.0) if probe_hits else 0.0

        lexical = self.db.search(
            index=INDEX_ALIAS,
            body={
                "size": 1,
                "query": self._keyword_query(query, allowed),
                "_source": False,
            },
        )
        lexical_hits = lexical.get("hits", {}).get("hits", [])
        if not lexical_hits and best_vector_score < settings["opensearch_min_vector_score"]:
            return []

        body = {
            "size": min(top_k, candidate_count),
            "_source": ["tool", "content", "category"],
            "query": {
                "hybrid": {
                    "queries": [
                        self._keyword_query(query, allowed),
                        vector_query,
                    ]
                }
            },
        }
        response = self.db.search(
            index=INDEX_ALIAS,
            body=body,
            params={"search_pipeline": SEARCH_PIPELINE},
        )
        results = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            tool = source.get("tool")
            if tool not in allowed:
                continue
            results.append(
                {
                    "tool": tool,
                    "content": source.get("content", by_name[tool]["content"]),
                    "category": source.get("category", by_name[tool]["category"]),
                    "score": hit.get("_score"),
                }
            )
        return results[:top_k]


catalog = ToolCatalog()
