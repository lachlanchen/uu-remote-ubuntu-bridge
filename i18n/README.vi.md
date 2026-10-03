<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Xem và điều khiển đầy đủ máy tính Ubuntu GNOME bằng NetEase UU Remote.**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="Màn hình Ubuntu GNOME được truy cập từ macOS qua UU Remote Ubuntu Bridge." width="1120">
  </a>
  <br>
  <sub>Màn hình Ubuntu GNOME được truy cập từ macOS qua UU Remote Ubuntu Bridge.</sub>
</p>

</div>

Cầu nối thử nghiệm chạy ứng dụng Windows chính thức trong Wine prefix riêng,
chia sẻ màn hình GNOME hiện có qua RDP cục bộ hoặc chuyển tiếp VNC cục bộ tùy
chọn dành cho X11.

Môi trường cơ sở là Ubuntu 24.04 x86-64, GNOME 46 và Wine 11. Cài đặt mới vẫn
khóa ở UU `4.33.0.8907`; `4.42.1.2835` có manifest hash chính xác và hồ sơ nghiệm
thu riêng. Công cụ không vá tệp nhị phân chưa biết.

<!-- feature-status:start -->
## Những tính năng đang hoạt động

Cập nhật **2026-10-04**. Điều khiển màn hình, clipboard văn bản và nhập liệu bằng
giọng nói hoạt động trên các đường đã thử nghiệm hoặc được người dùng xác nhận.
Điều này không bảo đảm mọi thiết bị, bố cục bàn phím hay tính năng UU trên Windows.

| Tính năng | Trạng thái | Phạm vi và giới hạn |
| --- | --- | --- |
| Màn hình Ubuntu hiện có | Hoạt động | Hình ảnh và kết nối lại giữ nguyên phiên đã chọn cùng các ứng dụng đang mở. |
| Chuột | Hoạt động | Di chuyển, nhấp, nút, con lăn và tiêu điểm trên đường chuyển tiếp đã thử nghiệm. |
| Bàn phím vật lý / phím tắt | Hoạt động, tùy máy điều khiển | Chữ, phím bổ trợ và ký hiệu; không bảo đảm mọi bố cục US/JIS/Mac. |
| Bàn phím điện thoại / Unicode | Hoạt động trên đường đã thử | Tiếng Trung, dấu câu, emoji và văn bản nhiều dòng; từng IME cần kiểm tra riêng. |
| Nhập giọng nói liên tục | Được xác nhận khi sử dụng, có kiểm thử hồi quy | Sửa phần đang nhập vẫn giữ thông điệp trước đó; phạm vi thử trên điện thoại thật tùy phiên bản. |
| Clipboard văn bản hai chiều | Hoạt động, tùy đường kết nối | Chỉ văn bản. Chiều trả về X11/VNC là tùy chọn, tối đa 60 KiB; không gồm ảnh hoặc tệp. |
| UU / RDP / RealVNC dùng chung màn hình | Cấu hình tùy chọn | Backend X11 vật lý dùng chung; các phiên mặc định riêng biệt không tự hợp nhất. |
| Độ phân giải / khung hình | Có thể cấu hình | Kích thước cố định hoặc tùy chọn theo kích thước X11/VNC ổn định; không phải màn hình ảo bổ sung. |
| Khôi phục / chạy sau khởi động | Có điều kiện | Dịch vụ được giám sát và giữ đăng nhập; cần phiên GNOME cùng keyring dùng được. Nghiệm thu 4.42 chưa thử khởi động lại máy. |
| Terminal gốc UU → shell Ubuntu | Bộ chuyển đổi hoạt động, kênh có điều kiện | UTF-8 và đổi kích thước PTY; vẫn có giới hạn phiên bản, kết nối và mã thoát của kênh gốc. |
| `uu-shell` | Đã kiểm tra với SSH đăng ký sẵn | Chọn rõ LazyTunnel, SSH qua ánh xạ cổng hoặc terminal gốc; SSH thành công không chứng minh kênh UU gốc. |
| Ánh xạ cổng UU / SSH / SCP | Có điều kiện | Có đường đã thử thành công; giành quyền điều khiển hoặc đóng kết nối vận chuyển có thể làm gián đoạn. Không phải VPN. |
| Super Screen / màn hình ảo bổ sung | Chưa xác minh | Chưa có nghiệm thu trên cầu nối Ubuntu; đổi kích thước màn hình thường không đủ chứng minh. |
| Chống nhìn trộm / màn hình riêng tư | Chưa xác minh | Chưa có backend Linux được kiểm chứng để che màn hình vật lý và khóa đầu vào cục bộ. Không dựa vào đó để bảo vệ riêng tư. |
| Âm thanh / micrô | Hạn chế | Tùy máy; một số cài đặt chủ động dùng backend im lặng. |
| Truyền tệp gốc, clipboard ảnh/tệp và tính năng khác | Chưa xác minh | Sao chép văn bản không phải truyền tệp; SCP/SFTP qua SSH đã kiểm tra là lựa chọn riêng. |

Xem [bằng chứng và giới hạn](../docs/features.md) cùng nghiệm thu riêng cho
[RDP](../docs/releases/4.42.1.2835-acceptance.md) và
[X11](../docs/releases/4.42-x11-workstation-20261001.md). Thử nghiệm máy điều khiển Mac
4.42 chưa xác minh nhập giọng nói liên tục trên điện thoại thật. Clipboard của màn hình
dùng chung qua XRDP 0.9.24 cũng có giới hạn đã ghi nhận với emoji ngoài BMP.

Với máy ngang hàng đã cấu hình tên `lab`:

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

Thay `lab` bằng tên cấu hình của bạn. `--lazy` yêu cầu đăng ký LazyTunnel;
`--native` yêu cầu terminal riêng của UU và có thể thất bại độc lập. Không âm thầm
đổi đường hay giành quyền điều khiển màn hình. [Chi tiết](../docs/fleet-shell.md).
<!-- feature-status:end -->

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
- [Terminal Ubuntu gốc](../docs/native-ubuntu-terminal.md)
- [Bí danh SSH và ánh xạ cổng giữa hai máy tính](../docs/ssh-and-port-mapping.md)

Kho mã không chứa mật khẩu, token, mã thiết bị, tệp thực thi UU hoặc log riêng
tư. Dự án thuộc [The Art of Lazying](https://lazying.art).

Nếu cần một hướng không phụ thuộc nhà cung cấp, [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_vi#review) dùng lõi mã nguồn mở tách biệt [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) để cung cấp quyền truy cập tự lưu trữ qua SSH, terminal và noVNC. Đây là một công cụ khác; kho mã này vẫn là lớp tương thích dành cho ứng dụng UU chính thức.

## Ủng hộ dự án

Nếu cây cầu này giúp bạn tiết kiệm thời gian, bạn có thể ủng hộ việc duy trì khả năng tương thích:

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> Tài liệu kỹ thuật đầy đủ được giữ bằng tiếng Anh để lệnh, hash và byte chỉ có
> một nguồn chính xác duy nhất.
