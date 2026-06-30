"""Data helpers for BToddB HA Music."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


type NamedMappingValue = str | list[str]
type NamedMapping = dict[str, NamedMappingValue]


class MappingParseError(ValueError):
    """Raised when a user-supplied mapping cannot be parsed."""


@dataclass(frozen=True, slots=True)
class NowPlaying:
    """Current media metadata for the selected speaker group."""

    state: str
    player_entity_id: str | None
    artist: str
    title: str
    album: str | None


@dataclass(frozen=True, slots=True)
class LikeCandidate:
    """A Spotify search result eligible to be saved to Liked Songs."""

    track_id: str
    uri: str
    label: str
    artist: str
    title: str
    album: str | None


def parse_named_mapping(raw: Any, *, allow_list_values: bool) -> NamedMapping:
    """Parse a JSON object into a name-to-value mapping."""

    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as err:
            raise MappingParseError(str(err)) from err
    else:
        parsed = raw

    if not isinstance(parsed, dict):
        raise MappingParseError("Expected a JSON object")

    mapping: NamedMapping = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not key.strip():
            raise MappingParseError("Every option name must be a non-empty string")

        option_name = key.strip()
        if isinstance(value, str) and value.strip():
            mapping[option_name] = value.strip()
            continue

        if allow_list_values and isinstance(value, list) and value:
            values: list[str] = []
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise MappingParseError(
                        f"{option_name} must only contain non-empty strings"
                    )
                values.append(item.strip())
            mapping[option_name] = values
            continue

        expected = "a non-empty string or string list"
        if not allow_list_values:
            expected = "a non-empty string"
        raise MappingParseError(f"{option_name} must be {expected}")

    return mapping


def mapping_to_json(mapping: NamedMapping) -> str:
    """Serialize a mapping for display in a config/options form."""

    return json.dumps(mapping, indent=2, sort_keys=True)
