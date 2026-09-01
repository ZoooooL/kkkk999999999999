# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .mandoub_setup import is_mandoub_pos_name


class PosConfig(models.Model):
    _inherit = "pos.config"

    is_mandoub_pos = fields.Boolean(
        string="نقطة بيع مندوب",
        compute="_compute_is_mandoub_pos",
        store=False,
    )
    mandoub_quotation_mode = fields.Boolean(
        string="المندوب يحفظ ويطبع عرض سعر",
        default=False,
        help="زر الدفع يصبح حفظ و طباعة: عرض سعر + PDF. المدير يؤكد، المخازن تشحن، الحسابات تفوتر.",
    )

    def _compute_is_mandoub_pos(self):
        for config in self:
            config.is_mandoub_pos = is_mandoub_pos_name(config.name)

    def is_mandoub_quotation_pos(self):
        self.ensure_one()
        return self.mandoub_quotation_mode or is_mandoub_pos_name(self.name)

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        for name in ("mandoub_quotation_mode", "name"):
            if name not in fields_list:
                fields_list.append(name)
        return fields_list

    @api.model
    def _load_pos_self_data_fields(self, pos_config_id):
        fields_list = super()._load_pos_self_data_fields(pos_config_id)
        for name in ("mandoub_quotation_mode", "name"):
            if name not in fields_list:
                fields_list.append(name)
        return fields_list

    def _load_self_data_models(self):
        models = super()._load_self_data_models()
        if "res.partner" not in models:
            models.append("res.partner")
        return models

    def action_open_wizard(self):
        """Open mandoub kiosks on the ordering screen, not the PWA install page."""
        self.ensure_one()
        if not self.is_mandoub_quotation_pos():
            return super().action_open_wizard()
        if not self.current_session_id:
            self._check_before_creating_new_session()
            session = self.env["pos.session"].create(
                {"user_id": self.env.uid, "config_id": self.id}
            )
            session.set_opening_control(0, "")
            self._notify("STATUS", {"status": "open"})
        return {
            "type": "ir.actions.act_url",
            "url": self._get_self_order_route(),
            "target": "new",
        }

    def action_open_mandoub_setup_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": "تهيئة جلسات المناديب",
            "res_model": "brodansh.mandoub.setup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_company_id": self.env.company.id},
        }
