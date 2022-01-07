"""Config flow flow LIFX."""
from __future__ import annotations

from typing import Any

import aiolifx
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEV_TIMEOUT,
    CONF_MSG_TIMEOUT,
    CONF_RETRY_COUNT,
    DEFAULT_DEV_TIMEOUT,
    DEFAULT_MSG_TIMEOUT,
    DEFAULT_RETRY_COUNT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class LifxConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a discovery config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the LIFX config flow."""
        self._domain = DOMAIN
        self._title = "LIFX"

    async def _async_has_devices(self):
        """Return if there are devices that can be discovered."""
        lifx_ip_addresses = await aiolifx.LifxScan(self.hass.loop).scan()
        return len(lifx_ip_addresses) > 0

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return LifxOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        await self.async_set_unique_id(self._domain, raise_on_progress=False)

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm setup."""
        if user_input is None:
            self._set_confirm_only()
            return self.async_show_form(step_id="confirm")

        if self.source == config_entries.SOURCE_USER:
            # Get current discovered entries.
            in_progress = self._async_in_progress()

            if not (has_devices := in_progress):
                has_devices = await self._async_has_devices()

            if not has_devices:
                return self.async_abort(reason="no_devices_found")

            # Cancel the discovered one.
            for flow in in_progress:
                self.hass.config_entries.flow.async_abort(flow["flow_id"])

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        return self.async_create_entry(title=self._title, data={})

    async def async_step_homekit(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle a flow initialized by Homekit discovery."""
        if self._async_in_progress() or self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        await self.async_set_unique_id(self._domain)

        return await self.async_step_confirm()


class LifxOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the LIFX Options Flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the LIFX options flow."""
        self.config_entry = config_entry
        self.updated_config: dict[str, Any] = {}

    async def async_step_init(self, user_input=None):
        """Handle configuration initiated by a user."""
        return await self.async_step_discovery_options(user_input)

    async def async_step_discovery_options(self, user_input=None):
        """Handle custom discovery option dialog and store."""
        errors = {}
        current_config = self.config_entry.data

        """Manage the options."""
        if user_input is not None:
            self.updated_config = dict(current_config)
            self.updated_config[CONF_SCAN_INTERVAL] = user_input.get(CONF_SCAN_INTERVAL)
            self.updated_config[CONF_MSG_TIMEOUT] = user_input.get(CONF_MSG_TIMEOUT)
            self.updated_config[CONF_RETRY_COUNT] = user_input.get(CONF_RETRY_COUNT)
            self.updated_config[CONF_DEV_TIMEOUT] = user_input.get(CONF_DEV_TIMEOUT)
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.updated_config
            )
            return self.async_create_entry(title="", data=None)

        discovery_schema = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.data.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
            ): cv.positive_int,
            vol.Required(
                CONF_MSG_TIMEOUT,
                default=self.config_entry.data.get(
                    CONF_MSG_TIMEOUT, DEFAULT_MSG_TIMEOUT
                ),
            ): cv.positive_float,
            vol.Required(
                CONF_RETRY_COUNT,
                default=self.config_entry.data.get(
                    CONF_RETRY_COUNT, DEFAULT_RETRY_COUNT
                ),
            ): cv.positive_int,
            vol.Required(
                CONF_DEV_TIMEOUT,
                default=self.config_entry.data.get(
                    CONF_DEV_TIMEOUT, DEFAULT_DEV_TIMEOUT
                ),
            ): cv.positive_int,
        }

        return self.async_show_form(
            step_id="discovery_options",
            data_schema=vol.Schema(discovery_schema),
            errors=errors,
            last_step=True,
        )
