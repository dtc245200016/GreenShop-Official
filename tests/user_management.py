from qa_support import PRIVATE, PROJECT
"""User security/UI QA in a separate Compose project. Never change real accounts."""
import json
import os
from pathlib import Path
import sys
import http.cookiejar
import ssl
import urllib.request
import concurrent.futures
import secrets
import re
import subprocess
import urllib.parse
import urllib.error
import copy
import order_management as om
import storefront_regression as gs

OUT=PRIVATE/'qa'
OUT.mkdir(mode=0o700,exist_ok=True)
om.OUT = OUT
om.QA_PROJECT=PROJECT

def prepare():
    om.prepare()

def upgrade_qa():
    import m1_acceptance as acceptance
    acceptance.migration_upgrade()

def save_legacy_sessions():
    raise RuntimeError("Historical pre-account-status cookies require an archived source image; use m1 migration and regression security instead.")

def legacy_client(name):
    jar=http.cookiejar.MozillaCookieJar(str(OUT/f'legacy-{name}.cookies'))
    jar.load(ignore_discard=True,ignore_expires=True)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),gs.NoRedirect(),urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),urllib.request.HTTPCookieProcessor(jar))

USER_BASE='/Admin/NguoiDung'

def change(client,uid,action,values=None):
    page=gs.get(client,f'{USER_BASE}/ChiTietNguoiDung/{uid}')[0]
    data={'ExpectedVersion':int(om.qa_sql(f'SELECT Version FROM Users WHERE Id={uid}'))}
    data.update(values or {})
    return gs.post(client,f'{USER_BASE}/{action}/{uid}',page,data)

def fixture_customer(label):
    password=secrets.token_urlsafe(24)
    email=f'qa-user-{label}-{secrets.token_hex(6)}@example.invalid'.lower()
    client=gs.client()
    form=gs.get(client,'/Account/Register')[0]
    result=gs.post(client,'/Account/Register',form,{'FullName':f'QA {label}','Email':email,'Phone':'0912345678','Password':password,'ConfirmPassword':password,'Role':1,'IsActive':False})
    assert result[0]==302
    uid=int(om.qa_sql('SELECT Id FROM Users WHERE Email='+gs.quote(email)))
    assert om.qa_sql(f'SELECT Role,IsActive FROM Users WHERE Id={uid}')=='0\t1'
    gs.login(client,[email,password])
    return uid,[email,password],client

def business(check_legacy=True):
    om.configure_qa()
    checks=[]
    def passed(message):
        checks.append(message); print('PASS: '+message,flush=True)
    compatibility=OUT/'legacy-compatibility-results.json'
    if check_legacy and not compatibility.exists():
        legacy_admin,legacy_customer=legacy_client('admin'),legacy_client('customer')
        gs.get(legacy_admin,USER_BASE+'/QuanLyNguoiDung')
        gs.get(legacy_customer,'/ThanhToan/ChiTietDonHang/1')
        assert om.qa_sql('SELECT COUNT(*) FROM Users WHERE Id IN (1,2,3) AND IsActive=1 AND Version=0 AND SessionVersion=0')=='3'
        compatibility.write_text(json.dumps({'status':'PASS','checks':'Genuine pre-migration Admin/Customer cookies accepted, old accounts active; persistent QA keys reused'},indent=2))
    if check_legacy: passed('Additive migration keeps existing users active; genuine Admin/Customer pre-migration cookies still work with persistent keys')
    admins=om.admin_sessions()
    a1,a2=admins
    anon=gs.client()
    uid,account,buyer=fixture_customer('Security')
    for path in ('QuanLyNguoiDung','ChiTietNguoiDung/1','CapNhatThongTinNguoiDung/1','ThayDoiVaiTro/1','KhoaTaiKhoan/1','MoKhoaTaiKhoan/1'):
        for client in (anon,buyer):
            code=gs.request(client,USER_BASE+'/'+path,None if path.startswith(('QuanLy','ChiTiet')) else {})[0]
            assert code==302,(path,code)
    page=gs.get(a1,f'{USER_BASE}/ChiTietNguoiDung/{uid}')[0]
    for action in ('CapNhatThongTinNguoiDung','ThayDoiVaiTro','KhoaTaiKhoan','MoKhoaTaiKhoan'):
        assert gs.request(a1,f'{USER_BASE}/{action}/{uid}')[0]==405
        assert gs.request(a1,f'{USER_BASE}/{action}/{uid}',{'ExpectedVersion':0,'TargetRole':1})[0]==400
        assert gs.post(buyer,f'{USER_BASE}/{action}/{uid}',page,{'ExpectedVersion':0,'TargetRole':1})[0]==302
    assert gs.request(a1,f'{USER_BASE}/ChiTietNguoiDung/9999999')[0]==404
    for query in ('Role=99','Active=invalid','Page=0','PageSize=999','Sort=bad','Search='+'x'*101):
        assert gs.request(a1,USER_BASE+'/QuanLyNguoiDung?'+query)[0]==400
    for data in ({'TargetRole':99},{'TargetRole':-1}): assert change(a1,uid,'ThayDoiVaiTro',data)[0]==400
    assert gs.post(a1,f'{USER_BASE}/ThayDoiVaiTro/{uid}',page,{'ExpectedVersion':0})[0]==400
    digest=om.qa_sql(f'SELECT PasswordHash FROM Users WHERE Id={uid}')
    _,body,_=gs.get(a1,f'{USER_BASE}/ChiTietNguoiDung/{uid}')
    assert digest not in body and 'SessionVersion' not in body and 'PasswordHash' not in body
    passed('Admin authorization, POST-only, antiforgery, missing/invalid inputs; no hash/secret disclosure; registration ignores privilege overposting')
    assert change(a1,uid,'CapNhatThongTinNguoiDung',{'FullName':'QA <script>alert(1)</script>','Phone':'0901234567','Email':'attacker@example.invalid','Role':1,'IsActive':False,'PasswordHash':'forged','CreatedAt':'2000-01-01','Id':1})[0]==302
    fields=om.qa_sql(f'SELECT Email,Role,IsActive,PasswordHash FROM Users WHERE Id={uid}').split('\t')
    assert fields==[account[0],'0','1',digest],{'uid':uid,'role':fields[1],'active':fields[2],'email_unchanged':fields[0]==account[0],'hash_unchanged':fields[3]==digest}
    body=gs.request(a1,f'{USER_BASE}/ChiTietNguoiDung/{uid}')[2]
    assert '&lt;script&gt;' in body and '<script>alert(1)</script>' not in body
    assert change(a2,uid,'CapNhatThongTinNguoiDung',{'FullName':'Stale overwrite','Phone':'','ExpectedVersion':0})[0]==409
    assert change(a1,uid,'CapNhatThongTinNguoiDung',{'FullName':' '*10,'Phone':''})[0] in (400,422)
    assert change(a1,uid,'CapNhatThongTinNguoiDung',{'FullName':'x'*101,'Phone':''})[0]==400
    assert change(a1,uid,'CapNhatThongTinNguoiDung',{'FullName':'QA Security','Phone':'bad phone'})[0]==400
    passed('Profile allowlist preserves email/password/role/status/date; escaped names, length/phone validation and stale-write CAS enforced')
    assert change(a1,uid,'CapNhatThongTinNguoiDung',{'FullName':'QA Security','Phone':'0901234567'})[0]==302
    # A genuine order/cart proves locking and role changes do not remove shopping relationships.
    oid=om.create_order(buyer,1,1)
    before=om.qa_sql(f'SELECT Id,UserId,Total,Status FROM Orders WHERE Id={oid}')
    p=gs.get(buyer,'/SanPham/ChiTietSanPham/1')[0]
    assert gs.post(buyer,'/GioHang/ThemVaoGioHang/1',p,{'Quantity':1})[0]==302
    cart=om.qa_sql(f'SELECT Id,ProductId,Quantity FROM CartItems WHERE UserId={uid}')
    assert change(a1,uid,'KhoaTaiKhoan')[0]==302
    for path in ('/GioHang/QuanLyGioHang','/ThanhToan/DonHangCuaToi',USER_BASE+'/QuanLyNguoiDung'):
        assert gs.request(buyer,path)[0]==302
    blocked=gs.client(); form=gs.get(blocked,'/Account/Login')[0]
    assert gs.post(blocked,'/Account/Login',form,{'Email':account[0],'Password':account[1]})[0]==200
    assert gs.request(blocked,'/GioHang/QuanLyGioHang')[0]==302
    # Preserve an untouched copy of a previously issued cookie across a lock/unlock cycle.
    if check_legacy: old=legacy_client('customer')
    else:
        old=gs.client();gs.login(old,json.loads((OUT/'accounts.json').read_text())[2])
    assert change(a1,3,'KhoaTaiKhoan')[0]==302
    assert change(a1,3,'MoKhoaTaiKhoan')[0]==302
    assert gs.request(old,'/ThanhToan/DonHangCuaToi')[0]==302
    assert change(a1,uid,'MoKhoaTaiKhoan')[0]==302
    gs.login(buyer,account)
    assert om.qa_sql(f'SELECT Role,IsActive,PasswordHash FROM Users WHERE Id={uid}')=='0\t1\t'+digest
    assert om.qa_sql(f'SELECT Id,UserId,Total,Status FROM Orders WHERE Id={oid}')==before
    assert om.qa_sql(f'SELECT Id,ProductId,Quantity FROM CartItems WHERE UserId={uid}')==cart
    passed('Locked users cannot login or use existing cookies; unlock preserves role/password/orders/cart; old cookie remains revoked after lock-unlock')
    assert change(a1,uid,'ThayDoiVaiTro',{'TargetRole':1})[0]==302
    assert gs.request(buyer,USER_BASE+'/QuanLyNguoiDung')[0]==302
    promoted=gs.client(); gs.login(promoted,account,expected='/Admin')
    gs.get(promoted,USER_BASE+'/QuanLyNguoiDung')
    assert change(a1,uid,'ThayDoiVaiTro',{'TargetRole':0})[0]==302
    assert gs.request(promoted,USER_BASE+'/QuanLyNguoiDung')[0]==302
    gs.login(promoted,account)
    assert gs.request(promoted,USER_BASE+'/QuanLyNguoiDung')[0]==302
    assert change(a1,1,'KhoaTaiKhoan')[0]==422
    assert change(a1,1,'ThayDoiVaiTro',{'TargetRole':0})[0]==422
    passed('Promotion/demotion require fresh login; stale Admin cookies lose all Admin access; self-lock and self-demotion rejected server-side')
    # Owner and ordinary Admin race; only the owner may change administrator roles.
    pages=[gs.get(admins[i],f'{USER_BASE}/ChiTietNguoiDung/{2 if i==0 else 1}')[0] for i in range(2)]
    versions=[int(om.qa_sql(f'SELECT Version FROM Users WHERE Id={2 if i==0 else 1}')) for i in range(2)]
    def cross(index):
        c=admins[index]; target=2 if index==0 else 1
        return gs.post(c,f'{USER_BASE}/ThayDoiVaiTro/{target}',pages[index],{'TargetRole':0,'ExpectedVersion':versions[index]})
    with concurrent.futures.ThreadPoolExecutor(2) as pool: results=list(pool.map(cross,[0,1]))
    rows=om.qa_sql('SELECT Id FROM Users WHERE Role=1 AND IsActive=1').splitlines()
    assert len(rows)==1,results
    assert rows==["1"],"The protected owner must remain active"
    winner=int(rows[0]); survivor=admins[winner-1]
    assert change(survivor,winner,'KhoaTaiKhoan')[0]==422
    assert change(survivor,winner,'ThayDoiVaiTro',{'TargetRole':0})[0]==422
    loser=2 if winner==1 else 1
    assert change(survivor,loser,'ThayDoiVaiTro',{'TargetRole':1})[0]==302
    # Re-login both legitimate synthetic admins to continue regression testing.
    a1,a2=om.admin_sessions()
    lock_admins=[a1,a2]
    pages=[gs.get(lock_admins[i],f'{USER_BASE}/ChiTietNguoiDung/{2 if i==0 else 1}')[0] for i in range(2)]
    versions=[int(om.qa_sql(f'SELECT Version FROM Users WHERE Id={2 if i==0 else 1}')) for i in range(2)]
    def cross_lock(index):
        c=lock_admins[index]; target=2 if index==0 else 1
        return gs.post(c,f'{USER_BASE}/KhoaTaiKhoan/{target}',pages[index],{'ExpectedVersion':versions[index]})
    with concurrent.futures.ThreadPoolExecutor(2) as pool: results=list(pool.map(cross_lock,[0,1]))
    rows=om.qa_sql('SELECT Id FROM Users WHERE Role=1 AND IsActive=1').splitlines()
    assert len(rows)==1,results
    assert rows==["1"],"An ordinary Admin must never lock the owner"
    winner=int(rows[0]); survivor=a1 if winner==1 else a2; loser=2 if winner==1 else 1
    assert change(survivor,loser,'MoKhoaTaiKhoan')[0]==302
    a1,a2=om.admin_sessions()
    passed('Owner wins cross-demotion/lock races; ordinary Admin cannot change the owner; revoked queued actor cannot proceed')
    # Identical expected versions cannot overwrite a concurrent profile write.
    version=int(om.qa_sql(f'SELECT Version FROM Users WHERE Id={uid}'))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(change,c,uid,'CapNhatThongTinNguoiDung',{'ExpectedVersion':version,'FullName':f'QA Concurrent {i}','Phone':''}) for i,c in enumerate((a1,a2))]
        assert sorted(f.result()[0] for f in futures)==[302,409]
    # Enough legitimately registered customers for real paging (no production seeding).
    for i in range(16): fixture_customer(f'Paging {i:02}')
    _,body,_=gs.get(a1,USER_BASE+'/QuanLyNguoiDung?Role=0&Active=true&Sort=oldest&PageSize=15')
    ids=re.findall(r'data-user-id="(\d+)"',body)
    nextbody=gs.get(a1,USER_BASE+'/QuanLyNguoiDung?Role=0&Active=true&Sort=oldest&PageSize=15&Page=2')[1]
    assert len(ids)==15 and not set(ids).intersection(re.findall(r'data-user-id="(\d+)"',nextbody))
    searched=gs.get(a1,USER_BASE+'/QuanLyNguoiDung?Search='+account[0])[1]
    assert re.findall(r'data-user-id="(\d+)"',searched)==[str(uid)]
    assert 'Không tìm thấy người dùng' in gs.get(a1,USER_BASE+'/QuanLyNguoiDung?Search=definitely-no-matching-user')[1]
    assert str(oid) in gs.get(a1,'/Admin/DonHang/QuanLyDonHang?CustomerId='+str(uid))[1]
    passed('Real database search/role/status/sort/pagination/empty states, exact customer-order linking and concurrent profile writes verified')
    # Wrong passwords and tampered encrypted cookies never authenticate.
    bad=gs.client(); form=gs.get(bad,'/Account/Login')[0]
    assert gs.post(bad,'/Account/Login',form,{'Email':account[0],'Password':'incorrect-random-password'})[0]==200
    assert gs.request(bad,'/GioHang/QuanLyGioHang')[0]==302
    tampered=False
    for handler in a1.handlers:
        if isinstance(handler,urllib.request.HTTPCookieProcessor):
            for cookie in handler.cookiejar:
                if cookie.name=='.AspNetCore.Cookies':
                    cookie.value=('y' if cookie.value.startswith('x') else 'x')+cookie.value[1:];tampered=True
    assert tampered,'The real configured Admin cookie must be present for this test'
    assert gs.request(a1,USER_BASE+'/QuanLyNguoiDung')[0]==302
    passed('Wrong passwords and tampered authentication cookies rejected; no identity bypass')
    (OUT/'user-test-state.json').write_text(json.dumps({'uid':uid,'account':account,'oid':oid}))
    os.chmod(OUT/'user-test-state.json',0o600)
    (OUT/'user-business-results.json').write_text(json.dumps({'status':'PASS','checks':checks},indent=2))

def preservation():
    before = json.loads((OUT/'baseline.json').read_text())
    after = om.real_snapshot()
    for key in ('products','categories','users','images','keys','infrastructure_source','containers','Orders','OrderItems','CartItems'):
        assert before[key] == after[key],key
    for path,digest in before['admin_source'].items():
        if '/SanPham/' in path or '/DanhMuc/' in path or path.endswith(('SanPhamController.cs','DanhMucController.cs')):
            assert after['admin_source'][path] == digest,path
    assert set(before['migrations']).issubset(after['migrations'])
    assert before['infrastructure_source']==after['infrastructure_source']
    if om.gs.sql("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='Users' AND COLUMN_NAME='IsActive'")=='1':
        assert om.gs.sql('SELECT COUNT(*) FROM Users WHERE NOT IsActive OR Version<>0 OR SessionVersion<>0')=='0'
    (OUT/'preservation-results.json').write_text(json.dumps({'status':'PASS','checks':'Original accounts/passwords/roles, orders/items/cart, stock/products/categories, keys/images and other containers unchanged'},indent=2))
    print('PASS: Original accounts/passwords/roles and all real business data preserved.',flush=True)

def production():
    om.production_checks()
    client=gs.client();results={}
    for path in (USER_BASE+'/QuanLyNguoiDung',USER_BASE+'/ChiTietNguoiDung/1'):
        code,headers,_=gs.request(client,path)
        assert code==302 and '/Account/Login' in headers.get('Location',''),(path,code)
        results[path]='302: login required'
    for action in ('CapNhatThongTinNguoiDung','ThayDoiVaiTro','KhoaTaiKhoan','MoKhoaTaiKhoan'):
        code,headers,_=gs.request(client,USER_BASE+'/'+action+'/1',{'ExpectedVersion':0})
        assert code==302 and '/Account/Login' in headers.get('Location',''),(action,code)
        results[action]='302: login required'
    for path in ('/css/admin-users.css','/css/admin-orders.css','/js/admin-orders.js'):
        code,_,body=gs.request(client,path)
        assert code==200 and len(body)>100,(path,code)
        results[path]=200
    assert gs.sql("SELECT COUNT(*) FROM __EFMigrationsHistory WHERE MigrationId='20261011131858_AddUserAccountStatus'")=='1'
    assert gs.sql('SELECT COUNT(*) FROM Users WHERE NOT IsActive OR Version<>0 OR SessionVersion<>0')=='0'
    gs.compose('exec','-T','nginx','nginx','-t')
    (OUT/'production-user-results.json').write_text(json.dumps({'status':'PASS','routes':results,'migration':'AddUserAccountStatus applied','writes':'none','scope':'Anonymous guards and static assets on production; authenticated operations tested on isolated identical image'},indent=2))
    print('PASS: Production User GET/POST routes require login, assets serve 200, migration applied with existing accounts active, nginx configuration valid. No real user/order writes.',flush=True)

def outage():
    om.configure_qa()
    admins=om.admin_sessions();admin=admins[0]
    page=gs.get(admin,USER_BASE+'/ChiTietNguoiDung/3')[0]
    before=om.qa_sql('SELECT Id,Role,IsActive,Version,SessionVersion FROM Users ORDER BY Id')
    payload=urllib.parse.urlencode({'__RequestVerificationToken':page.input('__RequestVerificationToken'),'ExpectedVersion':int(om.qa_sql('SELECT Version FROM Users WHERE Id=3')),'TargetRole':1}).encode()
    db=om.qa_compose('ps','-q','db')
    details=json.loads(subprocess.check_output(['docker','inspect',db],text=True))[0]
    assert details['Config']['Labels']['com.docker.compose.project']==om.QA_PROJECT
    network=next(iter(details['NetworkSettings']['Networks']))
    assert network.startswith(om.QA_PROJECT+'_')
    try:
        subprocess.run(['docker','network','disconnect',network,db],check=True)
        request=urllib.request.Request(om.QA_BASE+USER_BASE+'/ThayDoiVaiTro/3',data=payload)
        try: response=admin.open(request,timeout=180)
        except urllib.error.HTTPError as error: response=error
        body=response.read().decode();assert response.code==503,(response.code,body[:80])
        assert 'Chưa thể xác minh phiên đăng nhập' in body
    finally:
        subprocess.run(['docker','network','connect','--alias','db',network,db],check=True)
    assert om.qa_sql('SELECT Id,Role,IsActive,Version,SessionVersion FROM Users ORDER BY Id')==before
    gs.get(admin,USER_BASE+'/QuanLyNguoiDung')
    print('PASS: Database unavailable -> sensitive POST returns 503 without using stale claims or changing any user; existing cookie works again after connection restored.',flush=True)
    (OUT/'outage-results.json').write_text(json.dumps({'status':'PASS','checks':['Unavailable database denies sensitive action (503)','All account roles/status/versions unchanged','Existing unrelated cookie remains valid after recovery'],'database':'isolated only'},indent=2))

def additional_security():
    om.configure_qa()
    admin=om.admin_sessions()[0]
    uid,account,buyer=fixture_customer('Cookie POST guard')
    source=gs.get(buyer,'/SanPham/ChiTietSanPham/1')[0]
    def clone():
        client=gs.client()
        source_jar=next(h.cookiejar for h in buyer.handlers if isinstance(h,urllib.request.HTTPCookieProcessor))
        target_jar=next(h.cookiejar for h in client.handlers if isinstance(h,urllib.request.HTTPCookieProcessor))
        for cookie in source_jar: target_jar.set_cookie(copy.copy(cookie))
        return client
    cart_client,buy_client=clone(),clone()
    stock=om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1')
    assert change(admin,uid,'KhoaTaiKhoan')[0]==302
    for client,path in ((cart_client,'/GioHang/ThemVaoGioHang/1'),(buy_client,'/ThanhToan/MuaNgay/1')):
        code,headers,_=gs.post(client,path,source,{'Quantity':1})
        assert code in (302,400),(path,code)
        if code==302: assert '/Account/Login' in headers.get('Location','')
    assert om.qa_sql(f'SELECT COUNT(*) FROM CartItems WHERE UserId={uid}')=='0'
    assert om.qa_sql(f'SELECT COUNT(*) FROM Orders WHERE UserId={uid}')=='0'
    assert om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1')==stock
    assert change(admin,uid,'MoKhoaTaiKhoan')[0]==302
    gs.login(buyer,account)
    # Only this freshly registered, owned synthetic fixture with no relationships is removed.
    assert om.qa_sql(f'SELECT COUNT(*) FROM Users WHERE Id={uid} AND Email={gs.quote(account[0])} AND Role=0')=='1'
    om.qa_sql(f'DELETE FROM Users WHERE Id={uid} AND Email={gs.quote(account[0])} AND Role=0')
    assert gs.request(buyer,'/ThanhToan/DonHangCuaToi')[0]==302
    gs.get(admin,USER_BASE+'/QuanLyNguoiDung')
    (OUT/'additional-security-results.json').write_text(json.dumps({'status':'PASS','checks':['First request using locked cookie cannot POST Cart/Buy Now; no cart/order/stock change','Cookie referencing missing synthetic user rejected','Unrelated Admin cookie stays valid'],'database':'isolated only'},indent=2))
    print('PASS: Locked cookies cannot make first-request Cart/Buy Now POST; no stock/order/cart effects; missing-account cookie rejected; unrelated Admin session kept.',flush=True)

def browser():
    om.configure_qa()
    from playwright.sync_api import sync_playwright,expect
    state=json.loads((OUT/'user-test-state.json').read_text())
    accounts=json.loads((OUT/'accounts.json').read_text())
    checks=[]
    def passed(message): checks.append(message); print('PASS: '+message,flush=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000})
        page=context.new_page(); errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(om.QA_BASE+'/Account/Login')
        page.locator('[name=Email]').fill(accounts[0][0]);page.locator('[name=Password]').fill(accounts[0][1])
        page.locator('form:has(#Email) button[type=submit]').click()
        expect(page).to_have_url(re.compile(r'/Admin/Admin/TongQuan$'))
        page.locator('.admin-sidebar').get_by_role('link',name='Người dùng & Phân quyền',exact=True).click()
        expect(page.locator('.admin-sidebar [aria-current=page]')).to_contain_text('Người dùng')
        for width in (1440,768,360):
            page.set_viewport_size({'width':width,'height':1000})
            for label,path in (('list',USER_BASE+'/QuanLyNguoiDung'),('detail',f'{USER_BASE}/ChiTietNguoiDung/{state["uid"]}'),('empty',USER_BASE+'/QuanLyNguoiDung?Search=no-such-user-browser')):
                page.goto(om.QA_BASE+path)
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),(width,label)
                text=page.locator('.order-admin').inner_text()
                assert not re.search(r'@(if|foreach|Model|\{)',text),(width,label)
                page.screenshot(path=str(OUT/f'admin-user-{label}-{width}.png'),full_page=True,animations='disabled')
        passed('Real User list/detail/empty screens and active sidebar at 1440/768/360 px; no viewport overflow or unrendered Razor')
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto(om.QA_BASE+USER_BASE+'/QuanLyNguoiDung')
        page.locator('#userSearch').fill('QA Paging')
        page.locator('#userRole').select_option('0');page.locator('#userActive').select_option('true')
        page.locator('#userSort').select_option('oldest');page.get_by_role('button',name='Áp dụng bộ lọc').click()
        expect(page.locator('tbody tr')).to_have_count(15)
        page.get_by_role('link',name='Trang tiếp',exact=True).click()
        expect(page).to_have_url(re.compile('page=2')); assert 'role=0' in page.url.lower() and 'active=true' in page.url.lower() and 'sort=oldest' in page.url.lower()
        page.goto(om.QA_BASE+f'{USER_BASE}/ChiTietNguoiDung/{state["uid"]}')
        page.get_by_role('link',name='Xem đơn của người dùng',exact=True).click()
        expect(page).to_have_url(re.compile('customerId='+str(state['uid'])))
        page.get_by_role('button',name='Áp dụng bộ lọc').click()
        assert 'customerId='+str(state['uid']) in page.url
        passed('User search/role/status/sort/pagination and exact related-order filter run against database and survive filter submits')
        page.goto(om.QA_BASE+f'{USER_BASE}/ChiTietNguoiDung/{state["uid"]}')
        page.set_viewport_size({'width':1440,'height':700})
        page.locator('#FullName').fill('QA Browser Profile')
        page.evaluate('window.scrollTo(0,200)')
        page.get_by_role('button',name='Lưu thay đổi',exact=True).scroll_into_view_if_needed()
        scroll=page.evaluate('window.scrollY')
        page.get_by_role('button',name='Lưu thay đổi',exact=True).click()
        expect(page.locator('h1')).to_have_text('QA Browser Profile')
        assert abs(page.evaluate('window.scrollY')-scroll)<=2
        expect(page.locator('.admin-action-feedback')).to_contain_text('Đã lưu')
        page.locator('#FullName').fill('QA retained invalid draft')
        page.locator('#Phone').fill('invalid phone')
        page.get_by_role('button',name='Lưu thay đổi',exact=True).click()
        expect(page.locator('#phoneError')).to_contain_text('Số điện thoại không hợp lệ')
        expect(page.locator('#FullName')).to_have_value('QA retained invalid draft')
        expect(page.locator('#Phone')).to_have_value('invalid phone')
        page.locator('#FullName').fill('QA Browser Profile');page.locator('#Phone').fill('0901234567')
        page.get_by_role('button',name='Lưu thay đổi',exact=True).click()
        expect(page.locator('.admin-action-feedback')).to_contain_text('Đã lưu')
        page.get_by_role('button',name='Khóa tài khoản',exact=True).click()
        dialog=page.locator('#orderConfirmDialog');expect(dialog).to_be_visible()
        expect(dialog).to_contain_text(state['account'][0]);expect(page.locator('#orderConfirmSubmit')).to_have_text('Xác nhận khóa tài khoản')
        for _ in range(8):
            page.keyboard.press('Tab');assert page.evaluate('document.querySelector("#orderConfirmDialog").contains(document.activeElement)')
        page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
        expect(page.get_by_role('button',name='Khóa tài khoản',exact=True)).to_be_focused()
        page.get_by_role('button',name='Khóa tài khoản',exact=True).click()
        page.screenshot(path=str(OUT/'admin-user-lock-confirm.png'),animations='disabled')
        page.locator('#orderConfirmSubmit').click()
        expect(page.locator('.user-aside')).to_contain_text('Đã khóa')
        page.get_by_role('button',name='Mở khóa tài khoản',exact=True).click();page.locator('#orderConfirmSubmit').click()
        expect(page.locator('.user-aside')).to_contain_text('Đang hoạt động')
        page.locator('#TargetRole').select_option('1');page.get_by_role('button',name='Đổi quyền',exact=True).click()
        expect(dialog).to_contain_text('từ Khách hàng sang Quản trị viên')
        expect(page.locator('#orderConfirmSubmit')).to_have_text('Cấp quyền quản trị viên')
        page.locator('#orderConfirmSubmit').click();expect(page.locator('.user-aside .user-role')).to_have_text('Quản trị viên')
        page.locator('#TargetRole').select_option('0');page.get_by_role('button',name='Đổi quyền',exact=True).click()
        expect(page.locator('#orderConfirmSubmit')).to_have_text('Chuyển thành khách hàng')
        page.locator('#orderConfirmSubmit').click();expect(page.locator('.user-aside .user-role')).to_have_text('Khách hàng')
        page.goto(om.QA_BASE+USER_BASE+'/ChiTietNguoiDung/1')
        expect(page.get_by_role('button',name='Khóa tài khoản',exact=True)).to_have_count(0)
        expect(page.get_by_role('button',name='Đổi quyền',exact=True)).to_have_count(0)
        passed('Actual profile/lock/unlock/promotion/demotion submits, clear consequence/account/role confirmation, keyboard/Escape/focus and self protection; AJAX preserves scroll')
        # Do not mutate the legacy order: inspect/explain it before order regression runs.
        page.goto(om.QA_BASE+'/Admin/DonHang/ChiTietDonHang/1')
        expect(page.locator('.order-legacy-check')).to_contain_text('không trừ thêm hàng')
        page.get_by_role('button',name='Ghi nhận đơn đã trừ kho',exact=True).click()
        expect(page.locator('#orderConfirmSubmit')).to_have_text('Ghi nhận đơn đã trừ kho')
        page.screenshot(path=str(OUT/'admin-order-legacy-explanation.png'),animations='disabled')
        page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
        buyer=gs.client();gs.login(buyer,state['account'])
        oid=om.create_order(buyer,1,1)
        for width in (1440,768,360):
            page.set_viewport_size({'width':width,'height':1000})
            page.goto(om.QA_BASE+f'/Admin/DonHang/ChiTietDonHang/{oid}')
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
            page.screenshot(path=str(OUT/f'admin-order-reorganized-{width}.png'),full_page=True,animations='disabled')
        page.set_viewport_size({'width':1440,'height':800})
        page.goto(om.QA_BASE+f'/Admin/DonHang/ChiTietDonHang/{oid}')
        # Measure actual element/scroll displacement while opening and closing native modal.
        button=page.locator('.order-action-panel').get_by_role('button',name='Xác nhận đơn',exact=True)
        before=button.bounding_box(); scroll=page.evaluate('window.scrollY')
        button.click();expect(dialog).to_be_visible()
        during=button.bounding_box()
        assert abs(before['x']-during['x'])<=1 and abs(before['y']-during['y'])<=1,(before,during)
        page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
        after=button.bounding_box();assert abs(before['x']-after['x'])<=1 and abs(page.evaluate('window.scrollY')-scroll)<=1
        button.click();page.locator('#orderConfirmSubmit').click()
        expect(page.locator('.order-steps [aria-current=step]')).to_contain_text('Đã xác nhận')
        assert abs(page.evaluate('window.scrollY')-scroll)<=1
        page.get_by_role('button',name='Hủy đơn hàng',exact=True).click();expect(page.locator('#orderConfirmSubmit')).to_have_text('Hủy đơn và hoàn kho')
        page.locator('#orderReason').fill('QA Browser smooth cancellation');page.locator('#orderConfirmSubmit').click()
        expect(page.locator('.order-cancelled-message')).to_be_visible()
        page.emulate_media(reduced_motion='reduce')
        page.get_by_role('button',name='Lưu ghi chú',exact=True).focus()
        assert page.locator('.order-btn').first.evaluate('e=>getComputedStyle(e).transitionDuration')=='0s'
        passed('Reorganized order actions and understandable legacy explanation; modal open/close geometry and scroll stable; real confirm/cancel retain position; reduced motion')
        assert not errors,errors
        passed('No browser JavaScript errors; all sensitive fixtures isolated')
        context.close();browser.close()
    (OUT/'user-browser-results.json').write_text(json.dumps({'status':'PASS','checks':checks},indent=2))

if __name__ == '__main__':
    {'baseline':om.baseline,'prepare':prepare,'legacy':save_legacy_sessions,'start':om.start,'upgrade':upgrade_qa,'refresh':lambda:om.start(False),'business':business,'browser':browser,'additional':additional_security,'outage':outage,'order-business':om.run_business,'order-browser':om.browser_checks,'order-edge':om.edge_checks,'production':production,'preservation':preservation,'teardown':om.teardown}[sys.argv[1]]()
