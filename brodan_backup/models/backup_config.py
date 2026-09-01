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
DEFAULT_SFTP_PATH = "D:/Zool Sulotion"
DEFAULT_SFTP_HOST = "192.168.8.18"
DEFAULT_SFTP_USER = "lenovo"
DEFAULT_KEEP_DAYS = 2
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


def sftp_probe_program(host, user, password, remote_dir):
    """Tiny SFTP upload used to fail fast before starting a 50GB dump."""
    host = shell_token(host)
    user = shell_token(user)
    password = shell_token(password)
    remote_dir = str(remote_dir or DEFAULT_SFTP_PATH).replace("\\", "/").strip()
    remote_dir = remote_dir.replace("'", "").replace('"', "").replace(";", "")
    if not (host and user and password):
        return ""
    remote = "%s/brodan_sftp_probe.txt" % remote_dir.rstrip("/")
    remote = remote.replace(" ", "%20")
    return (
        "printf brodan-sftp-ok | curl --connect-timeout 8 --max-time 20 "
        "--ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s "
        "> /tmp/brodan_sftp_probe.txt 2>&1"
        % (user, password, host, remote)
    )


def shell_token(value):
    """Strip shell metacharacters before embedding in COPY TO PROGRAM."""
    text = str(value or "")
    for ch in ("'", '"', ";", "|", "&", "`", "$", "\n", "\r", " "):
        text = text.replace(ch, "")
    return text


def sftp_upload_program(dbname, host, user, password, remote_dir, filename):
    host = shell_token(host)
    user = shell_token(user)
    password = shell_token(password)
    remote_dir = str(remote_dir or DEFAULT_SFTP_PATH).replace("\\", "/").strip()
    remote_dir = remote_dir.replace("'", "").replace('"', "").replace(";", "")
    filename = shell_token(filename)
    dbname = shell_token(dbname)
    if not (host and user and password and filename and dbname):
        return ""
    remote = "%s/%s" % (remote_dir.rstrip("/"), filename)
    remote = remote.replace(" ", "%20")
    return (
        "nohup sh -c \"pg_dump --no-owner -Fc %s | gzip | "
        "curl --connect-timeout 20 --ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s\" "
        ">/tmp/brodan_sftp_out.txt 2>&1 &"
        % (dbname, user, password, host, remote)
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
