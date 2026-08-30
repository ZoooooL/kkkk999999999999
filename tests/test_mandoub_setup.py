import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_mandoub_pos" / "models"))

from mandoub_setup import (
    CREDIT_PAYMENT_NAME,
    DEFAULT_PACK_QTY,
    MANAGER_CONFIRM_ONLY_MSG,
    MANDOUB_POS_PREFIX,
    MANDOUB_QUOTATION_CREATED_MSG,
    SHARED_KITCHEN_NAME,
    choose_pack_qty,
    credit_payment_vals,
    default_pos_qty,
    is_mandoub_origin,
    is_mandoub_pos_name,
    kitchen_card_note,
    kitchen_display_name_for_pos,
    kitchen_stage_index,
    quotation_vals_from_pos_cart,
    sales_pack_qtys,
    stage_spec_list,
)


class MandoubSetupTests(unittest.TestCase):
    def test_mandoub_pos_names(self):
        self.assertTrue(is_mandoub_pos_name("مندوب — احمد مهران"))
        self.assertFalse(is_mandoub_pos_name("جملة الملابس — الشرقي"))
        self.assertFalse(is_mandoub_pos_name(""))
        self.assertFalse(is_mandoub_pos_name(None))

    def test_kitchen_display_name(self):
        self.assertEqual(
            kitchen_display_name_for_pos("مندوب — محمد صلاح"),
            "شاشة مندوب — محمد صلاح",
        )

    def test_stage_order_and_labels(self):
        names = [row["name"] for row in stage_spec_list()]
        self.assertEqual(names, ["التأكيد", "التوصيل", "الفوترة"])
        sequences = [row["sequence"] for row in stage_spec_list()]
        self.assertEqual(sequences, [1, 2, 3])

    def test_stage_spec_is_copied(self):
        specs = stage_spec_list()
        specs[0]["name"] = "changed"
        self.assertEqual(stage_spec_list()[0]["name"], "التأكيد")

    def test_shared_overview_name(self):
        self.assertEqual(SHARED_KITCHEN_NAME, "مناديب")

    def test_credit_payment_is_pay_later(self):
        vals = credit_payment_vals(3)
        self.assertEqual(vals["name"], CREDIT_PAYMENT_NAME)
        self.assertEqual(CREDIT_PAYMENT_NAME, "آجل")
        self.assertFalse(vals["journal_id"])
        self.assertTrue(vals["split_transactions"])
        self.assertEqual(vals["company_id"], 3)


class MandoubQuotationTests(unittest.TestCase):
    def test_origin_detects_mandoub_pos(self):
        self.assertTrue(is_mandoub_origin("مندوب — عبدالمجيد"))
        self.assertFalse(is_mandoub_origin("جملة الملابس — الشرقي"))
        self.assertFalse(is_mandoub_origin(""))

    def test_quotation_vals_from_flat_cart(self):
        vals = quotation_vals_from_pos_cart(
            {
                "partner_id": 26815,
                "uuid": "cart-1",
                "user_id": 120,
                "lines": [
                    {"product_id": 10, "qty": 2, "price_unit": 50, "discount": 0},
                    {"product_id": {"id": 11}, "qty": 1, "price_unit": 0},
                ],
            },
            {
                "origin": "مندوب — عبدالمجيد",
                "company_id": 3,
                "warehouse_id": 6,
                "payment_term_id": 4,
            },
        )
        self.assertEqual(vals["partner_id"], 26815)
        self.assertEqual(vals["origin"], "مندوب — عبدالمجيد")
        self.assertEqual(vals["client_order_ref"], "cart-1")
        self.assertEqual(vals["warehouse_id"], 6)
        self.assertEqual(len(vals["order_line"]), 2)
        self.assertEqual(vals["order_line"][0][2]["product_id"], 10)
        self.assertEqual(vals["order_line"][0][2]["product_uom_qty"], 2)
        self.assertEqual(vals["order_line"][1][2]["product_id"], 11)

    def test_quotation_vals_from_serialized_odoo_lines(self):
        vals = quotation_vals_from_pos_cart(
            {
                "partner_id": [9, "Customer"],
                "name": "Order 0001",
                "lines": [[0, 0, {"product_id": 5, "qty": 3, "price_unit": 12.5, "discount": 10}]],
            },
            {"origin": MANDOUB_POS_PREFIX + "اختبار", "company_id": 3},
        )
        self.assertEqual(vals["partner_id"], 9)
        self.assertEqual(vals["client_order_ref"], "Order 0001")
        self.assertEqual(vals["order_line"][0][2]["discount"], 10)

    def test_quotation_requires_partner_and_lines(self):
        with self.assertRaises(ValueError) as missing_partner:
            quotation_vals_from_pos_cart({"lines": [{"product_id": 1, "qty": 1}]}, {})
        self.assertEqual(str(missing_partner.exception), "partner_required")
        with self.assertRaises(ValueError) as empty_cart:
            quotation_vals_from_pos_cart({"partner_id": 1, "lines": []}, {})
        self.assertEqual(str(empty_cart.exception), "empty_cart")

    def test_normalize_arabic_matches_kashida_names(self):
        from mandoub_setup import normalize_arabic_name

        self.assertIn(
            normalize_arabic_name("عبدالمجيد"),
            normalize_arabic_name("عبدالمجيــد 111"),
        )

    def test_kitchen_card_note_and_stages(self):
        self.assertIn("S0001", kitchen_card_note("S0001", "عميل", "مندوب"))
        self.assertTrue(kitchen_card_note("S0001").startswith("[طلب]"))
        self.assertEqual(kitchen_stage_index("draft"), 0)
        self.assertEqual(kitchen_stage_index("sale"), 1)
        self.assertEqual(kitchen_stage_index("sale", delivery_done=True), 2)
        self.assertEqual(kitchen_stage_index("draft", invoiced=True), 2)
        self.assertIn("لا يفوتر", MANDOUB_QUOTATION_CREATED_MSG)
        self.assertIn("المدير فقط", MANAGER_CONFIRM_ONLY_MSG)
        self.assertIn("%s", MANDOUB_QUOTATION_CREATED_MSG)

    def test_default_pos_qty_uses_smallest_sales_pack_when_stock_unknown(self):
        self.assertEqual(DEFAULT_PACK_QTY, 12)
        self.assertEqual(default_pos_qty([]), 12)
        self.assertEqual(
            default_pos_qty(
                [
                    {"name": "PKG 24", "qty": 24, "sales": True},
                    {"name": "تعبئة 12", "qty": 12, "sales": True},
                    {"name": "شراء", "qty": 36, "sales": False},
                ]
            ),
            12,
        )
        self.assertEqual(sales_pack_qtys([{"qty": 12, "sales": True}, {"qty": 24, "sales": False}]), [12])

    def test_default_pos_qty_picks_largest_pack_that_fits_on_hand(self):
        packs = [
            {"qty": 12, "sales": True},
            {"qty": 24, "sales": True},
            {"qty": 36, "sales": True},
        ]
        self.assertEqual(default_pos_qty(packs, qty_on_hand=40), 36)
        self.assertEqual(default_pos_qty(packs, qty_on_hand=36), 36)
        self.assertEqual(default_pos_qty(packs, qty_on_hand=30), 24)
        self.assertEqual(default_pos_qty(packs, qty_on_hand=20), 12)
        self.assertEqual(default_pos_qty(packs, qty_on_hand=5), 5)
        self.assertEqual(default_pos_qty(packs, qty_on_hand=0), 12)
        self.assertEqual(default_pos_qty([{"qty": 12, "sales": True}], qty_on_hand=100), 12)

    def test_choose_pack_qty_subtracts_cart_qty(self):
        self.assertEqual(choose_pack_qty([12, 24, 36], qty_on_hand=40, already_in_cart=36), 4)
        self.assertEqual(choose_pack_qty([12, 24, 36], qty_on_hand=40, already_in_cart=40), 12)

    def test_factory_warehouse_code(self):
        from mandoub_setup import FACTORY_WAREHOUSE_CODE

        self.assertEqual(FACTORY_WAREHOUSE_CODE, "WH-MS")

    def test_only_finished_goods_category_is_allowed(self):
        from mandoub_setup import FINISHED_GOODS_CATEGORY_NAME, is_finished_goods_category

        self.assertEqual(FINISHED_GOODS_CATEGORY_NAME, "منتج تام")
        self.assertTrue(is_finished_goods_category("منتج تام"))
        self.assertTrue(is_finished_goods_category("منتج تام / زي مدرسي / بلايز ابتدائي"))
        self.assertTrue(is_finished_goods_category("منتج تام / لينجز"))
        self.assertFalse(is_finished_goods_category("خامات / كلف"))
        self.assertFalse(is_finished_goods_category("برودان / منتج تام"))
        self.assertFalse(is_finished_goods_category("الاقمشة"))
        self.assertFalse(is_finished_goods_category(""))


if __name__ == "__main__":
    unittest.main()
