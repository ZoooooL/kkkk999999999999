from odoo import api, fields, models

from .opening import (  # noqa: F401
    COMPANY_LABEL,
    OPENING_LABEL,
    SHOW_OPENING_BALANCE,
    effective_date_from_iso,
    filter_partner_ids_by_tags,
    ids_from_form_m2m,
    wizard_create_defaults,
    year_start_date,
)


class AccountPartnerLedger(models.TransientModel):
    _inherit = "account.report.partner.ledger"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string=COMPANY_LABEL,
        required=True,
        readonly=False,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string="تاريخ البدء",
        default=lambda self: year_start_date(),
    )
    # Same Studio/manual field already on live. Declaring it here makes a
    # normal addons_path install work without a leftover x_ field.
    x_show_opening_balance = fields.Boolean(
        string="إظهار الرصيد الافتتاحي",
        default=SHOW_OPENING_BALANCE,
        help="يعرض صف الرصيد قبل تاريخ البداية ويُضاف إلى الرصيد الجاري.",
    )
    x_partner_category_ids = fields.Many2many(
        comodel_name="res.partner.category",
        relation="x_account_report_pl_category_rel",
        column1="wizard_id",
        column2="category_id",
        string="علامات التصنيف",
        help="اطبع كل الشركاء بهذه العلامات في ملف واحد. كل عميل يبدأ في صفحة جديدة.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        defaults = wizard_create_defaults(
            date_from=res.get("date_from"),
            show_opening=res.get("x_show_opening_balance"),
        )
        for name, value in defaults.items():
            if name in fields_list:
                res[name] = value
        if "company_id" in fields_list and not res.get("company_id"):
            res["company_id"] = self.env.company.id
        return res

    def _get_report_data(self, data):
        data = super()._get_report_data(data)
        form = data["form"]
        form["date_from"] = effective_date_from_iso(form)
        form["x_show_opening_balance"] = bool(self.x_show_opening_balance)
        if self.company_id:
            form["company_id"] = [self.company_id.id, self.company_id.name]
            used = form.setdefault("used_context", {})
            used["company_id"] = self.company_id.id
        tag_ids = self.x_partner_category_ids.ids
        form["x_partner_category_ids"] = tag_ids
        if tag_ids:
            tagged = self.env["res.partner"].search([("category_id", "in", tag_ids)])
            selected = ids_from_form_m2m(form.get("partner_ids"))
            form["partner_ids"] = filter_partner_ids_by_tags(
                selected, tagged.ids, tag_ids
            )
        return data
