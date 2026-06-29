
## Repository setup: Dependabot → Claude review

[`dependabot-review.yml`](.github/workflows/dependabot-review.yml) posts `@claude
review` on every Dependabot PR so it gets the same Opus line-by-line review a human
typing that comment would trigger (see the `@claude` command table in
[CLAUDE.md](CLAUDE.md#github-workflow)).

That comment must be posted with a **personal access token**, not the default
`GITHUB_TOKEN` — GitHub blocks workflow runs from triggering other workflows when the
default token is used (an anti-recursion safeguard), so a `GITHUB_TOKEN`-authored
comment would never reach `claude.yml`'s `issue_comment` listener and the review would
silently never happen.

To wire this up on a repo:

1. Create a PAT scoped to this repo only:
   - **Fine-grained token** (recommended): grant **Pull requests: write**.
   - **Classic token**: grant the **repo** scope.
2. Add it as a repository secret named `DEPENDABOT_REVIEW_PAT`:
   ```
   gh secret set DEPENDABOT_REVIEW_PAT --repo <owner>/<repo>
   ```
   Or via the UI: repository → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret** → name it `DEPENDABOT_REVIEW_PAT`.

Without this secret, Dependabot PRs still open and pass CI, but never get an automatic
Claude review — you'd have to comment `@claude review` yourself.
