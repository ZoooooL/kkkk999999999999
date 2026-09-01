#!/usr/bin/env python3
"""Enable POS Self-Ordering (Kiosk) on Brodansh factory POS configs.

Idempotent XML-RPC configurator. Credentials come from the environment
(ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY) or a local .env file.
Does not print secrets. Does not close POS sessions.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import xmlrpc.client
from pathlib import Path

socket.setdefaulttimeout(300)

ROOT = Path(__file__).resolve().parents[1]

COMPANY_ID = 3
SELF_ORDERING_MODE = "kiosk"
SELF_ORDERING_PAY_AFTER = "each"
SELF_ORDERING_SERVICE_MODE = "counter"
DEFAULT_USER_ID = 2
ARABIC_LANG_ID = 3
ENGLISH_LANG_ID = 1
CREDIT_PAYMENT_NAME = "آجل-حساب"
CUSTOM_LINK_NAME = "اطلب الآن "


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


def available_language_ids() -> list[int]:
    return [ARABIC_LANG_ID, ENGLISH_LANG_ID]


def pos_config_vals() -> dict:
    return {
        "self_ordering_mode": SELF_ORDERING_MODE,
        "self_ordering_pay_after": SELF_ORDERING_PAY_AFTER,
        "self_ordering_service_mode": SELF_ORDERING_SERVICE_MODE,
        "self_ordering_default_user_id": DEFAULT_USER_ID,
        "self_ordering_default_language_id": ARABIC_LANG_ID,
        "self_ordering_available_language_ids": [(6, 0, available_language_ids())],
    }


def self_order_product_domain() -> list:
    return [
        ("available_in_pos", "=", True),
        ("self_order_available", "=", False),
    ]


def custom_link_url(config_id: int) -> str:
    return "/pos-self/%s/products" % int(config_id)


def payment_update_action(has_open_session: bool, already_has_credit: bool) -> str:
    if already_has_credit:
        return "already"
    if has_open_session:
        return "skipped_open_session"
    return "add"


def kiosk_ready(config: dict, credit_id: int | None) -> bool:
    mode_ok = config.get("self_ordering_mode") == SELF_ORDERING_MODE
    pay_ok = config.get("self_ordering_pay_after") == SELF_ORDERING_PAY_AFTER
    user_ok = bool(config.get("self_ordering_default_user_id"))
    token_ok = bool(config.get("access_token") or config.get("self_ordering_url"))
    payments = config.get("payment_method_ids") or []
    credit_ok = credit_id in payments if credit_id else True
    return bool(mode_ok and pay_ok and user_ok and token_ok and credit_ok)


class Odoo:
    def __init__(self, url: str, db: str, username: str, api_key: str) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.uid = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % self.url).authenticate(
            db, username, api_key, {}
        )
        if not self.uid:
            raise SystemExit("XML-RPC authentication failed")
        self._models = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % self.url)
        self._key = api_key
        self.context = {
            "allowed_company_ids": [COMPANY_ID],
            "active_test": False,
        }

    def execute(self, model: str, method: str, *args, **kwargs):
        kw = dict(kwargs)
        ctx = dict(self.context)
        if "context" in kw:
            ctx.update(kw.pop("context"))
        kw["context"] = ctx
        return self._models.execute_kw(self.db, self.uid, self._key, model, method, list(args), kw)


def find_credit_method(odoo: Odoo) -> dict | None:
    rows = odoo.execute(
        "pos.payment.method",
        "search_read",
        [
            ("company_id", "=", COMPANY_ID),
            ("name", "=", CREDIT_PAYMENT_NAME),
            ("type", "=", "pay_later"),
        ],
        ["name", "type", "is_cash_count", "company_id"],
        limit=1,
    )
    return rows[0] if rows else None


def load_pos_configs(odoo: Odoo) -> list[dict]:
    return odoo.execute(
        "pos.config",
        "search_read",
        [("company_id", "=", COMPANY_ID)],
        [
            "name",
            "active",
            "company_id",
            "self_ordering_mode",
            "self_ordering_url",
            "self_ordering_pay_after",
            "self_ordering_service_mode",
            "self_ordering_default_user_id",
            "self_ordering_default_language_id",
            "self_ordering_available_language_ids",
            "payment_method_ids",
            "current_session_id",
            "has_active_session",
            "access_token",
        ],
    )


def enable_self_order_products(odoo: Odoo, apply: bool) -> dict:
    domain = self_order_product_domain()
    ids = odoo.execute("product.template", "search", domain)
    result = {"to_enable": len(ids), "enabled": 0}
    if apply and ids:
        odoo.execute("product.template", "write", ids, {"self_order_available": True})
        result["enabled"] = len(ids)
    remaining = odoo.execute("product.template", "search_count", domain) if apply else len(ids)
    result["remaining_false"] = remaining
    result["available_in_pos"] = odoo.execute(
        "product.template", "search_count", [("available_in_pos", "=", True)]
    )
    result["self_order_true"] = odoo.execute(
        "product.template",
        "search_count",
        [("available_in_pos", "=", True), ("self_order_available", "=", True)],
    )
    return result


def ensure_custom_link(odoo: Odoo, config_id: int, apply: bool) -> str:
    url = custom_link_url(config_id)
    links = odoo.execute(
        "pos_self_order.custom_link",
        "search_read",
        [("url", "=", url)],
        ["name", "url", "pos_config_ids"],
    )
    matching = [row for row in links if config_id in (row.get("pos_config_ids") or [])]
    if matching:
        return "already"
    if not apply:
        return "would_fix"
    if links:
        odoo.execute(
            "pos_self_order.custom_link",
            "write",
            [links[0]["id"]],
            {"pos_config_ids": [(4, config_id)], "name": CUSTOM_LINK_NAME},
        )
        return "attached"
    odoo.execute(
        "pos_self_order.custom_link",
        "create",
        {
            "name": CUSTOM_LINK_NAME,
            "url": url,
            "pos_config_ids": [(6, 0, [config_id])],
            "style": "primary",
        },
    )
    return "created"


def configure_config(odoo: Odoo, row: dict, credit_id: int | None, apply: bool) -> dict:
    config_id = row["id"]
    has_session = bool(row.get("current_session_id") or row.get("has_active_session"))
    payments = list(row.get("payment_method_ids") or [])
    already_credit = bool(credit_id and credit_id in payments)
    pay_action = payment_update_action(has_session, already_credit)
    out = {
        "id": config_id,
        "name": row.get("name"),
        "active": row.get("active"),
        "has_session": has_session,
        "mode_write": "skipped",
        "pay_later": pay_action,
        "custom_link": "skipped",
        "error": None,
    }
    vals = pos_config_vals()
    if apply:
        try:
            odoo.execute("pos.config", "write", [config_id], vals)
            out["mode_write"] = "ok"
        except xmlrpc.client.Fault as ex:
            out["mode_write"] = "error"
            out["error"] = str(ex)
            return out
    else:
        out["mode_write"] = "would_write"

    if pay_action == "add" and credit_id:
        new_payments = payments + [credit_id]
        if apply:
            try:
                odoo.execute(
                    "pos.config",
                    "write",
                    [config_id],
                    {"payment_method_ids": [(6, 0, new_payments)]},
                )
                out["pay_later"] = "added"
            except xmlrpc.client.Fault as ex:
                out["pay_later"] = "error"
                out["error"] = str(ex)
        else:
            out["pay_later"] = "would_add"

    try:
        out["custom_link"] = ensure_custom_link(odoo, config_id, apply)
    except xmlrpc.client.Fault as ex:
        out["custom_link"] = "error"
        out["error"] = (out["error"] or "") + str(ex)

    refreshed = odoo.execute(
        "pos.config",
        "read",
        [config_id],
        [
            "self_ordering_mode",
            "self_ordering_url",
            "self_ordering_pay_after",
            "self_ordering_service_mode",
            "self_ordering_default_user_id",
            "payment_method_ids",
            "access_token",
            "current_session_id",
        ],
    )[0]
    out.update(
        {
            "mode": refreshed.get("self_ordering_mode"),
            "pay_after": refreshed.get("self_ordering_pay_after"),
            "service_mode": refreshed.get("self_ordering_service_mode"),
            "url": refreshed.get("self_ordering_url"),
            "payments": refreshed.get("payment_method_ids"),
            "ready": kiosk_ready(refreshed, credit_id),
        }
    )
    return out


def close_empty_probe_session(odoo: Odoo, apply: bool, session_id: int | None) -> dict | None:
    """Close a leftover empty session created by a kiosk-wizard probe.

    Only the explicit probe session is touched. Open business sessions are left alone.
    """
    if not session_id:
        return None
    rows = odoo.execute(
        "pos.session",
        "read",
        [session_id],
        ["name", "config_id", "state", "order_count", "user_id"],
    )
    if not rows:
        return {"id": session_id, "action": "missing"}
    row = rows[0]
    if row.get("order_count"):
        return {"id": session_id, "action": "kept_has_orders", "name": row.get("name")}
    if row.get("state") == "closed":
        return {"id": session_id, "action": "already_closed", "name": row.get("name")}
    if not apply:
        return {"id": session_id, "action": "would_close", "name": row.get("name")}
    try:
        odoo.execute("pos.config", "action_close_kiosk_session", [row["config_id"][0]])
        return {"id": session_id, "action": "closed", "name": row.get("name")}
    except xmlrpc.client.Fault as ex:
        try:
            odoo.execute("pos.session", "action_pos_session_closing_control", [session_id])
            return {"id": session_id, "action": "closed_control", "name": row.get("name")}
        except xmlrpc.client.Fault as ex2:
            return {
                "id": session_id,
                "action": "close_error",
                "name": row.get("name"),
                "error": "%s | %s" % (ex, ex2),
            }


def verify_kiosk_data(odoo: Odoo, config_id: int) -> dict:
    cfg = odoo.execute(
        "pos.config",
        "read",
        [config_id],
        [
            "name",
            "self_ordering_mode",
            "self_ordering_url",
            "self_ordering_pay_after",
            "payment_method_ids",
            "current_session_id",
            "access_token",
        ],
    )[0]
    products = odoo.execute(
        "product.product",
        "search_count",
        [("available_in_pos", "=", True), ("self_order_available", "=", True)],
    )
    sample = odoo.execute(
        "product.product",
        "search_read",
        [("available_in_pos", "=", True), ("self_order_available", "=", True)],
        ["name", "pos_categ_ids"],
        limit=5,
    )
    return {
        "config": cfg,
        "self_order_products": products,
        "product_sample": sample,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enable Brodansh POS kiosk self-ordering")
    parser.add_argument("--apply", action="store_true", help="Write changes to the live database")
    parser.add_argument(
        "--close-empty-session",
        type=int,
        default=0,
        help="Close one empty probe session id (never used for sessions with orders)",
    )
    parser.add_argument(
        "--verify-config",
        type=int,
        default=0,
        help="Load kiosk data for one pos.config id after configure",
    )
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")
    url = require_env("ODOO_URL")
    db = require_env("ODOO_DB")
    username = require_env("ODOO_USERNAME")
    api_key = require_env("ODOO_API_KEY")
    odoo = Odoo(url, db, username, api_key)

    credit = find_credit_method(odoo)
    credit_id = credit["id"] if credit else None
    configs = load_pos_configs(odoo)
    product_info = enable_self_order_products(odoo, args.apply)
    rows = [configure_config(odoo, row, credit_id, args.apply) for row in configs]
    probe = close_empty_probe_session(odoo, args.apply, args.close_empty_session or None)
    verify = None
    verify_id = args.verify_config or next(
        (row["id"] for row in rows if row.get("active") and row.get("mode") == SELF_ORDERING_MODE),
        None,
    )
    if args.apply and verify_id:
        verify = verify_kiosk_data(odoo, verify_id)

    report = {
        "database": db,
        "company_id": COMPANY_ID,
        "apply": args.apply,
        "mode": SELF_ORDERING_MODE,
        "pay_after": SELF_ORDERING_PAY_AFTER,
        "credit_payment": credit,
        "products": product_info,
        "configs": rows,
        "probe_session": probe,
        "verify": verify,
        "note": (
            "Public /pos-self URLs 404 until the server selects database %s "
            "(set dbfilter=^%s$ or open Open Kiosk from a logged-in session)."
            % (db, db)
        ),
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
