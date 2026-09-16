---
name: skill-creator
description: Write and improve SKILL.md files so the agent extends its own library.
---

# skill-creator

A skill = a folder `skills/<name>/SKILL.md`. Front-matter then body:
```
---
name: my-skill
description: One line — what it does and when to use it (drives triggering).
---
# my-skill
Concise, actionable steps + real commands/code. Keep it short; link out for depth.
```
Only name+description load into the prompt; the body loads on demand via
`load_skill`. Good descriptions = specific triggers. One skill = one job.
