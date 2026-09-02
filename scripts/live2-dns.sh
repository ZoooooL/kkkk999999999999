#!/usr/bin/env bash
# Inspect Live 2 DNS and print the ONE new record to add.
# Never changes Live 1, never changes the shop apex (@ / www).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/protect-live1.sh"
# shellcheck disable=SC1091
[[ -f $ROOT/.env ]] && { set -a; source "$ROOT/.env"; set +a; }

ASKED=${1:-${ODOO_DOMAIN:-odoo.zouljanaheen.com}}
SHOP=zouljanaheen.com
TYPOeee=zouljanaheeen.com

forbid_touching_live1 "$ASKED"

echo "Asked hostname: $ASKED"

if [[ $ASKED == "$TYPOeee" || $ASKED == *".$TYPOeee" ]]; then
  echo "NXDOMAIN: $TYPOeee is not registered (Verisign: No match)."
  echo "The domain you already own is $SHOP (Namecheap, shop at 46.101.110.51)."
  echo "Live 2 uses the subdomain odoo.$SHOP — extra 'e' spelling is unused."
  ASKED=odoo.$SHOP
  echo "Using: $ASKED"
fi

status=$(python3 - "$ASKED" <<'PY'
import json, ssl, sys, urllib.error, urllib.request
host = sys.argv[1].lower().rstrip(".")
# Check apex registration for *.example.com
parts = host.split(".")
apex = ".".join(parts[-2:]) if len(parts) >= 2 else host
url = f"https://rdap.verisign.com/com/v1/domain/{apex}"
ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(url, timeout=20, context=ctx) as resp:
        data = json.load(resp)
    print("registered")
    ns = ",".join(n.get("ldhName", "") for n in data.get("nameservers") or [])
    print(ns)
except urllib.error.HTTPError as e:
    if e.code == 404:
        print("unregistered")
        print("")
        sys.exit(0)
    raise
PY
)

reg=$(printf '%s\n' "$status" | sed -n '1p')
ns=$(printf '%s\n' "$status" | sed -n '2p')

if [[ $reg != registered ]]; then
  echo "Cannot set DNS: domain is not registered."
  exit 2
fi

echo "Apex registered. Nameservers: ${ns:-unknown}"
echo -n "Current A for $ASKED: "
dig +short "$ASKED" A || true
echo
echo "Add this ONE record at Namecheap (Advanced DNS for $SHOP)."
echo "Do not edit @ or www (that is the Bagisto shop)."
echo "Do not edit brodansh.de.com.eg."
echo
echo "  Type : A"
echo "  Host : odoo"
echo "  Value: <Hetzner CX33 IPv4 of brodansh-live2>"
echo "  TTL  : Automatic"
echo
echo "Then: ./scripts/ssl-init.sh"
echo "This script does not call the Namecheap API (setHosts would replace ALL records and could take down the shop)."
echo "Live 1 and https://$SHOP were not modified."
