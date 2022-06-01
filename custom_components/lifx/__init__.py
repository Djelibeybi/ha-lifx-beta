"""Support for LIFX."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

CONF_SERVER = "server"
CONF_BROADCAST = "broadcast"

INTERFACE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SERVER): cv.string,
        vol.Optional(CONF_PORT): cv.port,
        vol.Optional(CONF_BROADCAST): cv.string,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: {LIGHT_DOMAIN: vol.Schema(vol.All(cv.ensure_list, [INTERFACE_SCHEMA]))}},
    extra=vol.ALLOW_EXTRA,
)

DATA_LIFX_MANAGER = "lifx_manager"

PLATFORMS = [Platform.LIGHT]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LIFX from a config entry."""
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.pop(DATA_LIFX_MANAGER).cleanup()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
