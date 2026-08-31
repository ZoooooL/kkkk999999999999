# -*- coding: utf-8 -*-

MANDOUB_POS_PREFIX = "مندوب —"
KITCHEN_DISPLAY_PREFIX = "شاشة "
SHARED_KITCHEN_NAME = "مناديب"
MANDOUB_NAME_NEEDLE = "مندوب"
SETUP_GROUP_NAME = "ضبط نقاط بيع المناديب"
SETUP_GROUP_COMMENT = (
    "أثناء ضبط نقاط بيع المناديب وشاشة المطبخ: تظهر لصاحب هذه المجموعة فقط."
)
ACCESS_LOCK_PARAM = "brodansh_mandoub.setup_access_lock"
POS_ROOT_MENU_XMLID = ("point_of_sale", "menu_point_root")
KITCHEN_MENU_XMLID = ("point_of_sale", "menu_pos_preparation_display")
POS_USER_GROUP_XMLID = ("point_of_sale", "group_pos_user")
POS_MANAGER_GROUP_XMLID = ("point_of_sale", "group_pos_manager")
POS_CATEGORY_XMLID = ("base", "module_category_point_of_sale")

RULE_POS_CONFIG_HIDE = "مندوب: إخفاء نقاط البيع قيد الضبط"
RULE_POS_CONFIG_SHOW = "مندوب: إظهار نقاط البيع لمسؤول الضبط"
RULE_POS_SESSION_HIDE = "مندوب: إخفاء جلسات نقاط البيع قيد الضبط"
RULE_POS_SESSION_SHOW = "مندوب: إظهار جلسات نقاط البيع لمسؤول الضبط"
RULE_POS_ORDER_HIDE = "مندوب: إخفاء طلبات نقاط البيع قيد الضبط"
RULE_POS_ORDER_SHOW = "مندوب: إظهار طلبات نقاط البيع لمسؤول الضبط"
RULE_KITCHEN_HIDE = "مندوب: إخفاء شاشات المطبخ قيد الضبط"
RULE_KITCHEN_SHOW = "مندوب: إظهار شاشات المطبخ لمسؤول الضبط"
RULE_KITCHEN_ORDER_HIDE = "مندوب: إخفاء بطاقات المطبخ قيد الضبط"
RULE_KITCHEN_ORDER_SHOW = "مندوب: إظهار بطاقات المطبخ لمسؤول الضبط"
CREDIT_PAYMENT_NAME = "آجل"
CREDIT_PAYMENT_TERM_NAME = "30 يوماً"
FACTORY_WAREHOUSE_CODE = "WH-MS"

KITCHEN_STAGES = [
    {"name": "طلب", "color": "#fd7e14", "alert_timer": 15, "sequence": 1},
    {"name": "تم التأكيد", "color": "#198754", "alert_timer": 20, "sequence": 2},
    {"name": "تم الشحن", "color": "#0d6efd", "alert_timer": 30, "sequence": 3},
    {"name": "الفوترة", "color": "#6f42c1", "alert_timer": 10, "sequence": 4},
]
KITCHEN_NOTE_PREFIX = "[طلب]"
MANDOUB_SAVE_PRINT_LABEL = "حفظ و طباعة"
QUOTATION_REPORT_XMLID = "sale.action_report_saleorder"
QUOTATION_REPORT_NAME = "sale.report_saleorder"

MANDOUB_QUOTATION_CREATED_MSG = (
    "تم حفظ عرض السعر %s وطباعته. يظهر في المطبخ كطلب. "
    "مدير المبيعات يؤكد فيصبح أمر بيع (تم التأكيد)، ثم المستودع يشحّن (تم الشحن)، ثم الحسابات تفوتر."
)
MANAGER_CONFIRM_ONLY_MSG = (
    "المدير فقط يؤكد طلبات المناديب. بعد التأكيد المخازن توصل ثم الحسابات تفوتر."
)
POS_INVOICE_BLOCKED_MSG = (
    "نقطة بيع المندوب لا تُصدر فاتورة. أنشئ طلباً ليؤكده المدير."
)
DEFAULT_PACK_QTY = 12
PACKAGING_NAME = "تعبئة 12"
FINISHED_GOODS_CATEGORY_NAME = "منتج تام"


def normalize_cat_name(name):
    return " ".join((name or "").replace("ـ", "").split())


def is_finished_goods_category(complete_name, allowed_root=FINISHED_GOODS_CATEGORY_NAME):
    """True if the inventory category is منتج تام or one of its children."""
    name = normalize_cat_name(complete_name)
    root = normalize_cat_name(allowed_root)
    if not name or not root:
        return False
    return name == root or name.startswith(root + " /")


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


def pack_unit_qty(pack_qtys, fallback=DEFAULT_PACK_QTY):
    """One wholesale pack: the product's sales packaging, or 12 if none."""
    qtys = [qty for qty in (pack_qtys or []) if qty]
    return min(qtys) if qtys else fallback


def wholesale_line_qty(pack_qtys, pack_count=1, fallback=DEFAULT_PACK_QTY):
    """Numpad packs × packaging. 1 → 24, 3 × 24 → 72."""
    try:
        count = float(pack_count if pack_count not in (None, False, "") else 1)
    except (TypeError, ValueError):
        count = 1
    if count <= 0:
        count = 1
    return pack_unit_qty(pack_qtys, fallback=fallback) * count


def choose_pack_qty(pack_qtys, qty_on_hand=None, fallback=DEFAULT_PACK_QTY, already_in_cart=0):
    """Qty for one POS pack. Numpad count is applied by wholesale_line_qty."""
    return pack_unit_qty(pack_qtys, fallback=fallback)


def default_pos_qty(packagings, qty_on_hand=None, fallback=DEFAULT_PACK_QTY, already_in_cart=0):
    """Qty to add for one pack from packaging records."""
    return pack_unit_qty(sales_pack_qtys(packagings), fallback=fallback)


def is_mandoub_pos_name(name):
    return bool(name) and name.startswith(MANDOUB_POS_PREFIX)


def is_restricted_pos_name(name):
    """True for mandoub POS configs that stay hidden while setup is in progress."""
    return MANDOUB_NAME_NEEDLE in (name or "")


def is_restricted_kitchen_name(name):
    """True for mandoub kitchen screens, including the shared مناديب overview."""
    text = name or ""
    return MANDOUB_NAME_NEEDLE in text or SHARED_KITCHEN_NAME in text


def mandoub_record_hide_domain():
    return "[('name', 'not ilike', '%s')]" % MANDOUB_NAME_NEEDLE


def mandoub_record_show_domain():
    return "[('name', 'ilike', '%s')]" % MANDOUB_NAME_NEEDLE


def mandoub_session_hide_domain():
    return "[('config_id.name', 'not ilike', '%s')]" % MANDOUB_NAME_NEEDLE


def mandoub_session_show_domain():
    return "[('config_id.name', 'ilike', '%s')]" % MANDOUB_NAME_NEEDLE


def kitchen_record_hide_domain():
    return "['&', ('name', 'not ilike', '%s'), ('name', 'not ilike', '%s')]" % (
        MANDOUB_NAME_NEEDLE,
        SHARED_KITCHEN_NAME,
    )


def kitchen_record_show_domain():
    return "['|', ('name', 'ilike', '%s'), ('name', 'ilike', '%s')]" % (
        MANDOUB_NAME_NEEDLE,
        SHARED_KITCHEN_NAME,
    )


def kitchen_order_hide_domain():
    return "[('pos_config_id.name', 'not ilike', '%s')]" % MANDOUB_NAME_NEEDLE


def kitchen_order_show_domain():
    return "[('pos_config_id.name', 'ilike', '%s')]" % MANDOUB_NAME_NEEDLE


def setup_access_rule_specs():
    """Hide/show pairs applied while mandoub POS is being tuned."""
    return (
        ("pos.config", RULE_POS_CONFIG_HIDE, mandoub_record_hide_domain(), "hide"),
        ("pos.config", RULE_POS_CONFIG_SHOW, mandoub_record_show_domain(), "show"),
        ("pos.session", RULE_POS_SESSION_HIDE, mandoub_session_hide_domain(), "hide"),
        ("pos.session", RULE_POS_SESSION_SHOW, mandoub_session_show_domain(), "show"),
        ("pos.order", RULE_POS_ORDER_HIDE, mandoub_session_hide_domain(), "hide"),
        ("pos.order", RULE_POS_ORDER_SHOW, mandoub_session_show_domain(), "show"),
        (
            "pos_preparation_display.display",
            RULE_KITCHEN_HIDE,
            kitchen_record_hide_domain(),
            "hide",
        ),
        (
            "pos_preparation_display.display",
            RULE_KITCHEN_SHOW,
            kitchen_record_show_domain(),
            "show",
        ),
        (
            "pos_preparation_display.order",
            RULE_KITCHEN_ORDER_HIDE,
            kitchen_order_hide_domain(),
            "hide",
        ),
        (
            "pos_preparation_display.order",
            RULE_KITCHEN_ORDER_SHOW,
            kitchen_order_show_domain(),
            "show",
        ),
    )


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
    """0=طلب, 1=تم التأكيد, 2=تم الشحن, 3=الفوترة"""
    if invoiced:
        return 3
    if delivery_done:
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
    pack_qty = line.get("pack_qty")
    carton_qty = line.get("carton_qty")
    if carton_qty in (None, False):
        carton_qty = qty
    if pack_qty:
        qty = wholesale_line_qty([pack_qty], carton_qty, pack_qty)
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
    if pack_qty and carton_qty not in (None, False):
        extra = "%s كرتون × %s" % (
            int(carton_qty) if float(carton_qty).is_integer() else carton_qty,
            int(pack_qty) if float(pack_qty).is_integer() else pack_qty,
        )
        name = ("%s — %s" % (name, extra)) if name else extra
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
