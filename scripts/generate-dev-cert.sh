#!/usr/bin/env bash
set -euo pipefail

usage() { echo "Usage: bash scripts/generate-dev-cert.sh HOST [--force] [--output-dir DIRECTORY]" >&2; }
[[ $# -gt 0 ]] || { usage; exit 1; }
host=$1; shift
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
output_dir="$project_dir/nginx/ssl"; force=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) force=true; shift ;;
        --output-dir) [[ $# -ge 2 ]] || { usage; exit 1; }; output_dir=$2; shift 2 ;;
        *) usage; exit 1 ;;
    esac
done
command -v openssl >/dev/null || { echo "OpenSSL is required." >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 is required for safe IP/DNS validation." >&2; exit 1; }
san=$(python3 - "$host" <<'PY'
import ipaddress,re,sys
host=sys.argv[1]
try:
    address=ipaddress.ip_address(host)
    values=['IP:'+str(address),'IP:127.0.0.1','DNS:localhost']
except ValueError:
    if len(host)>253 or not host or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',part) for part in host.split('.')) or re.fullmatch(r'[0-9.]+',host):
        sys.exit('Invalid IP address or DNS name.')
    values=['DNS:'+host,'IP:127.0.0.1','DNS:localhost']
print(','.join(dict.fromkeys(values)))
PY
)
[[ ! -L "$output_dir/key.pem" && ! -L "$output_dir/cert.pem" ]] || { echo "Refusing symlink certificate/key targets." >&2; exit 1; }
if ! $force && { [[ -e "$output_dir/key.pem" ]] || [[ -e "$output_dir/cert.pem" ]]; }; then
    echo "Certificate/key already exists; preserved. Use --force only for an intentional rotation." >&2
    exit 1
fi
umask 077
mkdir -p -- "$output_dir"
mkdir -- "$output_dir/.cert-generation.lock" || { echo "Another certificate generation is in progress." >&2; exit 1; }
temporary_dir=''
cleanup() {
    if [[ -n "$temporary_dir" ]]; then
        rm -f -- "$temporary_dir/key.pem" "$temporary_dir/cert.pem"
        rmdir -- "$temporary_dir"
    fi
    rmdir -- "$output_dir/.cert-generation.lock"
}
trap cleanup EXIT
if ! $force && { [[ -e "$output_dir/key.pem" ]] || [[ -e "$output_dir/cert.pem" ]]; }; then
    echo "Certificate/key appeared while acquiring the lock; preserved." >&2
    exit 1
fi
temporary_dir=$(mktemp -d "$output_dir/.cert-generation.XXXXXX")
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 365 \
    -keyout "$temporary_dir/key.pem" -out "$temporary_dir/cert.pem" \
    -subj "/CN=$host/O=GreenShop Development" -addext "subjectAltName=$san" >/dev/null 2>&1
chmod 600 "$temporary_dir/key.pem"
chmod 644 "$temporary_dir/cert.pem"
openssl x509 -in "$temporary_dir/cert.pem" -noout -checkend 0 >/dev/null
mv -f -- "$temporary_dir/key.pem" "$output_dir/key.pem"
mv -f -- "$temporary_dir/cert.pem" "$output_dir/cert.pem"
echo "Created: $output_dir/cert.pem and $output_dir/key.pem"
echo "SAN: $san"
