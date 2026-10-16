"""Controlled QA outages and rollback rehearsal. No Main service is stopped."""
from pathlib import Path
import importlib.util,json,time,sys,requests
R=Path('/home/trung/GreenShop-Official') if Path(__file__).parent==Path('/tmp') else Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('m2',R/'tests/monitoring/acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.PROJECT=='greenshop-m2-qa'
def states():
 return {r['name']:r for g in m.graf('/api/prometheus/grafana/api/v1/rules')['data']['groups'] for r in g['rules']}
def faults():
 evidence={}
 m.dc('stop','web_app')
 try:
  evidence['web_down']=m.wait_for(lambda:(r if (r:=states()['GreenShopWebDown'])['state']=='firing' else None),90)
 finally:m.dc('start','--wait','--wait-timeout','120','web_app')
 m.wait_for(lambda:states()['GreenShopWebDown']['state']=='inactive',90)
 m.dc('stop','db')
 try:
  assert requests.get(m.BASE+'/health/ready',verify=False,timeout=30).status_code==503
  evidence['mysql_down']=m.wait_for(lambda:(r if (r:=states()['GreenShopMySQLDown'])['state']=='firing' else None),90)
  # Actual readiness failures create real 503 responses, no synthetic metric injection.
  started=time.monotonic()
  while time.monotonic()-started<150:
   assert requests.get(m.BASE+'/health/ready',verify=False,timeout=30).status_code==503
   r=states()['GreenShopHighHttp5xxRate']
   if r['state']=='firing':evidence['http_5xx']=r;break
   time.sleep(2)
  else:raise AssertionError('5xx ratio did not fire')
 finally:m.dc('start','--wait','--wait-timeout','120','db')
 m.wait_for(lambda:requests.get(m.BASE+'/health/ready',verify=False,timeout=20).status_code==200,90)
 m.wait_for(lambda:states()['GreenShopMySQLDown']['state']=='inactive',90)
 for _ in range(80):requests.get(m.BASE+'/health/ready',verify=False,timeout=10)
 m.wait_for(lambda:states()['GreenShopHighHttp5xxRate']['state']=='inactive',200)
 m.record('availability-alerts',{'status':'PASS','time':m.now(),'method':'Only QA web stopped / restored; only QA MySQL stopped / restored. Real HTTP 503 readiness requests drove error-rate rule.','firing_rules':evidence,'recovery':'all three back to inactive'})
 print('PASS: real QA web-down, MySQL-down and HTTP 5xx alerts fire and recover.',flush=True)
def rollback():
 before=m.sql(m.qa_name('db'),'SELECT COUNT(*) FROM Users',db='greenshop_m2_qa')
 config=json.loads((m.QA/'compose.json').read_text());web=config['services']['web_app'];web.pop('build',None)
 original=json.loads(m.run(['docker','image','inspect','greenshop-m1-rollback:pre-m2']))[0]['Id'];web['image']=original
 file=m.QA/'rollback-rehearsal.json';file.write_text(json.dumps(config));file.chmod(0o600)
 try:
  m.run(['docker','compose','-p',m.PROJECT,'-f',str(file),'up','-d','--no-deps','--wait','--wait-timeout','180','web_app'])
  assert requests.get(m.BASE+'/health/ready',verify=False,timeout=20).status_code==200
  a=json.loads((m.QA/'accounts.json').read_text());s=requests.Session();assert m.login(s,*a['customer']).status_code==302
 finally:m.dc('up','-d','--no-deps','--wait','--wait-timeout','180','web_app')
 m.wait_for(lambda:m.scalar('up{job="greenshop"}')==1,50)
 assert m.sql(m.qa_name('db'),'SELECT COUNT(*) FROM Users',db='greenshop_m2_qa')==before
 m.record('rollback-rehearsal',{'status':'PASS','time':m.now(),'method':'QA web temporarily ran the exact existing Main M1 image, preserving QA DB/keys/uploads. HTTPS readiness and genuine Customer login passed; then tested M2 image restored.','user_count_unchanged':True})
 print('PASS: QA rollback to current Main image and return to M2, preserving data and authentication.',flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
