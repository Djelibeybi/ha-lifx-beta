"""Const for LIFX."""
from homeassistant.const import Platform

CONF_DISCOVERY_INTERVAL = "discovery_interval"
CONF_MESSAGE_TIMEOUT = "message_timeout"
CONF_RETRY_COUNT = "retry_count"
CONF_GRACE_PERIOD = "grace_period"

DATA_LIFX_MANAGER = "lifx_manager"

DEFAULT_DISCOVERY_INTERVAL = 60
DEFAULT_MESSAGE_TIMEOUT = 0.5
DEFAULT_RETRY_COUNT = 3
DEFAULT_GRACE_PERIOD = 180

DOMAIN = "lifx"

PLATFORMS = [Platform.LIGHT]
