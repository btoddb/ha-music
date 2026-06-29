# Requirements

This folder is the **functional source of truth** for `room_climate_controller`.
It is written for both humans and the AI agent. If the code and a `spec/` file
disagree, that's a bug in one of them — say so rather than guessing.

## Layout

| Path | What it holds |
|---|---|
| [`spec/`](spec/) | The **living spec**: how the integration behaves *today*. Always kept in sync with shipped code. |
| [`proposals/`](proposals/) | New features / changes, written as deltas against the spec. Deleted once folded into `spec/`. |
| [`TEMPLATE.md`](TEMPLATE.md) | Copy this to start a new proposal. |

Spec files:

- [`spec/climate-control.md`](spec/climate-control.md) — the reactive control engine: devices, use toggles, targets, thresholds, fan-speed tiers, fan-only override, manual mode, constraints.
- [`spec/profiles.md`](spec/profiles.md) — daily climate profiles: data model, scheduling, apply semantics, copy/paste.
- [`spec/card-ux.md`](spec/card-ux.md) — the Lovelace card: layout, settings/energy/history dialogs, profiles section, UX rules.

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

- Temperatures are in **°F**. Comparisons truncate to whole degrees (`int()`); displays may show tenths. (`CC` spec, fan/threshold rules.)
- "Device types" are always **cooling / heating / fan** in that canonical order. A room only has the devices it's configured with — absent devices are ignored everywhere (no card section, no rules, no entities).
- The control engine ([`engine.py`](../custom_components/room_climate_controller/engine.py)) is a **pure function** with no HA imports, so its rules are unit-tested in plain Python. Behavior rules in `spec/climate-control.md` should map directly onto it.
