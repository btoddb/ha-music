"""Tests for BToddB Music button availability (issue #36)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.btoddb_ha_music.button import (
    MusicActionButton,
    async_setup_entry,
)
from custom_components.btoddb_ha_music.controller import MusicController


def _controller() -> MusicController:
    """Build a controller with a speaker, a radio station, and a playlist."""

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
    return MusicController(None, entry)


def _buttons(controller: MusicController) -> dict[str, MusicActionButton]:
    """Set up the button platform and index the entities by key."""

    entities: list[MusicActionButton] = []
    entry = SimpleNamespace(runtime_data=controller)
    asyncio.run(async_setup_entry(None, entry, entities.extend))
    prefix = f"{controller.entry.entry_id}_"
    return {button.unique_id.removeprefix(prefix): button for button in entities}


def test_transport_buttons_unavailable_while_nothing_is_playing() -> None:
    """With no playback started, only play/stop remain available."""

    buttons = _buttons(_controller())

    assert buttons["play_music"].available is True
    assert buttons["stop_music"].available is True
    assert buttons["next_track"].available is False
    assert buttons["pause_music"].available is False
    assert buttons["resume_music"].available is False


def test_playlist_playback_enables_skip_and_pause_but_not_resume() -> None:
    """While an un-paused playlist plays, skip and pause apply; resume does not."""

    controller = _controller()
    controller._set_playing_kind("playlist")  # noqa: SLF001
    buttons = _buttons(controller)

    assert buttons["next_track"].available is True
    assert buttons["pause_music"].available is True
    assert buttons["resume_music"].available is False


def test_paused_playlist_enables_resume_and_grays_pause() -> None:
    """While paused, resume applies and pause does not."""

    controller = _controller()
    controller._set_playing_kind("playlist")  # noqa: SLF001
    controller._set_paused_entity_ids(["media_player.office"])  # noqa: SLF001
    buttons = _buttons(controller)

    assert buttons["pause_music"].available is False
    assert buttons["resume_music"].available is True


def test_radio_playback_keeps_skip_pause_and_resume_unavailable() -> None:
    """A radio stream has no next track and cannot be paused or resumed."""

    controller = _controller()
    controller._set_playing_kind("radio_station")  # noqa: SLF001
    buttons = _buttons(controller)

    assert buttons["stop_music"].available is True
    assert buttons["next_track"].available is False
    assert buttons["pause_music"].available is False
    assert buttons["resume_music"].available is False
