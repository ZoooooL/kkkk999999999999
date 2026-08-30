# -*- coding: utf-8 -*-
from odoo import fields, models

from ..models.mandoub_setup import (
    CREDIT_PAYMENT_NAME,
    SHARED_KITCHEN_NAME,
    is_mandoub_pos_name,
    kitchen_display_name_for_pos,
    stage_spec_list,
)


class BrodanshMandoubSetupWizard(models.TransientModel):
    _name = "brodansh.mandoub.setup.wizard"
    _description = "تهيئة نقاط البيع وشاشات المطبخ للمناديب"

    company_id = fields.Many2one(
        "res.company",
        string="الشركة",
        required=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text(string="النتيجة", readonly=True)

    def action_apply(self):
        self.ensure_one()
        log = self._apply_setup()
        self.note = "\n".join(log)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _mandoub_configs(self):
        configs = self.env["pos.config"].search(
            [("company_id", "=", self.company_id.id), ("active", "=", True)]
        )
        return configs.filtered(lambda c: is_mandoub_pos_name(c.name))

    def _cashier_employee(self, config, user=None):
        user = user or config.current_user_id
        if not user and config.current_session_id:
            user = config.current_session_id.user_id
        if not user:
            return self.env["hr.employee"]
        return self.env["hr.employee"].search(
            [("user_id", "=", user.id), ("company_id", "=", self.company_id.id)],
            limit=1,
        )

    def _close_empty_sessions(self, configs, log):
        """Close empty sessions so payment methods can be changed."""
        users_by_config = {}
        for config in configs:
            session = config.current_session_id
            if session and session.user_id:
                users_by_config[config.id] = session.user_id
            if not session or session.state == "closed":
                continue
            if session.order_ids:
                log.append("جلسة %s فيها طلبات؛ لن تُغلق." % session.display_name)
                continue
            session.action_pos_session_closing_control()
            log.append("أُغلقت الجلسة الفارغة %s" % session.display_name)
        return users_by_config

    def _ensure_credit_payment(self):
        Method = self.env["pos.payment.method"]
        method = Method.search(
            [
                ("name", "=", CREDIT_PAYMENT_NAME),
                ("company_id", "=", self.company_id.id),
                ("type", "=", "pay_later"),
            ],
            limit=1,
        )
        if method:
            method.write({"journal_id": False, "split_transactions": True})
            return method
        template = Method.search(
            [("company_id", "=", self.company_id.id), ("journal_id", "!=", False)],
            limit=1,
        )
        if template:
            return template.copy(
                {
                    "name": CREDIT_PAYMENT_NAME,
                    "journal_id": False,
                    "split_transactions": True,
                }
            )
        return Method.create(
            {
                "name": CREDIT_PAYMENT_NAME,
                "company_id": self.company_id.id,
                "split_transactions": True,
            }
        )

    def _assign_cashier_and_credit(self, configs, users_by_config, log):
        credit = self._ensure_credit_payment()
        manager = self.env["hr.employee"].search(
            [("user_id", "=", self.env.uid), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        for config in configs:
            user = users_by_config.get(config.id) or config.current_user_id
            cashier = self._cashier_employee(config, user=user)
            if not cashier:
                log.append("لا يوجد موظف مربوط بنقطة البيع %s" % config.name)
                continue
            advanced = cashier
            if manager:
                advanced |= manager
            config.write(
                {
                    "module_pos_hr": True,
                    "mandoub_quotation_mode": True,
                    "basic_employee_ids": [(6, 0, cashier.ids)],
                    "advanced_employee_ids": [(6, 0, advanced.ids)],
                    "payment_method_ids": [(6, 0, credit.ids)],
                }
            )
            log.append("كاشير %s = %s، إنشاء طلب بدون فاتورة" % (config.name, cashier.name))

    def _open_sessions(self, configs, users_by_config, log):
        Session = self.env["pos.session"]
        now = fields.Datetime.now()
        for config in configs:
            user = users_by_config.get(config.id) or config.current_user_id
            cashier = self._cashier_employee(config, user=user)
            session = config.current_session_id
            if not session:
                session = Session.create(
                    {
                        "config_id": config.id,
                        "user_id": user.id if user else self.env.uid,
                        "employee_id": cashier.id if cashier else False,
                    }
                )
                log.append("أنشئت جلسة لـ %s" % config.name)
            vals = {}
            if session.state in ("new", "opening_control"):
                vals["state"] = "opened"
            if not session.start_at:
                vals["start_at"] = now
            if cashier:
                vals["employee_id"] = cashier.id
            if vals:
                session.write(vals)
                log.append("فُتحت جلسة %s والكاشير %s" % (session.display_name, cashier.name if cashier else "-"))

    def _sync_stages(self, display, log):
        Stage = self.env["pos_preparation_display.stage"]
        specs = stage_spec_list()
        existing = display.stage_ids.sorted(lambda s: (s.sequence or 0, s.id))
        for record, spec in zip(existing, specs):
            record.write(spec)
        missing = specs[len(existing) :]
        if missing:
            for spec in missing:
                Stage.create(dict(spec, preparation_display_id=display.id))
                log.append("أُضيفت مرحلة %s على %s" % (spec["name"], display.name))

    def _ensure_display(self, name, pos_configs, log):
        Display = self.env["pos_preparation_display.display"]
        display = Display.search(
            [("name", "=", name), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        if not display:
            # Create stages first, then link POS. Odoo blocks stage
            # edits on a display already tied to an open POS session.
            display = Display.create(
                {
                    "name": name,
                    "company_id": self.company_id.id,
                    "stage_ids": [(0, 0, spec) for spec in stage_spec_list()],
                }
            )
            log.append("أُنشئت شاشة %s" % name)
        else:
            self._sync_stages(display, log)
        display.write({"pos_config_ids": [(6, 0, pos_configs.ids)]})
        categories = self.env["pos.category"].search([])
        if categories:
            display.write({"category_ids": [(6, 0, categories.ids)]})
        return display

    def _apply_setup(self):
        log = []
        configs = self._mandoub_configs()
        if not configs:
            return ["لا توجد نقاط بيع يبدأ اسمها بـ «مندوب —» في هذه الشركة."]
        log.append("عُثر على %s نقطة بيع للمناديب." % len(configs))
        users_by_config = self._close_empty_sessions(configs, log)
        self._assign_cashier_and_credit(configs, users_by_config, log)
        self._open_sessions(configs, users_by_config, log)
        self._ensure_display(SHARED_KITCHEN_NAME, configs, log)
        for config in configs:
            self._ensure_display(kitchen_display_name_for_pos(config.name), config, log)
        self._set_delivery_invoice_policy(log)
        log.append("المراحل: التأكيد → التوصيل → الفوترة")
        log.append("التدفق: المندوب ينشئ الطلب → المدير يؤكد → المخازن توصل → الحسابات تفوتر")
        return log

    def _set_delivery_invoice_policy(self, log):
        products = self.env["product.template"].search(
            [
                ("sale_ok", "=", True),
                ("company_id", "=", self.company_id.id),
                ("invoice_policy", "=", "order"),
            ]
        )
        if products:
            products.write({"invoice_policy": "delivery"})
            log.append("سياسة فوترة %s صنفاً أصبحت عند التسليم." % len(products))
