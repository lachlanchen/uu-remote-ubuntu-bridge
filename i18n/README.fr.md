<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# Passerelle UU Remote pour Ubuntu

**Afficher et contrôler complètement le bureau Ubuntu GNOME avec NetEase UU Remote.**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="Un bureau Ubuntu GNOME accessible depuis macOS grâce à UU Remote Ubuntu Bridge." width="1120">
  </a>
  <br>
  <sub>Un bureau Ubuntu GNOME accessible depuis macOS grâce à UU Remote Ubuntu Bridge.</sub>
</p>

</div>

Cette passerelle expérimentale exécute le client Windows officiel dans un
préfixe Wine isolé et partage le bureau GNOME existant par RDP local ou par le
relais VNC local facultatif pour X11.

La base est Ubuntu 24.04 x86-64, GNOME 46 et Wine 11. Les nouvelles installations utilisent UU `4.42.1.2835`, validé avec des empreintes exactes et des comptes rendus de tests. Une réinstallation ordinaire conserve la version installée. Aucun binaire inconnu n’est modifié.

<!-- feature-status:start -->
## Ce qui fonctionne

Vérifié le **2026-10-04**. Le contrôle du bureau, le presse-papiers texte et la
dictée fonctionnent sur des chemins testés ou confirmés par l'utilisateur. Cela
ne garantit pas tous les appareils, dispositions de clavier ou fonctions du client Windows.

| Fonction | État | Portée et limites |
| --- | --- | --- |
| Bureau Ubuntu existant | Fonctionne | Vidéo et reconnexion conservent la session choisie et les applications ouvertes. |
| Souris | Fonctionne | Déplacement, clics, boutons, molette et focus sur les relais testés. |
| Clavier physique / raccourcis | Fonctionne, selon le client | Lettres, modificateurs et symboles ; aucune garantie universelle pour les dispositions US, JIS et Mac. |
| Clavier mobile / Unicode | Fonctionne sur les chemins testés | Chinois, ponctuation, emoji et texte multiligne ; chaque IME reste à vérifier. |
| Dictée continue | Confirmée à l'usage, tests de régression | Les révisions conservent les messages antérieurs ; les essais sur téléphones réels varient selon la version. |
| Presse-papiers texte bidirectionnel | Fonctionne, selon le chemin | Texte uniquement. Retour X11/VNC facultatif, jusqu'à 60 KiB ; images et fichiers exclus. |
| Même bureau via UU / RDP / RealVNC | Configuration facultative | Backend X11 physique partagé ; les sessions distinctes par défaut ne sont pas fusionnées automatiquement. |
| Résolution / ajustement du canevas | Configurable | Taille fixe ou suivi facultatif de la taille stable X11/VNC ; pas de moniteurs virtuels supplémentaires. |
| Récupération / démarrage automatique | Conditionnel | Redémarrage supervisé et connexion conservée ; session GNOME et trousseau utilisables nécessaires. Aucun nouveau redémarrage machine dans la validation 4.42. |
| Terminal natif UU → shell Ubuntu | Adaptateur fonctionnel, canal conditionnel | UTF-8 et taille PTY ; limites de version, de connexion et de code de sortie natif encore présentes. |
| `uu-shell` | Vérifié avec SSH enregistré | Choix explicite : LazyTunnel, SSH redirigé ou terminal natif. Une réussite SSH ne valide pas le canal UU natif. |
| Redirection de ports UU / SSH / SCP | Conditionnel | Des chemins sont validés ; une prise de contrôle ou fermeture du transport peut les couper. Ce n'est pas un VPN. |
| Super Screen / écrans virtuels supplémentaires | Non vérifié | Aucune validation du pont Ubuntu ; un simple redimensionnement du bureau ne suffit pas. |
| Anti-espionnage / écran de confidentialité | Non vérifié | Aucun backend Linux validé pour masquer l'écran physique et bloquer les entrées locales. Ne pas en dépendre pour la confidentialité. |
| Audio / microphone | Limité | Selon l'hôte ; certaines installations utilisent volontairement un backend silencieux. |
| Transfert natif de fichiers, presse-papiers images/fichiers, autres options | Non vérifié | Copier du texte ne transfère pas des fichiers ; SCP/SFTP sur SSH vérifié est une autre solution. |

Voir les [preuves et limites](../docs/features.md) et les validations distinctes
[RDP](../docs/releases/4.42.1.2835-acceptance.md) et
[X11](../docs/releases/4.42-x11-workstation-20261001.md). Le test du contrôleur Mac
4.42 n'a pas validé la dictée continue sur un vrai téléphone. Le presse-papiers du
bureau partagé sous XRDP 0.9.24 présente aussi une limite documentée pour les emoji hors BMP.

Pour un appareil déjà configuré nommé `lab` :

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

Remplacez `lab` par votre profil. `--lazy` nécessite un enregistrement LazyTunnel ;
`--native` demande le terminal de UU et peut échouer indépendamment. Aucun repli
silencieux ni prise de contrôle du bureau. [Détails](../docs/fleet-shell.md).
<!-- feature-status:end -->

## Installation rapide

```bash
./install.sh
```

Les nouvelles installations utilisent le manifeste validé **4.42.1.2835** ; une réinstallation ordinaire conserve la version installée. Le lien FreeRDP nightly fixé renvoie actuellement une erreur 404 : une nouvelle installation RDP nécessite donc un client existant dont le hash correspond exactement. Pour un bureau X11/XRDP, `./install.sh --desktop-relay vnc` évite cette dépendance. Voir la [récupération des téléchargements et le nettoyage des lanceurs en double](../docs/fresh-install-recovery.md).

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
