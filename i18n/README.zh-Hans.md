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

仓库不包含密码、令牌、设备标识、网易可执行文件或私人日志。本项目属于
[The Art of Lazying](https://lazying.art)。

> 完整技术参考保留英文版本，以确保命令、哈希和字节记录只有一个精确来源。
