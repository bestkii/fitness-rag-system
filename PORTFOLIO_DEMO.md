# Portfolio demo: Fitness Evidence Studio

## 90-second story

1. Enter a question such as `空腹有氧真的比普通有氧更减脂吗？`.
2. Show a locally collected Xiaohongshu trend card and explain that it is used only
   for topic discovery, not as factual evidence.
3. Load the representative textbook review queue, open one local source-page
   preview, and show the explicit approve/exclude controls.
4. Search the local staging corpus and point out the printed-page citation,
   OCR-review status, and local-only boundary.
5. Explain that only human-approved chunks can enter the separate formal index.
6. Show the two PubMed/Crossref queries planned by the agent.
7. Open the ranked source links and point out their source-tier labels.
8. Review the generated title, body, source markers, and five-card script.
9. Explain that neither private OCR text nor the old synthetic RAG result becomes a public citation.
10. Trigger the approval guard without checking the box to demonstrate the blocked state.
11. Open the sources, acknowledge review, approve, and export the text pack.
12. End on both retrieval evaluations and their different claim boundaries.

## What this demonstrates

- Tool-using research orchestration rather than a single prompt
- Source provenance and deterministic evidence-policy checks
- Separation of synthetic RAG context from real web sources
- Separation of social trend signals from academic evidence
- Structured content generation for a concrete product workflow
- Human-in-the-loop state management before external action
- Reproducible retrieval metrics that remain unchanged by the agent layer
- Evaluation-driven retriever selection: TF-IDF beat dense retrieval on the
  private staging pilot, so the demo uses the measured-better method

## Claims not to make yet

- Do not call the output medically validated.
- Do not claim that search snippets equal full-paper evidence.
- Do not claim autonomous Xiaohongshu publishing.
- Do not claim that Xiaohongshu popularity is evidence quality.
- Do not claim measured content quality, engagement, cost, or latency until evaluated.
- Do not call the private-textbook development pilot a held-out benchmark or a
  production-ready knowledge base.
