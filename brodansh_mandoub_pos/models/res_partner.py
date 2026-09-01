# -*- coding: utf-8 -*-
from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _load_pos_self_data_domain(self, data):
        # Customers are typed/searched on demand; do not dump the whole book.
        return [("id", "=", 0)]

    @api.model
    def _load_pos_self_data_fields(self, config_id):
        return ["id", "name", "phone", "mobile", "street", "city"]
