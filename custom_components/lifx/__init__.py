"""Support for LIFX."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN, PLATFORM_SCHEMA
from homeassistant.const import CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_DISCOVERY_INTERVAL,
    CONF_GRACE_PERIOD,
    CONF_MESSAGE_TIMEOUT,
    CONF_RETRY_COUNT,
    DATA_LIFX_MANAGER,
    DOMAIN,
    PLATFORMS,
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_DISCOVERY_INTERVAL): cv.time_period_seconds,
        vol.Optional(CONF_RETRY_COUNT): cv.positive_int,
        vol.Optional(CONF_MESSAGE_TIMEOUT): cv.time_period_seconds,
        vol.Optional(CONF_GRACE_PERIOD): cv.time_period_seconds,
    }
)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT): cv.string,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: {
            LIGHT_DOMAIN: vol.Schema(
                {
                    vol.All(
                        cv.ensure_list,
                        [DEVICE_SCHEMA],
                    )
                }
            )
        }
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the LIFX component."""
    hass.data[DOMAIN] = config.get(DOMAIN) or {}

    if hass.data[DOMAIN] is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
            )
        )
    return True


async def async_setup_entry(hass, entry):
    """Set up LIFX from a config entry."""
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    hass.data.pop(DATA_LIFX_MANAGER).cleanup()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
