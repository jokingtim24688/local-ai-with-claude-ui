---
name: code-review
description: Review a diff for correctness bugs and simplification/efficiency wins.
---

# code-review

Read the diff adversarially. Flag: correctness bugs (off-by-one, wrong operator,
null/edge cases, races), then reuse/simplify/efficiency. For each: file:line, the
concrete failure case, and the fix. Rank by severity. Verify before asserting;
don't invent issues. Keep noise low — real findings only.
