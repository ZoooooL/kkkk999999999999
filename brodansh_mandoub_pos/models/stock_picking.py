# -*- coding: utf-8 -*-
from odoo import models

from .mandoub_setup import is_mandoub_origin


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        result = super()._action_done()
        for picking in self:
            sale = picking.sale_id
            if sale and is_mandoub_origin(sale.origin):
                sale._move_mandoub_kitchen_stage(3)
        return result
