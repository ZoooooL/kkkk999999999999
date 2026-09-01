#!/usr/bin/env python3
"""Upload POS JS/CSS/XML assets to live Odoo as an imported data module.

Python models are not loaded by Apps → Import Module. The POS frontend still
loads because static files become attachments and ir.asset records. Stock and
pack quantities are fetched by the JS itself when a mandoub session opens.
"""
from __future__ import annotations

import argparse
import ast
import base64
import io
import os
import sys
import xmlrpc.client
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = "brodansh_mandoub_pos"
ASSET_FILES = [
    {
        "relative": "static/src/app/mandoub_quotation.js",
        "bundle": "point_of_sale._assets_pos",
        "mimetype": "text/javascript",
        "active": True,
    },
    {
        "relative": "static/src/app/mandoub_quotation.xml",
        "bundle": "point_of_sale._assets_pos",
        "mimetype": "application/xml",
        "active": False,
    },
    {
        "relative": "static/src/app/mandoub_quotation.scss",
        "bundle": "point_of_sale._assets_pos",
        "mimetype": "text/css",
        "active": True,
    },
    {
        "relative": "static/src/kitchen/mandoub_kitchen.js",
        "bundle": "pos_preparation_display.assets",
        "mimetype": "text/javascript",
        "active": True,
    },
    {
        "relative": "static/src/kitchen/mandoub_kitchen.scss",
        "bundle": "pos_preparation_display.assets",
        "mimetype": "text/css",
        "active": True,
    },
]
STATIC_FILES = [row["relative"] for row in ASSET_FILES]


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


def module_version(manifest_path: Path) -> str:
    data = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    return data.get("version") or "18.0.1.0"


def build_assets_zip(module_dir: Path) -> bytes:
    version = module_version(module_dir / "__manifest__.py")
    manifest = """{
    "name": "برودانش — جلسات المناديب وشاشة المطبخ",
    "version": "%s",
    "category": "Sales/Point of Sale",
    "depends": ["point_of_sale"],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "brodansh_mandoub_pos/static/src/app/mandoub_quotation.js",
            "brodansh_mandoub_pos/static/src/app/mandoub_quotation.xml",
            "brodansh_mandoub_pos/static/src/app/mandoub_quotation.scss",
        ],
        "pos_preparation_display.assets": [
            "brodansh_mandoub_pos/static/src/kitchen/mandoub_kitchen.js",
            "brodansh_mandoub_pos/static/src/kitchen/mandoub_kitchen.scss",
        ],
    },
    "installable": True,
    "application": False,
}
""" % version
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("%s/__init__.py" % MODULE, "")
        zf.writestr("%s/__manifest__.py" % MODULE, manifest)
        for relative in STATIC_FILES:
            src = module_dir / relative
            if not src.exists():
                raise SystemExit("Missing asset file: %s" % src)
            zf.write(src, "%s/%s" % (MODULE, relative))
    return buf.getvalue()


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

    def execute(self, model: str, method: str, *args, **kwargs):
        kw = dict(kwargs)
        kw["context"] = {**self.context, **kw.get("context", {})}
        return self.models.execute_kw(self.db, self.uid, self.api_key, model, method, list(args), kw)


def import_assets(client: OdooClient, zip_bytes: bytes) -> list[str]:
    log: list[str] = []
    wizard_id = client.execute(
        "base.import.module",
        "create",
        {"module_file": base64.b64encode(zip_bytes).decode("ascii"), "force": True, "with_demo": False},
    )
    client.execute("base.import.module", "import_module", [wizard_id])
    wizard = client.execute("base.import.module", "read", [wizard_id], ["state", "import_message"])
    log.append("Import wizard %s state=%s" % (wizard_id, wizard[0].get("state") if wizard else "?"))
    message = wizard[0].get("import_message") if wizard else ""
    if message:
        log.append(str(message))
    mods = client.execute(
        "ir.module.module",
        "search_read",
        [("name", "=", MODULE)],
        fields=["id", "name", "state", "latest_version", "imported"],
    )
    log.append("Module records: %s" % mods)
    assets = client.execute(
        "ir.asset",
        "search_read",
        [("name", "ilike", MODULE)],
        fields=["id", "name", "bundle", "path", "directive", "active"],
    )
    log.append("ir.asset rows: %s" % assets)
    attachments = client.execute(
        "ir.attachment",
        "search_read",
        [("url", "ilike", "/%s/static/" % MODULE)],
        fields=["id", "name", "url", "mimetype"],
    )
    log.append("static attachments: %s" % attachments)
    rewrite_asset_urls(client, attachments)
    return log


def rewrite_asset_urls(client: OdooClient, attachments: list[dict]) -> None:
    """Serve imported files via /web/content so POS/kitchen can load them with a session."""
    by_name = {row["name"]: row for row in attachments}
    for spec in ASSET_FILES:
        filename = Path(spec["relative"]).name
        att = by_name.get(filename)
        if not att:
            continue
        client.execute("ir.attachment", "write", [att["id"]], {"mimetype": spec["mimetype"], "public": True})
        path = "/web/content/%s/%s" % (att["id"], filename)
        assets = client.execute(
            "ir.asset",
            "search",
            [("path", "ilike", filename), ("name", "ilike", MODULE)],
        )
        if assets:
            vals = {"path": path, "active": spec["active"], "bundle": spec["bundle"]}
            client.execute("ir.asset", "write", assets, vals)
            print("ir.asset %s -> %s active=%s" % (assets, path, vals["active"]))


def strip_esm_exports(source: str) -> str:
    """odoo.define files are classic scripts; `export` inside them is a SyntaxError."""
    return (
        source.replace("export async function ", "async function ")
        .replace("export function ", "function ")
        .replace("export {", "const __mandoub_exports = {")
    )


def prepare_js_for_live(source: str) -> str:
    return strip_esm_exports(source)


def upsert_static_asset(client: OdooClient, module_dir: Path, spec: dict, version: str) -> str:
    src = module_dir / spec["relative"]
    filename = src.name
    content = src.read_bytes()
    if filename.endswith(".js"):
        content = prepare_js_for_live(content.decode("utf-8")).encode("utf-8")
    url = "/%s/%s" % (MODULE, spec["relative"])
    attachments = client.execute(
        "ir.attachment",
        "search",
        [
            "|",
            ("url", "=", url),
            "&",
            ("url", "ilike", "/%s/static/" % MODULE),
            ("name", "=", filename),
        ],
    )
    vals = {
        "name": filename,
        "type": "binary",
        "datas": base64.b64encode(content).decode("ascii"),
        "mimetype": spec["mimetype"],
        "public": True,
        "url": url,
    }
    if attachments:
        client.execute("ir.attachment", "write", attachments, vals)
        att_id = attachments[0]
    else:
        att_id = client.execute("ir.attachment", "create", vals)
    path = "/web/content/%s/%s?v=%s" % (att_id, filename, version)
    assets = client.execute(
        "ir.asset",
        "search",
        [
            ("bundle", "=", spec["bundle"]),
            "|",
            ("path", "ilike", filename),
            ("name", "ilike", filename),
        ],
    )
    asset_vals = {
        "name": "%s.%s.%s" % (MODULE, spec["bundle"], spec["relative"]),
        "bundle": spec["bundle"],
        "path": path,
        "active": spec["active"],
        "directive": "append",
    }
    if assets:
        client.execute("ir.asset", "write", assets, asset_vals)
    else:
        client.execute("ir.asset", "create", asset_vals)
    return "Asset %s -> %s active=%s" % (filename, path, spec["active"])


def clear_compiled_bundle(client: OdooClient, bundle: str) -> str:
    found = client.execute("ir.attachment", "search", [("name", "ilike", bundle)])
    if found:
        client.execute("ir.attachment", "unlink", found)
        return "Cleared compiled %s attachments %s" % (bundle, found)
    return "No compiled %s attachments" % bundle


def update_existing_attachments(client: OdooClient, module_dir: Path) -> list[str]:
    """Rewrite already-imported POS/kitchen assets. Zip re-import hits xmlid unique errors."""
    log: list[str] = []
    version = module_version(module_dir / "__manifest__.py")
    for spec in ASSET_FILES:
        log.append(upsert_static_asset(client, module_dir, spec, version))
    log.append(clear_compiled_bundle(client, "pos_preparation_display.assets"))
    return log


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--write-zip", default="")
    parser.add_argument(
        "--import-zip",
        action="store_true",
        help="Force zip import instead of updating existing attachments.",
    )
    args = parser.parse_args()
    load_dotenv(Path(args.env_file))
    zip_bytes = build_assets_zip(ROOT / MODULE)
    if args.write_zip:
        Path(args.write_zip).write_bytes(zip_bytes)
        print("Wrote %s (%s bytes)" % (args.write_zip, len(zip_bytes)))
        return
    client = OdooClient(
        require_env("ODOO_URL"),
        require_env("ODOO_DB"),
        require_env("ODOO_USERNAME"),
        require_env("ODOO_API_KEY"),
    )
    companies = client.execute("res.company", "search", [])
    client.context["allowed_company_ids"] = companies or [3]
    existing = client.execute(
        "ir.attachment",
        "search",
        [("url", "ilike", "/%s/static/" % MODULE)],
        limit=1,
    )
    if existing and not args.import_zip:
        for line in update_existing_attachments(client, ROOT / MODULE):
            print(line)
        return
    for line in import_assets(client, zip_bytes):
        print(line)


if __name__ == "__main__":
    main()
