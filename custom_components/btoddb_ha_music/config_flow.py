"""Config flow for BToddB HA Music."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_LIKE_PLAYLIST_ID,
    CONF_LIKE_SEARCH_LIMIT,
    CONF_PLAYLISTS,
    CONF_RADIO_STATIONS,
    CONF_SPEAKERS,
    CONF_SPOTIFY_ENTITY,
    DEFAULT_LIKE_SEARCH_LIMIT,
    DOMAIN,
    NAME,
    SPOTIFYPLUS_DOMAIN,
)
from .models import MappingParseError, mapping_to_json, parse_named_mapping


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BToddB HA Music."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""

        errors: dict[str, str] = {}
        if user_input is not None:
            parsed = _parse_form(user_input, errors)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=NAME, data=parsed)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""

        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Handle BToddB HA Music options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""

        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the integration options."""

        errors: dict[str, str] = {}
        if user_input is not None:
            parsed = _parse_form(user_input, errors)
            if not errors:
                return self.async_create_entry(title="", data=parsed)

        current = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or current),
            errors=errors,
        )


def _schema(values: dict[str, Any] | None = None) -> vol.Schema:
    """Build the shared setup/options schema."""

    values = values or {}
    text = selector.TextSelector(
        selector.TextSelectorConfig(
            multiline=True,
            type=selector.TextSelectorType.TEXT,
        )
    )
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_SPEAKERS,
            default=_default_json(values, CONF_SPEAKERS),
        ): text,
        vol.Required(
            CONF_RADIO_STATIONS,
            default=_default_json(values, CONF_RADIO_STATIONS),
        ): text,
        vol.Required(
            CONF_PLAYLISTS,
            default=_default_json(values, CONF_PLAYLISTS),
        ): text,
    }

    spotify_entity_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=MEDIA_PLAYER_DOMAIN, integration=SPOTIFYPLUS_DOMAIN
        )
    )
    current_spotify_entity = values.get(CONF_SPOTIFY_ENTITY)
    if current_spotify_entity:
        schema[vol.Optional(CONF_SPOTIFY_ENTITY, default=current_spotify_entity)] = (
            spotify_entity_selector
        )
    else:
        schema[vol.Optional(CONF_SPOTIFY_ENTITY)] = spotify_entity_selector

    schema[
        vol.Optional(
            CONF_LIKE_SEARCH_LIMIT,
            default=values.get(CONF_LIKE_SEARCH_LIMIT, DEFAULT_LIKE_SEARCH_LIMIT),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1, max=20, mode=selector.NumberSelectorMode.BOX
        )
    )

    like_playlist_selector = selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
    )
    current_like_playlist_id = values.get(CONF_LIKE_PLAYLIST_ID)
    if current_like_playlist_id:
        schema[
            vol.Optional(CONF_LIKE_PLAYLIST_ID, default=current_like_playlist_id)
        ] = like_playlist_selector
    else:
        schema[vol.Optional(CONF_LIKE_PLAYLIST_ID)] = like_playlist_selector

    return vol.Schema(schema)


def _default_json(values: dict[str, Any], key: str) -> str:
    """Return a JSON string default for a mapping field."""

    value = values.get(key, {})
    if isinstance(value, str):
        return value
    return mapping_to_json(value)


def _parse_form(user_input: dict[str, Any], errors: dict[str, str]) -> dict[str, Any]:
    """Parse and validate mappings from a config/options form."""

    parsed: dict[str, Any] = {}
    for key, allow_list_values in (
        (CONF_SPEAKERS, True),
        (CONF_RADIO_STATIONS, False),
        (CONF_PLAYLISTS, False),
    ):
        try:
            parsed[key] = parse_named_mapping(
                user_input.get(key), allow_list_values=allow_list_values
            )
        except MappingParseError:
            errors[key] = "invalid_mapping"

    spotify_entity = user_input.get(CONF_SPOTIFY_ENTITY)
    if spotify_entity:
        parsed[CONF_SPOTIFY_ENTITY] = spotify_entity
    parsed[CONF_LIKE_SEARCH_LIMIT] = int(
        user_input.get(CONF_LIKE_SEARCH_LIMIT, DEFAULT_LIKE_SEARCH_LIMIT)
    )
    like_playlist_id = user_input.get(CONF_LIKE_PLAYLIST_ID)
    if like_playlist_id:
        parsed[CONF_LIKE_PLAYLIST_ID] = like_playlist_id
    return parsed
