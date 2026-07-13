# Lovelace Card ("Play Something ...")

The `btoddb-ha-music-like-card` Lovelace card is the single dashboard surface
for the integration (issue #30): it combines now-playing metadata, the
combined media catalog, playback controls, the Spotify like flow, and speaker
selection.

- **constraint CARD-1** The card renders, in order: a "Play Something ..."
  header; a Now Playing section (artist and song from
  `sensor.<prefix>_now_playing`); a music-source dropdown backed by the
  combined media select; a Play/Skip button row; a Stop/Find Song button row;
  the like-candidate flow (hidden until Find Song returns matches); and a
  speakers dropdown backed by the speaker-group select.
- **constraint CARD-2** Entity resolution tries
  `<domain>.<entity_prefix>_<suffix>` first, then falls back to any entity in
  the domain whose id ends with `_<suffix>`, preferring ids that share the
  prefix's leading token. This is required because existing installs carry
  mixed device-name slugs (e.g. `sensor.btoddb_ha_music_now_playing` alongside
  `select.btoddb_music_music`), so one configured prefix cannot resolve every
  entity.
- **constraint CARD-3** Play, Skip, and Stop call the
  `btoddb_ha_music.play_music`, `next_track`, and `stop_music` services (no
  explicit `media`/`speakers`, so the integration's current selections apply);
  each is disabled while its call is in flight or when its backing button
  entity is missing or unavailable. Skip accepts either the `_skip_song` or
  legacy `_next_track` button entity id.
- **constraint CARD-4** The music and speakers dropdowns list the backing
  select's `options`, reflect its current state, and call
  `select.select_option` against the resolved entity id on change. A dropdown
  with no options is disabled.
- **constraint CARD-5** The like flow is unchanged from the original card:
  Find Song calls `find_like_matches`, candidates render from the
  like-candidate select's structured `candidates` attribute (falling back to
  `options`), clicking a candidate selects it, and Like/Cancel call
  `confirm_like`/`cancel_like` with availability mirroring the backing button
  entities.
