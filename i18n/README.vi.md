<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Xem và điều khiển đầy đủ máy tính Ubuntu GNOME bằng NetEase UU Remote.**

</div>

Cầu nối thử nghiệm này chạy ứng dụng Windows chính thức trong một Wine prefix
riêng và chuyển tiếp phiên GNOME Wayland thật qua kết nối RDP cục bộ. Hình ảnh,
chuột, bàn phím, kết nối lại và tự phục hồi dịch vụ đều hoạt động.

Phiên bản hiện tại được khóa có chủ đích ở UU Remote `4.33.0.8907`, Ubuntu
24.04, GNOME 46 và Wine 11. Công cụ không bao giờ vá tệp nhị phân chưa biết.

## Cài đặt nhanh

```bash
./install.sh
```

Trình cài đặt có tính lặp an toàn sẽ cài các gói phụ thuộc, kiểm tra hash, biên
dịch thành phần tương thích, cấu hình GNOME Remote Desktop, lưu mật khẩu RDP
trong GNOME Keyring và khởi động dịch vụ systemd của người dùng.

## Đường điều khiển

```text
Bộ điều khiển UU -> UU trong Wine -> bộ chuyển tiếp nhập liệu -> SDL FreeRDP
                 -> GNOME Remote Desktop -> màn hình GNOME Wayland
```

## Duy trì khi UU cập nhật

Bộ công cụ tách việc tìm ứng viên tự động khỏi bước phê duyệt của con người.
Nó tạo bản đồ PE, mốc ngữ nghĩa, chữ ký ứng viên và bản dịch ngược có mục tiêu,
nhưng bản nháp không thể chạy cho đến khi được kiểm tra về ngữ nghĩa và thử
trên một bản sao dùng một lần.

- [Quy trình cập nhật upstream đầy đủ](../docs/upstream-maintenance.md)
- [Phương pháp và danh mục công cụ](../docs/methodology-and-toolkit.md)
- [Hồ sơ dịch ngược](../docs/reverse-engineering.md)
- [Bảo mật](../docs/security.md)
- [Khắc phục sự cố](../docs/troubleshooting.md)

Kho mã không chứa mật khẩu, token, mã thiết bị, tệp thực thi UU hoặc log riêng
tư. Dự án thuộc [The Art of Lazying](https://lazying.art).

> Tài liệu kỹ thuật đầy đủ được giữ bằng tiếng Anh để lệnh, hash và byte chỉ có
> một nguồn chính xác duy nhất.
