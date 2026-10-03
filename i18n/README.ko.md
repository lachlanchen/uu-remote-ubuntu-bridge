<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**NetEase UU Remote로 Ubuntu GNOME 데스크톱을 보고 완전히 제어합니다.**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="UU Remote Ubuntu Bridge를 통해 macOS에서 접속한 Ubuntu GNOME 데스크톱." width="1120">
  </a>
  <br>
  <sub>UU Remote Ubuntu Bridge를 통해 macOS에서 접속한 Ubuntu GNOME 데스크톱.</sub>
</p>

</div>

이 실험적 브리지는 공식 Windows 클라이언트를 격리된 Wine 프리픽스에서 실행하고,
로컬 RDP 또는 X11에서 선택 가능한 로컬 VNC 중계로 기존 GNOME 데스크톱을 공유합니다.

기준 환경은 x86-64 Ubuntu 24.04, GNOME 46, Wine 11입니다. 새 설치는 여전히
UU `4.33.0.8907`에 고정되며, `4.42.1.2835`는 별도의 정확한 해시 매니페스트와
검증 기록으로 관리합니다. 알 수 없는 바이너리는 패치하지 않습니다.

<!-- feature-status:start -->
## 작동하는 기능

확인 날짜: **2026-10-04**. 데스크톱 제어, 텍스트 클립보드와 받아쓰기는 테스트하거나
사용자가 확인한 경로에서 작동합니다. 모든 기기, 키보드 배열 또는 Windows UU 기능을
검증했다는 뜻은 아닙니다.

| 기능 | 상태 | 범위와 제한 |
| --- | --- | --- |
| 기존 Ubuntu 데스크톱 | 작동 | 화면과 재연결이 선택한 세션 및 열려 있는 앱을 유지합니다. |
| 마우스 | 작동 | 검증된 중계 경로에서 이동, 클릭, 버튼, 휠, 포커스가 작동합니다. |
| 물리 키보드 / 단축키 | 작동, 클라이언트에 따라 다름 | 문자, 조합 키, 기호 지원. 모든 US/JIS/Mac 배열을 보장하지 않습니다. |
| 휴대폰 키보드 / Unicode | 검증된 경로에서 작동 | 중국어, 문장 부호, 이모지, 여러 줄 텍스트. 개별 IME 확인은 필요합니다. |
| 연속 받아쓰기 | 일상 사용 확인, 회귀 테스트 완료 | 조합 중인 입력을 수정해도 이전 메시지를 유지합니다. 실제 휴대폰 테스트 범위는 버전마다 다릅니다. |
| 양방향 텍스트 클립보드 | 작동, 경로에 따라 다름 | 텍스트만 지원. X11/VNC 반환 경로는 선택 사항이며 최대 60 KiB. 이미지와 파일은 제외됩니다. |
| UU / RDP / RealVNC의 동일 데스크톱 | 선택적 구성 | 물리 X11 공유 백엔드. 기본 별도 세션이 자동으로 합쳐지지는 않습니다. |
| 해상도 / 캔버스 맞춤 | 구성 가능 | 고정 크기 또는 안정된 X11/VNC 크기 추적. 추가 가상 화면 기능은 아닙니다. |
| 복구 / 부팅 시 시작 | 조건부 | 서비스 자동 재시작과 로그인 유지. 사용 가능한 GNOME 로그인 및 키링 필요. 4.42 검증에서 새 재부팅 테스트는 하지 않았습니다. |
| UU 기본 터미널 → Ubuntu 셸 | 어댑터 작동, 통신은 조건부 | UTF-8 및 PTY 크기 조절. 공급업체 버전, 연결 오류, 기본 종료 코드 제한이 남아 있습니다. |
| `uu-shell` | 등록된 SSH로 검증 | LazyTunnel, 포트 매핑 SSH 또는 기본 터미널을 명시적으로 선택. SSH 성공은 UU 기본 통신 검증이 아닙니다. |
| UU 포트 매핑 / SSH / SCP | 조건부 | 성공한 경로가 있으나 제어권 인계나 연결 종료 시 끊길 수 있습니다. VPN이 아닙니다. |
| Super Screen / 추가 가상 화면 | 미검증 | Ubuntu 브리지 검증 기록 없음. 일반 화면 크기 변경은 증거가 아닙니다. |
| 엿보기 방지 / 프라이버시 화면 | 미검증 | Linux 물리 화면 숨김과 로컬 입력 잠금용 검증된 백엔드가 없습니다. 개인정보 보호 수단으로 의존하지 마세요. |
| 오디오 / 마이크 | 제한적 | 호스트에 따라 다르며 일부 설치는 의도적으로 무음 백엔드를 사용합니다. |
| 기본 파일 전송, 이미지/파일 클립보드, 기타 기능 | 미검증 | 텍스트 복사는 파일 전송이 아닙니다. 검증된 SSH의 SCP/SFTP는 별도 선택지입니다. |

[근거와 제한](../docs/features.md), 별도의 [RDP](../docs/releases/4.42.1.2835-acceptance.md) 및
[X11](../docs/releases/4.42-x11-workstation-20261001.md) 검증 기록을 참고하세요.
4.42 Mac 제어 클라이언트 테스트는 실제 휴대폰 연속 받아쓰기를 검증하지 않았습니다.
공유 데스크톱의 XRDP 0.9.24 클립보드에는 BMP 밖 이모지 제한도 있습니다.

`lab`이라는 기기를 이미 구성한 경우:

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

`lab`을 자신의 프로필 이름으로 바꾸세요. `--lazy`는 LazyTunnel 등록이 필요합니다.
`--native`는 UU 자체 터미널을 요청하며 별도로 실패할 수 있습니다. 자동 전환이나
데스크톱 제어권 인계는 하지 않습니다. [상세 안내](../docs/fleet-shell.md).
<!-- feature-status:end -->

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
- [Ubuntu 네이티브 터미널](../docs/native-ubuntu-terminal.md)
- [SSH 별칭과 두 컴퓨터 간 포트 매핑](../docs/ssh-and-port-mapping.md)

비밀번호, 토큰, 장치 ID, UU 실행 파일 또는 개인 로그는 저장소에 커밋하지
않습니다. 이 프로젝트는 [The Art of Lazying](https://lazying.art)의 일부입니다.

특정 공급업체에 의존하지 않는 경로가 필요하다면 [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_ko#review)를 사용할 수 있습니다. 별도의 오픈 소스 [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) 코어를 바탕으로 SSH, 터미널, noVNC에 대한 자체 호스팅 접근을 제공합니다. 서로 다른 도구이며, 이 저장소는 계속 공식 UU 클라이언트의 호환 경로에 집중합니다.

## 프로젝트 후원

이 브리지가 시간을 아껴 주었다면 지속적인 호환성 유지보수를 후원할 수 있습니다:

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> 명령, 해시 및 바이트의 정확한 단일 출처를 유지하기 위해 전체 기술 문서는
> 영어로 관리합니다.
