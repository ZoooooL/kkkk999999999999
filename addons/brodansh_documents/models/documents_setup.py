# -*- coding: utf-8 -*-
import re

ADMIN_GROUP_NAME = "إدارة المستندات"
ADMIN_GROUP_COMMENT = (
    "يرى قائمة تهيئة المستندات والمجلدات المنظمة للكيانات. "
    "أضف المستخدمين هنا فقط."
)
UNTITLED_FOLDER_NAME = "جداول غير معنونة"

SUBFOLDER_LABELS = {
    "licenses": "تراخيص",
    "addresses": "عناوين",
    "certificates": "شهادات",
    "tax": "ضرائب",
    "finance": "مالية",
    "contracts": "عقود",
    "commercial": "السجل التجاري",
}

# entity → (subfolder keys in display order, default key for leftover files)
ENTITY_FOLDERS = (
    {
        "key": "factory",
        "name": "مصنع ذو الجناحين",
        "company_name": "مصنع ذو الجناحين للملابس الجاهزة",
        "pin": True,
        "subfolders": ("licenses", "addresses", "certificates", "tax", "finance"),
        "default_sub": "certificates",
    },
    {
        "key": "daughter",
        "name": "ابنتي الصغيرة",
        "company_name": "ابنتي الصغيرة",
        "pin": True,
        "subfolders": ("commercial", "addresses"),
        "default_sub": "commercial",
    },
    {
        "key": "workshop",
        "name": "الورشة",
        "company_name": None,
        "pin": True,
        "subfolders": ("licenses", "contracts"),
        "default_sub": "licenses",
    },
    {
        "key": "ramal",
        "name": "عمارة الرمال",
        "company_name": None,
        "pin": True,
        "subfolders": ("licenses", "addresses", "contracts"),
        "default_sub": "licenses",
    },
    {
        "key": "masfat",
        "name": "عمارة المصفاة",
        "company_name": None,
        "pin": True,
        "subfolders": ("licenses", "addresses", "contracts"),
        "default_sub": "licenses",
    },
)

SOURCE_FOLDER_HINTS = {
    "مستندات المصنع": "factory",
    "مستندات الورشة": "workshop",
    "Finance": "factory",
    "الماليـــه": "factory",
    "الضريبة": "factory",
    "مصنع ذو الجناحين": "factory",
    "ابنتي الصغيرة": "daughter",
    "الورشة": "workshop",
    "عمارة الرمال": "ramal",
    "عمارة المصفاة": "masfat",
    "عقود اعتماد": "factory",
}

SENSITIVE_FOLDER_NAMES = (
    "Spreadsheet",
    "Finance",
    "مستندات المصنع",
    "مستندات الورشة",
    "مخالفات الموظفين",
    "عقود اعتماد",
    "الجرد 2024",
    "الضريبة",
)

SOURCE_SUBFOLDER_HINTS = {
    "الضريبة": "tax",
    "Finance": "finance",
    "الماليـــه": "finance",
    "عقود اعتماد": "finance",
}

SKIP_MOVE_FOLDERS = (
    "HR",
    "Payroll",
    "كشوف المرتبات",
    "Fleet",
    "Sign",
    "Support",
    "Frozen spreadsheets",
)

FILENAME_FIXES = (
    ("رخصه الورشه.pdf", "رخصة الورشة.pdf"),
    ("شهادة  الزكاة.pdf", "شهادة الزكاة.pdf"),
    ("ترخيص  صناعي.jpeg", "ترخيص صناعي.jpeg"),
    ("العنوان  الوطني  - المصنع.png", "العنوان الوطني - المصنع.png"),
    ("عنوان الوطني مؤسسة ابنتي (1).png", "العنوان الوطني - ابنتي الصغيرة.png"),
    ("سجل التجاري ابنتي.pdf", "السجل التجاري - ابنتي الصغيرة.pdf"),
    ("ارقام حسابات ابنتي  الصغيرة  - غرفة تجارية.pdf", "أرقام حسابات - ابنتي الصغيرة.pdf"),
    ("ضريبة  7 - 2025", "ضريبة 07-2025"),
    ("09- 2025 .pdf", "ضريبة 09-2025.pdf"),
    ("نموذج-إقرار-القيمة-المضافة-excel-السعودية (1).xlsx", "إقرار ضريبة القيمة المضافة.xlsx"),
    ("ميزانية 2023.pdf-مكتب الحملي.pdf", "ميزانية 2023 - مكتب الحملي.pdf"),
    ("ملف الأنشطة للسجل 1010295153 (1).pdf", "ملف أنشطة السجل 1010295153.pdf"),
    ("شهادة الذكاة والدخل.pdf", "شهادة الزكاة والدخل.pdf"),
    ("عقد الجامعه.pdf", "عقد جامعة الملك.pdf"),
)

SUBFOLDER_ALIASES = {
    ("factory", "commercial"): "licenses",
    ("factory", "contracts"): "finance",
    ("factory", "spreadsheets"): "finance",
    ("workshop", "certificates"): "contracts",
    ("workshop", "addresses"): "licenses",
    ("workshop", "tax"): "licenses",
    ("workshop", "finance"): "contracts",
    ("daughter", "licenses"): "commercial",
    ("daughter", "certificates"): "commercial",
    ("daughter", "finance"): "commercial",
    ("daughter", "tax"): "commercial",
    ("daughter", "contracts"): "commercial",
}


def normalize_doc_name(text):
    return " ".join((text or "").replace("ـ", "").split()).strip().lower()


def clean_folder_name(text):
    return " ".join((text or "").split())


def numbered_folder_name(index, label):
    return "%s-%s" % (index, label)


def strip_folder_number(name):
    cleaned = clean_folder_name(name)
    return re.sub(r"^\d+-", "", cleaned)


def entity_spec(key):
    for spec in ENTITY_FOLDERS:
        if spec["key"] == key:
            return spec
    return None


def subfolder_label(key):
    if key == "untitled":
        return UNTITLED_FOLDER_NAME
    return SUBFOLDER_LABELS.get(key)


def match_entity_key(name):
    n = normalize_doc_name(name)
    if any(token in n for token in ("ابنتي", "ابنتى")):
        return "daughter"
    if "ورش" in n:
        return "workshop"
    if "رمال" in n:
        return "ramal"
    if "مصفاة" in n:
        return "masfat"
    if any(token in n for token in ("مصنع", "الجناحين", "janaheen", "zoul", "توطين", "جامعة")):
        return "factory"
    return None


def match_subfolder_key(name):
    n = normalize_doc_name(name)
    if "بلا عنوان" in n or "untitled" in n:
        return "untitled"
    if any(token in n for token in ("سجل", "غرفة تجارية", "غرفه تجارية")):
        return "commercial"
    if any(token in n for token in ("رخص", "ترخيص")):
        return "licenses"
    if "عنوان" in n:
        return "addresses"
    if any(token in n for token in ("شهاد", "استعراض", "مشهد", "9001", "تامين", "تأمين", "adobe scan", "مسح")):
        return "certificates"
    if any(token in n for token in ("ضريب", "زكاة", "زكاه", "الذكاة", "قيمة مضافة", "اقرار", "إقرار")):
        return "tax"
    if any(token in n for token in ("عقد", "عقود", "جامعة", "جامعه")):
        return "contracts"
    if n.endswith(".xlsx") or any(
        token in n for token in ("مبيعات", "مشتريات", "اهلاك", "إهلاك", "شيكات", "ميزانية", "تحويل", "مستودع")
    ):
        return "finance"
    if ".pdf" in n and re.search(r"\d{1,2}\s*[-/.]\s*202\d", n):
        return "tax"
    if n.endswith(".pdf") or n.endswith(".png") or n.endswith(".jpeg") or n.endswith(".jpg"):
        return None
    return None


def classify_document(name, source_folder_name=""):
    """Return (entity_key, subfolder_key)."""
    entity = match_entity_key(name)
    if entity is None and source_folder_name:
        cleaned = clean_folder_name(source_folder_name)
        entity = SOURCE_FOLDER_HINTS.get(cleaned) or SOURCE_FOLDER_HINTS.get(strip_folder_number(cleaned))
        if entity is None:
            for hint, key in SOURCE_FOLDER_HINTS.items():
                if normalize_doc_name(hint) in normalize_doc_name(source_folder_name):
                    entity = key
                    break
    sub = match_subfolder_key(name)
    if sub == "untitled":
        return None, "untitled"
    if entity is None and sub in ("tax", "finance"):
        entity = "factory"
    if entity and not sub and source_folder_name:
        cleaned = clean_folder_name(source_folder_name)
        sub = SOURCE_SUBFOLDER_HINTS.get(cleaned) or SOURCE_SUBFOLDER_HINTS.get(strip_folder_number(cleaned))
        if sub is None:
            for hint, key in SOURCE_SUBFOLDER_HINTS.items():
                if normalize_doc_name(hint) in normalize_doc_name(source_folder_name):
                    sub = key
                    break
    if entity is None:
        return None, sub
    return entity, resolve_subfolder(entity, sub)


def resolve_subfolder(entity, sub):
    spec = entity_spec(entity)
    if not spec:
        return sub
    allowed = spec["subfolders"]
    if sub == "untitled":
        return "untitled"
    if (entity, sub) in SUBFOLDER_ALIASES:
        sub = SUBFOLDER_ALIASES[(entity, sub)]
    if sub in allowed:
        return sub
    return spec["default_sub"]


def should_skip_source_folder(folder_name):
    cleaned = strip_folder_number(folder_name)
    return any(cleaned == name or cleaned.startswith(name) for name in SKIP_MOVE_FOLDERS)


def tidy_filename(name):
    """Collapse spaces and apply known Arabic filename fixes."""
    original = name or ""
    stripped = " ".join(original.split())
    for old, new in FILENAME_FIXES:
        if normalize_doc_name(stripped) == normalize_doc_name(old):
            return new
    if "9001" in stripped.lower() or "zoul_janaheen" in stripped.lower():
        return "شهادة ISO 9001.pdf"
    if stripped.lower().endswith(".pdf-مكتب الحملي.pdf".lower()) or "مكتب الحملي" in stripped:
        cleaned = stripped.replace(".pdf-مكتب الحملي.pdf", " - مكتب الحملي.pdf")
        return " ".join(cleaned.split())
    stripped = re.sub(r"\s+\.(pdf|png|jpeg|jpg|xlsx)$", r".\1", stripped, flags=re.I)
    stripped = stripped.replace(" (1)", "").replace("  ", " ")
    return stripped


def untitled_title(index, name):
    suffix = " (نسخة)" if "نسخة" in (name or "") else ""
    return "جدول %02d%s" % (index, suffix)
