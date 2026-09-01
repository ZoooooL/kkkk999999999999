import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_mandoub_pos" / "models"))

from mandoub_setup import (
    MANDOUB_CUSTOMER_PLACEHOLDER,
    MANDOUB_CUSTOMER_REQUIRED_MSG,
    append_customer_query,
    is_mandoub_customer_app,
    is_mandoub_pos_name,
    partner_create_vals,
    partner_public_payload,
    partner_search_domain,
    pick_or_create_partner_action,
)


class MandoubCustomerHelperTests(unittest.TestCase):
    def test_kiosk_install_page_is_a_customer_app(self):
        self.assertTrue(is_mandoub_customer_app("مندوب — صادق حنفي مهران", "/scoped_app"))
        self.assertTrue(
            is_mandoub_customer_app("Kiosk", "/pos-self/40?access_token=abc")
        )
        self.assertFalse(is_mandoub_customer_app("Discuss", "/odoo/discuss"))

    def test_empty_query_does_not_search(self):
        self.assertIsNone(partner_search_domain("   ", 3))
        self.assertIsNone(partner_search_domain("", 3))
        self.assertEqual(pick_or_create_partner_action("  ", ["محمد"]), "empty")

    def test_search_domain_matches_name_and_phone(self):
        domain = partner_search_domain("محمد علي", 3)
        self.assertIn(("name", "ilike", "محمد علي"), domain)
        self.assertIn(("phone", "ilike", "محمد علي"), domain)
        self.assertIn(("mobile", "ilike", "محمد علي"), domain)
        self.assertIn(("company_id", "=", 3), domain)

    def test_create_vals_and_payload(self):
        vals = partner_create_vals("  عميل تجريبي  ", 3)
        self.assertEqual(vals["name"], "عميل تجريبي")
        self.assertEqual(vals["company_id"], 3)
        self.assertEqual(vals["customer_rank"], 1)
        payload = partner_public_payload(88, "عميل تجريبي", "0500000000", "الرياض")
        self.assertEqual(payload["id"], 88)
        self.assertEqual(payload["phone"], "0500000000")

    def test_pick_existing_or_create(self):
        self.assertEqual(
            pick_or_create_partner_action("محمد علي", ["محمد علي", "أحمد"]),
            "use_existing",
        )
        self.assertEqual(pick_or_create_partner_action("محل جديد", ["محمد علي"]), "create")

    def test_append_customer_query_keeps_access_token(self):
        url = append_customer_query(
            "/pos-self/40?access_token=abc",
            "محل النور",
        )
        self.assertIn("access_token=abc", url)
        self.assertIn("customer=", url)
        self.assertIn("%D9%85%D8%AD%D9%84", url)

    def test_placeholder_is_write_the_customer(self):
        self.assertEqual(MANDOUB_CUSTOMER_PLACEHOLDER, "اكتب اسم العميل")
        self.assertIn("العميل", MANDOUB_CUSTOMER_REQUIRED_MSG)


class MandoubCustomerUiTests(unittest.TestCase):
    def test_pos_screen_has_customer_input(self):
        xml = (
            ROOT / "brodansh_mandoub_pos" / "static" / "src" / "app" / "mandoub_quotation.xml"
        ).read_text(encoding="utf-8")
        self.assertIn("اكتب اسم العميل", xml)
        self.assertIn("mandoub-customer-bar", xml)
        self.assertIn('id="mandoub_pos_customer"', xml)

    def test_kiosk_landing_has_customer_input(self):
        xml = (
            ROOT
            / "brodansh_mandoub_pos"
            / "static"
            / "src"
            / "self_order"
            / "mandoub_customer.xml"
        ).read_text(encoding="utf-8")
        self.assertIn("اكتب اسم العميل", xml)
        self.assertIn("بدء الطلب", xml)
        self.assertIn("mandoub-kiosk-customer", xml)

    def test_install_page_has_customer_input(self):
        xml = (
            ROOT
            / "brodansh_mandoub_pos"
            / "static"
            / "src"
            / "frontend"
            / "install_scoped_app.xml"
        ).read_text(encoding="utf-8")
        self.assertIn("اكتب اسم العميل", xml)
        self.assertIn("بدء الطلب", xml)
        js = (
            ROOT
            / "brodansh_mandoub_pos"
            / "static"
            / "src"
            / "frontend"
            / "install_scoped_app.js"
        ).read_text(encoding="utf-8")
        self.assertIn("customer=", js)
        self.assertTrue(is_mandoub_pos_name("مندوب — صادق حنفي مهران"))

    def test_kiosk_route_is_registered(self):
        source = (
            ROOT / "brodansh_mandoub_pos" / "controllers" / "mandoub_kiosk.py"
        ).read_text(encoding="utf-8")
        self.assertIn("/pos-self/mandoub/partners", source)
        manifest = (ROOT / "brodansh_mandoub_pos" / "__manifest__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("pos_self_order", manifest)
        self.assertIn("pos_self_order.assets", manifest)
        self.assertIn("web.assets_frontend", manifest)


if __name__ == "__main__":
    unittest.main()
