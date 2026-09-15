---
name: web-research
description: Use /web to look up terms and facts instead of guessing.
---

# web-research

Web tools only exist on turns the user prefixed with /web.

- `web_search(query)` → top links. Pick 2-3, then `web_fetch(url)` the best.
- Look up any unfamiliar word, gaming/slang term, or anything that does not
  make sense in context — search its meaning before answering.
- Quote the source, do not invent facts. If search returns nothing, say so.
- Do not claim you searched unless a web tool actually returned results.
