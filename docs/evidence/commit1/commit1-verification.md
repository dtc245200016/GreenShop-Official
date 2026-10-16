# GreenShop — Main deployment, botanical chat và phản hồi đánh giá

## Hoàn thiện đánh giá theo đơn, quyền chủ shop và tương tác chat — 16/10/2026

Đã triển khai lên **https://192.168.197.128** bằng đúng image QA được kiểm thử trong phiên tiếp tục. Không làm lại các chức năng đã hoàn thành ở các đợt bên dưới.

- **Đánh giá:** mỗi sản phẩm trong từng đơn đã giao thành công có một lượt riêng. Mua lại ở đơn khác tạo đánh giá độc lập; gửi lại cùng đơn không tạo trùng, chỉnh sửa có kiểm tra version. Server kiểm tra người mua, trạng thái giao hàng và Order ID của dòng hàng; không tin OrderId/UserId/ProductId gửi từ form. Điểm trung bình tính từ các đánh giá hiện hành không bị ẩn; ảnh và phản hồi đã lưu được giữ nguyên.
- **Chat Admin:** vùng lịch sử có chiều cao giới hạn, tin nhắn không bị co lại, cuộn chuột ngay trên nội dung; cuộn tiếp trang khi chạm biên. Tin nhắn mới không kéo xuống cuối khi Admin đang đọc lịch sử. Bố cục tiêu đề, bong bóng, ô nhập và trạng thái dùng font/màu của Admin hiện có.
- **Kéo chat:** nút nổi và cửa sổ kéo riêng, nhớ vị trí trên trình duyệt, giới hạn theo màn hình/bàn phím ảo; thao tác kéo không kích hoạt nhầm mở chat. Header/biểu tượng lá là tay kéo, không chặn cuộn nội dung hoặc nút thu gọn. Có phím mũi tên/Home, Alt + phím mũi tên trên launcher và focus/reduced-motion.
- **Chủ shop:** chỉ Admin có email `trungdtt123@gmail.com` được đổi vai trò người dùng. Admin thường không thể đổi quyền bất kỳ ai, sửa/khóa chủ shop hoặc Admin khác; vẫn có thể hỗ trợ hồ sơ/trạng thái khách hàng theo quyền hiện có. Kiểm tra actor bằng dữ liệu DB đã khóa trong transaction, không dựa vào trường giả mạo hoặc chỉ ẩn nút. Chủ shop không thể tự khóa/hạ quyền; email dành riêng không đăng ký công khai. Main đã có tài khoản chủ shop active/Admin, không chỉnh tài khoản thật.

**Kiểm thử mới:** Release build **PASS, 0 warning/0 error**; Razor publish và EF pending-model check **PASS**. **20/20 suites PASS:** account-switch, admin, ai-widget, business, contracts, customer, dashboard, engagement, floating, hybrid, inputs, order-owner-chat, payment, responsive, review-replies, security, support-reviews, user-browser, user-security, users. Có mua hai đơn thật trên QA, retry/concurrent edit, giả mạo quyền/ID, thu hồi cookie khi đổi vai trò, tranh khóa/hạ quyền, gửi nhận Shop/SignalR, lỗi mạng/bản nháp, ảnh/reply/rating, cuộn chuột thực, kéo/lưu vị trí/keyboard viewport, COD/VietQR/giỏ hàng/trừ-hoàn kho/Excel/Dashboard và 6 widths (320/375/390/768/1024/1440), Customer light/dark. QA dùng DB, secrets, ports, volumes và network riêng. Tệp QA tạm của phiên cũ mất sau khởi động lại nên đã dựng QA mới; không suy PASS từ bản ghi đã mất. Suite contracts cần fixture từ engagement; lỗi thiếu fixture ban đầu đã được xử lý bằng thứ tự chạy phù hợp, không thay đổi nghiệp vụ để test qua.

**Migration:** `20261015024032_ReviewPerCompletedOrder` thay chỉ mục Customer/Product từ unique thành nonunique, không xóa cột hoặc hàng. Kiểm thử 9→10 giữ mọi dữ liệu/ảnh/reply; chèn đánh giá cho đơn thứ hai thành công. Down cố tạo ràng buộc unique trước, chủ động thất bại khi có đánh giá độc lập, giữ nguyên dữ liệu/chỉ mục/history; không gộp/xóa đánh giá để hạ cấp. Bộ kiểm thử migration đã cập nhật theo bản thay đổi này.

**Triển khai và bảo toàn:** backup riêng DB, uploads, Data Protection keys, TLS, .env, Nginx và runtime image; thêm SQL quiescent sau khi dừng/drain writer. Phục hồi SQL thật vào schema QA mới, chạy image mới nâng cấp 9→10 và đối chiếu mọi cột/dòng cũ **PASS**; chạy image trước trên schema 10 để thử rollback code **PASS**. Main chạy đúng image QA, **10 migrations, áp dụng thêm 1**; mọi hàng/cột cũ (trừ bản ghi migration bổ sung), env, mounts, ảnh/keys/TLS giữ nguyên. DB/Nginx/phpMyAdmin không recreate; Nginx chỉ reload và được khôi phục nguyên cấu hình.

**Main sau cập nhật:** HTTPS xác minh bằng CA/certificate hiện có, config quiet/Nginx/app health và bốn services healthy **PASS**. Chromium chỉ đọc: route chính, role/login gates, widget/entry/legacy redirect, tay kéo, 6 widths/two themes, toàn bộ JS source đúng cú pháp, không JS error hoặc thiếu CSS/JS/font **PASS**. [floating-chat-main.png](floating-chat-main.png) được chụp lại trên Main thật. Các thao tác ghi của khách/Admin được kiểm thử trên QA cùng image; không đăng nhập thử bằng mật khẩu thật, tạo đơn/đánh giá/tin nhắn giả trên Main.

**Giới hạn:** không gọi thêm Gemini generation; AI status trên Main báo available, cấu hình/key/model/free-tier/budgets giữ nguyên. Mock HTTP dùng cho kiểm thử AI UI; không trình bày thành kiểm thử generation thật. Không Git commit/push/reset/clean, không xóa database/volumes, không sửa dữ liệu hoặc quyền tài khoản thật. Backup nằm trong `backups/` bị ignore, quyền riêng tư.

**Báo cáo hiện hành: 16/10/2026 (Asia/Ho_Chi_Minh).** Main đã triển khai theo phê duyệt trong prompt DEPLOY TO MAIN. Source backend, image đã kiểm thử trên QA và image Main khớp nhau; Main có đủ 9 migrations. Không commit/push/reset/clean hoặc tạo repository. Timestamps trong migration, backup và log giữ nguyên theo đồng hồ môi trường thực thi.

## Cập nhật chat trực tiếp, ảnh chatbot và đánh giá theo sản phẩm — 16/10/2026

Đã triển khai trên **https://192.168.197.128** bằng đúng image được kiểm thử trên QA. Không commit/push/reset/clean; không thêm migration hay thư viện.

- **Lỗi Admin phản hồi:** tái hiện HTTP 409 khi Admin gửi vào cuộc đang chờ mà chưa bấm tiếp nhận, trong khi composer vẫn cho gửi. Lần phản hồi đầu nay tự tiếp nhận trong transaction có khóa dòng; hai Admin gửi đồng thời chỉ một người nhận, request lặp không tạo tin trùng. Cuộc đang do Admin khác phụ trách hoặc đã kết thúc có trạng thái rõ và nút gửi phù hợp; người phụ trách có thể **Mở lại để phản hồi** với kiểm tra CSRF/role/version. Nội dung và thông báo lỗi được giữ lại khi gửi thất bại.
- **Ảnh chatbot:** `AiCatalogItem.ImageUrl` lấy từ Products qua cùng bộ chuẩn hóa ảnh của storefront. Controller đọc lại dữ liệu sau khi chờ provider; trình duyệt hiển thị ảnh, chỉ dùng URL hợp lệ và chuyển sang ảnh thay thế nếu tải lỗi. Không lấy đường dẫn ảnh do model tự bịa, không đổi luồng mua hàng.
- **Đánh giá theo sản phẩm:** mặc định là danh sách sản phẩm có ảnh, số đánh giá, điểm hiện hành và huy hiệu đỏ tròn báo số đánh giá chưa đọc của Admin đang đăng nhập. Bấm sản phẩm mở riêng các đánh giá và giữ chức năng phản hồi/ẩn/hiện/đánh dấu đã đọc. Lọc theo tên, danh mục, chưa đọc/đã có đánh giá, số sao, trạng thái; tìm trong nội dung/người mua ở trang chi tiết; phân trang giữ bộ lọc. ReviewId từ thông báo cũ và đánh giá của sản phẩm đã xóa vẫn truy cập được.
- **Đếm mới chính xác:** nhiều thông báo do khách sửa cùng một đánh giá chỉ tính một đánh giá chưa đọc. Đọc của Admin này không làm mất thông báo của Admin khác. GET xem danh sách không tự ghi trạng thái đã đọc.

**Kết quả lần cập nhật này:** Release build 0 warning/error, Razor publish, EF pending-model check và Docker source-only build **PASS**. **16/16 suites PASS:** support-reviews, review-replies, ai-widget, hybrid, engagement, contracts, inputs, security, customer, admin, payment, dashboard, responsive, account-switch, floating, business. Có gửi thật giữa hai browser QA, tranh nhận chat, đóng/mở lại, retry, CSRF/role/CAS/IDOR; mua hàng/giỏ hàng/trừ-hoàn kho/COD/VietQR/dashboard; 320/375/390/768/1024/1440px, Customer light/dark và Admin hiện có. Provider mock + MySQL QA xác minh dữ liệu ảnh/giá hiện tại và các giới hạn AI PASS. Cú pháp toàn bộ JavaScript PASS.

Các test cũ kỳ vọng phải tiếp nhận riêng đã được cập nhật theo luồng mới. Khi chạy liên tiếp/lặp lại, đã sửa fixture ảnh không tồn tại, ID fixture dùng chung giữa suites và nội dung chỉnh sửa lặp không đổi; giữ nguyên kiểm tra giỏ hàng, idempotency và tăng version khi thực sự có thay đổi. Không sửa nghiệp vụ cart/order để làm test qua.

**Main:** fresh backup DB/uploads/keys/TLS/.env/runtime image; phục hồi thử SQL trên schema QA riêng và đối chiếu mọi cột/dòng PASS. Main giữ **9 migrations, thêm 0**; mọi cột/dòng, `.env`, ảnh/keys/TLS và mounts không đổi; DB/Nginx/phpMyAdmin không recreate. Chromium trực tiếp Main PASS: đúng image, chat AI/Shop, product entry/legacy/role gate, sáu widths/two Customer themes, không JS error/missing assets và không ghi dữ liệu trong browser verification. HTTPS/config/Nginx/app healthcheck và bốn services healthy.

**Giới hạn xác minh:** Agent gọi thêm **0** Gemini generation; key/model/free-tier flags/budgets không đổi. Luồng Admin gửi/phản hồi, ảnh AI và quản lý đánh giá được kiểm tra tích hợp trên QA cùng source/image đã deploy; không tạo tin nhắn/đơn/đánh giá thử trên Main. Ảnh [review-products-admin-qa.png](review-products-admin-qa.png) dùng dữ liệu QA tổng hợp; [floating-chat-main.png](floating-chat-main.png) là Main thật, không phải một câu trả lời AI mới.

## Cập nhật giao diện chat theo mẫu — 16/10/2026

Bản UI tiếp theo đã triển khai lên **https://192.168.197.128** bằng đúng image đã kiểm thử trên QA. Header xanh botanical, hai tab dạng pill, bong bóng tin nhắn, gợi ý câu hỏi, thẻ sản phẩm và nút gửi tròn dùng lại font/theme của hệ thống. Thẻ sản phẩm mở trang chi tiết; không mô phỏng thêm giỏ hàng.

- **Sửa lỗi gửi:** cả AI và Chat với Shop xóa ô nhập ngay khi gửi, hiện tin nhắn tạm với trạng thái đang gửi; giữ nội dung đang viết tiếp khi phản hồi về. Khi thất bại, khôi phục nội dung nếu ô nhập trống; nếu đang có bản nháp mới thì giữ nội dung lỗi trong bong bóng được đánh dấu chưa gửi.
- **Đang trả lời:** AI hiện ba chấm chuyển động trong thời gian chờ HTTP thực tế, dọn trạng thái khi thành công/lỗi/hủy. Shop không giả lập Admin đang soạn tin; vẫn nhận tin qua SignalR và đối soát với lịch sử đã lưu, không hiển thị trùng tin nhắn thành công. Retry nội dung cũ giữ idempotency token; nội dung khác dùng token mới.
- **Tương tác:** hover/press, animation mở panel/gửi/nhận, Enter/Shift+Enter, focus, bàn phím màn hình và reduced-motion; bấm gợi ý chỉ điền câu hỏi, chưa gọi AI.
- **Phạm vi source mới:** chỉ `_HybridChat.cshtml`, `customer-engagement.css`, `customer-engagement.js`, `tests/customer_engagement.py`; cập nhật các evidence hiện có. Không thêm/xóa file source, không thay đổi controller/model/migration/luồng thanh toán hay cấu hình AI.
- **Build:** Release **PASS**, 0 warning, 0 error; Razor publish và EF pending-model check PASS. Build Docker từ source sạch file ignore PASS.
- **Regression trên image cuối:** **5/5 PASS** — ai-widget (gồm delayed-network composer), floating, hybrid, account-switch, responsive. Delayed responses xác minh clear ngay/ba chấm/khóa gửi/bản nháp mới/error retry/hủy khi reload. Shop gửi thật trên QA và nhận SignalR PASS; 6 widths 320/375/390/768/1024/1440, light/dark, viewport bàn phím 300px PASS.
- **Main sau triển khai:** Chromium read-only PASS, đúng image QA; launcher/AI/Shop/product entry/legacy redirect/role gate, 6 widths/two themes, không lỗi JavaScript hoặc asset thiếu. HTTPS và 4 services healthy; `docker compose config --quiet`, `nginx -t`, app healthcheck PASS.
- **Bảo toàn:** fresh backup DB/uploads/keys/TLS/.env/runtime image; phục hồi SQL và đối chiếu mọi cột/dòng trên schema QA riêng PASS. Main vẫn **9 migrations, áp dụng thêm 0**; mọi cột/dòng, mount, ảnh/keys/TLS và `.env` giữ nguyên. DB/Nginx/phpMyAdmin không recreate. Backup nằm trong thư mục `backups/` bị Git ignore, quyền riêng tư.
- **AI:** agent gọi thêm **0** Gemini generation; kiểm thử dùng mock. Effective key/model/free-tier flags và budgets giữ nguyên. Không gửi tin nhắn thử, tạo đơn hay đánh giá giả trên Main. Không Git commit/push/reset/clean.

Ảnh [floating-chat-main.png](floating-chat-main.png) là giao diện Main thật sau lần cập nhật này, có lời chào tĩnh, chưa tạo câu trả lời AI mới. Các kết quả 14-suite/review-reply/migration 7→9 bên dưới thuộc đợt triển khai trước; không trình bày thành kiểm thử mới của lần chỉnh UI này.

## A. Verdict

| Gate | Verdict | Bằng chứng / giới hạn |
|---|---|---|
| SOURCE_READY | YES | Restore, Release build 0 warning/error, Razor publish, JS syntax, EF snapshot/SQL PASS; backend byte-for-byte khớp candidate. |
| QA_READY | YES | 14 regression liên quan PASS, provider/grounding mock trên MySQL QA PASS; restore/upgrade/rollback rehearsal PASS. |
| MAIN_DEPLOYMENT | PASS | Recreate duy nhất web_app bằng image QA; Main 7→9; HTTPS và bốn service healthy. |
| FLOATING_CHAT_MAIN | PASS | Chromium trực tiếp Main: một panel, AI/Shop, product entry không navigation, legacy redirect và 6 widths/themes. |
| BOTANICAL_CHAT_ICON | PASS | Inline SVG chat bubble + cây mầm, hover/press/focus/reduced-motion; ảnh Main thật. |
| AI_CHAT | NOT VERIFIED — generation mới trên Main | Main provider available, đúng effective key/model/free-tier flags/budgets; mock PASS; không gọi thêm generation thật theo yêu cầu tiết kiệm quota. |
| SHOP_CHAT | PASS trên QA; đã deploy Main cùng image | Customer/Admin gửi nhận thật, persistence/reconnect/ownership PASS; Main kiểm tra panel/login gate, không tạo tin nhắn thử trên dữ liệu thật. |
| SIGNALR | PASS trên QA; Main đã deploy cùng backend/proxy | Real WebSocket, hai contexts, reconnect/catch-up/dedup/role/origin/group tests PASS. Không mô tả đây là một cuộc chat ghi dữ liệu mới trên Main. |
| REVIEW_REPLY_FEATURE | PASS trên QA; đã deploy Main | Tạo/sửa bằng HTTP và browser thật; CAS/role/CSRF/XSS/count/rating PASS; Main schema và runtime đã có tính năng. |
| REVIEW_REPLY_UI | PASS trên QA; UI đã deploy Main | 6 widths, Light/Dark, loading/success/error/focus, public reply block PASS. Main chưa có phản hồi chính thức để nghiệm thu nhánh có nội dung bằng tài khoản thật. |
| MAIN_DATA_PRESERVATION | PASS | Mọi original column/row, credentials/roles/orders/payments/stock, ảnh/keys/TLS giữ nguyên; cùng volumes, DB/PMA/Nginx container không recreate. |
| M1_READY | YES — core | Source/runtime/migration đồng bộ; core regression trên cùng image, Main read-only acceptance và evidence PASS. AI generation bổ sung không phải điều kiện M1. |
| PRODUCT_READY | PARTIAL | Còn nghiệm thu generation AI và thao tác phản hồi bằng tài khoản thật trên Main; không tạo dữ liệu/trao đổi giả chỉ để đánh dấu PASS. |

## B. Root cause

Source/QA đã có floating widget nhưng Main còn image cũ và 7 migrations, nên Customer vẫn gặp full-page chat của runtime cũ. Không có lý do viết thêm chatbot hoặc xóa view theo tên file. Main nay chạy candidate đã kiểm thử, cache-busted CSS/JS mới; các entry points Customer ở footer/product/order dùng chung widget. Launcher luôn mở AI; nút Chat với Shop mở thẳng Shop; route cũ redirect về Storefront với intent rồi bỏ intent khỏi URL.

ShopChat.cshtml vẫn phục vụ Admin Inbox. Full-page dành cho Admin được giữ; không còn entry point Customer thông thường trỏ vào view này.

## C. Files changed

Phạm vi **riêng yêu cầu này**, ngoài các thay đổi có sẵn đã được bảo toàn và đưa vào image:

- Models/CustomerEngagement.cs: bốn trường reply nullable và ReviewReplyInput allowlist.
- Data/AppDbContext.cs, Migrations/AppDbContextModelSnapshot.cs: FK Admin và model snapshot.
- Areas/Admin/Controllers/KhachHangController.cs: POST PhanHoiDanhGia, Admin-only/CSRF/validation/CAS.
- Areas/Admin/Views/KhachHang/DanhGia.cshtml: form lưu/cập nhật, preview và trạng thái.
- Views/Shared/_ProductReviews.cshtml: khối phản hồi chính thức, nội dung escaped và timestamp.
- Views/Shared/_HybridChat.cshtml: inline SVG cây mầm/chat.
- wwwroot/css/customer-engagement.css, wwwroot/js/customer-engagement.js: botanical states, reply AJAX/preview/draft/error và launcher mặc định AI.
- tests/customer_engagement.py, tests/m1_acceptance.py, tests/portal_sessions.py: regression reply/UI/security, rehearsal nhiều pending migrations và fixture thanh toán độc lập.
- README.md và evidence M1 hiện có: hướng dẫn và bằng chứng runtime mới.

**Thêm cần thiết:** 20261014232307_AddReviewReplies.cs, Designer tương ứng; ba ảnh evidence floating-chat-main.png, review-reply-admin-qa.png, review-reply-customer-qa.png. Không thêm service/adapter/theme/app frontend hoặc icon file riêng.

Main .env bị ignore chỉ bổ sung các cấu hình AI đã duyệt; key và DB credentials giữ nguyên. Nginx tạm maintenance/reload rồi khôi phục nguyên bytes cấu hình cũ. Các helper, SQL, logs và thông tin backup chỉ ở thư mục riêng ngoài source.

## D. File cleanup

| File / nhóm | Action | Reason |
|---|---|---|
| Views/Shared/ShopChat.cshtml | KEEP | ChatControllerBase và Admin Inbox dùng thật; hai-context chat regression PASS. |
| _HybridChat, customer-engagement CSS/JS | EXTEND | Tái sử dụng một implementation; không tạo chat-final-v2 hoặc theme trùng. |
| Inline SVG launcher | REUSE EXISTING PARTIAL | Không cần bitmap hay asset file mới. |
| Migrations/snapshot, tests, docs/evidence, scripts, fonts/FA/SignalR/licenses | KEEP | Runtime, regression, bootstrap, backup/HTTPS và nghiệm thu cần. |
| Hai Bootstrap maps đã bị xóa trước yêu cầu này | GIỮ NGUYÊN THAY ĐỔI CŨ | Không nhận là xóa mới hoặc reset thay đổi của người dùng. |
| File source bị xóa thêm | NONE | 0 file / 0 byte giảm do xóa; không đủ bằng chứng để xóa thêm an toàn. |
| QA phục hồi | STOP CONTAINERS/NETWORK | Đã hoàn tất; giữ volumes/backup; không dùng down -v. |

## E. Bugs fixed

| Severity | Root cause | Fix | Verification |
|---|---|---|---|
| P1 | Main còn runtime/schema cũ dù QA đã sửa floating | Backup/restore rehearsal, maintenance, deploy image đã QA, apply 2 pending migrations | Main exact IDs/image, HTTP/browser/same-data PASS |
| P1 | Thiếu nghiệp vụ phản hồi review | Một reply trên review, author/time, Admin-only update với shared version CAS; public block theo moderation | Real create/edit/race/CSRF/overposting/XSS/rating/hidden/archive tests PASS |
| P2 | Range attribute dùng double không loại chính xác long.MaxValue | Kiểm tra version âm/MaxValue trực tiếp trong action | Tái hiện 409 thay vì 400; boundary validation PASS sau sửa, không mutation |
| P2 | Test VietQR phụ thuộc Product 1 đã được test khác đổi từ 100k thành 110k | Fixture riêng 100k + policy 30k/300k, giữ expected total 130k | Chẩn đoán thực tế 110k + 30k = 140k đúng; fixture độc lập + payment flow PASS |
| P2 | Reconnect test làm offline trước khi socket sau reload kết nối xong; focus test dùng mouse modality | Chờ actual connected trước fault injection; dùng keyboard Tab thực | Reconnect/focus PASS, không nới lỏng assertion nghiệp vụ |
| Release verification | Docker đổi thứ tự list mounts, dù mọi mount giống nhau | So sánh toàn bộ mount theo Destination, kiểm lại data/keys/TLS rồi mới mở traffic | Exact volume name/source/destination/mode/RW và original hashes PASS; không chạy lại migration |

## F. Chat results

Launcher cây mầm kết hợp bubble, nền/shadow theo theme, hover nổi nhẹ + leaf tilt, press feedback, focus ring và reduced-motion. Một panel 400×600 giới hạn theo viewport/safe-area, history scroll riêng, Enter/Shift+Enter/Escape, role gates và độc lập AI/Shop history.

Main browser trực tiếp xác nhận: AI tab mặc định khi launcher mở; Shop entry đúng mode, không đổi URL/mất quantity; minimize/focus và legacy redirect; 320/375/390/768/1024/1440 ở Light/Dark, không JS error/missing asset. AI available status không phải bằng chứng generation thành công.

Ảnh thật: [launcher Main](storefront-main.png), [floating Main](floating-chat-main.png), [product Main](products-main.png). Ảnh có nội dung AI trả lời từ đợt trước là evidence lịch sử, không phải một generation mới của đợt này.

Gemini Native model gemini-3.5-flash-lite: [bảng giá Google hiện liệt kê Free Tier cho input/output](https://ai.google.dev/gemini-api/docs/pricing); [quota áp dụng theo project](https://ai.google.dev/gemini-api/docs/rate-limits). Effective key trong container Main khớp fingerprint key chủ project đã đối chiếu trên AI Studio. Không có Cloud credentials để đọc độc lập billing metadata; không suy tier từ HTTP success.

Ngân sách chạy Main: 5 RPM, 20 request/rolling 24h, 30.000 token/phút, 100.000 token/24h, input reserve cap 12.000, output 500, concurrency 2, timeout 20s. 429 cooldown, không retry/model/provider fallback; Shop không bị tắt khi AI quota hết. Verification có hạn; operator xem AI_CHAT_FREE_TIER_VERIFIED_UNTIL trong .env và xác minh lại trước khi gia hạn. Counters trong RAM/single instance, reset khi restart, không đo usage các app khác cùng project. **Agent gọi thêm generation thật: 0.**

## G. Review replies

Mỗi ProductReview có 0/1 ReplyContent (3–1500 ký tự), ReplyAdminId, ReplyCreatedAt, ReplyUpdatedAt. Lần cập nhật giữ ngày tạo, thay người sửa/thời điểm sửa; không thay Stars/Content của khách/count/average. Version CAS dùng chung với edit/moderation chống ghi đè.

Admin → Đánh giá khách hàng → Phản hồi đánh giá → Lưu/Cập nhật phản hồi. AJAX có disabled/loading, success/error live region, giữ draft khi lỗi; server vẫn bảo vệ khi bỏ JS. Bản lưu cũ không cho sửa; phản hồi của review đang ẩn không xuất hiện công khai, hiển thị lại cùng review sau unhide.

Public product hiển thị khối Phản hồi từ GreenShop ngay dưới review, không lộ email/credentials/Admin ID. Razor và textContent escape nội dung.

[Admin reply QA](review-reply-admin-qa.png), [Customer reply QA](review-reply-customer-qa.png): Chromium thật, dữ liệu synthetic. Main giữ 3 review cũ, hiện có 0 official replies. **Không kiểm thử ghi phản hồi lên review thật hoặc giả đăng nhập Admin để tạo evidence.** Chức năng đã deploy cùng exact image/schema đã QA; nghiệm thu thao tác thật cần Admin hiện có sử dụng trên Main.

## H. Database / deployment

- Source, QA và Main đều có 9 migrations, EF model/snapshot khớp.
- Đã apply: 20261014165031_CompleteCustomerEngagement và 20261014232307_AddReviewReplies.
- Migration 9 chỉ thêm bốn cột nullable, index và FK; không xóa review. Migration 8 giữ bản review cũ khi chuẩn hóa current review.
- Backup online trước thay đổi, restore old runtime/schema 7, upgrade clone 7→9, independent rollback restore PASS.
- Khi bảo trì: drain web writes/WebSockets, dump và archive mới, verify checksum/tar, restore fresh dump vào QA schema riêng và so mọi original column/row trước migration.
- Recreate chỉ web_app, giữ DB/PMA/Nginx container IDs/start times và named volumes. Nginx reload maintenance và restore, không thay TLS.
- Sau deploy so original columns/rows, mọi ảnh/keys cũ và TLS giữ nguyên. Không có synthetic Main order/payment/review/message/role write.

Backup thật nằm trong backups/main-release-* / backups/release-* bị ignore, mode riêng tư; old runtime image archive được verify. Không công khai dump, env, cookie hoặc key trong evidence. Private reports/manifest ở /tmp/greenshop-main-deploy-20261015; final read-only acceptance ở /tmp/greenshop-main-acceptance-20261016.

## I. Tests

| Nhóm | Result / scope |
|---|---|
| dotnet restore, Release build, Razor publish, JS parse, EF snapshot/upgrade SQL | PASS |
| 14 regression: review-replies, floating, hybrid, engagement, contracts, inputs, security, customer, admin, payment, dashboard, responsive, ai-widget, account-switch | PASS — synthetic QA |
| Provider/budget/history/error mocks và product-aware controller/retrieval trên MySQL QA 9 | PASS — mock transport, không generation thật |
| New reply create/edit, two-Admin CAS, validation/role/CSRF/overposting/XSS/hidden/archive/average/count | PASS — actual QA HTTP/browser |
| Backup verification + clone restore/upgrade 7→9 + independent rollback restore + fresh quiescent restore | PASS — QA tách biệt |
| Main deployment/image equality/original-data preservation | PASS |
| Main Chromium home/product/launcher/AI & Shop tabs/legacy route/6 widths/themes/assets | PASS — actual Main, read-only |
| Main Compose/MySQL/phpMyAdmin/Nginx/HTTPS SAN/CA/301/headers/health/auth challenges/exact migration IDs | PASS — actual Main |
| Gemini generation mới trên Main | NOT TESTED theo yêu cầu không gọi thêm khi chưa cần |
| Authenticated Admin create/edit reply và Customer/Admin chat ghi dữ liệu trên Main | NOT TESTED — positive flow đã PASS trên QA cùng image; giữ nguyên dữ liệu thật |
| Mobile keyboard vật lý / Windows tunnel / nhiều instance / load lớn | NOT TESTED; visualViewport/keyboard browser đã PASS, không đồng nhất với thiết bị vật lý |

## J. Remaining issues / release decision

- Không phát hiện P0 hoặc P1 code blocker sau regression và deployment; không có lỗi mất dữ liệu hoặc authorization bypass được biết trong phạm vi đã thử.
- Không còn chênh source/Main migration hoặc Main còn chạy giao diện cũ.
- Product acceptance còn partial cho AI generation và thao tác thật trên Main như ghi rõ ở A/I; không báo COMPLETE toàn bộ nghiệm thu tính năng khi chưa chạy chúng.
- P2 baseline: budget RAM/single instance, keyword retrieval/model prose cần tiếp tục giám sát; TLS self-signed/DB-scoped DDL/web root theo hạ tầng đồ án. Không thêm Redis/monitoring hoặc đổi kiến trúc ngoài phạm vi.
- Có thể review/chốt M1 core bằng quy trình Git của chủ dự án. **Không tự commit/push/create repository.**

Main để thử: https://192.168.197.128 — Admin reviews: /Admin/KhachHang/DanhGia. Nếu cửa sổ cũ còn giữ DOM/assets từ trước deployment, refresh trang để nhận HTML/cache-busted URLs hiện hành.


<details><summary>Lịch sử audit trước — giữ để đối chiếu, các verdict/config cũ không phải trạng thái hiện hành</summary>

# GreenShop — Gemini integration, comprehensive audit & release gate

Ngày báo cáo: **15/10/2026 — Asia/Ho_Chi_Minh**. Source hiện hành đã được build/kiểm thử; **Main chưa deploy, migrate, restart hoặc sửa dữ liệu/grants/volumes**. Không commit/push, đổi branch hay viết lại lịch sử Git. Phiên này kế thừa các thay đổi chưa commit của audit trước; không coi HEAD/remote là bản đã chứa patch.

## A. Overall verdict

| Gate | Verdict | Phạm vi / bằng chứng |
|---|---|---|
| SOURCE_READY | **YES** | Release build 0 warning/error, Razor publish, EF snapshot khớp, JS syntax, NuGet advisory audit, source sạch secrets. |
| QA_READY | **YES** | QA mới từ dữ liệu rỗng, 8 migration/15 bảng, 23 nhóm regression/fixture, browser, backup/restore, persistence. |
| GEMINI_READY | **YES — trên QA** | 4 lượt generation thật thành công qua endpoint ứng dụng; 2 từ chối cục bộ; mock fault matrix và grounding MySQL PASS. Main AI chưa bật. |
| HYBRID_CHAT_READY | **YES — trên QA** | Hai tab độc lập; real WebSockets, reconnect/offline/multi-tab/dedup, ownership, session revocation, assignment CAS và read/unread PASS. |
| M1_READY | **NO** | Main vẫn 7 migrations và runtime cũ; source/QA có 8. Gate exact IDs trả FAIL/nonzero đúng. |
| MAIN_DEPLOYMENT_READY | **YES — phần chuẩn bị** | Backup được xác minh, restore rehearsal/rollback PASS, image/SQL/override/maintenance được chuẩn bị; **còn yêu cầu phê duyệt theo §25**. |
| PRODUCT_READY | **PARTIAL** | Chưa nghiệm thu runtime mới trên Main sau deployment được cấp phép. Không tuyên bố toàn hệ thống đã release. |

Branch `main`, HEAD `e780615`, origin `https://github.com/dtc245200016/GreenShop.git` giữ nguyên; staging rỗng. QA hiện hành: project `greenshop-release-qa-341da3f2f2`, HTTPS `https://localhost:20543` trên VM, HTTP 20581, phpMyAdmin 20580, tất cả loopback. QA cũ và QA restore đã dừng container/network, **giữ nguyên volumes/backup**.

## B. Gemini integration

- Tái sử dụng `IAiChatProvider`, typed `HttpClient`, typed options và widget Razor hiện có. Một `ConfiguredAiChatProvider` chọn Gemini Native hoặc OpenAI Responses rõ ràng; không tạo chatbot/SDK thứ hai. Adapter cũ dùng Responses, không phải Chat Completions, nên không thay endpoint sang compatibility API một cách giả định.
- Endpoint Gemini: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, key trong header server `x-goog-api-key`, không đặt trong URL. Không redirect/retry/model fallback/billing changes. OpenAI tùy chọn giữ `store=false`; live OpenAI không được thử trong phiên này.
- Model **`gemini-3.5-flash-lite`** được key hiện tại liệt kê với `generateContent`, kiểm tra capability theo tài liệu chính thức và trả lời thật 4 lần. Dòng 2.5 có hạn chế access cho project mới theo tài liệu; 3.5 được chọn trước lần generation đầu, không phải fallback tự động.
- User xác nhận project thuộc **Free tier**. Không suy ra tier từ model listing và không tự thay billing. Generation thực tế **4**, dưới cap 6 đã trao đổi; không load test hay cố tình tạo lỗi bằng key thật. Provider duration 4.519–5.423 giây; metadata ghi 2934 input tokens, 274 output tokens. QA được tắt provider lại sau nghiệm thu để tránh dùng thêm quota.

| Live case | Vai trò | Kết quả |
|---|---|---|
| Chào hỏi tiếng Việt | Anonymous | HTTP 200, đáp án thật; thừa nhận thiếu mô tả thay vì bịa đặc tính. |
| Hỏi tiếp cây dưới 200.000đ | Anonymous, cùng lịch sử | HTTP 200, 6 sản phẩm thực, giá/tồn kho đối chiếu SQL tại thời điểm phục vụ, link nội bộ hợp lệ. |
| Cây ZZZ không tồn tại | Customer | HTTP 200, không gợi ý sản phẩm giả, thừa nhận chưa có dữ liệu. |
| Tư vấn cây để bàn | Admin ở Storefront | HTTP 200 qua browser/widget thật, 2 sản phẩm có thật, lời khuyên dựa trên mô tả. |
| Chính sách/khuyến mãi chưa có dữ liệu | Customer | HTTP 200 **từ chối cục bộ**, không gọi Gemini. |
| Credentials/đơn người khác/sửa giá/xác nhận tiền | Customer | HTTP 200 **từ chối cục bộ**, không có tool/private data/mutation. |

Toàn bộ bảng nghiệp vụ trước/sau AI không đổi; key không có trong HTTP response/logs. [Ảnh widget khi Gemini trả lời thật](gemini-chat-qa.png) chụp ở cuối vùng chat, thẻ sản phẩm đang hiển thị; không phải ảnh mock.

Cấu hình chỉ gồm tên biến, không có secret: `AI_CHAT_ENABLED`, `AI_CHAT_PROVIDER`, `AI_CHAT_MODEL`, `GEMINI_API_KEY`, `AI_CHAT_API_KEY` tùy provider, `AI_CHAT_TIMEOUT_SECONDS`, `AI_CHAT_REQUESTS_PER_MINUTE`, `AI_CHAT_MAX_OUTPUT_TOKENS`, `AI_CHAT_HISTORY_TURNS`. `.env.example` để model/key trống, disabled mặc định; `.env` thật bị ignore. Main release override đã chuẩn bị model đã kiểm thử, không chép key vào source.

Giới hạn: 1000 ký tự/câu hỏi, 2000 ký tự/đáp án, tối đa 4 cặp lịch sử/6000 ký tự; token lịch sử mã hóa/xác thực Data Protection, ràng buộc cookie HttpOnly + account/session, hết hạn 30 phút. Không lưu AI history vào MySQL/localStorage, không gửi cho Admin. Request 128 KiB, upstream response 64 KiB, output mặc định 500 tokens/cap 2000, timeout mặc định 20s/cap 60s, 6 request/IP/phút mặc định, concurrency 8 trên nhóm endpoint có limiter. Không tự retry khi lỗi/timeout/quota; retry UI là thao tác chủ động của người dùng.

Public retrieval SQL lọc danh mục active/còn hàng, ngân sách Việt và tên/mô tả/danh mục; tối đa 6 kết quả. Context có rating/review count và phí ship công khai. ID model ngoài context bị từ chối; backend đọc lại DB sau độ trễ model. Cards/link/phí ship do server tạo; output plain text. Prompt/catalog/history là untrusted; không có SQL/shell/filesystem/admin/payment tool. Đây là keyword retrieval, không phải semantic/vector search. Prompt + bộ lọc không chứng minh mọi câu văn tự nhiên đều đúng; dữ liệu thương mại chính thức nằm trên cards/checkout.

Mock PASS: missing/malformed config/header, model URI injection, 302/400/401/403/404/429/500/502/503, timeout/caller cancel/network, JSON sai cú pháp/sai kiểu/null, blocked/empty/incomplete/thought-only response, body quá lớn, unsafe prose/URL/HTML, ID giả, token limits, invalid roles/history, token tamper/cross-browser/cross-account/revoked session, long Vietnamese history. Mock không được tính thành live.

Tài liệu đối chiếu: [Native API](https://ai.google.dev/api/generate-content), [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai), [model discovery](https://ai.google.dev/api/models), [model 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [pricing](https://ai.google.dev/gemini-api/docs/pricing). Quota theo project/model/tier; không giả định subscription cá nhân cấp API quota.

## C. Bugs fixed

| Severity | Root cause | Files | Fix | Test evidence |
|---|---|---|---|---|
| P1 | Pomelo 8 không dịch `Any` trên primitive collection; AI catalog lookup có thể throw 500 khi bật provider. | `Services/StoreCatalog.cs` | Bounded OR expression chạy trong SQL, không load toàn catalog về memory. | Tái hiện `Primitive collections support has not been enabled`; MySQL AI integration PASS sau sửa. |
| P1 | Thiếu/sai `version` bind về 0 và action không kiểm tra ModelState, có thể nhận chat mới ngoài hợp đồng form. | Admin `KhachHangController.cs` | BindRequired/FromForm, kiểm tra version/id/ModelState; moderation cũng yêu cầu bool hợp lệ. | Tái hiện missing-version nhận chat; `inputs` PASS, không mutation với missing/malformed/negative inputs, valid CAS vẫn chạy. |
| P1 | Formatter Storefront/AI dùng 0 số lẻ dù giá DB cho phép 2 số lẻ: 10.50 hiển thị 11. | `Models/StorefrontViewModels.cs`, `customer-engagement.js` | Dùng lại formatter receipt hiện có; AI cards giữ tối đa 2 số lẻ. | Tái hiện HTTP DB 10.50 vs trang 11; `fractional` và AI-widget PASS: catalog/cart/preview/COD receipt 10,50; 3×10,50=31,50. |
| P2 | Upstream JSON shape/empty/refusal/errors chưa được chuẩn hóa đầy đủ; header secret sai định dạng có thể throw. | `Services/AiChatProvider.cs` | Parser kiểm tra kiểu, giới hạn body, category lỗi, validate cấu hình/header và log metadata. | HTTP mock fault matrix PASS; không retry/fallback/lộ key hoặc payload. |
| P2 | Hub lookup cho Customer luôn chọn own conversation, nên foreign-ID invocation có thể báo thành công khi khách đã có conversation riêng. Không có bằng chứng join group của người khác. | `Hubs/SupportHub.cs` | Yêu cầu `conversation.Id == id` trước AddToGroup. | Tái hiện bằng browser với own conversation đã tồn tại; hybrid regression kiểm tra lại foreign-ID rejection và own join. |
| P2 | Harness dùng order legacy đã bị tiêu thụ, bank state/fixture IDs va chạm; selector tên bị badge động; race swap client nhưng giữ CSRF token cũ. | `tests/order_management.py`, `payment_shipping.py`, `excel_exports.py`, `customer_engagement.py` | Fixture legacy mới theo lượt, chuẩn bị bank QA riêng, verified fixture reuse/auto IDs, selector ổn định và form gắn đúng identity. | Giữ assertions nghiệp vụ/quyền hạn; rerun 23 nhóm đạt, không xóa tests để né lỗi. |

Các thay đổi từ audit trước được giữ và kiểm thử lại: review 5 ảnh/edit/moderation + reconciliation, notifications per Admin, SignalR/assignment/reconnect, Production Razor compilation, exact migration IDs và QA context isolation. Bảy migration đã áp dụng Main **không sửa**.

## D. Cleanup

| File / nhóm | Decision | Lý do / reference verification |
|---|---|---|
| Bootstrap `bootstrap.min.css.map`, `bootstrap.bundle.min.js.map` | **DELETE** (đã có trong patch audit trước) | Không sourceMappingURL/reference trong Razor, JS, CSS, tests/deploy; min assets và licenses giữ nguyên; browser asset checks PASS. |
| Block `updateTotal` cũ trong `wwwroot/js/storefront.js` | **DELETE block**, giữ file | Chỉ nó tham chiếu `data-checkout-total`; không Razor/runtime tạo thuộc tính này. Checkout hiện dùng cents/BigInt của `payment-shipping.js`; quantity/decimal checkout regression PASS. |
| EF migrations/Designer/snapshot | **KEEP** | Runtime migration discovery, first-7 bytes unchanged, exact IDs/model/upgrade/restore test. |
| SignalR/minified libraries/fonts/licenses | **KEEP** | Layout/hub/browser dùng thật; license/OFL là nghĩa vụ phân phối. Không thay vendor bằng CDN. |
| Razor controllers/views/CSS/JS đang dùng | **KEEP** | MVC convention/dynamic routing/DI/layout/browser đã kiểm tra; không dựa riêng vào string references để xóa. |
| QA/test helpers, evidence chính thức | **KEEP** | Regression/prepare/isolation/release rehearsal có người gọi và giá trị nghiệm thu; không thêm mock production page. |
| Các mode tái hiện bug/cookie lịch sử | **REVIEW / giữ** | Cần image/cookie lưu trữ; không coi mode yêu cầu archived state là regression hiện hành, không xóa test có giá trị. |
| `.env`, uploads, DP/TLS keys, DB/backup/volumes | **KEEP ngoài Git** | Runtime/preservation/restore cần; không delete/reset/prune. |

Inventory cuối không có file trùng SHA, file source >5 MiB hoặc junk candidate trong Git-visible source. `bin/obj`, bytecode, secrets và backups được ignore. Không thêm React/Vite, layout/CSS/JS “final2”, SDK AI trùng chức năng hoặc report thứ hai.

## E. Features verified

- **Customer/auth:** đăng ký/login/logout, persistent cookies, safe ReturnUrl, portal separation, account lock/session revocation; catalog/category/search/filter/sort/paging/empty/inactive; cart ownership/merge/update/remove/concurrency; Buy Now/cart checkout, COD/VietQR, fee/threshold, order snapshots/idempotency, stock validation/deduction và own-only history/detail.
- **Admin:** actual-data dashboard/period/previous-window/chart và alerts; Product/Category CRUD/images/dependency guard; order status/CAS/cancel/inventory/paid guards, ghi chú/audit/print; users/profile/role/lock/self-protection/last-admin races/session revocation; bank/shipping validation/persistence; Excel exact rows/types/formula-safe text/Open XML/ClosedXML round-trip.
- **Reviews:** completed/verified purchase, 1–5 sao, max 5 ảnh với size/signature limits, owner edit/stale update, cross-purchase one-current-review, archive giữ dữ liệu cũ, moderation và real current-visible rating/count.
- **Notifications:** Order/Review/Message transaction events, recipient-specific unread/read-all/deep links, CSRF/IDOR, unique recipient/event, Pending order count là chỉ số riêng.
- **Hybrid:** default AI, anonymous login gate cho shop chat, Customer-only sending/Admin-only inbox, shared Waiting/InProgress/Resolved, atomic assignment, chỉ assigned Admin reply/resolve, customer reopen, persisted messages before broadcast, per-admin read cursor, ordering/idempotency/dedup/offline catch-up/multiple tabs, exact Origin/group ownership và revoked session checks.
- **AI:** Gemini thật theo bảng B; mock HTTP/UX và real MySQL grounding tách biệt, không private data/tools/business writes.

## F. Infrastructure / database / release preparation

Main và QA đều 4 services healthy tại lần xác minh cuối. Images được pin digest; runtime QA thực là **Microsoft.NETCore.App/Microsoft.AspNetCore.App 8.0.32**. Nginx syntax, HTTP→HTTPS, TLS 1.2/1.3/certificate-key match/security headers, WebSocket và schema-scoped app user/phpMyAdmin access đã kiểm tra. Không thay TLS/root password/grants/Main volumes.

Source/QA exact IDs:

```text
20261011064651_InitialCreate
20261011082144_AddCategoryManagement
20261011094337_AddCustomerShopping
20261011115904_AddAdminOrderWorkflow
20261011131858_AddUserAccountStatus
20261012055246_AddPaymentShippingSnapshots
20261014124847_AddCustomerEngagement
20261014165031_CompleteCustomerEngagement
```

Main có đúng 7 ID đầu / 13 bảng. QA có cả 8 / 15 bảng; EF pending-model changes: none. Migration 8 thêm review fields/current uniqueness, assignment/status/version, AdminNotifications, ShopConversationReads; raw update chỉ đánh dấu archive trên cột mới, không xóa review hay sửa cột gốc. Test duplicate reviews chọn mới nhất theo CreatedAt/Id, giữ mọi cột/dòng/ảnh cũ. SQL 7→8 đã sinh và review, không thực thi lên Main.

Backup riêng: `backups/release-20261015-020249-c68297/` bị ignore, thư mục 700/file 600: MySQL dump, uploads+DP archive, TLS archive, `.env`, runtime image và SHA-256 manifest. OCI digest/blobs, archive entries và bytes đã kiểm tra; TLS restore vào directory riêng khớp certificate/private key. Backup chứa dữ liệu/secret thật, không đưa vào evidence/Git.

Restore rehearsal trên project/DB/credentials/volumes/ports riêng đã boot **runtime Main cũ** từ backup 7 migrations + restored uploads/keys; runtime mới nâng copy đó 7→8 và giữ mọi cột/dòng gốc. Restore độc lập sau upgrade khôi phục lại đúng 7 migrations/rows; không dùng EF downgrade, không drop/reset Main. QA restore containers đã dừng, giữ volumes/backup.

Recreate QA DB giữ named volume/toàn bộ bảng; recreate web đổi IP và giữ cookies/uploads/keys; **Nginx container/start time không đổi**, tự phục hồi nhờ Docker DNS. Diễn tập QA Nginx write freeze: POST 503, GET/health 200, khôi phục CSRF 400 bình thường và DB hashes không đổi.

Release candidate: `sha256:7be367e698bb6bebd817d07ad5320c43b9ae0c8a8dff001cc8d78ac09806c04b`.
Rollback runtime giữ sẵn: `sha256:180ec655df23a78f7b85930369a781d2fb324e7d1453bfbae2fa9a990a9de885`.
194 file backend trong build context khớp source; fingerprint `de565db10e7dc079c71a9f85a3c81f034b94dfdea0a1787a816336e21c21aeef`.

Override image/rollback, maintenance config, SQL và release plan nằm riêng trong `/tmp/greenshop-integration-20261015/`, **chưa áp dụng**. Khi được duyệt: kiểm tra lại Main baseline, freeze/drain writes, tạo/verify backup mới sát deployment, recreate **chỉ web_app** bằng image đã test (`--no-deps --no-build --pull never`), áp dụng duy nhất migration pending qua startup, read-only smoke trước mở ghi lại. Dự kiến gián đoạn **30–90 giây**, là ước lượng cho web recreate/migration, không phải SLA. Không restart DB, đổi grants/TLS/volumes, tạo đơn thật hay giả xác nhận tiền trên Main.

Nếu lỗi: giữ maintenance, giữ bản trạng thái lỗi để chẩn đoán; dùng phương án restore đã diễn tập + runtime cũ nếu cần, bảo toàn/reconcile mọi ghi sau backup. MySQL DDL có thể commit từng bước; không blind downgrade/rerun/reset để che lỗi.

## G. Security

Role matrix được kiểm tra bằng HTTP GET/POST/AJAX và browser: Anonymous/Customer/Admin browse/search/AI; chỉ Customer cart/checkout/own orders/review/shop chat; chỉ Admin quản lý/inbox/notifs. Không tin Role/UserId/IsPaid/Total từ form. Antiforgery giữ nguyên, mutation GET 405, foreign IDs bị chặn, revoked/locked cookies không sống lại sau unlock, Admin self/last-admin safeguards và actor concurrency PASS.

SignalR chỉ broadcast invalidation IDs; nội dung HTTP được kiểm tra session/ownership lại. Broadcast IO/cancellation sau commit có warning metadata, không log nội dung tin. Join kiểm tra actor DB/role/version, không cho group người khác; exact Origin được kiểm tra. Upload limits/signature/path traversal/SVG/spoofed content, stored XSS và safe ReturnUrl được thử. AI text dùng textContent và card links strict local IDs; logs chỉ metadata. HTTP client redact rõ ràng Authorization/x-goog-api-key. Trust forwarded headers giới hạn proxy phân giải qua Docker DNS; nhánh DNS failure trust-list rỗng đã review tĩnh, không fault-inject Main.

Quét Git-visible source và **444 history blobs**: không phát hiện giá trị secret đang dùng hoặc mẫu private key/API/GitHub token đã kiểm tra. Không in key/headers/connection strings/cookies ra report. Đây không phải chứng minh tuyệt đối mọi lỗi bảo mật đều không tồn tại. NuGet advisory audit không báo package vulnerable; không tuyên bố đã có OS-image penetration/CVE scan riêng.

## H. UI/UX

Giữ Botanical Premium/Razor MVC, header/nav/vines/flower theme switch và giao diện Admin hiện có. Anonymous/Customer được kiểm tra light/dark; Admin giữ theme vốn có, không giả tuyên bố có dark toggle mới. Ma trận actual routes tại **320/375/390/768/1024/1440**: không horizontal overflow, lỗi JS hay thiếu asset thực. Hai URL ảnh cố ý lỗi trong negative fixtures được ghi riêng; fallback đã assert trong browser Customer/Admin, không tính chúng thành asset source mất.

Keyboard/focus/Escape/tab navigation, forms/loading/error/disabled, success feedback, hero auto-slide/drag/pause/loop/reduced-motion, native file chooser 5 ảnh, chat reconnect/offline và notification badge được thử. Admin muted text/primary/pending badge đo contrast ≥4.5:1. Kiểm thử browser dùng Chromium; không tuyên bố đã kiểm thử Safari/Firefox hay full WCAG audit.

## I. Changed files / purpose

| Nhóm | Mục đích |
|---|---|
| `AiChatProvider`, `AiConversationState`, `TroLyController`, `StoreCatalog`, `Program`, Compose/env example | Native Gemini, protected multi-turn, public grounding, safe errors/metadata/rates, server-only configuration. |
| `StorefrontViewModels`, `customer-engagement.js`, `storefront.js` | Exact decimal display, bounded AI UI/state/retry/reset, bỏ legacy total handler không còn caller. |
| Engagement model/context/migration/controller/views/services/hub | 5-photo current reviews, assignment/concurrency/read cursors, per-admin events, persisted real-time support. |
| Layout/partials/CSS/SignalR assets | Một widget hai tab, notification bell/inbox integration, responsive/focus/reduced-motion; giữ design. |
| QA helpers/suites | Identity/network/connection/mount/credential guards; cold start/exact IDs/upgrade/preservation/rehearsal, feature/security/browser/error tests. |
| README/evidence | Cấu hình/reproduction/release gates và ảnh/kết quả thực; không tạo report trùng. |

<details><summary>Danh sách file hiện có thay đổi so với HEAD (không staged)</summary>

```text
M .env.example
 M README.md
 M backend/GreenShop.Web/Areas/Admin/Controllers/KhachHangController.cs
 M backend/GreenShop.Web/Areas/Admin/Views/KhachHang/DanhGia.cshtml
 M backend/GreenShop.Web/Areas/Admin/Views/KhachHang/TinNhan.cshtml
 M backend/GreenShop.Web/Areas/Admin/Views/Shared/_AdminLayout.cshtml
 M backend/GreenShop.Web/Controllers/ChatControllerBase.cs
 M backend/GreenShop.Web/Controllers/SanPhamController.cs
 M backend/GreenShop.Web/Controllers/TuongTacController.cs
 M backend/GreenShop.Web/Data/AppDbContext.cs
 M backend/GreenShop.Web/Dockerfile
 M backend/GreenShop.Web/Migrations/AppDbContextModelSnapshot.cs
 M backend/GreenShop.Web/Models/CustomerEngagement.cs
 M backend/GreenShop.Web/Models/StorefrontViewModels.cs
 M backend/GreenShop.Web/Program.cs
 M backend/GreenShop.Web/Services/CheckoutOrders.cs
 M backend/GreenShop.Web/Services/ShopCommunication.cs
 M backend/GreenShop.Web/Services/StoreCatalog.cs
 M backend/GreenShop.Web/ViewComponents/AdminAlertsViewComponent.cs
 M backend/GreenShop.Web/Views/Shared/Components/AdminAlerts/Default.cshtml
 M backend/GreenShop.Web/Views/Shared/ShopChat.cshtml
 M backend/GreenShop.Web/Views/Shared/_Layout.cshtml
 M backend/GreenShop.Web/Views/Shared/_ProductReviews.cshtml
 M backend/GreenShop.Web/Views/ThanhToan/ChiTietDonHang.cshtml
 M backend/GreenShop.Web/Views/TuongTac/DanhGia.cshtml
 M backend/GreenShop.Web/wwwroot/css/customer-engagement.css
 M backend/GreenShop.Web/wwwroot/js/customer-engagement.js
 M backend/GreenShop.Web/wwwroot/js/storefront.js
 D backend/GreenShop.Web/wwwroot/lib/bootstrap/dist/css/bootstrap.min.css.map
 D backend/GreenShop.Web/wwwroot/lib/bootstrap/dist/js/bootstrap.bundle.min.js.map
 M docker-compose.yml
 M docs/evidence/commit1/admin-dashboard-qa.png
 M docs/evidence/commit1/build-release.txt
 M docs/evidence/commit1/checkout-qa.png
 M docs/evidence/commit1/commit1-verification.md
 M docs/evidence/commit1/compose-services.txt
 M docs/evidence/commit1/https-response.txt
 M docs/evidence/commit1/nginx-validation.txt
 M docs/evidence/commit1/phpmyadmin-qa.png
 M docs/evidence/commit1/products-main.png
 M docs/evidence/commit1/storefront-main.png
 M tests/admin_ui.py
 M tests/customer_engagement.py
 M tests/customer_ui.py
 M tests/dashboard_management.py
 M tests/excel_exports.py
 M tests/m1_acceptance.py
 M tests/order_management.py
 M tests/payment_shipping.py
 M tests/portal_sessions.py
 M tests/storefront_regression.py
 M tests/system_review.py
 M tests/ui_redesign.py
 M tests/user_management.py
?? backend/GreenShop.Web/Areas/Admin/Views/KhachHang/ThongBaoCuaToi.cshtml
?? backend/GreenShop.Web/Controllers/TroLyController.cs
?? backend/GreenShop.Web/Hubs/SupportHub.cs
?? backend/GreenShop.Web/Migrations/20261014165031_CompleteCustomerEngagement.Designer.cs
?? backend/GreenShop.Web/Migrations/20261014165031_CompleteCustomerEngagement.cs
?? backend/GreenShop.Web/Services/AdminNotifications.cs
?? backend/GreenShop.Web/Services/AiChatProvider.cs
?? backend/GreenShop.Web/Services/AiConversationState.cs
?? backend/GreenShop.Web/Views/Shared/_HybridChat.cshtml
?? backend/GreenShop.Web/wwwroot/lib/signalr/LICENSE.txt
?? backend/GreenShop.Web/wwwroot/lib/signalr/signalr.min.js
?? docs/evidence/commit1/gemini-chat-qa.png
?? docs/evidence/commit1/hybrid-chat-qa.png
?? tests/AiProviderCheck/AiProviderCheck.csproj
?? tests/AiProviderCheck/Program.cs
?? tests/qa_support.py
```

</details>

## J. New files / why needed

| File / nhóm mới trong patch | Lý do không nhét vào file không đúng trách nhiệm |
|---|---|
| `Services/AiChatProvider.cs`, `Controllers/TroLyController.cs` | Boundary provider/endpoint riêng cho một AI subsystem, tái sử dụng interface/widget; không trộn vào layout/Program. |
| `Services/AiConversationState.cs` | Codec Data Protection cho lịch sử có ràng buộc/expiry/limits; khác trách nhiệm transport và catalog. |
| `Hubs/SupportHub.cs`, SignalR client + MIT license | Endpoint realtime có ownership và thư viện browser thực; không thay bằng polling giả realtime. |
| `Services/AdminNotifications.cs`, `ThongBaoCuaToi.cshtml` | Event transaction helper + view recipient lifecycle; không phải counter suy diễn. |
| Migration 8 `.cs`/Designer | Schema additive và EF metadata bắt buộc; không sửa bảy migrations đã áp dụng. |
| `_HybridChat.cshtml` | Một partial dùng lại trong layout, không duplicate UI/app thứ hai. |
| `tests/qa_support.py`, `tests/AiProviderCheck/*` | Shared isolation/exact IDs và HTTP fault harness; app production không có fake provider. |
| `hybrid-chat-qa.png`, `gemini-chat-qa.png` | Evidence chính thức từ real browser/live provider, không debug mock screenshot. |

## K. Tests / results

| Nhóm | Kết quả | Giới hạn/phạm vi |
|---|---|---|
| Restore / Release build / Razor publish / JS syntax / Python parse | **PASS** | Build cuối 0 warning/0 error; 9 app JS files; dependency advisory audit không vulnerable package. |
| Clean source build / cold start | **PASS** | QA mới, no-cache build, DB rỗng → 8; four services, safe first-admin CLI/privileges/readiness fail-recovery. |
| 23 nhóm fixture/regression | **PASS** | Business, security, payment, audit, categories, users/user-security/user-browser, dashboard-fixtures/metrics, payment-full/edges/security/reports, Admin/Customer browser, engagement/inputs/hybrid/contracts/AI-widget/responsive/fractional. |
| Actual date helper / Excel | **PASS** | GMT+7 midnight/year/leap/previous period; Open XML schema/values/styles/formula safety/ClosedXML round-trip. |
| AI HTTP mocks / UI mocks | **PASS** | Faults không gọi key thật; UI responses mock được ghi đúng là mock. |
| AI DB integration | **PASS** | MySQL thật + provider mock; budget/nonexistent/history/tamper, re-read price after provider latency. |
| Gemini native live | **PASS** | 4 generations, all 200; 2 local refusals; no DB changes/key exposure; no load test. |
| Hybrid real WebSockets | **PASS** | Two-way delivery <2.5s assertions, multiple tabs, automatic reconnect/offline catch-up, dedup, group/Origin/session and assignment checks. |
| Upgrade/reconciliation/backup/restore/write freeze | **PASS** | Main read-only; all mutations on isolated QA; original rows/columns/images/keys retained. |
| DB/web recreate / Docker DNS / cookies/persistence | **PASS** | Real IP change; proxy unchanged; all table/file hashes and genuine cookies persist. |
| Current Main runtime/TLS/DB/read-only smoke + preservation | **PASS** | Existing runtime remains healthy; no Main deployment/mutations. |
| Main exact migration/source-runtime sync | **FAIL — intentional release blocker** | 7 applied vs 8 source; pending `CompleteCustomerEngagement`, awaiting authorization. |
| New runtime authenticated/core/live flows on Main | **NOT TESTED / BLOCKED by approval** | Không suy diễn QA success thành Main deployed success. |
| OpenAI live, alternate browsers/full WCAG, separate OS-image CVE scan | **NOT TESTED** | Không nằm trong kết quả PASS ở trên. |

Những lần FAIL trong quá trình sửa/fixture setup được giữ trong logs riêng; kết quả PASS chỉ sau khi sửa nguyên nhân và chạy lại. Không đổi expected values để che lỗi, không xóa test hoặc thêm fake production response.

## L. Remaining P0/P1/P2

- **P0:** chưa phát hiện blocker/data loss/auth bypass trong phạm vi đã kiểm thử. Không đồng nghĩa chứng minh tuyệt đối không có vulnerability.
- **P1 release gate:** Main còn runtime/schema cũ 7→8; chưa cho phép chốt M1 hay PRODUCT_READY YES trước deployment được duyệt và read-only acceptance.
- **P2 / giới hạn:** keyword retrieval và semantics của model cần đánh giá tiếp với catalog thực; limiter/SignalR ở một instance, local disk/key permissions theo baseline, TLS tự ký cho môi trường đồ án. Không mở rộng scope sang Redis/backplane/cloud/auth architecture.
- M2 (Prometheus/Grafana/metrics/alerts), M3 (Loki/Promtail hoặc phương án được môn chấp nhận/LogQL) chỉ roadmap, chưa triển khai và chưa tạo lịch sử Git milestone giả.

## M. Exact next action / approval

**Yêu cầu người dùng phê duyệt Main theo §25:** khóa ghi tạm thời và drain, backup mới sát thời điểm release, dùng image đã nghiệm thu để recreate **chỉ Main web_app**, áp dụng duy nhất migration `20261014165031_CompleteCustomerEngagement`, bật Gemini model đã kiểm thử qua secret server hiện có, kiểm tra read-only health/TLS/migrations/persistence/role gates rồi mở ghi lại. Không restart DB, đổi grants/TLS/volumes, tạo đơn thật hoặc giả thanh toán.

Ước lượng cửa sổ gián đoạn 30–90 giây. Image/rollback/SQL và backup restore đã review/rehearse; nếu Main thay đổi dữ liệu trước lúc được duyệt phải tạo/verify lại backup, không dùng snapshot cũ để bỏ mất giao dịch. User đã xác nhận Free tier; không cần gửi key vào chat và không đổi billing. Commit 1 **chưa chốt**, repository local sẵn review; không commit/push khi chưa được yêu cầu riêng.

---

<details><summary>Evidence lịch sử trước audit — giữ để đối chiếu, không phải verdict hiện hành</summary>

Các PASS/count/timestamp dưới đây thuộc lần nghiệm thu cũ. File screenshots/text đã được thay bằng evidence runtime mới ở các tên tương ứng; không dùng phần này để khẳng định source hiện tại đã deploy Main.

# GreenShop — Nghiệm thu M1 / Commit 1

**Verdict: M1 READY — workspace và runtime Ubuntu VMware đã nghiệm thu; chưa commit/push.**

Báo cáo chốt ngày 13/10/2026 theo thời gian phiên làm việc. Timestamp bên trong screenshot/log phản ánh đồng hồ VM khi thu thập; không chỉnh sửa ngày hoặc dữ liệu để tạo minh chứng.

## Phạm vi và môi trường

- Ubuntu 26.04 LTS, Docker Engine 29.7.2, Docker Compose plugin 5.4.0, SDK .NET 8.0.407, OpenSSL 3.5.5.
- Runtime Nginx 1.31.6, MySQL 8.0.46; IP VM đã kiểm tra trực tiếp: `192.168.197.128`.
- Bốn service M1: `db`, `web_app`, `nginx`, `phpmyadmin`; không thêm Prometheus/Grafana/Loki/Promtail.
- Main: `greenshop`; các phép ghi kiểm thử chỉ trong `greenshop_order_qa`, project `greenshop-m1-qa`, MySQL tmpfs và keys/images/cert riêng.
- Source code/remote hiện có: `https://github.com/dtc245200016/GreenShop`. Báo cáo này mô tả thay đổi local chưa push, không tuyên bố remote đã nhận chúng.

## Kết quả các issue

| Issue | Trạng thái | Giải pháp và bằng chứng |
|---|---|---|
| M1-01 README | PASS | Hướng dẫn tiếng Việt: prerequisites, cây thư mục thật, env, cert, DB user, Admin ban đầu, startup, backup, verification, troubleshooting, M2/M3 |
| M1-02 HTTPS | PASS | Script IP/DNS/IPv6 đúng SAN, key 600, key/cert khớp, từ chối overwrite ngầm và host sai; cert/key Main hiện có được giữ nguyên |
| M1-03 Legacy | PASS | Bỏ hai file legacy không được tham chiếu; Compose vẫn dùng `backend/GreenShop.Web/Dockerfile` và `nginx/default.conf`, upstream 8080 |
| M1-04 DB privileges | PASS trong M1 | Web dùng `greenshop_app`, chỉ quyền trong `greenshop.*`; root password không đổi. DDL vẫn cần cho startup migrations; runtime chỉ DML được hoãn |
| M1-05 Ports | PASS | 80/443 là entry point; 3306/5000/8080 bind 127.0.0.1. phpMyAdmin trên trình duyệt VM hoạt động |
| M1-06 Baseline | PASS trong M1 | Secret scan, ignore runtime secrets/data, image build excludes runtime files, TLS/headers, readiness có truy vấn DB; tồn tại non-root/network/firewall ghi rõ bên dưới |
| M1-07 Runtime | PASS | Build, cold start, migrations, SQL, phpMyAdmin, auth/business, persistence, recreate và IP-change recovery đều kiểm thử thật |

## Build và hạ tầng

| Kiểm tra | Kết quả thực tế |
|---|---|
| `docker compose config --quiet` | PASS |
| Host restore/build Release | PASS; 0 warnings, 0 errors; [log](build-release.txt) |
| Docker build/publish | PASS; 0 warnings, 0 errors; image nghiệm thu triển khai đúng image QA |
| EF pending model changes | PASS; không thay đổi model/schema, không thêm migration |
| Bốn service Main | PASS; tất cả running/healthy; [trạng thái](compose-services.txt) |
| Nginx syntax/version/DNS | PASS; version hỗ trợ `resolve`; [nginx -t](nginx-validation.txt) |
| HTTP → HTTPS | PASS; 301, giữ path và query; không redirect loop |
| TLS/SAN/key | PASS; cert khớp IP VM, chưa hết hạn, public key khớp; `curl --cacert nginx/ssl/cert.pem https://192.168.197.128/` trả 200, không dùng `-k` cho phép thử này |
| Headers trên response thật | PASS; nosniff, SAMEORIGIN, strict-origin-when-cross-origin, Server nginx không version; [response đã bỏ cookies](https-response.txt) |
| MySQL / migrations | PASS; 6 migrations, schema tồn tại; app user truy vấn được |
| phpMyAdmin | PASS; Main PHP/mysqli truy vấn MySQL thật trả đúng migration count; GUI QA đăng nhập và xem schema thành công |
| Readiness | PASS; QA DB pause → endpoint 503 và CLI probe nonzero dù web process còn sống; unpause → tự trở lại 200 |
| Cold start | PASS; MySQL tmpfs rỗng → schema, singleton shipping defaults và web; không seed dữ liệu bán hàng |
| Bootstrap | PASS; DB wrapper idempotent; app không đọc `mysql.user`, tạo user hoặc database khác; Admin mới chỉ khi Users rỗng, repeat không thay đổi dữ liệu; shell/TTY giấu password được thử thật |
| QA IP-change recovery | PASS; web chuyển từ IP Docker cấp sang `172.30.250.200`, Nginx giữ nguyên container/start time; HTTPS phục hồi, cả hai cookie vẫn đúng và mọi bảng QA không đổi |
| Main web recreate | PASS; chỉ recreate web, không restart/reload Nginx, không recreate DB để thử proxy; HTTPS 200 và dữ liệu giữ nguyên |
| Persistence Main | PASS; so hash toàn bộ 8 bảng nghiệp vụ trước/sau, ảnh/keys/cert/key và danh tính 3 named volumes giống nhau; 6 migrations không reset |
| Runtime logs | PASS; logs startup đã đọc, không có critical/unhandled exception; logs thô giữ riêng vì có thể chứa metadata vận hành |

## Hồi quy ứng dụng

Các test dưới đây chạy trên dữ liệu **synthetic QA**, không tạo/hủy/sửa/đánh dấu Paid đơn hàng thật.

- Storefront: danh mục, tìm kiếm, pagination, category không hoạt động/rỗng, product details, giá/stock live, HTML escaping.
- Auth: register/login/returnUrl, Admin-only, CSRF/POST-only, ownership, cookie không nâng quyền khi đổi tên; revoke/lock không làm hỏng portal còn lại.
- Cart/checkout: giỏ theo user, merge/update/remove, chống overposting, giá server, số lượng/stock, idempotency và hai khách tranh sản phẩm cuối.
- Orders/Admin: vòng đời 0→3→4→5→1, giá snapshot lịch sử, COD audit, CAS, hủy/hoàn kho đúng một lần, rollback multi-item, thiếu tham chiếu và dữ liệu tổng sai được chặn.
- Payment: cấu hình ngân hàng giả, VietQR render, customer notify vẫn unpaid, Admin xác nhận thủ công đúng actor, shipping 30k/ngưỡng 300k và XLSX download. Không có giao dịch tiền thật; không kiểm thử quét app ngân hàng.
- UI/browser: Admin orders/CRUD/upload/replacement, hộp xác nhận/focus/keyboard, print; customer home/catalog/auth/cart/checkout/history/receipt ở 320/360/768/1440 px; không tràn ngang/JS error trong kiểm thử.
- Main chỉ đọc: trang chủ/catalog/login/assets, HTTPS/header/challenges, SQL/schema, ảnh thật, volume/hash và public screenshots.

Các entry point kiểm thử được đọc trước khi chạy và gắn vào QA độc lập. `tests/m1_acceptance.py` tái sử dụng fixtures/suite hiện có. Dữ liệu giả hiển thị trong screenshot Admin/checkout/phpMyAdmin **không phải dữ liệu kinh doanh Main**.

## Minh chứng ảnh thật

| File | Nguồn và nội dung |
|---|---|
| [Storefront](storefront-main.png) | Main, public GET; ảnh/sản phẩm thật của catalogue, không đăng nhập |
| [Products](products-main.png) | Main, public GET; danh mục/sản phẩm thật |
| [Admin Dashboard](admin-dashboard-qa.png) | QA; tài khoản/tổng đơn và số liệu synthetic |
| [Checkout](checkout-qa.png) | QA; thông tin người nhận/địa chỉ synthetic, chưa submit trong lúc chụp |
| [phpMyAdmin](phpmyadmin-qa.png) | GUI đã đăng nhập vào DB QA; chín bảng gồm migration history, không có form password |

Ảnh được tạo trực tiếp bằng Chromium/Playwright, không dựng mockup hoặc đổi dữ liệu hiển thị để giả PASS. Không lưu `.env`, token, cookie, password, private key, dump hay dữ liệu khách hàng Main trong evidence. Backup, credential test, configs QA có secret và logs thô chỉ ở `/tmp/greenshop-m1`, không đưa vào Git.

## Security và giới hạn còn lại

- PASS: các file tracked/pending public không chứa hai password DB thật; cert/key/env/runtime uploads không tracked. Không reset root/Admin password, đổi role người dùng thật hay xoá volume/data.
- Web chạy root; keys hiện hữu `0:0/700`. Chuyển non-root cần migration ownership có kiểm soát và thử ghi keys/images; không `chown -R` dữ liệu thật trong M1.
- App DB user đã bỏ quyền global của root, nhưng vẫn có DDL schema để EF migrations; tách credentials migration/runtime và runtime DML-only làm ở hardening sau.
- Một bridge `app_net`; chưa tách frontend/backend. Các data/debug ports chỉ loopback.
- Firewall host: NOT TESTED đầy đủ do phiên này không có quyền sudo để đọc rules; không tự thay firewall hoặc dịch vụ host khác.
- SSH tunnel/Windows: NOT TESTED end-to-end; SSH reachable nhưng không có chứng thực tự động, không sửa authorized_keys/password host. Demo phpMyAdmin bằng browser VM đã PASS; hướng dẫn tunnel trong README cho bước kiểm tra từ Windows khi có tài khoản SSH.
- Tự ký là TLS demo/private VM, không phải cấu hình TLS public production. Không thêm CSP/HSTS mạnh hoặc stack monitoring/logging mới.

**Không còn blocker P0 trong phạm vi M1 chạy trên Ubuntu VM đã nghiệm thu.** Các giới hạn trên là hardening/demo bổ sung, không được báo là đã hoàn thành.

## Git và mốc tiếp theo

Branch `main`. Không commit, push, reset, checkout, stash hoặc clean. Bảo toàn các thay đổi UI/business chưa commit từ trước; chỉ chỉnh những file hạ tầng/documentation liên quan và phần deployment/readiness của Program.

Người dùng duyệt thay đổi và tự chốt Commit 1. Mốc tiếp theo được đề xuất: **M2 — Prometheus + Grafana**; chưa triển khai M2/M3 trong lần này.


</details>

</details>
