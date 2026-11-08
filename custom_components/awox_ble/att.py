"""Minimal GATT client on a raw L2CAP ATT socket (Linux, local adapters only).

Why not bleak/BlueZ: AwoX nodes never acknowledge the CCCD write that BlueZ
sends for start_notify, so BlueZ drops the link after the 30 s ATT timeout.
On our own ATT bearer we enable notifications with a write *command* (no
acknowledgement needed) and receive notifications directly on the socket.
Offers the subset of the BleakClient API that AwoxMesh uses.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import socket
import struct
from typing import Any

_LOGGER = logging.getLogger(__name__)

ATT_CID = 4
BDADDR_LE_PUBLIC = 1
BDADDR_LE_RANDOM = 2
REQUEST_TIMEOUT = 10.0
CONNECT_TIMEOUT = 10.0

OP_ERROR = 0x01
OP_READ_BY_TYPE_REQ, OP_READ_BY_TYPE_RSP = 0x08, 0x09
OP_READ_REQ, OP_READ_RSP = 0x0A, 0x0B
OP_WRITE_REQ, OP_WRITE_RSP = 0x12, 0x13
OP_WRITE_CMD = 0x52
OP_NOTIFY, OP_INDICATE, OP_CONFIRM = 0x1B, 0x1D, 0x1E
CHARACTERISTIC_DECLARATION = 0x2803
ERR_ATTRIBUTE_NOT_FOUND = 0x0A


class AttError(Exception):
    """ATT error response or a dead bearer."""


def address_type(ble_device: Any) -> int:
    """BlueZ reports the LE address type in the device properties."""
    details = getattr(ble_device, "details", None) or {}
    props = details.get("props", {}) if isinstance(details, dict) else {}
    return BDADDR_LE_RANDOM if props.get("AddressType") == "random" else BDADDR_LE_PUBLIC


def _uuid_str(raw: bytes) -> str:
    h = raw[::-1].hex() if len(raw) == 16 else f"0000{raw[::-1].hex()}00001000800000805f9b34fb"
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


class AttClient:
    def __init__(self, sock: socket.socket, address: str, disconnected: Callable[[AttClient], None]) -> None:
        self._sock = sock
        self.address = address
        self._disconnected_cb = disconnected
        self._closed = False
        self._reader: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._pending: tuple[bytes, int, asyncio.Future[bytes]] | None = None
        self._notify: dict[int, Callable[[Any, bytearray], None]] = {}
        self.handles: dict[str, int] = {}

    @classmethod
    async def connect(
        cls,
        address: str,
        adapter_address: str,
        addr_type: int,
        disconnected: Callable[[AttClient], None],
    ) -> AttClient:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        try:
            sock.setblocking(False)
            sock.bind((adapter_address, 0, ATT_CID, BDADDR_LE_PUBLIC))
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await asyncio.get_running_loop().sock_connect(sock, (address, 0, ATT_CID, addr_type))
        except BaseException:
            sock.close()
            raise
        client = cls(sock, address, disconnected)
        client.start()
        try:
            await client.discover()
        except BaseException:
            await client.disconnect()
            raise
        return client

    @property
    def is_connected(self) -> bool:
        return not self._closed

    def start(self) -> None:
        self._reader = asyncio.get_running_loop().create_task(self._read_loop(), name="awox_ble att reader")

    async def discover(self) -> None:
        start = 1
        while start <= 0xFFFF:
            try:
                rsp = await self._request(
                    struct.pack("<BHHH", OP_READ_BY_TYPE_REQ, start, 0xFFFF, CHARACTERISTIC_DECLARATION),
                    OP_READ_BY_TYPE_RSP,
                )
            except AttError as err:
                if err.args and err.args[0] == ERR_ATTRIBUTE_NOT_FOUND:
                    return
                raise
            size = rsp[1]
            if size < 7:  # handle, properties, value handle, 16-bit uuid at least
                return
            last = start
            for i in range(2, len(rsp) - size + 1, size):
                entry = rsp[i : i + size]
                value_handle = struct.unpack_from("<H", entry, 3)[0]
                self.handles[_uuid_str(entry[5:])] = value_handle
                last = value_handle
            if last < start:
                return
            start = last + 1

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        pdu = struct.pack("<BH", OP_WRITE_REQ if response else OP_WRITE_CMD, self._handle(uuid)) + bytes(data)
        if response:
            await self._request(pdu, OP_WRITE_RSP)
        else:
            await self._send(pdu)

    async def read_gatt_char(self, uuid: str) -> bytes:
        rsp = await self._request(struct.pack("<BH", OP_READ_REQ, self._handle(uuid)), OP_READ_RSP)
        return rsp[1:]

    async def start_notify(self, uuid: str, callback: Callable[[Any, bytearray], None]) -> None:
        handle = self._handle(uuid)
        self._notify[handle] = callback
        # CCCD directly follows the value handle on these devices; a write
        # command needs no acknowledgement, which the lamps never send.
        await self._send(struct.pack("<BH", OP_WRITE_CMD, handle + 1) + b"\x01\x00")

    async def disconnect(self) -> None:
        if self._reader and self._reader is not asyncio.current_task():
            self._reader.cancel()
        self._close()

    # ---- internals -----------------------------------------------------

    def _handle(self, uuid: str) -> int:
        try:
            return self.handles[uuid]
        except KeyError as err:
            raise AttError(f"characteristic {uuid} not found") from err

    async def _send(self, pdu: bytes) -> None:
        if self._closed:
            raise AttError("not connected")
        try:
            await asyncio.get_running_loop().sock_sendall(self._sock, pdu)
        except OSError as err:
            self._close()
            raise AttError(str(err)) from err

    async def _request(self, pdu: bytes, response_op: int) -> bytes:
        async with self._lock:
            future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
            self._pending = (pdu, response_op, future)
            try:
                await self._send(pdu)
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    rsp = await future
            finally:
                self._pending = None
        if rsp[0] == OP_ERROR:
            raise AttError(rsp[4] if len(rsp) > 4 else 0)
        return rsp

    async def _read_loop(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                pdu = await loop.sock_recv(self._sock, 512)
                if not pdu:
                    break
                try:
                    await self._dispatch(pdu)
                except AttError:
                    raise OSError("send failed") from None
                except Exception:  # noqa: BLE001 - a bad PDU or listener must not kill the link
                    _LOGGER.debug("Error handling ATT PDU %02x from %s", pdu[0], self.address, exc_info=True)
        except OSError as err:
            _LOGGER.debug("ATT link to %s closed: %s", self.address, err)
        finally:
            self._close()

    async def _dispatch(self, pdu: bytes) -> None:
        op = pdu[0]
        if op in (OP_NOTIFY, OP_INDICATE):
            if len(pdu) < 3:
                return
            if op == OP_INDICATE:
                await self._send(bytes([OP_CONFIRM]))
            handle = struct.unpack_from("<H", pdu, 1)[0]
            if cb := self._notify.get(handle):
                cb(handle, bytearray(pdu[3:]))
            return
        if self._pending and not self._pending[2].done() and self._answers(self._pending, pdu):
            self._pending[2].set_result(pdu)

    @staticmethod
    def _answers(pending: tuple[bytes, int, asyncio.Future[bytes]], pdu: bytes) -> bool:
        """Tell our response apart from ones meant for bluetoothd on the same link."""
        request, response_op, _ = pending
        if pdu[0] == OP_ERROR:
            return len(pdu) >= 5 and pdu[1] == request[0] and pdu[2:4] == request[1:3]
        if pdu[0] != response_op:
            return False
        if response_op == OP_READ_BY_TYPE_RSP:
            return len(pdu) >= 4 and struct.unpack_from("<H", pdu, 2)[0] >= struct.unpack_from("<H", request, 1)[0]
        return True

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._sock.close()
        if self._pending and not self._pending[2].done():
            self._pending[2].set_exception(AttError("disconnected"))
        self._disconnected_cb(self)
