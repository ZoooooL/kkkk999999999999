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
    MANDOUB_POS_PREFIX,
    SHARED_KITCHEN_NAME,
    is_mandoub_pos_name,
    kitchen_display_name_for_pos,
    stage_spec_list,
)

POS_TO_SO_AUTOMATION_NAME = "مندوب: تحويل نقطة البيع إلى عرض سعر بدون فاتورة"
CONFIRM_AUTOMATION_NAME = "مندوب: المدير فقط يؤكد الطلب"

POS_TO_SO_CODE = """
config = record.config_id
name = config.name if config else ''
if not name.startswith('%(prefix)s'):
    pass
elif record.state == 'invoiced' or record.account_move:
    pass
elif not record.lines:
    pass
elif not record.partner_id:
    raise UserError('اختر العميل قبل إنشاء الطلب. المندوب لا يفوتر.')
else:
    uuid = record.uuid or ''
    company = record.company_id
    warehouse = config.picking_type_id.warehouse_id
    user = record.employee_id.user_id or record.user_id
    lines = []
    sequence = 10
    for line in record.lines:
        if not line.product_id:
            continue
        price = line.price_unit
        if not price:
            price = line.product_id.lst_price
        lines.append((0, 0, {
            'sequence': sequence,
            'product_id': line.product_id.id,
            'product_uom_qty': line.qty,
            'price_unit': price,
            'discount': line.discount or 0.0,
        }))
        sequence += 10
    if not lines:
        raise UserError('أضف أصنافاً قبل إنشاء الطلب.')
    new_cr = record.env.registry.cursor()
    try:
        new_env = record.env(cr=new_cr, su=True).with_company(company)
        SaleOrder = new_env['sale.order']
        so = False
        if uuid:
            so = SaleOrder.search([('client_order_ref', '=', uuid), ('company_id', '=', company.id)], limit=1)
        if so:
            so_name = so.name
        else:
            term = new_env['account.payment.term'].search([('name', '=', '30 يوماً'), ('company_id', 'in', [company.id, False])], limit=1)
            so = SaleOrder.create({
                'partner_id': record.partner_id.id,
                'origin': name,
                'client_order_ref': uuid or False,
                'user_id': user.id if user else False,
                'company_id': company.id,
                'warehouse_id': warehouse.id if warehouse else False,
                'payment_term_id': term.id if term else False,
                'order_line': lines,
            })
            so_name = so.name
        new_cr.commit()
    finally:
        new_cr.close()
    raise UserError('تم إنشاء الطلب %%s. المندوب لا يفوتر. المدير يؤكد ثم المخازن توصل ثم الحسابات تفوتر. اضغط طلب جديد.' %% so_name)
""" % {"prefix": MANDOUB_POS_PREFIX}

CONFIRM_CODE = """
origin = record.origin or ''
if origin.startswith('%s') and not env.user.has_group('sales_team.group_sale_manager'):
    raise UserError('المدير فقط يؤكد طلبات المناديب. بعد التأكيد المخازن توصل ثم الحسابات تفوتر.')
""" % MANDOUB_POS_PREFIX


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
        log.append("Cashier %s = %s, create quotation (no invoice)" % (config["name"], cashier["name"]))
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


def _model_id(client: OdooClient, model_name: str) -> int:
    rows = client.execute("ir.model", "search_read", [("model", "=", model_name)], fields=["id"])
    if not rows:
        raise SystemExit("Model not found: %s" % model_name)
    return rows[0]["id"]


def _ensure_code_automation(
    client: OdooClient,
    name: str,
    model_name: str,
    trigger: str,
    code: str,
    extra: dict | None = None,
) -> str:
    model_id = _model_id(client, model_name)
    existing = client.execute(
        "base.automation",
        "search_read",
        [("name", "=", name), ("model_id", "=", model_id)],
        fields=["id", "action_server_ids"],
    )
    vals = {
        "name": name,
        "model_id": model_id,
        "trigger": trigger,
        "active": True,
    }
    if extra:
        vals.update(extra)
    if existing:
        auto_id = existing[0]["id"]
        client.execute("base.automation", "write", [auto_id], vals)
        action_ids = existing[0].get("action_server_ids") or []
        if action_ids:
            client.execute("ir.actions.server", "write", action_ids, {"state": "code", "code": code, "name": name})
        else:
            action_id = client.execute(
                "ir.actions.server",
                "create",
                {
                    "name": name,
                    "model_id": model_id,
                    "state": "code",
                    "code": code,
                    "usage": "base_automation",
                },
            )
            client.execute("base.automation", "write", [auto_id], {"action_server_ids": [(4, action_id)]})
        return "Updated automation %s" % name
    vals["action_server_ids"] = [
        (
            0,
            0,
            {
                "name": name,
                "model_id": model_id,
                "state": "code",
                "code": code,
                "usage": "base_automation",
            },
        )
    ]
    client.execute("base.automation", "create", vals)
    return "Created automation %s" % name


def set_delivery_invoice_policy(client: OdooClient, company_id: int) -> str:
    ids = client.execute(
        "product.template",
        "search",
        [("sale_ok", "=", True), ("company_id", "=", company_id), ("invoice_policy", "=", "order")],
    )
    if not ids:
        return "Invoice policy already delivery-based."
    for offset in range(0, len(ids), 80):
        client.execute("product.template", "write", ids[offset : offset + 80], {"invoice_policy": "delivery"})
    return "Set invoice_policy=delivery on %s products." % len(ids)


def enable_quotation_mode_field(client: OdooClient, config_ids: list[int]) -> str:
    fields = client.execute("pos.config", "fields_get", [], attributes=["type"])
    if "mandoub_quotation_mode" not in fields:
        return "POS quotation-mode field not installed yet (addon JS still required for the button label)."
    client.execute("pos.config", "write", config_ids, {"mandoub_quotation_mode": True})
    return "Enabled mandoub_quotation_mode on %s POS configs." % len(config_ids)


def apply_quotation_workflow(client: OdooClient, company_id: int, config_ids: list[int]) -> list[str]:
    log: list[str] = []
    log.append(set_delivery_invoice_policy(client, company_id))
    log.append(enable_quotation_mode_field(client, config_ids))
    log.append(
        _ensure_code_automation(
            client,
            POS_TO_SO_AUTOMATION_NAME,
            "pos.order",
            "on_create_or_write",
            POS_TO_SO_CODE,
            extra={"filter_domain": "[('config_id', 'in', %s)]" % config_ids},
        )
    )
    sale_state_auto = client.execute(
        "base.automation",
        "search_read",
        [("id", "=", 3)],
        fields=["trg_selection_field_id", "trigger_field_ids"],
    )
    extra = {"filter_domain": "[('state', '=', 'sale')]"}
    if sale_state_auto:
        trg = sale_state_auto[0].get("trg_selection_field_id")
        fields = sale_state_auto[0].get("trigger_field_ids")
        if trg:
            extra["trg_selection_field_id"] = trg[0] if isinstance(trg, (list, tuple)) else trg
        if fields:
            extra["trigger_field_ids"] = [(6, 0, fields)]
    log.append(
        _ensure_code_automation(
            client,
            CONFIRM_AUTOMATION_NAME,
            "sale.order",
            "on_state_set",
            CONFIRM_CODE,
            extra=extra,
        )
    )
    log.append("Workflow: mandoub creates quotation → manager confirms → warehouse delivers → accounting invoices")
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
    log.extend(apply_quotation_workflow(client, company_id, pos_ids))
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
        print("Flow: mandoub creates quotation → manager confirms → warehouse delivers → accounting invoices")
        print("Payment method (fallback only):", CREDIT_PAYMENT_NAME)
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
