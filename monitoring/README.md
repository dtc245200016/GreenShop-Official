# Monitoring & Logging GreenShop Main

Khởi động bằng `docker compose up -d --build` từ repository Official. Một Compose,12 service mặc định, không QA/profile/private compose.json. [Demo và query](../docs/demo.md), [kết quả](../docs/evidence/commit3/main-restoration.md).

## Metrics

Prometheus scrape10s: `greenshop`, `mysql`, `nginx`, `cadvisor`, `prometheus`; retention3d/512MiB. Metrics token dùng chung Web/Prometheus qua file secret RO. Web và Prometheus có monitoring_net, alias web_app bền vững qua recreate. Exporters chỉ được xem là hoạt động khi mysql_up/nginx_up=1.

Grafana OSS local admin, anonymous/signup tắt, loopback3000; 3 metric dashboards +1 logs dashboard, tổng19 panel, datasource greenshop-prometheus/greenshop-loki và1 alert GS-SEC-001. Không Grafana Cloud. CPU/RAM panels là dữ liệu cAdvisor/container thật. Credential hiện hữu và toàn bộ secrets được giữ nguyên; secret ở ../secrets ngoài Git.

## Logs

Cấu hình: [Promtail](promtail/promtail.yml), [Loki](loki/loki.yml), [Nginx JSON](../nginx/default.conf). Docker daemon gửi console của Web/Nginx/MySQL bằng syslog RFC5424micro tới UDP127.0.0.1:1514. Promtail10001:10001 nhận syslog, xử lý closed templates, gửi http://loki:3100/loki/api/v1/push. Không Docker socket/CIDs/file_sd_configs; recreate nguồn không cần chạy helper. Promtail tham gia logging_net và admin_net để Docker publish loopback listener; DB không trên hai mạng này.

Nhãn tĩnh ở syslog.labels: environment=main, project=dtc245200016_btl_tkqt_htpm, job=greenshop, source=docker. relabel_configs allowlist APP-NAME rồi gán service: nginx/greenshop-web/mysql. pipeline_stages parse JSON Web/Nginx hoặc code MySQL, giữ metadata bounded; không forward Message/Exception/State/Scopes/raw URL/identity/payment payload. Request/trace IDs không là stream labels. Historical streams cũ vẫn query bằng environment/service; không re-ingest hoặc xóa Loki storage.

UDP/syslog và buffer4MiB không bảo đảm zero-loss; khi collector dừng có thể mất log tập trung, local Docker cache10m×3 vẫn phục vụ logs. Không nhận durability bằng file tail/positions cho nguồn syslog. Loki retention72h +2h grace đã cấu hình; physical expiry không được tuyên bố đã quan sát. Promtail được giữ theo yêu cầu đồ án; không tuyên bố đây là hướng triển khai production mới.

## Alert GS-SEC-001

Giữ rule `sum(greenshop_auth_login_failures_last_60s) >= bool 5`, không hạ threshold/rate limit. 4 sai Normal,5 sai Firing, sau cửa sổ60s tự Resolved; webhook gửi receiver Main nội bộ. No Data/Error được tách thành DatasourceNoData/DatasourceError, không coi thiếu mẫu là đăng nhập sai. UID contact point cũ được giữ để không tạo duplicate identity; nó không phải một môi trường QA. Không email/third party hoặc khẳng định đã gửi cho quản trị viên bên ngoài.

## Kiểm tra nhanh

```bash
docker compose ps
docker compose logs --tail 30 promtail loki
```

Grafana Explore chọn GreenShop Loki, Last30m và environment main. Ba selector cơ bản: `{environment="main",service="nginx"}`, `{environment="main",service="greenshop-web"}`, `{environment="main",service="mysql"}`. Chỉ báo query PASS khi có event thật trong khoảng chọn. Full sanitizer regression độc lập: `python3 -B tests/logging/diagnostic_pipeline_test.py`; không tạo QA stack và không ingest fixture vào Loki.

## Kiểm chứng ổn định Grafana

Restart policy unless-stopped; volume dtc245200016_btl_tkqt_htpm_grafana_data hiện có,không thay/xóa. Healthcheck GET /api/health giữ nguyên. Datasources dùng DNS prometheus/loki qua networks Main,không IP cố định. Root URL/cổng3000 giữ nhất quán, chỉ bind127.0.0.1.

Giảm từ35 xuống19 panel, bỏ alert-list gây fan-out sang cả3 rule providers; stat GS-SEC-001 dùng metric sẵn có. Refresh30s, quota Grafana1CPU/512MiB sau khi đo saturation/throttling ở0.5CPU. Đã restart/recreate có kiểm soát, login credentials cũ và dữ liệu live đều PASS; không thêm script tự sửa lỗi. Docker enabled/active, containerd enabled; không reboot VM. Frontend Firefox được kiểm bằng nội dung/canvas từng panel sau query,không chỉ khung dashboard. Windows và ẩn danh đã xác nhận hoạt động; cache/cookies cũ chỉ là giả thuyết của lỗi trước,không kết luận chắc chắn.
