# -*- coding: utf-8 -*-
from odoo import fields, models

from .mandoub_setup import is_mandoub_pos_name


class PosConfig(models.Model):
    _inherit = "pos.config"

    is_mandoub_pos = fields.Boolean(
        string="نقطة بيع مندوب",
        compute="_compute_is_mandoub_pos",
        store=False,
    )

    def _compute_is_mandoub_pos(self):
        for config in self:
            config.is_mandoub_pos = is_mandoub_pos_name(config.name)

    def action_open_mandoub_setup_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": "تهيئة جلسات المناديب",
            "res_model": "brodansh.mandoub.setup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_company_id": self.env.company.id},
        }
