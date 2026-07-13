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


def _sensor_fixture(
    *, player_state: str = "playing"
) -> tuple[NowPlayingSensor, dict[str, _FakeState]]:
    """Build a NowPlayingSensor over a fake hass whose states can be mutated."""

    states: dict[str, _FakeState] = {
        "media_player.office": _FakeState(
            {
                ATTR_MEDIA_ARTIST: "Artist A",
                ATTR_MEDIA_TITLE: "Song A",
                ATTR_MEDIA_ALBUM_NAME: "Album A",
            },
            state=player_state,
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


def test_sensor_publishes_current_track_in_history_immediately() -> None:
    """The playing track is already in the history at first publish (issue #40)."""

    sensor, _states = _sensor_fixture()

    assert sensor.native_value == "Artist A - Song A"
    assert sensor.extra_state_attributes["artist"] == "Artist A"
    assert [
        (t["artist"], t["title"]) for t in sensor.extra_state_attributes["history"]
    ] == [("Artist A", "Song A")]


def test_sensor_publishes_history_on_track_transitions() -> None:
    """Each track lands in the published history as soon as it starts."""

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
        ("Artist C", "Song C"),
        ("Artist B", "Song B"),
        ("Artist A", "Song A"),
    ]
    # Newest-first entries carry the PH-3 shape: artist/title/album/played_at.
    assert history[0]["album"] is None
    assert history[2]["album"] == "Album A"
    for track in history:
        assert set(track) == {"artist", "title", "album", "played_at"}
        assert track["played_at"]
    assert sensor.extra_state_attributes["title"] == "Song C"


def test_sensor_ignores_retained_metadata_on_an_idle_player() -> None:
    """Startup over an idle player with stale metadata records no phantom play."""

    sensor, states = _sensor_fixture(player_state="idle")

    assert sensor.extra_state_attributes["playback_active"] is False
    assert sensor.extra_state_attributes["history"] == []

    # The same track actually starting afterwards is recorded.
    states["media_player.office"].state = "playing"
    sensor._update_now_playing()

    assert [
        (t["artist"], t["title"]) for t in sensor.extra_state_attributes["history"]
    ] == [("Artist A", "Song A")]


def test_sensor_playback_active_reflects_player_state_not_metadata() -> None:
    """An idle player retaining stale artist/title publishes playback_active=False."""

    sensor, states = _sensor_fixture()
    assert sensor.extra_state_attributes["playback_active"] is True

    # Queue finished on its own: the player goes idle but keeps its metadata.
    states["media_player.office"].state = "idle"
    sensor._update_now_playing()

    assert sensor.native_value == "Artist A - Song A"
    assert sensor.extra_state_attributes["playback_active"] is False


def test_sensor_playback_active_true_while_paused_by_the_integration() -> None:
    """A controller pause keeps playback_active True despite MA's idle state."""

    sensor, states = _sensor_fixture()
    controller = sensor._controller

    controller._set_paused_entity_ids(["media_player.office"])
    states["media_player.office"].state = "idle"
    sensor._update_now_playing()

    assert sensor.extra_state_attributes["playback_active"] is True
