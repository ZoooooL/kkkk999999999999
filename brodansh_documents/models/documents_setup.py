# -*- coding: utf-8 -*-

ADMIN_GROUP_NAME = "إدارة المستندات"
ADMIN_GROUP_COMMENT = (
    "يرى قائمة تهيئة المستندات والمجلدات المنظمة للكيانات. "
    "أضف المستخدمين هنا فقط."
)
UNTITLED_FOLDER_NAME = "جداول غير معنونة"

ENTITY_FOLDERS = (
    {
        "key": "factory",
        "name": "مصنع ذو الجناحين",
        "company_name": "مصنع ذو الجناحين للملابس الجاهزة",
        "pin": True,
    },
    {
        "key": "daughter",
        "name": "ابنتي الصغيرة",
        "company_name": "ابنتي الصغيرة",
        "pin": True,
    },
    {
        "key": "workshop",
        "name": "الورشة",
        "company_name": None,
        "pin": False,
    },
    {
        "key": "ramal",
        "name": "عمارة الرمال",
        "company_name": None,
        "pin": False,
    },
    {
        "key": "masfat",
        "name": "عمارة المصفاة",
        "company_name": None,
        "pin": False,
    },
)

SUBFOLDERS = (
    ("licenses", "تراخيص"),
    ("addresses", "عناوين"),
    ("certificates", "شهادات"),
    ("tax", "ضرائب"),
    ("finance", "مالية"),
    ("contracts", "عقود"),
    ("spreadsheets", "جداول"),
)

SOURCE_FOLDER_HINTS = {
    "مستندات المصنع": "factory",
    "مستندات الورشة": "workshop",
    "Finance": "factory",
    "الماليـــه": "factory",
    "الضريبة": "factory",
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

SKIP_MOVE_FOLDERS = (
    "HR",
    "Payroll",
    "كشوف المرتبات",
    "Fleet",
    "Sign",
    "Support",
    "Frozen spreadsheets",
)


def normalize_doc_name(text):
    return " ".join((text or "").replace("ـ", "").split()).strip().lower()


def clean_folder_name(text):
    return " ".join((text or "").split())


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
    if any(token in n for token in ("مصنع", "الجناحين", "janaheen", "zoul", "توطين")):
        return "factory"
    return None


def match_subfolder_key(name):
    n = normalize_doc_name(name)
    if "بلا عنوان" in n or "untitled" in n:
        return "untitled"
    if any(token in n for token in ("رخص", "ترخيص")):
        return "licenses"
    if "عنوان" in n:
        return "addresses"
    if any(token in n for token in ("شهاد", "استعراض")):
        return "certificates"
    if any(token in n for token in ("ضريب", "زكاة", "زكاه", "الذكاة", "قيمة مضافة", "اقرار", "إقرار")):
        return "tax"
    if any(token in n for token in ("عقد", "عقود")):
        return "contracts"
    if n.endswith(".xlsx") or any(token in n for token in ("مبيعات", "مشتريات", "اهلاك", "إهلاك")):
        return "finance"
    if n.endswith(".pdf") or n.endswith(".png") or n.endswith(".jpeg") or n.endswith(".jpg"):
        return None
    return None


def classify_document(name, source_folder_name=""):
    """Return (entity_key, subfolder_key). subfolder_key may be untitled/licenses/..."""
    entity = match_entity_key(name)
    if entity is None and source_folder_name:
        cleaned = clean_folder_name(source_folder_name)
        entity = SOURCE_FOLDER_HINTS.get(cleaned)
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
    if entity is None:
        return None, sub
    return entity, sub


def should_skip_source_folder(folder_name):
    cleaned = clean_folder_name(folder_name)
    return any(cleaned == name or cleaned.startswith(name) for name in SKIP_MOVE_FOLDERS)


def subfolder_label(key):
    for item_key, label in SUBFOLDERS:
        if item_key == key:
            return label
    if key == "untitled":
        return UNTITLED_FOLDER_NAME
    return None


def entity_spec(key):
    for spec in ENTITY_FOLDERS:
        if spec["key"] == key:
            return spec
    return None
