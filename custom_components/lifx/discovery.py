"""The lifx integration discovery."""
from __future__ import annotations

import asyncio
from collections.abc import Collection

from aiolifx.aiolifx import LifxDiscovery, Light
from aiolifx.message import Message

from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery_flow

from .const import CONF_SERIAL, DOMAIN, TARGET_ANY

DEFAULT_TIMEOUT = 8.5


class LIFXConnectivityManager:
    """Monitors connectivity via discovery responses."""

    def __init__(self, hass: HomeAssistant):
        """Initialise the connectivity monitor."""
        self._hass = hass
        self._devices: dict[str, Light] = {}
        self._discoveries: list[LifxDiscovery] = []
        self._connected: dict[str, bool] = {}

    @property
    def all_lights(self) -> Collection[Light]:
        """Return all discovered lights."""
        return [self._devices.values()]

    async def async_start_discovery(self) -> None:
        """Discover lifx devices."""

        broadcast_addrs = await network.async_get_ipv4_broadcast_addresses(self._hass)
        for address in broadcast_addrs:
            lifx_discovery = LifxDiscovery(
                self._hass.loop, self, broadcast_ip=str(address)
            )
            self._discoveries.append(lifx_discovery)
            lifx_discovery.start()

    async def async_discover_devices(self) -> Collection[Light]:
        """Start discovery of LIFX devices."""
        if len(self._discoveries) == 0:
            await self.async_start_discovery()
            await asyncio.sleep(DEFAULT_TIMEOUT)

        return self.all_lights

    def stop_discovery(self) -> None:
        """Stop discovery of LIFX devices."""
        for discovery in self._discoveries:
            discovery.cleanup()

    def is_connected(self, mac_addr: str) -> bool:
        """Return True if mac_addr is connected."""
        return self._connected.get(mac_addr, False)

    def set_connected(self, mac_addr: str, connected: bool) -> None:
        """Set the connected state of the device."""
        self._connected[mac_addr] = connected

    @callback
    def async_init_discovery_flow(self, host: str, serial: str) -> None:
        """Start discovery of devices."""
        discovery_flow.async_create_flow(
            self._hass,
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={CONF_HOST: host, CONF_SERIAL: serial},
        )

    @callback
    def async_trigger_discovery_flow(self) -> None:
        """Trigger config flows for discovered devices."""
        for device in self._devices.values():
            if isinstance(device, Light):
                # device.mac_addr is not the mac_address, its the serial number
                self.async_init_discovery_flow(device.ip_addr, device.mac_addr)

    def register(self, light: Light):
        """Handle detected bulb."""

        def _light_connected(light: Light, message: Message) -> None:
            """Handle get_hostfirmware response."""
            if light.mac_addr == TARGET_ANY:
                light.mac_addr = message.target_addr

            if light.mac_addr != TARGET_ANY:
                self._devices[light.mac_addr] = Light
                self._connected[light.mac_addr] = True

            discovery_flow.async_create_flow(
                self._hass,
                DOMAIN,
                context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HOST: light.ip_addr, CONF_SERIAL: light.mac_addr},
            )

        if light.mac_addr == TARGET_ANY or light.mac_addr not in self._devices:
            light.get_color(callb=_light_connected)

    def unregister(self, light: Light):
        """Handle disappearing bulb."""

        # mark disconnected
        self._connected[light.mac_addr] = False
