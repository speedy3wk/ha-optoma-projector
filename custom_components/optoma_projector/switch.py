"""Switch platform for Optoma Projector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SWITCHES, VALUE_NOT_AVAILABLE
from .coordinator import OptomaConfigEntry, OptomaCoordinator
from .entity import OptomaEntity, OptomaPoweredEntity

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
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [OptomaPowerSwitch(coordinator)]
    entities.extend(
        OptomaToggleSwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
    )
    async_add_entities(entities)


class OptomaPowerSwitch(OptomaEntity, SwitchEntity):
    """Power switch for Optoma projector."""

    def __init__(self, coordinator: OptomaCoordinator) -> None:
        """Initialize the power switch."""
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool:
        """Return true if projector is on (or warming up)."""
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
        await self.coordinator.async_power_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the projector off."""
        await self.coordinator.async_power_off()


class OptomaToggleSwitch(OptomaPoweredEntity, SwitchEntity):
    """Switch backed by a projector toggle command."""

    entity_description: OptomaSwitchEntityDescription

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        description: OptomaSwitchEntityDescription,
    ) -> None:
        """Initialize the toggle switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._state_key = description.state_key

    @property
    def is_on(self) -> bool | None:
        """Return true if feature is enabled."""
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self._state_key)
        if value is None or value == VALUE_NOT_AVAILABLE:
            return None
        return value == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the feature on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the feature off."""
        await self._async_set(False)

    async def _async_set(self, target: bool) -> None:
        await self.coordinator.async_toggle(
            self.entity_description.command, state_key=self._state_key, target=target
        )
