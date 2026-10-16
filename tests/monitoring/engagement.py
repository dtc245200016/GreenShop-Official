from pathlib import Path
import importlib.util,sys,json,os,uuid
R=Path('/home/trung/GreenShop-Official') if Path(__file__).parent==Path('/tmp') else Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tests'))
spec=importlib.util.spec_from_file_location('m2',R/'tests/monitoring/acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import storefront_regression as gs
gs.BASE=m.BASE;db=m.qa_name('db');assert m.inspect(db)['Config']['Labels']['com.docker.compose.project']==m.PROJECT
gs.sql=lambda q:m.sql(db,q,db='greenshop_m2_qa')
accounts=json.loads((m.QA/'accounts.json').read_text())
def sign_in(portal):
 c=gs.client();path='/Admin/Account/Login' if portal=='admin' else '/Account/Login';page=gs.get(c,path)[0]
 assert gs.post(c,path,page,{'Email':accounts[portal][0],'Password':accounts[portal][1]})[0]==302
 return c
admin=sign_in('admin');customer=sign_in('customer')
# Full checkout with the actual default shipping fee; completion uses the real Admin workflow.
pid=int(gs.sql('SELECT Id FROM Products ORDER BY Id LIMIT 1'))
page,values=gs.confirm(customer,pid,1)
code,headers,_=gs.post(customer,f'/ThanhToan/XacNhanMuaHang/{pid}',page,values);assert code==302
oid=int(headers['Location'].rsplit('/',1)[-1]);assert gs.sql(f'SELECT Subtotal,ShippingFee,Total FROM Orders WHERE Id={oid}')=='100000.00\t30000.00\t130000.00'
for status in [3,4,5,1]:
 page=gs.get(admin,f'/Admin/DonHang/ChiTietDonHang/{oid}')[0]
 version=gs.sql(f'SELECT Version FROM Orders WHERE Id={oid}')
 code,_,_=gs.post(admin,f'/Admin/DonHang/CapNhatTrangThaiDonHang/{oid}',page,{'ExpectedVersion':version,'TargetStatus':status})
 assert code==302,(status,code)
item=int(gs.sql(f'SELECT Id FROM OrderItems WHERE OrderId={oid}'))
page=gs.get(customer,f'/TuongTac/DanhGia/{item}')[0]
assert gs.post(customer,f'/TuongTac/DanhGia/{item}',page,{'Stars':5,'Content':'M2 QA review after completed order'})[0]==302
rid=int(gs.sql(f'SELECT Id FROM ProductReviews WHERE OrderItemId={item}'))
page=gs.get(admin,f'/Admin/KhachHang/DanhGia?reviewId={rid}')[0]
assert gs.post(admin,f'/Admin/KhachHang/PhanHoiDanhGia/{rid}',page,{'Version':gs.sql(f'SELECT Version FROM ProductReviews WHERE Id={rid}'),'Content':'M2 QA shop review reply'})[0]==302
assert 'M2 QA shop review reply' in gs.get(gs.client(),f'/SanPham/ChiTietSanPham/{pid}')[1]
source=gs.get(customer,'/')[0];message='M2 QA customer support '+uuid.uuid4().hex
r=gs.post(customer,'/TuongTac/GuiTinNhan',source,{'Content':message,'RequestToken':uuid.uuid4().hex});assert r[0]==200
mid=json.loads(r[2])['id'];cid=int(gs.sql(f'SELECT ConversationId FROM ShopMessages WHERE Id={mid}'))
page=gs.get(admin,f'/Admin/KhachHang/TroChuyen/{cid}')[0]
reply='M2 QA Admin live reply '+uuid.uuid4().hex
assert gs.post(admin,f'/Admin/KhachHang/GuiTinNhan/{cid}',page,{'Content':reply,'RequestToken':uuid.uuid4().hex})[0]==200
assert json.loads(gs.request(customer,'/TuongTac/TinNhanMoi')[2])['messages'][-1]['content']==reply

from playwright.sync_api import sync_playwright,expect
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE'))
 context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});page=context.new_page();errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(m.BASE+'/Account/Login');page.locator('#Email').fill(accounts['customer'][0]);page.locator('[name=Password]').fill(accounts['customer'][1]);page.locator('form:has(#Email) button[type=submit]').click()
 page.goto(m.BASE+'/?chat=shop')
 expect(page.locator('[data-widget-chat]')).to_have_attribute('data-realtime','connected',timeout=20000)
 page.screenshot(path=str(m.EVIDENCE/'qa-floating-chat.png'),full_page=True)
 for width in [390,1440]:
  page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors
 # Real SignalR negotiation is also protected against missing/foreign origin.
 no_origin=context.request.post(m.BASE+'/supportHub/negotiate?negotiateVersion=1');assert no_origin.status==403
 browser.close()
m.record('engagement-regression',{'status':'PASS','time':m.now(),'checks':['real checkout subtotal 100000 + shipping 30000 = total 130000','Admin advances order through 3/4/5/1 over HTTP with CSRF/version','Customer review after completed purchase','Admin reply stored and visible on public product','Customer message and Admin reply via actual support endpoints','floating hybrid chat renders at mobile/desktop widths','SignalR reaches connected state','SignalR without valid Origin rejected 403','no browser JavaScript errors'],'writes':'synthetic QA only'})
print('PASS: shipping checkout, real Admin order workflow, reviews/replies, support messages and live SignalR floating chat.',flush=True)
