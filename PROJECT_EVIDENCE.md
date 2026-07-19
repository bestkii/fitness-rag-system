# Project evidence

This file maps portfolio claims to reproducible public evidence.

## Implemented system

- FastAPI application: `app.py`
- Retrieval and optional generation service: `fitness_rag/service.py`
- Deterministic, leakage-audited split: `fitness_rag/data.py`
- Chroma knowledge-base builder: `scripts/build_knowledge_base.py`
- Dense-versus-TF-IDF evaluation: `scripts/evaluate_retrieval.py`
- Automated checks: `tests/test_system.py`

Configuration:

- Dataset: 3,000 DeepSeek-generated synthetic rumor/rebuttal records
- Indexed records: 2,700
- Held-out queries: 300
- Embedding: `BAAI/bge-small-zh-v1.5`, 512 dimensions
- Store and distance: ChromaDB, cosine
- Retrieval depth: top 3
- Split seed: `20260627`

## Evaluation audit

The original split-v1 result is preserved in
`artifacts/evaluation_baseline_split_v1.json`, but it is deprecated because one
normalized rumor crossed the train/test boundary. Split v2 groups identical
normalized rumors on one side before evaluation and verifies that the Chroma
metadata exactly matches the training indices.

Final split-v2 metrics are generated in `artifacts/evaluation_metrics.json`.

<!-- FINAL_METRICS_START -->
- Topic-pair Precision@3: dense `0.6256`; TF-IDF `0.5833`
- Topic-pair Recall@3: dense `0.0458`; TF-IDF `0.0424`
- Topic-pair Hit@3: dense `83.67%`; TF-IDF `80.67%`
- Mean reciprocal rank: dense `0.7383`; TF-IDF `0.6939`
- Expert-label Hit@3: dense `85.00%`; TF-IDF `82.00%`
- nDCG@3: dense `0.6337`; TF-IDF `0.5890`

Dense retrieval improved topic-pair Hit@3 by `3.00` percentage points,
MRR by `0.0444`, and nDCG@3 by `0.0447` over the TF-IDF baseline.
<!-- FINAL_METRICS_END -->

Failure review found 251 topic-pair hits and 49 misses among the 300 fixed
queries. The weakest topic-pair groups included `big_lifts|nutrition_tracking`
(1/5 hits), `big_lifts|meal_timing` (1/4), and `big_lifts|metabolic_truth`
(1/4). The run is deterministic for the fixed split; confidence intervals and
variance across alternate splits were not measured.

## Reproduction commands

```powershell
python scripts\build_knowledge_base.py
python scripts\evaluate_retrieval.py
python -m unittest discover -s tests -p "test_*.py" -v
python scripts\check_release.py
```

## Claim boundary

The measured results evaluate synthetic topic-pair retrieval. They do not
measure clinical validity, medical safety, or generated-answer correctness.
Offline mode returns a related synthetic rebuttal rather than asserting that a
user claim has been medically disproved. DeepSeek answer generation is optional
and was not used for the reported retrieval benchmark.
