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
  select; a Play/Skip button row (the Play button doubles as Pause and Resume
  — issue #39); a Stop button row; and the like-candidate flow (hidden until a
  ♥ search returns matches). There is no separate Find Song or Pause/Resume
  button — the ♥ on the Now Playing entry runs the now-playing search
  (issue #39 follow-up) and the Play button carries the transport actions.
- **constraint CARD-2** Entity resolution tries
  `<domain>.<entity_prefix>_<suffix>` first, then falls back to any entity in
  the domain whose id ends with `_<suffix>`, preferring ids that share the
  prefix's leading token. This is required because existing installs carry
  mixed device-name slugs (e.g. `sensor.btoddb_ha_music_now_playing` alongside
  `select.btoddb_music_music`), so one configured prefix cannot resolve every
  entity.
- **constraint CARD-3** The transport button (see CARD-6) and Skip and Stop
  call the `btoddb_ha_music` transport services (no
  explicit `media`/`speakers`, so the integration's current selections apply);
  each is disabled while its call is in flight or when its backing button
  entity is missing or unavailable. Skip accepts either the `_skip_song` or
  legacy `_next_track` button entity id. The card additionally grays the
  buttons that are not applicable (issue #36): the transport button while in
  Play mode grays while something is playing, and Skip/Stop while nothing is.
  The signal is the now-playing
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
- **constraint CARD-5** The like flow: the ♥ button on the Now Playing entry
  (CARD-1) and the ♥ buttons in the history list (CARD-7) call
  `find_like_matches`; candidates render from the
  like-candidate select's structured `candidates` attribute (falling back to
  `options`), clicking a candidate selects it, and Like/Cancel call
  `confirm_like`/`cancel_like` with availability mirroring the backing button
  entities. The dedicated Find Song button was removed (issue #39 follow-up)
  because the Now Playing ♥ already searches the now-playing track; a
  `find-status` row still shows a no-match message after a search returns
  nothing.
- **constraint CARD-6** The Play button is a single transport control that
  morphs its label and action to whichever transport applies (issue #39): it
  calls `btoddb_ha_music.play_music` as **Play**, `pause_music` as **Pause**,
  or `resume_music` as **Resume**. Mode is chosen from the backing button
  entities, which the integration keeps mutually exclusive per playback state
  (PM-8): while something is playing (CARD-3 `playback_active`), the button
  is **Resume** when `resume_music` is available (a paused playlist) and
  **Pause** when `pause_music` is available (an un-paused playlist);
  otherwise it is **Play**. Each mode follows its own availability rule —
  Play grays while something is playing (and Resume/Pause never apply then
  because their backing entities are unavailable, e.g. radio), while
  Pause/Resume gray while nothing is playing — plus the in-flight and
  missing/unavailable-backing rules of CARD-3. Because the backing entities
  are exclusive, the button never offers Pause and Resume at once, and a
  radio station (which cannot be paused/resumed) shows a grayed **Play**.
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
