# AvoX K1NG Dev

Schnelle, lokale Steuerung von AwoX- und EGLO-Bluetooth-Mesh-Lampen in Home Assistant (EGLO connect, AwoX HomeControl / SmartLIGHT, Telink-Mesh).

Funktioniert mit der Bluetooth-Integration von Home Assistant, lokalen Adaptern und ESPHome-Bluetooth-Proxys. Die Lampen sind normale `light`-Entitäten und lassen sich damit auch in Alexa, Google Home oder Apple Home nutzen – über Matter (z. B. Matterbridge) oder Home Assistant Cloud. Installierbar als benutzerdefiniertes HACS-Repository.

[English](README.md)

- An/aus, Helligkeit, Farbe (RGB), Farbtemperatur (2700–6500 K) und die eingebauten Farbprogramme – meist deutlich unter einer Sekunde.
- Eine dauerhafte Verbindung zu einer Einstiegslampe; alle anderen werden über das Mesh erreicht. Am Wandschalter ausgeschaltete Lampen werden automatisch berücksichtigt (siehe *Zuverlässigkeit*).
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

## Zuverlässigkeit

Gebaut für Wohnungen, in denen einzelne Lampen oft am Wandschalter ausgeschaltet werden:

- **Beste Einstiegslampe:** Home Assistant merkt sich, wie viele Lampen jede Einstiegslampe erreicht, und verbindet sich mit der, die die meisten erreicht. Leitet die aktuelle Einstiegslampe nichts mehr weiter, wechselt es innerhalb von etwa 2½ Minuten.
- **Direkte Verbindung als Notlösung:** Hat eine Lampe Strom (sie sendet), antwortet aber nicht über das Mesh, verbindet sich ein Befehl direkt mit ihr.
- **Kein Flackern in Alexa / Matter:** Beim Wechsel der Einstiegslampe oder Neuverbinden (bis 20 s) bleiben die Lampen *verfügbar*; Befehle warten auf die Verbindung statt zu scheitern.
- **Kein Hin und Her:** Eine schon probierte Einstiegslampe wird höchstens alle 10 Minuten wieder genutzt.
- **Keine Kollisionen:** Der Status wird Lampe für Lampe abgefragt statt bei allen gleichzeitig, damit keine Antworten verloren gehen.

## So funktioniert es

Das Protokoll (Kopplung, Sitzungsschlüssel, verschlüsselte Befehle) ist das Telink-Mesh-Protokoll aus [fsaris/home-assistant-awox](https://github.com/fsaris/home-assistant-awox) (MIT), das auf [Leiaz/python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light) aufbaut. Danke an beide.

AwoX-Lampen bestätigen die Benachrichtigungs-Anmeldung von BlueZ nie, BlueZ trennt deshalb nach 30 Sekunden. Mit einem lokalen Adapter spricht die Integration darum über einen eigenen kleinen ATT-Client (L2CAP-Socket) mit der Lampe und schaltet Statusmeldungen mit einem Schreibbefehl ohne Bestätigung ein. Über ESPHome-Proxys nutzt sie den normalen Bluetooth-Stack von Home Assistant.

## Grenzen

- Über einen ESPHome-Proxy kommen Statusmeldungen eventuell nicht zuverlässig an (siehe oben); Schalten funktioniert trotzdem.
- Neue Lampen koppeln, Firmware-Updates und das Mesh selbst verwaltest du in der AwoX-/EGLO-App.
- Der Energiezähler des Plug Plus wird direkt aus dem Stecker gelesen (0,1 Wh genau). Ob er sich täglich zurücksetzt, ist noch offen; das Energie-Dashboard rechnet in beiden Fällen richtig.

## Fehlersuche

Auf der Seite der Integration ⋮ → *Debug-Protokollierung aktivieren*, Problem nachstellen, Log an ein Issue anhängen. Zugangsdaten landen nie im Log.

## Lizenz

© 2026 Henrik. Alle Rechte vorbehalten. Installieren und privat nutzen ist erlaubt, Kopieren, Verändern und Weitergeben nicht. Siehe [LICENSE](LICENSE).
