# Basic RAG Agent

Small local question-answering agent using Markdown knowledge, Ollama embeddings, ChromaDB, and an Ollama chat model.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/)
- Models:

```bash
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
```

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Start Ollama, then run the chat app:

```bash
ollama serve
python app.py
```

Ask questions about `knowledge.md`. Type `exit` or `quit` to stop.

## Configuration

Edit `config.json` to change the knowledge file, models, Ollama host, retrieval count, or chunk size:

```json
{
  "knowledge_path": "knowledge.md",
  "chroma_path": "chroma",
  "ollama_host": "http://localhost:11434",
  "chat_model": "qwen3:0.6b",
  "embedding_model": "qwen3-embedding:0.6b",
  "top_k": 5,
  "max_chunk_chars": 700
}
```

Relative paths are resolved from the project folder. After changing the knowledge file or chunk settings, the index rebuilds automatically.

## Evaluate RAG quality

```bash
python eval.py
```

`eval.py` runs a fast deterministic benchmark. It reports:

- Recall@1, @3, and @5.
- MRR and nDCG@5.
- Answer match and a simple grounding proxy.
- Retrieval, generation, and end-to-end latency.

Evaluation cases live in `eval_cases.json`. Review generated or changed cases before treating them as ground truth.

Run one case while checking setup:

```bash
EVAL_LIMIT=1 python eval.py
```

The index automatically rebuilds when `knowledge.md` changes.

## Project layout

```text
app.py           Interactive CLI
eval.py          Retrieval evaluation
config.json      Runtime settings
knowledge.md     Source knowledge
llm.py           Ollama answer generation
rag.py           Chunking, indexing, retrieval, and RAG flow
chroma/          Local vector database (generated)
```

## How it works

1. Parse `knowledge.md` into Markdown-aware chunks.
2. Embed chunks with `qwen3-embedding:0.6b`.
3. Store embeddings in local ChromaDB.
4. Embed each user question and retrieve the closest chunks.
5. Give retrieved context to `qwen3:0.6b`.

Answers use only retrieved context. If context does not contain an answer, the model is instructed to say `I don't know.`
