<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**NetEase UU Remote から Ubuntu GNOME デスクトップを表示し、完全に操作します。**

</div>

この実験的なブリッジは、公式 Windows クライアントを分離された Wine
プレフィックスで実行し、ローカル RDP 経由で実際の GNOME Wayland
セッションを中継します。映像、マウス、キーボード、再接続、サービスの
自動復旧を利用できます。

現在の対応範囲は UU Remote `4.33.0.8907`、Ubuntu 24.04、GNOME 46、
Wine 11 に意図的に固定されています。未知のバイナリは一切パッチしません。

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

パスワード、トークン、デバイス ID、UU 実行ファイル、個人ログはコミット
しません。このプロジェクトは [The Art of Lazying](https://lazying.art)
の一部です。

> コマンド、ハッシュ、バイト列の正確な単一情報源を保つため、完全な技術資料は
> 英語版に集約しています。
