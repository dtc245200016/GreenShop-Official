# GreenShop BASIC — minh chứng đợt tinh gọn

Tài liệu và `acceptance.json` bên cạnh là snapshot trước đợt nghiệm thu cuối, không phải trạng thái Git/database trực tiếp. Hướng dẫn hiện hành: [quản trị và truy vấn](../../skill.md).

Một Main project dtc245200016_btl_tkqt_htpm, một docker-compose.yml; chạy docker compose up -d --build. [README](../../../README.md), [demo](../../demo.md), [kết quả máy đọc](acceptance.json).

| Hạng mục | Kết quả |
|---|---|
| Compose253 dòng/Promtail90 dòng | Cấu hình parse giữ nguyên; chỉ nâng Grafana CPU theo số đo |
|4 dashboard/19 panel/1 GS-SEC-001 | Đã provision và kiểm dữ liệu/Firefox |
| Grafana restart/recreate | Cùng named volume,cùng user/login,2DS/4dash/1rule và live metrics |
| Docker startup | Docker enabled+active,containerd enabled;không reboot |
| Credentials/backend/business data | Đối chiếu hash chính xác trong acceptance.json;không reset/rotate/create accounts |
| Monitoring/logging/hardening | Xem kết quả runtime và LogQL trong acceptance.json |

65 file tests/legacy đã xóa sau kiểm dependency. Giữ3 script thiết lập tùy chọn,receiver độc lập và các ảnh minh chứng. Không tạo QA,backup mới,script tự phục hồi hoặc exporter mới.

Grafana trước có quota0.5CPU bị saturation/throttling và request15–27s. Chuyển1CPU/RAM512MiB,refresh30s,thay alert-list fan-out bằng stat GS-SEC-001 có sẵn. Root URL,port,healthcheck,datasource DNS và volume giữ nguyên. Local Firefox kiểm actual panel data sau query;operator xác nhận Windows/ẩn danh hoạt động. Không khẳng định cache/cookies là nguyên nhân chắc chắn.

Giới hạn: self-signed TLS,cAdvisor host/socket,root masters và app schema DDL;syslog UDP không zero-loss. Không claim full browser website CRUD mới,live Gemini,CVE scan hoặc VM reboot. Chỉ có2 Git commits hiện hữu;Commit3 vẫn cần operator review/stage/commit theo yêu cầu không tự commit/push.
