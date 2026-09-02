#!/usr/bin/env python3
"""Write nginx/odoo.conf.runtime for Live 2 only."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TEMPLATE = ROOT / "nginx" / "odoo.conf"
OUT = ROOT / "nginx" / "odoo.conf.runtime"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def main() -> None:
    env = load_env(ENV_PATH)
    domain = env.get("ODOO_DOMAIN", "live2.brodansh.de.com.eg")
    if domain in {"brodansh.de.com.eg", "www.brodansh.de.com.eg"}:
        raise SystemExit(
            "Refusing to render nginx for Live 1. Set ODOO_DOMAIN=live2.brodansh.de.com.eg"
        )
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("live2.brodansh.de.com.eg", domain)
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote nginx for {domain}")


if __name__ == "__main__":
    main()
