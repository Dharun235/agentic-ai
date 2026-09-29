from __future__ import annotations

from pipelines.ros_agent.catalog import INDEX_ALIAS, SEARCH_PIPELINE, ToolCatalog


class MissingAlias(Exception):
    status_code = 404


class FakeIndices:
    def __init__(self):
        self.mappings = {}
        self.aliases = {}

    def exists(self, index):
        return index in self.mappings

    def get_mapping(self, index):
        return {index: {"mappings": self.mappings[index]}}

    def create(self, index, body):
        self.mappings[index] = body["mappings"]

    def delete(self, index):
        self.mappings.pop(index, None)
        for alias in self.aliases.values():
            alias.discard(index)

    def get_alias(self, name):
        indices = self.aliases.get(name, set())
        if not indices:
            raise MissingAlias(name)
        return {index: {"aliases": {name: {}}} for index in indices}

    def update_aliases(self, body):
        for action in body["actions"]:
            if "remove" in action:
                item = action["remove"]
                self.aliases.setdefault(item["alias"], set()).discard(item["index"])
            else:
                item = action["add"]
                self.aliases.setdefault(item["alias"], set()).add(item["index"])


class FakeTransport:
    def __init__(self):
        self.requests = []

    def perform_request(self, method, path, body):
        self.requests.append((method, path, body))


class FakeOpenSearch:
    def __init__(self, *, vector_score=0.8, lexical_hits=True):
        self.indices = FakeIndices()
        self.transport = FakeTransport()
        self.vector_score = vector_score
        self.lexical_hits = lexical_hits
        self.documents = {}
        self.searches = []

    def count(self, index):
        return {"count": len(self.documents.get(index, {}))}

    def bulk(self, body, refresh):
        index_name = None
        for item in body:
            if "index" in item:
                index_name = item["index"]["_index"]
                self.documents.setdefault(index_name, {})
            else:
                self.documents[index_name][item["tool"]] = item
        return {"errors": False}

    def search(self, index, body, params=None):
        self.searches.append((index, body, params))
        query = body["query"]
        if "hybrid" in query:
            docs = self.documents[ next(iter(self.indices.aliases[INDEX_ALIAS])) ]
            first, second = list(docs.values())[:2]
            return {
                "hits": {
                    "hits": [
                        {"_score": 0.9, "_source": first},
                        {"_score": 0.8, "_source": second},
                    ]
                }
            }
        if "knn" in query:
            return {"hits": {"hits": [{"_score": self.vector_score}]}}
        return {
            "hits": {"hits": [{"_score": 1.0}] if self.lexical_hits else []}
        }


class FakeOllama:
    def embed(self, model, input, keep_alive):
        texts = input if isinstance(input, list) else [input]
        return {"embeddings": [[float(index + 1), 0.5, 0.25] for index, _ in enumerate(texts)]}


def test_catalog_indexes_and_runs_filtered_hybrid_search(tmp_path):
    path = tmp_path / "tools.md"
    path.write_text(
        "# Graph tools\n\n"
        "- `list_ros_nodes`: List active nodes.\n"
        "- `ros_topic_info(topic)`: Inspect one topic.\n",
        encoding="utf-8",
    )
    client = FakeOpenSearch()
    catalog = ToolCatalog(path=path, client=client, ollama_client=FakeOllama())

    result = catalog.retrieve("List ROS 2 nodes", {"list_ros_nodes", "ros_topic_info"}, top_k=1)

    assert len(result) == 1
    assert client.indices.aliases[INDEX_ALIAS]
    physical_index = next(iter(client.indices.aliases[INDEX_ALIAS]))
    mapping = client.indices.mappings[physical_index]
    assert mapping["properties"]["embedding"]["type"] == "knn_vector"
    assert mapping["properties"]["embedding"]["dimension"] == 3
    assert client.transport.requests[0][0:2] == (
        "PUT", f"/_search/pipeline/{SEARCH_PIPELINE}"
    )
    hybrid_body = client.searches[-1][1]
    assert len(hybrid_body["query"]["hybrid"]["queries"]) == 2
    assert client.searches[-1][2] == {"search_pipeline": SEARCH_PIPELINE}


def test_catalog_rejects_out_of_scope_vector_matches(tmp_path):
    path = tmp_path / "tools.md"
    path.write_text("# Graph tools\n\n- `list_ros_nodes`: List active nodes.\n", encoding="utf-8")
    client = FakeOpenSearch(vector_score=0.50, lexical_hits=False)
    catalog = ToolCatalog(path=path, client=client, ollama_client=FakeOllama())

    assert catalog.retrieve("Weather in Stockholm", {"list_ros_nodes"}) == []
    assert len(client.searches) == 2
    assert "hybrid" not in client.searches[-1][1]["query"]
