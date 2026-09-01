from odoo import fields, models

from .opening import (  # noqa: F401
    OPENING_LABEL,
    filter_partner_ids_by_tags,
    ids_from_form_m2m,
)


class AccountPartnerLedger(models.TransientModel):
    _inherit = "account.report.partner.ledger"

    # Same Studio/manual field already on live. Declaring it here makes a
    # normal addons_path install work without a leftover x_ field.
    x_show_opening_balance = fields.Boolean(
        string="إظهار الرصيد الافتتاحي",
        default=True,
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

    def _get_report_data(self, data):
        data = super()._get_report_data(data)
        data["form"]["x_show_opening_balance"] = bool(self.x_show_opening_balance)
        tag_ids = self.x_partner_category_ids.ids
        data["form"]["x_partner_category_ids"] = tag_ids
        if tag_ids:
            tagged = self.env["res.partner"].search([("category_id", "in", tag_ids)])
            selected = ids_from_form_m2m(data["form"].get("partner_ids"))
            data["form"]["partner_ids"] = filter_partner_ids_by_tags(
                selected, tagged.ids, tag_ids
            )
        return data
