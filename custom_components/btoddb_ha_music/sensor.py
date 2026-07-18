"""Sensor entities for BToddB Music."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import Event, callback
from homeassistant.helpers.event import async_track_state_change_event

from . import MusicConfigEntry
from .const import LIKED_STATE_UNKNOWN
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
        # Identity of the track whose liked state is currently reflected in
        # `_liked_state`; None when nothing resolvable is playing. Includes the
        # media_content_id so a metadata revision that adds an exact Spotify
        # track id re-triggers resolution instead of keeping a stale fuzzy
        # result (PR #44 review). Guards the async resolve so it only runs when
        # the track's resolvable identity actually changes (issue #43).
        self._liked_key: tuple[str, str, str | None] | None = None
        self._liked_state = LIKED_STATE_UNKNOWN
        self._update_now_playing()

    @callback
    def _update_now_playing(self) -> None:
        """Read current media metadata once and cache it on the entity."""

        now_playing = self._controller.now_playing()
        playback_active = self._controller.playback_active()
        self._controller.record_now_playing(
            now_playing, playback_active=playback_active
        )
        self._attr_native_value = now_playing.state
        self._attr_extra_state_attributes = {
            "playback_active": playback_active,
            "player_entity_id": now_playing.player_entity_id,
            "artist": now_playing.artist,
            "title": now_playing.title,
            "album": now_playing.album,
            "now_playing_liked": self._liked_state,
            "history": [track.as_dict() for track in self._controller.play_history],
        }

    @callback
    def _sync_liked(self) -> None:
        """Refresh the cached liked state when the now-playing track changes.

        The favorites lookup is async (it may search Spotify), so it runs as a
        background task; the heart shows "unknown" until it resolves. A track
        that is not identifiable, has no SpotifyPlus entity, or is not playing
        resets to "unknown" without a lookup.
        """

        if self.hass is None:
            return

        now_playing = self._controller.now_playing()
        resolvable = (
            self._controller.spotify_entity_id is not None
            and self._controller.playback_active()
            and now_playing.artist != "unknown"
            and now_playing.title != "unknown"
        )
        key = (
            (now_playing.artist, now_playing.title, now_playing.media_content_id)
            if resolvable
            else None
        )
        if key == self._liked_key:
            return

        self._liked_key = key
        self._liked_state = LIKED_STATE_UNKNOWN
        self._attr_extra_state_attributes["now_playing_liked"] = self._liked_state
        if key is not None:
            self.hass.async_create_task(self._async_resolve_liked(key))

    async def _async_resolve_liked(self, key: tuple[str, str, str | None]) -> None:
        """Resolve and store the liked state for the given track key."""

        state = await self._controller.async_resolve_now_playing_liked()
        # A newer track took over while we were resolving; its own task owns
        # the state now, so drop this stale result.
        if key != self._liked_key or state == self._liked_state:
            return
        self._liked_state = state
        self._attr_extra_state_attributes["now_playing_liked"] = state
        self.async_write_ha_state()

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
        self._sync_liked()

    @callback
    def _handle_update(self) -> None:
        """Refresh cached metadata when the selected option changes."""

        self._update_now_playing()
        self._sync_liked()
        self.async_write_ha_state()

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Update the sensor when a media player changes."""

        self._update_now_playing()
        self._sync_liked()
        self.async_write_ha_state()
