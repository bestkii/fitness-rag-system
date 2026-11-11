# Portfolio demo: Fitness Evidence Studio

The local interview interface is available in both languages:

- English: `http://127.0.0.1:8010/` or `http://127.0.0.1:8010/en`
- Chinese: `http://127.0.0.1:8010/zh`

In the English workbench, open a candidate under **Community Questions**, select
**Use as topic**, and enter an editorial question in English. Run the draft,
inspect the five cards and academic source links, acknowledge source review, and
export the approved text pack. The Chinese demo below covers the private textbook
and Xiaohongshu modules.

## 90-second story

1. Use the hero and live system map to state the problem: fitness content should
   be traceable and reviewable, not merely generated.
2. Show the five-stage architecture and explain the separation between trend
   discovery, academic evidence, RAG context, generation, and approval.
3. Open **内容 Agent**, enter `空腹有氧真的比普通有氧更减脂吗？`, and run the
   real research-and-draft workflow.
4. Point out the ranked PubMed/Crossref sources, source markers, five-card script,
   and the approval guard that blocks export before source acknowledgement.
5. Switch to **教材 RAG**, search `抗阻训练计划包含哪些设计变量？`, and show the
   printed-page citation, local-only boundary, and explicit approve/exclude state.
6. End on **Evaluation**: dense retrieval wins on the fixed synthetic benchmark,
   while character TF-IDF wins on the private textbook development pilot.
7. Close with the ownership and limitations cards; do not imply medical validation
   or autonomous publishing.

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
