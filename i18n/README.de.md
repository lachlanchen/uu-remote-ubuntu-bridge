<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Den Ubuntu-GNOME-Desktop mit NetEase UU Remote anzeigen und vollständig steuern.**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="Ein Ubuntu-GNOME-Desktop, auf den über UU Remote Ubuntu Bridge von macOS aus zugegriffen wird." width="1120">
  </a>
  <br>
  <sub>Ein Ubuntu-GNOME-Desktop, auf den über UU Remote Ubuntu Bridge von macOS aus zugegriffen wird.</sub>
</p>

</div>

Diese experimentelle Brücke startet den offiziellen Windows-Client in einem
isolierten Wine-Präfix und teilt den bestehenden GNOME-Desktop über lokales RDP
oder den optionalen lokalen VNC-Relay für X11.

Die Basis ist x86-64 Ubuntu 24.04 mit GNOME 46 und Wine 11. Neuinstallationen verwenden das abgenommene UU `4.42.1.2835` mit exakten Hashes und Abnahmeprotokollen. Normale Neuinstallationen eines bestehenden Systems behalten dessen installierte Version. Unbekannte Binärdateien werden nicht gepatcht.

<!-- feature-status:start -->
## Was funktioniert

Stand: **2026-10-04**. Desktopsteuerung, Textzwischenablage und Diktat funktionieren
auf getesteten oder vom Nutzer bestätigten Wegen. Das gilt nicht automatisch für
jedes Gerät, jedes Tastaturlayout oder jede Funktion des Windows-Clients.

| Funktion | Status | Umfang und Grenzen |
| --- | --- | --- |
| Bestehender Ubuntu-Desktop | Funktioniert | Bildübertragung und Wiederverbindung erhalten die ausgewählte Sitzung und offene Anwendungen. |
| Maus | Funktioniert | Bewegung, Klicks, Tasten, Rad und Fokus auf getesteten Wegen. |
| Physische Tastatur / Tastenkürzel | Funktioniert, clientabhängig | Buchstaben, Zusatztasten und Symbole; keine Garantie für alle US-, JIS- und Mac-Layouts. |
| Handytastatur / Unicode | Auf getesteten Wegen nutzbar | Chinesisch, Satzzeichen, Emoji und mehrzeiliger Text; einzelne IMEs müssen geprüft werden. |
| Fortlaufendes Diktat | Im Alltag bestätigt, Regressionstests vorhanden | Korrekturen der laufenden Eingabe erhalten frühere Nachrichten; Handytests unterscheiden sich je Release. |
| Textzwischenablage in beide Richtungen | Funktioniert, wegabhängig | Nur Text. X11/VNC-Rückkanal optional, bis 60 KiB; keine Bilder oder Dateien. |
| Derselbe Desktop über UU / RDP / RealVNC | Optional eingerichtet | Gemeinsames physisches X11-Backend; getrennte Standardsitzungen werden nicht automatisch vereint. |
| Auflösung / Bildflächenanpassung | Konfigurierbar | Feste Größe oder optionale Übernahme stabiler X11/VNC-Größen; keine zusätzlichen virtuellen Monitore. |
| Wiederherstellung / Systemstart | Bedingt | Überwachter Neustart und erhaltener Login; funktionierende GNOME-Anmeldung und Schlüsselbund erforderlich. Kein neuer Rechnerneustarttest bei 4.42. |
| Natives UU-Terminal → Ubuntu-Shell | Adapter funktioniert, Kanal bedingt | UTF-8 und PTY-Größe; Hersteller-Versionsfehler, Verbindungsfehler und Einschränkungen beim Exitstatus bleiben. |
| `uu-shell` | Mit eingerichtetem SSH geprüft | Explizit LazyTunnel, weitergeleitetes SSH oder natives Terminal; SSH-Erfolg belegt nicht den nativen UU-Kanal. |
| UU-Portweiterleitung / SSH / SCP | Bedingt | Erfolgreiche Wege dokumentiert; Übernahme oder Schließen der Trägerverbindung kann sie unterbrechen. Kein VPN. |
| Super Screen / zusätzliche virtuelle Monitore | Ungeprüft | Keine bestätigte Ubuntu-Bridge-Abnahme; normale Größenänderung ist kein Nachweis. |
| Blickschutz / Privatsphäre-Bildschirm | Ungeprüft | Kein validiertes Linux-Backend zum Ausblenden physischer Bildschirme und Sperren lokaler Eingaben. Nicht als Datenschutzmaßnahme voraussetzen. |
| Audio / Mikrofon | Eingeschränkt | Hostabhängig; manche Installationen verwenden absichtlich ein stummes Backend. |
| Nativer Dateitransfer, Bild-/Dateizwischenablage, weitere Extras | Ungeprüft | Textkopieren ist kein Dateitransfer; SCP/SFTP über geprüftes SSH ist eine getrennte Möglichkeit. |

Siehe [Nachweise und Grenzen](../docs/features.md) sowie die getrennten
[RDP](../docs/releases/4.42.1.2835-acceptance.md)- und
[X11](../docs/releases/4.42-x11-workstation-20261001.md)-Abnahmen. Der Mac-Controllertest
für 4.42 prüfte kein fortlaufendes Diktat auf echten Handys. Die Zwischenablage des
gemeinsamen Desktops unter XRDP 0.9.24 hat zusätzlich eine bekannte Einschränkung bei Nicht-BMP-Emoji.

Für einen bereits eingerichteten Gegenrechner namens `lab`:

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

`lab` durch den eigenen Profilnamen ersetzen. `--lazy` benötigt eine LazyTunnel-
Registrierung; `--native` fordert das eigene UU-Terminal an und kann unabhängig
scheitern. Kein stiller Transportwechsel oder Desktop-Takeover. [Details](../docs/fleet-shell.md).
<!-- feature-status:end -->

## Schnellinstallation

```bash
./install.sh
```

Neue Installationen verwenden das geprüfte Manifest **4.42.1.2835**; bei einer normalen Neuinstallation bleibt die installierte Version erhalten. Der festgelegte FreeRDP-Nightly-Link liefert derzeit 404. Eine neue Installation mit dem standardmäßigen RDP-Relay benötigt deshalb einen vorhandenen Client mit exakt passendem Hash. Für X11/XRDP-Desktops umgeht `./install.sh --desktop-relay vnc` diese Abhängigkeit. Siehe [Download-Reparatur und Bereinigung doppelter Starter](../docs/fresh-install-recovery.md).

Das idempotente Installationsskript installiert Abhängigkeiten, prüft alle
Artefakte, kompiliert die Kompatibilitätskomponenten, richtet GNOME Remote
Desktop ein, speichert das RDP-Passwort im GNOME-Schlüsselbund und startet
einen systemd-Benutzerdienst.

## Steuerpfad

```text
UU-Controller -> UU in Wine -> Eingabe-Broker -> SDL FreeRDP
              -> GNOME Remote Desktop -> GNOME-Wayland-Desktop
```

## Neue Upstream-Versionen

Die Werkzeuge trennen automatische Kandidatensuche von menschlicher Freigabe.
Sie erzeugen PE-Zuordnungen, semantische Anker, Kandidatensignaturen und
gezielte Disassemblierung. Der Entwurf bleibt unbrauchbar, bis die Semantik
geprüft und eine Wegwerfkopie getestet wurde.

- [Vollständiger Aktualisierungsablauf](../docs/upstream-maintenance.md)
- [Methodik und Werkzeugübersicht](../docs/methodology-and-toolkit.md)
- [Reverse-Engineering-Protokoll](../docs/reverse-engineering.md)
- [Sicherheit](../docs/security.md)
- [Fehlerbehebung](../docs/troubleshooting.md)
- [Natives Ubuntu-Terminal](../docs/native-ubuntu-terminal.md)
- [SSH-Aliase und Portweiterleitung zwischen zwei Rechnern](../docs/ssh-and-port-mapping.md)

Passwörter, Token, Gerätekennungen, UU-Programme und private Protokolle werden
nicht eingecheckt. Das Projekt gehört zu
[The Art of Lazying](https://lazying.art).

Wer stattdessen einen herstellerunabhängigen Weg benötigt, kann [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_de#review) nutzen. Es basiert auf dem separaten, quelloffenen [LazyTunnel](https://github.com/lachlanchen/LazyTunnel)-Kern und bietet selbst gehosteten Zugriff per SSH, Terminal und noVNC. Es ist ein anderes Werkzeug; dieses Repository bleibt der Kompatibilitätsweg für den offiziellen UU-Client.

## Projekt unterstützen

Wenn dir diese Brücke Zeit spart, kannst du die weitere Kompatibilitätspflege unterstützen:

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> Die vollständige technische Referenz bleibt auf Englisch, damit Befehle,
> Hashes und Bytes in einer einzigen exakten Quelle gepflegt werden.
