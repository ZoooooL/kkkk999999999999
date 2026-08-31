#!/usr/bin/env python3
"""Idempotent Brodansh mandoub POS + kitchen-display configurator.

Reads Odoo XML-RPC credentials from the environment (or a local .env file).
Does not print secrets.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import xmlrpc.client
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_mandoub_pos" / "models"))

from mandoub_setup import (  # noqa: E402
    ACCESS_LOCK_PARAM,
    CREDIT_PAYMENT_NAME,
    FACTORY_WAREHOUSE_CODE,
    KITCHEN_MENU_XMLID,
    MANDOUB_POS_PREFIX,
    POS_MANAGER_GROUP_XMLID,
    POS_ROOT_MENU_XMLID,
    POS_USER_GROUP_XMLID,
    RULE_KITCHEN_SHOW,
    SETUP_GROUP_COMMENT,
    SETUP_GROUP_NAME,
    SHARED_KITCHEN_NAME,
    is_mandoub_pos_name,
    is_per_cashier_kitchen_name,
    is_restricted_kitchen_name,
    kitchen_record_show_domain,
    setup_access_rule_specs,
    stage_spec_list,
)
from mandoub_setup import normalize_arabic_name  # noqa: E402

POS_TO_SO_AUTOMATION_NAME = "مندوب: تحويل نقطة البيع إلى عرض سعر بدون فاتورة"
CONFIRM_AUTOMATION_NAME = "مندوب: المدير فقط يؤكد الطلب"
KITCHEN_CONFIRM_AUTOMATION_NAME = "مندوب: شاشة المطبخ — تم التأكيد"
KITCHEN_DELIVERY_AUTOMATION_NAME = "مندوب: شاشة المطبخ — تم الشحن"
KITCHEN_INVOICE_AUTOMATION_NAME = "مندوب: شاشة المطبخ — الفوترة"

POS_TO_SO_CODE = """
if env.context.get('mandoub_kitchen_shadow'):
    pass
else:
    config = record.config_id
    name = config.name if config else ''
    if record.state in ('cancel', 'invoiced') or record.account_move:
        pass
    elif not name.startswith('%(prefix)s'):
        pass
    elif not record.lines:
        pass
    elif not record.partner_id:
        raise UserError('اختر العميل قبل إنشاء الطلب. المندوب لا يفوتر.')
    else:
        uuid = record.uuid or ''
        company = record.company_id
        warehouse = config.picking_type_id.warehouse_id
        factory = record.env['stock.warehouse'].search([('code', '=', '%(warehouse)s'), ('company_id', '=', company.id)], limit=1)
        if factory:
            warehouse = factory
        user = record.employee_id.user_id or record.session_id.employee_id.user_id or record.session_id.user_id or record.user_id
        session_id = record.session_id.id
        employee_id = record.employee_id.id if record.employee_id else (record.session_id.employee_id.id if record.session_id.employee_id else False)
        partner_id = record.partner_id.id
        partner_name = record.partner_id.name or ''
        user_name = user.name if user else ''
        lines = []
        pos_lines = []
        sequence = 10
        for line in record.lines:
            if not line.product_id:
                continue
            price = line.price_unit
            if not price:
                price = line.product_id.lst_price
            qty = line.qty
            packs = line.product_id.packaging_ids.filtered(lambda p: p.sales and p.qty > 0)
            pack_qty = min(packs.mapped('qty')) if packs else 12
            piece_qty = qty * pack_qty
            lines.append((0, 0, {
                'sequence': sequence,
                'product_id': line.product_id.id,
                'product_uom_qty': piece_qty,
                'price_unit': price,
                'discount': line.discount or 0.0,
                'name': '%%s — %%s كرتون × %%s' %% (line.full_product_name or line.product_id.display_name, qty, pack_qty),
            }))
            pos_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'qty': piece_qty,
                'price_unit': price,
                'price_subtotal': price * piece_qty,
                'price_subtotal_incl': price * piece_qty,
                'full_product_name': line.full_product_name or line.product_id.display_name,
            }))
            sequence += 10
        if not lines:
            raise UserError('أضف أصنافاً قبل إنشاء الطلب.')
        new_cr = record.env.registry.cursor()
        try:
            new_env = record.env(cr=new_cr, su=True)
            SaleOrder = new_env['sale.order'].with_company(company)
            so = False
            if uuid:
                so = SaleOrder.search([('client_order_ref', '=', uuid), ('company_id', '=', company.id)], limit=1)
            if so:
                so_name = so.name
            else:
                term = new_env['account.payment.term'].search([('name', '=', '30 يوماً'), ('company_id', 'in', [company.id, False])], limit=1)
                so = SaleOrder.create({
                    'partner_id': partner_id,
                    'origin': name,
                    'client_order_ref': uuid or False,
                    'user_id': user.id if user else False,
                    'company_id': company.id,
                    'warehouse_id': warehouse.id if warehouse else False,
                    'payment_term_id': term.id if term else False,
                    'order_line': lines,
                })
                so_name = so.name
            note = '[طلب] | %%s | %%s | %%s' %% (so_name, partner_name, user_name)
            try:
                Shadow = new_env['pos.order'].with_context(mandoub_kitchen_shadow=True).with_company(company)
                shadow = Shadow.create({
                    'session_id': session_id,
                    'partner_id': partner_id,
                    'employee_id': employee_id or False,
                    'amount_tax': 0.0,
                    'amount_total': so.amount_total,
                    'amount_paid': 0.0,
                    'amount_return': 0.0,
                    'state': 'draft',
                    'to_invoice': False,
                    'general_note': note,
                    'lines': pos_lines,
                })
                new_env['pos_preparation_display.order'].process_order(shadow.id)
                preps = new_env['pos_preparation_display.order'].search([('pos_order_id', '=', shadow.id)])
                preps.write({'pdis_general_note': note, 'displayed': True, 'employee_id': employee_id or False})
                shadow.with_context(mandoub_kitchen_shadow=True).action_pos_order_cancel()
            except Exception:
                pass
            new_cr.commit()
        finally:
            new_cr.close()
        raise UserError('تم حفظ عرض السعر %%s وطباعته. يظهر في المطبخ كطلب. مدير المبيعات يؤكد (تم التأكيد) ثم المستودع يشحّن (تم الشحن) ثم الحسابات تفوتر. اضغط طلب جديد.' %% so_name)
""" % {"prefix": MANDOUB_POS_PREFIX, "warehouse": FACTORY_WAREHOUSE_CODE}

CONFIRM_CODE = """
origin = record.origin or ''
if origin.startswith('%s') and not env.user.has_group('sales_team.group_sale_manager'):
    raise UserError('المدير فقط يؤكد طلبات المناديب. بعد التأكيد المخازن توصل ثم الحسابات تفوتر.')
""" % MANDOUB_POS_PREFIX

KITCHEN_MOVE_CODE = """
origin = record.origin or ''
if not origin.startswith('%(prefix)s'):
    pass
else:
    seq = %(sequence)s
    preps = env['pos_preparation_display.order'].search([('pdis_general_note', 'ilike', record.name)])
    for prep in preps:
        for ost in prep.order_stage_ids:
            stages = env['pos_preparation_display.stage'].search([('preparation_display_id', '=', ost.preparation_display_id.id)], order='sequence, id')
            if len(stages) >= seq:
                prep.change_order_stage(stages[seq - 1].id, ost.preparation_display_id.id)
"""

KITCHEN_PICKING_CODE = """
sale = record.sale_id
if not sale and record.group_id:
    sale = env['sale.order'].search([('procurement_group_id', '=', record.group_id.id)], limit=1)
origin = sale.origin or '' if sale else ''
if sale and origin.startswith('%s'):
    preps = env['pos_preparation_display.order'].search([('pdis_general_note', 'ilike', sale.name)])
    for prep in preps:
        for ost in prep.order_stage_ids:
            stages = env['pos_preparation_display.stage'].search([('preparation_display_id', '=', ost.preparation_display_id.id)], order='sequence, id')
            if len(stages) >= 3:
                prep.change_order_stage(stages[2].id, ost.preparation_display_id.id)
""" % MANDOUB_POS_PREFIX

KITCHEN_INVOICE_CODE = """
origin_ok = False
sales = record.invoice_line_ids.mapped('sale_line_ids').mapped('order_id')
for sale in sales:
    origin = sale.origin or ''
    if not origin.startswith('%s'):
        continue
    origin_ok = True
    preps = env['pos_preparation_display.order'].search([('pdis_general_note', 'ilike', sale.name)])
    for prep in preps:
        for ost in prep.order_stage_ids:
            stages = env['pos_preparation_display.stage'].search([('preparation_display_id', '=', ost.preparation_display_id.id)], order='sequence, id')
            if len(stages) >= 4:
                prep.change_order_stage(stages[3].id, ost.preparation_display_id.id)
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


def _norm_ar(text: str) -> str:
    return normalize_arabic_name(text)


def employee_from_pos_name(client: OdooClient, pos_name: str, company_id: int, manager_uid: int) -> dict | None:
    suffix = pos_name.split("—", 1)[-1].strip() if "—" in pos_name else pos_name
    needle = _norm_ar(suffix)
    if not needle:
        return None
    employees = client.execute(
        "hr.employee",
        "search_read",
        [("company_id", "=", company_id), ("user_id", "!=", False)],
        fields=["name", "user_id"],
    )
    scored = []
    for emp in employees:
        if emp.get("user_id") and emp["user_id"][0] == manager_uid:
            continue
        hay = _norm_ar(emp["name"])
        if needle in hay or hay.startswith(needle.split()[0]):
            scored.append(emp)
    if len(scored) == 1:
        return scored[0]
    token = needle.split()[0]
    token_hits = [emp for emp in scored if token and token in _norm_ar(emp["name"])]
    if len(token_hits) == 1:
        return token_hits[0]
    return scored[0] if scored else None


def cashier_for_config(
    client: OdooClient,
    config: dict,
    users_by_config: dict[int, int],
    company_id: int,
    manager_uid: int,
) -> tuple[dict | None, int | None]:
    user_id = users_by_config.get(config["id"])
    if user_id == manager_uid:
        user_id = None
    if not user_id and config.get("current_user_id") and config["current_user_id"][0] != manager_uid:
        user_id = config["current_user_id"][0]
    cashier = employee_for_user(client, user_id, company_id) if user_id else None
    if cashier:
        return cashier, user_id
    cashier = employee_from_pos_name(client, config["name"], company_id, manager_uid)
    user_id = cashier["user_id"][0] if cashier and cashier.get("user_id") else user_id
    return cashier, user_id


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


def session_has_orders(client: OdooClient, config: dict) -> bool:
    session_id = config.get("current_session_id")
    if not session_id:
        return False
    return bool(client.execute("pos.order", "search_count", [("session_id", "=", session_id[0])]))


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
        cashier, user_id = cashier_for_config(client, config, users_by_config, company_id, manager_uid)
        if user_id:
            users_by_config[config["id"]] = user_id
        if not cashier:
            log.append("No employee linked to POS %s" % config["name"])
            continue
        advanced_ids = [cashier["id"]]
        if manager and manager["id"] not in advanced_ids:
            advanced_ids.append(manager["id"])
        vals = {
            "module_pos_hr": True,
            "basic_employee_ids": [(6, 0, [cashier["id"]])],
            "advanced_employee_ids": [(6, 0, advanced_ids)],
        }
        skip_payment = session_has_orders(client, config)
        if not skip_payment:
            vals["payment_method_ids"] = [(6, 0, [credit_id])]
        try:
            client.execute("pos.config", "write", [config["id"]], vals)
        except xmlrpc.client.Fault as err:
            if "payment_method_ids" not in vals:
                raise
            # Open sessions with orders block payment-method changes.
            vals.pop("payment_method_ids", None)
            client.execute("pos.config", "write", [config["id"]], vals)
            log.append(
                "Cashier %s = %s (آجل unchanged; session has orders: %s)"
                % (config["name"], cashier["name"], err.faultString[:120])
            )
            continue
        if skip_payment:
            log.append(
                "Cashier %s = %s, آجل skipped because the session already has orders"
                % (config["name"], cashier["name"])
            )
        else:
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
        cashier, user_id = cashier_for_config(client, config, users_by_config, company_id, client.uid)
        if user_id:
            users_by_config[config["id"]] = user_id
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
        {
            "pos_config_ids": [(6, 0, pos_ids)],
            "category_ids": [(6, 0, client.execute("pos.category", "search", []) or [])],
        },
    )
    return log


def _delete_kitchen_display(client: OdooClient, display_id: int) -> None:
    """Drop a leftover screen without touching POS sessions."""
    stages = client.execute(
        "pos_preparation_display.order.stage",
        "search",
        [("preparation_display_id", "=", display_id)],
    )
    if stages:
        client.execute("pos_preparation_display.order.stage", "unlink", stages)
    display_stages = client.execute(
        "pos_preparation_display.stage",
        "search",
        [("preparation_display_id", "=", display_id)],
    )
    if display_stages:
        try:
            client.execute("pos_preparation_display.stage", "unlink", display_stages)
        except Exception:
            pass
    client.execute("pos_preparation_display.display", "unlink", [display_id])


def consolidate_kitchen_to_shared_session(
    client: OdooClient, company_id: int, pos_ids: list[int]
) -> list[str]:
    """One kitchen session (مناديب) for every mandoub POS. Remove per-cashier screens."""
    log: list[str] = []
    log.extend(ensure_display(client, SHARED_KITCHEN_NAME, company_id, pos_ids))
    displays = client.execute(
        "pos_preparation_display.display",
        "search_read",
        [("company_id", "=", company_id)],
        fields=["id", "name"],
    )
    removed = 0
    for row in displays:
        name = row.get("name") or ""
        if not is_per_cashier_kitchen_name(name):
            continue
        try:
            _delete_kitchen_display(client, row["id"])
            removed += 1
            log.append("Removed per-cashier kitchen screen %s" % name)
        except Exception as exc:  # noqa: BLE001
            log.append("Could not remove kitchen screen %s: %s" % (name, exc))
    if removed:
        log.append("Kitchen cards now live in one session: %s" % SHARED_KITCHEN_NAME)
    else:
        leftovers = [row["name"] for row in displays if is_per_cashier_kitchen_name(row.get("name") or "")]
        if leftovers:
            log.append("Per-cashier kitchen screens still present: %s" % ", ".join(leftovers))
        else:
            log.append("Kitchen already uses one session: %s" % SHARED_KITCHEN_NAME)
    show_rules = client.execute("ir.rule", "search", [("name", "=", RULE_KITCHEN_SHOW)])
    if show_rules:
        _write_translated(
            client,
            "ir.rule",
            show_rules,
            {"domain_force": kitchen_record_show_domain()},
        )
        log.append("Kitchen menu lists only %s" % SHARED_KITCHEN_NAME)
    return log


def sync_all_mandoub_displays(client: OdooClient, company_id: int) -> list[str]:
    """Rename/create the 4 kitchen stages on every mandoub display, including leftovers."""
    log: list[str] = []
    displays = client.execute(
        "pos_preparation_display.display",
        "search_read",
        [("company_id", "=", company_id)],
        fields=["id", "name"],
    )
    for row in displays:
        name = row.get("name") or ""
        if name != SHARED_KITCHEN_NAME and "مندوب" not in name:
            continue
        log.extend(sync_stages(client, row["id"]))
        log.append("Updated display %s" % name)
    return log


def _rename_automations(client: OdooClient, domain: list, new_name: str) -> list[str]:
    found = client.execute("base.automation", "search", domain)
    if not found:
        return []
    for lang in ("ar_001", "en_US"):
        client.execute(
            "base.automation",
            "write",
            found,
            {"name": new_name},
            context={"lang": lang},
        )
    autos = client.execute("base.automation", "read", found, ["action_server_ids"])
    action_ids: list[int] = []
    for row in autos:
        action_ids.extend(row.get("action_server_ids") or [])
    if action_ids:
        for lang in ("ar_001", "en_US"):
            client.execute(
                "ir.actions.server",
                "write",
                action_ids,
                {"name": new_name},
                context={"lang": lang},
            )
    return ["Renamed automation(s) %s -> %s" % (found, new_name)]


def align_kitchen_automation_names(client: OdooClient) -> list[str]:
    """Match live kitchen automations by model so leftover Arabic names get renamed."""
    log: list[str] = []
    sale_model = _model_id(client, "sale.order")
    picking_model = _model_id(client, "stock.picking")
    move_model = _model_id(client, "account.move")
    log.extend(
        _rename_automations(
            client,
            [
                ("model_id", "=", sale_model),
                ("name", "ilike", "شاشة المطبخ"),
            ],
            KITCHEN_CONFIRM_AUTOMATION_NAME,
        )
    )
    log.extend(
        _rename_automations(
            client,
            [("model_id", "=", picking_model), ("name", "ilike", "شاشة المطبخ")],
            KITCHEN_DELIVERY_AUTOMATION_NAME,
        )
    )
    log.extend(
        _rename_automations(
            client,
            [("model_id", "=", move_model), ("name", "ilike", "شاشة المطبخ")],
            KITCHEN_INVOICE_AUTOMATION_NAME,
        )
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
        for lang in ("ar_001", "en_US"):
            client.execute(
                "base.automation",
                "write",
                [auto_id],
                vals,
                context={"lang": lang},
            )
        action_ids = existing[0].get("action_server_ids") or []
        if action_ids:
            for lang in ("ar_001", "en_US"):
                client.execute(
                    "ir.actions.server",
                    "write",
                    action_ids,
                    {"state": "code", "code": code, "name": name},
                    context={"lang": lang},
                )
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
    log.extend(align_kitchen_automation_names(client))
    log.append(
        _ensure_code_automation(
            client,
            KITCHEN_CONFIRM_AUTOMATION_NAME,
            "sale.order",
            "on_state_set",
            KITCHEN_MOVE_CODE % {"prefix": MANDOUB_POS_PREFIX, "sequence": 2},
            extra=extra,
        )
    )
    picking_extra = {"filter_domain": "[('state', '=', 'done')]"}
    picking_field = client.execute(
        "ir.model.fields",
        "search_read",
        [("model", "=", "stock.picking"), ("name", "=", "state")],
        fields=["id"],
    )
    if picking_field:
        picking_extra["trigger_field_ids"] = [(6, 0, [picking_field[0]["id"]])]
        done_sel = client.execute(
            "ir.model.fields.selection",
            "search_read",
            [("field_id", "=", picking_field[0]["id"]), ("value", "=", "done")],
            fields=["id"],
        )
        if done_sel:
            picking_extra["trg_selection_field_id"] = done_sel[0]["id"]
    log.append(
        _ensure_code_automation(
            client,
            KITCHEN_DELIVERY_AUTOMATION_NAME,
            "stock.picking",
            "on_state_set",
            KITCHEN_PICKING_CODE,
            extra=picking_extra,
        )
    )
    invoice_extra = {"filter_domain": "[('state', '=', 'posted'), ('move_type', 'in', ['out_invoice', 'out_refund'])]"}
    invoice_field = client.execute(
        "ir.model.fields",
        "search_read",
        [("model", "=", "account.move"), ("name", "=", "state")],
        fields=["id"],
    )
    if invoice_field:
        invoice_extra["trigger_field_ids"] = [(6, 0, [invoice_field[0]["id"]])]
        posted_sel = client.execute(
            "ir.model.fields.selection",
            "search_read",
            [("field_id", "=", invoice_field[0]["id"]), ("value", "=", "posted")],
            fields=["id"],
        )
        if posted_sel:
            invoice_extra["trg_selection_field_id"] = posted_sel[0]["id"]
    log.append(
        _ensure_code_automation(
            client,
            KITCHEN_INVOICE_AUTOMATION_NAME,
            "account.move",
            "on_state_set",
            KITCHEN_INVOICE_CODE,
            extra=invoice_extra,
        )
    )
    log.append("Workflow: حفظ و طباعة → طلب → تم التأكيد → تم الشحن → الفوترة")
    log.append("Kitchen: طلب → تم التأكيد → تم الشحن → الفوترة")
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
    log.extend(consolidate_kitchen_to_shared_session(client, company_id, pos_ids))
    log.append("Kitchen stages: طلب → تم التأكيد → تم الشحن → الفوترة")
    log.extend(apply_quotation_workflow(client, company_id, pos_ids))
    return log


def _xmlid_id(client: OdooClient, module: str, name: str) -> int:
    rows = client.execute(
        "ir.model.data",
        "search_read",
        [("module", "=", module), ("name", "=", name)],
        fields=["res_id"],
        limit=1,
    )
    if not rows:
        raise SystemExit("XMLID not found: %s.%s" % (module, name))
    return rows[0]["res_id"]


def _write_translated(client: OdooClient, model: str, ids: list[int], vals: dict) -> None:
    for lang in ("ar_001", "en_US"):
        client.execute(model, "write", ids, vals, context={"lang": lang})


def _param_get(client: OdooClient, key: str) -> str:
    rows = client.execute(
        "ir.config_parameter",
        "search_read",
        [("key", "=", key)],
        fields=["value"],
        limit=1,
    )
    return (rows[0]["value"] if rows else "") or ""


def _param_set(client: OdooClient, key: str, value: str) -> None:
    existing = client.execute("ir.config_parameter", "search", [("key", "=", key)])
    if existing:
        client.execute("ir.config_parameter", "write", existing, {"value": value})
    else:
        client.execute("ir.config_parameter", "create", {"key": key, "value": value})


def _ensure_setup_group(client: OdooClient, admin_uid: int) -> int:
    rows = client.execute(
        "res.groups",
        "search_read",
        [("name", "=", SETUP_GROUP_NAME)],
        fields=["id", "users"],
    )
    vals = {
        "name": SETUP_GROUP_NAME,
        "comment": SETUP_GROUP_COMMENT,
        "users": [(6, 0, [admin_uid])],
    }
    if rows:
        group_id = rows[0]["id"]
        _write_translated(client, "res.groups", [group_id], vals)
        return group_id
    group_id = client.execute("res.groups", "create", vals)
    _write_translated(
        client,
        "res.groups",
        [group_id],
        {"name": SETUP_GROUP_NAME, "comment": SETUP_GROUP_COMMENT},
    )
    return group_id


def _ensure_rule(
    client: OdooClient,
    name: str,
    model_name: str,
    domain: str,
    group_ids: list[int],
) -> int:
    model_id = _model_id(client, model_name)
    rows = client.execute(
        "ir.rule",
        "search_read",
        [("name", "=", name), ("model_id", "=", model_id)],
        fields=["id"],
    )
    vals = {
        "name": name,
        "model_id": model_id,
        "domain_force": domain,
        "groups": [(6, 0, group_ids)],
        "perm_read": True,
        "perm_write": True,
        "perm_create": True,
        "perm_unlink": True,
        "active": True,
    }
    if rows:
        rule_id = rows[0]["id"]
        _write_translated(client, "ir.rule", [rule_id], vals)
        return rule_id
    rule_id = client.execute("ir.rule", "create", vals)
    _write_translated(client, "ir.rule", [rule_id], {"name": name})
    return rule_id


def _mandoub_configs(client: OdooClient, company_id: int) -> list[dict]:
    rows = client.execute(
        "pos.config",
        "search_read",
        [("company_id", "=", company_id)],
        fields=["id", "name", "basic_employee_ids", "advanced_employee_ids"],
        context={"active_test": False},
    )
    return [row for row in rows if is_mandoub_pos_name(row["name"])]


def restrict_mandoub_to_admin(client: OdooClient, company_id: int, admin_uid: int) -> list[str]:
    """Hide mandoub POS + kitchen from everyone except admin_uid. Reversible."""
    log: list[str] = []
    previous = _param_get(client, ACCESS_LOCK_PARAM)
    backup = json.loads(previous) if previous else {}
    if not isinstance(backup, dict):
        backup = {}

    group_id = _ensure_setup_group(client, admin_uid)
    pos_user = _xmlid_id(client, *POS_USER_GROUP_XMLID)
    pos_manager = _xmlid_id(client, *POS_MANAGER_GROUP_XMLID)
    pos_menu = _xmlid_id(client, *POS_ROOT_MENU_XMLID)
    kitchen_menu = _xmlid_id(client, *KITCHEN_MENU_XMLID)

    menus = client.execute(
        "ir.ui.menu",
        "read",
        [pos_menu, kitchen_menu],
        ["id", "groups_id"],
    )
    menu_groups = backup.get("menu_groups") or {}
    for menu in menus:
        menu_groups.setdefault(str(menu["id"]), list(menu["groups_id"] or []))

    employee_backup = backup.get("employees") or {}
    manager_emp = employee_for_user(client, admin_uid, company_id)
    manager_emp_id = manager_emp["id"] if manager_emp else False
    configs = _mandoub_configs(client, company_id)
    for config in configs:
        key = str(config["id"])
        employee_backup.setdefault(
            key,
            {
                "basic": list(config.get("basic_employee_ids") or []),
                "advanced": list(config.get("advanced_employee_ids") or []),
            },
        )
        vals = {
            "basic_employee_ids": [(6, 0, [manager_emp_id] if manager_emp_id else [])],
            "advanced_employee_ids": [(6, 0, [manager_emp_id] if manager_emp_id else [])],
        }
        client.execute("pos.config", "write", [config["id"]], vals)
    log.append("Restricted cashiers on %s mandoub POS configs to admin only" % len(configs))

    displays = client.execute(
        "pos_preparation_display.display",
        "search_read",
        [("company_id", "=", company_id)],
        fields=["id", "name"],
    )
    kitchen_ids = [row["id"] for row in displays if is_restricted_kitchen_name(row["name"])]
    rotated = 0
    for display_id in kitchen_ids:
        try:
            client.execute(
                "pos_preparation_display.display",
                "write",
                [display_id],
                {"access_token": str(uuid.uuid4())},
            )
            rotated += 1
        except Exception as exc:  # noqa: BLE001
            log.append("Could not rotate kitchen token %s: %s" % (display_id, exc))
    if rotated:
        log.append("Rotated %s kitchen display tokens" % rotated)

    rule_ids = []
    for model_name, rule_name, domain, kind in setup_access_rule_specs():
        groups = [group_id] if kind == "show" else [pos_user, pos_manager]
        rule_ids.append(_ensure_rule(client, rule_name, model_name, domain, groups))
    log.append("Applied %s record rules hiding mandoub POS/kitchen" % len(rule_ids))

    client.execute("ir.ui.menu", "write", [pos_menu], {"groups_id": [(6, 0, [group_id])]})
    client.execute("ir.ui.menu", "write", [kitchen_menu], {"groups_id": [(6, 0, [group_id])]})
    log.append("Hid Point of Sale and kitchen menus except for %s" % SETUP_GROUP_NAME)

    payload = {
        "restricted": True,
        "admin_uid": admin_uid,
        "group_id": group_id,
        "rule_ids": rule_ids,
        "menu_groups": menu_groups,
        "employees": employee_backup,
        "pos_menu_id": pos_menu,
        "kitchen_menu_id": kitchen_menu,
    }
    _param_set(client, ACCESS_LOCK_PARAM, json.dumps(payload, ensure_ascii=False))
    log.append("Mandoub POS and kitchen are visible only to user %s" % admin_uid)
    return log


def restore_mandoub_access(client: OdooClient, company_id: int) -> list[str]:
    """Undo restrict_mandoub_to_admin using the stored backup."""
    log: list[str] = []
    raw = _param_get(client, ACCESS_LOCK_PARAM)
    backup = json.loads(raw) if raw else {}
    if not isinstance(backup, dict):
        backup = {}

    for _model_name, rule_name, _domain, _kind in setup_access_rule_specs():
        found = client.execute("ir.rule", "search", [("name", "=", rule_name)])
        if found:
            client.execute("ir.rule", "unlink", found)
            log.append("Removed rule %s" % rule_name)

    pos_user = _xmlid_id(client, *POS_USER_GROUP_XMLID)
    pos_manager = _xmlid_id(client, *POS_MANAGER_GROUP_XMLID)
    pos_menu = backup.get("pos_menu_id") or _xmlid_id(client, *POS_ROOT_MENU_XMLID)
    kitchen_menu = backup.get("kitchen_menu_id") or _xmlid_id(client, *KITCHEN_MENU_XMLID)
    menu_groups = backup.get("menu_groups") or {}
    pos_groups = menu_groups.get(str(pos_menu), [pos_manager, pos_user])
    kitchen_groups = menu_groups.get(str(kitchen_menu), [])
    client.execute("ir.ui.menu", "write", [pos_menu], {"groups_id": [(6, 0, pos_groups)]})
    client.execute("ir.ui.menu", "write", [kitchen_menu], {"groups_id": [(6, 0, kitchen_groups)]})
    log.append("Restored Point of Sale and kitchen menus")

    employees = backup.get("employees") or {}
    restored = 0
    for config_id, lists in employees.items():
        try:
            cid = int(config_id)
        except (TypeError, ValueError):
            continue
        client.execute(
            "pos.config",
            "write",
            [cid],
            {
                "basic_employee_ids": [(6, 0, lists.get("basic") or [])],
                "advanced_employee_ids": [(6, 0, lists.get("advanced") or [])],
            },
        )
        restored += 1
    if not employees:
        manager_uid = backup.get("admin_uid") or client.uid
        manager_emp = employee_for_user(client, manager_uid, company_id)
        manager_emp_id = manager_emp["id"] if manager_emp else False
        for config in _mandoub_configs(client, company_id):
            cashier, _user_id = cashier_for_config(client, config, {}, company_id, manager_uid)
            cashier_id = cashier["id"] if cashier else False
            advanced = [eid for eid in (manager_emp_id, cashier_id) if eid]
            basic = [cashier_id] if cashier_id else []
            client.execute(
                "pos.config",
                "write",
                [config["id"]],
                {
                    "basic_employee_ids": [(6, 0, basic)],
                    "advanced_employee_ids": [(6, 0, advanced)],
                },
            )
            restored += 1
    log.append("Restored cashiers on %s POS configs" % restored)

    _param_set(
        client,
        ACCESS_LOCK_PARAM,
        json.dumps({"restricted": False, "group_id": backup.get("group_id")}, ensure_ascii=False),
    )
    log.append("Mandoub POS and kitchen are visible to cashiers again")
    return log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure Brodansh mandoub POS + kitchen screens")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--kitchen-only",
        action="store_true",
        help="Put every mandoub order on the shared مناديب kitchen session without touching POS sessions.",
    )
    parser.add_argument(
        "--restrict-to-admin",
        action="store_true",
        help="Hide mandoub POS and kitchen from everyone except the API user (Waleed).",
    )
    parser.add_argument(
        "--restore-access",
        action="store_true",
        help="Undo --restrict-to-admin and show POS/kitchen to cashiers again.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(Path(args.env_file))
    if args.dry_run:
        company_name = os.getenv("ODOO_COMPANY_NAME", "مصنع ذو الجناحين للملابس الجاهزة").strip()
        print("Dry run: would use company=%s" % company_name)
        print("Kitchen stages:", ", ".join(spec["name"] for spec in stage_spec_list()))
        print("Shared kitchen session:", SHARED_KITCHEN_NAME)
        print("Cashier: each mandoub employee")
        print("Flow: حفظ و طباعة → طلب → تم التأكيد → تم الشحن → الفوترة")
        print("Payment method (fallback only):", CREDIT_PAYMENT_NAME)
        if args.restrict_to_admin:
            print("Would hide POS + kitchen except for the API user")
        if args.restore_access:
            print("Would restore POS + kitchen visibility to cashiers")
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
    if args.restrict_to_admin and args.restore_access:
        raise SystemExit("Use either --restrict-to-admin or --restore-access, not both.")
    if args.restrict_to_admin:
        for line in restrict_mandoub_to_admin(client, company_id, client.uid):
            print(line)
        return
    if args.restore_access:
        for line in restore_mandoub_access(client, company_id):
            print(line)
        return
    if args.kitchen_only:
        configs = client.execute(
            "pos.config",
            "search_read",
            [("company_id", "=", company_id), ("active", "=", True)],
            fields=["name"],
        )
        mandoub = [row for row in configs if is_mandoub_pos_name(row["name"])]
        pos_ids = [row["id"] for row in mandoub]
        logs = []
        logs.extend(consolidate_kitchen_to_shared_session(client, company_id, pos_ids))
        logs.extend(apply_quotation_workflow(client, company_id, pos_ids))
        for line in logs:
            print(line)
        return
    for line in configure(client, company_id):
        print(line)


if __name__ == "__main__":
    main()
