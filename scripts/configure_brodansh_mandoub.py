#!/usr/bin/env python3
"""Idempotent Brodansh mandoub POS + kitchen-display configurator.

Reads Odoo XML-RPC credentials from the environment (or a local .env file).
Does not print secrets.
"""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_mandoub_pos" / "models"))

from mandoub_setup import (  # noqa: E402
    SHARED_KITCHEN_NAME,
    is_mandoub_pos_name,
    kitchen_display_name_for_pos,
    stage_spec_list,
)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit("Missing required environment variable: %s" % name)
    return value


class OdooClient:
    def __init__(self, url: str, db: str, username: str, api_key: str) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.api_key = api_key
        common = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % self.url, allow_none=True)
        self.uid = common.authenticate(db, username, api_key, {})
        if not self.uid:
            raise SystemExit("Authentication failed. Check ODOO_DB / ODOO_USERNAME / ODOO_API_KEY.")
        self.models = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % self.url, allow_none=True)
        self.context = {"lang": "ar_001"}

    def set_company_ids(self, company_ids: list[int]) -> None:
        self.context["allowed_company_ids"] = company_ids

    def execute(self, model: str, method: str, *args, **kwargs):
        kw = dict(kwargs)
        kw["context"] = {**self.context, **kw.get("context", {})}
        return self.models.execute_kw(self.db, self.uid, self.api_key, model, method, list(args), kw)


def find_company_id(client: OdooClient, company_name: str) -> int:
    rows = client.execute(
        "res.company",
        "search_read",
        [("name", "=", company_name)],
        fields=["name"],
    )
    if not rows:
        raise SystemExit("Company not found: %s" % company_name)
    return rows[0]["id"]


def open_mandoub_sessions(client: OdooClient, configs: list[dict]) -> list[str]:
    log: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    session_ids = [c["current_session_id"][0] for c in configs if c.get("current_session_id")]
    if not session_ids:
        return ["No open/opening sessions found on mandoub POS configs."]
    sessions = client.execute(
        "pos.session",
        "read",
        session_ids,
        fields=["name", "state", "start_at", "config_id"],
    )
    for session in sessions:
        vals = {}
        if session["state"] in ("new", "opening_control"):
            vals["state"] = "opened"
        if not session["start_at"]:
            vals["start_at"] = now
        if vals:
            client.execute("pos.session", "write", [session["id"]], vals)
            log.append("Opened session %s (was %s)" % (session["name"], session["state"]))
    return log


def sync_stages(client: OdooClient, display_id: int) -> list[str]:
    log: list[str] = []
    specs = stage_spec_list()
    stages = client.execute(
        "pos_preparation_display.stage",
        "search_read",
        [("preparation_display_id", "=", display_id)],
        order="sequence, id",
        fields=["name", "sequence"],
    )
    stages = sorted(stages, key=lambda row: (row.get("sequence") or 0, row["id"]))
    for record, spec in zip(stages, specs):
        client.execute("pos_preparation_display.stage", "write", [record["id"]], spec)
        if record["name"] != spec["name"]:
            log.append("Renamed stage %s -> %s" % (record["name"], spec["name"]))
    for spec in specs[len(stages) :]:
        client.execute(
            "pos_preparation_display.stage",
            "create",
            {**spec, "preparation_display_id": display_id},
        )
        log.append("Created stage %s" % spec["name"])
    extra = stages[len(specs) :]
    if extra:
        log.append("Left extra stages in place: %s" % ", ".join(row["name"] for row in extra))
    return log


def ensure_display(client: OdooClient, name: str, company_id: int, pos_ids: list[int]) -> list[str]:
    log: list[str] = []
    existing = client.execute(
        "pos_preparation_display.display",
        "search_read",
        [("name", "=", name), ("company_id", "=", company_id)],
        fields=["id", "name"],
    )
    if existing:
        display_id = existing[0]["id"]
        log.extend(sync_stages(client, display_id))
        log.append("Updated display %s" % name)
    else:
        display_id = client.execute(
            "pos_preparation_display.display",
            "create",
            {
                "name": name,
                "company_id": company_id,
                "stage_ids": [(0, 0, spec) for spec in stage_spec_list()],
            },
        )
        log.append("Created display %s" % name)
    client.execute(
        "pos_preparation_display.display",
        "write",
        [display_id],
        {"pos_config_ids": [(6, 0, pos_ids)]},
    )
    return log


def configure(client: OdooClient, company_id: int) -> list[str]:
    log: list[str] = []
    configs = client.execute(
        "pos.config",
        "search_read",
        [("company_id", "=", company_id), ("active", "=", True)],
        fields=["name", "current_session_id", "current_session_state"],
    )
    mandoub = [row for row in configs if is_mandoub_pos_name(row["name"])]
    if not mandoub:
        return ["No POS configs named «مندوب — …» were found."]
    log.append("Found %s mandoub POS configs." % len(mandoub))
    log.extend(open_mandoub_sessions(client, mandoub))
    pos_ids = [row["id"] for row in mandoub]
    log.extend(ensure_display(client, SHARED_KITCHEN_NAME, company_id, pos_ids))
    for row in mandoub:
        log.extend(
            ensure_display(
                client,
                kitchen_display_name_for_pos(row["name"]),
                company_id,
                [row["id"]],
            )
        )
    log.append("Kitchen stages: مؤكد → تم الشحن → الفوترة")
    return log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure Brodansh mandoub POS + kitchen screens")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(Path(args.env_file))
    if args.dry_run:
        company_name = os.getenv("ODOO_COMPANY_NAME", "مصنع ذو الجناحين للملابس الجاهزة").strip()
        print("Dry run: would use company=%s" % company_name)
        print("Kitchen stages:", ", ".join(spec["name"] for spec in stage_spec_list()))
        print("Shared display:", SHARED_KITCHEN_NAME)
        return

    url = require_env("ODOO_URL")
    db = require_env("ODOO_DB")
    username = require_env("ODOO_USERNAME")
    api_key = require_env("ODOO_API_KEY")
    company_name = os.getenv("ODOO_COMPANY_NAME", "مصنع ذو الجناحين للملابس الجاهزة").strip()

    client = OdooClient(url, db, username, api_key)
    company_id = find_company_id(client, company_name)
    companies = client.execute("res.company", "search", [])
    client.set_company_ids(companies or [company_id])
    for line in configure(client, company_id):
        print(line)


if __name__ == "__main__":
    main()
