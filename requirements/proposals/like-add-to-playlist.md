# Add liked tracks to a configured Spotify playlist

**Status:** shipped
**Touches:** integration (controller, config flow)

## Goal

Music Assistant can play a Spotify *playlist* but cannot play Spotify *Liked
Songs* (it isn't a real playlist). Let a user optionally configure a Spotify
playlist so that confirming a like also appends the track there, making it
playable through MA.

## Behavior

1. **LK-8 (constraint):** Confirming a like (`async_confirm_like`) appends the
   selected candidate's track URI to the playlist configured via
   `like_playlist_id`, in addition to saving it to Liked Songs, via
   SpotifyPlus's `playlist_items_add` service.
2. **LK-9 (constraint):** `like_playlist_id` is optional. When unset,
   confirming a like behaves exactly as before (Liked Songs only) — this is
   backwards-compatible with [`like-current-track.md`](like-current-track.md).
3. **LK-10 (constraint):** `like_playlist_id` accepts a bare playlist id, a
   `spotify:playlist:<id>` URI, a Music-Assistant-style
   `spotify://playlist/<id>` URI, or an `open.spotify.com/playlist/<id>` URL,
   so the user can paste whatever form they have on hand. The value is
   normalized to the bare id before being sent to SpotifyPlus.

## Out of scope

- Creating or managing the target playlist itself — the user must already
  have a real Spotify playlist (e.g. "BToddB - All") to configure.
- Deduplicating tracks already present in the target playlist; SpotifyPlus's
  `playlist_items_add` behavior on duplicates is used as-is.

## Acceptance criteria

- [x] `confirm_like` with `like_playlist_id` configured calls both
      `save_track_favorites` and `playlist_items_add` with the selected
      candidate's URI and the normalized playlist id.
- [x] `confirm_like` with nothing configured calls only
      `save_track_favorites`.
- [x] The playlist id is normalized from bare id / URI / URL forms.
