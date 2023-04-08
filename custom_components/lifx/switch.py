from __future__ import annotations
from homeassistant.components.switch import ( SwitchEntity, SwitchEntityDescription, SwitchDeviceClass )

from typing import Any
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant import util

from .const import ( DOMAIN )
from .coordinator import LIFXUpdateCoordinator
from .entity import LIFXEntity
from .util import lifx_features

LIFX_SWITCH = SwitchEntityDescription(key="LIFX_SWITCH", name="LIFX Switch", device_class=SwitchDeviceClass.SWITCH)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LIFX from a config entry."""
    domain_data = hass.data[DOMAIN]
    coordinator: LIFXUpdateCoordinator = domain_data[entry.entry_id]
    if lifx_features(coordinator.device)["relays"]:
        async_add_entities([LIFXSwitch(coordinator, LIFX_SWITCH, 0), LIFXSwitch(coordinator, LIFX_SWITCH, 1), LIFXSwitch(coordinator, LIFX_SWITCH, 2), LIFXSwitch(coordinator, LIFX_SWITCH, 3)])


class LIFXSwitch(LIFXEntity, SwitchEntity):
    """Representation of a LIFX Switch"""

    def __init__(self, coordinator: LIFXUpdateCoordinator, description: SwitchEntityDescription, relay_index: int) -> None:
        super().__init__(coordinator)
        self.relay_index = relay_index
        self._attr_unique_id = f"{coordinator.serial_number}_{description.key}_{relay_index + 1}"
        self._attr_name = f"Relay {relay_index + 1}"
        self.entity_description = description
    
    @property
    def is_on(self) -> bool:
        return self.bulb.relays_power[self.relay_index]
    
    async def async_update(self) -> None:
        await self.coordinator.async_get_rpower()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_rpower(self.relay_index, True)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_rpower(self.relay_index, False)
        await self.coordinator.async_refresh()