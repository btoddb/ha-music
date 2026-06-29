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

MEDIA_CONTENT_TYPE_RADIO = "music"
MEDIA_CONTENT_TYPE_PLAYLIST = "playlist"
