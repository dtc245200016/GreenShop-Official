# Demo GreenShop trong3–5 phút

1. Mở HTTPS website và catalog; Prometheus Targets5/5 UP, Grafana Infrastructure/Application có dữ liệu.
2. Dùng fixture Customer, nhập sai password đúng1 lần. Dùng Customer đúng credentials tại Admin portal để tạo access-denied. Không dùng tài khoản thật, không brute force.
3. Grafana Explore → GreenShop Loki, Last30m: tìm auth.login.failed/auth.access.denied. Giải thích timestamp UTC, event, reason_code, request_id/trace_id, route; bị từ chối không đồng nghĩa có xâm nhập.
4. Admin tạo danh mục và sản phẩm có ảnh; query product.created/category.created. Sự kiện chỉ phát sau SaveChanges thành công; order.created chỉ sau transaction commit, replay không tạo trùng.
5. Cho thấy non-root, network separation, secret RO, metrics token và HTTPS headers. Nếu demo alert: đúng5 lần sai có kiểm soát với fixture trong cửa sổ sạch; xem Firing rồi Resolved và receiver nội bộ. Không gọi một404 thông thường là cuộc tấn công.

Tài khoản fixture: mở riêng `secrets/demo-accounts.json`; Grafana admin: `secrets/grafana-password`. Không chiếu hoặc paste credentials. Website `https://192.168.197.128`; forward3000/9090/8080 từ VM khi dùng Windows.

## 8 query quan trọng

PromQL, datasource GreenShop Prometheus:

```promql
up{job="greenshop"}
mysql_up
nginx_up
```

Ba query trả1. LogQL, datasource GreenShop Loki:

```logql
{environment="main",service="nginx"} | json | status="404" | __error__=""
{environment="main",service="greenshop-web"} | json | event="auth.login.failed" | __error__=""
{environment="main",service="greenshop-web"} | json | event="auth.access.denied" | __error__=""
{environment="main",service="greenshop-web"} | json | event=~"category.created|product.created|order.created" | __error__=""
{environment="main",service="mysql"}
```

Mỗi dòng là một query riêng. Tất cả đã có dữ liệu thật khi nghiệm thu; login/business events cần thao tác mới hoặc chọn đúng range có dữ liệu. MySQL là operational log, không bật general query log chứa dữ liệu người dùng. Có thể thêm `job="greenshop"` để chỉ xem pipeline syslog hiện tại.

## Lệnh cơ bản

```bash
cd /home/trung/GreenShop-Official
docker compose up -d --build
docker compose ps
docker compose logs --tail 30 web_app nginx promtail
```

Đọc raw Docker logs riêng trên VM; Explore dùng bản đã sanitize. Nghiệm thu đã force-recreate Web bằng Compose và xác minh session/network/metrics/logs vẫn hoạt động, không cần chạy lại khi demo. Không yêu cầu reboot VMware trong bài kiểm này.
