"""Data coordinator for Optoma Projector."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CMD_POWER_OFF,
    CMD_POWER_ON,
    CMD_QUERY,
    CMD_QUERY_INFO,
    CONF_PROJECTOR_ID,
    CONF_TELNET_FALLBACK,
    CONNECTION_LIMIT,
    CONNECTION_LIMIT_PER_HOST,
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
    MIN_COMMAND_INTERVAL,
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


class TelnetClient:
    """Telnet client for RS232 commands over TCP."""

    def __init__(self, host: str, port: int = TELNET_PORT, projector_id: int = 0) -> None:
        """Initialize the Telnet client."""
        self.host = host
        self.port = port
        self.projector_id = projector_id
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Connect to the projector via Telnet."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=TELNET_TIMEOUT
            )
            _LOGGER.debug("Telnet connected to %s:%d", self.host, self.port)
            return True
        except (OSError, TimeoutError) as err:
            _LOGGER.debug("Telnet connection failed: %s", err)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the projector."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            self._writer = None
            self._reader = None
            _LOGGER.debug("Telnet disconnected from %s", self.host)

    async def send_command(self, command_template: str) -> str | None:
        """Send a command and return the response."""
        async with self._lock:
            try:
                # Connect if not connected
                if not self._writer or self._writer.is_closing():
                    if not await self.connect():
                        return None

                # Format command with projector ID
                command = command_template.format(id=self.projector_id)
                _LOGGER.debug("Telnet sending: %s", command)

                # Send command with newline
                self._writer.write((command + "\r").encode("ascii"))
                await self._writer.drain()

                # Wait for response
                await asyncio.sleep(TELNET_COMMAND_DELAY)
                
                try:
                    response = await asyncio.wait_for(
                        self._reader.read(256),
                        timeout=TELNET_TIMEOUT
                    )
                    response_str = response.decode("ascii", errors="ignore").strip()
                    _LOGGER.debug("Telnet response: %s", response_str)
                    return response_str
                except TimeoutError:
                    _LOGGER.debug("Telnet read timeout")
                    return None

            except (OSError, ConnectionError) as err:
                _LOGGER.debug("Telnet command failed: %s", err)
                await self.disconnect()
                return None

    async def power_on(self) -> bool:
        """Send power on command."""
        response = await self.send_command(TELNET_CMD_POWER_ON)
        # Response should contain 'P' for pass or 'Ok' for success
        return response is not None and ("P" in response or "Ok" in response.lower())

    async def power_off(self) -> bool:
        """Send power off command."""
        response = await self.send_command(TELNET_CMD_POWER_OFF)
        return response is not None and ("P" in response or "Ok" in response.lower())

    async def get_power_status(self) -> int | None:
        """Get power status. Returns status code or None on error."""
        response = await self.send_command(TELNET_CMD_POWER_STATUS)
        if response:
            # Extract number from response (e.g., "Ok24" -> 24)
            match = re.search(r"(\d+)", response)
            if match:
                return int(match.group(1))
        return None


class OptomaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Optoma Projector data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        host: str,
        name: str,
        model: str = "UHD Laser",
        port: int = DEFAULT_PORT,
        scan_interval: timedelta | None = None,
        optimistic: bool = DEFAULT_OPTIMISTIC,
        telnet_fallback: bool = DEFAULT_TELNET_FALLBACK,
        projector_id: int = DEFAULT_PROJECTOR_ID,
    ) -> None:
        """Initialize the coordinator."""
        self._normal_update_interval = scan_interval or timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        self._transition_update_interval = timedelta(seconds=DEFAULT_TRANSITION_SCAN_INTERVAL)
        self._standby_update_interval = timedelta(seconds=DEFAULT_STANDBY_SCAN_INTERVAL)
        
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            config_entry=config_entry,
            update_interval=self._normal_update_interval,
            # Set always_update=False since projector state rarely changes
            always_update=False,
        )
        self.host = host
        self.port = port
        self.model = model
        self.optimistic = optimistic
        self.telnet_fallback = telnet_fallback
        self.projector_id = projector_id
        self._base_url = f"http://{host}:{port}"
        self._lock = asyncio.Lock()
        self._last_data: dict[str, Any] = {}
        # Device info fetched once
        self._device_info: dict[str, str] = {}
        self._device_info_fetched = False
        # Persistent session - created on first use
        self._session: aiohttp.ClientSession | None = None
        self._session_needs_refresh = False
        # Telnet client for fallback
        self._telnet: TelnetClient | None = None
        if telnet_fallback:
            self._telnet = TelnetClient(host, TELNET_PORT, projector_id)
        # Command throttling
        self._last_command_time: float = 0
        # Track consecutive failures for backoff
        self._consecutive_failures: int = 0
        self._max_consecutive_failures: int = 5

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create persistent HTTP session."""
        if self._session is None or self._session.closed or self._session_needs_refresh:
            # Close existing session if it needs refresh
            if self._session and not self._session.closed:
                await self._session.close()
            
            # Use unsafe=True to allow cookies for IP-based hosts (RFC 2109)
            cookie_jar = aiohttp.CookieJar(unsafe=True)
            # Configure TCP connector for connection pooling
            connector = aiohttp.TCPConnector(
                limit=CONNECTION_LIMIT,
                limit_per_host=CONNECTION_LIMIT_PER_HOST,
                # Enable TCP keepalive
                keepalive_timeout=30,
                # Allow connection reuse
                force_close=False,
                # Enable cleanup of closed connections
                enable_cleanup_closed=True,
            )
            # Create session with proper timeout configuration
            self._session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=cookie_jar,
                timeout=aiohttp.ClientTimeout(
                    total=DEFAULT_TIMEOUT,
                    connect=5,  # Connection timeout
                    sock_read=DEFAULT_TIMEOUT,  # Socket read timeout
                ),
            )
            self._session_needs_refresh = False
            _LOGGER.debug("Created new HTTP session for %s", self.host)
        return self._session

    async def _async_setup(self) -> None:
        """Set up the coordinator - called before first refresh.

        Fetch device info on startup to populate device registry.
        Errors here will not prevent integration from loading.
        """
        await self._fetch_device_info()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            _LOGGER.debug("Closed HTTP session for %s", self.host)
        # Close Telnet connection
        if self._telnet:
            await self._telnet.disconnect()
            _LOGGER.debug("Closed Telnet connection for %s", self.host)
        await super().async_shutdown()

    @property
    def is_on(self) -> bool:
        """Return True if projector is on (includes warming state)."""
        if not self.data:
            return False
        power = self.data.get(KEY_POWER)
        return power in (POWER_STATE_ON, POWER_STATE_WARMING)

    @property
    def power_state(self) -> str:
        """Return the current power state as string."""
        if not self.data:
            return "unknown"
        power = self.data.get(KEY_POWER)
        return POWER_STATES.get(power, "unknown")

    @property
    def is_warming(self) -> bool:
        """Return True if projector is warming up."""
        return self.data.get(KEY_POWER) == POWER_STATE_WARMING if self.data else False

    @property
    def is_cooling(self) -> bool:
        """Return True if projector is cooling down."""
        return self.data.get(KEY_POWER) == POWER_STATE_COOLING if self.data else False

    @property
    def is_in_transition(self) -> bool:
        """Return True if projector is warming or cooling."""
        return self.is_warming or self.is_cooling

    @property
    def can_accept_power_command(self) -> bool:
        """Return True if projector can safely accept a power command.
        
        Relies on the projector's reported state - it knows best when it's ready.
        Laser projectors don't need artificial cooling timers.
        """
        # Don't send power commands during warming/cooling
        return not self.is_in_transition

    @property
    def device_info_data(self) -> dict[str, str]:
        """Return cached device info."""
        return self._device_info

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the projector."""
        # Adjust polling interval based on projector state
        self._adjust_update_interval()
        
        try:
            data = await self._send_command_with_retry(CMD_QUERY)
            if data:
                self._last_data = data
                self._consecutive_failures = 0  # Reset failure counter on success
                return data
            # Return last known data on empty response
            if self._last_data:
                _LOGGER.debug("Empty response, using cached data")
                return self._last_data
            raise UpdateFailed("Empty response from projector")
        except aiohttp.ClientError as err:
            self._consecutive_failures += 1
            _LOGGER.debug(
                "Error fetching projector data (failure %d/%d): %s",
                self._consecutive_failures,
                self._max_consecutive_failures,
                err,
            )
            if self._last_data:
                return self._last_data
            raise UpdateFailed(f"Error communicating with projector: {err}") from err
        except TimeoutError as err:
            self._consecutive_failures += 1
            _LOGGER.debug(
                "Timeout fetching projector data (failure %d/%d): %s",
                self._consecutive_failures,
                self._max_consecutive_failures,
                err,
            )
            if self._last_data:
                return self._last_data
            raise UpdateFailed("Timeout communicating with projector") from err

    def _adjust_update_interval(self) -> None:
        """Adjust update interval based on projector state."""
        if self.is_in_transition:
            # Poll faster during warming/cooling to catch state changes
            if self.update_interval != self._transition_update_interval:
                self.update_interval = self._transition_update_interval
                _LOGGER.debug("Increased polling rate during transition")
        elif self.data and self.data.get(KEY_POWER) == POWER_STATE_STANDBY:
            # Slow polling in standby to reduce load
            if self.update_interval != self._standby_update_interval:
                self.update_interval = self._standby_update_interval
                _LOGGER.debug("Reduced polling rate in standby")
        else:
            # Normal polling rate
            if self.update_interval != self._normal_update_interval:
                self.update_interval = self._normal_update_interval
                _LOGGER.debug("Restored normal polling rate")

    async def _fetch_device_info(self) -> None:
        """Fetch device information from projector (model, firmware, MAC)."""
        try:
            # Try to get info from projector's info endpoint
            info = await self._send_command(CMD_QUERY_INFO)
            if info:
                self._device_info = {
                    "model": info.get("model", info.get("Model", "")),
                    "firmware": info.get("fw", info.get("firmware", info.get("Firmware", ""))),
                    "mac": info.get("mac", info.get("MAC", info.get("macaddr", ""))),
                    "serial": info.get("sn", info.get("serial", info.get("Serial", ""))),
                }
                self._device_info_fetched = True
                _LOGGER.debug("Fetched device info: %s", self._device_info)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not fetch device info: %s", err)
            # Not critical, continue without device info
            self._device_info_fetched = True

    async def _send_command_with_retry(
        self,
        body: str,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> dict[str, Any] | None:
        """Send command with retry mechanism."""
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                result = await self._send_command(body, timeout)
                if result is not None:
                    return result
                # Empty result, retry after delay
                if attempt < retries - 1:
                    _LOGGER.debug(
                        "Empty response, retrying (%d/%d)", attempt + 1, retries
                    )
                    await asyncio.sleep(DEFAULT_RETRY_DELAY)
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                last_error = err
                # Mark session for refresh on connection errors
                if isinstance(err, (aiohttp.ClientConnectorError, OSError)):
                    self._session_needs_refresh = True
                if attempt < retries - 1:
                    _LOGGER.debug(
                        "Request failed, retrying (%d/%d): %s",
                        attempt + 1,
                        retries,
                        err,
                    )
                    await asyncio.sleep(DEFAULT_RETRY_DELAY)

        if last_error:
            _LOGGER.warning(
                "Failed after %d attempts: %s", retries, last_error
            )
        return None

    async def _send_command(
        self, body: str, timeout: int = DEFAULT_TIMEOUT
    ) -> dict[str, Any] | None:
        """Send a command to the projector and return parsed response."""
        # Enforce minimum delay between commands
        await self._throttle_command()
        
        try:
            async with asyncio.timeout(LOCK_TIMEOUT):
                async with self._lock:
                    try:
                        session = await self._get_session()
                        headers = {
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Cookie": COOKIE,
                        }
                        url = f"{self._base_url}{CONTROL_PATH}"

                        async with session.post(
                            url,
                            data=body,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=timeout),
                            allow_redirects=False,  # Detect login redirects
                        ) as response:
                            # Check for redirect to login page (session expired)
                            if response.status in (301, 302, 303, 307, 308):
                                location = response.headers.get("Location", "")
                                if "login" in location.lower():
                                    _LOGGER.debug("Session expired, will refresh on next request")
                                    self._session_needs_refresh = True
                                    return None
                            
                            text = await response.text()
                            
                            # Check if response contains login page HTML
                            if "login" in text.lower() and "password" in text.lower():
                                _LOGGER.debug("Got login page, session may have expired")
                                self._session_needs_refresh = True
                                return None
                            
                            return self._parse_response(text)
                    except asyncio.TimeoutError:
                        _LOGGER.debug("Timeout communicating with projector at %s", self.host)
                        raise TimeoutError("Request timeout") from None
                    except aiohttp.ClientError as err:
                        _LOGGER.debug("Error communicating with projector: %s", err)
                        raise
                    except OSError as err:
                        # Handle low-level network errors (connection refused, etc.)
                        _LOGGER.debug("Network error communicating with projector: %s", err)
                        self._session_needs_refresh = True
                        raise
        except asyncio.TimeoutError:
            _LOGGER.warning("Lock acquisition timeout for projector at %s", self.host)
            raise TimeoutError("Lock acquisition timeout") from None

    async def _throttle_command(self) -> None:
        """Ensure minimum delay between commands to prevent overwhelming projector."""
        now = time.monotonic()
        elapsed = now - self._last_command_time
        if elapsed < MIN_COMMAND_INTERVAL:
            delay = MIN_COMMAND_INTERVAL - elapsed
            await asyncio.sleep(delay)
        self._last_command_time = time.monotonic()

    async def _recreate_session(self) -> None:
        """Mark session for refresh (actual refresh happens on next request)."""
        self._session_needs_refresh = True
        _LOGGER.debug("Session marked for refresh for %s", self.host)

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        """Parse the projector response JSON."""
        # Find JSON in response
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            _LOGGER.debug("No JSON found in response")
            return None

        json_str = text[start : end + 1]
        # Fix unquoted keys (projector returns non-standard JSON)
        json_str = re.sub(r"([,{])\s*([A-Za-z0-9_]+)\s*:", r'\1"\2":', json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as err:
            _LOGGER.warning("Failed to parse projector response: %s", err)
            return None

    async def async_send_command(
        self, body: str, timeout: int = DEFAULT_TIMEOUT
    ) -> bool:
        """Send a command to the projector.
        
        Returns True if command was successful, False otherwise.
        Updates coordinator data with response if available.
        """
        result = await self._send_command_with_retry(body, timeout=timeout)
        if result:
            # Update coordinator data with response
            self._last_data = result
            self.async_set_updated_data(result)
            return True
        # Command failed but we don't have updated state
        # Schedule a refresh to get current state
        await self.async_request_refresh()
        return False

    async def async_power_on(self) -> bool:
        """Turn the projector on."""
        # Check projector's reported state
        if self.is_cooling:
            _LOGGER.info("Cannot power on: projector is still cooling down")
            return False
        if self.is_warming or self.is_on:
            _LOGGER.debug("Projector is already on or warming up")
            return True  # Not an error, just already in desired state
        
        # Try HTTP first
        success = await self.async_send_command(CMD_POWER_ON, timeout=DEFAULT_POWER_TIMEOUT)
        
        # Fallback to Telnet if HTTP failed and fallback is enabled
        if not success and self._telnet:
            _LOGGER.info("HTTP power on failed, trying Telnet fallback...")
            success = await self._telnet.power_on()
            if success:
                _LOGGER.info("Telnet power on successful")
                # Update state optimistically since Telnet doesn't return full state
                self.update_optimistic(KEY_POWER, POWER_STATE_WARMING)
        
        if success:
            # Speed up polling to catch state changes
            self.update_interval = self._transition_update_interval
        
        return success

    async def async_power_off(self) -> bool:
        """Turn the projector off."""
        # Check projector's reported state
        if self.is_warming:
            _LOGGER.info("Cannot power off: projector is still warming up")
            return False
        if self.is_cooling or not self.is_on:
            _LOGGER.debug("Projector is already off or cooling down")
            return True  # Not an error, just already in desired state
        
        # Try HTTP first
        success = await self.async_send_command(CMD_POWER_OFF, timeout=DEFAULT_POWER_TIMEOUT)
        
        # Fallback to Telnet if HTTP failed and fallback is enabled
        if not success and self._telnet:
            _LOGGER.info("HTTP power off failed, trying Telnet fallback...")
            success = await self._telnet.power_off()
            if success:
                _LOGGER.info("Telnet power off successful")
                # Update state optimistically since Telnet doesn't return full state
                self.update_optimistic(KEY_POWER, POWER_STATE_COOLING)
        
        if success:
            # Speed up polling to catch state changes
            self.update_interval = self._transition_update_interval
        
        return success

    async def async_get_power_status_telnet(self) -> str | None:
        """Get power status via Telnet (for diagnostics or when HTTP fails)."""
        if not self._telnet:
            return None
        
        status = await self._telnet.get_power_status()
        if status is None:
            return None
        
        # Map Telnet status codes to our power states
        if status == TELNET_STATUS_STANDBY:
            return POWER_STATE_STANDBY
        elif status == TELNET_STATUS_WARMING:
            return POWER_STATE_WARMING
        elif status == TELNET_STATUS_COOLING:
            return POWER_STATE_COOLING
        elif status == TELNET_STATUS_READY:
            return POWER_STATE_ON
        else:
            _LOGGER.debug("Unknown Telnet power status: %d", status)
            return None

    async def async_set_value(
        self,
        param: str,
        value: str | int,
        min_val: int | None = None,
        max_val: int | None = None,
    ) -> bool:
        """Set a parameter value with optional validation."""
        # Validate numeric values if bounds provided
        if isinstance(value, (int, float)) and (min_val is not None or max_val is not None):
            if min_val is not None and value < min_val:
                _LOGGER.warning(
                    "Value %s for %s is below minimum %s, clamping",
                    value, param, min_val
                )
                value = min_val
            if max_val is not None and value > max_val:
                _LOGGER.warning(
                    "Value %s for %s is above maximum %s, clamping",
                    value, param, max_val
                )
                value = max_val
        
        body = f"{param}={value}"
        return await self.async_send_command(body)

    async def async_toggle(self, command: str) -> bool:
        """Toggle a setting."""
        return await self.async_send_command(command)

    def update_optimistic(self, key: str, value: Any) -> None:
        """Update data optimistically (before server confirms)."""
        if self.optimistic:
            new_data = dict(self._last_data)
            new_data[key] = value
            self._last_data = new_data
            self.async_set_updated_data(new_data)

    def is_key_available(self, key: str) -> bool:
        """Return True if key is present and not marked as not available."""
        if not self.data:
            return False
        value = self.data.get(key)
        if value is None:
            return False
        return value != VALUE_NOT_AVAILABLE
