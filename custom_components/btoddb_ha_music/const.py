"""Constants for BToddB HA Music."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "btoddb_ha_music"
NAME = "BToddB HA Music"

CONF_PLAYLISTS = "playlists"
CONF_RADIO_STATIONS = "radio_stations"
CONF_SPEAKERS = "speakers"
CONF_SPOTIFY_ENTITY = "spotify_entity"
CONF_LIKE_SEARCH_LIMIT = "like_search_limit"

DEFAULT_LIKE_SEARCH_LIMIT = 5

ATTR_PLAYLIST = "playlist"
ATTR_SPEAKERS = "speakers"
ATTR_STATION = "station"

SERVICE_PLAY_RADIO_STATION = "play_radio_station"
SERVICE_SHUFFLE_PLAY_PLAYLIST = "shuffle_play_playlist"
SERVICE_STOP_MUSIC = "stop_music"
SERVICE_FIND_LIKE_MATCHES = "find_like_matches"
SERVICE_CONFIRM_LIKE = "confirm_like"
SERVICE_CANCEL_LIKE = "cancel_like"

PLATFORMS = (Platform.SELECT, Platform.BUTTON, Platform.SENSOR)

# Music Assistant is the playback backend: the target speakers are all
# music_assistant media_player entities and the configured media values are
# Music Assistant URIs (e.g. spotify://playlist/..., radiobrowser://radio/...).
MUSIC_ASSISTANT_DOMAIN = "music_assistant"
SERVICE_MA_PLAY_MEDIA = "play_media"
MA_ENQUEUE_REPLACE = "replace"

# SpotifyPlus (thlucas1/spotifyplus, a separately installed HACS integration)
# is the only backend that exposes both a track search and a "Liked Songs"
# write call, so it backs the "like the current track" feature.
SPOTIFYPLUS_DOMAIN = "spotifyplus"
SERVICE_SPOTIFYPLUS_SEARCH_TRACKS = "search_tracks"
SERVICE_SPOTIFYPLUS_SAVE_TRACK_FAVORITES = "save_track_favorites"
