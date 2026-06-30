"""Controller for BToddB HA Music actions."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.components.media_player.const import (
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_TITLE,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SERVICE_MEDIA_STOP,
    SERVICE_SHUFFLE_SET,
    STATE_UNAVAILABLE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_LIKE_SEARCH_LIMIT,
    CONF_PLAYLISTS,
    CONF_RADIO_STATIONS,
    CONF_SPEAKERS,
    CONF_SPOTIFY_ENTITY,
    DEFAULT_LIKE_SEARCH_LIMIT,
    MA_ENQUEUE_REPLACE,
    MUSIC_ASSISTANT_DOMAIN,
    SERVICE_MA_PLAY_MEDIA,
    SERVICE_SPOTIFYPLUS_SAVE_TRACK_FAVORITES,
    SERVICE_SPOTIFYPLUS_SEARCH_TRACKS,
    SPOTIFYPLUS_DOMAIN,
)
from .models import LikeCandidate, NamedMapping, NowPlaying, parse_named_mapping

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
        self.spotify_entity_id = data.get(CONF_SPOTIFY_ENTITY) or None
        self.like_search_limit = int(
            data.get(CONF_LIKE_SEARCH_LIMIT, DEFAULT_LIKE_SEARCH_LIMIT)
        )
        self.like_candidates: list[LikeCandidate] = []
        self.selected_like_candidate: LikeCandidate | None = None
        self._listeners: list[SelectionListener] = []

    @property
    def like_enabled(self) -> bool:
        """Return whether a SpotifyPlus entity is configured for liking tracks."""

        return self.spotify_entity_id is not None

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
        media_id = self._resolve_media(
            station,
            selected=self.selected_radio_station,
            mapping=self.radio_stations,
            kind="radio station",
        )
        await self._async_set_shuffle(entity_ids, shuffle=False)
        await self._async_play_media(entity_ids, media_id)

    async def async_shuffle_play_playlist(
        self, *, playlist: str | None = None, speakers: str | list[str] | None = None
    ) -> None:
        """Shuffle play the selected or requested playlist."""

        entity_ids = self._resolve_speakers(speakers)
        media_id = self._resolve_media(
            playlist,
            selected=self.selected_playlist,
            mapping=self.playlists,
            kind="playlist",
        )
        await self._async_set_shuffle(entity_ids, shuffle=True)
        await self._async_play_media(entity_ids, media_id)

    async def _async_set_shuffle(self, entity_ids: list[str], *, shuffle: bool) -> None:
        """Set the shuffle mode on the target players before playback."""

        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_SHUFFLE_SET,
            {"entity_id": entity_ids, "shuffle": shuffle},
            blocking=True,
        )

    async def _async_play_media(self, entity_ids: list[str], media_id: str) -> None:
        """Replace the queue and play a Music Assistant media URI."""

        await self.hass.services.async_call(
            MUSIC_ASSISTANT_DOMAIN,
            SERVICE_MA_PLAY_MEDIA,
            {
                "entity_id": entity_ids,
                "media_id": media_id,
                "enqueue": MA_ENQUEUE_REPLACE,
            },
            blocking=True,
        )

    async def async_stop_music(
        self, *, speakers: str | list[str] | None = None
    ) -> None:
        """Stop playback.

        With no target this stops every configured speaker, so "stop whatever
        is playing" works regardless of which group is currently selected. A
        specific target can still be passed via the service call.
        """

        if speakers is None:
            entity_ids = sorted(self.all_media_player_entity_ids)
            if not entity_ids:
                raise HomeAssistantError("No speakers are configured")
        else:
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

            artist = state.attributes.get(ATTR_MEDIA_ARTIST)
            title = state.attributes.get(ATTR_MEDIA_TITLE)
            album = state.attributes.get(ATTR_MEDIA_ALBUM_NAME)
            display = " - ".join(part for part in (artist, title) if part) or "unknown"
            return NowPlaying(
                display, entity_id, artist or "unknown", title or "unknown", album
            )

        return NowPlaying("unknown", None, "unknown", "unknown", None)

    async def async_find_like_matches(self) -> None:
        """Search Spotify for tracks matching the now-playing artist/title."""

        if self.spotify_entity_id is None:
            raise HomeAssistantError("No SpotifyPlus entity is configured")

        now_playing = self.now_playing()
        if now_playing.artist == "unknown" or now_playing.title == "unknown":
            raise HomeAssistantError("Nothing identifiable is currently playing")

        query = f"{now_playing.artist} {now_playing.title}"
        response = await self.hass.services.async_call(
            SPOTIFYPLUS_DOMAIN,
            SERVICE_SPOTIFYPLUS_SEARCH_TRACKS,
            {
                "entity_id": self.spotify_entity_id,
                "criteria": query,
                "limit": self.like_search_limit,
            },
            blocking=True,
            return_response=True,
        )

        candidates = _parse_search_response(response)
        if not candidates:
            raise HomeAssistantError(f"No Spotify matches found for {query}")

        self.like_candidates = candidates
        self.selected_like_candidate = candidates[0]
        self._notify_listeners()

    @callback
    def set_selected_like_candidate(self, label: str) -> None:
        """Select a like candidate by its label."""

        for candidate in self.like_candidates:
            if candidate.label == label:
                self.selected_like_candidate = candidate
                self._notify_listeners()
                return
        raise ValueError(f"Unknown like candidate: {label}")

    async def async_confirm_like(self) -> None:
        """Save the selected like candidate to Spotify Liked Songs."""

        if self.spotify_entity_id is None:
            raise HomeAssistantError("No SpotifyPlus entity is configured")
        candidate = self.selected_like_candidate
        if candidate is None:
            raise HomeAssistantError("No like candidate is selected")

        await self.hass.services.async_call(
            SPOTIFYPLUS_DOMAIN,
            SERVICE_SPOTIFYPLUS_SAVE_TRACK_FAVORITES,
            {
                "entity_id": self.spotify_entity_id,
                "ids": candidate.track_id,
            },
            blocking=True,
        )
        self._clear_like_candidates()

    async def async_cancel_like(self) -> None:
        """Discard pending like candidates without saving anything."""

        self._clear_like_candidates()

    @callback
    def _clear_like_candidates(self) -> None:
        """Reset the like candidate list and notify listeners."""

        self.like_candidates = []
        self.selected_like_candidate = None
        self._notify_listeners()

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
        self._notify_listeners()

    @callback
    def _notify_listeners(self) -> None:
        """Notify listeners of a state change."""

        for listener in self._listeners:
            listener()


def _parse_search_response(response: Any) -> list[LikeCandidate]:
    """Build like candidates from a SpotifyPlus search_tracks response."""

    items: list[Any] = []
    if isinstance(response, dict):
        tracks = response.get("tracks")
        if not isinstance(tracks, dict):
            result = response.get("result")
            tracks = result.get("tracks") if isinstance(result, dict) else None
        if isinstance(tracks, dict):
            items = tracks.get("items") or []

    candidates: list[LikeCandidate] = []
    label_counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        track_id = item.get("id")
        uri = item.get("uri")
        if not track_id or not uri:
            continue

        title = item.get("name") or "unknown"
        artists = item.get("artists") or []
        artist = (
            ", ".join(
                a["name"] for a in artists if isinstance(a, dict) and a.get("name")
            )
            or "unknown"
        )
        album_obj = item.get("album")
        album = album_obj.get("name") if isinstance(album_obj, dict) else None

        base_label = f"{artist} - {title}" + (f" ({album})" if album else "")
        count = label_counts.get(base_label, 0)
        label_counts[base_label] = count + 1
        label = base_label if count == 0 else f"{base_label} [{count + 1}]"

        candidates.append(LikeCandidate(track_id, uri, label, artist, title, album))
    return candidates


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


class MusicEntity(Entity):
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


class MusicRestoreEntity(MusicEntity, RestoreEntity):
    """Base class for entities that restore their state across restarts."""
