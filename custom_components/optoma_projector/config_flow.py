"""Config flow for Optoma Projector integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CMD_QUERY,
    CONF_MODEL,
    CONF_OPTIMISTIC,
    CONF_PROJECTOR_ID,
    CONF_TELNET_FALLBACK,
    CONTROL_PATH,
    COOKIE,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_OPTIMISTIC,
    DEFAULT_PORT,
    DEFAULT_PROJECTOR_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TELNET_FALLBACK,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(TextSelectorConfig()),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): TextSelector(
            TextSelectorConfig()
        ),
        vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): TextSelector(
            TextSelectorConfig()
        ),
    }
)


async def validate_connection(host: str) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    errors: dict[str, str] = {}

    try:
        # Use unsafe cookie jar for IP-based hosts
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        connector = aiohttp.TCPConnector(limit=1)
        async with aiohttp.ClientSession(
            cookie_jar=cookie_jar, connector=connector
        ) as session:
            url = f"http://{host}:{DEFAULT_PORT}{CONTROL_PATH}"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": COOKIE,
            }

            async with session.post(
                url,
                data=CMD_QUERY,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                text = await response.text()
                if "{" not in text or "}" not in text:
                    errors["base"] = "invalid_response"
    except TimeoutError:
        errors["base"] = "timeout"
    except aiohttp.ClientError:
        errors["base"] = "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected exception")
        errors["base"] = "unknown"

    return errors


class OptomaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Optoma Projector."""

    VERSION = 1

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
            # Use host as unique_id for now (will be updated to MAC if available)
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            # Validate connection
            errors = await validate_connection(user_input[CONF_HOST])

            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            # Validate new connection
            errors = await validate_connection(user_input[CONF_HOST])

            if not errors:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates=user_input,
                )

        # Pre-fill with current values
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=reconfigure_entry.data.get(CONF_HOST)
                    ): TextSelector(TextSelectorConfig()),
                    vol.Optional(
                        CONF_NAME,
                        default=reconfigure_entry.data.get(CONF_NAME, DEFAULT_NAME),
                    ): TextSelector(TextSelectorConfig()),
                    vol.Optional(
                        CONF_MODEL,
                        default=reconfigure_entry.data.get(CONF_MODEL, DEFAULT_MODEL),
                    ): TextSelector(TextSelectorConfig()),
                }
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
