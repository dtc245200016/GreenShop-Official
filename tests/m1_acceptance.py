"""M1: cold-start/privileges/readiness/proxy acceptance; all business writes use QA only.

Run modes sequentially: prepare, cold, regression, resilience, main, evidence, teardown.
Private credentials/backups stay in GREENSHOP_QA_DIR; public evidence is sanitized.
"""
import sys,os,json,subprocess,secrets,time,hashlib,urllib.request,urllib.error,ssl,shutil
from qa_support import PRIVATE, PROJECT, expected_migrations, verify_migrations, verify_schema, table_hashes
from pathlib import Path
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import storefront_regression as gs
import order_management as om
import portal_sessions as ps

ROOT=gs.ROOT
PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)
OUT=PRIVATE/'qa';OUT.mkdir(mode=0o700,parents=True,exist_ok=True)
EVIDENCE=ROOT/'docs/evidence/commit1'
MAIN_COMPOSE=gs.main_compose;MAIN_SQL=gs.main_sql

om.OUT=ps.OUT=OUT;om.QA_PROJECT=PROJECT

def run(command,**kwargs):
    return subprocess.run(command,cwd=ROOT,text=True,capture_output=True,**kwargs)

def record(name,value):
    p=PRIVATE/(name+'.json');p.write_text(json.dumps(value,indent=2));os.chmod(p,0o600)

def baseline():
    assert not (PRIVATE/'baseline.json').exists(), 'Never overwrite an existing preservation baseline'
    value={'tables':table_hashes(MAIN_SQL),'migrations':MAIN_SQL('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines(),'head':run(['git','rev-parse','HEAD']).stdout.strip()}
    for service in ('db','web_app','nginx','phpmyadmin'):
        cid=MAIN_COMPOSE('ps','-q',service);info=json.loads(run(['docker','inspect',cid]).stdout)[0]
        value[service]={'id':cid,'started':info['State']['StartedAt'],'image':info['Image'],'mounts':info['Mounts']}
    value['files']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'nginx/ssl').glob('*') if p.is_file()}
    value['uploads']=MAIN_COMPOSE('exec','-T','web_app','sh','-c','find /app/wwwroot/uploads/products /app/keys -type f -exec sha256sum {} +')
    record('baseline',value)
    print('PASS: Read-only Main baseline captured privately; no Main writes.',flush=True)

def prepare():
    if not (PRIVATE/'baseline.json').exists(): baseline()
    assert PROJECT.startswith('greenshop-') and '-qa-' in PROJECT
    main_id=MAIN_COMPOSE('ps','-q','db')
    assert main_id, 'Start or explicitly inspect Main before preparing isolated QA'
    main_project=run(['docker','inspect','--format','{{index .Config.Labels "com.docker.compose.project"}}',main_id]).stdout.strip()
    assert PROJECT!=main_project, 'QA project must differ from Main'
    assert not om.qa_compose('ps','-q','db') if (OUT/'compose.yaml').exists() else True
    source=PRIVATE/'source'
    assert not source.exists(), 'Use a fresh GREENSHOP_QA_DIR; never overwrite an earlier run'
    source.mkdir()
    # Copy only Git-visible source; no ignored secrets, uploads, TLS or bin/obj.
    files=run(['git','ls-files','--cached','--others','--exclude-standard','-z']).stdout.split('\0')
    for name in files:
        if not name or not (ROOT/name).is_file(): continue
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    env_text=(source/'.env.example').read_text()
    for key in ('MYSQL_ROOT_PASSWORD','MYSQL_APP_PASSWORD'):
        import re
        env_text=re.sub(r'^'+key+r'=.*$',key+'='+secrets.token_hex(32),env_text,flags=re.M)
    (source/'.env').write_text(env_text);os.chmod(source/'.env',0o600)
    result=subprocess.run(['docker','compose','config','--format','json'],cwd=source,text=True,capture_output=True);assert result.returncode==0
    configuration=json.loads(result.stdout);services=configuration['services']
    root_password=secrets.token_hex(32);app_password=secrets.token_hex(32)
    for name in ('keys','images','ssl'):(OUT/name).mkdir(mode=0o700,exist_ok=True)
    assert run(['bash','scripts/generate-dev-cert.sh','localhost','--output-dir',str(OUT/'ssl')]).returncode==0
    services['db']['environment']={'MYSQL_ROOT_PASSWORD':root_password,'MYSQL_DATABASE':'greenshop_order_qa','MYSQL_USER':'greenshop_app','MYSQL_PASSWORD':app_password}
    services['db']['ports']=[];services['db']['volumes']=[{'type':'volume','source':'mysql_data','target':'/var/lib/mysql'}]
    services['web_app']['environment']={'ASPNETCORE_ENVIRONMENT':'Production','ASPNETCORE_URLS':'http://+:8080','ConnectionStrings__DefaultConnection':f'Server=db;Database=greenshop_order_qa;Uid=greenshop_app;Pwd={app_password};','Security__LoginAttemptsPerMinute':'200','Security__RegistrationAttemptsPerMinute':'200'}
    services['web_app']['image']=PROJECT+'-web:release';services['web_app']['ports']=[]
    services['web_app']['volumes']=[{'type':'bind','source':str(OUT/'keys'),'target':'/app/keys'},{'type':'bind','source':str(OUT/'images'),'target':'/app/wwwroot/uploads/products'}]
    https_port=os.environ.get('GREENSHOP_QA_HTTPS_PORT','18543');http_port=os.environ.get('GREENSHOP_QA_HTTP_PORT','18581');pma_port=os.environ.get('GREENSHOP_QA_PMA_PORT','18580')
    conf=(ROOT/'nginx/default.conf').read_text().replace('return 301 https://$host$request_uri;',f'return 301 https://$host:{https_port}$request_uri;').replace('proxy_set_header Host $host;','proxy_set_header Host $http_host;')
    (OUT/'nginx.conf').write_text(conf)
    services['nginx']['ports']=[{'target':443,'published':https_port,'host_ip':'127.0.0.1','protocol':'tcp'},{'target':80,'published':http_port,'host_ip':'127.0.0.1','protocol':'tcp'}]
    services['nginx']['volumes']=[{'type':'bind','source':str(OUT/'nginx.conf'),'target':'/etc/nginx/conf.d/default.conf','read_only':True},{'type':'bind','source':str(OUT/'ssl'),'target':'/etc/nginx/ssl','read_only':True}]
    services['phpmyadmin']['ports']=[{'target':80,'published':pma_port,'host_ip':'127.0.0.1','protocol':'tcp'}]
    services['phpmyadmin']['environment']={'PMA_HOST':'db','PMA_PORT':'3306','PMA_VERBOSE':'GreenShop M1 - disposable QA'}
    for service in services.values():service.pop('container_name',None)
    # An isolated, explicit subnet makes a real IP-change proxy test reproducible.
    used=run(['docker','network','inspect',*run(['docker','network','ls','-q']).stdout.split()]);assert used.returncode==0
    subnet=os.environ.get('GREENSHOP_QA_SUBNET','172.30.250.0/24')
    assert all(c.get('Subnet')!=subnet for n in json.loads(used.stdout) for c in (n.get('IPAM',{}).get('Config') or []))
    configuration={'services':services,'volumes':{'mysql_data':{}},'networks':{'app_net':{'driver':'bridge','ipam':{'config':[{'subnet':subnet}]}}}}
    p=OUT/'compose.yaml';p.write_text(json.dumps(configuration,indent=2));os.chmod(p,0o600)
    (OUT/'qa.env').write_text('QA_DB_PASSWORD='+root_password+'\n');os.chmod(OUT/'qa.env',0o600)
    (OUT/'credentials.json').write_text(json.dumps({'root':root_password,'app':app_password}));os.chmod(OUT/'credentials.json',0o600)
    print('PASS: Four-service disposable QA prepared; no production volumes/keys/certificates shared.',flush=True)

def certificates():
    checks=[]
    for host,label in (('192.0.2.8','ip'),('greenshop.example.invalid','dns'),('::1','ipv6')):
        directory=PRIVATE/('cert-'+label);directory.mkdir(exist_ok=True)
        result=run(['bash','scripts/generate-dev-cert.sh',host,'--output-dir',str(directory)]);assert result.returncode==0,result.stderr
        before={f:hashlib.sha256((directory/f).read_bytes()).hexdigest() for f in ('key.pem','cert.pem')}
        certificate=run(['openssl','x509','-in',str(directory/'cert.pem'),'-noout','-ext','subjectAltName']);assert certificate.returncode==0
        kind='-checkhost' if label=='dns' else '-checkip';assert run(['openssl','x509','-in',str(directory/'cert.pem'),'-noout',kind,host]).returncode==0
        certpub=run(['openssl','x509','-in',str(directory/'cert.pem'),'-pubkey','-noout']).stdout
        keypub=run(['openssl','pkey','-in',str(directory/'key.pem'),'-pubout']).stdout;assert certpub==keypub
        assert (directory/'key.pem').stat().st_mode&0o777==0o600
        assert run(['bash','scripts/generate-dev-cert.sh',host,'--output-dir',str(directory)]).returncode!=0
        assert before=={f:hashlib.sha256((directory/f).read_bytes()).hexdigest() for f in before}
        assert run(['bash','scripts/generate-dev-cert.sh','bad/name','--force','--output-dir',str(directory)]).returncode!=0
        assert before=={f:hashlib.sha256((directory/f).read_bytes()).hexdigest() for f in before}
        assert run(['bash','scripts/generate-dev-cert.sh',host,'--force','--output-dir',str(directory)]).returncode==0
        checks.append(label+': SAN/type, matching key, 600, no implicit overwrite, rejected invalid host, explicit force')
    record('cert-script',{'status':'PASS','checks':checks});print('PASS: Certificate script IP/DNS/IPv6, SAN/key match, permissions, overwrite guard and explicit rotation.',flush=True)

def cold():
    om.qa_compose('config','--quiet');om.qa_compose('build','--no-cache','web_app');om.qa_compose('up','-d','--wait','--wait-timeout','180')
    om.configure_qa();verify_migrations(om.qa_sql);verify_schema(om.qa_sql)
    assert om.qa_sql('SELECT COUNT(*) FROM Users')=='0' and om.qa_sql('SELECT COUNT(*) FROM Products')=='0'
    assert om.qa_sql('SELECT FlatShippingFee,FreeShippingThreshold,VietQrEnabled FROM PaymentShippingSettings')=='30000.00\t300000.00\t0'
    assert gs.request(gs.client(),'/health/ready')[0]==200
    # Exercise the exact operator shell wrapper with QA Compose overrides.
    env=os.environ.copy();env.update({'COMPOSE_FILE':str(OUT/'compose.yaml'),'COMPOSE_PROJECT_NAME':PROJECT,'COMPOSE_ENV_FILES':str(OUT/'qa.env')})
    result=run(['bash','scripts/bootstrap-db-user.sh'],env=env);assert result.returncode==0,result.stderr
    credentials=json.loads((OUT/'credentials.json').read_text())
    def app_sql(query):
        return om.qa_compose('exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_PASSWORD" mysql --protocol=TCP -h db -ugreenshop_app -N -B --database="$MYSQL_DATABASE"',input=query)
    assert app_sql('SELECT DATABASE(),CURRENT_USER()')=='greenshop_order_qa\tgreenshop_app@%'
    for query in ('SELECT User FROM mysql.user','CREATE DATABASE greenshop_forbidden','CREATE USER \'qa_forbidden\'@\'%\''):
        try:app_sql(query);raise AssertionError('Unexpected global privilege')
        except subprocess.CalledProcessError:pass
    # Fresh Admin: no default credentials; a repeat must refuse without data changes.
    accounts=[[f'qa-order-{i}@example.invalid',secrets.token_urlsafe(28)] for i in (1,2,3)]
    accounts[0][0]='trungdtt123@gmail.com'
    payload=json.dumps({'FullName':'QA Order User 1','Email':accounts[0][0],'Password':accounts[0][1]})
    assert om.qa_compose('exec','-T','web_app','dotnet','GreenShop.Web.dll','--create-initial-admin',input=payload)
    before=ps.table_hashes(om.qa_sql)
    try:om.qa_compose('exec','-T','web_app','dotnet','GreenShop.Web.dll','--create-initial-admin',input=payload);raise AssertionError('Initial Admin repeated')
    except subprocess.CalledProcessError:pass
    assert ps.table_hashes(om.qa_sql)==before
    import bcrypt
    for i in (2,3):
        digest=bcrypt.hashpw(accounts[i-1][1].encode(),bcrypt.gensalt()).decode()
        om.qa_sql(f"INSERT INTO Users (Id,FullName,Email,PasswordHash,Phone,Role,CreatedAt,IsActive,Version,SessionVersion) VALUES ({i},'QA Order User {i}',{gs.quote(accounts[i-1][0])},{gs.quote(digest)},'0912345678',{1 if i==2 else 0},UTC_TIMESTAMP(),1,0,0)")
    (OUT/'accounts.json').write_text(json.dumps(accounts));os.chmod(OUT/'accounts.json',0o600)
    om.qa_sql("INSERT INTO Products (Id,Name,Price,ImageUrl,Description,StockQuantity) VALUES (1,'QA Legacy Plant',100000,'/images/product-placeholder.svg','QA snapshot',18); INSERT INTO Orders (Id,UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES (1,3,'00000000000000000000000000000001','QA Recipient','0912345678','QA Address','2026-01-01',200000,0,0,'COD',0,'',0); INSERT INTO OrderItems (OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES (1,1,'QA Historical Plant','/images/product-placeholder.svg',100000,2)")
    # Prove readiness fails for unavailable DB while Kestrel remains listening.
    om.qa_compose('pause','db')
    try:
        assert gs.request(gs.client(),'/health/ready')[0]==503
        result=run(['docker','compose','--project-name',PROJECT,'--file',str(OUT/'compose.yaml'),'--env-file',str(OUT/'qa.env'),'exec','-T','web_app','dotnet','GreenShop.Web.dll','--healthcheck']);assert result.returncode!=0
    finally:om.qa_compose('unpause','db')
    for _ in range(20):
        if gs.request(gs.client(),'/health/ready')[0]==200:break
        time.sleep(1)
    else:raise AssertionError('Readiness did not recover')
    record('cold-start',{'status':'PASS','checks':['Four services start on isolated MySQL named volume','Source migration IDs match applied IDs; default shipping initialized by schema-scoped app user','Bootstrap wrapper idempotent; app cannot read mysql.user/create users/other databases','First Admin created only on empty Users; repeat changes no data','Readiness 503/nonzero when QA DB paused, recovers automatically'],'writes':'synthetic QA only'})
    print('PASS: Cold start, schema-scoped DB privileges, safe first Admin, real DB readiness failure/recovery.',flush=True)

def regression():
    import payment_shipping as payment
    import customer_ui as customer
    import dashboard_management as dashboard
    import user_management as users
    import customer_engagement as engagement
    import system_review as review
    for module in (om,ps,payment,customer,dashboard,users,engagement,review):module.OUT=OUT
    om.QA_PROJECT=PROJECT;payment.MAIN_COMPOSE=MAIN_COMPOSE
    gs.REPORTS=OUT/'storefront';gs.REPORTS.mkdir(exist_ok=True)
    callbacks={'order-owner-chat':engagement.order_owner_chat,'support-reviews':engagement.support_reviews,'review-replies':engagement.review_replies,'account-switch':engagement.account_switch,'floating':engagement.floating,'business':payment.business_regression,'security':ps.security,'payment':ps.payment_smoke,'admin':om.browser_checks,'customer':customer.browser,'engagement':engagement.run,'hybrid':engagement.hybrid_widget,'contracts':engagement.contracts,
        'ai-widget':engagement.ai_widget,'responsive':engagement.responsive_contract,'inputs':engagement.input_validation,'users':lambda:users.business(check_legacy=False),'user-browser':users.browser,'user-security':users.additional_security,'audit':review.audit,'dashboard':dashboard.metrics,'dashboard-fixtures':dashboard.fixtures,'categories':review.category_crud,
        'payment-full':payment.payment_checks,'payment-edges':payment.checkout_edges,'payment-security':payment.security,'payment-reports':payment.reports,'fractional':payment.fractional_prices}
    callbacks[sys.argv[2]]()
    record('regression-'+sys.argv[2],{'status':'PASS','writes':'synthetic QA only','suite':sys.argv[2]})

def resilience():
    om.configure_qa();accounts=json.loads((OUT/'accounts.json').read_text());client=gs.client()
    ps.sign_in(client,accounts[0],True);ps.sign_in(client,accounts[2]);before=ps.table_hashes(om.qa_sql)
    inspect=lambda service:json.loads(subprocess.check_output(['docker','inspect',om.qa_compose('ps','-q',service)],text=True))[0]
    assets=lambda:om.qa_compose('exec','-T','web_app','sh','-c','find /app/keys /app/wwwroot/uploads/products -type f -exec sha256sum {} +')
    asset_hashes=assets()
    original_db=inspect('db')
    om.qa_compose('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','--wait','--wait-timeout','120','db')
    current_db=inspect('db');assert current_db['Id']!=original_db['Id']
    assert current_db['Mounts']==original_db['Mounts']
    assert ps.table_hashes(om.qa_sql)==before
    web=inspect('web_app');proxy=inspect('nginx');old_ip=next(iter(web['NetworkSettings']['Networks'].values()))['IPAddress']
    p=OUT/'compose.yaml';configuration=json.loads(p.read_text())
    import ipaddress
    subnet=ipaddress.ip_network(configuration['networks']['app_net']['ipam']['config'][0]['subnet'])
    candidate=str(subnet.network_address+200);candidate=str(subnet.network_address+201) if candidate==old_ip else candidate
    configuration['services']['web_app']['networks']={'app_net':{'ipv4_address':candidate}};p.write_text(json.dumps(configuration,indent=2))
    om.qa_compose('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','--wait','--wait-timeout','90','web_app')
    current=inspect('web_app');new_ip=next(iter(current['NetworkSettings']['Networks'].values()))['IPAddress'];assert old_ip!=new_ip
    for _ in range(20):
        try:
            if gs.request(gs.client(),'/')[0]==200:break
        except (urllib.error.URLError,OSError):pass
        time.sleep(1)
    else:raise AssertionError('Nginx retained stale upstream')
    assert assets()==asset_hashes
    now=inspect('nginx');assert now['Id']==proxy['Id'] and now['State']['StartedAt']==proxy['State']['StartedAt']
    assert ps.table_hashes(om.qa_sql)==before
    assert 'QA Order User 1' in gs.get(client,'/Admin/DonHang/QuanLyDonHang')[1]
    assert 'QA Order User 3' in gs.get(client,'/ThanhToan/DonHangCuaToi')[1]
    assert om.qa_compose('exec','-T','nginx','nginx','-t')==''
    record('qa-resilience',{'status':'PASS','old_ip':old_ip,'new_ip':new_ip,'checks':'QA DB force-recreate preserves named volume/all tables; real web IP change; Nginx unchanged; HTTPS recovers; genuine Admin/Customer cookies retained'})
    print('PASS: Real QA web IP change recovers via unchanged Nginx; both cookies and all tables persist.',flush=True)

def browser_evidence():
    om.configure_qa();EVIDENCE.mkdir(parents=True,exist_ok=True);accounts=json.loads((OUT/'accounts.json').read_text());credentials=json.loads((OUT/'credentials.json').read_text())
    with ps.playwright() as pw:
        from playwright.sync_api import expect
        b=pw.chromium.launch();ctx=b.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});p=ctx.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(p,accounts[0],ps.ADMIN_LOGIN);p.goto(om.QA_BASE+'/Admin/Admin/TongQuan');p.screenshot(path=str(EVIDENCE/'admin-dashboard-qa.png'),full_page=True,animations='disabled')
        for path in ('/Admin/SanPham/QuanLySanPham','/Admin/DanhMuc/QuanLyDanhMuc','/Admin/DonHang/QuanLyDonHang','/Admin/NguoiDung/QuanLyNguoiDung','/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen'):
            assert p.goto(om.QA_BASE+path).status==200,path
        pma='http://127.0.0.1:'+os.environ.get('GREENSHOP_QA_PMA_PORT','18580');p.goto(pma+'/');expect(p.locator('#input_username')).to_be_visible();p.locator('#input_username').fill('greenshop_app');p.locator('#input_password').fill(credentials['app']);p.locator('#input_go').click()
        expect(p.locator('body')).to_contain_text('greenshop_order_qa');p.goto(pma+'/index.php?route=/database/structure&db=greenshop_order_qa')
        expect(p.locator('body')).to_contain_text('OrderItems');expect(p.locator('body')).to_contain_text('__EFMigrationsHistory')
        assert p.locator('input[type=password]').count()==0
        p.screenshot(path=str(EVIDENCE/'phpmyadmin-qa.png'),full_page=True)
        ctx.close();ctx=b.new_context(ignore_https_errors=True,viewport={'width':1280,'height':900});p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)))
        ps.login_page(p,accounts[2]);p.goto(om.QA_BASE+'/ThanhToan/XacNhanMuaHang/1');p.locator('#Address').fill('QA fixture - no real customer address')
        p.screenshot(path=str(EVIDENCE/'checkout-qa.png'),full_page=True,animations='disabled')
        assert not errors,errors;ctx.close();b.close()
    record('browser-evidence',{'status':'PASS','checks':'Actual QA Admin pages, authenticated phpMyAdmin schema and Customer checkout; synthetic accounts/records only; no credentials/tokens/cookies in screenshots'})
    print('PASS: Real QA Admin/phpMyAdmin/checkout screenshots and authenticated database access; no real customer credentials/data.',flush=True)

def preservation():
    before=json.loads((PRIVATE/'baseline.json').read_text());assert table_hashes(MAIN_SQL)==before['tables']
    assert MAIN_SQL('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines()==before['migrations']
    for service in ('db','web_app','nginx','phpmyadmin'):
        cid=MAIN_COMPOSE('ps','-q',service)
        current=json.loads(run(['docker','inspect',cid]).stdout)[0]
        assert cid==before[service]['id'] and current['State']['StartedAt']==before[service]['started']
        identity=lambda mounts: sorted(json.dumps(mount,sort_keys=True) for mount in mounts)
        assert identity(current['Mounts'])==identity(before[service]['mounts']), service
    for file,digest in before['files'].items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==digest
    assert MAIN_COMPOSE('exec','-T','web_app','sh','-c','find /app/wwwroot/uploads/products /app/keys -type f -exec sha256sum {} +')==before['uploads']
    record('preservation',{'status':'PASS','checks':'All Main tables/schema/credentials/roles/payments unchanged; same containers, volumes, TLS, uploads and key ring'})
    print('PASS: Main data, schema, containers, volumes, certificates, uploads and keys unchanged.',flush=True)

def main():
    assert run(['docker','compose','config','--quiet']).returncode==0
    result=run(['docker','compose','exec','-T','nginx','nginx','-t']);assert result.returncode==0
    route=run(['ip','-j','-4','route','get','1.1.1.1']);assert route.returncode==0
    address=json.loads(route.stdout)[0]['prefsrc']
    # Existing cert must validate without curl -k at its actual VM IP.
    certificate=ROOT/'nginx/ssl/cert.pem';key=ROOT/'nginx/ssl/key.pem'
    assert run(['openssl','x509','-in',str(certificate),'-noout','-checkip',address]).returncode==0
    assert run(['openssl','x509','-in',str(certificate),'-noout','-checkend','0']).returncode==0
    assert run(['openssl','x509','-in',str(certificate),'-pubkey','-noout']).stdout==run(['openssl','pkey','-in',str(key),'-pubout']).stdout
    assert run(['curl','--noproxy','*','--silent','--cacert',str(certificate),'--output','/dev/null','--write-out','%{http_code}','https://'+address+'/']).stdout=='200'
    for path in ('/','/SanPham/CuaHang','/Account/Login',ps.ADMIN_LOGIN,'/health/ready','/css/storefront-theme.css','/js/storefront-theme.js','/lib/fontawesome/css/all.min.css'):
        code,h,body=gs.request(gs.client(),path);assert code==200,path
        if path=='/':
            assert h['X-Content-Type-Options']=='nosniff' and h['X-Frame-Options']=='SAMEORIGIN' and h['Referrer-Policy']=='strict-origin-when-cross-origin'
            assert h['Server']=='nginx'
    opener=gs.client()
    try:opener.open('http://'+address+'/SanPham/CuaHang?search=qa');raise AssertionError('Missing HTTP redirect')
    except urllib.error.HTTPError as e:assert e.code==301 and e.headers['Location']=='https://'+address+'/SanPham/CuaHang?search=qa'
    for path,login in (('/Admin/DonHang/QuanLyDonHang',ps.ADMIN_LOGIN),('/ThanhToan/DonHangCuaToi','/Account/Login')):
        code,h,_=gs.request(gs.client(),path);assert code==302 and login in h['Location']
    applied=MAIN_SQL('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines()
    pending=[x for x in expected_migrations() if x not in applied]
    record('main-migrations',{'status':'PASS' if applied==expected_migrations() else 'FAIL','applied':applied,'expected':expected_migrations(),'pending':pending})
    assert MAIN_COMPOSE('exec','-T','web_app','dotnet','GreenShop.Web.dll','--healthcheck')==''
    for service in ('db','web_app','nginx','phpmyadmin'):
        cid=MAIN_COMPOSE('ps','-q',service);assert run(['docker','inspect','--format','{{.State.Health.Status}}',cid]).stdout.strip()=='healthy'
    for service,port in (('db','3306/tcp'),('web_app','8080/tcp'),('phpmyadmin','80/tcp')):
        cid=MAIN_COMPOSE('ps','-q',service);bindings=json.loads(run(['docker','inspect','--format','{{json .NetworkSettings.Ports}}',cid]).stdout)[port]
        assert bindings and all(b['HostIp']=='127.0.0.1' for b in bindings)
    assert MAIN_COMPOSE('exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_PASSWORD" mysql --protocol=TCP -h db -ugreenshop_app -N -B --database=greenshop -e "SELECT CURRENT_USER(),COUNT(*) FROM __EFMigrationsHistory"')=='greenshop_app@%\t'+str(len(applied))
    # Verify the actual phpMyAdmin container reaches Main MySQL with the app account.
    resolved=json.loads(run(['docker','compose','config','--format','json']).stdout)
    password=resolved['services']['db']['environment']['MYSQL_PASSWORD']
    php='$v=json_decode(stream_get_contents(STDIN),true); $db=new mysqli("db","greenshop_app",$v["password"],"greenshop"); $r=$db->query("SELECT COUNT(*) AS n FROM __EFMigrationsHistory"); echo $r->fetch_assoc()["n"];'
    result=run(['docker','compose','exec','-T','phpmyadmin','php','-r',php],input=json.dumps({'password':password}))
    assert result.returncode==0 and result.stdout.strip()==str(len(applied))
    preservation();record('main-runtime',{'status':'PASS','scope':'Read-only Main smoke; deployed image may precede working source','schemaMatchesSource':not pending,'checks':'TLS, redirect, headers, DB/phpMyAdmin, health and auth challenges'})
    print('PASS: Read-only Main runtime/TLS/DB smoke; no deployment or business writes.',flush=True)
    assert applied==expected_migrations(), 'Main migration IDs differ from audited source; deployment intentionally not performed'

def migration_upgrade():
    """The latest 9→10 index change preserves history and unlocks a second purchase."""
    om.configure_qa()
    schema='greenshop_upgrade_qa_'+secrets.token_hex(5)
    assert om.qa_sql("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME="+gs.quote(schema))=='0'
    om.qa_sql('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
    def sql(q):return om.qa_compose('exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B --default-character-set=utf8mb4 "$1"','sh',schema,input=q)
    env=os.environ.copy();env['ConnectionStrings__DefaultConnection']='Server=localhost;Database=greenshop_design;Uid=unused;Pwd=unused'
    ids=expected_migrations();ef=os.environ['GREENSHOP_EF_DLL']
    def script(start,end,name):
        result=subprocess.run(['dotnet',ef,'migrations','script',start,end,'--project','backend/GreenShop.Web','--configuration','Release','--no-build','--no-color'],env=env,check=True,capture_output=True,text=True)
        p=PRIVATE/(name+'.sql');p.write_text(result.stdout);os.chmod(p,0o600)
        return result.stdout
    sql(script('0',ids[-2],'legacy'))
    sql("INSERT INTO Users (Id,FullName,Email,PasswordHash,Phone,Role,CreatedAt,IsActive,Version,SessionVersion) VALUES (1,'QA upgrade','qa-upgrade@example.invalid','QA hash','',0,UTC_TIMESTAMP(),1,0,0),(2,'QA Admin','qa-upgrade-admin@example.invalid','QA hash','',1,UTC_TIMESTAMP(),1,0,0)")
    sql("INSERT INTO Products (Id,Name,Price,ImageUrl,Description,StockQuantity) VALUES (1,'QA upgrade plant',100000,'/images/product-placeholder.svg','',5)")
    for oid in (1,2):
        sql(f"INSERT INTO Orders (Id,UserId,ConfirmationToken,RecipientName,Phone,Address,CreatedAt,Total,Status,IsPaid,PaymentMethod,InventoryStatus,AdminNote,Version) VALUES ({oid},1,'{oid:032x}','QA','0912345678','QA address',UTC_TIMESTAMP(),100000,1,0,'COD',1,'',0)")
        sql(f"INSERT INTO OrderItems (Id,OrderId,ProductId,ProductName,ImageUrl,UnitPrice,Quantity) VALUES ({oid},{oid},1,'QA plant','/images/product-placeholder.svg',100000,1)")
    sql("INSERT INTO ProductReviews (Id,OrderItemId,UserId,ProductId,ProductName,Stars,Content,Image1,CreatedAt,ReplyContent,ReplyAdminId,ReplyCreatedAt) VALUES (1,1,1,1,'QA plant',3,'QA preserved first purchase','/uploads/products/qa-old.png','2026-01-01','QA preserved official reply',2,'2026-01-02')")
    columns={t:[r.split('\t')[0] for r in sql('SHOW COLUMNS FROM `'+t+'`').splitlines()] for t in sql('SHOW TABLES').splitlines() if t!='__EFMigrationsHistory'}
    def original_rows():
        return {t:hashlib.sha256('\n'.join(sorted(sql('SELECT '+','.join('`'+n+'`' for n in names)+' FROM `'+t+'`').splitlines())).encode()).hexdigest() for t,names in columns.items()}
    before=original_rows();old_review=sql('SELECT * FROM ProductReviews WHERE Id=1')
    sql(script(ids[-2],ids[-1],'upgrade'))
    assert original_rows()==before
    assert sql('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines()==ids
    sql("INSERT INTO ProductReviews (Id,OrderItemId,UserId,ProductId,ProductName,Stars,Content,CreatedAt) VALUES (2,2,1,1,'QA plant',5,'QA independent second purchase','2026-02-01')")
    assert sql('SELECT COUNT(*),AVG(Stars) FROM ProductReviews WHERE IsCurrent=1')=='2\t4.0000'
    assert sql('SELECT * FROM ProductReviews WHERE Id=1')==old_review
    after=original_rows();rollback=script(ids[-1],ids[-2],'rollback')
    try:
        sql(rollback)
        raise AssertionError('Unsafe uniqueness rollback unexpectedly succeeded')
    except subprocess.CalledProcessError:pass
    assert original_rows()==after and sql('SELECT * FROM ProductReviews WHERE Id=1')==old_review
    assert sql('SELECT DISTINCT NON_UNIQUE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='+gs.quote(schema)+" AND TABLE_NAME='ProductReviews' AND INDEX_NAME='IX_ProductReviews_UserId_CurrentProductId'")=='1'
    assert sql('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines()==ids
    record('migration-upgrade',{'status':'PASS','database':schema,'migrationIds':ids,'checks':'9→10 preserves every original row/column/photo/reply; second completed purchase has independent current review; unsafe Down fails before changing indexes or data; Main untouched'})
    print('PASS: QA 9→10 preserves all history, images and replies; second-order review works; unsafe downgrade refuses without data/index loss.',flush=True)

def release_rehearsal():
    """Read-only Main backup; restore/upgrade/rollback exclusively in a fresh isolated QA."""
    import tarfile,re
    from qa_support import guard
    if not (OUT/'compose.yaml').exists(): prepare()
    backup_info=PRIVATE/'release-backup.json'
    assert not backup_info.exists(), 'Never overwrite an earlier backup; use a fresh QA directory'
    progress=PRIVATE/'release-backup-progress.json'
    backup=Path(json.loads(progress.read_text())['path']) if progress.exists() else ROOT/'backups'/('release-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3))
    backup.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(backup.parent,0o700)
    if not progress.exists():record('release-backup-progress',{'path':str(backup)})
    assert run(['git','check-ignore',str(backup/'db.sql')]).returncode==0
    before=table_hashes(MAIN_SQL)
    columns={t:[r.split('\t')[0] for r in MAIN_SQL('SHOW COLUMNS FROM `'+t+'`').splitlines()] for t in before}
    def old_hashes(sql):
        result={}
        for t,names in columns.items():
            assert all(re.fullmatch(r'[A-Za-z0-9_]+',n) for n in [t,*names])
            where=" WHERE MigrationId IN ("+','.join(gs.quote(m) for m in json.loads((PRIVATE/'baseline.json').read_text())['migrations'])+")" if t=='__EFMigrationsHistory' else ''
            rows=sorted(sql('SELECT '+','.join('`'+n+'`' for n in names)+' FROM `'+t+'`'+where).splitlines())
            result[t]=hashlib.sha256('\n'.join(rows).encode()).hexdigest()
        return result
    original=old_hashes(MAIN_SQL)
    def capture(name,command):
        path=backup/name
        if path.exists():assert path.stat().st_size>0;return
        with path.open('xb') as output:
            os.chmod(path,0o600)
            result=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.PIPE)
        assert result.returncode==0, 'Backup command failed; private files retained'
    capture('db.sql',['docker','compose','exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --quick --routines --triggers --events --hex-blob --no-tablespaces --set-gtid-purged=OFF --default-character-set=utf8mb4 greenshop'])
    capture('uploads-keys.tar',['docker','compose','exec','-T','web_app','tar','-cf','-','-C','/app','wwwroot/uploads/products','keys'])
    if not (backup/'tls.tar').exists():
        with tarfile.open(backup/'tls.tar','x') as archive:
            os.chmod(backup/'tls.tar',0o600)
            for path in (ROOT/'nginx/ssl').iterdir():
                if path.is_file():archive.add(path,arcname=path.name)
    if not (backup/'server.env').exists():shutil.copyfile(ROOT/'.env',backup/'server.env');os.chmod(backup/'server.env',0o600)
    current_id=MAIN_COMPOSE('ps','-q','web_app');old_image=json.loads(run(['docker','inspect',current_id]).stdout)[0]['Image']
    capture('runtime-image.tar',['docker','image','save',old_image])
    with tarfile.open(backup/'runtime-image.tar') as archive:
        manifest=json.load(archive.extractfile('manifest.json'))
        if 'index.json' in archive.getnames():
            index=json.load(archive.extractfile('index.json'))
            assert any(m['digest']==old_image for m in index['manifests'])
            for member in archive:
                if member.isfile() and member.name.startswith('blobs/sha256/'):
                    assert hashlib.sha256(archive.extractfile(member).read()).hexdigest()==Path(member.name).name
        else:assert Path(manifest[0]['Config']).name.removesuffix('.json')==old_image.removeprefix('sha256:')
    for name in ('uploads-keys.tar','tls.tar'):
        with tarfile.open(backup/name) as archive:
            for member in archive:
                assert not member.name.startswith('/') and '..' not in Path(member.name).parts and not member.issym() and not member.islnk()
                if member.isfile():
                    data=archive.extractfile(member).read();assert len(data)==member.size
    assert (backup/'db.sql').stat().st_size>0 and before==table_hashes(MAIN_SQL) and original==old_hashes(MAIN_SQL), 'Main changed during online snapshot; do not deploy with this backup'
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.iterdir() if p.is_file()}
    record('release-backup',{'path':str(backup),'sha256':hashes,'image':old_image,'originalColumns':columns,'originalRows':original})
    (backup/'sha256.json').write_text(json.dumps(hashes,indent=2));os.chmod(backup/'sha256.json',0o600)
    print('PASS: Private MySQL/uploads/Data Protection/TLS/env/runtime backups, archive checks and checksums; stable Main snapshot.',flush=True)
    om.qa_compose('up','-d','--wait','db');guard(om.qa_compose,MAIN_COMPOSE,database_only=True)
    def sql(query):
        return om.qa_compose('exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B --default-character-set=utf8mb4 "$MYSQL_DATABASE"',input=query)
    assert sql('SELECT DATABASE()')=='greenshop_order_qa' and sql('SHOW TABLES')==''
    # Restore only the named source schema's tables, into the independently authenticated QA schema.
    sql((backup/'db.sql').read_text());assert original==old_hashes(sql)
    configuration=json.loads((OUT/'compose.yaml').read_text());new_image=configuration['services']['web_app']['image']
    build=configuration['services']['web_app'].pop('build',None);configuration['services']['web_app']['image']=old_image
    (OUT/'compose.yaml').write_text(json.dumps(configuration,indent=2))
    with (backup/'uploads-keys.tar').open('rb') as archive:
        result=subprocess.run(['docker','compose','-p',PROJECT,'-f',str(OUT/'compose.yaml'),'--env-file',str(OUT/'qa.env'),'run','--rm','--no-deps','-T','--entrypoint','sh','web_app','-c','tar -xf - -C /app'],cwd=ROOT,stdin=archive,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert result.returncode==0
    om.qa_compose('up','-d','--wait','--no-build');guard(om.qa_compose,MAIN_COMPOSE)
    original_ids=json.loads((PRIVATE/'baseline.json').read_text())['migrations']
    assert sql('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines()==original_ids and original==old_hashes(sql)
    gs.BASE=om.QA_BASE;assert gs.request(gs.client(),'/health/ready')[0]==200
    old_uploads=om.qa_compose('exec','-T','web_app','sh','-c','find /app/wwwroot/uploads/products /app/keys -type f -exec sha256sum {} +')
    print('PASS: Genuine Main runtime boots on restored QA DB/uploads/keys with original migration IDs and every original row.',flush=True)
    configuration['services']['web_app']['image']=new_image
    if build:configuration['services']['web_app']['build']=build
    (OUT/'compose.yaml').write_text(json.dumps(configuration,indent=2))
    om.qa_compose('build','web_app');om.qa_compose('up','-d','--no-deps','--no-build','--force-recreate','--wait','web_app')
    guard(om.qa_compose,MAIN_COMPOSE);verify_migrations(sql);verify_schema(sql)
    assert original==old_hashes(sql)
    assert set(old_uploads.splitlines()).issubset(set(om.qa_compose('exec','-T','web_app','sh','-c','find /app/wwwroot/uploads/products /app/keys -type f -exec sha256sum {} +').splitlines()))
    for _ in range(20):
        if gs.request(gs.client(),'/health/ready')[0]==200:break
        time.sleep(1)
    else:raise AssertionError('New runtime did not recover through unchanged QA Nginx')
    # Exercise a backup restore after upgrade in another QA-only schema. Never downgrade or drop Main.
    restore_schema='greenshop_restore_qa_'+secrets.token_hex(5)
    sql('CREATE DATABASE `'+restore_schema+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    def restored_sql(query):
        return om.qa_compose('exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B --default-character-set=utf8mb4 '+restore_schema,input=query)
    restored_sql((backup/'db.sql').read_text());assert original==old_hashes(restored_sql)
    assert restored_sql('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId')==MAIN_SQL('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId')
    for name,digest in hashes.items():assert hashlib.sha256((backup/name).read_bytes()).hexdigest()==digest
    preservation()
    record('release-rehearsal',{'status':'PASS','backup':str(backup),'originalMigrations':original_ids,'targetMigrations':expected_migrations(),'checks':['Verified online Main snapshot and image archive','Original runtime boots from isolated restored DB/uploads/keys','New runtime upgrades restored copy; all original columns/rows/uploads/keys preserved','Independent post-upgrade restore reproduces original backup schema/rows','QA-only ports/credentials/volumes; Main containers and all hashes unchanged'],'mainChanged':False})
    print('PASS: Restored Main clone upgrades '+str(len(original_ids))+'→'+str(len(expected_migrations()))+' without losing original columns/rows; independent rollback restore reproduces backup. Main unchanged.',flush=True)

if __name__=='__main__':
    {'release-rehearsal':release_rehearsal,'baseline':baseline,'migration':migration_upgrade,'prepare':prepare,'certificates':certificates,'cold':cold,'regression':regression,'resilience':resilience,'browser-evidence':browser_evidence,'preservation':preservation,'main':main,'teardown':om.teardown}[sys.argv[1]]()
