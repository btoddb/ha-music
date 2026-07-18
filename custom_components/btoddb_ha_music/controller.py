"""Controller for BToddB Music actions."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any

from homeassistant.components.media_player.const import (
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_TITLE,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_STOP,
    SERVICE_SHUFFLE_SET,
    STATE_UNAVAILABLE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_MA_ACTIVE_QUEUE,
    ATTR_MA_PLAYER_TYPE,
    CONF_LIKE_PLAYLIST_ID,
    MA_PLAYER_TYPE_GROUP,
    MEDIA_FILTER_ALL,
    MEDIA_FILTER_OPTIONS,
    MEDIA_FILTER_PLAYLISTS,
    MEDIA_FILTER_RADIO_STATIONS,
    CONF_LIKE_SEARCH_LIMIT,
    CONF_PLAYLISTS,
    CONF_RADIO_STATIONS,
    CONF_SPEAKERS,
    CONF_SPOTIFY_ENTITY,
    DEFAULT_LIKE_SEARCH_LIMIT,
    LIKED_STATE_LIKED,
    LIKED_STATE_NOT_LIKED,
    LIKED_STATE_UNKNOWN,
    MA_ENQUEUE_REPLACE,
    MUSIC_ASSISTANT_DOMAIN,
    SERVICE_MA_PLAY_MEDIA,
    SERVICE_SPOTIFYPLUS_ADD_PLAYLIST_ITEMS,
    SERVICE_SPOTIFYPLUS_CHECK_TRACK_FAVORITES,
    SERVICE_SPOTIFYPLUS_SAVE_TRACK_FAVORITES,
    SERVICE_SPOTIFYPLUS_SEARCH_TRACKS,
    SPOTIFYPLUS_DOMAIN,
)
from .models import (
    LikeCandidate,
    MediaItem,
    NamedMapping,
    NowPlaying,
    PlayedTrack,
    parse_named_mapping,
)

_LOGGER = logging.getLogger(__name__)

PLAY_HISTORY_LIMIT = 10

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
        self.media_items = _build_media_items(self.radio_stations, self.playlists)
        self.selected_media_filter = MEDIA_FILTER_ALL
        self.selected_media = next(iter(self.media_options()), None)
        self.spotify_entity_id = data.get(CONF_SPOTIFY_ENTITY) or None
        self.like_search_limit = int(
            data.get(CONF_LIKE_SEARCH_LIMIT, DEFAULT_LIKE_SEARCH_LIMIT)
        )
        self.like_playlist_id = _normalize_playlist_id(data.get(CONF_LIKE_PLAYLIST_ID))
        self.like_candidates: list[LikeCandidate] = []
        self.selected_like_candidate: LikeCandidate | None = None
        # Cache of resolved "already liked" state, so the same now-playing
        # track is not searched/checked against Spotify repeatedly as the media
        # player churns state (issue #43). Keyed on the exact Spotify track id
        # when one is available and on (artist, title) otherwise, so distinct
        # recordings that share an artist/title do not collide and a track that
        # gains a Spotify id resolves afresh (PR #44 review).
        self._liked_cache: dict[tuple[str, ...], str] = {}
        # Kind of the last media this controller started ("radio_station" or
        # "playlist"), cleared on stop. Pause/resume only make sense for
        # playlists, so their buttons key their availability off this.
        self.playing_kind: str | None = None
        # Players the last pause_music call paused. Music Assistant reports
        # them as "idle" afterwards, so resume_music cannot re-discover them
        # via the active-state filter. Cleared by resume, stop, and new
        # playback; not persisted across restarts.
        self._paused_entity_ids: list[str] = []
        # Recently played tracks, newest first, capped at PLAY_HISTORY_LIMIT.
        # A track lands here the moment it becomes the now-playing track
        # (issue #40), so the newest entry duplicates Now Playing while it
        # plays and nothing is lost when playback stops. In-memory only —
        # not persisted across restarts.
        self.play_history: list[PlayedTrack] = []
        self._last_now_playing: NowPlaying | None = None
        self._listeners: list[SelectionListener] = []

    @property
    def is_paused(self) -> bool:
        """Return whether the last pause_music call is still in effect."""

        return bool(self._paused_entity_ids)

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

    def media_options(self) -> list[str]:
        """Return the combined media labels matching the current filter."""

        if self.selected_media_filter == MEDIA_FILTER_RADIO_STATIONS:
            kinds = {"radio_station"}
        elif self.selected_media_filter == MEDIA_FILTER_PLAYLISTS:
            kinds = {"playlist"}
        else:
            kinds = {"radio_station", "playlist"}
        return [item.label for item in self.media_items if item.kind in kinds]

    @callback
    def set_selected_media_filter(self, option: str) -> None:
        """Set the media filter, keeping the media selection valid."""

        if option not in MEDIA_FILTER_OPTIONS:
            raise ValueError(f"Unknown media filter: {option}")
        self.selected_media_filter = option
        options = self.media_options()
        if self.selected_media not in options:
            self.selected_media = next(iter(options), None)
        self._notify_listeners()

    @callback
    def set_selected_media(self, option: str) -> None:
        """Set the selected combined media option."""

        if option not in self.media_options():
            raise ValueError(f"Unknown media: {option}")
        self.selected_media = option
        self._notify_listeners()

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
        self._set_playing_kind("radio_station")

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
        self._set_playing_kind("playlist")

    async def async_play_music(
        self, *, media: str | None = None, speakers: str | list[str] | None = None
    ) -> None:
        """Play the selected or requested media, radio or playlist alike.

        Radio stations play as-is; playlists are shuffled first. An unmapped
        value is treated as a raw Music Assistant URI and shuffled only when
        it looks like a playlist.
        """

        entity_ids = self._resolve_speakers(speakers)
        media_id, shuffle = self._resolve_music(media)
        await self._async_set_shuffle(entity_ids, shuffle=shuffle)
        await self._async_play_media(entity_ids, media_id)
        self._set_playing_kind("playlist" if shuffle else "radio_station")

    def _resolve_music(self, requested: str | None) -> tuple[str, bool]:
        """Resolve a combined media label, mapping name, or raw URI.

        Returns the media id and whether it should be shuffled.
        """

        option = requested or self.selected_media
        if option is None:
            raise HomeAssistantError("No music is configured or selected")

        for item in self.media_items:
            if item.label == option:
                return item.media_id, item.kind == "playlist"

        # Not a catalog label: accept a raw mapping name or Music Assistant URI.
        station = self.radio_stations.get(option)
        if isinstance(station, str):
            return station, False
        playlist = self.playlists.get(option)
        if isinstance(playlist, str):
            return playlist, True
        return option, "playlist" in option

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
        self._set_paused_entity_ids([])

    async def async_stop_music(
        self, *, speakers: str | list[str] | None = None
    ) -> None:
        """Stop playback.

        With no target this stops every configured speaker, so "stop whatever
        is playing" works regardless of which group is currently selected. A
        specific target can still be passed via the service call.
        """

        entity_ids = self._resolve_active_targets(speakers=speakers)
        self._set_playing_kind(None)
        self._set_paused_entity_ids([])
        if not entity_ids:
            return
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_STOP,
            {"entity_id": entity_ids},
            blocking=True,
        )

    async def async_pause_music(
        self, *, speakers: str | list[str] | None = None
    ) -> None:
        """Pause playback on the actively-playing configured speakers.

        Only meaningful while a playlist is playing; radio streams cannot be
        meaningfully paused/resumed, so the backing button entity is
        unavailable unless the controller last started a playlist.
        """

        entity_ids = self._resolve_active_targets(speakers=speakers)
        if speakers is None:
            entity_ids = self._collapse_queue_targets(entity_ids)
        if not entity_ids:
            return
        # Mark the pause BEFORE issuing media_pause. Music Assistant reports a
        # paused player as "idle", and its state event can arrive while the
        # blocking call is still awaited. If is_paused were not yet set, that
        # event would see every speaker idle, count playback as inactive, and
        # reset the now-playing start detector — so the pause would re-record
        # the current track as a duplicate play once is_paused flipped true
        # (issue #40 follow-up). Keeping is_paused true across the transition
        # keeps playback_active() true, so the paused track is never re-added.
        self._set_paused_entity_ids(entity_ids)
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PAUSE,
            {"entity_id": entity_ids},
            blocking=True,
        )

    async def async_resume_music(
        self, *, speakers: str | list[str] | None = None
    ) -> None:
        """Resume playback on the players a prior pause_music call paused.

        Music Assistant reports paused players as "idle", so the
        active-state target filter cannot find them again; the controller
        remembers exactly which players it paused and sends media_play back
        to those. With no remembered pause (or an explicit target), the
        stop/pause target resolution applies as a fallback.
        """

        if speakers is None and self._paused_entity_ids:
            entity_ids = self._paused_entity_ids
        else:
            entity_ids = self._resolve_active_targets(speakers=speakers)
            if speakers is None:
                entity_ids = self._collapse_queue_targets(entity_ids)
        if not entity_ids:
            return
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PLAY,
            {"entity_id": entity_ids},
            blocking=True,
        )
        self._set_paused_entity_ids([])

    @callback
    def _set_playing_kind(self, kind: str | None) -> None:
        """Record the kind of media playback just started (or cleared)."""

        if self.playing_kind == kind:
            return
        self.playing_kind = kind
        self._notify_listeners()

    @callback
    def _set_paused_entity_ids(self, entity_ids: list[str]) -> None:
        """Record the players the last pause call paused (or clear them).

        Pause/Resume button availability keys off ``is_paused``, so listeners
        are notified whenever the paused/not-paused state flips.
        """

        was_paused = self.is_paused
        self._paused_entity_ids = entity_ids
        if self.is_paused != was_paused:
            self._notify_listeners()

    async def async_next_track(
        self, *, speakers: str | list[str] | None = None
    ) -> None:
        """Skip to the next track.

        With no target this skips only the actively-playing configured speakers.
        A specific target can still be passed via the service call.
        """

        entity_ids = self._resolve_active_targets(speakers=speakers)
        if speakers is None:
            entity_ids = self._collapse_queue_targets(entity_ids)
        if not entity_ids:
            return
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_NEXT_TRACK,
            {"entity_id": entity_ids},
            blocking=True,
        )

    _INACTIVE_STATES = frozenset(
        {STATE_UNAVAILABLE, "unknown", "off", "idle", "standby"}
    )

    def _resolve_active_targets(self, *, speakers: str | list[str] | None) -> list[str]:
        """Resolve targets for stop/skip commands.

        With no explicit target, resolves to only the actively-playing configured
        speakers (raises when none are configured at all; returns [] when none are
        currently active so the caller can short-circuit). An explicit target is
        passed through unchanged regardless of playback state.
        """

        if speakers is None:
            all_ids = sorted(self.all_media_player_entity_ids)
            if not all_ids:
                raise HomeAssistantError("No speakers are configured")
            return self._filter_active_speakers(all_ids)
        return self._resolve_speakers(speakers)

    def _collapse_queue_targets(self, entity_ids: list[str]) -> list[str]:
        """Collapse sync-group members onto one target per active queue.

        When a Music Assistant group player is playing, its member players
        are also "active" and share the group's `active_queue`. Sending
        pause/play to a synced member makes MA raise ("set_members needs to
        be implemented when PlayerFeature.SET_MEMBERS is set"), so per queue
        the command goes to the group player (`mass_player_type: group`) when
        one is among the targets, otherwise to the first target only.
        """

        by_queue: dict[str, str] = {}
        result: list[str] = []
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            attributes = state.attributes if state is not None else {}
            queue = attributes.get(ATTR_MA_ACTIVE_QUEUE) or entity_id
            is_group = attributes.get(ATTR_MA_PLAYER_TYPE) == MA_PLAYER_TYPE_GROUP
            if queue not in by_queue:
                by_queue[queue] = entity_id
                result.append(entity_id)
            elif is_group:
                result[result.index(by_queue[queue])] = entity_id
                by_queue[queue] = entity_id
        return result

    def _filter_active_speakers(self, entity_ids: list[str]) -> list[str]:
        """Return only speakers that are in an active (non-idle/offline) state."""

        active = []
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state not in self._INACTIVE_STATES:
                active.append(entity_id)
        return active

    def playback_active(self) -> bool:
        """Return whether any configured speaker is actively playing.

        This is the "is anything playing" signal for button applicability
        (issue #36): it derives from the players' actual states, not from
        retained media metadata, because an idle player can keep its last
        artist/title after a queue finishes. Music Assistant reports paused
        players as "idle", so a pause this controller performed counts as
        active — Resume must stay applicable.
        """

        if self.is_paused:
            return True
        return bool(
            self._filter_active_speakers(sorted(self.all_media_player_entity_ids))
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
            content_id = state.attributes.get(ATTR_MEDIA_CONTENT_ID)
            display = " - ".join(part for part in (artist, title) if part) or "unknown"
            return NowPlaying(
                display,
                entity_id,
                artist or "unknown",
                title or "unknown",
                album,
                content_id,
            )

        return NowPlaying("unknown", None, "unknown", "unknown", None)

    @callback
    def record_now_playing(
        self,
        now_playing: NowPlaying | None = None,
        *,
        playback_active: bool | None = None,
    ) -> None:
        """Push the current track into the play history when it starts playing.

        Called by the now-playing sensor whenever it refreshes. The current
        track is recorded (newest first, capped at PLAY_HISTORY_LIMIT) the
        moment its artist/title pair becomes the now-playing track (issue
        #40), so stopping playback loses nothing. Pause/volume state churn
        and radio streams without metadata add nothing; album metadata that
        arrives after the track was recorded refreshes the newest entry.

        Recording is gated on the playback_active() lifecycle (PR #41
        review): an idle player retaining its last artist/title must not
        create a phantom play (integration startup, speaker switch), and
        going inactive resets start detection so replaying the same track
        after a stop records a new entry. A pause this controller performed
        counts as active (PM-8), so it neither resets nor re-records.
        """

        active = (
            playback_active if playback_active is not None else self.playback_active()
        )
        if not active:
            self._last_now_playing = None
            return

        current = now_playing if now_playing is not None else self.now_playing()
        previous = self._last_now_playing
        if previous is not None and (previous.artist, previous.title) == (
            current.artist,
            current.title,
        ):
            head = self.play_history[0] if self.play_history else None
            if (
                current.album
                and head is not None
                and (head.artist, head.title) == (current.artist, current.title)
                and head.album != current.album
            ):
                self.play_history[0] = replace(head, album=current.album)
                self._notify_listeners()
            return
        self._last_now_playing = current

        if current.artist == "unknown" or current.title == "unknown":
            return
        self.play_history.insert(
            0,
            PlayedTrack(
                current.artist,
                current.title,
                current.album,
                dt_util.utcnow().isoformat(),
            ),
        )
        del self.play_history[PLAY_HISTORY_LIMIT:]
        self._notify_listeners()

    async def _async_search_tracks(
        self, artist: str, title: str
    ) -> list[LikeCandidate]:
        """Search Spotify for tracks matching an artist/title.

        Returns the parsed candidates without mutating the like-picker state,
        so both the Like flow and the "already liked" heart check share one
        search path (issue #43).
        """

        query = f"{artist} {title}"
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
        return _parse_search_response(response)

    async def _async_check_track_favorites(
        self, track_ids: Iterable[str]
    ) -> dict[str, bool]:
        """Return which of the given Spotify track ids are in Liked Songs.

        Keys in the returned mapping are bare track ids. An empty input skips
        the service call entirely.
        """

        ids = [track_id for track_id in track_ids if track_id]
        if not ids:
            return {}
        response = await self.hass.services.async_call(
            SPOTIFYPLUS_DOMAIN,
            SERVICE_SPOTIFYPLUS_CHECK_TRACK_FAVORITES,
            {
                "entity_id": self.spotify_entity_id,
                "ids": ",".join(ids),
            },
            blocking=True,
            return_response=True,
        )
        return _parse_favorites_response(response)

    async def async_find_like_matches(
        self, *, artist: str | None = None, title: str | None = None
    ) -> None:
        """Search Spotify for tracks matching an artist/title.

        With no explicit artist/title the now-playing track is used; the card
        passes both explicitly to like a track from the play history.
        """

        if self.spotify_entity_id is None:
            raise HomeAssistantError("No SpotifyPlus entity is configured")

        if artist is None and title is None:
            now_playing = self.now_playing()
            artist = now_playing.artist
            title = now_playing.title
            if artist == "unknown" or title == "unknown":
                raise HomeAssistantError("Nothing identifiable is currently playing")
        elif not artist or not title:
            raise HomeAssistantError("Both artist and title are required")

        candidates = await self._async_search_tracks(artist, title)
        if not candidates:
            raise HomeAssistantError(f"No Spotify matches found for {artist} {title}")

        candidates = await self._async_annotate_liked(candidates)
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
        if self.like_playlist_id is not None:
            try:
                await self.hass.services.async_call(
                    SPOTIFYPLUS_DOMAIN,
                    SERVICE_SPOTIFYPLUS_ADD_PLAYLIST_ITEMS,
                    {
                        "entity_id": self.spotify_entity_id,
                        "playlist_id": self.like_playlist_id,
                        "uris": candidate.uri,
                    },
                    blocking=True,
                    return_response=True,
                )
            except HomeAssistantError as err:
                # The track is already saved to Liked Songs at this point, so a
                # playlist-add failure (bad id, transient API error, etc.)
                # shouldn't leave the like flow stuck "unfinished".
                _LOGGER.warning(
                    "Saved %s to Liked Songs but failed to add it to playlist %s: %s",
                    candidate.label,
                    self.like_playlist_id,
                    err,
                )
        # A just-liked track invalidates any cached "not liked" heart state,
        # so the next resolve re-checks against Spotify (issue #43).
        self._liked_cache.clear()
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

    async def _async_annotate_liked(
        self, candidates: list[LikeCandidate]
    ) -> list[LikeCandidate]:
        """Return the candidates with their Liked Songs membership filled in.

        A favorites-check failure is non-fatal: the candidates are returned
        unannotated (``liked`` left as None) so the Like flow still works.
        """

        try:
            favorites = await self._async_check_track_favorites(
                candidate.track_id for candidate in candidates
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Could not check track favorites: %s", err)
            return candidates
        return [
            replace(candidate, liked=favorites.get(candidate.track_id))
            for candidate in candidates
        ]

    async def async_resolve_now_playing_liked(self) -> str:
        """Return whether the now-playing track is already in Liked Songs.

        Resolves the current track to one or more Spotify track ids and checks
        their favorites membership (issue #43):

        - A Spotify-sourced track carries its exact id in ``media_content_id``,
          so it is checked directly.
        - Otherwise the track's artist/title are searched on Spotify and only
          candidates whose artist AND title match are checked; the song counts
          as liked if any matching candidate is a favorite.

        Returns ``LIKED_STATE_UNKNOWN`` when there is no Spotify entity, nothing
        identifiable is playing, or no confident match is found, so the heart
        never claims an unresolved track is unliked. Results are cached per
        (artist, title).
        """

        if self.spotify_entity_id is None:
            return LIKED_STATE_UNKNOWN

        now_playing = self.now_playing()
        artist, title = now_playing.artist, now_playing.title
        if artist == "unknown" or title == "unknown":
            return LIKED_STATE_UNKNOWN

        cache_key = _liked_cache_key(now_playing)
        cached = self._liked_cache.get(cache_key)
        if cached is not None:
            return cached

        state = await self._async_compute_liked(now_playing)
        # Only cache confident answers; an unknown may become resolvable once
        # richer metadata (e.g. a Spotify content id) arrives for the track.
        if state != LIKED_STATE_UNKNOWN:
            self._liked_cache[cache_key] = state
        return state

    async def _async_compute_liked(self, now_playing: NowPlaying) -> str:
        """Do the un-cached favorites resolution for a now-playing track."""

        track_id = _extract_spotify_track_id(now_playing.media_content_id)
        try:
            if track_id is not None:
                favorites = await self._async_check_track_favorites([track_id])
                if track_id in favorites:
                    return (
                        LIKED_STATE_LIKED
                        if favorites[track_id]
                        else LIKED_STATE_NOT_LIKED
                    )
                return LIKED_STATE_UNKNOWN

            candidates = await self._async_search_tracks(
                now_playing.artist, now_playing.title
            )
            matches = [
                candidate
                for candidate in candidates
                if _tracks_match(now_playing.artist, now_playing.title, candidate)
            ]
            if not matches:
                return LIKED_STATE_UNKNOWN
            favorites = await self._async_check_track_favorites(
                candidate.track_id for candidate in matches
            )
            if not favorites:
                return LIKED_STATE_UNKNOWN
            if any(favorites.get(candidate.track_id) for candidate in matches):
                return LIKED_STATE_LIKED
            return LIKED_STATE_NOT_LIKED
        except HomeAssistantError as err:
            _LOGGER.debug("Could not resolve liked state: %s", err)
            return LIKED_STATE_UNKNOWN

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
        result = response.get("result")
        track_pages = (
            response.get("tracks"),
            result.get("tracks") if isinstance(result, dict) else None,
            result,
        )
        for track_page in track_pages:
            if isinstance(track_page, dict) and isinstance(
                track_page.get("items"), list
            ):
                items = track_page["items"]
                break

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


def _parse_favorites_response(response: Any) -> dict[str, bool]:
    """Map bare Spotify track ids to their Liked Songs membership.

    SpotifyPlus returns ``{"result": {"spotify:track:<id>": bool, ...}}``; the
    keys are reduced to bare ids so callers can look up by ``track_id``.
    """

    favorites: dict[str, bool] = {}
    if not isinstance(response, dict):
        return favorites
    payload = response.get("result")
    if not isinstance(payload, dict):
        return favorites
    for key, value in payload.items():
        if not isinstance(key, str) or not key:
            continue
        track_id = key.rsplit(":", 1)[-1]
        favorites[track_id] = bool(value)
    return favorites


def _extract_spotify_track_id(content_id: Any) -> str | None:
    """Extract a bare Spotify track id from a media_content_id, if present.

    Handles Music Assistant's provider-scoped scheme
    (``spotify--<instance>://track/<id>``), the plain ``spotify://track/<id>``
    URI, and the ``spotify:track:<id>`` form. Returns None for anything that is
    not a Spotify track (radio streams, other providers), so a non-Spotify
    source falls through to the fuzzy search path (issue #43).
    """

    if not isinstance(content_id, str):
        return None
    value = content_id.strip()
    if not value:
        return None

    scheme, sep, rest = value.partition("://")
    if sep and scheme.startswith("spotify"):
        kind, _, tail = rest.partition("/")
        if kind == "track" and tail:
            track_id = tail.split("?", 1)[0].strip("/").split("/", 1)[0]
            return track_id if track_id.isalnum() else None
        return None
    if value.startswith("spotify:track:"):
        track_id = value[len("spotify:track:") :].split("?", 1)[0]
        return track_id if track_id.isalnum() else None
    return None


def _liked_cache_key(now_playing: NowPlaying) -> tuple[str, ...]:
    """Identity under which a track's liked state is cached.

    Prefers the exact Spotify track id (so two recordings sharing an
    artist/title stay distinct, and a track that later gains a Spotify id
    resolves under a new key rather than reusing a fuzzy result); falls back to
    (artist, title) for non-Spotify sources (PR #44 review).
    """

    track_id = _extract_spotify_track_id(now_playing.media_content_id)
    if track_id is not None:
        return ("id", track_id)
    return ("meta", now_playing.artist, now_playing.title)


# Bracketed qualifiers — "(feat. X)", "[Remastered]" — and trailing
# feat/with clauses are dropped before comparing titles so metadata noise does
# not defeat an otherwise exact match.
_STRIP_BRACKETS = re.compile(r"[(\[{].*?[)\]}]")
_STRIP_FEAT = re.compile(r"\b(?:feat|ft|featuring|with)\b.*", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Separators that join multiple artists in a single display string, across the
# Music Assistant ("A/B") and Spotify ("A, B") conventions.
_ARTIST_SPLIT = re.compile(r"[/,&]|\bx\b|\band\b|\bfeat\b|\bft\b", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    """Lowercase and strip punctuation/qualifiers for fuzzy comparison."""

    lowered = _STRIP_BRACKETS.sub(" ", text.casefold())
    lowered = _STRIP_FEAT.sub(" ", lowered)
    return " ".join(_NON_ALNUM.sub(" ", lowered).split())


def _artist_tokens(artist: str) -> set[str]:
    """Split a possibly-multi-artist string into a set of normalized names."""

    return {
        token
        for part in _ARTIST_SPLIT.split(artist)
        if (token := _normalize_text(part))
    }


def _tracks_match(artist: str, title: str, candidate: LikeCandidate) -> bool:
    """Return whether a search candidate is the same song as artist/title.

    The title must match exactly once normalized, and the artist sets must
    overlap — the artist-AND-title rule that keeps a liked cover or remix from
    lighting the heart for a different recording (issue #43).
    """

    if _normalize_text(title) != _normalize_text(candidate.title):
        return False
    now_tokens = _artist_tokens(artist)
    candidate_tokens = _artist_tokens(candidate.artist)
    if not now_tokens or not candidate_tokens:
        return False
    return bool(now_tokens & candidate_tokens)


def _normalize_playlist_id(raw: Any) -> str | None:
    """Extract a bare Spotify playlist id from a configured value.

    Accepts a bare id, a `spotify:playlist:<id>` URI, a Music-Assistant-style
    `spotify://playlist/<id>` URI, or an `open.spotify.com/playlist/<id>` URL,
    so users can paste whatever form they have on hand.
    """

    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None

    for prefix in ("spotify:playlist:", "spotify://playlist/"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    else:
        if "open.spotify.com/playlist/" in value:
            value = value.split("open.spotify.com/playlist/", 1)[1]

    value = value.split("?", 1)[0].strip("/").split("/", 1)[0]
    return value or None


def _build_media_items(
    radio_stations: NamedMapping, playlists: NamedMapping
) -> list[MediaItem]:
    """Combine radio stations and playlists into one labeled catalog.

    A name configured as both a radio station and a playlist gets a kind
    suffix on each label so the two stay selectable in one dropdown.
    """

    duplicates = set(radio_stations) & set(playlists)
    items: list[MediaItem] = []
    for name, value in radio_stations.items():
        if not isinstance(value, str):
            continue
        label = f"{name} (Radio)" if name in duplicates else name
        items.append(MediaItem(label, "radio_station", value))
    for name, value in playlists.items():
        if not isinstance(value, str):
            continue
        label = f"{name} (Playlist)" if name in duplicates else name
        items.append(MediaItem(label, "playlist", value))
    return items


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
            "name": "BToddB Music",
        }
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"


class MusicRestoreEntity(MusicEntity, RestoreEntity):
    """Base class for entities that restore their state across restarts."""
