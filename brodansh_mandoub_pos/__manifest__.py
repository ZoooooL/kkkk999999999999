{
    "name": "برودانش — جلسات المناديب وشاشة المطبخ",
    "summary": "المندوب ينشئ الطلب من نقطة البيع، والمدير يؤكد، والمخازن توصل، والحسابات تفوتر",
    "version": "18.0.1.9.0",
    "category": "Sales/Point of Sale",
    "author": "Brodansh",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "pos_hr",
        "pos_preparation_display",
        "hr",
        "sale_management",
        "stock",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/mandoub_setup_wizard_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "brodansh_mandoub_pos/static/src/app/mandoub_quotation.js",
            "brodansh_mandoub_pos/static/src/app/mandoub_quotation.xml",
            "brodansh_mandoub_pos/static/src/app/mandoub_quotation.scss",
        ],
        "pos_preparation_display.assets": [
            "brodansh_mandoub_pos/static/src/kitchen/mandoub_kitchen.js",
            "brodansh_mandoub_pos/static/src/kitchen/mandoub_kitchen.scss",
        ],
    },
    "installable": True,
    "application": False,
}
