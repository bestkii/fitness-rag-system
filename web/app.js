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
const toast = document.querySelector("#toast");
const uiLanguage = document.documentElement.lang.toLowerCase().startsWith("en") ? "en" : "zh";
const communityPanel = document.querySelector("#communityPanel");
const topicInput = document.querySelector("#topicInput");
let communitySourceUrl = null;
let currentDraftId = null;
let toastTimer = null;

const interfaceCopy = {
  en: {
    requestFailed: "Request failed. Check the local service.",
    backendUnavailable: "The local backend is not ready. The static architecture remains available.",
    openSourcePage: "Open source page ↗",
    approve: "Approve",
    exclude: "Exclude",
    libraryUnavailable: "Local textbook corpus unavailable",
    libraryResults: (count) => `${count} result${count === 1 ? "" : "s"} returned from the local staging corpus.`,
    reviewSaved: "Local review decision saved.",
    noTrendCards: "No local cards exist for this keyword. Run the bounded collector manually first.",
    openCard: "Open card ↗",
    draftReady: "Content pack generated. Human source review is still required.",
    acknowledgeFirst: "Open and verify the original sources before approval.",
    draftApproved: "Draft approved. The text pack can now be exported.",
    openSource: "Open source ↗",
    approved: "Approved",
    approveDraft: "Approve draft",
  },
  zh: {
    requestFailed: "请求失败，请检查本地服务。",
    backendUnavailable: "本地后端尚未就绪；静态项目架构仍可浏览。",
    openSourcePage: "打开原始页 ↗",
    approve: "批准",
    exclude: "排除",
    libraryUnavailable: "本地教材库未就绪",
    libraryResults: (count) => `已从本地 staging corpus 返回 ${count} 条结果。`,
    reviewSaved: "本地审核决定已保存。",
    noTrendCards: "本地暂无该关键词的卡片。请先手动运行有界采集器。",
    openCard: "打开原卡片 ↗",
    draftReady: "内容包已生成，等待人工来源审核。",
    acknowledgeFirst: "请先打开并核查原始来源，再确认审核。",
    draftApproved: "草稿已批准，现在可以导出文本包。",
    openSource: "打开来源 ↗",
    approved: "已批准",
    approveDraft: "批准草稿",
  },
};

function t(key, ...args) {
  const value = interfaceCopy[uiLanguage][key];
  return typeof value === "function" ? value(...args) : value;
}

function percent(value, digits = 2) {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function showToast(message, type = "info") {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.toggle("error", type === "error");
  toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 4200);
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(payload.detail) ? payload.detail[0]?.msg : payload.detail;
    throw new Error(detail || t("requestFailed"));
  }
  return payload;
}

function setupTabs() {
  const tabs = [...document.querySelectorAll("[data-tab]")];
  const panels = [...document.querySelectorAll("[data-tab-panel]")];
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      tabs.forEach((item) => item.setAttribute("aria-selected", String(item === tab)));
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.tabPanel !== target;
      });
    });
  });
}

async function initialize() {
  setupTabs();
  try {
    const [health, metrics] = await Promise.all([
      requestJson("/api/health"),
      requestJson("/api/metrics"),
    ]);
    document.querySelector("#systemStatus").textContent =
      `${health.status} · research ${health.research_provider} · RAG ${health.rag_available ? "on" : "needs index"} · books ${health.private_textbook_available ? "local" : "not built"}`;
    document.querySelector(".pulse").classList.add("ready");
    document.querySelector("#researchState").textContent =
      `${health.research_provider || "PubMed + Crossref"} · ready`;
    document.querySelector("#ragState").textContent =
      health.rag_available ? "BGE + ChromaDB · ready" : "Vector index unavailable";
    document.querySelector("#booksState").textContent =
      health.private_textbook_available ? "Local corpus · ready" : "Local corpus not built";
    document.querySelector("#ragNode").classList.toggle("is-live", Boolean(health.rag_available));
    document.querySelector("#reviewNode").classList.toggle("is-live", Boolean(health.private_textbook_available));

    if (metrics.dense_rag) {
      const denseHit = metrics.dense_rag.topic_pair_hit_rate_at_3;
      const baselineHit = metrics.lexical_tfidf_baseline.topic_pair_hit_rate_at_3;
      document.querySelector("#hitRate").textContent = percent(denseHit);
      document.querySelector("#baselineRate").textContent = percent(baselineHit);
      document.querySelector("#expertRate").textContent =
        `${percent(metrics.dense_rag.expert_hit_rate_at_3)} expert Hit@3`;
      document.querySelector("#heroHitRate").textContent = percent(denseHit);
      document.querySelector("#denseHitBar").style.setProperty("--value", percent(denseHit));
      document.querySelector("#baselineHitBar").style.setProperty("--value", percent(baselineHit));
    }
  } catch (error) {
    document.querySelector("#systemStatus").textContent = "engine unavailable";
    showToast(t("backendUnavailable"), "error");
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
        <a href="${escapeAttribute(item.source_page_url)}" target="_blank" rel="noopener">${t("openSourcePage")}</a>
        <button type="button" data-decision="approved">${t("approve")}</button>
        <button type="button" data-decision="rejected">${t("exclude")}</button>
      </div>
    </article>
  `).join("");
}

async function refreshReviewSummary() {
  try {
    const summary = await requestJson("/api/private-library/review-summary");
    document.querySelector("#reviewSummary").textContent =
      `${summary.approved} approved · ${summary.rejected} excluded · ${summary.pending} pending`;
  } catch (error) {
    document.querySelector("#reviewSummary").textContent = t("libraryUnavailable");
  }
}

libraryForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.querySelector("#libraryQuery").value.trim();
  try {
    const payload = await requestJson(`/api/private-library/search?q=${encodeURIComponent(query)}&limit=3`);
    renderLibraryResults(payload.results);
    showToast(t("libraryResults", payload.count));
  } catch (error) {
    showToast(error.message, "error");
  }
});

document.querySelector("#loadReviewQueue")?.addEventListener("click", async () => {
  try {
    const payload = await requestJson("/api/private-library/review-queue?limit=12");
    renderLibraryResults(payload.results);
    libraryResults.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message, "error");
  }
});

libraryResults?.addEventListener("click", async (event) => {
  const decisionButton = event.target.closest("button[data-decision]");
  if (!decisionButton) return;
  const article = decisionButton.closest("article[data-chunk-id]");
  try {
    const payload = await requestJson("/api/private-library/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chunk_id: article.dataset.chunkId,
        decision: decisionButton.dataset.decision,
        note: "Reviewed against the locally rendered source page",
      }),
    });
    article.querySelector(".review-decision").textContent = payload.review.decision.toUpperCase();
    await refreshReviewSummary();
    showToast(t("reviewSaved"));
  } catch (error) {
    showToast(error.message, "error");
  }
});

trendForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const keyword = document.querySelector("#trendKeyword").value.trim();
  try {
    const payload = await requestJson(`/api/trends?keyword=${encodeURIComponent(keyword)}&limit=20`);
    trendResults.hidden = false;
    if (!payload.notes.length) {
      trendResults.innerHTML = `<p class="empty-state">${t("noTrendCards")}</p>`;
      return;
    }
    trendResults.innerHTML = payload.notes.map((note) => `
      <article>
        <span>${note.like_count == null ? "VISIBLE CARD" : `${note.like_count.toLocaleString()} LIKES`}</span>
        <h3>${escapeHtml(note.title)}</h3>
        <p>${escapeHtml(note.author || "Public search result")}</p>
        <a href="${escapeAttribute(note.url)}" target="_blank" rel="noopener noreferrer">${t("openCard")}</a>
      </article>
    `).join("");
  } catch (error) {
    showToast(error.message, "error");
  }
});

function attachCommunitySource(url) {
  communitySourceUrl = url;
  const link = document.querySelector("#attachedCommunityLink");
  if (url) {
    link.href = url;
  } else {
    link.removeAttribute("href");
  }
  document.querySelector("#attachedCommunitySource").hidden = !url;
}

function setupCommunityQuestions() {
  const refresh = document.querySelector("#refreshCommunity");
  const status = document.querySelector("#communityStatus");
  const list = document.querySelector("#communityQuestions");
  const dateFormat = new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" });
  let attempted = false;

  function renderCandidate(candidate) {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = `#${candidate.tag} · ${dateFormat.format(new Date(candidate.created_at))}`;
    const link = document.createElement("a");
    link.href = candidate.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open original post";
    const select = document.createElement("button");
    select.type = "button";
    select.textContent = "Use as topic";
    select.addEventListener("click", () => {
      attachCommunitySource(candidate.url);
      topicInput.focus();
    });
    item.append(label, link, select);
    return item;
  }

  async function load() {
    if (refresh.disabled) return;
    attempted = true;
    refresh.disabled = true;
    status.textContent = "Loading possible questions from Mastodon…";
    const unavailable = () => {
      status.textContent = list.children.length
        ? "Both feeds are unavailable. Showing the previous results."
        : "Both feeds are unavailable. You can still enter a topic manually.";
    };
    try {
      const payload = await requestJson("/api/community/questions", { cache: "no-store" });
      if (payload.unavailable_tags.length === 2) {
        unavailable();
        return;
      }
      list.replaceChildren(...payload.questions.map(renderCandidate));
      const count = payload.questions.length;
      const result = count === 0
        ? "No possible English questions found in the available feeds."
        : `Found ${count} possible English question${count === 1 ? "" : "s"}.`;
      const missing = payload.unavailable_tags.length ? ` #${payload.unavailable_tags[0]} is unavailable.` : "";
      status.textContent = result + missing;
    } catch (error) {
      status.textContent = list.children.length
        ? "Refresh failed. Showing the previous results."
        : "Could not load community questions. You can still enter a topic manually.";
    } finally {
      refresh.disabled = false;
    }
  }

  refresh.addEventListener("click", load);
  communityPanel.addEventListener("toggle", () => {
    if (communityPanel.open && !attempted) load();
  });
  document.querySelector("#clearCommunitySource").addEventListener("click", () => {
    attachCommunitySource(null);
    topicInput.focus();
  });
  if (communityPanel.open) load();
}

draftForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  draftButton.disabled = true;
  draftLoading.hidden = false;
  draftPanel.hidden = true;
  try {
    const payload = await requestJson("/api/content/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: topicInput.value,
        audience: document.querySelector("#audienceInput").value,
        tone: document.querySelector("#toneInput").value,
        language: uiLanguage,
        community_source_url: communitySourceUrl,
      }),
    });
    renderDraft(payload);
    if (communityPanel) {
      const url = new URL(window.location.href);
      url.searchParams.set("draft", payload.id);
      window.history.replaceState(null, "", url);
    }
    draftPanel.hidden = false;
    draftPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    showToast(t("draftReady"));
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    draftLoading.hidden = true;
    draftButton.disabled = false;
  }
});

document.querySelector("#approveButton").addEventListener("click", async () => {
  if (!currentDraftId) return;
  const acknowledged = document.querySelector("#sourceAcknowledgement").checked;
  if (!acknowledged) {
    showToast(t("acknowledgeFirst"), "error");
    return;
  }
  try {
    const payload = await requestJson(`/api/content/drafts/${currentDraftId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledged_sources: true }),
    });
    renderDraft(payload);
    showToast(t("draftApproved"));
  } catch (error) {
    showToast(error.message, "error");
  }
});

function renderDraft(payload) {
  currentDraftId = payload.id;
  document.querySelector("#draftTitle").textContent = payload.content.title;
  document.querySelector("#draftBody").textContent = payload.content.body;
  document.querySelector("#draftStatus").textContent = payload.status.toUpperCase();
  document.querySelector("#draftHashtags").innerHTML = payload.content.hashtags
    .map((tag) => `<span>#${escapeHtml(tag)}</span>`).join("");
  if (communityPanel) {
    const link = document.querySelector("#draftCommunityLink");
    if (payload.community_source_url) {
      link.href = payload.community_source_url;
    } else {
      link.removeAttribute("href");
    }
    document.querySelector("#draftCommunitySource").hidden = !payload.community_source_url;
  }
  const flags = payload.review.flags.length
    ? payload.review.flags
    : ["No automated warning was triggered. Original-source review is still required."];
  document.querySelector("#reviewFlags").innerHTML = flags
    .map((flag) => `<li>${escapeHtml(flag)}</li>`).join("");
  document.querySelector("#carouselCards").innerHTML = payload.content.carousel
    .map((card, index) => `<article><span>${String(index + 1).padStart(2, "0")}</span><h4>${escapeHtml(card.heading)}</h4><p>${escapeHtml(card.copy)}</p></article>`).join("");
  document.querySelector("#sourceList").innerHTML = payload.research.sources
    .map((source, index) => `
      <article>
        <span class="source-tier">${escapeHtml(source.source_tier)}</span>
        <div><h4>[S${index + 1}] ${escapeHtml(source.title)}</h4><p>${escapeHtml(source.snippet)}</p></div>
        <a href="${escapeAttribute(source.url)}" target="_blank" rel="noopener noreferrer">${t("openSource")}</a>
      </article>
    `).join("");

  const approved = payload.status === "approved";
  document.querySelector("#sourceAcknowledgement").checked = approved;
  document.querySelector("#sourceAcknowledgement").disabled = approved;
  document.querySelector("#approveButton").disabled = approved;
  document.querySelector("#approveButton").textContent = approved ? t("approved") : t("approveDraft");
  const exportLink = document.querySelector("#exportLink");
  exportLink.href = `/api/content/drafts/${payload.id}/export`;
  exportLink.classList.toggle("disabled", !approved);
  exportLink.setAttribute("aria-disabled", String(!approved));
  exportLink.onclick = approved ? null : (event) => event.preventDefault();
  if (communityPanel) renderBlueskyDraft(payload, requestJson);
}

async function restoreEnglishDraft() {
  const id = new URLSearchParams(window.location.search).get("draft");
  if (!id) return;
  try {
    const draft = await requestJson(`/api/content/drafts/${encodeURIComponent(id)}`);
    if (draft.language !== "en") throw new Error("This draft belongs to the Chinese workspace.");
    if (currentDraftId) return;
    topicInput.value = draft.topic;
    attachCommunitySource(draft.community_source_url);
    renderDraft(draft);
    draftPanel.hidden = false;
  } catch (error) {
    showToast(error.message, "error");
  }
}

document.querySelectorAll(".example-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.dataset.claim;
    input.focus();
  });
});

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  loading.hidden = false;
  results.hidden = true;
  try {
    const payload = await requestJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim: input.value }),
    });
    renderResult(payload);
    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message, "error");
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
  document.querySelector("#modeBadge").textContent = `${payload.generation_mode.toUpperCase()} MODE`;
  document.querySelector("#evidenceList").innerHTML = payload.evidence
    .map((item) => `
      <article class="evidence-item">
        <span class="evidence-rank">0${item.rank}</span>
        <span class="evidence-score">SIMILARITY<strong>${(item.similarity * 100).toFixed(1)}%</strong></span>
        <div class="evidence-body"><h3>${escapeHtml(item.matched_claim)}</h3><p>${escapeHtml(item.truth)}</p></div>
        <span class="evidence-expert">${escapeHtml(item.expert_label)}</span>
      </article>
    `).join("");
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
}

function escapeAttribute(value) {
  return String(value)
    .replaceAll("&", "&amp;").replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

initialize();
if (libraryForm) refreshReviewSummary();
if (communityPanel) {
  setupCommunityQuestions();
  restoreEnglishDraft();
}
