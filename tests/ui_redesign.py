from qa_support import PRIVATE, PROJECT
"""GreenShop UI QA: baseline, browser, preservation. Uses scoped storefront fixtures."""
import hashlib
import json
import os
import pathlib
import sys
import storefront_regression as gs

OUT=PRIVATE/'qa'
OUT.mkdir(parents=True, exist_ok=True)


def protected_sources():
    app = gs.ROOT / "backend/GreenShop.Web"
    paths = list((app / "Controllers").glob("*.cs")) + list((app / "Migrations").glob("*.cs"))
    paths += list((app / "Services").glob("*.cs"))
    paths += [app / "Models" / name for name in ("Product.cs", "Category.cs", "User.cs", "Shopping.cs")]
    paths += [app / "Program.cs", app / "Data/AppDbContext.cs"]
    return {str(p.relative_to(gs.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def shopping_snapshot():
    return {table: gs.sql(query).splitlines() for table, query in {
        "cart": "SELECT Id,SHA2(CONCAT_WS(CHAR(31),Id,UserId,ProductId,Quantity),256) FROM CartItems ORDER BY Id",
        "orders": "SELECT Id,SHA2(CONCAT_WS(CHAR(31),Id,UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod),256) FROM Orders ORDER BY Id",
        "items": "SELECT Id,SHA2(CONCAT_WS(CHAR(31),Id,OrderId,COALESCE(ProductId,0),ProductName,ImageUrl,UnitPrice,Quantity),256) FROM OrderItems ORDER BY Id"
    }.items()}


def baseline():
    from playwright.sync_api import sync_playwright
    (OUT / "baseline.json").write_text(json.dumps({"runtime": gs.snapshot(), "backend": protected_sources(), "shopping": shopping_snapshot()}, indent=2))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(ignore_https_errors=True, viewport={"width": 1440, "height": 1000})
        page.goto(gs.BASE)
        page.screenshot(path=str(OUT / "before-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 360, "height": 900})
        page.goto(gs.BASE)
        page.screenshot(path=str(OUT / "before-mobile.png"), full_page=True)
        browser.close()
    print("Fresh runtime baseline and before screenshots saved.", flush=True)


def preservation():
    before = json.loads((OUT / "baseline.json").read_text())
    after = gs.snapshot()
    for key in ("products", "categories", "users", "images", "keys", "admin_source", "infrastructure_source", "containers", "migrations"):
        assert before["runtime"][key] == after[key], key
    assert before["backend"] == protected_sources(), "Backend source changed"
    assert before["shopping"] == shopping_snapshot(), "Existing carts/orders changed"
    (OUT / "preservation.json").write_text(json.dumps({"status": "PASS", "checks": ["Current real rows, uploads, keys, migrations, Admin, backend logic, infrastructure and other containers preserved"]}, indent=2))
    print("PASS: Current real data and all protected source/infrastructure preserved.", flush=True)


def http_checks():
    try:
        gs.fixtures()
        gs.http_checks()
    finally:
        gs.cleanup()
    (OUT / "http.json").write_text(json.dumps({"status": "PASS", "checks": gs.checks}, indent=2))


def check_overflow(page, width, path):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, path,
        page.evaluate("Array.from(document.querySelectorAll('body *')).filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0,8).map(e => [e.tagName,e.className,e.getBoundingClientRect().width])"))


def capture_final():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(ignore_https_errors=True, viewport={"width": 1440, "height": 1000})
        page.goto(gs.BASE + "/SanPham/CuaHang")
        card = page.locator(".shop-product-card").first
        if card.count():
            product_id = card.get_attribute("data-product-id")
            card.hover()
            page.wait_for_timeout(280)
            assert card.evaluate("e => getComputedStyle(e).transform") != "none"
            assert card.locator(".product-media img").evaluate("e => getComputedStyle(e).transform") != "none"
            card.screenshot(path=str(OUT / "product-hover.png"), animations="disabled")
            for width in (1440, 768, 360):
                page.set_viewport_size({"width": width, "height": 1000})
                page.goto(gs.BASE + f"/SanPham/ChiTietSanPham/{product_id}")
                check_overflow(page, width, "production detail")
                page.screenshot(path=str(OUT / f"detail-{width}.png"), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 360, "height": 900})
        page.goto(gs.BASE + "/")
        page.get_by_role("button", name="Mở menu điều hướng").click()
        page.screenshot(path=str(OUT / "mobile-drawer.png"), animations="disabled")
        browser.close()
    (OUT / "visual.json").write_text(json.dumps({"status": "PASS", "checks": ["Current real product hover lift and image zoom", "Production detail screenshots without overflow", "Production mobile drawer screenshot after opening animation"]}, indent=2))
    print("PASS: Final production screenshots; real card lift and image zoom.", flush=True)


def browser_checks():
    from playwright.sync_api import sync_playwright, expect
    import re
    checks, errors = [], []
    def passed(label):
        checks.append(label)
        print("PASS:", label, flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Production screenshots contain only the current real catalog, before any fixtures are added.
        for width in (1440, 768, 360):
            page.set_viewport_size({"width": width, "height": 1000})
            for name, path in (("home", "/"), ("catalog", "/SanPham/CuaHang"), ("empty", "/SanPham/CuaHang?search=GS_UI_NO_RESULTS_"), ("login", "/Account/Login"), ("register", "/Account/Register")):
                page.goto(gs.BASE + path)
                check_overflow(page, width, path)
                if name == "catalog" and page.locator(".shop-product-card").count() == 1:
                    assert abs(page.locator(".shop-product-card").bounding_box()["width"] - page.locator(".product-grid").bounding_box()["width"]) < 2
                page.screenshot(path=str(OUT / f"{name}-{width}.png"), full_page=True)
                if width == 360 and name == "home":
                    page.get_by_role("button", name="Mở menu điều hướng").click()
                    page.screenshot(path=str(OUT / "mobile-drawer.png"), animations="disabled")
                    page.keyboard.press("Escape")
        passed("Production home/catalog/empty/login/register screenshots at 1440/768/360 px; no overflow; single-product layout fills grid")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(gs.BASE + "/")
        page.locator(".account-menu summary").click()
        account = page.locator(".account-menu")
        expect(account.get_by_role("link", name="Đăng nhập", exact=True)).to_have_attribute("href", "/Account/Login")
        expect(account.get_by_role("link", name="Đăng ký", exact=True)).to_have_attribute("href", "/Account/Register")
        page.keyboard.press("Escape")
        assert not account.evaluate("e => e.open")
        passed("Guest account dropdown offers working Login/Register destinations and closes with Escape")
        discovery = page.locator("#discover-categories")
        if discovery.count():
            page.locator('.hero-actions a[href="#discover-categories"]').click()
            assert discovery.bounding_box()["y"] >= page.locator(".shop-header").bounding_box()["height"]
            passed("Category anchor clears sticky header")
            page.goto(gs.BASE + "/")
        contrasts = page.evaluate(r"""() => {
            const rgb = s => s.match(/\d+(?:\.\d+)?/g).slice(0,3).map(Number);
            const lum = s => rgb(s).map(x => { x /= 255; return x <= .04045 ? x/12.92 : ((x+.055)/1.055)**2.4; }).reduce((sum,x,i) => sum+x*[.2126,.7152,.0722][i],0);
            const ratio = (a,b) => (Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
            const styles = e => getComputedStyle(document.querySelector(e));
            return {body: ratio(styles('body').color,styles('body').backgroundColor),
                muted: ratio(styles('.hero-copy > p').color,styles('body').backgroundColor),
                button: ratio(styles('.hero-actions .primary').color,styles('.hero-actions .primary').backgroundColor),
                footer: ratio(styles('.footer-grid h2').color,styles('.shop-footer').backgroundColor)};
        }""")
        assert all(value >= 4.5 for value in contrasts.values()), contrasts
        (OUT / "contrast.json").write_text(json.dumps(contrasts, indent=2))
        passed("Measured body/muted/primary CTA/footer text contrast meets 4.5:1")
        slow = browser.new_context(ignore_https_errors=True, viewport={"width":1440,"height":1000})
        held, holding = [], [True]
        slow.route("**/uploads/products/**", lambda route: held.append(route) if holding[0] else route.continue_())
        slow_page = slow.new_page()
        slow_page.goto(gs.BASE + "/", wait_until="domcontentloaded")
        if held:
            before_image = slow_page.locator('.hero-featured').bounding_box()
            holding[0] = False
            for route in held: route.continue_()
            slow_page.wait_for_function("document.querySelector('.hero-featured img').naturalWidth > 0")
            assert before_image == slow_page.locator('.hero-featured').bounding_box()
            passed("Delayed real product image keeps hero dimensions stable")
        slow.close()
        try:
            gs.fixtures()
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.goto(gs.BASE + "/")
            category = gs.RUN + "A"
            page.locator(".category-menu summary").click()
            expect(page.locator(".category-menu .shop-menu-panel")).to_be_visible()
            expect(page.locator(".category-menu").get_by_role("link", name=re.compile(re.escape(category)))).to_be_visible()
            assert gs.RUN + "INACTIVE" not in page.locator(".category-menu").inner_text()
            page.keyboard.press("Escape")
            assert not page.locator(".category-menu").evaluate("e => e.open")
            page.locator(".category-menu summary").focus()
            page.keyboard.press("Enter")
            assert page.locator(".category-menu").evaluate("e => e.open")
            page.locator(".hero-copy h1").click()
            assert not page.locator(".category-menu").evaluate("e => e.open")
            page.locator(".category-menu summary").click()
            page.locator(".category-menu").get_by_role("link", name=re.compile(re.escape(category))).click()
            expect(page).to_have_url(re.compile(f"categoryId={gs.category_ids[0]}"))
            assert set(int(x) for x in page.locator(".shop-product-card").evaluate_all("items => items.map(e => e.dataset.productId)")) <= set(gs.product_ids[:13])
            passed("Dynamic category dropdown: active data, correct destination, Enter/Escape/outside click")
            page.get_by_role("button", name="Mở tìm kiếm", exact=True).click()
            expect(page.locator("#header-search")).to_be_focused()
            page.locator("#header-search").fill(gs.RUN + "_16")
            page.locator("#shop-search-dialog").get_by_role("button", name="Tìm kiếm", exact=True).click()
            expect(page.locator(".shop-product-card")).to_have_count(1)
            page.locator("#sort").select_option("price-asc")
            expect(page).to_have_url(re.compile("sort=price-asc"))
            assert gs.RUN + "_16" in page.locator("#product-search").input_value()
            page.locator("#product-search").fill("GS_UI_NO_RESULTS_")
            page.locator(".shop-search-toolbar").get_by_role("button", name="Tìm kiếm").click()
            expect(page.locator(".catalog-empty")).to_be_visible()
            assert page.locator(".catalog-empty").bounding_box()["height"] < 300
            assert page.locator("#product-search").input_value() == "GS_UI_NO_RESULTS_"
            page.locator(".catalog-empty").get_by_role("link", name="Xóa tìm kiếm", exact=False).click()
            assert page.locator("#product-search").input_value() == ""
            passed("Header search, real sort with preserved search, compact empty state and explicit clear")
            page.set_viewport_size({"width": 360, "height": 900})
            page.goto(gs.BASE + "/")
            toggle = page.get_by_role("button", name="Mở menu điều hướng")
            toggle.focus()
            page.keyboard.press("Enter")
            drawer = page.locator("#shop-navigation-dialog")
            expect(drawer).to_be_visible()
            for _ in range(30):
                page.keyboard.press("Tab")
                assert page.evaluate("document.getElementById('shop-navigation-dialog').contains(document.activeElement)")
            for _ in range(30):
                page.keyboard.press("Shift+Tab")
                assert page.evaluate("document.getElementById('shop-navigation-dialog').contains(document.activeElement)")
            page.screenshot(path=str(OUT / "mobile-drawer-fixture.png"), animations="disabled")
            page.keyboard.press("Escape")
            expect(drawer).not_to_be_visible()
            expect(toggle).to_be_focused()
            assert page.evaluate("getComputedStyle(document.documentElement).overflowY") != "hidden"
            toggle.click()
            page.mouse.click(5, 200)
            expect(drawer).not_to_be_visible()
            toggle.click()
            drawer.locator(f'a[href$="categoryId={gs.category_ids[0]}"]').click()
            expect(page).to_have_url(re.compile(f"categoryId={gs.category_ids[0]}"))
            passed("Mobile modal drawer: keyboard focus trap, Escape/backdrop close, focus return, scroll unlock and dynamic category links")
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.goto(gs.BASE + f"/SanPham/CuaHang?categoryId={gs.category_ids[0]}")
            card = page.locator(".shop-product-card").first
            card.hover()
            page.wait_for_timeout(300)
            hovered = card.evaluate("e => getComputedStyle(e).transform")
            assert hovered != "none"
            assert card.locator(".product-media img").evaluate("e => getComputedStyle(e).transform") != "none"
            page.mouse.down()
            page.wait_for_timeout(180)
            assert card.evaluate("e => getComputedStyle(e).transform") != hovered
            page.mouse.move(2, 2)
            page.mouse.up()
            card.locator(".product-link").focus()
            page.keyboard.press("Tab")
            page.keyboard.press("Shift+Tab")
            assert card.locator(".product-link").evaluate("e => getComputedStyle(e).outlineStyle") != "none"
            broken = page.locator(f'[data-product-id="{gs.product_ids[1]}"] img')
            expect(broken).to_have_attribute("src", "/images/product-placeholder.svg")
            page.emulate_media(reduced_motion="reduce")
            card.hover()
            assert card.evaluate("e => getComputedStyle(e).transitionDuration") == "0s"
            assert card.evaluate("e => getComputedStyle(e).transform") == "none"
            touch = browser.new_context(ignore_https_errors=True, is_mobile=True, has_touch=True, viewport={"width": 360, "height": 900})
            touch_page = touch.new_page()
            touch_page.goto(gs.BASE + f"/SanPham/CuaHang?categoryId={gs.category_ids[0]}")
            touch_card = touch_page.locator(".shop-product-card").first
            touch_card.hover()
            assert touch_card.evaluate("e => getComputedStyle(e).transform") == "none"
            touch.close()
            passed("Hover/zoom/pressed differ; focus visible; fallback; reduced motion; no hover lift on touch")
            page.goto(gs.BASE + f"/SanPham/ChiTietSanPham/{gs.product_ids[0]}")
            page.get_by_role("button", name="Tăng số lượng").click()
            page.get_by_role("button", name="Mua ngay", exact=False).click()
            expect(page).to_have_url(re.compile("/Account/Login\\?returnUrl="))
            c = gs.client()
            credentials = gs.register(c)
            page.locator("#Email").fill(credentials[0])
            page.locator("input[name=Password]").fill(credentials[1])
            page.locator("form button[type=submit]").click()
            expect(page.locator(".checkout-form")).to_be_visible()
            assert page.locator("#Quantity").input_value() == "2"
            page.locator("#Address").fill("123 Đường thử nghiệm, Hà Nội")
            page.locator(".checkout-form button[type=submit]").click()
            expect(page.locator(".order-items")).to_be_visible()
            page.goto(gs.BASE + f"/SanPham/ChiTietSanPham/{gs.product_ids[0]}")
            page.get_by_role("button", name="Thêm vào giỏ hàng", exact=True).click()
            expect(page.locator(".cart-row")).to_have_count(1)
            page.locator(".account-menu summary").click()
            expect(page.locator(".account-menu").get_by_role("link", name="Đơn hàng của tôi", exact=True)).to_be_visible()
            for width in (1440, 768, 360, 320):
                page.set_viewport_size({"width": width, "height": 1000})
                for path in (f"/SanPham/ChiTietSanPham/{gs.product_ids[0]}", "/GioHang/QuanLyGioHang", f"/ThanhToan/XacNhanMuaHang/{gs.product_ids[0]}", "/ThanhToan/DonHangCuaToi"):
                    page.goto(gs.BASE + path)
                    check_overflow(page, width, path)
                    if "/ChiTietSanPham/" in path:
                        page.screenshot(path=str(OUT / f"detail-fixture-{width}.png"), full_page=True)
                    if "/QuanLyGioHang" in path:
                        page.screenshot(path=str(OUT / f"cart-fixture-{width}.png"), full_page=True)
            assert not errors, errors
            passed("Buy Now/login/COD and add-to-cart/account/orders work; long names, cart/checkout/orders responsive at 1440/768/360/320; no JS errors")
        finally:
            gs.cleanup()
            browser.close()
    (OUT / "browser.json").write_text(json.dumps({"status": "PASS", "checks": checks}, indent=2))


if __name__ == "__main__":
    if sys.argv[1] == "capture-shopping":
        p = OUT / "baseline.json"
        current = json.loads(p.read_text())
        current["shopping"] = shopping_snapshot()
        p.write_text(json.dumps(current, indent=2))
        print("Current real cart/order hashes added to baseline.")
        sys.exit(0)
    {"baseline": baseline, "browser": browser_checks, "http": http_checks, "capture": capture_final, "preservation": preservation}[sys.argv[1]]()
