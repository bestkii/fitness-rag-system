const renderBlueskyDraft = (() => {
  const panel = document.querySelector("#blueskyPanel");
  const form = document.querySelector("#blueskyForm");
  const editor = document.querySelector("#blueskyEditor");
  const input = document.querySelector("#blueskyText");
  const sources = document.querySelector("#blueskySources");
  const preview = document.querySelector("#blueskyPreview");
  const count = document.querySelector("#blueskyCount");
  const myth = document.querySelector("#blueskyMyth");
  const clarification = document.querySelector("#blueskyClarification");
  const cardFigure = document.querySelector("#blueskyCardFigure");
  const cardPreview = document.querySelector("#blueskyCardPreview");
  const cardPalette = document.querySelector("#blueskyCardPalette");
  const cardMessage = document.querySelector("#blueskyCardMessage");
  const status = document.querySelector("#blueskyStatus");
  const button = document.querySelector("#blueskyPublish");
  const permalink = document.querySelector("#blueskyPermalink");
  let active = null;

  function selectedSources() {
    return Array.from(sources.querySelectorAll("input:checked"), (source) => Number(source.value));
  }

  function postText() {
    return input.value.replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, "");
  }

  function previewCard(publication) {
    if (publication?.state !== "ready") return publication?.card ?? null;
    const mythText = myth.value.trim().replace(/\s+/g, " ");
    const clarificationText = clarification.value.trim().replace(/\s+/g, " ");
    const palette = publication.next_palette;
    if (!mythText || !clarificationText || !mythCardPalettes[palette]) return null;
    const key = JSON.stringify([mythText, clarificationText, palette]);
    if (key !== active.cardKey) {
      active.card = drawMythCard(mythText, clarificationText, palette);
      active.cardKey = key;
    }
    return active.card;
  }

  function renderPreview() {
    if (!active) return;
    const { publication, submitting } = active;
    const state = publication?.state;
    const selected = selectedSources();
    const suffix = selected.length ? `\n\nSources: ${selected.map((index) => `[S${index}]`).join(" ")}` : "";
    const text = publication?.record?.text ?? (postText() ? postText() + suffix : "");
    const length = Array.from(text).length;
    const account = publication?.configured_account;
    const accountMatches = state !== "pending" || publication.account === account;
    let card;
    cardMessage.textContent = "";
    try {
      card = previewCard(publication);
      if (card) {
        const url = `data:image/jpeg;base64,${card.jpeg}`;
        if (cardPreview.getAttribute("src") !== url) cardPreview.src = url;
        cardPreview.alt = card.alt;
        cardPalette.textContent = mythCardPalettes[card.palette].name;
      } else {
        cardPreview.removeAttribute("src");
      }
    } catch (error) {
      cardMessage.textContent = error.message;
    }
    active.previewCard = card;
    cardFigure.hidden = !card;

    preview.textContent = text;
    count.textContent = `${length} / 300 characters`;
    editor.hidden = state === "pending" || state === "published";
    input.disabled = submitting;
    sources.disabled = submitting;
    myth.disabled = submitting;
    clarification.disabled = submitting;
    button.hidden = state === "published";
    button.textContent = state === "pending" ? "Retry the reviewed post" : "Publish with image";
    button.disabled = submitting || !account || !accountMatches || length > 300
      || (state !== "pending" && (!postText() || !selected.length || !card));
    permalink.hidden = state !== "published";
    if (state === "published") permalink.href = publication.permalink;
    else permalink.removeAttribute("href");

    if (submitting) status.textContent = "Checking or publishing the reviewed post…";
    else if (state === "published") status.textContent = `Published as @${publication.account}.`;
    else if (active.error) status.textContent = active.error;
    else if (!publication) status.textContent = "Checking publishing availability…";
    else if (!account) status.textContent = "Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in the local server environment to publish.";
    else if (!accountMatches) status.textContent = `Restore @${publication.account} to retry this post.`;
    else if (state === "pending") status.textContent = `Bluesky has yet to confirm the post for @${account}. Retry will check the same record.`;
    else status.textContent = `This preview will be public on @${account} when you publish.`;
  }

  function setSources(items) {
    sources.querySelectorAll("label").forEach((label) => label.remove());
    items.forEach((source, index) => {
      if (!source.url.startsWith("https://")) return;
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = String(index + 1);
      label.append(checkbox, `[S${index + 1}] ${source.title}`);
      sources.append(label);
    });
  }

  input.addEventListener("input", renderPreview);
  myth.addEventListener("input", renderPreview);
  clarification.addEventListener("input", renderPreview);
  sources.addEventListener("change", renderPreview);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!active || button.disabled || button.hidden) return;
    const current = active;
    const publication = current.publication;
    const payload = { account: publication.configured_account };
    if (publication.state !== "pending") {
      payload.text = postText();
      payload.sources = selectedSources();
      payload.card = current.previewCard;
    }
    current.submitting = true;
    current.error = "";
    renderPreview();
    try {
      current.publication = await current.request(current.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (error) {
      current.error = error.message;
      try {
        current.publication = await current.request(current.endpoint);
      } catch {
        // Retain the preview when the local status check is unavailable.
      }
    } finally {
      current.submitting = false;
      if (active === current) renderPreview();
    }
  });

  return async (draft, request) => {
    panel.hidden = draft.language !== "en" || draft.status !== "approved";
    if (panel.hidden) {
      active = null;
      return;
    }
    if (active?.id === draft.id) return;
    const current = {
      id: draft.id,
      endpoint: `/api/content/drafts/${draft.id}/publish/bluesky`,
      publication: null,
      request,
      submitting: false,
      error: "",
    };
    active = current;
    input.value = "";
    myth.value = "";
    clarification.value = "";
    setSources(draft.research.sources);
    renderPreview();
    try {
      current.publication = await request(current.endpoint);
    } catch (error) {
      current.error = error.message;
    }
    if (active === current) renderPreview();
  };
})();
