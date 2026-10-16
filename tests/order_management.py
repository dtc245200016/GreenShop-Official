from qa_support import PRIVATE, PROJECT
"""Order workflow QA against an isolated MySQL/GreenShop deployment; never mutate real orders.

Evidence and private backups stay in GREENSHOP_QA_DIR.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import concurrent.futures
import storefront_regression as gs

ROOT = gs.ROOT
MAIN_COMPOSE = gs.main_compose
from qa_support import PRIVATE, PROJECT, guard
OUT = PRIVATE / "qa"
OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
QA_BASE = "https://localhost:" + os.environ.get("GREENSHOP_QA_HTTPS_PORT", "18543")
QA_PROJECT = PROJECT


def qa_compose(*args, input=None):
    return subprocess.check_output(["docker", "compose", "--project-name", QA_PROJECT, "--file", str(OUT / "compose.yaml"),
        "--env-file", str(OUT / "qa.env"), *args], cwd=ROOT, text=True, input=input).strip()


_guarded_config = None

def qa_sql(query):
    global _guarded_config
    config = json.loads((OUT / "compose.yaml").read_text())
    assert config["services"]["db"]["environment"]["MYSQL_DATABASE"] == "greenshop_order_qa"
    assert QA_PROJECT == PROJECT
    digest = hashlib.sha256((OUT / "compose.yaml").read_bytes()).hexdigest()
    if not query.lstrip().upper().startswith(("SELECT ","SHOW ")) and _guarded_config != digest:
        guard(qa_compose, MAIN_COMPOSE)
        _guarded_config = digest
    return qa_compose("exec", "-T", "db", "sh", "-c", 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B --default-character-set=utf8mb4 "$MYSQL_DATABASE"', input=query)


def configure_qa():
    guard(qa_compose, MAIN_COMPOSE)
    assert qa_sql("SELECT DATABASE()") == "greenshop_order_qa"
    gs.BASE, gs.compose, gs.sql = QA_BASE, qa_compose, qa_sql


def prepare():
    import m1_acceptance
    m1_acceptance.prepare()
    m1_acceptance.cold()

def start(check_legacy=True):
    qa_compose("up", "-d", "web_app", "nginx")
    qa_compose("restart", "nginx")
    for _ in range(60):
        try:
            gs.BASE = QA_BASE
            if gs.request(gs.client(), "/")[0] == 200: break
        except (OSError, urllib.error.URLError): pass
        time.sleep(1)
    else: raise AssertionError("QA application did not start")
    if check_legacy:
        assert qa_sql("SELECT Version,InventoryStatus,Status,IsPaid,Total FROM Orders WHERE Id=1") == "0\t0\t0\t0\t200000.00"
        assert qa_sql("SELECT UnitPrice,Quantity FROM OrderItems WHERE OrderId=1") == "100000.00\t2"
        print("PASS: Additive migration preserved legacy order amounts/status/payment; legacy inventory remains explicitly unverified.", flush=True)
    else: print("PASS: Updated QA application ready; existing test data retained.", flush=True)


def admin_sessions():
    credentials = json.loads((OUT / "accounts.json").read_text())
    admins = [gs.client(), gs.client()]
    for client, account in zip(admins, credentials):
        gs.login(client, account, expected="/Admin")
    return admins


def detail(client, order_id):
    return gs.get(client, f"/Admin/DonHang/ChiTietDonHang/{order_id}")[0]


def mutate(client, order_id, action, values=None, source=None):
    source = source or detail(client, order_id)
    return gs.post(client, f"/Admin/DonHang/{action}/{order_id}", source,
        {"ExpectedVersion": qa_sql(f"SELECT Version FROM Orders WHERE Id={order_id}"), **(values or {})})


def create_order(client, product_id, quantity=2):
    page, values = gs.confirm(client, product_id, quantity)
    code, headers, _ = gs.post(client, f"/ThanhToan/XacNhanMuaHang/{product_id}", page, values)
    assert code == 302
    order_id = int(headers["Location"].rsplit("/", 1)[1])
    assert qa_sql(f"SELECT InventoryStatus FROM Orders WHERE Id={order_id}") == "1"
    return order_id


def run_business():
    configure_qa()
    checks = []
    def passed(label):
        checks.append(label)
        print("PASS:", label, flush=True)
    # Each invocation owns fresh in-memory fixture IDs, even after other suites in
    # the same process have registered users. Retain all previously created QA data.
    gs.RUN="GS_STOREFRONT_"+secrets.token_hex(16)
    gs.product_ids.clear();gs.category_ids.clear();gs.user_ids.clear();gs.checks.clear()
    # Existing end-to-end HTTP tests run only against this disposable database.
    gs.fixtures()
    gs.http_checks()
    checks.extend(gs.checks)
    a1, a2 = admin_sessions()
    anon, shopper, other = gs.client(), gs.client(), gs.client()
    creds = gs.register(shopper)
    gs.login(shopper, creds)
    gs.login(other, gs.register(other))
    actions = ("XacNhanDonHang", "CapNhatTrangThaiDonHang", "HuyDonHang", "CapNhatGhiChuDonHang", "XacNhanThuCod", "XacNhanDaTruKho")
    for client in (anon, shopper):
        for path in ("/Admin/DonHang/QuanLyDonHang", "/Admin/DonHang/ChiTietDonHang/1", "/Admin/DonHang/InDonHang/1"):
            gs.get(client, path, 302)
        source = gs.get(client, "/")[0]
        for action in actions:
            assert gs.post(client, f"/Admin/DonHang/{action}/1", source, {"ExpectedVersion": 0, "TargetStatus": 3, "Note": "Denied"})[0] == 302
    source = detail(a1, 1)
    for action in actions:
        gs.get(a1, f"/Admin/DonHang/{action}/1", 405)
        assert gs.request(a1, f"/Admin/DonHang/{action}/1", {"ExpectedVersion": 0})[0] == 400
    gs.get(a1, "/Admin/DonHang/ChiTietDonHang/2147483647", 404)
    gs.get(a1, "/Admin/DonHang/InDonHang/2147483647", 404)
    passed("Real login with two isolated Admins; anonymous/Customer denied for every Admin endpoint; POST-only, antiforgery, missing IDs")
    for path in ("?page=0", "?pageSize=999", "?status=999", "?sort=wrong", "?fromDate=2026-02-01&toDate=2026-01-01", "?search=" + "x"*101):
        gs.get(a1, "/Admin/DonHang/QuanLyDonHang" + path, 400)
    # A fresh legacy fixture makes this destructive workflow repeatable without resetting
    # previously audited orders or weakening the expected legacy inventory behavior.
    legacy_product=int(qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity) VALUES ('QA legacy inventory',100000,'/images/product-placeholder.svg','QA historical stock log: 20 minus 2 ordered',18); SELECT LAST_INSERT_ID()"))
    legacy=int(qa_sql("INSERT INTO Orders (UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES (3,"+gs.quote(__import__('uuid').uuid4().hex)+",'QA repeatable legacy','0912345678','QA legacy inventory address',UTC_TIMESTAMP(),200000,0,0,'COD',0,'',0); SELECT LAST_INSERT_ID()"))
    qa_sql(f"INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES ({legacy},{legacy_product},'QA legacy inventory','/images/product-placeholder.svg',100000,2)")
    legacy_stock = int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={legacy_product}"))
    assert mutate(a1, legacy, "XacNhanDonHang")[0] == 422
    assert mutate(a1, legacy, "HuyDonHang", {"Note": "Legacy cancel"})[0] == 422
    assert int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={legacy_product}")) == legacy_stock
    assert mutate(a1, legacy, "XacNhanDaTruKho", {"Note": ""})[0] == 422
    assert mutate(a1, legacy, "XacNhanDaTruKho", {"Note": "QA legacy stock log: 20 initial minus 2 ordered = 18"})[0] == 302
    assert int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={legacy_product}")) == legacy_stock
    assert mutate(a1, legacy, "HuyDonHang", {"Note": "QA cancel reconciled legacy order"})[0] == 302
    assert int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={legacy_product}")) == legacy_stock + 2
    assert qa_sql(f"SELECT COUNT(*) FROM Orders WHERE Id={legacy}") == "1"
    passed("Legacy unverified inventory blocks processing/cancellation; explicit evidence records no stock change; subsequent cancellation restores exactly once")
    p = gs.product_ids[2]
    order_id = create_order(shopper, p)
    stock = int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}"))
    amount = qa_sql(f"SELECT Total FROM Orders WHERE Id={order_id}")
    qa_sql(f"UPDATE Products SET Price=987654 WHERE Id={p}")
    _, body, _ = gs.get(a1, f"/Admin/DonHang/ChiTietDonHang/{order_id}")
    assert "254.000 đ" in body and "127.000 đ" in body and "987.654 đ" not in body
    assert mutate(a1, order_id, "XacNhanThuCod", {"Note": "Premature payment"})[0] == 409
    assert mutate(a1, order_id, "CapNhatTrangThaiDonHang", {"TargetStatus": 5})[0] == 409
    assert mutate(a1, order_id, "CapNhatTrangThaiDonHang", {"TargetStatus": 999})[0] == 400
    assert gs.post(a1, f"/Admin/DonHang/XacNhanDonHang/{order_id}", detail(a1, order_id), {})[0] == 400
    for action, target in (("XacNhanDonHang", 3), ("CapNhatTrangThaiDonHang", 4), ("CapNhatTrangThaiDonHang", 5), ("CapNhatTrangThaiDonHang", 1)):
        old_page = detail(a1, order_id)
        old_version = qa_sql(f"SELECT Version FROM Orders WHERE Id={order_id}")
        assert mutate(a1, order_id, action, {"TargetStatus": target})[0] == 302
        assert qa_sql(f"SELECT Status,IsPaid,Total FROM Orders WHERE Id={order_id}") == f"{target}\t0\t{amount}"
        assert int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}")) == stock
        assert gs.post(a2, f"/Admin/DonHang/{action}/{order_id}", detail(a2, order_id), {"ExpectedVersion": old_version, "TargetStatus": target})[0] == 409
        _, customer_body, _ = gs.get(shopper, f"/ThanhToan/ChiTietDonHang/{order_id}")
        assert {3: "Đã xác nhận", 4: "Đang xử lý", 5: "Đang giao", 1: "Đã giao"}[target] in customer_body
        if target == 5:
            assert mutate(a1, order_id, "HuyDonHang", {"Note": "Shipping cannot cancel"})[0] == 409
    assert mutate(a1, order_id, "HuyDonHang", {"Note": "Delivered cannot cancel"})[0] == 409
    assert mutate(a1, order_id, "CapNhatTrangThaiDonHang", {"TargetStatus": 0})[0] == 409
    gs.get(other, f"/ThanhToan/ChiTietDonHang/{order_id}", 404)
    assert qa_sql(f"SELECT COUNT(*) FROM OrderStatusHistories WHERE OrderId={order_id} AND Kind=0") == "4"
    assert mutate(a1, order_id, "XacNhanThuCod", {"Note": ""})[0] == 422
    assert mutate(a1, order_id, "XacNhanThuCod", {"Note": "QA COD collection receipt reconciled"})[0] == 302
    assert mutate(a2, order_id, "XacNhanThuCod", {"Note": "Duplicate"})[0] == 409
    assert qa_sql(f"SELECT IsPaid FROM Orders WHERE Id={order_id}") == "1"
    note = "QA internal <script>alert('x')</script>"
    assert mutate(a1, order_id, "CapNhatGhiChuDonHang", {"Note": note})[0] == 302
    raw = gs.request(a1, f"/Admin/DonHang/ChiTietDonHang/{order_id}")[2]
    assert "&lt;script&gt;" in raw and "<script>alert('x')</script>" not in raw
    assert "QA internal" not in gs.get(shopper, f"/ThanhToan/ChiTietDonHang/{order_id}")[1]
    passed("Historical price/total preserved; full 0→3→4→5→1 workflow; stale/backwards/invalid/terminal updates rejected; customer status/ownership synchronized; COD separate and audited; escaped internal notes")
    race = create_order(shopper, p)
    version = qa_sql(f"SELECT Version FROM Orders WHERE Id={race}")
    before_stock = int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}"))
    clients = (a1, a2)
    pages = [detail(c, race) for c in clients]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda x: gs.post(x[0], f"/Admin/DonHang/HuyDonHang/{race}", x[1], {"ExpectedVersion": version, "Note": "QA concurrent cancel"}), zip(clients, pages)))
    assert sorted(r[0] for r in results) == [302, 409]
    assert int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}")) == before_stock + 2
    assert qa_sql(f"SELECT Status,InventoryStatus FROM Orders WHERE Id={race}") == "2\t2"
    assert qa_sql(f"SELECT COUNT(*) FROM OrderStatusHistories WHERE OrderId={race}") == "1"
    assert mutate(a1, race, "HuyDonHang", {"Note": "Repeat cancel"})[0] == 409
    assert mutate(a1, race, "CapNhatTrangThaiDonHang", {"TargetStatus": 5})[0] == 409
    race2 = create_order(shopper, p)
    version = qa_sql(f"SELECT Version FROM Orders WHERE Id={race2}")
    pages = [detail(c, race2) for c in clients]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda x: gs.post(x[0], f"/Admin/DonHang/XacNhanDonHang/{race2}", x[1], {"ExpectedVersion": version}), zip(clients, pages)))
    assert sorted(r[0] for r in results) == [302, 409]
    assert qa_sql(f"SELECT Status FROM Orders WHERE Id={race2}") == "3"
    passed("Two Admins cancel concurrently: one winner, one history event, one exact stock restoration; repeat/terminal rejected; concurrent confirmation uses CAS")
    missing = create_order(shopper, gs.product_ids[3])
    qa_sql(f"UPDATE OrderItems SET ProductId=NULL,ImageUrl='/uploads/products/missing-order.png' WHERE OrderId={missing}")
    assert mutate(a1, missing, "HuyDonHang", {"Note": "Missing reference"})[0] == 422
    assert qa_sql(f"SELECT Status,Version FROM Orders WHERE Id={missing}") == "0\t0"
    gs.get(a1, f"/Admin/DonHang/ChiTietDonHang/{missing}")
    multi = create_order(shopper, p)
    p2 = gs.product_ids[4]
    qa_sql(f"UPDATE Products SET StockQuantity=StockQuantity-1 WHERE Id={p2}; INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) SELECT {multi},Id,Name,ImageUrl,Price,1 FROM Products WHERE Id={p2}; UPDATE Orders SET Total=Total+129000,Subtotal=CASE WHEN Subtotal IS NULL THEN NULL ELSE Subtotal+129000 END WHERE Id={multi}; UPDATE Products SET StockQuantity=2147483647 WHERE Id={p2};")
    stock = qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}")
    assert mutate(a1, multi, "HuyDonHang", {"Note": "Overflow rollback"})[0] == 422
    assert qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}") == stock
    assert qa_sql(f"SELECT Status,Version,InventoryStatus FROM Orders WHERE Id={multi}") == "0\t0\t1"
    assert qa_sql(f"SELECT COUNT(*) FROM OrderStatusHistories WHERE OrderId={multi}") == "0"
    qa_sql(f"UPDATE Products SET StockQuantity=10 WHERE Id={p2}")
    assert mutate(a1, multi, "HuyDonHang", {"Note": "Multi-item cancel"})[0] == 302
    assert int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}")) == int(stock) + 2
    assert qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p2}") == "11"
    bad_total = create_order(shopper, p)
    qa_sql(f"UPDATE Orders SET Total=Total+1 WHERE Id={bad_total}")
    assert mutate(a1, bad_total, "XacNhanDonHang")[0] == 422
    assert qa_sql(f"SELECT Version FROM Orders WHERE Id={bad_total}") == "0"
    passed("Missing product references safely block cancellation; multi-product cancellation atomic with full rollback on overflow; mismatched totals cannot be processed")
    for _ in range(17): create_order(shopper, gs.product_ids[5], 1)
    term = gs.RUN
    path = "/Admin/DonHang/QuanLyDonHang?" + urllib.parse.urlencode({"search": term, "status": 0, "fromDate": "2026-01-01", "toDate": "2026-12-31", "sort": "total-asc", "pageSize": 15})
    page, _, _ = gs.get(a1, path)
    ids = [int(a["data-order-id"]) for tag, a in page.nodes if tag == "tr" and "data-order-id" in a]
    assert len(ids) == 15
    totals = [float(qa_sql(f"SELECT Total FROM Orders WHERE Id={i}")) for i in ids]
    assert totals == sorted(totals)
    page2 = gs.get(a1, path + "&page=2")[0]
    ids2 = [int(a["data-order-id"]) for tag, a in page2.nodes if tag == "tr" and "data-order-id" in a]
    assert ids2 and not set(ids).intersection(ids2)
    links = [a["href"] for tag, a in page.nodes if tag == "a" and a.get("href", "").find("page=2") >= 0]
    assert links and all(key in links[0] for key in ("search=", "status=0", "fromDate=", "toDate=", "sort=total-asc", "pageSize=15"))
    for search in (f"GS-{order_id:06}", f"#{order_id}", creds[0]):
        gs.get(a1, "/Admin/DonHang/QuanLyDonHang?" + urllib.parse.urlencode({"search": search}))
    assert "Không tìm thấy đơn phù hợp" in gs.get(a1, "/Admin/DonHang/QuanLyDonHang?search=QA_NEVER_FOUND")[1]
    gs.get(a1, f"/Admin/DonHang/InDonHang/{order_id}")
    code,headers,_=gs.request(a1,"/Admin/Admin/Index")
    assert code==302 and '/Admin/Admin/TongQuan' in headers['Location']
    dashboard = gs.get(a1, "/Admin/Admin/TongQuan")[1]
    assert "/Admin/DonHang/QuanLyDonHang" in dashboard and "Giá trị đơn đã giao" in dashboard
    for action in ("QuanLySanPham", "ChiTietSanPham", "ThemSanPham"):
        gs.get(a1, "/Admin/SanPham/" + action + (f"/{p}" if action == "ChiTietSanPham" else ""))
    gs.get(a1, "/Admin/DanhMuc/QuanLyDanhMuc")
    (OUT / "test-state.json").write_text(json.dumps({"order_id": order_id, "pending_id": bad_total + 1, "missing_id": missing, "race_id": race, "product_id": p, "customer": creds, "customer_id": gs.user_ids[-2]}, indent=2))
    os.chmod(OUT / "test-state.json", 0o600)
    passed("SQL filters/search/sort/date bounds/pagination retained in links; real summary/dashboard; print/detail and existing Admin pages")
    (OUT / "business-results.json").write_text(json.dumps({"status": "PASS", "database": "isolated only", "checks": checks}, indent=2))


def browser_checks():
    import base64
    import re
    configure_qa()
    from playwright.sync_api import sync_playwright, expect
    state = json.loads((OUT / "test-state.json").read_text())
    account = json.loads((OUT / "accounts.json").read_text())[0]
    buyer = gs.client()
    gs.login(buyer, state["customer"])
    state["pending_id"] = create_order(buyer, state["product_id"], 1)
    checks, errors = [], []
    def passed(label):
        checks.append(label)
        print("PASS:", label, flush=True)
    def overflow(page, width, path):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, path,
            page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width])"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(ignore_https_errors=True, viewport={"width":1440,"height":1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(QA_BASE + "/Account/Login")
        page.locator("#Email").fill(account[0])
        page.locator("input[name=Password]").fill(account[1])
        page.locator("form:has(#Email) button[type=submit]").click()
        expect(page).to_have_url(re.compile(r"/Admin/Admin/TongQuan$"))
        expect(page.locator("[data-metric=value]")).to_contain_text("Giá trị đơn đã giao")
        original_value=page.locator("[data-metric=value] .dash-value").inner_text()
        original_date = qa_sql(f"SELECT DATE_FORMAT(CreatedAt,'%Y-%m-%d %H:%i:%s.%f') FROM Orders WHERE Id={state['order_id']}")
        try:
            qa_sql(f"UPDATE Orders SET CreatedAt=DATE_ADD(UTC_TIMESTAMP(),INTERVAL 2 MONTH) WHERE Id={state['order_id']}")
            page.reload()
            assert page.locator("[data-metric=value] .dash-value").inner_text()!=original_value
        finally:
            qa_sql(f"UPDATE Orders SET CreatedAt={gs.quote(original_date)} WHERE Id={state['order_id']}")
        page.reload()
        passed("Dashboard delivered-order value changes when a delivered fixture moves outside the selected period; future-month fixture excluded")
        # The link's accessible name includes its live Pending badge when nonzero.
        page.locator('.admin-sidebar a[href="/Admin/DonHang/QuanLyDonHang"]').click()
        expect(page.locator("h1")).to_have_text("Quản lý đơn hàng")
        expect(page.locator('.admin-sidebar a[aria-current=page]')).to_contain_text("Quản lý Đơn hàng")
        for width in (1440, 768, 360):
            page.set_viewport_size({"width":width,"height":1000})
            for name, path in (("list", "/Admin/DonHang/QuanLyDonHang"), ("detail", f"/Admin/DonHang/ChiTietDonHang/{state['order_id']}"), ("empty", "/Admin/DonHang/QuanLyDonHang?search=QA_NEVER_FOUND")):
                page.goto(QA_BASE + path)
                overflow(page, width, path)
                assert not re.search(r"@(if|foreach|Model\.|\{)", page.locator(".order-admin").inner_text()), path
                page.screenshot(path=str(OUT / f"admin-order-{name}-{width}.png"), full_page=True, animations="disabled")
                if width == 360 and name == "list":
                    page.screenshot(path=str(OUT / "admin-order-list-mobile-viewport.png"), animations="disabled")
        passed("Admin login/sidebar active; list/detail/empty screenshots at 1440/768/360 px, no horizontal overflow")
        page.set_viewport_size({"width":1440,"height":1000})
        page.goto(QA_BASE + "/Admin/DonHang/QuanLyDonHang")
        contrasts = page.evaluate(r"""() => {
            const lum = s => s.match(/\d+(?:\.\d+)?/g).slice(0,3).map(Number).map(x => { x/=255; return x<=.04045?x/12.92:((x+.055)/1.055)**2.4; }).reduce((sum,x,i)=>sum+x*[.2126,.7152,.0722][i],0);
            const ratio = (a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
            const css = s=>getComputedStyle(document.querySelector(s));
            const contrast = (text, background) => {
                let element=document.querySelector(background),style=getComputedStyle(element);
                while (style.backgroundColor==='rgba(0, 0, 0, 0)' && style.backgroundImage==='none' && element.parentElement) {
                    element=element.parentElement;style=getComputedStyle(element);
                }
                // Use the weakest contrast across actual gradient stops, rather than transparent black.
                const stops=style.backgroundImage.match(/rgba?\([^)]+\)/g);
                return Math.min(...(stops || [style.backgroundColor]).map(color=>ratio(css(text).color,color)));
            };
            return {muted:contrast('.order-stat > span:not(.order-stat-icon)','.order-stat'),
                button:contrast('.order-btn.primary','.order-btn.primary'),
                pending:contrast('.order-badge.pending','.order-badge.pending')};
        }""")
        assert all(v >= 4.5 for v in contrasts.values()), contrasts
        (OUT / "contrast.json").write_text(json.dumps(contrasts,indent=2))
        passed("Measured muted text/primary button/pending badge contrast meets 4.5:1")
        card = page.locator(".order-stat").first
        card.hover()
        page.wait_for_timeout(250)
        assert card.evaluate("e=>getComputedStyle(e).transform") != "none"
        button = page.locator(".order-row-action a").first
        button.focus()
        page.keyboard.press("Tab")
        page.keyboard.press("Shift+Tab")
        assert button.evaluate("e=>getComputedStyle(e).outlineStyle") != "none"
        button.hover()
        page.mouse.down()
        page.wait_for_timeout(170)
        assert button.evaluate("e=>getComputedStyle(e).transform") != "none"
        page.mouse.move(2,2)
        page.mouse.up()
        page.emulate_media(reduced_motion="reduce")
        card.hover()
        assert card.evaluate("e=>getComputedStyle(e).transitionDuration") == "0s"
        assert card.evaluate("e=>getComputedStyle(e).transform") == "none"
        page.emulate_media(reduced_motion="no-preference")
        page.locator("#orderStatus").select_option("0")
        page.locator("#orderSort").select_option("total-asc")
        page.get_by_role("button", name="Áp dụng bộ lọc").click()
        expect(page).to_have_url(re.compile("status=0"))
        assert page.locator("tbody tr").count() == 15
        page.locator(".order-pagination").get_by_role("link", name="Tiếp →").click()
        expect(page).to_have_url(re.compile("page=2"))
        assert "sort=total-asc" in page.url and "status=0" in page.url
        passed("Summary hover lift, pressed/focus and reduced motion; real status/sort controls and pagination keep filters")
        pending = state["pending_id"]
        page.goto(QA_BASE + f"/Admin/DonHang/ChiTietDonHang/{pending}")
        confirm = page.get_by_role("button", name="Xác nhận đơn", exact=True)
        confirm.click()
        dialog = page.locator("#orderConfirmDialog")
        expect(dialog).to_be_visible()
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate("document.querySelector('#orderConfirmDialog').contains(document.activeElement)")
        for _ in range(12):
            page.keyboard.press("Shift+Tab")
            assert page.evaluate("document.querySelector('#orderConfirmDialog').contains(document.activeElement)")
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(confirm).to_be_focused()
        # Native dialog close queues its close event, which restores scrolling.
        page.wait_for_function("getComputedStyle(document.documentElement).overflowY !== 'hidden'")
        confirm.click()
        page.mouse.click(2,2)
        expect(dialog).not_to_be_visible()
        confirm.click()
        page.screenshot(path=str(OUT / "admin-order-confirmation.png"), animations="disabled")
        page.locator("#orderConfirmSubmit").click()
        expect(page.locator(".admin-action-feedback")).to_be_visible()
        expect(page.locator(".order-steps [aria-current=step]")).to_contain_text("Đã xác nhận")
        page.get_by_role("button", name="Hủy đơn hàng", exact=True).click()
        page.locator("#orderConfirmSubmit").click()
        expect(dialog).to_be_visible()
        assert not page.locator("#orderReason").evaluate("e=>e.checkValidity()")
        page.locator("#orderReason").fill("QA browser cancellation evidence")
        page.screenshot(path=str(OUT / "admin-order-cancel-modal.png"), animations="disabled")
        page.locator("#orderConfirmSubmit").click()
        expect(page.locator(".order-cancelled-message")).to_be_visible()
        expect(page.get_by_role("button", name="Hủy đơn hàng", exact=True)).to_have_count(0)
        page.locator("#adminNote").fill("QA browser note: follow up")
        page.get_by_role("button", name="Lưu ghi chú", exact=True).click()
        expect(page.locator(".admin-action-feedback")).to_contain_text("Đã lưu ghi chú")
        passed("Native confirmation modal focus trap/Escape/backdrop/return and scroll unlock; status timeline, success feedback, required cancellation reason and notes submit")
        page.goto(QA_BASE + f"/Admin/DonHang/ChiTietDonHang/{state['missing_id']}")
        expect(page.locator("img[data-order-image]")).to_have_attribute("src", "/images/product-placeholder.svg")
        page.goto(QA_BASE + f"/Admin/DonHang/InDonHang/{state['order_id']}")
        expect(page.locator("[data-order-print]")).to_be_visible()
        page.emulate_media(media="print")
        assert page.locator(".admin-sidebar").evaluate("e=>getComputedStyle(e).display") == "none"
        assert page.locator(".order-action-panel").evaluate("e=>getComputedStyle(e).display") == "none"
        page.pdf(path=str(OUT / "admin-order-print.pdf"), format="A4", print_background=True)
        page.emulate_media(media="screen")
        passed("Broken order image fallback and real print view/PDF hide navigation/actions/internal notes")
        # Regression CRUD/upload runs exclusively in the owned test database.
        name = "QA Order Regression Category"
        page.goto(QA_BASE + "/Admin/DanhMuc/ThemDanhMuc")
        page.locator("#Name").fill(name)
        page.locator("#Description").fill("QA isolated category")
        page.locator("form:has(#Name) button[type=submit]").click()
        expect(page).to_have_url(re.compile("/Admin/DanhMuc/QuanLyDanhMuc"))
        category_id = int(qa_sql("SELECT Id FROM Categories WHERE Name=" + gs.quote(name)))
        page.goto(QA_BASE + f"/Admin/DanhMuc/SuaDanhMuc/{category_id}")
        page.locator("#Name").fill(name + " Updated")
        page.locator("form:has(#Name) button[type=submit]").click()
        expect(page).to_have_url(re.compile("/Admin/DanhMuc/QuanLyDanhMuc"))
        page.goto(QA_BASE + "/Admin/SanPham/ThemSanPham")
        page.locator("#Name").fill("QA Uploaded Plant")
        page.locator("#Price").fill("123000")
        page.locator("#StockQuantity").fill("7")
        page.locator("#CategoryId").select_option(str(category_id))
        image = {"name":"qa-order-fixture.png", "mimeType":"image/png", "buffer":base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1sAAAAASUVORK5CYII=")}
        page.locator("#Image").set_input_files(image)
        page.locator("form:has(#Name) button[type=submit]").click()
        expect(page).to_have_url(re.compile("/Admin/SanPham/QuanLySanPham"))
        product_id = int(qa_sql("SELECT Id FROM Products WHERE Name='QA Uploaded Plant'"))
        original = qa_sql(f"SELECT ImageUrl FROM Products WHERE Id={product_id}")
        assert original.startswith("/uploads/products/")
        page.goto(QA_BASE + original)
        assert page.locator("img").evaluate("e=>e.naturalWidth") == 1
        page.goto(QA_BASE + f"/Admin/SanPham/SuaSanPham/{product_id}")
        page.locator("#Price").fill("150000")
        page.locator("#Image").set_input_files(image)
        page.locator("form:has(#Name) button[type=submit]").click()
        expect(page).to_have_url(re.compile("/Admin/SanPham/QuanLySanPham"))
        updated = qa_sql(f"SELECT ImageUrl FROM Products WHERE Id={product_id}")
        assert original != updated and qa_sql(f"SELECT Price,StockQuantity,CategoryId FROM Products WHERE Id={product_id}") == f"150000.00\t7\t{category_id}"
        page.goto(QA_BASE + f"/Admin/DanhMuc/XoaDanhMuc/{category_id}")
        assert "Không thể xóa" in page.locator("body").inner_text() or page.locator('button[type=submit]:disabled').count() > 0
        page.goto(QA_BASE + f"/Admin/SanPham/XoaSanPham/{product_id}")
        page.locator("form[method=post]:not(#logoutForm) button[type=submit]").click()
        expect(page).to_have_url(re.compile("/Admin/SanPham/QuanLySanPham"))
        assert qa_sql(f"SELECT COUNT(*) FROM Products WHERE Id={product_id}") == "0"
        page.goto(QA_BASE + f"/Admin/DanhMuc/XoaDanhMuc/{category_id}")
        page.locator("form[method=post]:not(#logoutForm) button[type=submit]").click()
        expect(page).to_have_url(re.compile("/Admin/DanhMuc/QuanLyDanhMuc"))
        assert qa_sql(f"SELECT COUNT(*) FROM Categories WHERE Id={category_id}") == "0"
        passed("Admin Category/Product create/read/update/delete, dependency guard, real image upload/replacement; only isolated owned fixtures used")
        customer = browser.new_page(ignore_https_errors=True, viewport={"width":360,"height":900})
        customer.goto(QA_BASE + "/Account/Login")
        customer.locator("#Email").fill(state["customer"][0])
        customer.locator("input[name=Password]").fill(state["customer"][1])
        customer.locator("form:has(#Email) button[type=submit]").click()
        expect(customer).to_have_url(QA_BASE + "/")
        customer.goto(QA_BASE + f"/ThanhToan/ChiTietDonHang/{state['order_id']}")
        expect(customer.locator(".shop-page-heading")).to_contain_text("Đã giao")
        expect(customer.locator(".shop-page-heading")).to_contain_text("Đã thanh toán")
        customer.goto(QA_BASE + "/ThanhToan/DonHangCuaToi")
        overflow(customer,360,"customer history")
        page.goto(QA_BASE + "/Admin/DonHang/QuanLyDonHang")
        page.locator("#logoutForm button[type=submit]").click()
        expect(page).to_have_url(re.compile("/Account/Login"))
        assert not errors, errors
        browser.close()
    passed("Customer sees synchronized delivery/payment; history responsive; Admin logout; no JavaScript errors")
    (OUT / "browser-results.json").write_text(json.dumps({"status":"PASS","database":"isolated only","checks":checks},indent=2))


def real_snapshot():
    result = gs.snapshot()
    for table, fields in {
        "Orders": "Id,UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod",
        "OrderItems": "Id,OrderId,COALESCE(ProductId,0),ProductName,ImageUrl,UnitPrice,Quantity",
        "CartItems": "Id,UserId,ProductId,Quantity",
    }.items():
        result[table] = gs.sql(f"SELECT Id,SHA2(CONCAT_WS(CHAR(31),{fields}),256) FROM {table} ORDER BY Id").splitlines()
    return result


def baseline():
    (OUT / "baseline.json").write_text(json.dumps(real_snapshot(), indent=2))
    with open(OUT / "before-migration.sql", "wb") as backup:
        os.chmod(backup.name, 0o600)
        subprocess.run(["docker", "compose", "exec", "-T", "db", "sh", "-c",
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --no-tablespaces --set-gtid-purged=OFF greenshop'],
            cwd=ROOT, stdout=backup, check=True)
    print("PASS: Fresh real-data hashes and private migration backup saved under /tmp.", flush=True)


def preservation():
    before, after = json.loads((OUT / "baseline.json").read_text()), real_snapshot()
    for key in ("products", "categories", "users", "images", "keys", "infrastructure_source", "containers", "Orders", "OrderItems", "CartItems"):
        assert before[key] == after[key], key
    assert set(before["migrations"]).issubset(after["migrations"])
    for path, digest in before["admin_source"].items():
        if path.endswith(("AdminController.cs", "Admin/Index.cshtml", "Shared/_AdminLayout.cshtml", "Views/_ViewImports.cshtml")):
            continue
        assert after["admin_source"][path] == digest, path
    print("PASS: Real data/uploads/keys, existing migrations, Product/Category/Admin modules and other containers preserved.", flush=True)
    (OUT / "preservation-results.json").write_text(json.dumps({"status":"PASS","checks":"Real data, uploads, keys, migrations, existing modules and other containers preserved"},indent=2))


def production_checks():
    """Read-only smoke checks against the real deployed application."""
    client = gs.client()
    results = {}
    for path in ("/", "/SanPham/CuaHang", "/Account/Login", "/Account/Register"):
        code, _, body = gs.request(client, path)
        assert code == 200, (path, code)
        results[path] = code
    for path in ("/Admin/DonHang/QuanLyDonHang", "/Admin/DonHang/ChiTietDonHang/1", "/Admin/DonHang/InDonHang/1"):
        code, headers, _ = gs.request(client, path)
        assert code == 302 and "/Account/Login" in headers.get("Location", ""), path
        results[path] = "302: login required"
    try:
        response = client.open("http://localhost/", timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    assert response.code == 301 and response.headers.get("Location", "").startswith("https://"), (response.code,response.headers.get("Location"))
    assert gs.sql("SELECT COUNT(*) FROM __EFMigrationsHistory WHERE MigrationId='20261011115904_AddAdminOrderWorkflow'") == "1"
    assert "healthy" in gs.compose("ps", "web_app", "db")
    (OUT / "production-results.json").write_text(json.dumps({"status":"PASS","routes":results,"https_redirect":301,"migration":"AddAdminOrderWorkflow applied","writes":"none"},indent=2))
    print("PASS: Deployed storefront/auth routes return 200; Admin order routes require login; HTTP redirects to HTTPS; migration applied; web/database healthy. No real business-data writes.",flush=True)


def teardown():
    # Fixed project/file/env prevent affecting the real Compose project or its volumes.
    guard(qa_compose, MAIN_COMPOSE)
    qa_compose("down")
    print("PASS: Only isolated QA containers/network removed; real containers/volumes untouched.",flush=True)


def edge_checks():
    configure_qa()
    a1, a2 = admin_sessions()
    state = json.loads((OUT / "test-state.json").read_text())
    buyer = gs.client()
    gs.login(buyer, state["customer"])
    p = state["product_id"]
    stock = int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}"))
    oid = create_order(buyer, p, 1)
    assert mutate(a1, oid, "XacNhanDonHang")[0] == 302
    assert mutate(a1, oid, "CapNhatTrangThaiDonHang", {"TargetStatus":4})[0] == 302
    assert mutate(a1, oid, "HuyDonHang", {"Note":"QA processing cancellation"})[0] == 302
    assert int(qa_sql(f"SELECT StockQuantity FROM Products WHERE Id={p}")) == stock
    oid = create_order(buyer, p, 1)
    qa_sql(f"UPDATE Orders SET IsPaid=1 WHERE Id={oid}")
    assert mutate(a1, oid, "HuyDonHang", {"Note":"QA paid legacy cannot cancel"})[0] == 422
    assert qa_sql(f"SELECT Status,Version FROM Orders WHERE Id={oid}") == "0\t0"
    assert mutate(a1, oid, "CapNhatGhiChuDonHang", {"Note":"x"*1001})[0] == 400
    assert mutate(a1, oid, "CapNhatGhiChuDonHang", {"Note":"QA note v1"})[0] == 302
    assert mutate(a2, oid, "CapNhatGhiChuDonHang", {"Note":"Stale overwrite", "ExpectedVersion":0})[0] == 409
    assert qa_sql(f"SELECT AdminNote FROM Orders WHERE Id={oid}") == "QA note v1"
    # This paid legacy fixture was only for validation; keep other screenshot totals deterministic.
    qa_sql(f"UPDATE Orders SET IsPaid=0 WHERE Id={oid}")
    original_price = qa_sql(f"SELECT Price FROM Products WHERE Id={p}")
    try:
        qa_sql(f"UPDATE Products SET Price=12.34 WHERE Id={p}")
        fractional = create_order(buyer,p,3)
    finally:
        qa_sql(f"UPDATE Products SET Price={original_price} WHERE Id={p}")
    admin_body = gs.get(a1,f"/Admin/DonHang/ChiTietDonHang/{fractional}")[1]
    customer_body = gs.get(buyer,f"/ThanhToan/ChiTietDonHang/{fractional}")[1]
    assert "12,34 đ" in admin_body and "37,02 đ" in admin_body and "37,02 đ" in customer_body
    assert qa_sql(f"SELECT Total FROM Orders WHERE Id={fractional}") == "37.02"
    assert mutate(a1,fractional,"HuyDonHang",{"Note":"QA fractional amount snapshot"})[0] == 302
    print("PASS: Processing cancellation restores exact stock; paid legacy cancellation blocked; note limits and stale-note CAS enforced.",flush=True)
    print("PASS: Fractional historical amounts display exactly in Admin/Customer receipts after product price changes.",flush=True)
    (OUT / "edge-results.json").write_text(json.dumps({"status":"PASS","database":"isolated only","checks":["Processing cancellation, paid legacy guard, note length and stale-note concurrency", "Fractional historic prices/totals preserve two decimal places"]},indent=2))


if __name__ == "__main__":
    {"baseline": baseline, "prepare": prepare, "start": start, "refresh": lambda: start(False), "business": run_business, "browser": browser_checks, "edge": edge_checks, "preservation": preservation, "production": production_checks, "teardown": teardown}[sys.argv[1]]()
