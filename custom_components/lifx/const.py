"""Const for LIFX."""
from homeassistant.const import Platform

CONF_MSG_TIMEOUT = "message_timeout"
CONF_RETRY_COUNT = "retry_count"
CONF_DEV_TIMEOUT = "device_timeout"

DATA_LIFX_MANAGER = "lifx_manager"

DEFAULT_MSG_TIMEOUT = 0.5
DEFAULT_RETRY_COUNT = 3
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_DEV_TIMEOUT = 180

DOMAIN = "lifx"

PLATFORMS = [Platform.LIGHT]
