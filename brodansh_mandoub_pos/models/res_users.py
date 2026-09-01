# -*- coding: utf-8 -*-
from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _notify_security_setting_update(self, subject, content, mail_values=None, **kwargs):
        """Stop Odoo security-update emails (password/login/email changed)."""
        return
