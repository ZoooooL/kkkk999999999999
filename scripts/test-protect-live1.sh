#!/usr/bin/env bash
# Unit tests for Live 1 write-protection. No network.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/protect-live1.sh"

pass=0
fail=0

expect_block() {
  local label=$1
  local target=$2
  if (forbid_touching_live1 "$target") >/dev/null 2>&1; then
    echo "FAIL: should have blocked: $label ($target)"
    fail=$((fail + 1))
  else
    echo "OK  blocked: $label"
    pass=$((pass + 1))
  fi
}

expect_allow() {
  local label=$1
  local target=$2
  if (forbid_touching_live1 "$target") >/dev/null 2>&1; then
    echo "OK  allowed: $label"
    pass=$((pass + 1))
  else
    echo "FAIL: should have allowed: $label ($target)"
    fail=$((fail + 1))
  fi
}

expect_allow "empty" ""
expect_allow "live2 odoo subdomain" "odoo.zouljanaheen.com"
expect_allow "live2 alt subdomain" "live2.zouljanaheen.com"
expect_allow "hetzner ip" "root@162.55.12.34"
expect_block "live1 domain" "brodansh.de.com.eg"
expect_block "live1 url" "https://brodansh.de.com.eg"
expect_block "www live1" "www.brodansh.de.com.eg"
expect_block "live1 ip" "18.133.13.149"
expect_block "ssh live1" "ubuntu@18.133.13.149"
expect_block "other aws odoo" "root@3.8.46.165"
expect_block "shop apex" "zouljanaheen.com"
expect_block "shop www" "www.zouljanaheen.com"
expect_block "shop ip" "root@46.101.110.51"

if [[ $fail -ne 0 ]]; then
  echo "protect-live1 tests: $pass passed, $fail failed"
  exit 1
fi
echo "protect-live1 tests: $pass passed"
