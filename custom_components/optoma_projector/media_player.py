"""Media Player platform for Optoma Projector."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CMD_MUTE,
    DOMAIN,
    KEY_INPUT_SOURCE,
    KEY_MUTE,
    KEY_VOLUME,
    PARAM_SOURCE,
    PARAM_VOLUME,
    SELECTS,
    VALUE_NOT_AVAILABLE,
)
from .coordinator import OptomaConfigEntry, OptomaCoordinator
from .entity import OptomaEntity

PARALLEL_UPDATES = 1

SOURCE_VALUE_TO_NAME: dict[str, str] = next(
    dict(options)
    for select_id, _, _, _, options in SELECTS
    if select_id == "input_source"
)
SOURCE_NAME_TO_VALUE: dict[str, str] = {v: k for k, v in SOURCE_VALUE_TO_NAME.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma media player."""
    async_add_entities([OptomaMediaPlayer(entry.runtime_data)])


class OptomaMediaPlayer(OptomaEntity, MediaPlayerEntity):
    """Media Player entity for Optoma projector."""

    _attr_name = None
    _attr_volume_step = 0.05
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
    )

    def __init__(self, coordinator: OptomaCoordinator) -> None:
        """Initialize the media player."""
        super().__init__(coordinator, "media_player")
        # Main entity uses the device name
        self._attr_translation_key = None
        self._attr_source_list = list(SOURCE_NAME_TO_VALUE)

    def _value(self, key: str) -> str | None:
        if not self.coordinator.is_on or not self.coordinator.data:
            return None
        value = self.coordinator.data.get(key)
        return None if value in (None, VALUE_NOT_AVAILABLE) else str(value)

    @property
    def state(self) -> MediaPlayerState:
        """Return ON while on or warming up, OFF otherwise."""
        return MediaPlayerState.ON if self.coordinator.is_on else MediaPlayerState.OFF

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        if (value := self._value(KEY_INPUT_SOURCE)) is None:
            return None
        return SOURCE_VALUE_TO_NAME.get(value, f"Unknown ({value})")

    @property
    def volume_level(self) -> float | None:
        """Return volume level (0.0 to 1.0)."""
        try:
            return int(self._value(KEY_VOLUME)) / 100.0  # type: ignore[arg-type]
        except TypeError, ValueError:
            return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Return true if volume is muted."""
        if (value := self._value(KEY_MUTE)) is None:
            return None
        return value == "1"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs: dict[str, Any] = {"power_state": self.coordinator.power_state}
        if self.coordinator.is_warming:
            attrs["status"] = "warming_up"
        elif self.coordinator.is_cooling:
            attrs["status"] = "cooling_down"
        return attrs

    async def async_turn_on(self) -> None:
        """Turn the projector on."""
        await self.coordinator.async_power_on()

    async def async_turn_off(self) -> None:
        """Turn the projector off."""
        await self.coordinator.async_power_off()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        if (value := SOURCE_NAME_TO_VALUE.get(source)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_source",
                translation_placeholders={"source": source},
            )
        await self.coordinator.async_set_value(
            PARAM_SOURCE, value, state_key=KEY_INPUT_SOURCE
        )

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0.0 to 1.0)."""
        level = max(0, min(100, round(volume * 100)))
        await self.coordinator.async_set_value(
            PARAM_VOLUME, level, state_key=KEY_VOLUME
        )

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute/unmute volume (the projector only offers a toggle)."""
        await self.coordinator.async_toggle(CMD_MUTE, state_key=KEY_MUTE, target=mute)
