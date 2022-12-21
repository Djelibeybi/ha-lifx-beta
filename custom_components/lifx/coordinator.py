"""Coordinator for lifx."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import IntEnum
from functools import partial
from typing import Any, cast

from aiolifx.aiolifx import (
    Light,
    MultiZoneDirection,
    MultiZoneEffectType,
    TileEffectType,
    features_map,
    product_map,
)
from aiolifx.connection import LIFXConnection
from aiolifx.message import Message
from aiolifx.msgtypes import StateWifiInfo
from aiolifx_themes.themes import ThemeLibrary, ThemePainter
import async_timeout

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    _LOGGER,
    ATTR_REMAINING,
    DATA_LIFX_CONNECT,
    DOMAIN,
    IDENTIFY_WAVEFORM,
    MESSAGE_RETRIES,
    MESSAGE_TIMEOUT,
    OVERALL_TIMEOUT,
    TARGET_ANY,
    UNAVAILABLE_GRACE,
)
from .discovery import LIFXConnectivityManager
from .util import (
    get_real_mac_addr,
    infrared_brightness_option_to_value,
    infrared_brightness_value_to_option,
    signal_to_rssi,
)

LIGHT_UPDATE_INTERVAL = 10
REQUEST_REFRESH_DELAY = 0.35
LIFX_IDENTIFY_DELAY = 3.0


class FirmwareEffect(IntEnum):
    """Enumeration of LIFX firmware effects."""

    OFF = 0
    MOVE = 1
    MORPH = 2
    FLAME = 3


class LIFXException(Exception):
    """LIFX specific exception."""


class LIFXUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator to gather data for a specific lifx device."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: LIFXConnection,
        title: str,
    ) -> None:
        """Initialize DataUpdateCoordinator."""
        assert connection.device is not None
        self.connection = connection
        self.connect: LIFXConnectivityManager = hass.data[DOMAIN][DATA_LIFX_CONNECT]
        self.device = connection.device
        self._update_rssi: bool = False
        self.rssi: int = 0
        self.limit = asyncio.Semaphore(30)
        self.active_effect = FirmwareEffect.OFF
        self.last_used_theme: str = ""
        self._features: dict[str, Any] = {}
        self._disconnects: int = 0

        super().__init__(
            hass,
            _LOGGER,
            name=f"{title} ({self.device.ip_addr})",
            update_interval=timedelta(seconds=LIGHT_UPDATE_INTERVAL),
            # We don't want an immediate refresh since the device
            # takes a moment to reflect the state change
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REQUEST_REFRESH_DELAY, immediate=False
            ),
        )

    @callback
    def async_setup(self) -> None:
        """Change timeouts."""

        self.device.timeout = MESSAGE_TIMEOUT
        self.device.retry_count = MESSAGE_RETRIES
        self.device.unregister_timeout = UNAVAILABLE_GRACE

    @property
    def serial_number(self) -> str:
        """Return the internal mac address."""
        return cast(
            str, self.device.mac_addr
        )  # device.mac_addr is not the mac_address, its the serial number

    @property
    def mac_address(self) -> str:
        """Return the physical mac address."""
        return get_real_mac_addr(
            # device.mac_addr is not the mac_address, its the serial number
            self.device.mac_addr,
            self.device.host_firmware_version,
        )

    @property
    def label(self) -> str:
        """Return the label of the bulb."""
        return cast(str, self.device.label)

    @property
    def model(self) -> str:
        """Return the model type of the light."""
        return product_map[self.device.product]

    @property
    def current_infrared_brightness(self) -> str | None:
        """Return the current infrared brightness as a string."""
        return infrared_brightness_value_to_option(self.device.infrared_brightness)

    @property
    def lifx_features(self) -> dict[str, Any]:
        """Retrieve and cache lifx features of this device."""
        features: dict[str, Any] = (
            features_map.get(self.device.product) or features_map[1]
        )
        return features

    async def async_lifx_method_as_coro(self, method: Callable) -> Message | None:
        """Execute a lifx coroutine and wait for a response."""

        future: asyncio.Future[Message] = self.hass.loop.create_future()

        def _callback(light: Light, message: Message) -> None:
            """Ue the aiolifx callback return result to the future."""
            if light.mac_addr == TARGET_ANY and message is not None:
                light.mac_addr = message.target_addr

            if not future.done():
                future.set_result(message)

        def _reset_disconnects(_: datetime) -> None:
            """Reset disconnects to 0."""
            self._disconnects = 0

        if self.limit.locked():
            _LOGGER.debug(
                "In-flight limit reached: sleeping for %s seconds.", MESSAGE_TIMEOUT
            )
            await asyncio.sleep(MESSAGE_TIMEOUT)
            return await self.async_lifx_method_as_coro(method)

        method(callb=_callback)

        async with self.limit, async_timeout.timeout(OVERALL_TIMEOUT):
            message: Message = await future

            if message is None:
                if self.connect.is_connected(self.device.mac_addr):
                    if self._disconnects == 0:
                        # reset disconnects in a minute
                        async_track_time_interval(
                            self.hass, _reset_disconnects, timedelta(minutes=1)
                        )

                    self._disconnects += 1

                    _LOGGER.warning(
                        "[DEBUG] soft disconnect count for %s (%s) is %s",
                        self.device.label,
                        self.device.ip_addr,
                        self._disconnects,
                    )
                    if self._disconnects > 3:
                        _LOGGER.error(
                            "[DEBUG] Soft disconnect from %s (%s)",
                            self.device.label,
                            self.device.ip_addr,
                        )

                        raise UpdateFailed(
                            f"{self.device.label} ({self.device.ip_addr})"
                        )

            if (
                self.connect.is_connected(self.device.mac_addr) is False
                and self._disconnects > 0
            ):
                self.connect.set_connected(self.device.mac_addr, True)
                _reset_disconnects(datetime.now())

                _LOGGER.debug(
                    "Reconnected to %s (%s)",
                    self.label,
                    self.device.ip_addr,
                )

            return message

    async def diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information about the device."""
        features = self.lifx_features
        device_data = {
            "firmware": self.device.host_firmware_version,
            "vendor": self.device.vendor,
            "product_id": self.device.product,
            "features": features,
            "hue": self.device.color[0],
            "saturation": self.device.color[1],
            "brightness": self.device.color[2],
            "kelvin": self.device.color[3],
            "power": self.device.power_level,
        }

        if features.get("multizone", False) is True:
            zones = {"count": self.device.zones_count, "state": {}}
            for index, zone_color in enumerate(self.device.color_zones):
                zones["state"][index] = {
                    "hue": zone_color[0],
                    "saturation": zone_color[1],
                    "brightness": zone_color[2],
                    "kelvin": zone_color[3],
                }
            device_data["zones"] = zones

        if features["hev"] is True:
            device_data["hev"] = {
                "hev_cycle": self.device.hev_cycle,
                "hev_config": self.device.hev_cycle_configuration,
                "last_result": self.device.last_hev_cycle_result,
            }

        if features["infrared"] is True:
            device_data["infrared"] = {"brightness": self.device.infrared_brightness}

        return device_data

    def async_get_entity_id(self, platform: Platform, key: str) -> str | None:
        """Return the entity_id from the platform and key provided."""
        ent_reg = er.async_get(self.hass)
        return ent_reg.async_get_entity_id(
            platform, DOMAIN, f"{self.serial_number}_{key}"
        )

    async def _async_update_data(self) -> None:
        """Fetch all device data from the api."""

        await self.async_lifx_method_as_coro(self.device.get_color)

        if self.device.host_firmware_version is None:
            await self.async_lifx_method_as_coro(self.device.get_hostfirmware)

        if self.device.product is None:
            await self.async_lifx_method_as_coro(self.device.get_version)

        if self.device.group is None:
            await self.async_lifx_method_as_coro(self.device.get_group)

        if self.device.label is None:
            await self.async_lifx_method_as_coro(self.device.get_label)

        if self._update_rssi is True:
            await self.async_lifx_method_as_coro(self.device.get_wifiinfo)

        # Update extended multizone devices
        if self.lifx_features.get("extended_multizone", False):
            await self.async_lifx_method_as_coro(self.device.get_extended_color_zones)
            await self.async_lifx_method_as_coro(self.device.get_multizone_effect)
        # use legacy methods for older devices
        elif self.lifx_features.get("multizone", False):
            await self.async_get_color_zones()
            await self.async_lifx_method_as_coro(self.device.get_multizone_effect)

        if self.lifx_features.get("hev", False):
            await self.async_lifx_method_as_coro(self.device.get_hev_cycle)

        if self.lifx_features.get("infrared", False):
            await self.async_lifx_method_as_coro(self.device.get_infrared)

        if self.lifx_features.get("multizone", False):
            self.active_effect = FirmwareEffect[self.device.effect.get("effect", "OFF")]

    async def async_get_color_zones(self) -> None:
        """Get updated color information for each zone."""
        await self.async_lifx_method_as_coro(
            partial(self.device.get_color_zones, start_index=0, end_index=255)
        )

    async def async_set_waveform_optional(self, value: dict[str, Any]) -> None:
        """Send a set_waveform_optional message to the device."""
        await self.async_lifx_method_as_coro(
            partial(self.device.set_waveform_optional, value=value)
        )

    async def async_set_power(self, state: bool, duration: int | None) -> None:
        """Send a set power message to the device."""
        await self.async_lifx_method_as_coro(
            partial(self.device.set_power, state, duration=duration)
        )

    async def async_set_color(
        self, hsbk: list[float | int | None], duration: int | None
    ) -> None:
        """Send a set color message to the device."""
        await self.async_lifx_method_as_coro(
            partial(self.device.set_color, hsbk, duration=duration)
        )

    async def async_set_color_zones(
        self,
        start_index: int,
        end_index: int,
        hsbk: list[float | int | None],
        duration: int | None,
        apply: int,
    ) -> None:
        """Send a set color zones message to the device."""
        await self.async_lifx_method_as_coro(
            partial(
                self.device.set_color_zones,
                start_index=start_index,
                end_index=end_index,
                color=hsbk,
                duration=duration,
                apply=apply,
            )
        )

    async def async_set_extended_color_zones(
        self,
        colors: list[tuple[int | float, int | float, int | float, int | float]],
        colors_count: int | None = None,
        duration: int = 0,
        apply: int = 1,
    ) -> None:
        """Send a single set extended color zones message to the device."""

        if colors_count is None:
            colors_count = len(colors)

        # pad the color list with blanks if necessary
        if len(colors) < 82:
            for _ in range(82 - len(colors)):
                colors.append((0, 0, 0, 0))

        await self.async_lifx_method_as_coro(
            partial(
                self.device.set_extended_color_zones,
                colors=colors,
                colors_count=colors_count,
                duration=duration,
                apply=apply,
            )
        )

    async def async_set_multizone_effect(
        self,
        effect: str,
        speed: float = 3.0,
        direction: str = "RIGHT",
        theme_name: str | None = None,
        power_on: bool = True,
    ) -> None:
        """Control the firmware-based Move effect on a multizone device."""
        if self.lifx_features.get("multizone", False) is True:

            if power_on and self.device.power_level == 0:
                await self.async_set_power(True, 0)

            if theme_name is not None:
                theme = ThemeLibrary().get_theme(theme_name)
                await ThemePainter(self.hass.loop).paint(
                    theme, [self.device], round(speed)
                )

            await self.async_lifx_method_as_coro(
                partial(
                    self.device.set_multizone_effect,
                    effect=MultiZoneEffectType[effect.upper()].value,
                    speed=speed,
                    direction=MultiZoneDirection[direction.upper()].value,
                )
            )
            self.active_effect = FirmwareEffect[effect.upper()]

    async def async_set_matrix_effect(
        self,
        effect: str,
        palette: list[tuple[int, int, int, int]] | None = None,
        speed: float = 3,
        power_on: bool = True,
    ) -> None:
        """Control the firmware-based effects on a matrix device."""
        if self.lifx_features.get("matrix", False) is True:
            if power_on and self.device.power_level == 0:
                await self.async_set_power(True, 0)

            if palette is None:
                palette = []

            await self.async_lifx_method_as_coro(
                partial(
                    self.device.set_tile_effect,
                    effect=TileEffectType[effect.upper()].value,
                    speed=speed,
                    palette=palette,
                )
            )
            self.active_effect = FirmwareEffect[effect.upper()]

    def async_get_active_effect(self) -> int:
        """Return the enum value of the currently active firmware effect."""
        return self.active_effect.value

    async def async_set_infrared_brightness(self, option: str) -> None:
        """Set infrared brightness."""
        infrared_brightness = infrared_brightness_option_to_value(option)
        await self.async_lifx_method_as_coro(
            partial(self.device.set_infrared, infrared_brightness)
        )

    async def async_identify_bulb(self) -> None:
        """Identify the device by flashing it three times."""
        bulb: Light = self.device
        if bulb.power_level:
            # just flash the bulb for three seconds
            await self.async_set_waveform_optional(value=IDENTIFY_WAVEFORM)
            return
        # Turn the bulb on first, flash for 3 seconds, then turn off
        await self.async_set_power(state=True, duration=1)
        await self.async_set_waveform_optional(value=IDENTIFY_WAVEFORM)
        await asyncio.sleep(LIFX_IDENTIFY_DELAY)
        await self.async_set_power(state=False, duration=1)

    def async_enable_rssi_updates(self) -> Callable[[], None]:
        """Enable RSSI signal strength updates."""

        @callback
        def _async_disable_rssi_updates() -> None:
            """Disable RSSI updates when sensor removed."""
            self._update_rssi = False

        self._update_rssi = True
        return _async_disable_rssi_updates

    def async_get_hev_cycle_state(self) -> bool | None:
        """Return the current HEV cycle state."""
        if self.device.hev_cycle is None:
            return None
        return bool(self.device.hev_cycle.get(ATTR_REMAINING, 0) > 0)

    async def async_set_hev_cycle_state(self, enable: bool, duration: int = 0) -> None:
        """Start or stop an HEV cycle on a LIFX Clean bulb."""
        if self.lifx_features.get("hev", False):
            await self.async_lifx_method_as_coro(
                partial(
                    self.device.set_hev_cycle,
                    enable=enable,
                    duration=duration,
                )
            )

    async def async_update_rssi(self) -> None:
        """Update RSSI value."""
        resp: StateWifiInfo = await self.async_lifx_method_as_coro(
            self.device.get_wifiinfo
        )
        if isinstance(resp, StateWifiInfo):
            self.rssi = signal_to_rssi(resp.signal)

    async def async_apply_theme(self, theme_name: str) -> None:
        """Apply the selected theme to the device."""
        self.last_used_theme = theme_name
        theme = ThemeLibrary().get_theme(theme_name)
        await ThemePainter(self.hass.loop).paint(theme, [self.device])
