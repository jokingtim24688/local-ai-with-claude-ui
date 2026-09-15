const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const chat = $("#chat");
const input = $("#input");
const modelSel = $("#model");
const activity = $("#activity");

let messages = [];
let busy = false;

init();
async function init() {
  showEmpty();
  wireViews();
  wireComposer();
  wireVM();
  $("#clear").onclick = () => { messages = []; showEmpty(); };
  $("#reload-mem").onclick = loadMemory;
  $("#reload-tree").onclick = loadTree;
  await Promise.all([loadBranding(), loadConfig(), loadModels(), loadSkills(), loadMemory()]);
  loadTree(); loadVM();
}

async function loadBranding() {
  try {
    const b = await (await fetch("/api/branding")).json();
    if (b.name) { $("#brand-name").textContent = b.name; document.title = b.name; }
    if (b.logo) $("#logo").src = "/" + b.logo.replace(/^\//, "");
    const r = document.documentElement.style;
    if (b.accent) r.setProperty("--clay", b.accent);
    if (b.accent_soft) r.setProperty("--clay-soft", b.accent_soft);
    if (b.tagline) $("#status").setAttribute("title", b.tagline);
  } catch {}
}

/* ---------- views ---------- */
function wireViews() {
  const thumb = $("#thumb");
  const btns = $$("#views button");
  const move = (btn) => {
    thumb.style.width = btn.offsetWidth + "px";
    thumb.style.transform = `translateX(${btn.offsetLeft - 4}px)`;
  };
  const select = (name) => {
    btns.forEach((b) => b.classList.toggle("on", b.dataset.view === name));
    $$(".view").forEach((v) => v.classList.toggle("on", v.dataset.view === name));
    move(btns.find((b) => b.dataset.view === name));
    if (name === "code") loadTree();
    if (name === "vm") loadVM();
  };
  btns.forEach((b) => (b.onclick = () => select(b.dataset.view)));
  requestAnimationFrame(() => move(btns[0]));
  window.addEventListener("resize", () => move($("#views button.on")));
}

/* ---------- loaders ---------- */
async function loadConfig() {
  try {
    const c = await (await fetch("/api/config")).json();
    $("#workdir").textContent = c.workdir || "—";
    const st = $("#status");
    st.classList.toggle("up", !!c.ollama);
    st.classList.toggle("down", !c.ollama);
    st.lastChild.textContent = c.ollama ? "ollama online" : "ollama offline";
  } catch { setDown(); }
}
function setDown() {
  const st = $("#status"); st.classList.add("down"); st.lastChild.textContent = "offline";
}
async function loadModels() {
  try {
    const d = await (await fetch("/api/models")).json();
    modelSel.innerHTML = d.models.length
      ? d.models.map((m) => `<option>${esc(m)}</option>`).join("")
      : `<option>${esc(d.error || "no models")}</option>`;
  } catch { modelSel.innerHTML = "<option>offline</option>"; }
}
async function loadSkills() {
  try {
    const d = await (await fetch("/api/skills")).json();
    $("#skills").innerHTML = d.skills.length
      ? d.skills.map((s) => `<li><b>${esc(s.name)}</b><span>${esc(s.desc || "")}</span></li>`).join("")
      : "<li><span>drop skills/&lt;name&gt;/SKILL.md</span></li>";
  } catch {}
}
async function loadMemory() {
  try {
    const d = await (await fetch("/api/memory")).json();
    $("#memory").textContent = d.memory.trim() || "nothing remembered yet";
  } catch {}
}

/* ---------- code view ---------- */
async function loadTree() {
  try {
    const d = await (await fetch("/api/tree")).json();
    $("#tree").innerHTML = renderTree(d.tree, 0);
    $$("#tree li[data-file]").forEach((li) =>
      (li.onclick = () => openFile(li.dataset.file, li)));
  } catch {}
}
function renderTree(nodes, depth) {
  return nodes.map((n) => {
    const pad = depth ? ' class="kid"' : "";
    if (n.dir)
      return `<li${pad} class="dir">▸ ${esc(n.name)}</li>` + renderTree(n.children, depth + 1);
    return `<li${pad} data-file="${esc(n.path)}">${esc(n.name)}</li>`;
  }).join("");
}
async function openFile(path, li) {
  $$("#tree li").forEach((x) => x.classList.remove("sel"));
  if (li) li.classList.add("sel");
  $("#editor-path").textContent = path;
  try {
    const d = await (await fetch("/api/file?path=" + encodeURIComponent(path))).json();
    $("#editor-body").innerHTML = `<code>${esc(d.content || d.error || "")}</code>`;
  } catch {}
}

/* ---------- vm view ---------- */
function wireVM() {
  $$("[data-vm]").forEach((b) => (b.onclick = async () => {
    b.disabled = true;
    try {
      const d = await (await fetch("/api/vm/action", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: b.dataset.vm }),
      })).json();
      paintVM(d);
    } catch {}
    b.disabled = false;
  }));
}
async function loadVM() {
  try { paintVM(await (await fetch("/api/vm")).json()); } catch {}
}
function paintVM(d) {
  $("#vm-status").textContent = "status: " + (d.status || "unknown");
  const img = $("#vm-stream");
  if (d.stream) { img.src = d.stream; $("#vm-overlay").style.display = "none"; }
  if (d.app_url) $("#vm-app").innerHTML = `<iframe src="${esc(d.app_url)}" style="width:100%;height:100%;border:0;border-radius:12px"></iframe>`;
}

/* ---------- chat ---------- */
function wireComposer() {
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto"; input.style.height = input.scrollHeight + "px";
  });
}
function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
function showEmpty() {
  chat.innerHTML = `<div class="empty"><div class="mark"></div>
    <h2>What are we building?</h2>
    <p>Pick a model above and describe it. The AI writes, runs, and tests inside its sandbox — watch it in Code, or in the VM stream.</p></div>`;
}
function clearEmpty() { chat.querySelector(".empty")?.remove(); }
function bottom() { chat.scrollTop = chat.scrollHeight; }

function addMsg(role, text) {
  clearEmpty();
  const d = document.createElement("div");
  d.className = `msg ${role}`;
  d.innerHTML = `<div class="who">${role === "user" ? "you" : "local ai"}</div><div class="body"></div>`;
  d.querySelector(".body").textContent = text;
  chat.appendChild(d); bottom();
  return d.querySelector(".body");
}
function addTool(name, args) {
  clearEmpty();
  const a = Object.entries(args || {})
    .map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 70)}`).join(", ");
  const d = document.createElement("div");
  d.className = "tool";
  d.innerHTML = `<div class="call">${esc(name)}(${esc(a)})</div>`;
  chat.appendChild(d); bottom();
  // mirror into code-view activity feed
  const li = document.createElement("li");
  li.innerHTML = `<div class="a-tool">${esc(name)}</div>`;
  activity.prepend(li);
  return { chip: d, feed: li };
}
function addToolResult(ref, result) {
  const cls = result.startsWith("error") ? "err"
    : result.startsWith("OK") || result.startsWith("exit=0") ? "ok" : "";
  const r = document.createElement("div");
  r.className = "res " + cls;
  r.textContent = result.length > 1500 ? result.slice(0, 1500) + " …" : result;
  ref.chip.appendChild(r); bottom();
  const fr = document.createElement("div");
  fr.className = "a-res"; fr.textContent = result.slice(0, 200);
  ref.feed.appendChild(fr);
  loadTree();
}

async function send() {
  if (busy) return;
  let text = input.value.trim();
  if (!text) return;
  let web = false;
  if (text.startsWith("/web")) { web = true; text = text.slice(4).trim(); }
  addMsg("user", text);
  messages.push({ role: "user", content: text });
  input.value = ""; input.style.height = "auto";
  setBusy(true);
  try { await streamChat(web); }
  catch (e) { addMsg("assistant", "error: " + e.message); }
  setBusy(false); loadMemory();
}
function setBusy(b) { busy = b; $("#send").disabled = b; }

async function streamChat(web) {
  const res = await fetch("/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: modelSel.value, messages, web, tools: true, ask: true }),
  });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "", bodyEl = null, acc = "", ref = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const blocks = buf.split("\n\n"); buf = blocks.pop();
    for (const block of blocks) {
      const ev = /event: (.*)/.exec(block)?.[1];
      const dl = /data: (.*)/s.exec(block)?.[1];
      if (!ev) continue;
      const data = dl ? JSON.parse(dl) : null;
      if (ev === "token") {
        if (!bodyEl) { bodyEl = addMsg("assistant", ""); bodyEl.classList.add("caret"); acc = ""; }
        acc += data; bodyEl.textContent = acc; bottom();
      } else if (ev === "tool_call") {
        bodyEl?.classList.remove("caret"); bodyEl = null;
        ref = addTool(data.name, data.args);
      } else if (ev === "tool_result") {
        if (ref) addToolResult(ref, data.result); ref = null;
      } else if (ev === "approval") {
        await handleApproval(data);
      } else if (ev === "error") {
        addMsg("assistant", "error: " + data);
      } else if (ev === "done") {
        bodyEl?.classList.remove("caret");
        if (acc) messages.push({ role: "assistant", content: acc });
      }
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
      $("#modal").classList.add("hidden");
      $("#m-allow").onclick = $("#m-deny").onclick = null;
      await fetch("/api/approve", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: data.id, allow }),
      });
      resolve();
    };
    $("#m-allow").onclick = () => done(true);
    $("#m-deny").onclick = () => done(false);
  });
}
