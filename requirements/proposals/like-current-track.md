# Like the current track

**Status:** in progress
**Touches:** integration (controller, select, button, services, config flow)

## Goal

Let a user save the currently playing track to Spotify Liked Songs from a Home
Assistant dashboard, including when the source is radio (no Spotify track id
is available), by searching Spotify for the playing artist/title and letting
the user pick the right match before saving anything.

## Behavior

1. **LK-1 (constraint):** Liking is only available when a SpotifyPlus
   (`thlucas1/spotifyplus`) media_player entity is configured via
   `spotify_entity` in the config/options flow. With nothing configured, the
   like buttons are unavailable and the like services raise a clear error.
2. **LK-2 (constraint):** Finding matches reads the *artist* and *title* of
   whatever is currently playing on the selected speaker group and searches
   Spotify via SpotifyPlus's `search_tracks` service — it never depends on a
   Spotify track id, so it works for Music Assistant playback from any
   source, including internet radio.
3. **LK-3 (constraint):** Finding matches never writes to Spotify. It only
   populates a list of candidate tracks (capped at `like_search_limit`,
   default 5) and pre-selects the top match.
4. **LK-4 (constraint):** The candidate list is exposed through a
   `Like candidate` select entity so the user can review and change which
   match will be liked, or leave the pre-selected top match.
5. **LK-5 (constraint):** Confirming calls SpotifyPlus's
   `save_track_favorites` for the selected candidate only, then clears the
   candidate list. Confirming with nothing selected refuses with a clear
   error rather than guessing.
6. **LK-6 (constraint):** Canceling clears the candidate list without calling
   any Spotify write service.
7. **LK-7 (suggestion):** Duplicate artist/title/album matches in the search
   results get a disambiguating suffix (e.g. `Artist - Title (Album) [2]`) so
   every select option is distinct.

## Out of scope

- Adding the track to a named playlist (e.g. "BToddB All") — deferred; only
  Liked Songs is in scope for this iteration.
- Auto-liking a track without the search-and-pick step.
- Validating the installed SpotifyPlus version's exact service field names
  beyond what this proposal assumes (`search_tracks` fields `entity_id`,
  `criteria`, `limit`, returning a Spotify-API-shaped track search response;
  `save_track_favorites` fields `entity_id`, `ids`). If a user's installed
  SpotifyPlus version differs, the integration surfaces the resulting
  `HomeAssistantError` from the failed service call as-is.

## Acceptance criteria

- [x] `find_like_matches` refuses without a configured SpotifyPlus entity.
- [x] `find_like_matches` refuses when nothing identifiable is playing.
- [x] `find_like_matches` builds candidates from the search response and
      de-duplicates identical labels.
- [x] `confirm_like` saves the selected candidate and clears the list.
- [x] `confirm_like` refuses when nothing is selected.
- [x] `cancel_like` clears the list without saving.
