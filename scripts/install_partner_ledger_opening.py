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
    return {"wizard": wizard_id, "styles": styles_id, "table": table_id}


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
