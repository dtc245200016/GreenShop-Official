#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 - <<'PY'
import getpass,json,subprocess,sys
def ask(prompt):
    with open('/dev/tty') as terminal:
        print(prompt,end='',flush=True)
        return terminal.readline().strip()
name=ask('Tên quản trị viên đầu tiên: ')
email=ask('Email quản trị viên: ')
password=getpass.getpass('Mật khẩu mới (ít nhất 12 ký tự, tối đa 72 byte UTF-8): ')
if password!=getpass.getpass('Nhập lại mật khẩu: '):sys.exit('Mật khẩu không khớp.')
payload=json.dumps({'FullName':name,'Email':email,'Password':password})
sys.exit(subprocess.run(['docker','compose','exec','-T','web_app','dotnet','GreenShop.Web.dll','--create-initial-admin'],input=payload,text=True).returncode)
PY
