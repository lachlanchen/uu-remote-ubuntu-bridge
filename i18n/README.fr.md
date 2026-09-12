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
- [Terminal Ubuntu natif](../docs/native-ubuntu-terminal.md)
- [Alias SSH et redirection de ports entre deux ordinateurs](../docs/ssh-and-port-mapping.md)

Aucun mot de passe, jeton, identifiant d'appareil, exécutable UU ou journal
privé n'est versionné. Ce projet fait partie de
[The Art of Lazying](https://lazying.art).

Si vous avez plutôt besoin d'une solution indépendante du fournisseur, [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_fr#review) repose sur le cœur séparé et open source [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) pour un accès autohébergé par SSH, terminal et noVNC. Il s'agit d'un autre outil ; ce dépôt reste la voie de compatibilité avec le client UU officiel.

## Soutenir le projet

Si ce pont vous fait gagner du temps, vous pouvez soutenir la maintenance continue de sa compatibilité :

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> La référence technique complète reste en anglais afin de conserver une
> source unique et exacte pour les commandes, empreintes et octets.
