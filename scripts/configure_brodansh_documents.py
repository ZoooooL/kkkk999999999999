#!/usr/bin/env python3
"""Organize Brodansh documents into entity folders and restrict Configuration.

Reads Odoo XML-RPC credentials from the environment (or a local .env file).
Does not print secrets.
"""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_documents" / "models"))

from documents_setup import (  # noqa: E402
    ADMIN_GROUP_COMMENT,
    ADMIN_GROUP_NAME,
    ENTITY_FOLDERS,
    SENSITIVE_FOLDER_NAMES,
    UNTITLED_FOLDER_NAME,
    classify_document,
    clean_folder_name,
    entity_spec,
    should_skip_source_folder,
    subfolder_label,
)

DOCUMENTS_CONFIG_MENU_XMLID = ("documents", "Config")
DOCUMENTS_MANAGER_XMLID = ("documents", "group_documents_manager")
DOCUMENTS_CATEGORY_XMLID = ("base", "module_category_productivity_documents")
DEFAULT_ADMIN_LOGINS = ("whmm2299@hotmail.com", "sanad44mohsen@gmail.com")


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


def xmlid_res_id(client: OdooClient, module: str, name: str) -> int | None:
    rows = client.execute(
        "ir.model.data",
        "search_read",
        [("module", "=", module), ("name", "=", name)],
        fields=["res_id"],
        limit=1,
    )
    return rows[0]["res_id"] if rows else None


def company_id_by_name(client: OdooClient, name: str | None) -> int | False:
    if not name:
        return False
    rows = client.execute("res.company", "search_read", [("name", "=", name)], fields=["id"], limit=1)
    return rows[0]["id"] if rows else False


def ensure_admin_group(client: OdooClient) -> tuple[int, list[str]]:
    log: list[str] = []
    category_id = xmlid_res_id(client, *DOCUMENTS_CATEGORY_XMLID)
    manager_id = xmlid_res_id(client, *DOCUMENTS_MANAGER_XMLID)
    existing = client.execute(
        "res.groups",
        "search_read",
        [("name", "=", ADMIN_GROUP_NAME), ("category_id", "=", category_id)],
        fields=["id", "users"],
        limit=1,
    )
    vals = {
        "name": ADMIN_GROUP_NAME,
        "comment": ADMIN_GROUP_COMMENT,
    }
    if category_id:
        vals["category_id"] = category_id
    if manager_id:
        vals["implied_ids"] = [(4, manager_id)]
    if existing:
        group_id = existing[0]["id"]
        client.execute("res.groups", "write", [group_id], vals)
        log.append("Updated group %s" % ADMIN_GROUP_NAME)
    else:
        group_id = client.execute("res.groups", "create", vals)
        log.append("Created group %s" % ADMIN_GROUP_NAME)

    logins = [item.strip() for item in os.getenv("DOCUMENTS_ADMIN_LOGINS", ",".join(DEFAULT_ADMIN_LOGINS)).split(",") if item.strip()]
    users = client.execute(
        "res.users",
        "search_read",
        [("login", "in", logins), ("active", "in", [True, False])],
        fields=["id", "login", "partner_id", "name"],
    )
    user_ids = [row["id"] for row in users]
    if user_ids:
        client.execute("res.groups", "write", [group_id], {"users": [(4, uid) for uid in user_ids]})
        log.append("Group members: %s" % ", ".join(row["name"] for row in users))
    return group_id, log


def restrict_config_menu(client: OdooClient, group_id: int) -> str:
    menu_id = xmlid_res_id(client, *DOCUMENTS_CONFIG_MENU_XMLID)
    if not menu_id:
        return "Documents Configuration menu not found."
    client.execute("ir.ui.menu", "write", [menu_id], {"groups_id": [(6, 0, [group_id])]})
    return "Configuration menu limited to %s" % ADMIN_GROUP_NAME


def group_partner_ids(client: OdooClient, group_id: int) -> list[int]:
    group = client.execute("res.groups", "read", [group_id], fields=["users"])[0]
    if not group.get("users"):
        return []
    users = client.execute("res.users", "read", group["users"], fields=["partner_id"])
    partners = []
    for user in users:
        partner = user.get("partner_id")
        if partner:
            partners.append(partner[0])
    return partners


def grant_folder_access(client: OdooClient, folder_id: int, partner_ids: list[int]) -> None:
    for partner_id in partner_ids:
        existing = client.execute(
            "documents.access",
            "search_read",
            [("document_id", "=", folder_id), ("partner_id", "=", partner_id)],
            fields=["id", "role"],
            limit=1,
        )
        if existing:
            if existing[0].get("role") != "edit":
                client.execute("documents.access", "write", [existing[0]["id"]], {"role": "edit"})
        else:
            client.execute(
                "documents.access",
                "create",
                {"document_id": folder_id, "partner_id": partner_id, "role": "edit"},
            )


def find_folder(client: OdooClient, name: str, parent_id: int | False = False) -> dict | None:
    domain = [("type", "=", "folder"), ("name", "=", name)]
    if parent_id:
        domain.append(("folder_id", "=", parent_id))
    else:
        domain.append(("folder_id", "=", False))
    rows = client.execute(
        "documents.document",
        "search_read",
        domain,
        fields=["id", "name", "folder_id", "owner_id", "company_id", "access_internal"],
        limit=1,
    )
    if rows:
        return rows[0]
    # Tolerate extra spaces in existing names.
    all_rows = client.execute(
        "documents.document",
        "search_read",
        [("type", "=", "folder"), ("folder_id", "=", parent_id or False)],
        fields=["id", "name", "folder_id", "owner_id", "company_id", "access_internal"],
    )
    needle = clean_folder_name(name)
    for row in all_rows:
        if clean_folder_name(row["name"]) == needle:
            return row
    return None


def create_folder(client: OdooClient, vals: dict) -> int:
    try:
        return client.execute("documents.document", "create", vals)
    except xmlrpc.client.Fault:
        template = client.execute(
            "documents.document",
            "search_read",
            [("type", "=", "folder"), ("folder_id", "=", False), ("owner_id", "=", vals["owner_id"])],
            fields=["id"],
            limit=1,
        )
        if not template:
            template = client.execute(
                "documents.document",
                "search_read",
                [("type", "=", "folder")],
                fields=["id"],
                limit=1,
            )
        if not template:
            raise
        copied = client.execute("documents.document", "copy", [template[0]["id"]], default=vals)
        return copied[0] if isinstance(copied, list) else copied


def ensure_folder(
    client: OdooClient,
    name: str,
    owner_id: int,
    parent_id: int | False = False,
    company_id: int | False = False,
    pin: bool = False,
) -> tuple[int, str]:
    existing = find_folder(client, name, parent_id)
    vals = {
        "name": name,
        "type": "folder",
        "owner_id": owner_id,
        "access_internal": "none",
        "access_via_link": "none",
        "is_pinned_folder": pin,
        "company_id": company_id or False,
        "folder_id": parent_id or False,
    }
    if existing:
        write_vals = {
            "name": name,
            "access_internal": "none",
            "access_via_link": "none",
        }
        if pin:
            write_vals["is_pinned_folder"] = True
        if company_id:
            write_vals["company_id"] = company_id
        client.execute("documents.document", "write", [existing["id"]], write_vals)
        return existing["id"], "Updated folder %s" % name
    folder_id = create_folder(client, vals)
    return folder_id, "Created folder %s" % name


def ensure_entity_tree(client: OdooClient, owner_id: int, partner_ids: list[int]) -> tuple[dict, list[str]]:
    log: list[str] = []
    tree: dict[str, dict] = {}
    for spec in ENTITY_FOLDERS:
        company_id = company_id_by_name(client, spec["company_name"])
        folder_id, msg = ensure_folder(
            client,
            spec["name"],
            owner_id,
            parent_id=False,
            company_id=company_id,
            pin=spec["pin"],
        )
        grant_folder_access(client, folder_id, partner_ids)
        log.append(msg)
        children: dict[str, int] = {}
        for key, label in (
            ("licenses", "تراخيص"),
            ("addresses", "عناوين"),
            ("certificates", "شهادات"),
            ("tax", "ضرائب"),
            ("finance", "مالية"),
            ("contracts", "عقود"),
            ("spreadsheets", "جداول"),
        ):
            child_id, child_msg = ensure_folder(client, label, owner_id, parent_id=folder_id)
            grant_folder_access(client, child_id, partner_ids)
            children[key] = child_id
            log.append(child_msg)
        tree[spec["key"]] = {"id": folder_id, "children": children, "company_id": company_id}
    untitled_id, untitled_msg = ensure_folder(client, UNTITLED_FOLDER_NAME, owner_id, parent_id=False)
    grant_folder_access(client, untitled_id, partner_ids)
    tree["untitled"] = {"id": untitled_id, "children": {}, "company_id": False}
    log.append(untitled_msg)
    return tree, log


def target_folder_id(tree: dict, entity_key: str | None, sub_key: str | None) -> int | None:
    if sub_key == "untitled":
        return tree["untitled"]["id"]
    if not entity_key or entity_key not in tree:
        return None
    node = tree[entity_key]
    if sub_key and sub_key in node["children"]:
        return node["children"][sub_key]
    return node["id"]


def move_document(client: OdooClient, doc_id: int, folder_id: int, company_id: int | False) -> None:
    vals = {
        "folder_id": folder_id,
        "access_internal": "none",
        "access_via_link": "none",
    }
    if company_id:
        vals["company_id"] = company_id
    client.execute("documents.document", "write", [doc_id], vals)


def organize_files(client: OdooClient, tree: dict, owner_id: int) -> list[str]:
    log: list[str] = []
    moved = 0
    skipped = 0
    docs = client.execute(
        "documents.document",
        "search_read",
        [("type", "!=", "folder"), ("active", "=", True)],
        fields=["id", "name", "folder_id", "owner_id", "company_id"],
    )
    entity_ids = {node["id"]: key for key, node in tree.items() if key != "untitled"}
    child_ids = {child for node in tree.values() for child in node.get("children", {}).values()}
    untitled_id = tree["untitled"]["id"]
    for doc in docs:
        folder = doc.get("folder_id")
        folder_name = folder[1] if folder else ""
        folder_id = folder[0] if folder else False
        if folder_id in child_ids or folder_id == untitled_id:
            skipped += 1
            continue
        if folder_id not in entity_ids and should_skip_source_folder(folder_name):
            skipped += 1
            continue
        entity, sub = classify_document(doc.get("name") or "", folder_name)
        if folder_id in entity_ids:
            entity = entity or entity_ids[folder_id]
        if not entity and sub != "untitled":
            skipped += 1
            continue
        if sub == "untitled" and doc.get("owner_id") and doc["owner_id"][0] != owner_id:
            skipped += 1
            continue
        dest = target_folder_id(tree, entity, sub)
        if not dest or dest == folder_id:
            skipped += 1
            continue
        company_id = tree.get(entity or "", {}).get("company_id") or False
        move_document(client, doc["id"], dest, company_id)
        moved += 1
        log.append("Moved %s → folder %s" % (doc["name"], dest))
    log.append("Moved %s files; left %s in place." % (moved, skipped))
    return log


def lock_sensitive_folders(client: OdooClient) -> list[str]:
    log: list[str] = []
    folders = client.execute(
        "documents.document",
        "search_read",
        [("type", "=", "folder")],
        fields=["id", "name", "access_internal"],
    )
    targets = []
    for folder in folders:
        if clean_folder_name(folder["name"]) in {clean_folder_name(name) for name in SENSITIVE_FOLDER_NAMES}:
            if folder["access_internal"] != "none":
                targets.append(folder["id"])
                log.append("Locked folder %s" % clean_folder_name(folder["name"]))
    if targets:
        client.execute(
            "documents.document",
            "write",
            targets,
            {"access_internal": "none", "access_via_link": "none"},
        )
    if not log:
        log.append("Sensitive folders already private.")
    return log


def configure(client: OdooClient) -> list[str]:
    log: list[str] = []
    group_id, group_log = ensure_admin_group(client)
    log.extend(group_log)
    log.append(restrict_config_menu(client, group_id))
    partners = group_partner_ids(client, group_id)
    tree, tree_log = ensure_entity_tree(client, client.uid, partners)
    log.extend(tree_log)
    log.extend(organize_files(client, tree, client.uid))
    log.extend(lock_sensitive_folders(client))
    log.append("Documents: entity folders private to %s; Configuration hidden from other groups." % ADMIN_GROUP_NAME)
    return log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize Brodansh documents and restrict Configuration")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(Path(args.env_file))
    if args.dry_run:
        print("Dry run: group=%s" % ADMIN_GROUP_NAME)
        print("Entity folders:", ", ".join(spec["name"] for spec in ENTITY_FOLDERS))
        print("Untitled folder:", UNTITLED_FOLDER_NAME)
        print("Sample:", classify_document("سجل التجاري ابنتي.pdf", ""), classify_document("رخصه الورشه.pdf", "مستندات الورشة"))
        return

    url = require_env("ODOO_URL")
    db = require_env("ODOO_DB")
    username = require_env("ODOO_USERNAME")
    api_key = require_env("ODOO_API_KEY")
    client = OdooClient(url, db, username, api_key)
    companies = client.execute("res.company", "search", [])
    client.set_company_ids(companies or [3])
    for line in configure(client):
        print(line)


if __name__ == "__main__":
    main()
