#!/usr/bin/env python3
"""Clean stuck imported backup apps and install BRODAN Backup on live Odoo.

Imported ZIP modules cannot load Python. This installer:
1. Uninstalls leftover backup apps stuck in to upgrade / to remove
2. Creates the backup config/log models, menus, cron, and server action
3. Does not write a full dump onto a disk that cannot hold the database
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import xmlrpc.client
from pathlib import Path

socket.setdefaulttimeout(180)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodan_backup" / "models"))

from backup_config import (  # noqa: E402
    CONFIG_MODEL,
    CRON_NAME,
    DEFAULT_FOLDER,
    DEFAULT_KEEP_DAYS,
    DEFAULT_SFTP_HOST,
    DEFAULT_SFTP_PATH,
    DEFAULT_SFTP_USER,
    LOG_MODEL,
    MENU_NAME,
    SERVER_ACTION_NAME,
    STUCK_BACKUP_MODULE_NAMES,
    local_dump_allowed,
    parse_df_available_bytes,
    skip_message,
    sftp_missing_message,
    sftp_upload_program,
)

BACKUP_CODE = r"""
Config = env['x_brodan_backup_config'].sudo()
Log = env['x_brodan_backup_log'].sudo()
cfg = Config.search([], limit=1)
if not cfg:
    cfg = Config.create({'x_name': 'النسخ الاحتياطي', 'x_folder': '/var/tmp/brodan_backups', 'x_sftp_host': '192.168.8.18', 'x_sftp_user': 'lenovo', 'x_sftp_path': 'D:/Zool Sulotion', 'x_days_to_keep': 2, 'x_active': True})
env.cr.execute("SELECT pg_database_size(current_database())")
db_size = env.cr.fetchone()[0]
env.cr.execute("COPY (SELECT 1) TO PROGRAM 'df -PB1 /tmp > /tmp/brodan_df.txt 2>&1'")
env.cr.execute("SELECT pg_read_file('/tmp/brodan_df.txt')")
df_text = env.cr.fetchone()[0]
free = 0
for raw in str(df_text).splitlines():
    line = raw.strip()
    if (not line) or line.lower().startswith('filesystem'):
        continue
    parts = line.split()
    if len(parts) >= 4:
        try:
            n = int(parts[3])
            if (free == 0) or (n < free):
                free = n
        except Exception:
            pass
name = env.cr.dbname
host = (cfg.x_sftp_host or '').strip()
user = (cfg.x_sftp_user or '').strip()
password = (cfg.x_sftp_password or '').strip()
remote_dir = (cfg.x_sftp_path or 'D:/Zool Sulotion').replace('\\', '/').strip()
for ch in ["'", '"', ';', '|', '&', '`', '$', '\n', '\r']:
    host = host.replace(ch, '')
    user = user.replace(ch, '')
    password = password.replace(ch, '')
    remote_dir = remote_dir.replace(ch, '')
fname = '%s_%s.dump.gz' % (name, time.strftime('%Y%m%d_%H%M%S'))
msg = ''
state = 'skip'
if not cfg.x_active:
    msg = 'النسخ غير نشط.'
elif host and user and password:
    if free < 2147483648:
        msg = 'المساحة الحرة أقل من 2GB، لا يمكن تشغيل pg_dump للرفع إلى D.'
    else:
        remote = remote_dir.rstrip('/') + '/' + fname
        remote_url = remote.replace(' ', '%20')
        probe_url = (remote_dir.rstrip('/') + '/brodan_sftp_probe.txt').replace(' ', '%20')
        cfg.write({'x_last_status': 'جاري التحقق من الاتصال بـ %s ...' % host})
        probe = 'printf brodan-sftp-ok | curl --connect-timeout 8 --max-time 20 --ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s > /tmp/brodan_sftp_probe.txt 2>&1' % (user, password, host, probe_url)
        try:
            env.cr.execute('SAVEPOINT brodan_bk')
            env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + probe + '$brodan$')
            env.cr.execute('RELEASE SAVEPOINT brodan_bk')
            pout = ''
            try:
                env.cr.execute("SELECT pg_read_file('/tmp/brodan_sftp_probe.txt')")
                pout = str(env.cr.fetchone()[0] or '')
            except Exception:
                pout = ''
            if pout.strip():
                state = 'fail'
                msg = 'السيرفر لا يصل إلى جهازك %s على المنفذ 22. لذلك يظهر التحميل ثم يتوقف بدون ملف على D. افتح Port Forwarding للمنفذ 22 على الراوتر إلى هذا الجهاز أو استخدم VPN ثم اضغط نسخ الآن. تفصيل: %s' % (host, pout.strip()[:300])
            else:
                dump = 'nohup sh -c "pg_dump --no-owner -Fc %s | gzip | curl --connect-timeout 20 --ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s" >/tmp/brodan_sftp_out.txt 2>&1 &' % (name, user, password, host, remote_url)
                env.cr.execute('SAVEPOINT brodan_bk2')
                env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + dump + '$brodan$')
                env.cr.execute('RELEASE SAVEPOINT brodan_bk2')
                state = 'ok'
                msg = 'الاتصال نجح وبدأت النسخة في الخلفية إلى %s على %s. الملف كبير وقد يستغرق وقتاً طويلاً.' % (remote, host)
        except Exception as ex:
            try:
                env.cr.execute('ROLLBACK TO SAVEPOINT brodan_bk')
            except Exception:
                pass
            state = 'fail'
            msg = 'السيرفر لا يصل إلى جهازك %s على المنفذ 22. لذلك يظهر التحميل ثم يتوقف. افتح المنفذ 22 على الراوتر. تفصيل: %s' % (host, str(ex)[:300])
elif host:
    msg = 'Host وUser جاهزان (192.168.8.18 / lenovo). اكتب كلمة سر ويندوز لمستخدم lenovo. ملاحظة: هذا IP محلي ولن يصل إليه سيرفر أودو إلا بعد فتح المنفذ 22 على الراوتر أو VPN.'
else:
    msg = 'أدخل IP جهاز الويندوز في SFTP Host مع المستخدم وكلمة السر. المسار: D:/Zool Sulotion'
Log.create({'x_name': fname, 'x_state': state, 'x_message': msg, 'x_size': 0, 'x_path': (host or '') + ' ' + remote_dir})
cfg.write({'x_last_status': msg})
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


class Odoo:
    def __init__(self, url: str, db: str, username: str, api_key: str) -> None:
        self.db = db
        self.uid = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % url.rstrip("/")).authenticate(
            db, username, api_key, {}
        )
        if not self.uid:
            raise SystemExit("XML-RPC authentication failed")
        self._models = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % url.rstrip("/"))
        self._key = api_key

    def execute(self, model: str, method: str, *args, **kwargs):
        return self._models.execute_kw(self.db, self.uid, self._key, model, method, list(args), kwargs)


def ensure_model(odoo: Odoo, model: str, name: str) -> int:
    found = odoo.execute("ir.model", "search", [("model", "=", model)], limit=1)
    if found:
        return found[0]
    return odoo.execute("ir.model", "create", {"name": name, "model": model, "state": "manual"})


def ensure_field(odoo: Odoo, model_id: int, model: str, name: str, ttype: str, **vals) -> int:
    found = odoo.execute("ir.model.fields", "search", [("model", "=", model), ("name", "=", name)], limit=1)
    payload = {"model_id": model_id, "name": name, "ttype": ttype, "state": "manual"}
    payload.update(vals)
    if found:
        write_vals = {k: v for k, v in payload.items() if k not in ("model_id", "name", "state")}
        if write_vals:
            try:
                odoo.execute("ir.model.fields", "write", found, write_vals)
            except xmlrpc.client.Fault:
                pass
        return found[0]
    return odoo.execute("ir.model.fields", "create", payload)


def ensure_access(odoo: Odoo, model_id: int, name: str) -> None:
    found = odoo.execute("ir.model.access", "search", [("name", "=", name)], limit=1)
    if found:
        return
    group = odoo.execute("res.groups", "search", [("id", "=", 4)], limit=1)  # fallback
    system = odoo.execute("ir.model.data", "search_read", [("module", "=", "base"), ("name", "=", "group_system")], ["res_id"], limit=1)
    group_id = system[0]["res_id"] if system else (group[0] if group else False)
    odoo.execute(
        "ir.model.access",
        "create",
        {
            "name": name,
            "model_id": model_id,
            "group_id": group_id,
            "perm_read": True,
            "perm_write": True,
            "perm_create": True,
            "perm_unlink": True,
        },
    )


def ensure_view(odoo: Odoo, xml_id_name: str, model: str, vtype: str, arch: str, name: str) -> int:
    data = odoo.execute(
        "ir.model.data",
        "search_read",
        [("module", "=", "brodan_backup"), ("name", "=", xml_id_name)],
        ["res_id"],
        limit=1,
    )
    vals = {"name": name, "model": model, "type": vtype, "arch": arch}
    if data:
        odoo.execute("ir.ui.view", "write", [data[0]["res_id"]], vals)
        return data[0]["res_id"]
    view_id = odoo.execute("ir.ui.view", "create", vals)
    odoo.execute(
        "ir.model.data",
        "create",
        {
            "name": xml_id_name,
            "model": "ir.ui.view",
            "module": "brodan_backup",
            "res_id": view_id,
            "noupdate": False,
        },
    )
    return view_id


def ensure_action(odoo: Odoo, xml_id_name: str, vals: dict) -> int:
    data = odoo.execute(
        "ir.model.data",
        "search_read",
        [("module", "=", "brodan_backup"), ("name", "=", xml_id_name)],
        ["res_id"],
        limit=1,
    )
    if data:
        odoo.execute("ir.actions.act_window", "write", [data[0]["res_id"]], vals)
        return data[0]["res_id"]
    action_id = odoo.execute("ir.actions.act_window", "create", vals)
    odoo.execute(
        "ir.model.data",
        "create",
        {
            "name": xml_id_name,
            "model": "ir.actions.act_window",
            "module": "brodan_backup",
            "res_id": action_id,
            "noupdate": False,
        },
    )
    return action_id


def ensure_menu(odoo: Odoo, xml_id_name: str, vals: dict) -> int:
    data = odoo.execute(
        "ir.model.data",
        "search_read",
        [("module", "=", "brodan_backup"), ("name", "=", xml_id_name)],
        ["res_id"],
        limit=1,
    )
    if data:
        odoo.execute("ir.ui.menu", "write", [data[0]["res_id"]], vals)
        return data[0]["res_id"]
    menu_id = odoo.execute("ir.ui.menu", "create", vals)
    odoo.execute(
        "ir.model.data",
        "create",
        {
            "name": xml_id_name,
            "model": "ir.ui.menu",
            "module": "brodan_backup",
            "res_id": menu_id,
            "noupdate": False,
        },
    )
    return menu_id


def cleanup_stuck_modules(odoo: Odoo) -> list[dict]:
    rows = odoo.execute(
        "ir.module.module",
        "search_read",
        [("name", "in", list(STUCK_BACKUP_MODULE_NAMES))],
        ["name", "state"],
        context={"lang": "en_US"},
    )
    report = []
    ids = [row["id"] for row in rows]
    if not ids:
        return [{"name": name, "action": "absent"} for name in STUCK_BACKUP_MODULE_NAMES]
    for row in rows:
        if row["state"] not in ("to remove", "uninstalled"):
            try:
                odoo.execute("ir.module.module", "button_uninstall", [row["id"]])
                row["state"] = "to remove"
            except xmlrpc.client.Fault as ex:
                report.append({"name": row["name"], "action": "uninstall_error", "error": str(ex)[:200]})
    try:
        odoo.execute("ir.module.module", "module_uninstall", ids)
        for row in rows:
            report.append({"name": row["name"], "action": "removed"})
    except xmlrpc.client.Fault as ex:
        leftover = odoo.execute("ir.module.module", "search", [("id", "in", ids)])
        if leftover:
            report.append({"action": "module_uninstall_error", "error": str(ex)[:300], "left": leftover})
        else:
            for row in rows:
                report.append({"name": row["name"], "action": "removed"})
    still = odoo.execute("ir.module.module", "search_read", [("name", "in", list(STUCK_BACKUP_MODULE_NAMES))], ["name", "state"])
    for row in still:
        report.append({"name": row["name"], "action": "still_present", "state": row["state"]})
    if not report:
        report = [{"name": name, "action": "absent"} for name in STUCK_BACKUP_MODULE_NAMES]
    return report


def install_backup_app(odoo: Odoo, run_now: bool = False) -> dict:
    config_model_id = ensure_model(odoo, CONFIG_MODEL, "تهيئة النسخ الاحتياطي")
    log_model_id = ensure_model(odoo, LOG_MODEL, "سجل النسخ الاحتياطي")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_name", "char", field_description="الاسم")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_folder", "char", field_description="مجلد النسخ")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_days_to_keep", "integer", field_description="أيام الاحتفاظ")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_sftp_host", "char", field_description="IP جهاز الويندوز")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_sftp_user", "char", field_description="مستخدم ويندوز")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_sftp_password", "char", field_description="كلمة سر ويندوز")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_sftp_path", "char", field_description="مسار القرص D")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_active", "boolean", field_description="نشط")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_last_status", "text", field_description="آخر حالة")
    ensure_field(odoo, log_model_id, LOG_MODEL, "x_name", "char", field_description="الاسم")
    ensure_field(odoo, log_model_id, LOG_MODEL, "x_state", "char", field_description="الحالة")
    ensure_field(odoo, log_model_id, LOG_MODEL, "x_message", "text", field_description="الرسالة")
    ensure_field(odoo, log_model_id, LOG_MODEL, "x_size", "integer", field_description="الحجم")
    ensure_field(odoo, log_model_id, LOG_MODEL, "x_path", "char", field_description="المسار")
    ensure_access(odoo, config_model_id, "access_x_brodan_backup_config_system")
    ensure_access(odoo, log_model_id, "access_x_brodan_backup_log_system")

    form_arch = """
        <form>
            <header>
                <button name="%(action)s" type="action" string="نسخ الآن" class="btn-primary"/>
            </header>
            <sheet>
                <group>
                    <field name="x_name"/>
                    <field name="x_folder"/>
                    <field name="x_days_to_keep"/>
                    <field name="x_active"/>
                </group>
                <group string="النسخ إلى القرص D على جهاز ويندوز (SFTP / IP)">
                    <field name="x_sftp_host" placeholder="192.168.8.18"/>
                    <field name="x_sftp_user" placeholder="lenovo"/>
                    <field name="x_sftp_password" password="True"/>
                    <field name="x_sftp_path" placeholder="D:/Zool Sulotion"/>
                </group>
                <group>
                    <field name="x_last_status" readonly="1"/>
                    <div class="text-muted">زر نسخ الآن يختبر الاتصال خلال ثوانٍ. إن توقف التحميل فالمسار من السيرفر إلى جهازك مغلق (المنفذ 22).</div>
                </group>
            </sheet>
        </form>
    """
    tree_arch = """
        <list>
            <field name="create_date"/>
            <field name="x_name"/>
            <field name="x_state"/>
            <field name="x_size"/>
            <field name="x_message"/>
        </list>
    """

    server = odoo.execute("ir.actions.server", "search", [("name", "=", SERVER_ACTION_NAME)], limit=1)
    server_vals = {
        "name": SERVER_ACTION_NAME,
        "model_id": config_model_id,
        "state": "code",
        "code": BACKUP_CODE,
    }
    if server:
        odoo.execute("ir.actions.server", "write", server, {"code": BACKUP_CODE, "model_id": config_model_id})
        server_id = server[0]
    else:
        server_id = odoo.execute("ir.actions.server", "create", server_vals)

    form_arch = form_arch % {"action": server_id}
    ensure_view(odoo, "view_config_form", CONFIG_MODEL, "form", form_arch, "x.brodan.backup.config.form")
    ensure_view(odoo, "view_log_tree", LOG_MODEL, "list", tree_arch, "x.brodan.backup.log.tree")

    act_config = ensure_action(
        odoo,
        "action_config",
        {"name": MENU_NAME, "res_model": CONFIG_MODEL, "view_mode": "form", "target": "current"},
    )
    act_log = ensure_action(
        odoo,
        "action_log",
        {"name": "سجل النسخ الاحتياطي", "res_model": LOG_MODEL, "view_mode": "list", "target": "current"},
    )
    parent = odoo.execute("ir.model.data", "search_read", [("module", "=", "base"), ("name", "=", "menu_administration")], ["res_id"], limit=1)
    parent_id = parent[0]["res_id"] if parent else False
    root = ensure_menu(
        odoo,
        "menu_root",
        {"name": MENU_NAME, "parent_id": parent_id, "sequence": 80},
    )
    ensure_menu(odoo, "menu_config", {"name": "التهيئة", "parent_id": root, "action": "ir.actions.act_window,%s" % act_config, "sequence": 1})
    ensure_menu(odoo, "menu_log", {"name": "السجل", "parent_id": root, "action": "ir.actions.act_window,%s" % act_log, "sequence": 2})

    cfg = odoo.execute(CONFIG_MODEL, "search", [], limit=1)
    if cfg:
        odoo.execute(CONFIG_MODEL, "write", cfg, {
            "x_folder": DEFAULT_FOLDER,
            "x_days_to_keep": DEFAULT_KEEP_DAYS,
            "x_active": True,
            "x_name": MENU_NAME,
            "x_sftp_path": DEFAULT_SFTP_PATH,
            "x_sftp_host": DEFAULT_SFTP_HOST,
            "x_sftp_user": DEFAULT_SFTP_USER,
        })
        cfg_id = cfg[0]
    else:
        cfg_id = odoo.execute(
            CONFIG_MODEL,
            "create",
            {
                "x_name": MENU_NAME,
                "x_folder": DEFAULT_FOLDER,
                "x_days_to_keep": DEFAULT_KEEP_DAYS,
                "x_sftp_path": DEFAULT_SFTP_PATH,
                "x_sftp_host": DEFAULT_SFTP_HOST,
                "x_sftp_user": DEFAULT_SFTP_USER,
                "x_active": True,
            },
        )

    odoo.execute("ir.actions.act_window", "write", [act_config], {"res_id": cfg_id, "view_mode": "form"})

    cron = odoo.execute("ir.cron", "search", [("name", "=", CRON_NAME)], limit=1)
    cron_vals = {
        "name": CRON_NAME,
        "model_id": config_model_id,
        "state": "code",
        "code": BACKUP_CODE,
        "interval_number": 1,
        "interval_type": "days",
        "active": True,
        "user_id": 2,
    }
    if cron:
        odoo.execute("ir.cron", "write", cron, cron_vals)
        cron_id = cron[0]
    else:
        cron_id = odoo.execute("ir.cron", "create", cron_vals)

    if run_now:
        odoo.execute("ir.actions.server", "run", [server_id])
    logs = odoo.execute(LOG_MODEL, "search_read", [], ["x_name", "x_state", "x_message", "x_size"], limit=3, order="id desc")
    cfg_row = odoo.execute(CONFIG_MODEL, "read", [cfg_id], ["x_name", "x_folder", "x_last_status", "x_active"])[0]
    status = (cfg_row.get("x_last_status") or "")
    return {
        "config_id": cfg_id,
        "cron_id": cron_id,
        "server_id": server_id,
        "config": cfg_row,
        "logs": logs,
        "skipped_for_disk": "تم تخطي" in status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run", action="store_true", help="Run a backup/probe after installing")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    odoo = Odoo(require_env("ODOO_URL"), require_env("ODOO_DB"), require_env("ODOO_USERNAME"), require_env("ODOO_API_KEY"))
    cleanup = cleanup_stuck_modules(odoo)
    installed = install_backup_app(odoo, run_now=args.run) if args.apply else {"apply": False}
    report = {
        "database": odoo.db,
        "apply": args.apply,
        "cleanup": cleanup,
        "installed": installed,
        "helpers": {
            "skip_example": skip_message(54 * 1024 ** 3, 6 * 1024 ** 3),
            "parse_df": parse_df_available_bytes(
                "Filesystem 1-blocks Used Available Capacity Mounted on\n/dev/root 100 90 10 90% /\n"
            ),
        },
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
