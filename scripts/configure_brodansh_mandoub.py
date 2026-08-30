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
    CREDIT_PAYMENT_NAME,
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


def ensure_credit_payment(client: OdooClient, company_id: int) -> int:
    rows = client.execute(
        "pos.payment.method",
        "search_read",
        [("company_id", "=", company_id), ("name", "=", CREDIT_PAYMENT_NAME), ("type", "=", "pay_later")],
        fields=["id", "name", "type", "split_transactions"],
    )
    if rows:
        client.execute(
            "pos.payment.method",
            "write",
            [rows[0]["id"]],
            {"journal_id": False, "split_transactions": True},
        )
        return rows[0]["id"]
    templates = client.execute(
        "pos.payment.method",
        "search_read",
        [("company_id", "=", company_id), ("journal_id", "!=", False)],
        fields=["id"],
        limit=1,
    )
    if not templates:
        raise SystemExit("No payment method template found to copy for آجل.")
    copied = client.execute(
        "pos.payment.method",
        "copy",
        [templates[0]["id"]],
        default={"name": CREDIT_PAYMENT_NAME, "journal_id": False, "split_transactions": True},
    )
    method_id = copied[0] if isinstance(copied, list) else copied
    client.execute(
        "pos.payment.method",
        "write",
        [method_id],
        {"name": CREDIT_PAYMENT_NAME, "journal_id": False, "split_transactions": True},
    )
    return method_id


def employee_for_user(client: OdooClient, user_id: int, company_id: int) -> dict | None:
    rows = client.execute(
        "hr.employee",
        "search_read",
        [("user_id", "=", user_id), ("company_id", "=", company_id)],
        fields=["name", "user_id"],
        limit=1,
    )
    return rows[0] if rows else None


def close_empty_sessions(client: OdooClient, configs: list[dict]) -> tuple[list[str], dict[int, int]]:
    log: list[str] = []
    users_by_config: dict[int, int] = {}
    for config in configs:
        if config.get("current_session_id"):
            session = client.execute(
                "pos.session",
                "read",
                [config["current_session_id"][0]],
                fields=["name", "state", "user_id"],
            )[0]
            if session.get("user_id"):
                users_by_config[config["id"]] = session["user_id"][0]
            if session["state"] == "closed":
                continue
            orders = client.execute("pos.order", "search_count", [("session_id", "=", session["id"])])
            if orders:
                log.append("Skipped closing %s; it has orders." % session["name"])
                continue
            client.execute("pos.session", "action_pos_session_closing_control", [session["id"]])
            log.append("Closed empty session %s" % session["name"])
        elif config.get("current_user_id"):
            users_by_config[config["id"]] = config["current_user_id"][0]
    return log, users_by_config


def assign_cashier_and_credit(
    client: OdooClient,
    configs: list[dict],
    users_by_config: dict[int, int],
    company_id: int,
    manager_uid: int,
) -> list[str]:
    log: list[str] = []
    credit_id = ensure_credit_payment(client, company_id)
    manager = employee_for_user(client, manager_uid, company_id)
    for config in configs:
        user_id = users_by_config.get(config["id"])
        if not user_id and config.get("current_user_id"):
            user_id = config["current_user_id"][0]
        cashier = employee_for_user(client, user_id, company_id) if user_id else None
        if not cashier:
            log.append("No employee linked to POS %s" % config["name"])
            continue
        advanced_ids = [cashier["id"]]
        if manager and manager["id"] not in advanced_ids:
            advanced_ids.append(manager["id"])
        client.execute(
            "pos.config",
            "write",
            [config["id"]],
            {
                "module_pos_hr": True,
                "basic_employee_ids": [(6, 0, [cashier["id"]])],
                "advanced_employee_ids": [(6, 0, advanced_ids)],
                "payment_method_ids": [(6, 0, [credit_id])],
            },
        )
        log.append("Cashier %s = %s, payment = آجل" % (config["name"], cashier["name"]))
    return log


def open_mandoub_sessions(
    client: OdooClient,
    configs: list[dict],
    users_by_config: dict[int, int],
    company_id: int,
) -> list[str]:
    log: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for config in configs:
        user_id = users_by_config.get(config["id"])
        cashier = employee_for_user(client, user_id, company_id) if user_id else None
        refreshed = client.execute(
            "pos.config",
            "read",
            [config["id"]],
            fields=["current_session_id"],
        )[0]
        session_id = refreshed["current_session_id"][0] if refreshed.get("current_session_id") else None
        if session_id:
            state = client.execute("pos.session", "read", [session_id], fields=["state"])[0]["state"]
            if state == "closed":
                session_id = None
        if not session_id:
            vals = {
                "config_id": config["id"],
                "user_id": user_id or client.uid,
            }
            if cashier:
                vals["employee_id"] = cashier["id"]
            session_id = client.execute("pos.session", "create", vals)
            log.append("Created session for %s" % config["name"])
        write_vals = {"state": "opened", "start_at": now}
        if cashier:
            write_vals["employee_id"] = cashier["id"]
        if user_id:
            write_vals["user_id"] = user_id
        client.execute("pos.session", "write", [session_id], write_vals)
        log.append(
            "Opened session for %s cashier=%s"
            % (config["name"], cashier["name"] if cashier else "-")
        )
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
        fields=["name", "current_session_id", "current_session_state", "current_user_id"],
    )
    mandoub = [row for row in configs if is_mandoub_pos_name(row["name"])]
    if not mandoub:
        return ["No POS configs named «مندوب — …» were found."]
    log.append("Found %s mandoub POS configs." % len(mandoub))
    close_log, users_by_config = close_empty_sessions(client, mandoub)
    log.extend(close_log)
    log.extend(assign_cashier_and_credit(client, mandoub, users_by_config, company_id, client.uid))
    log.extend(open_mandoub_sessions(client, mandoub, users_by_config, company_id))
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
        print("Cashier: each mandoub employee")
        print("Payment method:", CREDIT_PAYMENT_NAME)
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
