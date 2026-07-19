# Dataset card

## Summary

`fitness_mock_3000.jsonl` contains 3,000 synthetic English fitness-misinformation
claims and rebuttals. It was generated with `deepseek-chat` from combinations of
12 topic labels. Each record contains the prompt topics, an expert-category label,
a rumor-style claim, a rebuttal, and generation metadata.

The data is included to reproduce this coursework prototype. It is not a medical,
clinical, or nutrition reference corpus.

## Provenance

- Generator: `async_fitness_data_generator.py`
- Model recorded in the dataset: `deepseek-chat`
- Temperature: `0.8`
- Generation completed: 2026-06-27 UTC
- Human clinical validation: none
- Source-document grounding: none

No textbook PDFs or third-party book content are included or indexed by this
repository.

## Split

The release uses split version 2:

- 2,700 indexed training records
- 300 held-out query records
- deterministic seed `20260627`
- stratified by unordered topic pair
- identical normalized rumor text is kept entirely on one side of the split

The exact indices, dataset fingerprint, and leakage diagnostics are stored in
`artifacts/dataset_split.json`.

## Known limitations

- The claims and rebuttals may contain model-generated inaccuracies.
- Topic and expert labels are synthetic and imbalanced.
- Retrieval relevance means “same unordered topic pair,” not medical correctness.
- This dataset must not be used for diagnosis, treatment, or safety-critical advice.
