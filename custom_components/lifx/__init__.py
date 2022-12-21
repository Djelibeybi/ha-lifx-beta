"""Support for LIFX."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import socket

from aiolifx.connection import LIFXConnection
import voluptuous as vol

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_call_later

from .const import DATA_LIFX_CONNECT, DATA_LIFX_MANAGER, DOMAIN, TARGET_ANY
from .coordinator import LIFXUpdateCoordinator
from .discovery import LIFXConnectivityManager
from .manager import LIFXManager

CONF_SERVER = "server"
CONF_BROADCAST = "broadcast"


INTERFACE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SERVER): cv.string,
        vol.Optional(CONF_PORT): cv.port,
        vol.Optional(CONF_BROADCAST): cv.string,
    }
)

CONFIG_SCHEMA = vol.All(
    cv.deprecated(DOMAIN),
    vol.Schema(
        {
            DOMAIN: {
                LIGHT_DOMAIN: vol.Schema(vol.All(cv.ensure_list, [INTERFACE_SCHEMA]))
            }
        },
        extra=vol.ALLOW_EXTRA,
    ),
)


PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
]


DISCOVERY_COOLDOWN = 5


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LIFX from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    assert entry.unique_id is not None
    domain_data = hass.data[DOMAIN]

    @callback
    def _async_delay_discovery(_: datetime) -> None:
        """
        Start an untracked task to discover devices.

        We do not want the discovery task to block startup.
        """
        task = asyncio.create_task(connect.async_start_discovery())

        @callback
        def _async_stop(_: Event) -> None:
            if not task.done():
                connect.stop_discovery()
                task.cancel()

        # Task must be shut down when home assistant is closing
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)

    if DATA_LIFX_MANAGER not in domain_data:
        manager = LIFXManager(hass)
        domain_data[DATA_LIFX_MANAGER] = manager
        manager.async_setup()

    connect = LIFXConnectivityManager(hass)
    domain_data[DATA_LIFX_CONNECT] = connect

    async_call_later(
        hass, timedelta(seconds=DISCOVERY_COOLDOWN), _async_delay_discovery
    )

    host = entry.data[CONF_HOST]
    connection = LIFXConnection(host, TARGET_ANY)
    try:
        await connection.async_setup()
    except socket.gaierror as ex:
        connection.async_stop()
        raise ConfigEntryNotReady(f"Could not resolve {host}: {ex}") from ex

    coordinator = LIFXUpdateCoordinator(hass, connection, entry.title)
    coordinator.async_setup()
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        connection.async_stop()
        raise

    if coordinator.device.mac_addr != TARGET_ANY:
        domain_data[entry.entry_id] = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    domain_data = hass.data[DOMAIN]
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: LIFXUpdateCoordinator = domain_data.pop(entry.entry_id)
        coordinator.connection.async_stop()

    connect: LIFXConnectivityManager = domain_data.pop(DATA_LIFX_CONNECT, None)
    if connect is not None:
        connect.stop_discovery()

    manager: LIFXManager = domain_data.pop(DATA_LIFX_MANAGER, None)
    if manager is not None:
        manager.async_unload()

    return unload_ok
