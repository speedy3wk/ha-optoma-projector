"""Media Player platform for Optoma Projector."""
from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OptomaConfigEntry
from .const import (
    KEY_INPUT_SOURCE,
    KEY_POWER,
    KEY_VOLUME,
    POWER_STATE_COOLING,
    POWER_STATE_ON,
    POWER_STATE_WARMING,
    SELECTS,
    VALUE_NOT_AVAILABLE,
)
from .coordinator import OptomaCoordinator
from .entity import OptomaEntity

# Limit concurrent platform updates (projector can only handle one request at a time)
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Optoma media player."""
    coordinator = entry.runtime_data
    async_add_entities([OptomaMediaPlayer(coordinator)])


# Build source mapping from SELECTS
def _get_source_mapping() -> tuple[dict[str, str], dict[str, str]]:
    """Get source value-to-name and name-to-value mappings."""
    value_to_name: dict[str, str] = {}
    name_to_value: dict[str, str] = {}

    for select_id, _name, state_key, _param, options in SELECTS:
        if select_id == "input_source":
            for value, label in options:
                value_to_name[value] = label
                name_to_value[label] = value
            break

    return value_to_name, name_to_value


SOURCE_VALUE_TO_NAME, SOURCE_NAME_TO_VALUE = _get_source_mapping()


class OptomaMediaPlayer(OptomaEntity, MediaPlayerEntity):
    """Media Player entity for Optoma projector."""

    _attr_name = None  # Use device name (this is the main entity)
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
        self._attr_unique_id = f"{coordinator.host}_media_player"
        # Remove translation key for main entity
        self._attr_translation_key = None
        # Optimistic state tracking
        self._optimistic_power: bool | None = None

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the projector."""
        # Use optimistic state if set and optimistic mode enabled
        if self._optimistic_power is not None and self.coordinator.optimistic:
            return MediaPlayerState.ON if self._optimistic_power else MediaPlayerState.OFF

        if not self.coordinator.data:
            return MediaPlayerState.OFF

        power = self.coordinator.data.get(KEY_POWER)
        if power == POWER_STATE_ON:
            return MediaPlayerState.ON
        elif power == POWER_STATE_WARMING:
            # Show as ON during warmup for better UX
            return MediaPlayerState.ON
        elif power == POWER_STATE_COOLING:
            # Show as OFF during cooldown
            return MediaPlayerState.OFF
        return MediaPlayerState.OFF

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        if self.coordinator.data:
            source_value = self.coordinator.data.get(KEY_INPUT_SOURCE)
            if source_value is not None:
                return SOURCE_VALUE_TO_NAME.get(source_value, f"Unknown ({source_value})")
        return None

    @property
    def source_list(self) -> list[str]:
        """Return the list of available input sources."""
        return list(SOURCE_NAME_TO_VALUE.keys())

    @property
    def volume_level(self) -> float | None:
        """Return volume level (0.0 to 1.0)."""
        if self.coordinator.data:
            volume = self.coordinator.data.get(KEY_VOLUME)
            # 255 means "not available"
            if volume is not None and volume != VALUE_NOT_AVAILABLE:
                try:
                    return int(volume) / 100.0
                except (ValueError, TypeError):
                    pass
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Return true if volume is muted."""
        if self.coordinator.data:
            # Key 'j' is audio mute in the Optoma protocol
            muted = self.coordinator.data.get("j")
            # 255 means "not available"
            if muted is not None and muted != VALUE_NOT_AVAILABLE:
                return muted == "1"
        return None

    async def async_turn_on(self) -> None:
        """Turn the projector on."""
        # Update optimistically for instant UI feedback
        if self.coordinator.optimistic:
            self._optimistic_power = True
            self.coordinator.update_optimistic(KEY_POWER, "1")
            self.async_write_ha_state()

        await self.coordinator.async_power_on()

        # Clear optimistic state after command completes
        self._optimistic_power = None

    async def async_turn_off(self) -> None:
        """Turn the projector off."""
        # Update optimistically for instant UI feedback
        if self.coordinator.optimistic:
            self._optimistic_power = False
            self.coordinator.update_optimistic(KEY_POWER, "0")
            self.async_write_ha_state()

        await self.coordinator.async_power_off()

        # Clear optimistic state after command completes
        self._optimistic_power = None

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        source_value = SOURCE_NAME_TO_VALUE.get(source)
        if source_value is not None:
            # Update optimistically for instant UI feedback
            if self.coordinator.optimistic:
                self.coordinator.update_optimistic(KEY_INPUT_SOURCE, source_value)
                self.async_write_ha_state()

            await self.coordinator.async_set_value("source", source_value)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0.0 to 1.0)."""
        volume_int = int(volume * 100)

        # Update optimistically for instant UI feedback
        if self.coordinator.optimistic:
            self.coordinator.update_optimistic(KEY_VOLUME, str(volume_int))
            self.async_write_ha_state()

        await self.coordinator.async_set_value("vol", volume_int)

    async def async_volume_up(self) -> None:
        """Increase volume."""
        if self.volume_level is not None:
            new_volume = min(1.0, self.volume_level + 0.05)
            await self.async_set_volume_level(new_volume)

    async def async_volume_down(self) -> None:
        """Decrease volume."""
        if self.volume_level is not None:
            new_volume = max(0.0, self.volume_level - 0.05)
            await self.async_set_volume_level(new_volume)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute/unmute volume."""
        current_mute = self.is_volume_muted
        # Only toggle if we know the current state and it differs from desired
        # If current_mute is None (unknown), we send the command anyway
        if current_mute is None or current_mute != mute:
            await self.coordinator.async_toggle("mute=mute")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs: dict[str, Any] = {
            "power_state": self.coordinator.power_state,
        }
        if self.coordinator.is_warming:
            attrs["status"] = "warming_up"
        elif self.coordinator.is_cooling:
            attrs["status"] = "cooling_down"
        return attrs
