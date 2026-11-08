# AvoX K1NG Dev

Fast, local Home Assistant control for AwoX and EGLO Bluetooth mesh lights (EGLO connect, AwoX HomeControl / SmartLIGHT, Telink mesh based).

[Deutsche Anleitung](README.de.md)

- Switch, dim, colour (RGB), colour temperature (2700–6500 K) and the built-in colour programs, typically in well under a second.
- One persistent connection to the lamp with the best signal; the rest of the mesh is reached through it. If that lamp loses power, the next one takes over automatically.
- Lamps that are switched off at the wall show up as *unavailable* within about 2–3 minutes and come back on their own.
- The EGLO Plug Plus appears as a switch with measured power (W), voltage (V) and energy (kWh, for the energy dashboard). It is never used as connection point, so Alexa keeps working through it.
- Lamps get "Power (estimated)" and "Energy (estimated)": rated power × brightness + 0.4 W standby. This is an estimate, not a measurement.
- Scenes, scripts and automations are built with Home Assistant as usual.

## Requirements

- Home Assistant 2026.3 or newer.
- A Bluetooth adapter on the Home Assistant host (recommended), or an ESPHome Bluetooth proxy (works, but see *Limitations*).
- An AwoX / EGLO account in which the lamps are paired.

## Installation

**HACS:** HACS → ⋮ → *Custom repositories* → add this repository as *Integration* → install *AvoX K1NG Dev* → restart Home Assistant.

**Manual:** copy `custom_components/awox_ble` into your `config/custom_components/` folder and restart Home Assistant.

## Setup

*Settings → Devices & services → Add integration → AvoX K1NG Dev*, then sign in with the account from the app. The account is only used once to download the mesh credentials and the device list; the password is not stored and the lamps are controlled locally.

Options:

- **Entry lamp:** pin the lamp Home Assistant connects to (default: best signal).
- **Rated power of the lamps:** watts at full brightness per lamp for the estimate (default 21 W).
- **Add a device by MAC address:** for a lamp that is missing from the account list.

If you later re-pair the lamps with a different account, Home Assistant asks you to sign in again.

## Effects

| Effect | Preset |
|---|---|
| Rainbow | 0 |
| Rainbow 2 | 1 |
| Colour program 2–6 | 2–6 |

## How it works

The protocol (pairing, session key, encrypted command packets) is the Telink mesh protocol as implemented by [fsaris/home-assistant-awox](https://github.com/fsaris/home-assistant-awox) (MIT), which builds on the reverse engineering in [Leiaz/python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light). Thanks to both.

AwoX nodes never acknowledge the notification subscription that BlueZ sends, so BlueZ drops the connection after 30 seconds. On a local adapter this integration therefore talks to the lamp over its own small ATT client on an L2CAP socket and enables status reports with a write command. Through ESPHome proxies it uses Home Assistant's normal Bluetooth stack.

## Limitations

- Through an ESPHome Bluetooth proxy, status reports may not work reliably (see above); switching still does.
- Pairing new lamps, firmware updates and the mesh itself are managed in the AwoX / EGLO app.
- The Plug Plus energy counter is read from the plug itself (0.1 Wh resolution). Whether it resets daily is still unknown; the energy dashboard handles both cases.

## Troubleshooting

Enable debug logging on the integration page (⋮ → *Enable debug logging*), reproduce the problem and attach the log to an issue. Credentials are never written to the log.

## License

© 2026 Henrik. All rights reserved. Free to install and use privately; copying, modifying and redistributing are not allowed. See [LICENSE](LICENSE).
