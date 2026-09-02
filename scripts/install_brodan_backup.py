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
import time
import xmlrpc.client
from pathlib import Path

socket.setdefaulttimeout(300)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodan_backup" / "models"))

from backup_config import (  # noqa: E402
    BACKUP_GROUP_NAME,
    BACKUP_GROUP_XMLID,
    BACKUP_OWNER_LOGIN,
    BACKUP_OWNER_UID,
    CONFIG_MODEL,
    CRON_NAME,
    DEFAULT_FOLDER,
    DEFAULT_KEEP_DAYS,
    DEFAULT_ONEDRIVE_FOLDER,
    DEFAULT_SFTP_HOST,
    DEFAULT_SFTP_PATH,
    DEFAULT_SFTP_USER,
    LEFTOVER_BACKUP_ACTION_NAMES,
    LOG_MODEL,
    MENU_NAME,
    SERVER_ACTION_NAME,
    STUCK_BACKUP_MODULE_NAMES,
    FILESTORE_ACTION_NAME,
    RPC_TMP_PARAM,
    local_dump_allowed,
    onedrive_missing_message,
    parse_df_available_bytes,
    rclone_install_program,
    rclone_rcat_program,
    skip_message,
    sftp_missing_message,
    sftp_upload_program,
    stream_write_program,
    sftp_stream_write_program,
    rclone_write_sftp_conf_program,
    filestore_stream_write_program,
    filestore_rcat_program,
)

BACKUP_CODE_TEMPLATE = r"""
Config = env['x_brodan_backup_config'].sudo()
Log = env['x_brodan_backup_log'].sudo()
cfg = Config.search([], limit=1)
if not cfg:
    cfg = Config.create({'x_name': 'النسخ الاحتياطي', 'x_folder': '/var/tmp/brodan_backups', 'x_sftp_host': '100.78.222.34', 'x_sftp_user': 'lenovo', 'x_sftp_path': '/D:/Zool Sulotion', 'x_onedrive_folder': 'Brodansh_Backups', 'x_onedrive_drive_type': 'personal', 'x_days_to_keep': 2, 'x_active': True})
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
password_raw = (cfg.x_sftp_password or '').strip()
password = password_raw
remote_dir = (cfg.x_sftp_path or 'D:/Zool Sulotion').replace('\\', '/').strip()
od_token = (cfg.x_onedrive_token or '').strip()
od_folder = (cfg.x_onedrive_folder or 'Brodansh_Backups').strip()
od_type = (cfg.x_onedrive_drive_type or 'personal').strip().lower()
for ch in ["'", '"', ';', '|', '&', '`', '$', '\n', '\r']:
    host = host.replace(ch, '')
    user = user.replace(ch, '')
    password = password.replace(ch, '')
    remote_dir = remote_dir.replace(ch, '')
    od_folder = od_folder.replace(ch, '')
    od_type = od_type.replace(ch, '')
od_folder = od_folder.replace(' ', '').replace('\\', '')
if not od_folder:
    od_folder = 'Brodansh_Backups'
if od_type not in ('personal', 'business'):
    od_type = 'personal'
fname = '%s_%s.dump' % (name, time.strftime('%Y%m%d_%H%M%S'))
msg = ''
state = 'skip'
ts_ok = False
if host and user and password_raw:
    ts_cmd = '/var/tmp/brodan_tailscale/tailscale --socket=/var/tmp/brodan_tailscale/tailscaled.sock status > /tmp/brodan_ts_status.txt 2>&1 || true'
    try:
        env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + ts_cmd + '$brodan$')
        env.cr.execute("SELECT pg_read_file('/tmp/brodan_ts_status.txt')")
        tstat = str(env.cr.fetchone()[0] or '')
        if ('100.78.222.34' in tstat) and ('Logged out' not in tstat):
            ts_ok = True
    except Exception:
        ts_ok = False
if not cfg.x_active:
    msg = 'النسخ غير نشط.'
elif ts_ok:
    if free < 2147483648:
        msg = 'المساحة الحرة أقل من 2GB، لا يمكن تشغيل pg_dump للرفع إلى اللاب.'
    else:
        cfg.write({'x_last_status': 'جاري النسخ إلى اللاب عبر Tailscale...'})
        lock_check = "if [ -f /tmp/brodan_backup.lock ] && kill -0 $(cat /tmp/brodan_backup.lock) 2>/dev/null; then echo RUNNING; elif pgrep -x pg_dump >/dev/null 2>&1; then echo RUNNING; else echo NONE; fi > /tmp/brodan_lock_check.txt"
        try:
            env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + lock_check + '$brodan$')
            running = ''
            try:
                env.cr.execute("SELECT pg_read_file('/tmp/brodan_lock_check.txt')")
                running = str(env.cr.fetchone()[0] or '')
            except Exception:
                running = ''
            if 'RUNNING' in running:
                state = 'skip'
                msg = 'نسخة أخرى ما زالت تعمل. بعد انتهائها سيبدأ النسخ إلى اللاب.'
            else:
                env.cr.execute("SELECT translate(encode(convert_to(%s, 'UTF8'), 'base64'), E'\\n', '')", (password_raw,))
                pw_b64 = env.cr.fetchone()[0]
                env.cr.execute('CREATE TEMP TABLE IF NOT EXISTS brodan_sftp_b64 (t text)')
                env.cr.execute('DELETE FROM brodan_sftp_b64')
                env.cr.execute('INSERT INTO brodan_sftp_b64 (t) VALUES (%s)', (pw_b64,))
                write_sftp_py = SFTP_CONF_WRITE
                write_stream = SFTP_STREAM_WRITE
                probe = "/var/tmp/brodan_rclone/rclone --config /var/tmp/brodan-rclone-sftp.conf lsd winpc:/D:/ --max-depth 1 --retries 1 --low-level-retries 1 --timeout 20s --contimeout 10s > /tmp/brodan_sftp_probe.txt 2>&1; echo EXIT:$? >> /tmp/brodan_sftp_probe.txt"
                env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + write_sftp_py + '$brodan$')
                env.cr.execute('COPY brodan_sftp_b64 TO PROGRAM $brodan$python3 /var/tmp/brodan_write_sftp.py ' + host + ' ' + user + '$brodan$')
                env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + probe + '$brodan$')
                pout = ''
                try:
                    env.cr.execute("SELECT pg_read_file('/tmp/brodan_sftp_probe.txt')")
                    pout = str(env.cr.fetchone()[0] or '')
                except Exception:
                    pout = ''
                if 'EXIT:0' not in pout:
                    state = 'fail'
                    msg = 'Tailscale متصل لكن SFTP فشل. تأكد أن OpenSSH شغال على ويندوز. تفصيل: ' + pout.strip()[:300]
                else:
                    safe_dir = remote_dir.replace("'", '')
                    env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + write_stream + '$brodan$')
                    dump = "rm -f /tmp/rclone-spool*; : > /tmp/brodan_sftp_out.txt; nohup python3 /var/tmp/brodan_sftp_stream.py %s '%s' %s >>/tmp/brodan_sftp_out.txt 2>&1 &" % (name, safe_dir, fname)
                    env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + dump + '$brodan$')
                    state = 'ok'
                    msg = 'بدأ النسخ إلى اللاب %s/%s عبر Tailscale. هذه نسخة القاعدة فقط بدون المرفقات. لا تضغط نسخ الآن حتى ينتهي.' % (safe_dir, fname)
        except Exception as ex:
            state = 'fail'
            msg = 'فشل النسخ إلى اللاب: ' + str(ex)[:300]
elif od_token:
    if free < 2147483648:
        msg = 'المساحة الحرة أقل من 2GB، لا يمكن تشغيل pg_dump للرفع إلى OneDrive.'
    else:
        cfg.write({'x_last_status': 'جاري تجهيز الرفع إلى OneDrive...'})
        cleaned = od_token
        if '{' in cleaned and '}' in cleaned:
            cleaned = cleaned[cleaned.find('{'):cleaned.rfind('}')+1]
        env.cr.execute('CREATE TEMP TABLE IF NOT EXISTS brodan_od_b64 (t text)')
        env.cr.execute('DELETE FROM brodan_od_b64')
        env.cr.execute("SELECT translate(encode(convert_to(%s, 'UTF8'), 'base64'), E'\\n', '')", (cleaned,))
        b64 = env.cr.fetchone()[0]
        env.cr.execute('INSERT INTO brodan_od_b64 (t) VALUES (%s)', (b64,))
        install = INSTALL_EXPR
        probe = '/var/tmp/brodan_rclone/rclone --config /var/tmp/brodan-rclone.conf lsd --onedrive-drive-type personal onedrive: --max-depth 1 --retries 1 --low-level-retries 1 --timeout 20s --contimeout 8s > /tmp/brodan_od_probe.txt 2>&1; echo EXIT:$? >> /tmp/brodan_od_probe.txt'
        lock_check = "if [ -f /tmp/brodan_backup.lock ] && kill -0 $(cat /tmp/brodan_backup.lock) 2>/dev/null; then echo RUNNING; elif pgrep -x pg_dump >/dev/null 2>&1; then echo RUNNING; else echo NONE; fi > /tmp/brodan_lock_check.txt"
        try:
            env.cr.execute('SAVEPOINT brodan_od1')
            env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + lock_check + '$brodan$')
            running = ''
            try:
                env.cr.execute("SELECT pg_read_file('/tmp/brodan_lock_check.txt')")
                running = str(env.cr.fetchone()[0] or '')
            except Exception:
                running = ''
            if 'RUNNING' in running:
                env.cr.execute('RELEASE SAVEPOINT brodan_od1')
                state = 'skip'
                msg = 'نسخة أخرى ما زالت تعمل. انتظر حتى تنتهي ثم اضغط نسخ الآن مرة واحدة فقط.'
            else:
                env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + install + '$brodan$')
                env.cr.execute('COPY brodan_od_b64 TO PROGRAM $brodan$python3 /var/tmp/brodan_write_rclone.py$brodan$')
                try:
                    env.cr.execute("SELECT pg_read_file('/tmp/brodan_od_newtoken.json')")
                    newtok = str(env.cr.fetchone()[0] or '').strip()
                    if newtok.startswith('{') and 'refresh_token' in newtok and len(newtok) > 100:
                        cfg.write({'x_onedrive_token': newtok})
                except Exception:
                    pass
                env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + probe + '$brodan$')
                env.cr.execute('RELEASE SAVEPOINT brodan_od1')
                pout = ''
                try:
                    env.cr.execute("SELECT pg_read_file('/tmp/brodan_od_probe.txt')")
                    pout = str(env.cr.fetchone()[0] or '')
                except Exception:
                    pout = ''
                if 'EXIT:0' not in pout:
                    state = 'fail'
                    wstat = ''
                    try:
                        env.cr.execute("SELECT pg_read_file('/tmp/brodan_od_write_status.txt')")
                        wstat = str(env.cr.fetchone()[0] or '').strip()
                    except Exception:
                        wstat = ''
                    msg = 'فشل ربط OneDrive. اللاب لا يصل من السيرفر لذلك نستخدم OneDrive. إن انتهى الرمز شغّل سكربت الربط مرة أخرى. تفصيل: ' + (wstat + ' ' + pout.strip())[:350]
                else:
                    write_py = STREAM_WRITE_EXPR
                    dump = 'rm -f /tmp/rclone-spool*; : > /tmp/brodan_od_out.txt; nohup python3 /var/tmp/brodan_od_stream.py %s %s %s >>/tmp/brodan_od_out.txt 2>&1 &' % (name, od_folder, fname)
                    env.cr.execute('SAVEPOINT brodan_od2')
                    env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + write_py + '$brodan$')
                    env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + dump + '$brodan$')
                    env.cr.execute('RELEASE SAVEPOINT brodan_od2')
                    state = 'ok'
                    msg = 'بدأ النسخ إلى OneDrive/%s/%s بدون ملف مؤقت (قياس ثم رفع). هذه نسخة القاعدة فقط بدون المرفقات. قد يستغرق ساعات. لا تضغط نسخ الآن مرة أخرى حتى ينتهي.' % (od_folder, fname)
        except Exception as ex:
            try:
                env.cr.execute('ROLLBACK TO SAVEPOINT brodan_od1')
            except Exception:
                pass
            state = 'fail'
            msg = 'فشل تجهيز OneDrive: ' + str(ex)[:300]
            if od_token:
                msg = msg.replace(od_token[:20], '***') if len(od_token) > 20 else msg
elif host and user and password:
    msg = 'الأفضل النسخ إلى OneDrive لأن السيرفر لا يصل إلى اللاب. شغّل سكربت الربط، الصق الرمز في حقل OneDrive، ثم حفظ ونسخ الآن. الحساب المجاني 5GB لا يكفي.'
    state = 'skip'
else:
    msg = 'الأفضل النسخ إلى OneDrive لأن السيرفر يصل للإنترنت ولا يصل إلى اللاب. شغّل سكربت الربط على ويندوز، الصق الرمز في حقل OneDrive، ثم حفظ ونسخ الآن. الحساب المجاني 5GB لا يكفي.'
Log.create({'x_name': fname, 'x_state': state, 'x_message': msg, 'x_size': 0, 'x_path': ('sftp:' + remote_dir) if ts_ok else (('onedrive:' + od_folder) if od_token else ((host or '') + ' ' + remote_dir))})
cfg.write({'x_last_status': msg})
"""
BACKUP_CODE = (
    BACKUP_CODE_TEMPLATE
    .replace("STREAM_WRITE_EXPR", repr(stream_write_program()))
    .replace("INSTALL_EXPR", repr(rclone_install_program()))
    .replace("SFTP_STREAM_WRITE", repr(sftp_stream_write_program()))
    .replace("SFTP_CONF_WRITE", repr(rclone_write_sftp_conf_program()))
)

FILESTORE_CODE_TEMPLATE = r"""
Config = env['x_brodan_backup_config'].sudo()
Log = env['x_brodan_backup_log'].sudo()
cfg = Config.search([], limit=1)
if not cfg:
    cfg = Config.create({'x_name': 'النسخ الاحتياطي', 'x_folder': '/var/tmp/brodan_backups', 'x_sftp_host': '100.78.222.34', 'x_sftp_user': 'lenovo', 'x_sftp_path': '/D:/Zool Sulotion', 'x_onedrive_folder': 'Brodansh_Backups', 'x_onedrive_drive_type': 'personal', 'x_days_to_keep': 2, 'x_active': True})
od_folder = (cfg.x_onedrive_folder or 'Brodansh_Backups').strip()
for ch in ["'", '"', ';', '|', '&', '`', '$', '\n', '\r', ' ', '\\']:
    od_folder = od_folder.replace(ch, '')
if not od_folder:
    od_folder = 'Brodansh_Backups'
fname = 'brodansh_filestore_%s.tar.gz' % time.strftime('%Y%m%d_%H%M%S')
param = env['ir.config_parameter'].sudo().get_param('brodan.rpc_tmp') or ''
lock_check = "if [ -f /tmp/brodan_backup.lock ] && kill -0 $(cat /tmp/brodan_backup.lock) 2>/dev/null; then echo RUNNING; elif pgrep -x pg_dump >/dev/null 2>&1; then echo RUNNING; else echo NONE; fi > /tmp/brodan_lock_check.txt"
state = 'fail'
msg = ''
if not param or '"key"' not in param:
    state = 'skip'
    msg = 'لا يمكن رفع المرفقات من الواجهة مباشرة.'
else:
    try:
        env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + lock_check + '$brodan$')
        running = ''
        try:
            env.cr.execute("SELECT pg_read_file('/tmp/brodan_lock_check.txt')")
            running = str(env.cr.fetchone()[0] or '')
        except Exception:
            running = ''
        if 'RUNNING' in running:
            state = 'skip'
            msg = 'نسخة أخرى ما زالت تعمل. انتظر حتى تنتهي ثم أعد رفع المرفقات.'
        else:
            write_py = FILESTORE_WRITE
            dump = 'rm -f /tmp/rclone-spool*; : > /tmp/brodan_fs_out.txt; nohup python3 /var/tmp/brodan_filestore_stream.py %s %s %s >>/tmp/brodan_fs_out.txt 2>&1 &' % (env.cr.dbname, od_folder, fname)
            env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + write_py + '$brodan$')
            env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + dump + '$brodan$')
            state = 'ok'
            msg = 'بدأ رفع المرفقات مضغوطة إلى OneDrive/%s/%s. هذه الملفات كاملة (صور ومستندات). قد يستغرق ساعات. لا تضغط نسخ الآن حتى ينتهي.' % (od_folder, fname)
    except Exception as ex:
        state = 'fail'
        msg = 'فشل بدء رفع المرفقات: ' + str(ex)[:300]
Log.create({'x_name': fname, 'x_state': state, 'x_message': msg, 'x_size': 0, 'x_path': 'onedrive:' + od_folder})
cfg.write({'x_last_status': msg})
"""
FILESTORE_CODE = FILESTORE_CODE_TEMPLATE.replace("FILESTORE_WRITE", repr(filestore_stream_write_program()))



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


def ensure_access(odoo: Odoo, model_id: int, name: str, group_id: int | None = None) -> None:
    if group_id is None:
        system = odoo.execute("ir.model.data", "search_read", [("module", "=", "base"), ("name", "=", "group_system")], ["res_id"], limit=1)
        group_id = system[0]["res_id"] if system else 4
    found = odoo.execute("ir.model.access", "search", [("name", "=", name)], limit=1)
    vals = {
        "name": name,
        "model_id": model_id,
        "group_id": group_id,
        "perm_read": True,
        "perm_write": True,
        "perm_create": True,
        "perm_unlink": True,
    }
    if found:
        odoo.execute("ir.model.access", "write", found, {"group_id": group_id})
        return
    odoo.execute("ir.model.access", "create", vals)


def ensure_backup_owner_group(odoo: Odoo) -> int:
    """Private group assigned only to the Brodansh owner login."""
    users = odoo.execute(
        "res.users",
        "search",
        [("login", "=", BACKUP_OWNER_LOGIN), ("active", "=", True)],
        limit=1,
    )
    owner_id = users[0] if users else BACKUP_OWNER_UID
    data = odoo.execute(
        "ir.model.data",
        "search_read",
        [("module", "=", "brodan_backup"), ("name", "=", BACKUP_GROUP_XMLID)],
        ["res_id"],
        limit=1,
    )
    vals = {"name": BACKUP_GROUP_NAME, "users": [(6, 0, [owner_id])]}
    if data:
        gid = data[0]["res_id"]
        odoo.execute("res.groups", "write", [gid], vals)
        return gid
    gid = odoo.execute("res.groups", "create", vals)
    odoo.execute(
        "ir.model.data",
        "create",
        {
            "name": BACKUP_GROUP_XMLID,
            "model": "res.groups",
            "module": "brodan_backup",
            "res_id": gid,
            "noupdate": True,
        },
    )
    return gid


def _set_groups(odoo: Odoo, model: str, ids: list[int], group_id: int) -> None:
    if ids:
        odoo.execute(model, "write", ids, {"groups_id": [(6, 0, [group_id])]})


def restrict_backup_to_owner(odoo: Odoo) -> dict:
    """Hide backup menus, logs, cron, and leftover probe actions from everyone except the owner."""
    gid = ensure_backup_owner_group(odoo)
    config_model_id = odoo.execute("ir.model", "search", [("model", "=", CONFIG_MODEL)], limit=1)
    log_model_id = odoo.execute("ir.model", "search", [("model", "=", LOG_MODEL)], limit=1)
    if config_model_id:
        ensure_access(odoo, config_model_id[0], "access_x_brodan_backup_config_system", gid)
    if log_model_id:
        ensure_access(odoo, log_model_id[0], "access_x_brodan_backup_log_system", gid)
    extra_acl = odoo.execute(
        "ir.model.access",
        "search",
        [("model_id.model", "in", [CONFIG_MODEL, LOG_MODEL])],
    ) or []
    if extra_acl:
        odoo.execute("ir.model.access", "write", extra_acl, {"group_id": gid})

    menu_ids = []
    for xml_name in ("menu_root", "menu_config", "menu_log"):
        data = odoo.execute(
            "ir.model.data",
            "search_read",
            [("module", "=", "brodan_backup"), ("name", "=", xml_name)],
            ["res_id"],
            limit=1,
        )
        if data:
            menu_ids.append(data[0]["res_id"])
    root = odoo.execute("ir.ui.menu", "search", [("name", "=", MENU_NAME), ("parent_id.name", "=", "Settings")], limit=5)
    menu_ids.extend(root or [])
    if root:
        menu_ids.extend(odoo.execute("ir.ui.menu", "search", [("parent_id", "in", root)]) or [])
    _set_groups(odoo, "ir.ui.menu", sorted(set(menu_ids)), gid)

    action_ids = []
    for xml_name in ("action_config", "action_log"):
        data = odoo.execute(
            "ir.model.data",
            "search_read",
            [("module", "=", "brodan_backup"), ("name", "=", xml_name)],
            ["res_id"],
            limit=1,
        )
        if data:
            action_ids.append(data[0]["res_id"])
    action_ids.extend(
        odoo.execute("ir.actions.act_window", "search", [("name", "in", [MENU_NAME, "سجل النسخ الاحتياطي"]), ("res_model", "in", [CONFIG_MODEL, LOG_MODEL])])
        or []
    )
    _set_groups(odoo, "ir.actions.act_window", sorted(set(action_ids)), gid)

    server_ids = odoo.execute(
        "ir.actions.server",
        "search",
        [("name", "in", [SERVER_ACTION_NAME, CRON_NAME, FILESTORE_ACTION_NAME])],
    ) or []
    _set_groups(odoo, "ir.actions.server", server_ids, gid)

    cron_ids = odoo.execute("ir.cron", "search", [("name", "=", CRON_NAME)]) or []
    _set_groups(odoo, "ir.cron", cron_ids, gid)

    leftover = odoo.execute("ir.actions.server", "search", [("name", "in", list(LEFTOVER_BACKUP_ACTION_NAMES))]) or []
    if leftover:
        odoo.execute("ir.actions.server", "unlink", leftover)

    group = odoo.execute("res.groups", "read", [gid], ["users"])[0]
    return {
        "group_id": gid,
        "owner_users": group.get("users") or [],
        "menus": sorted(set(menu_ids)),
        "removed_probe_actions": leftover,
    }


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


def ensure_rclone(odoo: Odoo, model_id: int) -> str:
    """Download rclone onto the Odoo host so OneDrive uploads can stream."""
    prog = rclone_install_program()
    code = (
        "env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + %r + '$brodan$')\n"
        "out = ''\n"
        "try:\n"
        "    env.cr.execute(\"SELECT pg_read_file('/tmp/brodan_rclone_install.txt')\")\n"
        "    out = str(env.cr.fetchone()[0] or '')\n"
        "except Exception:\n"
        "    out = 'no-install-log'\n"
        "env['ir.config_parameter'].sudo().set_param('brodan.rclone_ver', out[:800])\n"
    ) % prog
    name = "BRODAN: install rclone"
    found = odoo.execute("ir.actions.server", "search", [("name", "=", name)], limit=1)
    vals = {"name": name, "model_id": model_id, "state": "code", "code": code}
    if found:
        odoo.execute("ir.actions.server", "write", found, vals)
        sid = found[0]
    else:
        sid = odoo.execute("ir.actions.server", "create", vals)
    odoo.execute("ir.actions.server", "run", [sid])
    rows = odoo.execute("ir.config_parameter", "search_read", [("key", "=", "brodan.rclone_ver")], ["value"], limit=1)
    odoo.execute("ir.actions.server", "unlink", [sid])
    ids = odoo.execute("ir.config_parameter", "search", [("key", "=", "brodan.rclone_ver")])
    if ids:
        odoo.execute("ir.config_parameter", "unlink", ids)
    return rows[0]["value"] if rows else ""


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
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_onedrive_folder", "char", field_description="مجلد OneDrive")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_onedrive_token", "text", field_description="رمز OneDrive")
    ensure_field(odoo, config_model_id, CONFIG_MODEL, "x_onedrive_drive_type", "char", field_description="نوع OneDrive personal أو business")
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
                <group string="النسخ إلى OneDrive (مستحسن — السيرفر يصل للإنترنت)">
                    <field name="x_onedrive_folder" placeholder="Brodansh_Backups"/>
                    <field name="x_onedrive_drive_type" placeholder="personal"/>
                    <field name="x_onedrive_token" password="True"/>
                </group>
                <group string="احتياطي: القرص D على اللاب (لا يعمل بدون فتح المنفذ 22)">
                    <field name="x_sftp_host" placeholder="100.78.222.34"/>
                    <field name="x_sftp_user" placeholder="lenovo"/>
                    <field name="x_sftp_password" password="True"/>
                    <field name="x_sftp_path" placeholder="/D:/Zool Sulotion"/>
                </group>
                <group>
                    <field name="x_last_status" readonly="1"/>
                    <div class="text-muted">نسخ الآن يرفع القاعدة فقط. المرفقات (صور ومستندات) تُرفع كملف tar.gz منفصل إلى نفس مجلد OneDrive. الحساب المجاني 5GB لا يكفي.</div>
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

    fs_action = odoo.execute("ir.actions.server", "search", [("name", "=", FILESTORE_ACTION_NAME)], limit=1)
    fs_vals = {
        "name": FILESTORE_ACTION_NAME,
        "model_id": config_model_id,
        "state": "code",
        "code": FILESTORE_CODE,
    }
    if fs_action:
        odoo.execute("ir.actions.server", "write", fs_action, fs_vals)
        fs_action_id = fs_action[0]
    else:
        fs_action_id = odoo.execute("ir.actions.server", "create", fs_vals)

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
            "x_onedrive_folder": DEFAULT_ONEDRIVE_FOLDER,
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
                "x_onedrive_folder": DEFAULT_ONEDRIVE_FOLDER,
                "x_onedrive_drive_type": "personal",
                "x_last_status": onedrive_missing_message(),
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

    rclone_ver = ensure_rclone(odoo, config_model_id)

    if run_now:
        odoo.execute("ir.actions.server", "run", [server_id])
    restricted = restrict_backup_to_owner(odoo)
    logs = odoo.execute(LOG_MODEL, "search_read", [], ["x_name", "x_state", "x_message", "x_size"], limit=3, order="id desc")
    cfg_row = odoo.execute(CONFIG_MODEL, "read", [cfg_id], ["x_name", "x_folder", "x_last_status", "x_active"])[0]
    status = (cfg_row.get("x_last_status") or "")
    return {
        "config_id": cfg_id,
        "cron_id": cron_id,
        "server_id": server_id,
        "filestore_action_id": fs_action_id,
        "config": cfg_row,
        "logs": logs,
        "rclone": rclone_ver,
        "restricted": restricted,
        "skipped_for_disk": "تم تخطي" in status,
    }


def ensure_filestore_action(odoo: Odoo) -> int:
    model_ids = odoo.execute("ir.model", "search", [("model", "=", CONFIG_MODEL)], limit=1)
    if not model_ids:
        raise SystemExit("backup config model missing; run --apply first")
    found = odoo.execute("ir.actions.server", "search", [("name", "=", FILESTORE_ACTION_NAME)], limit=1)
    vals = {
        "name": FILESTORE_ACTION_NAME,
        "model_id": model_ids[0],
        "state": "code",
        "code": FILESTORE_CODE,
    }
    if found:
        odoo.execute("ir.actions.server", "write", found, vals)
        return found[0]
    return odoo.execute("ir.actions.server", "create", vals)


def run_host_cmd(odoo: Odoo, shell: str, out_path: str, param_key: str) -> str:
    """Run a short host command via COPY TO PROGRAM and return stdout from out_path."""
    cmd = "sh -c %s > %s 2>&1" % (json.dumps(shell), out_path)
    code = (
        "cmd = %s\n"
        "env.cr.execute('COPY (SELECT 1) TO PROGRAM $brodan$' + cmd + '$brodan$')\n"
        "env.cr.execute(\"SELECT pg_read_file(%s)\")\n"
        "out = env.cr.fetchone()[0] or ''\n"
        "env['ir.config_parameter'].sudo().set_param(%s, out[:50000])\n"
    ) % (repr(cmd), repr(out_path), repr(param_key))
    name = "BRODAN: host cmd"
    model_ids = odoo.execute("ir.model", "search", [("model", "=", CONFIG_MODEL)], limit=1)
    found = odoo.execute("ir.actions.server", "search", [("name", "=", name)])
    vals = {"name": name, "model_id": model_ids[0], "state": "code", "code": code}
    if found:
        odoo.execute("ir.actions.server", "write", found, vals)
        aid = found[0]
    else:
        aid = odoo.execute("ir.actions.server", "create", vals)
    try:
        odoo.execute("ir.actions.server", "run", [aid])
        rows = odoo.execute("ir.config_parameter", "search_read", [("key", "=", param_key)], ["value"], limit=1)
        return str(rows[0]["value"]) if rows else ""
    finally:
        try:
            odoo.execute("ir.actions.server", "unlink", [aid])
        except Exception:
            pass
        ids = odoo.execute("ir.config_parameter", "search", [("key", "=", param_key)])
        if ids:
            try:
                odoo.execute("ir.config_parameter", "unlink", ids)
            except Exception:
                pass


def start_filestore_backup(odoo: Odoo) -> dict:
    """Inject short-lived RPC auth and start the filestore tar.gz upload to OneDrive."""
    action_id = ensure_filestore_action(odoo)
    restrict_backup_to_owner(odoo)
    auth = {
        "url": "http://127.0.0.1:8069",
        "db": require_env("ODOO_DB"),
        "user": require_env("ODOO_USERNAME"),
        "key": require_env("ODOO_API_KEY"),
    }
    odoo.execute("ir.config_parameter", "set_param", RPC_TMP_PARAM, json.dumps(auth))
    try:
        odoo.execute("ir.actions.server", "run", [action_id])
    except Exception:
        ids = odoo.execute("ir.config_parameter", "search", [("key", "=", RPC_TMP_PARAM)])
        if ids:
            odoo.execute("ir.config_parameter", "unlink", ids)
        raise
    status = ""
    leftover = True
    for _ in range(8):
        time.sleep(2)
        status = run_host_cmd(
            odoo,
            "cat /tmp/brodan_fs_status.txt; echo; tail -n 8 /tmp/brodan_fs_out.txt; echo; "
            "if [ -f /tmp/brodan_backup.lock ]; then echo lock=$(cat /tmp/brodan_backup.lock); "
            "ps -p $(cat /tmp/brodan_backup.lock) -o pid,user,etime,cmd 2>/dev/null || echo dead; fi",
            "/tmp/brodan_fs_poll.txt",
            "brodan.fs_poll",
        )
        leftover_ids = odoo.execute("ir.config_parameter", "search", [("key", "=", RPC_TMP_PARAM)])
        leftover = bool(leftover_ids)
        if leftover_ids and ("AUTH_OK" in status or "PASS1" in status or "FAIL" in status):
            odoo.execute("ir.config_parameter", "unlink", leftover_ids)
            leftover = False
        if "AUTH_OK" in status or "PASS1" in status or "FAIL" in status or "SKIP" in status:
            break
    logs = odoo.execute(LOG_MODEL, "search_read", [], ["x_name", "x_state", "x_message", "x_size"], limit=3, order="id desc")
    cfg = odoo.execute(CONFIG_MODEL, "search_read", [], ["x_last_status"], limit=1)
    return {
        "action_id": action_id,
        "status": status[:2000],
        "auth_param_left": leftover,
        "logs": logs,
        "config": cfg,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restrict", action="store_true", help="Hide backup UI from everyone except the owner")
    parser.add_argument("--run", action="store_true", help="Run a backup/probe after installing")
    parser.add_argument("--filestore-now", action="store_true", help="Start a compressed filestore upload to OneDrive")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    odoo = Odoo(require_env("ODOO_URL"), require_env("ODOO_DB"), require_env("ODOO_USERNAME"), require_env("ODOO_API_KEY"))
    cleanup = []
    installed = {"apply": False}
    restricted = {}
    filestore = {}
    if args.apply:
        cleanup = cleanup_stuck_modules(odoo)
        installed = install_backup_app(odoo, run_now=args.run)
        restricted = installed.get("restricted") or {}
    elif args.restrict:
        restricted = restrict_backup_to_owner(odoo)
    if args.filestore_now:
        filestore = start_filestore_backup(odoo)
    report = {
        "database": odoo.db,
        "apply": args.apply,
        "cleanup": cleanup,
        "installed": installed,
        "restricted": restricted,
        "filestore": filestore,
        "helpers": {
            "skip_example": skip_message(54 * 1024 ** 3, 6 * 1024 ** 3),
            "onedrive": onedrive_missing_message(),
            "rclone_rcat": rclone_rcat_program("brodansh", "Brodansh_Backups", "brodansh.dump.gz"),
            "filestore_rcat": filestore_rcat_program("brodansh", "Brodansh_Backups", "brodansh_filestore.tar.gz"),
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
