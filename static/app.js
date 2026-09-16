const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const chat = $("#chat");
const input = $("#input");
const modelSel = $("#model");
const activity = $("#activity");
const chatView = $("#chat-view");

const K = { convos: "aiheaven.convos", projects: "aiheaven.projects", instr: "aiheaven.instructions" };
const state = {
  convos: [], projects: [], cur: null, projectFilter: null, showArchived: false,
  tools: true, web: false, auto: false, busy: false, instructions: "", models: [],
};

init();
async function init() {
  load();
  wireSidebar(); wireViews(); wireComposer(); wireVM(); wireCustomize(); wireConnectors(); wireTerminal();
  setGreeting();
  document.addEventListener("click", () => hideMenu());
  wireCollapse();
  wireTitlebar();
  await Promise.all([loadBranding(), loadConfig(), loadModels(), loadSkills(), loadMemory(), loadSubagents()]);
  applyDefaultModel();
  loadTree(); loadVM();
}

/* ---------- persistence ---------- */
function load() {
  try { state.convos = JSON.parse(localStorage.getItem(K.convos)) || []; } catch {}
  try { state.projects = JSON.parse(localStorage.getItem(K.projects)) || []; } catch {}
  state.instructions = localStorage.getItem(K.instr) || "";
  if (state.convos.length) state.cur = state.convos.find((c) => !c.archived)?.id || state.convos[0].id;
  else newChat();
}
function save() {
  try { localStorage.setItem(K.convos, JSON.stringify(state.convos.slice(0, 100))); } catch {}
  try { localStorage.setItem(K.projects, JSON.stringify(state.projects)); } catch {}
}
function curConvo() { return state.convos.find((c) => c.id === state.cur); }

/* ---------- conversations ---------- */
function newChat() {
  const c = { id: Date.now().toString(36), title: "New chat", messages: [],
    projectId: state.projectFilter, archived: false, ts: Date.now() };
  state.convos.unshift(c);
  state.cur = c.id; state.showArchived = false;
  renderAll(); renderThread();
}
function selectConvo(id) { state.cur = id; renderThread(); renderHistory(); }
function renderThread() {
  const c = curConvo();
  chat.innerHTML = "";
  (c?.messages || []).forEach((m) => { if (m.role === "user" || m.role === "assistant") addMsg(m.role, m.content); });
  chatView.classList.toggle("home", !(c?.messages || []).length);
  $("#crumb").textContent = c && c.projectId ? projName(c.projectId) : "";
}
function projName(id) { return state.projects.find((p) => p.id === id)?.name || ""; }

function renderAll() { renderProjects(); renderHistory(); }
function renderProjects() {
  const ul = $("#projects");
  ul.innerHTML = state.projects.map((p) =>
    `<li data-pid="${p.id}" class="${state.projectFilter === p.id ? "active" : ""}">
       <span class="proj-name">${esc(p.name)}</span>
       <button class="row-menu" data-pmenu="${p.id}">⋯</button></li>`).join("")
    || `<li class="empty-note">no projects</li>`;
  $$("#projects li[data-pid]").forEach((li) => {
    li.querySelector(".proj-name").onclick = () => {
      state.projectFilter = state.projectFilter === li.dataset.pid ? null : li.dataset.pid;
      renderAll();
    };
    li.querySelector("[data-pmenu]").onclick = (e) => { e.stopPropagation(); projectMenu(e, li.dataset.pid); };
  });
}
function renderHistory(filter) {
  const q = ($("#search").value || "").toLowerCase();
  $("#recents-label").textContent = state.showArchived ? "Archived"
    : state.projectFilter ? projName(state.projectFilter) : "Recents";
  $("#toggle-archived").textContent = state.showArchived ? "Back" : "Archived";
  const ul = $("#history");
  const list = state.convos.filter((c) =>
    !!c.archived === state.showArchived &&
    (state.showArchived || !state.projectFilter || c.projectId === state.projectFilter) &&
    c.title.toLowerCase().includes(q));
  if (!list.length) { ul.innerHTML = `<li class="empty-note">nothing here</li>`; return; }
  ul.innerHTML = list.map((c) =>
    `<li data-id="${c.id}" class="${c.id === state.cur ? "active" : ""}">
       <span class="chat-title">${esc(c.title)}</span>
       <button class="row-menu" data-menu="${c.id}">⋯</button></li>`).join("");
  $$("#history li[data-id]").forEach((li) => {
    li.querySelector(".chat-title").onclick = () => selectConvo(li.dataset.id);
    li.querySelector("[data-menu]").onclick = (e) => { e.stopPropagation(); chatMenu(e, li.dataset.id); };
  });
}

/* ---------- context menus ---------- */
function showMenu(x, y, items) {
  const m = $("#menu");
  m.innerHTML = items.map((it, i) => it.sep ? `<div class="menu-sep"></div>`
    : `<button data-i="${i}">${esc(it.label)}</button>`).join("");
  m.style.left = Math.min(x, innerWidth - 210) + "px";
  m.style.top = Math.min(y, innerHeight - 40 - items.length * 34) + "px";
  m.classList.remove("hidden");
  items.forEach((it, i) => { if (!it.sep) m.querySelector(`[data-i="${i}"]`).onclick = (e) => { e.stopPropagation(); hideMenu(); it.fn(); }; });
}
function hideMenu() { $("#menu").classList.add("hidden"); }
function chatMenu(e, id) {
  const c = state.convos.find((x) => x.id === id);
  const items = [
    { label: "Rename", fn: () => { const t = prompt("Rename chat", c.title); if (t) { c.title = t; save(); renderHistory(); } } },
    { label: c.archived ? "Unarchive" : "Archive", fn: () => { c.archived = !c.archived; save(); renderHistory(); } },
    { sep: true },
    ...state.projects.map((p) => ({ label: (c.projectId === p.id ? "✓ " : "") + "Move to " + p.name,
      fn: () => { c.projectId = c.projectId === p.id ? null : p.id; save(); renderAll(); renderThread(); } })),
    { label: "Remove from project", fn: () => { c.projectId = null; save(); renderAll(); renderThread(); } },
    { sep: true },
    { label: "Delete", fn: () => { state.convos = state.convos.filter((x) => x.id !== id);
      if (state.cur === id) state.cur = state.convos[0]?.id || null; if (!state.cur) newChat(); save(); renderAll(); renderThread(); } },
  ];
  showMenu(e.clientX, e.clientY, items);
}
function projectMenu(e, pid) {
  const p = state.projects.find((x) => x.id === pid);
  showMenu(e.clientX, e.clientY, [
    { label: "Rename", fn: () => { const n = prompt("Rename project", p.name); if (n) { p.name = n; save(); renderProjects(); } } },
    { label: "Delete project", fn: () => { state.projects = state.projects.filter((x) => x.id !== pid);
      state.convos.forEach((c) => { if (c.projectId === pid) c.projectId = null; });
      if (state.projectFilter === pid) state.projectFilter = null; save(); renderAll(); } },
  ]);
}

/* ---------- sidebar ---------- */
function wireSidebar() {
  $("#clear").onclick = newChat;
  $("#side-collapse").onclick = () => $("#shell").classList.add("collapsed");
  $("#side-open").onclick = () => $("#shell").classList.remove("collapsed");
  $("#search").addEventListener("input", () => renderHistory());
  $("#toggle-archived").onclick = () => { state.showArchived = !state.showArchived; state.projectFilter = null; renderAll(); };
  $("#add-project").onclick = () => { const n = prompt("New project name"); if (n) {
    state.projects.unshift({ id: "p" + Date.now().toString(36), name: n }); save(); renderProjects(); } };
  $("#open-customize").onclick = () => openCustomize("skills");
  renderAll();
}
function setGreeting() {
  const h = new Date().getHours();
  const t = h < 5 ? "Still awake" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  $("#greeting").textContent = t + ". What shall we create?";
}

/* ---------- view switcher (animated segmented) ---------- */
function moveInd() {
  const on = $("#views button.on"); const ind = $("#vs-ind");
  if (on && ind) { ind.style.width = on.offsetWidth + "px"; ind.style.transform = `translateX(${on.offsetLeft - 4}px)`; }
}
function selectView(v) {
  $$("#views button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  $$(".view").forEach((x) => x.classList.toggle("on", x.dataset.view === v));
  moveInd();
  document.documentElement.dataset.view = v;
  if (v === "code") loadTree(); if (v === "vm") loadVM();
  if (v === "terminal") { loadTargets(); loadChanges(); setTimeout(() => $("#term-in").focus(), 60); }
}

/* ---------- terminal mode ---------- */
function wireTerminal() {
  $("#term-form").addEventListener("submit", (e) => { e.preventDefault(); termSend(); });
  $("#term-changes-btn").onclick = () => { $("#term-changes").classList.toggle("hidden"); loadChanges(); };
  $("#term-push").onclick = termPush;
  $("#term-manage").onclick = addTarget;
}
function termOut() { return $("#term-out"); }
function termLine(text, cls) {
  const d = document.createElement("div");
  d.className = "tl " + (cls || "");
  d.textContent = text;
  termOut().appendChild(d); termOut().scrollTop = termOut().scrollHeight;
  return d;
}
async function loadTargets() {
  try {
    const d = await (await fetch("/api/targets")).json();
    const sel = $("#term-target");
    sel.innerHTML = d.targets.length
      ? d.targets.map((t) => `<option value="${t.id}">${t.type === "repo" ? "⎇" : "📄"} ${esc(t.name)}</option>`).join("")
      : `<option value="">no target — click + target</option>`;
  } catch {}
}
async function addTarget() {
  const type = (prompt("Target type: repo or file", "repo") || "").trim();
  if (type !== "repo" && type !== "file") return;
  const name = prompt("Name")?.trim(); if (!name) return;
  const body = { type, name };
  if (type === "repo") { body.url = prompt("Git URL (https://…​.git — token in URL if private)")?.trim() || ""; body.branch = prompt("Branch", "main")?.trim() || "main"; }
  else { body.path = prompt("File path (inside sandbox)")?.trim() || ""; }
  await fetch("/api/targets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  loadTargets();
}
async function loadChanges() {
  try {
    const s = await (await fetch("/api/git/status")).json();
    const d = await (await fetch("/api/git/diff")).json();
    const head = s.repo ? `on ${esc(s.branch || "?")} — ${s.files.length} changed\n` +
      s.files.map((f) => `  ${f.status.padEnd(2)} ${esc(f.path)}`).join("\n")
      : "not a git repo yet (Push will init one)";
    $("#term-changes").textContent = head + (d.diff ? "\n\n" + d.diff : "");
  } catch {}
}
async function termPush() {
  const tid = $("#term-target").value;
  if (!tid) { termLine("no target selected — click + target", "err"); return; }
  const msg = prompt("Commit message", "update from Ai Heaven") || "update from Ai Heaven";
  termLine("$ push → " + $("#term-target").selectedOptions[0].textContent, "u");
  try {
    const r = await (await fetch("/api/git/push", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_id: tid, message: msg }) })).json();
    termLine(r.log || (r.ok ? "pushed" : "failed"), r.ok ? "ok" : "err");
  } catch (e) { termLine("push error: " + e.message, "err"); }
  loadChanges();
}
async function termSend() {
  if (state.busy) return;
  let text = $("#term-in").value.trim(); if (!text) return;
  let web = state.web; if (text.startsWith("/web")) { web = true; text = text.slice(4).trim(); }
  const c = curConvo();
  termLine("$ " + text, "u"); c.messages.push({ role: "user", content: text });
  $("#term-in").value = ""; save(); setBusy(true);
  const msgs = [...c.messages]; if (state.instructions) msgs.unshift({ role: "system", content: state.instructions });
  let acc = "", line = null;
  try {
    const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: modelSel.value, messages: msgs, web, tools: state.tools, ask: !state.auto }) });
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const blocks = buf.split("\n\n"); buf = blocks.pop();
      for (const block of blocks) {
        const ev = /event: (.*)/.exec(block)?.[1]; const dl = /data: (.*)/s.exec(block)?.[1];
        if (!ev) continue; const data = dl ? JSON.parse(dl) : null;
        if (ev === "token") { if (!line) { line = termLine("", "a"); acc = ""; } acc += data; line.textContent = acc; termOut().scrollTop = termOut().scrollHeight; }
        else if (ev === "tool_call") { line = null; termLine("→ " + data.name + "(" + Object.keys(data.args || {}).join(",") + ")", "t"); }
        else if (ev === "tool_result") { termLine(data.result, data.result.startsWith("error") ? "err" : "r"); }
        else if (ev === "approval") { await handleApproval(data); }
        else if (ev === "error") { termLine("error: " + data, "err"); }
        else if (ev === "done") { if (acc) c.messages.push({ role: "assistant", content: acc }); }
      }
    }
  } catch (e) { termLine("error: " + e.message, "err"); }
  setBusy(false); save(); loadChanges();
}
function wireViews() {
  $$("#views button").forEach((b) => (b.onclick = () => selectView(b.dataset.view)));
  requestAnimationFrame(moveInd);
  window.addEventListener("resize", () => { moveInd(); });
}
function wireTitlebar() {
  const api = () => (window.pywebview && window.pywebview.api) || null;
  $("#win-min").onclick = () => api()?.minimize();
  $("#win-max").onclick = () => api()?.toggle_maximize();
  $("#win-close").onclick = () => api()?.close();
  // window controls only make sense inside the native (pywebview) window
  const show = () => { const c = $("#tb-ctrls"); if (c) c.hidden = false; };
  if (window.pywebview) show();
  window.addEventListener("pywebviewready", show);
}
function wireCollapse() {
  const collapse = () => $("#shell").classList.add("collapsed");
  const expand = () => $("#shell").classList.remove("collapsed");
  $("#side-collapse").onclick = collapse;
  $("#mini-expand").onclick = expand;
  $("#mini-new").onclick = () => { expand(); newChat(); };
  $("#mini-settings").onclick = () => openCustomize("skills");
}

/* ---------- loaders ---------- */
async function loadBranding() {
  try {
    const b = await (await fetch("/api/branding")).json();
    if (b.name) { $("#brand-name").textContent = b.name; $("#about-name").textContent = b.name; document.title = b.name; }
    if (b.logo) $("#logo").src = "/" + b.logo.replace(/^\//, "");
    const r = document.documentElement.style;
    if (b.accent) r.setProperty("--clay", b.accent);
    if (b.accent_soft) r.setProperty("--clay-soft", b.accent_soft);
    state.defaultModel = b.default_model || "";
  } catch {}
}
function applyDefaultModel() {
  if (!state.defaultModel) return;
  const opt = [...modelSel.options].find((o) => o.value === state.defaultModel);
  if (opt) modelSel.value = state.defaultModel;   // parent default (e.g. hermes3:8b)
}
async function loadConfig() {
  try {
    const c = await (await fetch("/api/config")).json();
    $("#workdir").textContent = c.workdir || "—";
    const st = $("#status");
    st.classList.toggle("up", !!c.ollama); st.classList.toggle("down", !c.ollama);
    st.lastChild.textContent = c.ollama ? "ollama online" : "ollama offline";
    const md = $("#mini-dot"); md.classList.toggle("up", !!c.ollama); md.classList.toggle("down", !c.ollama);
    md.title = c.ollama ? "ollama online" : "ollama offline";
  } catch { const st = $("#status"); st.classList.add("down"); st.lastChild.textContent = "offline"; $("#mini-dot").classList.add("down"); }
}
async function loadModels() {
  try {
    const d = await (await fetch("/api/models")).json();
    const all = d.models || [];
    // show only the recommended models for this app: hermes + dolphin
    const pick = all.filter((m) => /hermes|dolphin/i.test(m));
    state.models = pick.length ? pick : all;
    modelSel.innerHTML = state.models.length
      ? state.models.map((m) => `<option>${esc(m)}</option>`).join("")
      : `<option>${esc(d.error || "no hermes/dolphin model — ollama pull hermes3:8b")}</option>`;
    $("#sa-model").innerHTML = `<option value="">(inherit model)</option>` +
      state.models.map((m) => `<option>${esc(m)}</option>`).join("");
  } catch { modelSel.innerHTML = "<option>offline</option>"; }
}
async function loadSkills() {
  try {
    const d = await (await fetch("/api/skills")).json();
    $("#skills").innerHTML = d.skills.length
      ? d.skills.map((s) => `<li><b>${esc(s.name)}</b><span>${esc(s.desc || "")}</span></li>`).join("")
      : "<li><span>drop skills/&lt;name&gt;/SKILL.md next to the app</span></li>";
  } catch {}
}
async function loadMemory() {
  try { const d = await (await fetch("/api/memory")).json();
    $("#memory").textContent = d.memory.trim() || "nothing remembered yet"; } catch {}
}

/* ---------- subagents ---------- */
async function loadSubagents() {
  try {
    const d = await (await fetch("/api/subagents")).json();
    const ul = $("#subagents");
    ul.innerHTML = d.subagents.length ? d.subagents.map((s) =>
      `<li><div class="ag-top"><b>${esc(s.name)}</b>
         <span class="ag-model">${esc(s.model || "inherit")}</span>
         <button class="row-menu" data-del="${s.id}">✕</button></div>
       <span class="ag-desc">${esc(s.desc || "")}</span>
       ${s.vm && s.vm.stream ? `<span class="ag-vm">🖥 own VM</span>` : ""}</li>`).join("")
      : `<li class="empty-note">no subagents yet</li>`;
    $$("#subagents [data-del]").forEach((b) => (b.onclick = async () => {
      await fetch("/api/subagents/" + b.dataset.del, { method: "DELETE" }); loadSubagents(); loadVM();
    }));
  } catch {}
}
function wireCustomize() {
  $("#close-customize").onclick = () => $("#customize").classList.add("hidden");
  $("#customize").addEventListener("click", (e) => { if (e.target.id === "customize") $("#customize").classList.add("hidden"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#customize").classList.add("hidden"); });
  $$("#customize .tab").forEach((t) => (t.onclick = () => openCustomize(t.dataset.tab)));
  $("#agents-chip").onclick = () => openCustomize("agents");
  $("#reload-mem").onclick = loadMemory;
  $("#instructions").value = state.instructions;
  $("#save-instructions").onclick = () => {
    state.instructions = $("#instructions").value; localStorage.setItem(K.instr, state.instructions);
    $("#save-instructions").textContent = "Saved ✓"; setTimeout(() => ($("#save-instructions").textContent = "Save"), 1200);
  };
  $("#sa-add").onclick = async () => {
    const name = $("#sa-name").value.trim(); if (!name) return;
    const vm = $("#sa-vm").value.trim();
    await fetch("/api/subagents", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, desc: $("#sa-desc").value.trim(), model: $("#sa-model").value,
        system: $("#sa-system").value.trim(), vm: vm ? { stream: vm } : null }) });
    ["sa-name", "sa-desc", "sa-vm", "sa-system"].forEach((i) => ($("#" + i).value = ""));
    loadSubagents(); loadVM();
  };
}
function openCustomize(tab) {
  $("#customize").classList.remove("hidden");
  $$("#customize .tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === tab));
  $$("#customize .tabpane").forEach((p) => p.classList.toggle("on", p.dataset.tab === tab));
  if (tab === "memory") loadMemory();
  if (tab === "agents") loadSubagents();
  if (tab === "connectors") loadConnectors();
}

/* ---------- connectors (MCP) ---------- */
// The connectors Claude offers. Remote ones are hosted MCP endpoints you sign
// into; local ones run as an npx stdio server. Credentials are never exported —
// you authenticate with your own account when you enable one.
const CATALOG = [
  { name: "github", icon: "🐙", transport: "stdio", command: "npx -y @modelcontextprotocol/server-github" },
  { name: "gmail", icon: "✉️", transport: "sse", url: "" },
  { name: "google-drive", icon: "📄", transport: "sse", url: "" },
  { name: "dropbox", icon: "📦", transport: "sse", url: "" },
  { name: "slack", icon: "💬", transport: "sse", url: "" },
  { name: "notion", icon: "📓", transport: "sse", url: "" },
  { name: "linear", icon: "📐", transport: "sse", url: "" },
  { name: "stripe", icon: "💳", transport: "sse", url: "" },
  { name: "supabase", icon: "🗄️", transport: "sse", url: "" },
  { name: "vercel", icon: "▲", transport: "sse", url: "" },
  { name: "cloudflare", icon: "☁️", transport: "sse", url: "" },
  { name: "hugging-face", icon: "🤗", transport: "sse", url: "" },
  { name: "filesystem", icon: "🗂️", transport: "stdio", command: "npx -y @modelcontextprotocol/server-filesystem ." },
  { name: "fetch", icon: "🌐", transport: "stdio", command: "npx -y @modelcontextprotocol/server-fetch" },
];
function renderCatalog() {
  const el = $("#catalog"); if (!el) return;
  el.innerHTML = CATALOG.map((c, i) =>
    `<button class="cat-chip" data-cat="${i}"><span>${c.icon}</span>${esc(c.name)}<b>+</b></button>`).join("");
  $$("#catalog [data-cat]").forEach((b) => (b.onclick = async () => {
    const c = CATALOG[+b.dataset.cat];
    await fetch("/api/connectors", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: c.name, transport: c.transport,
        command: c.command ? c.command.split(/\s+/)[0] : "",
        args: c.command ? c.command.split(/\s+/).slice(1) : [], url: c.url || "" }) });
    loadConnectors();
  }));
}
async function loadConnectors() {
  renderCatalog();
  try {
    const d = await (await fetch("/api/connectors")).json();
    $("#mcp-status").textContent = d.mcp_available ? "· MCP ready" : "· install: pip install mcp";
    const ul = $("#connectors");
    ul.innerHTML = d.connectors.length ? d.connectors.map((c) =>
      `<li><div class="ag-top"><b>${esc(c.name)}</b>
         <span class="ag-model">${esc(c.transport)}</span>
         <button class="row-menu" data-cdel="${c.id}">✕</button></div>
       <span class="ag-desc">${esc(c.transport === "sse" ? c.url : (c.command || ""))}</span></li>`).join("")
      : `<li class="empty-note">no connectors yet</li>`;
    $$("#connectors [data-cdel]").forEach((b) => (b.onclick = async () => {
      await fetch("/api/connectors/" + b.dataset.cdel, { method: "DELETE" }); loadConnectors();
    }));
  } catch {}
}
function wireConnectors() {
  $("#co-transport").onchange = (e) => {
    const sse = e.target.value === "sse";
    $("#co-url").style.display = sse ? "" : "none";
    $("#co-command").style.display = sse ? "none" : "";
  };
  $("#co-add").onclick = async () => {
    const name = $("#co-name").value.trim(); if (!name) return;
    const transport = $("#co-transport").value;
    const raw = $("#co-command").value.trim().split(/\s+/);
    await fetch("/api/connectors", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, transport,
        command: transport === "stdio" ? (raw[0] || "") : "",
        args: transport === "stdio" ? raw.slice(1) : [],
        url: transport === "sse" ? $("#co-url").value.trim() : "" }) });
    ["co-name", "co-command", "co-url"].forEach((i) => ($("#" + i).value = ""));
    loadConnectors();
  };
}

/* ---------- code view ---------- */
async function loadTree() {
  try {
    const d = await (await fetch("/api/tree")).json();
    $("#tree").innerHTML = renderTree(d.tree, 0);
    $$("#tree li[data-file]").forEach((li) => (li.onclick = () => openFile(li.dataset.file, li)));
  } catch {}
}
function renderTree(nodes, depth) {
  return nodes.map((n) => {
    const pad = depth ? ' class="kid"' : "";
    if (n.dir) return `<li${pad} class="dir">▸ ${esc(n.name)}</li>` + renderTree(n.children, depth + 1);
    return `<li${pad} data-file="${esc(n.path)}">${esc(n.name)}</li>`;
  }).join("");
}
async function openFile(path, li) {
  $$("#tree li").forEach((x) => x.classList.remove("sel"));
  if (li) li.classList.add("sel");
  $("#editor-path").textContent = path;
  try { const d = await (await fetch("/api/file?path=" + encodeURIComponent(path))).json();
    $("#editor-body").innerHTML = `<code>${esc(d.content || d.error || "")}</code>`; } catch {}
}

/* ---------- vm view ---------- */
function wireVM() {
  $$("[data-vm]").forEach((b) => (b.onclick = async () => {
    b.disabled = true;
    try { paintVM(await (await fetch("/api/vm/action", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: b.dataset.vm }) })).json()); } catch {}
    b.disabled = false;
  }));
}
async function loadVM() {
  try { paintVM(await (await fetch("/api/vm")).json()); } catch {}
  try { const d = await (await fetch("/api/bus")).json();
    $("#bus").innerHTML = (d.bus || []).slice(-12).reverse().map((m) =>
      `<li><b>${esc(m.from)}→${esc(m.to)}</b> ${esc(m.text)}</li>`).join("") || `<li class="empty-note">no messages</li>`; } catch {}
  try { const d = await (await fetch("/api/tasks")).json();
    const t = $("#tasks"); if (t) t.innerHTML = (d.tasks || []).slice(-14).map((x) =>
      `<li class="tk tk-${esc(x.status)}"><span class="tk-dot"></span>
        <span class="tk-desc">${esc(x.desc)}</span>
        <span class="tk-who">${esc(x.assignee || x.status)}</span></li>`).join("")
      || `<li class="empty-note">no tasks</li>`; } catch {}
}
// a grok-style cloud bot face, tinted to `color`. `pose` drives the expression:
// look = eyes dart around (busy), sleep = eyes shut + grey (idle), happy/think/alert.
function grokAvatar(color, pose = "look") {
  const p = ["look", "sleep", "happy", "think", "alert"].includes(pose) ? pose : "look";
  return `<span class="gbot pose-${p}" style="--bot:${color}" aria-hidden="true">
    <svg viewBox="0 0 100 84" class="gbot-svg">
      <g class="gbot-body">
        <circle cx="30" cy="36" r="17"/><circle cx="68" cy="35" r="16"/>
        <circle cx="21" cy="52" r="15"/><circle cx="80" cy="52" r="14"/>
        <ellipse cx="50" cy="50" rx="35" ry="28"/>
      </g>
      <g class="gbot-eyes">
        <g class="eye eye-l"><ellipse class="ball" cx="39" cy="48" rx="7" ry="9"/>
          <circle class="pupil" cx="39" cy="48" r="3.4"/></g>
        <g class="eye eye-r"><ellipse class="ball" cx="61" cy="48" rx="7" ry="9"/>
          <circle class="pupil" cx="61" cy="48" r="3.4"/></g>
      </g>
      <g class="gbot-lids">
        <path class="lid lid-l" d="M31 48 q8 8 16 0"/>
        <path class="lid lid-r" d="M53 48 q8 8 16 0"/>
      </g>
    </svg></span>`;
}
function screenCard(name, stream, primary, runtime = "active", mode = "local", color = "#c99a3a", pose = "look") {
  const label = primary ? name + " · parent (2 models)" : name;
  const cls = runtime === "disabled" ? " off" : runtime === "paused" ? " paused" : "";
  const note = runtime === "disabled" ? "disabled by parent — freed for resources"
    : runtime === "paused" ? "paused (no task) — VM suspended so the PC can breathe"
    : primary && mode === "local" ? "Local mode — your agents work right here. Hit Run app to preview what they build."
    : primary ? "waiting for the VM stream…"
    : "runs on this machine — give it its own VM in Customize → Subagents";
  const body = (stream && runtime === "active")
    ? `<img src="${esc(stream)}" alt="">`
    : `<div class="vm-overlay">${grokAvatar(color, pose)}
        <span class="vm-live">${esc(name)}</span><p>${note}</p></div>`;
  return `<div class="vm-screen ${primary ? "primary" : ""}${cls}">
      <div class="vm-tag">${esc(label)} <span class="vm-st">${esc(runtime)}</span></div>${body}</div>`;
}
function meter(label, v) {
  if (v === null || v === undefined) return `<div class="mtr"><span>${label}</span><b>n/a</b></div>`;
  const cls = v > 85 ? "hot" : v > 60 ? "warm" : "";
  return `<div class="mtr ${cls}"><span>${label}</span>
    <div class="mtr-bar"><i style="width:${Math.min(100, v)}%"></i></div><b>${Math.round(v)}%</b></div>`;
}
function paintVM(d) {
  $("#vm-status").textContent = "status: " + (d.status || "idle");
  // label the controls for the current mode
  const vm = d.mode === "vm";
  if ($("#vm-start")) $("#vm-start").textContent = vm ? "Start VM" : "Run app";
  if ($("#vm-open")) $("#vm-open").hidden = vm;         // "Open folder" is local-only
  if ($("#vm-stop")) $("#vm-stop").textContent = "Stop";
  const sys = d.system || {};
  const sl = $("#sysload");
  if (sl) sl.innerHTML = meter("CPU", sys.cpu) + meter("RAM", sys.ram) +
    (sys.gpu !== null && sys.gpu !== undefined ? meter("GPU", sys.gpu) : "") +
    `<div class="mtr-note">${(d.agents || []).filter((a) => a.runtime === "active").length + 1} running · ${(d.agents || []).filter((a) => a.runtime === "paused").length} paused · ${sys.cores || "?"} cores</div>`;
  const grid = $("#vm-grid");
  if (grid) {
    const total = 1 + (d.agents || []).length;
    const cols = Math.ceil(Math.sqrt(total));           // shrink as agents grow
    grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
    let html = screenCard("main", d.stream, true, "active", d.mode, d.color || "#c99a3a", d.pose || "look");
    (d.agents || []).forEach((a) => (html += screenCard(a.name, a.stream, false, a.runtime || "active", d.mode, a.color, a.pose)));
    grid.innerHTML = html;
  }
  $("#vm-app").innerHTML = d.app_url
    ? `<iframe src="${esc(d.app_url)}" style="width:100%;height:100%;border:0;border-radius:12px"></iframe>`
    : `<span>your app appears here when you Run it</span>`;
}

/* ---------- composer / chat ---------- */
function wireComposer() {
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; });
  $("#tools-chip").onclick = (e) => { state.tools = !state.tools; e.target.classList.toggle("on", state.tools); };
  $("#web-chip").onclick = (e) => { state.web = !state.web; e.target.classList.toggle("on", state.web); };
  $("#auto-chip").onclick = (e) => { state.auto = !state.auto; e.target.classList.toggle("on", state.auto); };
}
function esc(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function bottom() { chat.scrollTop = chat.scrollHeight; }
function addMsg(role, text) {
  const d = document.createElement("div");
  d.className = `msg ${role}`;
  d.innerHTML = `<div class="who">${role === "user" ? "you" : "ai heaven"}</div><div class="body"></div>`;
  d.querySelector(".body").textContent = text;
  chat.appendChild(d); bottom();
  return d.querySelector(".body");
}
function addTool(name, args) {
  const label = name === "spawn_subagent" ? `delegate → ${args.name}`
    : name === "send_agent_message" ? `message → ${args.to || "all"}` : name;
  const a = Object.entries(args || {}).map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 60)}`).join(", ");
  const d = document.createElement("div");
  d.className = "tool" + (name.includes("agent") ? " agentic" : "");
  d.innerHTML = `<div class="call">${esc(label)}(${esc(a)})</div>`;
  chat.appendChild(d); bottom();
  const li = document.createElement("li");
  li.innerHTML = `<div class="a-tool">${esc(label)}</div>`;
  activity.prepend(li);
  return { chip: d, feed: li };
}
function addToolResult(ref, result) {
  const cls = result.startsWith("error") ? "err" : result.startsWith("OK") || result.startsWith("exit=0") ? "ok" : "";
  const r = document.createElement("div"); r.className = "res " + cls;
  r.textContent = result.length > 1500 ? result.slice(0, 1500) + " …" : result;
  ref.chip.appendChild(r); bottom();
  const fr = document.createElement("div"); fr.className = "a-res"; fr.textContent = result.slice(0, 200);
  ref.feed.appendChild(fr); loadTree(); loadVM();
}

async function send() {
  if (state.busy) return;
  let text = input.value.trim(); if (!text) return;
  let web = state.web;
  if (text.startsWith("/web")) { web = true; text = text.slice(4).trim(); }
  const c = curConvo();
  if (c.messages.length === 0) { c.title = text.slice(0, 42); renderHistory(); }
  chatView.classList.remove("home");
  addMsg("user", text); c.messages.push({ role: "user", content: text });
  input.value = ""; input.style.height = "auto"; save();
  setBusy(true);
  try { await streamChat(web); } catch (e) { addMsg("assistant", "error: " + e.message); }
  setBusy(false); save(); loadMemory();
}
function setBusy(b) { state.busy = b; $("#send").disabled = b; }

async function streamChat(web) {
  const c = curConvo();
  const msgs = [...c.messages];
  if (state.instructions) msgs.unshift({ role: "system", content: state.instructions });
  const res = await fetch("/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: modelSel.value, messages: msgs, web, tools: state.tools, ask: !state.auto }),
  });
  const reader = res.body.getReader(); const dec = new TextDecoder();
  let buf = "", bodyEl = null, acc = "", ref = null;
  while (true) {
    const { done, value } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    const blocks = buf.split("\n\n"); buf = blocks.pop();
    for (const block of blocks) {
      const ev = /event: (.*)/.exec(block)?.[1]; const dl = /data: (.*)/s.exec(block)?.[1];
      if (!ev) continue; const data = dl ? JSON.parse(dl) : null;
      if (ev === "token") {
        if (!bodyEl) { bodyEl = addMsg("assistant", ""); bodyEl.classList.add("caret"); acc = ""; }
        acc += data; bodyEl.textContent = acc; bottom();
      } else if (ev === "tool_call") { bodyEl?.classList.remove("caret"); bodyEl = null; ref = addTool(data.name, data.args); }
      else if (ev === "tool_result") { if (ref) addToolResult(ref, data.result); ref = null; }
      else if (ev === "approval") { await handleApproval(data); }
      else if (ev === "error") { addMsg("assistant", "error: " + data); }
      else if (ev === "done") { bodyEl?.classList.remove("caret"); if (acc) c.messages.push({ role: "assistant", content: acc }); }
    }
  }
}

/* ---------- approval ---------- */
function handleApproval(data) {
  return new Promise((resolve) => {
    $("#m-tool").textContent = data.tool;
    $("#m-args").textContent = JSON.stringify(data.args, null, 2);
    $("#modal").classList.remove("hidden");
    const done = async (allow) => {
      $("#modal").classList.add("hidden"); $("#m-allow").onclick = $("#m-deny").onclick = null;
      await fetch("/api/approve", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: data.id, allow }) });
      resolve();
    };
    $("#m-allow").onclick = () => done(true); $("#m-deny").onclick = () => done(false);
  });
}
