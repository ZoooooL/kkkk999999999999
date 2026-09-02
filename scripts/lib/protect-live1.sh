# Shared Live-1 protection. Source from other scripts.
# Live 1 = https://brodansh.de.com.eg on AWS 18.133.13.149 — never write to it.

LIVE1_DOMAIN=${LIVE1_DOMAIN:-brodansh.de.com.eg}
LIVE1_IP=${LIVE1_IP:-18.133.13.149}

forbid_touching_live1() {
  local target=${1:-}
  local lower
  lower=$(printf '%s' "$target" | tr 'A-Z' 'a-z')
  if [[ -z $target ]]; then
    return 0
  fi
  if [[ $lower == "$LIVE1_DOMAIN" || $lower == *"$LIVE1_IP"* || $lower == *"://$LIVE1_DOMAIN"* ]]; then
    echo "Refusing: this would touch Live 1 (${LIVE1_DOMAIN} / ${LIVE1_IP})." >&2
    echo "Live 1 stays as-is. Use Live 2 only (live2.brodansh.de.com.eg or the Hetzner CX33 IP)." >&2
    exit 1
  fi
}
