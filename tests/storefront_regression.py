"""Integration checks against GreenShop only. Random, scoped fixtures are removed in finally.

Usage: python3 tests/storefront_regression.py baseline|http|browser|preservation
Set PYTHONPATH and PLAYWRIGHT_BROWSERS_PATH to an existing Playwright installation for browser.
No Admin credentials or authentication bypass are used.
"""
import concurrent.futures
import hashlib
import html
import http.cookiejar
import json
import os
import pathlib
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
from qa_support import PRIVATE
REPORTS = PRIVATE/'storefront'
REPORTS.mkdir(mode=0o700, parents=True, exist_ok=True)
BASE = "https://localhost"
RUN = "GS_STOREFRONT_" + uuid.uuid4().hex
checks = []
product_ids, category_ids, user_ids = [], [], []


def compose(*args):
    return subprocess.check_output(["docker", "compose", *args], cwd=ROOT, text=True).strip()


main_compose = compose

def sql(query):
    if not query.lstrip().upper().startswith(("SELECT ", "SHOW ")) or ";" in query:
        raise RuntimeError("Main SQL is read-only. Use the guarded isolated QA runner.")
    return main_compose("exec", "-T", "db", "sh", "-c",
                   'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B --default-character-set=utf8mb4 greenshop -e "$1"',
                   "sh", query)


main_sql = sql

def quote(value):
    return "'" + value.replace("'", "''") + "'"


def snapshot():
    queries = {
        "products": "SELECT Id,SHA2(CONCAT_WS(CHAR(31),Id,Name,Price,ImageUrl,Description,StockQuantity,COALESCE(CategoryId,0)),256) FROM Products ORDER BY Id",
        "categories": "SELECT Id,SHA2(CONCAT_WS(CHAR(31),Id,Name,Description,IsActive),256) FROM Categories ORDER BY Id",
        "users": "SELECT Id,SHA2(CONCAT_WS(CHAR(31),Id,FullName,Email,PasswordHash,Phone,Role,CreatedAt),256) FROM Users ORDER BY Id",
        "migrations": "SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId"
    }
    result = {key: sql(query).splitlines() for key, query in queries.items()}
    result["images"] = compose("exec", "-T", "web_app", "sh", "-c", "find /app/wwwroot/uploads/products -type f -exec sha256sum {} +").splitlines()
    result["keys"] = compose("exec", "-T", "web_app", "sh", "-c", "sha256sum /app/keys/*.xml").splitlines()
    result["admin_source"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (ROOT / "backend/GreenShop.Web/Areas/Admin").rglob("*") if p.is_file()}
    result["infrastructure_source"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                                      for p in ("docker-compose.yml", "nginx/default.conf", "backend/GreenShop.Web/Services/ProductImageStorage.cs")}
    result["containers"] = {service: compose("ps", "-q", service) for service in ("db", "nginx", "phpmyadmin")}
    return result


def passed(label):
    checks.append(label)
    print("PASS:", label, flush=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.nodes = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def input(self, name):
        return next(a.get("value", "") for t, a in self.nodes if t == "input" and a.get("name") == name)

    def cards(self):
        return [int(a["data-product-id"]) for _, a in self.nodes if "data-product-id" in a]


def client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                      urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
                                      urllib.request.HTTPCookieProcessor(jar))


def request(c, path, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        response = c.open(urllib.request.Request(BASE + path, data=body), timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    return response.code, dict(response.headers), response.read().decode()


def get(c, path, status=200):
    code, headers, body = request(c, path)
    assert code == status, (path, code, status)
    return Page(body), html.unescape(body), headers


def post(c, path, source, values):
    code, headers, body = request(c, path, {**values, "__RequestVerificationToken": source.input("__RequestVerificationToken")})
    return code, headers, html.unescape(body)


def register(c, destination=""):
    email, password = RUN.lower() + uuid.uuid4().hex[:8] + "@example.invalid", uuid.uuid4().hex
    page, _, _ = get(c, "/Account/Register?" + urllib.parse.urlencode({"returnUrl": destination}))
    code, headers, _ = post(c, "/Account/Register", page, {
        "FullName": RUN, "Email": email, "Phone": "0912345678", "Password": password,
        "ConfirmPassword": password, "returnUrl": destination})
    assert code == 302 and headers["Location"].startswith("/Account/Login")
    user_ids.append(int(sql("SELECT Id FROM Users WHERE Email=" + quote(email))))
    return email, password, headers["Location"]


def login(c, credentials, destination="", expected="/"):
    page, _, _ = get(c, "/Account/Login?" + urllib.parse.urlencode({"returnUrl": destination}))
    code, headers, _ = post(c, "/Account/Login", page, {
        "Email": credentials[0], "Password": credentials[1], "returnUrl": destination})
    assert code == 302 and headers["Location"] == expected, (code, headers.get("Location"), expected)
    assert "secure" in headers.get("Set-Cookie", "").lower()


def fixtures():
    for suffix, active in (("A", 1), ("B", 1), ("INACTIVE", 0), ("EMPTY", 1)):
        category_ids.append(int(sql("INSERT INTO Categories (Name,Description,IsActive) VALUES (" +
                                      quote(RUN + suffix) + ",''," + str(active) + "); SELECT LAST_INSERT_ID()")))
    image = sql("SELECT ImageUrl FROM Products ORDER BY Id LIMIT 1") or "/images/product-placeholder.svg"
    # Names/images are test fixtures only and are removed before reporting production counts.
    for index in range(17):
        category = category_ids[0] if index < 13 else category_ids[1] if index < 15 else category_ids[2] if index == 15 else None
        stock = 0 if index == 14 else 1 if index == 13 else 20
        name = RUN + f"_{index:02}" + (" cây xanh " * 10 if index == 0 else "")
        url = "/uploads/products/GS_STOREFRONT_MISSING.jpg" if index == 1 else image
        product_ids.append(int(sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity,CategoryId) VALUES (" +
                                 ",".join((quote(name), str(125000 + index * 1000), quote(url),
                                           quote("Mô tả thật của fixture <script>alert(1)</script>"), str(stock), str(category) if category else "NULL")) +
                                 "); SELECT LAST_INSERT_ID()")))


def cleanup():
    # Verify both exact IDs and the per-run marker before deleting any task-owned records.
    for user_id in user_ids:
        assert sql(f"SELECT FullName FROM Users WHERE Id={user_id}") == RUN
        sql(f"DELETE FROM OrderItems WHERE OrderId IN (SELECT Id FROM Orders WHERE UserId={user_id}); DELETE FROM Orders WHERE UserId={user_id}; DELETE FROM CartItems WHERE UserId={user_id}; DELETE FROM Users WHERE Id={user_id}")
    for product_id in product_ids:
        assert sql(f"SELECT Name FROM Products WHERE Id={product_id}").startswith(RUN)
        sql(f"DELETE FROM Products WHERE Id={product_id}")
    for category_id in category_ids:
        assert sql(f"SELECT Name FROM Categories WHERE Id={category_id}").startswith(RUN)
        sql(f"DELETE FROM Categories WHERE Id={category_id}")
    print("Scoped fixtures removed.", flush=True)


def confirm(c, product_id, quantity=1):
    page, body, _ = get(c, f"/ThanhToan/XacNhanMuaHang/{product_id}?quantity={quantity}")
    values = {"Quantity": quantity, "RecipientName": RUN, "Phone": "0912345678", "Address": "123 Đường thử nghiệm, Hà Nội",
              "ConfirmationToken": page.input("ConfirmationToken"), "QuotedPrice": page.input("QuotedPrice"),"PolicyVersion":page.input("PolicyVersion")}
    return page, values


def http_checks():
    anon, shopper, other = client(), client(), client()
    a, b, inactive, empty = category_ids
    page, body, _ = get(anon, f"/SanPham/CuaHang?categoryId={a}&sort=price-asc")
    assert page.cards() == product_ids[:12]
    page, _, _ = get(anon, f"/SanPham/CuaHang?categoryId={a}&sort=price-asc&page=2")
    assert page.cards() == [product_ids[12]]
    page, _, _ = get(anon, f"/SanPham/CuaHang?categoryId={b}")
    assert set(page.cards()) == set(product_ids[13:15])
    _, body, _ = get(anon, f"/SanPham/CuaHang?categoryId={empty}")
    assert "Chưa có sản phẩm" in body
    _, body, _ = get(anon, "/SanPham/CuaHang")
    assert RUN + "INACTIVE" not in body and RUN + "EMPTY" in body
    get(anon, f"/SanPham/CuaHang?categoryId={inactive}", 404)
    get(anon, "/SanPham/CuaHang?categoryId=2147483647", 404)
    get(anon, f"/SanPham/ChiTietSanPham/{product_ids[15]}", 404)
    get(anon, "/SanPham/ChiTietSanPham/2147483647", 404)
    get(anon, "/SanPham/CuaHang?page=0", 400)
    get(anon, "/SanPham/CuaHang?sort=invalid", 400)
    passed("Dynamic categories, correct category isolation, inactive exclusion, empty states, 404/400 and database pagination")
    page, body, _ = get(anon, "/SanPham/CuaHang?" + urllib.parse.urlencode({"search": RUN + "_16"}))
    assert page.cards() == [product_ids[16]] and "Chưa phân loại" in body
    assert "141.000 đ" in body and "Còn 20 sản phẩm" in body
    assert "Chưa có đánh giá" in body and "Chưa có dữ liệu bán" in body
    _, body, _ = get(anon, f"/SanPham/ChiTietSanPham/{product_ids[0]}")
    raw = request(anon, f"/SanPham/ChiTietSanPham/{product_ids[0]}")[2]
    assert "&lt;script&gt;" in raw and "<script>alert(1)</script>" not in raw
    passed("Search, uncategorized products, real price/stock, truthful metrics and HTML escaping")
    sql(f"UPDATE Categories SET Name={quote(RUN + 'RENAMED')} WHERE Id={empty}")
    _, body, _ = get(anon, "/SanPham/CuaHang")
    assert RUN + "RENAMED" in body
    sql(f"UPDATE Categories SET IsActive=0 WHERE Id={empty}")
    _, body, _ = get(anon, "/SanPham/CuaHang")
    assert RUN + "RENAMED" not in body
    sql(f"UPDATE Products SET Price=999000,StockQuantity=7 WHERE Id={product_ids[16]}")
    _, body, _ = get(anon, f"/SanPham/ChiTietSanPham/{product_ids[16]}")
    assert "999.000 đ" in body and "Còn 7 sản phẩm" in body
    passed("Database category edits/inactivation and product price/stock edits appear on refresh without cache")
    page, _, _ = get(anon, f"/SanPham/ChiTietSanPham/{product_ids[0]}")
    for path, quantity in ((f"/GioHang/ThemVaoGioHang/{product_ids[0]}", 1), (f"/ThanhToan/MuaNgay/{product_ids[0]}", 2)):
        code, headers, _ = post(anon, path, page, {"Quantity": quantity})
        assert code == 302 and headers["Location"].startswith("/Account/Login?")
        destination = urllib.parse.parse_qs(urllib.parse.urlparse(headers["Location"]).query)["returnUrl"][0]
        assert str(product_ids[0]) in destination and "ThemVaoGioHang" not in destination and "MuaNgay" not in destination
        if quantity == 2:
            assert "quantity=2" in destination
    assert request(anon, f"/GioHang/ThemVaoGioHang/{product_ids[0]}", {"Quantity": 1})[0] == 400
    get(anon, f"/GioHang/ThemVaoGioHang/{product_ids[0]}", 405)
    get(anon, f"/ThanhToan/MuaNgay/{product_ids[0]}", 405)
    passed("Anonymous browsing; real POST shopping gates preserve ProductId/quantity; antiforgery enforced; mutation GET returns 405")
    credentials = register(shopper, destination)
    register_page, _, _ = get(shopper, "/Account/Login?" + urllib.parse.urlencode({"returnUrl": destination}))
    assert register_page.input("returnUrl") == destination and urllib.parse.parse_qs(urllib.parse.urlparse(credentials[2]).query)["returnUrl"][0] == destination
    login(shopper, credentials, destination, destination)
    get(shopper, destination)
    assert sql(f"SELECT COUNT(*) FROM Orders WHERE UserId={user_ids[0]}") == "0"
    for unsafe in ("https://example.com/", "//example.com/", "/GioHang/ThemVaoGioHang/1", "/ThanhToan/MuaNgay/1", "/\\example.com", "/Admin/Admin/Index"):
        fresh = client()
        login(fresh, credentials, unsafe, "/")
    passed("Register/login retains safe GET destination; no order on login or GET; external and mutation ReturnUrls rejected")
    credentials_other = register(other)
    login(other, credentials_other)
    get(shopper, "/Admin/SanPham/QuanLySanPham", 302)
    _, _, headers = get(shopper, "/Admin/DanhMuc/QuanLyDanhMuc", 302)
    assert headers["Location"].startswith(BASE + "/Admin/Account/Login")
    get(shopper, "/Account/AccessDenied", 403)
    passed("Customer cannot access Admin product/category management; AccessDenied remains available")
    detail, _, _ = get(shopper, f"/SanPham/ChiTietSanPham/{product_ids[0]}")
    for quantity in (2, 3):
        code, headers, _ = post(shopper, f"/GioHang/ThemVaoGioHang/{product_ids[0]}", detail, {"Quantity": quantity, "UserId": user_ids[1]})
        assert code == 302 and headers["Location"] == "/GioHang/QuanLyGioHang"
    assert sql(f"SELECT Quantity FROM CartItems WHERE UserId={user_ids[0]} AND ProductId={product_ids[0]}") == "5"
    assert sql(f"SELECT COUNT(*) FROM CartItems WHERE UserId={user_ids[1]}") == "0"
    assert sql(f"SELECT StockQuantity FROM Products WHERE Id={product_ids[0]}") == "20"
    for bad in (0, -1, "1.5", 1000001, 21, "abc"):
        post(shopper, f"/GioHang/ThemVaoGioHang/{product_ids[0]}", detail, {"Quantity": bad})
    assert sql(f"SELECT Quantity FROM CartItems WHERE UserId={user_ids[0]} AND ProductId={product_ids[0]}") == "5"
    cart_id = int(sql(f"SELECT Id FROM CartItems WHERE UserId={user_ids[0]}"))
    cart, _, _ = get(shopper, "/GioHang/QuanLyGioHang")
    other_cart, body, _ = get(other, "/GioHang/QuanLyGioHang")
    assert "Giỏ hàng đang trống" in body
    assert post(other, f"/GioHang/CapNhatSoLuong/{cart_id}", get(other, f"/SanPham/ChiTietSanPham/{product_ids[0]}")[0], {"Quantity": 1})[0] == 404
    assert post(other, f"/GioHang/XoaKhoiGioHang/{cart_id}", get(other, f"/SanPham/ChiTietSanPham/{product_ids[0]}")[0], {})[0] == 404
    assert post(shopper, f"/GioHang/CapNhatSoLuong/{cart_id}", cart, {"Quantity": 4})[0] == 302
    fresh = client()
    login(fresh, credentials)
    _, body, _ = get(fresh, "/GioHang/QuanLyGioHang")
    assert f'data-cart-id="{cart_id}"' in body
    assert post(shopper, f"/GioHang/XoaKhoiGioHang/{cart_id}", cart, {})[0] == 302
    passed("Persistent per-user cart; duplicate adds merge; quantities validated; stock unchanged; ownership/overposting checks; update/remove")
    zero = product_ids[14]
    zero_page, _, _ = get(shopper, f"/SanPham/ChiTietSanPham/{zero}")
    post(shopper, f"/GioHang/ThemVaoGioHang/{zero}", zero_page, {"Quantity": 1})
    assert sql(f"SELECT COUNT(*) FROM CartItems WHERE ProductId={zero}") == "0"
    checkout, values = confirm(shopper, product_ids[0], 2)
    values["QuotedPrice"] = "0.01"
    code, _, body = post(shopper, f"/ThanhToan/XacNhanMuaHang/{product_ids[0]}", checkout, values)
    assert code == 200 and "Giá đã thay đổi" in body
    assert sql(f"SELECT COUNT(*) FROM Orders WHERE UserId={user_ids[0]}") == "0"
    for bad in (0, -1, 21, 1000001, "1.5"):
        checkout, values = confirm(shopper, product_ids[0])
        values["Quantity"] = bad
        assert post(shopper, f"/ThanhToan/XacNhanMuaHang/{product_ids[0]}", checkout, values)[0] == 200
    assert sql(f"SELECT COUNT(*) FROM Orders WHERE UserId={user_ids[0]}") == "0"
    checkout, values = confirm(shopper, product_ids[0], 2)
    code, headers, _ = post(shopper, f"/ThanhToan/XacNhanMuaHang/{product_ids[0]}", checkout, values)
    assert code == 302, (code, headers)
    receipt = headers["Location"]
    get(shopper, receipt)
    get(other, receipt, 404)
    assert sql(f"SELECT Total,Status,IsPaid,PaymentMethod FROM Orders WHERE UserId={user_ids[0]}") == "250000.00\t0\t0\tCOD"
    assert sql(f"SELECT StockQuantity FROM Products WHERE Id={product_ids[0]}") == "18"
    assert post(shopper, f"/ThanhToan/XacNhanMuaHang/{product_ids[0]}", checkout, values)[1]["Location"] == receipt
    assert sql(f"SELECT COUNT(*) FROM Orders WHERE UserId={user_ids[0]}") == "1"
    get(shopper, "/ThanhToan/DonHangCuaToi")
    sql(f"UPDATE Orders SET Status=1 WHERE UserId={user_ids[0]}")
    _, body, _ = get(anon, f"/SanPham/ChiTietSanPham/{product_ids[0]}")
    assert "Đã bán 2" in body
    sql(f"UPDATE Orders SET Status=2 WHERE UserId={user_ids[0]}")
    _, body, _ = get(anon, f"/SanPham/ChiTietSanPham/{product_ids[0]}")
    assert "Chưa có dữ liệu bán" in body
    passed("Server price validation, invalid quantities/out-of-stock rejection, real COD order/receipt, stock deduction, idempotent resubmission, order isolation and completed-only sold count")
    race = product_ids[13]
    attempts = [(shopper, *confirm(shopper, race)), (other, *confirm(other, race))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: post(item[0], f"/ThanhToan/XacNhanMuaHang/{race}", item[1], item[2]), attempts))
    assert sorted(r[0] for r in results) == [200, 302], [r[0] for r in results]
    assert sql(f"SELECT StockQuantity FROM Products WHERE Id={race}") == "0"
    assert sql(f"SELECT SUM(Quantity) FROM OrderItems WHERE ProductId={race}") == "1"
    passed("Concurrent buyers of the last unit: exactly one saved order, one rejection, stock remains zero")


def browser_checks():
    # Use Playwright from the documented QA environment.
    from playwright.sync_api import sync_playwright, expect
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        for width in (1440, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            for path in ("/", f"/SanPham/CuaHang?categoryId={category_ids[0]}", f"/SanPham/ChiTietSanPham/{product_ids[0]}"):
                page.goto(BASE + path)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, path,
                    page.evaluate("Array.from(document.querySelectorAll('body *')).filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0, 10).map(e => [e.tagName, e.className, e.getBoundingClientRect().width])"))
            page.screenshot(path=str(REPORTS / f"detail-{width}.png"), full_page=True)
        passed("Chromium desktop/tablet/mobile at 1440/768/390/320 px: home, catalog and long-name detail without horizontal overflow")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(BASE + f"/SanPham/CuaHang?categoryId={category_ids[0]}")
        page.screenshot(path=str(REPORTS / "catalog-desktop.png"), full_page=True)
        card = page.locator(".shop-product-card").first
        card.hover()
        page.wait_for_timeout(400)
        assert card.evaluate("element => getComputedStyle(element).transform") != "none"
        assert card.locator(".product-discover").evaluate("element => getComputedStyle(element).opacity") == "1"
        page.mouse.down()
        page.wait_for_timeout(250)
        pressed = card.evaluate("element => getComputedStyle(element).transform")
        assert pressed != "none"
        page.mouse.move(5, 5)
        page.mouse.up()
        card.locator(".product-link").focus()
        page.keyboard.press("Tab")
        page.keyboard.press("Shift+Tab")
        assert card.locator(".product-link").evaluate("element => getComputedStyle(element).outlineStyle") != "none"
        broken = page.locator(f'[data-product-id="{product_ids[1]}"] img')
        expect(broken).to_have_attribute("src", "/images/product-placeholder.svg")
        assert broken.evaluate("element => element.complete && element.naturalWidth > 0")
        page.emulate_media(reduced_motion="reduce")
        card.hover()
        assert card.evaluate("element => getComputedStyle(element).transitionDuration") == "0s"
        assert card.evaluate("element => getComputedStyle(element).transform") == "none"
        passed("Real hover/pressed transform, detail affordance, keyboard focus, broken-image fallback and reduced motion")
        page.goto(BASE + f"/SanPham/ChiTietSanPham/{product_ids[0]}")
        page.get_by_role("button", name="Tăng số lượng").click()
        expect(page.locator("#Quantity")).to_have_value("2")
        page.get_by_role("button", name="Mua ngay", exact=False).click()
        expect(page).to_have_url(__import__("re").compile(r".*/Account/Login\?returnUrl=.*"))
        expect(page.get_by_text("Vui lòng đăng nhập để tiếp tục mua sắm.")).to_be_visible()
        c = client()
        credentials = register(c)
        page.locator("#Email").fill(credentials[0])
        page.locator("input[name=Password]").fill(credentials[1])
        page.locator("form button[type=submit]").click()
        expect(page.locator(".checkout-form")).to_be_visible()
        assert page.locator("#Quantity").input_value() == "2"
        expect(page.locator("[data-checkout-quantity]")).to_have_text("2")
        page.locator("#Quantity").fill("3")
        expect(page.locator("[data-checkout-quantity]")).to_have_text("3")
        page.locator("#Address").fill("123 Đường thử nghiệm, Hà Nội")
        page.locator(".checkout-form button[type=submit]").click()
        expect(page.locator(".order-items")).to_be_visible()
        assert "Chờ xử lý" in page.locator(".shop-page-heading").inner_text()
        page.screenshot(path=str(REPORTS / "cod-receipt.png"), full_page=True)
        page.goto(BASE + f"/SanPham/ChiTietSanPham/{product_ids[0]}")
        page.get_by_role("button", name="Thêm vào giỏ hàng", exact=True).click()
        expect(page.locator(".cart-row")).to_have_count(1)
        page.get_by_role("button", name="Mở menu tài khoản").click()
        expect(page.get_by_role("link", name="Đơn hàng của tôi", exact=True)).to_be_visible()
        page.screenshot(path=str(REPORTS / "cart-desktop.png"), full_page=True)
        for width in (768, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            for path in ("/GioHang/QuanLyGioHang", f"/ThanhToan/XacNhanMuaHang/{product_ids[0]}", "/ThanhToan/DonHangCuaToi"):
                page.goto(BASE + path)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, path,
                    page.evaluate("Array.from(document.querySelectorAll('body *')).filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0, 10).map(e => [e.tagName, e.className, e.getBoundingClientRect().width])"))
        assert not errors, errors
        passed("Browser Buy Now/login/COD confirmation/receipt and add-to-cart/account menu; checkout/cart/orders responsive; zero JavaScript errors")
        browser.close()


def main():
    mode = sys.argv[1]
    baseline_path = REPORTS / "preservation-baseline.json"
    if mode == "baseline":
        baseline_path.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2))
        print("Preservation baseline saved (hashes only).")
        return
    if mode == "preservation":
        before, after = json.loads(baseline_path.read_text()), snapshot()
        for key in ("products", "categories", "users", "images", "keys", "admin_source", "infrastructure_source", "containers"):
            assert before[key] == after[key], key
        assert set(before["migrations"]).issubset(after["migrations"])
        passed("Original products/categories/users, upload hashes, Data Protection keys, Admin/upload/infrastructure source and other containers unchanged; previous migrations retained")
    else:
        try:
            fixtures()
            (http_checks if mode == "http" else browser_checks)()
        finally:
            cleanup()
    (REPORTS / (mode + "-results.json")).write_text(json.dumps({"status": "PASS", "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
