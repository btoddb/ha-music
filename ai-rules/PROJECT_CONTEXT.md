# Project Context

This file provides guidance to AI coding agents when working with code in this repository.

**These rules are non-negotiable — follow them exactly.**

## Project Overview

This repo is a single Home Assistant **custom integration**, `btoddb_ha_reminders`
(HACS-installable), that allows the user to setup reminders, and have HA remind them at the specified time.

The repo is based on the `integration_blueprint` dev scaffold: `config/` is a throwaway
HA instance for local testing, `scripts/` holds dev helpers, and `requirements.txt`
pins the HA/lint toolchain.

Every directory under `custom_components/` **except `btoddb_ha_reminders`** is a
**vendored third-party integration** kept only for local testing (currently
`custom_components/dreo/`). Never modify any of them. If any command — including
`scripts/lint` — leaves changes under one of these directories, revert them; never
commit a diff outside `btoddb_ha_reminders`.

## Implementation details

- **Python version:** target python version 3.14 or newer
- **Ruff Formatting:** format all code according to the ruff formatting rules
- **Ruff Linting:** Ensure coding decisions are made with ruff linting rules in mind

## Key dev commands

- **Run HA locally:** `scripts/develop` (launches HA against `config/`). It runs HA
  in the **foreground** with `--debug` and does not return — to verify a change,
  background it and read `config/home-assistant.log`. Node/npm *are* available in
  this devcontainer (Node feature); `scripts/develop` is unrelated to the card build.
- **Lint:** `scripts/lint` (ruff). It **rewrites files** (`ruff format` +
  `ruff check --fix`) — it is not a check-only command, so expect working-tree
  changes after it runs.
- **Engine unit tests (no HA needed):** `python3 -m pytest` (from the repo root;
  `pytest.ini` sets `testpaths` and `conftest.py` inserts its own directory into
  `sys.path` so `load_module` is importable regardless of working directory)
- **Validate manifest/HACS:** `python3 -m script.hassfest` and the
  `.github/workflows/validate.yml` workflow.
- **Hassfest locally (Docker):** `scripts/validate` runs CI's Hassfest check
  (`ghcr.io/home-assistant/hassfest`) against the working tree — use it to catch
  manifest/dependency/translation errors before pushing. Requires Docker.
- **Build the card:** `scripts/deploy.sh` builds, bumps the version, and copies
  into `www/`. Edit the TypeScript source at
  `custom_components/btoddb_ha_reminders/card/src/*.ts` — never hand-edit the
  generated `www/*.js` bundle. (Card-specific guidance lives in that folder's
  `CLAUDE.md`.)

## Versioning

There are **two independent version numbers** — never hand-edit either:

- **Integration:** `manifest.json` (`"version": "vX.Y.Z"` — the leading `v` is
  intentional). Bumped only by `scripts/create-release.sh`.
- **Card:** `card/package.json` (plain `X.Y.Z`). Bumped only by `scripts/deploy.sh`,
  which also syncs the console banner in `card/src/index.ts`.

<!--
  DON'T EDIT BELOW THIS COMMENT, THIS PART SHOULD BE COPIED FROM THE WORKFLOW PIPELINE (btoddb/claude-pipeline)

  Shared `@claude` pipeline contract for CLAUDE.md.

  Paste this block into the consuming repo's own CLAUDE.md (there is no
  GitHub mechanism to "include" a remote markdown file at runtime, so each
  repo carries its own copy). Replace every <MAINTAINER> (@btoddb) with the GitHub
  username configured as the `maintainer` input in that repo's caller
  workflow, and adjust the `--allowedTools` examples in the Implementation
  and Review sections to match the repo's actual lint/test commands.
-->

## GitHub Workflow

`.github/workflows/claude.yml` is driven by **`@claude` commands**. A `dispatch`
job parses the text that mentions `@claude` and routes the run; the model is then
fixed per phase (you do not, and cannot, switch models yourself mid-run):

| Where you write it | Command | What runs |
| --- | --- | --- |
| New issue body/title, or any issue comment | `@claude` | Full pipeline: **plan (Opus)** → **implement (Sonnet)** if the plan has no open questions |
| New issue body/title, or any issue comment | `@claude plan` | **Planning only (Opus)** — posts the plan as a comment, never implements |
| Any issue comment | `@claude implement` | **Implementation only (Sonnet)** — skips planning, implements the latest `<!-- claude:plan -->` comment and opens a PR |
| PR comment / PR review | `@claude review` | **Line-by-line review (Opus)** — posts tagged comments; cannot change code (`contents` is read-only) |
| PR comment / PR review | `@claude revise` | **Iterate on the PR (Sonnet)** — re-implements from the feedback in your comment, committing to the PR branch; gets the same code-changing tools and language setup as `implement` |
| PR comment / PR review | `@claude ship [--force] [--public-release] [--bump-patch\|--bump-minor\|--bump-major]` | **Ship (no model)** — squash-merges the PR, deletes the branch, then runs `scripts/ship` to cut a release; add `--force` to skip the all-green guard |
| PR comment / PR review | `@claude` | Conversational reply — **Opus** for a submitted review, **Sonnet** for follow-up comments |

The subcommand is the word immediately after `@claude`; bare `@claude` defaults to
the full pipeline (on an issue) or a conversational reply (on a PR). `@claude
implement` bypasses the no-questions gate — it's an explicit instruction to build
the most recent plan as-is. `@claude revise` is the PR counterpart to `implement`:
use it (not bare `@claude`) when you want code changes on an open PR, because the
plain conversational reply does **not** carry the deploy/lint/test/npm tools.
`@claude plan` / `@claude implement` are issue-only and `@claude review` /
`@claude revise` / `@claude ship` are PR-only. A subcommand used in the wrong
context (e.g. `@claude implement` on a PR, `@claude review` on an issue) or one
that isn't recognized does **not** silently fall back: the `notify` job posts a
comment explaining that nothing ran and lists the valid commands. A plain comment
with no `@claude` mention never starts the pipeline at all.

So planning is no longer tied to issue-open: commenting `@claude` (or `@claude
plan`) on an already-open issue triggers it too. Adding more parameters later is
a matter of extending the `dispatch` job's parser.

The plan→implement handoff is a job dependency inside one run, not a re-trigger:
GitHub will not start a new workflow run from a comment the action posts with
`GITHUB_TOKEN`, so the pipeline is chained via `needs:` instead.

After each phase, the workflow posts a short comment recording the **actual**
model id the API reported for that run (read from the action's execution log,
not the requested `--model`) — on the issue for planning, on the PR for
implementation. This is automatic; you don't need to report your own model.

If a phase fails outright — usage/token limit reached, an API error, a
timeout — the pipeline's failure helper posts a `@btoddb`-tagged comment
naming the phase and, heuristically, the likely cause (usage/token limit vs.
a generic failure), instead of the run just going red with no comment. Every
phase job (`respond`, `review`, `revise`, `implement`, and the `plan` job's no-plan
gate) wires this in. This is automatic; you don't need to invoke it yourself.

Every Claude-running phase can file a follow-up GitHub issue with
`gh issue create` when it discovers work that belongs outside the current task.
This uses the workflow's `issues: write` token and does not relax each phase's
code-write boundary: planning, review, and conversational replies still cannot
edit files or push branches.
Call `gh issue create` non-interactively, with `--title` and `--body` spelled
out, so GitHub CLI never prompts or fails for missing required input in CI.

### Planning (Opus)
- For every new issue, Opus must read the codebase and generate a structural implementation plan before making any code changes.
- Ensure the plan is clear and outlines the required steps.
- **constraint** Opus must post the completed plan **as a comment on the issue** — this is the only thing that carries the plan to the implementation job.
- **You do NOT write any `<!-- claude:* -->` markers.** The workflow's gate step stamps `<!-- claude:plan -->`, `<!-- claude:plan-comment-id:... -->`, and when appropriate `<!-- claude:proceed -->` itself, deterministically, after your plan is posted. Hand-writing them does nothing useful and can confuse the gate — just write the plan. (Markers used to be your job and were forgotten, silently skipping implementation; that is why they moved into the pipeline.)
- **The proceed-vs-park decision is driven entirely by `[QUESTION]` items in your plan body** — this is the one machine signal you control:
  - **No open questions** → write none, and the gate auto-stamps the proceed marker; Sonnet implements and opens the PR with no human step.
  - **Any open question** → write it as a `[QUESTION]` item (literal `[QUESTION]` tag) and `@btoddb` so they are notified. The gate sees the tag and parks implementation until a newer plan resolves it. Use `[QUESTION]` *only* for genuine blockers — a stray `[QUESTION]` anywhere in the body will park the run.
  - For an **`@claude plan`** (plan-only) request, just write the plan; the gate stamps the plan marker but never proceeds, regardless of questions.
- **constraint** A plan **revision** is posted as a **new** comment — never silently rewrite history. The pipeline always uses the **most recent** plan comment from the run.
- **constraint** When re-planning (any `@claude plan` after an earlier plan comment exists), read the full issue thread first: find the prior plan's `[QUESTION]` items and check later comments for answers to them. Resolve answered questions in the revision instead of re-asking — only re-raise a `[QUESTION]` if it's genuinely still unanswered or unresolved.
- Planning may file follow-up issues with `gh issue create`, but it remains code-read-only: it cannot edit files, commit, or push.

### Implementation (Sonnet)
- Sonnet should execute the approved plan strictly. The workflow resolves the approved Opus plan comment from the control marker and passes that plan to Sonnet as explicit implementation-phase prompt context; use that approved plan as the source of truth.
- **constraint** The gate already validated a plan exists in a real (non-sandboxed) check before you ran — do not re-verify markers yourself or comment on whether any marker is present/missing in your PR summary. If you were invoked, a valid plan was already found; just build it.
- **constraint** **NEVER** work on main.  Create a new branch for the changes
- Implement the code and cut a Pull Request (PR) referencing the original issue. Opening the PR is the deliverable — don't finish without it. If Claude pushes changes but does not open the PR, the workflow creates it; if there is no pushed branch or no diff, the workflow fails instead of silently succeeding.
- **constraint** Call `gh pr create` non-interactively, with every flag spelled out — never bare `gh pr create` and never `--fill`. Bare invocations prompt interactively and will hang the run. Use:
  `gh pr create --base main --head <branch> --title "<title>" --body "<body>"`
  `Bash(gh pr create *)` is granted for exactly this; use it instead of leaving a compare/quick_pull link (the action's default, which does **not** satisfy the line above).
- **constraint** A re-run of `@claude implement` on a branch that already has a PR will hit `gh pr create`'s duplicate-PR error — that's fine, **not** a failure to fix. `gh pr list`/`gh pr view` aren't in `--allowedTools`, so don't reach for them: `gh pr create`'s own error message already contains the existing PR's URL, so on that specific error just report the existing PR from it instead of retrying.

### Revision (Sonnet)
- `@claude revise <feedback>` runs on an **open PR** and is the only PR command that changes code. It checks out the PR's head branch, applies the requested changes, and commits **to that same branch** — it does not open a new PR.
- It shares `implement`'s toolset (the `IMPL_TOOLS` list in the workflow + the repo's `implement-allowed-tools`) and runs the same language **setup + install** steps, so lint, tests, `scripts/deploy.sh`, and `npm` are all available while iterating.
- It can file follow-up issues with `gh issue create` for work discovered while revising that does not belong in the current PR.
- **constraint** Read the PR thread and the triggering comment first; make the change the feedback asks for, then push it to the PR branch. Don't open a second PR for the same work.

### Ship (no model)
- `@claude ship [--force] [--public-release] [--bump-patch|--bump-minor|--bump-major]` runs on an **open PR** and is the only command with no LLM involved — it's fully deterministic.
- It squash-merges the PR, deletes the head branch, checks out `main`, then runs `scripts/ship` in the repo root.
- **constraint** By default, ship requires **all checks to be green** before merging — failed, pending, and in-progress checks all block it. The comment it posts names each blocking check and its status. Add `--force` to override: `@claude ship --force`.
- **constraint** Each repo must provide `scripts/ship`. Use `templates/ship.template` from the pipeline repo as a starting point. The default template creates a pre-release tagged `<version>` with title `<version>-beta`; `--public-release` creates a `--latest` release.
- **constraint** If `scripts/ship` is missing, the job fails with guidance to create it. This is intentional — the pipeline does not assume a release strategy.
- `scripts/ship` is any executable with a shebang — the bash template is just a reference; consumers can use Python, Deno, or any other runtime.
- Client `scripts/ship` implementations are recommended to support `--public-release`, `--bump-patch`, `--bump-minor`, and `--bump-major`. The workflow forwards these flags to `scripts/ship`; `--public-release` should create a public "latest" release instead of a pre-release, and the bump flags should increment the release version by patch, minor, and major respectively.

#### What Not to Commit
- Build artifacts, generated bundles, and compiled outputs (unless the project explicitly tracks them).
- Dependency and cache directories: `node_modules/`, `__pycache__/`, `.venv/`, and equivalents.
- OS-generated files (`.DS_Store`, `Thumbs.db`) and editor swap/lock files.

#### Security
- **constraint** Never commit secrets, API keys, credentials, `.env` files, or private config — not even in test or scratch branches.
- **constraint** Flag any security vulnerability (XSS, SQL injection, command injection, etc.) and fix it before reporting the task complete.

### Review (Opus)
- **constraint** On any new PR, Opus should perform a line-by-line review.
- Add specific, actionable comments in the PR.
- **constraint** Always **post your review as a PR comment** — never finish silently. Even when you find nothing to flag, post a short, warm summary that names what you reviewed and explains specifically why it's solid (not a bare "LGTM").
- Stop, wait, and request explicit human approval before attempting any fixes or merges.
- **constraint** If you are asked to review a PR, **NEVER** make changes to the code base.  You are free to add comments with snippets of suggested code.
- Review may file follow-up issues with `gh issue create`, but it still cannot change the PR branch.

If you leave a comment on the PR, and it is more than just a comment, tag each comment with one of the following:
- [REQUIRED]: A critical issue that must be fixed before approval
- [QUESTION]: Asking for clarification on why an implementation was chosen
- [NIT]: Minor styling, naming choices, or optional micro-optimizations that won't hold up approval
- [PRAISE]: Highlighting particularly clean, clever, or well-written sections of code
