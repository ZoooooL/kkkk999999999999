"""Opening-balance helpers for the partner ledger PDF.

The live database imports this module as data, so Python may not load.
The QWeb template mirrors these rules with `o.env` queries. Keep both in sync.
"""

from __future__ import annotations

from datetime import date, datetime


OPENING_LABEL = "الرصيد الافتتاحي"
CLOSING_LABEL = "الرصيد النهائي"
COMPANY_LABEL = "الشركة"

# Wizard constants: start of the current calendar year, opening always on.
YEAR_START_MONTH = 1
YEAR_START_DAY = 1
SHOW_OPENING_BALANCE = True


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text in ("False", "None"):
        return None
    return date.fromisoformat(text[:10])


def year_start_date(today=None):
    """First day of the current calendar year (تاريخ بداية العام)."""
    today = _as_date(today) or date.today()
    return date(today.year, YEAR_START_MONTH, YEAR_START_DAY)


def year_start_iso(today=None):
    return year_start_date(today).isoformat()


def effective_date_from(form, today=None):
    """Use the wizard start date, otherwise the year-start constant."""
    return _as_date((form or {}).get("date_from")) or year_start_date(today)


def effective_date_from_iso(form, today=None):
    value = (form or {}).get("date_from")
    parsed = _as_date(value)
    if parsed:
        return parsed.isoformat()
    return year_start_iso(today)


def wizard_create_defaults(date_from=None, show_opening=None, today=None):
    """Defaults applied when the partner-ledger wizard is opened."""
    vals = {}
    if not _as_date(date_from):
        vals["date_from"] = year_start_date(today)
    if show_opening is None:
        vals["x_show_opening_balance"] = SHOW_OPENING_BALANCE
    return vals


def account_types_for_selection(result_selection):
    if result_selection == "supplier":
        return ["liability_payable"]
    if result_selection == "customer":
        return ["asset_receivable"]
    return ["asset_receivable", "liability_payable"]


def move_states_for_target(target_move):
    if target_move == "posted":
        return ["posted"]
    return ["draft", "posted"]


def company_id_from_form(form):
    used = form.get("used_context") or {}
    if used.get("company_id"):
        return used["company_id"]
    company = form.get("company_id")
    if isinstance(company, (list, tuple)) and company:
        return company[0]
    if isinstance(company, int):
        return company
    return False


def opening_domain(
    partner_id,
    date_from,
    company_id,
    account_types,
    journal_ids,
    move_states,
    include_reconciled,
):
    """Domain for posted (or all) partner AR/AP lines strictly before date_from."""
    domain = [
        ("partner_id", "=", partner_id),
        ("parent_state", "in", list(move_states)),
        ("account_id.account_type", "in", list(account_types)),
        ("display_type", "not in", ("line_section", "line_note")),
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))
    if date_from:
        domain.append(("date", "<", date_from))
    if journal_ids:
        domain.append(("journal_id", "in", list(journal_ids)))
    if not include_reconciled:
        domain.append(("full_reconcile_id", "=", False))
    return domain


def opening_from_group(group_rows):
    row = group_rows[0] if group_rows else {}
    debit = float(row.get("debit") or 0.0)
    credit = float(row.get("credit") or 0.0)
    return debit, credit, debit - credit


def should_show_opening(form, wizard_flag=None):
    """Use form data when present; otherwise the opening-balance constant."""
    form = form or {}
    if form.get("x_show_opening_balance") is not None:
        return bool(form.get("x_show_opening_balance"))
    if wizard_flag is not None:
        return bool(wizard_flag)
    return SHOW_OPENING_BALANCE


def adjust_line_progress(period_lines, opening_balance):
    adjusted = []
    for line in period_lines or []:
        row = dict(line)
        row["progress"] = float(row.get("progress") or 0.0) + float(opening_balance or 0.0)
        adjusted.append(row)
    return adjusted


def footer_totals(opening_debit, opening_credit, period_debit, period_credit):
    debit = float(opening_debit or 0.0) + float(period_debit or 0.0)
    credit = float(opening_credit or 0.0) + float(period_credit or 0.0)
    return debit, credit, debit - credit


ZERO_EPS = 0.004


def is_zero_amount(value):
    return abs(float(value or 0.0)) <= ZERO_EPS


def net_side_amounts(balance):
    """Show a net balance on debit or credit only; zeros stay empty."""
    bal = float(balance or 0.0)
    if bal > ZERO_EPS:
        return bal, 0.0
    if bal < -ZERO_EPS:
        return 0.0, -bal
    return 0.0, 0.0


def keep_partner_statement(balance):
    return not is_zero_amount(balance)


def ids_from_form_m2m(value):
    """Normalize a many2many value from wizard `read()` / form data to a list of ids."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if isinstance(item, int):
                out.append(item)
            elif isinstance(item, (list, tuple)) and item:
                out.append(item[0])
            elif isinstance(item, dict) and item.get("id"):
                out.append(item["id"])
        return out
    if isinstance(value, int):
        return [value]
    return []


def filter_partner_ids_by_tags(selected_partner_ids, tagged_partner_ids, tag_ids):
    """If tags are set, keep tagged partners; intersect when partners were also chosen."""
    if not tag_ids:
        return list(selected_partner_ids or [])
    tagged = list(tagged_partner_ids or [])
    if selected_partner_ids:
        selected = set(selected_partner_ids)
        return [pid for pid in tagged if pid in selected]
    return tagged


def partner_has_tags(partner_tag_ids, tag_ids):
    if not tag_ids:
        return True
    wanted = set(tag_ids)
    return any(tid in wanted for tid in (partner_tag_ids or []))
