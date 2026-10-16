from qa_support import verify_migrations
from qa_support import PRIVATE, PROJECT
"""Dashboard QA uses a separate Compose/MySQL project; production checks are read-only."""
import sys,os,json,re,subprocess,http.cookiejar,urllib.request,ssl,html,hashlib
from pathlib import Path
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from html.parser import HTMLParser
import order_management as om
import user_management as us
import storefront_regression as gs

OUT=PRIVATE/'qa';OUT.mkdir(mode=0o700,exist_ok=True)
om.OUT=us.OUT=OUT;om.QA_PROJECT=PROJECT
BASE='/Admin/Admin/TongQuan'
LOCAL=timezone(timedelta(hours=7))

class Dashboard(HTMLParser):
    def __init__(self,body):
        super().__init__();self.attrs={};self.metrics={};self.nodes=[];self.key=None;self.read=False;self.product_depth=0;self.product_id=None;self.product_text={};self.feed(body)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.nodes.append((tag,a))
        if 'data-best-id' in a:
            self.product_id=a['data-best-id'];self.product_text[self.product_id]='';self.product_depth=1
        elif self.product_depth and tag=='div':self.product_depth+=1
        if 'dashboard' in a.get('class','').split():self.attrs=a
        if 'data-metric' in a:self.key=a['data-metric']
        if 'dash-value' in a.get('class','').split():self.read=True;self.metrics[self.key]=''
    def handle_endtag(self,tag):
        if tag=='div' and self.product_depth:
            self.product_depth-=1
            if not self.product_depth:self.product_id=None
        if tag=='strong':self.read=False
        if tag=='article':self.key=None
    def handle_data(self,data):
        if self.read:self.metrics[self.key]+=data
        if self.product_id is not None:self.product_text[self.product_id]+=data

def prepare():
    om.prepare()

def upgrade():
    import m1_acceptance as acceptance
    acceptance.migration_upgrade()

def period(range,now):
    today=now.astimezone(LOCAL).replace(hour=0,minute=0,second=0,microsecond=0)
    start= today-timedelta(days=6 if range=='7d' else 29) if range in ('7d','30d') else today.replace(day=1) if range=='month' else today.replace(month=1,day=1)
    return start.astimezone(timezone.utc),(today+timedelta(days=1)).astimezone(timezone.utc)

def stamp(dt):return dt.strftime('%Y-%m-%d %H:%M:%S.%f')
def numeric(text):return Decimal(text.replace(' đ','').replace('.','').replace(',','.'))
def dates():
    folder=OUT/'date-checks';folder.mkdir(exist_ok=True)
    assembly=gs.ROOT/'backend/GreenShop.Web/bin/Release/net8.0/GreenShop.Web.dll'
    (folder/'Dates.csproj').write_text(f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup><ItemGroup><FrameworkReference Include="Microsoft.AspNetCore.App"/><Reference Include="GreenShop.Web"><HintPath>{assembly}</HintPath></Reference></ItemGroup></Project>')
    (folder/'Program.cs').write_text('''using GreenShop.Web.Models;
void Check(bool ok) { if (!ok) throw new Exception("Date/comparison assertion failed"); }
DateTime U(string s) => DateTime.Parse(s,null,System.Globalization.DateTimeStyles.AdjustToUniversal|System.Globalization.DateTimeStyles.AssumeUniversal);
var before=DashboardPeriod.Create("year",U("2026-12-31T16:59:59Z"));
Check(before.LocalStart==new DateTime(2026,1,1) && before.EndUtc==U("2026-12-31T17:00:00Z"));
var after=DashboardPeriod.Create("year",U("2026-12-31T17:00:00Z"));
Check(after.LocalStart==new DateTime(2027,1,1) && after.StartUtc==U("2026-12-31T17:00:00Z") && after.EndUtc==U("2027-01-01T17:00:00Z"));
var leap=DashboardPeriod.Create("month",U("2028-02-29T12:00:00Z"));
Check((leap.LocalEnd-leap.LocalStart).Days==29 && leap.StartUtc==U("2028-01-31T17:00:00Z") && leap.EndUtc==U("2028-02-29T17:00:00Z"));
foreach(var r in new[]{"7d","30d","month","year","unsafe"}) { var p=DashboardPeriod.Create(r,U("2027-01-01T00:00:00Z")); Check(p.StartUtc-p.PreviousStartUtc==p.EndUtc-p.StartUtc); }
Check(DashboardPeriod.Create("unsafe",U("2027-01-01T00:00:00Z")).Range=="30d");
Check(AdminDashboardViewModel.Comparison(100,0)=="Chưa đủ dữ liệu so sánh" && AdminDashboardViewModel.Comparison(0,0)=="Chưa đủ dữ liệu so sánh");
Check(AdminDashboardViewModel.Comparison(125,100)=="+25% so với kỳ trước" && AdminDashboardViewModel.Comparison(0,100)=="-100% so với kỳ trước");
Console.WriteLine("PASS: Actual production date helper: Vietnam midnight/year rollover, leap February, equal previous windows, invalid fallback and zero-safe growth.");
''')
    subprocess.run(['dotnet','build',str(folder/'Dates.csproj'),'--configuration','Release','--nologo'],check=True)
    subprocess.run(['dotnet',str(folder/'bin/Release/net8.0/Dates.dll')],check=True)
    (OUT/'dashboard-date-results.json').write_text(json.dumps({'status':'PASS','checks':'Production .NET date helper: Vietnam midnight/month/year/leap-year boundaries; equal previous period; zero-safe comparison'}))
def snapshot_qa():
    return {table:om.qa_sql(f'SELECT * FROM {table} ORDER BY Id') for table in ('Users','Products','Categories','Orders','OrderItems','OrderStatusHistories','CartItems')}

def fixtures():
    om.configure_qa()
    assert om.qa_sql('SELECT COUNT(*) FROM Products WHERE Id>=501 AND Id<=510')=='0'
    for i,stock in enumerate((0,1,5,6,25),501):
        name='QA Dash Plant '+str(i) if i!=505 else '<script>alert("dashboard")</script>'
        om.qa_sql(f"INSERT INTO Products (Id,Name,Price,ImageUrl,Description,StockQuantity) VALUES ({i},{gs.quote(name)},987654.99,'/uploads/products/nonexistent-dashboard.png','QA Dash',{stock})")
    now=datetime.now(timezone.utc);dates=[]
    for range in ('7d','30d','month','year'):
        start,end=period(range,now);dates.extend((start-timedelta(microseconds=1),start,end-timedelta(microseconds=1),end))
    # Both sides of Vietnam midnight, month/year, and previous-period boundaries.
    dates.extend((now,now-timedelta(days=45),now-timedelta(days=370)))
    for i,date in enumerate(dates,501):
        status=(1,1,5,1,2,0,4,3)[(i-501)%8];paid=int(i%2==0);qty=(i%4)+1
        product=501+i%5;total=Decimal('12.34')*qty
        if status==2:total=Decimal('999999.99')
        om.qa_sql(f"INSERT INTO Orders (Id,UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES ({i},3,'{i:032x}','QA Dash recipient','0912345678','QA Dash address',{gs.quote(stamp(date))},{total},{status},{paid},'COD',1,'',0); INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES ({i},{product},'Historical name','/images/product-placeholder.svg',12.34,{qty});")
    i=530
    om.qa_sql(f"INSERT INTO Orders (Id,UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES ({i},3,'{i:032x}','QA Deleted snapshot','0912345678','QA Dash address',UTC_TIMESTAMP(),37.02,1,0,'COD',1,'',0); INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES ({i},NULL,'QA Deleted plant','/uploads/products/missing-historical.png',12.34,3);")
    # Duplicate payment history must never multiply sales aggregates.
    om.qa_sql("INSERT INTO OrderStatusHistories (OrderId,Kind,CreatedAt,AdminId,AdminName,Note) VALUES (530,2,UTC_TIMESTAMP(),1,'QA','Synthetic duplicate history'),(530,2,UTC_TIMESTAMP(),1,'QA','Synthetic duplicate history')")
    start,_=period('30d',now)
    for i,date in ((501,start),(502,start-timedelta(microseconds=1))):
        om.qa_sql(f"INSERT INTO Users (Id,FullName,Email,PasswordHash,Phone,Role,CreatedAt,IsActive,Version,SessionVersion) SELECT {i},'QA Dash Customer','qa-dash-{i}@example.invalid',PasswordHash,'',0,{gs.quote(stamp(date))},1,0,0 FROM Users WHERE Id=3")
    print('PASS: Dashboard boundary/status/paid/unpaid/history/deleted-product/stock fixtures created only in isolated database.',flush=True)

def metrics():
    om.configure_qa();admin=om.admin_sessions()[0];before=snapshot_qa();checks=[]
    def passed(s):checks.append(s);print('PASS: '+s,flush=True)
    customer=gs.client();gs.login(customer,json.loads((OUT/'accounts.json').read_text())[2])
    for c in (gs.client(),customer):
        for path in ('/Admin','/Admin/Admin/Index',BASE,BASE+'?range=year'):
            code,headers,_=gs.request(c,path);assert code==302 and ('Login' in headers['Location'] or 'AccessDenied' in headers['Location'])
    for path in ('/Admin','/Admin/Admin/Index'):
        code,h,_=gs.request(admin,path+'?range=7d');assert code==302 and h['Location'].endswith('/Admin/Admin/TongQuan?range=7d')
    assert gs.request(admin,BASE,{'range':'7d'})[0]==405
    passed('Anonymous/Customer denied; Admin authorized; legacy routes redirect safely with range retained; Dashboard is GET only')
    now=datetime.now(timezone.utc)
    for range in ('7d','30d','month','year','invalid'):
        actual=range if range!='invalid' else '30d';start,end=period(actual,now)
        body=gs.request(admin,BASE+'?range='+range)[2];page=Dashboard(body)
        assert page.attrs['data-range']==actual
        assert datetime.fromisoformat(page.attrs['data-start'])==start and datetime.fromisoformat(page.attrs['data-end'])==end
        prev=start-(end-start);assert datetime.fromisoformat(page.attrs['data-previous'])==prev
        where=f"CreatedAt>={gs.quote(stamp(start))} AND CreatedAt<{gs.quote(stamp(end))}"
        expected=om.qa_sql(f"SELECT COUNT(*),COALESCE(SUM(CASE WHEN Status=1 THEN Total ELSE 0 END),0),SUM(Status=5),SUM(Status=0) FROM Orders WHERE {where}").split('\t')
        assert numeric(page.metrics['orders'])==int(expected[0])
        assert numeric(page.metrics['value'])==Decimal(expected[1])
        assert numeric(page.metrics['shipping'])==int(expected[2]) and numeric(page.metrics['pending'])==int(expected[3])
        assert numeric(page.metrics['customers'])==int(om.qa_sql(f'SELECT COUNT(*) FROM Users WHERE Role=0 AND {where}'))
        assert numeric(page.metrics['sold'])==int(om.qa_sql(f"SELECT COALESCE(SUM(i.Quantity),0) FROM OrderItems i JOIN Orders o ON o.Id=i.OrderId WHERE o.Status=1 AND o.{where}"))
        actual_counts={int(a['data-status']):int(a['data-count']) for _,a in page.nodes if 'data-status' in a}
        expected_counts={int(s):int(n) for s,n in (row.split('\t') for row in om.qa_sql(f'SELECT Status,COUNT(*) FROM Orders WHERE {where} GROUP BY Status').splitlines())}
        assert all(actual_counts.get(s)==expected_counts.get(s,0) for s in (0,1,2,3,4,5))
        chart={a['data-point']:Decimal(a['data-amount']) for _,a in page.nodes if 'data-point' in a}
        fmt='%Y-%m' if actual=='year' else '%Y-%m-%d'
        sqlchart={key:Decimal(value) for key,value in (r.split('\t') for r in om.qa_sql(f"SELECT DATE_FORMAT(DATE_ADD(CreatedAt,INTERVAL 7 HOUR),'{fmt}'),SUM(Total) FROM Orders WHERE Status=1 AND {where} GROUP BY 1").splitlines())}
        assert all(value==sqlchart.get(key,0) for key,value in chart.items()) and sum(chart.values())==Decimal(expected[1])
        assert len(chart)==(now.astimezone(LOCAL).month if actual=='year' else (end-start).days)
        recent=[int(a['data-recent-order']) for _,a in page.nodes if 'data-recent-order' in a]
        assert recent==[int(x) for x in om.qa_sql(f'SELECT Id FROM Orders WHERE {where} ORDER BY CreatedAt DESC,Id DESC LIMIT 7').splitlines()]
        best=[(a.get('data-best-id',''),a['data-best-name'],int(a['data-sold'])) for _,a in page.nodes if 'data-sold' in a]
        expected_best=om.qa_sql(f"SELECT COALESCE(i.ProductId,''),COALESCE(p.Name,MAX(i.ProductName)),SUM(i.Quantity) FROM OrderItems i JOIN Orders o ON o.Id=i.OrderId LEFT JOIN Products p ON p.Id=i.ProductId WHERE o.Status=1 AND o.{where} GROUP BY i.ProductId,CASE WHEN i.ProductId IS NULL THEN i.ProductName ELSE '' END,p.Name ORDER BY SUM(i.Quantity) DESC,i.ProductId,CASE WHEN i.ProductId IS NULL THEN i.ProductName ELSE '' END LIMIT 5")
        assert best==[(a,b,int(c)) for a,b,c in (r.split('\t') for r in expected_best.splitlines())]
        stock=[(int(a['data-stock-id']),int(a['data-stock'])) for _,a in page.nodes if 'data-stock-id' in a]
        assert stock==[(int(a),int(b)) for a,b in (r.split('\t') for r in om.qa_sql('SELECT Id,StockQuantity FROM Products WHERE StockQuantity<=5 ORDER BY StockQuantity,Id LIMIT 5').splitlines())]
        tasks={a['data-task']:int(a['data-count']) for _,a in page.nodes if 'data-task' in a}
        for key,condition in [('pending','Status=0'),('processing','Status=4'),('cod',"Status=1 AND NOT IsPaid AND PaymentMethod='COD'")]:
            count=int(om.qa_sql('SELECT COUNT(*) FROM Orders WHERE '+condition));assert tasks.get(key,0)==count
        assert tasks.get('stock',0)==int(om.qa_sql('SELECT COUNT(*) FROM Products WHERE StockQuantity<=5'))
        # Never interpolate a stored script/name as executable markup.
        assert '<script>alert("dashboard")</script>' not in body
        # Other suites may legitimately displace the seeded fixture from Top 5.
        # Validate each product actually selected by the independent SQL ranking.
        for pid,_,_ in best:
            if not pid:continue
            price=Decimal(om.qa_sql(f'SELECT Price FROM Products WHERE Id={int(pid)}'))
            rendered=(f'{price:,.0f}' if price==price.to_integral_value() else f'{price:,.2f}').replace(',','_').replace('.',',').replace('_','.')+' đ'
            assert rendered in page.product_text[pid],(range,pid,rendered,page.product_text[pid])
        previous_value=Decimal(om.qa_sql(f"SELECT COALESCE(SUM(Total),0) FROM Orders WHERE Status=1 AND CreatedAt>={gs.quote(stamp(prev))} AND CreatedAt<{gs.quote(stamp(start))}"))
        if previous_value==0:assert 'Chưa đủ dữ liệu so sánh' in html.unescape(body)
        passed(f'{range}: KPIs, GMT+7 boundaries, equal previous period, chart buckets, stable recent orders, top selling and current-state alerts match independent SQL')
    assert before==snapshot_qa()
    passed('Dashboard GETs leave all users, orders/history, products/stock, categories and carts byte-for-byte unchanged')
    (OUT/'dashboard-metric-results.json').write_text(json.dumps({'status':'PASS','checks':checks},indent=2))

def empty():
    om.configure_qa();before=om.qa_sql('SELECT Id,CreatedAt,Status FROM Orders ORDER BY Id');user_dates=om.qa_sql('SELECT Id,CreatedAt FROM Users ORDER BY Id');stocks=om.qa_sql('SELECT Id,StockQuantity FROM Products ORDER BY Id')
    # Temporarily move only this disposable schema's fixtures out of current year, then restore all values.
    try:
        om.qa_sql("UPDATE Orders SET CreatedAt='2020-01-01',Status=2; UPDATE Users SET CreatedAt='2020-01-01'; UPDATE Products SET StockQuantity=100")
        admin=om.admin_sessions()[0];body=gs.get(admin,BASE)[1];page=Dashboard(body)
        assert all(numeric(page.metrics[k])==0 for k in ('orders','value','customers','sold','shipping','pending'))
        assert not any('data-task' in a for _,a in page.nodes)
        assert 'Chưa có đơn hàng trong kỳ' in body and 'Chưa có dữ liệu bán hàng trong kỳ' in body and 'Không có sản phẩm tồn kho thấp' in body and 'Chưa đủ dữ liệu so sánh' in body
        browser(empty=True,configured=True)
    finally:
        for row in before.splitlines():i,date,status=row.split('\t');om.qa_sql(f'UPDATE Orders SET CreatedAt={gs.quote(date)},Status={status} WHERE Id={i}')
        for row in user_dates.splitlines():i,date=row.split('\t');om.qa_sql(f'UPDATE Users SET CreatedAt={gs.quote(date)} WHERE Id={i}')
        for row in stocks.splitlines():i,stock=row.split('\t');om.qa_sql(f'UPDATE Products SET StockQuantity={stock} WHERE Id={i}')
    (OUT/'dashboard-empty-results.json').write_text(json.dumps({'status':'PASS','checks':'No fake KPI, previous comparison, chart, recent orders, bestseller, stock or action alert in empty period; zero-data browser screenshots captured'}))
    print('PASS: Empty/zero charts, truthful comparison, empty widgets and no false alerts; isolated fixtures restored.',flush=True)

def browser(empty=False,configured=False):
    if not configured:om.configure_qa()
    from playwright.sync_api import sync_playwright,expect
    account=json.loads((OUT/'accounts.json').read_text())[0];checks=[]
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True);c=b.new_context(ignore_https_errors=True);page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(om.QA_BASE+'/Account/Login');page.locator('#Email').fill(account[0]);page.locator('[name=Password]').fill(account[1]);page.locator('form:has(#Email) button[type=submit]').click();expect(page).to_have_url(om.QA_BASE+BASE)
        for width in (1440,768,360):
            page.set_viewport_size({'width':width,'height':1000});page.goto(om.QA_BASE+BASE)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,page.evaluate("[...document.querySelectorAll('.dashboard *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,6).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width])"))
            expect(page.locator('.admin-sidebar [aria-current=page]')).to_have_text('Tổng quan')
            assert not re.search(r'@(if|foreach|Model)',page.locator('.dashboard').inner_text())
            page.screenshot(path=str(OUT/f'dashboard-{"empty" if empty else "filled"}-{width}.png'),full_page=True,animations='disabled')
        checks.append('Actual Dashboard login, sidebar and screenshots at 360/768/1440; no overflow/unrendered Razor')
        if not empty:
            page.set_viewport_size({'width':1440,'height':1000})
            for range in ('7d','year','month','30d'):
                page.locator('#dashRange').select_option(range);page.get_by_role('button',name='Áp dụng').click();expect(page.locator('.dashboard')).to_have_attribute('data-range',range);expect(page.locator('#dashRange')).to_have_value(range)
            bar=page.locator('.dash-bar').first;bar.hover();expect(page.locator('.dash-chart-tooltip')).to_be_visible();expect(page.locator('.dash-chart-tooltip')).to_contain_text('đ')
            bar.focus();expect(page.locator('.dash-chart-tooltip')).to_be_visible();page.keyboard.press('Escape');expect(page.locator('.dash-chart-tooltip')).not_to_be_visible()
            page.locator('.dash-data summary').click();expect(page.locator('[data-point]').first).to_be_visible()
            card=page.locator('.dash-kpi').first;card.hover();assert card.evaluate('e=>getComputedStyle(e).transform')!='none'
            page.emulate_media(reduced_motion='reduce');card.hover();assert card.evaluate('e=>getComputedStyle(e).transform')=='none'
            button=page.get_by_role('button',name='Áp dụng');page.locator('#dashRange').focus();page.keyboard.press('Tab');expect(button).to_be_focused();assert button.evaluate('e=>getComputedStyle(e).outlineStyle')=='solid'
            assert page.locator('.dash-kpi').first.evaluate('e=>getComputedStyle(e).transitionDuration')=='0s'
            contrast=page.evaluate("""() => {
                const luminance=s=>s.match(/\\d+(?:\\.\\d+)?/g).slice(0,3).map(Number).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0);
                return ['.dash-kpi h2','.dash-kpi small','.dash-caption','.dash-primary','.dash-link','.dash-tag'].map(selector=>{
                    let e=document.querySelector(selector),bg=e;while(bg && getComputedStyle(bg).backgroundColor==='rgba(0, 0, 0, 0)')bg=bg.parentElement;
                    const a=luminance(getComputedStyle(e).color),b=luminance(getComputedStyle(bg).backgroundColor);return [selector,(Math.max(a,b)+.05)/(Math.min(a,b)+.05)];
                });
            }""")
            assert all(ratio>=4.5 for _,ratio in contrast),contrast
            # Follow real links and verify their destination; stored image fallback works.
            images=page.locator('[data-dashboard-image]');images.first.scroll_into_view_if_needed();expect(images.first).to_have_attribute('src','/images/product-placeholder.svg')
            for selector in ('.dash-status-row[data-status="5"]','.dash-recent [data-recent-order] .dash-btn','.dash-shortcuts a', '#stockAlerts .dash-product-row .dash-btn','[data-task=cod]'):
                link=page.locator(selector).first;href=link.get_attribute('href');response=page.goto(om.QA_BASE+href);assert response.status==200,(selector,href,response.status)
                page.goto(om.QA_BASE+BASE)
            checks.append('Real range submits, keyboard/mouse tooltips, accessible data table, hover/focus/reduced-motion, sampled text/button contrast >=4.5:1, fallback images and all drill-through links')
            # SVG/data table do not depend on external chart scripts or JavaScript.
            offline=b.new_context(ignore_https_errors=True,java_script_enabled=False,storage_state=c.storage_state());fallback=offline.new_page();fallback.goto(om.QA_BASE+BASE);expect(fallback.locator('.dash-svg')).to_be_visible();fallback.locator('summary').click();expect(fallback.locator('[data-point]').first).to_be_visible();offline.close()
            checks.append('Chart and accessible data table remain usable without JavaScript/chart CDN')
        assert not errors,errors;c.close();b.close()
    if not empty:(OUT/'dashboard-browser-results.json').write_text(json.dumps({'status':'PASS','checks':checks},indent=2))
    for check in checks:print('PASS: '+check,flush=True)

def extra_snapshot():
    sources=['Program.cs','Controllers/AccountController.cs','Data/AppDbContext.cs','Models/User.cs','Models/Shopping.cs',
        'Services/UserSession.cs','Services/AdminUserService.cs','Services/AdminOrderService.cs','Services/ProductImageStorage.cs','Services/StoreCatalog.cs']
    root=gs.ROOT/'backend/GreenShop.Web'
    return {
        'user_status':gs.sql('SELECT Id,SHA2(CONCAT_WS(CHAR(31),IsActive,Version,SessionVersion),256) FROM Users ORDER BY Id'),
        'order_workflow':gs.sql('SELECT Id,SHA2(CONCAT_WS(CHAR(31),Version,InventoryStatus,AdminNote),256) FROM Orders ORDER BY Id'),
        'order_history':gs.sql("SELECT Id,SHA2(CONCAT_WS(CHAR(31),OrderId,Kind,COALESCE(FromStatus,-1),COALESCE(ToStatus,-1),CreatedAt,COALESCE(AdminId,0),AdminName,Note),256) FROM OrderStatusHistories ORDER BY Id"),
        'protected_sources':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sources}
    }

def capture_extra():
    file=OUT/'baseline.json';baseline=json.loads(file.read_text());assert 'extra' not in baseline
    baseline['extra']=extra_snapshot();file.write_text(json.dumps(baseline,indent=2))
    print('PASS: Additional user-session/order-history/source hashes captured before production deployment.',flush=True)

def preservation():
    before=json.loads((OUT/'baseline.json').read_text());after=om.real_snapshot()
    for k in ('products','categories','users','images','keys','infrastructure_source','containers','Orders','OrderItems','CartItems','migrations'):assert before[k]==after[k],k
    for path,digest in before['admin_source'].items():
        if path.endswith(('AdminController.cs','Admin/Index.cshtml','Shared/_AdminLayout.cshtml')):continue
        assert after['admin_source'][path]==digest,path
    if 'extra' in before:assert before['extra']==extra_snapshot()
    (OUT/'dashboard-preservation-results.json').write_text(json.dumps({'status':'PASS','checks':'Real users/passwords/roles, orders/items/cart, products/stock/categories/images/keys/migrations/other containers and existing Admin modules unchanged'}))
    print('PASS: Real data, existing modules, infrastructure, keys/images, migration history and other containers preserved.',flush=True)

def production():
    om.production_checks();client=gs.client()
    for path in ('/Admin','/Admin/Admin/Index',BASE,BASE+'?range=year'):
        code,headers,_=gs.request(client,path);assert code==302 and '/Account/Login' in headers.get('Location','')
    for path in ('/css/admin-dashboard.css','/js/admin-dashboard.js'):
        code,_,body=gs.request(client,path);assert code==200 and len(body)>100
    verify_migrations(gs.sql)
    gs.compose('exec','-T','nginx','nginx','-t')
    (OUT/'dashboard-production-results.json').write_text(json.dumps({'status':'PASS','checks':'Public storefront/auth HTTPS 200; Admin Dashboard guards; new assets 200; web/DB healthy; Nginx valid; no new migration; no business writes'}))
    print('PASS: Production read-only smoke, Dashboard authorization guards/assets, HTTPS and healthchecks.',flush=True)

if __name__=='__main__':
    modes={'baseline':om.baseline,'capture-extra':capture_extra,'prepare':prepare,'start':om.start,'refresh':lambda:om.start(False),'upgrade':upgrade,'fixtures':fixtures,'metrics':metrics,'dates':dates,'browser':browser,'empty':empty,'preservation':preservation,'production':production,'teardown':om.teardown,'user-business':lambda:us.business(check_legacy=False),'user-browser':us.browser,'order-business':om.run_business,'order-edge':om.edge_checks,'order-browser':om.browser_checks}
    modes[sys.argv[1]]()
