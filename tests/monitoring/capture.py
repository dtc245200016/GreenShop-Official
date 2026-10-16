"""Real QA event and preloaded browser: capture rendered panels while the rule is firing."""
import importlib.util,json,os,time,secrets,requests
from pathlib import Path
from playwright.sync_api import sync_playwright
R=Path('/home/trung/GreenShop-Official') if Path(__file__).parent==Path('/tmp') else Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('m2',R/'tests/monitoring/acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
credentials=json.loads((m.QA/'accounts.json').read_text())
pw=json.loads((m.QA/'passwords.json').read_text())['grafana']
m.wait_for(lambda:m.scalar('greenshop_auth_login_failures_last_60s')==0 and m.alert_state()['state']=='inactive')
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE'))
 c=b.new_context(viewport={'width':1600,'height':2000});page=c.new_page()
 page.goto(m.GRAF+'/login');page.locator('input[name="user"]').fill('admin');page.locator('input[name="password"]').fill(pw);page.get_by_role('button',name='Log in',exact=True).click();page.wait_for_timeout(3000)
 page.goto(m.GRAF+'/d/greenshop-security?refresh=5s');page.get_by_text('Failed Login Attempts — process lifetime',exact=True).wait_for()
 page.wait_for_load_state('networkidle',timeout=30000)
 page.get_by_text('0',exact=True).first.wait_for(timeout=30000)
 session=requests.Session();start=m.now();before=m.scalar('greenshop_auth_login_failures_total');t=time.monotonic()
 for _ in range(5):assert m.login(session,credentials['customer'][0],secrets.token_urlsafe(20)).status_code==200
 elapsed=time.monotonic()-t;assert elapsed<60
 m.wait_for(lambda:m.scalar('greenshop_auth_login_failures_total')==before+5,30)
 m.wait_for(lambda:m.alert_state()['state']=='firing',40)
 notification=m.wait_for(lambda:[x for x in m.incidents('firing') if x['received_at']>=start],20)
 page.reload();page.wait_for_load_state('networkidle',timeout=25000)
 page.get_by_text('5',exact=True).first.wait_for(timeout=20000)
 page.screenshot(path=str(m.EVIDENCE/'grafana-security-firing.png'),full_page=True)
 page.goto(m.GRAF+'/alerting/grafana/gs-sec-001/view');page.wait_for_load_state('networkidle',timeout=20000)
 assert 'Firing' in page.locator('body').inner_text()
 page.screenshot(path=str(m.EVIDENCE/'security-alert-firing.png'),full_page=True)
 info=m.inspect(m.qa_name('qa-alert-receiver'));address=info['NetworkSettings']['Networks'][m.PROJECT+'_monitoring_net']['IPAddress']
 page.goto('http://'+address+':8080/notifications');page.screenshot(path=str(m.EVIDENCE/'security-notification-received.png'),full_page=True)
 m.record('live-capture',{'status':'PASS','start':start,'seconds_for_5_rejections':elapsed,'counter_before':before,'counter_after':before+5,'window':5,'notification':notification[-1],'method':'Preloaded real Grafana browser; waited for data queries and visible value 5. Direct receiver /notifications screenshot. No UI mocking or metric injection.'})
 print('PASS: rendered Security Dashboard shows real 5, rule Firing and receiver payload captured.',flush=True)
 m.wait_for(lambda:m.alert_state()['state']=='inactive',110)
 m.wait_for(lambda:[x for x in m.incidents('resolved') if x['received_at']>=start],30)
 page.goto(m.GRAF+'/alerting/grafana/gs-sec-001/view');page.wait_for_load_state('networkidle',timeout=20000)
 page.screenshot(path=str(m.EVIDENCE/'security-alert-resolved.png'),full_page=True)
 b.close()
print('PASS: live capture cycle automatically resolved.',flush=True)
