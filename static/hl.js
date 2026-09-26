/* Offline syntax highlighter + chat markdown (code fences, inline code, bold).
   Languages the agents actually write here: Python/bpy/Unreal-Python, Luau (Roblox),
   C++ (Unreal), JS/TS/JSON, shell/batch/PowerShell. Colors live in style.css as the
   Catppuccin Mocha palette (.hl-kw, .hl-str, ...). No dependencies, no network. */
(function (g) {
  const W = (s) => new Set(s.split(" "));
  const LANGS = {
    python: {
      line: /#[^\n]*/y, block: null,
      str: /(?:[rRbBfFuU]{0,2})(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?)/y,
      deco: /@[A-Za-z_][\w.]*/y,
      kw: W("and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case"),
      cst: W("True False None self cls"),
      bi: W("print len range int float str list dict set tuple bool open enumerate zip map filter sorted min max sum abs isinstance getattr setattr hasattr super bpy bmesh mathutils unreal Vector Matrix Euler"),
    },
    js: {
      line: /\/\/[^\n]*/y, block: /\/\*[\s\S]*?(?:\*\/|$)/y,
      str: /`(?:\\.|[^`\\])*`?|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?/y,
      kw: W("const let var function return if else for while do break continue switch case default new delete typeof instanceof in of class extends super import export from as async await try catch finally throw yield this void type interface enum implements"),
      cst: W("true false null undefined NaN Infinity"),
      bi: W("console document window JSON Math Object Array Promise fetch Map Set Number String Boolean Error setTimeout"),
    },
    lua: {
      line: /--(?!\[=*\[)[^\n]*/y, block: /--\[(=*)\[[\s\S]*?(?:\]\1\]|$)/y,
      str: /\[(=*)\[[\s\S]*?(?:\]\1\]|$)|`(?:\\.|[^`\\])*`?|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?/y,
      deco: /--!\w+/y,
      kw: W("and break do else elseif end for function if in local not or repeat return then until while continue type export"),
      cst: W("true false nil self"),
      bi: W("game workspace script Instance Vector3 Vector2 CFrame Color3 UDim2 Enum TweenInfo task math string table print warn error require pcall xpcall typeof tostring tonumber pairs ipairs setmetatable coroutine os"),
    },
    cpp: {
      line: /\/\/[^\n]*/y, block: /\/\*[\s\S]*?(?:\*\/|$)/y,
      str: /(?:TEXT\()?"(?:\\.|[^"\\\n])*"?\)?|'(?:\\.|[^'\\\n])*'?/y,
      deco: /#\s*(?:include|pragma|define|if|ifdef|ifndef|endif|else|elif|undef)\b[^\n]*/y,
      kw: W("auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend if inline int long namespace new nullptr operator override private protected public return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while final uint8 int32 int64 uint32"),
      cst: W("true false nullptr NULL"),
      bi: W("UCLASS UPROPERTY UFUNCTION USTRUCT UENUM UINTERFACE GENERATED_BODY TEXT UE_LOG check ensure Super CreateDefaultSubobject NewObject GetWorld"),
      type: /^(?:[AUFTESI][A-Z]\w*|TArray|TMap|TSet|TSubclassOf|TObjectPtr|TWeakObjectPtr|FString|FName|FText|FVector|FRotator|FTransform)$/,
    },
    sh: {
      line: /(?:#|::|REM\b|rem\b)[^\n]*/y, block: null,
      str: /"(?:\\.|[^"\\\n])*"?|'[^'\n]*'?/y,
      deco: /\$\{?\w+\}?|%\w+%|\$env:\w+/y,
      kw: W("if then else elif fi for in do done while case esac function return set echo call cd export local exit goto not exist"),
      cst: W("true false"),
      bi: W("git python pip ollama blender rojo npm node cd mkdir"),
    },
  };
  const ALIAS = {
    py: "python", python: "python", bpy: "python", python3: "python",
    js: "js", javascript: "js", ts: "js", typescript: "js", jsx: "js", tsx: "js", json: "js", mjs: "js",
    lua: "lua", luau: "lua", roblox: "lua",
    c: "cpp", cpp: "cpp", "c++": "cpp", h: "cpp", hpp: "cpp", cs: "cpp", csharp: "cpp", unreal: "cpp", ue: "cpp", glsl: "cpp", hlsl: "cpp",
    sh: "sh", bash: "sh", zsh: "sh", shell: "sh", bat: "sh", cmd: "sh", ps1: "sh", powershell: "sh", console: "sh",
  };
  const EXT = { py: "py", js: "js", mjs: "js", ts: "ts", tsx: "ts", jsx: "js", json: "json", uproject: "json",
    uplugin: "json", lua: "lua", luau: "luau", cpp: "cpp", h: "h", hpp: "cpp", cs: "cs", c: "c",
    sh: "sh", bat: "bat", cmd: "bat", ps1: "ps1", glsl: "glsl", hlsl: "hlsl", usf: "hlsl" };

  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NUM = /(?:0x[\da-fA-F_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)[fFlLuU]?/y;
  const ID = /[A-Za-z_]\w*/y;

  const lineStart = (src, i) => i === 0 || src[i - 1] === "\n" || /^[ \t]*$/.test(src.slice(src.lastIndexOf("\n", i - 1) + 1, i));
  const wordStart = (src, i) => i === 0 || /\s/.test(src[i - 1]);
  // ordered rules: first match wins. [class, regex, guard?]
  function rules(L, key) {
    const r = [];
    if (key === "lua") r.push(["hl-deco", L.deco, lineStart]);           // --!strict
    if (key === "cpp") r.push(["hl-deco", L.deco, lineStart]);           // #include ...
    if (L.block) r.push(["hl-com", L.block]);
    r.push(["hl-com", L.line, key === "sh" ? wordStart : null]);
    r.push(["hl-str", L.str]);
    if (key === "python") r.push(["hl-deco", L.deco, lineStart]);        // @decorator
    if (key === "sh") r.push(["hl-deco", L.deco]);                       // $var %var%
    return r;
  }

  function tokens(src, lang) {
    const key = ALIAS[lang] || lang;
    const L = LANGS[key];
    if (!L) return [["", src]];
    const R = rules(L, key);
    const out = [];
    let i = 0, plain = "";
    const push = (cls, t) => { if (plain) { out.push(["", plain]); plain = ""; } out.push([cls, t]); };
    const at = (re) => { re.lastIndex = i; const m = re.exec(src); return m && m[0] ? m[0] : null; };
    outer: while (i < src.length) {
      for (const [cls, re, guard] of R) {
        if (guard && !guard(src, i)) continue;
        const m = at(re);
        if (m) { push(cls, m); i += m.length; continue outer; }
      }
      let m;
      if (/\d/.test(src[i]) && (i === 0 || !/\w/.test(src[i - 1])) && (m = at(NUM))) { push("hl-num", m); i += m.length; continue; }
      if ((m = at(ID))) {
        const call = /^\s*\(/.test(src.slice(i + m.length, i + m.length + 4));
        const cls = L.kw.has(m) ? "hl-kw" : L.cst.has(m) ? "hl-cst" : L.bi.has(m) ? "hl-bi"
          : (L.type && L.type.test(m)) ? "hl-type" : call ? "hl-fn"
          : /^[A-Z][A-Za-z0-9]*[a-z]/.test(m) ? "hl-type" : "";
        if (cls) push(cls, m); else plain += m;
        i += m.length; continue;
      }
      const c = src[i];
      if ("+-*/%=<>!&|^~?:".includes(c)) push("hl-op", c); else plain += c;
      i++;
    }
    if (plain) out.push(["", plain]);
    return out;
  }

  // highlighted HTML, one <span class="ln"> per line (spans never cross a newline)
  function highlight(src, lang) {
    const lines = [""];
    for (const [cls, text] of tokens(src, lang)) {
      text.split("\n").forEach((part, k) => {
        if (k) lines.push("");
        if (part) lines[lines.length - 1] += cls ? `<span class="${cls}">${esc(part)}</span>` : esc(part);
      });
    }
    // .ln is display:block, so no "\n" between lines (a <pre> would double-space them)
    return lines.map((l) => `<span class="ln">${l || " "}</span>`).join("");
  }

  function langFromPath(p) {
    const ext = (String(p).split(".").pop() || "").toLowerCase();
    return EXT[ext] || "";
  }

  function codeBlock(code, lang) {
    const label = lang || "text";
    return `<div class="codeblock"><div class="cb-head"><span class="cb-lang">${esc(label)}</span>` +
      `<button class="cb-copy" type="button">Copy</button></div>` +
      `<pre class="code"><code>${highlight(code.replace(/\n$/, ""), lang)}</code></pre></div>`;
  }

  function inline(text) {
    return esc(text)
      .replace(/`([^`\n]+)`/g, '<code class="ic">$1</code>')
      .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
      .replace(/^#{1,3} (.+)$/gm, '<span class="md-h">$1</span>');
  }

  // chat markdown: ```lang fences (an unclosed fence while streaming renders as code)
  function render(md) {
    let html = "", i = 0;
    const re = /```([\w+#.-]*)[^\n]*\n([\s\S]*?)(?:```|$)/g;
    let m;
    while ((m = re.exec(md))) {
      if (m.index > i) html += `<div class="md-text">${inline(md.slice(i, m.index).replace(/^\n+|\n+$/g, ""))}</div>`;
      html += codeBlock(m[2], m[1].toLowerCase());
      i = re.lastIndex;
      if (m[0].length === 0) break;
    }
    if (i < md.length) html += `<div class="md-text">${inline(md.slice(i).replace(/^\n+/, ""))}</div>`;
    return html;
  }

  g.HL = { highlight, render, langFromPath, codeBlock };
})(window);
