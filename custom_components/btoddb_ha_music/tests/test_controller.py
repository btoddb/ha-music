"""Tests for BToddB HA Music controller resolution logic."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from homeassistant.components.media_player.const import (
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_TITLE,
)
from homeassistant.exceptions import HomeAssistantError

from custom_components.btoddb_ha_music.controller import (
    MusicController,
    _parse_search_response,
)


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

    def __init__(self, attributes: dict) -> None:
        self.state = "playing"
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
