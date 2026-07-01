"""Select entities for BToddB HA Music."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback

from . import MusicConfigEntry
from .controller import MusicController, MusicEntity, MusicRestoreEntity


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
            LikeCandidateSelect(controller),
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


class LikeCandidateSelect(MusicEntity, SelectEntity):
    """Select which Spotify search match to save as a Liked Song."""

    _attr_translation_key = "like_candidate"

    def __init__(self, controller: MusicController) -> None:
        """Initialize the like candidate select."""

        super().__init__(controller, "like_candidate")

    @property
    def options(self) -> list[str]:
        """Return the labels of the current search matches."""

        return [candidate.label for candidate in self._controller.like_candidates]

    @property
    def current_option(self) -> str | None:
        """Return the label of the selected candidate."""

        candidate = self._controller.selected_like_candidate
        return candidate.label if candidate else None

    @property
    def available(self) -> bool:
        """Return whether there are any candidates to choose from."""

        return bool(self.options)

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller changes so options stay in sync."""

        await super().async_added_to_hass()
        self.async_on_remove(self._controller.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        """Re-render when the candidate list or selection changes."""

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose structured candidate data for the Lovelace card."""

        return {
            "candidates": [
                {
                    "label": c.label,
                    "artist": c.artist,
                    "title": c.title,
                    "album": c.album,
                }
                for c in self._controller.like_candidates
            ]
        }

    async def async_select_option(self, option: str) -> None:
        """Select a candidate by its label."""

        self._controller.set_selected_like_candidate(option)
