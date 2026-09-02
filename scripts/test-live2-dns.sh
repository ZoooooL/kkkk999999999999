#!/usr/bin/env bash
# live2-dns.sh must refuse Live 1 / shop apex and detect the extra-e typo.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
fail=0

if "$ROOT/scripts/live2-dns.sh" brodansh.de.com.eg >/dev/null 2>&1; then
  echo "FAIL: must refuse Live 1 domain"
  fail=1
else
  echo "OK refused Live 1"
fi

if "$ROOT/scripts/live2-dns.sh" zouljanaheen.com >/dev/null 2>&1; then
  echo "FAIL: must refuse shop apex"
  fail=1
else
  echo "OK refused shop apex"
fi

out=$("$ROOT/scripts/live2-dns.sh" zouljanaheeen.com)
if ! grep -q 'not registered' <<<"$out"; then
  echo "FAIL: extra-e domain must be reported unregistered"
  echo "$out"
  fail=1
else
  echo "OK extra-e NXDOMAIN detected"
fi
if ! grep -q 'Host : odoo' <<<"$out"; then
  echo "FAIL: should still print the odoo record for the owned domain"
  fail=1
else
  echo "OK prints odoo A record plan"
fi

if [[ $fail -ne 0 ]]; then
  exit 1
fi
echo "OK live2-dns checks"
