# Project Context

This file provides guidance to AI coding agents when working with code in this repository.

**These rules are non-negotiable — follow them exactly.**

## Project Overview

This repo is a single Home Assistant **custom integration**, `btoddb_ha_music`
(HACS-installable), that lets Home Assistant dashboards choose speaker groups,
play radio stations, shuffle playlists, stop playback, and show now-playing
metadata.

The repo is based on the `integration_blueprint` dev scaffold: `config/` is a throwaway
HA instance for local testing, `scripts/` holds dev helpers, and `requirements.txt`
pins the HA/lint toolchain.

Every directory under `custom_components/` **except `btoddb_ha_music`** is a
**vendored third-party integration** kept only for local testing (currently
`custom_components/dreo/`). Never modify any of them. If any command — including
`scripts/lint` — leaves changes under one of these directories, revert them; never
commit a diff outside `btoddb_ha_music`.

## Codex rules

- Always read and follow every file under `ai-rules/` before changing code.
- Never work on `main`; create a fresh task branch before edits.
- Keep implementation changes for this repo inside
  `custom_components/btoddb_ha_music/` unless repository metadata, docs, tests, or
  rule files must be updated for the requested task.
- Do not change, create, or delete anything in the user's production Home
  Assistant instance.

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
- **Build the card:** `scripts/deploy-card.sh` builds, bumps the version, and copies
  into `www/`. Edit the TypeScript source at
  `custom_components/btoddb_ha_music/card/src/*.ts` — never hand-edit the
  generated `www/*.js` bundle. (Card-specific guidance lives in that folder's
  `CLAUDE.md`.)

## Versioning

There are **two independent version numbers** — never hand-edit either:

- **Integration:** `manifest.json` (`"version": "vX.Y.Z"` — the leading `v` is
  intentional). Bumped only by `scripts/create-release.sh`.
- **Card:** `card/package.json` (plain `X.Y.Z`). Bumped only by `scripts/deploy-card.sh`,
  which also syncs the console banner in `card/src/index.ts`.
