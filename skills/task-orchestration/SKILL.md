---
name: task-orchestration
description: Shared task board: claim ≤2, finish, hand off; reviewer redoes work that misses prompt.md.
---

# task-orchestration

Work is a shared board (tasks.json) all agents see. Tools: add_task, list_tasks,
claim_task, complete_task, review_task.

Flow:
1. The prompt-writer turns prompt.md into concrete tasks with `add_task`.
2. Each worker `claim_task` up to **2** at a time (a 3rd is refused until one is
   freed). Do the work per prompt.md, then `complete_task` → it moves to *review*.
3. On completion, claim the next open task — so a finished agent immediately picks
   up more, and unclaimed tasks flow to whoever is free.
4. The **reviewer** checks each *review* task's code AND design against prompt.md.
   - meets it → `review_task verdict=approve` (→ done)
   - disagrees with code or design → `review_task verdict=redo` with a reason →
     it goes back to *todo* for another agent to redo.
5. Repeat until the board is all *done*.

Keep the bus updated (3P style: Progress / Plans / Problems) so others coordinate.
Never mark done work you didn't verify; never approve work that misses prompt.md.
