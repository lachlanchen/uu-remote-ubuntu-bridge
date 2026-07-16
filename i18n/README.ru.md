<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Просмотр и полноценное управление рабочим столом Ubuntu GNOME через NetEase UU Remote.**

</div>

Этот экспериментальный мост запускает официальный клиент Windows в
изолированном префиксе Wine и передаёт реальный сеанс GNOME Wayland через
локальное RDP-соединение. Работают видео, мышь, клавиатура, повторное
подключение и автоматическое восстановление службы.

Текущая версия намеренно привязана к UU Remote `4.33.0.8907`, Ubuntu 24.04,
GNOME 46 и Wine 11. Неизвестные двоичные файлы никогда не исправляются.

## Быстрая установка

```bash
./install.sh
```

Идемпотентный установщик ставит зависимости, проверяет хеши, собирает
компоненты совместимости, настраивает GNOME Remote Desktop, хранит пароль RDP
в GNOME Keyring и запускает пользовательскую службу systemd.

## Путь управления

```text
Контроллер UU -> UU в Wine -> брокер ввода -> SDL FreeRDP
              -> GNOME Remote Desktop -> рабочий стол GNOME Wayland
```

## Поддержка новых версий UU

Инструменты отделяют автоматический поиск кандидатов от человеческого
одобрения. Они создают карту PE, смысловые ориентиры, сигнатуры-кандидаты и
целевую дизассемблировку. Черновик нельзя применить, пока его семантика не
проверена и не испытана на одноразовой копии.

- [Полный процесс обновления](../docs/upstream-maintenance.md)
- [Методика и список инструментов](../docs/methodology-and-toolkit.md)
- [Протокол обратной разработки](../docs/reverse-engineering.md)
- [Безопасность](../docs/security.md)
- [Диагностика](../docs/troubleshooting.md)

В репозиторий не входят пароли, токены, идентификаторы устройств, программы UU
или личные журналы. Проект является частью
[The Art of Lazying](https://lazying.art).

> Полная техническая документация остаётся на английском, чтобы команды,
> хеши и байты имели один точный источник.
