"""Button platform for Optoma Projector."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BUTTONS
from .coordinator import OptomaConfigEntry, OptomaCoordinator
from .entity import OptomaPoweredEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OptomaButtonEntityDescription(ButtonEntityDescription):
    """Describes Optoma button entity."""

    command: str


BUTTON_DESCRIPTIONS: tuple[OptomaButtonEntityDescription, ...] = tuple(
    OptomaButtonEntityDescription(
        key=button_id,
        translation_key=button_id,
        command=command,
        entity_category=EntityCategory.CONFIG,
    )
    for button_id, _name, command in BUTTONS
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma buttons."""
    coordinator = entry.runtime_data

    async_add_entities(
        OptomaButton(coordinator, description) for description in BUTTON_DESCRIPTIONS
    )


class OptomaButton(OptomaPoweredEntity, ButtonEntity):
    """Button entity for Optoma projector."""

    entity_description: OptomaButtonEntityDescription

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        description: OptomaButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_send_command(self.entity_description.command)
