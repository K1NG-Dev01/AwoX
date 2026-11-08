"""Persistent connection to the mesh through one node, with failover.

One lamp with good signal acts as the entry point; commands for every device
are sent through it. If it goes away (e.g. switched off at the wall) the next
best lamp takes over. A lamp that stays connected but stops forwarding mesh
traffic is replaced as well. The Plug Plus is never used: it is the Alexa bridge.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import logging
import os
import time
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import protocol as p
from .att import AttClient, address_type
from .cloud import MeshDevice
from .const import PLUG_POLL_INTERVAL, STATUS_POLL_INTERVAL, UNAVAILABLE_AFTER

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 15.0
# Many AwoX nodes never answer the CCCD write behind start_notify; BlueZ then
# drops the link after the 30 s ATT timeout. Such nodes are useless as entry point.
NOTIFY_TIMEOUT = 5.0
CONNECT_WAIT = 30.0  # long enough for a failover across several dead nodes
DOUBLE_SEND_DELAY = 0.08
VERIFY_TIMEOUT = 1.5
RETRY_DELAYS = (2, 5, 10, 30, 60)
FAILED_PENALTY = 60.0
STALE_AFTER = 20.0  # seconds without an advertisement: probably powered off
# Connected, but no packet from any other device for this long: the entry lamp
# has stopped relaying (seen 2026-11-08). Status poll 60 s, plug poll 15 s.
RELAY_TIMEOUT = 150.0
NEVER = datetime(1970, 1, 1, tzinfo=UTC)

Connector = Callable[[BLEDevice, Callable[[BleakClient], None]], Awaitable[Any]]


async def _default_connector(device: BLEDevice, disconnected: Callable[[BleakClient], None]) -> BleakClient:
    return await establish_connection(
        BleakClientWithServiceCache,
        device,
        device.address,
        disconnected_callback=disconnected,
        max_attempts=2,
    )



async def _auto_connector(hass: HomeAssistant, device: BLEDevice, disconnected: Callable[[Any], None]) -> Any:
    """Own ATT bearer on local Linux adapters, bleak (e.g. ESPHome proxies) otherwise."""
    info = bluetooth.async_last_service_info(hass, device.address, connectable=True)
    scanner = bluetooth.async_scanner_by_source(hass, info.source) if info else None
    if str(getattr(scanner, "adapter", "")).startswith("hci"):
        return await AttClient.connect(device.address, info.source, address_type(device), disconnected)
    return await _default_connector(device, disconnected)

class AwoxMesh:
    """Connection manager and command sender for one AwoX mesh."""

    def __init__(
        self,
        hass: HomeAssistant,
        mesh_name: str,
        mesh_password: str,
        devices: list[MeshDevice],
        preferred_mac: str | None = None,
        connector: Connector | None = None,
        on_auth_failed: Callable[[], None] | None = None,
    ) -> None:
        self._hass = hass
        self._name = mesh_name.encode()
        self._password = mesh_password.encode()
        self._devices = {d.mesh_id: d for d in devices}
        self._mesh_ids = {d.mac: d.mesh_id for d in devices}
        self._preferred = preferred_mac.upper() if preferred_mac else None
        self._connector = connector or (lambda device, cb: _auto_connector(hass, device, cb))
        self._on_auth_failed = on_auth_failed

        self._client: Any = None
        self._key: bytes | None = None
        self._entry_mac: str | None = None
        self._lock = asyncio.Lock()
        self._connected = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._stopping = False
        self._loop_task: asyncio.Task | None = None
        self._unsub_poll: CALLBACK_TYPE | None = None
        self._failed_at: dict[str, float] = {}
        self._good: set[str] = set()
        self._power_gen: dict[int, int] = {}
        self._silent: set[str] = set()
        self._warned = False
        self._relayed_at = 0.0
        self._connected_at = 0.0
        self._reached: set[int] = set()
        self._coverage: dict[str, int] = {}  # entry mac -> devices it reached

        self._unsub_plug_poll: CALLBACK_TYPE | None = None
        self._plugs = [d.mesh_id for d in devices if p.capabilities(d.type).kind == "plug"]
        self._plug_listeners: dict[int, list[Callable[[p.PlugMeasurement | p.PlugEnergy], None]]] = {}
        self._listeners: dict[int, list[Callable[[p.LightStatus], None]]] = {}
        self._connection_listeners: list[Callable[[], None]] = []
        self._last_seen: dict[int, datetime] = {}
        self._baseline: datetime | None = None
        self._latest: dict[int, tuple[float, p.LightStatus]] = {}
        self._status_event: dict[int, asyncio.Event] = {}

    # ---- public API ----------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    async def start(self) -> None:
        self._loop_task = self._hass.async_create_background_task(self._connection_loop(), "awox_ble connection")
        self._unsub_poll = async_track_time_interval(self._hass, self._async_poll, STATUS_POLL_INTERVAL)
        if self._plugs:
            self._unsub_plug_poll = async_track_time_interval(self._hass, self._async_poll_plugs, PLUG_POLL_INTERVAL)

    async def stop(self) -> None:
        self._stopping = True
        for unsub in (self._unsub_poll, self._unsub_plug_poll):
            if unsub:
                unsub()
        self._unsub_poll = self._unsub_plug_poll = None
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        client = self._client
        self._set_disconnected()
        if client is not None:
            await self._safe_disconnect(client)

    async def async_wait_connected(self, timeout: float) -> bool:
        try:
            async with asyncio.timeout(timeout):
                await self._connected.wait()
        except TimeoutError:
            return False
        return True

    def subscribe(self, mesh_id: int, cb: Callable[[p.LightStatus], None]) -> Callable[[], None]:
        self._listeners.setdefault(mesh_id, []).append(cb)
        return lambda: self._listeners[mesh_id].remove(cb)

    def subscribe_plug(self, mesh_id: int, cb: Callable[[p.PlugMeasurement | p.PlugEnergy], None]) -> Callable[[], None]:
        self._plug_listeners.setdefault(mesh_id, []).append(cb)
        return lambda: self._plug_listeners[mesh_id].remove(cb)

    def subscribe_connection(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._connection_listeners.append(cb)
        return lambda: self._connection_listeners.remove(cb)

    def is_available(self, mesh_id: int) -> bool:
        if not self.connected:
            return False
        seen = self._last_seen.get(mesh_id, self._baseline)
        return seen is not None and dt_util.utcnow() - seen < UNAVAILABLE_AFTER

    async def send(self, mesh_id: int, command: p.Command) -> None:
        """Send a command (twice); for power commands, verify via status in the background."""
        start = asyncio.get_running_loop().time()
        await self._write(mesh_id, command)
        if command[0] == p.C_POWER:
            gen = self._power_gen[mesh_id] = self._power_gen.get(mesh_id, 0) + 1
            self._hass.async_create_task(
                self._verify(mesh_id, command, start, gen), "awox_ble verify", eager_start=False
            )

    async def probe(self, mac: str) -> bool:
        """Check whether a device accepts this mesh's credentials."""
        info = bluetooth.async_last_service_info(self._hass, mac.upper(), connectable=True)
        if info is None:
            return False
        client = None
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                client = await self._connector(info.device, lambda _c: None)
                await self._pair(client)
        except Exception as err:  # noqa: BLE001 - any failure means "not usable"
            _LOGGER.debug("Probe of %s failed: %s", mac, type(err).__name__)
            return False
        finally:
            if client is not None:
                await self._safe_disconnect(client)
        return True

    # ---- connection ----------------------------------------------------

    async def _connection_loop(self) -> None:
        attempt = 0
        while not self._stopping:
            if await self._connect_any():
                attempt = 0
                await self._disconnected.wait()
                continue
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            attempt += 1
            await asyncio.sleep(delay)

    def _candidates(self) -> list[tuple[str, Any]]:
        now = asyncio.get_running_loop().time()
        found = []
        for device in self._devices.values():
            if not p.capabilities(device.type).can_connect:
                continue
            info = bluetooth.async_last_service_info(self._hass, device.mac, connectable=True)
            if info is None:
                continue
            recently_failed = now - self._failed_at.get(device.mac, -FAILED_PENALTY) < FAILED_PENALTY
            seen = getattr(info, "time", None)
            stale = seen is not None and time.monotonic() - seen > STALE_AFTER
            found.append(
                (
                    (
                        stale,
                        device.mac in self._silent,
                        recently_failed,
                        device.mac != self._preferred,
                        -self._coverage.get(device.mac, len(self._devices)),
                        device.mac not in self._good,
                        -info.rssi,
                    ),
                    device.mac,
                    info.device,
                )
            )
        return [(mac, ble) for _, mac, ble in sorted(found, key=lambda f: f[0])]

    async def _connect_any(self) -> bool:
        rejected = 0
        candidates = self._candidates()
        for mac, ble_device in candidates:
            if self._stopping:
                return False
            client = None
            started = asyncio.get_running_loop().time()
            try:
                async with asyncio.timeout(CONNECT_TIMEOUT):
                    _LOGGER.debug("Connecting via %s", mac)
                    client = await self._connector(ble_device, self._on_disconnect)
                    _LOGGER.debug("BLE link to %s after %.1f s", mac, asyncio.get_running_loop().time() - started)
                    key = await self._pair(client)
                    _LOGGER.debug("Paired with %s after %.1f s", mac, asyncio.get_running_loop().time() - started)
                    self._client, self._key, self._entry_mac = client, key, mac
                    try:
                        async with asyncio.timeout(NOTIFY_TIMEOUT):
                            await client.start_notify(p.STATUS_UUID, self._on_notify)
                    except TimeoutError:
                        self._silent.add(mac)
                        raise
                    _LOGGER.debug("Notifications on after %.1f s", asyncio.get_running_loop().time() - started)
                    await client.write_gatt_char(p.STATUS_UUID, b"\x01", response=False)
                    _LOGGER.debug("Status enabled after %.1f s", asyncio.get_running_loop().time() - started)
            except asyncio.CancelledError:
                if client is not None and client is not self._client:
                    await self._safe_disconnect(client)
                raise
            except Exception as err:  # noqa: BLE001 - try the next node on any failure
                rejected += isinstance(err, p.PairRejected)
                self._failed_at[mac] = asyncio.get_running_loop().time()
                self._client = self._key = self._entry_mac = None
                _LOGGER.debug("Connecting via %s failed after %.1f s: %r", mac, asyncio.get_running_loop().time() - started, err)
                if client is not None:
                    await self._safe_disconnect(client)
                continue

            self._warned = False
            self._relayed_at = asyncio.get_running_loop().time()
            self._connected_at = self._relayed_at
            self._reached = set()
            self._failed_at.pop(mac, None)
            self._good.add(mac)
            if self._baseline is None:
                self._baseline = dt_util.utcnow()
            self._disconnected.clear()
            self._connected.set()
            _LOGGER.info("Connected to AwoX mesh via %s", mac)
            self._notify_connection()
            self._hass.async_create_task(self._request_all(), "awox_ble status", eager_start=False)
            return True

        if not self._warned:
            self._warned = True
            _LOGGER.warning("Could not connect to the AwoX mesh (%d candidates); retrying", len(candidates))
        if candidates and rejected == len(candidates) and self._on_auth_failed:
            self._on_auth_failed()
        return False

    async def _pair(self, client: Any) -> bytes:
        rnd = os.urandom(8)
        await client.write_gatt_char(p.PAIR_UUID, p.make_pair_packet(self._name, self._password, rnd), response=True)
        reply = bytes(await client.read_gatt_char(p.PAIR_UUID))
        return p.make_session_key(self._name, self._password, rnd, reply)

    @callback
    def _on_disconnect(self, client: Any) -> None:
        if client is self._client:
            _LOGGER.info("AwoX mesh connection via %s lost", self._entry_mac)
            if self._entry_mac:
                self._failed_at[self._entry_mac] = asyncio.get_running_loop().time()
                if (lost := self._mesh_ids.get(self._entry_mac)) is not None:
                    self._mark_unavailable(lost)
            self._set_disconnected()

    def _set_disconnected(self) -> None:
        was_connected = self.connected
        self._client = self._key = self._entry_mac = None
        self._connected.clear()
        self._disconnected.set()
        if was_connected:
            self._notify_connection()

    async def _safe_disconnect(self, client: Any) -> None:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    # ---- sending -------------------------------------------------------

    async def _write(self, mesh_id: int, command: p.Command) -> None:
        cmd, data = command
        for attempt in range(2):
            if not await self.async_wait_connected(CONNECT_WAIT):
                raise HomeAssistantError("AwoX mesh not connected")
            async with self._lock:
                client, key, mac = self._client, self._key, self._entry_mac
                if client is None:
                    continue
                try:
                    await client.write_gatt_char(
                        p.COMMAND_UUID, p.make_command_packet(key, mac, mesh_id, cmd, data), response=False
                    )
                    await asyncio.sleep(DOUBLE_SEND_DELAY)
                    await client.write_gatt_char(
                        p.COMMAND_UUID, p.make_command_packet(key, mac, mesh_id, cmd, data), response=False
                    )
                    return
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Write via %s failed: %s", mac, type(err).__name__)
                    self._failed_at[mac] = asyncio.get_running_loop().time()
                    self._set_disconnected()
                    self._hass.async_create_task(self._safe_disconnect(client), eager_start=False)
            if attempt:
                break
        raise HomeAssistantError("Sending to the AwoX mesh failed")

    async def _confirmed(self, mesh_id: int, start: float, expected: bool) -> bool:
        """Wait up to VERIFY_TIMEOUT for a status of mesh_id newer than start with on == expected."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + VERIFY_TIMEOUT
        while True:
            latest = self._latest.get(mesh_id)
            if latest and latest[0] >= start and latest[1].on == expected:
                return True
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            event = self._status_event.setdefault(mesh_id, asyncio.Event())
            try:
                async with asyncio.timeout(remaining):
                    await event.wait()
            except TimeoutError:
                return False

    async def _verify(self, mesh_id: int, command: p.Command, start: float, gen: int) -> None:
        expected = command[1] == b"\x01"

        def superseded() -> bool:
            return self._power_gen.get(mesh_id) != gen

        try:
            await self._write(mesh_id, p.request_status())
            if await self._confirmed(mesh_id, start, expected) or superseded():
                return
            _LOGGER.debug("No confirmation from mesh id %d, sending again", mesh_id)
            await self._write(mesh_id, command)
            await self._write(mesh_id, p.request_status())
            if await self._confirmed(mesh_id, start, expected) or superseded():
                return
        except HomeAssistantError:
            return
        _LOGGER.debug("Mesh id %d does not answer; marking unavailable", mesh_id)
        self._mark_unavailable(mesh_id)
        self._notify_connection()

    def _mark_unavailable(self, mesh_id: int) -> None:
        self._last_seen[mesh_id] = NEVER

    async def _request_all(self) -> None:
        try:
            await self._write(p.BROADCAST, p.request_status())
        except HomeAssistantError:
            pass
        await self._request_plugs()

    async def _request_plugs(self) -> None:
        for mesh_id in self._plugs:
            try:
                await self._write(mesh_id, p.request_plug_live())
                await self._write(mesh_id, p.request_plug_energy())
            except HomeAssistantError:
                return

    async def _async_poll_plugs(self, _now: datetime) -> None:
        if self.connected:
            await self._request_plugs()

    def _advertising(self, mac: str) -> bool:
        info = bluetooth.async_last_service_info(self._hass, mac, connectable=True)
        seen = getattr(info, "time", None) if info else None
        return seen is not None and time.monotonic() - seen <= STALE_AFTER

    def _check_relay(self) -> None:
        """Replace an entry lamp that forwards nothing, or misses devices that are powered.

        A device that advertises but never answers through this entry lamp is out
        of its reach in the mesh. Every lamp is then tried once; the one reaching
        the most devices wins (see the coverage key in _candidates).
        """
        now = asyncio.get_running_loop().time()
        client, mac = self._client, self._entry_mac
        if len(self._devices) < 2 or mac is None or now - self._connected_at < RELAY_TIMEOUT:
            return
        if now - self._relayed_at >= RELAY_TIMEOUT:
            _LOGGER.info("No answer from the mesh via %s; switching entry lamp", mac)
            self._failed_at[mac] = now
            self._hass.async_create_task(self._safe_disconnect(client), eager_start=False)
            return
        entry_id = self._mesh_ids.get(mac)
        self._coverage[mac] = len(self._reached)
        missing = [
            d.name for d in self._devices.values()
            if d.mesh_id != entry_id and d.mesh_id not in self._reached and self._advertising(d.mac)
        ]
        if not missing:
            return
        better = [
            d.mac for d in self._devices.values()
            if p.capabilities(d.type).can_connect and d.mac != mac and self._advertising(d.mac)
            and self._coverage.get(d.mac, len(self._devices)) > self._coverage[mac]
        ]
        if better:
            _LOGGER.info("%s not reachable via %s; trying another entry lamp", ", ".join(missing), mac)
            self._hass.async_create_task(self._safe_disconnect(client), eager_start=False)

    async def _async_poll(self, _now: datetime) -> None:
        if self.connected:
            self._check_relay()
            await self._request_all()
        self._notify_connection()

    def _heard_from(self, mesh_id: int) -> None:
        self._last_seen[mesh_id] = dt_util.utcnow()
        if mesh_id != self._mesh_ids.get(self._entry_mac or ""):
            self._relayed_at = asyncio.get_running_loop().time()
            self._reached.add(mesh_id)

    # ---- receiving -----------------------------------------------------

    @callback
    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        key, mac = self._key, self._entry_mac
        if key is None or mac is None:
            return
        plain = p.decrypt_packet(key, mac, bytes(data))
        if plain and (measurement := p.parse_plug(plain)) and measurement.mesh_id in self._devices:
            self._heard_from(measurement.mesh_id)
            _LOGGER.debug("Plug %d: %s", measurement.mesh_id, measurement)
            for cb in list(self._plug_listeners.get(measurement.mesh_id, ())):
                cb(measurement)
            return
        status = p.parse_status(plain) if plain else None
        if status is None or status.mesh_id not in self._devices:
            if plain and status is None:
                _LOGGER.debug("Unknown mesh packet cmd=%02x raw=%s", plain[7], plain[7:].hex())
            else:
                _LOGGER.debug("Ignoring mesh packet (%s)", "unknown device" if status else "unreadable")
            return
        _LOGGER.debug("Status from %d: on=%s raw=%s", status.mesh_id, status.on, plain[7:].hex())
        self._heard_from(status.mesh_id)
        self._latest[status.mesh_id] = (asyncio.get_running_loop().time(), status)
        if event := self._status_event.pop(status.mesh_id, None):
            event.set()
        for cb in list(self._listeners.get(status.mesh_id, ())):
            cb(status)

    def _notify_connection(self) -> None:
        for cb in list(self._connection_listeners):
            cb()
