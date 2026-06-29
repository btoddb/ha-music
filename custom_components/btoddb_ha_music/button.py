"""Button entities for BToddB HA Music."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.button import ButtonEntity

from . import MusicConfigEntry
from .controller import MusicController, MusicEntity


async def async_setup_entry(hass, entry: MusicConfigEntry, async_add_entities) -> None:
    """Set up music action buttons."""

    controller = entry.runtime_data
    async_add_entities(
        [
            MusicActionButton(
                controller,
                "play_radio_station",
                "play_radio_station",
                controller.async_play_radio_station,
                lambda: bool(controller.speakers and controller.radio_stations),
            ),
            MusicActionButton(
                controller,
                "shuffle_play_playlist",
                "shuffle_play_playlist",
                controller.async_shuffle_play_playlist,
                lambda: bool(controller.speakers and controller.playlists),
            ),
            MusicActionButton(
                controller,
                "stop_music",
                "stop_music",
                controller.async_stop_music,
                lambda: bool(controller.speakers),
            ),
        ]
    )


class MusicActionButton(MusicEntity, ButtonEntity):
    """Button that runs a music action."""

    def __init__(
        self,
        controller: MusicController,
        key: str,
        translation_key: str,
        action: Callable[[], Awaitable[None]],
        available: Callable[[], bool],
    ) -> None:
        """Initialize the button."""

        super().__init__(controller, key)
        self._attr_translation_key = translation_key
        self._action = action
        self._is_available = available

    @property
    def available(self) -> bool:
        """Return whether the button can run."""

        return self._is_available()

    async def async_press(self) -> None:
        """Run the button action."""

        await self._action()
