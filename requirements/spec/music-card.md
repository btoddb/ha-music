# Lovelace Card ("Play Something ...")

The `btoddb-ha-music-like-card` Lovelace card is the single dashboard surface
for the integration (issue #30): it combines now-playing metadata, the
combined media catalog, playback controls, the Spotify like flow, and speaker
selection.

- **constraint CARD-1** The card renders, in order: a "Play Something ..."
  header; a Now Playing section (artist and song from
  `sensor.<prefix>_now_playing`, rendered as a single history-style entry in
  the same outlined list style as the history entries, with a ♥ button that
  runs the now-playing like flow — issue #40; an italic "Nothing playing"
  row when nothing is playing per the CARD-3 signal); a music-source dropdown
  backed by the
  combined media select; a speakers dropdown backed by the speaker-group
  select; a Play/Skip button row; a Stop/Find Song button row; a Pause/Resume
  button row; and the like-candidate flow (hidden until Find Song returns
  matches).
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
  legacy `_next_track` button entity id. The card additionally grays the
  buttons that are not applicable (issue #36): Play while something is
  playing, and Skip/Stop while nothing is. The signal is the now-playing
  sensor's `playback_active` attribute, which the integration derives from
  the configured players' actual states (with its own remembered pause
  counting as active — PM-8) rather than from the sensor's metadata-built
  state string, because an idle player can retain its last artist/title
  after a queue finishes. It therefore self-heals when a playlist queue
  finishes on its own or HA restarts mid-playback. When the attribute is
  absent (older integration), the card falls back to treating a missing,
  `unknown`, or `unavailable` sensor state as nothing playing. Skip's
  playlist-only availability comes from the backing entity (PM-8).
- **constraint CARD-4** The music and speakers dropdowns list the backing
  select's `options`, reflect its current state, and call
  `select.select_option` against the resolved entity id on change. A dropdown
  with no options is disabled.
- **constraint CARD-5** The like flow is unchanged from the original card:
  Find Song calls `find_like_matches`, candidates render from the
  like-candidate select's structured `candidates` attribute (falling back to
  `options`), clicking a candidate selects it, and Like/Cancel call
  `confirm_like`/`cancel_like` with availability mirroring the backing button
  entities. Find Song (which searches for the now-playing track) is
  additionally grayed while nothing is playing (the CARD-3 `playback_active`
  signal, issue #36).
- **constraint CARD-6** Pause and Resume call the `btoddb_ha_music.pause_music`
  and `resume_music` services (issue #26). Each is disabled while its call is
  in flight, when its backing button entity is missing or unavailable (the
  integration marks both unavailable unless a playlist is the active media
  kind, and of the pair only the one matching the paused state stays
  available — see PM-7/PM-8), or while nothing is playing per the CARD-3
  `playback_active` signal (covers a playlist queue that finished on its
  own), so both gray out while a radio station or nothing is playing and
  they never present as clickable together.
- **constraint CARD-7** The Now Playing section also renders a "History"
  title (always visible) with a chevron that expands/hides the history list
  (issue #27, collapsed by default). The list renders the now-playing
  sensor's `history` attribute (newest first, capped at 10 by the
  integration — see PH-1/PH-3), excluding the newest entry matching the
  currently playing artist/title while something is playing (the integration
  records a track at play start, so that entry duplicates Now Playing —
  issue #40) and showing the full history when nothing is playing. Each
  entry shows artist and song plus a like (♥) button that calls
  `find_like_matches` with that entry's `artist` and `title`, feeding the
  existing like-candidate flow (CARD-5). The like
  buttons mirror the backing `find_like_matches` button entity's availability
  and the card's in-flight state — but not Find Song's nothing-playing
  graying (CARD-5), because history entries carry their own artist/title and
  must stay likable after playback stops. An empty history shows a "No songs
  played yet" row.
