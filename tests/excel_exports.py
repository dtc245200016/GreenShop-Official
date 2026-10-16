from qa_support import verify_migrations
from qa_support import PRIVATE, PROJECT
"""Excel export QA. All mutations are restricted to disposable MySQL fixtures."""
import sys,os,json,hashlib,subprocess
from pathlib import Path
import storefront_regression as gs
import order_management as om
import dashboard_management as dm
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import urllib.request,urllib.error,urllib.parse,re,zipfile,io

ORDER='/Admin/DonHang/XuatExcelDonHang';PRODUCT='/Admin/SanPham/XuatExcelSanPham';REPORT='/Admin/Admin/XuatBaoCaoDoanhThu'
ORDER_HEADERS=['STT','Mã đơn hàng','Ngày đặt (GMT+7)','Tên khách hàng','Người nhận','Điện thoại người nhận','Địa chỉ giao hàng','Số loại sản phẩm','Tổng số lượng','Tiền sản phẩm đã lưu','Phí vận chuyển đã lưu','Tổng thanh toán','Phương thức thanh toán','Trạng thái thanh toán','Trạng thái đơn hàng','Khách báo chuyển khoản (GMT+7)','Xác nhận nhận tiền (GMT+7)','Người xác nhận nhận tiền']
PRODUCT_HEADERS=['STT','Mã sản phẩm','Tên sản phẩm','Danh mục','Giá bán','Số lượng tồn kho','Tình trạng tồn kho']
STATES={0:'Chờ xác nhận',1:'Đã giao',2:'Đã hủy',3:'Đã xác nhận',4:'Đang xử lý',5:'Đang giao'}
MIME='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

def preservation():
    before=json.loads((OUT/'baseline.json').read_text());after=om.real_snapshot()
    for key in ('products','categories','users','images','keys','infrastructure_source','containers','Orders','OrderItems','CartItems','migrations'):assert before[key]==after[key],key
    assert before['extra']==dm.extra_snapshot()
    allowed={'Areas/Admin/Controllers/DonHangController.cs','Areas/Admin/Controllers/SanPhamController.cs','Areas/Admin/Controllers/AdminController.cs','Areas/Admin/Views/DonHang/QuanLyDonHang.cshtml','Areas/Admin/Views/SanPham/QuanLySanPham.cshtml','Areas/Admin/Views/Admin/TongQuan.cshtml','Areas/Admin/Views/Shared/_AdminLayout.cshtml','Services/DashboardStatistics.cs'}
    root=gs.ROOT/'backend/GreenShop.Web'
    for name,digest in before['protected_sources'].items():
        if str(Path(name).relative_to(root)) not in allowed:assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    (OUT/'preservation-results.json').write_text(json.dumps({'status':'PASS','checks':'All real data, stock, user credentials/roles/sessions, images/keys, migrations, infrastructure and unrelated customer/admin/business source preserved'}))
    print('PASS: All real business data and unrelated source preserved.',flush=True)

def data(query):
    return [json.loads(bytes.fromhex(line).decode()) for line in om.qa_sql(query).splitlines()]

def order_data(where='1=1',sort='o.CreatedAt DESC,o.Id DESC'):
    return data(f"SELECT HEX(JSON_OBJECT('id',o.Id,'date',o.CreatedAt,'customer',u.FullName,'recipient',o.RecipientName,'phone',o.Phone,'address',o.Address,'kinds',(SELECT COUNT(*) FROM OrderItems i WHERE i.OrderId=o.Id),'quantity',(SELECT COALESCE(SUM(i.Quantity),0) FROM OrderItems i WHERE i.OrderId=o.Id),'total',o.Total,'method',o.PaymentMethod,'paid',o.IsPaid,'status',o.Status,'subtotal',o.Subtotal,'shipping',o.ShippingFee,'notified',o.CustomerTransferNotifiedAt,'paidAt',o.PaidAt,'confirmedBy',o.PaymentConfirmedByName)) FROM Orders o JOIN Users u ON u.Id=o.UserId WHERE {where} ORDER BY {sort}")

def order_rows(items):
    rows=[]
    for i,o in enumerate(items,1):
        local=datetime.fromisoformat(o['date']).replace(tzinfo=timezone.utc).astimezone(dm.LOCAL).replace(tzinfo=None).isoformat()
        date=lambda s: {'date':datetime.fromisoformat(s).replace(tzinfo=timezone.utc).astimezone(dm.LOCAL).replace(tzinfo=None).isoformat()} if s else None
        rows.append([i,f"GS-{o['id']:06d}",{'date':local},o['customer'],o['recipient'],o['phone'],o['address'],o['kinds'],o['quantity'],o['subtotal'],o['shipping'],o['total'],o['method'],'Đã thanh toán' if o['paid'] else 'Chờ kiểm tra chuyển khoản' if o['method']=='VIETQR' and o['notified'] else 'Chưa thanh toán',STATES[o['status']],date(o['notified']),date(o['paidAt']),o['confirmedBy']])
    return rows

def sheet(name,headers,rows,total=True):
    return {'name':name,'headers':headers,'rows':rows,'totalRow':len(rows)+9 if total else 0}

def manifest(name,sheets,cells=None):
    values=cells or {}
    for spec in sheets:
        row=spec['totalRow'];data_rows=spec['rows']
        if not row:continue
        if spec['headers']==ORDER_HEADERS:values[spec['name']]={f'I{row}':sum(r[8] for r in data_rows),f'J{row}':sum(r[9] or 0 for r in data_rows),f'K{row}':sum(r[10] or 0 for r in data_rows),f'L{row}':sum(r[11] for r in data_rows)}
        elif spec['headers']==PRODUCT_HEADERS:values[spec['name']]={f'F{row}':sum(r[5] for r in data_rows)}
        elif spec['name']=='Theo thời gian':values[spec['name']]={f'B{row}':sum(r[1] for r in data_rows),f'C{row}':sum(r[2] for r in data_rows),f'D{row}':sum(r[3] for r in data_rows)}
    (OUT/(name+'.expected.json')).write_text(json.dumps({'file':name+'.xlsx','sheets':sheets,'cells':values},ensure_ascii=False))

def download(client,path,name,expected):
    try:response=client.open(gs.BASE+path,timeout=120)
    except urllib.error.HTTPError as error:response=error
    payload=response.read();assert response.code==200,(path,response.code,payload[:250])
    assert response.headers.get_content_type()==MIME and 'no-store' in response.headers.get('Cache-Control','')
    disposition=response.headers.get('Content-Disposition','');assert re.search(r'GreenShop_[A-Za-z0-9_-]+\.xlsx',disposition),disposition
    assert payload[:2]==b'PK'
    with zipfile.ZipFile(io.BytesIO(payload)) as z:assert z.testzip() is None and 'xl/workbook.xml' in z.namelist()
    file=OUT/(name+'.xlsx');file.write_bytes(payload);manifest(name,expected)
    return payload

def fixtures(reuse_dashboard=False):
    if not reuse_dashboard:dm.fixtures()
    else:
        om.configure_qa()
        assert om.qa_sql("SELECT COUNT(*) FROM Products WHERE Id BETWEEN 501 AND 504 AND Name=CONCAT('QA Dash Plant ',Id)")=='4', 'Only reuse verified dashboard-owned fixtures'
        assert om.qa_sql("SELECT COUNT(*) FROM Orders WHERE Id=530 AND RecipientName='QA Deleted snapshot'")=='1'
    # Hostile text remains ordinary text in the workbook, including leading zeros in phone.
    om.qa_sql("UPDATE Products SET Name='=HYPERLINK(\"https://example.invalid\",\"QA\")' WHERE Id=505; UPDATE Orders SET RecipientName='=1+1',Phone='001234567890',Address='@SUM(1,2)' WHERE Id=530")
    om.qa_sql("INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES (530,501,'Extra historical line','/images/product-placeholder.svg',0.01,1)")
    today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    for date in (today-timedelta(microseconds=1),today,today+timedelta(days=1,microseconds=-1),today+timedelta(days=1)):
        oid=int(om.qa_sql(f"INSERT INTO Orders (UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES (3,{gs.quote(__import__('uuid').uuid4().hex)},'QA UTC boundary','0912345678','QA boundary',{gs.quote(dm.stamp(date))},12.34,1,0,'COD',1,'',0); SELECT LAST_INSERT_ID()"))
        om.qa_sql(f"INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES ({oid},501,'Boundary snapshot','/images/product-placeholder.svg',12.34,1)")
    # Total is still the recorded 37.02. Export must not reprice/recalculate or duplicate it.
    print('PASS: Formula/phone/multiple-item/mismatched-historical-total fixtures are isolated only.',flush=True)

def exports():
    om.configure_qa();admin=om.admin_sessions()[0];before=dm.snapshot_qa();checks=[]
    def passed(s):checks.append(s);print('PASS: '+s,flush=True)
    cases=[('all','', '1=1','o.CreatedAt DESC,o.Id DESC'),('pages','?page=2&pageSize=15','1=1','o.CreatedAt DESC,o.Id DESC'),
        ('oldest','?sort=oldest','1=1','o.CreatedAt,o.Id'),('total-desc','?sort=total-desc','1=1','o.Total DESC,o.Id DESC'),('total-asc','?sort=total-asc','1=1','o.Total,o.Id'),
        ('status','?status=1','o.Status=1','o.CreatedAt DESC,o.Id DESC'),('customer','?customerId=3','o.UserId=3','o.CreatedAt DESC,o.Id DESC'),
        ('code','?search=GS-000530','o.Id=530','o.CreatedAt DESC,o.Id DESC'),('name','?search='+urllib.parse.quote('QA Dash recipient'),"o.RecipientName LIKE '%QA Dash recipient%'",'o.CreatedAt DESC,o.Id DESC'),
        ('email','?search=qa-order-3%40example.invalid',"u.Email LIKE '%qa-order-3@example.invalid%'",'o.CreatedAt DESC,o.Id DESC')]
    today=datetime.now(timezone.utc).date();stamp=today.isoformat()
    cases.append(('utc-day','?fromDate='+stamp+'&toDate='+stamp,f"o.CreatedAt>='{stamp}' AND o.CreatedAt<'{today+timedelta(days=1)}'",'o.CreatedAt DESC,o.Id DESC'))
    cases.append(('combined','?search=QA%20UTC%20boundary&customerId=3&status=1&fromDate='+stamp+'&toDate='+stamp+'&sort=oldest',f"o.RecipientName LIKE '%QA UTC boundary%' AND o.UserId=3 AND o.Status=1 AND o.CreatedAt>='{stamp}' AND o.CreatedAt<'{today+timedelta(days=1)}'",'o.CreatedAt,o.Id'))
    for name,query,where,sort in cases:
        items=order_data(where,sort);assert items
        download(admin,ORDER+query,'orders-'+name,[sheet('Đơn hàng',ORDER_HEADERS,order_rows(items))])
        body=gs.get(admin,'/Admin/DonHang/QuanLyDonHang'+query)[1]
        assert str(len(items))+' kết quả' in body,(name,len(items))
    assert len(order_data())>15
    passed('Order exports: exact stored totals/one row per order, stable four sorts, status/customer/name/email/code/UTC dates and all pages beyond 15 rows')
    products=data("SELECT HEX(JSON_OBJECT('id',p.Id,'name',p.Name,'category',COALESCE(c.Name,'Chưa phân loại'),'price',p.Price,'stock',p.StockQuantity)) FROM Products p LEFT JOIN Categories c ON c.Id=p.CategoryId ORDER BY p.Id DESC")
    rows=[[i,p['id'],p['name'],p['category'],p['price'],p['stock'],'Hết hàng' if p['stock']==0 else 'Sắp hết hàng' if p['stock']<=5 else 'Còn hàng'] for i,p in enumerate(products,1)]
    download(admin,PRODUCT,'products',[sheet('Sản phẩm & tồn kho',PRODUCT_HEADERS,rows)])
    passed('Product export: all existing list rows/ID order, category and live prices/stock, shared threshold 5, safe formula-shaped name')
    now=datetime.now(timezone.utc)
    for period in ('7d','30d','month','year'):
        start,end=dm.period(period,now);where=f"o.CreatedAt>={gs.quote(dm.stamp(start))} AND o.CreatedAt<{gs.quote(dm.stamp(end))}"
        all_orders=order_data(where);eligible=order_data(where+' AND o.Status=1');amount=sum(Decimal(str(o['total'])) for o in eligible);sold=sum(o['quantity'] for o in eligible)
        page=dm.Dashboard(gs.get(admin,'/Admin/Admin/TongQuan?range='+period)[1]);assert dm.numeric(page.metrics['value'])==amount
        startlocal=start.astimezone(dm.LOCAL).replace(tzinfo=None);endlocal=end.astimezone(dm.LOCAL).replace(tzinfo=None)
        summary=[['Từ ngày (GMT+7)',{'date':startlocal.isoformat()}],['Đến hết ngày (GMT+7)',{'date':(endlocal-timedelta(days=1)).isoformat()}],['Tổng số đơn đặt trong kỳ',len(all_orders)],['Số đơn đã giao',len(eligible)],['Số đơn đã hủy',sum(o['status']==2 for o in all_orders)],['Số đơn đã xác nhận / đang xử lý',sum(o['status'] in (3,4) for o in all_orders)],['Giá trị đơn đã giao',float(amount)],['Số lượng sản phẩm đã bán',sold],['Đơn đã giao chưa xác nhận thanh toán',sum(not o['paid'] for o in eligible)]]
        summary.extend([['Phí ship đã ghi nhận trong các đơn đã giao',sum(o['shipping'] or 0 for o in eligible)],['Đơn đã giao thiếu chi tiết phí ship',sum(o['shipping'] is None for o in eligible)]])
        monthly=period=='year';timeline=[];date=startlocal
        while date<endlocal:
            fmt='%Y-%m' if monthly else '%Y-%m-%d';key=date.strftime(fmt)
            group=[o for o in eligible if datetime.fromisoformat(o['date']).replace(tzinfo=timezone.utc).astimezone(dm.LOCAL).strftime(fmt)==key]
            timeline.append([{'date':date.isoformat()},len(group),sum(o['total'] for o in group),sum(o['quantity'] for o in group)])
            date=datetime(date.year+(date.month==12),date.month%12+1,1) if monthly else date+timedelta(days=1)
        sheets=[sheet('Tổng quan',['Chỉ số','Giá trị'],summary,False),sheet('Theo thời gian',['Tháng (GMT+7)' if monthly else 'Ngày (GMT+7)','Số đơn đã giao','Giá trị đơn đã giao','Số lượng sản phẩm đã bán'],timeline)]
        if eligible:sheets.append(sheet('Đơn hàng liên quan',ORDER_HEADERS,order_rows(eligible)))
        download(admin,REPORT+'?range='+period,'report-'+period,sheets)
    passed('Report 7d/30d/month/year equals actual Dashboard and independent MySQL totals/day-month boundaries; cancelled excluded, paid/unpaid COD included only as delivered value, duplicated histories/multiple lines cannot double count')
    for path in (ORDER+'?search=QA-NO-MATCH-EXCEL',ORDER+'?fromDate=9998-01-01&toDate=9998-01-02'):
        code,headers,body=gs.request(admin,path);assert code==404 and 'Không có dữ liệu' in body and '.xlsx' not in headers.get('Content-Disposition','')
    invalid=['status=999','sort=bad','fromDate=not-a-date','fromDate=2026-02-01&toDate=2026-01-01','toDate=9999-12-31','search='+'x'*101,'customerId=0','page=0','pageSize=999']
    for query in invalid:assert gs.request(admin,ORDER+'?'+query)[0]==400,query
    assert gs.request(admin,REPORT+'?range=bad')[0]==400
    for endpoint in (ORDER,PRODUCT,REPORT):assert gs.request(admin,endpoint,{})[0]==405
    passed('Empty results/invalid dates-status-sort-length/range use clear non-XLSX errors; exports are GET only')
    assert dm.snapshot_qa()==before
    (OUT/'export-data-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'writes':'none during exports'},indent=2))

def authorization():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());a1,a2=om.admin_sessions();customer=gs.client();gs.login(customer,accounts[2])
    for client in (gs.client(),customer):
        for endpoint in (ORDER,PRODUCT,REPORT):
            code,headers,_=gs.request(client,endpoint+'?Role=Admin&UserId=1');assert code==302 and ('Login' in headers['Location'] or 'AccessDenied' in headers['Location'])
    def change(action,values):
        page=gs.get(a1,'/Admin/NguoiDung/ChiTietNguoiDung/2')[0]
        return gs.post(a1,'/Admin/NguoiDung/'+action+'/2',page,{'ExpectedVersion':om.qa_sql('SELECT Version FROM Users WHERE Id=2'),**values})[0]
    assert change('ThayDoiVaiTro',{'TargetRole':0})==302
    for endpoint in (ORDER,PRODUCT,REPORT):assert gs.request(a2,endpoint)[0]==302
    assert change('ThayDoiVaiTro',{'TargetRole':1})==302
    a2=gs.client();gs.login(a2,accounts[1],expected='/Admin')
    assert change('KhoaTaiKhoan',{})==302
    for endpoint in (ORDER,PRODUCT,REPORT):assert gs.request(a2,endpoint)[0]==302
    assert change('MoKhoaTaiKhoan',{})==302
    print('PASS: Admin only; Anonymous/Customer/client-role injection denied; revoked Admin and locked-account genuine old cookies denied on all export routes; only synthetic account changed.',flush=True)
    (OUT/'export-auth-results.json').write_text(json.dumps({'status':'PASS','checks':'Admin, anonymous, customer, forged query role, stale revoked-role cookie, locked user; synthetic accounts only'}))

def roundtrip():
    for file in OUT.glob('*.expected.json'):
        spec=json.loads(file.read_text());manifest(file.name.removesuffix('.expected.json'),spec['sheets'])
    subprocess.run(['dotnet','run','--project',str(gs.ROOT/'tests/ExcelWorkbookCheck'),'--configuration','Release','--',str(OUT)],check=True)

def browser():
    om.configure_qa();before=dm.snapshot_qa()
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True);context=b.new_context(ignore_https_errors=True,accept_downloads=True);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        account=json.loads((OUT/'accounts.json').read_text())[0];page.goto(om.QA_BASE+'/Account/Login');page.locator('#Email').fill(account[0]);page.locator('[name=Password]').fill(account[1]);page.locator('form:has(#Email) button[type=submit]').click()
        routes=[('orders','/Admin/DonHang/QuanLyDonHang?search=GS-000530&sort=oldest'),('products','/Admin/SanPham/QuanLySanPham'),('report','/Admin/Admin/TongQuan?range=7d')]
        for width in (1440,768,360):
            page.set_viewport_size({'width':width,'height':1000})
            for label,path in routes:
                page.goto(om.QA_BASE+path);page.evaluate('document.fonts.ready');page.wait_for_timeout(400);button=page.locator('[data-excel-export]');expect(button).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(label,width)
                button.focus();assert button.evaluate('e=>getComputedStyle(e).outlineStyle')=='solid'
                button.evaluate("e=>e.scrollIntoView({block:'center',behavior:'instant'})")
                button.hover();page.wait_for_timeout(230);rect=button.bounding_box()
                # Keep the target below the fixed header after Chromium's auto-scroll.
                button.evaluate("e=>e.scrollIntoView({block:'center',behavior:'instant'})");rect=button.bounding_box()
                page.mouse.move(rect['x']+rect['width']/2,rect['y']+rect['height']/2);page.mouse.down()
                page.wait_for_function("e=>getComputedStyle(e).transform!=='none'",arg=button.element_handle(),timeout=2000)
                page.mouse.move(0,0);page.mouse.up()
                page.screenshot(path=str(OUT/f'export-{label}-{width}.png'),full_page=True,animations='disabled')
        page.set_viewport_size({'width':1440,'height':1000});page.goto(om.QA_BASE+routes[0][1]);button=page.locator('[data-excel-export]');url=page.url;href=button.get_attribute('href');assert 'search=GS-000530' in href and 'sort=oldest' in href and 'pageSize' not in href
        pending=[];page.route('**/Admin/DonHang/XuatExcelDonHang**',lambda route:pending.append(route))
        width=button.bounding_box()['width'];button.click();expect(button).to_have_attribute('aria-busy','true');expect(button).to_contain_text('Đang chuẩn bị file');assert abs(button.bounding_box()['width']-width)<1
        button.dispatch_event('click');button.dispatch_event('click');page.wait_for_timeout(100);assert len(pending)==1
        with page.expect_download() as got:pending[0].continue_()
        download_file=got.value;assert re.match(r'GreenShop_DonHang_.*\.xlsx',download_file.suggested_filename);download_file.save_as(str(OUT/'browser-orders.xlsx'));page.unroute('**/Admin/DonHang/XuatExcelDonHang**')
        manifest('browser-orders',[sheet('Đơn hàng',ORDER_HEADERS,order_rows(order_data('o.Id=530','o.CreatedAt,o.Id')))])
        expect(button).not_to_have_attribute('aria-busy','true');expect(button).to_contain_text('Xuất Excel');assert page.url==url
        for label,path in routes[1:]:
            page.goto(om.QA_BASE+path)
            with page.expect_download() as got:page.locator('[data-excel-export]').click()
            got.value.save_as(str(OUT/f'browser-{label}.xlsx'))
            metadata=json.loads((OUT/('products.expected.json' if label=='products' else 'report-7d.expected.json')).read_text());metadata['file']=f'browser-{label}.xlsx';(OUT/f'browser-{label}.expected.json').write_text(json.dumps(metadata))
            expect(page.locator('[data-excel-export]')).not_to_have_attribute('aria-busy','true');assert page.url==om.QA_BASE+path
        page.goto(om.QA_BASE+'/Admin/DonHang/QuanLyDonHang?search=QA-NO-MATCH-EXCEL');page.locator('[data-excel-export]').click();expect(page.locator('.excel-feedback')).to_contain_text('Không có dữ liệu phù hợp');assert page.locator('.excel-feedback').get_attribute('class').endswith('is-error');expect(page.locator('[data-excel-export]')).to_contain_text('Xuất Excel')
        page.goto(om.QA_BASE+routes[0][1]);page.route('**/Admin/DonHang/XuatExcelDonHang**',lambda route:route.fulfill(status=503,content_type='application/json',body=json.dumps({'message':'Chưa thể đọc dữ liệu để xuất Excel. Vui lòng thử lại sau.'})));page.locator('[data-excel-export]').click();expect(page.locator('.excel-feedback')).to_contain_text('Chưa thể đọc dữ liệu');page.unroute('**/Admin/DonHang/XuatExcelDonHang**')
        page.route('**/Admin/DonHang/XuatExcelDonHang**',lambda route:route.abort());page.locator('[data-excel-export]').click();expect(page.locator('.excel-feedback')).to_contain_text('Không thể kết nối');page.unroute('**/Admin/DonHang/XuatExcelDonHang**')
        page.emulate_media(reduced_motion='reduce');assert page.locator('[data-excel-export]').evaluate('e=>getComputedStyle(e).transitionDuration')=='0s'
        assert not errors,errors;context.close();b.close()
    assert dm.snapshot_qa()==before
    print('PASS: Chromium real downloads on all three pages; applied filters/page preserved; 360/768/1440 responsive, hover/pressed/focus/reduced motion, loading stable width, one request on repeated clicks, actual empty error and mocked service/network feedback; no DB mutations.',flush=True)
    (OUT/'export-browser-results.json').write_text(json.dumps({'status':'PASS','checks':'Real three downloads; applied filters, responsive 360/768/1440, stable loading, repeated-click guard, keyboard/motion, empty/server/network feedback, no JS errors','writes':'none'}))

def limits():
    om.configure_qa();admin=om.admin_sessions()[0];before=dm.snapshot_qa();file=OUT/'compose.yaml';original=file.read_text()
    try:
        file.write_text(original.replace('      ASPNETCORE_ENVIRONMENT: Production','      ASPNETCORE_ENVIRONMENT: Production\n      ExcelExport__MaxRows: 5'))
        om.start(False)
        for endpoint in (ORDER,PRODUCT,REPORT):
            code,headers,body=gs.request(admin,endpoint);assert code==422 and 'vượt giới hạn' in body and '.xlsx' not in headers.get('Content-Disposition',''),(endpoint,code)
        file.write_text(original.replace('      ASPNETCORE_ENVIRONMENT: Production','      ASPNETCORE_ENVIRONMENT: Production\n      Dashboard__LowStockThreshold: 3'))
        om.start(False)
        products=data("SELECT HEX(JSON_OBJECT('id',p.Id,'name',p.Name,'category',COALESCE(c.Name,'Chưa phân loại'),'price',p.Price,'stock',p.StockQuantity)) FROM Products p LEFT JOIN Categories c ON c.Id=p.CategoryId ORDER BY p.Id DESC")
        rows=[[i,p['id'],p['name'],p['category'],p['price'],p['stock'],'Hết hàng' if p['stock']==0 else 'Sắp hết hàng' if p['stock']<=3 else 'Còn hàng'] for i,p in enumerate(products,1)]
        download(admin,PRODUCT,'products-configured',[sheet('Sản phẩm & tồn kho',PRODUCT_HEADERS,rows)])
        page=dm.Dashboard(gs.get(admin,'/Admin/Admin/TongQuan')[1]);assert all(int(a['data-stock'])<=3 for _,a in page.nodes if 'data-stock' in a)
    finally:
        file.write_text(original);om.start(False)
    assert dm.snapshot_qa()==before
    print('PASS: Configured limit rejects all three oversized exports without partial files; configured stock threshold shared by Dashboard and Excel; genuine Admin cookie survives web recreation; all QA data unchanged.',flush=True)
    (OUT/'export-limit-results.json').write_text(json.dumps({'status':'PASS','checks':'HTTP row-limit 5 for all exports; threshold 3 shared; genuine cookie persists; no partial file/no business writes'}))

def empty_report():
    om.configure_qa();admin=om.admin_sessions()[0];before=dm.snapshot_qa();original=om.qa_sql('SELECT Id,CreatedAt,Status FROM Orders ORDER BY Id')
    try:
        om.qa_sql("UPDATE Orders SET CreatedAt='2020-01-01'")
        code,headers,body=gs.request(admin,REPORT);assert code==404 and 'Không có dữ liệu' in body and '.xlsx' not in headers.get('Content-Disposition','')
        om.qa_sql('UPDATE Orders SET CreatedAt=UTC_TIMESTAMP(),Status=0')
        now=datetime.now(timezone.utc);start,end=dm.period('7d',now);start=start.astimezone(dm.LOCAL).replace(tzinfo=None);end=end.astimezone(dm.LOCAL).replace(tzinfo=None)
        count=int(om.qa_sql('SELECT COUNT(*) FROM Orders'))
        summary=[['Từ ngày (GMT+7)',{'date':start.isoformat()}],['Đến hết ngày (GMT+7)',{'date':(end-timedelta(days=1)).isoformat()}],['Tổng số đơn đặt trong kỳ',count],['Số đơn đã giao',0],['Số đơn đã hủy',0],['Số đơn đã xác nhận / đang xử lý',0],['Giá trị đơn đã giao',0],['Số lượng sản phẩm đã bán',0],['Đơn đã giao chưa xác nhận thanh toán',0]]
        summary.extend([['Phí ship đã ghi nhận trong các đơn đã giao',0],['Đơn đã giao thiếu chi tiết phí ship',0]])
        timeline=[[{'date':(start+timedelta(days=i)).isoformat()},0,0,0] for i in range(7)]
        download(admin,REPORT+'?range=7d','report-zero-delivered',[sheet('Tổng quan',['Chỉ số','Giá trị'],summary,False),sheet('Theo thời gian',['Ngày (GMT+7)','Số đơn đã giao','Giá trị đơn đã giao','Số lượng sản phẩm đã bán'],timeline)])
    finally:
        for row in original.splitlines():i,date,status=row.split('\t');om.qa_sql(f'UPDATE Orders SET CreatedAt={gs.quote(date)},Status={status} WHERE Id={i}')
    assert dm.snapshot_qa()==before
    print('PASS: Empty report gives clear non-file 404; pending-only report has correct numeric zero value/counts and daily buckets, no divide by zero; isolated fixtures restored exactly.',flush=True)
    (OUT/'export-empty-results.json').write_text(json.dumps({'status':'PASS','checks':'Empty period 404; pending-only value 0 workbook; fixtures restored'}))

def production():
    om.production_checks();client=gs.client()
    for endpoint in (ORDER,PRODUCT,REPORT):
        code,headers,_=gs.request(client,endpoint);assert code==302 and '/Account/Login' in headers.get('Location','')
    for path in ('/css/admin-excel.css','/js/admin-excel.js'):
        code,_,body=gs.request(client,path);assert code==200 and len(body)>100
    verify_migrations(gs.sql)
    real=gs.compose('ps','-q','web_app');qa=om.qa_compose('ps','-q','web_app')
    def identity(container):return subprocess.check_output(['docker','inspect','--format','{{.Image}}',container],text=True).strip()
    assert identity(real)==identity(qa)
    (OUT/'excel-production-results.json').write_text(json.dumps({'status':'PASS','checks':'HTTPS, no 502, web/database healthy; export routes Admin-protected, assets 200; actual deployed image matches authenticated QA downloads; source-matched migration IDs','scope':'Production read-only; legitimate authenticated downloads verified on isolated identical image'}))
    print('PASS: Production HTTPS/routes/assets/health, source-matched migration IDs, same image as authenticated QA downloads; no production business writes.',flush=True)

OUT=PRIVATE/'qa';OUT.mkdir(mode=0o700,exist_ok=True)
om.OUT=dm.OUT=dm.us.OUT=OUT;om.QA_PROJECT=PROJECT

def baseline():
    om.baseline()
    file=OUT/'baseline.json';value=json.loads(file.read_text());value['extra']=dm.extra_snapshot()
    value['protected_sources']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (gs.ROOT/'backend/GreenShop.Web').rglob('*') if p.is_file() and p.suffix in ('.cs','.cshtml','.css','.js') and not any(x in p.parts for x in ('obj','bin'))}
    file.write_text(json.dumps(value));os.chmod(file,0o600)
    print('PASS: Private production baseline captured; no business data changed.',flush=True)

def prepare():
    om.prepare()
    for name in ('keys','images'):(OUT/name).mkdir(mode=0o700,exist_ok=True)
    file=OUT/'compose.yaml'
    file.write_text(file.read_text().replace('    environment:\n      ASPNETCORE_ENVIRONMENT: Production',f'    volumes:\n      - {OUT}/keys:/app/keys\n      - {OUT}/images:/app/wwwroot/uploads/products\n    environment:\n      ASPNETCORE_ENVIRONMENT: Production'))

if __name__=='__main__':
    {'baseline':baseline,'prepare':prepare,'start':om.start,'refresh':lambda:om.start(False),'business':om.run_business,'admin-regression':om.browser_checks,'edge':om.edge_checks,'teardown':om.teardown,'fixtures':fixtures,'exports':exports,'authorization':authorization,'roundtrip':roundtrip,'preservation':preservation,'dashboard-regression':dm.metrics,'browser':browser,'limits':limits,'empty-report':empty_report,'user-regression':lambda:dm.us.business(False),'production':production}[sys.argv[1]]()
