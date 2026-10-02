# >>> PIVOT 44 — whole-app test (2026-10-02) <<<
tests_app.py: 55 checks against a stub Ollama in a temp workspace + temp data dir — every GET
route, X-NC guards, 6 sandbox-escape attempts, a real session (list -> read -> missing-file
steer -> write bad Java -> javac fails -> rewrite -> javac passes -> delete), the honesty
guards (false claim / proposal / repeat / thinking-only), the approval gate incl. a DENIED
tool not running, compaction on a 73k chat, routing, the model fitness test, a live MCP
server over stdio, and UI id wiring. All pass.
REAL BUG it found: tools.scan_skills() cleared SKILLS before checking the folder, so
GET /api/skills with a missing/empty skills dir wiped the catalogue and killed routing until
restart. Now a missing or empty dir leaves the loaded skills alone.

# >>> PIVOT 43 — real context compaction (2026-10-02) <<<
trim_history DELETED the oldest turns, so long chats lost the file just written and the lead
answered with nothing. context.compact(msgs, budget, summarise, keep_recent=6) now summarises
that span into one "[earlier in this chat] …" user message via the resident model (app.py
passes _sum()). Cached by sha1 of the span so it runs once per long chat, never splits a tool
result from its call, keeps the system prompt, falls back to trim_history when there is no
summariser or it raises. Verified: 72.6k-char history -> 10.4k sent, summary present, user
told "(compacted 74 earlier messages…)". 10 unit cases + 1 end-to-end.

# >>> PIVOT 42 — orbit spinner, smooth pinned scroll, proposals pushed into action <<<
1. static/app.js bottom(): smooth scrollTo, but only when `pinned` (user within 80px of the
   bottom) — reading back is no longer interrupted. Honours prefers-reduced-motion.
2. showOrbit()/hideOrbit()/setOrbitLabel(): sun + 2 orbiting planets in the accent colour,
   appended to the chat while busy, label follows the work ("running write_file…"). WAAPI,
   not CSS keyframes (Windows animation-effects-off = prefers-reduced-motion freezes those).
3. toolcalls.proposes_work(): "we should create…", "let's compile…", "next step is to…",
   "here is the code:". When nothing ran and the reply only proposes, the loop pushes once
   ("do it NOW with real tool calls") — this is the "qwen said we should create the file and
   did nothing" case; claims_work_done deliberately ignores proposals. 16 phrase cases +
   3 end-to-end turns + a regression case.

# >>> PIVOT 41 — abliterated model installer (2026-10-02) <<<
User wants ~20 abliterated models to rank in-app. Searched HF: most "abliterated instruct"
hits are creative-writing merges, useless for tool calling. Shipped 10 VERIFIED ones
(repo + exact Q4_K_M filename + size checked via hf_fs) in
scripts/install_abliterated_models.ps1: llama3.1-abl x3, qwen2.5-7b-instruct-abl, qwen3-abl x2,
granite3.3-abl, LFM2.5-Hermes-agentic (own template), hermes3-abl-3b, qwen2.5-coder-abl.
Downloads with curl.exe (ollama pull hf.co/... hits the CDN "blocked redirect" on the user's
box) and borrows the matching official Ollama template so tool calling works. ~46 GB total.
NOTE: there is NO abliterated Hermes-3 8B on HF, only 3B.

# >>> PIVOT 40b — rank every installed model (2026-10-02) <<<
POST /api/model/test {"all": true} -> test_all_models(): every installed chat model (SKIP_MODELS
drops embed/rerank/clip...), keep_alive=0 so each unloads, sorted by score desc. "Rank all my
models" button next to "Test the lead model". Verified on 4 stub models incl. an embedding one.

# >>> PIVOT 40 — MCP tools never reached the model + model fitness test (2026-10-02) <<<
1. REAL BUG: MCP connectors only loaded when the chat TEXT contained the connector name
   (UI switchOnConnectors). "create a project" / "delete a couple of files" therefore ran with
   zero engine tools even though the servers were enabled and running. api_chat now auto-adds
   the BUILTIN connector matching skill_router.domain_of(task). Verified: "create a new unreal
   project" -> mcp__unreal__* reach the model; a no-domain message still gets none.
2. POST /api/model/test + "Test the lead model" button (Customize -> Apps): checks plain-text
   answering and real tool calling (native OR text-typed-and-recovered), verdict =
   good lead / worker-only / not usable. 4 stub models tested.

# >>> PIVOT 39 — real build tools per language (2026-10-02) <<<
Only gradle existed, so the lead could not build a C#/JS/Python/C++ app at all. Added to
apps.py: dotnet, npm, node_run, python_run, cmake_build, maven (+ FINDERS/LABELS for
dotnet/node/npm/cmake/gcc/python/javac/maven so app_status reports them). All share
_toolchain(): workspace-jailed, gated, error lines first then tail, honest "not installed,
install from X" when the toolchain is missing. DOMAIN_TOOLS: csharp->dotnet, web->npm+node_run,
python->python_run, cpp->cmake_build, java->gradle+maven. Verified end to end in the sandbox:
cmake produced a Demo binary that ran, a broken .cpp surfaced the real error, python traceback
and node output came back, missing dotnet gave the install hint, /etc/passwd stayed blocked.

# >>> PIVOT 38 — act-don't-ask prompt, typo-tolerant routing (2026-10-02) <<<
User: "I shouldn't have to ask for a command to be run" + typos should just work.
1. SYSTEM_PROMPT: ACT DON'T ASK (run the steps, "should I run it?" is not a question),
   typo paragraph (read what they MEANT, never correct them, glob to resolve near-names),
   gradle-not-javac + build->read error->fix->build loop, delete_file + confirm with list_dir,
   "finish the whole request before answering".
2. skill_router.score -> (exact, fuzzy) tuple so exact always beats fuzzy; _close() needs same
   first letter + len diff <=2 + ratio >=0.80. Found by "make a cube in blendr" -> cpp
   ("make"~"cmake"). lang-java triggers widened (mod/mods/modding/minecraft/compile/gradlew/
   mixin). GENERAL_APP_TOOLS now includes gradle, so "compile the mod" offers it even with no
   domain match. tests_routing.py = 17 cases, typos and correct spellings.

# >>> PIVOT 37 — repeat guard was blocking real build loops (2026-10-02) <<<
Screenshot: write_file -> `javac` came back "(already called ... this turn)" and the build
stalled. The guard keyed only on (tool, args), so the edit-compile-edit-compile loop looked
like a repeat. Key is now (tool, args, world); `world` increments on every successful
write_file/edit_file/delete_file (WRITE_TOOLS in app.py). Tested: compile->fail->write->
compile RUNS AGAIN, while an unchanged-state repeat is still blocked after one warning.

# >>> PIVOT 36b — claim detector fixes (2026-10-02) <<<
Real miss from a screenshot: "The ... files have been successfully deleted. ... The compilation
process WILL generate the .jar" was NOT flagged, for two reasons, both fixed:
 - an adverb between "been" and the verb ("been successfully deleted") broke the pattern, and
   delete/remove were missing from the "successfully <verb>" list;
 - claims_work_done() split by LINES, so the later "will generate" (a NOT_A_CLAIM hit) excused
   the earlier claim in the same paragraph. It now splits per SENTENCE.
18 phrase cases + 3 regression turns (incl. an honest plan that must NOT be flagged).

# >>> PIVOT 36 — mechanical hallucination flag + updater closes dupes (2026-10-02) <<<
1. toolcalls.claims_work_done(): regex set for completion claims, with a NOT_A_CLAIM guard so
   plans ("I would create", "to build this, run") don't match. app.py tracks ran_ok (any tool
   result not error/FAILED/blocked); claim + nothing succeeded -> a ⚠ line is appended to the
   reply. 12 phrase cases + 4 end-to-end turns tested; regression case added.
2. launcher.close_running(): psutil, terminate-then-kill any other "Night Crew"/desktop.py in
   THIS folder (never self or a parent) before launch(), so an update leaves one window.

# >>> PIVOT 35 — delete_file + workspace-only execution (2026-10-02) <<<
User: deletes and commands must stay in the workspace (they point the workspace at their
project via IDE -> PC -> Use). run_command cwd now goes through _jail (not _read_jail),
gradle resolves + stops its gradlew walk-up at the workspace root, and delete_file(path,
recursive) is workspace-only, gated, refuses the root and needs recursive for folders.
Reads still reach registered project folders. 8 cases tested incl. .. escape and absolute paths.

# >>> PIVOT 34 — gradle/builds, no-hallucination rule, real window drag (2026-10-02) <<<
1. tools.run_command(command, cwd, timeout): runs in the workspace OR a registered project
   folder, up to 1800s, output trimmed. apps.gradle(task, project) walks up for gradlew/.bat,
   surfaces error lines. Both GATED. DOMAIN_TOOLS["java"] = ["gradle"] so the lead gets it.
2. SYSTEM_PROMPT: never claim built/compiled/created unless a tool call returned success.
3. desktop.Api.drag_start/drag_move + #titlebar pointer handlers in app.js = window dragging
   that actually works on WebView2 (pywebview's drag region does not). dblclick = maximize.
   Untested on real Windows — the user must confirm.

# >>> PIVOT 33 — repeated-tool-call loop (2026-10-02) <<<
qwen3-abl called `remember` with the SAME note 9+ times (user screenshot) until the 12-round
cap. Now done_calls/seen_calls key on tool+args: run once, 2nd time returns a canned
"nothing changed, answer now", and `looping` + loop_strikes ends the turn after one warning
(the check sits AFTER the dispatch loop — before it, the flag was always still False).
Same guard in _run_subagent. Verified: 1 real call, <=3 bubbles, never a blank reply.

# >>> PIVOT 32 — silent turns on thinking models (2026-10-02) <<<
Qwen3 lead returned NOTHING in the UI: the loop only read message.content, and the
"blank reply" notice was gated behind `acc.strip()`, so a turn with thinking-only output
printed nothing at all. Now: think_arg() sends `think` only to models whose caps include
"thinking" (default OFF, setting `think` + Customize checkbox), message.thinking is
collected, and an empty turn always explains itself (thinking-only / nothing / typed-JSON).

# >>> PIVOT 31 — chats persist on disk; read-not-create fix; language skills (2026-10-02) <<<
1. Chat history was lost whenever desktop.free_port() picked 5174/5175/0: localStorage is keyed by
   origin. Chats/projects/instructions now live in NightCrew-data/chats.json via GET/POST /api/chats
   (X-NC header, atomic write-then-rename, 400ms debounce, one-time migration from localStorage).
2. tools: read_file/list_dir/glob/grep also reach registered project folders (apps.json) via
   _read_jail; missing-file error lists near matches and forbids inventing it; exec_tags no longer
   overwrites an EXISTING file when the block has no `run` (that was silent data loss).
3. skills/lang-{python,java,csharp,cpp,web}: layout, build+check commands, real menu-bar code,
   traps. Auto-checks added for .java (javac), .c/.cpp (-fsyntax-only), .ts (tsc --noEmit).

# >>> PIVOT 30 — chat-output fix + tool-capability detection (2026-10-01) <<<
1. toolcalls.visible_text(): tool-call JSON a small model TYPES never reaches the chat (also fixes
   duplicated prose after a nudge, half-streamed calls, blank replies). tests_chat_output.py guards it.
2. app.py: model_caps() = `ollama show` capabilities; /api/models returns {tools:{model:bool}};
   picker labels "· no native tools". A lead/worker WITHOUT tools gets text_tool_note() (tools listed in
   the prompt, one JSON line to call) and extract_calls() runs it, so any community model can drive apps.
3. SYSTEM_PROMPT: answer in plain sentences, never JSON.
Not verified: which abliterated tags exist (ollama.com blocked in the sandbox) — user picks on their PC.
Suspect for garbled 3B output: OLLAMA_KV_CACHE_TYPE=q4_0 default (set env to q8_0 to override).

# >>> PIVOT 29 — our own MCP server per app + live bridges — DONE (2026-09-30) <<<
Redo recipe:
1. mcp_servers/core.py = tiny stdio JSON-RPC MCP server (no SDK; schemas from the Python signature;
   returns (text, png) for image content). mcp_servers/{blender,unreal,roblox,openscad,fortnite}.py
   = 60 tools. `python desktop.py --mcp <name>` runs one (desktop.py checks --mcp before importing app).
2. live.py = bridges: Blender add-on TCP 9876 (token ~/.nightcrew/bridge.token), Roblox plugin queue
   HTTP 9877 (X-NC header + token), Unreal Remote Control 30010 (+ unreal_enable_live writes plugins
   + DefaultRemoteControl.ini). bridges/blender/nightcrew_bridge.py, bridges/roblox/NightCrewBridge.lua.
3. app.py: startup_bridges() (hosts the Roblox queue, seeds builtin connectors), /api/bridges GET+POST.
   UI: Customize > Apps > Live control buttons.
4. Plan tools take `spec` inline (core.plan_arg saves plans/<name>.json); engines._load_plan accepts JSON text.
   engines.openscad_render(defines=) for -D overrides; island z_scale (default 12) + relative DEVICES.md paths.
5. examples/CrescentIsles = a full map built through the MCP tools as a test.
Tested: real MCP client lists 60 tools in 0.7s; Blender/Roblox bridges tested against stand-ins;
OpenSCAD renders. Unreal live + real Blender/Studio untested (no Windows/engines here).

# >>> PIVOT 28 — Sign in with Google + keychain vault — DONE (2026-09-30) <<<
Redo recipe:
1. vault.py: keyring on win32/darwin only (Credential Manager / Keychain), else chmod-600 vault.json.
2. google_auth.py: OAuth installed-app + PKCE + 127.0.0.1 loopback, httpx only; scope gmail.readonly;
   refresh token in vault (`google.refresh_token`); /api/google/signin|signout need X-NC:1.
3. integrations.py: secrets -> vault (telegram.token, gmail.client_secret), old plaintext migrated out of json.
   gmail schema = client_id, client_secret, account, whitelist, interval (app_password REMOVED).
4. gmail_listener.py: Gmail API (list unread from whitelisted senders, format=full), same Listener/recent API.
5. UI Integrations tab: client id/secret, Sign in / Sign out, status. docs/INTEGRATIONS.md = user setup.
6. keyring added to requirements + both build configs.
Tested in sandbox with mocked Google (PKCE, bad-state reject, refresh, revoke). NOT tested on real Win/mac.

# >>> PIVOT 27 — Telegram bot + Gmail watcher + scraper — DONE (2026-09-30) <<<
Redo recipe:
1. scraper.py (trafilatura -> markdown; SSRF guard; optional Playwright render) + web.py tool `web_scrape`
   (only on /web turns). Chosen over crawl4ai/Firecrawl/Scrapy: tiny, pure Python, builds cleanly.
2. integrations.py: NightCrew-data/integrations.json (gitignored): telegram{token,owner_id,pair_code,model,auto},
   gmail{address,app_password,whitelist,interval}. Secrets masked in /api/integrations (POST needs X-NC:1).
3. telegram_bridge.py: long-poll; owner-locked (pair via `/pair <6-digit code>`, strangers get silence);
   runs the real /api/chat loop via app.test_client; approvals = inline buttons; writes files back as documents;
   /new /web /auto /model /files /open /mail /status.
4. gmail_listener.py: IMAP read-only (BODY.PEEK), whitelist senders only, notifies owner on Telegram;
   mail text is NEVER executed as instructions.
5. app.py startup_integrations() (also called in desktop.serve); UI Customize > Integrations tab.
6. Installers: requirements (trafilatura, httpx), install.sh/.bat offer Playwright, builds include the packages.
Not built yet: MCP per-prompt routing, doc editing, web automation w/ vault, handwriting, installer .iss.

# >>> PIVOT 26 — images + vision fallback + context control — DONE (2026-09-30) <<<
Redo recipe (if lost): 
1. vision.py: is_vision(name), save_image -> workspace/attachments/, describe() via small vision model
   (setting vision_model, default qwen2.5vl:3b, keep_alive=0), prepare(): native images for a vision
   lead, else description appended as text. Only newest user msg keeps images.
2. context.py: collapse_tool_outputs (old tool results -> head/tail), trim_history (drop oldest turns).
3. app.py: settings num_ctx (16384) + vision_model; ctx_size(); api_chat calls vision.prepare, emits SSE
   `image_note`, runs collapse+trim before every model call.
4. desktop.py: OLLAMA_KV_CACHE_TYPE default q4_0 (needs flash attention, already set).
5. UI: Image chip + file input, paste handler, drag-drop, thumbnail strip, downscale to 1280px JPEG,
   `images` sent on the newest message only (never saved to localStorage), image_note handler.
Deferred (NOT built, scope unconfirmed): Telegram bridge, MCP per-prompt routing, doc editing,
web automation, Gmail, installer. Ask user which next.

# >>> ENGINE BRIDGE — DONE (see docs/ENGINE_BRIDGE.md). User's prompt was cut off after Component 1 <<<
Goal: OpenSCAD + UE5 + UEFN/Verse + Roblox bridge for a 3B lead (qwen2.5-coder:3b),
dynamic skill loader, execution tags, JSON plans, CLI.
- [x] skill_router.py, exec_tags.py, engines.py, apps.py registration
- [x] skills: openscad-cad, fortnite-map-maker, roblox-obby-builder, unreal-level-layout (+triggers on old ones)
- [x] app.py: routed skills in lead + worker prompts, domain tool filtering, exec tags -> calls,
      auto-checks (.scad compile, .verse lint, plan validate), specialists openscad/fortnite
- [x] nightcrew_cli.py, docs/ENGINE_BRIDGE.md, tests, commit/push

# >>> LATEST (2026-09-27) — resume here <<<
Last pushed: ef0fae3 "Make the lead act instead of printing JSON or instructions".
User reported the lead printing tool-call JSON / instructions (they were on a qwen
model; screenshots showed llama3.2:3b too). Fix shipped: toolcalls.py + lean lead +
app_control/open_url/unreal_quick_level/blender one-shot. NOT yet verified on the
user's PC. Next: read the user's queued prompt; if tool calls still fail, check which
qwen tag they use (qwen2.5-coder's Ollama template emits text calls; qwen3 / qwen2.5
instruct use real tool calls) and look at update.log + the chat output.
Open item: PR #1 README conflict — still waiting on the user's choice.

# >>> REWORK 2 (IDE + connectors + auto-setup) — DONE, see PROGRESS.md PIVOT 20 <<<
User asked: remove VM + Terminal tabs (agents keep running in the background);
IDE view looks like Google Antigravity (explorer | editor tabs | agent chat panel on
the right — the chat REPLACES "Live activity"); opening the IDE closes the sidebar
with a "going into the light" animation; connectors always on but only used when a
chat asks for one — asked once -> saved as per-chat temporary instructions; on start
the app checks Roblox Studio + Unreal Engine, installs if missing, launches them in
the background.
- [x] backend: per-chat connectors (/api/chat body.connectors), settings
      auto_setup/launch_on_start, apps auto-setup thread + /api/apps/setup
- [x] UI: drop VM/Terminal views, Antigravity IDE layout, sidebar light animation,
      chat moves into IDE agent panel, per-chat connector chips, setup banner
- [x] previews, docs, commit, push
Redo recipe: read this, `git log --oneline -10`, continue first unchecked item.

# >>> REWORK 2026-09-26 — DONE (see PROGRESS.md PIVOT 19) <<<
User asked: (1) Mac + Windows app, (2) agents manage Unreal Engine, Blender,
Roblox Studio + public docs for each, (3) theme: midnight app + Catppuccin
("cappuccino") code colors, (4) keep subagents but they run LOW-POWER coder models
that write code / 3D-model scripts; the parent (main) DEBUGS after each one finishes.
Checklist (tick in git log / PROGRESS.md PIVOT 19):
- [x] desktop.py: fix drag crash (js_api must not expose window -> Api._window),
      mac traffic-light controls, ollama discovery on mac/win
- [x] paths.py: mac data dir ~/Library/Application Support/AiHeaven when frozen
- [x] apps.py: detect Blender/Unreal/Roblox (win+mac), tools blender_run,
      unreal_run_python, unreal_uat, roblox_open, rojo, luau_check, app_launch,
      app_status, fetch_docs (whitelisted official docs + disk cache)
- [x] skills: blender-python, unreal-engine, roblox-studio (condensed public docs + links)
- [x] app.py: worker_model (default qwen2.5-coder:3b), specialists blender/unreal/roblox,
      post-run auto checks (compile/json/node/luau) + "PARENT: debug now" handoff,
      /api/apps endpoints, main-only app tools (gated)
- [x] UI: midnight theme rewrite of static/style.css, Catppuccin code blocks,
      static/hl.js highlighter, markdown code fences in chat, Apps tab in Customize
- [x] logo: crescent mark -> assets/logo.svg, icon.ico, icon.icns
- [x] build_mac.sh (+ nuitka mac flags), docs (CLAUDE.md, PROGRESS.md), previews
Redo recipe: read this list, `git log --oneline -15`, continue the first unchecked item.

# CONTINUE HERE — Ai Heaven handoff

Pick this up in a fresh chat. Branch: `claude/amazing-keller-dvibe7`.
Repo: `jokingtim24688/local-ai-with-claude-ui`. Dev in cloud sandbox (no PC access);
user pulls + runs/builds on their own Windows PC and pastes screenshots/console.

## What the app is
Native desktop app (pywebview frameless window + Flask backend, vanilla JS UI in
`static/`). Runs a local coding-agent pool on Ollama. Heaven theme, gold accent.
Parent = 2 models (prompt-maker + skill-maker) managing subagents (buddy, designer,
researcher, tester, reviewer, porter) via shared prompt.md, task board, agent bus.
See CLAUDE.md, HANDOFF.md, VM_DESIGN.md, PROGRESS.md.

## Done this session
- **Grok-bot avatars** (PIVOT 17). Each VM-tab agent = a tintable inline-SVG cloud
  face w/ two eyes, distinct color per pool slot. Working = eyes dart around; idle =
  eyes shut + greyed. Parent tool `set_avatar(name, pose)` (look/sleep/happy/think/
  alert/auto). Code: `grokAvatar()` + `screenCard()` in `static/app.js`; `.gbot`
  CSS + keyframes in `static/style.css`; backend `_avatar_color`/`_avatar_pose`/
  `set_avatar`/`AVATAR_POSE` in `app.py`, surfaced in `/api/vm` (`color`,`pose`).
  (The user's uploaded Grok PNGs are NOT reachable from the cloud sandbox — they
  live only in chat — so the face is drawn in code. Same look, animates + tints.)
- **Desktop window fixes**: force `gui="edgechromium"` in `desktop.py` (MSHTML
  fallback was freezing the window), whole top bar draggable (`pywebview-drag-region`
  on `.spacer` in `static/index.html`), set Windows AppUserModelID + pass icon to
  the window. Exe/folder icon flags already correct (`build_nuitka.py`
  `--windows-icon-from-ico`, `elysium.spec`); needs a rebuild + Windows icon-cache
  refresh to show.

## FIXED (PIVOT 19) — was: **Dragging the window from the top bar crashes with a Python `RecursionError`:**
console spams `Empty.Empty.Empty.…: maximum recursion depth exceeded`.

- Trigger: user grabbed the titlebar drag region and the window died.
- The `Empty.Empty.…` chain is pywebview's js_api bridge (pythonnet/.NET
  `Empty` objects) recursing — almost certainly the drag handling path on the
  edgechromium backend, likely interacting with our custom `Api` js_api object
  or the `pywebview-drag-region` + `easy_drag=False` combo.
- Files: `desktop.py` (`Api` class, `webview.create_window(..., frameless=True,
  easy_drag=False, js_api=api)`, the `webview.start(gui="edgechromium", ...)` call)
  and `static/index.html` (`.titlebar`, `.tb-brand`/`.spacer` drag regions).

### Things to try
1. Reproduce: `python desktop.py`, drag the top bar. Capture full traceback (the
   recursion likely originates in pywebview's `edgechromium`/`js_bridge` — run with
   `debug=True` in `webview.start` to see the real stack).
2. Suspect the **js_api serialization**: pywebview may try to JSON-serialize the
   `Api` object or a return value on drag and recurse. Ensure `Api` methods return
   `None`/plain values, never `self` or the window. They already return None —
   double check nothing implicitly returns the window.
3. Try **`easy_drag=True` + remove the `pywebview-drag-region` classes** (native
   easy_drag instead of CSS regions) and see if the crash goes away. If easy_drag
   drags from everywhere (incl. buttons/inputs), scope it or re-add regions.
4. Check pywebview version pin (`requirements.txt` has `pywebview>=5.0`); a known
   drag/recursion bug may be version-specific — pin a known-good version.
5. If edgechromium drag is the culprit, consider a **JS-driven move** via the
   js_api (`api.start_drag()` on `mousedown` calling `window.move`) instead of the
   built-in drag region.
6. Verify WebView2 Runtime is installed on the PC (Win11 usually has it).

## How the user runs it (their Windows PC)
```
cd /d "%USERPROFILE%\Desktop\local-ai-with-claude-ui"
git pull origin claude/amazing-keller-dvibe7
python desktop.py                          # quick test
call buildenv\Scripts\activate && python build_nuitka.py --desktop   # real exe
```
Every new CMD window: run the `cd /d` line first. Commit msg footer:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: <session url>
```
User preference: reply caveman-brief. Save progress every 5 min to a file with
redo instructions.
