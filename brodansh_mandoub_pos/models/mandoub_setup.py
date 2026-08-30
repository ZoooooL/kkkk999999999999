# -*- coding: utf-8 -*-

MANDOUB_POS_PREFIX = "مندوب —"
KITCHEN_DISPLAY_PREFIX = "شاشة "
SHARED_KITCHEN_NAME = "مناديب"

KITCHEN_STAGES = [
    {"name": "مؤكد", "color": "#198754", "alert_timer": 15, "sequence": 1},
    {"name": "تم الشحن", "color": "#0d6efd", "alert_timer": 30, "sequence": 2},
    {"name": "الفوترة", "color": "#6f42c1", "alert_timer": 10, "sequence": 3},
]


def is_mandoub_pos_name(name):
    return bool(name) and name.startswith(MANDOUB_POS_PREFIX)


def kitchen_display_name_for_pos(pos_name):
    return "%s%s" % (KITCHEN_DISPLAY_PREFIX, pos_name)


def stage_spec_list():
    return [dict(item) for item in KITCHEN_STAGES]
