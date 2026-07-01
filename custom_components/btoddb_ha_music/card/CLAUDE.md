# Card — BToddB HA Music Lovelace Card

TypeScript source for the `btoddb-ha-music-like-card` Lovelace card shipped with the
`btoddb_ha_music` integration.

## Building

Run `scripts/deploy-card` from the repo root. It installs deps, bumps the patch version,
builds, and copies the bundle into `../www/` (served as `/btoddb_ha_music/btoddb_ha_music.js`).
Hard-refresh your browser after each build — no HA restart or Lovelace resource edit needed.

## Source

`src/index.ts` — single-file custom element `btoddb-ha-music-like-card`.

Card config options:

| key | default | description |
|-----|---------|-------------|
| `entity_prefix` | `btoddb_ha_music` | Prefix used to look up entities (`sensor.<prefix>_now_playing`, etc.) |

## Versioning

Do **not** hand-edit the `version` field in `package.json` or the `v0.0.x` banner in
`src/index.ts` — `scripts/deploy-card` manages both atomically and rolls back on failure.
