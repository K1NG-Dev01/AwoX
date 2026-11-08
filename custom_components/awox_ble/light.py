"""AwoX / EGLO mesh lights."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AwoxConfigEntry
from . import protocol as p
from .cloud import MeshDevice
from .const import CONF_DEVICES, EFFECTS
from .entity import AwoxEntity
from .mesh import AwoxMesh


async def async_setup_entry(
    hass: HomeAssistant, entry: AwoxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    devices = [MeshDevice.from_dict(d) for d in entry.data[CONF_DEVICES]]
    async_add_entities(
        AwoxLight(entry.runtime_data, d) for d in devices if p.capabilities(d.type).kind == "light"
    )


class AwoxLight(AwoxEntity, LightEntity):
    _attr_name = None
    _attr_translation_key = "awox_light"
    _attr_min_color_temp_kelvin = p.KELVIN_WARM
    _attr_max_color_temp_kelvin = p.KELVIN_COLD

    def __init__(self, mesh: AwoxMesh, device: MeshDevice) -> None:
        super().__init__(mesh, device)
        modes: set[ColorMode] = set()
        if self._caps.color:
            modes.add(ColorMode.RGB)
        if self._caps.temperature:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes:
            modes.add(self._white_mode)
        self._attr_supported_color_modes = modes
        self._attr_color_mode = self._white_mode if self._white_mode in modes else ColorMode.RGB
        if self._caps.color:
            self._attr_supported_features = LightEntityFeature.EFFECT
            self._attr_effect_list = list(EFFECTS)

    @property
    def _white_mode(self) -> ColorMode:
        if self._caps.temperature:
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS if self._caps.dimming else ColorMode.ONOFF

    async def _send(self, command: p.Command) -> None:
        await self._mesh.send(self._device.mesh_id, command)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if not self.is_on or not kwargs:
            await self._send(p.power(True))
            self._attr_is_on = True

        if (effect := kwargs.get(ATTR_EFFECT)) in EFFECTS:
            await self._send(p.preset(EFFECTS[effect]))
            self._attr_effect = effect
            self._attr_color_mode = ColorMode.RGB
        elif (rgb := kwargs.get(ATTR_RGB_COLOR)) is not None:
            await self._send(p.color(*rgb))
            self._attr_rgb_color = tuple(rgb)
            self._attr_color_mode = ColorMode.RGB
            self._attr_effect = None
            if brightness is not None:
                await self._send(p.color_brightness(p.ha_to_color_brightness(brightness)))
        elif (kelvin := kwargs.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
            await self._send(p.white_temperature(p.kelvin_to_device(kelvin)))
            self._attr_color_temp_kelvin = kelvin
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_effect = None
            if brightness is not None:
                await self._send(p.white_brightness(p.ha_to_white_brightness(brightness)))
        elif brightness is not None:
            if self._attr_color_mode == ColorMode.RGB:
                await self._send(p.color_brightness(p.ha_to_color_brightness(brightness)))
            elif self._attr_color_mode != ColorMode.ONOFF:
                await self._send(p.white_brightness(p.ha_to_white_brightness(brightness)))

        if brightness is not None:
            self._attr_brightness = brightness
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(p.power(False))
        self._attr_is_on = False
        self.async_write_ha_state()

    def _apply_status(self, status: p.LightStatus) -> None:
        self._attr_is_on = status.on
        if status.color_mode and self._caps.color:
            self._attr_color_mode = ColorMode.RGB
            self._attr_brightness = p.color_brightness_to_ha(status.color_brightness)
            self._attr_rgb_color = status.rgb
        else:
            self._attr_color_mode = self._white_mode
            self._attr_brightness = p.white_brightness_to_ha(status.white_brightness)
            self._attr_color_temp_kelvin = p.device_to_kelvin(status.white_temperature)
        if not status.transition_mode:
            self._attr_effect = None
