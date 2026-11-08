"""Energy bookkeeping and the lamp power estimate (pure, unit tested)."""

from __future__ import annotations

from dataclasses import dataclass

STANDBY_W = 0.4  # typical standby of a Telink BLE lamp (radio stays on)
DEFAULT_RATED_W = 21.0  # EGLO panel 97629
MAX_GAP = 600.0  # seconds; longer gaps without data are not integrated


@dataclass
class EnergyMeter:
    """Left Riemann sum: the previous power holds until the next sample."""

    total_kwh: float = 0.0
    _power: float | None = None
    _time: float | None = None

    def update(self, power_w: float, now: float) -> float:
        if self._power is not None and self._time is not None:
            dt = now - self._time
            if 0 < dt <= MAX_GAP:
                self.total_kwh += self._power * dt / 3_600_000
            if dt < 0:
                return self.total_kwh
        self._power, self._time = power_w, now
        return self.total_kwh

    def reset_reference(self) -> None:
        self._power = self._time = None


def estimate_lamp_power(on: bool, brightness: int | None, rated_w: float) -> float:
    """Rated watts scaled by brightness (1-255) plus standby."""
    if not on:
        return STANDBY_W
    share = 1.0 if brightness is None else brightness / 255
    return rated_w * share + STANDBY_W
