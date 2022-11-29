"""Support for LIFX."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from math import floor, log10
from typing import Any

from aiolifx import products
from aiolifx.aiolifx import Light
from aiolifx.message import Message
from aiolifx.msgtypes import (
    Acknowledgement,
    LightState,
    LightStateInfrared,
    MultiZoneDirection,
    MultiZoneEffectType,
    MultiZoneStateExtendedColorZones,
    MultiZoneStateMultiZone,
    MultiZoneStateMultiZoneEffect,
    StateGroup,
    StateHevCycle,
    StateHostFirmware,
    StateLabel,
    StateVersion,
    StateWifiInfo,
)
import async_timeout
from awesomeversion import AwesomeVersion

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_NAME,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_XY_COLOR,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
import homeassistant.util.color as color_util

from .const import (
    _LOGGER,
    DOMAIN,
    INFRARED_BRIGHTNESS_VALUES_MAP,
    OVERALL_TIMEOUT,
    TARGET_ANY,
)

FIX_MAC_FW = AwesomeVersion("3.70")


@callback
def async_entry_is_legacy(entry: ConfigEntry) -> bool:
    """Check if a config entry is the legacy shared one."""
    return entry.unique_id is None or entry.unique_id == DOMAIN


@callback
def async_get_legacy_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Get the legacy config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if async_entry_is_legacy(entry):
            return entry
    return None


def infrared_brightness_value_to_option(value: int) -> str | None:
    """Convert infrared brightness from value to option."""
    return INFRARED_BRIGHTNESS_VALUES_MAP.get(value, None)


def infrared_brightness_option_to_value(option: str) -> int | None:
    """Convert infrared brightness option to value."""
    option_values = {v: k for k, v in INFRARED_BRIGHTNESS_VALUES_MAP.items()}
    return option_values.get(option, None)


def convert_8_to_16(value: int) -> int:
    """Scale an 8 bit level into 16 bits."""
    return (value << 8) | value


def convert_16_to_8(value: int) -> int:
    """Scale a 16 bit level into 8 bits."""
    return value >> 8


def lifx_features(light: Light) -> dict[str, Any]:
    """Return a feature map for this light, or a default map if unknown."""
    features: dict[str, Any] = (
        products.features_map.get(light.product) or products.features_map[1]
    )
    return features


def signal_to_rssi(signal: float) -> int:
    """Convert LIFX signal value to RSSI."""
    return int(floor(10 * log10(signal) + 0.5))


def find_hsbk(hass: HomeAssistant, **kwargs: Any) -> list[float | int | None] | None:
    """Find the desired color from a number of possible inputs.

    Hue, Saturation, Brightness, Kelvin
    """
    hue, saturation, brightness, kelvin = [None] * 4

    if (color_name := kwargs.get(ATTR_COLOR_NAME)) is not None:
        try:
            hue, saturation = color_util.color_RGB_to_hs(
                *color_util.color_name_to_rgb(color_name)
            )
        except ValueError:
            _LOGGER.warning(
                "Got unknown color %s, falling back to neutral white", color_name
            )
            hue, saturation = (0, 0)

    if ATTR_HS_COLOR in kwargs:
        hue, saturation = kwargs[ATTR_HS_COLOR]
    elif ATTR_RGB_COLOR in kwargs:
        hue, saturation = color_util.color_RGB_to_hs(*kwargs[ATTR_RGB_COLOR])
    elif ATTR_XY_COLOR in kwargs:
        hue, saturation = color_util.color_xy_to_hs(*kwargs[ATTR_XY_COLOR])

    if hue is not None:
        assert saturation is not None
        hue = int(hue / 360 * 65535)
        saturation = int(saturation / 100 * 65535)
        kelvin = 3500

    if ATTR_KELVIN in kwargs:
        _LOGGER.warning(
            "The 'kelvin' parameter is deprecated. Please use 'color_temp_kelvin' for all service calls"
        )
        kelvin = kwargs.pop(ATTR_KELVIN)
        saturation = 0

    if ATTR_COLOR_TEMP in kwargs:
        kelvin = color_util.color_temperature_mired_to_kelvin(
            kwargs.pop(ATTR_COLOR_TEMP)
        )
        saturation = 0

    if ATTR_COLOR_TEMP_KELVIN in kwargs:
        kelvin = kwargs.pop(ATTR_COLOR_TEMP_KELVIN)
        saturation = 0

    if ATTR_BRIGHTNESS in kwargs:
        brightness = convert_8_to_16(kwargs[ATTR_BRIGHTNESS])

    if ATTR_BRIGHTNESS_PCT in kwargs:
        brightness = convert_8_to_16(round(255 * kwargs[ATTR_BRIGHTNESS_PCT] / 100))

    hsbk = [hue, saturation, brightness, kelvin]
    return None if hsbk == [None] * 4 else hsbk


def merge_hsbk(
    base: list[float | int | None], change: list[float | int | None]
) -> list[float | int | None]:
    """Copy change on top of base, except when None.

    Hue, Saturation, Brightness, Kelvin
    """
    return [b if c is None else c for b, c in zip(base, change)]


def _get_mac_offset(mac_addr: str, offset: int) -> str:
    octets = [int(octet, 16) for octet in mac_addr.split(":")]
    octets[5] = (octets[5] + offset) % 256
    return ":".join(f"{octet:02x}" for octet in octets)


def _off_by_one_mac(firmware: str) -> bool:
    """Check if the firmware version has the off by one mac."""
    return bool(firmware and AwesomeVersion(firmware) >= FIX_MAC_FW)


def get_real_mac_addr(mac_addr: str, firmware: str) -> str:
    """Increment the last byte of the mac address by one for FW>3.70."""
    return _get_mac_offset(mac_addr, 1) if _off_by_one_mac(firmware) else mac_addr


def formatted_serial(serial_number: str) -> str:
    """Format the serial number to match the HA device registry."""
    return dr.format_mac(serial_number)


def mac_matches_serial_number(mac_addr: str, serial_number: str) -> bool:
    """Check if a mac address matches the serial number."""
    formatted_mac = dr.format_mac(mac_addr)
    return bool(
        formatted_serial(serial_number) == formatted_mac
        or _get_mac_offset(serial_number, 1) == formatted_mac
    )


def _unpack_bytes(label: bytes) -> str:
    """Bytes to string transformation."""
    return bytes(label).decode().replace("\x00", "")


async def async_execute_lifx(method: Callable) -> Message:
    """Execute a lifx coroutine and wait for a response."""
    future: asyncio.Future[Message] = asyncio.Future()

    def _callback(light: Light, message: Message) -> None:

        if message is None:
            _LOGGER.error("No response from %s (%s)", light.ip_addr, light.mac_addr)
            return

        if light.mac_addr == TARGET_ANY:
            light.mac_addr = message.target_addr

        if not future.done():
            # The future will get canceled out from under
            # us by async_timeout when we hit the OVERALL_TIMEOUT

            if isinstance(message, StateGroup):
                light.group = _unpack_bytes(message.label)
            elif isinstance(message, StateLabel):
                light.label = _unpack_bytes(message.label)
            elif isinstance(message, StateHostFirmware):
                major_version = str(message.version >> 16)
                minor_version = str(message.version & 0xFFFF)
                light.host_firmware_version = f"{major_version}.{minor_version}"
            elif isinstance(message, StateVersion):
                light.product = message.product
            elif isinstance(message, LightState):
                light.color = message.color
                light.label = _unpack_bytes(message.label)
                light.power_level = message.power_level
            elif isinstance(message, StateHevCycle):
                light.hev_cycle = {
                    "duration": message.duration,
                    "remaining": message.remaining,
                    "last_power": message.last_power,
                }
            elif isinstance(message, LightStateInfrared):
                light.infrared_brightness = message.infrared_brightness
            elif isinstance(message, MultiZoneStateMultiZone):
                if light.color_zones is None:
                    light.color_zones = list(None * message.count)
                for zone in range(message.index, min(message.index + 8, message.count)):
                    _LOGGER.debug(
                        "Updating color zones %s-%s of %s for %s",
                        zone*8 + 1,
                        min(zone*8 + 8, message.count),
                        message.count,
                        light.label,
                    )
                    if zone > len(light.color_zones) - 1:
                        light.color_zones += [message.color[zone - message.index]] * (
                            zone - len(light.color_zones)
                        )
                        light.color_zones.append(message.color[zone - message.index])
                    else:
                        light.color_zones[zone] = message.color[zone - message.index]
            elif isinstance(message, MultiZoneStateExtendedColorZones):
                light.zones_count = message.zones_count
                light.color_zones = message.colors[
                    message.zone_index : message.zones_count
                ]
            elif isinstance(message, MultiZoneStateMultiZoneEffect):
                light.effect = {
                    "effect": MultiZoneEffectType(message.effect).name.upper()
                }
                if message.effect != 0:
                    light.effect["speed"] = message.speed / 1000
                    light.effect["duration"] = (
                        0.0
                        if message.duration == 0
                        else float(f"{message.duration / 1000000000:4f}")
                    )
                    light.effect["direction"] = MultiZoneDirection(
                        message.direction
                    ).name.capitalize()
            elif isinstance(message, StateWifiInfo):
                # Not handled by aiolifx so just return the entire message
                pass
            elif isinstance(message, Acknowledgement):
                # Expected response for any non-rapid set method
                pass
            else:
                _LOGGER.debug("No handler for: %s", message.__class__.__name__)

            future.set_result((light, message))

    method(callb=_callback)
    result = None

    async with async_timeout.timeout(OVERALL_TIMEOUT):
        result = await future

    if result[1] is None:
        _LOGGER.error("No response from %s (%s)", result[0].ip_addr, result[0].mac_addr)

    return result[1]
