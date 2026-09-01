import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = ROOT / "brodan_partner_ledger_opening" / "models"

import sys

sys.path.insert(0, str(sys_path))

from opening import (  # noqa: E402
    CLOSING_LABEL,
    OPENING_LABEL,
    account_types_for_selection,
    adjust_line_progress,
    company_id_from_form,
    footer_totals,
    move_states_for_target,
    opening_domain,
    opening_from_group,
    should_show_opening,
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
        self.assertFalse(should_show_opening({"date_from": False}, wizard_flag=True))
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


if __name__ == "__main__":
    unittest.main()
