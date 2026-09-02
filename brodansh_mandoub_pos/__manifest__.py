{
    "name": "برودانش — جلسات المناديب وشاشة المطبخ",
    "summary": "المندوب ينشئ الطلب من نقطة البيع، والمدير يؤكد، والمخازن توصل، والحسابات تفوتر",
    "version": "18.0.1.11.0",
    "category": "Sales/Point of Sale",
    "author": "Brodansh",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "pos_hr",
        "pos_preparation_display",
        "pos_self_order",
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
        "pos_self_order.assets": [
            "brodansh_mandoub_pos/static/src/self_order/mandoub_customer.js",
            "brodansh_mandoub_pos/static/src/self_order/mandoub_customer.xml",
            "brodansh_mandoub_pos/static/src/self_order/mandoub_customer.scss",
        ],
        "web.assets_frontend": [
            "brodansh_mandoub_pos/static/src/frontend/install_scoped_app.js",
            "brodansh_mandoub_pos/static/src/frontend/install_scoped_app.xml",
            "brodansh_mandoub_pos/static/src/frontend/install_scoped_app.scss",
        ],
    },
    "installable": True,
    "application": False,
}
