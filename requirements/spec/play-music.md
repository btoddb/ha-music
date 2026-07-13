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
