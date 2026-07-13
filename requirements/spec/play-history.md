# Play History ("recently played songs")

The integration keeps a short history of recently played songs so a user can
review what played and like a song they missed (issue #27).

- **constraint PH-1** The controller records a play history, newest first,
  capped at the 10 most recent tracks. A track lands in the history when the
  now-playing artist/title pair *changes away* from it (next track, stop,
  switching speaker groups), so the history never duplicates the track
  currently shown as Now Playing and the last track still lands when playback
  stops.
- **constraint PH-2** State churn that does not change the artist/title pair
  (pause, volume, album metadata arriving late) records nothing, and a track
  with an unknown artist or unknown title (e.g. a radio stream without
  metadata) is never recorded.
- **constraint PH-3** The history is exposed as the `history` attribute of
  `sensor.<prefix>_now_playing`: a list of `{artist, title, album,
  played_at}` objects, newest first, where `played_at` is an ISO-8601 UTC
  timestamp. It is in-memory only and resets on Home Assistant restart.
- **constraint PH-4** `btoddb_ha_music.find_like_matches` accepts optional
  `artist` and `title` fields so a history entry can be liked through the
  existing search-and-pick like flow. Passing only one of the two is refused
  with a clear error; passing neither keeps the existing now-playing
  behavior.
