<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Visualiza y controla por completo el escritorio Ubuntu GNOME mediante NetEase UU Remote.**

</div>

Este puente experimental ejecuta el cliente oficial de Windows dentro de un
prefijo Wine aislado y muestra la sesión GNOME Wayland real mediante un enlace
RDP local. Funcionan vídeo, ratón, teclado, reconexión y recuperación del
servicio.

La versión actual está bloqueada deliberadamente a UU Remote `4.33.0.8907`,
Ubuntu 24.04, GNOME 46 y Wine 11. Un binario desconocido nunca se parchea.

## Instalación rápida

```bash
./install.sh
```

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

El repositorio no incluye contraseñas, tokens, identificadores de dispositivo,
ejecutables de UU ni registros privados. Forma parte de
[The Art of Lazying](https://lazying.art).

> La referencia técnica completa permanece en inglés para mantener comandos,
> hashes y bytes en una única fuente exacta.
