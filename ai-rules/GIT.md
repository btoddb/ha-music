# GIT rules

## ALWAYS Work On a Branch
- **constraint** **NEVER** work on main.  Before making any changes, create a
  fresh, clearly task-named branch from `main` for the current request (for
  example, `git switch -c feature/<task-slug> main`). Do not reuse or continue
  on a random existing branch just because it is not `main`.

## What Not to Commit
- Build artifacts, generated bundles, and compiled outputs (unless the project explicitly tracks them).
- Dependency and cache directories: `node_modules/`, `__pycache__/`, `.venv/`, and equivalents.
- OS-generated files (`.DS_Store`, `Thumbs.db`) and editor swap/lock files.

## Security
- **constraint** Never commit secrets, API keys, credentials, `.env` files, or private config — not even in test or scratch branches.
- **constraint** Flag any security vulnerability (XSS, SQL injection, command injection, etc.) and fix it before reporting the task complete.

## Before committing

- **constraint** run all tests
- **constraint** run lint
- **constraint** **Hassfest locally (Docker):** `scripts/validate` runs CI's Hassfest check
  (`ghcr.io/home-assistant/hassfest`) against the working tree — use it to catch
  manifest/dependency/translation errors before pushing. Requires Docker.
