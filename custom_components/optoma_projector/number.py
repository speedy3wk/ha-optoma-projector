"""Number platform for Optoma Projector."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NUMBERS, VALUE_NOT_AVAILABLE
from .coordinator import OptomaConfigEntry, OptomaCoordinator
from .entity import OptomaPoweredEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OptomaNumberEntityDescription(NumberEntityDescription):
    """Describes Optoma number entity."""

    state_key: str
    param: str


def _build_number_descriptions() -> tuple[OptomaNumberEntityDescription, ...]:
    """Build number entity descriptions from const."""
    descriptions = []
    for number_id, _name, state_key, param, min_val, max_val, step, unit in NUMBERS:
        # Volume is a primary control, others are config
        entity_category = None if number_id == "volume" else EntityCategory.CONFIG

        descriptions.append(
            OptomaNumberEntityDescription(
                key=number_id,
                translation_key=number_id,
                state_key=state_key,
                param=param,
                native_min_value=min_val,
                native_max_value=max_val,
                native_step=step,
                native_unit_of_measurement=unit,
                entity_category=entity_category,
            )
        )
    return tuple(descriptions)


NUMBER_DESCRIPTIONS = _build_number_descriptions()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma numbers."""
    coordinator = entry.runtime_data

    async_add_entities(
        OptomaNumber(coordinator, description) for description in NUMBER_DESCRIPTIONS
    )


class OptomaNumber(OptomaPoweredEntity, NumberEntity):
    """Number entity for Optoma projector."""

    entity_description: OptomaNumberEntityDescription
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        description: OptomaNumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._state_key = description.state_key

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if self.coordinator.data:
            value = self.coordinator.data.get(self.entity_description.state_key)
            # 255 means "not available" for this field
            if value is not None and value != VALUE_NOT_AVAILABLE:
                try:
                    return float(value)
                except ValueError, TypeError:
                    return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value (HA already validates the min/max range)."""
        await self.coordinator.async_set_value(
            self.entity_description.param, int(value), state_key=self._state_key
        )
