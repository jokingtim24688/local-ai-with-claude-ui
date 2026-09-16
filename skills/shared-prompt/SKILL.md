---
name: shared-prompt
description: Every agent follows the shared prompt.md; the prompt-writer maintains it.
---

# shared-prompt

There is one shared brief the whole pool obeys: **prompt.md** in the workspace.
- It is injected into every agent's system prompt each turn. Read it and follow it.
- Whenever the goal changes, the **prompt-writer** rewrites prompt.md with
  `write_file` and announces it on the bus. Everyone picks up the new version on
  their next turn — no need to re-tell each agent.
- If prompt.md and a chat instruction conflict, prompt.md is the standing source
  of truth for the build; ask only if they truly contradict.
- To change what all agents do: update prompt.md (or ask the prompt-writer to).
