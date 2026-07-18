# "Already liked?" heart indicator (issue #43)

The card's ♥ doubles as a status light: it shows whether the current song is
already in the user's Spotify **Liked Songs** so a user does not re-like a song
they already saved. Because the user most often listens through a non-Spotify
source, resolution must work without an exact Spotify track id.

- **constraint LS-1** "Liked" means membership in Spotify **Liked Songs**
  (`check_track_favorites`), which is what the like flow always writes via
  `save_track_favorites`. The optionally-configured like playlist
  (`like_playlist_id`) is not consulted — Spotify exposes no
  track-in-playlist check, and Liked Songs is the reliable signal.
- **constraint LS-2** The now-playing track is resolved to one or more Spotify
  track ids and checked for favorites membership. When the media player's
  `media_content_id` is a Spotify track (`spotify…://track/<id>` or
  `spotify:track:<id>`), that exact id is checked with no search. Otherwise the
  track's `artist`/`title` are searched on Spotify and only candidates whose
  **normalized artist AND title** match are checked; the song is liked if any
  matching candidate is a favorite.
- **constraint LS-3** Matching normalizes case, punctuation, bracketed
  qualifiers (`(feat. …)`, `[Remastered]`), and `feat`/`ft`/`with` clauses;
  multi-artist strings are split on `/`, `,`, `&`, `x`, `and`, `feat`, `ft`
  and compared as overlapping sets. The title must match once normalized and
  the artist sets must intersect (the artist-AND-title rule).
- **constraint LS-4** The result is exposed as the `now_playing_liked`
  attribute of `sensor.<prefix>_now_playing`, one of `liked`, `not_liked`, or
  `unknown`. `unknown` is used whenever the track cannot be resolved
  confidently — no SpotifyPlus entity, nothing identifiable playing, or no
  matching search hit — so the heart never claims an unresolved track is
  unliked. The lookup runs asynchronously when the now-playing track changes;
  the attribute reads `unknown` until it resolves.
- **constraint LS-5** Confident results (`liked`/`not_liked`) are cached per
  `(artist, title)` so a track is not re-searched as the media player churns
  state; `unknown` is not cached (richer metadata may arrive), and a
  `confirm_like` clears the cache so a just-liked track re-resolves.
- **constraint LS-6** The like-candidate select's `candidates` attribute
  carries a per-candidate `liked` boolean (or null before the check runs).
  Because a chosen candidate has an exact track id, this membership is exact,
  not fuzzy — the card marks already-liked candidates in the picker (CARD-8).
- **constraint LS-7** A favorites-check or search failure is non-fatal: the
  now-playing heart falls back to `unknown` and the like flow still returns
  its candidates (unannotated) so liking continues to work.
- **constraint LS-8** Play-history rows are not resolved (each would need its
  own search); their hearts render as `unknown`. Determining liked state for a
  specific history entry happens only through the existing search-and-pick
  flow (PH-4), where per-candidate `liked` (LS-6) applies.
