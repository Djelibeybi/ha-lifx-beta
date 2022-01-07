"""Support for LIFX."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import CONF_SCAN_INTERVAL

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_DEV_TIMEOUT,
    CONF_MSG_TIMEOUT,
    CONF_RETRY_COUNT,
    DATA_LIFX_MANAGER,
    DEFAULT_DEV_TIMEOUT,
    DEFAULT_MSG_TIMEOUT,
    DEFAULT_RETRY_COUNT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)

INTERFACE_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): cv.time_period_seconds,
        vol.Optional(CONF_RETRY_COUNT, default=DEFAULT_RETRY_COUNT): cv.positive_int,
        vol.Optional(
            CONF_MSG_TIMEOUT, default=DEFAULT_MSG_TIMEOUT
        ): cv.time_period_seconds,
        vol.Optional(
            CONF_DEV_TIMEOUT, default=DEFAULT_DEV_TIMEOUT
        ): cv.time_period_seconds,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: {LIGHT_DOMAIN: vol.Schema(vol.All(cv.ensure_list, [INTERFACE_SCHEMA]))}},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the LIFX component."""
    conf = config.get(DOMAIN)

    hass.data[DOMAIN] = conf or {}

    if conf is not None:
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
