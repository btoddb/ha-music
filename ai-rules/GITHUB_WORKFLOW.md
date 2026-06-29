
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
| PR comment / PR review | `@claude revise` | **Revision (Sonnet)** — reads the review comments and implements the requested changes, then updates the PR |
| PR comment / PR review | `@claude` | Conversational reply — **Opus** for a submitted review, **Sonnet** for follow-up comments |

The subcommand is the word immediately after `@claude`; bare `@claude` defaults to
the full pipeline. `@claude implement` bypasses the no-questions gate — it's an
explicit instruction to build the most recent plan as-is. `@claude plan` /
`@claude implement` are issue-only and `@claude review` is PR-only; a subcommand
used in the wrong context falls back to that context's bare-`@claude` behavior.

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
timeout — `.github/scripts/report-failure.sh` posts an @btoddb-tagged comment
naming the phase and, heuristically, the likely cause (usage/token limit vs.
a generic failure), instead of the run just going red with no comment. Every
phase job (`respond`, `review`, `implement`, and the `plan` job's no-plan
gate) wires this in. This is automatic; you don't need to invoke it yourself.

### Planning (Opus)
- For every new issue, Opus must read the codebase and generate a structural implementation plan before making any code changes.
- Ensure the plan is clear and outlines the required steps.
- **constraint** Opus must post the completed plan **as a comment on the issue** — this is the only thing that carries the plan to the implementation job.
- **You do NOT write any `<!-- claude:* -->` markers.** The workflow's gate step stamps `<!-- claude:plan -->` / `<!-- claude:proceed -->` itself, deterministically, after your plan is posted. Hand-writing them does nothing useful and can confuse the gate — just write the plan. (Markers used to be your job and were forgotten, silently skipping implementation; that is why they moved into the pipeline.)
- **The proceed-vs-park decision is driven entirely by `[QUESTION]` items in your plan body** — this is the one machine signal you control:
  - **No open questions** → write none, and the gate auto-stamps the proceed marker; Sonnet implements and opens the PR with no human step.
  - **Any open question** → write it as a `[QUESTION]` item (literal `[QUESTION]` tag) and `@btoddb` so they are notified. The gate sees the tag and parks implementation until a newer plan resolves it. Use `[QUESTION]` *only* for genuine blockers — a stray `[QUESTION]` anywhere in the body will park the run.
  - For an **`@claude plan`** (plan-only) request, just write the plan; the gate stamps the plan marker but never proceeds, regardless of questions.
- **constraint** A plan **revision** is posted as a **new** comment — never silently rewrite history. The pipeline always uses the **most recent** plan comment from the run.
- **constraint** When re-planning (any `@claude plan` after an earlier plan comment exists), read the full issue thread first: find the prior plan's `[QUESTION]` items and check later comments for answers to them. Resolve answered questions in the revision instead of re-asking — only re-raise a `[QUESTION]` if it's genuinely still unanswered or unresolved.

### Implementation (Sonnet)
- Sonnet should execute the approved plan strictly. The plan is the **most recent substantive plan comment Opus wrote in the thread** — use it as the source of truth. (The `<!-- claude:plan -->` marker now lives in a short control comment the *workflow* posts; that comment is the pipeline's signal, not where the plan content lives, so read the plan itself from Opus's comment above it.)
- **constraint** The gate already validated a plan exists in a real (non-sandboxed) check before you ran — do not re-verify markers yourself or comment on whether any marker is present/missing in your PR summary. If you were invoked, a valid plan was already found; just build it.
- **constraint** Call `gh pr create` non-interactively, with every flag spelled out — never bare `gh pr create` and never `--fill`. Bare invocations prompt interactively and will hang the run. Use:
  `gh pr create --base main --head <branch> --title "<title>" --body "<body>"`
  `Bash(gh pr create *)` is granted for exactly this; use it instead of leaving a compare/quick_pull link (the action's default, which does **not** satisfy the line above).
- **constraint** A re-run of `@claude implement` on a branch that already has a PR will hit `gh pr create`'s duplicate-PR error — that's fine, **not** a failure to fix. `gh pr list`/`gh pr view` aren't in `--allowedTools`, so don't reach for them: `gh pr create`'s own error message already contains the existing PR's URL, so on that specific error just report the existing PR from it instead of retrying.


### Review (Opus)
- **constraint** On any new PR, Opus should perform a line-by-line review.
- Add specific, actionable comments in the PR.
- **constraint** Always **post your review as a PR comment** — never finish silently. Even when you find nothing to flag, post a short, warm summary that names what you reviewed and explains specifically why it's solid (not a bare "LGTM").
- Stop, wait, and request explicit human approval before attempting any fixes or merges.
- **constraint** If you are asked to review a PR, **NEVER** make changes to the code base.  You are free to add comments with snippets of suggested code.

If you leave a comment on the PR, and it is more than just a comment, tag each comment with one of the following:
- [REQUIRED]: A critical issue that must be fixed before approval
- [QUESTION]: Asking for clarification on why an implementation was chosen
- [NIT]: Minor styling, naming choices, or optional micro-optimizations that won't hold up approval
- [PRAISE]: Highlighting particularly clean, clever, or well-written sections of code
