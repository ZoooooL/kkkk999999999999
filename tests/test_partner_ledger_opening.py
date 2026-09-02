import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = ROOT / "brodan_partner_ledger_opening" / "models"

import sys

sys.path.insert(0, str(sys_path))

from opening import (  # noqa: E402
    CLOSING_LABEL,
    COMPANY_LABEL,
    OPENING_LABEL,
    SHOW_OPENING_BALANCE,
    YEAR_START_DAY,
    YEAR_START_MONTH,
    account_types_for_selection,
    adjust_line_progress,
    company_id_from_form,
    effective_date_from,
    effective_date_from_iso,
    footer_totals,
    move_states_for_target,
    opening_domain,
    opening_from_group,
    should_show_opening,
    wizard_create_defaults,
    year_start_date,
    year_start_iso,
)

MODULE = ROOT / "brodan_partner_ledger_opening"


class PartnerLedgerOpeningTests(unittest.TestCase):
    def test_account_types(self):
        self.assertEqual(account_types_for_selection("supplier"), ["liability_payable"])
        self.assertEqual(account_types_for_selection("customer"), ["asset_receivable"])
        self.assertEqual(
            account_types_for_selection("customer_supplier"),
            ["asset_receivable", "liability_payable"],
        )

    def test_opening_domain_uses_date_before_start(self):
        domain = opening_domain(
            partner_id=46545,
            date_from="2026-01-01",
            company_id=3,
            account_types=["asset_receivable", "liability_payable"],
            journal_ids=[120, 226],
            move_states=["posted"],
            include_reconciled=True,
        )
        self.assertIn(("date", "<", "2026-01-01"), domain)
        self.assertIn(("partner_id", "=", 46545), domain)
        self.assertIn(("company_id", "=", 3), domain)
        self.assertNotIn(("full_reconcile_id", "=", False), domain)

    def test_unreconciled_filter(self):
        domain = opening_domain(
            partner_id=1,
            date_from="2026-01-01",
            company_id=3,
            account_types=["asset_receivable"],
            journal_ids=[],
            move_states=["posted"],
            include_reconciled=False,
        )
        self.assertIn(("full_reconcile_id", "=", False), domain)
        self.assertFalse(any(term[0] == "journal_id" for term in domain))

    def test_opening_from_group_handles_empty_and_false(self):
        self.assertEqual(opening_from_group([]), (0.0, 0.0, 0.0))
        self.assertEqual(
            opening_from_group([{"debit": False, "credit": False}]),
            (0.0, 0.0, 0.0),
        )
        debit, credit, balance = opening_from_group(
            [{"debit": 47991.77, "credit": 10000.0}]
        )
        self.assertEqual(debit, 47991.77)
        self.assertEqual(credit, 10000.0)
        self.assertEqual(round(balance, 2), 37991.77)

    def test_should_show_opening_reads_wizard_when_form_omits_flag(self):
        form = {"date_from": "2026-01-01"}
        self.assertTrue(should_show_opening(form, wizard_flag=True))
        self.assertFalse(should_show_opening(form, wizard_flag=False))
        self.assertTrue(should_show_opening({"date_from": False}, wizard_flag=True))
        self.assertTrue(should_show_opening({}))
        self.assertTrue(SHOW_OPENING_BALANCE)
        self.assertTrue(
            should_show_opening(
                {"date_from": "2026-01-01", "x_show_opening_balance": True},
                wizard_flag=False,
            )
        )
        self.assertFalse(
            should_show_opening(
                {"date_from": "2026-01-01", "x_show_opening_balance": False},
                wizard_flag=True,
            )
        )

    def test_progress_includes_opening(self):
        lines = adjust_line_progress(
            [{"progress": 38055.77, "debit": 38055.77, "credit": 0.0}],
            1000.0,
        )
        self.assertEqual(lines[0]["progress"], 39055.77)

    def test_footer_adds_opening_to_period_totals(self):
        debit, credit, balance = footer_totals(1000, 200, 47991.77, 10000)
        self.assertEqual(debit, 48991.77)
        self.assertEqual(credit, 10200.0)
        self.assertEqual(round(balance, 2), 38791.77)

    def test_company_id_from_form(self):
        self.assertEqual(
            company_id_from_form({"used_context": {"company_id": 3}}),
            3,
        )
        self.assertEqual(
            company_id_from_form({"company_id": [3, "مصنع ذو الجناحين للملابس الجاهزة"]}),
            3,
        )

    def test_move_states(self):
        self.assertEqual(move_states_for_target("posted"), ["posted"])
        self.assertEqual(move_states_for_target("all"), ["draft", "posted"])

    def test_qweb_computes_opening_in_template(self):
        arch = (MODULE / "report" / "report_partner_ledger.xml").read_text(encoding="utf-8")
        self.assertIn(OPENING_LABEL, arch)
        self.assertIn(CLOSING_LABEL, arch)
        self.assertIn("x_show_opening_balance", arch)
        self.assertIn("year_start", arch)
        self.assertIn("datetime.date.today().replace(month=1, day=1)", arch)
        self.assertIn("('date', '&lt;', date_from)", arch)
        self.assertIn("account.move.line", arch)
        self.assertIn("read_group", arch)
        self.assertIn("wiz.exists()", arch)

    def test_report_xml_parses(self):
        ET.parse(MODULE / "report" / "report_partner_ledger.xml")
        ET.parse(MODULE / "views" / "partner_ledger_wizard.xml")

    def test_wizard_view_has_checkbox(self):
        arch = (MODULE / "views" / "partner_ledger_wizard.xml").read_text(encoding="utf-8")
        self.assertIn('name="x_show_opening_balance"', arch)
        self.assertIn("date_from", arch)

    def test_wizard_view_has_company_field(self):
        xml = (MODULE / "views" / "partner_ledger_wizard.xml").read_text(encoding="utf-8")
        self.assertIn('name="company_id"', xml)
        self.assertIn(COMPANY_LABEL, xml)
        self.assertIn('readonly="0"', xml)
        self.assertIn("default_partner_ledger_show_opening", xml)
        self.assertIn("<field name=\"json_value\">true</field>", xml)

    def test_year_start_constant(self):
        from datetime import date

        self.assertEqual(YEAR_START_MONTH, 1)
        self.assertEqual(YEAR_START_DAY, 1)
        self.assertEqual(year_start_date(date(2026, 9, 2)), date(2026, 1, 1))
        self.assertEqual(year_start_iso(date(2025, 12, 31)), "2025-01-01")
        self.assertEqual(effective_date_from_iso({"date_from": False}, today=date(2026, 3, 15)), "2026-01-01")
        self.assertEqual(effective_date_from_iso({"date_from": "2026-04-01"}), "2026-04-01")
        self.assertEqual(effective_date_from({}, today=date(2026, 9, 2)), date(2026, 1, 1))

    def test_wizard_create_defaults(self):
        from datetime import date

        defaults = wizard_create_defaults(today=date(2026, 9, 2))
        self.assertEqual(defaults["date_from"], date(2026, 1, 1))
        self.assertTrue(defaults["x_show_opening_balance"])
        self.assertEqual(
            wizard_create_defaults(date_from="2026-04-01", show_opening=False),
            {},
        )

    def test_wizard_view_has_tags_field(self):
        arch = (MODULE / "views" / "partner_ledger_wizard.xml").read_text(encoding="utf-8")
        self.assertIn('name="x_partner_category_ids"', arch)
        self.assertIn("علامات التصنيف", arch)
        self.assertIn("widget=\"many2many_tags\"", arch)

    def test_qweb_page_break_and_tag_filter(self):
        arch = (MODULE / "report" / "report_partner_ledger.xml").read_text(encoding="utf-8")
        self.assertIn("brodan-partner-page-break", arch)
        self.assertNotIn('t-set="company_id"', arch)
        self.assertIn('t-set="pl_company_id"', arch)
        self.assertIn("keep_partner", arch)
        self.assertIn("ob_open_debit", arch)
        self.assertIn("التاريخ", arch)
        self.assertNotIn('t-esc="0.0"', arch)
        self.assertIn("x_partner_category_ids", (MODULE / "views" / "partner_ledger_wizard.xml").read_text(encoding="utf-8"))
        self.assertIn("المندوب:", arch)
        self.assertIn("التصنيف:", arch)

    def test_filter_partner_ids_by_tags(self):
        from opening import filter_partner_ids_by_tags, ids_from_form_m2m, partner_has_tags

        self.assertEqual(filter_partner_ids_by_tags([1, 2], [2, 3, 4], []), [1, 2])
        self.assertEqual(filter_partner_ids_by_tags([], [2, 3, 4], [10]), [2, 3, 4])
        self.assertEqual(filter_partner_ids_by_tags([1, 2, 9], [2, 3, 4], [10]), [2])
        self.assertEqual(ids_from_form_m2m([1, 2]), [1, 2])
        self.assertEqual(ids_from_form_m2m([[3, "Tag"]]), [3])
        self.assertTrue(partner_has_tags([10, 11], [11]))
        self.assertFalse(partner_has_tags([10], [11]))
        self.assertTrue(partner_has_tags([], []))

    def test_zero_balance_hidden_and_net_opening(self):
        from opening import is_zero_amount, keep_partner_statement, net_side_amounts

        self.assertTrue(is_zero_amount(0))
        self.assertTrue(is_zero_amount(0.0))
        self.assertTrue(is_zero_amount(0.001))
        self.assertFalse(is_zero_amount(3.30782))
        self.assertFalse(keep_partner_statement(0))
        self.assertTrue(keep_partner_statement(3307.82))
        self.assertEqual(net_side_amounts(3307.82), (3307.82, 0.0))
        self.assertEqual(net_side_amounts(-150.5), (0.0, 150.5))
        self.assertEqual(net_side_amounts(0), (0.0, 0.0))

    def test_python_wizard_declares_year_company_opening(self):
        source = (MODULE / "models" / "account_partner_ledger.py").read_text(encoding="utf-8")
        self.assertIn("company_id = fields.Many2one", source)
        self.assertIn("readonly=False", source)
        self.assertIn("year_start_date()", source)
        self.assertIn("SHOW_OPENING_BALANCE", source)
        self.assertIn("default_get", source)

    def test_install_script_sets_year_start_and_company(self):
        source = (ROOT / "scripts" / "install_partner_ledger_opening.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("date.today().replace(month=1, day=1)", source)
        self.assertIn("vals['x_show_opening_balance'] = True", source)
        self.assertIn("vals['company_id'] = env.company.id", source)
        self.assertIn("ensure_opening_default", source)


if __name__ == "__main__":
    unittest.main()
