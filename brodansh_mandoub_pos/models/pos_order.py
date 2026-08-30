# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError

from .mandoub_setup import POS_INVOICE_BLOCKED_MSG


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _is_mandoub_quotation_order(self):
        return bool(self.config_id) and self.config_id.is_mandoub_quotation_pos()

    def _generate_pos_order_invoice(self):
        blocked = self.filtered(lambda order: order._is_mandoub_quotation_order())
        if blocked:
            raise UserError(_(POS_INVOICE_BLOCKED_MSG))
        return super()._generate_pos_order_invoice()

    def action_pos_order_invoice(self):
        blocked = self.filtered(lambda order: order._is_mandoub_quotation_order())
        if blocked:
            raise UserError(_(POS_INVOICE_BLOCKED_MSG))
        return super().action_pos_order_invoice()
