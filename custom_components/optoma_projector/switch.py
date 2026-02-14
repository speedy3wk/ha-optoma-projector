"""Switch platform for Optoma Projector."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OptomaConfigEntry
from .const import (
    KEY_POWER,
    POWER_STATE_ON,
    POWER_STATE_STANDBY,
    SWITCHES,
    VALUE_NOT_AVAILABLE,
)
from .coordinator import OptomaCoordinator
from .entity import OptomaEntity

# Limit concurrent platform updates (projector can only handle one request at a time)
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OptomaSwitchEntityDescription(SwitchEntityDescription):
    """Describes Optoma switch entity."""

    state_key: str
    command: str


SWITCH_DESCRIPTIONS: tuple[OptomaSwitchEntityDescription, ...] = tuple(
    OptomaSwitchEntityDescription(
        key=switch_id,
        translation_key=switch_id,
        state_key=state_key,
        command=command,
        entity_category=EntityCategory.CONFIG,
    )
    for switch_id, _name, state_key, command, _is_toggle in SWITCHES
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Optoma switches."""
    coordinator = entry.runtime_data

    entities: list[SwitchEntity] = [
        OptomaPowerSwitch(coordinator),
    ]

    # Add toggle switches using entity descriptions
    entities.extend(
        OptomaToggleSwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
    )

    async_add_entities(entities)


class OptomaPowerSwitch(OptomaEntity, SwitchEntity):
    """Power switch for Optoma projector."""

    _attr_name = None  # Use device name as entity name (main feature)

    def __init__(self, coordinator: OptomaCoordinator) -> None:
        """Initialize the power switch."""
        super().__init__(coordinator, "power")
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool:
        """Return true if projector is on."""
        # Use optimistic state if set and optimistic mode enabled
        if self._optimistic_state is not None and self.coordinator.optimistic:
            return self._optimistic_state
        # Use coordinator's is_on which handles warming state
        return self.coordinator.is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "power_state": self.coordinator.power_state,
            "is_warming": self.coordinator.is_warming,
            "is_cooling": self.coordinator.is_cooling,
            "can_accept_power_command": self.coordinator.can_accept_power_command,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the projector on."""
        # Check if we can accept the command
        if not self.coordinator.can_accept_power_command:
            return
        
        # Update optimistically for instant UI feedback
        if self.coordinator.optimistic:
            self._optimistic_state = True
            self.coordinator.update_optimistic(KEY_POWER, POWER_STATE_ON)
            self.async_write_ha_state()
        try:
            await self.coordinator.async_power_on()
        finally:
            # Clear optimistic state after command completes
            self._optimistic_state = None
            if self.coordinator.optimistic:
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the projector off."""
        # Check if projector is in transition
        if self.coordinator.is_in_transition:
            return
        
        # Update optimistically for instant UI feedback
        if self.coordinator.optimistic:
            self._optimistic_state = False
            self.coordinator.update_optimistic(KEY_POWER, POWER_STATE_STANDBY)
            self.async_write_ha_state()
        try:
            await self.coordinator.async_power_off()
        finally:
            # Clear optimistic state after command completes
            self._optimistic_state = None
            if self.coordinator.optimistic:
                self.async_write_ha_state()


class OptomaToggleSwitch(OptomaEntity, SwitchEntity):
    """Toggle switch for Optoma projector features."""

    entity_description: OptomaSwitchEntityDescription

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        description: OptomaSwitchEntityDescription,
    ) -> None:
        """Initialize the toggle switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._optimistic_state: bool | None = None
        self._command_in_progress: bool = False

    @property
    def available(self) -> bool:
        """Return if entity is available (only when projector is on)."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.is_on
            and self.coordinator.is_key_available(self.entity_description.state_key)
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if feature is enabled."""
        # Use optimistic state if set and optimistic mode enabled
        if self._optimistic_state is not None and self.coordinator.optimistic:
            return self._optimistic_state
        if self.coordinator.data:
            value = self.coordinator.data.get(self.entity_description.state_key)
            # 255 means "not available" - return None (unknown)
            if value == VALUE_NOT_AVAILABLE:
                return None
            return value == "1"
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the feature on."""
        # Prevent concurrent commands to same switch
        if self._command_in_progress:
            return
        
        self._command_in_progress = True
        try:
            # Update optimistically for instant UI feedback
            if self.coordinator.optimistic:
                self._optimistic_state = True
                self.coordinator.update_optimistic(self.entity_description.state_key, "1")
                self.async_write_ha_state()
            
            # Always send toggle command - let the projector handle the state
            await self.coordinator.async_toggle(self.entity_description.command)

            # Give the projector a moment, then refresh to sync state
            await asyncio.sleep(0.8)
            await self.coordinator.async_request_refresh()
        finally:
            # Clear optimistic state after command completes
            self._optimistic_state = None
            if self.coordinator.optimistic:
                self.async_write_ha_state()
            self._command_in_progress = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the feature off."""
        # Prevent concurrent commands to same switch
        if self._command_in_progress:
            return
        
        self._command_in_progress = True
        try:
            # Update optimistically for instant UI feedback
            if self.coordinator.optimistic:
                self._optimistic_state = False
                self.coordinator.update_optimistic(self.entity_description.state_key, "0")
                self.async_write_ha_state()
            
            # Always send toggle command - let the projector handle the state
            await self.coordinator.async_toggle(self.entity_description.command)

            # Give the projector a moment, then refresh to sync state
            await asyncio.sleep(0.8)
            await self.coordinator.async_request_refresh()
        finally:
            # Clear optimistic state after command completes
            self._optimistic_state = None
            if self.coordinator.optimistic:
                self.async_write_ha_state()
            self._command_in_progress = False
