# Agent run: Add repository-wide AI development policy

- **Date:** 2026-11-22
- **Status:** Awaiting pull-request review
- **Related issues:** None; scoped repository policy setup
- **Branch:** `chore/add-agent-operating-policy`
- **Commit reference:** `cfdebeab7316ef0623948cee82e5eb70afd0a0c8` (initial AGENTS.md addition)
- **PR:** To be linked after creation

## Objective and authorized scope

Install the user-provided `AGENTS.md` policy in the Basketball Intelligence Lab repository and add only minimal supporting files/directories. Preserve the existing project plan, EPM-replication constraints and ADR location.

## Work completed

- Added user-supplied root `AGENTS.md` without changing its operating rules.
- Added `docs/agent-runs/README.md` and `TEMPLATE.md` for continuous run handoffs.
- Documented continued use of existing `docs/DECISIONS.md`, rather than creating a competing `docs/decisions/` directory.
- Linked the policy and run-handoff convention from the root README (same branch).

## Key decisions

- Keep the policy verbatim rather than add agent-specific vendor configuration or provider model names.
- Preserve the project's existing decisions register and research standards.
- Use a scoped branch and a reviewable PR; do not merge without authorization.
- No issues created for this small setup change.

## Verification performed

- GitHub connector was used to inspect existing repository files and confirm root `AGENTS.md` and `docs/agent-runs/` did not exist.
- Files were written to the scoped branch through GitHub and will be read back for verification before handoff.
- No Python tests or application behavior checks are necessary for these documentation-only changes; no claim of CI success.
- Independent review has **not** occurred; PR remains awaiting review.

## Blockers and remaining risks

- Approval/merge remains a maintainer action.
- Policy makes no unsupported claims about availability of subagents or paid model providers.

## Next actions

Review the PR; merge when approved. For subsequent coding runs, read `AGENTS.md`, relevant Issues and this handoff, then document actual verification and progress in a new run note.
