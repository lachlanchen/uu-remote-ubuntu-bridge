<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Den Ubuntu-GNOME-Desktop mit NetEase UU Remote anzeigen und vollständig steuern.**

</div>

Diese experimentelle Brücke führt den offiziellen Windows-Client in einem
isolierten Wine-Präfix aus und überträgt die echte GNOME-Wayland-Sitzung über
eine lokale RDP-Verbindung. Video, Maus, Tastatur, Wiederverbindung und
Dienstwiederherstellung funktionieren.

Die aktuelle Version ist absichtlich auf UU Remote `4.33.0.8907`, Ubuntu
24.04, GNOME 46 und Wine 11 festgelegt. Unbekannte Binärdateien werden niemals
gepatcht.

## Schnellinstallation

```bash
./install.sh
```

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

Wer stattdessen einen herstellerunabhängigen Weg benötigt, kann [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_de) nutzen. Es basiert auf dem separaten, quelloffenen [LazyTunnel](https://github.com/lachlanchen/LazyTunnel)-Kern und bietet selbst gehosteten Zugriff per SSH, Terminal und noVNC. Es ist ein anderes Werkzeug; dieses Repository bleibt der Kompatibilitätsweg für den offiziellen UU-Client.

> Die vollständige technische Referenz bleibt auf Englisch, damit Befehle,
> Hashes und Bytes in einer einzigen exakten Quelle gepflegt werden.
