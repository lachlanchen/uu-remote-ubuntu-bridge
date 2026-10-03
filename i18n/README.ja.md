<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**NetEase UU Remote から Ubuntu GNOME デスクトップを表示し、完全に操作します。**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="UU Remote Ubuntu Bridge を使い、macOS から Ubuntu GNOME デスクトップに接続した画面。" width="1120">
  </a>
  <br>
  <sub>UU Remote Ubuntu Bridge を使い、macOS から Ubuntu GNOME デスクトップに接続した画面。</sub>
</p>

</div>

この実験的なブリッジは公式 Windows クライアントを分離した Wine プレフィックスで
実行し、ローカル RDP、または X11 向けの任意のローカル VNC 中継で既存の GNOME
デスクトップを共有します。

基準環境は x86-64 Ubuntu 24.04、GNOME 46、Wine 11 です。新規インストールは
引き続き UU `4.33.0.8907` に固定し、`4.42.1.2835` は専用の厳密なハッシュ
マニフェストと検証記録で扱います。未知のバイナリにはパッチしません。

<!-- feature-status:start -->
## 動作する機能

確認日：**2026-10-04**。通常のデスクトップ操作、テキストのコピー、音声入力は、
試験済みまたは利用者が確認した経路で動作しています。すべての端末、キー配列、
Windows 版 UU の機能を検証済みという意味ではありません。

| 機能 | 状態 | 範囲と制限 |
| --- | --- | --- |
| 既存の Ubuntu デスクトップ | 動作確認済み | 映像と再接続は選択したセッションと開いているアプリを維持します。 |
| マウス | 動作確認済み | 検証済みの中継経路で移動、クリック、ボタン、ホイール、フォーカスが動作。 |
| 物理キーボード・ショートカット | 動作、クライアント依存 | 文字、修飾キー、記号に対応。US・JIS・Mac 全配列の一致は保証しません。 |
| スマートフォンのキーボード・Unicode | 検証済み経路で動作 | 中国語、句読点、絵文字、複数行テキスト。各 IME は個別確認が必要。 |
| 連続音声入力 | 日常利用で確認、回帰試験済み | 変換途中の修正で以前のメッセージを消さない設計。実機試験の範囲はリリースごとに異なります。 |
| 双方向テキストクリップボード | 動作、経路依存 | テキストのみ。X11/VNC の返送は任意設定で最大 60 KiB。画像・ファイルは対象外。 |
| UU・RDP・RealVNC で同じデスクトップ | 任意設定 | 物理 X11 共有バックエンドを使用。既定の別セッションを自動統合する機能ではありません。 |
| 解像度・キャンバス調整 | 設定可能 | 固定サイズ、または X11/VNC の安定したサイズ変更への追従。追加仮想画面とは別です。 |
| 復旧・起動時の自動開始 | 条件付き | サービス再起動とログイン保持。利用可能な GNOME ログインとキーリングが必要。4.42 検証時の本体再起動試験は未実施。 |
| UU ネイティブ端末 → Ubuntu shell | アダプター動作、通信は条件付き | UTF-8 と PTY サイズ変更。ベンダーのバージョン・接続エラーや終了コードの制限があります。 |
| `uu-shell` | 登録済み SSH 経路で検証済み | LazyTunnel、転送 SSH、ネイティブ端末を明示選択。SSH 成功は UU ネイティブ端末の証明ではありません。 |
| UU ポート転送・SSH・SCP | 条件付き | 成功した経路あり。接続の引き継ぎや終了で切断される場合があります。VPN ではありません。 |
| Super Screen・追加仮想画面 | 未検証 | Ubuntu ブリッジでの合格記録なし。通常の画面リサイズは証明になりません。 |
| 覗き見防止・プライバシー画面 | 未検証 | Linux の物理画面非表示とローカル入力ロックの検証済みバックエンドはありません。プライバシー保護を依存させないでください。 |
| 音声・マイク | 制限あり | ホスト依存。一部環境では意図的に無音バックエンドを使用します。 |
| ネイティブファイル転送・画像やファイルのコピー・その他 | 未検証 | テキストコピーとは別機能。検証済み SSH 上の SCP/SFTP は独立した選択肢です。 |

[根拠と制限](../docs/features.md)、それぞれ独立した
[RDP](../docs/releases/4.42.1.2835-acceptance.md)・[X11](../docs/releases/4.42-x11-workstation-20261001.md)
検証記録を参照してください。4.42 の Mac コントローラー試験は実際のスマートフォンでの
連続音声入力を含みません。共有デスクトップの XRDP 0.9.24 クリップボードには非 BMP 絵文字の制限もあります。

`lab` という接続先を設定済みの場合：

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

`lab` を自分の接続先名に置き換えます。`--lazy` には LazyTunnel 登録が必要です。
`--native` は UU 独自の端末を要求し、別途失敗する場合があります。暗黙の代替経路や
デスクトップの乗っ取りは行いません。[詳細](../docs/fleet-shell.md)を参照してください。
<!-- feature-status:end -->

## クイックインストール

```bash
./install.sh
```

冪等なインストーラーが依存パッケージの導入、成果物のハッシュ検証、互換
コンポーネントのビルド、GNOME Remote Desktop の設定、GNOME Keyring
への RDP パスワード保存、systemd ユーザーサービスの起動まで行います。

## 制御経路

```text
UU コントローラー -> Wine 上の UU -> 入力ブローカー -> SDL FreeRDP
                   -> GNOME Remote Desktop -> GNOME Wayland デスクトップ
```

## UU 更新への対応

新しいツールは、自動候補探索と人による承認を分離します。PE マップ、意味的
ランドマーク、候補シグネチャ、対象部分の逆アセンブルを生成しますが、意味を
確認し使い捨てコピーでテストするまでは実行不能なドラフトのままです。

- [上流更新の完全な手順](../docs/upstream-maintenance.md)
- [方法論とツール一覧](../docs/methodology-and-toolkit.md)
- [リバースエンジニアリング記録](../docs/reverse-engineering.md)
- [セキュリティ](../docs/security.md)
- [トラブルシューティング](../docs/troubleshooting.md)
- [Ubuntu ネイティブ端末](../docs/native-ubuntu-terminal.md)
- [SSH エイリアスと2台間のポート転送](../docs/ssh-and-port-mapping.md)

パスワード、トークン、デバイス ID、UU 実行ファイル、個人ログはコミット
しません。このプロジェクトは [The Art of Lazying](https://lazying.art)
の一部です。

ベンダーに依存しない経路が必要な場合は、別のオープンソース中核 [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) を使った [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_ja#review) で、SSH、ターミナル、noVNC へのセルフホスト型アクセスを利用できます。これは別のツールであり、このリポジトリは公式 UU クライアント向けの互換経路に引き続き専念します。

## プロジェクトを支援

このブリッジが時間の節約になった場合は、継続的な互換性メンテナンスを支援できます：

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> コマンド、ハッシュ、バイト列の正確な単一情報源を保つため、完全な技術資料は
> 英語版に集約しています。
