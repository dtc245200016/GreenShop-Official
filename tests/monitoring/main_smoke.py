"""Read-only Main verification. No Main customer or administrator authentication."""
import importlib.util,json,os,time,hashlib,requests
from pathlib import Path
R=Path('/home/trung/GreenShop-Official') if Path(__file__).parent==Path('/tmp') else Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('m2',R/'tests/monitoring/acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
before=json.loads((m.PRIVATE/'baseline.json').read_text());after=m.snapshot()
assert before['tables']==after['tables'],'Main table contents changed'
assert before['files']==after['files'],'Uploads or keys changed'
assert before['tls']==after['tls'],'TLS changed'
for n in ['greenshop_db','greenshop_phpmyadmin']:
 assert before['containers'][n]['id']==after['containers'][n]['id'],n+' recreated'
for n in before['containers']:assert after['containers'][n]['health']=='healthy',n
assert before['migrations']==after['migrations']
original=json.loads((m.PRIVATE/'main/before.json').read_text())
env=[v for v in m.inspect('greenshop_web')['Config']['Env'] if not v.startswith('Metrics__TokenFile=')]
assert hashlib.sha256('\n'.join(sorted(env)).encode()).hexdigest()==original['greenshop_web']['env_hash'],'Existing application environment changed'
pw=json.loads((m.PRIVATE/'main/passwords.json').read_text())
assert pw['grafana'] and pw['grafana']!='admin' # Operator may select a custom password.
def graf(path):
 r=requests.get('http://127.0.0.1:3000'+path,auth=('admin',pw['grafana']),timeout=20);r.raise_for_status();return r.json()
def query(expr):
 r=requests.get('http://127.0.0.1:9090/api/v1/query',params={'query':expr},timeout=20);r.raise_for_status();return r.json()['data']['result']
assert requests.get('http://127.0.0.1:3000/api/user',auth=('admin','admin'),timeout=10).status_code==401
assert requests.get('http://127.0.0.1:3000/api/search',timeout=10).status_code==401
assert graf('/api/datasources/uid/greenshop-prometheus/health')['status']=='OK'
assert len(graf('/api/search?type=dash-db'))==3
assert len(graf('/api/v1/provisioning/alert-rules'))==4
assert float(query('mysql_up')[0]['value'][1])==1
assert float(query('greenshop_auth_login_failures_total')[0]['value'][1])==0
panels=[]
for p in (R/'monitoring/grafana/dashboards').glob('*.json'):
 for panel in json.loads(p.read_text())['panels']:
  for t in panel.get('targets',[]):
   values=query(t['expr'].replace('$project',m.MAIN_PROJECT));assert values,panel['title']
   panels.append({'dashboard':p.stem,'panel':panel['title'],'series':len(values)})
for path in ['/metrics','/metrics/','/nginx_status']:
 assert requests.get('https://192.168.197.128'+path,verify=False,headers={'Authorization':'Bearer '+pw['metrics']},timeout=10).status_code==404
assert requests.get('http://127.0.0.1:5000/metrics',timeout=10).status_code==404
grants=m.sql('greenshop_db',"SHOW GRANTS FOR 'greenshop_exporter'@'%'")
assert 'PROCESS' in grants and 'SELECT' not in grants and 'ALL PRIVILEGES' not in grants
rules=[{'name':r['name'],'state':r['state'],'health':r.get('health')} for g in graf('/api/prometheus/grafana/api/v1/rules')['data']['groups'] for r in g['rules']]
assert all(r['state']=='inactive' and r['health']=='ok' for r in rules),rules
m.record('main-postdeploy-verification',{'status':'PASS','time':m.now(),'application_table_hashes_unchanged':True,'uploads_keys_tls_unchanged':True,'migration_ids_unchanged':True,'existing_application_environment_unchanged':True,'database_phpmyadmin_container_ids_unchanged':True,'all_Main_services_healthy':True,'grafana_auth':'UI login checked below, default password rejected, anonymous API rejected','mysql_exporter_grants':grants.splitlines(),'public_metrics':'404 even with valid token; direct app port without token 404','rules':rules,'panels':panels,'Main_customer_admin_login':'NOT TESTED: no credentials; no Main application accounts created or modified'})

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE'))
 c=b.new_context(viewport={'width':1600,'height':2250});page=c.new_page()
 page.goto('http://127.0.0.1:3000/login');page.locator('input[name="user"]').fill('admin');page.locator('input[name="password"]').fill(pw['grafana']);page.get_by_role('button',name='Log in',exact=True).click();page.wait_for_timeout(3000)
 for name in ['infrastructure','application','security']:
  page.goto('http://127.0.0.1:3000/d/greenshop-'+name+'?var-project='+m.MAIN_PROJECT)
  page.get_by_text('Overall Service Status' if name=='infrastructure' else 'HTTP Requests Per Second' if name=='application' else 'Failed Login Attempts — process lifetime',exact=True).wait_for(timeout=30000)
  page.wait_for_timeout(5000);page.screenshot(path=str(m.EVIDENCE/('main-grafana-'+name+'.png')),full_page=True)
 page.goto('http://127.0.0.1:9090/targets');page.wait_for_timeout(3000);page.screenshot(path=str(m.EVIDENCE/'main-prometheus-targets.png'),full_page=True)
 b.close()
m.record('main-grafana-ui',{'status':'PASS','time':m.now(),'method':'Actual Chromium form login with locally mounted random secret; three real Main dashboards rendered; screenshots captured.'})
print('PASS: Main data/environment/TLS preserved; all panels have real Main data; rules Normal; protected metrics; genuine Grafana UI login.',flush=True)
