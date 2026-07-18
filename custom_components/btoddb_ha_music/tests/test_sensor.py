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
        assert set(track) == {"artist", "title", "album", "played_at", "liked"}
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


# --- issue #43: now-playing "already liked" heart ----------------------------


from homeassistant.components.media_player.const import (  # noqa: E402
    ATTR_MEDIA_CONTENT_ID,
)

from custom_components.btoddb_ha_music.const import (  # noqa: E402
    LIKED_STATE_LIKED,
    LIKED_STATE_UNKNOWN,
)


class _RoutedServices:
    """Records service calls and returns a per-service canned response."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.calls: list[tuple] = []
        self._responses = responses

    async def async_call(
        self, domain, service, data, blocking=True, return_response=False
    ):
        self.calls.append((domain, service))
        return self._responses.get(service) if return_response else None


def _liked_sensor_fixture(content_id: str, responses: dict[str, dict]):
    """Build a sensor whose SpotifyPlus-backed liked resolution can be driven."""

    states = {
        "media_player.office": _FakeState(
            {
                ATTR_MEDIA_ARTIST: "Artist A",
                ATTR_MEDIA_TITLE: "Song A",
                ATTR_MEDIA_CONTENT_ID: content_id,
            }
        )
    }
    hass = SimpleNamespace(
        states=SimpleNamespace(get=states.get),
        services=_RoutedServices(responses),
    )
    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": {"Office": "media_player.office"},
            "radio_stations": {},
            "playlists": {},
            "spotify_entity": "media_player.spotifyplus",
        },
        options={},
    )
    sensor = NowPlayingSensor(MusicController(hass, entry))
    return sensor, hass


def test_sensor_liked_defaults_to_unknown() -> None:
    """Before any resolution the heart state reads unknown."""

    sensor, _states = _sensor_fixture()
    assert sensor.extra_state_attributes["now_playing_liked"] == LIKED_STATE_UNKNOWN


def test_sensor_resolves_liked_from_exact_content_id() -> None:
    """A Spotify-sourced now-playing track resolves its exact liked state."""

    import asyncio

    sensor, _hass = _liked_sensor_fixture(
        "spotify://track/abc",
        {"check_track_favorites": {"result": {"spotify:track:abc": True}}},
    )
    writes: list[int] = []
    sensor.async_write_ha_state = lambda: writes.append(1)

    key = ("Artist A", "Song A", "spotify://track/abc", 0)
    sensor._liked_key = key
    asyncio.run(sensor._async_resolve_liked(key))

    assert sensor.extra_state_attributes["now_playing_liked"] == LIKED_STATE_LIKED
    assert writes == [1]


def test_sensor_mirrors_resolved_liked_into_history() -> None:
    """The resolved heart state lands on the track's history entry.

    Otherwise a liked now-playing track would flip back to a neutral heart
    the moment it moves into the history list.
    """

    import asyncio

    sensor, _hass = _liked_sensor_fixture(
        "spotify://track/abc",
        {"check_track_favorites": {"result": {"spotify:track:abc": True}}},
    )
    sensor.async_write_ha_state = lambda: None

    key = ("Artist A", "Song A", "spotify://track/abc", 0)
    sensor._liked_key = key
    asyncio.run(sensor._async_resolve_liked(key))

    assert sensor._controller.play_history[0].liked == LIKED_STATE_LIKED
    sensor._update_now_playing()
    assert sensor.extra_state_attributes["history"][0]["liked"] == LIKED_STATE_LIKED


def test_sensor_sync_liked_skips_scheduling_without_spotify() -> None:
    """With no SpotifyPlus entity the sensor never schedules a lookup."""

    sensor, _states = _sensor_fixture()
    scheduled: list = []
    sensor.hass = SimpleNamespace(async_create_task=scheduled.append)

    sensor._sync_liked()

    assert scheduled == []
    assert sensor._liked_key is None
    assert sensor.extra_state_attributes["now_playing_liked"] == LIKED_STATE_UNKNOWN


def test_sensor_rechecks_liked_when_content_id_is_added(monkeypatch) -> None:
    """A metadata revision adding the Spotify id re-resolves the heart (PR #44)."""

    import asyncio

    from homeassistant.components.media_player.const import ATTR_MEDIA_CONTENT_ID

    state = _FakeState(
        {
            ATTR_MEDIA_ARTIST: "Artist A",
            ATTR_MEDIA_TITLE: "Song A",
            ATTR_MEDIA_CONTENT_ID: "radiobrowser://radio/kexp",
        }
    )
    non_matching = {
        "tracks": {
            "items": [
                {
                    "id": "9",
                    "uri": "spotify:track:9",
                    "name": "Different",
                    "artists": [{"name": "Someone Else"}],
                    "album": None,
                }
            ]
        }
    }
    hass = SimpleNamespace(
        states=SimpleNamespace(get={"media_player.office": state}.get),
        services=_RoutedServices(
            {
                "search_tracks": non_matching,
                "check_track_favorites": {"result": {"spotify:track:abc": True}},
            }
        ),
    )
    entry = SimpleNamespace(
        entry_id="test",
        domain="btoddb_ha_music",
        data={
            "speakers": {"Office": "media_player.office"},
            "radio_stations": {},
            "playlists": {},
            "spotify_entity": "media_player.spotifyplus",
        },
        options={},
    )
    sensor = NowPlayingSensor(MusicController(hass, entry))
    sensor.async_write_ha_state = lambda: None

    scheduled: list = []
    sensor.hass = SimpleNamespace(async_create_task=scheduled.append)

    def run_scheduled() -> None:
        while scheduled:
            asyncio.run(scheduled.pop(0))

    # First pass: no Spotify id, fuzzy search finds no match -> unknown.
    sensor._sync_liked()
    run_scheduled()
    assert sensor.extra_state_attributes["now_playing_liked"] == LIKED_STATE_UNKNOWN

    # Music Assistant attaches the exact Spotify track id; the key changes, so
    # a fresh lookup runs and flips the heart to liked.
    state.attributes[ATTR_MEDIA_CONTENT_ID] = "spotify://track/abc"
    sensor._sync_liked()
    run_scheduled()
    assert sensor.extra_state_attributes["now_playing_liked"] == LIKED_STATE_LIKED
