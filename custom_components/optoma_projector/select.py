"""Select platform for Optoma Projector."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OptomaConfigEntry
from .const import SELECTS, VALUE_NOT_AVAILABLE
from .coordinator import OptomaCoordinator
from .entity import OptomaEntity

# Limit concurrent platform updates (projector can only handle one request at a time)
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OptomaSelectEntityDescription(SelectEntityDescription):
    """Describes Optoma select entity."""

    state_key: str
    param: str
    options_map: dict[str, str]  # value -> label
    reverse_map: dict[str, str]  # label -> value


def _build_select_descriptions() -> tuple[OptomaSelectEntityDescription, ...]:
    """Build select entity descriptions from const."""
    descriptions = []
    for select_id, _name, state_key, param, options in SELECTS:
        options_map = {val: label for val, label in options}
        reverse_map = {label: val for val, label in options}
        option_labels = [label for _, label in options]

        # Input source is a primary control, others are config
        entity_category = None if select_id == "input_source" else EntityCategory.CONFIG

        descriptions.append(
            OptomaSelectEntityDescription(
                key=select_id,
                translation_key=select_id,
                state_key=state_key,
                param=param,
                options=option_labels,
                options_map=options_map,
                reverse_map=reverse_map,
                entity_category=entity_category,
            )
        )
    return tuple(descriptions)


SELECT_DESCRIPTIONS = _build_select_descriptions()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Optoma selects."""
    coordinator = entry.runtime_data

    async_add_entities(
        OptomaSelect(coordinator, description) for description in SELECT_DESCRIPTIONS
    )


class OptomaSelect(OptomaEntity, SelectEntity):
    """Select entity for Optoma projector."""

    entity_description: OptomaSelectEntityDescription

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        description: OptomaSelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_options = description.options

    @property
    def available(self) -> bool:
        """Return if entity is available (only when projector is on)."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.is_on
            and self.coordinator.is_key_available(self.entity_description.state_key)
        )

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        if self.coordinator.data:
            value = self.coordinator.data.get(self.entity_description.state_key)
            # 255 means "not available" for this field
            if value is not None and value != VALUE_NOT_AVAILABLE:
                return self.entity_description.options_map.get(str(value))
        return None

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        value = self.entity_description.reverse_map.get(option)
        if value is not None:
            await self.coordinator.async_set_value(self.entity_description.param, value)
