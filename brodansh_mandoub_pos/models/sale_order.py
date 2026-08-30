# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError

from .mandoub_setup import (
    CREDIT_PAYMENT_TERM_NAME,
    FACTORY_WAREHOUSE_CODE,
    MANAGER_CONFIRM_ONLY_MSG,
    MANDOUB_QUOTATION_CREATED_MSG,
    _as_id,
    is_mandoub_origin,
    is_mandoub_pos_name,
    quotation_vals_from_pos_cart,
)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _is_mandoub_quotation(self):
        self.ensure_one()
        return is_mandoub_origin(self.origin)

    def action_confirm(self):
        if not self.env.su and not self.env.user.has_group("sales_team.group_sale_manager"):
            mandoub_orders = self.filtered(lambda order: order._is_mandoub_quotation())
            if mandoub_orders:
                raise UserError(_(MANAGER_CONFIRM_ONLY_MSG))
        return super().action_confirm()

    def _mandoub_warehouse(self, config):
        warehouse = config.picking_type_id.warehouse_id
        if warehouse:
            return warehouse
        Warehouse = self.env["stock.warehouse"].sudo()
        warehouse = Warehouse.search(
            [("company_id", "=", config.company_id.id), ("code", "=", FACTORY_WAREHOUSE_CODE)],
            limit=1,
        )
        return warehouse or Warehouse.search([("company_id", "=", config.company_id.id)], limit=1)

    def _mandoub_payment_term(self, company):
        Term = self.env["account.payment.term"].sudo()
        term = Term.search(
            [("name", "=", CREDIT_PAYMENT_TERM_NAME), ("company_id", "in", [company.id, False])],
            limit=1,
        )
        return term or Term.search([("name", "ilike", "30"), ("company_id", "in", [company.id, False])], limit=1)

    def _fill_zero_prices(self, vals, payload):
        """If POS sent 0.00, use the product sales price."""
        Product = self.env["product.product"].sudo()
        for _cmd, _id, line in vals.get("order_line") or []:
            if line.get("price_unit"):
                continue
            product = Product.browse(line["product_id"])
            line["price_unit"] = product.lst_price or 0.0

    @api.model
    def create_from_mandoub_pos(self, payload):
        """Create a draft quotation from the POS cart. Never confirms or invoices."""
        payload = payload or {}
        session = self.env["pos.session"].browse(_as_id(payload.get("session_id")))
        config = self.env["pos.config"].browse(_as_id(payload.get("config_id")))
        if session:
            config = session.config_id
        if not config or not config.is_mandoub_quotation_pos():
            if not (config and is_mandoub_pos_name(config.name)):
                raise UserError(_("هذه النقطة ليست نقطة بيع مندوب."))
        salesperson = self.env.user
        if session and session.employee_id.user_id:
            salesperson = session.employee_id.user_id
        elif session and session.user_id:
            salesperson = session.user_id
        warehouse = self._mandoub_warehouse(config)
        try:
            vals = quotation_vals_from_pos_cart(
                payload,
                {
                    "origin": config.name,
                    "user_id": salesperson.id,
                    "company_id": config.company_id.id,
                    "warehouse_id": warehouse.id if warehouse else False,
                    "payment_term_id": self._mandoub_payment_term(config.company_id).id,
                    "team_id": salesperson.sale_team_id.id if salesperson.sale_team_id else False,
                },
            )
        except ValueError as err:
            if str(err) == "partner_required":
                raise UserError(_("اختر العميل قبل إنشاء الطلب.")) from err
            raise UserError(_("أضف أصنافاً قبل إنشاء الطلب.")) from err
        self._fill_zero_prices(vals, payload)
        existing = self.sudo().search(
            [
                ("client_order_ref", "=", vals.get("client_order_ref")),
                ("company_id", "=", config.company_id.id),
                ("client_order_ref", "!=", False),
            ],
            limit=1,
        )
        if existing:
            return {"sale_order_id": existing.id, "name": existing.name, "duplicate": True}
        order = (
            self.sudo()
            .with_company(config.company_id)
            .with_context(default_company_id=config.company_id.id)
            .create(vals)
        )
        order.message_post(
            body=_(
                "أنشئ من نقطة البيع %s. بانتظار تأكيد المدير، ثم التوصيل من المخازن، ثم فاتورة الحسابات."
            )
            % config.name
        )
        return {
            "sale_order_id": order.id,
            "name": order.name,
            "duplicate": False,
            "message": MANDOUB_QUOTATION_CREATED_MSG % order.name,
        }
