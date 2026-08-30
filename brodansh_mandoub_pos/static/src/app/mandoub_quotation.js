/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { ProductCard } from "@point_of_sale/app/generic_components/product_card/product_card";

const MANDOUB_POS_PREFIX = "مندوب —";

function productValue(product, name) {
    if (!product) {
        return undefined;
    }
    if (product[name] !== undefined) {
        return product[name];
    }
    if (product.raw && product.raw[name] !== undefined) {
        return product.raw[name];
    }
    return undefined;
}

export function collectPackQtys(product) {
    if (!product) {
        return [];
    }
    const loaded = productValue(product, "mandoub_pack_qtys");
    if (Array.isArray(loaded) && loaded.length) {
        return loaded.map(Number).filter((qty) => qty > 0);
    }
    if (typeof loaded === "string" && loaded.trim()) {
        return loaded
            .split(",")
            .map(Number)
            .filter((qty) => qty > 0);
    }
    const packs = product.packaging_ids || product.packagings || [];
    const qtys = [];
    for (const pack of packs) {
        const rec = pack && typeof pack === "object" ? pack : null;
        if (!rec || rec.sales === false) {
            continue;
        }
        const qty = Number(rec.qty);
        if (qty > 0) {
            qtys.push(qty);
        }
    }
    return qtys;
}

export function choosePackQty(packQtys, qtyOnHand = null, fallback = 12, alreadyInCart = 0) {
    const qtys = (packQtys || []).map(Number).filter((qty) => qty > 0);
    let remaining = null;
    if (qtyOnHand !== undefined && qtyOnHand !== null && qtyOnHand !== false) {
        remaining = Number(qtyOnHand) - Number(alreadyInCart || 0);
        if (Number.isNaN(remaining)) {
            remaining = null;
        }
    }
    if (!qtys.length) {
        if (remaining !== null && remaining > 0 && remaining < fallback) {
            return remaining;
        }
        return fallback;
    }
    if (remaining === null) {
        return Math.min(...qtys);
    }
    const fitting = qtys.filter((qty) => qty <= remaining);
    if (fitting.length) {
        return Math.max(...fitting);
    }
    if (remaining > 0) {
        return remaining;
    }
    return Math.min(...qtys);
}

export function salesPackQty(product, fallback = 12, alreadyInCart = 0) {
    if (!product) {
        return fallback;
    }
    const packQtys = collectPackQtys(product);
    let onHand = productValue(product, "mandoub_qty_on_hand");
    if (onHand === undefined || onHand === null || onHand === false) {
        onHand = null;
    }
    const loadedPackQty = productValue(product, "mandoub_pack_qty");
    if (!packQtys.length && loadedPackQty) {
        return choosePackQty([Number(loadedPackQty)], onHand, fallback, alreadyInCart);
    }
    return choosePackQty(packQtys, onHand, fallback, alreadyInCart);
}

export function formatOnHandQty(qty, env) {
    if (qty === undefined || qty === null || qty === false) {
        return "";
    }
    const n = Number(qty);
    if (Number.isNaN(n)) {
        return "";
    }
    if (env?.utils?.formatProductQty) {
        return env.utils.formatProductQty(n, false);
    }
    return Number.isInteger(n) ? String(n) : String(Math.round(n * 1000) / 1000);
}

function cartQtyForProduct(pos, product) {
    if (!pos || !product) {
        return 0;
    }
    const order = pos.get_order?.() || pos.getOrder?.();
    if (!order) {
        return 0;
    }
    const productId = product.id || productValue(product, "id");
    const lines = order.get_orderlines?.() || order.lines || [];
    let total = 0;
    for (const line of lines) {
        const lineProduct = line.get_product?.() || line.product_id;
        const lineId = lineProduct?.id || lineProduct;
        if (lineId === productId) {
            total += Number(line.get_quantity?.() || line.qty || 0);
        }
    }
    return total;
}

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
    async addProductToCurrentOrder(product, options = {}) {
        if (
            isMandoubQuotationPos(this) &&
            (options.quantity === undefined || options.quantity === null)
        ) {
            options = {
                ...options,
                quantity: salesPackQty(product, 12, cartQtyForProduct(this, product)),
            };
        }
        return super.addProductToCurrentOrder(product, options);
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

patch(ProductCard.prototype, {
    get mandoubShowQtyOnHand() {
        const qty = productValue(this.props.product, "mandoub_qty_on_hand");
        return qty !== undefined && qty !== null && qty !== false;
    },
    get mandoubQtyOnHandLabel() {
        return formatOnHandQty(productValue(this.props.product, "mandoub_qty_on_hand"), this.env);
    },
});
