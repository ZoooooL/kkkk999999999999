#!/usr/bin/env python3
"""Write config/odoo.conf.runtime from the committed template and .env."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TEMPLATE = ROOT / "config" / "odoo.conf"
PROD_TEMPLATE = ROOT / "config" / "odoo.prod.conf"
OUT = ROOT / "config" / "odoo.conf.runtime"
PROD_OUT = ROOT / "config" / "odoo.prod.conf.runtime"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise SystemExit(f"Missing {path}. Copy .env.example to .env first.")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def render(template: Path, env: dict[str, str]) -> str:
    text = template.read_text(encoding="utf-8")
    replacements = {
        "admin_passwd = CHANGE_ME": f"admin_passwd = {env['ODOO_ADMIN_PASSWORD']}",
        "db_password = CHANGE_ME": f"db_password = {env['POSTGRES_PASSWORD']}",
        "db_user = odoo": f"db_user = {env.get('POSTGRES_USER', 'odoo')}",
        "db_name = brodansh": f"db_name = {env.get('ODOO_DB_NAME', 'brodansh')}",
        "dbfilter = ^brodansh$": f"dbfilter = ^{env.get('ODOO_DB_NAME', 'brodansh')}$",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if "CHANGE_ME" in text:
        raise SystemExit(f"{template} still contains CHANGE_ME after render")
    return text


def main() -> None:
    env = load_env(ENV_PATH)
    for required in ("POSTGRES_PASSWORD", "ODOO_ADMIN_PASSWORD"):
        if not env.get(required) or env[required].startswith("change-this"):
            raise SystemExit(
                f"Set a real {required} in .env before starting Odoo."
            )
    OUT.write_text(render(TEMPLATE, env), encoding="utf-8")
    PROD_OUT.write_text(render(PROD_TEMPLATE, env), encoding="utf-8")
    os.chmod(OUT, 0o600)
    os.chmod(PROD_OUT, 0o600)
    print(f"Wrote {OUT.relative_to(ROOT)} and {PROD_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
