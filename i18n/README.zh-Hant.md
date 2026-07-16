<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu 橋接器

**透過網易 UU 遠端查看並完整控制 Ubuntu GNOME 桌面。**

</div>

這個實驗性橋接器在獨立 Wine 前綴中執行官方 Windows 用戶端，並透過本機
RDP 中繼呈現真實的 GNOME Wayland 工作階段。畫面、滑鼠、鍵盤、重新連線和
服務自動復原均已驗證。

目前版本刻意鎖定為 UU 遠端 `4.33.0.8907`、Ubuntu 24.04、GNOME 46 和
Wine 11。任何未知二進位檔都會被拒絕，絕不直接套用舊補丁。

## 快速安裝

```bash
./install.sh
```

這個冪等安裝腳本會安裝相依套件、驗證上游檔案、編譯相容元件、設定 GNOME
Remote Desktop、將 RDP 密碼保存到 GNOME Keyring，並啟動使用者層級
systemd 服務。重複執行不會破壞既有帳戶狀態。

## 控制路徑

```text
UU 控制端 -> Wine 中的 UU -> 輸入代理 -> SDL FreeRDP
           -> GNOME Remote Desktop -> GNOME Wayland 桌面
```

## 如何維護上游更新

新的維護工具把「自動尋找候選位置」和「人工語意核准」嚴格分開。它會產生
PE 對應、語意地標、候選簽章和定點反組譯，但在逐項審閱並對一次性副本完成
測試前，草稿清單無法被補丁器或安裝器使用。

- [完整上游維護流程](../docs/upstream-maintenance.md)
- [解題方法與工具清單](../docs/methodology-and-toolkit.md)
- [精確逆向工程記錄](../docs/reverse-engineering.md)
- [安全邊界](../docs/security.md)
- [疑難排解](../docs/troubleshooting.md)

儲存庫不包含密碼、權杖、裝置識別碼、網易執行檔或私人日誌。本專案屬於
[The Art of Lazying](https://lazying.art)。

> 完整技術參考保留英文版本，以確保命令、雜湊和位元組記錄只有一個精確來源。
