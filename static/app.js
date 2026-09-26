const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const chat = $("#chat");
const input = $("#input");
const modelSel = $("#model");
const chatView = $("#chat-view");

const K = { convos: "aiheaven.convos", projects: "aiheaven.projects", instr: "aiheaven.instructions" };
const state = {
  convos: [], projects: [], cur: null, projectFilter: null, showArchived: false,
  tools: true, web: false, auto: false, busy: false, instructions: "", models: [],
  tabs: [], activeTab: null, connectorNames: [],
};

init();
async function init() {
  load();
  wireSidebar(); wireViews(); wireComposer(); wireCustomize(); wireConnectors();
  wireApps(); wireCodeCopy(); wireIDE();
  setGreeting(); renderThread();       // show the selected chat on startup
  document.addEventListener("click", () => hideMenu());
  wireCollapse();
  wireTitlebar();
  await Promise.all([loadBranding(), loadConfig(), loadModels(), loadSkills(), loadMemory(), loadSubagents(),
    loadConnectorNames()]);
  applyDefaultModel(); paintWorkerSelect();
  loadTree(); pollSetup();
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
  paintChatCtx();
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
  const t = h < 5 ? "Still up? Good." : h < 12 ? "Morning." : h < 18 ? "Afternoon." : "Evening.";
  $("#greeting").textContent = t + (h >= 18 || h < 5 ? " What are we building tonight?" : " What are we building today?");
}

/* ---------- view switcher (animated segmented) ---------- */
function moveInd() {
  const on = $("#views button.on"); const ind = $("#vs-ind");
  if (on && ind) { ind.style.width = on.offsetWidth + "px"; ind.style.transform = `translateX(${on.offsetLeft - 4}px)`; }
}
function selectView(v) {
  const was = document.documentElement.dataset.view || "chat";
  $$("#views button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  $$(".view").forEach((x) => x.classList.toggle("on", x.dataset.view === v));
  moveInd();
  document.documentElement.dataset.view = v;
  if (v === "code" && was !== "code") enterIDE();
  if (v !== "code" && was === "code") leaveIDE();
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
    if (b.accent) r.setProperty("--accent", b.accent);
    if (b.accent_soft) r.setProperty("--accent-soft", b.accent_soft);
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
    document.documentElement.classList.add("plat-" + (c.platform || "win"));
    state.workerModel = c.worker_model || "";
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
    // lead + worker candidates: tool-calling chat/coder models (skip embedders etc.)
    const pick = all.filter((m) => /hermes|dolphin|qwen|llama3|phi4|mistral|gemma3|deepseek|granite|coder/i.test(m)
      && !/embed/i.test(m));
    state.models = pick.length ? pick : all;
    modelSel.innerHTML = state.models.length
      ? state.models.map((m) => `<option>${esc(m)}</option>`).join("")
      : `<option>${esc(d.error || "no model yet — ollama pull hermes3:8b")}</option>`;
    $("#sa-model").innerHTML = `<option value="">worker model</option>` +
      state.models.map((m) => `<option>${esc(m)}</option>`).join("");
    paintWorkerSelect();
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
         <span class="ag-model">${esc(s.model || "worker model")}</span>
         <button class="row-menu" data-del="${s.id}">✕</button></div>
       <span class="ag-desc">${esc(s.desc || "")}</span>
       ${s.vm && s.vm.stream ? `<span class="ag-vm">🖥 own VM</span>` : ""}</li>`).join("")
      : `<li class="empty-note">no subagents yet</li>`;
    $$("#subagents [data-del]").forEach((b) => (b.onclick = async () => {
      await fetch("/api/subagents/" + b.dataset.del, { method: "DELETE" }); loadSubagents();
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
    loadSubagents();
  };
}
function openCustomize(tab) {
  $("#customize").classList.remove("hidden");
  $$("#customize .tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === tab));
  $$("#customize .tabpane").forEach((p) => p.classList.toggle("on", p.dataset.tab === tab));
  if (tab === "memory") loadMemory();
  if (tab === "agents") loadSubagents();
  if (tab === "connectors") loadConnectors();
  if (tab === "apps") loadApps();
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
    $$("#tree li[data-file]").forEach((li) => (li.onclick = () => openFile(li.dataset.file)));
    $$("#tree li[data-file]").forEach((x) => x.classList.toggle("sel", x.dataset.file === state.activeTab));
  } catch {}
}
function renderTree(nodes, depth) {
  return nodes.map((n) => {
    const pad = depth ? ' class="kid"' : "";
    if (n.dir) return `<li${pad} class="dir">▸ ${esc(n.name)}</li>` + renderTree(n.children, depth + 1);
    return `<li${pad} data-file="${esc(n.path)}">${esc(n.name)}</li>`;
  }).join("");
}
async function openFile(path) {
  if (!state.tabs.includes(path)) state.tabs.push(path);
  state.activeTab = path;
  $$("#tree li[data-file]").forEach((x) => x.classList.toggle("sel", x.dataset.file === path));
  $("#editor-path").innerHTML = path.split("/").map(esc).join('<span class="sep">›</span>');
  paintTabs();
  try {
    const d = await (await fetch("/api/file?path=" + encodeURIComponent(path))).json();
    const text = d.content || d.error || "";
    const lang = HL.langFromPath(path);
    $("#editor-body").innerHTML = `<code>${HL.highlight(text, lang)}</code>`;
    $("#ide-status").innerHTML = `<span>${esc(lang || "text")}</span><span>${text.split("\n").length} lines</span>` +
      `<span class="spacer"></span><span>lead ${esc(modelSel.value || "?")}</span><span>workers ${esc(state.workerModel || "?")}</span>`;
  } catch {}
}
function paintTabs() {
  $("#ide-tabs").innerHTML = state.tabs.map((t) =>
    `<button class="ide-tab ${t === state.activeTab ? "on" : ""}" data-tab="${esc(t)}">
       <span>${esc(t.split("/").pop())}</span><i data-close="${esc(t)}" title="close">×</i></button>`).join("");
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
  d.innerHTML = `<div class="who">${role === "user" ? "You" : "Lead"}</div><div class="body"></div>`;
  d.querySelector(".body").innerHTML = HL.render(text);
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
  return { chip: d, name, args: args || {} };
}
function addToolResult(ref, result) {
  const cls = result.startsWith("error") ? "err" : result.startsWith("OK") || result.startsWith("exit=0") ? "ok" : "";
  const r = document.createElement("div"); r.className = "res " + cls;
  r.textContent = result.length > 1500 ? result.slice(0, 1500) + " …" : result;
  ref.chip.appendChild(r); bottom();
  loadTree();
  // like Antigravity: when the agent writes a file while the IDE is open, show it
  if (/^(write_file|edit_file)$/.test(ref.name) && cls === "ok" && ref.args.path && document.documentElement.dataset.view === "code")
    openFile(ref.args.path);
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
  switchOnConnectors(c, text);
  input.value = ""; input.style.height = "auto"; save();
  setBusy(true);
  try { await streamChat(web); } catch (e) { addMsg("assistant", "error: " + e.message); }
  setBusy(false); save(); loadMemory();
}
function setBusy(b) { state.busy = b; $("#send").disabled = b; }

async function streamChat(web) {
  const c = curConvo();
  const msgs = [...c.messages];
  const chatRules = chatInstructions(c);                      // this chat only
  if (chatRules) msgs.unshift({ role: "system", content: chatRules });
  if (state.instructions) msgs.unshift({ role: "system", content: state.instructions });
  const res = await fetch("/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: modelSel.value, messages: msgs, web, tools: state.tools, ask: !state.auto,
      connectors: c.connectors || [] }),
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
        acc += data; paintStream(bodyEl, acc);
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

/* ---------- chat rendering helpers ---------- */
// re-render streamed markdown at most once per frame (code fences highlight live)
function paintStream(el, text) {
  el._pending = text;
  if (el._raf) return;
  el._raf = requestAnimationFrame(() => { el._raf = 0; el.innerHTML = HL.render(el._pending); bottom(); });
}
function wireCodeCopy() {
  document.addEventListener("click", async (e) => {
    const b = e.target.closest(".cb-copy"); if (!b) return;
    const code = b.closest(".codeblock").querySelector("code");
    const text = [...code.querySelectorAll(".ln")].map((l) => l.textContent).join("\n");
    try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; b.classList.add("done"); }
    catch { b.textContent = "Select + copy"; }
    setTimeout(() => { b.textContent = "Copy"; b.classList.remove("done"); }, 1400);
  });
}

/* ---------- worker model ---------- */
function paintWorkerSelect() {
  const sel = $("#worker-model"); if (!sel) return;
  const want = state.workerModel || "qwen2.5-coder:3b";
  const opts = state.models.includes(want) ? state.models : [want, ...state.models];
  sel.innerHTML = opts.map((m) => `<option ${m === want ? "selected" : ""}>${esc(m)}</option>`).join("");
  $("#worker-hint").textContent = state.models.includes(want)
    ? "writes the first drafts" : `not pulled yet: ollama pull ${want}`;
}

/* ---------- apps (Blender / Unreal / Roblox) ---------- */
const APP_GLYPH = { blender: ["Bl", "blender"], unreal: ["UE", "unreal"], roblox: ["Rb", "roblox"],
  rojo: ["Rj", "tool"], luau: ["Lu", "tool"] };
const DOC_APP = { blender: "blender", unreal: "unreal", roblox: "roblox" };
let appsData = null;
async function loadApps() {
  try { appsData = await (await fetch("/api/apps")).json(); } catch { return; }
  try {
    const st = await (await fetch("/api/settings")).json();
    $("#set-auto-setup").checked = !!st.auto_setup; $("#set-launch").checked = !!st.launch_on_start;
    paintSetupLog(await (await fetch("/api/apps/setup")).json());
  } catch {}
  const ul = $("#app-cards");
  ul.innerHTML = appsData.apps.map((a) => {
    const [g, cls] = APP_GLYPH[a.key] || ["?", "tool"];
    const docs = DOC_APP[a.key] ? (appsData.docs[a.key] || []).map((d) =>
      `<button class="doc-link ${d.cached ? "cached" : ""}" data-url="${esc(d.url)}">${esc(d.key)}</button>`).join("") : "";
    const launch = DOC_APP[a.key] && a.found ? `<button class="pill ghost small" data-launch="${a.key}">Open</button>` : "";
    return `<li class="app-card" data-key="${a.key}">
      <div class="app-top"><span class="app-glyph ${cls}">${g}</span>
        <span class="app-name">${esc(a.label)}</span>
        <span class="app-state ${a.found ? "found" : "missing"}">${a.found ? (a.custom ? "set by you" : "found") : "not installed"}</span>
        <span class="spacer"></span>${launch}
        <button class="pill ghost small" data-editpath="${a.key}">${a.found ? "Change path" : "Set path"}</button></div>
      ${a.path ? `<div class="app-path">${esc(a.path)}</div>` : ""}
      <div class="app-edit row"><input class="field" placeholder="full path to the program" value="${esc(a.custom ? a.path : "")}">
        <button class="pill small" data-savepath="${a.key}">Save</button></div>
      ${docs ? `<div class="docs-list">${docs}</div>` : ""}</li>`;
  }).join("");
  $("#proj-list").innerHTML = appsData.projects.length ? appsData.projects.map((p) =>
    `<li><span>${esc(p)}</span><button class="row-menu" data-rmproj="${esc(p)}" title="remove">✕</button></li>`).join("")
    : `<li class="empty-note">None yet. New work goes in the sandbox; add a folder here to let agents open an existing project.</li>`;
}
async function postApps(body) {
  const r = await fetch("/api/apps", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) { alert(d.error || "couldn't save"); return false; }
  loadApps(); return true;
}
function wireApps() {
  $("#app-cards").addEventListener("click", async (e) => {
    const t = e.target;
    if (t.dataset.editpath) t.closest(".app-card").classList.toggle("editing");
    if (t.dataset.savepath) postApps({ key: t.dataset.savepath, path: t.closest(".app-edit").querySelector("input").value });
    if (t.dataset.url) fetch("/api/open-url", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: t.dataset.url }) });
    if (t.dataset.launch) {
      t.disabled = true;
      const r = await (await fetch("/api/apps/launch", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app: t.dataset.launch }) })).json();
      t.textContent = r.ok ? "Opening…" : "Failed"; if (!r.ok) alert(r.error);
      setTimeout(() => { t.textContent = "Open"; t.disabled = false; }, 2500);
    }
  });
  $("#proj-list").addEventListener("click", (e) => { const p = e.target.dataset.rmproj; if (p) postApps({ remove_project: p }); });
  $("#proj-add").onclick = async () => {
    const v = $("#proj-add-path").value.trim(); if (!v) return;
    if (await postApps({ add_project: v })) $("#proj-add-path").value = "";
  };
  $("#docs-prefetch").onclick = async () => {
    const b = $("#docs-prefetch"); b.disabled = true; $("#docs-status").textContent = "downloading official docs…";
    try {
      const r = await (await fetch("/api/apps/docs/prefetch", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
      $("#docs-status").textContent = `${r.ok} pages saved` + (r.failed.length ? `, ${r.failed.length} unreachable (offline?)` : "");
    } catch { $("#docs-status").textContent = "failed — are you online?"; }
    b.disabled = false; loadApps();
  };
  const saveSetting = (k) => (e) => fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [k]: e.target.checked }) });
  $("#set-auto-setup").onchange = saveSetting("auto_setup");
  $("#set-launch").onchange = saveSetting("launch_on_start");
  $("#setup-run").onclick = async () => {
    await fetch("/api/apps/setup", { method: "POST" }); pollSetup(); setTimeout(loadApps, 4000);
  };
  $("#worker-model").onchange = async (e) => {
    const d = await (await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ worker_model: e.target.value }) })).json();
    state.workerModel = d.worker_model; paintWorkerSelect();
  };
}

/* ---------- IDE (Antigravity-style) ---------- */
// The one chat (thread + composer) lives in the Chat view; opening the IDE moves the
// same DOM into the right-hand Agent panel, so there's never a second chat to sync.
function moveChat(toIDE) {
  const wrap = $(".composer-wrap");
  if (toIDE) { $("#ide-agent-body").append(chat, wrap); }
  else { $("#chat-view .thread").append(chat); $("#chat-view").append(wrap); }
  bottom();
}
function enterIDE() {
  const sb = $("#sidebar"), shell = $("#shell");
  moveChat(true); loadTree();
  $("#ide-agent-model").textContent = modelSel.value || "";
  if (shell.classList.contains("collapsed") || getComputedStyle(sb).display === "none") { shell.classList.add("ide-mode"); return; }
  sb.classList.remove("from-light"); sb.classList.add("to-light");      // the sidebar goes into the light
  sb.addEventListener("animationend", () => { shell.classList.add("ide-mode"); sb.classList.remove("to-light"); }, { once: true });
}
function leaveIDE() {
  const sb = $("#sidebar"), shell = $("#shell");
  moveChat(false);
  shell.classList.remove("ide-mode");
  sb.classList.remove("to-light"); sb.classList.add("from-light");     // and comes back out of it
  sb.addEventListener("animationend", () => sb.classList.remove("from-light"), { once: true });
}
function wireIDE() {
  $("#ide-tabs").addEventListener("click", (e) => {
    const close = e.target.dataset.close;
    if (close) {
      state.tabs = state.tabs.filter((t) => t !== close);
      if (state.activeTab === close) {
        state.activeTab = state.tabs[state.tabs.length - 1] || null;
        if (state.activeTab) return openFile(state.activeTab);
        $("#editor-body").innerHTML = `<code><span class="ln">Open a file from the explorer, or ask the agent to write one.</span></code>`;
        $("#editor-path").textContent = "no file open"; $("#ide-status").innerHTML = "";
      }
      return paintTabs();
    }
    const t = e.target.closest(".ide-tab"); if (t) openFile(t.dataset.tab);
  });
  $("#ide-new-chat").onclick = () => { newChat(); input.focus(); };
  $("#reload-tree").onclick = loadTree;
  modelSel.addEventListener("change", () => { $("#ide-agent-model").textContent = modelSel.value; });
}

/* ---------- connectors: always ready, on per chat once asked ---------- */
async function loadConnectorNames() {
  try { state.connectorNames = ((await (await fetch("/api/connectors")).json()).connectors || []).map((c) => c.name); } catch {}
}
function connectorRe(name) {
  const body = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/[-_ ]+/g, "[\\s_-]?");
  return new RegExp(`(^|[^a-z0-9])${body}($|[^a-z0-9])`, "i");
}
function switchOnConnectors(c, text) {
  const on = c.connectors || (c.connectors = []);
  const hits = state.connectorNames.filter((n) => !on.includes(n) && connectorRe(n).test(text));
  if (!hits.length) return;
  on.push(...hits); save(); paintChatCtx();
  const note = document.createElement("div"); note.className = "ctx-note";
  note.textContent = `${hits.join(", ")} ${hits.length > 1 ? "are" : "is"} on for this chat`;
  chat.appendChild(note); bottom();
}
function chatInstructions(c) {
  const on = c.connectors || [];
  if (!on.length) return "";
  return "Instructions for THIS chat only: the user switched on these connectors: " +
    on.map((n) => `${n} (tools named mcp__${n}__*)`).join(", ") +
    ". Use them whenever a request in this chat needs that service.";
}
function paintChatCtx() {
  const c = curConvo(), el = $("#chat-ctx"); if (!el) return;
  const on = (c && c.connectors) || [];
  el.hidden = !on.length;
  el.innerHTML = on.length ? `<span class="ctx-label">This chat</span>` + on.map((n) =>
    `<span class="ctx-chip">${esc(n)}<button type="button" data-off="${esc(n)}" title="turn off for this chat">×</button></span>`).join("") : "";
  el.querySelectorAll("[data-off]").forEach((b) => (b.onclick = () => {
    c.connectors = on.filter((x) => x !== b.dataset.off); save(); paintChatCtx();
  }));
}

/* ---------- startup setup (Roblox Studio / Unreal) ---------- */
async function pollSetup(tries = 0) {
  let d; try { d = await (await fetch("/api/apps/setup")).json(); } catch { return; }
  const note = $("#setup-note"), last = d.log[d.log.length - 1] || "";
  const needsYou = d.log.some((l) => l.includes("ONE-TIME STEP"));
  note.hidden = !(d.running || needsYou);
  note.textContent = d.running ? "Setting up apps: " + last.replace(/^\S+ /, "") : "Unreal needs your Epic sign-in (click)";
  note.onclick = () => openCustomize("apps");
  paintSetupLog(d);
  // keep polling while it runs; give a just-started app a few seconds to kick it off
  if (d.running || (!d.done && tries < 5)) setTimeout(() => pollSetup(tries + 1), 3000);
}
function paintSetupLog(d) {
  const pre = $("#setup-log"); if (!pre) return;
  pre.hidden = !d.log.length; pre.textContent = d.log.join("\n"); pre.scrollTop = pre.scrollHeight;
}
