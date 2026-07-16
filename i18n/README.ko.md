<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**NetEase UU Remote로 Ubuntu GNOME 데스크톱을 보고 완전히 제어합니다.**

</div>

이 실험적 브리지는 공식 Windows 클라이언트를 격리된 Wine 프리픽스에서
실행하고, 로컬 RDP 연결을 통해 실제 GNOME Wayland 세션을 전달합니다. 화면,
마우스, 키보드, 재연결 및 서비스 자동 복구를 지원합니다.

현재 버전은 의도적으로 UU Remote `4.33.0.8907`, Ubuntu 24.04, GNOME 46,
Wine 11에 고정되어 있습니다. 알 수 없는 바이너리는 절대 패치하지 않습니다.

## 빠른 설치

```bash
./install.sh
```

멱등 설치 스크립트가 의존성 설치, 아티팩트 해시 검증, 호환성 구성 요소 빌드,
GNOME Remote Desktop 설정, GNOME Keyring의 RDP 비밀번호 저장, systemd 사용자
서비스 시작까지 처리합니다.

## 제어 경로

```text
UU 컨트롤러 -> Wine의 UU -> 입력 브로커 -> SDL FreeRDP
             -> GNOME Remote Desktop -> GNOME Wayland 데스크톱
```

## 새 UU 버전 유지보수

업데이트 도구는 자동 후보 탐색과 사람의 승인을 분리합니다. PE 매핑, 의미적
랜드마크, 후보 시그니처 및 대상 디스어셈블리를 생성하지만, 의미 검토와 일회용
복사본 테스트가 끝날 때까지 초안은 실행할 수 없습니다.

- [전체 업스트림 업데이트 절차](../docs/upstream-maintenance.md)
- [방법론 및 도구 목록](../docs/methodology-and-toolkit.md)
- [리버스 엔지니어링 기록](../docs/reverse-engineering.md)
- [보안](../docs/security.md)
- [문제 해결](../docs/troubleshooting.md)

비밀번호, 토큰, 장치 ID, UU 실행 파일 또는 개인 로그는 저장소에 커밋하지
않습니다. 이 프로젝트는 [The Art of Lazying](https://lazying.art)의 일부입니다.

> 명령, 해시 및 바이트의 정확한 단일 출처를 유지하기 위해 전체 기술 문서는
> 영어로 관리합니다.
