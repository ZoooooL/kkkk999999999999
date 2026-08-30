# -*- coding: utf-8 -*-

MANDOUB_POS_PREFIX = "مندوب —"
KITCHEN_DISPLAY_PREFIX = "شاشة "
SHARED_KITCHEN_NAME = "مناديب"
CREDIT_PAYMENT_NAME = "آجل"
CREDIT_PAYMENT_TERM_NAME = "30 يوماً"
FACTORY_WAREHOUSE_CODE = "WH-MS"

KITCHEN_STAGES = [
    {"name": "التأكيد", "color": "#198754", "alert_timer": 15, "sequence": 1},
    {"name": "التوصيل", "color": "#0d6efd", "alert_timer": 30, "sequence": 2},
    {"name": "الفوترة", "color": "#6f42c1", "alert_timer": 10, "sequence": 3},
]
KITCHEN_NOTE_PREFIX = "[طلب]"

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
DEFAULT_PACK_QTY = 12
PACKAGING_NAME = "تعبئة 12"


def normalize_cat_name(name):
    return " ".join((name or "").replace("ـ", "").split())


def sales_pack_qtys(packagings):
    """Positive sales-pack quantities from product.packaging rows or dicts."""
    qtys = []
    for pack in packagings or []:
        if isinstance(pack, dict):
            if pack.get("sales") is False:
                continue
            qty = pack.get("qty")
        else:
            qty = pack
        if qty:
            qtys.append(qty)
    return qtys


def choose_pack_qty(pack_qtys, qty_on_hand=None, fallback=DEFAULT_PACK_QTY, already_in_cart=0):
    """Qty to add on one POS click.

    If the product has several sales packs (12 / 24 / 36), pick the largest pack
    that still fits in remaining qty on hand. Unknown stock keeps the smallest
    pack so a click does not oversell. Leftover below the smallest pack is added
    as-is. Empty stock still uses the smallest pack so a quotation can be created.
    """
    qtys = [qty for qty in (pack_qtys or []) if qty]
    remaining = None
    if qty_on_hand is not None:
        try:
            remaining = float(qty_on_hand) - float(already_in_cart or 0)
        except (TypeError, ValueError):
            remaining = None
    if not qtys:
        if remaining is not None and 0 < remaining < fallback:
            return remaining
        return fallback
    if remaining is None:
        return min(qtys)
    fitting = [qty for qty in qtys if qty <= remaining]
    if fitting:
        return max(fitting)
    if remaining > 0:
        return remaining
    return min(qtys)


def default_pos_qty(packagings, qty_on_hand=None, fallback=DEFAULT_PACK_QTY, already_in_cart=0):
    """Qty to add on one POS click from packaging records and warehouse stock."""
    return choose_pack_qty(
        sales_pack_qtys(packagings),
        qty_on_hand=qty_on_hand,
        fallback=fallback,
        already_in_cart=already_in_cart,
    )


def is_mandoub_pos_name(name):
    return bool(name) and name.startswith(MANDOUB_POS_PREFIX)


def normalize_arabic_name(text):
    return (text or "").replace("ـ", "").replace("  ", " ").strip()


def kitchen_display_name_for_pos(pos_name):
    return "%s%s" % (KITCHEN_DISPLAY_PREFIX, pos_name)


def kitchen_card_note(so_name, partner_name="", salesperson_name=""):
    parts = [KITCHEN_NOTE_PREFIX, so_name]
    if partner_name:
        parts.append(partner_name)
    if salesperson_name:
        parts.append(salesperson_name)
    return " | ".join(parts)


def kitchen_stage_index(order_state, delivery_done=False, invoiced=False):
    """0=التأكيد, 1=التوصيل, 2=الفوترة"""
    if invoiced or delivery_done:
        return 2
    if order_state == "sale":
        return 1
    return 0


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
