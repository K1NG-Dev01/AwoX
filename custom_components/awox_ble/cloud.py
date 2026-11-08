"""One-time download of mesh credentials and the device list from the AwoX account.

The lamps are never controlled through the cloud. Endpoints and app keys are the
public constants of the AwoX app, as used by fsaris/home-assistant-awox.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any
import uuid

import aiohttp

CONNECT_URL = "https://l4hparse-prod.awox.cloud/parse/"
HOME_CONTROL_URL = "https://l4hparse-hc-prod.awox.cloud/parse/"
APPLICATION_ID = "55O69FLtoxPt67LLwaHGpHmVWndhZGn9Wty8PLrJ"
CLIENT_KEY = "PyR3yV65rytEicteNlQHSVNpAGvCByOrsLiEqJtI"
TIMEOUT = aiohttp.ClientTimeout(total=20)


class CloudError(Exception):
    """The AwoX account could not be read."""


class CloudAuthError(CloudError):
    """Wrong e-mail or password."""


@dataclass(frozen=True)
class MeshDevice:
    mac: str
    mesh_id: int
    name: str
    type: str
    model: str
    manufacturer: str
    firmware: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MeshDevice:
        return cls(**{key: data[key] for key in cls.__dataclass_fields__})


async def fetch_mesh(
    session: aiohttp.ClientSession, username: str, password: str
) -> tuple[str, str, list[MeshDevice]]:
    """Return (mesh_name, mesh_password, devices)."""
    headers = {
        "x-parse-application-id": APPLICATION_ID,
        "x-parse-client-key": CLIENT_KEY,
        "x-parse-installation-id": str(uuid.uuid4()),
        "content-type": "application/json",
    }

    async def post(url: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        async with session.post(url, json=body, headers=headers, timeout=TIMEOUT) as resp:
            return resp.status, await resp.json(content_type=None)

    try:
        login = {"username": username, "password": password, "_method": "GET"}
        for base in (CONNECT_URL, HOME_CONTROL_URL):
            status, user = await post(f"{base}login", login)
            if status == 200:
                break
        else:
            raise CloudAuthError

        headers["x-parse-session-token"] = user["sessionToken"]
        owner = {"owner": {"__type": "Pointer", "className": "_User", "objectId": user["objectId"]}}

        async def fetch_class(name: str) -> list[dict[str, Any]]:
            status, data = await post(f"{base}classes/{name}", {"where": owner, "_method": "GET"})
            if status != 200:
                raise CloudError(f"loading {name} failed (HTTP {status})")
            return data.get("results", [])

        mesh = next((c for c in await fetch_class("Credential") if c.get("service") == "mesh"), None)
        if mesh is None or not mesh.get("client_id"):
            raise CloudError("account has no mesh credentials")
        raw_devices = await fetch_class("Device")
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError) as err:
        raise CloudError(type(err).__name__) from err

    devices = [
        MeshDevice(
            mac=d["macAddress"].upper(),
            mesh_id=int(d["address"]),
            name=d["displayName"],
            type=d["type"],
            model=d.get("modelName") or "unknown",
            manufacturer=d.get("vendor") or "unknown",
            firmware=d.get("version") or "unknown",
        )
        for d in raw_devices
        if str(d.get("type", "")).startswith(".ble.tlmesh")
        and d.get("address")
        and d.get("macAddress")
        and d.get("displayName")
    ]
    return mesh["client_id"], mesh["access_token"], devices
