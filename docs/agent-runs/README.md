# Agent Run Handoffs

This directory contains concise, durable handoffs from development-agent runs in Basketball Intelligence Lab. Agents should read the latest relevant handoff and the applicable GitHub issue/PR before modifying the project.

## Run naming

Use `YYYY-MM-DD-short-descriptive-slug.md` (append a distinguishing suffix if multiple runs share a slug). Small documentation tasks may have very short handoffs; major research/engineering runs need fuller notes. Use [TEMPLATE.md](TEMPLATE.md) as a guide rather than a mandatory form.

## What to capture

- Objective and authorized scope, with issue/PR references if any.
- What actually changed; affected paths; significant decisions and tradeoffs.
- What was verified, including exact commands/checks that ran and anything skipped.
- Observed failures, unresolved questions, risks and blockers.
- Branch, relevant commit(s), PR links, review/merge state and the next action.

Record **results**, not speculative success, secret tokens, large tool dumps, private scratchpads, or chain-of-thought transcripts. Keep lasting architecture decisions in the existing [docs/DECISIONS.md](../DECISIONS.md), not a second ADR registry.

## Task lifecycle

1. Read [AGENTS.md](../../AGENTS.md), [PROJECT_PLAN.md](../PROJECT_PLAN.md), the current issue, and relevant prior handoff.
2. Implement in a scoped branch; validate.
3. Record the handoff before ending the planned run.
4. Link it from the associated issue or PR when useful.
5. Mark work accurately as completed, blocked, or awaiting review.

GitHub Issues/PRs remain the durable task and review record; this directory preserves technical continuity between agent contexts.
