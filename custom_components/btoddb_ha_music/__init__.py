"""BToddB HA Music integration."""

from __future__ import annotations

from dataclasses import dataclass, field

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_PLAYLIST,
    ATTR_SPEAKERS,
    ATTR_STATION,
    DOMAIN,
    PLATFORMS,
    SERVICE_PLAY_RADIO_STATION,
    SERVICE_SHUFFLE_PLAY_PLAYLIST,
    SERVICE_STOP_MUSIC,
)
from .controller import MusicController

type MusicConfigEntry = ConfigEntry[MusicController]

ATTR_CONFIG_ENTRY = "config_entry"


@dataclass(slots=True)
class MusicData:
    """Runtime data for the integration."""

    controllers: dict[str, MusicController] = field(default_factory=dict)
    services_registered: bool = False


async def async_setup_entry(hass: HomeAssistant, entry: MusicConfigEntry) -> bool:
    """Set up BToddB HA Music from a config entry."""

    controller = MusicController(hass, entry)
    entry.runtime_data = controller
    _async_data(hass).controllers[entry.entry_id] = controller

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MusicConfigEntry) -> bool:
    """Unload a BToddB HA Music config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = _async_data(hass)
        data.controllers.pop(entry.entry_id, None)
        if not data.controllers:
            _async_unregister_services(hass)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: MusicConfigEntry) -> None:
    """Reload the config entry after options change."""

    await hass.config_entries.async_reload(entry.entry_id)


def _async_data(hass: HomeAssistant) -> MusicData:
    """Return the integration runtime data."""

    return hass.data.setdefault(DOMAIN, MusicData())


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

    data = _async_data(hass)
    if data.services_registered:
        return

    async def play_radio_station(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_play_radio_station(
            station=call.data.get(ATTR_STATION),
            speakers=call.data.get(ATTR_SPEAKERS),
        )

    async def shuffle_play_playlist(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_shuffle_play_playlist(
            playlist=call.data.get(ATTR_PLAYLIST),
            speakers=call.data.get(ATTR_SPEAKERS),
        )

    async def stop_music(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_stop_music(speakers=call.data.get(ATTR_SPEAKERS))

    speaker_value = vol.Any(cv.string, vol.All(cv.ensure_list, [cv.string]))
    hass.services.async_register(
        DOMAIN,
        SERVICE_PLAY_RADIO_STATION,
        play_radio_station,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
                vol.Optional(ATTR_STATION): cv.string,
                vol.Optional(ATTR_SPEAKERS): speaker_value,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SHUFFLE_PLAY_PLAYLIST,
        shuffle_play_playlist,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
                vol.Optional(ATTR_PLAYLIST): cv.string,
                vol.Optional(ATTR_SPEAKERS): speaker_value,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_MUSIC,
        stop_music,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
                vol.Optional(ATTR_SPEAKERS): speaker_value,
            }
        ),
    )
    data.services_registered = True


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Remove integration services."""

    data = _async_data(hass)
    for service in (
        SERVICE_PLAY_RADIO_STATION,
        SERVICE_SHUFFLE_PLAY_PLAYLIST,
        SERVICE_STOP_MUSIC,
    ):
        hass.services.async_remove(DOMAIN, service)
    data.services_registered = False


def _controller_from_call(hass: HomeAssistant, call: ServiceCall) -> MusicController:
    """Resolve the target controller for a service call."""

    controllers = _async_data(hass).controllers
    entry_id = call.data.get(ATTR_CONFIG_ENTRY)
    if entry_id:
        if entry_id not in controllers:
            raise HomeAssistantError(f"Unknown BToddB HA Music entry: {entry_id}")
        return controllers[entry_id]
    if not controllers:
        raise HomeAssistantError("BToddB HA Music is not configured")
    return next(iter(controllers.values()))


__all__ = [
    "ATTR_CONFIG_ENTRY",
    "MusicConfigEntry",
]
