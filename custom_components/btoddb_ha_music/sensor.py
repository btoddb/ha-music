"""Sensor entities for BToddB HA Music."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import Event, callback
from homeassistant.helpers.event import async_track_state_change_event

from . import MusicConfigEntry
from .controller import MusicController, MusicEntity


async def async_setup_entry(hass, entry: MusicConfigEntry, async_add_entities) -> None:
    """Set up music sensors."""

    async_add_entities([NowPlayingSensor(entry.runtime_data)])


class NowPlayingSensor(MusicEntity, SensorEntity):
    """Expose now playing metadata for the selected speaker group."""

    _attr_translation_key = "now_playing"
    _attr_icon = "mdi:music-note"

    def __init__(self, controller: MusicController) -> None:
        """Initialize the sensor."""

        super().__init__(controller, "now_playing")
        self._update_now_playing()

    @callback
    def _update_now_playing(self) -> None:
        """Read current media metadata once and cache it on the entity."""

        now_playing = self._controller.now_playing()
        self._attr_native_value = now_playing.state
        self._attr_extra_state_attributes = {
            "player_entity_id": now_playing.player_entity_id,
            "artist": now_playing.artist,
            "title": now_playing.title,
            "album": now_playing.album,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to selected speaker and media player changes."""

        await super().async_added_to_hass()
        self.async_on_remove(self._controller.async_add_listener(self._handle_update))
        entity_ids = self._controller.all_media_player_entity_ids
        if entity_ids:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    list(entity_ids),
                    self._handle_state_change,
                )
            )

    @callback
    def _handle_update(self) -> None:
        """Refresh cached metadata when the selected option changes."""

        self._update_now_playing()
        self.async_write_ha_state()

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Update the sensor when a media player changes."""

        self._update_now_playing()
        self.async_write_ha_state()
