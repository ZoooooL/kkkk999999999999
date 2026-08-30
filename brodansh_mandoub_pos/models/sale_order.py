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
    kitchen_card_note,
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
        res = super().action_confirm()
        self.filtered(lambda order: order._is_mandoub_quotation())._move_mandoub_kitchen_stage(2)
        return res

    def _mandoub_kitchen_preps(self):
        self.ensure_one()
        return self.env["pos_preparation_display.order"].search(
            [("pdis_general_note", "ilike", self.name)]
        )

    def _move_mandoub_kitchen_stage(self, sequence):
        PrepOrder = self.env["pos_preparation_display.order"]
        for order in self:
            for prep in order._mandoub_kitchen_preps():
                for ost in prep.order_stage_ids:
                    stages = ost.preparation_display_id.stage_ids.sorted(
                        lambda stage: (stage.sequence or 0, stage.id)
                    )
                    if len(stages) < sequence:
                        continue
                    prep.change_order_stage(stages[sequence - 1].id, ost.preparation_display_id.id)

    def _create_mandoub_kitchen_card(self, session=None):
        """Put the quotation on the kitchen screens: التأكيد → التوصيل → الفوترة."""
        self.ensure_one()
        if session is None or not session:
            session = self.env["pos.session"].search(
                [("config_id.name", "=", self.origin), ("state", "=", "opened")],
                limit=1,
            )
        if not session:
            return False
        note = kitchen_card_note(self.name, self.partner_id.display_name, self.user_id.name)
        pos_lines = []
        for line in self.order_line.filtered(lambda l: l.product_id):
            pos_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": line.product_id.id,
                        "qty": line.product_uom_qty,
                        "price_unit": line.price_unit,
                        "price_subtotal": line.price_subtotal,
                        "price_subtotal_incl": line.price_total,
                        "full_product_name": line.name or line.product_id.display_name,
                    },
                )
            )
        if not pos_lines:
            return False
        employee = session.employee_id
        if self.user_id:
            employee = (
                self.env["hr.employee"].search(
                    [("user_id", "=", self.user_id.id), ("company_id", "=", self.company_id.id)],
                    limit=1,
                )
                or employee
            )
        shadow = (
            self.env["pos.order"]
            .with_context(mandoub_kitchen_shadow=True)
            .create(
                {
                    "session_id": session.id,
                    "partner_id": self.partner_id.id,
                    "employee_id": employee.id if employee else False,
                    "amount_tax": self.amount_tax,
                    "amount_total": self.amount_total,
                    "amount_paid": 0.0,
                    "amount_return": 0.0,
                    "state": "draft",
                    "to_invoice": False,
                    "general_note": note,
                    "lines": pos_lines,
                }
            )
        )
        self.env["pos_preparation_display.order"].process_order(shadow.id)
        preps = self.env["pos_preparation_display.order"].search([("pos_order_id", "=", shadow.id)])
        preps.write(
            {
                "pdis_general_note": note,
                "displayed": True,
                "employee_id": employee.id if employee else False,
            }
        )
        shadow.with_context(mandoub_kitchen_shadow=True).action_pos_order_cancel()
        return True

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
        order._create_mandoub_kitchen_card(session=session if session else None)
        return {
            "sale_order_id": order.id,
            "name": order.name,
            "duplicate": False,
            "message": MANDOUB_QUOTATION_CREATED_MSG % order.name,
        }
