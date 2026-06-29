"""Controller for BToddB HA Music actions."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.components.media_player.const import (
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_TITLE,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_PLAY_MEDIA,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SERVICE_MEDIA_STOP,
    SERVICE_SHUFFLE_SET,
    STATE_UNAVAILABLE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_PLAYLISTS,
    CONF_RADIO_STATIONS,
    CONF_SPEAKERS,
    MEDIA_CONTENT_TYPE_PLAYLIST,
    MEDIA_CONTENT_TYPE_RADIO,
)
from .models import NamedMapping, NowPlaying, parse_named_mapping

SelectionListener = Callable[[], None]


class MusicController:
    """Coordinate selected music targets with Home Assistant media services."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the controller."""

        self.hass = hass
        self.entry = entry
        data = {**entry.data, **entry.options}
        self.speakers = parse_named_mapping(
            data.get(CONF_SPEAKERS, {}), allow_list_values=True
        )
        self.radio_stations = parse_named_mapping(
            data.get(CONF_RADIO_STATIONS, {}), allow_list_values=False
        )
        self.playlists = parse_named_mapping(
            data.get(CONF_PLAYLISTS, {}), allow_list_values=False
        )
        self.selected_speakers = _first_option(self.speakers)
        self.selected_radio_station = _first_option(self.radio_stations)
        self.selected_playlist = _first_option(self.playlists)
        self._listeners: list[SelectionListener] = []

    @property
    def all_media_player_entity_ids(self) -> set[str]:
        """Return all configured media player entity ids."""

        entity_ids: set[str] = set()
        for value in self.speakers.values():
            if isinstance(value, str):
                entity_ids.add(value)
            else:
                entity_ids.update(value)
        return entity_ids

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return no entity category so dashboard entities are easy to find."""

        return None

    @callback
    def async_add_listener(self, listener: SelectionListener) -> CALLBACK_TYPE:
        """Register a listener for selection changes."""

        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.remove(listener)

        return remove_listener

    @callback
    def set_selected_speakers(self, option: str) -> None:
        """Set the selected speaker option."""

        self._set_option("speakers", option, self.speakers)

    @callback
    def set_selected_radio_station(self, option: str) -> None:
        """Set the selected radio station option."""

        self._set_option("radio station", option, self.radio_stations)

    @callback
    def set_selected_playlist(self, option: str) -> None:
        """Set the selected playlist option."""

        self._set_option("playlist", option, self.playlists)

    async def async_play_radio_station(
        self, *, station: str | None = None, speakers: str | list[str] | None = None
    ) -> None:
        """Play the selected or requested radio station."""

        entity_ids = self._resolve_speakers(speakers)
        media_content_id = self._resolve_media(
            station,
            selected=self.selected_radio_station,
            mapping=self.radio_stations,
            kind="radio station",
        )
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                "entity_id": entity_ids,
                ATTR_MEDIA_CONTENT_ID: media_content_id,
                ATTR_MEDIA_CONTENT_TYPE: MEDIA_CONTENT_TYPE_RADIO,
            },
            blocking=True,
        )

    async def async_shuffle_play_playlist(
        self, *, playlist: str | None = None, speakers: str | list[str] | None = None
    ) -> None:
        """Shuffle play the selected or requested playlist."""

        entity_ids = self._resolve_speakers(speakers)
        media_content_id = self._resolve_media(
            playlist,
            selected=self.selected_playlist,
            mapping=self.playlists,
            kind="playlist",
        )
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_SHUFFLE_SET,
            {"entity_id": entity_ids, "shuffle": True},
            blocking=True,
        )
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                "entity_id": entity_ids,
                ATTR_MEDIA_CONTENT_ID: media_content_id,
                ATTR_MEDIA_CONTENT_TYPE: MEDIA_CONTENT_TYPE_PLAYLIST,
            },
            blocking=True,
        )

    async def async_stop_music(
        self, *, speakers: str | list[str] | None = None
    ) -> None:
        """Stop playback on the selected or requested speakers."""

        entity_ids = self._resolve_speakers(speakers)
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_STOP,
            {"entity_id": entity_ids},
            blocking=True,
        )

    def now_playing(self) -> NowPlaying:
        """Return current media metadata for the selected speaker option."""

        if self.selected_speakers is None:
            return NowPlaying("unknown", None, "unknown", "unknown", None)

        for entity_id in self._resolve_speakers(self.selected_speakers):
            state = self.hass.states.get(entity_id)
            if state is None or state.state == STATE_UNAVAILABLE:
                continue

            artist = state.attributes.get(ATTR_MEDIA_ARTIST) or "unknown"
            title = state.attributes.get(ATTR_MEDIA_TITLE) or "unknown"
            album = state.attributes.get(ATTR_MEDIA_ALBUM_NAME)
            if artist == "unknown" and title == "unknown":
                return NowPlaying("unknown", entity_id, artist, title, album)
            return NowPlaying(f"{artist} - {title}", entity_id, artist, title, album)

        return NowPlaying("unknown", None, "unknown", "unknown", None)

    def _resolve_speakers(self, speakers: str | list[str] | None) -> list[str]:
        """Resolve a speaker option or entity id list into media players."""

        requested = speakers or self.selected_speakers
        if requested is None:
            raise HomeAssistantError("No speakers are configured or selected")

        if isinstance(requested, list):
            return _validate_entity_ids(requested, kind="speakers")

        if requested in self.speakers:
            mapped = self.speakers[requested]
            if isinstance(mapped, str):
                return _validate_entity_ids([mapped], kind="speakers")
            return _validate_entity_ids(mapped, kind="speakers")

        return _validate_entity_ids([requested], kind="speakers")

    def _resolve_media(
        self,
        requested: str | None,
        *,
        selected: str | None,
        mapping: NamedMapping,
        kind: str,
    ) -> str:
        """Resolve a media option name or raw content id."""

        option = requested or selected
        if option is None:
            raise HomeAssistantError(f"No {kind} is configured or selected")
        if option in mapping:
            value = mapping[option]
            if isinstance(value, list):
                raise HomeAssistantError(f"{kind} cannot resolve to multiple values")
            return value
        return option

    @callback
    def _set_option(self, label: str, option: str, mapping: NamedMapping) -> None:
        """Set and announce a selected option."""

        if option not in mapping:
            raise ValueError(f"Unknown {label}: {option}")
        if label == "speakers":
            self.selected_speakers = option
        elif label == "radio station":
            self.selected_radio_station = option
        elif label == "playlist":
            self.selected_playlist = option
        for listener in self._listeners:
            listener()


def _first_option(mapping: NamedMapping) -> str | None:
    """Return the first configured option name."""

    return next(iter(mapping), None)


def _validate_entity_ids(entity_ids: Iterable[str], *, kind: str) -> list[str]:
    """Validate and normalize media player entity ids."""

    normalized: list[str] = []
    for entity_id in entity_ids:
        if not entity_id.startswith(f"{MEDIA_PLAYER_DOMAIN}."):
            raise HomeAssistantError(
                f"{kind} must target media_player entities, got {entity_id}"
            )
        normalized.append(entity_id)
    if not normalized:
        raise HomeAssistantError(f"No {kind} are configured or selected")
    return normalized


class MusicRestoreEntity(RestoreEntity):
    """Base class for entities backed by the controller."""

    _attr_has_entity_name = True

    def __init__(self, controller: MusicController, key: str) -> None:
        """Initialize the entity."""

        self._controller = controller
        self._attr_device_info = {
            "identifiers": {(controller.entry.domain, controller.entry.entry_id)},
            "name": "BToddB HA Music",
        }
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
