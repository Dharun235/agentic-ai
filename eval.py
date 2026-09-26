import json
import math
import os
import re
from pathlib import Path
from statistics import mean, median
from time import perf_counter

from llm import answer
from rag import build, retrieve_scored


ROOT = Path(__file__).resolve().parent


def percentile(values, value):
    ordered = sorted(values)
    return ordered[round((value / 100) * (len(ordered) - 1))]


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def main():
    cases = json.loads((ROOT / "eval_cases.json").read_text(encoding="utf-8"))
    limit = int(os.getenv("EVAL_LIMIT", "0"))
    cases = cases[:limit] if limit else cases

    start = perf_counter()
    build()
    indexing_ms = (perf_counter() - start) * 1000

    hits = {1: 0, 3: 0, 5: 0}
    reciprocal_ranks = []
    ndcg_scores = []
    answer_matches = []
    grounding_scores = []
    retrieval_ms = []
    generation_ms = []

    for case in cases:
        question = case["question"]
        expected = case["expected_answer"].lower()

        start = perf_counter()
        scored = retrieve_scored(question)
        retrieval_ms.append((perf_counter() - start) * 1000)
        docs = [document for _, document, _ in scored]
        relevant = [expected in document.lower() for document in docs]

        for k in hits:
            hits[k] += int(any(relevant[:k]))

        rank = next((index + 1 for index, hit in enumerate(relevant) if hit), None)
        reciprocal_ranks.append(1 / rank if rank else 0)
        dcg = sum(int(hit) / math.log2(index + 2) for index, hit in enumerate(relevant))
        ideal = sum(1 / math.log2(index + 2) for index in range(sum(relevant)))
        ndcg_scores.append(dcg / ideal if ideal else 0)

        start = perf_counter()
        output = answer(question, "\n\n".join(docs))
        generation_ms.append((perf_counter() - start) * 1000)
        answer_matches.append(expected in output.lower())
        grounding_scores.append(len(words(output) & words(" ".join(docs))) / max(len(words(output)), 1))

        print(f"{question} | rank={rank or 'miss'} | answer={answer_matches[-1]}")

    total = len(cases)
    print("\nMetrics")
    print(f"Recall@1/3/5: {hits[1] / total:.1%}/{hits[3] / total:.1%}/{hits[5] / total:.1%}")
    print(f"MRR: {mean(reciprocal_ranks):.3f}")
    print(f"nDCG@5: {mean(ndcg_scores):.3f}")
    print(f"Answer match: {mean(answer_matches):.1%}")
    print(f"Grounding proxy: {mean(grounding_scores):.1%}")
    print("\nLatency (milliseconds)")
    print(f"Indexing: {indexing_ms:.1f}")
    print(f"Retrieval p50/p95: {median(retrieval_ms):.1f}/{percentile(retrieval_ms, 95):.1f}")
    print(f"Generation p50/p95: {median(generation_ms):.1f}/{percentile(generation_ms, 95):.1f}")
    print(f"End-to-end mean: {mean(r + g for r, g in zip(retrieval_ms, generation_ms)):.1f}")


if __name__ == "__main__":
    main()
