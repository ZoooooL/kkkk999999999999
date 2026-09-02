#!/usr/bin/env bash
# Live 2 templates must match Live 1's public DB selector (all four DBs).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
fail=0

check() {
  local file=$1
  if ! grep -q '^list_db = True' "$file"; then
    echo "FAIL: $file must have list_db = True (Live 1 selector is public)"
    fail=1
  fi
  if ! grep -q '^dbfilter =$' "$file"; then
    echo "FAIL: $file must have empty dbfilter (Live 1 lists brodan, brodan2026, brodansh, test)"
    fail=1
  fi
  if ! grep -q '^db_name = False' "$file"; then
    echo "FAIL: $file must have db_name = False"
    fail=1
  fi
}

check "$ROOT/config/odoo.conf"
check "$ROOT/config/odoo.prod.conf"

if ! grep -q 'X-XSS-Protection' "$ROOT/nginx/odoo.conf"; then
  echo "FAIL: nginx must send X-XSS-Protection like Live 1"
  fail=1
fi

if grep -q 'dbfilter = \^' "$ROOT/config/odoo.prod.conf"; then
  echo "FAIL: prod dbfilter must not pin a single database"
  fail=1
fi

python3 - "$ROOT/live1/fingerprint.json" <<'PY'
import json, sys
fp = json.load(open(sys.argv[1]))
assert fp["server_version"] == "18.0+e"
assert fp["databases"] == ["brodan", "brodan2026", "brodansh", "test"]
assert fp["list_db"] is True
print("OK fingerprint contract")
PY

if [[ $fail -ne 0 ]]; then
  exit 1
fi
echo "OK Live 2 config matches Live 1 selector policy"
