<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Visualiza y controla por completo el escritorio Ubuntu GNOME mediante NetEase UU Remote.**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="Un escritorio Ubuntu GNOME al que se accede desde macOS mediante UU Remote Ubuntu Bridge." width="1120">
  </a>
  <br>
  <sub>Un escritorio Ubuntu GNOME al que se accede desde macOS mediante UU Remote Ubuntu Bridge.</sub>
</p>

</div>

Este puente experimental ejecuta el cliente oficial de Windows en un prefijo
Wine aislado y comparte el escritorio GNOME existente mediante RDP local o el
enlace VNC local opcional para X11.

La base es Ubuntu 24.04 x86-64, GNOME 46 y Wine 11. Las instalaciones nuevas usan UU `4.42.1.2835`, validado con hashes exactos y registros de aceptación. Una reinstalación normal conserva la versión instalada. Nunca se parchean binarios desconocidos.

<!-- feature-status:start -->
## Qué funciona

Revisado el **2026-10-04**. El control del escritorio, el portapapeles de texto y
el dictado funcionan en rutas probadas o confirmadas por el usuario. Esto no
garantiza todos los dispositivos, distribuciones de teclado ni funciones del cliente Windows.

| Función | Estado | Alcance y límites |
| --- | --- | --- |
| Escritorio Ubuntu existente | Funciona | Vídeo y reconexión conservan la sesión elegida y las aplicaciones abiertas. |
| Ratón | Funciona | Movimiento, clics, botones, rueda y foco en los enlaces probados. |
| Teclado físico / atajos | Funciona, depende del cliente | Letras, modificadores y símbolos; sin garantía universal para distribuciones US, JIS y Mac. |
| Teclado móvil / Unicode | Funciona en rutas probadas | Chino, puntuación, emoji y texto multilínea; cada IME requiere comprobación. |
| Dictado continuo | Confirmado en uso diario y con pruebas de regresión | Las revisiones conservan los mensajes anteriores; las pruebas con móviles reales varían por versión. |
| Portapapeles de texto bidireccional | Funciona, depende de la ruta | Solo texto. Retorno X11/VNC opcional, hasta 60 KiB; no cubre imágenes ni archivos. |
| Mismo escritorio por UU / RDP / RealVNC | Configuración opcional | Backend X11 físico compartido; las sesiones separadas predeterminadas no se unifican solas. |
| Resolución / ajuste del lienzo | Configurable | Tamaño fijo o seguimiento opcional del tamaño estable de X11/VNC; no crea pantallas virtuales adicionales. |
| Recuperación / inicio al arrancar | Condicional | Reinicio supervisado y sesión de cuenta conservada; requiere acceso GNOME y llavero utilizables. La aceptación 4.42 no incluyó un nuevo reinicio del equipo. |
| Terminal nativo UU → shell Ubuntu | Adaptador funcional, canal condicional | UTF-8 y tamaño PTY; persisten límites de versión, conexión y códigos de salida nativos. |
| `uu-shell` | Verificado con SSH registrado | Selección explícita de LazyTunnel, SSH redirigido o terminal nativo; SSH no demuestra que funcione el canal nativo UU. |
| Mapeo de puertos UU / SSH / SCP | Condicional | Hay rutas probadas; tomar el control o cerrar la conexión portadora puede interrumpirlas. No es una VPN. |
| Super Screen / pantallas virtuales adicionales | Sin verificar | Sin aceptación del puente Ubuntu; redimensionar un escritorio no demuestra esta función. |
| Antiespía / pantalla de privacidad | Sin verificar | No hay backend Linux validado que oculte monitores físicos y bloquee la entrada local. No confiar en él para proteger la privacidad. |
| Audio / micrófono | Limitado | Depende del host; algunas instalaciones usan deliberadamente un backend silencioso. |
| Transferencia nativa de archivos, portapapeles de imágenes/archivos y otros extras | Sin verificar | Copiar texto no transfiere archivos; SCP/SFTP sobre SSH verificado es otra opción. |

Consulte las [pruebas y limitaciones](../docs/features.md) y las aceptaciones separadas
de [RDP](../docs/releases/4.42.1.2835-acceptance.md) y
[X11](../docs/releases/4.42-x11-workstation-20261001.md). La prueba con controlador Mac
de 4.42 no validó dictado continuo desde un móvil real. El portapapeles del escritorio
compartido con XRDP 0.9.24 también tiene una limitación documentada con emoji fuera del BMP.

Para un equipo ya configurado llamado `lab`:

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

Sustituya `lab` por su perfil. `--lazy` requiere registro en LazyTunnel;
`--native` solicita el terminal propio de UU y puede fallar por separado. No cambia
de transporte ni toma el escritorio de forma oculta. [Detalles](../docs/fleet-shell.md).
<!-- feature-status:end -->

## Instalación rápida

```bash
./install.sh
```

Las instalaciones nuevas usan el manifiesto validado **4.42.1.2835**; una reinstalación normal conserva la versión instalada. El enlace fijo de FreeRDP nightly devuelve actualmente 404, por lo que una instalación nueva con RDP necesita un cliente existente cuyo hash coincida exactamente. En escritorios X11/XRDP, `./install.sh --desktop-relay vnc` evita esa dependencia. Consulta la [recuperación de descargas y limpieza de lanzadores duplicados](../docs/fresh-install-recovery.md).

El instalador idempotente instala dependencias, verifica todos los artefactos,
compila el código de compatibilidad, configura GNOME Remote Desktop, guarda la
contraseña RDP en GNOME Keyring e inicia un servicio systemd de usuario.

## Ruta de control

```text
Controlador UU -> UU en Wine -> broker de entrada -> SDL FreeRDP
              -> GNOME Remote Desktop -> escritorio GNOME Wayland
```

## Cómo mantener futuras versiones

Las herramientas nuevas separan la detección automática de la aprobación
humana. Generan mapas PE, puntos semánticos, candidatos y desensamblado, pero
la salida sigue siendo un borrador inutilizable hasta revisar la semántica y
probar una copia desechable.

- [Flujo completo para actualizaciones](../docs/upstream-maintenance.md)
- [Metodología e inventario de herramientas](../docs/methodology-and-toolkit.md)
- [Registro exacto de ingeniería inversa](../docs/reverse-engineering.md)
- [Seguridad](../docs/security.md)
- [Solución de problemas](../docs/troubleshooting.md)
- [Terminal nativo de Ubuntu](../docs/native-ubuntu-terminal.md)
- [Alias SSH y mapeo de puertos entre dos equipos](../docs/ssh-and-port-mapping.md)

El repositorio no incluye contraseñas, tokens, identificadores de dispositivo,
ejecutables de UU ni registros privados. Forma parte de
[The Art of Lazying](https://lazying.art).

Si prefieres una opción independiente del proveedor, [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_es#review) utiliza el núcleo separado y de código abierto [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) para ofrecer acceso autohospedado por SSH, terminal y noVNC. Es una herramienta distinta; este repositorio sigue siendo la vía de compatibilidad con el cliente oficial de UU.

## Apoyar el proyecto

Si este puente te ahorra tiempo, puedes apoyar el mantenimiento continuo de la compatibilidad:

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> La referencia técnica completa permanece en inglés para mantener comandos,
> hashes y bytes en una única fuente exacta.
