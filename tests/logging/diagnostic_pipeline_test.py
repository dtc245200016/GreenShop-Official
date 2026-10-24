"""Exercise the exact Promtail production stages with fake data, without sending fixtures to Loki.

Dry-run uses the pinned production binary. A loopback test receiver separately
returns 500 then 204 to test the real client's bounded retry, never production.
"""
import copy,datetime,hashlib,http.server,json,subprocess,tempfile,threading,time
from pathlib import Path
import yaml
R=Path(__file__).resolve().parents[2];E=R/'docs/evidence/commit3'
IMAGE='grafana/promtail:3.6.11@sha256:a761cb834cfaeee29745440d4884d6748f0a08d8f68928db1d707018c1dcfbe9'
CANARY='M3_FAKE_SECRET_DO_NOT_FORWARD_a91z'
T='2026-10-17T01:02:03.123Z';RID='0HNPBLA2Q4DMF:00000001';TRACE='602e253f0f538aff9d9e1243964e43b8'
def base():return {'Timestamp':T,'LogLevel':'Error','Category':'Microsoft.EntityFrameworkCore.Database.Connection','EventId':20004,'Message':CANARY,'State':{'password':CANARY,'{OriginalFormat}':CANARY},'Scopes':[{'TraceId':TRACE},{'RequestPath':'/health/ready?token='+CANARY,'RequestId':RID,'password':CANARY}]}
def auth(event,id):
 d=base();d.update(Category='GreenShop.Web.Services.Observability',EventId=id,LogLevel='Warning',State={'SecurityEvent':event,'password':CANARY});d['Scopes'].append({'event':event,'request_id':RID,'route':'authentication','reason_code':'invalid_credentials','incident':'GS-SEC-001','email':CANARY});return d
fixtures=[('database_failure',base()),('normal_information',dict(base(),Category='Microsoft.Hosting.Lifetime',EventId=0,LogLevel='Information')),('authentication_failure',auth('auth.login.failed',2001)),('authentication_success',auth('auth.login.succeeded',2002)),('access_denied',auth('auth.access.denied',2003)),('controlled_exception',dict(base(),Category='Microsoft.AspNetCore.Diagnostics.ExceptionHandlerMiddleware',EventId=1,Exception='System.InvalidOperationException: '+CANARY)),('query_exception',dict(base(),Category='Microsoft.EntityFrameworkCore.Query',EventId=10100,Exception='MySqlConnector.MySqlException (0x80004005): '+CANARY)),('missing_optional',{'Timestamp':T}),('malformed_inner','{'+CANARY),('non_object',CANARY),('nested_untrusted_scopes',dict(base(),Scopes=[CANARY,{'Nested':{'RequestId':CANARY,'Authorization':CANARY}},{'RequestId':RID,'RequestPath':'/Admin/'+CANARY},{'TraceId':TRACE}])),('malformed_outer',None),('duplicate_a',base()),('duplicate_b',base())]
# Business events must pass the same strict allowlist and secret stripping.
for event, event_id, category in [
 ('category.created',3001,'GreenShop.Web.Areas.Admin.Controllers.DanhMucController'),
 ('product.created',3002,'GreenShop.Web.Areas.Admin.Controllers.SanPhamController'),
 ('order.created',3003,'GreenShop.Web.Controllers.ThanhToanController')]:
 d=base();d.update(Category=category,EventId=event_id,LogLevel='Information',State={'BusinessEvent':event,'password':CANARY})
 d['Scopes'].append({'event':event,'reason_code':'committed','incident':'business','request_id':RID})
 fixtures.append((event,d))
# Attempt each secret class in every otherwise trusted structured field.
for key in ['Timestamp','Category','LogLevel','EventId','Exception']:
 d=base();d[key]=CANARY;fixtures.append(('untrusted_'+key,d))
d=auth(CANARY,2001);fixtures.append(('untrusted_event',d))
d=base();d['Scopes']=[{'event':'x','request_id':CANARY,'route':CANARY,'reason_code':CANARY,'incident':CANARY,'TraceId':CANARY,'RequestId':CANARY,'RequestPath':'/'+CANARY}];fixtures.append(('untrusted_scope_fields',d))
# Shapes that previously hid framework scopes must not break templating.
for name,scopes in [('scope_null',None),('scope_object',{'RequestId':RID}),('scope_nested',[{'nested':{'RequestId':RID}}])]:fixtures.append((name,dict(base(),Scopes=scopes)))
secret_kinds=['password','password_hash','Authorization','JWT','session_cookie','csrf_token','connection_string','Gemini_API_key','webhook','customer_email','customer_phone','customer_address','login_body','checkout_body','AI_chat','payment']
for kind in secret_kinds:
 d=base();d.update(Message=kind+':'+CANARY,Exception=kind+':'+CANARY,State={kind:CANARY});d['Scopes'].append({kind:CANARY});fixtures.append(('canary_'+kind,d))
config=yaml.safe_load((R/'monitoring/promtail/promtail.yml').read_text())
def config_for(service,directory):
 c=copy.deepcopy(config);c['positions']['filename']='/tmp/positions.yml';sc=c['scrape_configs'][0];sc.pop('file_sd_configs',None);sc.pop('syslog',None);sc.pop('relabel_configs',None);sc['static_configs']=[{'targets':['localhost'],'labels':{'service':service,'environment':'qa','source':'fixture'}}];c['server']['http_listen_port']=0;c['clients'][0]['url']='http://127.0.0.1:1/loki/api/v1/push';p=directory/'config.yml';p.write_text(yaml.safe_dump(c,sort_keys=False));p.chmod(0o644);return p,c
def command(path,network='none'):
 return ['docker','run','--rm','--network',network,'--user','10001:0','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=8m','--cap-drop','ALL','--security-opt','no-new-privileges','-i','-v',str(path)+':/etc/promtail/test.yml:ro',IMAGE,'-config.file=/etc/promtail/test.yml','-stdin']
def wrapped(d):return d if isinstance(d,str) else json.dumps(d)
def input_run(args,payload):
 # Promtail stdin can exit on EOF before the last asynchronous stage drains.
 # Keep stdin open briefly while communicate concurrently drains both output pipes.
 proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 stream=proc.stdin;proc.stdin=None
 def feed():
  try:stream.write(payload);stream.flush();time.sleep(1)
  finally:stream.close()
 feeder=threading.Thread(target=feed,daemon=True);feeder.start()
 out,err=proc.communicate(timeout=45);feeder.join(2)
 return subprocess.CompletedProcess(args,proc.returncode,out,err)
def dry(service,items,directory):
 p,_=config_for(service,directory);lines=[wrapped(d) if d is not None else '{'+CANARY for _,d in items];r=input_run(command(p)+['-dry-run'],('\n'.join(lines)+'\n').encode());assert r.returncode==0,r.stderr.decode()[-500:]
 output=[]
 for line in r.stdout.decode().splitlines():
  cols=line.split('\t',2)
  if len(cols)==3:output.append(json.loads(cols[2]))
 assert len(output)==len(items),(service,len(items),len(output))
 assert CANARY not in r.stdout.decode()+r.stderr.decode(),'Fake secret reached output'
 return output
with tempfile.TemporaryDirectory(prefix='greenshop-diagnostic-') as td:
 directory=Path(td);directory.chmod(0o755);app=dry('greenshop-web',fixtures,directory);by=dict(zip((n for n,_ in fixtures),app))
 assert by['database_failure']['diagnostic_code']=='db.connection.failed'
 assert by['database_failure']['diagnostic_message']=='Database connection failed.'
 assert by['database_failure']['request_id']==RID and by['database_failure']['trace_id']==TRACE and by['database_failure']['route']=='health'
 assert by['normal_information']['diagnostic_code']=='application.lifecycle'
 assert by['authentication_failure']['event']=='auth.login.failed' and by['authentication_failure']['incident']=='GS-SEC-001'
 assert by['authentication_success']['event']=='auth.login.succeeded'
 for event in ('category.created','product.created','order.created'):
  assert by[event]['event']==event and by[event]['reason_code']=='committed' and by[event]['incident']=='business'
 assert by['controlled_exception']['exception_type']=='System.InvalidOperationException'
 assert by['nested_untrusted_scopes']['request_id']==RID and by['nested_untrusted_scopes']['route']=='admin'
 assert by['malformed_inner']['diagnostic_code']==by['malformed_outer']['diagnostic_code']=='parse.unrecognized'
 assert by['duplicate_a']==by['duplicate_b'] # Pipeline intentionally preserves two input entries, not exactly-once deduplication.
 assert not any(set(d)&{'Message','State','Scopes','Exception','RequestPath','email','password'} for d in app)
 ng={'timestamp_utc':'2026-10-17T01:02:03+00:00','method':'GET','status':'404','duration':'0.003','route_group':'health','upstream_status':'404','upstream_time':'0.002','Authorization':CANARY,'query':CANARY}
 ngi=[('normal',ng),('malformed',CANARY)]+[(k,dict(ng,**{k:CANARY})) for k in ng if k not in ['Authorization','query']];ngout=dry('nginx',ngi,directory);assert ngout[0]['status']=='404'
 myout=dry('mysql',[('operational','2026-10-17T01:02:03.123Z 0 [ERROR] [MY-010001] [Server] '+CANARY),('malformed',CANARY)],directory);assert myout[0]['code']=='MY-010001'
 received=[]
 class Receiver(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   body=self.rfile.read(int(self.headers['Content-Length']));received.append({'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'path':self.path});self.send_response(500 if len(received)==1 else 204);self.send_header('Content-Length','0');self.end_headers()
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Receiver);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  p,c=config_for('greenshop-web',directory);c['clients'][0]['url']='http://127.0.0.1:'+str(server.server_port)+'/loki/api/v1/push';p.write_text(yaml.safe_dump(c,sort_keys=False));result=input_run(command(p,'host'),(wrapped(base())+'\n').encode())
  assert result.returncode==0,result.stderr.decode()[-500:]
  assert len(received)==2 and received[0]==received[1],received
  assert CANARY.encode() not in result.stdout+result.stderr
 finally:server.shutdown();server.server_close()
report={'status':'PASS','observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'image':IMAGE,'production_pipeline_sha256':hashlib.sha256((R/'monitoring/promtail/promtail.yml').read_bytes()).hexdigest(),'method':'Exact production stages with pinned Promtail stdin dry-run; isolated loopback fake receiver for actual HTTP retry. No fixture sent to production/QA Loki.','cases':[{'name':name,'status':'PASS'} for name,_ in fixtures],'nginx_cases':len(ngi),'mysql_cases':2,'secret_canary_classes':secret_kinds,'canary_disclosure':False,'framework_scope_sample':by['database_failure'],'controlled_exception_sample':by['controlled_exception'],'duplicate_behavior':'Two equal input records produce two equal sanitized records; no exactly-once guarantee.','retry_test':{'first_status':500,'second_status':204,'identical_payload_retried':True,'attempts':len(received),'accepted_batches':1},'limits':['Known-format IDs are bounded and never promoted to stream labels. This is not proof against all unknown secrets in a deliberately forged identifier.','Unknown categories/types use generic diagnostic templates; raw messages and stack traces remain private Docker logs.','Acknowledgement loss after Loki accepts a batch may still duplicate logs; bounded retries may lose data during long outage.']}
(E/'diagnostic-pipeline-tests.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS exact Promtail stages:',len(fixtures),'application cases,',len(ngi),'Nginx, 2 MySQL; canaries absent; real 500→204 retry verified')
