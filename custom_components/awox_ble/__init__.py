"""AwoX / EGLO BLE mesh (local)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .cloud import MeshDevice
from .const import CONF_DEVICES, CONF_MESH_NAME, CONF_MESH_PASSWORD, CONF_PREFERRED_MAC
from .mesh import AwoxMesh

PLATFORMS = [Platform.LIGHT, Platform.SENSOR, Platform.SWITCH]

type AwoxConfigEntry = ConfigEntry[AwoxMesh]


async def async_setup_entry(hass: HomeAssistant, entry: AwoxConfigEntry) -> bool:
    mesh = AwoxMesh(
        hass,
        entry.data[CONF_MESH_NAME],
        entry.data[CONF_MESH_PASSWORD],
        [MeshDevice.from_dict(d) for d in entry.data[CONF_DEVICES]],
        preferred_mac=entry.options.get(CONF_PREFERRED_MAC),
        on_auth_failed=lambda: entry.async_start_reauth(hass),
    )
    await mesh.start()
    entry.runtime_data = mesh
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AwoxConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: AwoxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
