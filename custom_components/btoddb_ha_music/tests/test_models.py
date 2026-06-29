"""Tests for BToddB HA Music model helpers."""

from __future__ import annotations

import pytest

from custom_components.btoddb_ha_music.models import (
    MappingParseError,
    mapping_to_json,
    parse_named_mapping,
)


def test_parse_speaker_mapping_accepts_string_and_list_values() -> None:
    """Speaker mappings can target one media player or a group."""

    assert parse_named_mapping(
        '{"Kitchen": "media_player.kitchen", "Downstairs": ["media_player.kitchen", "media_player.living_room"]}',
        allow_list_values=True,
    ) == {
        "Kitchen": "media_player.kitchen",
        "Downstairs": ["media_player.kitchen", "media_player.living_room"],
    }


def test_parse_media_mapping_requires_string_values() -> None:
    """Radio stations and playlists resolve to one media content id."""

    with pytest.raises(MappingParseError):
        parse_named_mapping(
            '{"Morning": ["spotify:playlist:abc"]}', allow_list_values=False
        )


def test_parse_empty_mapping() -> None:
    """Empty form values are treated as empty mappings."""

    assert parse_named_mapping("", allow_list_values=False) == {}


def test_mapping_to_json_is_stable() -> None:
    """Mappings serialize predictably for options forms."""

    assert (
        mapping_to_json({"B": "two", "A": "one"}) == '{\n  "A": "one",\n  "B": "two"\n}'
    )
