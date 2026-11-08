"""Config flow for AwoX / EGLO BLE mesh.

The AwoX account is used once to read the mesh credentials and the device
list; the account password itself is never stored.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .cloud import CloudAuthError, CloudError, MeshDevice, fetch_mesh
from .const import CONF_DEVICES, CONF_MESH_NAME, CONF_MESH_PASSWORD, CONF_PREFERRED_MAC, CONF_RATED_WATTS, DOMAIN
from .energy import DEFAULT_RATED_W
from .protocol import capabilities

AUTO = "auto"
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required("username"): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required("password"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


class AwoxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _fetch(self, user_input: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str]]:
        try:
            name, password, devices = await fetch_mesh(
                async_get_clientsession(self.hass), user_input["username"], user_input["password"]
            )
        except CloudAuthError:
            return None, {"base": "invalid_auth"}
        except CloudError:
            return None, {"base": "cannot_connect"}
        if not devices:
            return None, {"base": "no_devices"}
        data = {
            CONF_MESH_NAME: name,
            CONF_MESH_PASSWORD: password,
            CONF_DEVICES: [d.as_dict() for d in devices],
        }
        return data, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._fetch(user_input)
            if data:
                await self.async_set_unique_id(hashlib.sha256(data[CONF_MESH_NAME].encode()).hexdigest()[:16])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="AvoX K1NG Dev", data=data)
        return self.async_show_form(step_id="user", data_schema=ACCOUNT_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._fetch(user_input)
            if data:
                return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
        return self.async_show_form(step_id="reauth_confirm", data_schema=ACCOUNT_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> AwoxOptionsFlow:
        return AwoxOptionsFlow()


class AwoxOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["preferred", "rated_watts", "add_device"])

    def _devices(self) -> list[MeshDevice]:
        return [MeshDevice.from_dict(d) for d in self.config_entry.data[CONF_DEVICES]]

    async def async_step_preferred(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            mac = user_input[CONF_PREFERRED_MAC]
            return self.async_create_entry(
                data={**self.config_entry.options, CONF_PREFERRED_MAC: None if mac == AUTO else mac}
            )

        options = [SelectOptionDict(value=AUTO, label="Automatic (best signal)")] + [
            SelectOptionDict(value=d.mac, label=d.name)
            for d in self._devices()
            if capabilities(d.type).can_connect
        ]
        current = self.config_entry.options.get(CONF_PREFERRED_MAC) or AUTO
        schema = vol.Schema(
            {
                vol.Required(CONF_PREFERRED_MAC, default=current): SelectSelector(
                    SelectSelectorConfig(options=options, translation_key="preferred")
                )
            }
        )
        return self.async_show_form(step_id="preferred", data_schema=schema)

    async def async_step_rated_watts(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Rated wattage per lamp for the estimated power sensors (fields named after the lamps)."""
        lamps = [d for d in self._devices() if capabilities(d.type).kind == "light"]
        current = self.config_entry.options.get(CONF_RATED_WATTS, {})
        if user_input is not None:
            rated = {d.mac: float(user_input[d.name]) for d in lamps if d.name in user_input}
            return self.async_create_entry(data={**self.config_entry.options, CONF_RATED_WATTS: rated})
        schema = vol.Schema(
            {
                vol.Required(d.name, default=current.get(d.mac, DEFAULT_RATED_W)): NumberSelector(
                    NumberSelectorConfig(min=0.5, max=200, step=0.5, unit_of_measurement="W", mode=NumberSelectorMode.BOX)
                )
                for d in lamps
            }
        )
        return self.async_show_form(step_id="rated_watts", data_schema=schema)

    async def async_step_add_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            mac = user_input["mac"].strip().upper().replace("-", ":")
            if not MAC_RE.match(mac):
                errors["mac"] = "invalid_mac"
            elif any(d.mac == mac for d in self._devices()):
                errors["base"] = "already_added"
            elif not await self.config_entry.runtime_data.probe(mac):
                errors["base"] = "other_mesh"
            else:
                device = MeshDevice(mac, int(user_input["mesh_id"]), user_input["name"], "", "unknown", "unknown", "unknown")
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_DEVICES: [*self.config_entry.data[CONF_DEVICES], device.as_dict()]},
                )
                return self.async_create_entry(data=dict(self.config_entry.options))

        schema = vol.Schema(
            {
                vol.Required("mac"): TextSelector(),
                vol.Required("mesh_id"): NumberSelector(
                    NumberSelectorConfig(min=1, max=32767, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Required("name"): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="add_device", data_schema=self.add_suggested_values_to_schema(schema, user_input), errors=errors
        )
