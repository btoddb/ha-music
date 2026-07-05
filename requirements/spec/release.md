# Release Workflow

The repository release path is driven by `/btbai ship` or by running
`scripts/ship` from a clean `main` checkout.

- **constraint REL-1** `scripts/ship` is a thin wrapper around the shared
  `btoddb/btb-pipeline` base command at
  `$BTB_PIPELINE_ROOT/scripts/btb-ship-base`, defaulting `BTB_PIPELINE_ROOT` to
  `.btb-pipeline` in the repository root. If the default local checkout is
  missing, `scripts/ship` bootstraps it by cloning `btoddb/btb-pipeline@v1` into
  `.btb-pipeline`; if `BTB_PIPELINE_ROOT` is set explicitly, missing base-command
  paths fail fast instead of being replaced.
- **constraint REL-2** Version bumps remain manifest-based for this integration:
  `--bump-patch`, `--bump-minor`, and `--bump-major` resolve the next
  `vX.Y.Z` from `custom_components/btoddb_ha_music/manifest.json`, then pass the
  resolved tag to the base command with `--set-version`.
- **constraint REL-3** Explicit release versions may be passed as
  `--set-version vX.Y.Z`, `--set-version=vX.Y.Z`, `--version vX.Y.Z`, or
  `--version=vX.Y.Z`; only one version option is allowed.
- **constraint REL-4** Repository-specific release work runs from the executable
  `scripts/ship.d/before-release-commit` hook. The hook runs
  `scripts/deploy-card` and updates the integration manifest to
  `$BTB_VERSION_TAG` before the base command creates the release commit.
- **constraint REL-5** If the release hook is invoked with `BTB_DRY_RUN=true`,
  it prints the card build and manifest update actions without running
  `scripts/deploy-card` or modifying `manifest.json`. The shared base command may
  skip executing hooks during its own dry-run and print the hook path instead.
