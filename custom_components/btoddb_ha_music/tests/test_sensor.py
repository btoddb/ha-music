"""Tests for the now-playing sensor's play-history wiring."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.media_player.const import (
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_TITLE,
)

from custom_components.btoddb_ha_music.controller import MusicController
from custom_components.btoddb_ha_music.sensor import NowPlayingSensor


class _FakeState:
    """A minimal stand-in for a Home Assistant media_player state."""

    def __init__(self, attributes: dict, *, state: str = "playing") -> None:
        self.state = state
        self.attributes = attributes


def _sensor_fixture() -> tuple[NowPlayingSensor, dict[str, _FakeState]]:
    """Build a NowPlayingSensor over a fake hass whose states can be mutated."""

    states: dict[str, _FakeState] = {
        "media_player.office": _FakeState(
            {
                ATTR_MEDIA_ARTIST: "Artist A",
                ATTR_MEDIA_TITLE: "Song A",
                ATTR_MEDIA_ALBUM_NAME: "Album A",
            }
        )
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), services=None)
    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": {"Office": "media_player.office"},
            "radio_stations": {},
            "playlists": {},
        },
        options={},
    )
    controller = MusicController(hass, entry)
    return NowPlayingSensor(controller), states


def test_sensor_publishes_empty_history_initially() -> None:
    """Before any track change, the sensor exposes an empty history list."""

    sensor, _states = _sensor_fixture()

    assert sensor.native_value == "Artist A - Song A"
    assert sensor.extra_state_attributes["artist"] == "Artist A"
    assert sensor.extra_state_attributes["history"] == []


def test_sensor_publishes_history_on_track_transitions() -> None:
    """Track changes push previous tracks into the published history attribute."""

    sensor, states = _sensor_fixture()

    states["media_player.office"] = _FakeState(
        {ATTR_MEDIA_ARTIST: "Artist B", ATTR_MEDIA_TITLE: "Song B"}
    )
    sensor._update_now_playing()
    states["media_player.office"] = _FakeState(
        {ATTR_MEDIA_ARTIST: "Artist C", ATTR_MEDIA_TITLE: "Song C"}
    )
    sensor._update_now_playing()

    history = sensor.extra_state_attributes["history"]
    assert [(t["artist"], t["title"]) for t in history] == [
        ("Artist B", "Song B"),
        ("Artist A", "Song A"),
    ]
    # Newest-first entries carry the PH-3 shape: artist/title/album/played_at.
    assert history[0]["album"] is None
    assert history[1]["album"] == "Album A"
    for track in history:
        assert set(track) == {"artist", "title", "album", "played_at"}
        assert track["played_at"]
    assert sensor.extra_state_attributes["title"] == "Song C"
