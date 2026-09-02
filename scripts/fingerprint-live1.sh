#!/usr/bin/env bash
# Read-only public HTTP fingerprint of Live 1. Never SSH, never POST writes.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
LIVE=${LIVE_URL:-${LIVE1_URL:-https://brodansh.de.com.eg}}
OUT=${1:-"$ROOT/live1/fingerprint.runtime.json"}

python3 - "$LIVE" "$OUT" "$ROOT/live1/fingerprint.json" <<'PY'
import json, sys, urllib.request

url, out_path, committed = sys.argv[1:4]
base = url.rstrip("/")

def fetch(path, data=None, headers=None):
    req = urllib.request.Request(
        base + path,
        data=data,
        headers=headers or {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
        hdrs = {k: v for k, v in resp.headers.items()}
        return resp.status, hdrs, body

status, headers, _ = fetch("/")
server = headers.get("Server") or headers.get("server")
xss = headers.get("X-XSS-Protection") or headers.get("x-xss-protection")
frame = headers.get("X-Frame-Options") or headers.get("x-frame-options")
nosniff = headers.get("X-Content-Type-Options") or headers.get("x-content-type-options")

payload = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}).encode()
json_headers = {"Content-Type": "application/json"}
_, _, version_raw = fetch("/web/webclient/version_info", payload, json_headers)
_, _, dbs_raw = fetch("/web/database/list", payload, json_headers)
version = json.loads(version_raw).get("result") or {}
databases = json.loads(dbs_raw).get("result") or []

snap = {
    "url": base,
    "nginx": server,
    "server_version": version.get("server_version"),
    "server_version_info": version.get("server_version_info"),
    "server_serie": version.get("server_serie"),
    "protocol_version": version.get("protocol_version"),
    "databases": databases,
    "list_db": True,
    "headers": {
        "X-Content-Type-Options": nosniff,
        "X-Frame-Options": frame,
        "X-XSS-Protection": xss,
        "Server": server,
        "root_http_status": status,
    },
}

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(snap, fh, indent=2)
    fh.write("\n")

expected = json.load(open(committed, encoding="utf-8"))
ok = True
if snap["server_version"] != expected["server_version"]:
    print(f"WARN: live version now {snap['server_version']} (fingerprint file has {expected['server_version']})")
    ok = False
if list(snap["databases"]) != list(expected["databases"]):
    print(f"WARN: live databases now {snap['databases']} (fingerprint file has {expected['databases']})")
    ok = False
print(json.dumps(snap, indent=2))
print(f"Wrote {out_path}")
print("Live 1 was not modified (public HTTP only).")
sys.exit(0 if ok else 2)
PY
