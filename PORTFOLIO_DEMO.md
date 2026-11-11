# Portfolio demo: Fitness Evidence Studio

The local interview interface is available in both languages:

- English: `http://127.0.0.1:8010/` or `http://127.0.0.1:8010/en`
- Chinese: `http://127.0.0.1:8010/zh`

In the English workbench, open a candidate under **Community Questions**, select
**Use as topic**, and enter an editorial question in English. Run the draft,
inspect the five cards and academic source links, acknowledge source review, and
export the approved text pack. The Chinese demo below covers the private textbook
and Xiaohongshu modules.

## Bluesky demo

Use the English topic **Accuracy in predicting repetitions to task failure in
resistance exercise**. Look for the 2022 Halperin et al. exploratory
meta-analysis, DOI `10.1007/s40279-021-01559-x`, and check the original source.
Select that paper in the Bluesky preview. Example post text for editorial review:

> How many reps did you have left? In a review of resistance training studies,
> lifters underestimated reps to failure by about one rep on average. Estimates
> varied widely, so treat reps in reserve as a rough guide. AI-assisted.

For the visual example, use **How many reps left?** as the headline and enter
**8** with **Reps completed** and **2** with **Reps estimated**. The solid and
dashed frames distinguish the two values, and a supporting gym photo can show
the setting. The workbench generates the image and adds the selected research
link to the text preview. Review the text, image, and destination account before
clicking **Publish with image**.

Enable **Include a Read more thread** and review each explanation reply. For this
topic, explain what repetitions in reserve measures, how predicted and actual
repetitions were compared, what the pooled average means, and the study
limitations. Check each statement against its selected source. The myth post's
**Read more ↓** link will open the first reply.

### Editorial explanation example

Verify the [Halperin et al. review](https://doi.org/10.1007/s40279-021-01559-x)
and select it as the source for each of these draft replies.

1. Reps in reserve (RIR) describes how many more reps you think you could complete before task failure. Stopping after 8 reps at 2 RIR implies a predicted capacity of 10 reps. That prediction depends on how task failure is defined.
2. Halperin et al. pooled 12 studies with 414 participants. Healthy participants predicted their remaining reps before or during a set, then continued to task failure so researchers could compare predicted and actual repetitions.
3. Predictions averaged 0.95 reps below actual capacity, with a 95% confidence interval of 0.17 to 1.73. Results varied substantially across studies. The pooled average gives limited information about the error in a particular set.
4. The review found estimates tended to improve closer to failure and in later sets. Use RIR as an estimate when logging effort. The authors also called for clearer definitions and confirmation of task failure in future studies.

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
