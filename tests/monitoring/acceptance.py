"""GreenShop M2 isolated acceptance runner; private material never enters Git.

Usage: python tests/monitoring/acceptance.py prepare|backup|start|verify|incident|screenshots|preservation
The QA project is intentionally separate from the audited Main project.
"""
import os,sys,json,subprocess,secrets,time,hashlib,tarfile,re,ssl
from pathlib import Path
from datetime import datetime,timezone
import requests,yaml,html

ROOT=Path('/home/trung/GreenShop-Official') if Path(__file__).parent==Path('/tmp') else Path(__file__).resolve().parents[2]
PRIVATE=Path(os.environ.get('GREENSHOP_M2_PRIVATE',str(Path.home()/'.local/share/greenshop-monitoring')))
PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)
QA=PRIVATE/'qa';QA.mkdir(mode=0o700,exist_ok=True)
EVIDENCE=ROOT/'docs/evidence/commit2'
PROJECT='greenshop-m2-qa'
MAIN_PROJECT='dtc245200016_btl_tkqt_htpm'
BASE='https://localhost:21543'
PROM='http://127.0.0.1:21990'
GRAF='http://127.0.0.1:21300'
requests.packages.urllib3.disable_warnings()
def now():return datetime.now(timezone.utc).isoformat()
def run(cmd,**kw):
 p=subprocess.run(cmd,cwd=ROOT,capture_output=True,**kw)
 if p.returncode:raise RuntimeError('Command failed: '+str(cmd[:3])+'; see private command-error.txt')
 return p.stdout
def dc(*args,**kw):return run(['docker','compose','-p',PROJECT,'-f',str(QA/'compose.json'),*args],**kw)
def inspect(name):return json.loads(run(['docker','inspect',name]))[0]
def private(name,data):
 p=PRIVATE/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 p.write_text(json.dumps(data,indent=2));p.chmod(0o600)
def record(name,data):
 EVIDENCE.mkdir(parents=True,exist_ok=True)
 (EVIDENCE/(name+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def sql(container,query,db='greenshop',user='root',password_env='MYSQL_ROOT_PASSWORD'):
 assert re.fullmatch(r'[A-Za-z0-9_]+',db)
 return run(['docker','exec','-i',container,'sh','-c',f'MYSQL_PWD="${password_env}" exec mysql -u{user} -N -B --default-character-set=utf8mb4 '+db],input=query.encode()).decode().strip()
def qa_name(service):return dc('ps','-q',service).decode().strip()
def snapshot():
 db=inspect('greenshop_db');assert db['Config']['Labels']['com.docker.compose.project']==MAIN_PROJECT
 tables=sql('greenshop_db','SHOW TABLES').splitlines()
 hashes={t:hashlib.sha256(sql('greenshop_db','SELECT * FROM `'+t+'` ORDER BY '+ ('MigrationId' if t=='__EFMigrationsHistory' else '1')).encode()).hexdigest() for t in tables}
 files=run(['docker','exec','greenshop_web','sh','-c','find /app/keys /app/wwwroot/uploads/products -type f -exec sha256sum {} +']).decode().splitlines()
 nginx=inspect('nginx_server')
 tls=run(['docker','exec','nginx_server','sh','-c','sha256sum /etc/nginx/ssl/*']).decode().splitlines()
 return {'timestamp':now(),'tables':hashes,'files':sorted(files),'tls':sorted(tls),'migrations':sql('greenshop_db','SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines(),'containers':{n:{'id':inspect(n)['Id'],'image':inspect(n)['Image'],'mounts':inspect(n)['Mounts'],'health':inspect(n)['State']['Health']['Status']} for n in ['greenshop_db','greenshop_web','nginx_server','greenshop_phpmyadmin']}}
def prepare():
 assert not (QA/'compose.json').exists(),'Refuse to overwrite a QA deployment; use its existing configuration.'
 private('baseline.json',snapshot())
 s=QA/'secrets';s.mkdir(mode=0o700)
 pw={k:secrets.token_hex(32) for k in ['root','app','exporter','grafana','metrics']}
 private('qa/passwords.json',pw)
 for n,v in [('metrics-token',pw['metrics']),('grafana-password',pw['grafana']),('mysql-exporter.cnf','[client]\nuser=greenshop_exporter\npassword='+pw['exporter']+'\n')]:
  p=s/n;p.write_text(v);p.chmod(0o444) # Parent is 0700; readable only through explicit container secret mounts.
 env=dict(os.environ,MYSQL_ROOT_PASSWORD=pw['root'],MYSQL_APP_PASSWORD=pw['app'],MONITORING_SECRETS_DIR=str(s))
 c=json.loads(run(['docker','compose','--profile','monitoring','--profile','qa','config','--format','json'],env=env))
 sv=c['services']
 for name,v in sv.items():
  v.pop('container_name',None);v.pop('profiles',None)
  # Deterministic container names remain scoped to QA.
  v['restart']='unless-stopped'
 sv['db']['ports']=[]
 sv['db']['environment']['MYSQL_DATABASE']='greenshop_m2_qa'
 sv['db']['networks']={'database_net':None}
 sv['web_app']['environment']['ConnectionStrings__DefaultConnection']='Server=db;Database=greenshop_m2_qa;Uid=greenshop_app;Pwd='+pw['app']+';'
 sv['web_app']['networks']={'app_net':None,'database_net':None,'monitoring_net':None}
 sv['web_app']['ports']=[]
 sv['web_app']['image']='greenshop-m2-web:qa'
 sv['mysql-exporter']['networks']={'database_net':None,'monitoring_net':None}
 sv['phpmyadmin']['networks']={'database_net':None}
 sv['phpmyadmin']['ports']=[]
 sv['nginx']['ports']=[{'host_ip':'127.0.0.1','target':443,'published':'21543','protocol':'tcp'}]
 sv['prometheus']['ports']=[{'host_ip':'127.0.0.1','target':9090,'published':'21990','protocol':'tcp'}]
 sv['grafana']['ports']=[{'host_ip':'127.0.0.1','target':3000,'published':'21300','protocol':'tcp'}]
 sv['grafana']['environment']['GF_SERVER_ROOT_URL']='http://localhost:21300/'
 c['networks']['database_net']={'driver':'bridge','internal':True}
 # Do not copy or mount any Main key, upload or TLS material.
 (QA/'ssl').mkdir(mode=0o700)
 run(['bash','scripts/generate-dev-cert.sh','localhost','--output-dir',str(QA/'ssl')])
 conf=(ROOT/'nginx/default.conf').read_text().replace('proxy_set_header Host $host;','proxy_set_header Host $http_host;')
 (QA/'nginx.conf').write_text(conf)
 sv['nginx']['volumes']=[{'type':'bind','source':str(QA/'nginx.conf'),'target':'/etc/nginx/conf.d/default.conf','read_only':True},{'type':'bind','source':str(QA/'ssl'),'target':'/etc/nginx/ssl','read_only':True}]
 c.pop('name',None)
 for name,v in c['volumes'].items():v['name']=PROJECT+'_'+name
 for name,v in c['networks'].items():v['name']=PROJECT+'_'+name
 private('qa/compose.json',c)
 dc('config','--quiet')
 print('PASS: audited Main snapshot; separate QA secrets, DB, networks, volumes, keys and TLS.',flush=True)
def backup():
 assert not (PRIVATE/'backup').exists(),'Never overwrite a backup.'
 b=PRIVATE/'backup';b.mkdir(mode=0o700)
 with (b/'mysql.sql').open('wb') as f:
  p=subprocess.run(['docker','exec','greenshop_db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --routines --triggers --events --no-tablespaces --set-gtid-purged=OFF greenshop'],stdout=f,stderr=subprocess.PIPE)
  assert p.returncode==0
 for container,folder,name in [('greenshop_web','/app/keys','keys.tar'),('greenshop_web','/app/wwwroot/uploads/products','uploads.tar'),('nginx_server','/etc/nginx/ssl','tls.tar')]:
  with (b/name).open('wb') as f:
   p=subprocess.run(['docker','exec',container,'tar','cf','-','-C',folder,'.'],stdout=f,stderr=subprocess.PIPE);assert p.returncode==0
  with tarfile.open(b/name) as t:
   for member in t.getmembers():
    if member.isfile():assert len(t.extractfile(member).read())==member.size
 for p in b.iterdir():p.chmod(0o600)
 private('backup/manifest.json',{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in b.iterdir()})
 print('PASS: private consistent MySQL dump and readable keys/uploads/TLS archives; restore verification follows on isolated QA DB.',flush=True)
def start():
 p=subprocess.run(['docker','compose','-p',PROJECT,'-f',str(QA/'compose.json'),'build','web_app'],cwd=ROOT,stdout=(PRIVATE/'docker-build.txt').open('w'),stderr=subprocess.STDOUT)
 assert p.returncode==0,'Build failed; see private docker-build.txt'
 dc('up','-d','--wait','--wait-timeout','240','db')
 db=qa_name('db');assert db!=inspect('greenshop_db')['Id']
 # Verify restoration in a separate schema, without touching Main or the QA app schema.
 sql(db,'CREATE DATABASE greenshop_backup_verify;',db='greenshop_m2_qa')
 sql(db,(PRIVATE/'backup/mysql.sql').read_text(),db='greenshop_backup_verify')
 main=json.loads((PRIVATE/'baseline.json').read_text())
 restored={t:hashlib.sha256(sql(db,'SELECT * FROM `'+t+'` ORDER BY '+('MigrationId' if t=='__EFMigrationsHistory' else '1'),db='greenshop_backup_verify').encode()).hexdigest() for t in main['tables']}
 assert restored==main['tables'],'Backup restore row hashes differ'
 record('backup-verification',{'status':'PASS','time':now(),'mysql':'Restored into isolated greenshop_backup_verify schema; all table hashes match Main snapshot.','archives':'All members readable; sizes verified. Backups private outside Git.'})
 pw=json.loads((QA/'passwords.json').read_text())
 sql(db,"CREATE USER 'greenshop_exporter'@'%' IDENTIFIED BY '"+pw['exporter']+"' WITH MAX_USER_CONNECTIONS 3; GRANT PROCESS ON *.* TO 'greenshop_exporter'@'%';",db='greenshop_m2_qa')
 dc('up','-d','--wait','--wait-timeout','240')
 print('PASS: QA stack started; MySQL backup restored and compared; exporter has PROCESS only, no application data grants.',flush=True)
def graf(path,**kw):
 pw=json.loads((QA/'passwords.json').read_text())['grafana']
 r=requests.get(GRAF+path,auth=('admin',pw),timeout=20,**kw);r.raise_for_status();return r.json()
def query(expr):
 r=requests.get(PROM+'/api/v1/query',params={'query':expr},timeout=20);r.raise_for_status();d=r.json();assert d['status']=='success';return d['data']['result']
def scalar(expr):
 result=query(expr);assert result,expr;return float(result[0]['value'][1])
def verify():
 for _ in range(24):
  t=requests.get(PROM+'/api/v1/targets',timeout=10).json()['data']['activeTargets']
  if len(t)==5 and all(x['health']=='up' for x in t):break
  time.sleep(5)
 record('prometheus-targets',{'timestamp':now(),'targets':[{k:x[k] for k in ['labels','health','lastError','lastScrape','scrapeUrl']} for x in t]})
 assert len(t)==5 and all(x['health']=='up' for x in t),'Target down, inspect evidence'
 assert scalar('mysql_up')==1 and scalar('nginx_up')==1
 assert scalar('greenshop_auth_login_failures_total')==0
 assert scalar('greenshop_auth_login_failures_last_60s')==0
 assert scalar('mysql_global_status_threads_connected')>=1
 assert query('mysql_global_status_queries')
 assert query('nginx_connections_active') and query('nginx_http_requests_total')
 assert query('container_cpu_usage_seconds_total{container_label_com_docker_compose_service!=""}')
 assert query('container_memory_working_set_bytes{container_label_com_docker_compose_service!=""}')
 assert query('container_network_receive_bytes_total{container_label_com_docker_compose_service!=""}')
 assert graf('/api/health')['database']=='ok'
 assert requests.get(GRAF+'/api/search',timeout=10).status_code==401
 weak=requests.get(GRAF+'/api/user',auth=('admin','admin'),timeout=10);assert weak.status_code==401
 dashboards=graf('/api/search?type=dash-db');assert len([d for d in dashboards if d['uid'].startswith('greenshop-')])==3
 assert graf('/api/datasources/uid/greenshop-prometheus/health')['status']=='OK'
 assert len(graf('/api/v1/provisioning/alert-rules'))==4
 for path in ['/metrics','/metrics/','/nginx_status']:
  assert requests.get(BASE+path,verify=False,timeout=10).status_code==404
 assert requests.get(BASE+'/health/ready',verify=False,timeout=10).status_code==200
 # Every dashboard expression must return a real series (histograms may need a rate warmup).
 panels=[]
 for p in (ROOT/'monitoring/grafana/dashboards').glob('*.json'):
  for panel in json.loads(p.read_text())['panels']:
   for target in panel.get('targets',[]):
    result=query(target['expr'].replace('$project','.*'));panels.append({'dashboard':p.stem,'panel':panel['title'],'series':len(result)});assert result,panel['title']
 record('runtime-verification',{'status':'PASS','timestamp':now(),'checks':['five targets UP','actual application, container, nginx and MySQL metric families','Grafana auth rejects anonymous/default credentials','Prometheus datasource health OK','3 dashboards / 4 provisioned alerts','public metrics and stub_status blocked','QA readiness 200'],'panels':panels})
 print('PASS: metrics, targets, dashboards, datasource, Grafana auth and protected endpoints.',flush=True)
def alert_state():
 d=graf('/api/prometheus/grafana/api/v1/rules')
 for g in d['data']['groups']:
  for r in g['rules']:
   if r.get('name')=='GreenShopSuspiciousLoginFailures':return r
 raise AssertionError('Security rule missing')
def notifications():
 return json.loads(dc('exec','-T','qa-alert-receiver','python','-c','import urllib.request; print(urllib.request.urlopen("http://localhost:8080/notifications").read().decode())'))
def incidents(status):
 return [x for x in notifications() if any(a.get('labels',{}).get('incident')=='GS-SEC-001' and a.get('status')==status for a in x['payload'].get('alerts',[]))]
def wait_for(fn,timeout=110):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:value=fn()
  except requests.RequestException:value=None
  if value:return value
  time.sleep(2)
 raise AssertionError('Timed out waiting for real pipeline state')
def login(session,email,password,path='/Account/Login'):
 from html.parser import HTMLParser
 class Form(HTMLParser):
  token=''
  def handle_starttag(self,tag,attrs):
   a=dict(attrs)
   if tag=='input' and a.get('name')=='__RequestVerificationToken':self.token=a['value']
 r=session.get(BASE+path,verify=False,timeout=15);p=Form();p.feed(r.text);assert p.token
 return session.post(BASE+path,data={'Email':email,'Password':password,'__RequestVerificationToken':p.token},verify=False,allow_redirects=False,timeout=15)
def fixture():
 import bcrypt
 pw=secrets.token_urlsafe(24);admin=secrets.token_urlsafe(24)
 db=qa_name('db');assert inspect(db)['Config']['Labels']['com.docker.compose.project']==PROJECT
 assert sql(db,'SELECT DATABASE()',db='greenshop_m2_qa')=='greenshop_m2_qa'
 assert sql(db,'SELECT COUNT(*) FROM Users',db='greenshop_m2_qa')=='0','Use existing fixtures on repeat runs.'
 for role,email,password in [(0,'m2-customer@example.invalid',pw),(1,'m2-admin@example.invalid',admin)]:
  h=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
  sql(db,f"INSERT INTO Users (FullName,Email,PasswordHash,Phone,Role,CreatedAt,IsActive,Version,SessionVersion) VALUES ('M2 QA User','{email}','{h}','',{role},UTC_TIMESTAMP(6),1,0,0)",db='greenshop_m2_qa')
 private('qa/accounts.json',{'customer':['m2-customer@example.invalid',pw],'admin':['m2-admin@example.invalid',admin]})
 sql(db,"INSERT INTO Categories (Name,Description,IsActive) VALUES ('M2 QA Plants','Disposable QA',1); INSERT INTO Products (Name,Price,ImageUrl,Description,StockQuantity,CategoryId) VALUES ('M2 QA Plant',100000,'/images/product-placeholder.svg','Disposable QA plant',30,1)",db='greenshop_m2_qa')
def incident():
 test_started=now()
 if not (QA/'accounts.json').exists():fixture()
 a=json.loads((QA/'accounts.json').read_text());tests=[]
 s=requests.Session();initial=scalar('greenshop_auth_login_failures_total')
 # Authentication, authorization, validation and anti-CSRF regression before incidents.
 assert s.get(BASE+'/Admin/DonHang/QuanLyDonHang',verify=False,allow_redirects=False).status_code==302
 assert s.post(BASE+'/Account/Login',data={'Email':a['customer'][0],'Password':'wrong'},verify=False).status_code==400
 s.get(BASE+'/Account/Login',verify=False)
 # Form validation must not be counted as invalid credentials.
 assert login(s,'invalid-email','').status_code==200
 customer=requests.Session();assert login(customer,*a['customer']).status_code==302
 assert customer.get(BASE+'/Admin/DonHang/QuanLyDonHang',verify=False,allow_redirects=False).status_code==302
 admin=requests.Session();assert login(admin,*a['admin'],path='/Admin/Account/Login').status_code==302
 assert admin.get(BASE+'/Admin/DonHang/QuanLyDonHang',verify=False).status_code==200
 assert login(requests.Session(),*a['customer'],path='/Admin/Account/Login').status_code==200
 time.sleep(12);assert scalar('greenshop_auth_login_failures_total')==initial
 record('auth-regression',{'status':'PASS','time':now(),'checks':['GET login does not count','invalid form does not count','CSRF missing rejected 400','Customer/Admin valid sign-in','Customer cannot access Admin','wrong-role login denied without credential-failure increment'],'main_authenticated_tests':'NOT TESTED: no credentials; no Main account changes'})
 for n in [1,2]:
  wait_for(lambda: scalar('greenshop_auth_login_failures_last_60s')==0 and alert_state()['state']=='inactive')
  before=scalar('greenshop_auth_login_failures_total');normal=alert_state();start=now();start_m=time.monotonic();session=requests.Session()
  for _ in range(5):
   r=login(session,a['customer'][0],secrets.token_urlsafe(20));assert r.status_code==200 and 'không chính xác' in html.unescape(r.text)
  elapsed=time.monotonic()-start_m;assert elapsed<60
  wait_for(lambda:scalar('greenshop_auth_login_failures_total')==before+5,40)
  assert scalar('greenshop_auth_login_failures_last_60s')==5
  firing=wait_for(lambda:(v if (v:=alert_state())['state']=='firing' else None),50)
  received=wait_for(lambda:[x for x in incidents('firing') if x['received_at']>=start],45)
  record('incident-'+str(n)+'-firing',{'status':'PASS','run':n,'start':start,'elapsed_seconds':elapsed,'real_failed_logins':5,'counter_before':before,'counter_after':scalar('greenshop_auth_login_failures_total'),'rolling_count':scalar('greenshop_auth_login_failures_last_60s'),'normal_rule':normal,'firing_rule':firing,'notification':received[-1]})
  print(f'PASS: incident {n}: exactly 5 actual rejected logins, counter +5, Grafana FIRING, webhook received.',flush=True)
  if n==1:screenshots('firing')
  resolved=wait_for(lambda:(v if (v:=alert_state())['state']=='inactive' else None),110)
  recovery=wait_for(lambda:[x for x in incidents('resolved') if x['received_at']>=start],40)
  record('incident-'+str(n)+'-resolved',{'status':'PASS','time':now(),'rule':resolved,'rolling_count':scalar('greenshop_auth_login_failures_last_60s'),'notification':recovery[-1]})
  print(f'PASS: incident {n}: automatic recovery, resolved notification received.',flush=True)
  if n==1:screenshots('resolved')
 # Real security JSON events, whitelist fields only. Never export arbitrary application logs.
 logs=dc('logs','--since',test_started,'--no-log-prefix','web_app').decode();events=[]
 for line in logs.splitlines():
  try:d=json.loads(line)
  except ValueError:continue
  if d.get('EventId') in [2001,2002,2003]:events.append(d)
 assert len([e for e in events if e['EventId']==2001])==10
 record('security-events',{'status':'PASS','events':events})
 print('PASS: both runs repeatable; structured stdout contains exactly 10 credential-failure events.',flush=True)
def screenshots(state='normal'):
 from playwright.sync_api import sync_playwright
 pw=json.loads((QA/'passwords.json').read_text())['grafana']
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_EXECUTABLE"))
  context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1050})
  page=context.new_page();page.goto(GRAF+'/login');page.locator('input[name="user"]').fill('admin');page.locator('input[name="password"]').fill(pw);page.get_by_role('button',name='Log in',exact=True).click();page.wait_for_timeout(2500)
  if state=='normal':
   for name in ['infrastructure','application','security']:
    page.goto(GRAF+'/d/greenshop-'+name);page.wait_for_load_state('networkidle',timeout=30000);page.wait_for_timeout(1500);page.screenshot(path=str(EVIDENCE/('grafana-'+name+'.png')),full_page=True)
   page.goto(PROM+'/targets');page.wait_for_timeout(2500);page.screenshot(path=str(EVIDENCE/'prometheus-targets.png'),full_page=True)
  page.goto(GRAF+'/alerting/grafana/gs-sec-001/view');page.wait_for_timeout(2500);page.screenshot(path=str(EVIDENCE/('security-alert-'+state+'.png')),full_page=True)
  if state=='firing':
   page.goto(GRAF+'/d/greenshop-security');page.get_by_text('Failed Login Attempts — process lifetime',exact=True).wait_for(timeout=30000);page.wait_for_timeout(3000);page.screenshot(path=str(EVIDENCE/'grafana-security-firing.png'),full_page=True)
   # A real receiver response is displayed without fabricating a screenshot.
   info=inspect(qa_name('qa-alert-receiver'))
   address=info['NetworkSettings']['Networks'][PROJECT+'_monitoring_net']['IPAddress']
   page.goto('http://'+address+':8080/notifications');page.screenshot(path=str(EVIDENCE/'security-notification-received.png'),full_page=True)
  browser.close()
def preservation():
 before=json.loads((PRIVATE/'baseline.json').read_text());after=snapshot()
 assert before['tables']==after['tables'],'Main business tables changed'
 assert before['files']==after['files'] and before['tls']==after['tls']
 for name,old in before['containers'].items():
  current=after['containers'][name]
  assert old['id']==current['id'] and old['image']==current['image'],name+' identity changed'
  assert sorted(old['mounts'],key=lambda x:x['Destination'])==sorted(current['mounts'],key=lambda x:x['Destination']),name+' mounts changed'
  assert current['health']=='healthy',name+' health not ready'
 r=requests.get('https://192.168.197.128/health/ready',verify=False,timeout=15);assert r.status_code==200
 record('main-preservation',{'status':'PASS','time':now(),'checks':['Main tables unchanged by hash','uploads and Data Protection keys unchanged','TLS unchanged','all four Main container IDs/images/mounts unchanged','Main HTTPS ready 200'],'authenticated_main':'NOT TESTED; no credentials'})
 print('PASS: Main data, files, TLS, containers and HTTPS preserved.',flush=True)


def boundary():
 wait_for(lambda:scalar('greenshop_auth_login_failures_last_60s')==0 and alert_state()['state']=='inactive',120)
 a=json.loads((QA/'accounts.json').read_text());session=requests.Session()
 start=now();clock=time.monotonic();before=scalar('greenshop_auth_login_failures_total')
 for _ in range(4):
  r=login(session,a['customer'][0],secrets.token_urlsafe(20));assert r.status_code==200 and 'không chính xác' in html.unescape(r.text)
 wait_for(lambda:scalar('greenshop_auth_login_failures_last_60s')==4,25)
 time.sleep(12)
 four=alert_state();assert four['state']=='inactive'
 r=login(session,a['customer'][0],secrets.token_urlsafe(20));assert r.status_code==200
 elapsed=time.monotonic()-clock;assert elapsed<60
 wait_for(lambda:scalar('greenshop_auth_login_failures_total')==before+5,25)
 firing=wait_for(lambda:(r if (r:=alert_state())['state']=='firing' else None),30)
 received=wait_for(lambda:[x for x in incidents('firing') if x['received_at']>=start],20)
 record('threshold-boundary',{'status':'PASS','time':now(),'start':start,'seconds_to_fifth_rejection':elapsed,'four_failures_rule':four,'five_failures_rule':firing,'counter_delta':5,'notification':received[-1]})
 print('PASS: four real failures stay Normal; fifth within 60s causes Firing and notification.',flush=True)
 screenshots('firing')
 wait_for(lambda:alert_state()['state']=='inactive',110)
 wait_for(lambda:[x for x in incidents('resolved') if x['received_at']>=start],30)
 screenshots('resolved')
 print('PASS: threshold boundary recovery and real UI screenshots captured.',flush=True)

if __name__=='__main__':
 try:globals()[sys.argv[1]]()
 except Exception as ex:
  (PRIVATE/'command-error.txt').write_text(str(ex));print('FAILED:',type(ex).__name__,str(ex),flush=True);raise
