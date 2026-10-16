from qa_support import verify_migrations
from qa_support import PRIVATE, PROJECT
"""COD/VietQR/shipping QA. Business mutations are restricted to a disposable database."""
import sys,os,json,hashlib,subprocess
from pathlib import Path
import storefront_regression as gs
import order_management as om
import dashboard_management as dm
import concurrent.futures,urllib.parse,urllib.error,re,io,zipfile
from decimal import Decimal
MAIN_COMPOSE=gs.main_compose
SETTINGS='/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen'

def qa_hashes(columns=None):
    result={}
    for table in ('Users','Products','Categories','Orders','OrderItems','OrderStatusHistories','CartItems'):
        cols=columns[table]['columns'] if columns else om.qa_sql("SELECT COLUMN_NAME FROM information_schema.columns WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME="+gs.quote(table)+" ORDER BY ORDINAL_POSITION").splitlines()
        value=om.qa_sql('SELECT '+','.join('`'+c+'`' for c in cols)+' FROM '+table+' ORDER BY Id')
        result[table]={'columns':cols,'digest':hashlib.sha256(value.encode()).hexdigest()}
    return result

def upgrade():
    import m1_acceptance as acceptance
    acceptance.migration_upgrade()

def shipping(admin,fee=30000,threshold=300000):
    page=gs.get(admin,SETTINGS)[0]
    return gs.post(admin,'/Admin/CaiDatCuaHang/LuuChinhSachVanChuyen',page,{'Shipping.ExpectedVersion':om.qa_sql('SELECT Version FROM PaymentShippingSettings'),'Shipping.FlatShippingFee':fee,'Shipping.FreeShippingThreshold':threshold})

def bank(admin,bin='970436',account='0000000000000000000',holder='QA KHONG CHUYEN TIEN',enabled=True,version=None):
    page=gs.get(admin,SETTINGS)[0]
    return gs.post(admin,'/Admin/CaiDatCuaHang/LuuTaiKhoanNganHang',page,{'Bank.ExpectedVersion':om.qa_sql('SELECT Version FROM PaymentShippingSettings') if version is None else version,'Bank.BankBin':bin,'Bank.AccountNumber':account,'Bank.AccountHolderName':holder,'Bank.VietQrEnabled':str(enabled),'Bank.BankDetailsChecked':'true'})

def business_regression():
    om.configure_qa();admin=om.admin_sessions()[0]
    assert shipping(admin,0)[0]==302
    gs.compose=MAIN_COMPOSE
    om.run_business()
    assert shipping(admin)[0]==302

def rules():
    subprocess.run(['dotnet','run','--project',str(gs.ROOT/'tests/ExcelWorkbookCheck'),'--configuration','Release','--','payment-rules',str(OUT)],check=True)

def create(buyer,pid,method='COD',quantity=1,extra=None):
    page,values=gs.confirm(buyer,pid,quantity);values.update({'PaymentMethod':method,**(extra or {})})
    code,headers,body=gs.post(buyer,f'/ThanhToan/XacNhanMuaHang/{pid}',page,values)
    assert code==302,(code,body[:100]);return int(headers['Location'].rsplit('/',1)[1]),page,values

def notify(buyer,oid,version=None):
    page=gs.get(buyer,f'/ThanhToan/ThanhToanVietQR/{oid}')[0]
    return gs.post(buyer,f'/ThanhToan/ThongBaoDaChuyenKhoan/{oid}',page,{'ExpectedVersion':om.qa_sql(f'SELECT Version FROM Orders WHERE Id={oid}') if version is None else version})

def money(oid):return om.qa_sql(f'SELECT Subtotal,ShippingFee,Total FROM Orders WHERE Id={oid}')

def payment_checks():
    om.configure_qa();a1,a2=om.admin_sessions();buyer=gs.client();credentials=json.loads((OUT/'accounts.json').read_text());gs.login(buyer,credentials[2]);other=gs.client();other_account=gs.register(other);gs.login(other,other_account)
    checks=[]
    def passed(label):checks.append(label);print('PASS: '+label,flush=True)
    assert shipping(a1)[0]==302
    # This suite may follow a successful bank/payment smoke test. Recreate the
    # unconfigured-bank precondition only in guarded synthetic QA; retain all old order snapshots.
    om.qa_sql("UPDATE PaymentShippingSettings SET VietQrEnabled=0,BankBin='',BankName='',AccountNumber='',AccountHolderName='',Version=Version+1 WHERE Id=1")
    # No configured receiving bank: COD remains usable, forged VietQR is rejected.
    assert om.qa_sql('SELECT VietQrEnabled,BankBin FROM PaymentShippingSettings').split('\t')[0]=='0'
    for pid,price in enumerate((89000,250000,299999,300000,450000),1001):
        om.qa_sql(f"INSERT INTO Products (Id,Name,Price,ImageUrl,Description,StockQuantity) VALUES ({pid},'QA Payment Plant {pid}',{price},'/images/product-placeholder.svg','Owned payment fixture',100)")
    page,values=gs.confirm(buyer,1001);values['PaymentMethod']='VIETQR';before=om.qa_sql('SELECT COUNT(*) FROM Orders');stocks=om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1001')
    assert gs.post(buyer,'/ThanhToan/XacNhanMuaHang/1001',page,values)[0]==200
    assert om.qa_sql('SELECT COUNT(*) FROM Orders')==before and om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1001')==stocks
    examples=[]
    for pid,subtotal,fee,total in ((1001,89000,30000,119000),(1002,250000,30000,280000),(1003,299999,30000,329999),(1004,300000,0,300000),(1005,450000,0,450000)):
        oid,page,values=create(buyer,pid,extra={'ShippingFee':0,'Total':1,'Subtotal':1,'IsPaid':True,'UserId':1});examples.append(oid)
        assert money(oid)==f'{subtotal}.00\t{fee}.00\t{total}.00' and om.qa_sql(f'SELECT IsPaid,UserId,PaymentMethod FROM Orders WHERE Id={oid}')=='0\t3\tCOD'
        before_stock=om.qa_sql(f'SELECT StockQuantity FROM Products WHERE Id={pid}')
        assert gs.post(buyer,f'/ThanhToan/XacNhanMuaHang/{pid}',page,values)[0]==302
        assert before_stock==om.qa_sql(f'SELECT StockQuantity FROM Products WHERE Id={pid}')
    passed('Official shipping cases 89k/250k/299999/300k/450k, server-controlled totals and owner/paid fields, COD without a bank and repeated checkout does not deduct stock twice')
    # Shipping changed while checkout is open: show the new amount before confirming.
    page,values=gs.confirm(buyer,1001);count=om.qa_sql('SELECT COUNT(*) FROM Orders');assert shipping(a1,25000)[0]==302
    code,_,body=gs.post(buyer,'/ThanhToan/XacNhanMuaHang/1001',page,values);assert code==200 and 'Chính sách' in body and '114.000 đ' in body and om.qa_sql('SELECT COUNT(*) FROM Orders')==count
    assert money(examples[0])=='89000.00\t30000.00\t119000.00'
    assert shipping(a1)[0]==302
    page=gs.get(a1,SETTINGS)[0];state=om.qa_sql('SELECT * FROM PaymentShippingSettings')
    for values in ({'Shipping.FlatShippingFee':-1,'Shipping.FreeShippingThreshold':300000},{'Shipping.FlatShippingFee':'1.5','Shipping.FreeShippingThreshold':300000},{'Shipping.FlatShippingFee':1000001,'Shipping.FreeShippingThreshold':300000}):
        assert gs.post(a1,'/Admin/CaiDatCuaHang/LuuChinhSachVanChuyen',page,{'Shipping.ExpectedVersion':om.qa_sql('SELECT Version FROM PaymentShippingSettings'),**values})[0]==400
    for bad in ('999999','970436/evil'):assert bank(a1,bin=bad)[0]==400
    assert bank(a1,account='bad/account')[0]==400 and bank(a1,holder='')[0]==400
    assert om.qa_sql('SELECT * FROM PaymentShippingSettings')==state
    assert bank(a1)[0]==302;firstbank=om.qa_sql('SELECT BankBin,AccountNumber,AccountHolderName FROM PaymentShippingSettings')
    assert firstbank.split('\t')[1].startswith('0000')
    stale=int(om.qa_sql('SELECT Version FROM PaymentShippingSettings'));assert shipping(a1)[0]==302;assert bank(a2,version=stale)[0]==409
    passed('Policy changes require reconfirmation and preserve old fees; bank/shipping validation, leading-zero account and optimistic concurrency prevent invalid/stale saves')
    qr,source,values=create(buyer,1001,'VIETQR',extra={'BankBin':'evil','AccountNumber':'evil','PaymentAmount':1})
    assert money(qr)=='89000.00\t30000.00\t119000.00';assert om.qa_sql(f'SELECT BankBinSnapshot,BankAccountSnapshot,BankHolderSnapshot,TransferContent,IsPaid FROM Orders WHERE Id={qr}')==firstbank+f'\tGS{qr}\t0'
    page=gs.get(buyer,f'/ThanhToan/ThanhToanVietQR/{qr}?amount=1&accountNumber=evil')[0]
    image_url=next(a['src'] for tag,a in page.nodes if tag=='img' and 'data-vietqr-image' in a)
    parsed=urllib.parse.urlsplit(image_url);query=urllib.parse.parse_qs(parsed.query)
    assert parsed.hostname=='img.vietqr.io' and query['amount']==['119000'] and query['addInfo']==[f'GS{qr}'] and query['accountName']==[firstbank.split('\t')[2]] and 'evil' not in image_url
    assert bank(a1,bin='970415',account='QADEMO0000000000001',holder='QA NGAN HANG B')[0]==302
    body=gs.get(buyer,f'/ThanhToan/ThanhToanVietQR/{qr}')[1];assert image_url.replace('&','&amp;') in gs.request(buyer,f'/ThanhToan/ThanhToanVietQR/{qr}')[2] and 'QA NGAN HANG B' not in body
    qr_new,_,_=create(buyer,1002,'VIETQR');assert om.qa_sql(f'SELECT BankBinSnapshot FROM Orders WHERE Id={qr_new}')=='970415'
    assert bank(a1,bin='970415',account='QADEMO0000000000001',holder='QA NGAN HANG B',enabled=False)[0]==302
    assert image_url.replace('&','&amp;') in gs.request(buyer,f'/ThanhToan/ThanhToanVietQR/{qr}')[2]
    before_orders=om.qa_sql('SELECT COUNT(*) FROM Orders');values['ConfirmationToken']='f'*32
    assert gs.post(buyer,'/ThanhToan/XacNhanMuaHang/1001',source,values)[0]==200 and before_orders==om.qa_sql('SELECT COUNT(*) FROM Orders')
    assert bank(a1)[0]==302
    passed('VietQR URL comes only from a saved order and exact amount/reference; bank A->B affects new orders only; disabling blocks new transfers without changing old QR snapshots')
    for client in (gs.client(),other):
        code=gs.request(client,f'/ThanhToan/ThanhToanVietQR/{qr}')[0];assert code in (302,404)
        code=gs.request(client,f'/ThanhToan/ThongBaoDaChuyenKhoan/{qr}',{'ExpectedVersion':0})[0];assert code in (302,400,404)
    before_stock=om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id')
    assert notify(buyer,qr)[0]==302
    assert om.qa_sql(f'SELECT IsPaid,PaidAt,CustomerTransferNotifiedAt IS NOT NULL FROM Orders WHERE Id={qr}')=='0\tNULL\t1'
    assert notify(buyer,qr)[0]==302 and om.qa_sql(f'SELECT COUNT(*) FROM OrderStatusHistories WHERE OrderId={qr} AND Kind=4')=='1'
    assert 'Chờ kiểm tra chuyển khoản' in gs.get(a1,f'/Admin/DonHang/ChiTietDonHang/{qr}')[1]
    assert 'Chờ kiểm tra chuyển khoản' in gs.get(buyer,'/ThanhToan/DonHangCuaToi')[1]
    assert om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id')==before_stock
    assert om.mutate(a1,qr,'XacNhanDonHang')[0]==302 and om.mutate(a1,qr,'CapNhatTrangThaiDonHang',{'TargetStatus':4})[0]==302
    assert om.mutate(a1,qr,'CapNhatTrangThaiDonHang',{'TargetStatus':5})[0]==422
    base=om.qa_sql(f'SELECT Version,Status FROM Orders WHERE Id={qr}').split('\t');detail1=om.detail(a1,qr);detail2=om.detail(a2,qr)
    def pay(pair):return gs.post(pair[0],f'/Admin/DonHang/XacNhanDaNhanTien/{qr}',pair[1],{'ExpectedVersion':base[0],'Note':'QA manual bank match; no real funds'})[0]
    with concurrent.futures.ThreadPoolExecutor(2) as pool:codes=list(pool.map(pay,[(a1,detail1),(a2,detail2)]))
    assert sorted(codes)==[302,409],codes
    assert om.qa_sql(f'SELECT IsPaid,PaidAt IS NOT NULL,PaymentConfirmedById IN (1,2),Status FROM Orders WHERE Id={qr}')=='1\t1\t1\t4'
    assert om.qa_sql(f'SELECT COUNT(*) FROM OrderStatusHistories WHERE OrderId={qr} AND Kind=2')=='1'
    assert om.mutate(a1,qr,'XacNhanDaNhanTien',{'Note':'Repeated'})[0]==409
    assert om.mutate(a1,qr,'HuyDonHang',{'Note':'Paid needs manual reconciliation'})[0]==422
    paidpage=gs.get(buyer,f'/ThanhToan/ThanhToanVietQR/{qr}')[0];assert not any('data-vietqr-image' in a for _,a in paidpage.nodes) and not any('/ThongBaoDaChuyenKhoan/' in a.get('action','') for _,a in paidpage.nodes)
    assert om.mutate(a1,qr,'CapNhatTrangThaiDonHang',{'TargetStatus':5})[0]==302 and om.mutate(a1,qr,'CapNhatTrangThaiDonHang',{'TargetStatus':1})[0]==302
    assert om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id')==before_stock
    passed('Owned customer notification is idempotent and never Paid/stock-changing; unpaid VietQR shipping blocked; concurrent Admin confirmations have one winner/history event, preserve workflow and stock, record PaidAt/actor; paid page no longer requests transfer')
    cancelled,_,_=create(buyer,1001,'VIETQR');stock=om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1001');assert om.mutate(a1,cancelled,'HuyDonHang',{'Note':'QA unpaid cancellation'})[0]==302
    assert int(om.qa_sql('SELECT StockQuantity FROM Products WHERE Id=1001'))==int(stock)+1
    assert om.mutate(a1,cancelled,'HuyDonHang',{'Note':'Repeat'})[0]==409 and om.mutate(a1,cancelled,'XacNhanDaNhanTien',{'Note':'Cancelled'})[0]==409
    assert notify(buyer,cancelled)[0]==302
    cp=gs.get(buyer,f'/ThanhToan/ThanhToanVietQR/{cancelled}')[0];assert not any('data-vietqr-image' in a for _,a in cp.nodes)
    # Cart checkout: each line saved exactly once, one shipping charge, persisted quote, user ownership.
    for pid in (1001,1002):
        detail=gs.get(buyer,f'/SanPham/ChiTietSanPham/{pid}')[0];assert gs.post(buyer,f'/GioHang/ThemVaoGioHang/{pid}',detail,{'Quantity':1})[0]==302
    cart=gs.get(buyer,'/ThanhToan/XacNhanGioHang')[0]
    cv={'Quantity':1,'QuotedPrice':cart.input('QuotedPrice'),'PolicyVersion':cart.input('PolicyVersion'),'CartQuote':cart.input('CartQuote'),'ConfirmationToken':cart.input('ConfirmationToken'),'RecipientName':'QA Cart Buyer','Phone':'0912345678','Address':'123 QA Cart Shipping Address','PaymentMethod':'VIETQR','Total':1,'ShippingFee':0,'UserId':1}
    cart_before=om.qa_sql('SELECT COUNT(*) FROM CartItems WHERE UserId=3');assert int(cart_before)>=2
    code,h,_=gs.post(buyer,'/ThanhToan/XacNhanGioHang',cart,cv);assert code==302;cart_order=int(h['Location'].rsplit('/',1)[1])
    assert om.qa_sql(f'SELECT COUNT(*) FROM OrderItems WHERE OrderId={cart_order}')==cart_before and om.qa_sql('SELECT COUNT(*) FROM CartItems WHERE UserId=3')=='0'
    assert Decimal(om.qa_sql(f'SELECT Subtotal FROM Orders WHERE Id={cart_order}'))>=339000 and om.qa_sql(f'SELECT ShippingFee FROM Orders WHERE Id={cart_order}')=='0.00'
    stocks=om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id');assert gs.post(buyer,'/ThanhToan/XacNhanGioHang',cart,cv)[0]==302 and stocks==om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id')
    passed('Unpaid cancellation restores inventory once and suppresses QR; cart creates one order with actual item snapshots, one shipping fee, clears only owner cart and retries do not deduct again')
    # Read-only financial view remains delivered-order value and includes the recorded shipping fee once.
    body=gs.get(a1,'/Admin/Admin/TongQuan?range=year')[1];dashboard=dm.Dashboard(body)
    now=__import__('datetime').datetime.now(__import__('datetime').timezone.utc);start,end=dm.period('year',now)
    total=Decimal(om.qa_sql(f"SELECT COALESCE(SUM(Total),0) FROM Orders WHERE Status=1 AND CreatedAt>={gs.quote(dm.stamp(start))} AND CreatedAt<{gs.quote(dm.stamp(end))}"));assert dm.numeric(dashboard.metrics['value'])==total
    passed('Dashboard remains recorded delivered-order value (including shipping once), not uncollected COD/VietQR cash revenue')
    state={'qr_paid':qr,'qr_pending':cart_order,'qr_cancelled':cancelled,'cod':examples[0],'buyer':credentials[2],'other':other_account,'examples':examples}
    (OUT/'payment-state.json').write_text(json.dumps(state));os.chmod(OUT/'payment-state.json',0o600)
    (OUT/'payment-business-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'writes':'synthetic isolated only'},indent=2))

def checkout_edges():
    om.configure_qa();checks=[]
    buyer=gs.client();other=gs.client();credentials=gs.register(buyer);other_credentials=gs.register(other)
    gs.login(buyer,credentials);gs.login(other,other_credentials)
    uid=int(om.qa_sql('SELECT Id FROM Users WHERE Email='+gs.quote(credentials[0])))
    other_uid=int(om.qa_sql('SELECT Id FROM Users WHERE Email='+gs.quote(other_credentials[0])))
    ids=[]
    for price,stock in ((89000,10),('10.50',10),('9999999999',2000)):
        ids.append(int(om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity) VALUES ('QA Payment Edge',"+str(price)+",'/images/product-placeholder.svg','Owned edge fixture',"+str(stock)+"); SELECT LAST_INSERT_ID()")))
    def snapshot():return om.qa_sql('SELECT COUNT(*),SUM(Total) FROM Orders'),om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id')
    before=snapshot()
    for pid,qty in ((ids[1],1),(ids[2],1001)):
        page,values=gs.confirm(buyer,pid,qty);values['PaymentMethod']='VIETQR'
        code,_,body=gs.post(buyer,f'/ThanhToan/XacNhanMuaHang/{pid}',page,values)
        assert code==200 and '13 chữ số' in body and snapshot()==before
    page,values=gs.confirm(buyer,ids[0]);values['PaymentMethod']='FORGED'
    assert gs.post(buyer,f'/ThanhToan/XacNhanMuaHang/{ids[0]}',page,values)[0]==200 and snapshot()==before
    values['PaymentMethod']='COD';values['Quantity']='1.5'
    assert gs.post(buyer,f'/ThanhToan/XacNhanMuaHang/{ids[0]}',page,values)[0]==200 and snapshot()==before
    checks.append('Fractional/over-13-digit VietQR amount and invalid method/quantity create no order or stock change')
    def add(c):
        p=gs.get(c,f'/SanPham/ChiTietSanPham/{ids[0]}')[0]
        assert gs.post(c,f'/GioHang/ThemVaoGioHang/{ids[0]}',p,{'Quantity':1})[0]==302
    def quote(c):
        p=gs.get(c,'/ThanhToan/XacNhanGioHang')[0]
        values={n:p.input(n) for n in ('Quantity','QuotedPrice','PolicyVersion','CartQuote','ConfirmationToken')}
        values.update({'RecipientName':'QA Edge Buyer','Phone':'0912345678','Address':'123 QA Edge Shipping Address','PaymentMethod':'COD'})
        return p,values
    add(buyer);add(other);page,values=quote(buyer);op,ov=quote(other);before=snapshot()
    for forged in (values['CartQuote']+'tampered',ov['CartQuote']):
        assert gs.post(buyer,'/ThanhToan/XacNhanGioHang',page,{**values,'CartQuote':forged})[0]==200 and snapshot()==before
    add(buyer)
    assert gs.post(buyer,'/ThanhToan/XacNhanGioHang',page,values)[0]==200 and snapshot()==before
    assert om.qa_sql(f'SELECT Quantity FROM CartItems WHERE UserId={uid}')=='2'
    assert om.qa_sql(f'SELECT Quantity FROM CartItems WHERE UserId={other_uid}')=='1'
    page,values=quote(buyer);om.qa_sql(f'UPDATE Products SET Price=90000 WHERE Id={ids[0]}')
    assert gs.post(buyer,'/ThanhToan/XacNhanGioHang',page,values)[0]==200 and snapshot()==before
    page,values=quote(buyer);om.qa_sql(f'UPDATE Products SET StockQuantity=0 WHERE Id={ids[0]}');zero=snapshot()
    assert gs.post(buyer,'/ThanhToan/XacNhanGioHang',page,values)[0]==200 and snapshot()==zero
    om.qa_sql(f'UPDATE Products SET StockQuantity=10 WHERE Id={ids[0]}')
    checks.append('Protected cart quote rejects tampering, other-owner quote, changed quantities/prices and insufficient stock; carts remain owned and no partial order')
    page,values=quote(buyer);cartid=om.qa_sql(f'SELECT Id FROM CartItems WHERE UserId={uid}')
    assert gs.post(buyer,'/GioHang/XoaKhoiGioHang/'+cartid,page,{})[0]==302
    before=snapshot();code,headers,_=gs.post(buyer,'/ThanhToan/XacNhanGioHang',page,values)
    assert code==302 and '/GioHang/QuanLyGioHang' in headers.get('Location',''),('empty cart post',code)
    assert snapshot()==before and om.qa_sql(f'SELECT Quantity FROM CartItems WHERE UserId={other_uid}')=='1'
    checks.append('Cart emptied in another tab redirects to cart with feedback, preserving other cart/orders/stock')
    (OUT/'payment-checkout-edges-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'writes':'isolated synthetic QA only'},indent=2))
    for check in checks:print('PASS: '+check,flush=True)

def browser():
    om.configure_qa()
    from playwright.sync_api import sync_playwright,expect
    state=json.loads((OUT/'payment-state.json').read_text());account=json.loads((OUT/'accounts.json').read_text())[0]
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True);admin_context=b.new_context(ignore_https_errors=True);customer_context=b.new_context(ignore_https_errors=True,permissions=['clipboard-read','clipboard-write']);admin=admin_context.new_page();customer=customer_context.new_page();errors=[]
        for page,credential in ((admin,account),(customer,state['buyer'])):
            page.on('pageerror',lambda error:errors.append(str(error)));page.goto(om.QA_BASE+'/Account/Login');page.locator('#Email').fill(credential[0]);page.locator('[name=Password]').fill(credential[1]);page.locator('form:has(#Email) button[type=submit]').click()
        for width in (1440,768,360):
            for page in (admin,customer):page.set_viewport_size({'width':width,'height':1000})
            paths=[(admin,'settings',SETTINGS),(admin,'admin-detail',f"/Admin/DonHang/ChiTietDonHang/{state['qr_pending']}"),(customer,'checkout','/ThanhToan/XacNhanMuaHang/1001'),(customer,'qr',f"/ThanhToan/ThanhToanVietQR/{state['qr_pending']}"),(customer,'paid',f"/ThanhToan/ThanhToanVietQR/{state['qr_paid']}"),(customer,'cancelled',f"/ThanhToan/ThanhToanVietQR/{state['qr_cancelled']}"),(customer,'history','/ThanhToan/DonHangCuaToi')]
            for page,label,path in paths:
                page.goto(om.QA_BASE+path);page.evaluate('document.fonts.ready');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(label,width,page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width])"))
                page.screenshot(path=str(OUT/f'payment-{label}-{width}.png'),full_page=True,animations='disabled')
        admin.set_viewport_size({'width':1440,'height':1000});admin.goto(om.QA_BASE+'/Admin/Admin/TongQuan');admin.get_by_role('button',name='Cài đặt cửa hàng',exact=True).click();admin.get_by_role('link',name='Cài đặt thanh toán & vận chuyển',exact=True).click();expect(admin).to_have_url(om.QA_BASE+SETTINGS)
        admin.locator('#shippingExample').fill('299999');expect(admin.locator('[data-example-fee]')).to_have_text('30.000 đ');expect(admin.locator('[data-example-total]')).to_have_text('329.999 đ')
        admin.locator('#shippingExample').fill('300000');expect(admin.locator('[data-example-fee]')).to_have_text('0 đ');admin.locator('#bankSearch').fill('vietcombank');assert admin.locator('#Bank_BankBin option:not([hidden])').count()>=1
        customer.set_viewport_size({'width':1440,'height':1000});customer.goto(om.QA_BASE+'/ThanhToan/XacNhanMuaHang/1001');expect(customer.locator('[data-payment-total]')).to_have_text('119.000 đ');customer.locator('#Quantity').fill('4');expect(customer.locator('[data-payment-total]')).to_have_text('356.000 đ');expect(customer.locator('[data-payment-shipping]')).to_have_text('0 đ');customer.get_by_label('Chuyển khoản ngân hàng qua VietQR',exact=False).check();expect(customer.locator('[data-method-note]')).to_contain_text('Sau khi đặt hàng')
        customer.goto(om.QA_BASE+f"/ThanhToan/ThanhToanVietQR/{state['qr_pending']}");customer.get_by_role('button',name='Sao chép số tài khoản',exact=True).click();expect(customer.locator('.payment-copy-feedback')).to_contain_text('Đã sao chép');assert customer.evaluate('navigator.clipboard.readText()')==om.qa_sql(f"SELECT BankAccountSnapshot FROM Orders WHERE Id={state['qr_pending']}")
        customer.get_by_role('button',name='Sao chép số tiền',exact=True).click();assert customer.evaluate('navigator.clipboard.readText()')==str(int(Decimal(om.qa_sql(f"SELECT Total FROM Orders WHERE Id={state['qr_pending']}"))))
        customer.get_by_role('button',name='Sao chép nội dung chuyển khoản',exact=True).click();assert customer.evaluate('navigator.clipboard.readText()')==f"GS{state['qr_pending']}"
        img=customer.locator('[data-vietqr-image]');customer.wait_for_function("document.querySelector('[data-vietqr-image]').complete",timeout=30000);qr_loaded=img.evaluate('e=>e.naturalWidth>0')
        if qr_loaded:assert img.evaluate('e=>e.naturalWidth===540 && e.naturalHeight===640')
        customer.route('https://img.vietqr.io/**',lambda route:route.abort());img.evaluate("e=>e.src=e.src+'&qaFallback=1'");expect(customer.locator('[data-qr-error]')).to_be_visible();expect(customer.get_by_role('button',name='Sao chép số tài khoản',exact=True)).to_be_visible();customer.unroute('https://img.vietqr.io/**')
        customer.get_by_role('button',name='Tôi đã chuyển khoản',exact=True).click();expect(customer.locator('.payment-verification')).to_contain_text('Đang chờ xác nhận');expect(customer.get_by_role('button',name='Tôi đã chuyển khoản',exact=True)).to_have_count(0)
        admin.goto(om.QA_BASE+f"/Admin/DonHang/ChiTietDonHang/{state['qr_pending']}");expect(admin.locator('.order-info-panel').filter(has=admin.get_by_role('heading',name='Thông tin thanh toán',exact=True))).to_contain_text('Chờ kiểm tra chuyển khoản');admin.get_by_role('button',name='Xác nhận đã nhận tiền',exact=True).click();expect(admin.locator('#orderConfirmDialog')).to_be_visible();expect(admin.locator('#orderConfirmDescription')).to_contain_text(f"GS{state['qr_pending']}");admin.keyboard.press('Escape');expect(admin.locator('#orderConfirmDialog')).not_to_be_visible();admin.wait_for_function("getComputedStyle(document.documentElement).overflowY!=='hidden'")
        customer.emulate_media(reduced_motion='reduce');customer.get_by_role('button',name='Sao chép số tài khoản',exact=True).hover();assert customer.locator('.payment-copy').first.evaluate('e=>getComputedStyle(e).transitionDuration')=='0s'
        assert not errors,errors;admin_context.close();customer_context.close();b.close()
    (OUT/'payment-browser-results.json').write_text(json.dumps({'status':'PASS','checks':'Real Settings menu/inputs/example, checkout exact live preview/radio, QR copy clipboard/forced fallback, notify/Admin sync/modal, paid/cancelled states, 360/768/1440 no overflow/JS errors; reduced motion','external_qr_image':'PASS: actual 540x640 provider image' if qr_loaded else 'Image unavailable; fallback verified','bank_app_scan':'NOT TESTED; no real money transaction'}))
    print('PASS: Chromium 360/768/1440 settings/checkout/VietQR/paid/cancelled/history, live shipping boundary preview, actual clipboard, QR fallback, notification sync and native confirmation; no JS errors.',flush=True)

def security():
    om.configure_qa();a1,a2=om.admin_sessions();state=json.loads((OUT/'payment-state.json').read_text());buyer=gs.client();gs.login(buyer,state['buyer']);anon=gs.client()
    for client in (anon,buyer):
        assert gs.request(client,SETTINGS)[0]==302
        for action in ('LuuTaiKhoanNganHang','LuuChinhSachVanChuyen'):
            assert gs.request(client,'/Admin/CaiDatCuaHang/'+action,{'Role':'Admin'})[0]==302
        assert gs.request(client,f"/Admin/DonHang/XacNhanDaNhanTien/{state['qr_pending']}",{})[0]==302
    for action in ('LuuTaiKhoanNganHang','LuuChinhSachVanChuyen'):
        assert gs.request(a1,'/Admin/CaiDatCuaHang/'+action)[0]==405
        assert gs.request(a1,'/Admin/CaiDatCuaHang/'+action,{})[0]==400
    assert gs.request(a1,f"/Admin/DonHang/XacNhanDaNhanTien/{state['qr_pending']}")[0]==405
    assert gs.request(a1,f"/Admin/DonHang/XacNhanDaNhanTien/{state['qr_pending']}",{'ExpectedVersion':0})[0]==400
    assert gs.request(buyer,f"/ThanhToan/ThongBaoDaChuyenKhoan/{state['qr_pending']}")[0]==405
    assert gs.request(buyer,f"/ThanhToan/ThongBaoDaChuyenKhoan/{state['qr_pending']}",{'ExpectedVersion':0})[0]==400
    def change(uid,action,values=None):
        page=gs.get(a1,f'/Admin/NguoiDung/ChiTietNguoiDung/{uid}')[0]
        return gs.post(a1,f'/Admin/NguoiDung/{action}/{uid}',page,{'ExpectedVersion':om.qa_sql(f'SELECT Version FROM Users WHERE Id={uid}'),**(values or {})})[0]
    assert change(2,'ThayDoiVaiTro',{'TargetRole':0})==302
    assert gs.request(a2,SETTINGS)[0]==302 and gs.request(a2,f"/Admin/DonHang/XacNhanDaNhanTien/{state['qr_pending']}",{})[0]==302
    assert change(2,'ThayDoiVaiTro',{'TargetRole':1})==302
    before=om.qa_sql('SELECT COUNT(*),SUM(Total) FROM Orders');stock=om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id');policy=om.qa_sql('SELECT * FROM PaymentShippingSettings')
    assert change(3,'KhoaTaiKhoan')==302
    assert gs.request(buyer,f"/ThanhToan/ThongBaoDaChuyenKhoan/{state['qr_pending']}",{})[0]==302
    assert gs.request(buyer,'/ThanhToan/XacNhanGioHang',{})[0]==302
    assert change(3,'MoKhoaTaiKhoan')==302
    assert before==om.qa_sql('SELECT COUNT(*),SUM(Total) FROM Orders') and stock==om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id') and policy==om.qa_sql('SELECT * FROM PaymentShippingSettings')
    (OUT/'payment-security-results.json').write_text(json.dumps({'status':'PASS','checks':'Admin settings/confirmation authorization, GET 405/CSRF 400, customer notify ownership, forged role, revoked Admin cookie, locked Customer cookie; no order/payment/stock/config effects','writes':'only synthetic QA account transitions'}))
    print('PASS: Settings/payment confirmation Admin only, POST/CSRF enforced; revoked-role and locked-account cookies cannot change orders/stock/payments/config.',flush=True)

def reports():
    import excel_exports as ex
    ex.OUT=om.OUT=dm.OUT=dm.us.OUT=OUT;om.QA_PROJECT=PROJECT
    for check in (lambda:ex.fixtures(reuse_dashboard=(OUT/'dashboard-metric-results.json').exists()),ex.exports,dm.metrics,ex.roundtrip):
        gs.compose=MAIN_COMPOSE
        check()

def report_payment_filters():
    import excel_exports as ex
    ex.OUT=OUT/'payment-filter-workbooks';ex.OUT.mkdir(mode=0o700,exist_ok=True)
    om.OUT=dm.OUT=dm.us.OUT=OUT;om.QA_PROJECT=PROJECT;gs.compose=MAIN_COMPOSE
    om.configure_qa();admin=om.admin_sessions()[0];before=qa_hashes()
    cases=[('vietqr','?paymentMethod=VIETQR',"o.PaymentMethod='VIETQR'"),('cod','?paymentMethod=COD',"o.PaymentMethod='COD'"),
        ('pending','?paymentState=pending',"o.IsPaid=0 AND o.PaymentMethod='VIETQR' AND o.CustomerTransferNotifiedAt IS NOT NULL AND o.Status<>2"),
        ('paid-bank','?paymentMethod=VIETQR&paymentState=paid',"o.PaymentMethod='VIETQR' AND o.IsPaid=1"),
        ('unpaid-bank','?paymentMethod=VIETQR&paymentState=unpaid',"o.PaymentMethod='VIETQR' AND o.IsPaid=0")]
    for name,query,where in cases:
        rows=ex.order_data(where);assert rows
        ex.download(admin,ex.ORDER+query,name,[ex.sheet('Đơn hàng',ex.ORDER_HEADERS,ex.order_rows(rows))])
        assert str(len(rows))+' kết quả' in gs.get(admin,'/Admin/DonHang/QuanLyDonHang'+query)[1]
    for query in ('?paymentMethod=FORGED','?paymentState=FORGED'):
        assert gs.request(admin,ex.ORDER+query)[0]==400
        assert gs.request(admin,'/Admin/DonHang/QuanLyDonHang'+query)[0]==400
    assert gs.request(admin,ex.ORDER+'?paymentMethod=COD&paymentState=pending')[0]==404
    assert qa_hashes()==before
    ex.roundtrip()
    (OUT/'payment-report-filters-results.json').write_text(json.dumps({'status':'PASS','checks':'Shared COD/VietQR and pending/paid/unpaid list/export filters; five real workbooks with exact stored shipping, statuses and nullable legacy/paid timestamps; invalid filters 400 and empty 404; no database writes'}))
    print('PASS: Five real payment-filter Excel files match list/SQL, snapshots/statuses/audit dates; Open XML and round-trip passed; invalid/empty filters rejected; all data unchanged.',flush=True)

def persistence():
    om.configure_qa();before=qa_hashes();settings=om.qa_sql('SELECT * FROM PaymentShippingSettings');admin=om.admin_sessions()[0]
    om.qa_compose('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','web_app')
    om.start(False)
    assert qa_hashes()==before and om.qa_sql('SELECT * FROM PaymentShippingSettings')==settings
    gs.get(admin,SETTINGS)
    (OUT/'payment-persistence-results.json').write_text(json.dumps({'status':'PASS','checks':'Bank/shipping settings and all order/payment/fee snapshots, original records and genuine Admin cookie survive QA web recreate'}))
    print('PASS: Persistent settings/payment/shipping snapshots, all data and genuine cookie survive QA web recreate.',flush=True)

def preservation():
    import m1_acceptance as acceptance
    acceptance.preservation()

def production():
    om.production_checks();client=gs.client()
    for path in (SETTINGS,'/ThanhToan/ThanhToanVietQR/1','/ThanhToan/XacNhanGioHang'):
        code,headers,_=gs.request(client,path);assert code==302 and '/Account/Login' in headers.get('Location','')
    for path in ('/css/payment-shipping.css','/js/payment-shipping.js'):
        code,_,body=gs.request(client,path);assert code==200 and len(body)>100
    verify_migrations(gs.sql)
    real=gs.compose('ps','-q','web_app');qa=om.qa_compose('ps','-q','web_app')
    image=lambda container:subprocess.check_output(['docker','inspect','--format','{{.Image}}',container],text=True).strip()
    assert image(real)==image(qa)
    (OUT/'payment-production-results.json').write_text(json.dumps({'status':'PASS','checks':'source-matched migration IDs; HTTPS 200/no 502; protected payment/settings/cart routes; real image identical to fully authenticated QA, default receiving bank empty/disabled','scope':'Production read-only; no real payment/account changes'}))
    print('PASS: Production HTTPS/health, protected routes/assets, source-matched migration IDs and same tested image; no real transfer or bank account configured.',flush=True)
OUT=PRIVATE/'qa';OUT.mkdir(mode=0o700,exist_ok=True)
om.OUT=dm.OUT=dm.us.OUT=OUT;om.QA_PROJECT=PROJECT

def baseline():
    om.baseline();file=OUT/'baseline.json';value=json.loads(file.read_text());value['extra']=dm.extra_snapshot()
    root=gs.ROOT/'backend/GreenShop.Web'
    value['sources']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.suffix in ('.cs','.cshtml','.css','.js','.csproj') and not any(x in p.parts for x in ('obj','bin'))}
    file.write_text(json.dumps(value));os.chmod(file,0o600)
    print('PASS: Private production baseline/backup captured before payment migration; no business changes.',flush=True)

def prepare():
    om.prepare()

if __name__=='__main__':
    {'baseline':baseline,'prepare':prepare,'start':om.start,'refresh':lambda:om.start(False),'teardown':om.teardown,'upgrade':upgrade,'business-regression':business_regression,'rules':rules,'payments':payment_checks,'edges':checkout_edges,'browser':browser,'security':security,'reports':reports,'report-payment-filters':report_payment_filters,'persistence':persistence,'preservation':preservation,'production':production,'admin-regression':om.browser_checks}[sys.argv[1]]()


def fractional_prices():
    """Fractional catalog, cart, checkout preview and COD receipt remain exact."""
    from playwright.sync_api import expect
    import portal_sessions as ps
    om.configure_qa();buyer=gs.client();account=gs.register(buyer);gs.login(buyer,account)
    pid=int(om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity) VALUES ('QA exact fractional price',10.50,'/images/product-placeholder.svg','Owned exact-price regression',10); SELECT LAST_INSERT_ID()"))
    page,body,_=gs.get(buyer,f'/SanPham/ChiTietSanPham/{pid}');assert '10,50 đ' in body
    assert gs.post(buyer,f'/GioHang/ThemVaoGioHang/{pid}',page,{'Quantity':3})[0]==302
    assert '31,50 đ' in gs.get(buyer,'/GioHang/QuanLyGioHang')[1]
    with ps.playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(ignore_https_errors=True);p=context.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(p,account);p.goto(om.QA_BASE+f'/ThanhToan/XacNhanMuaHang/{pid}?quantity=3')
        expect(p.locator('[data-payment-subtotal]')).to_have_text('31,50 đ')
        p.locator('#Quantity').fill('2');expect(p.locator('[data-payment-subtotal]')).to_have_text('21 đ')
        p.locator('#Quantity').fill('3');expect(p.locator('[data-payment-subtotal]')).to_have_text('31,50 đ')
        p.locator('#Address').fill('123 QA exact fractional-price address')
        p.locator('[value=COD]').check();p.locator('button[type=submit]').filter(has_text='Xác nhận').click()
        expect(p).to_have_url(__import__('re').compile('/ThanhToan/ChiTietDonHang/'))
        expect(p.locator('.order-items')).to_contain_text('10,50 đ');expect(p.locator('.order-items')).to_contain_text('31,50 đ')
        assert not errors,errors;context.close();browser.close()
    assert om.qa_sql(f'SELECT StockQuantity FROM Products WHERE Id={pid}')=='7'
    (OUT/'fractional-price-results.json').write_text(json.dumps({'status':'PASS','checks':'10.50 displays 10,50; cart 3×10.50=31.50; preview quantity changes 3→2→3 exact; actual synthetic COD receipt preserves unit/line totals and stock deduction'}))
    print('PASS: Fractional prices stay exact across real catalog/cart/browser checkout/COD receipt; whole prices unchanged.',flush=True)
