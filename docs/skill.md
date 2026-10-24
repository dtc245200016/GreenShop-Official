# GreenShop — Hướng dẫn quản trị và truy vấn

Áp dụng cho VM hiện tại, kiểm tra ngày **24/10/2026**. Chạy lệnh tại `/home/trung/GreenShop-Official`; project Compose là `dtc245200016_btl_tkqt_htpm`. Các query dưới đây chạy **từng câu riêng**.

## A. Hệ thống và truy cập

| Service | Nhiệm vụ / địa chỉ |
|---|---|
| `nginx`, `web_app` | HTTPS reverse proxy và ASP.NET Core; `https://192.168.197.128` |
| `db`, `phpmyadmin` | MySQL; phpMyAdmin `http://127.0.0.1:8080`, DB loopback `127.0.0.1:3306` |
| `prometheus` | Thu thập 5 targets; `http://127.0.0.1:9090` |
| `grafana` | 4 dashboard, 2 datasource, rule GS-SEC-001; `http://127.0.0.1:3000` |
| `mysql-exporter`, `nginx-exporter`, `cadvisor` | Metrics DB, Nginx và container; không publish cổng host |
| `promtail`, `loki` | Nhận syslog, lọc dữ liệu nhạy cảm và lưu log; truy vấn qua Grafana |
| `alert-receiver` | Nhận webhook nội bộ; không gửi email/dịch vụ bên ngoài |

Trên Ubuntu, mở trực tiếp các URL trên. Trên Windows, dùng VS Code Remote SSH → **Ports** → forward `3000`, `9090`, `8080`, rồi mở **Forwarded Address** thực tế. Website dùng IP VM và chứng chỉ lab. Giữ cổng quản trị ở loopback; Root URL Grafana hiện là `http://localhost:3000/`.

Dùng tài khoản hiện hữu; đọc thông tin đăng nhập riêng trong thư mục `secrets/`, không đưa giá trị vào lệnh được chia sẻ, ảnh hoặc Git. 7 volumes dữ liệu và 6 networks là tài nguyên Main có sẵn; `external` ngăn Compose tạo storage thay thế. Images đã được chuẩn bị trên VM, cấu hình không tự khởi tạo một máy mới trống.

## B. Docker Compose

```bash
cd /home/trung/GreenShop-Official
docker compose ps
docker compose config --quiet
docker compose logs --tail 50
docker compose logs --since 10m grafana
docker compose logs --since 10m prometheus
docker compose logs --since 10m promtail loki
docker compose logs --since 10m nginx web_app
docker compose logs --since 10m alert-receiver
docker stats --no-stream
```

`ps` xem trạng thái; `config --quiet` kiểm tra cấu hình (thành công không in nội dung); `logs` đọc sự kiện, không sửa hệ thống. `stats` xem CPU/RAM; lệnh này liệt kê cả container dự án khác nếu có. Bình thường 12 service chạy, 10 có healthcheck đạt `healthy`; 2 exporters được xác minh thêm bằng metrics, không chỉ trạng thái `running`. Log ít/không có dòng mới không tự chứng minh dịch vụ lỗi. Không chia sẻ raw logs chưa kiểm tra thông tin nhạy cảm.

| Lệnh thay đổi trạng thái | Khi dùng và lưu ý |
|---|---|
| `docker compose up -d` | Tạo/khởi động và áp dụng cấu hình; có thể recreate service thay đổi. Chỉ chạy từ Official sau khi kiểm tra mounts/volumes và ảnh hưởng. |
| `docker compose up -d --build` | Build rồi áp dụng khi source/image cần cập nhật; không dùng để chẩn đoán mỗi lần mở máy. |
| `docker compose restart grafana` | Restart đúng service khi có lý do; gây gián đoạn ngắn, không áp dụng thay đổi environment/Compose. Kiểm tra lại sau restart. |

Không chạy `down -v`, xóa volumes hoặc prune để sửa lỗi. Không restart toàn stack khi một service có vấn đề. Volumes giữ DB, ảnh, keys và dữ liệu giám sát; lịch sử tạm trong RAM của receiver không bền qua restart.

## C. Website, HTTP và tốc độ

```bash
curl -sS -o /dev/null -w 'HTTP=%{http_code} total=%{time_total}s\n' http://192.168.197.128/
curl --cacert nginx/ssl/cert.pem -sS -o /dev/null -w 'HTTP=%{http_code} total=%{time_total}s\n' https://192.168.197.128/health/ready
curl --cacert nginx/ssl/cert.pem -sS -D - -o /dev/null https://192.168.197.128/health/ready
curl -sS http://127.0.0.1:3000/api/health
curl -sS -o /dev/null -w 'HTTP=%{http_code} total=%{time_total}s\n' http://127.0.0.1:9090/-/ready
```

HTTP website bình thường trả **301** sang HTTPS; `/health/ready` trả **200**, kiểm tra được kết nối DB. Grafana health trả `database: ok`. Headers HTTPS có `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`. Chứng chỉ lab tự ký cần CA file trên; không dùng `-k` để kết luận TLS đã được xác minh.

| HTTP | Cách hiểu trong GreenShop |
|---|---|
| 200 / 301 / 302 / 304 | Thành công / HTTP chuyển HTTPS / điều hướng đăng nhập hoặc sau submit / tài nguyên cache chưa đổi |
| 400 / 401 / 403 / 404 | Request hoặc CSRF sai / cần xác thực / sai quyền hoặc Origin / không có tài nguyên |
| 429 | Rate limit; xem `Retry-After`, không spam thử lại |
| 500 / 502 / 503 | Lỗi backend / Nginx chưa kết nối upstream / chưa sẵn sàng hoặc dependency tạm gián đoạn |

Public `/metrics` và `/nginx_status` cố ý trả 404 theo hardening. Kiểm thử chức năng ghi đơn/sản phẩm hoặc gọi chatbot có thể phát sinh phí chỉ khi được phép; không dùng dữ liệu kinh doanh thật để thử phá lỗi.

## D. Prometheus — PromQL

Mở Prometheus hoặc Grafana Explore → **GreenShop Prometheus**. Mỗi dòng dưới là một query:

```promql
up
up{job="greenshop"}
mysql_up
nginx_up
greenshop_auth_login_failures_last_60s
sum(greenshop_auth_login_failures_last_60s) >= bool 5
```

`up` bình thường có 5 series bằng 1; `mysql_up`/`nginx_up` bằng 1 mới chứng minh exporter kết nối backend. Gauge đăng nhập là số lần thực sự bị từ chối trong 60 giây, reset khi Web restart. Biểu thức cuối trả A=0 khi dưới 5 lần, A=1 khi từ 5 lần; không phải counter tổng.

CPU theo service, đơn vị **% của một CPU core**; RAM là **MiB**. Labels được cAdvisor cung cấp từ Compose:

```promql
100 * sum by(container_label_com_docker_compose_service)(rate(container_cpu_usage_seconds_total{container_label_com_docker_compose_project="dtc245200016_btl_tkqt_htpm",image!=""}[5m]))
max by(container_label_com_docker_compose_service)(container_memory_working_set_bytes{container_label_com_docker_compose_project="dtc245200016_btl_tkqt_htpm",image!=""}) / 1024 / 1024
mysql_global_status_threads_connected
rate(mysql_global_status_questions[5m])
rate(nginx_http_requests_total[5m])
```

HTTP requests/giây, tỷ lệ 5xx (nhân 100 thành %), p95 latency (giây), và tuổi mẫu scrape (giây):

```promql
sum(rate(greenshop_http_requests_total[5m]))
sum(rate(greenshop_http_requests_total{status_code=~"5.."}[5m])) / clamp_min(sum(rate(greenshop_http_requests_total[5m])), 0.001)
histogram_quantile(0.95, sum by(le)(rate(greenshop_http_request_duration_seconds_bucket[5m])))
time() - timestamp(up{job="greenshop"})
```

Web dùng labels `route_group`, `method`, `status_code`; histogram nhóm theo `route_group`. Không dùng `status` của Nginx log thay `status_code` của metrics Web. Kết quả rỗng/NaN cần xem targets và khoảng thời gian; không tự đổi thành 0 để che mất dữ liệu.

## E. Loki — LogQL

Grafana Explore → **GreenShop Loki**. Chọn **Last 24 hours** để xem các sự kiện đã có, hoặc **Last 15 minutes** và Refresh sau thao tác mới. Dùng UTC khi đối chiếu JSON với lịch sử; timezone của giao diện chỉ đổi cách hiển thị.

```logql
{job="greenshop"}
{job="greenshop",service="nginx"}
{job="greenshop",service="greenshop-web"}
{job="greenshop",service="mysql"}
{job="greenshop",service="nginx"} |= "404"
{job="greenshop",service="nginx"} | json | status="404" | __error__=""
{job="greenshop",service="nginx"} | json | status="500" | __error__=""
{job="greenshop",service="nginx"} | json | status >= 500 | __error__=""
{job="greenshop",service="greenshop-web"} | json | event="auth.login.failed" | __error__=""
{job="greenshop",environment="main",service=~"nginx|greenshop-web"}
sum by(service)(count_over_time({job="greenshop",service="nginx"} | json | status >= 500 | __error__="" [5m]))
```

| Nhãn / trường | Ý nghĩa thực tế |
|---|---|
| `job="greenshop"` | Stream từ pipeline syslog Main hiện tại |
| `environment="main"` | Môi trường Main |
| `service` | Stream label `nginx`, `greenshop-web` hoặc `mysql` |
| `status`, `method`, `route_group` | Trường JSON Nginx sau `| json`: mã HTTP, GET/POST…, nhóm route như `catalog`, `authentication`, `orders` |
| `event`, `diagnostic_code` | Trường JSON Web: sự kiện đăng nhập/nghiệp vụ hoặc mã chẩn đoán; không phải mặc định stream labels |

`|= "404"` tìm chuỗi ở bất kỳ trường nào; lọc `status="404"` chính xác hơn. `| json` parse nội dung và `__error__=""` loại lỗi parse/chuyển kiểu. `[5m]` là cửa sổ thống kê, khác với khoảng thời gian hiển thị ở góc phải. Không có sự kiện 500/5xx thì query có thể rỗng hoặc không có điểm thống kê; đó không tự chứng minh pipeline hỏng. Đừng tạo lỗi giả để có dữ liệu.

Pipeline: Docker syslog UDP `127.0.0.1:1514` → Promtail → `loki:3100` → Grafana. MySQL chỉ có log vận hành, không bật general query log. Nguồn ít hoạt động có thể không có log mới; UDP có thể mất log khi collector dừng, cache Docker vẫn có rotation. Recreate Web không cần sửa container IDs/targets trong Promtail.

## F. Grafana Alerting và GS-SEC-001

Mở **Alerting → Alert rules → GreenShopSuspiciousLoginFailures** (UID `gs-sec-001`). Xem **Instances** để biết trạng thái hiện tại; **History** để đối chiếu thời gian, A và C. Grafana hiện đánh giá mỗi 10 giây, điều kiện **C: A is above 0**, không có pending delay.

| Trạng thái / giá trị | Ý nghĩa |
|---|---|
| Normal; A=0, C=0 | Dưới ngưỡng 5 lần đăng nhập sai trong 60 giây |
| Firing/Alerting; A=1, C=1 | Đã đạt ngưỡng; nghi ngờ đoán mật khẩu, không phải kết luận bị xâm nhập |
| Resolved | Thông báo kết thúc trạng thái firing; rule trở lại Normal khi cửa sổ 60 giây hết sự kiện |
| Alerting (NoData); A=-1, C=-1 trong lịch sử cũ | Lúc đó thiếu dữ liệu và rule được cấu hình chuyển Alerting; **không phải -1 hay 5 lần đăng nhập sai** |

Cấu hình hiện tại dùng `noDataState: NoData`, `execErrState: Error`: Grafana phân biệt `DatasourceNoData`/`DatasourceError` với cảnh báo đăng nhập. Vẫn báo gián đoạn monitoring, không gán dữ liệu thiếu thành 0 hoặc im lặng coi là Normal. Không cần tắt Prometheus để thử trường hợp này trên Main. [Giải thích chính thức của Grafana](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/nodata-and-error-states/).

**Contact points** và **Notification policies** trỏ `GreenShop Security Alerts` tới webhook nội bộ `http://alert-receiver:8080/alerts`, có gửi resolved. UID contact point giữ tên lịch sử, không có QA stack đang chạy. Kiểm tra:

```bash
docker compose logs --since 10m alert-receiver
docker compose logs --since 2h alert-receiver
```

Tìm `status: firing` rồi `resolved`, `received_at` UTC và incident GS-SEC-001. Đã đối chiếu notification thật ngày 24/10: firing lúc 14:22:40, resolved lúc 14:23:00 (UTC+7). Không có dòng trong 10 phút gần nhất không đồng nghĩa webhook hỏng. Receiver lưu 100 notification gần nhất trong RAM; đây là sink demo nội bộ, không phải dịch vụ email.

`ConnectionResetError` đã được xác định ở `do_GET` khi healthcheck đóng socket trước khi đọc hết body; không phải POST webhook thất bại. Nếu lỗi xuất hiện ở `do_POST` hoặc thiếu notification tương ứng, phải điều tra lại; không bỏ qua mọi lỗi reset.

## G. Thời gian VMware và lỗi Loading chập chờn

Kiểm tra chỉ đọc:

```bash
date
timedatectl status
chronyc tracking
chronyc sources -v
systemctl status chrony --no-pager
systemctl is-enabled chrony docker
```

Bình thường: synchronized=yes, NTP active, Leap status=Normal, nguồn NTP có dấu `*`, Reach ổn định tới `377`. UTC+7 là múi giờ Việt Nam, không phải lỗi lệch 7 giờ; container chia sẻ đồng hồ kernel với Ubuntu. Có thể đối chiếu `date -u` và `docker compose exec -T web_app date -u`.

Cấu hình Chrony đã xác minh: `/etc/chrony/chrony.conf` dùng **`makestep 1 -1`**, cho phép sửa bước lớn hơn 1 giây ở các cập nhật sau resume, thay vì chỉ lần đầu. Chrony/Docker enabled và active; không phát hiện systemd-timesyncd hoạt động, VM chưa cài open-vm-tools. Chưa kiểm chứng thiết lập đồng bộ phía VMware host và một chu kỳ Windows Sleep/VMware Suspend/resume thực tế.

Khi Prometheus báo **Server time is out of sync**, so giờ Ubuntu/NTP với Windows trước; xem `time()` trong Prometheus và `Date.now()` trong Console Windows (milliseconds). Khi Loki/Grafana lệch khoảng thời gian, kiểm tra lại đồng hồ rồi chọn Last 15m/Refresh. Chỉnh timezone không sửa được đồng hồ sai thật.

Lệnh can thiệp **chỉ dành cho quản trị viên sau khi xác nhận sai giờ**:

```bash
sudo chronyc makestep
```

Lệnh này nhảy đồng hồ ngay, có thể làm gián đoạn timeline/cảnh báo; không chạy để chữa mọi lỗi Loading. Dạng `sudo chronyc makestep 1 -1` chỉ đặt chính sách tự step cho daemon đang chạy; cấu hình file giữ chính sách qua reboot. Không tự sửa giờ Windows, cài NTP thứ hai, reboot VM hoặc tạo cron restart.

Nếu lỗi Loading tái diễn trên Windows:

1. F12 → Network, bật **Preserve log**, reload một lần. Ghi Forwarded Address, request Pending/Failed, Status, Duration/Timing và giờ xảy ra; không chia sẻ cookies, Authorization hoặc HAR chưa lọc secrets.
2. Trong Ubuntu chạy kiểm tra HTTP ở mục C, `docker stats --no-stream`, logs Grafana/Prometheus/Loki ở mục B và Chrony ở trên. API local nhanh nhưng Windows chậm hướng tới browser/SSH forwarding; API local cũng chậm cần điều tra server/DB/tài nguyên.
3. Sau Sleep/resume, chờ NTP synchronized rồi kiểm tra 5 targets, `/api/health`, Dashboards và Explore. Nếu phiên SSH bị ngắt, reconnect VS Code và kiểm tra lại Ports. Ghi kết quả trước/sau để phân biệt các nguyên nhân.

Đã đo trên Firefox Ubuntu: lần mở đầu khoảng 10 giây; API Dashboards khi đã warm khoảng 5–230 ms, 4 dashboard hiển thị đủ 19 panel và Explore có log thật. Gzip đã bật sẵn; không tìm thấy lỗi asset hoặc CPU bị nghẽn kéo dài trong lần đo. Điều đó **không chứng minh đã sửa triệt để lỗi chập chờn Windows**. Việc chỉ tắt màn hình, Sleep và Suspend là các trường hợp khác nhau, cần người dùng tái hiện riêng.

## H. Git/GitHub

```bash
git status
git log --oneline -5
git diff
git diff --cached
git remote -v
```

`status` phân biệt thay đổi working tree và staged; chưa commit không có nghĩa là editor chưa lưu. `log` kiểm tra lịch sử thật; `diff` xem thay đổi chưa stage, `diff --cached` xem nội dung sẽ commit. `origin` phải là `https://github.com/dtc245200016/GreenShop-Official.git`. Đọc diff riêng trước khi chia sẻ vì có thể chứa dữ liệu nhạy cảm.

Chỉ stage file đã review, chạy `git diff --cached --check`, bảo đảm `.env`, `secrets/`, TLS keys, dữ liệu và backups không được track. Commit local chỉ khi kiểm tra quan trọng đạt; push là thao tác riêng cần chỉ đạo của người dùng. Không reset/force push hoặc tạo commit rỗng để đủ số thứ tự.
