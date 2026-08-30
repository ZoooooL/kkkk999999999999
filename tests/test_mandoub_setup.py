import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_mandoub_pos" / "models"))

from mandoub_setup import (
    SHARED_KITCHEN_NAME,
    is_mandoub_pos_name,
    kitchen_display_name_for_pos,
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
        self.assertEqual(names, ["مؤكد", "تم الشحن", "الفوترة"])
        sequences = [row["sequence"] for row in stage_spec_list()]
        self.assertEqual(sequences, [1, 2, 3])

    def test_stage_spec_is_copied(self):
        specs = stage_spec_list()
        specs[0]["name"] = "changed"
        self.assertEqual(stage_spec_list()[0]["name"], "مؤكد")

    def test_shared_overview_name(self):
        self.assertEqual(SHARED_KITCHEN_NAME, "مناديب")


if __name__ == "__main__":
    unittest.main()
