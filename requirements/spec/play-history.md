# Play History ("recently played songs")

The integration keeps a short history of recently played songs so a user can
review what played and like a song they missed (issue #27).

- **constraint PH-1** The controller records a play history, newest first,
  capped at the 10 most recent tracks. A track lands in the history the
  moment its artist/title pair *becomes* the now-playing track (issue #40),
  so the newest entry duplicates the track currently shown as Now Playing
  while it plays and nothing is lost when playback stops — the card is
  responsible for not showing the current track twice (CARD-7).
- **constraint PH-2** State churn that does not change the artist/title pair
  (pause, volume) records nothing, and a track with an unknown artist or
  unknown title (e.g. a radio stream without metadata) is never recorded.
  Album metadata that arrives after the track was recorded refreshes the
  newest history entry in place.
- **constraint PH-3** The history is exposed as the `history` attribute of
  `sensor.<prefix>_now_playing`: a list of `{artist, title, album,
  played_at}` objects, newest first, where `played_at` is an ISO-8601 UTC
  timestamp. It is in-memory only and resets on Home Assistant restart.
- **constraint PH-4** `btoddb_ha_music.find_like_matches` accepts optional
  `artist` and `title` fields so a history entry can be liked through the
  existing search-and-pick like flow. Passing only one of the two is refused
  with a clear error; passing neither keeps the existing now-playing
  behavior.
