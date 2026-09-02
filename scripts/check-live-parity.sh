#!/usr/bin/env bash
# Compare this Docker stack with the live site.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
[[ -f .env ]] && { set -a; source .env; set +a; }

LIVE=${LIVE_URL:-https://brodansh.de.com.eg}
LOCAL=http://127.0.0.1:${ODOO_HTTP_PORT:-8069}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl -fsS -X POST "$LIVE/web/webclient/version_info" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}' > "$TMP/live.json"
curl -fsS -X POST "$LOCAL/web/webclient/version_info" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}' > "$TMP/local.json"

python3 - "$TMP/live.json" "$TMP/local.json" <<'PY'
import json, sys
live = json.load(open(sys.argv[1]))["result"]
local = json.load(open(sys.argv[2]))["result"]
print("live ", live.get("server_version"))
print("local", local.get("server_version"))

def is_ent(info):
    ver = info.get("server_version") or ""
    extra = (info.get("server_version_info") or [None])[-1]
    return ver.endswith("+e") or extra == "e"

ok = True
if live.get("server_serie") != local.get("server_serie"):
    print("FAIL: Odoo series mismatch")
    ok = False
if is_ent(live) and not is_ent(local):
    print("FAIL: live is Enterprise 18.0+e; this Docker is Community.")
    print("      rsync Enterprise addons into ./enterprise and restore the live DB.")
    ok = False
    sys.exit(2)
if ok and is_ent(local):
    print("OK: same Odoo 18 Enterprise series as live.")
    sys.exit(0)
if ok:
    print("PARTIAL: same Odoo 18 series, Community edition — not a 100% live clone yet.")
    sys.exit(2)
sys.exit(1)
PY
