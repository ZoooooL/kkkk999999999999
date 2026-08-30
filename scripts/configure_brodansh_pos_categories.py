#!/usr/bin/env python3
"""Enable POS categories and sales packaging (تعبئة 12) for Brodansh mandoub POS."""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_mandoub_pos" / "models"))

from mandoub_setup import DEFAULT_PACK_QTY, PACKAGING_NAME, normalize_cat_name  # noqa: E402


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
            raise SystemExit("Authentication failed.")
        self.models = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % self.url, allow_none=True)
        self.context = {"lang": "ar_001"}

    def set_company_ids(self, company_ids: list[int]) -> None:
        self.context["allowed_company_ids"] = company_ids

    def execute(self, model: str, method: str, *args, **kwargs):
        kw = dict(kwargs)
        kw["context"] = {**self.context, **kw.get("context", {})}
        return self.models.execute_kw(self.db, self.uid, self.api_key, model, method, list(args), kw)


def find_company_id(client: OdooClient, name: str) -> int:
    rows = client.execute("res.company", "search_read", [("name", "=", name)], fields=["id"])
    if not rows:
        raise SystemExit("Company not found: %s" % name)
    return rows[0]["id"]


def enable_pos_categories(client: OdooClient, company_id: int) -> list[str]:
    log: list[str] = []
    ids = client.execute(
        "product.template",
        "search",
        [
            ("sale_ok", "=", True),
            ("company_id", "in", [company_id, False]),
            ("pos_categ_ids", "!=", False),
            ("available_in_pos", "=", False),
        ],
    )
    for offset in range(0, len(ids), 80):
        chunk = ids[offset : offset + 80]
        client.execute("product.template", "write", chunk, {"available_in_pos": True})
    log.append("Enabled available_in_pos on %s products that already have a POS category." % len(ids))
    return log


def link_missing_pos_categories(client: OdooClient, company_id: int) -> list[str]:
    log: list[str] = []
    pos_cats = client.execute("pos.category", "search_read", [], fields=["id", "name"])
    int_cats = client.execute("product.category", "search_read", [], fields=["id", "name"])
    pos_by_name = {normalize_cat_name(row["name"]): row["id"] for row in pos_cats}
    linked = 0
    for category in int_cats:
        pos_id = pos_by_name.get(normalize_cat_name(category["name"]))
        if not pos_id:
            continue
        tmpl_ids = client.execute(
            "product.template",
            "search",
            [
                ("categ_id", "=", category["id"]),
                ("sale_ok", "=", True),
                ("company_id", "in", [company_id, False]),
                ("pos_categ_ids", "not in", [pos_id]),
            ],
        )
        for offset in range(0, len(tmpl_ids), 80):
            chunk = tmpl_ids[offset : offset + 80]
            client.execute("product.template", "write", chunk, {"pos_categ_ids": [(4, pos_id)]})
            linked += len(chunk)
    log.append("Linked POS category on %s extra products." % linked)
    return log


def ensure_packaging(client: OdooClient, company_id: int) -> list[str]:
    log: list[str] = []
    tmpl_ids = client.execute(
        "product.template",
        "search",
        [
            ("sale_ok", "=", True),
            ("available_in_pos", "=", True),
            ("company_id", "in", [company_id, False]),
        ],
    )
    created = 0
    skipped = 0
    for offset in range(0, len(tmpl_ids), 40):
        chunk = tmpl_ids[offset : offset + 40]
        variants = client.execute(
            "product.product",
            "search_read",
            [("product_tmpl_id", "in", chunk)],
            fields=["id"],
        )
        variant_ids = [row["id"] for row in variants]
        if not variant_ids:
            continue
        existing = client.execute(
            "product.packaging",
            "search_read",
            [("product_id", "in", variant_ids), ("sales", "=", True), ("qty", ">", 0)],
            fields=["product_id"],
        )
        have = {row["product_id"][0] for row in existing if row.get("product_id")}
        for variant_id in variant_ids:
            if variant_id in have:
                skipped += 1
                continue
            client.execute(
                "product.packaging",
                "create",
                {
                    "name": PACKAGING_NAME,
                    "qty": DEFAULT_PACK_QTY,
                    "product_id": variant_id,
                    "sales": True,
                },
            )
            created += 1
    log.append("Created %s «%s» packs; %s variants already had sales packaging." % (created, PACKAGING_NAME, skipped))
    return log


def configure(client: OdooClient, company_id: int) -> list[str]:
    log: list[str] = []
    log.extend(link_missing_pos_categories(client, company_id))
    log.extend(enable_pos_categories(client, company_id))
    log.extend(ensure_packaging(client, company_id))
    log.append("POS: categories show products; one click adds تعبئة 12 unless the product has another pack.")
    return log


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--skip-packaging", action="store_true")
    args = parser.parse_args()
    load_dotenv(Path(args.env_file))
    client = OdooClient(
        require_env("ODOO_URL"),
        require_env("ODOO_DB"),
        require_env("ODOO_USERNAME"),
        require_env("ODOO_API_KEY"),
    )
    company_name = os.getenv("ODOO_COMPANY_NAME", "مصنع ذو الجناحين للملابس الجاهزة").strip()
    company_id = find_company_id(client, company_name)
    companies = client.execute("res.company", "search", [])
    client.set_company_ids(companies or [company_id])
    logs = []
    logs.extend(link_missing_pos_categories(client, company_id))
    logs.extend(enable_pos_categories(client, company_id))
    if not args.skip_packaging:
        logs.extend(ensure_packaging(client, company_id))
    logs.append("POS: categories show products; one click adds تعبئة 12 unless the product has another pack.")
    for line in logs:
        print(line)


if __name__ == "__main__":
    main()
