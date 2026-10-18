"""Tests for the Optoma Projector config flow."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.optoma_projector.const import CONF_MODEL, DOMAIN

from .conftest import HOST, URL, FakeProjector

NEW_UI_URL = f"https://{HOST}:8088/"
USER_INPUT = {CONF_HOST: f" {HOST} ", CONF_NAME: "Beamer", CONF_MODEL: "ZK708T"}


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return result["flow_id"]


async def test_user_flow_success(hass: HomeAssistant, projector: FakeProjector) -> None:
    """Test a successful user flow."""
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Beamer"
    assert result["data"][CONF_HOST] == HOST
    assert result["result"].unique_id == HOST


async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test cannot_connect, invalid_response and timeout errors."""
    flow_id = await _start(hass)
    aioclient_mock.get(NEW_UI_URL, exc=aiohttp.ClientConnectionError())

    for kwargs, error in (
        ({"exc": aiohttp.ClientConnectionError()}, "cannot_connect"),
        ({"exc": TimeoutError()}, "timeout"),
        ({"text": "<html>no data</html>"}, "invalid_response"),
    ):
        aioclient_mock.post(URL, **kwargs)
        result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": error}
        aioclient_mock.clear_requests()
        aioclient_mock.get(NEW_UI_URL, exc=aiohttp.ClientConnectionError())

    aioclient_mock.post(URL, text='{pw:"0"}')
    result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unsupported_model(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test projectors with the newer HTTPS web UI are reported as unsupported."""
    aioclient_mock.post(URL, exc=aiohttp.ClientConnectionError())
    aioclient_mock.get(NEW_UI_URL, text="<html>login</html>")

    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unsupported_model"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry, projector: FakeProjector
) -> None:
    """Test a host can only be configured once."""
    config_entry.add_to_hass(hass)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test changing the host updates data and unique ID."""
    new_host = "192.168.1.60"
    config_entry.add_to_hass(hass)
    aioclient_mock.post(f"http://{new_host}/form/control_cgi", text='{pw:"0"}')

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: new_host}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_HOST] == new_host
    assert config_entry.unique_id == new_host


async def test_reconfigure_to_existing_host(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Test reconfiguring to a host of another entry aborts."""
    other_host = "192.168.1.70"
    config_entry.add_to_hass(hass)
    MockConfigEntry(
        domain=DOMAIN, unique_id=other_host, data={CONF_HOST: other_host}
    ).add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: other_host}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == HOST
