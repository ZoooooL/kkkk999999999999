# -*- coding: utf-8 -*-
from odoo import models

from .mandoub_setup import is_mandoub_origin


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        result = super().action_post()
        sales = self.invoice_line_ids.sale_line_ids.order_id
        for sale in sales:
            if is_mandoub_origin(sale.origin):
                sale._move_mandoub_kitchen_stage(4)
        return result
