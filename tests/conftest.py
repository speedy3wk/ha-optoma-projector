"""Fixtures for Optoma Projector tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.optoma_projector.const import (
    CONF_MODEL,
    DOMAIN,
    NUMBERS,
    SELECTS,
    SWITCHES,
)

HOST = "192.168.1.50"
URL = f"http://{HOST}/form/control_cgi"

_TOGGLES = {command.split("=")[0]: key for _, _, key, command, _ in SWITCHES} | {
    "mute": "j"
}
_PARAMS = {select[3]: select[2] for select in SELECTS} | {
    number[3]: number[2] for number in NUMBERS
}


def projector_text(state: dict[str, str]) -> str:
    """Render state in the projector's non-standard JSON format."""
    return "{" + ",".join(f'{key}:"{value}"' for key, value in state.items()) + "}"


class FakeProjector:
    """Emulates /form/control_cgi of an Optoma projector."""

    def __init__(self) -> None:
        """Initialize with a powered-on projector."""
        self.state: dict[str, str] = {
            "pw": "1",
            "a": "0",
            "m": "40",
            "j": "0",
            "F15": "0",
            "F0": "0",
            "b": "3",
            "c": "0",
            "F19": "255",
        }
        self.bodies: list[str] = []
        self.fail: Exception | None = None
        self.login_redirects = 0

    async def handle(
        self, method: str, url: Any, data: Any
    ) -> AiohttpClientMockResponse:
        """Handle a POST request."""
        body = data if isinstance(data, str) else str(data)
        self.bodies.append(body)
        if self.fail is not None:
            raise self.fail
        if self.login_redirects:
            self.login_redirects -= 1
            return AiohttpClientMockResponse(
                method, url, status=302, headers={"Location": "/login.htm"}
            )
        if body == "QueryInfo=QueryInfo":
            return AiohttpClientMockResponse(method, url, text="<html></html>")
        name, _, value = body.partition("=")
        before = dict(self.state)
        if name == "btn_powon":
            self.state["pw"] = "2"
            return AiohttpClientMockResponse(method, url, text=projector_text(before))
        if name == "btn_powoff":
            self.state["pw"] = "3"
            return AiohttpClientMockResponse(method, url, text=projector_text(before))
        if name in _TOGGLES:
            key = _TOGGLES[name]
            self.state[key] = "0" if self.state.get(key) == "1" else "1"
            # The real projector answers toggles with the pre-toggle state
            return AiohttpClientMockResponse(method, url, text=projector_text(before))
        if name in _PARAMS:
            self.state[_PARAMS[name]] = value
        return AiohttpClientMockResponse(method, url, text=projector_text(self.state))

    def count(self, body: str) -> int:
        """Return how often a body was sent."""
        return self.bodies.count(body)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


@pytest.fixture(autouse=True)
def fast_io() -> Generator[None]:
    """Remove artificial delays."""
    with (
        patch("custom_components.optoma_projector.coordinator.DEFAULT_RETRY_DELAY", 0),
        patch("custom_components.optoma_projector.coordinator.MIN_COMMAND_INTERVAL", 0),
    ):
        yield


@pytest.fixture
def projector(aioclient_mock: AiohttpClientMocker) -> FakeProjector:
    """Register the fake projector."""
    fake = FakeProjector()
    aioclient_mock.post(URL, side_effect=fake.handle)
    return fake


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Beamer",
        unique_id=HOST,
        data={CONF_HOST: HOST, CONF_NAME: "Beamer", CONF_MODEL: "ZK708T"},
        version=1,
        minor_version=2,
    )


async def setup_entry(
    hass: HomeAssistant, entry: MockConfigEntry, options: dict[str, Any] | None = None
) -> None:
    """Add and set up a config entry."""
    entry.add_to_hass(hass)
    if options:
        hass.config_entries.async_update_entry(entry, options=options)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
