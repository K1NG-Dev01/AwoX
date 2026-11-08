"""Shared base for AwoX mesh entities."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .cloud import MeshDevice
from .const import DOMAIN
from .mesh import AwoxMesh
from .protocol import LightStatus, capabilities


class AwoxEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, mesh: AwoxMesh, device: MeshDevice) -> None:
        self._mesh = mesh
        self._device = device
        self._caps = capabilities(device.type)
        self._attr_unique_id = device.mac.lower()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.mac.lower())},
            connections={(CONNECTION_BLUETOOTH, device.mac)},
            name=device.name,
            manufacturer=device.manufacturer,
            model=device.model,
            sw_version=device.firmware,
        )

    @property
    def available(self) -> bool:
        return self._mesh.is_available(self._device.mesh_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._mesh.subscribe(self._device.mesh_id, self._handle_status))
        self.async_on_remove(self._mesh.subscribe_connection(self.async_write_ha_state))

    @callback
    def _handle_status(self, status: LightStatus) -> None:
        self._apply_status(status)
        self.async_write_ha_state()

    def _apply_status(self, status: LightStatus) -> None:
        raise NotImplementedError
