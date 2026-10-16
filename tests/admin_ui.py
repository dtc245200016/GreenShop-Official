from qa_support import PRIVATE, PROJECT
"""Shared Admin appearance and regressions on a disposable Compose project."""
import sys,os,json,hashlib,subprocess,re
from pathlib import Path
import dashboard_management as dm
import user_management as us
import order_management as om
import storefront_regression as gs

OUT=PRIVATE/'qa';OUT.mkdir(mode=0o700,exist_ok=True)
dm.OUT=us.OUT=om.OUT=OUT;om.QA_PROJECT=PROJECT

def prepare():
    om.prepare()
    for name in ('keys','images'):(OUT/name).mkdir(mode=0o700,exist_ok=True)
    file=OUT/'compose.yaml';s=file.read_text().replace('    environment:\n      ASPNETCORE_ENVIRONMENT: Production',f'    volumes:\n      - {OUT}/keys:/app/keys\n      - {OUT}/images:/app/wwwroot/uploads/products\n    environment:\n      ASPNETCORE_ENVIRONMENT: Production');file.write_text(s)

def preservation():
    before=json.loads((OUT/'baseline.json').read_text());after=om.real_snapshot()
    for key in ('products','categories','users','images','keys','infrastructure_source','containers','Orders','OrderItems','CartItems','migrations'):assert before[key]==after[key],key
    assert before['extra']==dm.extra_snapshot()
    for name,digest in before['admin_source'].items():
        if not name.endswith('Shared/_AdminLayout.cshtml'):assert after['admin_source'][name]==digest,name
    for name,digest in before['business_sources'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    (OUT/'preservation-results.json').write_text(json.dumps({'status':'PASS','checks':'Every controller/model/service/context/migration source unchanged; real users/order/history/stock/cart/data/images/keys/infrastructure preserved'}))
    print('PASS: All business source and real data/keys/images/migrations/containers preserved.',flush=True)

def browser():
    om.configure_qa()
    from playwright.sync_api import sync_playwright,expect
    account=json.loads((OUT/'accounts.json').read_text())[0];checks=[]
    def passed(s):checks.append(s);print('PASS: '+s,flush=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(om.QA_BASE+'/Admin/Account/Login');page.locator('#Email').fill(account[0]);page.locator('[name=Password]').fill(account[1]);page.locator('form:has(#Email) button[type=submit]').click();expect(page).to_have_url(om.QA_BASE+dm.BASE)
        admin=om.admin_sessions()[0]
        category=om.qa_sql("SELECT Id FROM Categories WHERE Name='UI Modal QA'")
        if not category:
            form=gs.get(admin,'/Admin/DanhMuc/ThemDanhMuc')[0]
            assert gs.post(admin,'/Admin/DanhMuc/ThemDanhMuc',form,{'Name':'UI Modal QA','Description':'Synthetic UI fixture','IsActive':'true'})[0]==302
            category=om.qa_sql("SELECT Id FROM Categories WHERE Name='UI Modal QA'")
        pages=[('dashboard',dm.BASE),('products','/Admin/SanPham/QuanLySanPham'),('product-create','/Admin/SanPham/ThemSanPham'),('product-edit','/Admin/SanPham/SuaSanPham/1'),('product-detail','/Admin/SanPham/ChiTietSanPham/1'),('product-delete','/Admin/SanPham/XoaSanPham/1'),('categories','/Admin/DanhMuc/QuanLyDanhMuc'),('category-create','/Admin/DanhMuc/ThemDanhMuc'),('users','/Admin/NguoiDung/QuanLyNguoiDung'),('user-detail','/Admin/NguoiDung/ChiTietNguoiDung/3'),('orders','/Admin/DonHang/QuanLyDonHang'),('order-detail','/Admin/DonHang/ChiTietDonHang/1')]
        pages.extend((label,'/Admin/DanhMuc/'+action+'/'+category) for label,action in [('category-detail','ChiTietDanhMuc'),('category-edit','SuaDanhMuc'),('category-delete','XoaDanhMuc')])
        page.add_init_script("document.addEventListener('animationstart',e=>{if(e.animationName==='admin-page-enter')window.__adminEntrance=(window.__adminEntrance||0)+1},true)")
        for width in (1440,768,360):
            page.set_viewport_size({'width':width,'height':1000})
            for label,path in pages:
                response=page.goto(om.QA_BASE+path);assert response.status==200,(label,response.status)
                page.evaluate('document.fonts.ready');page.wait_for_function("getComputedStyle(document.querySelector('.admin-page-content')).opacity==='1'")
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,label,page.evaluate("[...document.querySelectorAll('.admin-main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,5).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width])"))
                assert 'Be Vietnam Pro' in page.locator('.admin-main').evaluate('e=>getComputedStyle(e).fontFamily')
                assert page.evaluate("document.fonts.check('400 14px \"Be Vietnam Pro\"','Quản lý Người dùng Đơn hàng')")
                assert page.evaluate('window.__adminEntrance')==1
                assert not re.search(r'@(if|foreach|Model)',page.locator('.admin-main').inner_text())
                page.screenshot(path=str(OUT/f'admin-{label}-{width}.png'),full_page=True,animations='disabled')
                if label in ('dashboard','products','users'):page.screenshot(path=str(OUT/f'admin-{label}-viewport-{width}.png'),animations='disabled')
            passed(f'{width}px: all five modules and product forms/detail/delete render; local Vietnamese font loaded; entrance animation; no page overflow')
        page.set_viewport_size({'width':1440,'height':1000});page.goto(om.QA_BASE+dm.BASE);page.evaluate('document.fonts.ready')
        page.reload();page.wait_for_function("getComputedStyle(document.querySelector('.admin-page-content')).opacity==='1'");assert page.evaluate('window.__adminEntrance')==1
        button=page.get_by_role('button',name='Áp dụng');normal=button.evaluate('e=>getComputedStyle(e).boxShadow');button.hover();page.wait_for_timeout(220);assert button.evaluate('e=>getComputedStyle(e).boxShadow')!=normal
        box=button.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();expect(button).to_have_class(re.compile('admin-pressed'));page.wait_for_timeout(140);assert button.evaluate('e=>getComputedStyle(e).transform')!='none';page.mouse.move(10,90);page.mouse.up()
        page.locator('#dashRange').focus();page.keyboard.press('Tab');expect(button).to_be_focused();assert button.evaluate('e=>getComputedStyle(e).outlineStyle')=='solid'
        page.emulate_media(reduced_motion='reduce');page.reload();assert page.locator('.admin-page-content').evaluate('e=>getComputedStyle(e).animationName')=='none';assert button.evaluate('e=>getComputedStyle(e).transitionDuration')=='0s';expect(page.locator('h1')).to_be_visible()
        page.emulate_media(reduced_motion='no-preference')
        passed('Reload entrance, real hover/press feedback and keyboard focus; reduced motion removes animation and keeps content visible')
        page.goto(om.QA_BASE+'/Admin/DanhMuc/QuanLyDanhMuc');page.locator('[data-confirm-status]').first.click();modal=page.locator('#categoryConfirmModal');expect(modal).to_be_visible()
        page.wait_for_function("getComputedStyle(document.querySelector('#categoryConfirmModal .modal-dialog')).transform==='none'")
        bounds=page.locator('#categoryConfirmModal .modal-dialog').bounding_box();assert bounds['y']>=0 and bounds['y']+bounds['height']<=1000
        assert modal.get_by_role('button',name='Hủy',exact=True).evaluate("e=>{const b=e.getBoundingClientRect();return e.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2))}")
        page.screenshot(path=str(OUT/'admin-category-modal.png'),animations='disabled');page.keyboard.press('Escape');expect(modal).not_to_be_visible()
        passed('Existing Bootstrap confirmation modal stays inside the viewport and Escape closes it')
        page.set_viewport_size({'width':360,'height':800});page.goto(om.QA_BASE+dm.BASE);toggle=page.locator('#adminSidebarToggle');toggle.click();expect(toggle).to_have_attribute('aria-expanded','true');page.locator('#adminSidebarOverlay').click();expect(toggle).to_have_attribute('aria-expanded','false')
        page.goto(om.QA_BASE+'/Admin/DonHang/InDonHang/1');page.emulate_media(media='print');expect(page.locator('.admin-topbar')).not_to_be_visible();expect(page.locator('.order-action-panel')).not_to_be_visible();expect(page.locator('.order-purchased-items')).to_be_visible();assert page.locator('.admin-page-content').evaluate('e=>getComputedStyle(e).opacity')=='1';page.pdf(path=str(OUT/'admin-print.pdf'));page.emulate_media(media='screen')
        passed('Mobile menu works and existing printable receipt keeps content visible while hiding chrome/actions')
        assert not errors,errors;context.close();browser.close()
    (OUT/'ui-browser-results.json').write_text(json.dumps({'status':'PASS','checks':checks},indent=2))

def production():
    dm.production()
    client=gs.client()
    for path in ('/css/admin-fonts.css','/css/admin-theme.css','/js/admin-theme.js'):
        code,_,body=gs.request(client,path);assert code==200 and len(body)>100
    req=gs.BASE+'/fonts/be-vietnam-pro/be-vietnam-pro-400-vietnamese.woff2'
    response=client.open(req,timeout=30);assert response.code==200 and response.read(4)==b'wOF2'
    print('PASS: Production shared theme assets and local Vietnamese font serve 200.',flush=True)


def typography(override=False,phase='all'):
    """Verify real Vietnamese text, forms and icons across all shared layouts in QA."""
    import portal_sessions as ps
    from playwright.sync_api import expect
    if gs.compose!=om.qa_compose:om.configure_qa()
    assert om.qa_sql('SELECT DATABASE()')=='greenshop_order_qa'
    accounts=json.loads((OUT/'accounts.json').read_text());checks=[]
    category=om.qa_sql('SELECT Id FROM Categories ORDER BY Id LIMIT 1')
    if not category:
        category=om.qa_sql("INSERT INTO Categories (Name,Description,IsActive) VALUES ('QA Readable Category','QA type fixture',1); SELECT LAST_INSERT_ID()")
    product=om.qa_sql('SELECT Id FROM Products ORDER BY Id LIMIT 1')
    conversation=om.qa_sql('SELECT Id FROM ShopConversations WHERE CustomerId=3 LIMIT 1')
    admin_paths=[dm.BASE,'/Admin/SanPham/QuanLySanPham','/Admin/SanPham/ThemSanPham',
        *('/Admin/SanPham/'+a+'/'+product for a in ('SuaSanPham','ChiTietSanPham','XoaSanPham')),
        '/Admin/DanhMuc/QuanLyDanhMuc','/Admin/DanhMuc/ThemDanhMuc',
        *('/Admin/DanhMuc/'+a+'/'+category for a in ('ChiTietDanhMuc','SuaDanhMuc','XoaDanhMuc')),
        '/Admin/NguoiDung/QuanLyNguoiDung','/Admin/NguoiDung/ChiTietNguoiDung/3',
        '/Admin/DonHang/QuanLyDonHang','/Admin/DonHang/ChiTietDonHang/1',
        '/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen',
        '/Admin/KhachHang/Slider','/Admin/KhachHang/TinNhan','/Admin/KhachHang/DanhGia']
    if conversation:admin_paths.append('/Admin/KhachHang/TroChuyen/'+conversation)
    if phase=='dashboard':admin_paths=[dm.BASE]
    with ps.playwright() as pw:
        browser=pw.chromium.launch();errors=[];missing=[]
        def watch(page):
            if override:
                page.route(re.compile(re.escape(om.QA_BASE)+r'/css/[^/?]+\.css(?:\?.*)?$'),lambda route:route.fulfill(content_type='text/css',body=(gs.ROOT/'backend/GreenShop.Web/wwwroot/css'/route.request.url.split('/css/')[-1].split('?')[0]).read_text()))
                page.route(re.compile(re.escape(om.QA_BASE)+r'/js/admin-dashboard\.js(?:\?.*)?$'),lambda route:route.fulfill(content_type='application/javascript',body=(gs.ROOT/'backend/GreenShop.Web/wwwroot/js/admin-dashboard.js').read_text()))
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('response',lambda r:missing.append((r.status,r.url)) if r.request.resource_type in ('stylesheet','script','font') and r.status>=400 else None)
        context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});page=context.new_page();watch(page);ps.login_page(page,accounts[0],ps.ADMIN_LOGIN)
        def verify(path,width,admin=False):
            response=page.goto(om.QA_BASE+path,wait_until='networkidle');assert response.status==(403 if path.endswith('/AccessDenied') else 200),(width,path,response.status)
            page.evaluate('document.fonts.ready');page.wait_for_timeout(350)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path,'page overflow')
            assert 'Be Vietnam Pro' in page.locator('body').evaluate('e=>getComputedStyle(e).fontFamily')
            assert page.evaluate("document.fonts.check('400 16px \"Be Vietnam Pro\"','Đơn hàng Người dùng Chọn file')")
            assert float(page.locator('body').evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'))>=16
            # Inspect actual rendered text, excluding decorative marks and notification counters.
            failures=page.evaluate("""()=>{
                const root=document.querySelector('main'),walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),bad=[];
                while(walker.nextNode()){
                    const n=walker.currentNode,e=n.parentElement;
                    if(!n.textContent.trim()||!e||e.closest('script,style,.visually-hidden,[hidden],[inert],.hero-stamp,.hero-visual-label,.hero-caption small,.shop-eyebrow,.shop-alert-badge,.product-add-label'))continue;
                    const s=getComputedStyle(e);if(!e.getClientRects().length||s.visibility==='hidden')continue;
                    if(!s.fontFamily.includes('Be Vietnam Pro')||parseFloat(s.fontSize)<14)bad.push([e.tagName,e.className,n.textContent.trim().slice(0,40),s.fontFamily,s.fontSize]);
                }return bad.slice(0,12)
            }""")
            assert not failures,(width,path,failures)
            for input in page.locator('main input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]),main select,main textarea').all():
                if input.is_visible():assert float(input.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'))>=16,(width,path,'input too small')
            icon=page.locator('.fa-solid,.fa-regular').first
            if icon.count():assert 'Font Awesome' in icon.evaluate('e=>getComputedStyle(e).fontFamily')
            if admin:
                if path==dm.BASE:
                    if width<=575:
                        assert page.locator('.dash-kpis').evaluate('e=>getComputedStyle(e).gridTemplateColumns.split(" ").length')==1
                        assert page.locator('.dash-value').evaluate_all('(values)=>values.every(e=>{const range=document.createRange();range.selectNodeContents(e);return range.getClientRects().length===1})'),(width,'KPI number split over lines')
                    ticks=page.locator('.dash-axis:visible')
                    assert ticks.count()>=2
                    assert ticks.evaluate_all('(ticks)=>ticks.every(t=>parseFloat(getComputedStyle(t).fontSize)*t.getScreenCTM().a>=13.9)')
                    bar=page.locator('.dash-bar').first;bar.focus();bar.press('Enter');expect(bar).to_have_attribute('aria-pressed','true');expect(page.locator('[data-chart-selection]')).to_contain_text(bar.get_attribute('data-label'))
                    bar.press('Escape');expect(bar).to_have_attribute('aria-pressed','false')
                assert float(page.locator('.admin-sidebar .nav-link').first.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'))>=15
                for button in page.locator('.admin-topbar button,.admin-topbar a').all():
                    if button.is_visible():
                        b=button.bounding_box();assert b['x']>=-1 and b['x']+b['width']<=width+1,(width,path,'clipped header control')
        for width in (() if phase=='auth' else (1440,768,390,320)):
            page.set_viewport_size({'width':width,'height':1000})
            for path in admin_paths:verify(path,width,True)
            page.goto(om.QA_BASE+dm.BASE,wait_until='networkidle');page.screenshot(path=str(OUT/f'typography-admin-{width}.png'),animations='disabled',full_page=True)
            checks.append(f'Admin {width}px: {len(admin_paths)} pages, fonts/inputs/table text/icons/assets/overflow')
            print('PASS: '+checks[-1],flush=True)
        context.close();context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});page=context.new_page();watch(page);ps.login_page(page,accounts[2])
        paths=['/','/SanPham/CuaHang','/SanPham/ChiTietSanPham/'+product,'/GioHang/QuanLyGioHang','/ThanhToan/DonHangCuaToi','/ThanhToan/ChiTietDonHang/1','/TuongTac/TroChuyen']
        item=om.qa_sql('SELECT i.Id FROM OrderItems i JOIN Orders o ON o.Id=i.OrderId WHERE o.UserId=3 AND o.Status=1 AND i.ProductId IS NOT NULL AND NOT EXISTS(SELECT 1 FROM ProductReviews r WHERE r.OrderItemId=i.Id) LIMIT 1')
        if item:paths.append('/TuongTac/DanhGia/'+item)
        for theme in (() if phase in ('auth','dashboard') else ('light','dark')):
            context.add_init_script(f"localStorage.setItem('greenshop.theme','{theme}')")
            for width in (1440,768,390,320):
                page.set_viewport_size({'width':width,'height':1000})
                for path in paths:verify(path,width)
                page.goto(om.QA_BASE+'/',wait_until='networkidle');page.screenshot(path=str(OUT/f'typography-home-{theme}-{width}.png'),animations='disabled',full_page=True)
                checks.append(f'Customer {theme}/{width}px: fonts/inputs/body/icons/assets/overflow')
                print('PASS: '+checks[-1],flush=True)
        context.close();context=browser.new_context(ignore_https_errors=True);page=context.new_page();watch(page)
        for width in (() if phase=='dashboard' else (1440,390,320)):
            page.set_viewport_size({'width':width,'height':900})
            for path in ('/Account/Login','/Admin/Account/Login','/Account/Register','/Account/AccessDenied'):verify(path,width)
            checks.append(f'Auth {width}px: Customer/Admin login, register and genuine 403 denial page; fonts/forms/icons/assets/overflow')
            print('PASS: '+checks[-1],flush=True)
        assert not errors and not missing,(errors,missing);context.close();browser.close()
    (OUT/f'typography-{phase}-results.json').write_text(json.dumps({'status':'PASS','phase':phase,'checks':checks},indent=2))

if __name__=='__main__':
    {'prepare':prepare,'start':om.start,'refresh':lambda:om.start(False),'browser':browser,'typography':typography,'preservation':preservation,'production':production,'teardown':om.teardown,'fixtures':dm.fixtures,'dashboard-browser':dm.browser,'user-business':lambda:us.business(check_legacy=False),'user-browser':us.browser,'order-business':om.run_business,'order-edge':om.edge_checks,'order-browser':om.browser_checks}[sys.argv[1]]()
