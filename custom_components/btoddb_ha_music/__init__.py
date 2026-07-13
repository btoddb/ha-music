"""BToddB Music integration."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_MEDIA,
    ATTR_PLAYLIST,
    ATTR_SPEAKERS,
    ATTR_STATION,
    DOMAIN,
    PLATFORMS,
    SERVICE_CANCEL_LIKE,
    SERVICE_CONFIRM_LIKE,
    SERVICE_FIND_LIKE_MATCHES,
    SERVICE_NEXT_TRACK,
    SERVICE_PAUSE_MUSIC,
    SERVICE_PLAY_MUSIC,
    SERVICE_PLAY_RADIO_STATION,
    SERVICE_RESUME_MUSIC,
    SERVICE_SHUFFLE_PLAY_PLAYLIST,
    SERVICE_STOP_MUSIC,
)
from .controller import MusicController

type MusicConfigEntry = ConfigEntry[MusicController]

_LOGGER = logging.getLogger(__name__)

ATTR_CONFIG_ENTRY = "config_entry"

CARD_URL_BASE = f"/{DOMAIN}"
CARD_FILENAME = f"{DOMAIN}.js"
_CARD_STATIC_PATH_KEY = f"{DOMAIN}_card_static_path"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class MusicData:
    """Runtime data for the integration."""

    controllers: dict[str, MusicController] = field(default_factory=dict)
    services_registered: bool = False


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Lovelace card and serve static frontend assets."""
    await _async_register_card(hass)
    return True


def _card_digest(path: Path) -> str:
    """Return a short content hash for cache-busting the card bundle URL."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


async def _async_register_card(hass: HomeAssistant) -> None:
    """
    Make the card available to dashboards without manual resource setup.

    The card must be a Lovelace resource, not only an extra frontend module
    (add_extra_js_url): extra modules are baked into index.html at render time,
    and HA's service worker caches dashboard pages stale-while-revalidate. A
    page rendered while HA was still starting can miss the module import and
    keep showing "custom element doesn't exist" until caches turn over.
    Lovelace resources are fetched at dashboard load, and the content-hash query
    param busts stale HTTP/service-worker caches whenever the bundle changes.
    """
    www_dir = Path(__file__).parent / "www"
    if not hass.data.get(_CARD_STATIC_PATH_KEY):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(www_dir), cache_headers=False)]
        )
        hass.data[_CARD_STATIC_PATH_KEY] = True

    card_path = www_dir / CARD_FILENAME
    try:
        digest = await hass.async_add_executor_job(_card_digest, card_path)
    except OSError:
        _LOGGER.exception("Card bundle missing or unreadable: %s", card_path)
        return

    base_url = f"{CARD_URL_BASE}/{CARD_FILENAME}"
    url = f"{base_url}?v={digest}"

    resources = hass.data[LOVELACE_DATA].resources
    if not isinstance(resources, ResourceStorageCollection):
        # YAML-managed resources are read-only to integrations; keep the older
        # index-injected module fallback for that configuration.
        add_extra_js_url(hass, url)
        return

    await resources.async_get_info()
    for item in resources.async_items():
        if item["url"].partition("?")[0] == base_url:
            if item["url"] != url:
                await resources.async_update_item(item["id"], {"url": url})
            return
    await resources.async_create_item({"res_type": "module", "url": url})


async def async_setup_entry(hass: HomeAssistant, entry: MusicConfigEntry) -> bool:
    """Set up BToddB Music from a config entry."""

    controller = MusicController(hass, entry)
    entry.runtime_data = controller
    _async_data(hass).controllers[entry.entry_id] = controller

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MusicConfigEntry) -> bool:
    """Unload a BToddB Music config entry."""

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

    async def play_music(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_play_music(
            media=call.data.get(ATTR_MEDIA),
            speakers=call.data.get(ATTR_SPEAKERS),
        )

    async def stop_music(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_stop_music(speakers=call.data.get(ATTR_SPEAKERS))

    async def pause_music(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_pause_music(speakers=call.data.get(ATTR_SPEAKERS))

    async def resume_music(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_resume_music(speakers=call.data.get(ATTR_SPEAKERS))

    async def find_like_matches(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_find_like_matches()

    async def confirm_like(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_confirm_like()

    async def cancel_like(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_cancel_like()

    async def next_track(call: ServiceCall) -> None:
        controller = _controller_from_call(hass, call)
        await controller.async_next_track(speakers=call.data.get(ATTR_SPEAKERS))

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
        SERVICE_PLAY_MUSIC,
        play_music,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
                vol.Optional(ATTR_MEDIA): cv.string,
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_PAUSE_MUSIC,
        pause_music,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
                vol.Optional(ATTR_SPEAKERS): speaker_value,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESUME_MUSIC,
        resume_music,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
                vol.Optional(ATTR_SPEAKERS): speaker_value,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FIND_LIKE_MATCHES,
        find_like_matches,
        schema=vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIRM_LIKE,
        confirm_like,
        schema=vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_LIKE,
        cancel_like,
        schema=vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NEXT_TRACK,
        next_track,
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
        SERVICE_PLAY_MUSIC,
        SERVICE_PLAY_RADIO_STATION,
        SERVICE_SHUFFLE_PLAY_PLAYLIST,
        SERVICE_STOP_MUSIC,
        SERVICE_PAUSE_MUSIC,
        SERVICE_RESUME_MUSIC,
        SERVICE_FIND_LIKE_MATCHES,
        SERVICE_CONFIRM_LIKE,
        SERVICE_CANCEL_LIKE,
        SERVICE_NEXT_TRACK,
    ):
        hass.services.async_remove(DOMAIN, service)
    data.services_registered = False


def _controller_from_call(hass: HomeAssistant, call: ServiceCall) -> MusicController:
    """Resolve the target controller for a service call."""

    controllers = _async_data(hass).controllers
    entry_id = call.data.get(ATTR_CONFIG_ENTRY)
    if entry_id:
        if entry_id not in controllers:
            raise HomeAssistantError(f"Unknown BToddB Music entry: {entry_id}")
        return controllers[entry_id]
    if not controllers:
        raise HomeAssistantError("BToddB Music is not configured")
    return next(iter(controllers.values()))


__all__ = [
    "ATTR_CONFIG_ENTRY",
    "MusicConfigEntry",
]
