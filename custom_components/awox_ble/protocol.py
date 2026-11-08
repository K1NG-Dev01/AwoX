"""Telink BLE mesh protocol as used by AwoX / EGLO devices.

Packet layout and crypto follow fsaris/home-assistant-awox (MIT), which in turn
builds on the reverse engineering in Leiaz/python-awox-mesh-light.
Pure Python, no I/O: everything here is unit tested without hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import struct
from typing import Literal

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PAIR_UUID = "00010203-0405-0607-0809-0a0b0c0d1914"
COMMAND_UUID = "00010203-0405-0607-0809-0a0b0c0d1912"
STATUS_UUID = "00010203-0405-0607-0809-0a0b0c0d1911"

C_POWER = 0xD0
C_COLOR = 0xE2
C_COLOR_BRIGHTNESS = 0xF2
C_WHITE_TEMPERATURE = 0xF0
C_WHITE_BRIGHTNESS = 0xF1
C_PRESET = 0xC8
C_SEQUENCE_COLOR_DURATION = 0xF5
C_SEQUENCE_FADE_DURATION = 0xF6
C_GET_STATUS = 0xDA
C_STATUS = 0xDB
C_NOTIFICATION = 0xDC

BROADCAST = 0xFFFF

PAIR_OK = 0x0D

KELVIN_WARM = 2700
KELVIN_COLD = 6500
WHITE_TEMPERATURE_MAX = 0x7F
WHITE_BRIGHTNESS_MIN, WHITE_BRIGHTNESS_MAX = 0x01, 0x7F
COLOR_BRIGHTNESS_MIN, COLOR_BRIGHTNESS_MAX = 0x0A, 0x64

Command = tuple[int, bytes]


class PairRejected(Exception):
    """The device refused the mesh name/password."""

    def __init__(self, code: int) -> None:
        super().__init__(f"pairing rejected (code {code:#04x})")
        self.code = code


def _encrypt(key: bytes, value: bytes) -> bytes:
    """AES-128-ECB with both key and block byte-reversed, as Telink does it."""
    k = bytes(reversed(key))
    v = bytes(reversed(value.ljust(16, b"\0")))
    encryptor = Cipher(algorithms.AES(k), modes.ECB()).encryptor()
    return bytes(reversed(encryptor.update(v) + encryptor.finalize()))


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def make_checksum(key: bytes, nonce: bytes, payload: bytes) -> bytes:
    check = _encrypt(key, (nonce + bytes([len(payload)])).ljust(16, b"\0"))
    for i in range(0, len(payload), 16):
        check = _encrypt(key, _xor(check, payload[i : i + 16].ljust(16, b"\0")))
    return check


def crypt_payload(key: bytes, nonce: bytes, payload: bytes) -> bytes:
    """Encrypt or decrypt (CTR-like, symmetric)."""
    base = bytearray(b"\0" + nonce).ljust(16, b"\0")
    out = bytearray()
    for i in range(0, len(payload), 16):
        out += _xor(_encrypt(key, bytes(base)), payload[i : i + 16])
        base[0] += 1
    return bytes(out)


def _reversed_mac(mac: str) -> bytes:
    return bytes(reversed(bytes.fromhex(mac.replace(":", ""))))


def make_pair_packet(name: bytes, password: bytes, rnd: bytes) -> bytes:
    name_pass = _xor(name.ljust(16, b"\0"), password.ljust(16, b"\0"))
    return b"\x0c" + rnd + _encrypt(rnd.ljust(16, b"\0"), name_pass)[0:8]


def make_session_key(name: bytes, password: bytes, rnd: bytes, reply: bytes) -> bytes:
    """Derive the session key from the full pair reply; raise PairRejected otherwise."""
    if not reply or reply[0] != PAIR_OK or len(reply) < 9:
        raise PairRejected(reply[0] if reply else -1)
    name_pass = _xor(name.ljust(16, b"\0"), password.ljust(16, b"\0"))
    return _encrypt(name_pass, rnd + reply[1:9])


def make_command_packet(
    key: bytes, mac: str, dest: int, cmd: int, data: bytes, seq: bytes | None = None
) -> bytes:
    seq = os.urandom(3) if seq is None else seq
    nonce = _reversed_mac(mac)[0:4] + b"\x01" + seq
    payload = (struct.pack("<H", dest) + bytes([cmd]) + b"\x60\x01" + data).ljust(15, b"\0")
    return seq + make_checksum(key, nonce, payload)[0:2] + crypt_payload(key, nonce, payload)


def decrypt_packet(key: bytes, mac: str, packet: bytes) -> bytes | None:
    """Decrypt a notification; None if it is too short or the checksum fails."""
    if len(packet) < 8:
        return None
    nonce = _reversed_mac(mac)[0:3] + packet[0:5]
    payload = crypt_payload(key, nonce, packet[7:])
    if make_checksum(key, nonce, payload)[0:2] != packet[5:7]:
        return None
    return packet[0:7] + payload


@dataclass(frozen=True)
class LightStatus:
    mesh_id: int
    on: bool
    color_mode: bool
    transition_mode: bool
    white_brightness: int
    white_temperature: int
    color_brightness: int
    rgb: tuple[int, int, int]


def _status(mesh_id: int, mode: int, white: bytes, color: bytes) -> LightStatus:
    return LightStatus(
        mesh_id=mesh_id,
        on=bool(mode & 1),
        color_mode=bool(mode >> 1 & 1),
        transition_mode=bool(mode >> 2 & 1),
        white_brightness=white[0],
        white_temperature=white[1],
        color_brightness=color[0],
        rgb=(color[1], color[2], color[3]),
    )


def parse_status(data: bytes) -> LightStatus | None:
    """Parse a decrypted status (0xdb) or notification (0xdc) packet."""
    if len(data) < 20:
        return None
    if data[7] == C_STATUS:
        return _status(data[3] | data[4] << 8, data[10], data[11:13], data[13:17])
    if data[7] == C_NOTIFICATION:
        return _status(data[10] | data[19] << 8, data[12], data[13:15], data[15:19])
    return None


def power(on: bool) -> Command:
    return C_POWER, b"\x01" if on else b"\x00"


def color(red: int, green: int, blue: int) -> Command:
    return C_COLOR, bytes([0x04, red, green, blue])


def color_brightness(value: int) -> Command:
    return C_COLOR_BRIGHTNESS, bytes([value])


def white_temperature(value: int) -> Command:
    return C_WHITE_TEMPERATURE, bytes([value])


def white_brightness(value: int) -> Command:
    return C_WHITE_BRIGHTNESS, bytes([value])


def preset(number: int) -> Command:
    return C_PRESET, bytes([number])


def sequence_color_duration(ms: int) -> Command:
    return C_SEQUENCE_COLOR_DURATION, struct.pack("<I", ms)


def sequence_fade_duration(ms: int) -> Command:
    return C_SEQUENCE_FADE_DURATION, struct.pack("<I", ms)


def request_status() -> Command:
    return C_GET_STATUS, b"\x10"


def _scale(value: float, src_min: float, src_max: float, dst_min: float, dst_max: float) -> int:
    value = min(max(value, src_min), src_max)
    return round(dst_min + (value - src_min) * (dst_max - dst_min) / (src_max - src_min))


def ha_to_white_brightness(brightness: int) -> int:
    return _scale(brightness, 1, 255, WHITE_BRIGHTNESS_MIN, WHITE_BRIGHTNESS_MAX)


def white_brightness_to_ha(value: int) -> int:
    return _scale(value, WHITE_BRIGHTNESS_MIN, WHITE_BRIGHTNESS_MAX, 1, 255)


def ha_to_color_brightness(brightness: int) -> int:
    return _scale(brightness, 1, 255, COLOR_BRIGHTNESS_MIN, COLOR_BRIGHTNESS_MAX)


def color_brightness_to_ha(value: int) -> int:
    return _scale(value, COLOR_BRIGHTNESS_MIN, COLOR_BRIGHTNESS_MAX, 1, 255)


def kelvin_to_device(kelvin: int) -> int:
    """Device scale runs the other way: 0x7f is warm, 0 is cold."""
    return _scale(kelvin, KELVIN_WARM, KELVIN_COLD, WHITE_TEMPERATURE_MAX, 0)


def device_to_kelvin(value: int) -> int:
    return _scale(value, 0, WHITE_TEMPERATURE_MAX, KELVIN_COLD, KELVIN_WARM)


@dataclass(frozen=True)
class Capabilities:
    kind: Literal["light", "plug", "other"]
    color: bool
    temperature: bool
    dimming: bool
    can_connect: bool


def capabilities(type_string: str) -> Capabilities:
    """Derive features from the AwoX type string, e.g. '.ble.tlmesh.light.switch.color.'."""
    if not type_string:
        return Capabilities("light", color=True, temperature=True, dimming=True, can_connect=True)
    parts = set(type_string.strip(".").split("."))
    if "plug" in parts:
        return Capabilities("plug", color=False, temperature=False, dimming=False, can_connect=False)
    if "light" not in parts:
        return Capabilities("other", color=False, temperature=False, dimming=False, can_connect=False)
    return Capabilities(
        "light",
        color="color" in parts,
        temperature="temperature" in parts,
        dimming="dimming" in parts,
        can_connect="bridge" not in parts,
    )


# ---- Plug Plus power meter ------------------------------------------------
# Found on hardware 2026-11-08: 0xea with data (0x10, subtype[, index]) makes the
# plug answer with 0xd8 + vendor 0x0160 + subtype. Subtype 0x13 = live values:
# u16 LE voltage x0.1 V, u16 LE power x0.1 W. 0x14/0x15/0x16 = history (unclear).

C_PLUG_REQUEST = 0xEA
C_PLUG_REPLY = 0xD8
PLUG_LIVE = 0x13


@dataclass(frozen=True)
class PlugMeasurement:
    mesh_id: int
    voltage: float
    power: float


def request_plug_live() -> Command:
    return C_PLUG_REQUEST, bytes([0x10, PLUG_LIVE])


def parse_plug(data: bytes) -> PlugMeasurement | None:
    """Parse a decrypted 0xd8 live-data reply of the Plug Plus."""
    if len(data) < 15 or data[7] != C_PLUG_REPLY or data[8:10] != b"\x60\x01" or data[10] != PLUG_LIVE:
        return None
    voltage, watts = struct.unpack_from("<HH", data, 11)
    return PlugMeasurement(data[3] | data[4] << 8, voltage / 10, watts / 10)
