<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu 桥接器

**通过网易 UU 远程查看并完整控制 Ubuntu GNOME 桌面。**

</div>

这个实验性桥接器在独立 Wine 前缀中运行官方 Windows 客户端，并通过本机
RDP 中继呈现真实的 GNOME Wayland 会话。画面、鼠标、键盘、重新连接和服务
自动恢复均已验证。

当前版本有意锁定为 UU 远程 `4.33.0.8907`、Ubuntu 24.04、GNOME 46 和
Wine 11。任何未知二进制文件都会被拒绝，绝不会直接套用旧补丁。

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

## 支持项目

如果这个桥接器帮你节省了时间，可以支持我们继续维护兼容性：

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> 完整技术参考保留英文版本，以确保命令、哈希和字节记录只有一个精确来源。
