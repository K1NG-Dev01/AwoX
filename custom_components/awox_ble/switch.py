"""EGLO Plug Plus as a switch (commands go through the mesh)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AwoxConfigEntry
from .cloud import MeshDevice
from .const import CONF_DEVICES
from .entity import AwoxEntity
from .protocol import LightStatus, capabilities, power


async def async_setup_entry(
    hass: HomeAssistant, entry: AwoxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    devices = [MeshDevice.from_dict(d) for d in entry.data[CONF_DEVICES]]
    async_add_entities(
        AwoxSwitch(entry.runtime_data, d) for d in devices if capabilities(d.type).kind == "plug"
    )


class AwoxSwitch(AwoxEntity, SwitchEntity):
    _attr_name = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._mesh.send(self._device.mesh_id, power(True))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._mesh.send(self._device.mesh_id, power(False))
        self._attr_is_on = False
        self.async_write_ha_state()

    def _apply_status(self, status: LightStatus) -> None:
        self._attr_is_on = status.on
