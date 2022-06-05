"""Support for LIFX lights."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import partial
from ipaddress import IPv4Address
import logging
import math

import aiolifx as aiolifx_module
from aiolifx.aiolifx import LifxDiscovery, Light
import aiolifx_effects as aiolifx_effects_module
from awesomeversion import AwesomeVersion
import voluptuous as vol

from homeassistant import util
from homeassistant.components import network
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_NAME,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
    COLOR_GROUP,
    DOMAIN,
    LIGHT_TURN_ON_SCHEMA,
    VALID_BRIGHTNESS,
    VALID_BRIGHTNESS_PCT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
    preprocess_turn_on_alternatives,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_MODE,
    ATTR_MODEL,
    ATTR_SW_VERSION,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback, EntityPlatform
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.color as color_util

from . import (
    CONF_BROADCAST,
    CONF_PORT,
    CONF_SERVER,
    DATA_LIFX_MANAGER,
    DOMAIN as LIFX_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)

DISCOVERY_INTERVAL = 10
MESSAGE_TIMEOUT = 0.5
MESSAGE_RETRIES = 8
UNAVAILABLE_GRACE = 90

FIX_MAC_FW = AwesomeVersion("3.70")
SERVICE_LIFX_SET_STATE = "set_state"

ATTR_INFRARED = "infrared"
ATTR_ZONES = "zones"
ATTR_POWER = "power"

LIFX_SET_STATE_SCHEMA = cv.make_entity_service_schema(
    {
        **LIGHT_TURN_ON_SCHEMA,
        ATTR_INFRARED: vol.All(vol.Coerce(int), vol.Clamp(min=0, max=255)),
        ATTR_ZONES: vol.All(cv.ensure_list, [cv.positive_int]),
        ATTR_POWER: cv.boolean,
    }
)

SERVICE_EFFECT_PULSE = "effect_pulse"
SERVICE_EFFECT_COLORLOOP = "effect_colorloop"
SERVICE_EFFECT_STOP = "effect_stop"

ATTR_POWER_ON = "power_on"
ATTR_PERIOD = "period"
ATTR_CYCLES = "cycles"
ATTR_SPREAD = "spread"
ATTR_CHANGE = "change"

PULSE_MODE_BLINK = "blink"
PULSE_MODE_BREATHE = "breathe"
PULSE_MODE_PING = "ping"
PULSE_MODE_STROBE = "strobe"
PULSE_MODE_SOLID = "solid"

PULSE_MODES = [
    PULSE_MODE_BLINK,
    PULSE_MODE_BREATHE,
    PULSE_MODE_PING,
    PULSE_MODE_STROBE,
    PULSE_MODE_SOLID,
]

LIFX_EFFECT_SCHEMA = {
    vol.Optional(ATTR_POWER_ON, default=True): cv.boolean,
}

LIFX_EFFECT_PULSE_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        ATTR_BRIGHTNESS: VALID_BRIGHTNESS,
        ATTR_BRIGHTNESS_PCT: VALID_BRIGHTNESS_PCT,
        vol.Exclusive(ATTR_COLOR_NAME, COLOR_GROUP): cv.string,
        vol.Exclusive(ATTR_RGB_COLOR, COLOR_GROUP): vol.All(
            vol.Coerce(tuple), vol.ExactSequence((cv.byte, cv.byte, cv.byte))
        ),
        vol.Exclusive(ATTR_XY_COLOR, COLOR_GROUP): vol.All(
            vol.Coerce(tuple), vol.ExactSequence((cv.small_float, cv.small_float))
        ),
        vol.Exclusive(ATTR_HS_COLOR, COLOR_GROUP): vol.All(
            vol.Coerce(tuple),
            vol.ExactSequence(
                (
                    vol.All(vol.Coerce(float), vol.Range(min=0, max=360)),
                    vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                )
            ),
        ),
        vol.Exclusive(ATTR_COLOR_TEMP, COLOR_GROUP): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Exclusive(ATTR_KELVIN, COLOR_GROUP): cv.positive_int,
        ATTR_PERIOD: vol.All(vol.Coerce(float), vol.Range(min=0.05)),
        ATTR_CYCLES: vol.All(vol.Coerce(float), vol.Range(min=1)),
        ATTR_MODE: vol.In(PULSE_MODES),
    }
)

LIFX_EFFECT_COLORLOOP_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        ATTR_BRIGHTNESS: VALID_BRIGHTNESS,
        ATTR_BRIGHTNESS_PCT: VALID_BRIGHTNESS_PCT,
        ATTR_PERIOD: vol.All(vol.Coerce(float), vol.Clamp(min=0.05)),
        ATTR_CHANGE: vol.All(vol.Coerce(float), vol.Clamp(min=0, max=360)),
        ATTR_SPREAD: vol.All(vol.Coerce(float), vol.Clamp(min=0, max=360)),
        ATTR_TRANSITION: cv.positive_float,
    }
)

LIFX_EFFECT_STOP_SCHEMA = cv.make_entity_service_schema({})

ATTR_HEV_STOP = "stop"
ATTR_HEV_DURATION = "duration"

SERVICE_LIFX_HEV_CYCLE = "hev_cycle"

LIFX_HEV_CYCLE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_HEV_STOP, default=False): bool,
        vol.Optional(ATTR_HEV_DURATION, default=7200): cv.positive_int,
    }
)


def aiolifx():
    """Return the aiolifx module."""
    return aiolifx_module


def aiolifx_effects():
    """Return the aiolifx_effects module."""
    return aiolifx_effects_module


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the LIFX light platform. Obsolete."""
    _LOGGER.warning("LIFX no longer works with light platform configuration")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LIFX from a config entry."""
    # Priority 1: manual config
    if not (interfaces := hass.data[LIFX_DOMAIN].get(DOMAIN)):
        # Priority 2: Home Assistant enabled interfaces
        ip_addresses = (
            source_ip
            for source_ip in await network.async_get_enabled_source_ips(hass)
            if isinstance(source_ip, IPv4Address) and not source_ip.is_loopback
        )
        interfaces = [{CONF_SERVER: str(ip)} for ip in ip_addresses]

    platform = entity_platform.async_get_current_platform()
    lifx_manager = LIFXManager(hass, platform, config_entry, async_add_entities)
    hass.data[DATA_LIFX_MANAGER] = lifx_manager

    for interface in interfaces:
        lifx_manager.start_discovery(interface)


def lifx_features(bulb):
    """Return a feature map for this bulb, or a default map if unknown."""
    return aiolifx().products.features_map.get(
        bulb.product
    ) or aiolifx().products.features_map.get(1)


def find_hsbk(hass, **kwargs):
    """Find the desired color from a number of possible inputs."""
    hue, saturation, brightness, kelvin = [None] * 4

    preprocess_turn_on_alternatives(hass, kwargs)

    if ATTR_HS_COLOR in kwargs:
        hue, saturation = kwargs[ATTR_HS_COLOR]
    elif ATTR_RGB_COLOR in kwargs:
        hue, saturation = color_util.color_RGB_to_hs(*kwargs[ATTR_RGB_COLOR])
    elif ATTR_XY_COLOR in kwargs:
        hue, saturation = color_util.color_xy_to_hs(*kwargs[ATTR_XY_COLOR])

    if hue is not None:
        hue = int(hue / 360 * 65535)
        saturation = int(saturation / 100 * 65535)
        kelvin = 3500

    if ATTR_COLOR_TEMP in kwargs:
        kelvin = int(
            color_util.color_temperature_mired_to_kelvin(kwargs[ATTR_COLOR_TEMP])
        )
        saturation = 0

    if ATTR_BRIGHTNESS in kwargs:
        brightness = convert_8_to_16(kwargs[ATTR_BRIGHTNESS])

    hsbk = [hue, saturation, brightness, kelvin]
    return None if hsbk == [None] * 4 else hsbk


def merge_hsbk(base, change):
    """Copy change on top of base, except when None."""
    if change is None:
        return None
    return [b if c is None else c for b, c in zip(base, change)]


class LIFXManager:
    """Representation of all known LIFX entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        platform: EntityPlatform,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Initialize the light."""
        self.entities: dict[str, LIFXLight] = {}
        self.switch_devices: list[str] = []
        self.hass = hass
        self.platform = platform
        self.config_entry = config_entry
        self.async_add_entities = async_add_entities
        self.effects_conductor = aiolifx_effects().Conductor(hass.loop)
        self.discoveries: list[LifxDiscovery] = []
        self.cleanup_unsub = self.hass.bus.async_listen(
            EVENT_HOMEASSISTANT_STOP, self.cleanup
        )
        self.entity_registry_updated_unsub = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self.entity_registry_updated
        )

        self.register_set_state()
        self.register_hev_cycle()
        self.register_effects()

    def start_discovery(self, interface):
        """Start discovery on a network interface."""
        kwargs = {"discovery_interval": DISCOVERY_INTERVAL}
        if broadcast_ip := interface.get(CONF_BROADCAST):
            kwargs["broadcast_ip"] = broadcast_ip
        lifx_discovery = aiolifx().LifxDiscovery(self.hass.loop, self, **kwargs)

        kwargs = {}
        if listen_ip := interface.get(CONF_SERVER):
            kwargs["listen_ip"] = listen_ip
        if listen_port := interface.get(CONF_PORT):
            kwargs["listen_port"] = listen_port
        lifx_discovery.start(**kwargs)

        self.discoveries.append(lifx_discovery)

    @callback
    def cleanup(self, event=None):
        """Release resources."""
        self.cleanup_unsub()
        self.entity_registry_updated_unsub()

        for discovery in self.discoveries:
            discovery.cleanup()

        for service in (
            SERVICE_LIFX_SET_STATE,
            SERVICE_EFFECT_STOP,
            SERVICE_EFFECT_PULSE,
            SERVICE_EFFECT_COLORLOOP,
        ):
            self.hass.services.async_remove(LIFX_DOMAIN, service)

    def register_set_state(self):
        """Register the LIFX set_state service call."""
        self.platform.async_register_entity_service(
            SERVICE_LIFX_SET_STATE, LIFX_SET_STATE_SCHEMA, "set_state"
        )

    def register_hev_cycle(self):
        """Register the LIFX hev_cycle service call."""
        self.platform.async_register_entity_service(
            SERVICE_LIFX_HEV_CYCLE, LIFX_HEV_CYCLE_SCHEMA, "hev_cycle"
        )

    def register_effects(self):
        """Register the LIFX effects as hass service calls."""

        async def service_handler(service: ServiceCall) -> None:
            """Apply a service, i.e. start an effect."""
            entities = await self.platform.async_extract_from_service(service)
            if entities:
                await self.start_effect(entities, service.service, **service.data)

        self.hass.services.async_register(
            LIFX_DOMAIN,
            SERVICE_EFFECT_PULSE,
            service_handler,
            schema=LIFX_EFFECT_PULSE_SCHEMA,
        )

        self.hass.services.async_register(
            LIFX_DOMAIN,
            SERVICE_EFFECT_COLORLOOP,
            service_handler,
            schema=LIFX_EFFECT_COLORLOOP_SCHEMA,
        )

        self.hass.services.async_register(
            LIFX_DOMAIN,
            SERVICE_EFFECT_STOP,
            service_handler,
            schema=LIFX_EFFECT_STOP_SCHEMA,
        )

    async def start_effect(self, entities, service, **kwargs):
        """Start a light effect on entities."""
        bulbs = [light.bulb for light in entities]

        if service == SERVICE_EFFECT_PULSE:
            effect = aiolifx_effects().EffectPulse(
                power_on=kwargs.get(ATTR_POWER_ON),
                period=kwargs.get(ATTR_PERIOD),
                cycles=kwargs.get(ATTR_CYCLES),
                mode=kwargs.get(ATTR_MODE),
                hsbk=find_hsbk(self.hass, **kwargs),
            )
            await self.effects_conductor.start(effect, bulbs)
        elif service == SERVICE_EFFECT_COLORLOOP:
            preprocess_turn_on_alternatives(self.hass, kwargs)

            brightness = None
            if ATTR_BRIGHTNESS in kwargs:
                brightness = convert_8_to_16(kwargs[ATTR_BRIGHTNESS])

            effect = aiolifx_effects().EffectColorloop(
                power_on=kwargs.get(ATTR_POWER_ON),
                period=kwargs.get(ATTR_PERIOD),
                change=kwargs.get(ATTR_CHANGE),
                spread=kwargs.get(ATTR_SPREAD),
                transition=kwargs.get(ATTR_TRANSITION),
                brightness=brightness,
            )
            await self.effects_conductor.start(effect, bulbs)
        elif service == SERVICE_EFFECT_STOP:
            await self.effects_conductor.stop(bulbs)

    @callback
    def register(self, bulb: Light) -> None:
        """Allow a single in-flight discovery per bulb."""
        if bulb.mac_addr not in self.switch_devices:
            self.hass.async_create_task(self._handle_discovery(bulb))

    async def _handle_discovery(self, bulb: Light) -> None:
        """Handle LIFX bulb registration lifecycle."""
        if entity := self.entities.get(bulb.mac_addr):
            entity.registered = True
            _LOGGER.debug("Reconnected to %s", entity.who)
            await entity.update_hass()
            return

        # Don't process LIFX Switch devices and ignore them in future
        if bulb.version is None:
            version_resp = await AwaitAioLIFX().wait(bulb.get_version)
            if version_resp and lifx_features(bulb)["relays"]:
                self.switch_devices.append(bulb.mac_addr)
                _LOGGER.debug(
                    "Adding LIFX Switch %s (%s) to ignore list",
                    str(bulb.mac_addr).replace(":", ""),
                    bulb.ip_addr,
                )
                return

        await self._async_process_discovery(bulb)

    async def _async_process_discovery(self, bulb: Light) -> None:
        """Process discovery of a device."""
        _LOGGER.debug("Connecting to %s (%s)", bulb.ip_addr, bulb.mac_addr)

        # Read initial state
        ack = AwaitAioLIFX().wait

        color_resp = await ack(bulb.get_color)

        if color_resp is None:
            _LOGGER.error("Failed to connect to %s", bulb.ip_addr)
            bulb.registered = False
            return

        bulb.timeout = MESSAGE_TIMEOUT
        bulb.retry_count = MESSAGE_RETRIES
        bulb.unregister_timeout = UNAVAILABLE_GRACE

        if lifx_features(bulb)["multizone"]:
            entity: LIFXLight = LIFXStrip(bulb, self.effects_conductor)
        elif lifx_features(bulb)["color"]:
            entity = LIFXColor(bulb, self.effects_conductor)
        else:
            entity = LIFXWhite(bulb, self.effects_conductor)

        _LOGGER.debug("Connected to %s", entity.who)
        self.entities[bulb.mac_addr] = entity
        self.async_add_entities([entity], True)

    @callback
    def unregister(self, bulb: Light) -> None:
        """Disconnect and unregister non-responsive bulbs."""
        if bulb.mac_addr in self.entities:
            entity = self.entities[bulb.mac_addr]
            _LOGGER.debug("Disconnected from %s", entity.who)
            entity.registered = False
            entity.async_write_ha_state()

    @callback
    def entity_registry_updated(self, event):
        """Handle entity registry updated."""
        if event.data["action"] == "remove":
            self.remove_empty_devices()

    def remove_empty_devices(self):
        """Remove devices with no entities."""
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        device_list = dr.async_entries_for_config_entry(
            device_reg, self.config_entry.entry_id
        )
        for device_entry in device_list:
            if not er.async_entries_for_device(
                entity_reg,
                device_entry.id,
                include_disabled_entities=True,
            ):
                device_reg.async_update_device(
                    device_entry.id, remove_config_entry_id=self.config_entry.entry_id
                )


class AwaitAioLIFX:
    """Wait for an aiolifx callback and return the message."""

    def __init__(self):
        """Initialize the wrapper."""
        self.message = None
        self.event = asyncio.Event()

    @callback
    def callback(self, bulb, message):
        """Handle responses."""
        self.message = message
        self.event.set()

    async def wait(self, method):
        """Call an aiolifx method and wait for its response."""
        self.message = None
        self.event.clear()
        method(callb=self.callback)

        await self.event.wait()
        return self.message


def convert_8_to_16(value):
    """Scale an 8 bit level into 16 bits."""
    return (value << 8) | value


def convert_16_to_8(value):
    """Scale a 16 bit level into 8 bits."""
    return value >> 8


class LIFXLight(LightEntity):
    """Representation of a LIFX light."""

    _attr_supported_features = LightEntityFeature.TRANSITION | LightEntityFeature.EFFECT

    def __init__(
        self, bulb: Light, effects_conductor: aiolifx_effects_module.Conductor
    ) -> None:
        """Initialize the light."""
        self.bulb = bulb
        self.effects_conductor = effects_conductor
        self.registered = True
        self.postponed_update = None
        self.lock = asyncio.Lock()

    def get_mac_addr(self):
        """Increment the last byte of the mac address by one for FW>3.70."""
        if (
            self.bulb.host_firmware_version
            and AwesomeVersion(self.bulb.host_firmware_version) >= FIX_MAC_FW
        ):
            octets = [int(octet, 16) for octet in self.bulb.mac_addr.split(":")]
            octets[5] = (octets[5] + 1) % 256
            return ":".join(f"{octet:02x}" for octet in octets)
        return self.bulb.mac_addr

    @property
    def device_info(self) -> DeviceInfo:
        """Return information about the device."""
        _map = aiolifx().products.product_map

        info = DeviceInfo(
            identifiers={(LIFX_DOMAIN, self.unique_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, self.get_mac_addr())},
            manufacturer="LIFX",
            name=self.name,
        )

        if (model := (_map.get(self.bulb.product) or self.bulb.product)) is not None:
            info[ATTR_MODEL] = str(model)
        if (version := self.bulb.host_firmware_version) is not None:
            info[ATTR_SW_VERSION] = version

        return info

    @property
    def available(self):
        """Return the availability of the bulb."""
        return self.registered

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self.bulb.mac_addr

    @property
    def name(self):
        """Return the name of the bulb."""
        return self.bulb.label

    @property
    def who(self):
        """Return a string identifying the bulb by name and mac."""
        return f"{self.name} ({self.bulb.mac_addr})"

    @property
    def min_mireds(self):
        """Return the coldest color_temp that this light supports."""
        kelvin = lifx_features(self.bulb)["max_kelvin"]
        return math.floor(color_util.color_temperature_kelvin_to_mired(kelvin))

    @property
    def max_mireds(self):
        """Return the warmest color_temp that this light supports."""
        kelvin = lifx_features(self.bulb)["min_kelvin"]
        return math.ceil(color_util.color_temperature_kelvin_to_mired(kelvin))

    @property
    def color_mode(self) -> ColorMode:
        """Return the color mode of the light."""
        bulb_features = lifx_features(self.bulb)
        if bulb_features["min_kelvin"] != bulb_features["max_kelvin"]:
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Flag supported color modes."""
        return {self.color_mode}

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        fade = self.bulb.power_level / 65535
        return convert_16_to_8(int(fade * self.bulb.color[2]))

    @property
    def color_temp(self):
        """Return the color temperature."""
        _, sat, _, kelvin = self.bulb.color
        if sat:
            return None
        return color_util.color_temperature_kelvin_to_mired(kelvin)

    @property
    def is_on(self):
        """Return true if light is on."""
        return self.bulb.power_level != 0

    @property
    def effect(self):
        """Return the name of the currently running effect."""
        effect = self.effects_conductor.effect(self.bulb)
        if effect:
            return f"lifx_effect_{effect.name}"
        return None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes for certain bulb types."""
        if lifx_features(self.bulb)["hev"] is True:
            if self.bulb.hev_cycle["remaining"] > 0:
                return {
                    "hev_cycle_active": True,
                    "hev_cycle_duration": self.bulb.hev_cycle["duration"],
                    "hev_cycle_remaining": self.bulb.hev_cycle["remaining"],
                    "hev_restore_power": self.bulb.hev_cycle["last_power"],
                }

            return {"hev_cycle_active": False}

        return {}

    async def update_hass(self, now=None):
        """Request new status and push it to hass."""
        self.postponed_update = None
        await self.async_update()
        self.async_write_ha_state()

    async def update_during_transition(self, when):
        """Update state at the start and end of a transition."""
        if self.postponed_update:
            self.postponed_update()

        # Transition has started
        await self.update_hass()

        # Transition has ended
        if when > 0:
            self.postponed_update = async_track_point_in_utc_time(
                self.hass,
                self.update_hass,
                util.dt.utcnow() + timedelta(milliseconds=when),
            )

    async def async_turn_on(self, **kwargs):
        """Turn the light on."""
        kwargs[ATTR_POWER] = True
        self.hass.async_create_task(self.set_state(**kwargs))

    async def async_turn_off(self, **kwargs):
        """Turn the light off."""
        kwargs[ATTR_POWER] = False
        self.hass.async_create_task(self.set_state(**kwargs))

    async def set_state(self, **kwargs):
        """Set a color on the light and turn it on/off."""
        async with self.lock:
            bulb = self.bulb

            await self.effects_conductor.stop([bulb])

            if ATTR_EFFECT in kwargs:
                await self.default_effect(**kwargs)
                return

            if ATTR_INFRARED in kwargs:
                bulb.set_infrared(convert_8_to_16(kwargs[ATTR_INFRARED]))

            if ATTR_TRANSITION in kwargs:
                fade = int(kwargs[ATTR_TRANSITION] * 1000)
            else:
                fade = 0

            # These are both False if ATTR_POWER is not set
            power_on = kwargs.get(ATTR_POWER, False)
            power_off = not kwargs.get(ATTR_POWER, True)

            hsbk = find_hsbk(self.hass, **kwargs)

            # Send messages, waiting for ACK each time
            ack = AwaitAioLIFX().wait

            if not self.is_on:
                if power_off:
                    await self.set_power(ack, False)
                # If fading on with color, set color immediately
                if hsbk and power_on:
                    await self.set_color(ack, hsbk, kwargs)
                    await self.set_power(ack, True, duration=fade)
                elif hsbk:
                    await self.set_color(ack, hsbk, kwargs, duration=fade)
                elif power_on:
                    await self.set_power(ack, True, duration=fade)
            else:
                if power_on:
                    await self.set_power(ack, True)
                if hsbk:
                    await self.set_color(ack, hsbk, kwargs, duration=fade)
                if power_off:
                    await self.set_power(ack, False, duration=fade)

            # Avoid state ping-pong by holding off updates as the state settles
            await asyncio.sleep(0.3)

        # Update when the transition starts and ends
        await self.update_during_transition(fade)

    async def hev_cycle(self, **kwargs):
        """Manage an HEV cleaning cycle."""
        ack = AwaitAioLIFX().wait
        stop = kwargs.get(ATTR_HEV_STOP, False)
        duration = kwargs.get(ATTR_HEV_DURATION, 7200)

        if stop is True:
            await ack(partial(self.bulb.set_hev_cycle, enable=False))
        else:
            await ack(partial(self.bulb.set_hev_cycle, enable=True, duration=duration))

    async def set_power(self, ack, pwr, duration=0):
        """Send a power change to the bulb."""
        await ack(partial(self.bulb.set_power, pwr, duration=duration))

    async def set_color(self, ack, hsbk, kwargs, duration=0):
        """Send a color change to the bulb."""
        hsbk = merge_hsbk(self.bulb.color, hsbk)
        await ack(partial(self.bulb.set_color, hsbk, duration=duration))

    async def default_effect(self, **kwargs):
        """Start an effect with default parameters."""
        service = kwargs[ATTR_EFFECT]
        data = {ATTR_ENTITY_ID: self.entity_id}
        await self.hass.services.async_call(
            LIFX_DOMAIN, service, data, context=self._context
        )

    async def async_update(self):
        """Update bulb status."""
        if self.available and not self.lock.locked():
            await AwaitAioLIFX().wait(self.bulb.get_color)
            if lifx_features(self.bulb)["hev"] is True:
                await AwaitAioLIFX().wait(self.bulb.get_hev_cycle)


class LIFXWhite(LIFXLight):
    """Representation of a white-only LIFX light."""

    @property
    def effect_list(self):
        """Return the list of supported effects for this light."""
        return [SERVICE_EFFECT_PULSE, SERVICE_EFFECT_STOP]


class LIFXColor(LIFXLight):
    """Representation of a color LIFX light."""

    @property
    def color_mode(self) -> ColorMode:
        """Return the color mode of the light."""
        sat = self.bulb.color[1]
        if sat:
            return ColorMode.HS
        return ColorMode.COLOR_TEMP

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Flag supported color modes."""
        return {ColorMode.COLOR_TEMP, ColorMode.HS}

    @property
    def effect_list(self):
        """Return the list of supported effects for this light."""
        return [SERVICE_EFFECT_COLORLOOP, SERVICE_EFFECT_PULSE, SERVICE_EFFECT_STOP]

    @property
    def hs_color(self):
        """Return the hs value."""
        hue, sat, _, _ = self.bulb.color
        hue = hue / 65535 * 360
        sat = sat / 65535 * 100
        return (hue, sat) if sat else None


class LIFXStrip(LIFXColor):
    """Representation of a LIFX light strip with multiple zones."""

    async def set_color(self, ack, hsbk, kwargs, duration=0):
        """Send a color change to the bulb."""
        bulb = self.bulb
        num_zones = len(bulb.color_zones)

        if (zones := kwargs.get(ATTR_ZONES)) is None:
            # Fast track: setting all zones to the same brightness and color
            # can be treated as a single-zone bulb.
            if hsbk[2] is not None and hsbk[3] is not None:
                await super().set_color(ack, hsbk, kwargs, duration)
                return

            zones = list(range(0, num_zones))
        else:
            zones = [x for x in set(zones) if x < num_zones]

        # Zone brightness is not reported when powered off
        if not self.is_on and hsbk[2] is None:
            await self.set_power(ack, True)
            await asyncio.sleep(0.3)
            await self.update_color_zones()
            await self.set_power(ack, False)
            await asyncio.sleep(0.3)

        # Send new color to each zone
        for index, zone in enumerate(zones):
            zone_hsbk = merge_hsbk(bulb.color_zones[zone], hsbk)
            apply = 1 if (index == len(zones) - 1) else 0
            set_zone = partial(
                bulb.set_color_zones,
                start_index=zone,
                end_index=zone,
                color=zone_hsbk,
                duration=duration,
                apply=apply,
            )
            await ack(set_zone)

    async def async_update(self):
        """Update strip status."""
        if self.available and not self.lock.locked():
            await super().async_update()
            await self.update_color_zones()

    async def update_color_zones(self):
        """Get updated color information for each zone."""
        zone = 0
        top = 1
        while self.available and zone < top:
            # Each get_color_zones can update 8 zones at once
            resp = await AwaitAioLIFX().wait(
                partial(self.bulb.get_color_zones, start_index=zone)
            )
            if resp:
                zone += 8
                top = resp.count

                # We only await multizone responses so don't ask for just one
                if zone == top - 1:
                    zone -= 1
