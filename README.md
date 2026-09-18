# Fitness Evidence Studio

A portfolio-oriented research and drafting agent built on the original reproducible
Fitness RAG prototype. It turns a fitness topic into a source-linked Xiaohongshu
draft, five-card carousel script, review checklist, and exportable content pack.
It deliberately stops before publication.

> This is a coursework prototype built from synthetic model-generated text. It is
> not a medical fact-checker and must not be used for health decisions.

## Agent workflow

```text
topic -> two planned PubMed/Crossref searches -> deduplicate + topic relevance
      -> source-tier ranking
      -> research packet -> optional legacy RAG orientation context
      -> template or LLM draft -> citation checks -> human review
      -> approval -> text export (no automatic posting)
```

The research path uses the free PubMed E-utilities and Crossref REST API by
default; no research API key is required. Without a content-model key, the
application still produces a deterministic, reviewable template. Set
`CONTENT_API_KEY` or `DEEPSEEK_API_KEY` to enable LLM drafting. Brave remains an
explicit opt-in fallback through `RESEARCH_PROVIDER=brave` plus your own key.

The current integration uses PubMed abstracts and Crossref metadata as research
leads. Reviewers must open the original URLs before approval; excerpts are not
treated as complete papers. Runtime drafts are stored under the ignored `runtime/`
directory. Queries with a known ambiguity, such as fasted cardio, also require
every retained source to match the defining topic concepts before drafting.

## Read-only Xiaohongshu trend collector

The optional collector opens a visible local Chrome window and reads a small number
of public search-result cards from the rendered page. It does not call private
mobile APIs, intercept network traffic, bypass verification, or like, follow,
comment, message, or publish. It stops if Xiaohongshu requests login or presents a
risk-control challenge. The local browser profile and SQLite trend database stay
under the ignored `runtime/` directory.

First, open a reusable local browser profile and scan the login QR code yourself:

```powershell
python scripts\xiaohongshu_login.py
```

For the most stable demo path, collect up to 20 fitness-related cards from the
public personalized home feed:

```powershell
python scripts\xiaohongshu_collect.py --home-fitness --limit 20
```

Keyword mode is also available, but Xiaohongshu's search page may return no cards
when its public web UI changes:

```powershell
python scripts\xiaohongshu_collect.py "空腹有氧" --limit 20
```

The collector has a hard cap of 30 notes and five scrolls per run. Home-feed mode
labels its records `首页健身筛选`; it does not claim they are exact search results.
The website's
`Local Xiaohongshu Trend Radar` reads those saved cards; it never launches a
background collector from the server.

## Private textbook OCR pilot

Private, legally obtained reference books can be evaluated as a separate local
corpus. Raw PDFs, OCR text, and any resulting index stay under ignored `runtime/`
paths and are not part of the public repository. Install the optional local OCR
dependencies, then run a representative-page pilot:

```powershell
pip install -r requirements-ocr.txt
python scripts\ocr_pilot.py --source "C:\path\to\book.pdf" --source-id book_edition --sample-count 20
```

The report separates OCR readability from RAG eligibility. It records page-type and
layout warnings, excludes image-only and reference pages, and routes tables and
split layouts for manual review. No sampled page is auto-ingested: terminology,
reading order, tables, and citations must be verified before a book can enter the
textbook layer of the RAG corpus.

Selected sections can then be extracted into a separate local staging corpus. Every
chunk retains the book, section, PDF page, printed page, and review status. The
private index is separate from the 2,700-record synthetic benchmark and remains
under ignored `runtime/private_corpus/` paths:

```powershell
python scripts\extract_private_textbook.py --source "C:\path\to\book.pdf" --source-id book_section --title "Book title" --section-id section_name --section-title "Section title" --start-page 10 --end-page 20 --printed-page-offset 5
python scripts\build_private_textbook_index.py --source-id book_section
python scripts\evaluate_private_textbook_retrieval.py
```

The staged index is retrieval-only until its OCR terminology and reconstructed page
order have been reviewed. Table-heavy pages are excluded from this first text index.
The app exposes the measured-better staging retriever at
`GET /api/private-library/search?q=...`; it returns local excerpts with printed-page
citations and never sends book text to the web research or cloud content model.
The review queue records explicit approve/reject decisions in an ignored local
SQLite database. Source-page previews are rendered only from PDFs registered in
the local source registry. The approved index builder refuses to run until at
least one chunk has been human-approved:

```powershell
python scripts\configure_private_source_registry.py --source "book_section=C:\path\to\book.pdf"
python scripts\build_approved_private_textbook_index.py
```

## Legacy RAG architecture

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

Do not paste keys into source files or browser JavaScript. With the server running,
open the homepage and use **Create a sourced draft**. The API endpoints are:

- `POST /api/content/drafts`: research and create a draft
- `GET /api/content/drafts/{id}`: inspect a persisted draft
- `POST /api/content/drafts/{id}/approve`: acknowledge source review
- `GET /api/content/drafts/{id}/export`: export the text pack
- `GET /api/trends?keyword=空腹有氧`: inspect locally collected public cards

See `PORTFOLIO_DEMO.md` for the recruiter-facing demo flow.

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
- `fitness_rag/evidence.py`: free PubMed and Crossref adapters
- `fitness_rag/research.py`: provider selection, source policy, and research plan
- `fitness_rag/xiaohongshu.py`: bounded visible-browser trend collector and local store
- `fitness_rag/content.py`: grounded content drafting and citation checks
- `fitness_rag/drafts.py`: local draft, approval, and export state
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
- Academic excerpts/metadata are discovery evidence and require original-page review
- Xiaohongshu DOM selectors may change and require maintenance
- Trend cards describe popularity/positioning, not scientific evidence
- No unattended social-media publishing or analytics integration

## License

MIT. See `LICENSE`.
