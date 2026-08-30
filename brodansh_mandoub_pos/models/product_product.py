# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .mandoub_setup import DEFAULT_PACK_QTY


class ProductProduct(models.Model):
    _inherit = "product.product"

    mandoub_pack_qty = fields.Float(
        string="كمية التعبئة في نقطة البيع",
        compute="_compute_mandoub_pack_qty",
        help="ضغطة واحدة في نقطة بيع المندوب تضيف هذه الكمية (تعبئة 12 عادة).",
    )

    def _compute_mandoub_pack_qty(self):
        for product in self:
            packs = product.packaging_ids.filtered(lambda pack: pack.sales and pack.qty > 0)
            product.mandoub_pack_qty = min(packs.mapped("qty")) if packs else DEFAULT_PACK_QTY

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        if "mandoub_pack_qty" not in fields_list:
            fields_list.append("mandoub_pack_qty")
        return fields_list
