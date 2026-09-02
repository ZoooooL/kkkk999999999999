#!/usr/bin/env bash
# Compare this Docker Live 2 stack with Live 1 (public HTTP only).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
[[ -f .env ]] && { set -a; source .env; set +a; }

LIVE=${LIVE_URL:-${LIVE1_URL:-https://brodansh.de.com.eg}}
LOCAL=http://127.0.0.1:${ODOO_HTTP_PORT:-8069}
EXPECTED="$ROOT/live1/fingerprint.json"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl -fsS -X POST "$LIVE/web/webclient/version_info" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}' > "$TMP/live.json"
curl -fsS -X POST "$LIVE/web/database/list" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}' > "$TMP/live-dbs.json"
curl -fsS -X POST "$LOCAL/web/webclient/version_info" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}' > "$TMP/local.json"
curl -fsS -X POST "$LOCAL/web/database/list" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}' > "$TMP/local-dbs.json"

python3 - "$TMP/live.json" "$TMP/local.json" "$TMP/live-dbs.json" "$TMP/local-dbs.json" "$EXPECTED" <<'PY'
import json, sys

live = json.load(open(sys.argv[1]))["result"]
local = json.load(open(sys.argv[2]))["result"]
live_dbs = json.load(open(sys.argv[3])).get("result") or []
local_dbs = json.load(open(sys.argv[4])).get("result") or []
expected = json.load(open(sys.argv[5]))

print("live    version ", live.get("server_version"))
print("local   version ", local.get("server_version"))
print("live    databases", live_dbs)
print("local   databases", local_dbs)
print("target  databases", expected.get("databases"))

def is_ent(info):
    ver = info.get("server_version") or ""
    extra = (info.get("server_version_info") or [None])[-1]
    return ver.endswith("+e") or extra == "e"

gaps = []
if live.get("server_serie") != local.get("server_serie"):
    gaps.append("Odoo series mismatch")
if is_ent(live) and not is_ent(local):
    gaps.append("Live 1 is Enterprise 18.0+e; Live 2 is Community until ./enterprise is filled from a read-only dump")
if sorted(live_dbs) != sorted(local_dbs):
    gaps.append(
        f"Database names differ (Live 1={live_dbs}, Live 2={local_dbs}). "
        "Import backups/brodansh-live1-readonly-*.tar.gz — do not touch Live 1."
    )

if not gaps:
    print("OK: Live 2 matches Live 1 (edition + database names).")
    sys.exit(0)

print("NOT 100% YET:")
for gap in gaps:
    print(" -", gap)
print("Live 1 was only read via public HTTP. It was not modified.")
sys.exit(2)
PY
