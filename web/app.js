const form = document.querySelector("#claimForm");
const input = document.querySelector("#claimInput");
const button = document.querySelector("#analyzeButton");
const loading = document.querySelector("#loadingPanel");
const results = document.querySelector("#resultPanel");
const draftForm = document.querySelector("#draftForm");
const draftButton = document.querySelector("#draftButton");
const draftLoading = document.querySelector("#draftLoading");
const draftPanel = document.querySelector("#draftPanel");
const trendForm = document.querySelector("#trendForm");
const trendResults = document.querySelector("#trendResults");
const libraryForm = document.querySelector("#libraryForm");
const libraryResults = document.querySelector("#libraryResults");
let currentDraftId = null;

function percent(value) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

async function initialize() {
  try {
    const [healthResponse, metricsResponse] = await Promise.all([
      fetch("/api/health"),
      fetch("/api/metrics"),
    ]);
    const health = await healthResponse.json();
    const metrics = await metricsResponse.json();
    document.querySelector("#systemStatus").textContent =
      `${health.status} · research ${health.research_provider} · RAG ${health.rag_available ? "on" : "needs index"} · books ${health.private_textbook_available ? "local" : "not built"}`;
    document.querySelector(".pulse").classList.add("ready");
    if (metrics.dense_rag) {
      document.querySelector("#hitRate").textContent =
        percent(metrics.dense_rag.topic_pair_hit_rate_at_3);
      document.querySelector("#baselineRate").textContent =
        percent(metrics.lexical_tfidf_baseline.topic_pair_hit_rate_at_3);
      document.querySelector("#expertRate").textContent =
        percent(metrics.dense_rag.expert_hit_rate_at_3);
    }
  } catch (error) {
    document.querySelector("#systemStatus").textContent = "engine unavailable";
  }
}

function renderLibraryResults(items) {
  libraryResults.hidden = false;
  libraryResults.innerHTML = items.map((item) => `
    <article data-chunk-id="${escapeAttribute(item.chunk_id)}">
      <div class="library-result-meta">
        <span>${String(item.rank).padStart(2, "0")}</span>
        <span>${item.score == null ? "REVIEW ITEM" : `${(item.score * 100).toFixed(1)}% MATCH`}</span>
        <span>PRINTED PAGE ${item.printed_page}</span>
        <span class="review-decision">${item.review ? item.review.decision.toUpperCase() : "PENDING"}</span>
      </div>
      <h3>${escapeHtml(item.section_title)}</h3>
      <p>${escapeHtml(item.excerpt)}</p>
      <small>${escapeHtml(item.title)} · ${escapeHtml(item.review_status)}</small>
      <div class="library-actions">
        <a href="${escapeAttribute(item.source_page_url)}" target="_blank" rel="noopener">Open source page ↗</a>
        <button type="button" data-decision="approved">Approve</button>
        <button type="button" data-decision="rejected">Exclude</button>
      </div>
    </article>
  `).join("");
}

async function refreshReviewSummary() {
  const response = await fetch("/api/private-library/review-summary");
  if (!response.ok) return;
  const summary = await response.json();
  document.querySelector("#reviewSummary").textContent =
    `${summary.approved} approved · ${summary.rejected} excluded · ${summary.pending} pending`;
}

libraryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.querySelector("#libraryQuery").value.trim();
  const response = await fetch(`/api/private-library/search?q=${encodeURIComponent(query)}&limit=3`);
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.detail || "Could not search the local textbook corpus");
    return;
  }
  renderLibraryResults(payload.results);
});

document.querySelector("#loadReviewQueue").addEventListener("click", async () => {
  const response = await fetch("/api/private-library/review-queue?limit=12");
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.detail || "Could not load the review queue");
    return;
  }
  renderLibraryResults(payload.results);
  libraryResults.scrollIntoView({ behavior: "smooth", block: "start" });
});

libraryResults.addEventListener("click", async (event) => {
  const decisionButton = event.target.closest("button[data-decision]");
  if (!decisionButton) return;
  const article = decisionButton.closest("article[data-chunk-id]");
  const response = await fetch("/api/private-library/reviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chunk_id: article.dataset.chunkId,
      decision: decisionButton.dataset.decision,
      note: "Reviewed against the locally rendered source page",
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.detail || "Could not save the review decision");
    return;
  }
  article.querySelector(".review-decision").textContent = payload.review.decision.toUpperCase();
  await refreshReviewSummary();
});

trendForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const keyword = document.querySelector("#trendKeyword").value.trim();
  const response = await fetch(`/api/trends?keyword=${encodeURIComponent(keyword)}&limit=20`);
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.detail || "Could not load local trends");
    return;
  }
  trendResults.hidden = false;
  if (!payload.notes.length) {
    trendResults.innerHTML = "<p class=\"empty-state\">No local cards yet. Run the collector for this keyword first.</p>";
    return;
  }
  trendResults.innerHTML = payload.notes.map((note) => `
    <article>
      <span>${note.like_count == null ? "VISIBLE CARD" : `${note.like_count.toLocaleString()} LIKES`}</span>
      <h3>${escapeHtml(note.title)}</h3>
      <p>${escapeHtml(note.author || "Public search result")}</p>
      <a href="${escapeAttribute(note.url)}" target="_blank" rel="noopener noreferrer">Open note ↗</a>
    </article>
  `).join("");
});

draftForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  draftButton.disabled = true;
  draftLoading.hidden = false;
  draftPanel.hidden = true;
  try {
    const response = await fetch("/api/content/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: document.querySelector("#topicInput").value,
        audience: document.querySelector("#audienceInput").value,
        tone: document.querySelector("#toneInput").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Draft creation failed");
    renderDraft(payload);
    draftPanel.hidden = false;
    draftPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    alert(error.message);
  } finally {
    draftLoading.hidden = true;
    draftButton.disabled = false;
  }
});

document.querySelector("#approveButton").addEventListener("click", async () => {
  if (!currentDraftId) return;
  const acknowledged = document.querySelector("#sourceAcknowledgement").checked;
  if (!acknowledged) {
    alert("Please open and check the source links before approval.");
    return;
  }
  const response = await fetch(`/api/content/drafts/${currentDraftId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ acknowledged_sources: true }),
  });
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.detail || "Approval failed");
    return;
  }
  renderDraft(payload);
});

function renderDraft(payload) {
  currentDraftId = payload.id;
  document.querySelector("#draftTitle").textContent = payload.content.title;
  document.querySelector("#draftBody").textContent = payload.content.body;
  document.querySelector("#draftStatus").textContent = payload.status.toUpperCase();
  document.querySelector("#draftHashtags").innerHTML = payload.content.hashtags
    .map((tag) => `<span>#${escapeHtml(tag)}</span>`)
    .join("");
  const flags = payload.review.flags.length
    ? payload.review.flags
    : ["No automated warning was triggered. Original-source review is still required."];
  document.querySelector("#reviewFlags").innerHTML = flags
    .map((flag) => `<li>${escapeHtml(flag)}</li>`)
    .join("");
  document.querySelector("#carouselCards").innerHTML = payload.content.carousel
    .map((card, index) => `
      <article><span>${String(index + 1).padStart(2, "0")}</span><h4>${escapeHtml(card.heading)}</h4><p>${escapeHtml(card.copy)}</p></article>
    `)
    .join("");
  document.querySelector("#sourceList").innerHTML = payload.research.sources
    .map((source, index) => `
      <article>
        <span class="source-tier">${escapeHtml(source.source_tier)}</span>
        <div><h4>[S${index + 1}] ${escapeHtml(source.title)}</h4><p>${escapeHtml(source.snippet)}</p></div>
        <a href="${escapeAttribute(source.url)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>
      </article>
    `)
    .join("");

  const approved = payload.status === "approved";
  document.querySelector("#sourceAcknowledgement").checked = approved;
  document.querySelector("#sourceAcknowledgement").disabled = approved;
  document.querySelector("#approveButton").disabled = approved;
  document.querySelector("#approveButton").textContent = approved ? "Approved" : "Approve draft";
  const exportLink = document.querySelector("#exportLink");
  exportLink.href = `/api/content/drafts/${payload.id}/export`;
  exportLink.classList.toggle("disabled", !approved);
  exportLink.setAttribute("aria-disabled", String(!approved));
  exportLink.onclick = approved ? null : (event) => event.preventDefault();
}

document.querySelectorAll(".example-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.dataset.claim;
    input.focus();
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  loading.hidden = false;
  results.hidden = true;
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim: input.value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Analysis failed");
    renderResult(payload);
    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    alert(error.message);
  } finally {
    loading.hidden = true;
    button.disabled = false;
  }
});

function renderResult(payload) {
  document.querySelector("#resultVerdict").textContent = payload.verdict;
  document.querySelector("#resultSummary").textContent = payload.summary;
  document.querySelector("#resultReasoning").textContent = payload.reasoning;
  document.querySelector("#expertLabel").textContent = payload.expert_label;
  document.querySelector("#riskBadge").textContent = `${payload.risk.toUpperCase()} RISK`;
  document.querySelector("#modeBadge").textContent =
    `${payload.generation_mode.toUpperCase()} MODE`;

  document.querySelector("#evidenceList").innerHTML = payload.evidence
    .map((item) => `
      <article class="evidence-item">
        <span class="evidence-rank">0${item.rank}</span>
        <span class="evidence-score">SIMILARITY<strong>${(item.similarity * 100).toFixed(1)}%</strong></span>
        <div class="evidence-body">
          <h3>${escapeHtml(item.matched_claim)}</h3>
          <p>${escapeHtml(item.truth)}</p>
        </div>
        <span class="evidence-expert">${escapeHtml(item.expert_label)}</span>
      </article>
    `)
    .join("");
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
}

function escapeAttribute(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

initialize();
refreshReviewSummary();
