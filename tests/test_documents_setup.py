import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brodansh_documents" / "models"))

from documents_setup import (
    ADMIN_GROUP_NAME,
    UNTITLED_FOLDER_NAME,
    classify_document,
    clean_folder_name,
    match_entity_key,
    should_skip_source_folder,
    subfolder_label,
)


class DocumentsSetupTests(unittest.TestCase):
    def test_admin_group_name(self):
        self.assertEqual(ADMIN_GROUP_NAME, "إدارة المستندات")
        self.assertEqual(UNTITLED_FOLDER_NAME, "جداول غير معنونة")

    def test_clean_folder_name(self):
        self.assertEqual(clean_folder_name("مصنع ذو الجناحين  "), "مصنع ذو الجناحين")
        self.assertEqual(clean_folder_name("عمارة  الرمال  "), "عمارة الرمال")

    def test_entity_from_filename(self):
        self.assertEqual(match_entity_key("سجل التجاري ابنتي.pdf"), "daughter")
        self.assertEqual(match_entity_key("رخصه الورشه.pdf"), "workshop")
        self.assertEqual(match_entity_key("العنوان - مصنع ذو الجناحين.pdf"), "factory")
        self.assertEqual(match_entity_key("عمارة الرمال عقد.pdf"), "ramal")
        self.assertEqual(match_entity_key("رخصة عمارة المصفاة.pdf"), "masfat")

    def test_classify_named_files(self):
        self.assertEqual(
            classify_document("سجل التجاري ابنتي.pdf", ""),
            ("daughter", None),
        )
        self.assertEqual(
            classify_document("عنوان الوطني مؤسسة ابنتي (1).png", ""),
            ("daughter", "addresses"),
        )
        self.assertEqual(
            classify_document("رخصه الورشه.pdf", "مستندات الورشة"),
            ("workshop", "licenses"),
        )
        self.assertEqual(
            classify_document("ترخيص صناعي.pdf", "مستندات المصنع"),
            ("factory", "licenses"),
        )
        self.assertEqual(
            classify_document("شهادة الزكاة.pdf", "مستندات المصنع "),
            ("factory", "certificates"),
        )
        self.assertEqual(
            classify_document("ضريبة  7 - 2025", "Spreadsheet"),
            ("factory", "tax"),
        )
        self.assertEqual(
            classify_document("مشهد صيانة.pdf", "الورشة"),
            ("workshop", "certificates"),
        )
        self.assertEqual(
            classify_document("التامينات.pdf", "مستندات المصنع"),
            ("factory", "certificates"),
        )
        self.assertEqual(
            classify_document("09- 2025 .pdf", "مصنع ذو الجناحين"),
            ("factory", "tax"),
        )

    def test_untitled_spreadsheets(self):
        self.assertEqual(
            classify_document("جدول بيانات بلا عنوان ", "Spreadsheet"),
            (None, "untitled"),
        )

    def test_source_folder_hint_without_name_match(self):
        self.assertEqual(
            classify_document("Adobe Scan ١٨_٠٨_٢٠٢٥.pdf", "مستندات المصنع"),
            ("factory", None),
        )
        self.assertEqual(
            classify_document("مبيعات 07  2025.xlsx", "Finance"),
            ("factory", "finance"),
        )

    def test_skip_hr_and_payroll(self):
        self.assertTrue(should_skip_source_folder("HR"))
        self.assertTrue(should_skip_source_folder("كشوف المرتبات "))
        self.assertFalse(should_skip_source_folder("مستندات المصنع "))

    def test_subfolder_labels(self):
        self.assertEqual(subfolder_label("licenses"), "تراخيص")
        self.assertEqual(subfolder_label("untitled"), "جداول غير معنونة")
        self.assertIsNone(subfolder_label("missing"))


if __name__ == "__main__":
    unittest.main()
