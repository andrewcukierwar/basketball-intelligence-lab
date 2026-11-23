@AGENTS.md

# Claude Code notes for Basketball Intelligence Lab

AGENTS.md, imported above, is the shared policy for every coding agent. This file adds project facts and Claude Code specifics. Where they differ, AGENTS.md and explicit user instructions take precedence.

## Read first

- [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) §2: non-negotiable research rules. Never train, calibrate, select features or tune against EPM outputs. Avoid temporal leakage. Label claims **Documented**, **Inferred**, **Experimental** or **Original**.
- The open GitHub issue for the task (`gh issue view <n> --comments`) and the latest relevant handoff in [docs/agent-runs/](docs/agent-runs/README.md).
- [docs/DECISIONS.md](docs/DECISIONS.md) for settled decisions. Record new decisions there, not in a `docs/decisions/` directory.

## Commands

```sh
uv sync --locked --extra dev --extra pilot --extra rapm
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src                              # strict
```

CI runs the same checks on Python 3.12 with `pip install ".[dev,pilot,rapm]"`. The [pilot guide](docs/data-pilot.md) covers capture and builds. The [synthetic RAPM guide](docs/research/rapm-synthetic.md) covers the numerical reference and sensitivity experiment.

## Data handling

- Never commit anything under `data/` (raw, processed, interim and cache are gitignored). Source data is for private, noncommercial research only. See [docs/data-sources.md](docs/data-sources.md).
- Use a new output directory for each pilot build, and keep DuckDB spills in the private build staging directory.

## Claude Code mapping of AGENTS.md roles

- **Branches:** start from an up-to-date `origin/main` and use a `claude/issue-<n>-<slug>` prefix. Existing `codex/` branches belong to Codex runs.
- **Implementer:** the lead session, or a subagent for bounded, well-specified tasks. Use a git worktree (`isolation: "worktree"`) when subagents edit code in parallel.
- **Reviewer:** run independent review from a fresh context, using `/code-review` or a fresh subagent given the exact diff, the acceptance criteria and the relevant tests. A different model family, such as a Codex review, is preferable for material changes when the user arranges it. Name only reviews that actually ran.
- **Planning:** GitHub Issues remain the durable record. The app's task list serves as the local plan when GitHub is unavailable.
- **Handoffs and PRs:** write the handoff in `docs/agent-runs/` using [TEMPLATE.md](docs/agent-runs/TEMPLATE.md). Fill in [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md), including evidence class and leakage checks.
- Commit, push or open PRs only when the user authorizes it.
