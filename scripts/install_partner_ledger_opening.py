#!/usr/bin/env python3
"""Apply Brodan partner-ledger opening-balance QWeb views on live Odoo.

The addon is imported as a data module, so Python does not load. This script
writes the QWeb/wizard views through XML-RPC (same xmlids as the imported
module) so the PDF shows الرصيد الافتتاحي without an addons_path install.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
import xmlrpc.client
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MODULE = "brodan_partner_ledger_opening"
MODULE_DIR = ROOT / MODULE
WIZARD_XML = MODULE_DIR / "views" / "partner_ledger_wizard.xml"
REPORT_XML = MODULE_DIR / "report" / "report_partner_ledger.xml"
TAG_FIELD_NAME = "x_partner_category_ids"
TAG_REL_TABLE = "x_account_report_pl_category_rel"
TAG_AUTOMATION_NAME = "دفتر الشركاء: تعبئة الشركاء من علامات التصنيف"
TAG_FILL_CODE = """
if env.context.get('brodan_pl_skip_tag_fill'):
    pass
else:
    tags = record.x_partner_category_ids
    if tags:
        tagged = env['res.partner'].search([('category_id', 'in', tags.ids)])
        if record.partner_ids:
            keep_ids = [pid for pid in record.partner_ids.ids if pid in tagged.ids]
        else:
            keep_ids = tagged.ids
        current_ids = record.partner_ids.ids
        if sorted(keep_ids) != sorted(current_ids):
            record.with_context(brodan_pl_skip_tag_fill=True).write({'partner_ids': [(6, 0, keep_ids)]})
"""


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


def module_version() -> str:
    data = ast.literal_eval((MODULE_DIR / "__manifest__.py").read_text(encoding="utf-8"))
    return data.get("version") or "18.0.1.7.0"


def inner_xml(element: ET.Element) -> str:
    parts = [element.text or ""]
    for child in list(element):
        parts.append(ET.tostring(child, encoding="unicode"))
    parts.append(element.tail or "")
    return "".join(parts).strip()


def template_arch(xml_path: Path, xml_id: str) -> str:
    tree = ET.parse(xml_path)
    for node in tree.getroot().iter():
        if node.tag in ("template", "{http://www.w3.org/1999/xhtml}template"):
            if node.attrib.get("id") == xml_id:
                inherit = node.attrib.get("inherit_id") or ""
                body = inner_xml(node)
                return (
                    '<data inherit_id="%s">\n%s\n</data>' % (inherit, body)
                    if inherit
                    else body
                )
        if node.tag == "record" and node.attrib.get("id") == xml_id:
            for field in node.findall("field"):
                if field.attrib.get("name") == "arch":
                    return inner_xml(field)
    raise SystemExit("Could not find arch for %s in %s" % (xml_id, xml_path))


def connect():
    load_dotenv(ROOT / ".env")
    url = require_env("ODOO_URL").rstrip("/")
    db = require_env("ODOO_DB")
    username = require_env("ODOO_USERNAME")
    password = require_env("ODOO_API_KEY")
    uid = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % url).authenticate(
        db, username, password, {}
    )
    if not uid:
        raise SystemExit("Odoo authentication failed")
    models = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % url)

    def execute(model, method, *args, **kwargs):
        return models.execute_kw(db, uid, password, model, method, list(args), kwargs)

    return execute


def upsert_xmlid(execute, xmlid: str, model: str, res_id: int) -> None:
    module, name = xmlid.split(".", 1)
    found = execute(
        "ir.model.data",
        "search_read",
        [["module", "=", module], ["name", "=", name]],
        fields=["res_id", "model"],
        limit=1,
    )
    if found:
        if found[0]["res_id"] != res_id or found[0]["model"] != model:
            execute(
                "ir.model.data",
                "write",
                [found[0]["id"]],
                {"res_id": res_id, "model": model, "noupdate": False},
            )
        return
    execute(
        "ir.model.data",
        "create",
        {
            "module": module,
            "name": name,
            "model": model,
            "res_id": res_id,
            "noupdate": False,
        },
    )


def ensure_category_field(execute) -> int:
    model_ids = execute(
        "ir.model",
        "search",
        [["model", "=", "account.report.partner.ledger"]],
        limit=1,
    )
    if not model_ids:
        raise SystemExit("account.report.partner.ledger is missing")
    found = execute(
        "ir.model.fields",
        "search",
        [["model", "=", "account.report.partner.ledger"], ["name", "=", TAG_FIELD_NAME]],
        limit=1,
    )
    values = {
        "name": TAG_FIELD_NAME,
        "field_description": "علامات التصنيف",
        "help": "اطبع كل الشركاء بهذه العلامات في ملف واحد. كل عميل يبدأ في صفحة جديدة.",
        "model_id": model_ids[0],
        "model": "account.report.partner.ledger",
        "ttype": "many2many",
        "relation": "res.partner.category",
        "relation_table": TAG_REL_TABLE,
        "column1": "wizard_id",
        "column2": "category_id",
        "state": "manual",
        "copied": True,
        "store": True,
    }
    if found:
        execute("ir.model.fields", "write", found, values)
        field_id = found[0]
    else:
        field_id = execute("ir.model.fields", "create", values)
    upsert_xmlid(
        execute,
        MODULE + ".field_account_report_partner_ledger_x_partner_category_ids",
        "ir.model.fields",
        field_id,
    )
    return field_id


def ensure_tag_automation(execute) -> dict:
    model_ids = execute(
        "ir.model",
        "search",
        [["model", "=", "account.report.partner.ledger"]],
        limit=1,
    )
    autos = execute(
        "base.automation",
        "search",
        [["name", "=", TAG_AUTOMATION_NAME]],
        limit=1,
    )
    auto_vals = {
        "name": TAG_AUTOMATION_NAME,
        "model_id": model_ids[0],
        "trigger": "on_create_or_write",
        "active": True,
    }
    if autos:
        execute("base.automation", "write", autos, auto_vals)
        auto_id = autos[0]
    else:
        auto_id = execute("base.automation", "create", auto_vals)
    actions = execute(
        "ir.actions.server",
        "search",
        [["base_automation_id", "=", auto_id], ["state", "=", "code"]],
        limit=1,
    )
    action_vals = {
        "name": "Execute Code",
        "model_id": model_ids[0],
        "state": "code",
        "usage": "base_automation",
        "base_automation_id": auto_id,
        "code": TAG_FILL_CODE,
    }
    if actions:
        execute("ir.actions.server", "write", actions, action_vals)
        action_id = actions[0]
    else:
        action_id = execute("ir.actions.server", "create", action_vals)
    return {"automation": auto_id, "action": action_id}


def upsert_view(execute, xmlid: str, values: dict) -> int:
    module, name = xmlid.split(".", 1)
    found = execute(
        "ir.model.data",
        "search_read",
        [["module", "=", module], ["name", "=", name], ["model", "=", "ir.ui.view"]],
        fields=["res_id"],
        limit=1,
    )
    if found:
        view_id = found[0]["res_id"]
        execute("ir.ui.view", "write", [view_id], values)
        return view_id
    view_id = execute("ir.ui.view", "create", values)
    execute(
        "ir.model.data",
        "create",
        {
            "module": module,
            "name": name,
            "model": "ir.ui.view",
            "res_id": view_id,
            "noupdate": False,
        },
    )
    return view_id


def apply_views(execute) -> dict:
    field_id = ensure_category_field(execute)
    automation = ensure_tag_automation(execute)
    partner_view = execute(
        "ir.model.data",
        "search_read",
        [
            ["module", "=", "accounting_pdf_reports"],
            ["name", "=", "account_report_partner_ledger_view"],
        ],
        fields=["res_id"],
        limit=1,
    )
    report_view = execute(
        "ir.model.data",
        "search_read",
        [
            ["module", "=", "accounting_pdf_reports"],
            ["name", "=", "report_partnerledger"],
        ],
        fields=["res_id"],
        limit=1,
    )
    if not partner_view or not report_view:
        raise SystemExit("accounting_pdf_reports views are missing on this database")

    wizard_arch = template_arch(
        WIZARD_XML, "accounting_pdf_reports_account_report_partner_ledger_view"
    )
    styles_arch = template_arch(REPORT_XML, "report_partnerledger_brodan_styles")
    table_arch = template_arch(REPORT_XML, "report_partnerledger_brodan_table")

    wizard_id = upsert_view(
        execute,
        MODULE + ".accounting_pdf_reports_account_report_partner_ledger_view",
        {
            "name": "account.report.partner.ledger.form.opening.balance",
            "model": "account.report.partner.ledger",
            "type": "form",
            "inherit_id": partner_view[0]["res_id"],
            "mode": "extension",
            "arch_db": wizard_arch,
            "active": True,
        },
    )
    styles_id = upsert_view(
        execute,
        MODULE + ".report_partnerledger_brodan_styles",
        {
            "name": "report_partnerledger_brodan_styles",
            "type": "qweb",
            "inherit_id": report_view[0]["res_id"],
            "mode": "extension",
            "arch_db": styles_arch,
            "active": True,
            "key": MODULE + ".report_partnerledger_brodan_styles",
        },
    )
    table_id = upsert_view(
        execute,
        MODULE + ".report_partnerledger_brodan_table",
        {
            "name": "report_partnerledger_brodan_table",
            "type": "qweb",
            "inherit_id": report_view[0]["res_id"],
            "mode": "extension",
            "arch_db": table_arch,
            "active": True,
            "key": MODULE + ".report_partnerledger_brodan_table",
        },
    )
    mods = execute(
        "ir.module.module",
        "search",
        [["name", "=", MODULE]],
        limit=1,
    )
    if mods:
        execute(
            "ir.module.module",
            "write",
            mods,
            {"state": "installed", "latest_version": module_version()},
        )
    return {
        "wizard": wizard_id,
        "styles": styles_id,
        "table": table_id,
        "tag_field": field_id,
        **automation,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write views on live Odoo")
    args = parser.parse_args(argv)
    if not args.apply:
        print("Refusing to write the live database without --apply")
        return 2
    execute = connect()
    ids = apply_views(execute)
    print("Updated partner ledger opening views:", ids)
    print("Module version:", module_version())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
