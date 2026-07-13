# Combined Media Selection ("Play music")

Radio stations and playlists are also exposed through one combined dropdown so
a dashboard needs only a single selector and a single play button
(issue #28). The original per-kind selects, buttons, and services remain for
backward compatibility.

- **constraint PM-1** `select.<prefix>_media` lists every configured radio
  station followed by every configured playlist. A name configured as both
  gets a ` (Radio)` / ` (Playlist)` suffix on each label so both stay
  selectable.
- **constraint PM-2** `select.<prefix>_media_filter` offers `All`,
  `Playlists`, and `Radio stations` and narrows the media dropdown's options.
  If the current media selection is filtered out, the selection falls back to
  the first remaining option.
- **constraint PM-3** `button.<prefix>_play_music` and the
  `btoddb_ha_music.play_music` service play the selected (or explicitly
  passed `media`) entry on the selected (or passed) speakers: radio stations
  play with shuffle off, playlists with shuffle on.
- **constraint PM-4** An unmapped `media` value passed to the service is
  treated as a raw Music Assistant URI and is shuffled only when it contains
  `playlist`.
- **constraint PM-5** Both the filter and the media selection are restored
  across Home Assistant restarts when still valid.
- **constraint PM-6** `btoddb_ha_music.pause_music` and `resume_music`
  (issue #26) call `media_player.media_pause` / `media_player.media_play` on
  the actively-playing configured speakers, using the same active-target
  resolution as stop/skip (paused players count as active so Resume reaches
  them; explicit `speakers` targets pass through unfiltered). With no
  explicit target, active players sharing one Music Assistant
  `active_queue` are additionally collapsed to a single target per queue —
  the `mass_player_type: group` player when present, else the first — because
  MA rejects transport commands sent to synced group members
  ("set_members needs to be implemented when PlayerFeature.SET_MEMBERS is
  set"). Because MA reports paused players as `idle` (which the
  active-state filter excludes), `pause_music` records the players it
  paused and `resume_music` sends `media_play` back to exactly those,
  falling back to active-target resolution when nothing is remembered. The
  remembered targets are cleared by resume, stop, or starting new playback,
  and are not persisted across restarts.
- **constraint PM-7** The controller records the kind of media it last
  started (`playing_kind`: radio station or playlist), clearing it on
  `stop_music`. `button.<prefix>_pause_music` and
  `button.<prefix>_resume_music` are available only while `playing_kind` is
  playlist, because radio streams cannot be meaningfully paused and resumed.
  The kind is not persisted across Home Assistant restarts, so both buttons
  start unavailable until the next play action.
