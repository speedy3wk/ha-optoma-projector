"""Number platform for Optoma Projector."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OptomaConfigEntry
from .const import NUMBERS, VALUE_NOT_AVAILABLE
from .coordinator import OptomaCoordinator
from .entity import OptomaEntity

# Limit concurrent platform updates (projector can only handle one request at a time)
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
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Optoma numbers."""
    coordinator = entry.runtime_data

    async_add_entities(
        OptomaNumber(coordinator, description) for description in NUMBER_DESCRIPTIONS
    )


class OptomaNumber(OptomaEntity, NumberEntity):
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

    @property
    def available(self) -> bool:
        """Return if entity is available (only when projector is on)."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.is_on
            and self.coordinator.is_key_available(self.entity_description.state_key)
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if self.coordinator.data:
            value = self.coordinator.data.get(self.entity_description.state_key)
            # 255 means "not available" for this field
            if value is not None and value != VALUE_NOT_AVAILABLE:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value with validation."""
        # Clamp value to valid range
        min_val = self.entity_description.native_min_value
        max_val = self.entity_description.native_max_value
        
        if min_val is not None and value < min_val:
            value = min_val
        if max_val is not None and value > max_val:
            value = max_val
        
        await self.coordinator.async_set_value(
            self.entity_description.param,
            int(value),
            min_val=int(min_val) if min_val is not None else None,
            max_val=int(max_val) if max_val is not None else None,
        )
