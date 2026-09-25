/* studio.js — the Studio's views, wired to the real runtime.
 *
 * House rule that shapes most of this file: when the runtime refuses something,
 * the UI shows the refusal, its reason and its hint. It never quietly renders an
 * empty panel, because "you cannot read this" and "this is empty" are different
 * facts and conflating them would misrepresent the very thing being demonstrated.
 */
(function () {
  "use strict";

  /* ── tiny helpers ─────────────────────────────────────────────────── */
  const $ = sel => document.querySelector(sel);
  const $$ = sel => Array.from(document.querySelectorAll(sel));
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html !== undefined) n.innerHTML = html;
    return n;
  };
  const esc = s => String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  async function api(path, body) {
    const opts = body
      ? { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body) }
      : {};
    const res = await fetch(path, opts);
    const json = await res.json().catch(() => ({ ok: false, error: "bad_response" }));
    return json;
  }

  let toastTimer = null;
  function toast(msg, kind) {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "toast" + (kind ? " " + kind : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add("hidden"), 4200);
  }

  const state = {
    knowledge: null,
    loops: [],
    field: null,
    field3d: null,
    selectedRegion: null,
    viewAs: "",
    stages: [],
    currentExp: null,
    traceTimer: null,
    gateTimer: null,
    gateTraceRoles: []
  };

  /* ── tabs ─────────────────────────────────────────────────────────── */
  $$("#tabs button").forEach(btn => {
    btn.addEventListener("click", () => {
      $$("#tabs button").forEach(b => b.classList.toggle("active", b === btn));
      const view = btn.dataset.view;
      $$(".view").forEach(v => v.classList.toggle("hidden", v.dataset.view !== view));
      if (view === "semantic") initSemantic();
      if (view === "window") refreshWindow();
      if (view === "evidence") refreshEvidence();
      if (view === "mission") initMission();
      if (view === "gate") initGate();
      // Leaving a tab stops its poller. The trace timer historically kept
      // running in the background; a second one doing the same would turn a
      // quirk into a pattern.
      if (view !== "gate") { clearInterval(state.gateTimer); state.gateTimer = null; }
    });
  });

  /* ── overview ─────────────────────────────────────────────────────── */
  function renderCounts(k) {
    const c = k.counts;
    $("#counts").innerHTML = [
      ["concepts", c.concepts], ["skills", c.skills], ["agents", c.agents],
      ["loops", c.loops], ["roster", c.roster],
      ["validated", (c.loops_by_status || {}).validated || 0]
    ].map(([label, v]) =>
      `<div class="stat"><b>${v}</b><span>${label}</span></div>`).join("");

    $("#sources").innerHTML = Object.entries(k.sources)
      .map(([key, v]) => `<dt>${esc(key)}</dt><dd>${esc(v)}</dd>`).join("");

    $("#brand-sub").textContent =
      `${c.concepts} concepts · ${c.skills} skills · ${c.agents} agents · ${c.loops} loops`;
  }

  function renderRoute(r) {
    const box = $("#route-result");
    if (!r.ok) { box.innerHTML = `<div class="refusal"><b>${esc(r.error)}</b></div>`; return; }

    const scores = (r.concept_scores || []).slice(0, 5)
      .map(s => `<span class="chip">${esc(s.concept)} <b>${s.score}</b></span>`).join(" ");

    if (r.decision === "loop_hit") {
      const l = r.loop;
      box.innerHTML = `
        <div class="allowed">Loop hit — a hardened loop already covers this, partition included.</div>
        <div class="chainview">${scores}</div>
        <div class="loop"><div>
          <div class="lt">${esc(l.title)}</div>
          <div class="lm">${esc(l.id)} · ${(l.agent_stages || l.roles || []).length} stages</div>
        </div><div class="lacts">
          <span class="pill ${esc(l.status)}">${esc(l.status)}</span>
          <button class="primary tiny" data-bind="${esc(l.id)}">Bind SCWs</button>
        </div></div>
        ${(r.alternatives || []).length
          ? `<p class="muted small">Also matched: ${r.alternatives.map(esc).join(", ")}</p>` : ""}`;
      box.querySelector("[data-bind]").addEventListener("click", e =>
        bindLoop(e.target.dataset.bind));
    } else if (r.decision === "fallback_skill") {
      box.innerHTML = `
        <div class="residue"><b>No loop matched.</b> This is the loop-assembly path —
        the skills below are the material a new loop would be built from, and this
        decision is itself recorded as experimental data.</div>
        <div class="chainview">${scores}</div>
        <div class="chainview">${r.skills.map(s =>
          `<span class="chip">${esc(s.title || s.skill)} <b>${s.score}</b></span>`).join("")}</div>
        <button class="ghost tiny" id="to-designer">Build this loop in the Designer →</button>`;
      $("#to-designer").addEventListener("click", () =>
        $$("#tabs button").find(b => b.dataset.view === "designer").click());
    } else {
      box.innerHTML = `
        <div class="residue"><b>No loop and no skill matched.</b> Falling through to
        the agent roster — the deepest fallback there is.</div>
        <div class="chainview">${scores || '<span class="muted small">no concept scored above zero</span>'}</div>
        <div class="chainview">${(r.agents || []).map(a =>
          `<span class="chip">${esc(a.agent)} ${esc(a.name)}</span>`).join("")
          || '<span class="muted small">nothing in the roster matched either</span>'}</div>`;
    }
  }

  $("#route-go").addEventListener("click", async () => {
    const task = $("#route-input").value.trim();
    if (!task) return;
    renderRoute(await api("/api/route", { task }));
  });
  $("#route-input").addEventListener("keydown", e => {
    if (e.key === "Enter") $("#route-go").click();
  });

  /* ── concepts ─────────────────────────────────────────────────────── */
  function renderConcepts() {
    const counts = {};
    state.loops.forEach(l => (l.concept_tags || []).forEach(c => {
      counts[c] = (counts[c] || 0) + 1;
    }));
    $("#concept-grid").innerHTML = state.knowledge.concepts.map(c => `
      <div class="concept" data-concept="${esc(c.id)}">
        <span class="count">${counts[c.id] || 0}</span>
        <b>${esc(c.title || c.id)}</b>
        <div class="ct">${esc(c.concept_type || "")}</div>
        <div class="tags">${(c.tags || []).slice(0, 6)
          .map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      </div>`).join("");

    $$("#concept-grid .concept").forEach(node => {
      node.addEventListener("click", () => {
        $("#filter-concept").value = node.dataset.concept;
        $$("#tabs button").find(b => b.dataset.view === "loops").click();
        renderLoops();
      });
    });
  }

  /* ── loops ────────────────────────────────────────────────────────── */
  function renderLoops() {
    const fc = $("#filter-concept").value;
    const fs = $("#filter-status").value;
    const ft = $("#filter-text").value.toLowerCase().trim();

    const rows = state.loops.filter(l =>
      (!fc || (l.concept_tags || []).includes(fc)) &&
      (!fs || l.status === fs) &&
      (!ft || l.title.toLowerCase().includes(ft) || l.id.toLowerCase().includes(ft)));

    $("#loop-list").innerHTML = rows.length ? rows.map(l => {
      const h = l.hardening || {};
      const bindable = l.execution_mode === "in-window";
      return `
      <div class="loop" data-id="${esc(l.id)}">
        <div>
          <div class="lt">${esc(l.title)}</div>
          <div class="lm">${esc(l.id)} · ${l.stages} stages · ${esc(l.topology || "")}
            ${h.reduction_ratio ? " · ratio " + h.reduction_ratio : ""}
            ${h.negative_controls_refused ? " · NC " + esc(h.negative_controls_refused) : ""}</div>
        </div>
        <div class="lacts">
          <span class="pill ${esc(l.status)}">${esc(l.status)}</span>
          <button class="ghost tiny" data-detail="${esc(l.id)}">Detail</button>
          ${bindable ? `<button class="primary tiny" data-bind="${esc(l.id)}">Bind</button>`
                     : `<span class="chip" title="Cross-window: separate model calls, no shared buffer. Run it for real from Claude Code with /maxey0:cross-window ${esc(l.id)}">cross-window</span>`}
        </div>
      </div>`;
    }).join("") : `<p class="muted">No loops match those filters.</p>`;

    $$("#loop-list [data-bind]").forEach(b =>
      b.addEventListener("click", () => bindLoop(b.dataset.bind)));
    $$("#loop-list [data-detail]").forEach(b =>
      b.addEventListener("click", () => showLoopDetail(b.dataset.detail, b)));
  }

  async function showLoopDetail(id, btn) {
    const card = btn.closest(".loop");
    const existing = card.querySelector(".loopdetail");
    if (existing) { existing.remove(); return; }

    const res = await api(`/api/loop?id=${encodeURIComponent(id)}`);
    if (!res.ok) { toast("Could not load " + id, "bad"); return; }
    const l = res.loop, h = l.hardening || {};

    const stages = (l.agent_stages || []).map(s =>
      `<span class="chip role">${esc(s.agent_id)}</span><span class="arrow">→</span>`).join("");
    const roles = (l.roles || []).map(r =>
      `<span class="chip role">${esc(r)}</span><span class="arrow">→</span>`).join("");

    const d = el("div", "loopdetail", `
      <div class="chainview">${(stages || roles).replace(/<span class="arrow">→<\/span>$/, "")}</div>
      <div class="grid-3">
        <div><h4>Hardening</h4><div class="kv small">
          <dt>checked</dt><dd>${h.checked}</dd>
          <dt>passed</dt><dd>${h.passed}</dd>
          <dt>bound_holds</dt><dd>${h.bound_holds}</dd>
          <dt>widest read</dt><dd>${h.widest_read_closure ?? "—"}</dd>
          <dt>ratio</dt><dd>${h.reduction_ratio ?? "—"}</dd>
          <dt>neg. controls</dt><dd>${esc(h.negative_controls_refused || "—")}</dd>
        </div></div>
        <div><h4>Tags</h4>
          <div class="tags">${(l.concept_tags || [])
            .map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
          <div class="tags" style="margin-top:6px">${(l.skill_tags || [])
            .map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
        </div>
        <div><h4>Provenance</h4><div class="kv small">
          <dt>provenance</dt><dd>${esc(l.provenance)}</dd>
          <dt>mode</dt><dd>${esc(l.execution_mode)}</dd>
          <dt>sources</dt><dd>${(l.source_files || []).map(esc).join("<br>")}</dd>
        </div></div>
      </div>
      ${(h.breaches || []).length ? `<div class="refusal"><b>Containment breach recorded</b>
        <p>${esc(JSON.stringify(h.breaches))}</p></div>` : ""}
      ${l.notes ? `<p class="muted small" style="margin-top:8px">${esc(l.notes)}</p>` : ""}`);
    card.appendChild(d);
  }

  async function bindLoop(id) {
    const res = await api("/api/bind", { loop_id: id });
    if (!res.ok) {
      toast(res.message || res.error, "bad");
      return;
    }
    toast(`Bound ${res.instance}: ${res.roles.length} roles, ` +
          `${res.refused_negative_controls} negative controls refused`, "ok");
    $$("#tabs button").find(b => b.dataset.view === "window").click();
    refreshWindow();
  }

  ["#filter-concept", "#filter-status"].forEach(s =>
    $(s).addEventListener("change", renderLoops));
  $("#filter-text").addEventListener("input", renderLoops);

  /* ── designer ─────────────────────────────────────────────────────── */
  function renderPalette(filter) {
    const q = (filter || "").toLowerCase();
    const agents = state.knowledge.agents.filter(a =>
      !q || a.name.toLowerCase().includes(q) ||
      a.registry_index.toLowerCase().includes(q) ||
      (a.specialization || "").toLowerCase().includes(q));

    $("#agent-palette").innerHTML = agents.map(a => `
      <div class="pagent" draggable="true"
           data-id="${esc(a.registry_index)}" data-name="${esc(a.name)}">
        <b>${esc(a.registry_index)}</b> ${esc(a.name)}
        <span>${esc(a.specialization || "")}</span>
      </div>`).join("");

    $$("#agent-palette .pagent").forEach(node => {
      node.addEventListener("dragstart", e => {
        e.dataTransfer.setData("text/plain", JSON.stringify({
          agent_id: node.dataset.id, agent_name: node.dataset.name
        }));
        e.dataTransfer.effectAllowed = "copy";
      });
      node.addEventListener("click", () =>
        addStage(node.dataset.id, node.dataset.name));
    });
  }

  function addStage(agent_id, agent_name) {
    state.stages.push({ agent_id, agent_name });
    renderStages();
  }

  function renderStages() {
    const strip = $("#stage-strip");
    if (!state.stages.length) {
      strip.innerHTML = `<div class="stage-empty">Drop agents here to build the pipeline</div>`;
      $("#design-save").disabled = true;
      return;
    }
    strip.innerHTML = state.stages.map((s, i) => {
      const role = `stage${i}-${s.agent_id.toLowerCase()}`;
      return `
      <div class="stage" draggable="true" data-i="${i}">
        <button class="rm" data-rm="${i}" title="remove">×</button>
        <div class="sn">stage ${i}</div>
        <b>${esc(s.agent_id)}</b>
        <span>${esc(s.agent_name)}</span>
        <div class="scw">pad: ${esc(role)}-pad<br>out: ${esc(role)}-out</div>
      </div>`;
    }).join("");

    $$("#stage-strip [data-rm]").forEach(b => b.addEventListener("click", e => {
      e.stopPropagation();
      state.stages.splice(Number(b.dataset.rm), 1);
      renderStages();
    }));

    let dragFrom = null;
    $$("#stage-strip .stage").forEach(node => {
      node.addEventListener("dragstart", e => {
        dragFrom = Number(node.dataset.i);
        node.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        // Marks this as an internal reorder, distinct from a palette drop.
        e.dataTransfer.setData("text/plain", JSON.stringify({ reorder: dragFrom }));
      });
      node.addEventListener("dragend", () => node.classList.remove("dragging"));
      node.addEventListener("dragover", e => e.preventDefault());
      node.addEventListener("drop", e => {
        e.preventDefault();
        e.stopPropagation();
        const to = Number(node.dataset.i);
        if (dragFrom === null || dragFrom === to) return;
        const [moved] = state.stages.splice(dragFrom, 1);
        state.stages.splice(to, 0, moved);
        dragFrom = null;
        renderStages();
      });
    });

    $("#design-save").disabled = true;   // must re-harden after any edit
    $("#design-result").innerHTML =
      `<p class="muted small">${state.stages.length} stages — press Harden to build
       this against a real window before saving.</p>`;
  }

  const strip = $("#stage-strip");
  strip.addEventListener("dragover", e => {
    e.preventDefault();
    strip.classList.add("dragover");
  });
  strip.addEventListener("dragleave", () => strip.classList.remove("dragover"));
  strip.addEventListener("drop", e => {
    e.preventDefault();
    strip.classList.remove("dragover");
    let payload;
    try { payload = JSON.parse(e.dataTransfer.getData("text/plain")); }
    catch (_) { return; }
    if (payload && payload.agent_id) addStage(payload.agent_id, payload.agent_name);
  });

  $("#agent-search").addEventListener("input", e => renderPalette(e.target.value));

  $("#design-preview").addEventListener("click", async () => {
    if (!state.stages.length) { toast("Add at least one stage", "bad"); return; }
    const res = await api("/api/designer/preview", {
      title: $("#design-title").value || "Untitled loop",
      slug: ($("#design-title").value || "untitled").toLowerCase().replace(/\s+/g, "-"),
      agent_stages: state.stages
    });
    const box = $("#design-result");
    if (!res.ok) {
      box.innerHTML = `<div class="refusal"><b>${esc(res.error)}</b>
        <p>${esc(res.message)}</p></div>`;
      $("#design-save").disabled = true;
      return;
    }
    const h = res.hardening;
    box.innerHTML = `
      <div class="${h.passed ? "allowed" : "residue"}">
        <b>${h.passed ? "Hardened" : "Built, with a problem"}</b> —
        built for real against a live ContextWindow.
      </div>
      <div class="kv small" style="margin-top:8px">
        <dt>roles</dt><dd>${res.roles.length}</dd>
        <dt>regions</dt><dd>${res.regions.length}</dd>
        <dt>bound_holds</dt><dd>${h.bound_holds}</dd>
        <dt>widest read closure</dt><dd>${h.widest_read_closure}</dd>
        <dt>negative controls refused</dt><dd>${esc(h.negative_controls_refused)}</dd>
        <dt>flat/partitioned ratio</dt><dd>${h.reduction_ratio}</dd>
      </div>
      <p class="muted small">${esc(h.verdict)}</p>`;
    $("#design-save").disabled = false;
  });

  $("#design-save").addEventListener("click", async () => {
    const title = $("#design-title").value || "Untitled loop";
    const res = await api("/api/designer/save", {
      title, slug: title.toLowerCase().replace(/\s+/g, "-"),
      agent_stages: state.stages, notes: "Designed in Maxey0 Studio."
    });
    if (!res.ok) { toast(res.message || res.error, "bad"); return; }
    toast(`Saved ${res.saved} (${res.status})`, "ok");
    await loadLoops();
    renderLoops();
  });

  /* ── window ───────────────────────────────────────────────────────── */
  async function refreshWindow() {
    const snap = await api("/api/window");
    if (!snap.ok) return;
    $("#run-badge").textContent = snap.run_id + " · " + snap.events + " events";

    const sel = $("#view-as");
    const prev = sel.value;
    sel.innerHTML = `<option value="">host (unbound)</option>` +
      snap.loops.map(l => `<option value="${esc(l.loop_id)}">${esc(l.loop_id)}</option>`).join("");
    sel.value = snap.loops.some(l => l.loop_id === prev) ? prev : "";
    state.viewAs = sel.value;

    const closure = new Set();
    if (state.viewAs) {
      const me = snap.loops.find(l => l.loop_id === state.viewAs);
      (me ? me.read_closure : []).forEach(r => closure.add(r));
    }

    const tree = $("#region-tree");
    tree.innerHTML = snap.regions.length ? snap.regions.map(r => {
      const reachable = !state.viewAs || closure.has(r.scw_id);
      return `
      <div class="rnode ${state.selectedRegion === r.scw_id ? "sel" : ""}"
           data-id="${esc(r.scw_id)}" style="padding-left:${9 + (r.depth || 0) * 16}px">
        <div>
          <span class="rid">${esc(r.scw_id)}</span>
          ${reachable ? "" : `<span class="lock" title="outside this role's read closure">⊘</span>`}
          <div class="muted" style="font-size:11px">${esc(r.label || "")}</div>
        </div>
        <div class="row">
          <span class="rt ${esc(r.region_type)}">${esc(r.region_type)}</span>
          <span class="rtok">${r.tokens ?? 0}t</span>
        </div>
      </div>`;
    }).join("") : `<p class="muted">No regions yet. Bind a loop from the Loops tab.</p>`;

    $$("#region-tree .rnode").forEach(node =>
      node.addEventListener("click", () => selectRegion(node.dataset.id)));

    if (state.selectedRegion) selectRegion(state.selectedRegion, true);
    refreshTrace();
  }

  $("#view-as").addEventListener("change", e => {
    state.viewAs = e.target.value;
    refreshWindow();
  });

  async function selectRegion(scw_id, keep) {
    state.selectedRegion = scw_id;
    if (!keep) {
      $$("#region-tree .rnode").forEach(n =>
        n.classList.toggle("sel", n.dataset.id === scw_id));
    }
    const q = `/api/region?id=${encodeURIComponent(scw_id)}` +
      (state.viewAs ? `&as_loop=${encodeURIComponent(state.viewAs)}` : "");
    const r = await api(q);
    const box = $("#region-detail");
    $("#region-title").textContent = "— " + scw_id;

    if (!r.ok) {
      box.innerHTML = `<div class="refusal"><b>${esc(r.error)}</b></div>`;
      return;
    }

    let head = "";
    if (r.scope_check) {
      head = r.scope_check.allowed
        ? `<div class="allowed">✓ <code>${esc(r.scope_check.as_loop)}</code>
             may read this region — the runtime allowed the call.</div>`
        : `<div class="refusal"><b>${esc(r.scope_check.error)}</b>
             <p>${esc(r.scope_check.message)}</p>
             ${r.scope_check.hint ? `<div class="hint">↳ ${esc(r.scope_check.hint)}</div>` : ""}
             <p class="muted small">Contents are withheld because the runtime refused
             the read — not because the region is empty.</p></div>`;
    }

    const meta = `<div class="kv small" style="margin-bottom:10px">
      <dt>type</dt><dd>${esc(r.region_type)}</dd>
      <dt>lifecycle</dt><dd>${esc(r.lifecycle)}</dd>
      <dt>tokens</dt><dd>${r.tokens}</dd>
      <dt>revision</dt><dd>${r.revision}</dd>
      <dt>bridgeable</dt><dd>${r.policy.bridgeable}</dd>
      <dt>mutability</dt><dd>${esc(r.policy.mutability)}</dd>
      <dt>reset each tick</dt><dd>${r.policy.reset_each_tick}</dd>
    </div>`;

    const entries = r.entries.length
      ? r.entries.map(e => `
        <div class="entry">
          <div class="eh"><span>${esc(e.entry_id)}</span>
            ${e.key ? `<span>key=${esc(e.key)}</span>` : ""}
            <span>${e.tokens}t</span><span>by ${esc(e.written_by)}</span>
            <span>tick ${e.tick}</span></div>
          <pre>${esc(e.data)}</pre>
        </div>`).join("")
      : (r.scope_check && !r.scope_check.allowed
          ? "" : `<p class="muted">This region is genuinely empty.</p>`);

    box.innerHTML = head + meta + entries;
  }

  async function refreshTrace() {
    const r = await api("/api/trace?limit=120");
    if (!r.ok) return;
    $("#trace-list").innerHTML = r.events.slice().reverse().map(e => {
      const cls = e.type.includes("denied") ? "denied"
        : e.type.startsWith("route.") ? "route" : "";
      const p = e.payload || {};
      const summary = p.scw_id || p.loop_id || p.reason || p.task || p.harness_id || "";
      return `<div class="tev">
        <span class="seq">${e.seq}</span>
        <span class="ty ${cls}">${esc(e.type)}</span>
        <span class="pl">${esc(String(summary).slice(0, 120))}</span>
        <span class="dg">${esc(e.digest)}</span>
      </div>`;
    }).join("") || `<p class="muted">No events yet.</p>`;
  }

  $("#trace-refresh").addEventListener("click", refreshTrace);
  $("#trace-auto").addEventListener("change", e => {
    clearInterval(state.traceTimer);
    if (e.target.checked) state.traceTimer = setInterval(refreshWindow, 2000);
  });

  /* ── gate ─────────────────────────────────────────────────────────────
     What the delegated agents did, as opposed to what the host did to the
     window. Polls rather than streams: the coding session writes the journal
     from a different OS process, so there is nothing to push from — a server
     push would be this same poll, moved. */

  function gateContainment(c, chain, damaged) {
    if (!c) return `<p class="muted">No gate activity recorded yet.</p>`;
    const held = c.held === null
      ? `<span class="pill residue">not established</span>`
      : c.held
        ? `<span class="pill allowed">held</span>`
        : `<span class="pill denied">BREACHED</span>`;
    const claim = c.claimable
      ? `<span class="pill allowed">claimable</span>`
      : `<span class="pill residue">not claimable</span>`;
    const r = c.residue || {};
    const rows = [
      ["evaluated", c.evaluated], ["allowed", c.allowed], ["denied", c.denied],
      ["observed only", c.observed_only]
    ].map(([k, v]) => `<span class="chip">${esc(k)}: ${esc(v)}</span>`).join("");
    const res = [
      ["fail-open", r.fail_open], ["gate errors", r.gate_errors],
      ["unattributed", r.unattributed], ["lost records", r.damaged_records]
    ].filter(([, v]) => v).map(([k, v]) =>
      `<span class="chip residue">${esc(k)}: ${esc(v)}</span>`).join("");
    // Ambient calls are shown but are NOT residue: no role was dispatched, so
    // there is no containment claim for them to weaken.
    const amb = c.ambient_calls
      ? `<p class="muted"><span class="chip">ambient: ${esc(c.ambient_calls)}</span>
           subagents that were never dispatched as SCW roles — shown for
           completeness, not counted against containment.</p>`
      : "";
    const chainNote = chain && !chain.ok
      ? `<div class="refusal">Gate journal chain broken after ${esc(chain.verified_prefix)} records.
           <div class="hint">Records past the break are not evidence.</div></div>`
      : "";
    return `<p>${held} ${claim}</p>
      <p>${rows}</p>
      ${res ? `<p><strong>Residue</strong> ${res}</p>` : ""}
      ${amb}
      ${chainNote}
      <p class="muted">${esc(c.note || "")}</p>`;
  }

  function gateRoles(roles) {
    if (!roles || !roles.length) return `<p class="muted">No role has been dispatched yet.</p>`;
    const traceBy = {};
    (state.gateTraceRoles || []).forEach(t => {
      traceBy[t.loop_id === null ? "(unattributed)" : t.loop_id] = t;
    });
    return roles.map(r => {
      // `actor` is set for the two non-role rows: "(host)" is the orchestrator
      // that built the partition and is governed by no policy; "(unattributed)"
      // is residue. They must not render alike.
      const key = r.actor || r.loop_id;
      const t = traceBy[key] || {};
      const name = r.actor === "(host)"
        ? `<span class="chip">host — the orchestrator, governed by no policy</span>`
        : r.actor === "(ambient)"
          ? `<span class="chip">ambient — a subagent that was never dispatched as an SCW role</span>`
          : r.actor === "(unattributed)"
            ? `<span class="pill residue">unattributed</span>`
            : `<code>${esc(r.loop_id)}</code>`;
      const tools = Object.entries(r.tools || {})
        .map(([tn, n]) => `<span class="chip">${esc(tn)} ×${esc(n)}</span>`).join("");
      const how = Object.entries(r.attribution || {})
        .map(([h, n]) => `<span class="chip">${esc(h)} ×${esc(n)}</span>`).join("");
      const denied = (r.denied_examples || []).map(d =>
        `<div class="refusal">${esc(d.tool)} → ${esc(d.reason_code)}<br>${esc(d.message)}
           ${d.hint ? `<div class="hint">${esc(d.hint)}</div>` : ""}</div>`).join("");
      // the context half of the join: what the runtime handed this role
      const ctx = t.transfers_in !== undefined
        ? `<span class="chip">${esc(t.transfers_in)} transfers in</span>
           <span class="chip">${esc(t.tokens_in || 0)} tokens in</span>`
        : "";
      const finding = t.finding
        ? `<p class="muted"><strong>Finding:</strong> ${esc(t.finding)}</p>` : "";
      return `<div class="detail">
        <p>${name}
          ${ctx}
          <span class="chip">${esc(r.attempts)} calls</span>
          <span class="chip allowed">${esc(r.allowed)} allowed</span>
          <span class="chip denied">${esc(r.denied)} denied</span>
          ${r.residue ? `<span class="chip residue">${esc(r.residue)} residue</span>` : ""}
        </p>
        <p>${tools}</p>
        <p class="muted">attributed by: ${how || "—"}</p>
        ${finding}
        ${denied}
      </div>`;
    }).join("");
  }

  const LEVEL_LABEL = {
    L0_none: "L0 — none", L1_logical: "L1 — logical",
    L2_execution: "L2 — execution", L3_observed: "L3 — observed"
  };

  function gateIsolation(iso) {
    if (!iso || !iso.evidenced) return `<p class="muted">Not assessed.</p>`;
    const ev = LEVEL_LABEL[iso.evidenced] || iso.evidenced;
    const cls = iso.evidenced === "L3_observed" ? "allowed"
      : iso.evidenced === "L0_none" ? "denied" : "residue";
    const declared = iso.declared
      ? (iso.holds
        ? `<span class="chip allowed">declared ${esc(LEVEL_LABEL[iso.declared] || iso.declared)} — met</span>`
        : `<span class="chip denied">declared ${esc(LEVEL_LABEL[iso.declared] || iso.declared)} — NOT met</span>`)
      : "";
    const reasons = (iso.reasons || [])
      .map(r => `<li>${esc(r)}</li>`).join("");
    const shortfall = (iso.shortfall || [])
      .map(s => `<li>${esc(s)}</li>`).join("");
    const g = iso.guarantees || {};
    const sig = Object.entries(iso.signals || {})
      .map(([k, v]) => `<span class="chip">${esc(k.replace(/_/g, " "))}: ${esc(
        Array.isArray(v) ? (v.join(", ") || "—") : v)}</span>`).join("");
    return `
      <p><span class="pill ${cls}">${esc(ev)}</span> ${declared}</p>
      ${reasons ? `<p><strong>Evidence</strong></p><ul>${reasons}</ul>` : ""}
      ${shortfall ? `<div class="refusal"><b>Shortfall</b><ul>${shortfall}</ul></div>` : ""}
      <p>${sig}</p>
      ${g.may_claim ? `<p class="muted"><strong>May claim:</strong> ${esc(g.may_claim)}</p>` : ""}
      ${g.may_not_claim ? `<div class="residue"><b>May not claim</b>
         <ul><li>${esc(g.may_not_claim)}</li></ul></div>` : ""}
      ${iso.note ? `<p class="muted">${esc(iso.note)}</p>` : ""}`;
  }

  async function refreshGate() {
    const role = $("#gate-role").value;
    const kind = $("#gate-kind").value;
    const declared = $("#gate-declared").value;
    const qs = ["limit=200"];
    if (role) qs.push("loop_id=" + encodeURIComponent(role));
    if (kind) qs.push("kinds=" + encodeURIComponent(kind));

    const [feed, roles, iso, tr] = await Promise.all([
      api("/api/live/gate?" + qs.join("&")),
      api("/api/live/gate/roles"),
      api("/api/live/isolation" + (declared ? "?declared=" + encodeURIComponent(declared) : "")),
      api("/api/live/traces?limit=1")
    ]);
    $("#gate-isolation").innerHTML = gateIsolation(iso);
    state.gateTraceRoles = (tr && tr.by_role) || [];

    if (feed.available === false) {
      $("#gate-containment").innerHTML =
        `<p class="muted">${esc(feed.message || "No gate journal yet.")}</p>`;
      $("#gate-roles").innerHTML = "";
      $("#gate-list").innerHTML = `<p class="muted">No agent tool call has been intercepted.</p>`;
      $("#gate-chain").textContent = "no journal";
      return;
    }

    $("#gate-chain").textContent = feed.chain
      ? (feed.chain.ok ? `chain ok · ${feed.chain.records}` : "CHAIN BROKEN")
      : "—";

    $("#gate-containment").innerHTML = gateContainment(
      roles.summary && roles.summary.containment, feed.chain, feed.damaged);
    $("#gate-roles").innerHTML = gateRoles(roles.roles);

    // keep the role filter populated from what actually appeared
    const seen = (roles.roles || []).map(r => r.loop_id).filter(Boolean);
    const sel = $("#gate-role");
    const keep = sel.value;
    sel.innerHTML = `<option value="">all roles</option>` +
      seen.map(r => `<option value="${esc(r)}">${esc(r)}</option>`).join("");
    sel.value = keep;

    $("#gate-list").innerHTML = (feed.events || []).slice().reverse().map(e => {
      const cls = e.kind === "refusal" ? "denied"
        : e.kind === "allowed" ? "allowed"
        : e.kind === "residue" ? "residue" : "";
      const who = e.loop_id || "(unattributed)";
      const what = e.resource ? String(e.resource).slice(0, 90) : (e.reason_code || "");
      return `<div class="tev">
        <span class="seq">${esc(e.seq)}</span>
        <span class="ty ${cls}">${esc(e.tool || e.type)}</span>
        <span class="pl"><code>${esc(who)}</code> ${esc(what)}</span>
        <span class="dg">${esc(e.verdict || "")}</span>
      </div>`;
    }).join("") || `<p class="muted">No events match this filter.</p>`;
  }

  function initGate() {
    refreshGate();
  }

  $("#gate-refresh").addEventListener("click", refreshGate);
  $("#gate-role").addEventListener("change", refreshGate);
  $("#gate-kind").addEventListener("change", refreshGate);
  $("#gate-declared").addEventListener("change", refreshGate);
  $("#gate-auto").addEventListener("change", e => {
    clearInterval(state.gateTimer);
    state.gateTimer = e.target.checked ? setInterval(refreshGate, 2000) : null;
  });

  $("#btn-verify").addEventListener("click", async () => {
    const r = await api("/api/verify");
    toast(r.verified
      ? `Chain verified over ${r.events} events; replay ${r.replay_identical
          ? "reproduced the window exactly" : "DIVERGED"}`
      : `Chain broken: ${r.message}`,
      r.verified && r.replay_identical ? "ok" : "bad");
  });

  $("#btn-reset").addEventListener("click", async () => {
    if (!confirm("Tear down the live window and start a fresh run?")) return;
    await api("/api/reset", {});
    state.selectedRegion = null;
    toast("Window reset", "ok");
    refreshWindow();
  });

  /* ── semantic 3D ──────────────────────────────────────────────────── */
  async function initSemantic() {
    if (!state.field3d) {
      state.field3d = new Field3D($("#field3d"));
      state.field3d.onHover = (node, mx, my) => {
        const tip = $("#field-tip");
        if (!node) { tip.classList.add("hidden"); return; }
        tip.classList.remove("hidden");
        tip.innerHTML = `<b>${esc(node.label)}</b>
          <div class="tl">${esc(node.level)} · ${esc(node.id)}</div>
          ${node.dominant ? `<div class="tl">nearest anchor: ${esc(node.dominant)}</div>`
                          : `<div class="tl">unanchored — parked on the edge ring</div>`}
          <div class="tags" style="margin-top:5px">${(node.tags || []).slice(0, 6)
            .map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>`;
        const wrap = tip.parentElement.getBoundingClientRect();
        tip.style.left = Math.min(mx + 14, wrap.width - 310) + "px";
        tip.style.top = Math.max(6, my - 10) + "px";
      };
      ["concept", "skill", "agent", "edges"].forEach(k =>
        $("#lv-" + k).addEventListener("change", e =>
          state.field3d.setVisible(k, e.target.checked)));
      $("#cam-reset").addEventListener("click", () => state.field3d.resetCamera());
    }
    if (!state.field) {
      state.field = await api("/api/field");
      $("#semantic-method").textContent = state.field.method +
        ` — ${state.field.stats.nodes} nodes, ${state.field.stats.edges} edges, ` +
        `${state.field.stats.unanchored} unanchored`;
    }
    state.field3d.setData(state.field);
    state.field3d.resize();
  }

  /* -- evidence: containment, tested rather than declared ---------------
   *
   * Four HTTP routes existed, were documented, and were never fetched by this
   * file: /api/containment, /api/observability, /api/observability/attempts.
   * So the four containment assertions and the typed event stream -- the
   * sharpest evidence the product produces -- had no surface at all, and the
   * only way to see them was to call the tools from a session.
   *
   * Every row here says whether it is an attempt or a computation, because a
   * set computation over the region graph is a weaker claim than a read the
   * runtime actually refused, and a view that showed them identically would be
   * overstating what the run established.
   */
  async function refreshEvidence() {
    await Promise.all([refreshContainment(), refreshLevel(), refreshStream()]);
  }

  async function refreshContainment() {
    const box = $("#ev-containment");
    const r = await api("/api/containment");
    if (!r.ok) {
      box.innerHTML = `<div class="refusal"><b>${esc(r.error || "unavailable")}</b>
        <p>${esc(r.message || "")}</p>
        <p class="em">No roles are bound, so there is nothing to contain. That
        is not a clean result &mdash; it is no result.</p></div>`;
      return;
    }

    const c = r.containment, probed = r.probed || {};
    const dis = probed.closure_disagreements || [];
    const regions = Object.keys((probed.matrix || {})[Object.keys(probed.matrix || {})[0]] || {});

    box.innerHTML = `
      <div class="${c.bound_holds ? "allowed" : "refusal"}">
        <b>bound_holds = ${c.bound_holds}</b>
        <p>${esc(c.verdict)}</p>
        ${(c.breaches || []).map(b => `<p>BREACH: <code>${esc(b.loop)}</code>
          reached ${esc(JSON.stringify(b.reached))}</p>`).join("")}
      </div>
      <p class="em">Computed over the region graph &mdash; a statement about a
      data structure.</p>

      <h3>Probed &mdash; a real read attempted per cell</h3>
      <div class="statgrid">
        <div class="stat"><b>${probed.refused ?? "-"}</b><span>refused</span></div>
        <div class="stat"><b>${probed.granted ?? "-"}</b><span>authorized</span></div>
        <div class="stat"><b>${probed.cells ?? "-"}</b><span>cells</span></div>
      </div>
      ${regions.length ? `<table class="rep">
        <tr><th>role</th>${regions.map(x => `<th>${esc(x)}</th>`).join("")}</tr>
        ${Object.entries(probed.matrix).map(([role, row]) => `<tr>
          <td><b>${esc(role)}</b></td>
          ${regions.map(x => `<td class="${row[x] ? "" : "bad"}">${
            row[x] ? "read" : "refused"}</td>`).join("")}
        </tr>`).join("")}</table>` : ""}
      <p class="em">Each refusal above was produced by the enforcement layer and
      is a record in the ledger that replay reproduces.</p>

      <div class="${dis.length ? "refusal" : "allowed"}">
        <b>closure disagreements: ${dis.length}</b>
        ${dis.length
          ? `<p>The computation and the attempt disagree. One of them is wrong,
             and that is a defect rather than a measurement.</p>
             ${dis.map(d => `<p><code>${esc(d.loop)}</code> &rarr;
               <code>${esc(d.region)}</code>: call said ${d.call},
               closure said ${d.closure}</p>`).join("")}`
          : "<p>Every cell agrees with its closure.</p>"}
      </div>`;
  }

  async function refreshLevel() {
    const box = $("#ev-level");
    const declared = $("#ev-declared").value;
    const q = declared ? `?declared=${encodeURIComponent(declared)}` : "";
    const r = await api(`/api/live/isolation${q}`);
    if (!r.ok) {
      box.innerHTML = `<div class="refusal"><b>${esc(r.error || "unavailable")}</b></div>`;
      return;
    }
    const short = r.shortfall;
    box.innerHTML = `
      <div class="statgrid">
        <div class="stat"><b>${esc(r.evidenced || "-")}</b><span>evidenced</span></div>
        <div class="stat"><b>${esc(r.declared || "-")}</b><span>declared</span></div>
      </div>
      ${short ? `<div class="refusal"><b>Shortfall</b><p>${esc(
        typeof short === "string" ? short : JSON.stringify(short))}</p></div>` : ""}`;
  }

  async function refreshStream() {
    const box = $("#ev-stream");
    const params = new URLSearchParams();
    const kind = $("#ev-kind").value, role = $("#ev-role").value.trim(),
          region = $("#ev-region").value.trim();
    if (kind) params.set("kinds", kind);
    if (role) params.set("loop_id", role);
    if (region) params.set("scw_id", region);

    const r = await api(`/api/observability?${params}`);
    if (!r.ok) {
      box.innerHTML = `<div class="refusal"><b>${esc(r.error || "unavailable")}</b></div>`;
      return;
    }

    let attempts = "";
    if (role || region) {
      const a = await api(`/api/observability/attempts?${params}`);
      if (a.ok) {
        // Three-valued on purpose. Null is not a pass.
        const v = a.contained;
        const cls = v === true ? "allowed" : v === false ? "refusal" : "";
        attempts = `<div class="${cls}"><b>contained = ${
          v === null || v === undefined ? "null" : v}</b>
          ${v === null || v === undefined
            ? "<p>No attempt was recorded. This establishes nothing either way.</p>"
            : ""}</div>`;
      }
    }

    // The endpoint returns two different shapes on purpose: a summary of the
    // whole run when nothing is filtered, and a projected list when something
    // is. Reading `events` as a list either way silently renders "no events"
    // over a run that had thousands.
    if (!Array.isArray(r.events)) {
      const kinds = Object.entries(r.by_kind || {});
      const refusals = Object.entries(r.refusals_by_loop || {});
      box.innerHTML = attempts + `
        <div class="statgrid">
          <div class="stat"><b>${r.events ?? 0}</b><span>events</span></div>
          <div class="stat"><b>${refusals.reduce((n, [, v]) => n + v, 0)}</b>
            <span>refusals</span></div>
          <div class="stat"><b>${Object.keys(r.regions_refused || {}).length}</b>
            <span>regions refused</span></div>
        </div>
        ${kinds.length ? `<table class="rep"><tr><th>kind</th><th>events</th></tr>
          ${kinds.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`)
            .join("")}</table>` : ""}
        ${refusals.length ? `<h3>Refusals by role</h3>
          <table class="rep"><tr><th>role</th><th>refused</th></tr>
          ${refusals.map(([k, v]) => `<tr><td><code>${esc(k)}</code></td>
            <td>${v}</td></tr>`).join("")}</table>` : ""}
        <p class="em">Summary of the whole run. Filter by kind, role or region
        above for the individual events.</p>`;
      return;
    }

    const events = r.events;
    box.innerHTML = attempts + (events.length
      ? `<p class="em">${r.matched} matched, ${r.returned} shown.</p>
         <table class="rep"><tr><th>seq</th><th>kind</th><th>type</th>
           <th>role</th><th>region</th></tr>
         ${events.slice(-120).reverse().map(e => `<tr>
           <td>${e.seq ?? ""}</td><td>${esc(e.kind || "")}</td>
           <td><code>${esc(e.type || "")}</code></td>
           <td>${esc(e.loop_id || "-")}</td>
           <td>${esc(e.scw_id || "-")}</td></tr>`).join("")}</table>`
      : `<p class="muted">No events match this filter. An empty stream is not
         evidence of containment; it is an absence of evidence.</p>`);
  }

  $("#ev-refresh").addEventListener("click", refreshEvidence);
  $("#ev-declared").addEventListener("change", refreshLevel);
  $("#ev-kind").addEventListener("change", refreshStream);
  $("#ev-role").addEventListener("change", refreshStream);
  $("#ev-region").addEventListener("change", refreshStream);

  /* ── mission control ──────────────────────────────────────────────── */
  const mc = { catalog: null, source: "studio", page: 0, regions: [], note: "" };
  const MC_PAGE_SIZE = 9;

  function mcInitFabric() {
    const canvas = $("#mc-fabric");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const style = getComputedStyle(document.documentElement);
    const accent = style.getPropertyValue("--accent").trim() || "#6ea8fe";
    const warn = style.getPropertyValue("--warn").trim() || "#fbbf24";
    let w, h, dpr = Math.min(2, window.devicePixelRatio || 1);
    const N = 110, LINK = 120;
    const nodes = [];
    function resize() {
      w = window.innerWidth; h = window.innerHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener("resize", resize);
    for (let i = 0; i < N; i++) {
      nodes.push({ x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - .5) * .1, vy: (Math.random() - .5) * .1, heat: 0 });
    }
    mc._pulse = () => {
      for (let i = 0; i < 4; i++) nodes[Math.floor(Math.random() * nodes.length)].heat = 1;
    };
    function frame() {
      ctx.clearRect(0, 0, w, h);
      for (const n of nodes) {
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0) n.x = w; if (n.x > w) n.x = 0;
        if (n.y < 0) n.y = h; if (n.y > h) n.y = 0;
        n.heat *= .94;
      }
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < LINK) {
            const heat = Math.max(a.heat, b.heat);
            const alpha = (1 - d / LINK) * .1 + heat * .4;
            ctx.strokeStyle = (heat > .15 ? warn : accent) + Math.round(Math.min(alpha, .8) * 255).toString(16).padStart(2, "0");
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  async function mcLoadCatalog() {
    const r = await api("/api/mission/catalog");
    if (!r.ok) { toast("Failed to load mission catalog", "bad"); return; }
    mc.catalog = r.catalog;
    $("#mc-concept").innerHTML = `<option value="">— any —</option>` +
      mc.catalog.concepts.map(c =>
        `<option value="${esc(c.id)}">${esc(c.title)} (${c.skill_count})</option>`).join("");
  }

  function mcConcept() { return mc.catalog.concepts.find(c => c.id === $("#mc-concept").value); }
  function mcSkill() {
    const c = mcConcept();
    return c && c.skills.find(s => s.id === $("#mc-skill").value);
  }

  function mcOnConceptChange() {
    const c = mcConcept();
    const sel = $("#mc-skill");
    sel.disabled = !c;
    sel.innerHTML = `<option value="">— any —</option>` +
      (c ? c.skills.map(s => `<option value="${esc(s.id)}">${esc(s.title)}</option>`).join("") : "");
    mcOnSkillChange();
  }

  function mcOnSkillChange() {
    const s = mcSkill();
    $("#mc-skill-desc").textContent = s ? s.description : "";
    const sel = $("#mc-agent");
    sel.disabled = !s;
    sel.innerHTML = `<option value="">— unbound —</option>` +
      (s ? s.agents.map(a => `<option value="${esc(a.slug)}">${esc(a.name)} (${esc(a.role)})</option>`).join("") : "");
  }

  async function mcLoadKeyStatus() {
    const r = await api("/api/mission/config");
    const box = $("#mc-key-status");
    if (r.ok && r.anthropic.configured) {
      box.innerHTML = `<span style="color:var(--ok)">configured</span> — dispatch calls the real Claude API (${esc(r.anthropic.model)})`;
      $("#mc-mode-badge").textContent = "mode: real api";
    } else {
      box.innerHTML = `not configured — dispatch runs the timed simulation. Set <code>ANTHROPIC_API_KEY</code> or a <code>.env</code> next to server/ to enable real calls.`;
      $("#mc-mode-badge").textContent = "mode: simulated";
    }
  }

  async function mcFetchRegions() {
    if (mc.source === "live") {
      const r = await api("/api/live/session");
      if (!r.ok || !r.available) {
        mc.note = r.message || "no live session activity recorded";
        return [];
      }
      const chain = r.chain_intact ? "chain intact" : "chain integrity broken (concurrent writers on this machine)";
      mc.note = `${r.source === "this_session" ? "this coding session" : "last recorded session"} · ` +
        `run ${esc(r.window.run_id)} · ${r.window.record_count} events · ${chain} · read-only mirror`;
      return r.window.regions || [];
    }
    const r = await api("/api/window");
    mc.note = r.ok ? `studio's own standalone window · run ${esc(r.run_id)}` : "";
    return r.ok ? r.regions : [];
  }

  async function mcRefresh() {
    mc.regions = await mcFetchRegions();
    $("#mc-live-note").classList.toggle("hidden", mc.source !== "live");
    $("#mc-live-note").textContent = mc.note;
    $("#mc-source-label").textContent = mc.source === "live" ? "— read-only" : "— create/dispatch here";
    $("#mc-new-fields").style.display = mc.source === "live" ? "none" : "";
    $("#mc-drop").style.display = mc.source === "live" ? "none" : "";
    $("#mc-dispatch").disabled = mc.source === "live";
    mcPopulateTargetSelect();
    if (mc.page * MC_PAGE_SIZE >= mc.regions.length) mc.page = 0;
    mcRenderGrid();
  }

  function mcPopulateTargetSelect() {
    const sel = $("#mc-target");
    const keep = sel.value;
    const opts = mc.source === "live" ? [] : [`<option value="__new__">+ new scw</option>`];
    sel.innerHTML = opts.concat(mc.regions.map(r =>
      `<option value="${esc(r.scw_id)}">${esc(r.label)} [${esc(r.region_type)}]</option>`)).join("");
    if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
    $("#mc-new-fields").style.display = (mc.source !== "live" && sel.value === "__new__") ? "" : "none";
  }

  function mcRenderGrid() {
    const total = mc.regions.length;
    const pages = Math.max(1, Math.ceil(total / MC_PAGE_SIZE));
    mc.page = Math.min(mc.page, pages - 1);
    const start = mc.page * MC_PAGE_SIZE;
    const slice = mc.regions.slice(start, start + MC_PAGE_SIZE);
    $("#mc-pageinfo").textContent = total
      ? `regions ${start + 1}–${Math.min(total, start + MC_PAGE_SIZE)} of ${total} · page ${mc.page + 1}/${pages}`
      : "no regions yet";
    $("#mc-prev").disabled = mc.page <= 0;
    $("#mc-next").disabled = mc.page >= pages - 1;

    const grid = $("#mc-grid");
    grid.innerHTML = "";
    const cellCount = Math.max(slice.length, 1);
    for (let i = 0; i < MC_PAGE_SIZE; i++) {
      const r = slice[i];
      const cell = el("div", "mc-cell" + (r ? "" : " empty"));
      if (!r) { cell.textContent = i === 0 && total === 0 ? "no regions — dispatch to create one" : ""; grid.appendChild(cell); continue; }
      const budget = r.policy.token_budget;
      const pct = budget ? Math.min(100, (r.own_tokens / budget) * 100) : 0;
      cell.innerHTML = `
        <div class="mc-cell-head">
          <span class="mc-cell-name" title="${esc(r.scw_id)}">${esc(r.label)}</span>
          <span class="mc-cell-type">${esc(r.region_type)}</span>
        </div>
        <div class="muted small">${esc(r.lifecycle)} · ${r.entry_count} entries · depth ${r.depth ?? 0}</div>
        <div class="mc-metrics">
          <div class="mc-metric-row">
            <span class="mc-metric-label">tokens</span>
            <span class="mc-metric-bar"><span class="mc-metric-fill eviction-${esc(r.policy.eviction)}" style="width:${budget ? pct : 8}%"></span></span>
            <span class="mc-metric-val">${r.own_tokens}${budget ? "/" + budget : ""}</span>
          </div>
        </div>
        <div class="mc-cell-actions">
          <button class="ghost tiny" data-inspect="${esc(r.scw_id)}">inspect</button>
          ${mc.source !== "live" ? `<button class="ghost tiny danger" data-close="${esc(r.scw_id)}">close</button>` : ""}
        </div>`;
      cell.addEventListener("dragover", e => { e.preventDefault(); cell.classList.add("dragover"); });
      cell.addEventListener("dragleave", () => cell.classList.remove("dragover"));
      cell.addEventListener("drop", e => {
        e.preventDefault(); cell.classList.remove("dragover");
        if (mc.source === "live") return;
        mcHandleFileDrop(e, r.scw_id);
      });
      grid.appendChild(cell);
    }
    grid.querySelectorAll("[data-inspect]").forEach(b => b.addEventListener("click", () => {
      $$("#tabs button").forEach(btn => btn.classList.toggle("active", btn.dataset.view === "window"));
      $$(".view").forEach(v => v.classList.toggle("hidden", v.dataset.view !== "window"));
      refreshWindow().then(() => selectRegion(b.dataset.inspect));
    }));
    grid.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", async () => {
      const r = await api(`/api/mission/close`, { scw_id: b.dataset.close });
      if (r.ok) { toast(`closed ${b.dataset.close}`, "ok"); mcRefresh(); }
      else toast(r.message || r.error, "bad");
    }));
  }

  async function mcHandleFileDrop(e, scwId) {
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    const text = await file.text();
    const r = await api("/api/mission/file", { scw_id: scwId, filename: file.name, content: text });
    if (r.ok) { toast(`${file.name} written into ${scwId}`, "ok"); mc._pulse && mc._pulse(); mcRefresh(); }
    else toast(r.message || r.error || "refused", "bad");
  }

  async function mcDispatch() {
    const s = mcSkill();
    const agentSlug = $("#mc-agent").value;
    const agentName = s ? (s.agents.find(a => a.slug === agentSlug) || {}).name || "" : "";
    const targetVal = $("#mc-target").value;
    const isNew = targetVal === "__new__" || !targetVal;
    const body = {
      target_scw_id: isNew ? null : targetVal,
      label: $("#mc-label").value.trim() || (s ? s.id : (mcConcept() || {}).id) || "scw",
      region_type: $("#mc-region-type").value,
      token_ceiling: parseInt($("#mc-ceiling").value, 10) || 8000,
      agent_slug: agentSlug,
      agent_name: agentName,
      skill_desc: s ? s.description : "",
      prompt: $("#mc-prompt").value.trim(),
      create_count: parseInt($("#mc-count").value, 10) || 1,
    };
    $("#mc-dispatch").disabled = true;
    const r = await api("/api/mission/dispatch", body);
    $("#mc-dispatch").disabled = false;
    if (!r.ok) { $("#mc-status").textContent = `refused: ${r.message || r.error}`; toast(r.message || r.error, "bad"); return; }
    $("#mc-status").textContent = `${r.mode} · target ${r.target}${r.created.length > 1 ? ` · created ${r.created.length}` : ""}`;
    toast(`dispatched (${r.mode})`, "ok");
    mc._pulse && mc._pulse();
    $("#mc-prompt").value = "";
    mcRefresh();
  }

  function mcWire() {
    $("#mc-concept").addEventListener("change", mcOnConceptChange);
    $("#mc-skill").addEventListener("change", mcOnSkillChange);
    $("#mc-target").addEventListener("change", () => {
      $("#mc-new-fields").style.display = (mc.source !== "live" && $("#mc-target").value === "__new__") ? "" : "none";
    });
    $("#mc-source").addEventListener("change", e => { mc.source = e.target.value; mc.page = 0; mcRefresh(); });
    $("#mc-refresh").addEventListener("click", mcRefresh);
    $("#mc-prev").addEventListener("click", () => { mc.page = Math.max(0, mc.page - 1); mcRenderGrid(); });
    $("#mc-next").addEventListener("click", () => { mc.page += 1; mcRenderGrid(); });
    $("#mc-dispatch").addEventListener("click", mcDispatch);

    const drop = $("#mc-drop");
    drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("dragover"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
    drop.addEventListener("drop", e => {
      e.preventDefault(); drop.classList.remove("dragover");
      const targetVal = $("#mc-target").value;
      const scwId = (targetVal === "__new__" || !targetVal) ? null : targetVal;
      if (!scwId) { toast("pick an existing target scw to drop a file onto, or dispatch first to create one", "bad"); return; }
      mcHandleFileDrop(e, scwId);
    });
  }

  async function initMission() {
    if (!mc._inited) {
      mc._inited = true;
      mcInitFabric();
      mcWire();
      await mcLoadCatalog();
    }
    await mcLoadKeyStatus();
    await mcRefresh();
  }

  /* ── boot ─────────────────────────────────────────────────────────── */
  async function loadLoops() {
    const r = await api("/api/loops");
    state.loops = r.ok ? r.loops : [];
  }

  async function boot() {
    const k = await api("/api/knowledge");
    if (!k.ok) { toast("Failed to load knowledge base", "bad"); return; }
    state.knowledge = k;
    renderCounts(k);

    await loadLoops();

    $("#filter-concept").innerHTML = `<option value="">all concepts</option>` +
      k.concepts.map(c => `<option value="${esc(c.id)}">${esc(c.title || c.id)}</option>`).join("");

    renderConcepts();
    renderLoops();
    renderPalette("");
    refreshWindow();
  }

  boot();
})();
