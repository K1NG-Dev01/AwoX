# Installation guide – AvoX K1NG Dev

Step by step from zero to your first lamp in Home Assistant and Alexa. [Deutsch](INSTALL.de.md)

## 1. Check the requirements

- **Home Assistant 2026.3 or newer** (*Settings → About*).
- **Bluetooth on the Home Assistant machine.** A built-in or USB Bluetooth adapter works best. An ESPHome Bluetooth proxy also works, but status reports may not arrive reliably through it.
- **The lamps are paired in the AwoX or EGLO connect app** and can be switched there. You need that account's e-mail and password once during setup.
- **HACS** is installed (for option A in step 2). Guide: <https://hacs.xyz/docs/use/>

### Only for Home Assistant in a Docker container

The container needs access to Bluetooth. Start it with:

```bash
docker run -d --name homeassistant --restart=unless-stopped \
  --privileged --network=host \
  -v /PATH/TO/homeassistant:/config \
  -v /run/dbus:/run/dbus:ro \
  ghcr.io/home-assistant/home-assistant:stable
```

What matters is `--network=host`, `--privileged` and `/run/dbus`. Bluetooth must be running on the host (`bluetoothctl show` lists the adapter). Home Assistant OS and Supervised need none of this.

## 2. Install the integration

### Option A: via HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Top right **⋮ → Custom repositories**.
3. *Repository*: `https://github.com/K1NG-Dev01/AwoX`
4. *Type*: **Integration** → **Add**.
5. Search HACS for **AvoX K1NG Dev** → open it → **Download**.
6. **Restart Home Assistant** (*Settings → System → ⏻ → Restart*).

Updates then show up automatically under *Settings → Updates*.

### Option B: manually

1. Download this repository as ZIP (*Code → Download ZIP*) and unpack it.
2. Copy the folder `custom_components/awox_ble` to `config/custom_components/awox_ble` (e.g. with the *File editor* or *Samba* add-on).
3. Restart Home Assistant.

## 3. Set it up

1. **Settings → Devices & services → Add integration**.
2. Search for **AvoX K1NG Dev**.
3. Sign in with the e-mail and password from the AwoX / EGLO app.
   The account is only used once to download the mesh credentials and the device list. The password is not stored; afterwards everything runs locally over Bluetooth.
4. Done – every lamp appears as its own device with a `light` entity, the Plug Plus as a switch with power, voltage and energy.

The first connection takes up to a minute. Lamps that are currently off at the wall show as *unavailable* and come back on their own once they have power.

## 4. Options (optional)

*Settings → Devices & services → AvoX K1NG Dev → Configure*:

- **Entry lamp:** normally Home Assistant picks it itself. Pin one only if a lamp always has power and is in good range.
- **Rated power of the lamps:** watts at full brightness, for the consumption estimate (default 21 W).
- **Add a device by MAC address:** for a lamp missing from the account list.

**Energy dashboard:** *Settings → Dashboards → Energy → Add device* → pick the "Energy" (Plug Plus) or "Energy (estimated)" (lamps) sensors.

## 5. Use with Alexa, Google Home or Apple Home

The lamps are normal Home Assistant lights. Two ways:

- **Home Assistant Cloud (Nabu Casa):** *Settings → Voice assistants → Alexa / Google* → expose the lamps.
- **Matter via Matterbridge (free, local):** install the *Matterbridge* add-on or container with the *matterbridge-hass* plugin, add the lamps to its *whiteList* and add Matterbridge to the Alexa, Google Home or Apple Home app as a Matter device via QR code.

Then in the Alexa app *Devices → + → Add device*, or say "Alexa, discover devices".

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| Integration does not show up after installing | Really restart Home Assistant, then clear the browser cache (Ctrl+F5). |
| All lamps *unavailable* | Check the Bluetooth integration under *Devices & services*; is a lamp close enough to the adapter? For Docker see step 1. |
| "Wrong e-mail or password" / "no Bluetooth mesh devices found" | Use the same account as in the app, the one the lamps are paired in. |
| A lamp is often *unavailable* | Does it have power (wall switch)? Otherwise it is probably out of Bluetooth range – a lamp in between helps. |
| Alexa says "device is not responding" | Check whether the lamp switches in Home Assistant. If it does, the problem is Matter/Alexa, not this integration. |

Still stuck: on the integration page **⋮ → Enable debug logging**, reproduce the problem, disable debug logging again and attach the downloaded log file to an [issue](https://github.com/K1NG-Dev01/AwoX/issues). Credentials are never written to the log.
