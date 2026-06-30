"""Button entities for BToddB HA Music."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback

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
            MusicActionButton(
                controller,
                "find_like_matches",
                "find_like_matches",
                controller.async_find_like_matches,
                lambda: controller.like_enabled,
            ),
            MusicActionButton(
                controller,
                "confirm_like",
                "confirm_like",
                controller.async_confirm_like,
                lambda: (
                    controller.like_enabled
                    and controller.selected_like_candidate is not None
                ),
            ),
            MusicActionButton(
                controller,
                "cancel_like",
                "cancel_like",
                controller.async_cancel_like,
                lambda: controller.like_enabled and bool(controller.like_candidates),
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

    async def async_added_to_hass(self) -> None:
        """Refresh availability when the controller's state changes."""

        await super().async_added_to_hass()
        self.async_on_remove(self._controller.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        """Re-render so availability reflects the latest controller state."""

        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Run the button action."""

        await self._action()
