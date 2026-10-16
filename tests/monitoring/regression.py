"""Additional real QA regression and persistence. All writes are guarded synthetic QA."""
import importlib.util,sys,os,json,time,hashlib,subprocess,tarfile
from pathlib import Path
import requests
R=Path('/home/trung/GreenShop-Official') if Path(__file__).parent==Path('/tmp') else Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('m2',R/'tests/monitoring/acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def regression():
 sys.path.insert(0,str(R/'tests'));import storefront_regression as gs
 gs.BASE=m.BASE;gs.REPORTS=m.QA/'storefront';gs.REPORTS.mkdir(exist_ok=True)
 db=m.qa_name('db');assert m.inspect(db)['Config']['Labels']['com.docker.compose.project']==m.PROJECT
 gs.sql=lambda q:m.sql(db,q,db='greenshop_m2_qa')
 accounts=json.loads((m.QA/'accounts.json').read_text())
 operator=gs.client();page=gs.get(operator,'/Admin/Account/Login')[0]
 assert gs.post(operator,'/Admin/Account/Login',page,{'Email':accounts['admin'][0],'Password':accounts['admin'][1]})[0]==302
 original=gs.sql('SELECT FlatShippingFee,FreeShippingThreshold FROM PaymentShippingSettings').split('\t')
 def shipping(fee,threshold):
  page=gs.get(operator,'/Admin/CaiDatCuaHang/QuanLyThanhToanVanChuyen')[0]
  assert gs.post(operator,'/Admin/CaiDatCuaHang/LuuChinhSachVanChuyen',page,{'Shipping.ExpectedVersion':gs.sql('SELECT Version FROM PaymentShippingSettings'),'Shipping.FlatShippingFee':fee,'Shipping.FreeShippingThreshold':threshold})[0]==302
 # Same zero-fee fixture used by the existing M1 payment.business_regression wrapper.
 shipping(0,300000)
 gs.fixtures()
 try:gs.http_checks()
 finally:
  gs.cleanup();shipping(*original)
 admin=requests.Session();assert m.login(admin,*accounts['admin'],path='/Admin/Account/Login').status_code==302
 checks=[]
 for path in ['/Admin','/Admin/SanPham/QuanLySanPham','/Admin/DanhMuc/QuanLyDanhMuc','/Admin/DonHang/QuanLyDonHang','/Admin/NguoiDung/QuanLyNguoiDung','/Admin/KhachHang/DanhGia','/Admin/KhachHang/ThongBaoCuaToi','/Admin/KhachHang/TinNhan']:
  r=admin.get(m.BASE+path,verify=False,timeout=20);assert r.status_code==200,path;checks.append({'route':path,'status':r.status_code})
 m.record('business-regression',{'status':'PASS','time':m.now(),'existing_suite':'tests/storefront_regression.py fixtures/http_checks/cleanup','checks':gs.checks,'admin_routes':checks,'writes':'Only synthetic fixtures on guarded greenshop-m2-qa DB; Main unchanged.'})
 print('PASS: existing storefront HTTP regression plus Admin pages.',flush=True)
def grants():
 db=m.qa_name('db');pw=json.loads((m.QA/'passwords.json').read_text())['exporter']
 def exporter(q):
  return subprocess.run(['docker','exec','-i',db,'sh','-c','IFS= read -r MYSQL_PWD; export MYSQL_PWD; exec mysql --protocol=TCP -h 127.0.0.1 -ugreenshop_exporter -N -B'],input=(pw+'\n'+q).encode(),capture_output=True)
 allowed=exporter('SHOW GLOBAL STATUS LIKE "Threads_connected";');assert allowed.returncode==0
 read=exporter('SELECT * FROM greenshop_m2_qa.Users LIMIT 0;');assert read.returncode!=0
 write=exporter('UPDATE greenshop_m2_qa.Products SET StockQuantity=StockQuantity WHERE 1=0;');assert write.returncode!=0
 grants=m.sql(db,"SHOW GRANTS FOR 'greenshop_exporter'@'%'",db='greenshop_m2_qa')
 assert 'PROCESS' in grants and 'SELECT' not in grants and 'ALL PRIVILEGES' not in grants
 m.record('mysql-exporter-privileges',{'status':'PASS','time':m.now(),'grants':grants.splitlines(),'global_status_read':True,'application_select_denied':True,'application_update_denied':True,'mysql_up':m.scalar('mysql_up'),'connections':m.scalar('mysql_global_status_threads_connected'),'queries':m.scalar('mysql_global_status_queries')})
 print('PASS: exporter real connection, PROCESS-only grants; application SELECT and UPDATE denied.',flush=True)
def persistence():
 db=m.qa_name('db');before=m.sql(db,'SELECT COUNT(*) FROM Users',db='greenshop_m2_qa');counter=m.scalar('greenshop_auth_login_failures_total')
 m.dc('restart','grafana','prometheus')
 m.wait_for(lambda:requests.get(m.GRAF+'/api/health',timeout=5).status_code==200)
 time.sleep(20)
 assert len(m.graf('/api/search?type=dash-db'))==3
 assert len(m.graf('/api/v1/provisioning/alert-rules'))==4
 assert m.scalar('greenshop_auth_login_failures_total')==counter
 assert m.sql(db,'SELECT COUNT(*) FROM Users',db='greenshop_m2_qa')==before
 assert m.query('greenshop_auth_login_failures_total offset 1m'),'TSDB history did not survive'
 m.record('persistence',{'status':'PASS','time':m.now(),'checks':['Grafana/Prometheus restarted','3 dashboard UIDs retained','4 provisioned rules retained','TSDB historical series retained','application counter unchanged','QA MySQL user count unchanged']})
 print('PASS: Grafana dashboards/rules and Prometheus history survive restart.',flush=True)
def archives():
 baseline=json.loads((m.PRIVATE/'baseline.json').read_text());expected={}
 for line in baseline['files']+baseline['tls']:
  digest,path=line.split(None,1);expected[path]=digest
 checked=[]
 for name,prefix in [('keys.tar','/app/keys/'),('uploads.tar','/app/wwwroot/uploads/products/'),('tls.tar','/etc/nginx/ssl/')]:
  with tarfile.open(m.PRIVATE/'backup'/name) as t:
   for member in t.getmembers():
    if not member.isfile():continue
    path=prefix+member.name.removeprefix('./')
    assert hashlib.sha256(t.extractfile(member).read()).hexdigest()==expected[path],path
    checked.append(path)
 assert len(checked)==len(expected)
 m.record('archive-verification',{'status':'PASS','time':m.now(),'checks':'Every archived keys/uploads/TLS file hash equals its live baseline source','files_checked':len(checked)})
 print('PASS: all keys/uploads/TLS archive hashes match live baseline files.',flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
