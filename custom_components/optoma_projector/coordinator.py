"""Data coordinator for Optoma Projector."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import json
import logging
import re
import time
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util.dt import utcnow

from .const import (
    CMD_POWER_OFF,
    CMD_POWER_ON,
    CMD_QUERY,
    CMD_QUERY_INFO,
    COMMAND_REFRESH_DELAY,
    CONTROL_PATH,
    COOKIE,
    DEFAULT_OPTIMISTIC,
    DEFAULT_PORT,
    DEFAULT_POWER_TIMEOUT,
    DEFAULT_PROJECTOR_ID,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STANDBY_SCAN_INTERVAL,
    DEFAULT_TELNET_FALLBACK,
    DEFAULT_TIMEOUT,
    DEFAULT_TRANSITION_SCAN_INTERVAL,
    DOMAIN,
    KEY_POWER,
    LOCK_TIMEOUT,
    MAX_CONSECUTIVE_FAILURES,
    MIN_COMMAND_INTERVAL,
    POWER_COMMAND_FAST_POLL,
    POWER_STATE_COOLING,
    POWER_STATE_ON,
    POWER_STATE_STANDBY,
    POWER_STATE_WARMING,
    POWER_STATES,
    TELNET_CMD_POWER_OFF,
    TELNET_CMD_POWER_ON,
    TELNET_CMD_POWER_STATUS,
    TELNET_COMMAND_DELAY,
    TELNET_PORT,
    TELNET_STATUS_COOLING,
    TELNET_STATUS_READY,
    TELNET_STATUS_STANDBY,
    TELNET_STATUS_WARMING,
    TELNET_TIMEOUT,
    VALUE_NOT_AVAILABLE,
)

_LOGGER = logging.getLogger(__name__)

type OptomaConfigEntry = ConfigEntry[OptomaCoordinator]

REQUEST_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Cookie": COOKIE,
}
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_UNQUOTED_KEY = re.compile(r"([,{])\s*([A-Za-z0-9_]+)\s*:")
_TELNET_STATUS_MAP = {
    TELNET_STATUS_STANDBY: POWER_STATE_STANDBY,
    TELNET_STATUS_WARMING: POWER_STATE_WARMING,
    TELNET_STATUS_COOLING: POWER_STATE_COOLING,
    TELNET_STATUS_READY: POWER_STATE_ON,
}


class OptomaError(Exception):
    """Base error for projector communication."""


class OptomaConnectionError(OptomaError):
    """Projector could not be reached or did not answer in time."""


class OptomaAuthError(OptomaError):
    """Projector answered with its login page; the command was not executed."""


def parse_response(text: str) -> dict[str, Any] | None:
    """Parse the projector's non-standard JSON (unquoted keys)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    json_str = _UNQUOTED_KEY.sub(r'\1"\2":', text[start : end + 1])
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as err:
        _LOGGER.debug("Failed to parse projector response: %s", err)
        return None
    return data if isinstance(data, dict) else None


def is_login_page(text: str) -> bool:
    """Return True if the response is the web UI login page."""
    lowered = text.lower()
    return "login" in lowered and "password" in lowered


class TelnetClient:
    """Telnet client for RS232 commands over TCP."""

    def __init__(
        self, host: str, port: int = TELNET_PORT, projector_id: int = 0
    ) -> None:
        """Initialize the Telnet client."""
        self.host = host
        self.port = port
        self.projector_id = projector_id
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> bool:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=TELNET_TIMEOUT
            )
        except (OSError, TimeoutError) as err:
            _LOGGER.debug("Telnet connection to %s failed: %s", self.host, err)
            return False
        _LOGGER.debug("Telnet connected to %s:%d", self.host, self.port)
        return True

    async def disconnect(self) -> None:
        """Disconnect from the projector."""
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass

    async def send_command(self, command_template: str) -> str | None:
        """Send a command and return the raw response."""
        async with self._lock:
            if (
                self._writer is None or self._writer.is_closing()
            ) and not await self._connect():
                return None
            assert self._reader is not None and self._writer is not None
            command = command_template.format(id=self.projector_id)
            _LOGGER.debug("Telnet sending: %s", command)
            try:
                self._writer.write(f"{command}\r".encode("ascii"))
                await self._writer.drain()
                await asyncio.sleep(TELNET_COMMAND_DELAY)
                response = await asyncio.wait_for(
                    self._reader.read(256), timeout=TELNET_TIMEOUT
                )
            except TimeoutError:
                _LOGGER.debug("Telnet read timeout")
                return None
            except OSError as err:
                _LOGGER.debug("Telnet command failed: %s", err)
                await self.disconnect()
                return None
            if not response:
                # Remote side closed the connection
                await self.disconnect()
                return None
            response_str = response.decode("ascii", errors="ignore").strip()
            _LOGGER.debug("Telnet response: %s", response_str)
            return response_str

    @staticmethod
    def is_success(response: str | None) -> bool:
        """Return True if a response line signals success ('P' or 'Ok...')."""
        if not response:
            return False
        return any(
            line.strip() == "P" or line.strip().upper().startswith("OK")
            for line in response.splitlines()
        )

    async def power_on(self) -> bool:
        """Send power on command."""
        return self.is_success(await self.send_command(TELNET_CMD_POWER_ON))

    async def power_off(self) -> bool:
        """Send power off command."""
        return self.is_success(await self.send_command(TELNET_CMD_POWER_OFF))

    async def get_power_status(self) -> int | None:
        """Return the raw power status code (e.g. 'Ok1' -> 1) or None."""
        response = await self.send_command(TELNET_CMD_POWER_STATUS)
        if response and (match := re.search(r"OK\s*(\d+)", response, re.IGNORECASE)):
            return int(match.group(1))
        return None


class OptomaCoordinator(TimestampDataUpdateCoordinator[dict[str, Any]]):
    """Coordinator owning all projector IO."""

    config_entry: OptomaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OptomaConfigEntry,
        host: str,
        name: str,
        model: str,
        port: int = DEFAULT_PORT,
        scan_interval: timedelta | None = None,
        optimistic: bool = DEFAULT_OPTIMISTIC,
        telnet_fallback: bool = DEFAULT_TELNET_FALLBACK,
        projector_id: int = DEFAULT_PROJECTOR_ID,
    ) -> None:
        """Initialize the coordinator."""
        self._normal_update_interval = scan_interval or timedelta(
            seconds=DEFAULT_SCAN_INTERVAL
        )
        self._transition_update_interval = timedelta(
            seconds=DEFAULT_TRANSITION_SCAN_INTERVAL
        )
        self._standby_update_interval = timedelta(seconds=DEFAULT_STANDBY_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            config_entry=config_entry,
            update_interval=self._normal_update_interval,
            always_update=False,
        )
        self.host = host
        self.port = port
        self.model = model
        self.optimistic = optimistic
        self.projector_id = projector_id
        self._url = f"http://{host}:{port}{CONTROL_PATH}"
        self._lock = asyncio.Lock()
        self._device_info: dict[str, str] = {}
        # Unsafe cookie jar is required for IP-based hosts; detached automatically on unload
        self._session = async_create_clientsession(
            hass, cookie_jar=aiohttp.CookieJar(unsafe=True)
        )
        self._telnet: TelnetClient | None = (
            TelnetClient(host, TELNET_PORT, projector_id) if telnet_fallback else None
        )
        self._last_command_time = 0.0
        self._consecutive_failures = 0
        self._fast_poll_until = 0.0
        self._unsub_followup_refresh: CALLBACK_TYPE | None = None
        # Toggle targets not yet confirmed by a poll: state_key -> (target, sent_at)
        self._pending_toggles: dict[str, tuple[bool, float]] = {}
        self._toggle_lock = asyncio.Lock()

    @property
    def telnet_fallback(self) -> bool:
        """Return True if the Telnet fallback is enabled."""
        return self._telnet is not None

    @property
    def consecutive_failures(self) -> int:
        """Return the number of consecutive failed polls."""
        return self._consecutive_failures

    async def _async_setup(self) -> None:
        """Fetch static device info once before the first refresh."""
        try:
            info = await self._async_send(CMD_QUERY_INFO, idempotent=False)
        except OptomaError as err:
            _LOGGER.debug("Could not fetch device info: %s", err)
            return
        if not info:
            return
        self._device_info = {
            key: str(value)
            for key, value in (
                ("model", info.get("model") or info.get("Model")),
                (
                    "firmware",
                    info.get("fw") or info.get("firmware") or info.get("Firmware"),
                ),
                ("mac", info.get("mac") or info.get("MAC") or info.get("macaddr")),
                ("serial", info.get("sn") or info.get("serial") or info.get("Serial")),
            )
            if value
        }
        _LOGGER.debug("Fetched device info: %s", self._device_info)

    async def async_shutdown(self) -> None:
        """Cancel pending work and close the Telnet connection."""
        if self._unsub_followup_refresh:
            self._unsub_followup_refresh()
            self._unsub_followup_refresh = None
        if self._telnet:
            await self._telnet.disconnect()
        await super().async_shutdown()

    # ------------------------------------------------------------------ state

    @property
    def is_on(self) -> bool:
        """Return True if projector is on (includes warming state)."""
        return self._power in (POWER_STATE_ON, POWER_STATE_WARMING)

    @property
    def power_state(self) -> str | None:
        """Return the current power state as string."""
        return POWER_STATES.get(self._power or "")

    @property
    def is_warming(self) -> bool:
        """Return True if projector is warming up."""
        return self._power == POWER_STATE_WARMING

    @property
    def is_cooling(self) -> bool:
        """Return True if projector is cooling down."""
        return self._power == POWER_STATE_COOLING

    @property
    def is_in_transition(self) -> bool:
        """Return True if projector is warming or cooling."""
        return self.is_warming or self.is_cooling

    @property
    def can_accept_power_command(self) -> bool:
        """Return True if projector can safely accept a power command."""
        return not self.is_in_transition

    @property
    def device_info_data(self) -> dict[str, str]:
        """Return cached device info."""
        return self._device_info

    @property
    def _power(self) -> str | None:
        return self.data.get(KEY_POWER) if self.data else None

    def is_key_available(self, key: str) -> bool:
        """Return True if key is present and not marked as not available."""
        if not self.data:
            return False
        value = self.data.get(key)
        return value is not None and value != VALUE_NOT_AVAILABLE

    # ---------------------------------------------------------------- polling

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the projector."""
        error: Exception | None = None
        poll_started = time.monotonic()
        try:
            data = await self._async_send(CMD_QUERY, idempotent=True)
        except OptomaError as err:
            data, error = None, err

        if data:
            # Toggles sent before this poll started are reflected in its data
            self._pending_toggles = {
                key: pending
                for key, pending in self._pending_toggles.items()
                if pending[1] >= poll_started
            }
        elif self._telnet:
            data = await self._async_telnet_power_data()

        if data:
            self._consecutive_failures = 0
            self._adjust_update_interval(data)
            return data

        self._consecutive_failures += 1
        if self.data and self._consecutive_failures < MAX_CONSECUTIVE_FAILURES:
            _LOGGER.debug(
                "Poll failed (%d/%d), keeping last state: %s",
                self._consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                error or "invalid response",
            )
            return self.data
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="update_failed",
            translation_placeholders={
                "host": self.host,
                "error": str(error or "invalid response"),
            },
        )

    async def _async_telnet_power_data(self) -> dict[str, Any] | None:
        """Return minimal state from the Telnet power status (deep standby)."""
        assert self._telnet is not None
        status = await self._telnet.get_power_status()
        if status is None:
            return None
        if (power := _TELNET_STATUS_MAP.get(status)) is None:
            _LOGGER.debug("Unknown Telnet power status: %s", status)
            return None
        _LOGGER.debug("HTTP unavailable, power state %s read via Telnet", power)
        return {**(self.data or {}), KEY_POWER: power}

    def _adjust_update_interval(self, data: dict[str, Any] | None) -> None:
        """Pick the polling interval matching the (new) power state."""
        power = data.get(KEY_POWER) if data else None
        if (
            power in (POWER_STATE_WARMING, POWER_STATE_COOLING)
            or time.monotonic() < self._fast_poll_until
        ):
            interval = self._transition_update_interval
        elif power == POWER_STATE_STANDBY:
            interval = self._standby_update_interval
        else:
            interval = self._normal_update_interval
        if self.update_interval != interval:
            _LOGGER.debug("Polling interval set to %s", interval)
            self.update_interval = interval

    @callback
    def async_set_updated_data(self, data: dict[str, Any]) -> None:
        """Set data and reschedule polling with the matching interval."""
        self._adjust_update_interval(data)
        super().async_set_updated_data(data)

    # --------------------------------------------------------------------- IO

    async def _async_request(self, body: str, timeout: float) -> dict[str, Any] | None:
        """Send one request (serialized and throttled); return parsed data."""
        try:
            async with asyncio.timeout(LOCK_TIMEOUT):
                await self._lock.acquire()
        except TimeoutError as err:
            raise OptomaConnectionError(
                "Timed out waiting for previous request"
            ) from err
        try:
            delay = MIN_COMMAND_INTERVAL - (time.monotonic() - self._last_command_time)
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                async with self._session.post(
                    self._url,
                    data=body,
                    headers=REQUEST_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=False,
                ) as response:
                    location = response.headers.get("Location", "")
                    if (
                        response.status in _REDIRECT_STATUSES
                        and "login" in location.lower()
                    ):
                        self._session.cookie_jar.clear()
                        raise OptomaAuthError("Redirected to login page")
                    text = await response.text()
            except TimeoutError as err:
                raise OptomaConnectionError(
                    f"Request timed out after {timeout}s"
                ) from err
            except (aiohttp.ClientError, OSError) as err:
                raise OptomaConnectionError(str(err) or type(err).__name__) from err
            finally:
                self._last_command_time = time.monotonic()
        finally:
            self._lock.release()

        if is_login_page(text):
            self._session.cookie_jar.clear()
            raise OptomaAuthError("Received login page")
        data = parse_response(text)
        if data is None:
            _LOGGER.debug("No parseable data in response to %s", body)
        return data

    async def _async_send(
        self, body: str, *, idempotent: bool, timeout: float = DEFAULT_TIMEOUT
    ) -> dict[str, Any] | None:
        """Send a request with retries.

        Connection errors are only retried for idempotent requests: a toggle that
        timed out may still have been executed and must not be sent twice.
        """
        last_error: OptomaError | None = None
        for attempt in range(DEFAULT_RETRIES):
            if attempt:
                await asyncio.sleep(DEFAULT_RETRY_DELAY)
            try:
                data = await self._async_request(body, timeout)
            except OptomaAuthError as err:
                last_error = err
                continue
            except OptomaConnectionError as err:
                last_error = err
                if not idempotent:
                    break
                _LOGGER.debug("Request failed (attempt %d): %s", attempt + 1, err)
                continue
            if data is not None or not idempotent:
                return data
            last_error = None
        if last_error is not None:
            raise last_error
        return None

    # --------------------------------------------------------------- commands

    async def async_send_command(
        self,
        body: str,
        *,
        idempotent: bool = False,
        optimistic: dict[str, str] | None = None,
        use_response: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Send a command; raise HomeAssistantError if the projector is unreachable.

        Toggle responses reflect the state *before* the toggle, so they must not be
        applied (use_response=False); a follow-up refresh reads the new state.
        """
        previous = self._apply_optimistic(optimistic)
        try:
            result = await self._async_send(
                body, idempotent=idempotent, timeout=timeout
            )
        except OptomaError as err:
            self._rollback_optimistic(previous)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if result and use_response and previous is None:
            self._set_confirmed_data(result)
        self._schedule_followup_refresh()

    async def async_set_value(
        self, param: str, value: str | int, *, state_key: str | None = None
    ) -> None:
        """Set a parameter (idempotent, safe to retry)."""
        await self.async_send_command(
            f"{param}={value}",
            idempotent=True,
            optimistic={state_key: str(value)} if state_key else None,
        )

    def toggle_state(self, state_key: str) -> bool | None:
        """Return the expected state of a toggle, including unconfirmed commands."""
        if (pending := self._pending_toggles.get(state_key)) is not None:
            return pending[0]
        if not self.is_key_available(state_key):
            return None
        return self.data[state_key] == "1"

    async def async_toggle(self, command: str, *, state_key: str, target: bool) -> None:
        """Toggle a feature into the target state (never retried).

        The projector only offers "toggle", so nothing is sent if the feature
        already is (or was just commanded) in the target state.
        """
        async with self._toggle_lock:
            if self.toggle_state(state_key) == target:
                return
            await self.async_send_command(
                command,
                optimistic={state_key: "1" if target else "0"},
                use_response=False,
            )
            self._pending_toggles[state_key] = (target, time.monotonic())

    async def async_power_on(self) -> None:
        """Turn the projector on."""
        if self.is_cooling:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="power_on_while_cooling"
            )
        if self.is_on:
            return
        await self._async_power(
            CMD_POWER_ON,
            self._telnet.power_on if self._telnet else None,
            POWER_STATE_WARMING,
        )

    async def async_power_off(self) -> None:
        """Turn the projector off."""
        if self.is_warming:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="power_off_while_warming"
            )
        if not self.is_on:
            return
        await self._async_power(
            CMD_POWER_OFF,
            self._telnet.power_off if self._telnet else None,
            POWER_STATE_COOLING,
        )

    async def _async_power(
        self,
        command: str,
        telnet_command: Callable[[], Awaitable[bool]] | None,
        transition_state: str,
    ) -> None:
        """Send a power command via HTTP with optional Telnet fallback."""
        self._fast_poll_until = time.monotonic() + POWER_COMMAND_FAST_POLL
        previous = self._apply_optimistic({KEY_POWER: transition_state})
        try:
            await self._async_send(
                command, idempotent=False, timeout=DEFAULT_POWER_TIMEOUT
            )
        except OptomaError as err:
            if telnet_command is not None:
                _LOGGER.info("HTTP power command failed (%s), trying Telnet", err)
                if await telnet_command():
                    self.async_set_updated_data(
                        {**(self.data or {}), KEY_POWER: transition_state}
                    )
                    self._schedule_followup_refresh()
                    return
            self._fast_poll_until = 0.0
            self._rollback_optimistic(previous)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        # The response still shows the old power state; switch to fast polling.
        self._adjust_update_interval(self.data)
        self._schedule_followup_refresh()

    # ------------------------------------------------------------- optimistic

    def _apply_optimistic(
        self, changes: dict[str, str] | None
    ) -> dict[str, Any] | None:
        """Apply optimistic values; return previous values for rollback."""
        if not changes or not self.optimistic or not self.last_update_success:
            return None
        data = self.data or {}
        previous = {key: data.get(key) for key in changes}
        self.async_set_updated_data({**data, **changes})
        return previous

    def _rollback_optimistic(self, previous: dict[str, Any] | None) -> None:
        if not previous or self.data is None:
            return
        data = dict(self.data)
        for key, value in previous.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        self.async_set_updated_data(data)

    def _set_confirmed_data(self, data: dict[str, Any]) -> None:
        self.last_update_success_time = utcnow()
        self.async_set_updated_data(data)

    def _schedule_followup_refresh(self) -> None:
        """Re-read state shortly after a command (responses can be stale)."""
        if self._unsub_followup_refresh:
            self._unsub_followup_refresh()
        self._unsub_followup_refresh = async_call_later(
            self.hass, COMMAND_REFRESH_DELAY, self._async_followup_refresh
        )

    async def _async_followup_refresh(self, _now: datetime) -> None:
        self._unsub_followup_refresh = None
        await self.async_request_refresh()
