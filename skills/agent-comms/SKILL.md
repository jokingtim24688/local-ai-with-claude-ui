---
name: agent-comms
description: How agents talk on the bus — terse 3P updates (Progress, Plans, Problems).
---

# agent-comms

Use send_agent_message / read_agent_messages to coordinate. Keep it terse and
structured so others can act without asking.

Format each update as **3P**:
- **Progress** — what you just finished (task id + result).
- **Plans** — what you'll do next (task id you claimed).
- **Problems** — blockers, or a redo reason if you're the reviewer.

Address a specific agent by name, or `all` for the pool. Read the bus at the
start of a turn to see hand-offs, redo requests, and new prompt.md announcements.
Facts only — an action counts only when its tool returned OK.
