/* Research Drive — faculty chat wired to desk brain (Cursor Composer 2.5 + MCP, or MCP tools fallback). */
(function () {
  const SESSION_KEY = "procure_session_id";
  const EMAIL_KEY = "procure_user_email";
  const TOKEN_KEY = "desk_access_token";
  const GENERIC_STARTERS = [
    "What datasets does the lab already have for my area?",
    "Source a dataset we do not have yet",
    "TWSE daily prices for governance studies",
    "ETH volatility joined to GDELT Asia news",
  ];

  let chatBusy = false;
  let chatSessionId = localStorage.getItem(SESSION_KEY) || "";
  let messages = [];
  let profile = null;
  let campaigns = [];
  let pins = [];
  let pendingJobs = 0;

  function deskHeaders() {
    const h = { "Content-Type": "application/json" };
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (token) h["X-Desk-Token"] = token;
    return h;
  }

  function userEmail() {
    return (localStorage.getItem(EMAIL_KEY) || "").trim().toLowerCase();
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function slug(v) {
    return String(v || "").toLowerCase().replace(/\s+/g, "-");
  }

  function formatReply(text) {
    return esc(text).replace(/\n/g, "<br>");
  }

  function setStatus(text) {
    const el = document.getElementById("chatStatus");
    if (el) el.textContent = text || "";
  }

  function needsAuth(prompt) {
    return /\b(collect|download|approve|source this)\b/i.test(prompt);
  }

  function parseStoredMessage(m, sessionState, isLastAssistant) {
    const artifacts = m.artifacts || {};
    const statePatch = artifacts.state_patch || {};
    return {
      role: m.role,
      text: m.content,
      action: artifacts.action,
      campaignId: statePatch.campaign_id || artifacts.campaign_id || sessionState?.campaign_id,
      preview: artifacts.preview || null,
      candidates: isLastAssistant ? sessionState?.candidates || artifacts.candidates || [] : [],
      suggestedPrompts: artifacts.suggestions || artifacts.suggested_prompts || [],
      artifacts,
      blocked: artifacts.blocked,
      gate: artifacts.gate,
      pendingJobId: artifacts.job?.id || statePatch.pending_job_id || sessionState?.pending_job_id,
      registryPromotion: artifacts.registry_promotion,
      nextSteps: isLastAssistant ? artifacts.next_steps || [] : [],
      compareTable: artifacts.compare_table || null,
    };
  }

  function normalizeChatResult(out) {
    const artifacts = out.artifacts || {};
    return {
      role: "assistant",
      text: out.reply || "",
      action: out.action,
      campaignId: out.campaign_id,
      preview: out.preview || artifacts.preview || null,
      candidates: out.candidates || artifacts.candidates || [],
      suggestedPrompts: out.suggested_prompts || artifacts.suggestions || [],
      artifacts,
      blocked: artifacts.blocked,
      gate: artifacts.gate,
      pendingJobId: artifacts.job?.id || artifacts.state_patch?.pending_job_id,
      registryPromotion: out.registry_promotion || artifacts.registry_promotion,
      nextSteps: out.next_steps || artifacts.next_steps || [],
      compareTable: out.compare_table || artifacts.compare_table || null,
    };
  }

  function renderPreviewTable(preview) {
    if (!preview?.rows?.length) return "";
    const cols = preview.columns?.length ? preview.columns : Object.keys(preview.rows[0] || {});
    return `<div class="chat-preview-wrap"><table class="chat-preview"><thead><tr>${cols
      .slice(0, 8)
      .map((c) => `<th>${esc(c)}</th>`)
      .join("")}</tr></thead><tbody>${preview.rows
      .slice(0, 5)
      .map(
        (row, i) =>
          `<tr key="${i}">${cols
            .slice(0, 8)
            .map((c) => `<td title="${esc(row[c])}">${esc(String(row[c] ?? "").slice(0, 48))}</td>`)
            .join("")}</tr>`,
      )
      .join("")}</tbody></table></div>`;
  }

  function renderCandidates(candidates) {
    if (!candidates?.length) return "";
    return `<div class="chat-candidates">${candidates
      .slice(0, 8)
      .map((c) => {
        const idx = c.index ?? 0;
        const collect =
          c.collect_via && c.collect_via !== "none"
            ? `<button type="button" class="chip chat-chip primary" data-chat="download #${idx}">Collect</button>`
            : "";
        const scoreBar =
          c.score_pct != null
            ? `<div class="chat-score-bar"><span style="width:${Math.min(100, c.score_pct)}%"></span></div>`
            : "";
        const pills = [
          c.trust_tier ? `<span class="pill">${esc(c.trust_tier.replace(/_/g, " "))}</span>` : "",
          c.format && c.format !== "—" ? `<span class="pill">${esc(c.format)}</span>` : "",
          c.license && c.license !== "—" ? `<span class="pill">${esc(c.license)}</span>` : "",
        ]
          .filter(Boolean)
          .join("");
        return `<div class="chat-candidate ${c.collect_via === "none" ? "muted" : ""}">
          <div class="chat-candidate-head"><span class="mono">#${idx}</span> <strong>${esc(c.title || c.doi || "Dataset")}</strong>${c.score_pct != null ? `<span class="mono faint">${c.score_pct}%</span>` : ""}</div>
          ${scoreBar}
          <div class="chat-candidate-pills">${pills}</div>
          <div class="chat-candidate-meta mono">${esc((c.badges || []).slice(0, 2).join(" · "))}${c.publisher && c.publisher !== "—" ? ` · ${esc(c.publisher)}` : ""}${c.collect_via && c.collect_via !== "none" ? ` · via ${esc(c.collect_via)}` : ""}</div>
          <div class="chat-chips">
            <button type="button" class="chip chat-chip" data-chat="preview #${idx}">Preview</button>
            ${collect}
          </div>
        </div>`;
      })
      .join("")}</div>`;
  }

  function renderCompareTable(table) {
    if (!table?.rows?.length) return "";
    const cols = table.candidates || [];
    const head = cols.map((c) => `<th>#${c.index} ${esc(String(c.title || "").slice(0, 36))}</th>`).join("");
    const body = table.rows
      .map(
        (row) =>
          `<tr><th>${esc(row.label)}</th>${row.values.map((v) => `<td>${esc(String(v).slice(0, 64))}</td>`).join("")}</tr>`,
      )
      .join("");
    const rec = table.recommendation
      ? `<p class="mono faint">${esc(table.recommendation.reason || "")}</p>`
      : "";
    return `<div class="chat-compare-wrap"><strong>Comparison</strong><table class="chat-compare"><thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table>${rec}</div>`;
  }

  function renderPendingActions(m) {
    const artifacts = m.artifacts || {};
    const job = artifacts.job || {};
    const pendingId = m.pendingJobId || artifacts.state_patch?.pending_job_id || job.id;
    const jobPending =
      job.status === "pending_approval" ||
      (pendingId && !["completed", "running", "failed"].includes(job.status));
    const blocked = m.blocked || artifacts.blocked;
    const gate = m.gate || artifacts.gate || {};
    const licenseDoi = gate.doi || artifacts.state_patch?.pending_license_doi;
    if (!jobPending && !blocked) return "";
    let html = '<div class="chat-pending">';
    if (jobPending && pendingId) {
      html += `<button type="button" class="btn primary small" data-approve-job="${esc(pendingId)}">Launch job ${esc(String(pendingId).slice(0, 8))}…</button>`;
    }
    if (blocked && licenseDoi) {
      html += `<button type="button" class="btn primary small" data-approve-license="${esc(licenseDoi)}" data-license-text="${esc(gate.license_text || gate.license || "")}">Approve license ${esc(licenseDoi)}</button>`;
    }
    html += "</div>";
    return html;
  }

  function renderCollectOutcome(m) {
    const promo = m.registryPromotion || [];
    if (!promo.length && !m.campaignId) return "";
    let html = '<div class="chat-outcome">';
    if (m.campaignId) html += `<span class="pill connected">Campaign ${esc(String(m.campaignId).slice(0, 8))}</span>`;
    promo.forEach((p) => {
      html += `<span class="pill verified">Registry · ${esc(p.dataset_id)}</span>`;
    });
    html += "</div>";
    return html;
  }

  function renderChips(items, label) {
    if (!items?.length) return "";
    return `<div class="chat-block"><strong>${esc(label)}</strong><div class="chat-chips">${items
      .slice(0, 5)
      .map((s) => {
        const prompt = typeof s === "string" ? s : s.prompt || s.label || s;
        const text = typeof s === "string" ? s : s.label || s.prompt || s;
        return `<button type="button" class="chip chat-chip" data-chat="${esc(prompt)}">${esc(text)}</button>`;
      })
      .join("")}</div></div>`;
  }

  function renderMessage(m) {
    if (m.role === "user") {
      return `<article class="chat-msg user"><div class="chat-bubble">${formatReply(m.text)}</div></article>`;
    }
    if (m.role === "error") {
      return `<article class="chat-msg error"><div class="chat-bubble">${formatReply(m.text)}</div></article>`;
    }
    if (m.streaming) {
      return `<article class="chat-msg assistant"><div class="chat-bubble muted">Thinking…</div></article>`;
    }
    return `<article class="chat-msg assistant">
      ${m.action ? `<small class="chat-action mono">${esc(m.action)}</small>` : ""}
      <div class="chat-bubble">${formatReply(m.text)}</div>
      ${renderCollectOutcome(m)}
      ${renderCandidates(m.candidates)}
      ${renderCompareTable(m.compareTable)}
      ${renderPendingActions(m)}
      ${renderChips(m.nextSteps, "Next")}
      ${renderChips(m.suggestedPrompts, "Suggested")}
      ${renderPreviewTable(m.preview)}
    </article>`;
  }

  function renderStarters() {
    const el = document.getElementById("chatStarters");
    if (!el) return;
    if (messages.length || chatBusy) {
      el.innerHTML = "";
      el.style.display = "none";
      return;
    }
    const starters = profile?.starter_prompts?.length ? profile.starter_prompts.slice(0, 5) : GENERIC_STARTERS;
    const label = profile?.name_en ? `For ${profile.name_en.split(",")[0]}` : "Try asking";
    el.style.display = "flex";
    el.innerHTML = `<span class="chat-starter-label mono">${esc(label)}</span>${starters
      .map((s) => `<button type="button" class="chip chat-chip" data-chat="${esc(s)}">${esc(s)}</button>`)
      .join("")}`;
    el.querySelectorAll("[data-chat]").forEach((btn) => {
      btn.onclick = () => sendChat(btn.getAttribute("data-chat"));
    });
  }

  function renderChat() {
    const el = document.getElementById("answer");
    if (!el) return;
    if (!messages.length && !chatBusy) {
      el.innerHTML = "";
      renderStarters();
      return;
    }
    el.innerHTML = `<div class="chat-thread">${messages.map(renderMessage).join("")}</div>`;
    el.querySelectorAll("[data-chat]").forEach((btn) => {
      btn.onclick = () => sendChat(btn.getAttribute("data-chat"));
    });
    el.querySelectorAll("[data-approve-job]").forEach((btn) => {
      btn.onclick = () => approveJob(btn.getAttribute("data-approve-job"));
    });
    el.querySelectorAll("[data-approve-license]").forEach((btn) => {
      btn.onclick = () =>
        approveLicense(btn.getAttribute("data-approve-license"), {
          license_text: btn.getAttribute("data-license-text") || "",
        });
    });
    const thread = el.querySelector(".chat-thread");
    if (thread) thread.scrollTop = thread.scrollHeight;
    renderStarters();
  }

  async function sendChat(message) {
    const prompt = String(message || "").trim();
    if (!prompt || chatBusy) return;
    if (needsAuth(prompt) && !userEmail()) {
      setStatus("Sign in with faculty email to collect data.");
      const panel = document.getElementById("accountPanel");
      if (panel) panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    chatBusy = true;
    messages = [...messages, { role: "user", text: prompt }, { role: "assistant", streaming: true }];
    renderChat();
    setStatus("Thinking…");

    try {
      const res = await fetch("/library/chat", {
        method: "POST",
        headers: deskHeaders(),
        body: JSON.stringify({
          message: prompt,
          session_id: chatSessionId || undefined,
          user_email: userEmail() || undefined,
        }),
      });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(out.message || out.error || "Chat failed");
      if (out.session_id) {
        chatSessionId = out.session_id;
        localStorage.setItem(SESSION_KEY, chatSessionId);
      }
      const assistant = normalizeChatResult(out);
      messages = [...messages.filter((m) => !m.streaming), assistant];
      setStatus(out.campaign_id ? `Campaign ${out.campaign_id.slice(0, 8)}…` : "");
      if (["collect", "acquire", "collect_doi", "approve_collect"].includes(out.action)) {
        loadLab();
        loadPendingJobs();
        loadActivity();
        if (typeof boot === "function") boot();
      }
      const search = document.getElementById("search");
      if (search && !search.value.trim()) search.value = prompt.slice(0, 120);
    } catch (err) {
      messages = [...messages.filter((m) => !m.streaming), { role: "error", text: err.message }];
      setStatus(err.message);
    } finally {
      chatBusy = false;
      renderChat();
    }
  }

  async function approveJob(jobId) {
    if (!jobId || chatBusy) return;
    chatBusy = true;
    setStatus("Launching job…");
    try {
      const res = await fetch(`/yzu/jobs/${jobId}/approve`, {
        method: "POST",
        headers: deskHeaders(),
        body: "{}",
      });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(out.message || out.error || "Approve failed");
      messages = [
        ...messages,
        { role: "assistant", text: `Job \`${jobId}\` approved and queued on the cluster worker.`, action: "approve_collect" },
      ];
      loadLab();
      loadPendingJobs();
      loadActivity();
      setStatus("");
    } catch (err) {
      messages = [...messages, { role: "error", text: err.message }];
      setStatus(err.message);
    } finally {
      chatBusy = false;
      renderChat();
    }
  }

  async function approveLicense(doi, gate) {
    if (!doi || chatBusy) return;
    chatBusy = true;
    setStatus("Approving license…");
    try {
      const res = await fetch("/library/licenses/approve", {
        method: "POST",
        headers: deskHeaders(),
        body: JSON.stringify({
          doi,
          license: gate?.license_text || gate?.license || "",
          note: "approved via desk",
        }),
      });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(out.message || out.error || "License approval failed");
      await sendChat(`collect ${doi}`);
    } catch (err) {
      messages = [...messages, { role: "error", text: err.message }];
      setStatus(err.message);
      chatBusy = false;
      renderChat();
    }
  }

  function newSession() {
    chatSessionId = "";
    localStorage.removeItem(SESSION_KEY);
    messages = [];
    setStatus("");
    renderChat();
  }

  async function loadProfile() {
    const email = userEmail();
    if (!email) {
      profile = null;
      updateAvatar();
      renderStarters();
      return;
    }
    try {
      const data = await fetch(`/library/faculty/profile?email=${encodeURIComponent(email)}`).then((r) => r.json());
      profile = data.found ? data.profile : { email, unknown: true };
    } catch {
      profile = { email, unknown: true };
    }
    updateAvatar();
    updateRailGreeting();
    renderStarters();
  }

  function updateRailContext(asset) {
    const input = document.getElementById("chatInput");
    const lead = document.getElementById("railOsLead");
    if (!asset) {
      if (input) input.placeholder = "Describe the dataset you need, or ask about lab registry coverage…";
      return;
    }
    if (input) {
      input.placeholder = `Ask about ${asset.name} — preview, joins, procure, or schedule…`;
    }
    if (lead && asset.id) {
      lead.textContent = `Context: ${asset.name}. DeepSeek can preview rows, explain schema, estimate queries, and procure if missing.`;
    }
  }

  function updateRailGreeting() {
    const lead = document.getElementById("railOsLead");
    if (!lead || window.selected) return;
    if (profile?.name_en) {
      const surname = profile.name_en.includes(",")
        ? profile.name_en.split(",")[0]
        : profile.name_en.split(/\s+/).pop();
      lead.textContent = `${surname ? `Prof. ${surname} — ` : ""}describe what you need; I'll search DataCite, HF, BigQuery, and the lab registry, then stage collection.`;
    }
  }

  function updateAvatar() {
    const av = document.querySelector(".avatar");
    if (!av) return;
    const email = userEmail();
    if (!email) {
      av.textContent = "YZ";
      return;
    }
    const name = (profile?.name_en || "").trim();
    if (name.includes(",")) av.textContent = name.split(",")[0].slice(0, 2).toUpperCase();
    else if (name) av.textContent = (name.split(/\s+/).pop() || "?").slice(0, 2).toUpperCase();
    else av.textContent = email.slice(0, 2).toUpperCase();
  }

  async function loadLab() {
    try {
      const [camp, pinData] = await Promise.all([
        fetch("/library/campaigns?limit=12").then((r) => r.json()),
        fetch("/library/pins?limit=12").then((r) => r.json()),
      ]);
      campaigns = camp.campaigns || [];
      pins = pinData.pins || [];
      renderLabPanel();
    } catch {
      /* keep cached */
    }
  }

  async function loadPendingJobs() {
    try {
      const data = await fetch("/yzu/jobs?status=pending_approval&limit=20").then((r) => r.json());
      const jobs = data.jobs || [];
      pendingJobs = jobs.length;
      const badge = document.getElementById("pendingJobsBadge");
      if (badge) {
        badge.textContent = pendingJobs ? String(pendingJobs) : "";
        badge.style.display = pendingJobs ? "inline-flex" : "none";
      }
    } catch {
      pendingJobs = 0;
    }
  }

  function renderLabPanel() {
    const el = document.getElementById("railLabPanel");
    if (!el) return;
    const active = campaigns.filter((c) => !["ready", "failed"].includes(c.phase));
    const pinHtml = pins.length
      ? pins
          .slice(0, 6)
          .map(
            (p) =>
              `<button type="button" class="lab-item" data-chat="preview ${esc(p.handle || p.doi)}"><strong>${esc((p.title || p.handle || p.doi || "").slice(0, 48))}</strong><small class="mono">${esc(p.handle || p.doi || "")}</small></button>`,
          )
          .join("")
      : '<p class="muted small">No pinned datasets yet.</p>';
    const campHtml = active.length
      ? active
          .slice(0, 4)
          .map(
            (c) =>
              `<button type="button" class="lab-item" data-chat="Continue: ${esc(c.goal || c.id)}"><strong>${esc((c.goal || c.id || "").slice(0, 48))}</strong><small class="mono">${esc(c.phase || "active")}</small></button>`,
          )
          .join("")
      : '<p class="muted small">No active campaigns.</p>';
    el.innerHTML = `
      <div class="lab-section"><h4>Procured</h4>${pinHtml}</div>
      <div class="lab-section"><h4>Campaigns</h4>${campHtml}</div>`;
    el.querySelectorAll("[data-chat]").forEach((btn) => {
      btn.onclick = () => sendChat(btn.getAttribute("data-chat"));
    });
  }

  async function loadActivity() {
    const el = document.getElementById("activityRows");
    if (!el) return;
    try {
      const data = await fetch("/yzu/acquisitions?live=1").then((r) => r.json());
      const rows = data.acquisitions || [];
      if (!rows.length) {
        el.innerHTML = '<p class="muted" style="padding:16px 0">No active background work.</p>';
        return;
      }
      el.innerHTML = rows
        .slice(0, 10)
        .map((r) => {
          const pill = r.stage === "running" ? "Running" : r.stage === "completed" ? "Ready" : "Scheduled";
          return `<div class="activity-row"><div><strong>${esc(r.name)}</strong><div class="mono">${esc(r.amount || r.subtitle || "")}</div></div><div><span class="pill ${slug(pill)}">${pill}</span></div><div>${esc(r.destination || r.worker || "")}</div></div>`;
        })
        .join("");
    } catch {
      /* keep mock jobs */
    }
  }

  async function loadRecommended() {
    const el = document.getElementById("recommendedRows");
    if (!el) return;
    try {
      const q = (document.getElementById("search")?.value || "finance crypto dataset").trim();
      const data = await fetch(`/library/search?q=${encodeURIComponent(q)}&limit=8`).then((r) => r.json());
      const external = (data.sections || [])
        .flatMap((s) => (s.rows || []).map((row) => ({ ...row, section: s.label || s.id })))
        .filter((row) => row.kind !== "local_registry")
        .slice(0, 8);
      if (!external.length) return;
      window.recs = external.map((r, i) => ({
        id: r.doi || r.handle || `rec-${i}`,
        name: r.title || r.name || r.handle,
        provider: r.source || r.section || "External",
        state: r.kind === "datacite" ? "Indexed" : "Connected",
        trust: r.collect_via && r.collect_via !== "none" ? "Inferred" : "Not acquired",
        reason: r.reason || r.subtitle || "Candidate for faculty procurement.",
      }));
      document.getElementById("recCount").textContent = String(window.recs.length);
      if (typeof render === "function") render();
    } catch {
      /* keep mock recs */
    }
  }

  async function loadDatasetPreview(asset) {
    const tab = document.getElementById("tab-preview");
    if (!tab || !asset || !asset.id) return;
    tab.innerHTML = '<h3>Preview</h3><p class="muted">Loading preview…</p>';
    try {
      const data = await fetch(`/query/${encodeURIComponent(asset.id)}?limit=8`).then((r) => r.json());
      const rows = data.rows || data.preview || [];
      if (!rows.length) {
        tab.innerHTML =
          '<h3>Preview</h3><p class="muted">No preview rows yet. <button type="button" class="btn primary small" id="previewAsk">Ask DeepSeek to query this</button></p>';
        document.getElementById("previewAsk")?.addEventListener("click", () =>
          sendChat(`Preview rows from ${asset.name} (${asset.id})`),
        );
        return;
      }
      const cols = Object.keys(rows[0] || {});
      tab.innerHTML = `<h3>Preview</h3><table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows
        .map((row) => `<tr>${cols.map((c) => `<td>${esc(row[c])}</td>`).join("")}</tr>`)
        .join("")}</tbody></table>`;
    } catch {
      tab.innerHTML =
        '<h3>Preview</h3><p class="muted">Preview unavailable. <button type="button" class="btn primary small" id="previewAsk">Ask DeepSeek</button></p>';
      document.getElementById("previewAsk")?.addEventListener("click", () =>
        sendChat(`Query and preview ${asset.name} (${asset.id})`),
      );
    }
  }

  function wireQueryTab(asset) {
    const tab = document.getElementById("tab-query");
    if (!tab || !asset) return;
    tab.innerHTML = `<h3>Query</h3>
      <textarea id="datasetQueryInput" placeholder="Ask DeepSeek or write SQL…">select * from ${esc(asset.tables?.[0] || asset.id)} limit 100;</textarea>
      <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
        <button type="button" class="btn primary" id="queryAskDeepSeek">Ask DeepSeek</button>
        <button type="button" class="btn" id="queryEstimate">Estimate via chat</button>
      </div>`;
    document.getElementById("queryAskDeepSeek")?.addEventListener("click", () => {
      const sql = document.getElementById("datasetQueryInput")?.value || "";
      sendChat(`Run or estimate this query on ${asset.name} (${asset.id}):\n${sql}`);
    });
    document.getElementById("queryEstimate")?.addEventListener("click", () => {
      sendChat(`Estimate cost and rows for ${asset.id} with a sensible default query.`);
    });
  }

  function wireAccount() {
    const side = document.querySelector(".side");
    if (!side || document.getElementById("accountPanel")) return;
    const wrap = document.createElement("div");
    wrap.id = "accountPanel";
    wrap.className = "account-panel";
    wrap.innerHTML = `
      <label class="mono">Faculty email</label>
      <input id="facultyEmail" type="email" placeholder="you@saturn.yzu.edu.tw" value="${esc(userEmail())}" />
      <small class="muted">Personalized starters · collect approvals · job launch</small>`;
    side.appendChild(wrap);
    const input = document.getElementById("facultyEmail");
    input.addEventListener("change", () => {
      const v = input.value.trim().toLowerCase();
      if (v) localStorage.setItem(EMAIL_KEY, v);
      else localStorage.removeItem(EMAIL_KEY);
      loadProfile();
    });
    if (userEmail()) loadProfile();
  }

  async function restoreSession(sid) {
    if (!sid) return;
    try {
      const data = await fetch(`/library/chat/${sid}`).then((r) => (r.ok ? r.json() : null));
      if (!data?.messages) return;
      const state = data.state || {};
      let lastAssistantIdx = -1;
      data.messages.forEach((m, i) => {
        if (m.role === "assistant") lastAssistantIdx = i;
      });
      messages = data.messages.map((m, i) => parseStoredMessage(m, state, i === lastAssistantIdx));
      renderChat();
    } catch {
      /* fresh */
    }
  }

  function wireOs() {
    wireAccount();
    const search = document.getElementById("search");
    const askBtn = document.getElementById("ask");
    const chatInput = document.getElementById("chatInput");
    const chatNew = document.getElementById("chatNew");
    const recRefresh = document.getElementById("recRefresh");

    function submitSearch() {
      const q = (search && search.value.trim()) || "";
      if (!q) return;
      sendChat(q);
    }

    if (askBtn) askBtn.onclick = submitSearch;
    if (chatNew) chatNew.onclick = newSession;
    if (recRefresh) recRefresh.onclick = () => loadRecommended();
    if (search) {
      search.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          submitSearch();
        }
      });
    }
    if (chatInput) {
      chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendChat(chatInput.value);
          chatInput.value = "";
        }
      });
      const sendBtn = document.getElementById("chatSend");
      if (sendBtn) {
        sendBtn.onclick = () => {
          sendChat(chatInput.value);
          chatInput.value = "";
        };
      }
    }

    window.updateRailContext = updateRailContext;
    if (window.selected) updateRailContext(window.selected);

    const origOpen = window.openAsset;
    if (typeof origOpen === "function") {
      window.openAsset = function (a) {
        origOpen(a);
        loadDatasetPreview(a);
        wireQueryTab(a);
      };
    }

    document.querySelectorAll("[data-tab]").forEach((b) => {
      b.addEventListener("click", () => {
        if (b.dataset.tab === "preview" && window.selected) loadDatasetPreview(window.selected);
      });
    });

    const origShow = typeof show === "function" ? show : null;
    if (origShow) {
      window.show = function (v) {
        origShow(v);
        if (v === "activity") loadActivity();
        if (v === "recommended") loadRecommended();
      };
    }

    loadActivity();
    loadRecommended();
    loadLab();
    loadPendingJobs();
    if (chatSessionId) restoreSession(chatSessionId);
    else renderStarters();
  }

  window.sendChat = sendChat;
  window.loadDatasetPreview = loadDatasetPreview;
  document.addEventListener("DOMContentLoaded", wireOs);
  if (document.readyState !== "loading") wireOs();
})();
