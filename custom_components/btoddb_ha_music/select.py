"""Select entities for BToddB HA Music."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity

from . import MusicConfigEntry
from .controller import MusicController, MusicRestoreEntity


async def async_setup_entry(hass, entry: MusicConfigEntry, async_add_entities) -> None:
    """Set up the music select entities."""

    controller = entry.runtime_data
    async_add_entities(
        [
            MusicOptionSelect(
                controller,
                "speakers",
                "speaker_group",
                list(controller.speakers),
                controller.selected_speakers,
                controller.set_selected_speakers,
            ),
            MusicOptionSelect(
                controller,
                "radio_station",
                "radio_station",
                list(controller.radio_stations),
                controller.selected_radio_station,
                controller.set_selected_radio_station,
            ),
            MusicOptionSelect(
                controller,
                "playlist",
                "playlist",
                list(controller.playlists),
                controller.selected_playlist,
                controller.set_selected_playlist,
            ),
        ]
    )


class MusicOptionSelect(MusicRestoreEntity, SelectEntity):
    """Select a configured music option."""

    def __init__(
        self,
        controller: MusicController,
        key: str,
        translation_key: str,
        options: list[str],
        current_option: str | None,
        setter,
    ) -> None:
        """Initialize the select entity."""

        super().__init__(controller, key)
        self._attr_translation_key = translation_key
        self._attr_options = options
        self._current_option = current_option
        self._setter = setter

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""

        return self._current_option

    @property
    def available(self) -> bool:
        """Return whether any options are configured."""

        return bool(self.options)

    async def async_added_to_hass(self) -> None:
        """Restore the previous selected option if it still exists."""

        await super().async_added_to_hass()
        previous = await self.async_get_last_state()
        if previous and previous.state in self.options:
            self._current_option = previous.state
            self._setter(previous.state)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""

        self._setter(option)
        self._current_option = option
        self.async_write_ha_state()
