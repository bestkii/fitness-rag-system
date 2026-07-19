# Fitness Misinformation RAG System

A reproducible FastAPI and ChromaDB prototype for retrieving synthetic rebuttal
records related to a fitness claim. The project emphasizes transparent evaluation:
its dense BGE retrieval is compared with a TF-IDF baseline on a fixed, leakage-audited
held-out split.

> This is a coursework prototype built from synthetic model-generated text. It is
> not a medical fact-checker and must not be used for health decisions.

## Architecture

```text
claim -> BAAI/bge-small-zh-v1.5 -> ChromaDB cosine top-3
      -> expert-label aggregation -> extractive synthetic rebuttal
                                  -> optional DeepSeek synthesis
```

The application runs without an API key in conservative offline extractive mode.
If `DEEPSEEK_API_KEY` is present, it can synthesize a response using only the
retrieved context.

## Reproduced evaluation

The repository includes 3,000 synthetic records. Split v2 indexes 2,700 and holds
out 300 queries, stratifies by unordered topic pair, and keeps identical normalized
rumor text on only one side of the split.

<!-- FINAL_METRICS_START -->
| Metric | Dense BGE | TF-IDF | Absolute gain |
|---|---:|---:|---:|
| Topic-pair Precision@3 | 0.6256 | 0.5833 | +0.0423 |
| Topic-pair Recall@3 | 0.0458 | 0.0424 | +0.0034 |
| Topic-pair Hit@3 | 83.67% | 80.67% | +3.00 pp |
| MRR | 0.7383 | 0.6939 | +0.0444 |
| Expert-label Hit@3 | 85.00% | 82.00% | +3.00 pp |
| nDCG@3 | 0.6337 | 0.5890 | +0.0447 |
<!-- FINAL_METRICS_END -->

The labels and text are synthetic. These values measure topic-pair retrieval—not
medical correctness or answer quality. See `PROJECT_EVIDENCE.md` and
`artifacts/evaluation_metrics.json` for the complete configuration and caveats.

## Quick start

Python 3.12 is the verified runtime.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\build_knowledge_base.py
python scripts\evaluate_retrieval.py
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>.

For optional DeepSeek synthesis, copy `.env.example` for reference and set the
environment variable in your shell. The application does not automatically load
`.env` files.

```powershell
$env:DEEPSEEK_API_KEY = "your-own-key"
```

## Verification

After building the vector store:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python scripts\check_release.py
```

The unit tests check dataset size, complete/disjoint split coverage, absence of
normalized-rumor leakage, index membership when a local vector store exists, the
stored evaluation design, and an offline analysis smoke test.

## Repository contents

- `fitness_mock_3000.jsonl`: synthetic dataset
- `fitness_rag/`: configuration, data splitting, and RAG service
- `scripts/`: index builder, evaluator, and release guard
- `web/`: browser interface
- `tests/`: unit and integration checks
- `artifacts/`: fixed split and measured retrieval results
- `DATASET_CARD.md`: provenance and limitations
- `PROJECT_EVIDENCE.md`: portfolio claim-to-proof map

The original coursework folder also contained a virtual environment, multiple
vector stores, demo videos, submission packages, credential material, and
third-party PDFs. None of those files are part of this repository.

## Limitations

- No human-validated medical knowledge base or clinical evaluation
- No labeled answer-quality evaluation
- No calibrated out-of-domain rejection threshold
- Expert routing is a majority vote over retrieved synthetic metadata
- Optional DeepSeek generation has not been benchmarked for quality, cost, or latency
- Synthetic expert labels are imbalanced

## License

MIT. See `LICENSE`.
