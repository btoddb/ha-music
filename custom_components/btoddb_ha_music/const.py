"""Constants for BToddB HA Music."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "btoddb_ha_music"
NAME = "BToddB HA Music"

CONF_PLAYLISTS = "playlists"
CONF_RADIO_STATIONS = "radio_stations"
CONF_SPEAKERS = "speakers"

ATTR_PLAYLIST = "playlist"
ATTR_SPEAKERS = "speakers"
ATTR_STATION = "station"

SERVICE_PLAY_RADIO_STATION = "play_radio_station"
SERVICE_SHUFFLE_PLAY_PLAYLIST = "shuffle_play_playlist"
SERVICE_STOP_MUSIC = "stop_music"

PLATFORMS = (Platform.SELECT, Platform.BUTTON, Platform.SENSOR)

# Music Assistant is the playback backend: the target speakers are all
# music_assistant media_player entities and the configured media values are
# Music Assistant URIs (e.g. spotify://playlist/..., radiobrowser://radio/...).
MUSIC_ASSISTANT_DOMAIN = "music_assistant"
SERVICE_MA_PLAY_MEDIA = "play_media"
MA_ENQUEUE_REPLACE = "replace"
