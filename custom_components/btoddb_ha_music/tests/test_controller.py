"""Tests for BToddB Music controller resolution logic."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from homeassistant.components.media_player.const import (
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_TITLE,
)
from homeassistant.exceptions import HomeAssistantError

from custom_components.btoddb_ha_music.const import (
    LIKED_STATE_LIKED,
    LIKED_STATE_NOT_LIKED,
    LIKED_STATE_UNKNOWN,
)
from custom_components.btoddb_ha_music.controller import (
    PLAY_HISTORY_LIMIT,
    MusicController,
    _extract_spotify_track_id,
    _normalize_playlist_id,
    _parse_favorites_response,
    _parse_search_response,
    _tracks_match,
)
from custom_components.btoddb_ha_music.models import LikeCandidate, NowPlaying


def _controller(
    *,
    speakers: dict | None = None,
    radio_stations: dict | None = None,
    playlists: dict | None = None,
) -> MusicController:
    """Build a controller with the given mappings and no Home Assistant."""

    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": speakers or {},
            "radio_stations": radio_stations or {},
            "playlists": playlists or {},
        },
        options={},
    )
    return MusicController(None, entry)


class _FakeState:
    """A minimal stand-in for a Home Assistant media_player state."""

    def __init__(self, attributes: dict, *, state: str = "playing") -> None:
        self.state = state
        self.attributes = attributes


class _FakeServices:
    """Records service calls and returns a canned response."""

    def __init__(self, response: dict | None = None) -> None:
        self.calls: list[tuple] = []
        self._response = response

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict,
        blocking: bool = True,
        return_response: bool = False,
    ):
        self.calls.append((domain, service, data, blocking, return_response))
        return self._response if return_response else None


class _FakeHass:
    """A minimal stand-in for HomeAssistant covering states and services."""

    def __init__(
        self, *, states: dict | None = None, response: dict | None = None
    ) -> None:
        self.states = SimpleNamespace(get=(states or {}).get)
        self.services = _FakeServices(response)


def _like_controller(
    hass: _FakeHass,
    *,
    speakers: dict,
    spotify_entity: str | None = None,
    like_playlist_id: str | None = None,
) -> MusicController:
    """Build a controller wired to a fake hass for like-flow tests."""

    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": speakers,
            "radio_stations": {},
            "playlists": {},
            "spotify_entity": spotify_entity or "",
            "like_playlist_id": like_playlist_id or "",
        },
        options={},
    )
    return MusicController(hass, entry)


_SEARCH_RESPONSE = {
    "tracks": {
        "items": [
            {
                "id": "1",
                "uri": "spotify:track:1",
                "name": "Song",
                "artists": [{"name": "Artist"}],
                "album": {"name": "Album"},
            },
            {
                "id": "2",
                "uri": "spotify:track:2",
                "name": "Song",
                "artists": [{"name": "Artist"}],
                "album": {"name": "Album"},
            },
        ]
    }
}


def test_resolve_speakers_maps_option_to_single_entity() -> None:
    """A speaker option pointing at one entity resolves to that entity."""

    controller = _controller(speakers={"Office": "media_player.office_speaker"})

    assert controller._resolve_speakers("Office") == ["media_player.office_speaker"]


def test_resolve_speakers_maps_option_to_group() -> None:
    """A speaker option pointing at a list resolves to every entity."""

    controller = _controller(
        speakers={"Upstairs": ["media_player.office", "media_player.bedroom"]}
    )

    assert controller._resolve_speakers("Upstairs") == [
        "media_player.office",
        "media_player.bedroom",
    ]


def test_resolve_speakers_falls_back_to_selection() -> None:
    """With no argument the first configured option is used."""

    controller = _controller(speakers={"All": "media_player.all_speakers"})

    assert controller._resolve_speakers(None) == ["media_player.all_speakers"]


def test_resolve_speakers_passes_through_raw_entity_id() -> None:
    """A raw media_player entity id is accepted without a mapping."""

    controller = _controller()

    assert controller._resolve_speakers("media_player.kitchen") == [
        "media_player.kitchen"
    ]


def test_resolve_speakers_rejects_non_media_player() -> None:
    """Targets outside the media_player domain are rejected."""

    controller = _controller()

    with pytest.raises(HomeAssistantError):
        controller._resolve_speakers("light.kitchen")


def test_resolve_speakers_requires_a_target() -> None:
    """With nothing configured or selected, resolution fails."""

    controller = _controller()

    with pytest.raises(HomeAssistantError):
        controller._resolve_speakers(None)


def test_resolve_media_maps_alias_to_uri() -> None:
    """A configured option name resolves to its Music Assistant URI."""

    controller = _controller(radio_stations={"KEXP": "radiobrowser://radio/abc"})

    assert (
        controller._resolve_media(
            "KEXP",
            selected=controller.selected_radio_station,
            mapping=controller.radio_stations,
            kind="radio station",
        )
        == "radiobrowser://radio/abc"
    )


def test_resolve_media_passes_through_raw_uri() -> None:
    """An unmapped value is treated as a raw URI."""

    controller = _controller()

    assert (
        controller._resolve_media(
            "spotify://playlist/xyz",
            selected=None,
            mapping=controller.playlists,
            kind="playlist",
        )
        == "spotify://playlist/xyz"
    )


def test_resolve_media_requires_a_target() -> None:
    """With nothing configured or selected, media resolution fails."""

    controller = _controller()

    with pytest.raises(HomeAssistantError):
        controller._resolve_media(
            None, selected=None, mapping=controller.playlists, kind="playlist"
        )


def test_like_enabled_reflects_spotify_entity_configuration() -> None:
    """Liking is only enabled once a SpotifyPlus entity is configured."""

    without_entity = _like_controller(_FakeHass(), speakers={})
    with_entity = _like_controller(
        _FakeHass(), speakers={}, spotify_entity="media_player.spotifyplus"
    )

    assert without_entity.like_enabled is False
    assert with_entity.like_enabled is True


def test_find_like_matches_requires_spotify_entity() -> None:
    """Searching for matches refuses without a configured SpotifyPlus entity."""

    controller = _like_controller(
        _FakeHass(), speakers={"Office": "media_player.office"}
    )

    with pytest.raises(HomeAssistantError):
        asyncio.run(controller.async_find_like_matches())


def test_find_like_matches_requires_identifiable_track() -> None:
    """Searching for matches refuses when artist/title are unknown."""

    hass = _FakeHass(states={"media_player.office": _FakeState({})})
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    with pytest.raises(HomeAssistantError):
        asyncio.run(controller.async_find_like_matches())


def test_find_like_matches_builds_and_dedups_candidates() -> None:
    """A successful search loads candidates and pre-selects the top match."""

    hass = _FakeHass(
        states={
            "media_player.office": _FakeState(
                {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"}
            )
        },
        response=_SEARCH_RESPONSE,
    )
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    asyncio.run(controller.async_find_like_matches())

    assert [c.label for c in controller.like_candidates] == [
        "Artist - Song (Album)",
        "Artist - Song (Album) [2]",
    ]
    assert controller.selected_like_candidate == controller.like_candidates[0]
    domain, service, data, _blocking, return_response = hass.services.calls[0]
    assert (domain, service) == ("spotifyplus", "search_tracks")
    assert data["entity_id"] == "media_player.spotifyplus"
    assert data["criteria"] == "Artist Song"
    assert return_response is True


def test_find_like_matches_raises_when_no_results() -> None:
    """An empty search result is reported as a clear error."""

    hass = _FakeHass(
        states={
            "media_player.office": _FakeState(
                {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"}
            )
        },
        response={"tracks": {"items": []}},
    )
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    with pytest.raises(HomeAssistantError):
        asyncio.run(controller.async_find_like_matches())


def test_set_selected_like_candidate_selects_by_label() -> None:
    """Selecting a candidate by label updates the current selection."""

    hass = _FakeHass(
        states={
            "media_player.office": _FakeState(
                {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"}
            )
        },
        response=_SEARCH_RESPONSE,
    )
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )
    asyncio.run(controller.async_find_like_matches())

    controller.set_selected_like_candidate("Artist - Song (Album) [2]")

    assert controller.selected_like_candidate.label == "Artist - Song (Album) [2]"


def test_set_selected_like_candidate_rejects_unknown_label() -> None:
    """Selecting an unknown label is rejected."""

    controller = _like_controller(
        _FakeHass(), speakers={"Office": "media_player.office"}
    )

    with pytest.raises(ValueError):
        controller.set_selected_like_candidate("nope")


def test_confirm_like_saves_and_clears() -> None:
    """Confirming saves the selected candidate and clears the list."""

    hass = _FakeHass(
        states={
            "media_player.office": _FakeState(
                {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"}
            )
        },
        response=_SEARCH_RESPONSE,
    )
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )
    asyncio.run(controller.async_find_like_matches())

    asyncio.run(controller.async_confirm_like())

    assert controller.like_candidates == []
    assert controller.selected_like_candidate is None
    domain, service, data, _blocking, _return_response = hass.services.calls[-1]
    assert (domain, service) == ("spotifyplus", "save_track_favorites")
    assert data == {"entity_id": "media_player.spotifyplus", "ids": "1"}
    assert all(call[1] != "playlist_items_add" for call in hass.services.calls)


def test_confirm_like_also_adds_to_configured_playlist() -> None:
    """Confirming with a playlist configured saves and appends to it."""

    hass = _FakeHass(
        states={
            "media_player.office": _FakeState(
                {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"}
            )
        },
        response=_SEARCH_RESPONSE,
    )
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
        like_playlist_id="spotify:playlist:abc123",
    )
    asyncio.run(controller.async_find_like_matches())

    asyncio.run(controller.async_confirm_like())

    assert controller.like_candidates == []
    assert controller.selected_like_candidate is None
    domain, service, data, blocking, return_response = hass.services.calls[-1]
    assert (domain, service) == ("spotifyplus", "playlist_items_add")
    assert data == {
        "entity_id": "media_player.spotifyplus",
        "playlist_id": "abc123",
        "uris": "spotify:track:1",
    }
    assert blocking is True
    assert return_response is True
    assert any(call[1] == "save_track_favorites" for call in hass.services.calls)


def test_confirm_like_logs_and_completes_when_playlist_add_fails() -> None:
    """A playlist-add failure is swallowed so the Liked Songs save still sticks."""

    class _FailingPlaylistAddServices(_FakeServices):
        async def async_call(
            self,
            domain: str,
            service: str,
            data: dict,
            blocking: bool = True,
            return_response: bool = False,
        ):
            if service == "playlist_items_add":
                self.calls.append((domain, service, data, blocking, return_response))
                raise HomeAssistantError("boom")
            return await super().async_call(
                domain,
                service,
                data,
                blocking=blocking,
                return_response=return_response,
            )

    hass = _FakeHass(
        states={
            "media_player.office": _FakeState(
                {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"}
            )
        },
        response=_SEARCH_RESPONSE,
    )
    hass.services = _FailingPlaylistAddServices(_SEARCH_RESPONSE)
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
        like_playlist_id="spotify:playlist:abc123",
    )
    asyncio.run(controller.async_find_like_matches())

    asyncio.run(controller.async_confirm_like())

    assert controller.like_candidates == []
    assert controller.selected_like_candidate is None
    assert any(call[1] == "save_track_favorites" for call in hass.services.calls)
    assert any(call[1] == "playlist_items_add" for call in hass.services.calls)


def test_confirm_like_requires_a_selected_candidate() -> None:
    """Confirming with nothing selected refuses rather than guessing."""

    controller = _like_controller(
        _FakeHass(),
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    with pytest.raises(HomeAssistantError):
        asyncio.run(controller.async_confirm_like())


def test_cancel_like_clears_without_saving() -> None:
    """Canceling clears candidates and never calls the save service."""

    hass = _FakeHass(
        states={
            "media_player.office": _FakeState(
                {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"}
            )
        },
        response=_SEARCH_RESPONSE,
    )
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )
    asyncio.run(controller.async_find_like_matches())

    asyncio.run(controller.async_cancel_like())

    assert controller.like_candidates == []
    assert controller.selected_like_candidate is None
    assert all(call[1] != "save_track_favorites" for call in hass.services.calls)


def test_parse_search_response_handles_nested_result_shape() -> None:
    """A response nested under a 'result' key is also understood."""

    response = {"result": _SEARCH_RESPONSE}

    candidates = _parse_search_response(response)

    assert [c.track_id for c in candidates] == ["1", "2"]


def test_parse_search_response_handles_real_spotifyplus_shape() -> None:
    """The actual SpotifyPlus shape nests items directly under 'result'."""

    response = {"result": _SEARCH_RESPONSE["tracks"]}

    candidates = _parse_search_response(response)

    assert [c.track_id for c in candidates] == ["1", "2"]


def test_parse_search_response_skips_items_missing_identifiers() -> None:
    """Items without an id or uri can't be liked, so they're dropped."""

    response = {
        "tracks": {
            "items": [
                {"name": "No id", "artists": [{"name": "Artist"}]},
                {
                    "id": "3",
                    "uri": "spotify:track:3",
                    "name": "Song",
                    "artists": [{"name": "Artist"}],
                    "album": {"name": "Album"},
                },
            ]
        }
    }

    candidates = _parse_search_response(response)

    assert [c.track_id for c in candidates] == ["3"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abc123", "abc123"),
        ("spotify:playlist:abc123", "abc123"),
        ("spotify://playlist/abc123", "abc123"),
        ("https://open.spotify.com/playlist/abc123", "abc123"),
        ("https://open.spotify.com/playlist/abc123?si=xyz", "abc123"),
        ("https://open.spotify.com/playlist/abc123/comments", "abc123"),
        ("  abc123  ", "abc123"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_playlist_id_accepts_known_forms(raw, expected) -> None:
    """The playlist id is extracted from any pasted form."""

    assert _normalize_playlist_id(raw) == expected


def _stop_controller(hass: _FakeHass, *, speakers: dict) -> MusicController:
    """Build a controller wired to a fake hass for stop-music tests."""

    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={"speakers": speakers, "radio_stations": {}, "playlists": {}},
        options={},
    )
    return MusicController(hass, entry)


def test_stop_music_no_target_skips_inactive_speakers() -> None:
    """With no target, only actively-playing speakers receive the stop call."""

    states = {
        "media_player.playing": _FakeState({}, state="playing"),
        "media_player.paused": _FakeState({}, state="paused"),
        "media_player.unavailable": _FakeState({}, state="unavailable"),
        "media_player.idle": _FakeState({}, state="idle"),
        "media_player.off": _FakeState({}, state="off"),
        "media_player.standby": _FakeState({}, state="standby"),
        "media_player.unknown": _FakeState({}, state="unknown"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={
            "All": [
                "media_player.playing",
                "media_player.paused",
                "media_player.unavailable",
                "media_player.idle",
                "media_player.off",
                "media_player.standby",
                "media_player.unknown",
            ]
        },
    )

    asyncio.run(controller.async_stop_music())

    assert len(hass.services.calls) == 1
    _domain, _service, data, _blocking, _ret = hass.services.calls[0]
    assert sorted(data["entity_id"]) == [
        "media_player.paused",
        "media_player.playing",
    ]


def test_stop_music_no_target_no_active_speakers_makes_no_call() -> None:
    """With no active speakers the stop command returns without calling any service."""

    states = {
        "media_player.unavailable": _FakeState({}, state="unavailable"),
        "media_player.idle": _FakeState({}, state="idle"),
        "media_player.off": _FakeState({}, state="off"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={
            "All": [
                "media_player.unavailable",
                "media_player.idle",
                "media_player.off",
            ]
        },
    )

    asyncio.run(controller.async_stop_music())

    assert hass.services.calls == []


def test_stop_music_explicit_target_is_not_filtered() -> None:
    """An explicit speaker target is passed through unchanged, regardless of state."""

    states = {"media_player.idle_speaker": _FakeState({}, state="idle")}
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass, speakers={"Office": "media_player.idle_speaker"}
    )

    asyncio.run(controller.async_stop_music(speakers="media_player.idle_speaker"))

    assert len(hass.services.calls) == 1
    _domain, _service, data, _blocking, _ret = hass.services.calls[0]
    assert data["entity_id"] == ["media_player.idle_speaker"]


def test_next_track_no_target_skips_only_active_speakers() -> None:
    """With no target, only actively-playing speakers receive the next_track call."""

    states = {
        "media_player.playing": _FakeState({}, state="playing"),
        "media_player.idle": _FakeState({}, state="idle"),
        "media_player.unavailable": _FakeState({}, state="unavailable"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={
            "All": [
                "media_player.playing",
                "media_player.idle",
                "media_player.unavailable",
            ]
        },
    )

    asyncio.run(controller.async_next_track())

    assert len(hass.services.calls) == 1
    _domain, service, data, _blocking, _ret = hass.services.calls[0]
    assert service == "media_next_track"
    assert data["entity_id"] == ["media_player.playing"]


def test_next_track_no_active_speakers_makes_no_call() -> None:
    """With no active speakers the next_track command returns without calling any service."""

    states = {
        "media_player.idle": _FakeState({}, state="idle"),
        "media_player.off": _FakeState({}, state="off"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={"All": ["media_player.idle", "media_player.off"]},
    )

    asyncio.run(controller.async_next_track())

    assert hass.services.calls == []


def test_next_track_explicit_target_is_not_filtered() -> None:
    """An explicit speaker target is passed through unchanged, regardless of state."""

    states = {"media_player.idle_speaker": _FakeState({}, state="idle")}
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass, speakers={"Office": "media_player.idle_speaker"}
    )

    asyncio.run(controller.async_next_track(speakers="media_player.idle_speaker"))

    assert len(hass.services.calls) == 1
    _domain, service, data, _blocking, _ret = hass.services.calls[0]
    assert service == "media_next_track"
    assert data["entity_id"] == ["media_player.idle_speaker"]


def test_media_options_combines_stations_and_playlists() -> None:
    """With the default filter, stations come first, then playlists."""

    controller = _controller(
        radio_stations={"KEXP": "radiobrowser://radio/kexp"},
        playlists={"Dinner": "spotify://playlist/dinner"},
    )

    assert controller.media_options() == ["KEXP", "Dinner"]
    assert controller.selected_media == "KEXP"


def test_media_options_disambiguates_duplicate_names() -> None:
    """A name in both mappings is suffixed so both stay selectable."""

    controller = _controller(
        radio_stations={"Jazz": "radiobrowser://radio/jazz"},
        playlists={"Jazz": "spotify://playlist/jazz"},
    )

    assert controller.media_options() == ["Jazz (Radio)", "Jazz (Playlist)"]


def test_media_filter_narrows_options_and_moves_selection() -> None:
    """Filtering away the current selection falls back to the first match."""

    controller = _controller(
        radio_stations={"KEXP": "radiobrowser://radio/kexp"},
        playlists={"Dinner": "spotify://playlist/dinner"},
    )

    controller.set_selected_media_filter("Playlists")

    assert controller.media_options() == ["Dinner"]
    assert controller.selected_media == "Dinner"

    controller.set_selected_media_filter("Radio stations")

    assert controller.media_options() == ["KEXP"]
    assert controller.selected_media == "KEXP"


def test_media_filter_keeps_valid_selection() -> None:
    """A selection still visible under the new filter is kept."""

    controller = _controller(
        radio_stations={"KEXP": "radiobrowser://radio/kexp"},
        playlists={"Dinner": "spotify://playlist/dinner"},
    )
    controller.set_selected_media("Dinner")

    controller.set_selected_media_filter("Playlists")

    assert controller.selected_media == "Dinner"


def test_set_selected_media_filter_rejects_unknown_option() -> None:
    """An unknown filter value is rejected."""

    controller = _controller()

    with pytest.raises(ValueError):
        controller.set_selected_media_filter("nope")


def test_set_selected_media_rejects_label_hidden_by_filter() -> None:
    """A label filtered out of the dropdown cannot be selected."""

    controller = _controller(
        radio_stations={"KEXP": "radiobrowser://radio/kexp"},
        playlists={"Dinner": "spotify://playlist/dinner"},
    )
    controller.set_selected_media_filter("Playlists")

    with pytest.raises(ValueError):
        controller.set_selected_media("KEXP")


def test_play_music_selected_radio_station_does_not_shuffle() -> None:
    """Playing a selected radio station turns shuffle off."""

    hass = _FakeHass()
    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": {"Office": "media_player.office"},
            "radio_stations": {"KEXP": "radiobrowser://radio/kexp"},
            "playlists": {"Dinner": "spotify://playlist/dinner"},
        },
        options={},
    )
    controller = MusicController(hass, entry)

    asyncio.run(controller.async_play_music())

    shuffle_call, play_call = hass.services.calls
    assert shuffle_call[1] == "shuffle_set"
    assert shuffle_call[2]["shuffle"] is False
    assert play_call[0] == "music_assistant"
    assert play_call[2]["media_id"] == "radiobrowser://radio/kexp"


def test_play_music_selected_playlist_shuffles() -> None:
    """Playing a selected playlist turns shuffle on."""

    hass = _FakeHass()
    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": {"Office": "media_player.office"},
            "radio_stations": {"KEXP": "radiobrowser://radio/kexp"},
            "playlists": {"Dinner": "spotify://playlist/dinner"},
        },
        options={},
    )
    controller = MusicController(hass, entry)
    controller.set_selected_media("Dinner")

    asyncio.run(controller.async_play_music())

    shuffle_call, play_call = hass.services.calls
    assert shuffle_call[2]["shuffle"] is True
    assert play_call[2]["media_id"] == "spotify://playlist/dinner"


def test_play_music_resolves_explicit_mapping_names() -> None:
    """An explicit media argument resolves through both mappings."""

    controller = _controller(
        radio_stations={"KEXP": "radiobrowser://radio/kexp"},
        playlists={"Dinner": "spotify://playlist/dinner"},
    )

    assert controller._resolve_music("KEXP") == ("radiobrowser://radio/kexp", False)
    assert controller._resolve_music("Dinner") == ("spotify://playlist/dinner", True)


def test_play_music_resolves_suffixed_duplicate_labels() -> None:
    """Suffixed duplicate labels resolve to the right mapping and shuffle."""

    controller = _controller(
        radio_stations={"Jazz": "radiobrowser://radio/jazz"},
        playlists={"Jazz": "spotify://playlist/jazz"},
    )

    assert controller._resolve_music("Jazz (Radio)") == (
        "radiobrowser://radio/jazz",
        False,
    )
    assert controller._resolve_music("Jazz (Playlist)") == (
        "spotify://playlist/jazz",
        True,
    )


def test_play_music_raw_uri_shuffles_only_playlists() -> None:
    """A raw URI is passed through, shuffled only when it is a playlist."""

    controller = _controller()

    assert controller._resolve_music("spotify://playlist/xyz") == (
        "spotify://playlist/xyz",
        True,
    )
    assert controller._resolve_music("radiobrowser://radio/abc") == (
        "radiobrowser://radio/abc",
        False,
    )


def test_play_music_requires_a_selection() -> None:
    """With nothing configured or selected, play music refuses."""

    controller = _controller(speakers={"Office": "media_player.office"})

    with pytest.raises(HomeAssistantError):
        asyncio.run(controller.async_play_music())


def _play_controller(hass: _FakeHass, *, speakers: dict) -> MusicController:
    """Build a controller with one radio station and one playlist configured."""

    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": speakers,
            "radio_stations": {"KEXP": "radiobrowser://radio/kexp"},
            "playlists": {"Dinner": "spotify://playlist/dinner"},
        },
        options={},
    )
    return MusicController(hass, entry)


def test_pause_music_no_target_targets_only_active_speakers() -> None:
    """With no target, only active speakers receive the media_pause call."""

    states = {
        "media_player.playing": _FakeState({}, state="playing"),
        "media_player.idle": _FakeState({}, state="idle"),
        "media_player.unavailable": _FakeState({}, state="unavailable"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={
            "All": [
                "media_player.playing",
                "media_player.idle",
                "media_player.unavailable",
            ]
        },
    )

    asyncio.run(controller.async_pause_music())

    assert len(hass.services.calls) == 1
    domain, service, data, _blocking, _ret = hass.services.calls[0]
    assert domain == "media_player"
    assert service == "media_pause"
    assert data["entity_id"] == ["media_player.playing"]


def test_resume_music_targets_paused_speakers() -> None:
    """Paused speakers are active targets, so resume reaches them."""

    states = {
        "media_player.paused": _FakeState({}, state="paused"),
        "media_player.off": _FakeState({}, state="off"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={"All": ["media_player.paused", "media_player.off"]},
    )

    asyncio.run(controller.async_resume_music())

    assert len(hass.services.calls) == 1
    domain, service, data, _blocking, _ret = hass.services.calls[0]
    assert domain == "media_player"
    assert service == "media_play"
    assert data["entity_id"] == ["media_player.paused"]


def test_pause_music_no_active_speakers_makes_no_call() -> None:
    """With no active speakers, pause returns without calling any service."""

    states = {
        "media_player.idle": _FakeState({}, state="idle"),
        "media_player.off": _FakeState({}, state="off"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={"All": ["media_player.idle", "media_player.off"]},
    )

    asyncio.run(controller.async_pause_music())
    asyncio.run(controller.async_resume_music())

    assert hass.services.calls == []


def test_pause_and_resume_explicit_target_is_not_filtered() -> None:
    """An explicit speaker target is passed through unchanged, regardless of state."""

    states = {"media_player.idle_speaker": _FakeState({}, state="idle")}
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass, speakers={"Office": "media_player.idle_speaker"}
    )

    asyncio.run(controller.async_pause_music(speakers="media_player.idle_speaker"))
    asyncio.run(controller.async_resume_music(speakers="media_player.idle_speaker"))

    assert [call[1] for call in hass.services.calls] == ["media_pause", "media_play"]
    assert all(
        call[2]["entity_id"] == ["media_player.idle_speaker"]
        for call in hass.services.calls
    )


def test_playing_kind_tracks_playback_lifecycle() -> None:
    """Play calls record the media kind and stop clears it."""

    states = {"media_player.office": _FakeState({}, state="playing")}
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    assert controller.playing_kind is None

    asyncio.run(controller.async_play_music(media="KEXP"))
    assert controller.playing_kind == "radio_station"

    asyncio.run(controller.async_play_music(media="Dinner"))
    assert controller.playing_kind == "playlist"

    asyncio.run(controller.async_stop_music())
    assert controller.playing_kind is None

    asyncio.run(controller.async_play_radio_station(station="KEXP"))
    assert controller.playing_kind == "radio_station"

    asyncio.run(controller.async_shuffle_play_playlist(playlist="Dinner"))
    assert controller.playing_kind == "playlist"


def test_playing_kind_change_notifies_listeners() -> None:
    """Playing-kind transitions notify listeners so button availability refreshes."""

    states = {"media_player.office": _FakeState({}, state="playing")}
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    notified = []
    controller.async_add_listener(lambda: notified.append(True))

    asyncio.run(controller.async_shuffle_play_playlist(playlist="Dinner"))
    assert notified

    notified.clear()
    asyncio.run(controller.async_stop_music())
    assert notified


def test_pause_music_collapses_group_members_onto_group_player() -> None:
    """Synced members sharing the group's queue are not sent the pause call.

    Music Assistant raises "set_members needs to be implemented" when a
    transport command hits a synced member, so only the queue-owning group
    player may be targeted.
    """

    states = {
        "media_player.kitchen": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "player"},
            state="playing",
        ),
        "media_player.main_floor": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "group"},
            state="playing",
        ),
        "media_player.office": _FakeState(
            {"active_queue": "queue_office", "mass_player_type": "player"},
            state="playing",
        ),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={
            "Main Floor": "media_player.main_floor",
            "Kitchen": "media_player.kitchen",
            "Office": "media_player.office",
        },
    )

    asyncio.run(controller.async_pause_music())

    assert len(hass.services.calls) == 1
    _domain, service, data, _blocking, _ret = hass.services.calls[0]
    assert service == "media_pause"
    # kitchen sorts before main_floor, but the group player still wins its queue
    assert data["entity_id"] == ["media_player.main_floor", "media_player.office"]


def test_resume_music_collapses_members_without_a_group_to_one_target() -> None:
    """With no group player among the targets, one member per queue is kept."""

    states = {
        "media_player.a": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "player"},
            state="paused",
        ),
        "media_player.b": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "player"},
            state="paused",
        ),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass, speakers={"All": ["media_player.a", "media_player.b"]}
    )

    asyncio.run(controller.async_resume_music())

    assert len(hass.services.calls) == 1
    _domain, service, data, _blocking, _ret = hass.services.calls[0]
    assert service == "media_play"
    assert data["entity_id"] == ["media_player.a"]


def test_next_track_collapses_group_members_onto_group_player() -> None:
    """Skip goes to one player per queue, or the queue advances once per target.

    A synced member and its group player share the same MA queue; sending
    media_next_track to both skips two songs (issue: Skip skipped the now
    playing AND the next song).
    """

    states = {
        "media_player.kitchen": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "player"},
            state="playing",
        ),
        "media_player.main_floor": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "group"},
            state="playing",
        ),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={
            "Main Floor": "media_player.main_floor",
            "Kitchen": "media_player.kitchen",
        },
    )

    asyncio.run(controller.async_next_track())

    assert len(hass.services.calls) == 1
    _domain, service, data, _blocking, _ret = hass.services.calls[0]
    assert service == "media_next_track"
    assert data["entity_id"] == ["media_player.main_floor"]


def test_pause_music_keeps_players_without_queue_attributes() -> None:
    """Players missing MA attributes each stay their own target."""

    states = {
        "media_player.a": _FakeState({}, state="playing"),
        "media_player.b": _FakeState({}, state="playing"),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass, speakers={"All": ["media_player.a", "media_player.b"]}
    )

    asyncio.run(controller.async_pause_music())

    _domain, _service, data, _blocking, _ret = hass.services.calls[0]
    assert data["entity_id"] == ["media_player.a", "media_player.b"]


def test_pause_music_explicit_target_is_not_collapsed() -> None:
    """Explicit speaker targets pass through without queue collapsing."""

    states = {
        "media_player.a": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "player"},
            state="playing",
        ),
        "media_player.b": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "player"},
            state="playing",
        ),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass, speakers={"All": ["media_player.a", "media_player.b"]}
    )

    asyncio.run(
        controller.async_pause_music(speakers=["media_player.a", "media_player.b"])
    )

    _domain, _service, data, _blocking, _ret = hass.services.calls[0]
    assert data["entity_id"] == ["media_player.a", "media_player.b"]


def test_resume_music_targets_players_remembered_from_pause() -> None:
    """Resume reaches the paused players even though MA reports them idle.

    Music Assistant reports paused players as "idle", which the active-state
    filter excludes, so resume must replay the targets pause recorded.
    """

    states = {
        "media_player.group": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "group"},
            state="playing",
        ),
        "media_player.member": _FakeState(
            {"active_queue": "syncgroup_1", "mass_player_type": "player"},
            state="playing",
        ),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={"Group": "media_player.group", "Member": "media_player.member"},
    )

    asyncio.run(controller.async_pause_music())
    # MA now reports both players idle.
    states["media_player.group"].state = "idle"
    states["media_player.member"].state = "idle"

    asyncio.run(controller.async_resume_music())

    assert [call[1] for call in hass.services.calls] == ["media_pause", "media_play"]
    assert hass.services.calls[1][2]["entity_id"] == ["media_player.group"]


def test_resume_music_clears_remembered_pause_targets() -> None:
    """A second resume falls back to active-target resolution (a no-op here)."""

    states = {
        "media_player.office": _FakeState(
            {"active_queue": "q1", "mass_player_type": "player"}, state="playing"
        ),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(hass, speakers={"Office": "media_player.office"})

    asyncio.run(controller.async_pause_music())
    states["media_player.office"].state = "idle"
    asyncio.run(controller.async_resume_music())
    asyncio.run(controller.async_resume_music())

    assert [call[1] for call in hass.services.calls] == ["media_pause", "media_play"]


def test_new_playback_and_stop_clear_remembered_pause_targets() -> None:
    """Playing something new or stopping discards the remembered pause."""

    states = {
        "media_player.office": _FakeState(
            {"active_queue": "q1", "mass_player_type": "player"}, state="playing"
        ),
    }
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    asyncio.run(controller.async_pause_music())
    asyncio.run(controller.async_play_music(media="Dinner"))
    assert controller._paused_entity_ids == []

    asyncio.run(controller.async_pause_music())
    asyncio.run(controller.async_stop_music())
    assert controller._paused_entity_ids == []


def test_resume_music_explicit_target_ignores_remembered_pause() -> None:
    """An explicit speaker target overrides the remembered pause targets."""

    states = {
        "media_player.office": _FakeState(
            {"active_queue": "q1", "mass_player_type": "player"}, state="playing"
        ),
        "media_player.kitchen": _FakeState(
            {"active_queue": "q2", "mass_player_type": "player"}, state="idle"
        ),
    }
    hass = _FakeHass(states=states)
    controller = _stop_controller(
        hass,
        speakers={"Office": "media_player.office", "Kitchen": "media_player.kitchen"},
    )

    asyncio.run(controller.async_pause_music())
    asyncio.run(controller.async_resume_music(speakers="media_player.kitchen"))

    assert hass.services.calls[1][1] == "media_play"
    assert hass.services.calls[1][2]["entity_id"] == ["media_player.kitchen"]


def _now_playing(artist: str, title: str, album: str | None = None) -> NowPlaying:
    """Build a NowPlaying value for play-history tests."""

    display = " - ".join(part for part in (artist, title) if part != "unknown")
    return NowPlaying(display or "unknown", "media_player.office", artist, title, album)


def _record(controller, now_playing, *, active: bool = True) -> None:
    """Record with an explicit playback lifecycle signal (PR #41 review)."""

    controller.record_now_playing(now_playing, playback_active=active)


def test_record_now_playing_records_track_when_it_starts() -> None:
    """A track lands in the history the moment it starts playing (issue #40)."""

    controller = _controller()

    _record(controller, _now_playing("Artist A", "Song A", "Album A"))
    assert [(t.artist, t.title) for t in controller.play_history] == [
        ("Artist A", "Song A")
    ]

    _record(controller, _now_playing("Artist B", "Song B"))
    _record(controller, _now_playing("Artist C", "Song C"))

    assert [(t.artist, t.title) for t in controller.play_history] == [
        ("Artist C", "Song C"),
        ("Artist B", "Song B"),
        ("Artist A", "Song A"),
    ]
    assert controller.play_history[2].album == "Album A"
    assert controller.play_history[0].played_at  # timestamp is recorded


def test_record_now_playing_keeps_track_recorded_after_stop() -> None:
    """Stopping playback keeps the last track in the history (issue #40)."""

    controller = _controller()

    _record(controller, _now_playing("Artist", "Song"))
    # A stopped/idle player may retain its metadata (PR #41 review).
    _record(controller, _now_playing("Artist", "Song"), active=False)

    assert [(t.artist, t.title) for t in controller.play_history] == [
        ("Artist", "Song")
    ]


def test_record_now_playing_ignores_retained_metadata_while_inactive() -> None:
    """An idle player retaining artist/title creates no phantom play (PR #41)."""

    controller = _controller()
    events: list[str] = []
    controller.async_add_listener(lambda: events.append("notified"))

    _record(controller, _now_playing("Stale Artist", "Stale Song"), active=False)

    assert controller.play_history == []
    assert events == []


def test_record_now_playing_records_same_song_replayed_after_stop() -> None:
    """Going inactive resets start detection so a replay records (PR #41)."""

    controller = _controller()

    _record(controller, _now_playing("Artist", "Song"))
    _record(controller, _now_playing("Artist", "Song"), active=False)
    _record(controller, _now_playing("Artist", "Song"))

    assert [(t.artist, t.title) for t in controller.play_history] == [
        ("Artist", "Song"),
        ("Artist", "Song"),
    ]


def test_record_now_playing_pause_does_not_reset_or_duplicate() -> None:
    """An integration pause counts as active, so it neither resets nor re-records."""

    controller = _controller()

    _record(controller, _now_playing("Artist", "Song"))
    # playback_active() reports True during a controller pause (PM-8).
    _record(controller, _now_playing("Artist", "Song"), active=True)
    _record(controller, _now_playing("Artist", "Song"), active=True)

    assert [(t.artist, t.title) for t in controller.play_history] == [
        ("Artist", "Song")
    ]


def test_pause_marks_paused_before_issuing_media_pause() -> None:
    """is_paused is set before the media_pause call (issue #40 follow-up).

    Music Assistant reports a paused player as "idle" and its state event can
    arrive while the blocking media_pause is still awaited. is_paused must
    already be true then, so playback_active() stays true and the racing idle
    event does not reset now-playing start detection.
    """

    states = {
        "media_player.office": _FakeState(
            {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"},
            state="playing",
        )
    }
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    paused_when_called: list[bool] = []
    original = hass.services.async_call

    async def _spy(domain, service, data, blocking=True, return_response=False):
        if service == "media_pause":
            paused_when_called.append(controller.is_paused)
        return await original(domain, service, data, blocking, return_response)

    hass.services.async_call = _spy

    asyncio.run(controller.async_pause_music())

    assert paused_when_called == [True]


def test_pause_does_not_duplicate_history_when_idle_event_races() -> None:
    """The idle event MA emits mid-pause must not re-record the track (issue #40).

    Reproduces the reported bug: pausing a playing playlist added a second copy
    of the current track to the history (visible in both Now Playing and the
    history list, persisting after resume).
    """

    states = {
        "media_player.office": _FakeState(
            {ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"},
            state="playing",
        )
    }
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    def refresh() -> None:
        controller.record_now_playing(
            controller.now_playing(), playback_active=controller.playback_active()
        )

    # Track is playing and recorded once.
    refresh()
    # The sensor refreshes whenever the controller notifies (e.g. the pause flip).
    controller.async_add_listener(refresh)

    original = hass.services.async_call

    async def _pause(domain, service, data, blocking=True, return_response=False):
        # MA applies the pause: the player goes idle (metadata retained) and its
        # state event fires a sensor refresh while media_pause is still awaited.
        states["media_player.office"].state = "idle"
        refresh()
        return await original(domain, service, data, blocking, return_response)

    hass.services.async_call = _pause
    asyncio.run(controller.async_pause_music())

    # Resume: the player plays again and refreshes once more.
    states["media_player.office"].state = "playing"
    refresh()

    assert [(t.artist, t.title) for t in controller.play_history] == [
        ("Artist", "Song")
    ]


def test_record_now_playing_ignores_unchanged_track() -> None:
    """Repeated updates for the same track add nothing to the history."""

    controller = _controller()

    _record(controller, _now_playing("Artist", "Song"))
    _record(controller, _now_playing("Artist", "Song"))
    _record(controller, _now_playing("Artist", "Song"))

    assert [(t.artist, t.title) for t in controller.play_history] == [
        ("Artist", "Song")
    ]


def test_record_now_playing_refreshes_late_album_metadata() -> None:
    """Album metadata arriving after the track was recorded updates the entry."""

    controller = _controller()

    _record(controller, _now_playing("Artist", "Song"))
    assert controller.play_history[0].album is None

    _record(controller, _now_playing("Artist", "Song", "Album"))

    assert len(controller.play_history) == 1
    assert controller.play_history[0].album == "Album"


def test_record_now_playing_skips_unidentifiable_track() -> None:
    """A track with unknown artist or title is never recorded."""

    controller = _controller()

    _record(controller, _now_playing("unknown", "unknown"))
    _record(controller, _now_playing("Artist", "unknown"))
    _record(controller, _now_playing("unknown", "Song"))

    assert controller.play_history == []


def test_record_now_playing_caps_history_at_limit() -> None:
    """The history keeps only the most recent PLAY_HISTORY_LIMIT tracks."""

    controller = _controller()

    for index in range(PLAY_HISTORY_LIMIT + 3):
        _record(controller, _now_playing(f"Artist {index}", f"Song {index}"))

    assert len(controller.play_history) == PLAY_HISTORY_LIMIT
    # Newest first; the current track is the newest history entry.
    assert controller.play_history[0].title == f"Song {PLAY_HISTORY_LIMIT + 2}"
    assert controller.play_history[-1].title == "Song 3"


def test_record_now_playing_notifies_listeners_only_on_history_change() -> None:
    """Listeners fire when a track lands in history, not on no-op updates."""

    controller = _controller()
    events: list[str] = []
    controller.async_add_listener(lambda: events.append("notified"))

    _record(controller, _now_playing("unknown", "unknown"))
    assert events == []

    _record(controller, _now_playing("Artist A", "Song A"))
    assert events == ["notified"]

    _record(controller, _now_playing("Artist A", "Song A"))
    assert events == ["notified"]

    _record(controller, _now_playing("Artist B", "Song B"))
    assert events == ["notified", "notified"]


def test_find_like_matches_with_explicit_artist_and_title() -> None:
    """Explicit artist/title (a history entry) searches without now-playing."""

    hass = _FakeHass(states={}, response=_SEARCH_RESPONSE)
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    asyncio.run(
        controller.async_find_like_matches(artist="History Artist", title="Old Song")
    )

    domain, service, data, _blocking, _return_response = hass.services.calls[0]
    assert (domain, service) == ("spotifyplus", "search_tracks")
    assert data["criteria"] == "History Artist Old Song"
    assert controller.like_candidates


def test_find_like_matches_rejects_partial_artist_title() -> None:
    """Passing only one of artist/title is refused with a clear error."""

    hass = _FakeHass(states={}, response=_SEARCH_RESPONSE)
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    with pytest.raises(HomeAssistantError):
        asyncio.run(controller.async_find_like_matches(artist="Artist"))
    with pytest.raises(HomeAssistantError):
        asyncio.run(controller.async_find_like_matches(title="Song"))


def test_is_paused_tracks_pause_resume_lifecycle() -> None:
    """Pause sets is_paused; resume, stop, and new playback clear it."""

    states = {"media_player.office": _FakeState({}, state="playing")}
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    assert controller.is_paused is False

    asyncio.run(controller.async_pause_music())
    assert controller.is_paused is True

    asyncio.run(controller.async_resume_music())
    assert controller.is_paused is False

    asyncio.run(controller.async_pause_music())
    asyncio.run(controller.async_stop_music())
    assert controller.is_paused is False

    asyncio.run(controller.async_pause_music())
    asyncio.run(controller.async_shuffle_play_playlist(playlist="Dinner"))
    assert controller.is_paused is False


def test_paused_state_change_notifies_listeners() -> None:
    """Paused/not-paused flips notify listeners so button availability refreshes."""

    states = {"media_player.office": _FakeState({}, state="playing")}
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    notified = []
    controller.async_add_listener(lambda: notified.append(True))

    asyncio.run(controller.async_pause_music())
    assert notified

    notified.clear()
    asyncio.run(controller.async_resume_music())
    assert notified

    # Clearing an already-clear paused state is not a flip and stays silent.
    notified.clear()
    controller._set_paused_entity_ids([])  # noqa: SLF001
    assert not notified


def test_playback_active_ignores_retained_metadata_on_idle_players() -> None:
    """An idle player keeping its last artist/title does not count as active."""

    states = {
        "media_player.office": _FakeState(
            {ATTR_MEDIA_ARTIST: "Artist A", ATTR_MEDIA_TITLE: "Song A"},
            state="idle",
        )
    }
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    assert controller.playback_active() is False

    states["media_player.office"].state = "playing"
    assert controller.playback_active() is True


def test_playback_active_counts_remembered_pause_as_active() -> None:
    """MA reports paused players as idle; a controller pause keeps it active."""

    states = {"media_player.office": _FakeState({}, state="playing")}
    hass = _FakeHass(states=states)
    controller = _play_controller(hass, speakers={"Office": "media_player.office"})

    asyncio.run(controller.async_pause_music())
    states["media_player.office"].state = "idle"
    assert controller.playback_active() is True

    asyncio.run(controller.async_resume_music())
    assert controller.playback_active() is False


# --- issue #43: "already liked" heart resolution ------------------------------


class _RoutedServices:
    """Records service calls and returns a per-service canned response."""

    def __init__(self, responses: dict[str, dict] | None = None) -> None:
        self.calls: list[tuple] = []
        self._responses = responses or {}

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict,
        blocking: bool = True,
        return_response: bool = False,
    ):
        self.calls.append((domain, service, data, blocking, return_response))
        return self._responses.get(service) if return_response else None


class _RoutedHass:
    """A fake hass whose service responses vary by service name."""

    def __init__(
        self, *, states: dict | None = None, responses: dict[str, dict] | None = None
    ) -> None:
        self.states = SimpleNamespace(get=(states or {}).get)
        self.services = _RoutedServices(responses)


def _favorites(**by_id: bool) -> dict:
    """Build a SpotifyPlus check_track_favorites response."""

    return {"result": {f"spotify:track:{tid}": liked for tid, liked in by_id.items()}}


def _liked_controller(hass, *, states_attrs: dict, spotify_entity: str = "media_player.spotifyplus") -> MusicController:
    """Build a controller whose Office speaker reports the given attributes."""

    hass.states = SimpleNamespace(
        get={"media_player.office": _FakeState(states_attrs)}.get
    )
    return _like_controller(
        hass, speakers={"Office": "media_player.office"}, spotify_entity=spotify_entity
    )


@pytest.mark.parametrize(
    "content_id, expected",
    [
        ("spotify--F4QubKZS://track/7lPgKA5mLFNmGPMdb07OlM", "7lPgKA5mLFNmGPMdb07OlM"),
        ("spotify://track/abc123", "abc123"),
        ("spotify:track:abc123", "abc123"),
        ("spotify://track/abc123?foo=bar", "abc123"),
        ("radiobrowser://radio/kexp", None),
        ("spotify://playlist/xyz", None),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_extract_spotify_track_id(content_id, expected) -> None:
    """Only Spotify track content ids yield a bare track id."""

    assert _extract_spotify_track_id(content_id) == expected


def test_parse_favorites_response_reduces_uris_to_ids() -> None:
    """The favorites response is keyed by bare track id and coerced to bool."""

    parsed = _parse_favorites_response(_favorites(a=True, b=False))
    assert parsed == {"a": True, "b": False}


def test_parse_favorites_response_handles_malformed_input() -> None:
    """Non-dict payloads degrade to an empty mapping."""

    assert _parse_favorites_response(None) == {}
    assert _parse_favorites_response({"result": "nope"}) == {}


def _candidate(track_id: str, artist: str, title: str) -> LikeCandidate:
    return LikeCandidate(track_id, f"spotify:track:{track_id}", "l", artist, title, None)


def test_tracks_match_requires_artist_and_title() -> None:
    """A candidate matches only when both artist and title align."""

    assert _tracks_match("Jamie xx/Romy", "Loud Places", _candidate("1", "Jamie xx, Romy", "Loud Places"))
    # Title mismatch.
    assert not _tracks_match("Artist", "Song", _candidate("1", "Artist", "Other"))
    # Artist mismatch.
    assert not _tracks_match("Artist", "Song", _candidate("1", "Someone", "Song"))


def test_tracks_match_ignores_feat_and_punctuation() -> None:
    """Bracketed qualifiers and feat clauses do not defeat a real match."""

    assert _tracks_match(
        "Artist",
        "Song (feat. Guest) [Remastered]",
        _candidate("1", "Artist feat. Guest", "Song"),
    )


def test_resolve_liked_uses_exact_content_id_when_spotify() -> None:
    """A Spotify-sourced track is checked by its exact id, no search."""

    hass = _RoutedHass(responses={"check_track_favorites": _favorites(abc=True)})
    controller = _liked_controller(
        hass,
        states_attrs={
            ATTR_MEDIA_ARTIST: "Artist",
            ATTR_MEDIA_TITLE: "Song",
            ATTR_MEDIA_CONTENT_ID: "spotify://track/abc",
        },
    )

    assert asyncio.run(controller.async_resolve_now_playing_liked()) == LIKED_STATE_LIKED
    services = [call[1] for call in hass.services.calls]
    assert services == ["check_track_favorites"]


def test_resolve_liked_exact_content_id_not_liked() -> None:
    """An exact-id check that returns False resolves to not_liked."""

    hass = _RoutedHass(responses={"check_track_favorites": _favorites(abc=False)})
    controller = _liked_controller(
        hass,
        states_attrs={
            ATTR_MEDIA_ARTIST: "Artist",
            ATTR_MEDIA_TITLE: "Song",
            ATTR_MEDIA_CONTENT_ID: "spotify://track/abc",
        },
    )

    assert (
        asyncio.run(controller.async_resolve_now_playing_liked())
        == LIKED_STATE_NOT_LIKED
    )


def test_resolve_liked_fuzzy_search_when_not_spotify() -> None:
    """A non-Spotify source searches, matches, and reports liked."""

    hass = _RoutedHass(
        responses={
            "search_tracks": _SEARCH_RESPONSE,
            "check_track_favorites": _favorites(**{"1": False, "2": True}),
        }
    )
    controller = _liked_controller(
        hass,
        states_attrs={
            ATTR_MEDIA_ARTIST: "Artist",
            ATTR_MEDIA_TITLE: "Song",
            ATTR_MEDIA_CONTENT_ID: "radiobrowser://radio/kexp",
        },
    )

    assert asyncio.run(controller.async_resolve_now_playing_liked()) == LIKED_STATE_LIKED
    services = [call[1] for call in hass.services.calls]
    assert services == ["search_tracks", "check_track_favorites"]


def test_resolve_liked_returns_unknown_when_no_match() -> None:
    """A search with no artist/title match resolves to unknown, no check."""

    hass = _RoutedHass(responses={"search_tracks": _SEARCH_RESPONSE})
    controller = _liked_controller(
        hass,
        states_attrs={
            ATTR_MEDIA_ARTIST: "Nobody",
            ATTR_MEDIA_TITLE: "Nothing",
            ATTR_MEDIA_CONTENT_ID: "radiobrowser://radio/kexp",
        },
    )

    assert (
        asyncio.run(controller.async_resolve_now_playing_liked()) == LIKED_STATE_UNKNOWN
    )
    services = [call[1] for call in hass.services.calls]
    assert services == ["search_tracks"]


def test_resolve_liked_without_spotify_entity_is_unknown() -> None:
    """No SpotifyPlus entity means the heart cannot be resolved."""

    hass = _RoutedHass()
    controller = _liked_controller(
        hass,
        states_attrs={ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"},
        spotify_entity="",
    )

    assert (
        asyncio.run(controller.async_resolve_now_playing_liked()) == LIKED_STATE_UNKNOWN
    )
    assert hass.services.calls == []


def test_resolve_liked_caches_confident_result() -> None:
    """Re-resolving the same track hits the cache instead of the API."""

    hass = _RoutedHass(responses={"check_track_favorites": _favorites(abc=True)})
    controller = _liked_controller(
        hass,
        states_attrs={
            ATTR_MEDIA_ARTIST: "Artist",
            ATTR_MEDIA_TITLE: "Song",
            ATTR_MEDIA_CONTENT_ID: "spotify://track/abc",
        },
    )

    asyncio.run(controller.async_resolve_now_playing_liked())
    asyncio.run(controller.async_resolve_now_playing_liked())
    assert [call[1] for call in hass.services.calls] == ["check_track_favorites"]


def test_find_like_matches_annotates_candidate_liked_state() -> None:
    """Each search candidate carries its exact Liked Songs membership."""

    hass = _RoutedHass(
        responses={
            "search_tracks": _SEARCH_RESPONSE,
            "check_track_favorites": _favorites(**{"1": True, "2": False}),
        }
    )
    controller = _liked_controller(
        hass,
        states_attrs={ATTR_MEDIA_ARTIST: "Artist", ATTR_MEDIA_TITLE: "Song"},
    )

    asyncio.run(controller.async_find_like_matches(artist="Artist", title="Song"))
    assert [c.liked for c in controller.like_candidates] == [True, False]


def test_confirm_like_clears_liked_cache() -> None:
    """Liking a track invalidates the cached heart state so it re-checks."""

    hass = _RoutedHass(responses={"check_track_favorites": _favorites(abc=False)})
    controller = _liked_controller(
        hass,
        states_attrs={
            ATTR_MEDIA_ARTIST: "Artist",
            ATTR_MEDIA_TITLE: "Song",
            ATTR_MEDIA_CONTENT_ID: "spotify://track/abc",
        },
    )

    asyncio.run(controller.async_resolve_now_playing_liked())
    controller.like_candidates = [_candidate("abc", "Artist", "Song")]
    controller.selected_like_candidate = controller.like_candidates[0]
    asyncio.run(controller.async_confirm_like())
    assert controller._liked_cache == {}


_NON_MATCHING_SEARCH = {
    "tracks": {
        "items": [
            {
                "id": "9",
                "uri": "spotify:track:9",
                "name": "Different",
                "artists": [{"name": "Someone Else"}],
                "album": {"name": "Album"},
            }
        ]
    }
}


def test_resolve_liked_rechecks_when_content_id_arrives_later() -> None:
    """A fuzzy 'unknown' is not sticky: a later exact id resolves afresh (PR #44)."""

    state = _FakeState(
        {
            ATTR_MEDIA_ARTIST: "Artist",
            ATTR_MEDIA_TITLE: "Song",
            ATTR_MEDIA_CONTENT_ID: "radiobrowser://radio/kexp",
        }
    )
    hass = _RoutedHass(
        responses={
            "search_tracks": _NON_MATCHING_SEARCH,
            "check_track_favorites": _favorites(xyz=True),
        }
    )
    hass.states = SimpleNamespace(get={"media_player.office": state}.get)
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    # No Spotify id yet: fuzzy search finds no artist+title match -> unknown.
    assert (
        asyncio.run(controller.async_resolve_now_playing_liked()) == LIKED_STATE_UNKNOWN
    )

    # Music Assistant later attaches the exact Spotify track id.
    state.attributes[ATTR_MEDIA_CONTENT_ID] = "spotify://track/xyz"
    assert asyncio.run(controller.async_resolve_now_playing_liked()) == LIKED_STATE_LIKED


def test_resolve_liked_does_not_collide_distinct_recordings() -> None:
    """Two recordings sharing artist/title cache under their own track ids."""

    state = _FakeState(
        {
            ATTR_MEDIA_ARTIST: "Artist",
            ATTR_MEDIA_TITLE: "Song",
            ATTR_MEDIA_CONTENT_ID: "spotify://track/aaa",
        }
    )
    hass = _RoutedHass(
        responses={"check_track_favorites": _favorites(aaa=True, bbb=False)}
    )
    hass.states = SimpleNamespace(get={"media_player.office": state}.get)
    controller = _like_controller(
        hass,
        speakers={"Office": "media_player.office"},
        spotify_entity="media_player.spotifyplus",
    )

    assert asyncio.run(controller.async_resolve_now_playing_liked()) == LIKED_STATE_LIKED
    state.attributes[ATTR_MEDIA_CONTENT_ID] = "spotify://track/bbb"
    assert (
        asyncio.run(controller.async_resolve_now_playing_liked())
        == LIKED_STATE_NOT_LIKED
    )
