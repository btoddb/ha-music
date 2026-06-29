"""Tests for BToddB HA Music controller resolution logic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.btoddb_ha_music.controller import MusicController


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
