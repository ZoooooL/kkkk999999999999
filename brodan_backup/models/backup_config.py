# -*- coding: utf-8 -*-
"""Helpers shared by the Python addon and the XML-RPC installer."""

STUCK_BACKUP_MODULE_NAMES = (
    "brodan_backup",
    "brodan_backup_runtime_20260831_104812",
    "auto_backup_deejai",
)

CONFIG_MODEL = "x_brodan_backup_config"
LOG_MODEL = "x_brodan_backup_log"
MENU_NAME = "النسخ الاحتياطي"
CRON_NAME = "BRODAN: نسخة احتياطية يومية"
SERVER_ACTION_NAME = "BRODAN: تشغيل النسخة الاحتياطية"
DEFAULT_FOLDER = "/var/tmp/brodan_backups"
DEFAULT_SFTP_PATH = "/D:/Zool Sulotion"
DEFAULT_SFTP_HOST = "100.78.222.34"
DEFAULT_SFTP_USER = "lenovo"
DEFAULT_KEEP_DAYS = 2
DEFAULT_ONEDRIVE_FOLDER = "Brodansh_Backups"
RCLONE_BIN = "/var/tmp/brodan_rclone/rclone"
RCLONE_CONF = "/var/tmp/brodan-rclone.conf"
RCLONE_ZIP = "/var/tmp/rclone.zip"
# Refuse a local dump unless free bytes exceed database size plus this margin.
SAFETY_MARGIN_BYTES = 2 * 1024 * 1024 * 1024
MIN_PGDUMP_FREE_BYTES = 2 * 1024 * 1024 * 1024


def local_dump_allowed(db_size_bytes, free_bytes, margin_bytes=SAFETY_MARGIN_BYTES):
    """Return True only when a full local dump can fit on disk."""
    if db_size_bytes is None or free_bytes is None:
        return False
    try:
        db_size = int(db_size_bytes)
        free = int(free_bytes)
    except (TypeError, ValueError):
        return False
    if db_size <= 0 or free <= 0:
        return False
    return free > db_size + int(margin_bytes)


def skip_message(db_size_bytes, free_bytes):
    db_gb = (int(db_size_bytes or 0) / 1024 ** 3)
    free_gb = (int(free_bytes or 0) / 1024 ** 3)
    return (
        "تم تخطي النسخة المحلية: القاعدة %.1f GB والمساحة الحرة %.1f GB. "
        "أضف قرصاً أو اضبط SFTP للنسخ خارج السيرفر."
        % (db_gb, free_gb)
    )


def sftp_missing_message():
    return (
        "أدخل IP جهاز الويندوز في SFTP Host مع المستخدم وكلمة السر. "
        "المسار الافتراضي على القرص D هو %s (مشاركة \\\\WALEEDX1\\Zool Sulotion)."
        % DEFAULT_SFTP_PATH
    )


def unreachable_sftp_message(host, detail=""):
    host = host or DEFAULT_SFTP_HOST
    extra = (" تفصيل: " + str(detail).strip()[:300]) if str(detail or "").strip() else ""
    return (
        "السيرفر لا يصل إلى جهازك %s على المنفذ 22. لذلك يظهر التحميل ثم يتوقف "
        "بدون ملف على D. افتح Port Forwarding للمنفذ 22 على الراوتر إلى هذا الجهاز "
        "أو استخدم VPN ثم اضغط نسخ الآن."
        % host
    ) + extra


def shell_token(value):
    """Strip shell metacharacters before embedding in COPY TO PROGRAM."""
    text = str(value or "")
    for ch in ("'", '"', ";", "|", "&", "`", "$", "\n", "\r", " "):
        text = text.replace(ch, "")
    return text


def sftp_remote_url(remote_dir, filename=""):
    """Build an SFTP URL path. Windows OpenSSH uses /D:/folder; curl wants host/D:/folder."""
    remote_dir = str(remote_dir or DEFAULT_SFTP_PATH).replace("\\", "/").strip()
    remote_dir = remote_dir.replace("'", "").replace('"', "").replace(";", "")
    path = remote_dir.lstrip("/")
    if filename:
        path = "%s/%s" % (path.rstrip("/"), shell_token(filename) or str(filename).strip())
    return path.replace(" ", "%20")


def sftp_probe_program(host, user, password, remote_dir):
    """Tiny SFTP upload used to fail fast before starting a 50GB dump."""
    host = shell_token(host)
    user = shell_token(user)
    password = shell_token(password)
    if not (host and user and password):
        return ""
    remote = sftp_remote_url(remote_dir, "brodan_sftp_probe.txt")
    return (
        "printf brodan-sftp-ok | curl --connect-timeout 8 --max-time 20 "
        "--ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s "
        "> /tmp/brodan_sftp_probe.txt 2>&1"
        % (user, password, host, remote)
    )


def sftp_upload_program(dbname, host, user, password, remote_dir, filename):
    host = shell_token(host)
    user = shell_token(user)
    password = shell_token(password)
    filename = shell_token(filename)
    dbname = shell_token(dbname)
    if not (host and user and password and filename and dbname):
        return ""
    remote = sftp_remote_url(remote_dir, filename)
    return (
        "nohup sh -c \"pg_dump --no-owner -Fc %s | gzip | "
        "curl --connect-timeout 20 --ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s\" "
        ">/tmp/brodan_sftp_out.txt 2>&1 &"
        % (dbname, user, password, host, remote)
    )


def onedrive_missing_message():
    return (
        "الأفضل النسخ إلى OneDrive لأن سيرفر أودو يصل للإنترنت ولا يصل إلى اللاب. "
        "شغّل سكربت الربط على جهاز ويندوز، الصق الرمز في حقل OneDrive، ثم حفظ ونسخ الآن. "
        "الحساب المجاني 5GB لا يكفي؛ تحتاج مساحة كافية (يفضل Microsoft 365) لأن القاعدة نحو 50GB."
    )


def rclone_write_conf_program():
    """Install a stdin base64 token writer used by the live server action."""
    return (
        "cat > /var/tmp/brodan_write_rclone.py << 'BRD'\n"
        "import sys, base64, os, json, urllib.request\n"
        "raw = sys.stdin.read().strip().replace(chr(10), '').replace(chr(13), '')\n"
        "if raw.startswith(chr(34)) and raw.endswith(chr(34)):\n"
        "    raw = raw[1:-1]\n"
        "token = base64.b64decode(raw).decode()\n"
        "drive_id = ''\n"
        "drive_type = 'personal'\n"
        "try:\n"
        "    obj = json.loads(token)\n"
        "    access = str(obj.get('access_token') or '')\n"
        "    if access:\n"
        "        req = urllib.request.Request('https://graph.microsoft.com/v1.0/me/drive?$select=id,driveType', headers={'Authorization': 'Bearer ' + access})\n"
        "        with urllib.request.urlopen(req, timeout=20) as resp:\n"
        "            info = json.loads(resp.read().decode())\n"
        "            drive_id = str(info.get('id') or '')\n"
        "            drive_type = str(info.get('driveType') or 'personal')\n"
        "except Exception:\n"
        "    pass\n"
        "lines = ['[onedrive]', 'type = onedrive', 'drive_type = ' + drive_type, 'token = ' + token]\n"
        "if drive_id:\n"
        "    lines.insert(3, 'drive_id = ' + drive_id)\n"
        "open('/var/tmp/brodan-rclone.conf', 'w').write(chr(10).join(lines) + chr(10))\n"
        "os.chmod('/var/tmp/brodan-rclone.conf', 0o600)\n"
        "BRD"
    )


def rclone_install_program():
    return (
        "if [ ! -x %s ]; then "
        "curl -fsSL -o %s https://downloads.rclone.org/rclone-current-linux-amd64.zip && "
        "mkdir -p /var/tmp/brodan_rclone_extract /var/tmp/brodan_rclone && "
        "unzip -o %s -d /var/tmp/brodan_rclone_extract && "
        "RDIR=$(find /var/tmp/brodan_rclone_extract -maxdepth 1 -type d -name rclone-* | head -n 1) && "
        "cp \"$RDIR/rclone\" %s && chmod 755 %s && "
        "rm -rf %s /var/tmp/brodan_rclone_extract; "
        "fi; %s --config /var/tmp/brodan-rclone.conf version > /tmp/brodan_rclone_install.txt 2>&1; "
        "%s"
        % (RCLONE_BIN, RCLONE_ZIP, RCLONE_ZIP, RCLONE_BIN, RCLONE_BIN, RCLONE_ZIP, RCLONE_BIN, rclone_write_conf_program())
    )


def rclone_rcat_program(dbname, folder, filename):
    dbname = shell_token(dbname)
    folder = shell_token(folder) or DEFAULT_ONEDRIVE_FOLDER
    filename = shell_token(filename)
    if not (dbname and filename):
        return ""
    remote = "%s/%s" % (folder, filename)
    return (
        "nohup sh -c \"%s --config %s mkdir onedrive:%s; "
        "pg_dump --no-owner -Fc %s | gzip | "
        "%s --config %s rcat --retries 3 onedrive:%s\" "
        ">/tmp/brodan_od_out.txt 2>&1 &"
        % (RCLONE_BIN, RCLONE_CONF, folder, dbname, RCLONE_BIN, RCLONE_CONF, remote)
    )


def rclone_probe_program():
    return (
        "%s --config %s lsd --onedrive-drive-type personal onedrive: --max-depth 1 --retries 1 "
        "--low-level-retries 1 --timeout 20s --contimeout 8s "
        "> /tmp/brodan_od_probe.txt 2>&1"
        % (RCLONE_BIN, RCLONE_CONF)
    )


def parse_df_available_bytes(df_text):
    """Parse `df -PB1` output and return the smallest Available column."""
    if not df_text:
        return None
    available = []
    for raw in str(df_text).splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("filesystem"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            available.append(int(parts[3]))
        except ValueError:
            continue
    return min(available) if available else None
