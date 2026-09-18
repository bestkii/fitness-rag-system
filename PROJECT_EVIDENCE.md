# Project evidence

This file maps portfolio claims to reproducible public evidence.

## Implemented system

- Two-query academic research plan with free PubMed and Crossref APIs
- URL deduplication, topic-concept relevance checks, and explicit
  authoritative/academic/general source tiers
- Read-only, visible-browser Xiaohongshu trend collection with local persistence,
  hard result/scroll caps, and stop-on-verification behavior
- Local trend API and dashboard that keep popularity signals separate from evidence
- Source-linked Chinese Xiaohongshu draft plus five-card carousel script
- Persistent draft-to-approved transition with source-review acknowledgement
- Text-pack export with no automatic publication
- FastAPI application: `app.py`
- Retrieval and optional generation service: `fitness_rag/service.py`
- Deterministic, leakage-audited split: `fitness_rag/data.py`
- Chroma knowledge-base builder: `scripts/build_knowledge_base.py`
- Dense-versus-TF-IDF evaluation: `scripts/evaluate_retrieval.py`
- Automated checks: `tests/test_system.py`
- Local-only RapidOCR textbook pipeline with page-type gates and page citations
- Separate 126-chunk staging index for selected dietary-guideline and NSCA sections
- Local textbook search API using the pilot's measured-better character TF-IDF retriever
- Local source-page review queue with persistent approve/exclude decisions
- Separate approved-index builder that refuses to run with zero human approvals

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

## Private textbook staging pilot

Two legally held PDFs were processed locally. Original PDFs, OCR text, vector
data, and detailed reports are ignored under `runtime/private_corpus/`; no book
text is sent to the web-research or cloud-content workflow. The first selection
covers printed pages 3-46 of the Chinese Dietary Guidelines (2022) and printed
pages 471-500 of NSCA-CSCS 4th edition. Quality gates staged 58 of 74 pages and
excluded 16 table-heavy or structurally unsuitable pages, producing 126 chunks.

An 11-query, table-of-contents-derived development pilot compared the existing
dense embedding with character TF-IDF at top 3. Dense page-range Hit@3 was
`81.82%`; TF-IDF was `100.00%`. Dense MRR was `0.7727`; TF-IDF was `0.9091`.
The local demo therefore defaults to TF-IDF for this staging corpus. These are
development-set retrieval-location metrics, not a held-out benchmark and not a
measure of OCR correctness, answer quality, or medical validity. Future changes
require a new held-out query set.

The staging corpus is not the formal RAG knowledge base. A reviewer must compare
each candidate with its locally rendered source page and explicitly approve or
exclude it. Only approved chunks can enter the separate approved index; the
current review count is reported by the local application rather than inferred
from the OCR pipeline.

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

The content workflow does not change the fixed split, embedding configuration,
vector store, or stored retrieval metrics. Academic search quality,
generated-content correctness, latency, and social-media performance are not yet
benchmarked. Abstracts and metadata must be checked against their original pages
before a draft is approved. The Xiaohongshu collector depends on changeable
public-page DOM and has not been load-tested. The application does not publish to
Xiaohongshu automatically.
