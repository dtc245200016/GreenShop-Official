from qa_support import verify_migrations
from qa_support import PRIVATE, PROJECT
"""System/security/motion review using a disposable QA database; evidence stays in /tmp."""
import sys,os,json,hashlib,subprocess,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
import storefront_regression as gs
import order_management as om
import portal_sessions as ps

MAIN_COMPOSE=gs.main_compose
MAIN_SQL=gs.main_sql
OUT=PRIVATE/'qa';OUT.mkdir(mode=0o700,exist_ok=True)
om.OUT=ps.OUT=OUT;om.QA_PROJECT=PROJECT

def baseline():
    value={'real':om.real_snapshot(),'tables':ps.table_hashes(gs.sql)}
    root=gs.ROOT/'backend/GreenShop.Web'
    value['sources']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()
        and p.suffix in ('.cs','.cshtml','.css','.js','.csproj') and not any(x in p.parts for x in ('bin','obj'))}
    value['volumes']={s:json.loads(subprocess.check_output(['docker','inspect','--format','{{json .Mounts}}',gs.compose('ps','-q',s)],text=True)) for s in ('db','web_app')}
    file=OUT/'baseline.json';file.write_text(json.dumps(value));os.chmod(file,0o600)
    with (OUT/'before-review.sql').open('wb') as f:
        os.chmod(f.name,0o600)
        subprocess.run(['docker','compose','exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --no-tablespaces --set-gtid-purged=OFF greenshop'],stdout=f,check=True)
    print('PASS: Read-only real-data/source/volume baseline and private backup saved.',flush=True)

def prepare():
    om.prepare()

def refresh():
    om.configure_qa()
    om.qa_compose("up","-d","--no-deps","--no-build","--force-recreate","--wait","web_app")

def edit_values(page,stock,name='QA edited plant'):
    values={'Name':name,'Price':'110000','StockQuantity':stock,'Description':'QA edit evidence','CategoryId':''}
    expected=next((a.get('value','') for tag,a in page.nodes if tag=='input' and a.get('name')=='ExpectedStockQuantity'),None)
    if expected is not None:values['ExpectedStockQuantity']=expected
    return values

def reproduce():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());admin=gs.client();customer=gs.client();ps.sign_in(admin,accounts[0],True);ps.sign_in(customer,accounts[2])
    edit=gs.get(admin,'/Admin/SanPham/SuaSanPham/1')[0];stock=int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))
    oid=om.create_order(customer,1,1);assert int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))==stock-1
    assert gs.post(admin,'/Admin/SanPham/SuaSanPham/1',edit,edit_values(edit,stock))[0]==302
    assert int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))==stock
    (OUT/'stock-reproduction.json').write_text(json.dumps({'status':'REPRODUCED','checks':'Old Admin edit form restores old stock after another customer checkout; isolated fixture only'}))
    print('REPRODUCED: Stale Admin product edit overwrites stock already deducted by checkout.',flush=True)

def multipart(client,path,page,values,file_bytes=None,filename='qa.png'):
    boundary='GSQA'+__import__('uuid').uuid4().hex;body=bytearray()
    for key,value in {**values,'__RequestVerificationToken':page.input('__RequestVerificationToken')}.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    if file_bytes is not None:
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="Image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode());body.extend(file_bytes);body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())
    req=urllib.request.Request(gs.BASE+path,data=bytes(body),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    try:r=client.open(req,timeout=40)
    except urllib.error.HTTPError as e:r=e
    return r.code,dict(r.headers),r.read().decode()

def audit():
    import concurrent.futures,base64,uuid
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());a1,a2=om.admin_sessions();customer=gs.client();ps.sign_in(customer,accounts[2]);checks=[]
    def passed(s):checks.append(s);print('PASS: '+s,flush=True)
    page=gs.get(a1,'/Admin/SanPham/SuaSanPham/1')[0];stock=int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'));before_name=om.qa_sql('SELECT Name FROM Products WHERE Id=1')
    oid=om.create_order(customer,1,1);assert int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))==stock-1
    code,_,body=gs.post(a1,'/Admin/SanPham/SuaSanPham/1',page,edit_values(page,stock,'Must not overwrite checkout'))
    assert code==409 and 'Tồn kho đã thay đổi' in body
    assert int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))==stock-1 and om.qa_sql('SELECT Name FROM Products WHERE Id=1')==before_name
    fresh=gs.get(a1,'/Admin/SanPham/SuaSanPham/1')[0];p2=gs.get(a2,'/Admin/SanPham/SuaSanPham/1')[0]
    def save(pair):return gs.post(pair[0],'/Admin/SanPham/SuaSanPham/1',pair[1],edit_values(pair[1],stock-2,pair[2]))[0]
    with concurrent.futures.ThreadPoolExecutor(2) as pool:codes=list(pool.map(save,[(a1,fresh,'QA CAS Admin A'),(a2,p2,'QA CAS Admin B')]))
    assert sorted(codes)==[302,409],codes
    missing=edit_values(gs.get(a1,'/Admin/SanPham/SuaSanPham/1')[0],stock-2);missing.pop('ExpectedStockQuantity')
    assert gs.post(a1,'/Admin/SanPham/SuaSanPham/1',gs.get(a1,'/Admin/SanPham/SuaSanPham/1')[0],missing)[0]==200
    assert int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))==stock-2
    passed('Stale Admin stock edit cannot restore purchased units; concurrent stock-changing edits have one winner; missing expected stock cannot bypass the guard')
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l5cAAAAASUVORK5CYII=')
    form=gs.get(a1,'/Admin/SanPham/ThemSanPham')[0];name='QA historical image '+uuid.uuid4().hex[:8]
    values={'Name':name,'Price':'89000','StockQuantity':5,'Description':'QA image fixture','CategoryId':''}
    assert multipart(a1,'/Admin/SanPham/ThemSanPham',form,values,png)[0]==302
    pid=int(om.qa_sql('SELECT Id FROM Products WHERE Name='+gs.quote(name)));old=om.qa_sql(f'SELECT ImageUrl FROM Products WHERE Id={pid}')
    order=om.create_order(customer,pid,1);page=gs.get(a1,f'/Admin/SanPham/SuaSanPham/{pid}')[0]
    values.update({'ExpectedStockQuantity':4,'StockQuantity':4})
    assert multipart(a1,f'/Admin/SanPham/SuaSanPham/{pid}',page,values,png)[0]==302
    new=om.qa_sql(f'SELECT ImageUrl FROM Products WHERE Id={pid}');assert old!=new
    assert a1.open(gs.BASE+old).status==200
    assert gs.post(a1,f'/Admin/SanPham/XoaSanPham/{pid}',gs.get(a1,f'/Admin/SanPham/XoaSanPham/{pid}')[0],{})[0]==302
    assert a1.open(gs.BASE+old).status==200 and om.qa_sql(f'SELECT ProductId IS NULL FROM OrderItems WHERE OrderId={order}')=='1'
    try:a1.open(gs.BASE+new);raise AssertionError('Unreferenced new image should be removed')
    except urllib.error.HTTPError as e:assert e.code==404
    for filename,payload in (('script.svg',b'<svg onload="alert(1)"></svg>'),('script.png',b'<script>alert(1)</script>'),('../escape.png',png),('too-big.png',png+b'x'*(5*1024*1024))):
        before=om.qa_sql('SELECT COUNT(*) FROM Products')
        assert multipart(a1,'/Admin/SanPham/ThemSanPham',form,values,payload,filename)[0] in (200,400,413)
        assert om.qa_sql('SELECT COUNT(*) FROM Products')==before
    passed('Real upload/replacement/deletion preserves image referenced by historical orders; unreferenced image removed; SVG/script/spoofed PNG/path traversal/oversize upload rejected')
    clients=[gs.client(),gs.client()];pages=[gs.get(c,'/Account/Register')[0] for c in clients];email='qa-race-'+uuid.uuid4().hex+'@example.invalid'
    reg={'FullName':'QA duplicate registration','Email':email,'Phone':'0912345678','Password':'QaStrongPassword123','ConfirmPassword':'QaStrongPassword123','Role':1,'IsActive':False}
    with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda i:gs.post(clients[i],'/Account/Register',pages[i],reg),range(2)))
    assert sorted(r[0] for r in results)==[200,302] and om.qa_sql('SELECT COUNT(*) FROM Users WHERE Email='+gs.quote(email))=='1'
    assert om.qa_sql('SELECT Role,IsActive FROM Users WHERE Email='+gs.quote(email))=='0\t1'
    invalid=[{'FullName':'X'*101},{'Email':'X'*260+'@example.invalid'},{'Phone':'1'*22},{'Password':'A'*73,'ConfirmPassword':'A'*73},{'Password':'đ'*40,'ConfirmPassword':'đ'*40}]
    before=om.qa_sql('SELECT COUNT(*) FROM Users');client=gs.client();page=gs.get(client,'/Account/Register')[0]
    for bad in invalid:
        code,_,_=gs.post(client,'/Account/Register',page,{**reg,'Email':'qa-invalid-'+uuid.uuid4().hex+'@example.invalid',**bad});assert code==200
        assert om.qa_sql('SELECT COUNT(*) FROM Users')==before
    passed('Concurrent duplicate signup returns a validation message instead of 500, creates one Customer only; field lengths and bcrypt password byte boundary reject invalid new accounts')
    anon=gs.client();before=ps.table_hashes(om.qa_sql)
    for path in ('/Admin/DonHang/QuanLyDonHang','/Admin/SanPham/ThemSanPham','/Admin/NguoiDung/QuanLyNguoiDung','/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen'):
        for c in (anon,customer):assert gs.request(c,path)[0]==302
    for path in ('/Account/Register','/Account/Login','/Admin/Account/Login','/GioHang/ThemVaoGioHang/1','/ThanhToan/XacNhanMuaHang/1'):
        assert gs.request(anon,path,{})[0] in (400,302)
    for query in ("' OR 1=1 --",'<script>window.__qaXss=1</script>'):
        code,_,body=gs.request(anon,'/SanPham/CuaHang?search='+urllib.parse.quote(query));assert code==200 and '<script>window.__qaXss' not in body
    for path in ('/.env','/appsettings.json','/keys/','/../.env'):
        assert gs.request(anon,path)[0] in (400,404)
    assert ps.table_hashes(om.qa_sql)==before
    passed('Admin authorization/CSRF and protected files remain enforced; SQL/XSS-shaped search stays escaped and changes no data')
    (OUT/'audit-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'writes':'isolated QA only'},indent=2))

def motion():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());checks=[]
    def passed(s):checks.append(s);print('PASS: '+s,flush=True)
    for i in range(601,610):
        om.qa_sql(f"INSERT IGNORE INTO Products (Id,Name,Price,ImageUrl,Description,StockQuantity) VALUES ({i},'QA Motion Plant {i}',99000,'/images/product-placeholder.svg','QA carousel fixture',20)")
    # Genuine completed-order fixture produces meaningful heights without changing real orders.
    om.qa_sql("INSERT IGNORE INTO Orders (Id,UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES (601,3,'601motion','QA Motion','0912345678','QA address',UTC_TIMESTAMP(),345000,1,0,'COD',1,'',0)")
    with ps.playwright() as pw:
        from playwright.sync_api import expect
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});errors=[];external=[]
        ctx.on('request',lambda r:external.append(r.url) if r.resource_type in ('script','stylesheet','font') and not r.url.startswith(om.QA_BASE) else None)
        admin=ctx.new_page();customer=ctx.new_page()
        for p in (admin,customer):p.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(admin,accounts[0],ps.ADMIN_LOGIN);ps.login_page(customer,accounts[2]);customer.goto(om.QA_BASE+'/')
        root=customer.locator('[data-product-carousel]');track=customer.locator('[data-carousel-track]');root.scroll_into_view_if_needed();customer.mouse.move(2,2)
        customer.wait_for_function("document.querySelector('[data-product-carousel]').dataset.carouselAutoplay==='running'")
        initial=track.evaluate('(e)=>e.scrollLeft');customer.wait_for_function('(x)=>document.querySelector("[data-carousel-track]").scrollLeft>x+20',arg=initial,timeout=7500)
        customer.wait_for_timeout(700);root.hover();left=track.evaluate('(e)=>e.scrollLeft');customer.wait_for_timeout(5300);assert abs(track.evaluate('(e)=>e.scrollLeft')-left)<2
        customer.mouse.move(2,2);track.focus();assert root.get_attribute('data-carousel-autoplay')=='paused';track.press('Home');customer.wait_for_timeout(700);assert track.evaluate('(e)=>e.scrollLeft')<2
        track.press('ArrowRight');customer.wait_for_timeout(700);assert track.evaluate('(e)=>e.scrollLeft')>20
        customer.locator('[data-carousel-next]').click();customer.wait_for_timeout(700)
        customer.locator('[data-carousel-dots] button').first.click();customer.wait_for_timeout(700);assert track.evaluate('(e)=>e.scrollLeft')<2
        track.focus();customer.locator('header a').first.focus();customer.mouse.move(2,2);assert root.get_attribute('data-carousel-autoplay')=='paused'
        root.scroll_into_view_if_needed();customer.locator('[data-carousel-toggle]').click();customer.mouse.move(2,2)
        customer.wait_for_function("document.querySelector('[data-product-carousel]').dataset.carouselAutoplay==='running'")
        customer.locator('[data-carousel-toggle]').click();assert root.get_attribute('data-carousel-autoplay')=='paused'
        track.focus();track.press('Home');customer.wait_for_timeout(700);bounds=track.bounding_box();url=customer.url
        customer.mouse.move(bounds['x']+bounds['width']*.8,bounds['y']+50);customer.mouse.down();customer.mouse.move(bounds['x']+bounds['width']*.35,bounds['y']+50,steps=20);customer.mouse.up();customer.wait_for_timeout(700)
        assert track.evaluate('(e)=>e.scrollLeft')>20 and customer.url==url
        expected_ids=[int(i) for i in om.qa_sql('SELECT p.Id FROM Products p LEFT JOIN Categories c ON c.Id=p.CategoryId WHERE p.CategoryId IS NULL OR c.IsActive=1 ORDER BY p.Id DESC LIMIT 12').splitlines()]
        assert track.locator('.shop-product-card').evaluate_all('(cards)=>cards.map(c=>Number(c.dataset.productId))')==expected_ids
        assert track.locator('form').count()==track.locator('.shop-product-card').count()*2
        passed('Real carousel auto-slides, pauses on hover/focus, resumes explicitly; arrows/dots/keyboard/mouse drag work without cloned cards/forms or accidental navigation')
        # Click an existing real purchase form after dragging, then place an actual QA order.
        track.press('Home');customer.wait_for_timeout(700);pid=int(track.locator('.shop-product-card').first.get_attribute('data-product-id'));stock=int(om.qa_sql(f'SELECT StockQuantity FROM Products WHERE Id={pid}'))
        track.locator('.shop-product-card').first.locator('.product-card-buy button').click();expect(customer).to_have_url(__import__('re').compile('/ThanhToan/XacNhanMuaHang'))
        customer.locator('#Address').fill('123 QA motion checkout');customer.get_by_role('button',name='Xác nhận đặt hàng',exact=False).click();expect(customer).to_have_url(__import__('re').compile('/ThanhToan/ChiTietDonHang/'))
        oid=int(customer.url.rsplit('/',1)[1]);assert om.qa_sql(f'SELECT UserId FROM Orders WHERE Id={oid}')=='3' and int(om.qa_sql(f'SELECT StockQuantity FROM Products WHERE Id={pid}'))==stock-1
        assert gs.request(om.admin_sessions()[0],f'/Admin/DonHang/ChiTietDonHang/{oid}')[0]==200
        assert {ps.ADMIN_COOKIE,ps.CUSTOMER_COOKIE}.issubset({c['name'] for c in ctx.cookies()});assert all(c['secure'] and c['httpOnly'] for c in ctx.cookies() if c['name'] in (ps.ADMIN_COOKIE,ps.CUSTOMER_COOKIE))
        passed('Buy-now remains a real owned checkout with one stock deduction; simultaneous Admin/Customer tabs retain separate secure cookies')
        for width in (320,360,768,1440):
            customer.set_viewport_size({'width':width,'height':1000});customer.goto(om.QA_BASE+'/');root.scroll_into_view_if_needed();customer.wait_for_timeout(600)
            assert customer.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            customer.screenshot(path=str(OUT/f'carousel-{width}.png'),full_page=True)
        passed('Homepage carousel stays within viewport at 320/360/768/1440px with matching local typography and controls')
        admin.goto(om.QA_BASE+'/Admin/Admin/TongQuan?range=7d',wait_until='domcontentloaded');chart=admin.locator('[data-chart]');chart.scroll_into_view_if_needed();bar=admin.locator('.dash-bar').last
        admin.wait_for_function("document.querySelector('[data-chart]').dataset.chartRevealed==='true'")
        assert admin.locator('.dash-bar').evaluate_all('(els)=>els.some(e=>e.getAnimations().length>0)')
        admin.wait_for_timeout(1100);heights=admin.locator('.dash-bar').evaluate_all('(els)=>els.map(e=>e.getAttribute("height"))')
        bar.click();expect(bar).to_have_attribute('aria-pressed','true');assert bar.evaluate('(e)=>e.getAnimations().length')>0
        expect(admin.locator('[data-chart-selection]')).to_have_text(bar.get_attribute('data-label')+' · '+bar.get_attribute('data-value'))
        bar.evaluate('(e)=>e.getAnimations().forEach(a=>a.currentTime=244)');assert bar.evaluate('(e)=>new DOMMatrix(getComputedStyle(e).transform).d')>1
        admin.wait_for_timeout(700);assert heights==admin.locator('.dash-bar').evaluate_all('(els)=>els.map(e=>e.getAttribute("height"))')
        first=admin.locator('.dash-bar').first;first.focus();first.press('Enter');expect(first).to_have_attribute('aria-pressed','true');expect(bar).to_have_attribute('aria-pressed','false');first.press('Escape');expect(first).to_have_attribute('aria-pressed','false')
        admin.reload(wait_until='domcontentloaded');chart.scroll_into_view_if_needed();admin.wait_for_function("[...document.querySelectorAll('.dash-bar')].some(e=>e.getAnimations().length>0)")
        admin.wait_for_timeout(1100);admin.screenshot(path=str(OUT/'dashboard-motion.png'),full_page=True)
        assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth')
        admin.locator('.dash-status-row').first.click();expect(admin).to_have_url(__import__('re').compile('/Admin/DonHang/QuanLyDonHang'))
        passed('Dashboard bars grow on entry and reload, pulse above baseline when selected, expose real values with mouse/keyboard, preserve numerical heights and keep real status links')
        ctx.close();ctx=browser.new_context(ignore_https_errors=True,reduced_motion='reduce',viewport={'width':360,'height':1000});customer=ctx.new_page();admin=ctx.new_page()
        customer.goto(om.QA_BASE+'/');root=customer.locator('[data-product-carousel]');track=customer.locator('[data-carousel-track]');root.scroll_into_view_if_needed();expect(customer.locator('[data-carousel-toggle]')).to_be_disabled()
        left=track.evaluate('(e)=>e.scrollLeft');customer.wait_for_timeout(5300);assert track.evaluate('(e)=>e.scrollLeft')==left
        customer.locator('[data-carousel-next]').click();assert track.evaluate('(e)=>e.scrollLeft')>left
        ps.login_page(admin,accounts[0],ps.ADMIN_LOGIN);admin.goto(om.QA_BASE+'/Admin/Admin/TongQuan?range=year');admin.locator('[data-chart]').scroll_into_view_if_needed();assert admin.locator('.dash-bar').evaluate_all('(els)=>els.every(e=>e.getAnimations().length===0)')
        admin.locator('.dash-bar').last.focus();admin.locator('.dash-bar').last.press('Space');expect(admin.locator('.dash-bar').last).to_have_attribute('aria-pressed','true');assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors;assert not external,external
        passed('Reduced-motion disables automatic/decorative movement but preserves manual interaction; no browser JS errors or external UI scripts/styles/fonts')
        ctx.close();browser.close()
    (OUT/'motion-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'writes':'isolated QA only'},indent=2))

def rates():
    p=OUT/'compose.yaml';original=p.read_text();p.write_text(original.replace('LoginAttemptsPerMinute: 200','LoginAttemptsPerMinute: 3').replace('RegistrationAttemptsPerMinute: 200','RegistrationAttemptsPerMinute: 2'))
    try:
        om.qa_compose('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','web_app');om.start(False);om.configure_qa();c=gs.client();page=gs.get(c,'/Account/Login')[0]
        for _ in range(3):assert gs.post(c,'/Account/Login',page,{'Email':'not-real@example.invalid','Password':'wrong'})[0]==200
        code,h,_=gs.post(c,'/Account/Login',page,{'Email':'not-real@example.invalid','Password':'wrong'});assert code==429 and int(h['Retry-After'])>0
        req=urllib.request.Request(gs.BASE+'/Account/Login',data=urllib.parse.urlencode({'Email':'not-real@example.invalid','Password':'wrong','__RequestVerificationToken':page.input('__RequestVerificationToken')}).encode(),headers={'X-Forwarded-For':'198.51.100.11'})
        try:c.open(req);raise AssertionError('Client spoof bypassed rate limit')
        except urllib.error.HTTPError as e:assert e.code==429
        assert gs.post(c,ps.ADMIN_LOGIN,gs.get(c,ps.ADMIN_LOGIN)[0],{'Email':'not-real@example.invalid','Password':'wrong'})[0]==429
        reg=gs.get(c,'/Account/Register')[0]
        for _ in range(2):assert gs.post(c,'/Account/Register',reg,{'FullName':''})[0]==200
        assert gs.post(c,'/Account/Register',reg,{'FullName':''})[0]==429
        assert gs.request(c,'/')[0]==200 and gs.request(c,'/SanPham/CuaHang')[0]==200
        print('PASS: Real login/signup throttling returns 429/Retry-After; Admin alias and spoofed XFF cannot bypass; public pages stay available.',flush=True)
        (OUT/'rate-results.json').write_text(json.dumps({'status':'PASS','checks':'login/register, shared aliases, trusted proxy IP and unaffected browsing'}))
    finally:
        p.write_text(original);om.qa_compose('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','web_app');om.start(False)

def regression():
    import payment_shipping as payment
    import excel_exports as exports
    import dashboard_management as dashboard
    import user_management as users
    import customer_ui as customer_ui
    for module in (om,ps,payment,exports,dashboard,users,customer_ui):module.OUT=OUT
    om.QA_PROJECT=PROJECT;payment.MAIN_COMPOSE=MAIN_COMPOSE
    gs.REPORTS=OUT/'storefront';gs.REPORTS.mkdir(exist_ok=True)
    mode=sys.argv[2]
    if mode=='business':
        om.qa_sql('UPDATE Products SET Price=100000,StockQuantity=30 WHERE Id=1')
        payment.business_regression()
    elif mode=='payment':ps.payment_smoke()
    elif mode=='security':ps.security()
    elif mode=='persistence':ps.persistence()
    elif mode=='customer-ui':customer_ui.browser()
    elif mode=='dashboard-ui':dashboard.browser()
    elif mode=='public-preview':customer_ui.public_preview()
    elif mode=='reports':
        exports.fixtures();gs.compose=MAIN_COMPOSE;exports.exports();exports.roundtrip()
        gs.compose=MAIN_COMPOSE;dashboard.metrics()
    else:raise ValueError(mode)

def carousel_edges():
    om.configure_qa();saved=om.qa_sql('SELECT Id,COALESCE(CategoryId,0),StockQuantity FROM Products ORDER BY Id')
    hidden=int(om.qa_sql("INSERT INTO Categories (Name,Description,IsActive) VALUES ('QA carousel edge','QA owned temporary fixture',0); SELECT LAST_INSERT_ID()"))
    try:
        om.qa_sql(f'UPDATE Products SET CategoryId={hidden}')
        with ps.playwright() as pw:
            from playwright.sync_api import expect
            b=pw.chromium.launch();ctx=b.new_context(ignore_https_errors=True,viewport={'width':360,'height':900});p=ctx.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
            p.goto(om.QA_BASE+'/');assert p.locator('[data-carousel-track]').count()==0;expect(p.locator('main')).to_contain_text('Chưa có sản phẩm')
            om.qa_sql('UPDATE Products SET CategoryId=NULL,StockQuantity=0 WHERE Id=1')
            p.reload();expect(p.locator('[data-carousel-track] .shop-product-card')).to_have_count(1)
            expect(p.locator('[data-carousel-next]')).not_to_be_visible();expect(p.locator('.product-card-buy button')).to_be_disabled()
            assert p.locator('[data-product-carousel]').get_attribute('data-carousel-autoplay')=='paused' and p.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors;ctx.close();b.close()
    finally:
        for row in saved.splitlines():
            pid,category,stock=row.split('\t');om.qa_sql(f'UPDATE Products SET CategoryId={category if category!="0" else "NULL"},StockQuantity={stock} WHERE Id={pid}')
        om.qa_sql(f'DELETE FROM Categories WHERE Id={hidden}')
    with ps.playwright() as pw:
        b=pw.chromium.launch();ctx=b.new_context(ignore_https_errors=True,java_script_enabled=False,viewport={'width':360,'height':900});p=ctx.new_page();p.goto(om.QA_BASE+'/')
        track=p.locator('[data-carousel-track]');assert track.locator('.shop-product-card').count()==12 and track.evaluate('(e)=>e.scrollWidth>e.clientWidth')
        expect(track.locator('.product-link').first).to_have_attribute('href',__import__('re').compile('/SanPham/ChiTietSanPham/'))
        ctx.close();b.close()
    (OUT/'carousel-edge-results.json').write_text(json.dumps({'status':'PASS','checks':'Empty catalogue, single sold-out item, hidden idle controls, native scrolling/real links without JS; temporary categories/stocks restored'}))
    print('PASS: Carousel handles empty/single/sold-out catalogues and remains natively scrollable without JavaScript; QA fixtures restored.',flush=True)

def preservation():
    import m1_acceptance as acceptance
    acceptance.preservation()

def production():
    for path in ('/','/Account/Login',ps.ADMIN_LOGIN,'/SanPham/CuaHang','/lib/bootstrap/dist/css/bootstrap.min.css','/lib/bootstrap/dist/js/bootstrap.bundle.min.js','/lib/fontawesome/css/all.min.css','/lib/fontawesome/webfonts/fa-solid-900.woff2','/lib/fontawesome/webfonts/fa-regular-400.woff2'):
        c=gs.client();r=c.open('https://localhost'+path);assert r.status==200,path
    for path,login in (('/Admin/DonHang/QuanLyDonHang',ps.ADMIN_LOGIN),('/ThanhToan/DonHangCuaToi','/Account/Login')):
        code,h,_=gs.request(gs.client(),path);assert code==302 and login in h['Location']
    verify_migrations(MAIN_SQL)
    for s in ('web_app','db'):
        cid=MAIN_COMPOSE('ps','-q',s);assert subprocess.check_output(['docker','inspect','--format','{{.State.Health.Status}}',cid],text=True).strip()=='healthy'
    for s,port in (('db','3306/tcp'),('phpmyadmin','80/tcp'),('web_app','8080/tcp')):
        bindings=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .NetworkSettings.Ports}}',MAIN_COMPOSE('ps','-q',s)],text=True))[port]
        assert bindings and all(b['HostIp']=='127.0.0.1' for b in bindings),(s,bindings)
    image=lambda cid:subprocess.check_output(['docker','inspect','--format','{{.Image}}',cid],text=True).strip()
    current=image(MAIN_COMPOSE('ps','-q','web_app'));assert current==image(om.qa_compose('ps','-q','web_app'))
    preservation()
    (OUT/'production-results.json').write_text(json.dumps({'status':'PASS','image':current,'checks':'Tested QA image deployed; HTTPS/pages/local assets healthy; DB/PMA/backend bind localhost; all real data preserved'}))
    print('PASS: Tested image is live; HTTPS/local assets/auth challenges healthy, private ports localhost-only, real data unchanged.',flush=True)

if __name__=='__main__':
    {'baseline':baseline,'prepare':prepare,'reproduce':reproduce,'refresh':refresh,'audit':audit,'motion':motion,'carousel-edges':carousel_edges,'rates':rates,'regression':regression,'preservation':preservation,'production':production,'teardown':om.teardown}[sys.argv[1]]()


def category_crud():
    """Exercise actual MVC category CRUD/relations, not SQL-only seeding."""
    import uuid
    om.configure_qa();admin=om.admin_sessions()[0];customer=gs.client();ps.sign_in(customer,json.loads((OUT/'accounts.json').read_text())[2])
    base='/Admin/DanhMuc/';name='QA Category '+uuid.uuid4().hex[:8]
    page=gs.get(admin,base+'ThemDanhMuc')[0]
    assert gs.post(admin,base+'ThemDanhMuc',page,{'Name':'','Description':'','IsActive':'true'})[0]==200
    assert gs.post(admin,base+'ThemDanhMuc',page,{'Name':name,'Description':'QA public relation','IsActive':'true'})[0]==302
    cid=int(om.qa_sql('SELECT Id FROM Categories WHERE Name='+gs.quote(name)))
    assert gs.post(admin,base+'ThemDanhMuc',page,{'Name':name,'Description':'Duplicate','IsActive':'true'})[0]==200
    assert gs.request(customer,base+f'SuaDanhMuc/{cid}')[0]==302
    edit=gs.get(admin,base+f'SuaDanhMuc/{cid}')[0]
    edited=name+' edited';assert gs.post(admin,base+f'SuaDanhMuc/{cid}',edit,{'Name':edited,'Description':'<script>window.categoryXss=1</script>','IsActive':'true'})[0]==302
    public=gs.request(gs.client(),'/SanPham/CuaHang')[2];assert edited in public
    pid=int(om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity,CategoryId) VALUES ('QA category-linked plant',90000,'/images/product-placeholder.svg','QA category relation',3,"+str(cid)+"); SELECT LAST_INSERT_ID()"))
    assert pid in gs.get(gs.client(),f'/SanPham/CuaHang?categoryId={cid}')[0].cards()
    source=gs.get(admin,base+'QuanLyDanhMuc')[0]
    assert gs.request(admin,base+f'ThayDoiTrangThaiDanhMuc/{cid}')[0]==405
    assert gs.request(admin,base+f'ThayDoiTrangThaiDanhMuc/{cid}',{'isActive':'false'})[0]==400
    assert gs.post(admin,base+f'ThayDoiTrangThaiDanhMuc/{cid}',source,{'isActive':'false'})[0]==302
    assert gs.request(gs.client(),f'/SanPham/CuaHang?categoryId={cid}')[0]==404
    assert gs.request(gs.client(),f'/SanPham/ChiTietSanPham/{pid}')[0]==404
    assert gs.post(admin,base+f'ThayDoiTrangThaiDanhMuc/{cid}',source,{'isActive':'true'})[0]==302
    delete=gs.get(admin,base+f'XoaDanhMuc/{cid}')[0]
    assert gs.post(admin,base+f'XoaDanhMuc/{cid}',delete,{})[0]==200
    assert om.qa_sql(f'SELECT COUNT(*) FROM Categories WHERE Id={cid}')=='1'
    assert om.qa_sql(f'SELECT CategoryId FROM Products WHERE Id={pid}')==str(cid)
    # Remove the freshly owned fixture product through the real product endpoint, then delete the empty category.
    product_delete=gs.get(admin,f'/Admin/SanPham/XoaSanPham/{pid}')[0]
    assert gs.post(admin,f'/Admin/SanPham/XoaSanPham/{pid}',product_delete,{})[0]==302
    assert gs.post(admin,base+f'XoaDanhMuc/{cid}',delete,{})[0]==302
    assert om.qa_sql(f'SELECT COUNT(*) FROM Categories WHERE Id={cid}')=='0'
    assert om.qa_sql(f'SELECT COUNT(*) FROM Products WHERE Id={pid}')=='0'
    (OUT/'category-crud-results.json').write_text(json.dumps({'status':'PASS','checks':'Real HTTP create/edit/duplicate validation/status/delete; Customer denied; CSRF and method gates; inactive hidden; linked category deletion blocked; empty category deletion succeeds'}))
    print('PASS: Category HTTP CRUD, duplicate/input validation, public navigation/relations, status/CSRF/roles; linked deletion blocked, empty deletion allowed.',flush=True)
