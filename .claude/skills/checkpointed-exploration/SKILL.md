---
name: checkpointed-exploration
description: Explore ambiguous or high-risk work in bounded reviewable checkpoints. Do one scoped step, summarize evidence, then park with SYMPHONY_QUESTION for operator review before continuing.
---

# Checkpointed Exploration

Use this skill when the operator wants investigation, design exploration, or risky discovery to proceed in reviewable increments instead of one long unattended run.

## Protocol

1. Choose one bounded exploration step that can be completed in this run.
2. State the step and the evidence target before acting.
3. Perform only that step. Do not continue into adjacent implementation or additional investigation.
4. Summarize what you learned, files inspected, and the next recommended step.
5. Park for operator review using the Question Park output contract:

```text
SYMPHONY_QUESTION_BEGIN
I completed this checkpoint: <summary>. Continue with <next bounded step>?
SYMPHONY_QUESTION_END
```

## Completion rule

Do not emit `SYMPHONY_RESULT: done` unless the operator explicitly says exploration is complete. Between checkpoints, always park with `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` so Symphony keeps the issue in review and resumes the same session after the operator replies.
