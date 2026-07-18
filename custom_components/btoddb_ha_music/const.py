"""Constants for BToddB Music."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "btoddb_ha_music"
NAME = "BToddB Music"

CONF_PLAYLISTS = "playlists"
CONF_RADIO_STATIONS = "radio_stations"
CONF_SPEAKERS = "speakers"
CONF_SPOTIFY_ENTITY = "spotify_entity"
CONF_LIKE_SEARCH_LIMIT = "like_search_limit"
CONF_LIKE_PLAYLIST_ID = "like_playlist_id"

DEFAULT_LIKE_SEARCH_LIMIT = 5

ATTR_ARTIST = "artist"
ATTR_MEDIA = "media"
ATTR_PLAYLIST = "playlist"
ATTR_SPEAKERS = "speakers"
ATTR_STATION = "station"
ATTR_TITLE = "title"

MEDIA_FILTER_ALL = "All"
MEDIA_FILTER_PLAYLISTS = "Playlists"
MEDIA_FILTER_RADIO_STATIONS = "Radio stations"
MEDIA_FILTER_OPTIONS = (
    MEDIA_FILTER_ALL,
    MEDIA_FILTER_PLAYLISTS,
    MEDIA_FILTER_RADIO_STATIONS,
)

SERVICE_PLAY_MUSIC = "play_music"
SERVICE_PLAY_RADIO_STATION = "play_radio_station"
SERVICE_SHUFFLE_PLAY_PLAYLIST = "shuffle_play_playlist"
SERVICE_STOP_MUSIC = "stop_music"
SERVICE_PAUSE_MUSIC = "pause_music"
SERVICE_RESUME_MUSIC = "resume_music"
SERVICE_FIND_LIKE_MATCHES = "find_like_matches"
SERVICE_CONFIRM_LIKE = "confirm_like"
SERVICE_CANCEL_LIKE = "cancel_like"
SERVICE_NEXT_TRACK = "next_track"

PLATFORMS = (Platform.SELECT, Platform.BUTTON, Platform.SENSOR)

# Music Assistant is the playback backend: the target speakers are all
# music_assistant media_player entities and the configured media values are
# Music Assistant URIs (e.g. spotify://playlist/..., radiobrowser://radio/...).
MUSIC_ASSISTANT_DOMAIN = "music_assistant"
SERVICE_MA_PLAY_MEDIA = "play_media"
MA_ENQUEUE_REPLACE = "replace"
# State attributes the Music Assistant integration puts on its media_players,
# used to route pause/resume to the queue-owning group player instead of its
# synced members (which reject transport commands).
ATTR_MA_ACTIVE_QUEUE = "active_queue"
ATTR_MA_PLAYER_TYPE = "mass_player_type"
MA_PLAYER_TYPE_GROUP = "group"

# SpotifyPlus (thlucas1/spotifyplus, a separately installed HACS integration)
# is the only backend that exposes both a track search and a "Liked Songs"
# write call, so it backs the "like the current track" feature.
SPOTIFYPLUS_DOMAIN = "spotifyplus"
SERVICE_SPOTIFYPLUS_SEARCH_TRACKS = "search_tracks"
SERVICE_SPOTIFYPLUS_SAVE_TRACK_FAVORITES = "save_track_favorites"
SERVICE_SPOTIFYPLUS_ADD_PLAYLIST_ITEMS = "playlist_items_add"
# Reports, per Spotify track id, whether the track is in the user's Liked
# Songs. Backs the "already liked?" heart indicator (issue #43).
SERVICE_SPOTIFYPLUS_CHECK_TRACK_FAVORITES = "check_track_favorites"

# now-playing "already liked" states exposed by the sensor and rendered by the
# card's heart. UNKNOWN means the track could not be resolved to a Spotify
# track confidently (non-Spotify source with no matching search hit), so the
# heart must not claim the song is unliked.
LIKED_STATE_LIKED = "liked"
LIKED_STATE_NOT_LIKED = "not_liked"
LIKED_STATE_UNKNOWN = "unknown"
