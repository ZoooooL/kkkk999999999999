/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

const MANDOUB_POS_PREFIX = "مندوب —";

export function isMandoubQuotationPos(pos) {
    const config = pos?.config;
    if (!config) {
        return false;
    }
    if (config.mandoub_quotation_mode) {
        return true;
    }
    return Boolean(config.name) && String(config.name).startsWith(MANDOUB_POS_PREFIX);
}

function recordId(value) {
    if (!value) {
        return false;
    }
    if (typeof value === "object") {
        return value.id || false;
    }
    return value;
}

export function cartPayloadFromOrder(pos) {
    const order = pos.get_order();
    const partner = order.get_partner ? order.get_partner() : order.partner_id;
    const lines = (order.get_orderlines ? order.get_orderlines() : order.lines) || [];
    return {
        partner_id: recordId(partner),
        session_id: recordId(pos.session),
        config_id: recordId(pos.config),
        user_id: recordId(order.user_id) || recordId(pos.user) || recordId(pos.cashier),
        pricelist_id: recordId(order.pricelist_id),
        fiscal_position_id: recordId(order.fiscal_position_id),
        uuid: order.uuid,
        note: order.general_note || order.note || "",
        origin: pos.config?.name,
        lines: lines.map((line) => {
            const product = line.get_product ? line.get_product() : line.product_id;
            return {
                product_id: recordId(product),
                qty: line.get_quantity ? line.get_quantity() : line.qty,
                price_unit: line.get_unit_price ? line.get_unit_price() : line.price_unit,
                discount: line.get_discount ? line.get_discount() : line.discount || 0,
                full_product_name: line.full_product_name || line.get_full_product_name?.() || "",
            };
        }),
    };
}

patch(PosStore.prototype, {
    get isMandoubQuotationPos() {
        return isMandoubQuotationPos(this);
    },
    async pay() {
        if (isMandoubQuotationPos(this)) {
            return this.createMandoubQuotation();
        }
        return super.pay(...arguments);
    },
    async createMandoubQuotation() {
        const order = this.get_order();
        if (!order || order.is_empty?.() || !(order.lines || []).length) {
            this.env.services.dialog.add(AlertDialog, {
                title: _t("السلة فارغة"),
                body: _t("أضف أصنافاً قبل إنشاء الطلب."),
            });
            return;
        }
        const partner = order.get_partner ? order.get_partner() : order.partner_id;
        if (!partner) {
            this.env.services.dialog.add(AlertDialog, {
                title: _t("العميل مطلوب"),
                body: _t("اختر العميل ثم اضغط إنشاء طلب. المندوب لا يفوتر."),
            });
            return;
        }
        const ui = this.env.services.ui;
        ui.block();
        try {
            const result = await this.data.call("sale.order", "create_from_mandoub_pos", [
                cartPayloadFromOrder(this),
            ]);
            this.removeOrder(order, false);
            this.add_new_order();
            this.env.services.dialog.add(AlertDialog, {
                title: _t("تم إنشاء الطلب"),
                body:
                    result.message ||
                    _t(
                        "تم إنشاء الطلب %s. المدير يؤكد، ثم المخازن توصل، ثم الحسابات تفوتر.",
                        result.name
                    ),
            });
        } finally {
            ui.unblock();
        }
    },
});

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        if (isMandoubQuotationPos(this.pos)) {
            await this.pos.createMandoubQuotation();
            this.pos.showScreen("ProductScreen");
            return;
        }
        return super.validateOrder(isForceValidate);
    },
});

patch(ProductScreen.prototype, {
    get mandoubPayLabel() {
        return isMandoubQuotationPos(this.pos) ? _t("إنشاء طلب") : _t("Pay");
    },
    get mandoubPaymentLabel() {
        return isMandoubQuotationPos(this.pos) ? _t("إنشاء طلب") : _t("Payment");
    },
});
