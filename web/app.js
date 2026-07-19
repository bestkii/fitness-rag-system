const form = document.querySelector("#claimForm");
const input = document.querySelector("#claimInput");
const button = document.querySelector("#analyzeButton");
const loading = document.querySelector("#loadingPanel");
const results = document.querySelector("#resultPanel");

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
      `${health.status} · ${health.indexed_records} records · top-${health.top_k}`;
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

initialize();
