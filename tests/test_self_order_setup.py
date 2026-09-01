import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "configure_brodansh_self_order.py"
spec = importlib.util.spec_from_file_location("configure_brodansh_self_order", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class SelfOrderSetupTests(unittest.TestCase):
    def test_kiosk_mode_and_pay_after_each(self):
        self.assertEqual(mod.SELF_ORDERING_MODE, "kiosk")
        self.assertEqual(mod.SELF_ORDERING_PAY_AFTER, "each")
        self.assertEqual(mod.SELF_ORDERING_SERVICE_MODE, "counter")

    def test_arabic_is_default_language(self):
        vals = mod.pos_config_vals()
        self.assertEqual(vals["self_ordering_default_language_id"], mod.ARABIC_LANG_ID)
        self.assertEqual(vals["self_ordering_available_language_ids"], [(6, 0, [3, 1])])
        self.assertEqual(vals["self_ordering_default_user_id"], 2)

    def test_credit_payment_name(self):
        self.assertEqual(mod.CREDIT_PAYMENT_NAME, "آجل-حساب")

    def test_payment_update_skips_open_sessions(self):
        self.assertEqual(mod.payment_update_action(True, False), "skipped_open_session")
        self.assertEqual(mod.payment_update_action(True, True), "already")
        self.assertEqual(mod.payment_update_action(False, False), "add")
        self.assertEqual(mod.payment_update_action(False, True), "already")

    def test_custom_link_url(self):
        self.assertEqual(mod.custom_link_url(40), "/pos-self/40/products")

    def test_kiosk_ready_requires_credit_and_mode(self):
        row = {
            "self_ordering_mode": "kiosk",
            "self_ordering_pay_after": "each",
            "self_ordering_default_user_id": [2, "admin"],
            "self_ordering_url": "https://example/pos-self/40?access_token=abc",
            "payment_method_ids": [35],
        }
        self.assertTrue(mod.kiosk_ready(row, 35))
        self.assertFalse(mod.kiosk_ready({**row, "payment_method_ids": [29, 30]}, 35))
        self.assertFalse(mod.kiosk_ready({**row, "self_ordering_mode": "nothing"}, 35))

    def test_product_domain_only_pos_items_missing_flag(self):
        self.assertEqual(
            mod.self_order_product_domain(),
            [
                ("available_in_pos", "=", True),
                ("self_order_available", "=", False),
            ],
        )


if __name__ == "__main__":
    unittest.main()
