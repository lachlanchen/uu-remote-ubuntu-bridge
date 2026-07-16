<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# Passerelle UU Remote pour Ubuntu

**Afficher et contrôler complètement le bureau Ubuntu GNOME avec NetEase UU Remote.**

</div>

Cette passerelle expérimentale exécute le client Windows officiel dans un
préfixe Wine isolé et transmet la session GNOME Wayland réelle par une liaison
RDP locale. La vidéo, la souris, le clavier, la reconnexion et la récupération
du service sont prises en charge.

La version actuelle est volontairement limitée à UU Remote `4.33.0.8907`,
Ubuntu 24.04, GNOME 46 et Wine 11. Aucun binaire inconnu n'est modifié.

## Installation rapide

```bash
./install.sh
```

Le programme d'installation idempotent installe les dépendances, vérifie les
artefacts, compile les composants de compatibilité, configure GNOME Remote
Desktop, conserve le mot de passe RDP dans GNOME Keyring et démarre un service
systemd utilisateur.

## Chemin de contrôle

```text
Contrôleur UU -> UU dans Wine -> courtier d'entrée -> SDL FreeRDP
              -> GNOME Remote Desktop -> bureau GNOME Wayland
```

## Suivre les mises à jour amont

Les outils distinguent la recherche automatique de l'approbation humaine. Ils
produisent la carte PE, les repères sémantiques, les signatures candidates et
le désassemblage ciblé. Le manifeste reste inutilisable tant que la sémantique
n'a pas été relue et testée sur une copie jetable.

- [Procédure complète de mise à jour](../docs/upstream-maintenance.md)
- [Méthodologie et outils](../docs/methodology-and-toolkit.md)
- [Dossier d'ingénierie inverse](../docs/reverse-engineering.md)
- [Sécurité](../docs/security.md)
- [Dépannage](../docs/troubleshooting.md)

Aucun mot de passe, jeton, identifiant d'appareil, exécutable UU ou journal
privé n'est versionné. Ce projet fait partie de
[The Art of Lazying](https://lazying.art).

> La référence technique complète reste en anglais afin de conserver une
> source unique et exacte pour les commandes, empreintes et octets.
