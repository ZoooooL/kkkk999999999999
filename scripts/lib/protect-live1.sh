# Shared Live-1 protection. Source from other scripts.
# Live 1 = https://brodansh.de.com.eg on AWS 18.133.13.149 — never write to it.
# 3.8.46.165 is a separate existing AWS Odoo (db "clo"); do not overwrite it either.

LIVE1_DOMAIN=${LIVE1_DOMAIN:-brodansh.de.com.eg}
LIVE1_IP=${LIVE1_IP:-18.133.13.149}
PROTECTED_IPS=${PROTECTED_IPS:-18.133.13.149,3.8.46.165}
PROTECTED_DOMAINS=${PROTECTED_DOMAINS:-brodansh.de.com.eg,www.brodansh.de.com.eg}

_protect_haystack() {
  printf '%s' "$1" | tr 'A-Z' 'a-z'
}

forbid_touching_live1() {
  local target=${1:-}
  local lower
  local ip
  local domain
  if [[ -z $target ]]; then
    return 0
  fi
  lower=$(_protect_haystack "$target")

  IFS=',' read -r -a _protect_ips <<<"$PROTECTED_IPS"
  for ip in "${_protect_ips[@]}"; do
    ip=$(printf '%s' "$ip" | tr -d ' ')
    [[ -z $ip ]] && continue
    if [[ $lower == *"$ip"* ]]; then
      echo "Refusing: this would touch an existing AWS Odoo host (${ip})." >&2
      echo "Live 1 (${LIVE1_DOMAIN} / ${LIVE1_IP}) stays as-is. Deploy Live 2 to a NEW machine only." >&2
      exit 1
    fi
  done

  IFS=',' read -r -a _protect_domains <<<"$PROTECTED_DOMAINS"
  for domain in "${_protect_domains[@]}"; do
    domain=$(printf '%s' "$domain" | tr 'A-Z' 'a-z' | tr -d ' ')
    [[ -z $domain ]] && continue
    if [[ $lower == "$domain" || $lower == *"://$domain"* || $lower == *"@$domain"* ]]; then
      echo "Refusing: this would touch Live 1 (${LIVE1_DOMAIN} / ${LIVE1_IP})." >&2
      echo "Live 1 stays as-is. Use Live 2 only (a new Hetzner CX33 IP, never ${LIVE1_DOMAIN})." >&2
      exit 1
    fi
  done
}
