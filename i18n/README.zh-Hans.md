<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu 桥接器

**通过网易 UU 远程查看并完整控制 Ubuntu GNOME 桌面。**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="通过 UU Remote Ubuntu Bridge，从 macOS 连接 Ubuntu GNOME 桌面的实际画面。" width="1120">
  </a>
  <br>
  <sub>通过 UU Remote Ubuntu Bridge，从 macOS 连接 Ubuntu GNOME 桌面的实际画面。</sub>
</p>

</div>

这个实验性桥接器在独立 Wine 前缀中运行官方 Windows 客户端，通过本机 RDP
中继或 X11 上可选的本机 VNC 中继共享现有 GNOME 桌面。

基础环境为 x86-64 Ubuntu 24.04、GNOME 46 和 Wine 11。全新安装仍锁定
UU `4.33.0.8907`；`4.42.1.2835` 有独立的精确哈希清单及验收记录。
未知二进制文件会被拒绝，不会直接套用旧补丁。

UU 只从网易官方域名 [uuyc.163.com](https://uuyc.163.com/) 下载。官方页面
目前没有列出 Linux 被控端；本桥使用官方 Windows 客户端并核对安装包完整哈希。
不要从仿冒下载页安装未经验证的 `.deb`、`.rpm` 或 AppImage。

正在使用或需要其他 Ubuntu 版本、桌面/会话、CPU 架构、UU 版本或控制端平台？
请[提交一条兼容性反馈或需求](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/issues/new?template=compatibility.yml)。
提交免费且内容公开，但不构成支持承诺。请勿附加或链接专有二进制文件、凭据、
账号或设备 ID、原始日志、截图或私有配置。

如果想先弄清 Wine、中继、真实 GNOME 桌面和输入链路怎样接在一起，可以读这篇
[完整中文指南](https://blog.lazying.art/html/computer_internet/3818/use-uu-remote-on-ubuntu-with-a-reproducible-bridge.html?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=zh_hans_guide)。
它也说明了已验证范围、上游更新为何需要重新审查，以及什么时候不适合使用这座桥。

<!-- feature-status:start -->
## 哪些功能可以用

更新于 **2026-10-04**。桌面控制、文本剪贴板和听写已在实测或用户确认的链路上可用。
“可用”指这些链路，不代表所有设备、键盘布局或 Windows 原生 UU 功能都已验证。

| 功能 | 状态 | 范围与限制 |
| --- | --- | --- |
| 现有 Ubuntu 桌面 | 可用 | 画面与重连保留选定会话及已打开的应用。 |
| 鼠标 | 可用 | 已测试中继上的移动、点击、按键、滚轮和焦点。 |
| 实体键盘与快捷键 | 可用，取决于控制端 | 字母、修饰键与符号；不保证所有美式、日式和 Mac 布局一致。 |
| 手机键盘与 Unicode | 已测试链路可用 | 中文、标点、表情和多行文本；各输入法仍需单独验证。 |
| 连续听写 | 日常使用确认，回归测试通过 | 组合输入修订保留先前消息；各版本的真实手机测试范围不同。 |
| 双向文本剪贴板 | 可用，取决于链路 | 仅文本；X11/VNC 回传需启用，最多 60 KiB，不涵盖图片或文件。 |
| UU、RDP、RealVNC 共用桌面 | 可选配置 | 共用物理 X11 桌面后端；默认的独立会话不会自动合并。 |
| 分辨率与画布适配 | 可配置 | 固定尺寸或可选的 X11/VNC 稳定尺寸跟随，不等于新增虚拟屏幕。 |
| 故障恢复与开机启动 | 有条件可用 | 服务监管重启并保留登录；需要可用的 GNOME 登录及密钥环，4.42 验收未重新测试整机重启。 |
| UU 原生终端 → Ubuntu shell | 适配器可用，通道有条件 | 支持 UTF-8 与 PTY 尺寸调整；仍有厂商版本、连接和原生退出码限制。 |
| `uu-shell` | 已验证已注册的 SSH 链路 | 明确选择 LazyTunnel、映射 SSH 或原生终端；SSH 成功不代表原生 UU 成功。 |
| UU 端口映射、SSH、SCP | 有条件可用 | 已有成功测试；接管或关闭承载连接可能中断，不是 VPN。 |
| Super Screen／超级屏与额外虚拟屏幕 | 未验证 | 无 Ubuntu 桥接验收记录；普通桌面缩放不能证明可用。 |
| 防窥／隐私屏幕 | 未验证 | 无经过验证的 Linux 物理屏幕遮蔽及本地输入锁定后端，请勿依赖它保护隐私。 |
| 声音与麦克风 | 有限支持 | 取决于主机；部分安装特意使用静音后端。 |
| 原生文件传输、图片／文件剪贴板及其他功能 | 未验证 | 文本复制不等于文件传输；已验证 SSH 上的 SCP/SFTP 是独立方案。 |

详见[功能证据与限制](../docs/features.md)，以及各自独立的
[RDP](../docs/releases/4.42.1.2835-acceptance.md) 和
[X11](../docs/releases/4.42-x11-workstation-20261001.md) 验收记录。
4.42 的 Mac 控制端测试未验证真实手机连续听写；共用桌面的 XRDP 0.9.24
剪贴板另有非 BMP 表情字符限制。

假设已配置一个名为 `lab` 的设备：

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

将 `lab` 换成你的设备名。`--lazy` 需要先注册 LazyTunnel；`--native` 请求 UU
自己的终端通道，可能独立失败。不会暗中切换链路或接管桌面，详见[终端指南](../docs/fleet-shell.md)。
<!-- feature-status:end -->

## 快速安装

```bash
./install.sh
```

这个幂等安装脚本会安装依赖、校验上游文件、编译所有兼容组件、配置 GNOME
Remote Desktop、把 RDP 密码保存到 GNOME Keyring，并启动用户级 systemd
服务。重复运行不会破坏已有账户状态。

## 控制链路

```text
UU 控制端 -> Wine 中的 UU -> 输入代理 -> SDL FreeRDP
           -> GNOME Remote Desktop -> GNOME Wayland 桌面
```

## 如何适配上游更新

新的维护工具把“自动寻找候选位置”和“人工语义批准”严格分开。它会生成 PE
映射、语义地标、候选签名和定点反汇编，但在逐项审阅并对一次性副本完成测试
前，草稿清单无法被补丁器或安装器使用。

- [完整上游维护流程](../docs/upstream-maintenance.md)
- [解决方法与工具清单](../docs/methodology-and-toolkit.md)
- [精确逆向工程记录](../docs/reverse-engineering.md)
- [安全边界](../docs/security.md)
- [故障排查](../docs/troubleshooting.md)
- [原生 Ubuntu 终端](../docs/native-ubuntu-terminal.md)
- [SSH 别名与双机端口映射](../docs/ssh-and-port-mapping.md)

仓库不包含密码、令牌、设备标识、网易可执行文件或私人日志。本项目属于
[The Art of Lazying](https://lazying.art)。

如果你更需要独立于厂商的方案，[LazyRemote 中文页](https://remote.lazying.art/zh-Hans/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_zh_hans#review) 由另一套开源 [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) 核心提供自托管的 SSH、终端与 noVNC 访问。这是不同的工具；本仓库仍专注于兼容官方 UU 客户端。

如果已有一台可连接的中继和最多三台电脑，但希望在改动前先核对端口暴露与密钥
角色，可以先看[完整中文样例](https://remote.lazying.art/zh-Hans/sample-report.html?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=network_review_sample_zh_hans)。
可选的固定评估服务为 USD 250，先做[免费的纯元数据适配确认](https://lazying.art/lazyremote/fit-check/zh-Hans/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=network_review_fit_check_zh_hans)，
不包含部署、硬件和持续支持。

## 支持项目

如果这个桥接器帮你节省了时间，可以支持我们继续维护兼容性：

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> 完整技术参考保留英文版本，以确保命令、哈希和字节记录只有一个精确来源。
