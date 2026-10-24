# GreenShop

Đồ án **Triển khai và Quản trị Hệ thống Phần mềm — Đề tài số 9: Website thương mại điện tử**.

GreenShop sử dụng ASP.NET Core MVC, MySQL và Nginx HTTPS. Website có phân quyền Customer/Admin, quản lý sản phẩm, giỏ hàng, đơn hàng, đánh giá, chat trực tiếp và trợ lý Gemini. Prometheus/Grafana giám sát hệ thống; Loki/Promtail tập trung log.

## Khởi động

Chạy từ repository chính thức trên Ubuntu VMware:

```bash
cd /home/trung/GreenShop-Official
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Project Main cố định: **`dtc245200016_btl_tkqt_htpm`**. Cấu hình gồm 12 dịch vụ, sử dụng 7 volumes và 6 networks hiện có qua `external`. Giữ nguyên tên project và triển khai từ thư mục Official.

Cấu hình này dành cho VM hiện hữu, với images đã chuẩn bị, `.env`, `secrets/` và chứng chỉ trong `nginx/ssl/`. Máy mới cần chuẩn bị các tài nguyên này trước khi chạy; `.env.example` là mẫu cấu hình, không dùng ghi đè `.env` đang hoạt động. Ba script trong `scripts/` phục vụ thiết lập ban đầu, không cần chạy lại để khởi động hệ thống hiện có.

## Truy cập

| Thành phần | Địa chỉ trên VM |
|---|---|
| Website HTTPS | `https://192.168.197.128` |
| phpMyAdmin | `http://127.0.0.1:8080` |
| Grafana | `http://127.0.0.1:3000` |
| Prometheus | `http://127.0.0.1:9090` |

Trên Windows, dùng VS Code Remote SSH để forward các cổng 3000, 9090, 8080 và mở **Forwarded Address** thực tế. Website dùng IP VM với chứng chỉ lab. Tài khoản demo và mật khẩu Grafana được lưu riêng trong `secrets/demo-accounts.json` và `secrets/grafana-password`; không đưa các giá trị này vào Git hoặc ảnh minh chứng.

## Kiến trúc

```text
Trình duyệt → Nginx HTTPS → GreenShop Web → MySQL
Web / exporters / cAdvisor → Prometheus → Grafana
Docker syslog → Promtail → Loki → Grafana Explore
Grafana GS-SEC-001 → alert-receiver nội bộ
```

Service DNS (`web_app`, `db`, `prometheus`, `loki`) được dùng cho kết nối nội bộ. Các network tách lưu lượng ứng dụng, database, monitoring và logging. Grafana gồm 4 dashboard: Application, Infrastructure, Logs, Security; tổng cộng 19 panel, làm mới mỗi 30 giây.

## Kiểm tra nhanh

```bash
curl --cacert nginx/ssl/cert.pem https://192.168.197.128/health/ready
docker compose logs --tail 30 web_app nginx promtail
```

Trong Prometheus, `up` phải có 5 targets bằng 1: GreenShop, Prometheus, MySQL exporter, Nginx exporter và cAdvisor. Kiểm tra thêm:

```promql
up{job="greenshop"}
mysql_up
nginx_up
```

Trong Grafana Explore, chọn **GreenShop Loki**, khoảng thời gian **Last 24 hours**, chạy từng query riêng:

```logql
{environment="main",job="greenshop",service="nginx"} | json | status >= 400 | __error__=""
{environment="main",job="greenshop",service="greenshop-web"}
{environment="main",job="greenshop",service="mysql"}
```

Log MySQL là log vận hành; một nguồn có thể không phát sinh sự kiện mới liên tục. Log tập trung đã được lọc để loại thông tin nhạy cảm. Syslog UDP có thể mất log khi collector gián đoạn; Docker vẫn giữ cache log có rotation.

## Vận hành và bảo mật

- Dữ liệu MySQL, ảnh sản phẩm, keys, Grafana, Prometheus và Loki nằm trong volumes bền vững. Giữ nguyên volumes khi cập nhật dịch vụ.
- Dịch vụ có restart policy; Grafana dùng `unless-stopped` và volume dữ liệu hiện hữu. Các cổng quản trị chỉ bind loopback.
- Giữ HTTPS/security headers, non-root trên dịch vụ phù hợp, network isolation, giới hạn quyền container và secrets chỉ đọc. Tài khoản DB ứng dụng bị giới hạn trong schema `greenshop`; quyền DDL được giữ cho EF migrations.
- Chatbot dùng `AI_CHAT_ENABLED`, `AI_CHAT_MODEL` và API key hiện có trong `.env`. Giới hạn hiện tại là 20 lượt/ngày và 5 lượt/phút; bộ đếm trong RAM được reset khi Web khởi động lại. Chi phí/quota phụ thuộc Google project.

Xem [hướng dẫn quản trị và truy vấn](docs/skill.md), [hướng dẫn demo](docs/demo.md), [cấu hình monitoring/logging](monitoring/README.md) và [minh chứng](docs/evidence/).
