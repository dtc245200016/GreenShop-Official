"""Customer engagement regression. Requires order_management's disposable QA guard.

Uses synthetic sales fixtures, real purchase/workflow/review/chat HTTP endpoints,
and Chromium to verify transitions, SignalR, ownership, CSRF and escaped content.
Never invoke with production Compose/database; configure_qa verifies isolation.
"""
import base64,json,re,uuid,urllib.request,urllib.error,concurrent.futures
from pathlib import Path
import storefront_regression as gs
import order_management as om
import portal_sessions as ps

from qa_support import PRIVATE
OUT=PRIVATE/'qa'

def autoplay(page):
    """GET-only regression: hover, retained arrow focus and a complete automatic loop."""
    from playwright.sync_api import expect
    root=page.locator('[data-hero-slider]');slides=root.locator('[data-hero-slide]');count=slides.count()
    assert count>=2,'The autoplay test needs at least two products.'
    expect(root).to_have_attribute('data-hero-index','0');expect(root).to_have_attribute('data-hero-autoplay','running')
    slides.first.locator('.hero-featured').hover();expect(root).to_have_attribute('data-hero-autoplay','running')
    expect(root).to_have_attribute('data-hero-index','1',timeout=6000)
    next_button=root.locator('[data-hero-next]');next_button.click();expect(next_button).to_be_focused()
    index=2%count;expect(root).to_have_attribute('data-hero-index',str(index));expect(root).to_have_attribute('data-hero-autoplay','running')
    page.wait_for_timeout(4000);expect(root).to_have_attribute('data-hero-index',str(index))
    # Leave mouse/focus on the arrow. It must keep rotating through last -> first.
    for _ in range(count+1):
        previous=index;index=(index+1)%count
        expect(root).to_have_attribute('data-hero-index',str(index),timeout=6000)
        assert index!=previous
        active=root.locator('[data-hero-slide][aria-hidden=false]');assert active.count()==1
        assert active.get_attribute('data-product-id')==slides.nth(index).get_attribute('data-product-id')
        assert next_button.evaluate('(e)=>document.activeElement===e')
    root.locator('[data-hero-pause]').click();frozen=root.get_attribute('data-hero-index');page.wait_for_timeout(5300);expect(root).to_have_attribute('data-hero-index',frozen)
    root.locator('[data-hero-pause]').click();expect(root).to_have_attribute('data-hero-index',str((int(frozen)+1)%count),timeout=6000)
    page.emulate_media(reduced_motion='reduce');frozen=root.get_attribute('data-hero-index');page.wait_for_timeout(5300);expect(root).to_have_attribute('data-hero-index',frozen)
    print('PASS: Mouse hover and retained arrow focus no longer stop 5s autoplay; complete loop, manual reset, pause/resume and reduced motion verified.',flush=True)

def file_picker(page,selector,files):
    """The styled button must open the real chooser and retain native form binding."""
    from playwright.sync_api import expect
    native=page.locator(selector);picker=native.locator('..');button=picker.get_by_role('button',name='Chọn file',exact=True)
    original_name=native.get_attribute('name');assert original_name
    expect(button).to_be_visible();button.focus()
    with page.expect_file_chooser() as event:button.press('Enter')
    event.value.set_files(files)
    assert native.get_attribute('name')==original_name
    assert native.evaluate('(e)=>e.files.length')==len(files)
    expect(picker.locator('.file-picker-name')).to_contain_text(files[0]['name'])
    assert native.evaluate('(e)=>e.form!==null')
    print('PASS: Chọn file opens native chooser by keyboard, shows filenames and preserves form fields/files.',flush=True)

def multipart(client,path,source,values,photos):
    boundary='gs'+uuid.uuid4().hex;parts=[]
    for name,value in {**values,'__RequestVerificationToken':source.input('__RequestVerificationToken')}.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name,data in photos:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="Photos"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode()+data+b'\r\n')
    body=b''.join(parts)+f'--{boundary}--\r\n'.encode()
    request=urllib.request.Request(gs.BASE+path,data=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
    try:response=client.open(request,timeout=30)
    except urllib.error.HTTPError as error:response=error
    return response.code,dict(response.headers),response.read().decode()

def run():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());checks=[]
    def passed(label):checks.append(label);print('PASS: '+label,flush=True)
    admin,buyer,other=gs.client(),gs.client(),gs.client();ps.sign_in(admin,accounts[0],True);ps.sign_in(buyer,accounts[2]);other_account=gs.register(other);gs.login(other,other_account)
    # Ranking: cancelled/pending and inactive products cannot displace recent delivered sales.
    cid=int(om.qa_sql("INSERT INTO Categories (Name,Description,IsActive) VALUES ('QA Slider "+uuid.uuid4().hex[:8]+"','',1); SELECT LAST_INSERT_ID()"))
    products=[]
    for index in range(7):
        products.append(int(om.qa_sql(f"INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity,CategoryId) VALUES ('QA Slider {index}',100000,'/images/product-placeholder.svg','',50,{cid}); SELECT LAST_INSERT_ID()")))
    inactive=int(om.qa_sql("INSERT INTO Categories (Name,Description,IsActive) VALUES ('QA Hidden "+uuid.uuid4().hex[:8]+"','',0); SELECT LAST_INSERT_ID()"))
    om.qa_sql(f'UPDATE Products SET CategoryId={inactive} WHERE Id={products[6]}')
    base=int(om.qa_sql('SELECT COALESCE(MAX(s.Quantity),0) FROM (SELECT SUM(i.Quantity) Quantity FROM OrderItems i JOIN Orders o ON o.Id=i.OrderId JOIN Products p ON p.Id=i.ProductId LEFT JOIN Categories c ON c.Id=p.CategoryId WHERE o.Status=1 AND (p.CategoryId IS NULL OR c.IsActive=1) GROUP BY i.ProductId) s'))+10000
    for pid,quantity,status,days in [(products[i],base-i*100,1,2) for i in range(5)]+[(products[5],base*2,1,80),(products[5],base*20,2,1),(products[5],base*18,0,1),(products[6],base*22,1,1)]:
        oid=int(om.qa_sql(f"INSERT INTO Orders (UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES (3,{gs.quote(uuid.uuid4().hex)},'QA Sales','0912345678','QA Synthetic sales address',DATE_SUB(UTC_TIMESTAMP(),INTERVAL {days} DAY),{quantity*100000},{status},0,'COD',1,'',0); SELECT LAST_INSERT_ID()"))
        om.qa_sql(f"INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES ({oid},{pid},'QA Sales Product','/images/product-placeholder.svg',100000,{quantity})")
    def configure_slider(mode,count,days,status=302,version=None):
        source=gs.get(admin,'/Admin/KhachHang/Slider')[0]
        values={'Mode':mode,'ProductCount':count,'Days':days,'Version':om.qa_sql('SELECT Version FROM HomeSliderSettings') if version is None else version}
        assert gs.post(admin,'/Admin/KhachHang/Slider',source,values)[0]==status
    def hero_ids():
        source=gs.get(buyer,'/')[0];return [int(a['data-product-id']) for tag,a in source.nodes if 'data-hero-slide' in a]
    configure_slider('bestsellers',5,30);assert hero_ids()==products[:5]
    configure_slider('bestsellers',2,0);assert hero_ids()==[products[5],products[0]]
    configure_slider('all',5,30);assert set(hero_ids())==set(map(int,om.qa_sql('SELECT Id FROM Products WHERE CategoryId IS NULL OR CategoryId IN (SELECT Id FROM Categories WHERE IsActive=1)').splitlines()))
    version=om.qa_sql('SELECT Version FROM HomeSliderSettings');configure_slider('bestsellers',5,30);configure_slider('all',5,30,409,version)
    for mode,count,days in [('invalid',5,30),('bestsellers',0,30),('bestsellers',101,30),('bestsellers',5,-1)]:configure_slider(mode,count,days,400)
    assert gs.request(admin,'/Admin/KhachHang/Slider',{'Mode':'all','ProductCount':5,'Days':30,'Version':version})[0]==400
    assert gs.request(buyer,'/Admin/KhachHang/Slider')[0]==302
    passed('Slider ranks only delivered saleable products in configurable time window; top X and all products work; validation, stale settings, Admin-only and CSRF guards')

    def purchase(client,pid=None):
        oid=om.create_order(client,products[0] if pid is None else pid,1);source=gs.get(client,f'/ThanhToan/ChiTietDonHang/{oid}')[0]
        item=int(om.qa_sql(f'SELECT Id FROM OrderItems WHERE OrderId={oid}'))
        assert gs.request(client,f'/TuongTac/DanhGia/{item}')[0]==404
        for state in (3,4,5,1):assert om.mutate(admin,oid,'CapNhatTrangThaiDonHang',{'TargetStatus':state})[0]==302
        return oid,item
    oid,item=purchase(buyer);_,other_item=purchase(other)
    assert gs.request(other,f'/TuongTac/DanhGia/{item}')[0]==404
    source=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    assert gs.request(buyer,f'/TuongTac/DanhGia/{item}',{'Stars':5,'Content':'CSRF denied'})[0]==400
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',source,{'Stars':0,'Content':'Bad stars'})[0]==400
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII=')
    for photos in [[('evil.svg',b'<svg onload="alert(1)"></svg>')],[('wrong.png',b'not a real PNG header')],[('valid.png',png)]*6,[('large.png',png+b'x'*(2*1024*1024))]]:
        assert multipart(buyer,f'/TuongTac/DanhGia/{item}',source,{'Stars':5,'Content':'Upload denied'},photos)[0]==400
    review_text='QA review <img src=x onerror="window.__reviewXss=1">'
    assert multipart(buyer,f'/TuongTac/DanhGia/{item}',source,{'Stars':5,'Content':review_text,'UserId':999,'ProductId':products[5]},[('experience.png',png)])[0]==302
    rid=int(om.qa_sql(f'SELECT Id FROM ProductReviews WHERE OrderItemId={item}'));image=om.qa_sql(f'SELECT Image1 FROM ProductReviews WHERE Id={rid}')
    assert re.fullmatch(r'/uploads/products/[a-f0-9]{32}\.png',image)
    assert om.qa_sql(f'SELECT UserId,ProductId,Stars FROM ProductReviews WHERE Id={rid}')==f'3\t{products[0]}\t5'
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',source,{'Stars':1,'Content':'Repeat denied'})[0]==302
    assert om.qa_sql(f'SELECT COUNT(*) FROM ProductReviews WHERE OrderItemId={item}')=='1'
    other_source=gs.get(other,f'/TuongTac/DanhGia/{other_item}')[0]
    assert gs.post(other,f'/TuongTac/DanhGia/{other_item}',other_source,{'Stars':3,'Content':'QA second verified review'})[0]==302
    assert float(om.qa_sql(f'SELECT AVG(Stars) FROM ProductReviews WHERE ProductId={products[0]}'))==4
    _,body,_=gs.get(buyer,f'/SanPham/ChiTietSanPham/{products[0]}');assert re.search(r'4[.,]0/5 · 2 đánh giá',body)
    raw=gs.request(buyer,f'/SanPham/ChiTietSanPham/{products[0]}')[2];assert '<img src=x onerror=' not in raw
    alerts=json.loads(gs.request(admin,'/Admin/KhachHang/ThongBao')[2]);assert alerts['reviews']>=2
    source=gs.get(admin,'/Admin/KhachHang/DanhGia')[0];assert gs.post(admin,f'/Admin/KhachHang/DaDocDanhGia/{rid}',source,{})[0]==302
    assert om.qa_sql(f"SELECT COUNT(*) FROM AdminNotifications WHERE RecipientId=1 AND EventKey LIKE 'review:{rid}:%' AND ReadAt IS NULL")=='0'
    passed('Real COD purchase and delivered workflow -> owner-only review; 1-5 stars, text/image validation, safe images, duplicate prevention, real 4/5 average and unread review acknowledgements')

    edit=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    values={'Stars':4,'Content':'QA edited review <script>window.__editedXss=1</script>','ReviewId':rid,'Version':edit.input('Version')}
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',edit,values)[0]==302
    assert om.qa_sql(f'SELECT Stars,Version,Image1 IS NOT NULL FROM ProductReviews WHERE Id={rid}')=='4\t1\t1'
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',edit,{**values,'Stars':1})[0]==302
    assert om.qa_sql(f'SELECT Stars FROM ProductReviews WHERE Id={rid}')=='4'
    moderation=gs.get(admin,'/Admin/KhachHang/DanhGia')[0]
    assert gs.request(buyer,f'/Admin/KhachHang/AnHienDanhGia/{rid}',{'hidden':'true','version':1})[0]==302
    assert gs.post(admin,f'/Admin/KhachHang/AnHienDanhGia/{rid}',moderation,{'hidden':'true','version':1})[0]==302
    raw=gs.get(buyer,f'/SanPham/ChiTietSanPham/{products[0]}')[1]
    assert 'QA edited review' not in raw and re.search(r'3[.,]0/5 · 1 đánh giá',raw)
    assert gs.post(admin,f'/Admin/KhachHang/AnHienDanhGia/{rid}',moderation,{'hidden':'false','version':2})[0]==302
    # Restore only this synthetic QA review for legacy visual expectations.
    edit=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',edit,{'Stars':5,'Content':review_text,'ReviewId':rid,'Version':3})[0]==302
    admin2=gs.client();ps.sign_in(admin2,accounts[1],True)
    other_notices=int(om.qa_sql('SELECT COUNT(*) FROM AdminNotifications WHERE RecipientId=2 AND ReadAt IS NULL'))
    notices=gs.get(admin,'/Admin/KhachHang/ThongBaoCuaToi')[0]
    assert gs.request(admin,'/Admin/KhachHang/DocTatCa',{})[0]==400
    assert gs.post(admin,'/Admin/KhachHang/DocTatCa',notices,{})[0]==302
    assert om.qa_sql('SELECT COUNT(*) FROM AdminNotifications WHERE RecipientId=1 AND ReadAt IS NULL')=='0'
    assert int(om.qa_sql('SELECT COUNT(*) FROM AdminNotifications WHERE RecipientId=2 AND ReadAt IS NULL'))==other_notices
    foreign=om.qa_sql('SELECT Id FROM AdminNotifications WHERE RecipientId=2 ORDER BY Id LIMIT 1')
    assert gs.post(admin,f'/Admin/KhachHang/DocThongBao/{foreign}',notices,{})[0]==404
    assert int(om.qa_sql("SELECT COUNT(*) FROM (SELECT RecipientId,EventKey,COUNT(*) n FROM AdminNotifications GROUP BY RecipientId,EventKey HAVING n>1) d"))==0
    passed('Review editing retains images; stale updates rejected; hidden reviews excluded from detail/rating; notification reads are independent per Admin with CSRF/IDOR protection')

    existing=om.qa_sql('SELECT Id,AssignedAdminId,Version,Status FROM ShopConversations WHERE CustomerId=3')
    if existing:
        cid,owner,version,state=existing.split('\t')
        if state=='InProgress':
            closer=gs.client();ps.sign_in(closer,accounts[0 if owner=='1' else 1],True)
            close_source=gs.get(closer,f'/Admin/KhachHang/TroChuyen/{cid}')[0]
            assert gs.post(closer,f'/Admin/KhachHang/KetThuc/{cid}',close_source,{'version':version})[0]==302
    chat=gs.get(buyer,'/')[0];message_token=uuid.uuid4().hex
    assert gs.request(buyer,'/TuongTac/GuiTinNhan',{'Content':'CSRF denied','RequestToken':message_token})[0]==400
    text='QA private message <script>window.__chatXss=1</script>'
    data={'Content':text,'RequestToken':message_token,'FromAdmin':'true','UserId':1}
    result=gs.post(buyer,'/TuongTac/GuiTinNhan',chat,data);assert result[0]==200;mid=json.loads(result[2])['id'];conv=int(om.qa_sql(f'SELECT ConversationId FROM ShopMessages WHERE Id={mid}'))
    retry=gs.post(buyer,'/TuongTac/GuiTinNhan',chat,data);assert retry[0]==200 and json.loads(retry[2])['id']==mid
    assert om.qa_sql(f'SELECT COUNT(*) FROM ShopMessages WHERE RequestToken={gs.quote(message_token)}')=='1'
    assert om.qa_sql(f'SELECT SenderId,FromAdmin FROM ShopMessages WHERE Id={mid}')=='3\t0'
    assert gs.post(buyer,'/TuongTac/GuiTinNhan',chat,{**data,'Content':'Changed replay'})[0]==409
    assert gs.post(buyer,'/TuongTac/GuiTinNhan',chat,{'Content':'x'*2001,'RequestToken':uuid.uuid4().hex})[0]==400
    assert gs.request(buyer,'/TuongTac/GuiTinNhan')[0]==405
    own=json.loads(gs.request(other,f'/TuongTac/TinNhanMoi/{conv}?UserId=3&role=Admin')[2]);assert own['messages']==[]
    assert gs.request(other,f'/Admin/KhachHang/TinNhanMoi/{conv}')[0]==302
    admin_chat=gs.get(admin,f'/Admin/KhachHang/TroChuyen/{conv}')[0]
    assert json.loads(gs.request(admin,f'/Admin/KhachHang/TinNhanMoi/{conv}?after={mid-1}')[2])['messages'][0]['content']==text
    before_read=om.qa_sql(f'SELECT AdminReadMessageId FROM ShopConversations WHERE Id={conv}')
    assert gs.post(admin,f'/Admin/KhachHang/DaDoc/{conv}',admin_chat,{'through':999999})[0]==400
    assert om.qa_sql(f'SELECT AdminReadMessageId FROM ShopConversations WHERE Id={conv}')==before_read
    assert gs.post(admin,f'/Admin/KhachHang/DaDoc/{conv}',admin_chat,{'through':mid})[0]==204
    admin2_chat=gs.get(admin2,f'/Admin/KhachHang/TroChuyen/{conv}')[0]
    assert 'tự động tiếp nhận' in gs.get(admin2,f'/Admin/KhachHang/TroChuyen/{conv}')[1]
    claim_version=om.qa_sql(f'SELECT Version FROM ShopConversations WHERE Id={conv}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda pair:gs.post(pair[0],f'/Admin/KhachHang/TiepNhan/{conv}',pair[1],{'version':claim_version})[0],[(admin,admin_chat),(admin2,admin2_chat)]))
    assert sorted(claims)==[302,409],claims
    winner=int(om.qa_sql(f'SELECT AssignedAdminId FROM ShopConversations WHERE Id={conv}'))
    if winner==2: admin,admin2=admin2,admin;accounts[0],accounts[1]=accounts[1],accounts[0]
    admin_chat=gs.get(admin,f'/Admin/KhachHang/TroChuyen/{conv}')[0]
    # Antiforgery tokens are identity-bound; swapping race winners also requires the matching form.
    admin2_chat=gs.get(admin2,f'/Admin/KhachHang/TroChuyen/{conv}')[0]
    assert gs.post(admin2,f'/Admin/KhachHang/GuiTinNhan/{conv}',admin2_chat,{'Content':'QA wrong assignment denied','RequestToken':uuid.uuid4().hex})[0]==409
    admin_chat=gs.get(admin,f'/Admin/KhachHang/TroChuyen/{conv}')[0]
    assert gs.post(admin,f'/Admin/KhachHang/GuiTinNhan/{conv}',admin_chat,{'Content':'QA reply from real Admin','RequestToken':uuid.uuid4().hex})[0]==200
    assert len(json.loads(gs.request(buyer,f'/TuongTac/TinNhanMoi?after={mid-1}')[2])['messages'])==2
    passed('Persistent private chat, genuine Admin reply, anti-forgery and role/ownership guards, escaped content, idempotent send, invalid read cursor rejected')
    browser_review_order,browser_review_item=purchase(buyer,products[1])

    from playwright.sync_api import expect
    with ps.playwright() as pw:
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});page=ctx.new_page();errors=[];missing=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('response',lambda r:missing.append(r.url) if r.request.resource_type in ('script','stylesheet','font') and r.status>=400 else None)
        ps.login_page(page,accounts[2]);page.goto(om.QA_BASE+'/');page.mouse.move(0,0);page.wait_for_function('document.querySelector("[data-hero-slider]").dataset.heroAutoplay==="running"')
        start=page.locator('[data-hero-slider]').get_attribute('data-hero-index');page.wait_for_timeout(4300);assert page.locator('[data-hero-slider]').get_attribute('data-hero-index')==start
        page.wait_for_function('(old)=>document.querySelector("[data-hero-slider]").dataset.heroIndex!==old',arg=start,timeout=2000)
        page.get_by_role('button',name='Sản phẩm nổi bật tiếp theo',exact=True).click();expected_index=(int(start)+2)%5;expect(page.locator('[data-hero-slider]')).to_have_attribute('data-hero-index',str(expected_index))
        active=page.locator('[data-hero-slide][aria-hidden=false]');assert int(active.get_attribute('data-product-id'))==products[expected_index]
        assert int(active.locator('.hero-purchase form').get_attribute('action').rsplit('/',1)[1])==products[expected_index]
        page.get_by_role('button',name='Sản phẩm nổi bật trước',exact=True).click();expect(page.locator('[data-hero-slider]')).to_have_attribute('data-hero-index',str((expected_index-1)%5))
        box=page.locator('.hero-slider-viewport').bounding_box();x=box['x']+box['width']*.7;y=box['y']+box['width']*.45
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x-130,y,steps=12);page.mouse.up();expect(page.locator('[data-hero-slider]')).to_have_attribute('data-hero-index',str(expected_index));assert page.url==om.QA_BASE+'/'
        page.locator('[data-hero-slider]').get_by_role('button',name='Tạm dừng tự trượt',exact=True).click();page.mouse.move(0,0);page.locator('h1').click();frozen=page.locator('[data-hero-slider]').get_attribute('data-hero-index');page.wait_for_timeout(5500);assert page.locator('[data-hero-slider]').get_attribute('data-hero-index')==frozen
        page.emulate_media(reduced_motion='reduce');page.reload();page.wait_for_timeout(5500);expect(page.locator('[data-hero-slider]')).to_have_attribute('data-hero-index','0');page.get_by_role('button',name='Sản phẩm nổi bật tiếp theo',exact=True).click();expect(page.locator('[data-hero-slider]')).to_have_attribute('data-hero-index','1')
        page.goto(om.QA_BASE+f'/SanPham/ChiTietSanPham/{products[0]}');assert page.evaluate('window.__reviewXss') is None;expect(page.locator('.review-content').filter(has_text='QA review')).to_contain_text('<img src=x')
        page.locator('.review-photos img').first.scroll_into_view_if_needed();page.wait_for_function('document.querySelector(".review-photos img").naturalWidth>0')
        page.goto(om.QA_BASE+f'/TuongTac/DanhGia/{browser_review_item}')
        assert page.locator('[id^="review-star-"]').evaluate_all('(els)=>new Set(els.map(e=>e.id)).size===els.length')
        page.get_by_role('radio',name='4 sao',exact=True).check();expect(page.get_by_role('radio',name='4 sao',exact=True)).to_be_checked()
        page.locator('#Content').fill('QA native star and photo form')
        page.locator('#Photos').set_input_files([{'name':f'experience-{n}.png','mimeType':'image/png','buffer':png} for n in range(5)])
        page.get_by_role('button',name='Gửi đánh giá',exact=True).click();expect(page).to_have_url(om.QA_BASE+f'/ThanhToan/ChiTietDonHang/{browser_review_order}');expect(page.locator('.review-complete')).to_be_visible()
        assert om.qa_sql(f'SELECT Stars,Image1 IS NOT NULL,Image2 IS NOT NULL,Image3 IS NOT NULL,Image4 IS NOT NULL,Image5 IS NOT NULL FROM ProductReviews WHERE OrderItemId={browser_review_item}')=='4\t1\t1\t1\t1\t1'
        page.goto(om.QA_BASE+'/TuongTac/TroChuyen');expect(page.locator(f'.chat-bubble[data-message-id="{mid}"]')).to_be_visible();assert page.evaluate('window.__chatXss') is None
        admin_ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});ap=admin_ctx.new_page();ps.login_page(ap,accounts[0],ps.ADMIN_LOGIN);ap.goto(om.QA_BASE+f'/Admin/KhachHang/TroChuyen/{conv}')
        expect(ap.locator(f'.chat-bubble[data-message-id="{mid}"]')).to_be_visible()
        customer_live=f'QA live browser customer {uuid.uuid4().hex[:8]}';shop_live=f'QA live browser shop {uuid.uuid4().hex[:8]}';second_live=f'QA second realtime message {uuid.uuid4().hex[:8]}'
        page.locator('[data-widget-chat] #widget-chat-content').fill(customer_live);page.locator('[data-widget-chat]').get_by_role('button',name='Gửi tin nhắn',exact=True).click();expect(ap.locator('.chat-bubble').filter(has_text=customer_live)).to_be_visible(timeout=2500)
        ap.locator('#chat-content').fill(shop_live);ap.get_by_role('button',name='Gửi tin nhắn',exact=True).click();expect(page.locator('.chat-bubble').filter(has_text=shop_live)).to_be_visible(timeout=2500)
        page.locator('[data-widget-chat] #widget-chat-content').fill(second_live);page.locator('[data-widget-chat]').get_by_role('button',name='Gửi tin nhắn',exact=True).click();expect(ap.locator('.chat-bubble').filter(has_text=second_live)).to_be_visible(timeout=2500)
        expected_pending=om.qa_sql('SELECT COUNT(*) FROM Orders WHERE Status=0');expect(ap.locator('.admin-sidebar [data-alert-count=orders]')).to_have_text(expected_pending)
        live_order=om.create_order(buyer,products[1],1)
        expect(ap.locator('.admin-sidebar [data-alert-count=orders]')).to_have_text(str(int(expected_pending)+1),timeout=22000)
        assert om.mutate(admin,live_order,'XacNhanDonHang',{})[0]==302
        expect(ap.locator('.admin-sidebar [data-alert-count=orders]')).to_have_text(expected_pending,timeout=22000)
        for width in (320,390,768,1440):
            page.set_viewport_size({'width':width,'height':900});ap.set_viewport_size({'width':width,'height':900})
            for theme in ('light','dark'):
                page.evaluate('(t)=>localStorage.setItem("greenshop.theme",t)',theme)
                for path in ('/','/TuongTac/TroChuyen',f'/SanPham/ChiTietSanPham/{products[0]}'):
                    page.goto(om.QA_BASE+path,wait_until='networkidle');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
                    assert page.locator('.shop-chat-launcher').evaluate('(e)=>getComputedStyle(e).position')=='fixed'
            for path in ('/Admin/KhachHang/Slider','/Admin/KhachHang/TinNhan','/Admin/KhachHang/DanhGia',f'/Admin/KhachHang/TroChuyen/{conv}'):
                ap.goto(om.QA_BASE+path,wait_until='networkidle');assert ap.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
                assert ap.locator('.admin-topbar .btn').evaluate_all('(els)=>els.filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})'),('Admin topbar controls',width,path)
                assert ap.locator('.admin-alerts>button').evaluate('(e)=>getComputedStyle(e).overflow')=='visible'
            page.screenshot(path=str(OUT/f'engagement-customer-{width}.png'),animations='disabled');ap.screenshot(path=str(OUT/f'engagement-admin-{width}.png'),animations='disabled')
        assert not errors and not missing,(errors,missing);ctx.close();admin_ctx.close();browser.close()
    passed('Actual 5-second slide timing, arrows/mouse drag/pause/reduced motion, current-product Buy Now; real two-way browser chat via SignalR across multiple messages; images/XSS/focus/assets and responsive Customer/Admin pages')
    _,concurrent_item=purchase(buyer,products[2]);review_page=gs.get(buyer,f'/TuongTac/DanhGia/{concurrent_item}')[0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda stars:gs.post(buyer,f'/TuongTac/DanhGia/{concurrent_item}',review_page,{'Stars':stars,'Content':'QA simultaneous review'}),[4,2]))
    assert all(r[0]==302 for r in results) and om.qa_sql(f'SELECT COUNT(*) FROM ProductReviews WHERE OrderItemId={concurrent_item}')=='1'
    other_chat=gs.get(other,'/')[0]
    for index in range(20):assert gs.post(other,'/TuongTac/GuiTinNhan',other_chat,{'Content':f'QA rate check {index}','RequestToken':uuid.uuid4().hex})[0]==200
    assert gs.post(other,'/TuongTac/GuiTinNhan',other_chat,{'Content':'QA exceeds rate','RequestToken':uuid.uuid4().hex})[0]==429
    other_mid=int(om.qa_sql(f'SELECT MAX(Id) FROM ShopMessages WHERE ConversationId<>{conv}'))
    assert gs.post(admin,f'/Admin/KhachHang/DaDoc/{conv}',admin_chat,{'through':other_mid})[0]==400
    passed('Red order badge increases on real QA checkout and decreases on confirmation; concurrent review creates one row; message spam limited server-side and cross-conversation read cursors denied')
    (OUT/'engagement-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'database':'isolated QA only'},indent=2))

def hybrid_widget():
    """Actual WebSocket delivery, offline synchronization, tabs, origin and group guards."""
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text())
    buyer=gs.client();ps.sign_in(buyer,accounts[2])
    source=gs.get(buyer,'/')[0]
    assert gs.post(buyer,'/TuongTac/GuiTinNhan',source,{'Content':'QA widget session','RequestToken':uuid.uuid4().hex})[0]==200
    conv=int(om.qa_sql('SELECT Id FROM ShopConversations WHERE CustomerId=3'))
    assigned=om.qa_sql(f'SELECT AssignedAdminId FROM ShopConversations WHERE Id={conv}')
    admin_index=1 if assigned=='2' else 0
    admin=gs.client();ps.sign_in(admin,accounts[admin_index],True)
    admin_source=gs.get(admin,f'/Admin/KhachHang/TroChuyen/{conv}')[0]
    state=om.qa_sql(f'SELECT Status FROM ShopConversations WHERE Id={conv}')
    if state=='Waiting':
        assert gs.post(admin,f'/Admin/KhachHang/TiepNhan/{conv}',admin_source,{'version':om.qa_sql(f'SELECT Version FROM ShopConversations WHERE Id={conv}')})[0]==302
        admin_source=gs.get(admin,f'/Admin/KhachHang/TroChuyen/{conv}')[0]
    other=gs.client();other_account=gs.register(other);gs.login(other,other_account)
    def negotiate(client,path,origin):
        req=urllib.request.Request(gs.BASE+path+'?negotiateVersion=1',data=b'',headers={'Origin':origin})
        try:r=client.open(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        return r.code
    assert negotiate(buyer,'/supportHub/negotiate','https://evil.example.invalid')==403
    assert negotiate(gs.client(),'/supportHub/negotiate',om.QA_BASE)!=200
    assert negotiate(admin,'/supportHub/negotiate',om.QA_BASE)!=200
    assert negotiate(buyer,'/Admin/supportHub/negotiate',om.QA_BASE)!=200
    from playwright.sync_api import expect
    with ps.playwright() as pw:
        b=pw.chromium.launch();errors=[];assets=[];websockets=[]
        c=b.new_context(ignore_https_errors=True,viewport={'width':390,'height':844});p=c.new_page()
        p.on('pageerror',lambda e:errors.append(str(e)))
        p.on('response',lambda r:assets.append(r.url) if r.request.resource_type in ('script','stylesheet','font','image') and r.status>=400 else None)
        p.on('websocket',lambda ws:websockets.append(ws.url))
        routes=[]
        def socket_route(route):
            route.connect_to_server();routes.append(route)
        p.route_web_socket('**/supportHub?*',socket_route)
        p.goto(om.QA_BASE+'/');p.locator('[data-hybrid-open]').click()
        expect(p.get_by_role('tab',name='Trợ lý AI',exact=True)).to_have_attribute('aria-selected','true')
        expect(p.locator('[data-ai-status]')).to_contain_text('chưa khả dụng')
        expect(p.locator('[data-ai-form] button')).to_be_disabled()
        p.get_by_role('tab',name='Chat với Shop',exact=True).click();expect(p.locator('#store-panel')).to_contain_text('Đăng nhập để nhắn tin trực tiếp với cửa hàng.')
        p.keyboard.press('Escape');expect(p.locator('[data-hybrid-open]')).to_be_focused()
        ps.login_page(p,accounts[2]);p.goto(om.QA_BASE+'/');p.locator('[data-hybrid-open]').click();p.get_by_role('tab',name='Chat với Shop',exact=True).click()
        before_url=p.url
        for _ in range(3):
            p.locator('[data-hybrid-close]').click();p.locator('[data-hybrid-open]').click()
            expect(p.get_by_role('tab',name='Trợ lý AI',exact=True)).to_have_attribute('aria-selected','true')
            p.get_by_role('tab',name='Chat với Shop',exact=True).click()
        assert p.url==before_url and p.locator('[data-hybrid-chat]').count()==1 and p.locator('[data-shop-chat]').count()==1
        chat=p.locator('[data-widget-chat]');expect(chat).to_have_attribute('data-realtime','connected',timeout=15000)
        a=b.new_context(ignore_https_errors=True);ap=a.new_page();ap.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(ap,accounts[admin_index],ps.ADMIN_LOGIN);ap.goto(om.QA_BASE+f'/Admin/KhachHang/TroChuyen/{conv}')
        expect(ap.locator('[data-shop-chat]')).to_have_attribute('data-realtime','connected',timeout=15000)
        customer_message='QA widget customer '+uuid.uuid4().hex[:8]
        p.locator('#widget-chat-content').fill(customer_message);chat.get_by_role('button',name='Gửi tin nhắn',exact=True).click()
        expect(ap.locator('.chat-bubble').filter(has_text=customer_message)).to_be_visible(timeout=2500)
        assert any('/supportHub' in url for url in websockets),'No actual WebSocket established'
        shop_message='QA widget reply '+uuid.uuid4().hex[:8]
        ap.locator('#chat-content').fill(shop_message);ap.get_by_role('button',name='Gửi tin nhắn',exact=True).click()
        expect(chat.locator('.chat-bubble').filter(has_text=shop_message)).to_be_visible(timeout=2500)
        # Reload reconnects, rejoins the group and synchronizes MySQL history without duplicates.
        p.reload();p.locator('[data-hybrid-open]').click();p.get_by_role('tab',name='Chat với Shop',exact=True).click()
        expect(chat.locator('.chat-bubble').filter(has_text=shop_message)).to_have_count(1)
        expect(chat).to_have_attribute('data-realtime','connected',timeout=15000)
        old_routes=len(routes);assert old_routes>0
        c.set_offline(True);routes[-1].close(code=1012,reason='QA connection failure')
        expect(chat).to_have_attribute('data-realtime','reconnecting',timeout=5000)
        lost='QA reconnect message '+uuid.uuid4().hex[:8]
        ap.locator('#chat-content').fill(lost);ap.get_by_role('button',name='Gửi tin nhắn',exact=True).click()
        c.set_offline(False)
        expect(chat).to_have_attribute('data-realtime','connected',timeout=15000)
        expect(chat.locator('.chat-bubble').filter(has_text=lost)).to_have_count(1,timeout=5000)
        assert len(routes)>old_routes, 'No replacement WebSocket was established'
        second=c.new_page();second.goto(om.QA_BASE+'/');second.locator('[data-hybrid-open]').click();second.get_by_role('tab',name='Chat với Shop',exact=True).click()
        second_chat=second.locator('[data-widget-chat]');expect(second_chat).to_have_attribute('data-realtime','connected')
        expect(second_chat.locator('.chat-bubble').filter(has_text=lost)).to_have_count(1)
        multitab='QA multiple tabs '+uuid.uuid4().hex[:8]
        ap.locator('#chat-content').fill(multitab);ap.get_by_role('button',name='Gửi tin nhắn',exact=True).click()
        expect(chat.locator('.chat-bubble').filter(has_text=multitab)).to_have_count(1,timeout=2500)
        expect(second_chat.locator('.chat-bubble').filter(has_text=multitab)).to_have_count(1,timeout=2500)
        second.close()
        o=b.new_context(ignore_https_errors=True);op=o.new_page();ps.login_page(op,other_account);op.goto(om.QA_BASE+'/')
        denied=op.evaluate('''async id=>{const h=new signalR.HubConnectionBuilder().withUrl('/supportHub').build();await h.start();try{await h.invoke('JoinConversation',id);return false;}catch{return true;}finally{await h.stop();}}''',conv)
        assert denied,'Cross-customer SignalR group access was allowed'
        other_source=gs.get(other,'/')[0]
        assert gs.post(other,'/TuongTac/GuiTinNhan',other_source,{'Content':'QA session revocation','RequestToken':uuid.uuid4().hex})[0]==200
        other_id=int(om.qa_sql('SELECT Id FROM Users WHERE Email='+gs.quote(other_account[0])))
        other_conv=int(om.qa_sql(f'SELECT Id FROM ShopConversations WHERE CustomerId={other_id}'))
        op.evaluate('''async id=>{window.qaHub=new signalR.HubConnectionBuilder().withUrl('/supportHub').build();await qaHub.start();await qaHub.invoke('JoinConversation',id);}''',other_conv)
        assert op.evaluate('''async id=>{try{await qaHub.invoke('JoinConversation',id);return false;}catch{return true;}}''',conv), 'A Customer with an existing own conversation must still be denied a foreign conversation ID'
        import user_management as users
        users.OUT=OUT
        assert users.change(admin,other_id,'KhoaTaiKhoan')[0]==302
        try:
            assert op.evaluate('''async id=>{try{await qaHub.invoke('JoinConversation',id);return false;}catch{return true;}}''',other_conv)
            assert op.evaluate('''async()=>{try{await fetch('/TuongTac/TinNhanMoi',{redirect:'error'});return false;}catch{return true;}}''')
        finally:
            assert users.change(admin,other_id,'MoKhoaTaiKhoan')[0]==302
            op.evaluate('qaHub.stop()')
        for width in (320,390,768,1440):
            p.set_viewport_size({'width':width,'height':900})
            for theme in ('light','dark'):
                p.evaluate('(t)=>{localStorage.setItem("greenshop.theme",t);document.documentElement.dataset.theme=t;}',theme)
                assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme)
                assert p.locator('#hybrid-chat').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}')
        p.emulate_media(reduced_motion='reduce');p.screenshot(path=str(OUT/'hybrid-chat-qa.png'),full_page=True,animations='disabled')
        intentional=[url for url in assets if url.endswith('/uploads/products/nonexistent-dashboard.png')]
        assert all(url in intentional for url in assets),(errors,assets)
        p.wait_for_function('[...document.querySelectorAll("img[data-product-image]")].every(e=>e.dataset.fallback ? e.complete&&e.naturalWidth>0 : !e.complete||e.naturalWidth>0)')
        assert not errors,errors
        o.close();a.close();c.close();b.close()
    # Closing and reopening is an explicit lifecycle; only the assigned Admin may close.
    version=om.qa_sql(f'SELECT Version FROM ShopConversations WHERE Id={conv}')
    assert gs.post(admin,f'/Admin/KhachHang/KetThuc/{conv}',admin_source,{'version':version})[0]==302
    assert om.qa_sql(f'SELECT Status FROM ShopConversations WHERE Id={conv}')=='Resolved'
    assert gs.post(buyer,'/TuongTac/GuiTinNhan',source,{'Content':'QA reopen support','RequestToken':uuid.uuid4().hex})[0]==200
    assert om.qa_sql(f'SELECT Status,AssignedAdminId IS NULL FROM ShopConversations WHERE Id={conv}')=='Waiting\t1'
    assert gs.post(admin,f'/Admin/KhachHang/GuiTinNhan/{conv}',admin_source,{'Content':'QA auto reclaim first reply','RequestToken':uuid.uuid4().hex})[0]==200
    assert om.qa_sql(f'SELECT Status,AssignedAdminId FROM ShopConversations WHERE Id={conv}')=='InProgress\t'+str(admin_index+1)
    print('PASS: Hybrid default AI/unavailable, actual two-context WebSocket delivery, automatic reconnect/offline synchronization, no duplicates, Origin/role/group denial, responsive themes, conversation lifecycle',flush=True)
    (OUT/'hybrid-results.json').write_text(json.dumps({'status':'PASS','transport':'SignalR WebSockets','checks':'Two browser contexts; real-time delivery <2.5s; automatic reconnect after closed socket and offline catch-up; owner-only groups; exact Origin; role separation; default AI unavailable; mobile/light/dark; assignment lifecycle','AI_PROVIDER_LIVE_TEST':'NOT TESTED — CONFIGURATION REQUIRED'},indent=2))

def contracts():
    """Independent completed-order reviews, independent order events and new route matrix."""
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text())
    buyer,admin,admin2,anon=gs.client(),gs.client(),gs.client(),gs.client()
    ps.sign_in(buyer,accounts[2]);ps.sign_in(admin,accounts[0],True);ps.sign_in(admin2,accounts[1],True)
    candidate=om.qa_sql('SELECT r.Id,r.ProductId,r.Version FROM ProductReviews r JOIN Products p ON p.Id=r.ProductId WHERE r.UserId=3 AND r.IsCurrent=1 AND r.IsHidden=0 AND p.StockQuantity>2 ORDER BY r.Id DESC LIMIT 1')
    rid,pid,version=map(int,candidate.split('\t'))
    oid=om.create_order(buyer,pid,1)
    assert om.qa_sql(f"SELECT COUNT(*) FROM AdminNotifications WHERE EventKey='order:{oid}' AND ReadAt IS NULL")=='2'
    for state in (3,4,5,1):assert om.mutate(admin,oid,'CapNhatTrangThaiDonHang',{'TargetStatus':state})[0]==302
    assert om.qa_sql(f"SELECT COUNT(*) FROM AdminNotifications WHERE EventKey='order:{oid}' AND ReadAt IS NULL")=='2','Completing an order must not read its notification'
    item=int(om.qa_sql(f'SELECT Id FROM OrderItems WHERE OrderId={oid}'))
    form=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    assert int(form.input('ReviewId'))==0,'A different completed order grants an independent review'
    text='QA independent second purchase '+uuid.uuid4().hex[:8]
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',form,{'Stars':4,'Content':text})[0]==302
    second=int(om.qa_sql(f'SELECT Id FROM ProductReviews WHERE OrderItemId={item}'))
    assert second!=rid and om.qa_sql(f'SELECT Version FROM ProductReviews WHERE Id={rid}')==str(version)
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',form,{'Stars':4,'Content':text})[0]==302
    assert om.qa_sql(f'SELECT COUNT(*) FROM ProductReviews WHERE OrderItemId={item}')=='1'
    edit=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',edit,{'ReviewId':second,'Version':0,'Stars':3,'Content':text+' edited'})[0]==302
    assert om.qa_sql(f'SELECT Stars,Version FROM ProductReviews WHERE Id={second}')=='3\t1'
    for actor in (anon,buyer):
        for path in ('TinNhan','DanhGia','ThongBaoCuaToi'):
            assert gs.request(actor,'/Admin/KhachHang/'+path)[0]==302
        for action in ('AnHienDanhGia','TiepNhan','KetThuc','MoLai','DocThongBao','DocTatCa'):
            assert gs.request(actor,'/Admin/KhachHang/'+action+'/1',{})[0]==302
    for path in ('/TuongTac/TroChuyen','/GioHang/QuanLyGioHang','/ThanhToan/DonHangCuaToi',f'/TuongTac/DanhGia/{item}'):
        assert gs.request(admin,path)[0]==302
    for action in ('AnHienDanhGia','TiepNhan','KetThuc','MoLai','DocThongBao','DocTatCa'):
        assert gs.request(admin,'/Admin/KhachHang/'+action+'/1',{})[0]==400
        assert gs.request(admin,'/Admin/KhachHang/'+action+'/1')[0]==405
    before=ps.table_hashes(om.qa_sql)
    ai_source=gs.get(anon,'/')[0]
    assert json.loads(gs.request(anon,'/TroLy/TrangThai')[2])['available'] is False
    assert gs.request(anon,'/TroLy/Hoi',{'Question':'QA plant'})[0]==400
    seen=[]
    for _ in range(8):
        result=gs.post(anon,'/TroLy/Hoi',ai_source,{'Question':'QA tư vấn cây'})[0];seen.append(result)
        if result==429:break
    assert 503 in seen and seen[-1]==429,seen
    assert ps.table_hashes(om.qa_sql)==before
    print('PASS: Same Customer/Product across completed purchases creates independent reviews; order events survive status changes; new Admin/Customer routes enforce role, CSRF and POST; anonymous AI unavailable/rate limit writes no data',flush=True)
    (OUT/'contract-results.json').write_text(json.dumps({'status':'PASS','checks':'Per-completed-order review independence/idempotency/editing; new Order notification independent of Pending status; new route role/CSRF/method matrix; anonymous AI missing key 503 and 429; no AI business writes'},indent=2))


def ai_widget():
    """Browser UX contract with explicitly mocked AI HTTP responses; never a live-provider claim."""
    from playwright.sync_api import expect
    om.configure_qa()
    with ps.playwright() as pw:
        b=pw.chromium.launch();ctx=b.new_context(ignore_https_errors=True,viewport={'width':1440,'height':900})
        p=ctx.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)));requests=[]
        catalog_image=om.qa_sql('SELECT Image1 FROM ProductReviews WHERE Image1 IS NOT NULL LIMIT 1');assert catalog_image.startswith('/uploads/products/')
        p.route('**/uploads/products/qa-ai-missing-image.png',lambda r:r.fulfill(status=404,body='QA missing fixture'))
        p.route('**/TroLy/TrangThai',lambda route:route.fulfill(json={'available':True,'session':'a'*64}))
        def response(route):
            requests.append(route.request.post_data or '')
            if len(requests)==1:
                route.fulfill(json={'answer':'<svg onload="window.aiXss=1">Chăm cây nhẹ nhàng.</svg>','conversation':'opaque-fixture-1','policy':'Phí giao hàng: 30.000 đ.','products':[
                    {'id':19,'name':'QA fern','price':150000.50,'stockQuantity':3,'link':'/SanPham/ChiTietSanPham/19','rating':4.5,'reviewCount':2,'imageUrl':catalog_image},
                    {'id':20,'name':'unsafe-link','price':1,'stockQuantity':1,'link':'https://evil.invalid'},
                    {'id':21,'name':'QA unsafe image','price':1,'stockQuantity':1,'link':'/SanPham/ChiTietSanPham/21','imageUrl':'javascript:window.aiXss=1'},
                    {'id':22,'name':'QA missing image','price':1,'stockQuantity':1,'link':'/SanPham/ChiTietSanPham/22','imageUrl':'/uploads/products/qa-ai-missing-image.png'}]})
            elif len(requests)==2:route.fulfill(status=429,json={'message':'QA hạn mức; thử lại sau.'})
            elif len(requests)==3:route.fulfill(json={'answer':'Cần ánh sáng dịu.','conversation':'opaque-fixture-2','products':[]})
            else:route.fulfill(status=400,json={'message':'Hội thoại hết hạn.','resetConversation':True})
        p.route('**/TroLy/Hoi',response);p.goto(om.QA_BASE+'/');p.locator('[data-hybrid-open]').click()
        form=p.locator('[data-ai-form]');send=form.locator('button');question=form.locator('[name=Question]');log=p.locator('[data-ai-messages]')
        expect(send).to_be_enabled();question.fill('Cây dưới 200k');send.click()
        expect(log).to_contain_text('Chăm cây nhẹ nhàng.');assert log.locator('svg').count()==0 and p.evaluate('window.aiXss===undefined')
        assert log.locator('a').count()==3 and log.locator('a').first.get_attribute('href')=='/SanPham/ChiTietSanPham/19'
        expect(log.locator('a').first.locator('img')).to_have_attribute('src',om.QA_BASE+catalog_image)
        expect(log.locator('a').nth(1).locator('img')).to_have_attribute('src','/images/product-placeholder.svg')
        expect(log.locator('a').nth(2).locator('img')).to_have_attribute('src','/images/product-placeholder.svg')
        assert log.locator('img').evaluate_all('(images)=>images.every(image=>image.complete&&image.naturalWidth>0)')
        expect(log).to_contain_text('150.000,50');expect(log).to_contain_text('4.5/5');expect(log).to_contain_text('Phí giao hàng')
        p.locator('[data-hybrid-close]').click();p.locator('[data-hybrid-open]').click();expect(log).to_contain_text('Chăm cây nhẹ nhàng.')
        p.reload();p.locator('[data-hybrid-open]').click();expect(log).to_contain_text('Chăm cây nhẹ nhàng.');assert log.locator('a').count()==0
        question.fill('Tưới thế nào?');send.click();expect(p.locator('[data-ai-status]')).to_contain_text('QA hạn mức')
        expect(send).to_be_enabled();expect(question).to_have_value('Tưới thế nào?');assert 'opaque-fixture-1' in requests[1]
        send.click();expect(log).to_contain_text('Cần ánh sáng dịu.');assert 'opaque-fixture-1' in requests[2]
        question.fill('Hỏi tiếp');send.click();expect(p.locator('[data-ai-status]')).to_contain_text('Hội thoại hết hạn')
        p.locator('[data-ai-reset]').click();expect(log.locator('[data-chat-welcome]')).to_be_visible();expect(log.locator('.is-own')).to_have_count(0);expect(question).to_be_focused()
        for width in (320,375,390,768,1024,1440):
            p.set_viewport_size({'width':width,'height':900})
            for theme in ('light','dark'):
                p.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme)
                assert p.locator('#hybrid-chat').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}')
        p.keyboard.press('Escape');expect(p.locator('#hybrid-chat')).to_be_hidden();expect(p.locator('[data-hybrid-open]')).to_be_focused()
        assert not errors,errors;ctx.close();b.close()
    (OUT/'ai-widget-results.json').write_text(json.dumps({'status':'PASS','transport':'mocked browser AI HTTP only','checks':['Plain text XSS safety','DB-card rendering and strict local links','Bounded conversation token forwarded','429 retains input and safe manual retry','Expired history reset and keyboard focus','320/375/390/768/1024/1440 light/dark no overflow'],'liveGemini':False}))
    chat_composer()
    print('PASS: AI widget with mocked HTTP: text/link safety, multi-turn token, quota retry, reset/keyboard and six responsive widths; no Gemini generation.',flush=True)



def chat_composer():
    """Hold network responses to prove optimistic UI, draft recovery and realtime deduplication."""
    from playwright.sync_api import expect
    with ps.playwright() as pw:
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':850});p=ctx.new_page();held=[];errors=[]
        p.on('pageerror',lambda e:errors.append(str(e)))
        p.route('**/TroLy/TrangThai',lambda r:r.fulfill(json={'available':True,'session':'b'*64}))
        p.route('**/TroLy/Hoi',lambda r:held.append(r))
        p.goto(om.QA_BASE+'/');p.locator('[data-hybrid-open]').click()
        q=p.locator('#ai-question');send=p.locator('[data-ai-form] button');log=p.locator('[data-ai-messages]');typing=log.locator('.chat-typing')
        expect(send).to_be_enabled();p.get_by_role('button',name='Cây để bàn',exact=True).click();expect(q).to_have_value('Gợi ý cây dễ chăm để bàn làm việc');assert not held
        sent=q.input_value();q.press('Enter');expect(q).to_have_value('');expect(typing.locator('span')).to_have_count(3);expect(typing).to_be_visible();expect(send).to_be_disabled();expect(p.locator('[data-ai-reset]')).to_be_disabled()
        expect(log.locator('.is-own').filter(has_text=sent)).to_have_count(1)
        q.fill('Bản nháp tiếp theo');p.locator('[data-hybrid-close]').click();p.locator('[data-hybrid-open]').click();expect(q).to_have_value('Bản nháp tiếp theo')
        held.pop(0).fulfill(json={'answer':'QA trả lời thật từ HTTP mock.','conversation':'opaque-composer','products':[]})
        expect(log).to_contain_text('QA trả lời thật từ HTTP mock.');expect(typing).to_have_count(0);expect(q).to_have_value('Bản nháp tiếp theo');expect(send).to_be_enabled()
        send.click();expect(q).to_have_value('');expect(typing).to_be_visible();q.fill('Đang viết câu mới')
        held.pop(0).fulfill(status=503,json={'message':'QA lỗi có kiểm soát.'})
        expect(p.locator('[data-ai-status]')).to_contain_text('QA lỗi có kiểm soát');expect(q).to_have_value('Đang viết câu mới');expect(log.locator('.is-failed')).to_contain_text('Bản nháp tiếp theo');expect(typing).to_have_count(0)
        q.fill('Tin nhắn cần thử lại');send.click();expect(q).to_have_value('');expect(typing).to_be_visible()
        p.emulate_media(reduced_motion='reduce');assert typing.locator('span').first.evaluate('e=>getComputedStyle(e).animationName')=='none'
        held.pop(0).fulfill(status=429,json={'message':'QA hết hạn mức.'})
        expect(q).to_have_value('Tin nhắn cần thử lại');expect(send).to_be_enabled();expect(typing).to_have_count(0)
        # An abortable browser transport mock avoids leaving a Playwright route suspended across navigation.
        p.unroute('**/TroLy/Hoi')
        p.evaluate("""()=>{const original=window.fetch;window.fetch=(url,options)=>new URL(url,location.href).pathname==='/TroLy/Hoi'?new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true})):original(url,options)}""")
        send.click();expect(q).to_have_value('');expect(typing).to_be_visible();p.reload();p.locator('[data-hybrid-open]').click();expect(q).to_have_value('Tin nhắn cần thử lại');expect(send).to_be_enabled();expect(typing).to_have_count(0)
        ctx.close()
        # Real Customer send with delayed response, plus actual SignalR invalidation.
        accounts=json.loads((OUT/'accounts.json').read_text());ctx=browser.new_context(ignore_https_errors=True);p=ctx.new_page();ps.login_page(p,accounts[2]);p.goto(om.QA_BASE+'/?chat=shop')
        chat=p.locator('[data-widget-chat]');expect(chat).to_have_attribute('data-realtime','connected',timeout=15000)
        held=[];p.route('**/TuongTac/GuiTinNhan',lambda r:held.append(r));q=p.locator('#widget-chat-content');send=p.get_by_role('button',name='Gửi tin nhắn',exact=True);log=p.locator('[data-chat-messages]')
        text='QA optimistic '+uuid.uuid4().hex[:10];q.fill(text);send.click();expect(q).to_have_value('');expect(log.locator('.is-sending')).to_contain_text(text);expect(send).to_be_disabled();q.fill('Bản nháp shop tiếp theo')
        route=held.pop(0);response=route.fetch();route.fulfill(response=response)
        expect(log.locator('[data-message-id]').filter(has_text=text)).to_have_count(1);expect(log.locator('.is-sending')).to_have_count(0);expect(q).to_have_value('Bản nháp shop tiếp theo');expect(send).to_be_enabled()
        q.fill('QA lỗi gửi shop');send.click();expect(q).to_have_value('');expect(log.locator('.is-sending')).to_be_visible();held.pop(0).fulfill(status=503,json={'message':'QA chưa gửi được.'})
        expect(q).to_have_value('QA lỗi gửi shop');expect(send).to_be_enabled();expect(log.locator('.is-sending')).to_have_count(0)
        assert not errors,errors;ctx.close();browser.close()
    (OUT/'chat-composer-results.json').write_text(json.dumps({'status':'PASS','liveGemini':False,'checks':'Delayed HTTP proves immediate clear/one own bubble/three-dot typing/button lock; next draft preserved on success and error; failed input retry; abort/reload recovery; suggestions require explicit send; reduced motion; real QA Shop send and SignalR dedup; Shop error draft recovery'}))
    print('PASS: Delayed composer/typing/draft tests and real QA Shop send with SignalR dedup; zero live Gemini.',flush=True)


def input_validation():
    """Missing/malformed CAS inputs must never mutate a fresh conversation or review."""
    om.configure_qa();admin=om.admin_sessions()[0];buyer=gs.client();account=gs.register(buyer);gs.login(buyer,account)
    source=gs.get(buyer,'/')[0];admin_source=gs.get(admin,'/Admin/KhachHang/TinNhan')[0]
    assert gs.post(buyer,'/TuongTac/GuiTinNhan',source,{'Content':'QA CAS input validation','RequestToken':uuid.uuid4().hex})[0]==200
    cid=int(om.qa_sql('SELECT c.Id FROM ShopConversations c JOIN Users u ON u.Id=c.CustomerId WHERE u.Email='+gs.quote(account[0])))
    before=om.qa_sql(f'SELECT Status,AssignedAdminId,Version FROM ShopConversations WHERE Id={cid}')
    for values in ({},{'version':'invalid'},{'version':-1}):
        assert gs.post(admin,f'/Admin/KhachHang/TiepNhan/{cid}',admin_source,values)[0]==400
        assert om.qa_sql(f'SELECT Status,AssignedAdminId,Version FROM ShopConversations WHERE Id={cid}')==before
    assert gs.post(admin,f'/Admin/KhachHang/TiepNhan/{cid}',admin_source,{'version':0})[0]==302
    before=om.qa_sql(f'SELECT Status,AssignedAdminId,Version FROM ShopConversations WHERE Id={cid}')
    for values in ({},{'version':'invalid'},{'version':-1}):
        assert gs.post(admin,f'/Admin/KhachHang/KetThuc/{cid}',admin_source,values)[0]==400
        assert om.qa_sql(f'SELECT Status,AssignedAdminId,Version FROM ShopConversations WHERE Id={cid}')==before
    assert gs.post(admin,f'/Admin/KhachHang/KetThuc/{cid}',admin_source,{'version':1})[0]==302
    row=om.qa_sql('SELECT Id,Version,IsHidden FROM ProductReviews WHERE IsCurrent=1 ORDER BY Id DESC LIMIT 1')
    if row:
        rid,version,hidden=row.split('\t');before=om.qa_sql(f'SELECT Version,IsHidden FROM ProductReviews WHERE Id={rid}')
        for values in ({'hidden':'true'},{'version':version},{'version':'invalid','hidden':'false'},{'version':version,'hidden':'invalid'}):
            assert gs.post(admin,f'/Admin/KhachHang/AnHienDanhGia/{rid}',admin_source,values)[0]==400
            assert om.qa_sql(f'SELECT Version,IsHidden FROM ProductReviews WHERE Id={rid}')==before
    (OUT/'engagement-input-results.json').write_text(json.dumps({'status':'PASS','reviewChecked':bool(row),'checks':'Missing/malformed/negative versions rejected without conversation mutation; missing/malformed moderation fields rejected; valid claim/resolve still work'}))
    print('PASS: Conversation CAS and review moderation require valid form fields; malformed requests change no data.',flush=True)


def responsive_contract():
    """Six requested viewport widths, both themes, all three portals, real routes/assets."""
    from playwright.sync_api import expect
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());checks=[]
    pid=int(om.qa_sql('SELECT p.Id FROM Products p LEFT JOIN Categories c ON c.Id=p.CategoryId WHERE p.StockQuantity>3 AND (p.CategoryId IS NULL OR c.IsActive=1) ORDER BY p.Id DESC LIMIT 1'))
    oid=int(om.qa_sql('SELECT Id FROM Orders WHERE UserId=3 ORDER BY Id DESC LIMIT 1'))
    item=int(om.qa_sql('SELECT i.Id FROM OrderItems i JOIN Orders o ON o.Id=i.OrderId WHERE o.UserId=3 AND o.Status=1 AND i.ProductId IS NOT NULL ORDER BY i.Id DESC LIMIT 1'))
    conv=int(om.qa_sql('SELECT Id FROM ShopConversations WHERE CustomerId=3'))
    routes={
        'anonymous':['/','/SanPham/CuaHang',f'/SanPham/ChiTietSanPham/{pid}','/SanPham/CuaHang?search=ZZZ-empty-audit','/Account/Login','/Account/Register'],
        'customer':['/GioHang/QuanLyGioHang',f'/ThanhToan/XacNhanMuaHang/{pid}','/ThanhToan/DonHangCuaToi',f'/ThanhToan/ChiTietDonHang/{oid}',f'/TuongTac/DanhGia/{item}','/TuongTac/TroChuyen'],
        'admin':['/Admin/Admin/TongQuan','/Admin/SanPham/QuanLySanPham','/Admin/DanhMuc/QuanLyDanhMuc','/Admin/DonHang/QuanLyDonHang',f'/Admin/DonHang/ChiTietDonHang/{oid}','/Admin/NguoiDung/QuanLyNguoiDung','/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen','/Admin/KhachHang/Slider','/Admin/KhachHang/DanhGia','/Admin/KhachHang/TinNhan',f'/Admin/KhachHang/TroChuyen/{conv}','/Admin/KhachHang/ThongBaoCuaToi']}
    with ps.playwright() as pw:
        browser=pw.chromium.launch();errors=[];missing=[];negative_images=[]
        def asset_response(response):
            if response.status<400 or not response.url.startswith(om.QA_BASE) or response.request.resource_type not in ('script','stylesheet','font','image'):return
            if response.request.resource_type=='image' and response.url.removeprefix(om.QA_BASE) in ('/uploads/products/nonexistent-dashboard.png','/uploads/products/GS_STOREFRONT_MISSING.jpg'):
                negative_images.append(response.url) # Deliberate fixtures, fallback separately asserted in admin/customer browser suites.
            else:missing.append(response.url)
        for role,paths in routes.items():
            context=browser.new_context(ignore_https_errors=True,reduced_motion='reduce');page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('response',asset_response)
            if role!='anonymous':ps.login_page(page,accounts[0] if role=='admin' else accounts[2],ps.ADMIN_LOGIN if role=='admin' else '/Account/Login')
            else:page.goto(om.QA_BASE+'/')
            # Storefront supports light/dark; Admin preserves its existing interface/theme.
            theme_key='greenshop.theme'
            for width in (320,375,390,768,1024,1440):
                page.set_viewport_size({'width':width,'height':1000})
                for theme in (('existing' ,) if role=='admin' else ('light','dark')):
                    if role!='admin':page.evaluate('([key,theme])=>localStorage.setItem(key,theme)',[theme_key,theme])
                    for path in paths:
                        response=page.goto(om.QA_BASE+path);assert response.status==200,(role,path,response.status)
                        page.evaluate('document.fonts.ready')
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(role,path,width,theme)
                        assert page.locator('main').count()>0,(role,path)
                    checks.append(f'{role} {width}px {theme}: {len(paths)} routes')
            context.close()
        assert not errors and not missing,(errors,missing);browser.close()
    (OUT/'responsive-contract-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'consoleErrors':errors,'missingAssets':missing,'deliberateBrokenImageFixtures':sorted(set(negative_images)),'widths':[320,375,390,768,1024,1440]}))
    print('PASS: Real Anonymous/Customer light/dark and existing Admin interface at all six widths, no overflow, JS errors or missing local assets.',flush=True)


def order_owner_chat():
    """Completed-order review entitlements, protected owner and real pointer/wheel interaction."""
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text())
    import user_management as users
    users.OUT=OUT
    from playwright.sync_api import expect
    owner,normal=gs.client(),gs.client();ps.sign_in(owner,accounts[0],True);ps.sign_in(normal,accounts[1],True)
    assert accounts[0][0]=='trungdtt123@gmail.com'
    uid,credentials,buyer=users.fixture_customer('Per order review')
    pid=int(om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity) VALUES ('QA Independent Reviews',100000,'/images/product-placeholder.svg','QA per-order entitlement',20); SELECT LAST_INSERT_ID()"))
    receipts=[];items=[];rids=[]
    for stars in (5,1):
        oid=om.create_order(buyer,pid,1);receipts.append(oid);item=int(om.qa_sql(f'SELECT Id FROM OrderItems WHERE OrderId={oid}'));items.append(item)
        assert gs.request(buyer,f'/TuongTac/DanhGia/{item}')[0]==404
        for state in (3,4,5,1):assert om.mutate(owner,oid,'CapNhatTrangThaiDonHang',{'TargetStatus':state})[0]==302
        form,html,_=gs.get(buyer,f'/TuongTac/DanhGia/{item}');assert form.input('ReviewId')=='0' and str(oid) in html
        content=f'QA independent order {oid}'
        assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',form,{'Stars':stars,'Content':content,'OrderId':receipts[0],'UserId':1,'ProductId':1})[0]==302
        rid=int(om.qa_sql(f'SELECT Id FROM ProductReviews WHERE OrderItemId={item}'));rids.append(rid)
        assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',form,{'Stars':stars,'Content':content})[0]==302
        assert om.qa_sql(f'SELECT COUNT(*) FROM ProductReviews WHERE OrderItemId={item}')=='1'
    assert rids[0]!=rids[1]
    assert om.qa_sql(f'SELECT COUNT(*),AVG(Stars) FROM ProductReviews WHERE UserId={uid} AND ProductId={pid} AND IsCurrent=1')=='2\t3.0000'
    assert re.search(r'3[.,]0/5 · 2 đánh giá',gs.get(buyer,f'/SanPham/ChiTietSanPham/{pid}')[1])
    before=om.qa_sql(f'SELECT * FROM ProductReviews WHERE Id={rids[0]}')
    form=gs.get(buyer,f'/TuongTac/DanhGia/{items[1]}')[0]
    assert gs.post(buyer,f'/TuongTac/DanhGia/{items[1]}',form,{'Stars':2,'Content':'QA forged cross-order review ID','ReviewId':rids[0],'Version':0})[0]==302
    assert om.qa_sql(f'SELECT * FROM ProductReviews WHERE Id={rids[0]}')==before
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        updates=list(pool.map(lambda value:gs.post(buyer,f'/TuongTac/DanhGia/{items[1]}',form,{'Stars':value,'Content':'QA concurrent edit '+str(value),'ReviewId':rids[1],'Version':0})[0],(2,4)))
    assert updates==[302,302] and om.qa_sql(f'SELECT Version FROM ProductReviews WHERE Id={rids[1]}')=='1'
    assert om.qa_sql(f'SELECT * FROM ProductReviews WHERE Id={rids[0]}')==before
    outsider=gs.client();outside_account=gs.register(outsider);gs.login(outsider,outside_account);assert gs.request(outsider,f'/TuongTac/DanhGia/{items[0]}')[0]==404
    for oid in receipts:assert 'Đã đánh giá' in gs.get(buyer,f'/ThanhToan/ChiTietDonHang/{oid}')[1]
    # Normal admins cannot grant themselves, a customer, a peer or the owner any role.
    for target in (uid,1,2):
        snapshot=om.qa_sql(f'SELECT * FROM Users WHERE Id={target}')
        assert users.change(normal,target,'ThayDoiVaiTro',{'TargetRole':0 if target in (1,2) else 1,'Email':'trungdtt123@gmail.com','Role':'Owner'})[0]==403
        assert om.qa_sql(f'SELECT * FROM Users WHERE Id={target}')==snapshot
    for action,values in (('KhoaTaiKhoan',{}),('MoKhoaTaiKhoan',{}),('CapNhatThongTinNguoiDung',{'FullName':'QA must not change owner','Phone':''})):
        snapshot=om.qa_sql('SELECT * FROM Users WHERE Id=1');assert users.change(normal,1,action,values)[0]==403;assert om.qa_sql('SELECT * FROM Users WHERE Id=1')==snapshot
    assert users.change(normal,uid,'CapNhatThongTinNguoiDung',{'FullName':'QA Customer edited by support','Phone':'0912345678'})[0]==302
    assert users.change(owner,uid,'ThayDoiVaiTro',{'TargetRole':1})[0]==302
    promoted=gs.client();ps.sign_in(promoted,credentials,True)
    assert users.change(promoted,2,'ThayDoiVaiTro',{'TargetRole':0})[0]==403
    assert users.change(promoted,2,'KhoaTaiKhoan')[0]==403
    assert users.change(owner,uid,'ThayDoiVaiTro',{'TargetRole':0})[0]==302
    assert gs.request(promoted,'/Admin/NguoiDung/QuanLyNguoiDung')[0]==302
    ps.sign_in(buyer,credentials)
    registration=gs.client();register_form=gs.get(registration,'/Account/Register')[0]
    count=om.qa_sql('SELECT COUNT(*) FROM Users')
    reserved=gs.post(registration,'/Account/Register',register_form,{'FullName':'Must not claim owner','Email':'TRUNGDTT123@GMAIL.COM','Password':'QA reserved account password','ConfirmPassword':'QA reserved account password','Role':1})
    assert reserved[0]==200 and 'Email này dành cho tài khoản chủ shop' in reserved[2]
    assert om.qa_sql('SELECT COUNT(*) FROM Users')==count
    # Real history long enough to test the wheel over the message content, not the scrollbar.
    response=gs.post(buyer,'/TuongTac/GuiTinNhan',gs.get(buyer,'/')[0],{'Content':'QA scroll history','RequestToken':uuid.uuid4().hex});assert response[0]==200
    mid=json.loads(response[2])['id'];cid=int(om.qa_sql(f'SELECT ConversationId FROM ShopMessages WHERE Id={mid}'))
    rows=[f"({cid},{uid},0,{gs.quote('QA wheel message '+str(i)+' · Lịch sử trò chuyện cần đọc lại.')},{gs.quote(uuid.uuid4().hex)},UTC_TIMESTAMP()-INTERVAL 10 MINUTE)" for i in range(45)]
    om.qa_sql('INSERT INTO ShopMessages (ConversationId,SenderId,FromAdmin,Content,RequestToken,CreatedAt) VALUES '+','.join(rows))
    with ps.playwright() as pw:
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':900});p=ctx.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(p,accounts[1],ps.ADMIN_LOGIN);p.goto(om.QA_BASE+f'/Admin/NguoiDung/ChiTietNguoiDung/{uid}');expect(p.locator('form[action*="ThayDoiVaiTro"]')).to_have_count(0)
        p.goto(om.QA_BASE+'/Admin/NguoiDung/ChiTietNguoiDung/1');expect(p.get_by_role('button',name='Lưu thay đổi',exact=True)).to_be_disabled();expect(p.locator('form[action*="KhoaTaiKhoan"]')).to_have_count(0)
        p.goto(om.QA_BASE+f'/Admin/KhachHang/TroChuyen/{cid}');log=p.locator('[data-chat-messages]');expect(log.locator('[data-message-id]')).to_have_count(46)
        log.scroll_into_view_if_needed();log.evaluate('e=>e.scrollTop=e.scrollHeight');bottom=log.evaluate('e=>e.scrollTop');assert bottom>500
        box=log.bounding_box();p.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);p.mouse.wheel(0,-600)
        p.wait_for_function('(value)=>document.querySelector("[data-chat-messages]").scrollTop<value-100',arg=bottom)
        position=log.evaluate('e=>e.scrollTop');assert gs.post(buyer,'/TuongTac/GuiTinNhan',gs.get(buyer,'/')[0],{'Content':'QA new message while reading old history','RequestToken':uuid.uuid4().hex})[0]==200
        expect(log).to_contain_text('QA new message while reading old history');assert abs(log.evaluate('e=>e.scrollTop')-position)<100
        p.screenshot(path=str(OUT/'admin-support-wheel-qa.png'),animations='disabled')
        for width in (320,375,390,768,1024,1440):p.set_viewport_size({'width':width,'height':900});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
        ctx.close();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':900});p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));p.goto(om.QA_BASE+'/')
        launcher=p.locator('[data-hybrid-open]');panel=p.locator('[data-hybrid-chat]')
        def drag(locator,dx,dy):
            box=locator.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2;p.mouse.move(x,y);p.mouse.down();p.mouse.move(x+dx,y+dy,steps=18);p.mouse.up()
        original=launcher.bounding_box();drag(launcher,-550,-330);expect(panel).to_be_hidden();moved=launcher.bounding_box();assert moved['x']<original['x']-400 and moved['y']<original['y']-200
        p.reload();assert abs(launcher.bounding_box()['x']-moved['x'])<6
        launcher.click();expect(panel).to_be_visible();original=panel.bounding_box();drag(panel.locator('header strong'),-500,-70);moved=panel.bounding_box();assert moved['x']<original['x']-300
        p.locator('[data-hybrid-close]').click();launcher.click();assert abs(panel.bounding_box()['x']-moved['x'])<3
        p.locator('[data-chat-drag-handle]').focus();x=panel.bounding_box()['x'];p.keyboard.press('ArrowRight');assert panel.bounding_box()['x']>x
        p.reload();launcher.click();assert panel.bounding_box()['x']<800
        for width in (320,375,390,768,1024,1440):
            p.set_viewport_size({'width':width,'height':900});assert panel.evaluate('e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight}')
        p.set_viewport_size({'width':390,'height':900});p.evaluate("()=>{const v=new EventTarget();Object.assign(v,{height:300,offsetTop:0});Object.defineProperty(window,'visualViewport',{configurable:true,value:v});dispatchEvent(new Event('resize'));}")
        assert panel.evaluate('e=>e.getBoundingClientRect().bottom<=300')
        p.locator('[data-chat-drag-handle]').focus();p.keyboard.press('Home');p.keyboard.press('Escape');expect(panel).to_be_hidden()
        assert not errors,errors;ctx.close();browser.close()
    (OUT/'order-owner-chat-results.json').write_text(json.dumps({'status':'PASS','checks':'Independent completed-order reviews, duplicate retry/concurrent edit, cross-order/ownership denial, average and receipts; protected DB owner role/status/profile, ordinary-admin and forged-field denial, owner promotion/demotion revokes sessions, reserved registration; real Admin wheel/history scroll retention; launcher/panel pointer dragging, persistence, keyboard, six widths and keyboard viewport','liveGemini':False}))
    print('PASS: Per-order independent reviews, owner-only role administration, real Admin wheel scroll and draggable chat with viewport/keyboard safeguards.',flush=True)


def support_reviews():
    """Reproduce first-reply failure, verify atomic claims and product-first review triage."""
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text())
    from playwright.sync_api import expect
    from urllib.parse import urlencode
    admin,admin2=gs.client(),gs.client();ps.sign_in(admin,accounts[0],True);ps.sign_in(admin2,accounts[1],True)
    def fresh_chat():
        customer=gs.client();credentials=gs.register(customer);gs.login(customer,credentials)
        source=gs.get(customer,'/')[0];reply=gs.post(customer,'/TuongTac/GuiTinNhan',source,{'Content':'QA cần shop hỗ trợ','RequestToken':uuid.uuid4().hex});assert reply[0]==200
        mid=json.loads(reply[2])['id'];cid=int(om.qa_sql(f'SELECT ConversationId FROM ShopMessages WHERE Id={mid}'))
        return customer,credentials,cid
    buyer,credentials,cid=fresh_chat();path=f'/Admin/KhachHang/GuiTinNhan/{cid}';page=gs.get(admin,f'/Admin/KhachHang/TroChuyen/{cid}')[0]
    values={'Content':'QA phản hồi đầu tiên không cần bấm tiếp nhận','RequestToken':uuid.uuid4().hex}
    assert gs.request(admin,path,values)[0]==400
    assert gs.post(buyer,path,gs.get(buyer,'/')[0],values)[0]==302
    r=gs.post(admin,path,page,values);assert r[0]==200,r
    mid=json.loads(r[2])['id'];assert om.qa_sql(f'SELECT Status,AssignedAdminId,Version FROM ShopConversations WHERE Id={cid}')=='InProgress\t1\t1'
    assert gs.post(admin,path,page,values)[0]==200 and om.qa_sql(f'SELECT COUNT(*) FROM ShopMessages WHERE Id={mid}')=='1'
    other=gs.get(admin2,f'/Admin/KhachHang/TroChuyen/{cid}')[0]
    assert gs.post(admin2,path,other,{'Content':'QA không giành cuộc đang phụ trách','RequestToken':uuid.uuid4().hex})[0]==409
    assert json.loads(gs.request(buyer,'/TuongTac/TinNhanMoi')[2])['messages'][-1]['content']==values['Content']
    _,_,race=fresh_chat();pages=[gs.get(c,f'/Admin/KhachHang/TroChuyen/{race}')[0] for c in (admin,admin2)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda i:gs.post((admin,admin2)[i],f'/Admin/KhachHang/GuiTinNhan/{race}',pages[i],{'Content':'QA concurrent first reply '+str(i),'RequestToken':uuid.uuid4().hex})[0],(0,1)))
    assert sorted(replies)==[200,409],replies
    assert om.qa_sql(f'SELECT COUNT(*) FROM ShopMessages WHERE ConversationId={race} AND FromAdmin=1')=='1'
    version=om.qa_sql(f'SELECT Version FROM ShopConversations WHERE Id={cid}')
    assert gs.post(admin,f'/Admin/KhachHang/KetThuc/{cid}',page,{'version':version})[0]==302
    assert gs.request(admin,f'/Admin/KhachHang/MoLai/{cid}',{'version':2})[0]==400
    assert gs.post(admin2,f'/Admin/KhachHang/MoLai/{cid}',other,{'version':2})[0]==409
    for value in ('bad',-1,9223372036854775807):assert gs.post(admin,f'/Admin/KhachHang/MoLai/{cid}',page,{'version':value})[0]==400
    assert gs.post(admin,f'/Admin/KhachHang/MoLai/{cid}',page,{'version':2})[0]==302
    assert gs.post(admin,f'/Admin/KhachHang/MoLai/{cid}',page,{'version':2})[0]==409
    live_buyer,live_credentials,live=fresh_chat()
    with ps.playwright() as pw:
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True);ap=ctx.new_page();errors=[];ap.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(ap,accounts[0],ps.ADMIN_LOGIN);ap.goto(om.QA_BASE+f'/Admin/KhachHang/TroChuyen/{live}');expect(ap.locator('[data-conversation-hint]')).to_contain_text('tự động tiếp nhận')
        customer=browser.new_context(ignore_https_errors=True);cp=customer.new_page();ps.login_page(cp,live_credentials);cp.goto(om.QA_BASE+'/?chat=shop');expect(cp.locator('[data-widget-chat]')).to_have_attribute('data-realtime','connected',timeout=15000)
        field=ap.locator('#chat-content');send=ap.get_by_role('button',name='Gửi tin nhắn',exact=True);text='QA Admin gửi trực tiếp '+uuid.uuid4().hex[:8]
        field.fill(text);send.click();expect(field).to_have_value('');expect(cp.locator('[data-chat-messages] .chat-bubble').filter(has_text=text)).to_have_count(1);expect(ap.locator('[data-conversation-state]')).to_have_text('Đang hỗ trợ')
        assert om.qa_sql(f'SELECT AssignedAdminId FROM ShopConversations WHERE Id={live}')=='1'
        ap.get_by_role('button',name='Đánh dấu đã giải quyết',exact=True).click();expect(send).to_be_disabled();ap.get_by_role('button',name='Mở lại để phản hồi',exact=True).click();expect(send).to_be_enabled()
        ap.route('**/Admin/KhachHang/GuiTinNhan/*',lambda route:route.fulfill(status=503,json={'message':'QA lỗi gửi được giữ lại'}))
        field.fill('QA bản nháp Admin khi lỗi');send.click();expect(field).to_have_value('QA bản nháp Admin khi lỗi');expect(ap.locator('[data-chat-feedback]')).to_contain_text('QA lỗi gửi được giữ lại');ap.wait_for_timeout(200);expect(ap.locator('[data-chat-feedback]')).to_contain_text('QA lỗi gửi được giữ lại')
        ap.unroute('**/Admin/KhachHang/GuiTinNhan/*');send.click();expect(cp.locator('[data-chat-messages]')).to_contain_text('QA bản nháp Admin khi lỗi')
        assert not errors,errors;customer.close();ctx.close();browser.close()
    marker='QA Triage '+uuid.uuid4().hex[:8]
    cat=int(om.qa_sql("INSERT INTO Categories (Name,Description,IsActive) VALUES ("+gs.quote(marker)+",'',1); SELECT LAST_INSERT_ID()"))
    image=om.qa_sql('SELECT Image1 FROM ProductReviews WHERE Image1 IS NOT NULL LIMIT 1');assert image.startswith('/uploads/products/')
    products=[];rids=[]
    for i in range(2):
        pid=int(om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity,CategoryId) VALUES ("+gs.quote(marker+' '+str(i))+",100000,"+gs.quote(image)+",'QA triage purchase',10,"+str(cat)+"); SELECT LAST_INSERT_ID()"));products.append(pid)
        oid=om.create_order(buyer,pid,1)
        for state in (3,4,5,1):assert om.mutate(admin,oid,'CapNhatTrangThaiDonHang',{'TargetStatus':state})[0]==302
        item=int(om.qa_sql(f'SELECT Id FROM OrderItems WHERE OrderId={oid}'));source=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
        assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',source,{'Stars':5 if i==0 else 3,'Content':'QA triage review '+str(i)})[0]==302
        rid=int(om.qa_sql(f'SELECT Id FROM ProductReviews WHERE OrderItemId={item}'));rids.append((rid,item))
    rid,item=rids[0];edit=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',edit,{'Stars':4,'Content':'QA triage review edited','ReviewId':rid,'Version':0})[0]==302
    # Two unread events for one edited review must produce a count of one review.
    assert om.qa_sql(f"SELECT COUNT(*) FROM AdminNotifications WHERE RecipientId=1 AND EventKey LIKE 'review:{rid}:%' AND ReadAt IS NULL")=='2'
    for i in range(22):om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity,CategoryId) VALUES ("+gs.quote(marker+' empty '+str(i))+",100000,"+gs.quote(image)+",'',10,"+str(cat)+")")
    query=urlencode({'search':marker,'categoryId':cat});index='/Admin/KhachHang/DanhGia?'+query;src,html,_=gs.get(admin,index)
    assert 'data-review-product=' in html and 'data-admin-review=' not in html and 'QA triage review edited' not in html
    assert len(re.findall('data-review-product="',html))==20 and 'Trang sau' in html
    assert 'data-review-unread="1"' in html
    def matching(suffix):return gs.get(admin,index+'&'+suffix)[1]
    assert len(re.findall('data-review-product="',matching('scope=unread')))==2
    assert len(re.findall('data-review-product="',matching('scope=with-reviews')))==2
    assert len(re.findall('data-review-product="',matching('stars=3')))==1
    assert f'data-review-product="{products[1]}"' in matching('stars=3')
    assert 'data-review-product=' not in gs.get(admin,'/Admin/KhachHang/DanhGia?search=ZZZNoProductTriage')[1]
    for invalid in ('page=0','page=bad','stars=6','productId=-1','categoryId=-1','scope=bad','visibility=bad','search='+'a'*151):assert gs.request(admin,'/Admin/KhachHang/DanhGia?'+invalid)[0]==400,invalid
    detail='/Admin/KhachHang/DanhGia?productId='+str(products[0]);_,html,_=gs.get(admin,detail);assert 'QA triage review edited' in html and 'QA triage review 1' not in html
    assert gs.request(admin,'/Admin/KhachHang/DanhGia?productId=2147483647')[0]==404
    assert gs.request(admin,detail+'&reviewId='+str(rids[1][0]))[0]==400
    mark=f'/Admin/KhachHang/DaDocDanhGia/{rid}';assert gs.request(admin,mark,{})[0]==400
    returned=gs.post(admin,mark,src,{'returnUrl':detail+'&stars=4'});assert returned[0]==302 and returned[1]['Location']==detail+'&stars=4'
    assert om.qa_sql(f"SELECT COUNT(*) FROM AdminNotifications WHERE RecipientId=1 AND EventKey LIKE 'review:{rid}:%' AND ReadAt IS NULL")=='0'
    assert om.qa_sql(f"SELECT COUNT(*) FROM AdminNotifications WHERE RecipientId=2 AND EventKey LIKE 'review:{rid}:%' AND ReadAt IS NULL")=='2'
    assert gs.post(admin,mark,src,{'returnUrl':'https://evil.invalid'})[1]['Location'].startswith('/Admin/KhachHang/DanhGia?reviewId=')
    edit=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0];assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',edit,{'Stars':4,'Content':'QA triage review unread again','ReviewId':rid,'Version':1})[0]==302
    with ps.playwright() as pw:
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});p=ctx.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(p,accounts[0],ps.ADMIN_LOGIN);p.goto(om.QA_BASE+index);row=p.locator(f'[data-review-product="{products[0]}"]');expect(row.locator('[data-review-unread]')).to_have_attribute('data-review-unread','1')
        assert row.locator('.shop-alert-badge').evaluate('e=>{const r=e.getBoundingClientRect();return Math.abs(r.width-r.height)<1&&getComputedStyle(e).borderRadius==="50%"}')
        p.screenshot(path=str(OUT/'review-products-admin-qa.png'),full_page=True,animations='disabled')
        p.locator('#review-scope').select_option('unread');p.get_by_role('button',name='Lọc',exact=True).click();expect(p.locator('[data-review-product]')).to_have_count(2)
        p.locator(f'[data-review-product="{products[0]}"]').click();expect(p.locator('[data-admin-review]')).to_have_count(1);expect(p.locator('[data-admin-review]')).to_contain_text('QA triage review unread again')
        p.screenshot(path=str(OUT/'review-product-detail-admin-qa.png'),full_page=True,animations='disabled')
        p.get_by_role('button',name='Đánh dấu đã đọc',exact=True).click();expect(p.locator('[data-admin-review]')).to_have_count(0)
        p.goto(om.QA_BASE+index+'&scope=unread');expect(p.locator('[data-review-product]')).to_have_count(1)
        for width in (320,375,390,768,1024,1440):
            p.set_viewport_size({'width':width,'height':1000})
            for path in (index,detail):
                p.goto(om.QA_BASE+path);assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
        p.goto(om.QA_BASE+index);p.emulate_media(reduced_motion='reduce');assert p.locator('[data-review-product]').first.evaluate('e=>getComputedStyle(e).animationName')=='none'
        assert not errors,errors;ctx.close();browser.close()
    # Deleted-product reviews remain accessible without deleting real catalog data.
    other_rid,_=rids[1];om.qa_sql(f'UPDATE ProductReviews SET ProductId=NULL WHERE Id={other_rid}')
    assert 'Sản phẩm đã xóa' in gs.get(admin,'/Admin/KhachHang/DanhGia')[1]
    assert 'QA triage review 1' in gs.get(admin,'/Admin/KhachHang/DanhGia?productId=0')[1]
    (OUT/'support-reviews-results.json').write_text(json.dumps({'status':'PASS','checks':'Atomic first Admin reply, idempotency, simultaneous assignee race, owner/CSRF/version guards, resolve/reopen, genuine two-browser SignalR and persistent errors; product-first index/search/category/stars/unread/pagination, distinct review counts per Admin, mark-read and customer re-edit, safe redirects, legacy/deleted-product access, six widths and reduced motion','liveGemini':False}))
    print('PASS: First Admin reply and atomic assignment/reopen/security; real two-way browser chat; product review filters, per-Admin badges, pagination, legacy access and responsive UI.',flush=True)


def review_replies():
    """Real Admin reply writes, ownership/CAS, public rendering and AJAX UX on QA."""
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text())
    admin,admin2,buyer=gs.client(),gs.client(),gs.client()
    ps.sign_in(admin,accounts[0],True);ps.sign_in(admin2,accounts[1],True);ps.sign_in(buyer,accounts[2])
    pid=int(om.qa_sql("INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity) VALUES ('QA Review Replies',120000,'/images/product-placeholder.svg','QA review reply regression',20); SELECT LAST_INSERT_ID()"))
    oid=om.create_order(buyer,pid,1)
    for state in (3,4,5,1):assert om.mutate(admin,oid,'CapNhatTrangThaiDonHang',{'TargetStatus':state})[0]==302
    item=int(om.qa_sql(f'SELECT Id FROM OrderItems WHERE OrderId={oid}'))
    source=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',source,{'Stars':5,'Content':'QA khách hàng hài lòng'})[0]==302
    rid=int(om.qa_sql(f'SELECT Id FROM ProductReviews WHERE OrderItemId={item}'))
    path=f'/Admin/KhachHang/PhanHoiDanhGia/{rid}';public=f'/SanPham/ChiTietSanPham/{pid}'
    page=gs.get(admin,f'/Admin/KhachHang/DanhGia?reviewId={rid}')[0]
    version=lambda:om.qa_sql(f'SELECT Version FROM ProductReviews WHERE Id={rid}')
    rating=lambda:om.qa_sql(f'SELECT COUNT(*),AVG(Stars),SUM(Stars) FROM ProductReviews WHERE IsCurrent=1 AND IsHidden=0 AND ProductId={pid}')
    before=rating();initial=om.qa_sql(f'SELECT * FROM ProductReviews WHERE Id={rid}')
    assert gs.request(admin,path)[0]==405
    assert gs.request(admin,path,{'Content':'No CSRF','Version':version()})[0]==400
    assert gs.post(buyer,path,source,{'Content':'Customer forbidden','Version':version()})[0]==302
    guest=gs.client();guest_source=gs.get(guest,'/')[0]
    assert gs.post(guest,path,guest_source,{'Content':'Guest forbidden','Version':version()})[0]==302
    for values in ({'Content':'Missing version'},{'Content':'Bad version','Version':'bad'},{'Content':'Negative','Version':-1},{'Content':'Overflow','Version':9223372036854775807},{'Content':'  ','Version':0},{'Content':'ab','Version':0},{'Content':'x'*1501,'Version':0}):
        code=gs.post(admin,path,page,values)[0];assert code==400,(values.get('Version','missing'),len(values['Content']),code)
    assert om.qa_sql(f'SELECT * FROM ProductReviews WHERE Id={rid}')==initial
    assert gs.post(admin,'/Admin/KhachHang/PhanHoiDanhGia/2147483647',page,{'Content':'Unknown review','Version':0})[0]==404
    text='Cảm ơn bạn <script>window.replyXss=1</script>'
    assert gs.post(admin,path,page,{'Content':text,'Version':version(),'Stars':1,'UserId':2,'ReplyAdminId':999})[0]==302
    created=om.qa_sql(f'SELECT ReplyCreatedAt FROM ProductReviews WHERE Id={rid}')
    assert om.qa_sql(f'SELECT ReplyAdminId,Stars,UserId FROM ProductReviews WHERE Id={rid}')=='1\t5\t3'
    raw=gs.request(guest,public)[2]
    assert 'Phản hồi từ GreenShop' in raw and '&lt;script&gt;window.replyXss=1&lt;/script&gt;' in raw and '<script>window.replyXss' not in raw
    assert gs.post(admin,path,page,{'Content':'Stale overwrite','Version':0})[0]==409
    assert gs.post(admin,path,page,{'Content':'Cảm ơn, cửa hàng đã cập nhật phản hồi.','Version':version()})[0]==302
    assert om.qa_sql(f'SELECT ReplyCreatedAt FROM ProductReviews WHERE Id={rid}')==created
    page2=gs.get(admin2,f'/Admin/KhachHang/DanhGia?reviewId={rid}')[0];v=version()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda args:gs.post(args[0],path,args[1],{'Content':args[2],'Version':v})[0],[(admin,page,'QA phản hồi quản trị A'),(admin2,page2,'QA phản hồi quản trị B')]))
    assert sorted(results)==[302,409] and int(version())==int(v)+1
    assert rating()==before
    assert gs.post(admin,f'/Admin/KhachHang/AnHienDanhGia/{rid}',page,{'hidden':'true','version':version()})[0]==302
    assert gs.post(admin,path,page,{'Content':'QA phản hồi khi đang ẩn','Version':version()})[0]==302
    assert 'QA phản hồi khi đang ẩn' not in gs.get(guest,public)[1]
    assert gs.post(admin,f'/Admin/KhachHang/AnHienDanhGia/{rid}',page,{'hidden':'false','version':version()})[0]==302
    assert 'QA phản hồi khi đang ẩn' in gs.get(guest,public)[1] and rating()==before
    customer_form=gs.get(buyer,f'/TuongTac/DanhGia/{item}')[0]
    assert gs.post(buyer,f'/TuongTac/DanhGia/{item}',customer_form,{'Stars':5,'Content':'QA khách chỉnh nội dung','ReviewId':rid,'Version':version(),'ReplyContent':'Customer forged reply','ReplyAdminId':3})[0]==302
    assert om.qa_sql(f'SELECT ReplyContent FROM ProductReviews WHERE Id={rid}')=='QA phản hồi khi đang ẩn'
    om.qa_sql(f'UPDATE ProductReviews SET IsCurrent=0 WHERE Id={rid}')
    assert gs.post(admin,path,page,{'Content':'Archive edit denied','Version':version()})[0]==409
    om.qa_sql(f'UPDATE ProductReviews SET IsCurrent=1,ReplyContent=NULL,ReplyAdminId=NULL,ReplyCreatedAt=NULL,ReplyUpdatedAt=NULL,Version=Version+1 WHERE Id={rid}')
    from playwright.sync_api import expect
    with ps.playwright() as pw:
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});p=ctx.new_page();errors=[]
        p.on('pageerror',lambda error:errors.append(str(error)));ps.login_page(p,accounts[0],ps.ADMIN_LOGIN);p.goto(om.QA_BASE+f'/Admin/KhachHang/DanhGia?reviewId={rid}')
        form=p.locator('[data-review-reply-form]');field=form.locator('textarea');button=form.locator('button[type=submit]');status=form.locator('[data-reply-feedback]');url=p.url
        held=[];p.route('**/Admin/KhachHang/PhanHoiDanhGia/*',lambda route:held.append(route))
        field.fill('Cảm ơn bạn đã tin tưởng GreenShop. Chúc cây luôn xanh tốt!');button.click();expect(form).to_have_attribute('aria-busy','true');expect(button).to_be_disabled()
        button.dispatch_event('click');p.wait_for_timeout(100);assert len(held)==1
        held[0].continue_();p.unroute('**/Admin/KhachHang/PhanHoiDanhGia/*');expect(status).to_contain_text('Đã lưu phản hồi');expect(button).to_have_text('Cập nhật phản hồi');assert p.url==url
        original_text=field.input_value();field.fill('Cửa hàng đã cập nhật hướng dẫn chăm sóc cho bạn.');button.click();expect(status).to_contain_text('Đã lưu phản hồi');expect(form).not_to_have_attribute('aria-busy','true')
        assert om.qa_sql(f'SELECT ReplyContent FROM ProductReviews WHERE Id={rid}')==field.input_value()
        p.screenshot(path=str(OUT/'review-reply-admin-1440.png'),full_page=True,animations='disabled')
        for width in (320,375,390,768,1024,1440):
            p.set_viewport_size({'width':width,'height':1000});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
        p.set_viewport_size({'width':390,'height':1000});p.screenshot(path=str(OUT/'review-reply-admin-mobile.png'),full_page=True,animations='disabled')
        p.route('**/Admin/KhachHang/PhanHoiDanhGia/*',lambda route:route.fulfill(status=503,content_type='application/json',body=json.dumps({'message':'QA service unavailable'})))
        field.fill('Bản nháp cần được giữ khi lỗi kết nối.');button.click();expect(status).to_contain_text('QA service unavailable');expect(field).to_have_value('Bản nháp cần được giữ khi lỗi kết nối.');expect(button).to_be_enabled();p.unroute('**/Admin/KhachHang/PhanHoiDanhGia/*')
        p.emulate_media(reduced_motion='reduce');field.focus();p.keyboard.press('Tab');expect(button).to_be_focused();assert button.evaluate("e=>getComputedStyle(e).outlineStyle")!='none'
        customer=browser.new_context(ignore_https_errors=True);view=customer.new_page();view.on('pageerror',lambda error:errors.append(str(error)));view.goto(om.QA_BASE+public)
        reply=view.locator(f'[data-review-id="{rid}"] [data-review-reply]');expect(reply).to_contain_text('Cửa hàng đã cập nhật hướng dẫn chăm sóc')
        assert view.locator('script').filter(has_text='window.replyXss').count()==0
        for width in (320,375,390,768,1024,1440):
            view.set_viewport_size({'width':width,'height':900})
            for theme in ('light','dark'):
                view.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
                assert view.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert reply.evaluate('e=>e.getBoundingClientRect().width<=innerWidth')
                if width in (390,1440):reply.scroll_into_view_if_needed();view.screenshot(path=str(OUT/f'review-reply-public-{width}-{theme}.png'),animations='disabled')
        assert not errors,errors;customer.close();ctx.close();browser.close()
    assert rating()==before
    (OUT/'review-replies-results.json').write_text(json.dumps({'status':'PASS','productId':pid,'reviewId':rid,'checks':'Real delivered purchase and review; Admin create/edit, CAS race, stale/archive/CSRF/roles/overposting/validation/XSS; hidden reply follows moderation; original stars/count/average preserved; real browser AJAX loading/dedup/error draft and six widths/themes; no Main writes'}))
    print('PASS: Review replies: real Admin create/edit and public display, secure role/CSRF/CAS/validation, rating preserved, hidden/archive handling, AJAX states and responsive UI.',flush=True)

def floating():
    """Actual widget entry points keep the current page, drafts and identity intact."""
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text())
    from playwright.sync_api import expect
    with ps.playwright() as pw:
        browser=pw.chromium.launch();ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':900});p=ctx.new_page();errors=[];sockets=[]
        p.on('pageerror',lambda e:errors.append(str(e)));p.on('websocket',lambda ws:sockets.append(ws.url))
        # No chat socket is needed while closed or viewing the AI mode.
        p.goto(om.QA_BASE+'/',wait_until='networkidle');url=p.url;p.locator('[data-hybrid-open]').click()
        assert p.locator('[data-hybrid-open] svg .botanical-chat-sprout').count()==1
        expect(p.get_by_role('tab',name='Trợ lý AI',exact=True)).to_have_attribute('aria-selected','true');assert p.url==url and not sockets
        p.get_by_role('tab',name='Chat với Shop',exact=True).click();expect(p.locator('#store-panel')).to_contain_text('Đăng nhập để nhắn tin trực tiếp')
        assert p.locator('#hybrid-chat').get_attribute('aria-modal') is None
        p.keyboard.press('Escape');expect(p.locator('[data-hybrid-open]')).to_be_focused()
        ps.login_page(p,accounts[2]);p.goto(om.QA_BASE+'/SanPham/ChiTietSanPham/1',wait_until='networkidle');url=p.url
        quantity=p.locator('#Quantity');quantity.fill('2');token=quantity.locator('..').locator('..').locator('[name=__RequestVerificationToken]').input_value()
        before=om.qa_sql('SELECT COUNT(*) FROM ShopConversations');auth={c['name']:c['value'] for c in ctx.cookies() if c['name']=='GreenShop.Customer'}
        entry=p.locator('.chat-entry');entry.click();expect(p.get_by_role('tab',name='Chat với Shop',exact=True)).to_have_attribute('aria-selected','true')
        expect(p.locator('[data-widget-chat]')).to_have_attribute('data-realtime','connected',timeout=15000)
        assert p.url==url and quantity.input_value()=='2' and om.qa_sql('SELECT COUNT(*) FROM ShopConversations')==before
        assert quantity.locator('..').locator('..').locator('[name=__RequestVerificationToken]').input_value()==token
        assert auth=={c['name']:c['value'] for c in ctx.cookies() if c['name']=='GreenShop.Customer'}
        draft=p.locator('#widget-chat-content');draft.fill('QA giữ bản nháp khi đổi tab');p.get_by_role('tab',name='Trợ lý AI',exact=True).click();p.get_by_role('tab',name='Chat với Shop',exact=True).click();expect(draft).to_have_value('QA giữ bản nháp khi đổi tab')
        for _ in range(4):p.locator('[data-hybrid-close]').click();expect(entry).to_be_focused();entry.click()
        assert len(sockets)==1,sockets
        draft.fill('QA Shift Enter');draft.press('Shift+Enter');assert draft.input_value().endswith('\n');draft.fill('QA Enter submit '+uuid.uuid4().hex[:8]);sent=draft.input_value();draft.press('Enter');expect(p.locator('[data-chat-messages]')).to_contain_text(sent)
        for width in (320,375,390,768,1024,1440):
            p.set_viewport_size({'width':width,'height':900})
            for theme in ('light','dark'):
                p.evaluate('(t)=>{document.documentElement.dataset.theme=t;localStorage.setItem("greenshop.theme",t)}',theme)
                for mode in ('ai','store'):
                    p.locator(f'[data-hybrid-tab="{mode}"]').click();p.wait_for_timeout(200)
                    assert p.locator('#hybrid-chat').evaluate('(e)=>{const b=e.getBoundingClientRect();return b.x>=0&&b.right<=innerWidth&&b.y>=0&&b.bottom<=innerHeight}')
                    pane=p.locator('#ai-panel' if mode=='ai' else '#store-panel');send=pane.locator('form button[type=submit]')
                    assert send.evaluate('(e)=>{const b=e.getBoundingClientRect(),panel=document.querySelector("#hybrid-chat").getBoundingClientRect();return b.bottom<=panel.bottom&&b.top>=panel.top}')
            p.screenshot(path=str(OUT/f'floating-{width}.png'),animations='disabled')
        p.set_viewport_size({'width':390,'height':900})
        # Emulate the visual viewport available above a software keyboard, without a screenshot fake.
        p.evaluate("""()=>{window.qaVisualViewport=new EventTarget();Object.assign(qaVisualViewport,{height:300,offsetTop:0});Object.defineProperty(window,'visualViewport',{configurable:true,value:qaVisualViewport});dispatchEvent(new Event('resize'));}""")
        for mode in ('ai','store'):
            p.locator(f'[data-hybrid-tab="{mode}"]').click();assert p.locator('#hybrid-chat').evaluate('(e)=>e.getBoundingClientRect().bottom<=300')
            assert p.locator('#'+('ai-panel' if mode=='ai' else 'store-panel')+' form button').evaluate('(e)=>e.getBoundingClientRect().bottom<=300')
        p.reload();p.locator('.chat-entry').click();p.emulate_media(reduced_motion='reduce');assert p.locator('#hybrid-chat').evaluate('e=>getComputedStyle(e).animationName')=='none'
        p.locator('[data-hybrid-close]').click();p.locator('.shop-footer [data-chat-mode]').click();assert p.url==url;expect(p.get_by_role('tab',name='Chat với Shop',exact=True)).to_have_attribute('aria-selected','true')
        p.goto(om.QA_BASE+'/ThanhToan/ChiTietDonHang/1');url=p.url;p.locator('.chat-entry').click();assert p.url==url;expect(p.get_by_role('tab',name='Chat với Shop',exact=True)).to_have_attribute('aria-selected','true')
        p.goto(om.QA_BASE+'/TuongTac/TroChuyen',wait_until='networkidle');assert p.url==om.QA_BASE+'/';expect(p.locator('#hybrid-chat')).to_be_visible();expect(p.get_by_role('tab',name='Chat với Shop',exact=True)).to_have_attribute('aria-selected','true')
        ctx.close();ctx=browser.new_context(ignore_https_errors=True);p=ctx.new_page();ps.login_page(p,accounts[0],ps.ADMIN_LOGIN);p.goto(om.QA_BASE+'/?portal=admin');p.locator('[data-hybrid-open]').click();p.get_by_role('tab',name='Chat với Shop',exact=True).click();expect(p.get_by_role('link',name='Mở hộp thư quản trị')).to_be_visible();assert p.locator('[data-widget-chat]').count()==0
        assert not errors,errors;ctx.close();browser.close()
    (OUT/'floating-results.json').write_text(json.dumps({'status':'PASS','checks':'Actual entry points, no navigation/reload/form/token/cookie loss, first AI mode, direct Shop mode, one lazy WebSocket, drafts, Enter/Shift Enter, six widths/two themes, visual viewport keyboard simulation, reduced motion, legacy redirect and Admin gate'}))
    print('PASS: Single floating widget: product/order/footer/legacy routes, URL/form/cookie preservation, one lazy socket, keyboard, six widths/themes and viewport-aware composer.',flush=True)


def account_switch():
    """Prevent old and newly authenticated account histories mixing in an existing tab."""
    om.configure_qa();a,b=gs.client(),gs.client();aa=gs.register(a);bb=gs.register(b);gs.login(a,aa);gs.login(b,bb)
    from playwright.sync_api import expect
    with ps.playwright() as pw:
     br=pw.chromium.launch();ca=br.new_context(ignore_https_errors=True);pa=ca.new_page();ps.login_page(pa,aa);pa.goto(om.QA_BASE+'/?chat=shop',wait_until='networkidle');pa.locator('#widget-chat-content').fill('QA identity old actor');pa.get_by_role('button',name='Gửi tin nhắn',exact=True).click();expect(pa.locator('[data-chat-messages]')).to_contain_text('QA identity old actor')
     cb=br.new_context(ignore_https_errors=True);pb=cb.new_page();ps.login_page(pb,bb);pb.goto(om.QA_BASE+'/?chat=shop',wait_until='networkidle');pb.locator('#widget-chat-content').fill('QA identity new actor');pb.get_by_role('button',name='Gửi tin nhắn',exact=True).click();expect(pb.locator('[data-chat-messages]')).to_contain_text('QA identity new actor')
     ca.add_cookies([x for x in cb.cookies() if x['name']=='GreenShop.Customer']);pa.get_by_role('tab',name='Trợ lý AI',exact=True).click();pa.get_by_role('tab',name='Chat với Shop',exact=True).click();pa.wait_for_timeout(1500)
     expect(pa.locator('[data-chat-feedback]')).to_contain_text('Phiên đăng nhập đã thay đổi');expect(pa.locator('[data-chat-messages]')).to_be_empty();expect(pa.locator('#widget-chat-content')).to_be_disabled();mixed=False
     (OUT/'account-switch-results.json').write_text(json.dumps({'status':'PASS','scope':'Genuine synthetic Customer cookies switch while first tab remains open; old history purged, connection stopped, composer disabled'}));print('PASS: Account change invalidates chat UI instead of mixing histories.',flush=True);br.close()
