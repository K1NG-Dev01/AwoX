"""Constants for the AwoX / EGLO BLE mesh integration."""

from datetime import timedelta

DOMAIN = "awox_ble"

CONF_MESH_NAME = "mesh_name"
CONF_MESH_PASSWORD = "mesh_password"
CONF_DEVICES = "devices"
CONF_PREFERRED_MAC = "preferred_mac"

STATUS_POLL_INTERVAL = timedelta(minutes=1)
UNAVAILABLE_AFTER = timedelta(seconds=150)

# Built-in colour programs (preset numbers 0-6). Names from the hardware test on
# 2026-11-08: 0 and 1 are rainbow cycles, 2-6 other colour programs.
EFFECTS: dict[str, int] = {
    "rainbow": 0,
    "rainbow_2": 1,
    **{f"colour_program_{n}": n for n in range(2, 7)},
}

CONF_RATED_WATTS = "rated_watts"
PLUG_POLL_INTERVAL = timedelta(seconds=15)
