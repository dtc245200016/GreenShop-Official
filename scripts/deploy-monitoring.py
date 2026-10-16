"""Audited Main monitoring rollout. Never invokes Git or recreates MySQL/phpMyAdmin."""
import os,json,subprocess,secrets,sys,time,hashlib
from pathlib import Path
import requests,yaml
R=Path('/home/trung/GreenShop-Official')
P=Path.home()/'.local/share/greenshop-monitoring'
M=P/'main';M.mkdir(mode=0o700,exist_ok=True)
PROJECT='dtc245200016_btl_tkqt_htpm'
OLD=Path('/home/trung/DTC245200016_BTL_TKQT_HTPM')
def run(cmd,**kw):
 p=subprocess.run(cmd,cwd=kw.pop("cwd",R),capture_output=True,**kw)
 if p.returncode:
  (M/'command-error.txt').write_bytes(p.stderr);raise RuntimeError('Command failed; see private Main command-error.txt')
 return p.stdout
def info(n):return json.loads(run(['docker','inspect',n]))[0]
def save(path,obj):path.write_text(json.dumps(obj,indent=2));path.chmod(0o600)
def compose(file,*args):return run(['docker','compose','-p',PROJECT,'-f',str(file),*args])
def sql(q):return run(['docker','exec','-i','greenshop_db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B greenshop'],input=q.encode()).decode().strip()
def prepare():
 assert not (M/'compose.json').exists(),'Refuse to replace an audited rollout plan'
 for f in ['backup-verification.json','archive-verification.json','runtime-verification.json','incident-1-firing.json','incident-1-resolved.json','incident-2-firing.json','incident-2-resolved.json','business-regression.json','engagement-regression.json','mysql-exporter-privileges.json','persistence.json','main-preservation.json']:
  d=json.loads((R/'docs/evidence/commit2'/f).read_text());assert d['status']=='PASS',f
 baseline=json.loads((P/'baseline.json').read_text())
 ids={n:info(n)['Id'] for n in baseline['containers']}
 assert all(ids[n]==baseline['containers'][n]['id'] for n in ids)
 expected=sorted(p.name.removesuffix('.Designer.cs') for p in (R/'backend/GreenShop.Web/Migrations').glob('*.Designer.cs'))
 assert sql('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines()==expected,'Unexpected migrations'
 # Actual deployed configuration, with original env, mounts and project identity.
 original=json.loads(run(['docker','compose','-p',PROJECT,'-f',str(OLD/'docker-compose.yml'),'config','--format','json'],cwd=OLD))
 assert info('greenshop_db')['Config']['Labels']['com.docker.compose.project']==PROJECT
 rollback=json.loads(json.dumps(original))
 image=info('greenshop_web')['Image']
 run(['docker','tag',image,'greenshop-m1-rollback:pre-m2'])
 rollback['services']['web_app']['environment']=dict(v.split('=',1) for v in info('greenshop_web')['Config']['Env'] if '=' in v)
 rollback['services']['web_app'].pop('build',None);rollback['services']['web_app']['image']='greenshop-m1-rollback:pre-m2'
 save(M/'rollback.json',rollback)
 save(M/'before.json',{n:{'id':info(n)['Id'],'image':info(n)['Image'],'mounts':info(n)['Mounts'],'env_hash':hashlib.sha256('\n'.join(sorted(info(n)['Config']['Env'])).encode()).hexdigest()} for n in ids})
 s=M/'secrets';s.mkdir(mode=0o700,exist_ok=True)
 pw=json.loads((M/'passwords.json').read_text()) if (M/'passwords.json').exists() else {k:secrets.token_hex(32) for k in ['metrics','grafana','exporter']};save(M/'passwords.json',pw)
 for name,value in [('metrics-token',pw['metrics']),('grafana-password',pw['grafana']),('mysql-exporter.cnf','[client]\nuser=greenshop_exporter\npassword='+pw['exporter']+'\n')]:
  p=s/name
  if p.exists():assert p.read_text()==value,"Existing secret mismatch"
  else:p.write_text(value);p.chmod(0o444)
 env=dict(os.environ,MYSQL_ROOT_PASSWORD='configuration-validation-only',MYSQL_APP_PASSWORD='configuration-validation-only',MONITORING_SECRETS_DIR=str(s))
 source=json.loads(run(['docker','compose','--profile','monitoring','--profile','qa','config','--format','json'],env=env))
 c=original
 # Reuse exactly the application environment which is actually running, including AI settings.
 c['services']['web_app']['environment']=dict(v.split('=',1) for v in info('greenshop_web')['Config']['Env'] if '=' in v)
 c['services']['web_app']['environment']['Metrics__TokenFile']='/run/secrets/metrics_token'
 c['services']['web_app']['secrets']=[{'source':'metrics_token','target':'metrics_token'}]
 c['services']['web_app']['networks']['monitoring_net']=None
 c['services']['web_app'].pop('build',None);c['services']['web_app']['image']='greenshop-m2-web:release'
 run(['docker','tag','greenshop-m2-web:qa','greenshop-m2-web:release'])
 c['services']['nginx']['networks']['monitoring_net']=None
 for mount in c['services']['nginx']['volumes']:
  if mount['target']=='/etc/nginx/conf.d/default.conf':mount['source']=str(R/'nginx/default.conf')
 for name in ['prometheus','grafana','mysql-exporter','nginx-exporter','cadvisor','qa-alert-receiver']:
  c['services'][name]=source['services'][name];c['services'][name].pop('profiles',None)
  if name=='qa-alert-receiver':c['services'][name]['container_name']='greenshop-main-qa-alert-receiver'
 for name in ['monitoring_net','admin_net']:
  c['networks'][name]=source['networks'][name];c['networks'][name]['name']=PROJECT+'_'+name
 for name in ['prometheus_data','grafana_data']:
  c['volumes'][name]=source['volumes'][name];c['volumes'][name]['name']=PROJECT+'_'+name
 c['secrets']=source['secrets'];c['name']=PROJECT
 for target,name in [('/var/lib/mysql','mysql_data'),('/app/keys','data_protection_keys'),('/app/wwwroot/uploads/products','product_images')]:
  container=info('greenshop_db' if target=='/var/lib/mysql' else 'greenshop_web')
  actual=next(x['Name'] for x in container['Mounts'] if x['Destination']==target)
  assert c['volumes'][name]['name']==actual,(target,actual)
 save(M/'compose.json',c);compose(M/'compose.json','config','--quiet')
 print('PASS: concrete Main/rollback plans preserve exact project, MySQL/upload/key volumes, TLS and running app environment.',flush=True)
def deploy():
 assert (M/'compose.json').exists() and (M/'rollback.json').exists()
 # Dedicated monitoring account only; never alters application accounts/passwords.
 pw=json.loads((M/'passwords.json').read_text())
 assert sql("SELECT COUNT(*) FROM mysql.user WHERE User='greenshop_exporter'")=='0','Existing exporter account requires separate audit'
 sql("CREATE USER 'greenshop_exporter'@'%' IDENTIFIED BY '"+pw['exporter']+"' WITH MAX_USER_CONNECTIONS 3; GRANT PROCESS ON *.* TO 'greenshop_exporter'@'%';")
 try:
  compose(M/'compose.json','up','-d','--no-deps','--wait','--wait-timeout','180','web_app')
  compose(M/'compose.json','up','-d','--no-deps','--wait','--wait-timeout','90','nginx')
  compose(M/'compose.json','up','-d','--no-deps','--wait','--wait-timeout','180','prometheus','grafana','mysql-exporter','nginx-exporter','cadvisor','qa-alert-receiver')
  run(['docker','exec','nginx_server','nginx','-t'])
  before=json.loads((M/'before.json').read_text())
  assert all(info(n)['Id']==before[n]['id'] for n in ['greenshop_db','greenshop_phpmyadmin'])
  requests.packages.urllib3.disable_warnings()
  for path in ['/','/health/ready','/SanPham/CuaHang','/Account/Login','/Admin/Account/Login']:
   assert requests.get('https://192.168.197.128'+path,verify=False,timeout=20).status_code==200,path
  for path in ['/metrics','/metrics/','/nginx_status']:
   assert requests.get('https://192.168.197.128'+path,verify=False,timeout=10).status_code==404,path
  for _ in range(20):
   targets=requests.get('http://127.0.0.1:9090/api/v1/targets',timeout=10).json()['data']['activeTargets']
   if len(targets)==5 and all(t['health']=='up' for t in targets):break
   time.sleep(5)
  assert all(t['health']=='up' for t in targets) and len(targets)==5
  for path in ['/api/search?type=dash-db','/api/v1/provisioning/alert-rules','/api/datasources/uid/greenshop-prometheus/health']:
   r=requests.get('http://127.0.0.1:3000'+path,auth=('admin',pw['grafana']),timeout=20);assert r.status_code==200,path
  evidence={'status':'PASS','time':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'project':PROJECT,'database_container_unchanged':True,'phpmyadmin_container_unchanged':True,'targets':[{'labels':t['labels'],'health':t['health'],'lastScrape':t['lastScrape']} for t in targets],'smoke':'HTTPS, database readiness, product browsing, login pages PASS; public metrics/stub_status 404','authenticated_main':'NOT TESTED: no credentials; no application accounts changed','ports':'Grafana 127.0.0.1:3000, Prometheus 127.0.0.1:9090; exporters and internal QA sink unpublished'}
  (R/'docs/evidence/commit2/main-deployment.json').write_text(json.dumps(evidence,indent=2)+'\n')
  print('PASS: Main monitoring deployed; all five targets UP; original DB/phpMyAdmin preserved; HTTPS and protected endpoints PASS.',flush=True)
 except Exception:
  compose(M/'rollback.json','up','-d','--no-deps','--wait','--wait-timeout','180','web_app','nginx')
  print('Main smoke failed; original web/Nginx configuration restored under same project. Inspect private error.',flush=True)
  raise
if __name__=='__main__':globals()[sys.argv[1]]()
