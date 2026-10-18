"""Tests for the coordinator and entity behaviour."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import aiohttp
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.optoma_projector.const import (
    CONF_OPTIMISTIC,
    CONF_TELNET_FALLBACK,
    DOMAIN,
    TELNET_STATUS_STANDBY,
)
from custom_components.optoma_projector.coordinator import (
    TelnetClient,
    is_login_page,
    parse_response,
)

from .conftest import FakeProjector, setup_entry


def _entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str
) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def _fire_followup(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()


def test_parse_response() -> None:
    """Test parsing the non-standard JSON format."""
    assert parse_response('junk {pw:"1",a:"3",F19:"255"} junk') == {
        "pw": "1",
        "a": "3",
        "F19": "255",
    }
    assert parse_response("<html></html>") is None
    assert parse_response("{broken") is None
    assert is_login_page("<form>Login</form><input type=password>")
    assert not is_login_page('{pw:"1"}')


async def test_unavailable_after_consecutive_failures(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test single failed polls keep the last state."""
    await setup_entry(hass, config_entry)
    coordinator = config_entry.runtime_data
    entity_id = _entity_id(hass, config_entry, "media_player", "media_player")

    projector.fail = aiohttp.ClientConnectionError()
    for _ in range(2):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "on"

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    projector.fail = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"
    assert coordinator.consecutive_failures == 0


async def test_login_redirect_is_retried(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test a login redirect triggers a retry."""
    await setup_entry(hass, config_entry)
    coordinator = config_entry.runtime_data
    projector.login_redirects = 1
    projector.bodies.clear()

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert projector.count("QueryControl=QueryControl") == 2


async def test_power_off(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test power off sends the command and the follow-up refresh reads the state."""
    await setup_entry(hass, config_entry)
    media_player = _entity_id(hass, config_entry, "media_player", "media_player")
    power_state = _entity_id(hass, config_entry, "sensor", "power_state")

    await hass.services.async_call(
        "media_player", "turn_off", {ATTR_ENTITY_ID: media_player}, blocking=True
    )
    assert projector.count("btn_powoff=btn_powoff") == 1

    await _fire_followup(hass)
    assert hass.states.get(power_state).state == "cooling"
    assert hass.states.get(media_player).state == "off"

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "media_player", "turn_on", {ATTR_ENTITY_ID: media_player}, blocking=True
        )
    assert projector.count("btn_powon=btn_powon") == 0


async def test_power_off_optimistic(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test optimistic mode shows the transition immediately."""
    await setup_entry(hass, config_entry, {CONF_OPTIMISTIC: True})
    media_player = _entity_id(hass, config_entry, "media_player", "media_player")
    power_state = _entity_id(hass, config_entry, "sensor", "power_state")

    await hass.services.async_call(
        "media_player", "turn_off", {ATTR_ENTITY_ID: media_player}, blocking=True
    )

    assert projector.count("btn_powoff=btn_powoff") == 1
    assert hass.states.get(power_state).state == "cooling"


async def test_power_command_failure_rolls_back(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test a failed optimistic power command restores the previous state."""
    await setup_entry(hass, config_entry, {CONF_OPTIMISTIC: True})
    media_player = _entity_id(hass, config_entry, "media_player", "media_player")
    power_state = _entity_id(hass, config_entry, "sensor", "power_state")
    projector.fail = aiohttp.ClientConnectionError()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "media_player", "turn_off", {ATTR_ENTITY_ID: media_player}, blocking=True
        )

    assert projector.count("btn_powoff=btn_powoff") == 1
    assert hass.states.get(power_state).state == "on"


async def test_toggle_switch(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test toggles are idempotent and ignore the stale response."""
    await setup_entry(hass, config_entry)
    av_mute = _entity_id(hass, config_entry, "switch", "av_mute")
    assert hass.states.get(av_mute).state == "off"

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: av_mute}, blocking=True
    )
    assert projector.count("avmute=avmute") == 0

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: av_mute}, blocking=True
    )
    assert projector.count("avmute=avmute") == 1
    # Stale (pre-toggle) response must not be applied
    assert hass.states.get(av_mute).state == "off"

    # A repeated call before the state is confirmed must not toggle back
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: av_mute}, blocking=True
    )
    assert projector.count("avmute=avmute") == 1

    await _fire_followup(hass)
    assert hass.states.get(av_mute).state == "on"


async def test_toggle_not_retried_on_connection_error(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test toggles are sent only once when the connection fails."""
    await setup_entry(hass, config_entry)
    av_mute = _entity_id(hass, config_entry, "switch", "av_mute")
    projector.fail = TimeoutError()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch", "turn_on", {ATTR_ENTITY_ID: av_mute}, blocking=True
        )
    assert projector.count("avmute=avmute") == 1


async def test_set_value_is_retried(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test idempotent value commands are retried and applied."""
    await setup_entry(hass, config_entry)
    volume = _entity_id(hass, config_entry, "number", "volume")

    projector.fail = aiohttp.ClientConnectionError()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value", {ATTR_ENTITY_ID: volume, "value": 50}, blocking=True
        )
    assert projector.count("vol=50") == 2

    projector.fail = None
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: volume, "value": 55}, blocking=True
    )
    assert float(hass.states.get(volume).state) == 55


async def test_hour_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test hour sensors are unavailable without data."""
    await setup_entry(hass, config_entry)
    light = _entity_id(hass, config_entry, "sensor", "light_source_hours")
    filter_hours = _entity_id(hass, config_entry, "sensor", "filter_hours")
    assert hass.states.get(light).state == STATE_UNAVAILABLE
    assert hass.states.get(filter_hours).state == STATE_UNAVAILABLE

    projector.state["n"] = "1234"
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(light).state == "1234"


async def test_telnet_fallback_reads_power_state(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test the power state is read via Telnet when HTTP is down."""
    await setup_entry(hass, config_entry, {CONF_TELNET_FALLBACK: True})
    coordinator = config_entry.runtime_data
    power_state = _entity_id(hass, config_entry, "sensor", "power_state")
    av_mute = _entity_id(hass, config_entry, "switch", "av_mute")
    projector.fail = aiohttp.ClientConnectionError()

    with patch.object(
        TelnetClient, "get_power_status", return_value=TELNET_STATUS_STANDBY
    ):
        for _ in range(3):
            await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.last_update_success
    assert hass.states.get(power_state).state == "standby"
    assert hass.states.get(av_mute).state == STATE_UNAVAILABLE


async def test_toggle_back_before_confirmation(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test toggling back right away sends a second toggle."""
    await setup_entry(hass, config_entry)
    av_mute = _entity_id(hass, config_entry, "switch", "av_mute")

    for service in ("turn_on", "turn_off"):
        await hass.services.async_call(
            "switch", service, {ATTR_ENTITY_ID: av_mute}, blocking=True
        )
    assert projector.count("avmute=avmute") == 2

    await _fire_followup(hass)
    assert hass.states.get(av_mute).state == "off"
    assert projector.state["F15"] == "0"
