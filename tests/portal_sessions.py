from qa_support import verify_migrations
from qa_support import PRIVATE, PROJECT
"""Admin/customer session isolation QA; every business mutation uses disposable fixtures."""
import hashlib,json,os,sys,subprocess
from pathlib import Path
import storefront_regression as gs
import order_management as om
MAIN_COMPOSE=gs.main_compose

OUT=PRIVATE/'qa';OUT.mkdir(mode=0o700,exist_ok=True)
om.OUT=OUT;om.QA_PROJECT=PROJECT
ADMIN_LOGIN='/Admin/Account/Login'
ADMIN_COOKIE='.AspNetCore.Cookies'
CUSTOMER_COOKIE='GreenShop.Customer'

from qa_support import table_hashes

def baseline():
    value={'real':om.real_snapshot(),'tables':table_hashes(gs.sql)}
    root=gs.ROOT/'backend/GreenShop.Web'
    value['sources']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
        if p.is_file() and p.suffix in ('.cs','.cshtml','.css','.js','.csproj') and not any(x in p.parts for x in ('bin','obj'))}
    (OUT/'baseline.json').write_text(json.dumps(value));os.chmod(OUT/'baseline.json',0o600)
    print('PASS: Read-only real data, keys, uploads, infrastructure and source baseline captured.',flush=True)

def prepare():
    om.prepare()

def playwright():
    # Install Playwright in a venv; respect PYTHONPATH and PLAYWRIGHT_BROWSERS_PATH.
    from playwright.sync_api import sync_playwright
    return sync_playwright()

def login_page(page,credentials,path='/Account/Login'):
    page.goto(om.QA_BASE+path);page.locator('#Email').fill(credentials[0]);page.locator('[name=Password]').fill(credentials[1]);page.locator('form:has(#Email) button[type=submit]').click()

def reproduce():
    raise RuntimeError("The historical shared-cookie bug is fixed. Run m1 regression security for current isolation checks.")

def refresh():
    om.configure_qa()
    om.qa_compose("up","-d","--no-deps","--no-build","--force-recreate","--wait","web_app")

def browser_checks():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());checks=[]
    def passed(message):checks.append(message);print('PASS: '+message,flush=True)
    with playwright() as pw:
        from playwright.sync_api import expect
        b=pw.chromium.launch();errors=[]
        def submit_admin(p):
            p.locator('#orderConfirmSubmit').click()
            p.wait_for_function("!document.querySelector('.order-admin form[data-busy=\"true\"]')")
            expect(p.locator('.admin-action-feedback')).to_be_visible()
            assert 'error' not in (p.locator('.admin-action-feedback').get_attribute('class') or ''),p.locator('.admin-action-feedback').inner_text()
        # Genuine cookies from the old deployed image, not manufactured authentication tickets.
        for name,uid,path in (('admin',1,'/Admin/DonHang/ChiTietDonHang/1'),('customer',3,'/ThanhToan/DonHangCuaToi')):
            ctx=b.new_context(ignore_https_errors=True,storage_state=str(OUT/f'legacy-{name}.json'));p=ctx.new_page();p.goto(om.QA_BASE+path)
            assert p.url==om.QA_BASE+path and f'QA Order User {uid}' in p.locator('body').inner_text()
            if name=='customer':
                assert any(c['name']==CUSTOMER_COOKIE for c in ctx.cookies());p.goto(om.QA_BASE+'/Admin/DonHang/QuanLyDonHang');expect(p).to_have_url(__import__('re').compile('/Admin/Account/Login'))
                p.goto(om.QA_BASE+'/ThanhToan/DonHangCuaToi');assert p.url.endswith('/ThanhToan/DonHangCuaToi')
            ctx.close()
        passed('Genuine old Admin cookie still works; old Customer cookie migrates safely and never authenticates Admin routes')
        legacy=int(om.qa_sql("INSERT INTO Orders (UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES (3,"+gs.quote(__import__('uuid').uuid4().hex)+",'QA Legacy Browser Fixture','0912345678','QA legacy fixture address',UTC_TIMESTAMP(),200000,0,0,'COD',0,'',0); SELECT LAST_INSERT_ID()"))
        om.qa_sql(f"INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES ({legacy},1,'QA Historical Browser Plant','/images/product-placeholder.svg',100000,2)")
        # One browser context and two pages: Admin rendered before Customer login/renewal.
        ctx=b.new_context(ignore_https_errors=True);admin=ctx.new_page();customer=ctx.new_page()
        for p in (admin,customer):p.on('pageerror',lambda e:errors.append(str(e)))
        login_page(admin,accounts[0],ADMIN_LOGIN);admin.goto(om.QA_BASE+f'/Admin/DonHang/ChiTietDonHang/{legacy}')
        admin.get_by_role('button',name='Ghi nhận đơn đã trừ kho',exact=True).click();admin.locator('#orderReason').fill('QA original inventory evidence; no new deduction')
        login_page(customer,accounts[2]);customer.goto(om.QA_BASE+'/ThanhToan/DonHangCuaToi')
        assert f'QA Order User 3' in customer.locator('body').inner_text()
        assert {ADMIN_COOKIE,CUSTOMER_COOKIE}.issubset({c['name'] for c in ctx.cookies()})
        stock=om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1');submit_admin(admin)
        assert om.qa_sql(f'SELECT InventoryStatus FROM Orders WHERE Id={legacy}')=='1' and stock==om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1')
        assert 'QA Order User 1' in admin.locator('body').inner_text()
        for label,status in (('Xác nhận đơn',3),('Bắt đầu xử lý',4),('Bắt đầu giao hàng',5),('Xác nhận đã giao',1)):
            admin.get_by_role('button',name=label,exact=True).click();submit_admin(admin)
            assert om.qa_sql(f'SELECT Status FROM Orders WHERE Id={legacy}')==str(status)
            customer.reload();assert customer.url.endswith('/ThanhToan/DonHangCuaToi') and 'QA Order User 3' in customer.locator('body').inner_text()
        admin.get_by_role('button',name='Ghi nhận đã nhận tiền COD',exact=True).click();admin.locator('#orderReason').fill('QA COD fixture only; no real funds');submit_admin(admin)
        assert om.qa_sql(f'SELECT IsPaid,PaymentConfirmedById FROM Orders WHERE Id={legacy}')=='1\t1'
        assert om.qa_sql(f'SELECT COUNT(*) FROM OrderStatusHistories WHERE OrderId={legacy} AND AdminId<>1')=='0'
        admin.screenshot(path=str(OUT/'admin-with-customer-tab.png'),full_page=True);customer.screenshot(path=str(OUT/'customer-with-admin-tab.png'),full_page=True)
        passed('Admin-first, Customer-second in two shared-context tabs: stale modal/CSRF succeeds, full order workflow/COD audit remains Admin 1, Customer stays User 3, no extra stock deduction')
        # Logout affects only its own portal, including actions rendered in the other tab.
        customer.goto(om.QA_BASE+'/');customer.locator('.account-menu summary').click();customer.locator('.account-menu form button[type=submit]').click()
        expect(customer).to_have_url(om.QA_BASE+'/Account/Login');admin.reload();assert f'/Admin/DonHang/ChiTietDonHang/{legacy}' in admin.url
        login_page(customer,accounts[2]);admin.locator('#logoutForm button[type=submit]').click();expect(admin).to_have_url(om.QA_BASE+ADMIN_LOGIN)
        customer.goto(om.QA_BASE+'/ThanhToan/DonHangCuaToi');assert customer.url.endswith('/ThanhToan/DonHangCuaToi')
        passed('Customer logout leaves Admin authenticated; Admin logout leaves Customer authenticated and redirects to the correct login portal')
        ctx.close()
        # Reverse order, including a stale customer checkout form across Admin login.
        ctx=b.new_context(ignore_https_errors=True);customer=ctx.new_page();admin=ctx.new_page()
        for p in (admin,customer):p.on('pageerror',lambda e:errors.append(str(e)))
        login_page(customer,accounts[2]);customer.goto(om.QA_BASE+'/ThanhToan/XacNhanMuaHang/1');customer.locator('#Address').fill('123 QA shared browser checkout address')
        admin.goto(om.QA_BASE+'/Admin/DonHang/QuanLyDonHang');expect(admin).to_have_url(__import__('re').compile('/Admin/Account/Login'))
        admin.locator('#Email').fill(accounts[2][0]);admin.locator('[name=Password]').fill(accounts[2][1]);admin.locator('form:has(#Email) button[type=submit]').click()
        expect(admin.locator('.validation-summary-errors')).to_contain_text('không có quyền quản trị')
        assert CUSTOMER_COOKIE in {c['name'] for c in ctx.cookies()} and ADMIN_COOKIE not in {c['name'] for c in ctx.cookies()}
        admin.locator('#Email').fill(accounts[0][0]);admin.locator('[name=Password]').fill(accounts[0][1]);admin.locator('form:has(#Email) button[type=submit]').click()
        expect(admin).to_have_url(om.QA_BASE+'/Admin/DonHang/QuanLyDonHang')
        customer.get_by_role('button',name='Xác nhận đặt hàng',exact=False).click();assert '/ThanhToan/ChiTietDonHang/' in customer.url
        oid=int(customer.url.rsplit('/',1)[1]);assert om.qa_sql(f'SELECT UserId,IsPaid,Subtotal,ShippingFee,Total FROM Orders WHERE Id={oid}')=='3\t0\t100000.00\t30000.00\t130000.00'
        assert om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1')==str(int(stock)-1)
        admin.goto(om.QA_BASE+f'/Admin/DonHang/ChiTietDonHang/{oid}');admin.get_by_role('button',name='Xác nhận đơn',exact=True).click()
        customer.goto(om.QA_BASE+'/');customer.locator('.account-menu summary').click();customer.locator('.account-menu form button[type=submit]').click()
        submit_admin(admin);assert om.qa_sql(f'SELECT Status FROM Orders WHERE Id={oid}')=='3'
        login_page(customer,accounts[2]);customer.goto(om.QA_BASE+'/ThanhToan/DonHangCuaToi');assert 'QA Order User 3' in customer.locator('body').inner_text()
        passed('Customer-first, Admin-second: wrong-role Admin login is rejected; returnUrl stays in Admin; stale Customer checkout creates the correct owned order/fee; Customer logout cannot break a previously opened Admin action')
        guest=b.new_context(ignore_https_errors=True);p=guest.new_page()
        for width in (360,768,1440):
            p.set_viewport_size({'width':width,'height':900})
            for path,label in ((ADMIN_LOGIN,'admin'),('/Account/Login','customer')):
                p.goto(om.QA_BASE+path);assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert p.locator('form:has(#Email)').get_attribute('action')==path
                p.screenshot(path=str(OUT/f'login-{label}-{width}.png'),full_page=True)
        guest.close()
        assert not errors,errors;ctx.close();b.close()
    (OUT/'browser-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'context':'Admin and Customer tabs share one real Chromium browser context; no isolated profile workaround','writes':'QA fixtures only'},indent=2))

def preservation():
    before=json.loads((OUT/'baseline.json').read_text());assert table_hashes(gs.sql)==before['tables']
    after=om.real_snapshot()
    for key in ('products','categories','users','images','keys','infrastructure_source','containers','Orders','OrderItems','CartItems','migrations'):
        assert after[key]==before['real'][key],key
    allowed={'Program.cs','Controllers/AccountController.cs','Services/UserSession.cs','Views/Account/Login.cshtml','Areas/Admin/Views/Shared/_AdminLayout.cshtml','wwwroot/js/admin-orders.js','Views/Shared/Components/StoreNavigation/Header.cshtml'}
    root=gs.ROOT/'backend/GreenShop.Web'
    for path,digest in before['sources'].items():
        if path not in allowed:assert hashlib.sha256((root/path).read_bytes()).hexdigest()==digest,path
    (OUT/'preservation-results.json').write_text(json.dumps({'status':'PASS','checks':'Every real table/row including Users roles/passwords/session versions, orders/payment/audit/stock/settings unchanged; same keys/uploads/infrastructure/other containers and source-matched migration IDs; unrelated source unchanged'}))
    print('PASS: All real business/account/session data, keys/uploads, infrastructure and unrelated source remain unchanged.',flush=True)

def sign_in(client,account,admin=False,return_url=None):
    path=ADMIN_LOGIN if admin else '/Account/Login'
    if return_url:path+='?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode({'returnUrl':return_url})
    source=gs.get(client,path)[0]
    code,headers,_=gs.post(client,ADMIN_LOGIN if admin else '/Account/Login',source,{'Email':account[0],'Password':account[1],'RememberMe':'true','returnUrl':return_url or ''})
    assert code==302,(code,headers.get('Location'))
    return headers

def security():
    import copy,urllib.request
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());checks=[]
    def passed(s):checks.append(s);print('PASS: '+s,flush=True)
    a1=gs.client();sign_in(a1,accounts[0],True)
    customer=gs.client();sign_in(customer,accounts[2]);both=gs.client();sign_in(both,accounts[2]);sign_in(both,accounts[1],True)
    before=table_hashes(om.qa_sql)
    for client in (gs.client(),customer):
        for path in ('/Admin/DonHang/QuanLyDonHang','/Admin/NguoiDung/QuanLyNguoiDung','/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen','/Admin/DonHang/XuatExcelDonHang'):
            code,h,_=gs.request(client,path);assert code==302 and ADMIN_LOGIN in h['Location']
        source=gs.get(client,'/Account/Login' if client is not customer else '/')[0]
        for action in ('XacNhanDonHang','HuyDonHang','XacNhanDaNhanTien','XacNhanThuCod','XacNhanDaTruKho','CapNhatGhiChuDonHang'):
            assert gs.post(client,'/Admin/DonHang/'+action+'/1',source,{'ExpectedVersion':0,'Note':'Must deny','Role':'Admin'})[0]==302
    source=gs.get(both,'/')[0]
    assert gs.post(both,'/Admin/DonHang/CapNhatGhiChuDonHang/1',source,{'ExpectedVersion':om.qa_sql('SELECT Version FROM Orders WHERE Id=1'),'Note':'Wrong-portal CSRF'})[0]==400
    for path in ('/Account/Login',ADMIN_LOGIN,'/Account/Logout','/Admin/Account/Logout'):
        assert gs.request(both,path,{})[0]==400
    for path in ('/Account/Logout','/Admin/Account/Logout'):assert gs.request(both,path)[0]==405
    def cookie(c,name):
        return next(copy.copy(v) for h in c.handlers if isinstance(h,urllib.request.HTTPCookieProcessor) for v in h.cookiejar if v.name==name)
    for source,old,new,path in ((customer,CUSTOMER_COOKIE,ADMIN_COOKIE,'/Admin/DonHang/QuanLyDonHang'),(a1,ADMIN_COOKIE,CUSTOMER_COOKIE,'/ThanhToan/DonHangCuaToi')):
        swapped=gs.client();value=cookie(source,old);value.name=new
        next(h.cookiejar for h in swapped.handlers if isinstance(h,urllib.request.HTTPCookieProcessor)).set_cookie(value)
        assert gs.request(swapped,path)[0]==302
    assert table_hashes(om.qa_sql)==before
    passed('Customer-only/anonymous cannot use Admin pages/actions/exports/settings; role query and renamed cookies cannot elevate; cross-portal/missing CSRF rejected; GET logout 405; denied requests change no data')
    # The existing DB role/IsActive/SessionVersion revocation checks remain mandatory per portal.
    def change(uid,action,values=None):
        source=gs.get(a1,f'/Admin/NguoiDung/ChiTietNguoiDung/{uid}')[0]
        return gs.post(a1,f'/Admin/NguoiDung/{action}/{uid}',source,{'ExpectedVersion':om.qa_sql(f'SELECT Version FROM Users WHERE Id={uid}'),**(values or {})})[0]
    assert change(2,'ThayDoiVaiTro',{'TargetRole':0})==302
    assert gs.request(both,'/Admin/DonHang/QuanLyDonHang')[0]==302
    assert 'QA Order User 3' in gs.get(both,'/ThanhToan/DonHangCuaToi')[1]
    assert change(2,'ThayDoiVaiTro',{'TargetRole':1})==302
    assert gs.request(both,'/Admin/DonHang/QuanLyDonHang')[0]==302
    passed('Revoked Admin cookie stays revoked after restoring role; the simultaneous Customer session remains usable')
    sign_in(both,accounts[0],True);source=gs.get(both,'/Admin/DonHang/ChiTietDonHang/1')[0]
    stock=om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id');orders=om.qa_sql('SELECT Id,Version,IsPaid,Status FROM Orders ORDER BY Id')
    assert change(3,'KhoaTaiKhoan')==302 and gs.request(both,'/ThanhToan/DonHangCuaToi')[0]==302
    assert gs.request(both,'/Admin/DonHang/QuanLyDonHang')[0]==200
    assert change(3,'MoKhoaTaiKhoan')==302 and gs.request(both,'/ThanhToan/DonHangCuaToi')[0]==302
    assert stock==om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id') and orders==om.qa_sql('SELECT Id,Version,IsPaid,Status FROM Orders ORDER BY Id')
    passed('Locked Customer cookie is rejected and cannot revive after unlock; simultaneous Admin session remains authenticated; orders/payment/stock unchanged')
    for value in ('https://example.invalid/','//example.invalid/','/Admin/DonHang/HuyDonHang/1','/Admin/DonHang/XacNhanDaNhanTien/1','/ThanhToan/XacNhanMuaHang/1'):
        c=gs.client();h=sign_in(c,accounts[0],True,value);assert h['Location']=='/Admin'
    c=gs.client();h=sign_in(c,accounts[0],True,'/Admin/DonHang/ChiTietDonHang/1?from=qa');assert h['Location']=='/Admin/DonHang/ChiTietDonHang/1?from=qa'
    passed('Admin returnUrl permits actual GET management pages only, rejecting external/customer/mutation targets')
    (OUT/'security-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'writes':'only synthetic QA user revocation/restore transitions'},indent=2))

def persistence():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());c=gs.client()
    sign_in(c,accounts[2]);sign_in(c,accounts[0],True);before=table_hashes(om.qa_sql)
    om.qa_compose('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','web_app');om.start(False)
    assert table_hashes(om.qa_sql)==before
    assert 'QA Order User 3' in gs.get(c,'/ThanhToan/DonHangCuaToi')[1]
    assert 'QA Order User 1' in gs.get(c,'/Admin/DonHang/QuanLyDonHang')[1]
    (OUT/'persistence-results.json').write_text(json.dumps({'status':'PASS','checks':'Both genuine Admin and Customer cookies in the same jar remain valid across QA force-recreate with existing keys; all tables unchanged'}))
    print('PASS: Simultaneous Admin/Customer cookies and all data survive web force-recreate.',flush=True)

def payment_smoke():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());c=gs.client();sign_in(c,accounts[2]);sign_in(c,accounts[0],True)
    path='/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen';p=gs.get(c,path)[0]
    assert gs.post(c,'/Admin/CaiDatCuaHang/LuuTaiKhoanNganHang',p,{'Bank.ExpectedVersion':om.qa_sql('SELECT Version FROM PaymentShippingSettings'),'Bank.BankBin':'970436','Bank.AccountNumber':'0000000000000000000','Bank.AccountHolderName':'QA KHONG CHUYEN TIEN','Bank.VietQrEnabled':'true','Bank.BankDetailsChecked':'true'})[0]==302
    assert gs.post(c,'/Admin/CaiDatCuaHang/LuuChinhSachVanChuyen',p,{'Shipping.ExpectedVersion':om.qa_sql('SELECT Version FROM PaymentShippingSettings'),'Shipping.FlatShippingFee':30000,'Shipping.FreeShippingThreshold':300000})[0]==302
    # A prior stock/price CAS regression may legitimately edit Product 1.
    # Own the priced fixture so this test still proves an exact 100k + 30k checkout.
    pid=int(om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity) VALUES ('QA Portal Payment',100000,'/images/product-placeholder.svg','QA isolated bank checkout',10); SELECT LAST_INSERT_ID()"))
    page,values=gs.confirm(c,pid);values['PaymentMethod']='VIETQR';stock=int(om.qa_sql(f'SELECT StockQuantity FROM Products WHERE Id={pid}'))
    code,h,_=gs.post(c,f'/ThanhToan/XacNhanMuaHang/{pid}',page,values);assert code==302 and '/ThanhToan/ThanhToanVietQR/' in h['Location'];oid=int(h['Location'].rsplit('/',1)[1])
    p,body,_=gs.get(c,h['Location']);assert 'img.vietqr.io/image/' in body
    assert om.qa_sql(f'SELECT UserId,IsPaid,Total FROM Orders WHERE Id={oid}')=='3\t0\t130000.00'
    assert gs.post(c,f'/ThanhToan/ThongBaoDaChuyenKhoan/{oid}',p,{'ExpectedVersion':0})[0]==302
    assert om.qa_sql(f'SELECT IsPaid,CustomerTransferNotifiedAt IS NOT NULL FROM Orders WHERE Id={oid}')=='0\t1'
    p=gs.get(c,f'/Admin/DonHang/ChiTietDonHang/{oid}')[0]
    assert gs.post(c,f'/Admin/DonHang/XacNhanDaNhanTien/{oid}',p,{'ExpectedVersion':1,'Note':'QA fake bank evidence only; no real transfer'})[0]==302
    assert om.qa_sql(f'SELECT IsPaid,PaymentConfirmedById,Status FROM Orders WHERE Id={oid}')=='1\t1\t0'
    assert int(om.qa_sql(f'SELECT StockQuantity FROM Products WHERE Id={pid}'))==stock-1
    assert om.qa_sql(f'SELECT COUNT(*) FROM OrderStatusHistories WHERE OrderId={oid} AND Kind=4 AND AdminId IS NULL')=='1'
    assert 'Đã thanh toán' in gs.get(c,f'/ThanhToan/ThanhToanVietQR/{oid}')[1]
    import urllib.request
    response=c.open(gs.BASE+f'/Admin/DonHang/XuatExcelDonHang?search=GS-{oid:06d}&paymentMethod=VIETQR&paymentState=paid')
    assert response.status==200 and response.headers['Content-Type'].startswith('application/vnd.openxmlformats') and response.read().startswith(b'PK')
    (OUT/'payment-results.json').write_text(json.dumps({'status':'PASS','checks':'One cookie jar holds Admin 1 + Customer 3: protected bank settings, actual VietQR checkout with fee/owner/stock, owner notification without Paid, Admin manual confirmation/audit, Customer paid page and real Excel download; only fake bank/QA fixtures'}))
    print('PASS: COD/browser and VietQR/settings/notify/payment/Excel flows retain the correct per-route identity in one shared cookie jar.',flush=True)

def production():
    client=gs.client()
    for path in ('/','/Account/Login',ADMIN_LOGIN,'/SanPham/CuaHang'):
        assert gs.request(client,path)[0]==200,path
    for path in ('/Admin/DonHang/QuanLyDonHang','/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen'):
        code,h,_=gs.request(client,path);assert code==302 and ADMIN_LOGIN in h['Location']
    code,h,_=gs.request(client,'/ThanhToan/DonHangCuaToi');assert code==302 and '/Account/Login' in h['Location'] and ADMIN_LOGIN not in h['Location']
    verify_migrations(gs.sql)
    assert 'healthy' in gs.compose('ps','web_app','db')
    image=lambda c:subprocess.check_output(['docker','inspect','--format','{{.Image}}',c],text=True).strip()
    current=image(gs.compose('ps','-q','web_app'));assert current==image(om.qa_compose('ps','-q','web_app'))
    (OUT/'production-results.json').write_text(json.dumps({'status':'PASS','image':current,'checks':'Public/login HTTP 200; Admin and Customer challenges target separate login portals; HTTPS/no 502 and web/DB healthy; migration IDs match source; same image as authenticated QA; production read-only'}))
    print('PASS: Deployed tested image; separate login/challenge routes, HTTPS and healthy web/DB; no new migration or real-data writes.',flush=True)

def expired_browser():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());revoker=gs.client();sign_in(revoker,accounts[0],True)
    oid=om.qa_sql('SELECT Id FROM Orders WHERE Status=3 AND PaymentMethod=\'COD\' ORDER BY Id DESC LIMIT 1');assert oid
    def role(target):
        p=gs.get(revoker,'/Admin/NguoiDung/ChiTietNguoiDung/2')[0]
        assert gs.post(revoker,'/Admin/NguoiDung/ThayDoiVaiTro/2',p,{'ExpectedVersion':om.qa_sql('SELECT Version FROM Users WHERE Id=2'),'TargetRole':target})[0]==302
    before={t:hashlib.sha256(om.qa_sql('SELECT * FROM '+t+' ORDER BY Id').encode()).hexdigest() for t in ('Orders','OrderStatusHistories','Products')}
    with playwright() as pw:
        from playwright.sync_api import expect
        b=pw.chromium.launch();ctx=b.new_context(ignore_https_errors=True);admin=ctx.new_page();customer=ctx.new_page()
        login_page(admin,accounts[1],ADMIN_LOGIN);admin.goto(om.QA_BASE+f'/Admin/DonHang/ChiTietDonHang/{oid}')
        admin.get_by_role('button',name='Bắt đầu xử lý',exact=True).click();login_page(customer,accounts[2])
        role(0)
        try:
            admin.locator('#orderConfirmSubmit').click();expect(admin).to_have_url(__import__('re').compile('/Admin/Account/Login'))
            customer.goto(om.QA_BASE+'/ThanhToan/DonHangCuaToi');assert customer.url.endswith('/ThanhToan/DonHangCuaToi') and 'QA Order User 3' in customer.locator('body').inner_text()
            admin.screenshot(path=str(OUT/'revoked-admin-customer-stays.png'),full_page=True)
        finally:role(1)
        ctx.close();b.close()
    after={t:hashlib.sha256(om.qa_sql('SELECT * FROM '+t+' ORDER BY Id').encode()).hexdigest() for t in ('Orders','OrderStatusHistories','Products')};assert before==after
    (OUT/'expired-browser-results.json').write_text(json.dumps({'status':'PASS','checks':'In one browser context, revoked Admin AJAX action returns to Admin login; Customer tab stays authenticated; order/audit/stock unchanged; only QA Admin role revoked/restored'}))
    print('PASS: Revoked Admin stale AJAX action redirects to Admin login while the Customer tab remains signed in; no business changes.',flush=True)

def remaining():
    for check in (expired_browser,payment_smoke,persistence):
        gs.compose=MAIN_COMPOSE
        check()

def navigation():
    """Admin preview reuses its ticket; all mutations and purchases remain QA-only."""
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());checks=[]
    def passed(label):checks.append(label);print('PASS: '+label,flush=True)
    category=om.qa_sql("SELECT Id FROM Categories WHERE Name='QA Navigation'")
    if not category:category=om.qa_sql("INSERT INTO Categories (Name,Description,IsActive) VALUES ('QA Navigation','',1); SELECT LAST_INSERT_ID()")
    om.qa_sql(f'UPDATE Products SET CategoryId={category} WHERE Id=1')
    before=table_hashes(om.qa_sql)
    with playwright() as pw:
        from playwright.sync_api import expect
        b=pw.chromium.launch();ctx=b.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});p=ctx.new_page();errors=[];bad=[]
        p.on('pageerror',lambda e:errors.append(str(e)))
        p.on('response',lambda r:bad.append((r.status,r.url)) if r.url.startswith(om.QA_BASE) and r.request.resource_type in ('script','stylesheet','font') and r.status>=400 else None)
        login_page(p,accounts[0],ADMIN_LOGIN);expect(p).to_have_url(om.QA_BASE+'/Admin/Admin/TongQuan')
        auth=lambda:{c['name']:c['value'] for c in ctx.cookies() if c['name'] in (ADMIN_COOKIE,CUSTOMER_COOKIE)}
        original=auth();assert set(original)=={ADMIN_COOKIE}
        p.get_by_role('link',name='Xem website',exact=True).click();expect(p.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 1')
        assert auth()==original and p.locator('a[href*="/Account/Login"],a[href*="/Account/Register"]').count()==0
        expect(p.get_by_role('link',name='Quay lại quản trị',exact=True)).to_be_visible()
        p.get_by_role('link',name='Quay lại quản trị',exact=True).click();expect(p).to_have_url(om.QA_BASE+'/Admin/Admin/TongQuan')
        passed('Admin Dashboard -> Xem website -> Quay lại quản trị uses the same Admin/account/cookie; no Customer cookie, role change or second login')
        for path in ('/?portal=admin','/SanPham/CuaHang?portal=admin',f'/SanPham/CuaHang?categoryId={category}&portal=admin','/SanPham/ChiTietSanPham/1?portal=admin'):
            assert p.goto(om.QA_BASE+path).status==200
            expect(p.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 1')
            assert p.locator('form[action*="GioHang"],form[action*="ThanhToan"],a[href*="GioHang"],a[href*="ThanhToan"]').count()==0
            expect(p.get_by_role('link',name='Quay lại quản trị',exact=True)).to_be_visible()
        p.get_by_role('button',name='Mở tìm kiếm',exact=True).click();p.locator('#header-search').fill('QA');p.locator('#shop-search-dialog button[type=submit]').click()
        assert 'portal=admin' in p.url;expect(p.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 1')
        detail=p.locator('.product-link').first;assert 'portal=admin' in detail.get_attribute('href');detail.click();expect(p.locator('.shop-admin-note')).to_be_visible()
        passed('Server-rendered Admin name/return link on home/catalog/category/detail/search; preview follows GET forms and links; purchasing controls absent')
        for width in (320,360,768,1024,1440):
            p.set_viewport_size({'width':width,'height':1000});p.goto(om.QA_BASE+'/?portal=admin')
            assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            if width<768:p.get_by_role('button',name='Mở menu điều hướng',exact=True).click()
            link=p.get_by_role('link',name='Quay lại quản trị',exact=True);expect(link).to_be_visible();link.focus();assert link.evaluate('(e)=>document.activeElement===e')
            p.screenshot(path=str(OUT/f'navigation-admin-{width}.png'),full_page=True)
            link.press('Enter');expect(p).to_have_url(om.QA_BASE+'/Admin/Admin/TongQuan');assert auth()==original
        p.emulate_media(reduced_motion='reduce');p.goto(om.QA_BASE+'/?portal=admin');link=p.locator('.shop-account-nav .shop-admin-return')
        assert link.evaluate('(e)=>getComputedStyle(e).transitionDuration')=='0s'
        assert not errors and not bad,(errors,bad)
        passed('Admin desktop/mobile 320-1440 px, keyboard/focus/reduced motion, no overflow, missing CSS/JS/font or browser errors')
        p.set_viewport_size({'width':1440,'height':1000});p.emulate_media(reduced_motion='no-preference')
        # Same context, genuine independent accounts, explicit Admin preview remains Admin.
        customer=ctx.new_page();login_page(customer,accounts[2]);customer.goto(om.QA_BASE+'/')
        expect(customer.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 3');assert customer.locator('.shop-admin-return').count()==0
        p.goto(om.QA_BASE+'/Admin/Admin/TongQuan');p.get_by_role('link',name='Xem website',exact=True).click()
        expect(p.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 1');p.locator('.product-link').first.click()
        expect(p.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 1')
        customer.reload();expect(customer.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 3')
        assert auth()[ADMIN_COOKIE]==original[ADMIN_COOKIE] and set(auth())=={ADMIN_COOKIE,CUSTOMER_COOKIE}
        p.locator('.account-menu summary').click();p.locator('.account-menu button[type=submit]').click();expect(p).to_have_url(__import__('re').compile('/Admin/Account/Login'))
        assert set(auth())=={CUSTOMER_COOKIE};customer.reload();expect(customer.locator('.account-menu .menu-user-name')).to_have_text('QA Order User 3')
        passed('Admin and Customer tabs keep separate identities; preview remains Admin through links; storefront Admin logout removes only Admin cookie')
        ctx.close()
        for account in (None,accounts[2]):
            c=b.new_context(ignore_https_errors=True);page=c.new_page()
            if account:login_page(page,account)
            page.goto(om.QA_BASE+'/?portal=admin&role=Admin&UserId=1');assert page.locator('.shop-admin-return').count()==0
            page.goto(om.QA_BASE+'/Admin/Admin/TongQuan');expect(page).to_have_url(__import__('re').compile('/Admin/Account/Login'))
            c.close()
        b.close()
    assert table_hashes(om.qa_sql)==before
    passed('Customer/Anonymous cannot expose Admin controls or enter Dashboard using query parameters; browsing/login/logout changes no business rows')
    a=gs.client();sign_in(a,accounts[0],True);source=gs.get(a,'/?portal=admin')[0]
    for path in ('/GioHang/QuanLyGioHang','/ThanhToan/XacNhanMuaHang/1','/ThanhToan/XacNhanGioHang','/ThanhToan/DonHangCuaToi'):
        code,h,_=gs.request(a,path+'?portal=admin');assert code in (302,403) and (code==403 or 'AccessDenied' in h.get('Location','')),(path,code,h.get('Location'))
    for path in ('/GioHang/ThemVaoGioHang/1','/GioHang/CapNhatSoLuong/1','/GioHang/XoaKhoiGioHang/1','/ThanhToan/MuaNgay/1','/ThanhToan/XacNhanMuaHang/1','/ThanhToan/XacNhanGioHang','/ThanhToan/ThongBaoDaChuyenKhoan/1'):
        code,h,_=gs.post(a,path+'?portal=admin',source,{'Quantity':1,'ExpectedVersion':0});assert code in (302,403) and (code==403 or 'AccessDenied' in h.get('Location','')),(path,code,h.get('Location'))
    assert table_hashes(om.qa_sql)==before and 'QA Order User 1' in gs.get(a,'/Admin/Admin/TongQuan')[1]
    passed('Authenticated Admin GET/POST cart, Buy Now, checkout and transfer endpoints are forbidden with valid CSRF; every table/stock/order unchanged')
    # A second genuine Customer cookie does not bypass the selected Admin preview's restrictions.
    sign_in(a,accounts[2]);source=gs.get(a,'/?portal=admin')[0]
    assert 'QA Order User 1' in gs.get(a,'/?portal=admin')[1] and 'QA Order User 3' in gs.get(a,'/')[1]
    code,h,_=gs.post(a,'/ThanhToan/MuaNgay/1?portal=admin',source,{'Quantity':1});assert code==302 and 'AccessDenied' in h['Location']
    assert table_hashes(om.qa_sql)==before
    buyer=gs.client();sign_in(buyer,accounts[2]);page=gs.get(buyer,'/SanPham/ChiTietSanPham/1')[0]
    assert gs.post(buyer,'/GioHang/ThemVaoGioHang/1',page,{'Quantity':1})[0]==302
    page=gs.get(buyer,'/ThanhToan/XacNhanGioHang')[0];stock=int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))
    values={name:page.input(name) for name in ('QuotedPrice','PolicyVersion','CartQuote','ConfirmationToken')}
    values.update({'Quantity':1,'RecipientName':'QA Navigation Customer','Phone':'0912345678','Address':'123 QA Navigation Address','PaymentMethod':'COD'})
    code,h,_=gs.post(buyer,'/ThanhToan/XacNhanGioHang',page,values);assert code==302 and '/ThanhToan/ChiTietDonHang/' in h['Location']
    assert int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1'))==stock-1
    assert 'QA Navigation Customer' in gs.get(buyer,h['Location'])[1]
    passed('Customer cart and real COD checkout still work; selected Admin preview cannot borrow the simultaneous Customer cookie to buy')
    (OUT/'navigation-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'writes':'synthetic isolated QA only'},indent=2))

if __name__=='__main__':
    {'baseline':baseline,'prepare':prepare,'reproduce':reproduce,'refresh':refresh,'browser':browser_checks,'security':security,'expired-browser':expired_browser,'payment':payment_smoke,'navigation':navigation,'persistence':persistence,'remaining':remaining,'preservation':preservation,'production':production,'teardown':om.teardown}[sys.argv[1]]()
