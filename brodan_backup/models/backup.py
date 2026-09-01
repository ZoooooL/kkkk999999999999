# -*- coding: utf-8 -*-
import io
import logging
import os
import shutil
import time

from odoo import api, fields, models, _
from odoo.service import db as db_service

from .backup_config import (
    DEFAULT_FOLDER,
    DEFAULT_KEEP_DAYS,
    SAFETY_MARGIN_BYTES,
    local_dump_allowed,
    skip_message,
)

_logger = logging.getLogger(__name__)


class BrodanBackupConfig(models.Model):
    _name = "brodan.backup.config"
    _description = "BRODAN Backup Config"
    _rec_name = "folder"

    folder = fields.Char(default=DEFAULT_FOLDER, required=True)
    days_to_keep = fields.Integer(default=DEFAULT_KEEP_DAYS, required=True)
    sftp_host = fields.Char()
    sftp_user = fields.Char()
    sftp_password = fields.Char()
    sftp_path = fields.Char()
    active = fields.Boolean(default=True)
    last_run = fields.Datetime(readonly=True)
    last_status = fields.Text(readonly=True)

    def _disk_free(self):
        self.ensure_one()
        path = self.folder or DEFAULT_FOLDER
        try:
            os.makedirs(path, exist_ok=True)
            return shutil.disk_usage(path).free
        except OSError:
            return shutil.disk_usage("/").free

    def _db_size(self):
        self.env.cr.execute("SELECT pg_database_size(current_database())")
        return self.env.cr.fetchone()[0]

    def action_run_now(self):
        for rec in self:
            rec._run_backup()
        return True

    def _run_backup(self):
        self.ensure_one()
        Log = self.env["brodan.backup.log"].sudo()
        db_size = self._db_size()
        free = self._disk_free()
        now = time.strftime("%Y%m%d_%H%M%S")
        filename = "%s_%s.zip" % (self.env.cr.dbname, now)
        if not local_dump_allowed(db_size, free, SAFETY_MARGIN_BYTES):
            message = skip_message(db_size, free)
            Log.create({"name": filename, "state": "skip", "message": message, "size": 0})
            self.last_run = fields.Datetime.now()
            self.last_status = message
            _logger.warning(message)
            return False
        folder = self.folder or DEFAULT_FOLDER
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, filename)
        buf = io.BytesIO()
        db_service.dump_db(self.env.cr.dbname, buf, "zip")
        data = buf.getvalue()
        with open(path, "wb") as handle:
            handle.write(data)
        Log.create({
            "name": filename,
            "state": "ok",
            "message": path,
            "size": len(data),
            "path": path,
        })
        self.last_run = fields.Datetime.now()
        self.last_status = _("Backup written to %s (%s bytes)") % (path, len(data))
        self._cleanup_old_files()
        return True

    def _cleanup_old_files(self):
        folder = self.folder or DEFAULT_FOLDER
        keep = max(int(self.days_to_keep or 0), 1)
        cutoff = time.time() - keep * 86400
        if not os.path.isdir(folder):
            return
        for name in os.listdir(folder):
            if self.env.cr.dbname not in name:
                continue
            full = os.path.join(folder, name)
            if os.path.isfile(full) and os.stat(full).st_mtime < cutoff:
                os.remove(full)

    @api.model
    def cron_run(self):
        rec = self.search([], limit=1)
        if not rec:
            rec = self.create({})
        rec._run_backup()


class BrodanBackupLog(models.Model):
    _name = "brodan.backup.log"
    _description = "BRODAN Backup Log"
    _order = "create_date desc"

    name = fields.Char(required=True)
    state = fields.Selection(
        [("ok", "OK"), ("skip", "Skipped"), ("fail", "Failed")],
        default="ok",
        required=True,
    )
    message = fields.Text()
    size = fields.Integer()
    path = fields.Char()
