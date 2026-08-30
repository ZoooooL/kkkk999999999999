# -*- coding: utf-8 -*-

MANDOUB_POS_PREFIX = "مندوب —"
KITCHEN_DISPLAY_PREFIX = "شاشة "
SHARED_KITCHEN_NAME = "مناديب"
CREDIT_PAYMENT_NAME = "آجل"
CREDIT_PAYMENT_TERM_NAME = "30 يوماً"
FACTORY_WAREHOUSE_CODE = "WH-MS"

KITCHEN_STAGES = [
    {"name": "مؤكد", "color": "#198754", "alert_timer": 15, "sequence": 1},
    {"name": "تم الشحن", "color": "#0d6efd", "alert_timer": 30, "sequence": 2},
    {"name": "الفوترة", "color": "#6f42c1", "alert_timer": 10, "sequence": 3},
]

MANDOUB_QUOTATION_CREATED_MSG = (
    "تم إنشاء الطلب %s. المندوب لا يفوتر ولا يستلم دفعاً. "
    "المدير يؤكد، ثم المخازن توصل، ثم الحسابات تفوتر."
)
MANAGER_CONFIRM_ONLY_MSG = (
    "المدير فقط يؤكد طلبات المناديب. بعد التأكيد المخازن توصل ثم الحسابات تفوتر."
)
POS_INVOICE_BLOCKED_MSG = (
    "نقطة بيع المندوب لا تُصدر فاتورة. أنشئ طلباً ليؤكده المدير."
)


def is_mandoub_pos_name(name):
    return bool(name) and name.startswith(MANDOUB_POS_PREFIX)


def kitchen_display_name_for_pos(pos_name):
    return "%s%s" % (KITCHEN_DISPLAY_PREFIX, pos_name)


def stage_spec_list():
    return [dict(item) for item in KITCHEN_STAGES]


def credit_payment_vals(company_id):
    return {
        "name": CREDIT_PAYMENT_NAME,
        "company_id": company_id,
        "journal_id": False,
        "split_transactions": True,
        "payment_method_type": "none",
    }


def is_mandoub_origin(origin):
    return bool(origin) and origin.startswith(MANDOUB_POS_PREFIX)


def _as_id(value):
    if value in (None, False, 0, "0"):
        return False
    if isinstance(value, dict):
        return _as_id(value.get("id"))
    if isinstance(value, (list, tuple)):
        if not value:
            return False
        return _as_id(value[0])
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


def iter_pos_line_vals(lines):
    """Normalize POS line payloads (Odoo 18 serialize or a flat cart dict)."""
    for item in lines or []:
        if isinstance(item, (list, tuple)) and len(item) >= 3 and isinstance(item[2], dict):
            yield item[2]
        elif isinstance(item, dict):
            yield item


def quotation_line_command(line, sequence):
    product_id = _as_id(line.get("product_id") or line.get("productId"))
    if not product_id:
        return None
    qty = line.get("qty")
    if qty in (None, False):
        qty = line.get("product_uom_qty") or line.get("quantity") or 0
    price = line.get("price_unit")
    if price in (None, False):
        price = line.get("price") or 0
    discount = line.get("discount") or 0
    vals = {
        "sequence": sequence,
        "product_id": product_id,
        "product_uom_qty": qty,
        "price_unit": price,
        "discount": discount,
    }
    name = line.get("full_product_name") or line.get("customer_note")
    if name:
        vals["name"] = name
    return (0, 0, vals)


def quotation_vals_from_pos_cart(payload, defaults):
    """Build sale.order create vals from a POS cart payload. Pure Python."""
    partner_id = _as_id(payload.get("partner_id"))
    if not partner_id:
        raise ValueError("partner_required")
    order_lines = []
    sequence = 10
    for line in iter_pos_line_vals(payload.get("lines") or payload.get("line_ids")):
        command = quotation_line_command(line, sequence)
        if command:
            order_lines.append(command)
            sequence += 10
    if not order_lines:
        raise ValueError("empty_cart")
    vals = {
        "partner_id": partner_id,
        "origin": defaults.get("origin") or payload.get("origin") or "",
        "client_order_ref": payload.get("uuid") or payload.get("client_order_ref") or payload.get("name") or False,
        "user_id": _as_id(payload.get("user_id")) or defaults.get("user_id") or False,
        "company_id": defaults.get("company_id"),
        "warehouse_id": defaults.get("warehouse_id") or False,
        "payment_term_id": defaults.get("payment_term_id") or False,
        "pricelist_id": _as_id(payload.get("pricelist_id")) or False,
        "fiscal_position_id": _as_id(payload.get("fiscal_position_id")) or False,
        "note": payload.get("note") or payload.get("general_note") or False,
        "order_line": order_lines,
    }
    team_id = defaults.get("team_id") or _as_id(payload.get("team_id"))
    if team_id:
        vals["team_id"] = team_id
    return {key: value for key, value in vals.items() if value not in (None,)}
