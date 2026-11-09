# Installationsanleitung – AvoX K1NG Dev

Schritt für Schritt von null bis zur ersten Lampe in Home Assistant und Alexa. [English](INSTALL.md)

## 1. Voraussetzungen prüfen

- **Home Assistant 2026.3 oder neuer** (*Einstellungen → Info*).
- **Bluetooth am Home-Assistant-Rechner.** Am besten ein eingebauter oder USB-Bluetooth-Adapter. Ein ESPHome-Bluetooth-Proxy geht auch, Statusmeldungen kommen darüber aber eventuell nicht zuverlässig an.
- **Die Lampen sind in der AwoX- bzw. EGLO-connect-App gekoppelt** und lassen sich dort schalten. E-Mail und Passwort dieses Kontos brauchst du einmal bei der Einrichtung.
- **HACS** ist installiert (für Weg A in Schritt 2). Anleitung: <https://hacs.xyz/docs/use/>

### Nur bei Home Assistant im Docker-Container

Der Container braucht Zugriff auf Bluetooth. Starte ihn mit:

```bash
docker run -d --name homeassistant --restart=unless-stopped \
  --privileged --network=host \
  -v /PFAD/ZU/homeassistant:/config \
  -v /run/dbus:/run/dbus:ro \
  ghcr.io/home-assistant/home-assistant:stable
```

Wichtig sind `--network=host`, `--privileged` und `/run/dbus`. Auf dem Host muss Bluetooth laufen (`bluetoothctl show` zeigt den Adapter). Home Assistant OS und Supervised brauchen nichts davon.

## 2. Integration installieren

### Weg A: über HACS (empfohlen)

1. In Home Assistant **HACS** öffnen.
2. Oben rechts **⋮ → Benutzerdefinierte Repositories**.
3. Bei *Repository* eintragen: `https://github.com/K1NG-Dev01/AwoX`
4. Bei *Typ* **Integration** wählen → **Hinzufügen**.
5. In HACS nach **AvoX K1NG Dev** suchen → öffnen → **Herunterladen**.
6. **Home Assistant neu starten** (*Einstellungen → System → ⏻ → Neu starten*).

Updates erscheinen danach automatisch unter *Einstellungen → Updates*.

### Weg B: von Hand

1. Dieses Repository als ZIP herunterladen (*Code → Download ZIP*) und entpacken.
2. Den Ordner `custom_components/awox_ble` nach `config/custom_components/awox_ble` kopieren (z. B. mit dem *File editor*- oder *Samba*-Add-on).
3. Home Assistant neu starten.

## 3. Einrichten

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen**.
2. Nach **AvoX K1NG Dev** suchen.
3. Mit E-Mail und Passwort aus der AwoX-/EGLO-App anmelden.
   Das Konto wird nur einmal genutzt, um die Mesh-Zugangsdaten und die Geräteliste zu laden. Das Passwort wird nicht gespeichert, gesteuert wird danach komplett lokal per Bluetooth.
4. Fertig – jede Lampe erscheint als eigenes Gerät mit einer `light`-Entität, der Plug Plus als Schalter mit Leistung, Spannung und Energie.

Die erste Verbindung dauert bis zu einer Minute. Lampen, die gerade am Wandschalter aus sind, erscheinen als *nicht verfügbar* und kommen von selbst, sobald sie Strom haben.

## 4. Optionen (optional)

*Einstellungen → Geräte & Dienste → AvoX K1NG Dev → Konfigurieren*:

- **Einstiegslampe:** Normalerweise sucht Home Assistant sie selbst aus. Fest einstellen nur, wenn eine Lampe immer Strom hat und gut erreichbar ist.
- **Nennleistung der Lampen:** Watt bei voller Helligkeit, für die Verbrauchsschätzung (Standard 21 W).
- **Gerät per MAC-Adresse hinzufügen:** für eine Lampe, die in der Kontoliste fehlt.

**Energie-Dashboard:** *Einstellungen → Dashboards → Energie → Gerät hinzufügen* → die Sensoren „Energie“ (Plug Plus) bzw. „Energie (geschätzt)“ (Lampen) wählen.

## 5. Mit Alexa, Google Home oder Apple Home nutzen

Die Lampen sind normale Home-Assistant-Lichter. Du hast zwei Wege:

- **Home Assistant Cloud (Nabu Casa):** *Einstellungen → Sprachassistenten → Alexa / Google* → Lampen freigeben.
- **Matter über Matterbridge (kostenlos, lokal):** Das Add-on bzw. den Container *Matterbridge* mit dem Plugin *matterbridge-hass* installieren, die Lampen in der Positivliste (*whiteList*) eintragen und Matterbridge in der Alexa-, Google-Home- oder Apple-Home-App per QR-Code als Matter-Gerät hinzufügen.

Danach in der Alexa-App *Geräte → + → Gerät hinzufügen* bzw. „Alexa, suche Geräte“.

## 6. Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| Integration taucht nach der Installation nicht auf | Home Assistant wirklich neu starten, dann Browser-Cache leeren (Strg+F5). |
| Alle Lampen *nicht verfügbar* | Bluetooth-Integration unter *Geräte & Dienste* prüfen; steht eine Lampe nah genug am Adapter? Bei Docker siehe Schritt 1. |
| „E-Mail oder Passwort falsch“ / „keine Bluetooth-Mesh-Geräte gefunden“ | Dasselbe Konto wie in der App verwenden, in dem die Lampen gekoppelt sind. |
| Eine Lampe ist oft *nicht verfügbar* | Hat sie Strom (Wandschalter)? Sonst ist sie für Bluetooth vermutlich zu weit weg – eine Lampe dazwischen hilft. |
| Alexa meldet „Gerät reagiert nicht“ | In Home Assistant prüfen, ob die Lampe dort schaltet. Wenn ja, liegt es an Matter/Alexa, nicht an dieser Integration. |

Hilft das nicht: auf der Integrationsseite **⋮ → Debug-Protokollierung aktivieren**, Problem nachstellen, Protokollierung wieder ausschalten und die heruntergeladene Log-Datei an ein [Issue](https://github.com/K1NG-Dev01/AwoX/issues) anhängen. Zugangsdaten landen nie im Log.
