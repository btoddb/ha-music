# Requirements

This folder is the **functional source of truth** for this Home Assistant (HA)
integration. It is written for both humans and the AI agent. If the code and a
`spec/` file disagree, that's a bug in one of them — say so rather than
guessing.

## Layout

| Path | What it holds |
|---|---|
| [`spec/`](spec/) | The **living spec**: how the integration behaves *today*. Always kept in sync with shipped code. |
| [`proposals/`](proposals/) | New features / changes, written as deltas against the spec. Deleted once folded into `spec/`. |
| [`TEMPLATE.md`](TEMPLATE.md) | Copy this to start a new proposal. |

Spec files:

- [`spec/release.md`](spec/release.md) — the repository release workflow,
  including the `/btbai ship` wrapper and repo-local release hook behavior.

## How to write requirements (for humans)

- **Each rule gets a stable ID** — `CC-1`, `PR-1`, `UX-1` (Climate-Control / PRofiles / Ux). Reference these IDs in chat, commits, and PRs so we both point at the same thing.
- **State behavior, not implementation**, unless the implementation *is* the requirement (e.g. "Low = 10%"). Write rules as testable statements.
- **Distinguish musts from suggestions.** A **constraint** is non-negotiable ("heating target must stay below cooling target"). A **suggestion** invites the agent to propose alternatives ("a 3-tier fan speed feels right"). Label them when it isn't obvious.
- **One-off instructions go in chat, not here.** "Regenerate the sample dashboard", "rename Todd's Bedroom" — those are conversational, not durable spec.
- **Bug reports go in chat or a proposal**, never appended to spec prose. The spec describes intended behavior; a bug is a deviation from it.

## How changes flow

1. New work starts as a file in `proposals/` (from `TEMPLATE.md`) or directly in chat for small things.
1. Shipped means that the proposal's **Status:** is set to shipped
2. When it ships, its behavior is **folded into the relevant `spec/` file** (update the rules, bump/add IDs) and the proposal file is **deleted**. Git history preserves it.
3. The spec never accumulates "we used to…" prose. If behavior is gone, the rule is gone.

## Conventions that apply everywhere

- Integration behavior lives under `custom_components/btoddb_ha_music/`.
- Generated Lovelace card bundles are managed by `scripts/deploy-card`; edit the
  TypeScript source and let the script update tracked generated assets.
