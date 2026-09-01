from odoo import fields, models

from .opening import OPENING_LABEL  # noqa: F401  — imported for tests/docs


class AccountPartnerLedger(models.TransientModel):
    _inherit = "account.report.partner.ledger"

    # Same Studio/manual field already on live. Declaring it here makes a
    # normal addons_path install work without a leftover x_ field.
    x_show_opening_balance = fields.Boolean(
        string="إظهار الرصيد الافتتاحي",
        default=True,
        help="يعرض صف الرصيد قبل تاريخ البداية ويُضاف إلى الرصيد الجاري.",
    )

    def _get_report_data(self, data):
        data = super()._get_report_data(data)
        data["form"]["x_show_opening_balance"] = bool(self.x_show_opening_balance)
        return data
