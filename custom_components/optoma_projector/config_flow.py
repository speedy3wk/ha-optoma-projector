"""Config flow for Optoma Projector integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
import voluptuous as vol

from .const import (
    CMD_QUERY,
    CONF_MODEL,
    CONF_OPTIMISTIC,
    CONF_PROJECTOR_ID,
    CONF_TELNET_FALLBACK,
    CONTROL_PATH,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_OPTIMISTIC,
    DEFAULT_PORT,
    DEFAULT_PROJECTOR_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TELNET_FALLBACK,
    DOMAIN,
    NEW_WEB_UI_PORT,
    NEW_WEB_UI_PROBE_TIMEOUT,
)
from .coordinator import REQUEST_HEADERS, parse_response

_LOGGER = logging.getLogger(__name__)


def _connection_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): (
                TextSelector(TextSelectorConfig())
            ),
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): (
                TextSelector(TextSelectorConfig())
            ),
            vol.Optional(CONF_MODEL, default=defaults.get(CONF_MODEL, DEFAULT_MODEL)): (
                TextSelector(TextSelectorConfig())
            ),
        }
    )


async def _async_has_new_web_ui(hass: HomeAssistant, host: str) -> bool:
    """Return True if the newer HTTPS web UI (port 8088) answers on this host."""
    session = async_get_clientsession(hass, verify_ssl=False)
    try:
        async with session.get(
            f"https://{host}:{NEW_WEB_UI_PORT}/",
            timeout=aiohttp.ClientTimeout(total=NEW_WEB_UI_PROBE_TIMEOUT),
            allow_redirects=False,
        ):
            return True
    except (TimeoutError, aiohttp.ClientError, OSError) as err:
        _LOGGER.debug("No HTTPS web UI on %s:%s: %s", host, NEW_WEB_UI_PORT, err)
        return False


async def validate_connection(hass: HomeAssistant, host: str) -> dict[str, str]:
    """Validate that the projector's web control interface answers."""
    error: str | None = None
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            f"http://{host}:{DEFAULT_PORT}{CONTROL_PATH}",
            data=CMD_QUERY,
            headers=REQUEST_HEADERS,
            timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=False,
        ) as response:
            text = await response.text()
    except TimeoutError:
        error = "timeout"
    except aiohttp.ClientError, OSError:
        error = "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected exception")
        return {"base": "unknown"}
    else:
        if parse_response(text) is None:
            error = "invalid_response"

    if error is None:
        return {}
    if await _async_has_new_web_ui(hass, host):
        _LOGGER.debug("%s runs the newer HTTPS web UI, which is not supported", host)
        return {"base": "unsupported_model"}
    return {"base": error}


class OptomaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Optoma Projector."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        """Get the options flow for this handler."""
        return OptomaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            # No stable hardware ID is available from the projector, so use the host
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            errors = await validate_connection(self.hass, user_input[CONF_HOST])
            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema({}), user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            if host != reconfigure_entry.data[CONF_HOST]:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()

            errors = await validate_connection(self.hass, host)
            if not errors:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    unique_id=host,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(
                user_input if user_input is not None else dict(reconfigure_entry.data)
            ),
            errors=errors,
        )


class OptomaOptionsFlow(OptionsFlowWithReload):
    """Handle options flow for Optoma Projector (auto-reloads on change)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_optimistic = self.config_entry.options.get(
            CONF_OPTIMISTIC, DEFAULT_OPTIMISTIC
        )
        current_telnet_fallback = self.config_entry.options.get(
            CONF_TELNET_FALLBACK, DEFAULT_TELNET_FALLBACK
        )
        current_projector_id = self.config_entry.options.get(
            CONF_PROJECTOR_ID, DEFAULT_PROJECTOR_ID
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=60,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Optional(
                        CONF_OPTIMISTIC,
                        default=current_optimistic,
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_TELNET_FALLBACK,
                        default=current_telnet_fallback,
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_PROJECTOR_ID,
                        default=current_projector_id,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=99,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
