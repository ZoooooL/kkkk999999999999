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
DEFAULT_KEEP_DAYS = 2
# Refuse a local dump unless free bytes exceed database size plus this margin.
SAFETY_MARGIN_BYTES = 2 * 1024 * 1024 * 1024


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
