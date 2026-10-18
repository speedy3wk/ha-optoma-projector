"""Tests for setup, unload and migration."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.optoma_projector.const import CONF_MODEL, DOMAIN

from .conftest import HOST, FakeProjector, setup_entry


async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test the entry sets up and unloads cleanly."""
    await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id(
        "media_player", DOMAIN, f"{config_entry.entry_id}_media_player"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "on"

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, config_entry.entry_id), config_entry.entry_id
    )
    assert device is not None

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_unreachable(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test setup is retried when the projector is unreachable."""
    projector.fail = aiohttp.ClientConnectionError()
    await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_migrate_unique_ids_to_entry_id(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    """Test host-based unique IDs and device identifiers are migrated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Beamer",
        unique_id=HOST,
        data={CONF_HOST: HOST, CONF_NAME: "Beamer", CONF_MODEL: "ZK708T"},
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, HOST)}
    )
    old = {
        ("media_player", "media_player"),
        ("switch", "av_mute"),
        ("sensor", "power_state"),
        ("select", "input_source"),
    }
    for domain, key in old:
        ent_reg.async_get_or_create(
            domain,
            DOMAIN,
            f"{HOST}_{key}",
            config_entry=entry,
            device_id=device.id,
        )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 2
    for domain, key in old:
        assert ent_reg.async_get_entity_id(domain, DOMAIN, f"{HOST}_{key}") is None
        assert (
            ent_reg.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
            is not None
        )
    migrated = dev_reg.async_get(device.id)
    assert migrated.identifiers == {(DOMAIN, entry.entry_id)}
