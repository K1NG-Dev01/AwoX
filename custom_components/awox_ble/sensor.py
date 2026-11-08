"""Power sensors: measured by the Plug Plus, estimated for lamps.

The plug reports voltage, power and an energy counter itself. Lamps have no
meter, so their values are an estimate from the
rated wattage and brightness and are named "(estimated)".
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricPotential, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import AwoxConfigEntry
from . import protocol as p
from .cloud import MeshDevice
from .const import CONF_DEVICES, CONF_RATED_WATTS
from .energy import DEFAULT_RATED_W, EnergyMeter, estimate_lamp_power
from .entity import AwoxEntity
from .mesh import AwoxMesh


async def async_setup_entry(
    hass: HomeAssistant, entry: AwoxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    mesh = entry.runtime_data
    rated = entry.options.get(CONF_RATED_WATTS, {})
    entities: list[SensorEntity] = []
    for device in (MeshDevice.from_dict(d) for d in entry.data[CONF_DEVICES]):
        kind = p.capabilities(device.type).kind
        if kind == "plug":
            entities += [PlugPower(mesh, device), PlugVoltage(mesh, device), PlugEnergy(mesh, device)]
        elif kind == "light":
            watts = float(rated.get(device.mac, DEFAULT_RATED_W))
            entities += [LampPower(mesh, device, watts), LampEnergy(mesh, device, watts)]
    async_add_entities(entities)


def _now() -> float:
    return dt_util.utcnow().timestamp()


class _Sensor(AwoxEntity, SensorEntity):
    _key: str

    def __init__(self, mesh: AwoxMesh, device: MeshDevice) -> None:
        super().__init__(mesh, device)
        self._attr_translation_key = self._key
        self._attr_unique_id = f"{device.mac.lower()}_{self._key}"


class _PowerMixin:
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1


class _EnergyMixin:
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3


class _EnergySensor(_EnergyMixin, _Sensor, RestoreSensor):
    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._meter = EnergyMeter()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) and last.native_value is not None:
            self._meter.total_kwh = float(last.native_value)
            self._attr_native_value = self._meter.total_kwh

    def _record(self, power_w: float) -> None:
        self._attr_native_value = round(self._meter.update(power_w, _now()), 6)

    @property
    def available(self) -> bool:
        ok = super().available
        if not ok:
            self._meter.reset_reference()
        return ok


# ---- Plug Plus (measured) ------------------------------------------------


class _PlugSensor(_Sensor):
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._mesh.subscribe_plug(self._device.mesh_id, self._handle_measurement))

    _reading: type = p.PlugMeasurement

    @callback
    def _handle_measurement(self, measurement: p.PlugMeasurement | p.PlugEnergy) -> None:
        if isinstance(measurement, self._reading):
            self._apply_measurement(measurement)
            self.async_write_ha_state()

    def _apply_measurement(self, measurement) -> None:
        raise NotImplementedError

    def _apply_status(self, status: p.LightStatus) -> None:
        """On/off status carries no measurement."""


class PlugPower(_PowerMixin, _PlugSensor):
    _key = "power"

    def _apply_measurement(self, measurement: p.PlugMeasurement) -> None:
        self._attr_native_value = measurement.power


class PlugVoltage(_PlugSensor):
    _key = "voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def _apply_measurement(self, measurement: p.PlugMeasurement) -> None:
        self._attr_native_value = measurement.voltage


class PlugEnergy(_EnergyMixin, _PlugSensor):
    """The plug's own energy counter (may reset daily; total_increasing handles that)."""

    _key = "energy"
    _reading = p.PlugEnergy

    def _apply_measurement(self, measurement: p.PlugEnergy) -> None:
        self._attr_native_value = measurement.kwh


# ---- Lamps (estimated) ---------------------------------------------------


def _ha_brightness(status: p.LightStatus, caps: p.Capabilities) -> int:
    if status.color_mode and caps.color:
        return p.color_brightness_to_ha(status.color_brightness)
    return p.white_brightness_to_ha(status.white_brightness)


class _LampSensor(_Sensor):
    def __init__(self, mesh: AwoxMesh, device: MeshDevice, rated_w: float) -> None:
        super().__init__(mesh, device)
        self._rated_w = rated_w
        self._attr_extra_state_attributes = {"rated_power_w": rated_w}

    def _estimate(self, status: p.LightStatus) -> float:
        brightness = _ha_brightness(status, self._caps) if self._caps.dimming or self._caps.color else None
        return estimate_lamp_power(status.on, brightness, self._rated_w)


class LampPower(_PowerMixin, _LampSensor):
    _key = "estimated_power"

    def _apply_status(self, status: p.LightStatus) -> None:
        self._attr_native_value = round(self._estimate(status), 2)


class LampEnergy(_EnergySensor, _LampSensor):
    _key = "estimated_energy"

    def _apply_status(self, status: p.LightStatus) -> None:
        self._record(self._estimate(status))
