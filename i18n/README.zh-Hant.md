<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu 橋接器

**透過網易 UU 遠端查看並完整控制 Ubuntu GNOME 桌面。**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="透過 UU Remote Ubuntu Bridge，從 macOS 連線至 Ubuntu GNOME 桌面的實際畫面。" width="1120">
  </a>
  <br>
  <sub>透過 UU Remote Ubuntu Bridge，從 macOS 連線至 Ubuntu GNOME 桌面的實際畫面。</sub>
</p>

</div>

這個實驗性橋接器在獨立 Wine 前綴中執行官方 Windows 用戶端，透過本機 RDP
中繼或 X11 上選用的本機 VNC 中繼分享現有 GNOME 桌面。

基礎環境為 x86-64 Ubuntu 24.04、GNOME 46 和 Wine 11。全新安裝使用已驗收的 UU `4.42.1.2835`，並核對精確雜湊及驗收紀錄。一般重新安裝會保留已安裝版本。未知二進位檔會被拒絕，不會直接套用舊補丁。

<!-- feature-status:start -->
## 哪些功能可以用

更新於 **2026-10-04**。桌面控制、文字剪貼簿和聽寫已在實測或使用者確認的路徑上可用。
「可用」指這些路徑，不代表所有裝置、鍵盤配置或 Windows 原生 UU 功能都已驗證。

| 功能 | 狀態 | 範圍與限制 |
| --- | --- | --- |
| 現有 Ubuntu 桌面 | 可用 | 畫面與重新連線保留選定工作階段及已開啟的應用程式。 |
| 滑鼠 | 可用 | 已測試中繼上的移動、點擊、按鈕、滾輪和焦點。 |
| 實體鍵盤與快捷鍵 | 可用，取決於控制端 | 字母、修飾鍵與符號；不保證所有美式、日式和 Mac 配置一致。 |
| 手機鍵盤與 Unicode | 已測試路徑可用 | 中文、標點、表情和多行文字；各輸入法仍需單獨驗證。 |
| 連續聽寫 | 日常使用確認，迴歸測試通過 | 組合輸入修訂保留先前訊息；各版本的實際手機測試範圍不同。 |
| 雙向文字剪貼簿 | 可用，取決於路徑 | 僅文字；X11/VNC 回傳需啟用，最多 60 KiB，不涵蓋圖片或檔案。 |
| UU、RDP、RealVNC 共用桌面 | 選用配置 | 共用實體 X11 桌面後端；預設的獨立工作階段不會自動合併。 |
| 解析度與畫布適配 | 可配置 | 固定尺寸或選用的 X11/VNC 穩定尺寸跟隨，不等於新增虛擬螢幕。 |
| 故障復原與開機啟動 | 有條件可用 | 服務監管重新啟動並保留登入；需要可用的 GNOME 登入及金鑰環，4.42 驗收未重新測試整機重新啟動。 |
| UU 原生終端 → Ubuntu shell | 介接程式可用，通道有條件 | 支援 UTF-8 與 PTY 尺寸調整；仍有廠商版本、連線和原生結束碼限制。 |
| `uu-shell` | 已驗證已註冊的 SSH 路徑 | 明確選擇 LazyTunnel、映射 SSH 或原生終端；SSH 成功不代表原生 UU 成功。 |
| UU 連接埠映射、SSH、SCP | 有條件可用 | 已有成功測試；接管或關閉承載連線可能中斷，不是 VPN。 |
| Super Screen／超級螢幕與額外虛擬螢幕 | 未驗證 | 無 Ubuntu 橋接驗收紀錄；一般桌面縮放不能證明可用。 |
| 防窺／隱私螢幕 | 未驗證 | 無經過驗證的 Linux 實體螢幕遮蔽及本機輸入鎖定後端，請勿依賴它保護隱私。 |
| 聲音與麥克風 | 有限支援 | 取決於主機；部分安裝特意使用靜音後端。 |
| 原生檔案傳輸、圖片／檔案剪貼簿及其他功能 | 未驗證 | 文字複製不等於檔案傳輸；已驗證 SSH 上的 SCP/SFTP 是獨立方案。 |

詳見[功能證據與限制](../docs/features.md)，以及各自獨立的
[RDP](../docs/releases/4.42.1.2835-acceptance.md) 和
[X11](../docs/releases/4.42-x11-workstation-20261001.md) 驗收紀錄。
4.42 的 Mac 控制端測試未驗證實際手機連續聽寫；共用桌面的 XRDP 0.9.24
剪貼簿另有非 BMP 表情字元限制。

假設已配置一個名為 `lab` 的裝置：

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

將 `lab` 換成你的裝置名稱。`--lazy` 需要先註冊 LazyTunnel；`--native` 請求 UU
自己的終端通道，可能獨立失敗。不會暗中切換路徑或接管桌面，詳見[終端指南](../docs/fleet-shell.md)。
<!-- feature-status:end -->

## 快速安裝

```bash
./install.sh
```

全新安裝使用已驗收的 **4.42.1.2835** 清單；一般重新安裝會保留已安裝版本。目前固定的 FreeRDP nightly 連結回傳 404，因此全新預設 RDP 安裝需要既有且雜湊完全相符的用戶端。X11/XRDP 桌面可用 `./install.sh --desktop-relay vnc` 避開此相依項目。詳見[下載復原與重複啟動器清理](../docs/fresh-install-recovery.md)。

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
- [原生 Ubuntu 終端機](../docs/native-ubuntu-terminal.md)
- [SSH 別名與雙機連接埠對應](../docs/ssh-and-port-mapping.md)

儲存庫不包含密碼、權杖、裝置識別碼、網易執行檔或私人日誌。本專案屬於
[The Art of Lazying](https://lazying.art)。

如果你更需要獨立於廠商的方案，[LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_zh_hant#review) 由另一套開源 [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) 核心提供自行託管的 SSH、終端機與 noVNC 存取。這是不同的工具；本儲存庫仍專注於相容官方 UU 用戶端。

## 支持專案

如果這個橋接器幫你節省了時間，可以支持我們繼續維護相容性：

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> 完整技術參考保留英文版本，以確保命令、雜湊和位元組記錄只有一個精確來源。
