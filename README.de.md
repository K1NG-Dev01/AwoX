# AvoX K1NG Dev

Schnelle, lokale Steuerung von AwoX- und EGLO-Bluetooth-Mesh-Lampen in Home Assistant (EGLO connect, AwoX HomeControl / SmartLIGHT, Telink-Mesh).

[English](README.md)

- An/aus, Helligkeit, Farbe (RGB), Farbtemperatur (2700–6500 K) und die eingebauten Farbprogramme – meist deutlich unter einer Sekunde.
- Eine dauerhafte Verbindung zur Lampe mit dem besten Signal; alle anderen werden über das Mesh erreicht. Verliert diese Lampe den Strom, übernimmt automatisch die nächste.
- Am Wandschalter ausgeschaltete Lampen werden nach etwa 2–3 Minuten als *nicht verfügbar* angezeigt und kommen von selbst wieder.
- Der EGLO Plug Plus erscheint als Schalter mit gemessener Leistung (W), Spannung (V) und Energie (kWh, für das Energie-Dashboard). Er wird nie als Verbindungspunkt genutzt, damit Alexa über ihn weiter funktioniert.
- Lampen bekommen „Leistung (geschätzt)“ und „Energie (geschätzt)“: Nennleistung × Helligkeit + 0,4 W Standby. Das ist eine Schätzung, keine Messung.
- Szenen, Skripte und Automationen baust du wie gewohnt mit Home Assistant.

## Voraussetzungen

- Home Assistant 2026.3 oder neuer.
- Ein Bluetooth-Adapter am Home-Assistant-Rechner (empfohlen) oder ein ESPHome-Bluetooth-Proxy (geht, siehe *Grenzen*).
- Ein AwoX-/EGLO-Konto, in dem die Lampen gekoppelt sind.

## Installation

**HACS:** HACS → ⋮ → *Benutzerdefinierte Repositories* → dieses Repository als *Integration* hinzufügen → *AvoX K1NG Dev* installieren → Home Assistant neu starten.

**Manuell:** `custom_components/awox_ble` in deinen Ordner `config/custom_components/` kopieren und Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → AvoX K1NG Dev*, dann mit dem Konto aus der App anmelden. Das Konto wird nur einmal genutzt, um die Mesh-Zugangsdaten und die Geräteliste abzuholen; das Passwort wird nicht gespeichert, die Lampen werden lokal gesteuert.

Optionen:

- **Einstiegslampe:** feste Lampe, mit der sich Home Assistant verbindet (Standard: bestes Signal).
- **Nennleistung der Lampen:** Watt bei voller Helligkeit je Lampe für die Schätzung (Standard 21 W).
- **Gerät per MAC-Adresse hinzufügen:** für eine Lampe, die in der Kontoliste fehlt.

Wenn du die Lampen später mit einem anderen Konto neu koppelst, fragt Home Assistant nach einer neuen Anmeldung.

## Effekte

| Effekt | Nummer |
|---|---|
| Regenbogen | 0 |
| Regenbogen 2 | 1 |
| Farbprogramm 2–6 | 2–6 |

## So funktioniert es

Das Protokoll (Kopplung, Sitzungsschlüssel, verschlüsselte Befehle) ist das Telink-Mesh-Protokoll aus [fsaris/home-assistant-awox](https://github.com/fsaris/home-assistant-awox) (MIT), das auf [Leiaz/python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light) aufbaut. Danke an beide.

AwoX-Lampen bestätigen die Benachrichtigungs-Anmeldung von BlueZ nie, BlueZ trennt deshalb nach 30 Sekunden. Mit einem lokalen Adapter spricht die Integration darum über einen eigenen kleinen ATT-Client (L2CAP-Socket) mit der Lampe und schaltet Statusmeldungen mit einem Schreibbefehl ohne Bestätigung ein. Über ESPHome-Proxys nutzt sie den normalen Bluetooth-Stack von Home Assistant.

## Grenzen

- Über einen ESPHome-Proxy kommen Statusmeldungen eventuell nicht zuverlässig an (siehe oben); Schalten funktioniert trotzdem.
- Neue Lampen koppeln, Firmware-Updates und das Mesh selbst verwaltest du in der AwoX-/EGLO-App.
- Die Energie des Plug Plus wird aus der gemessenen Leistung (alle 15 s) aufsummiert; der interne Zählerstand des Steckers wird noch nicht gelesen.

## Fehlersuche

Auf der Seite der Integration ⋮ → *Debug-Protokollierung aktivieren*, Problem nachstellen, Log an ein Issue anhängen. Zugangsdaten landen nie im Log.

## Lizenz

© 2026 Henrik. Alle Rechte vorbehalten. Installieren und privat nutzen ist erlaubt, Kopieren, Verändern und Weitergeben nicht. Siehe [LICENSE](LICENSE).
