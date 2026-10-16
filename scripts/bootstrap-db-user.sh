#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v python3 >/dev/null || { echo "Python 3 is required." >&2; exit 1; }
python3 - <<'PY'
import json,subprocess,sys
try:
    # Capture configuration privately; never echo resolved secrets.
    configuration=subprocess.run(['docker','compose','config','--format','json'],capture_output=True,text=True,check=True)
    services=json.loads(configuration.stdout)['services']
    database=services['db']['environment']
    payload={'Database':database['MYSQL_DATABASE'],'RootPassword':database['MYSQL_ROOT_PASSWORD'],'AppPassword':database['MYSQL_PASSWORD']}
    result=subprocess.run(['docker','compose','run','--rm','--no-deps','-T','web_app','--bootstrap-db-user'],input=json.dumps(payload),text=True)
    sys.exit(result.returncode)
except (subprocess.CalledProcessError,KeyError,ValueError):
    sys.exit('Bootstrap failed: check .env, Compose configuration and a healthy db; no credentials were printed.')
PY
