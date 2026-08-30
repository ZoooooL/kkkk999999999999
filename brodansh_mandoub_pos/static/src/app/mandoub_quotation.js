odoo.define("brodansh_mandoub_pos.mandoub_quotation", [
    "@web/core/l10n/translation",
    "@web/core/utils/patch",
    "@web/core/confirmation_dialog/confirmation_dialog",
    "@point_of_sale/app/store/pos_store",
    "@point_of_sale/app/screens/payment_screen/payment_screen",
    "@point_of_sale/app/screens/product_screen/product_screen",
    "@point_of_sale/app/screens/product_screen/action_pad/action_pad",
    "@point_of_sale/app/generic_components/product_card/product_card",
    "@odoo/owl",
], function (require) {
    "use strict";

    const { _t } = require("@web/core/l10n/translation");
    const { patch } = require("@web/core/utils/patch");
    const { AlertDialog } = require("@web/core/confirmation_dialog/confirmation_dialog");
    const { PosStore } = require("@point_of_sale/app/store/pos_store");
    const { PaymentScreen } = require("@point_of_sale/app/screens/payment_screen/payment_screen");
    const { ProductScreen } = require("@point_of_sale/app/screens/product_screen/product_screen");
    const actionPadMod = require("@point_of_sale/app/screens/product_screen/action_pad/action_pad");
    const ActionpadWidget = actionPadMod.ActionpadWidget || actionPadMod;
    const { ProductCard } = require("@point_of_sale/app/generic_components/product_card/product_card");
    const { onMounted, onPatched } = require("@odoo/owl");

const MANDOUB_POS_PREFIX = "مندوب —";
const FACTORY_WAREHOUSE_CODE = "WH-MS";
const STOCK_CHUNK = 200;

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

function collectPackQtys(product) {
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

function choosePackQty(packQtys, qtyOnHand = null, fallback = 12, alreadyInCart = 0) {
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

function salesPackQty(product, fallback = 12, alreadyInCart = 0) {
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

function formatOnHandQty(qty, env) {
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

function isMandoubQuotationPos(pos) {
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

function mandoubOrm(pos) {
    return pos.env?.services?.orm || pos.data?.orm;
}

function applyMandoubStockToProduct(product, onHand, packQtys) {
    const qtys = (packQtys || []).map(Number).filter((qty) => qty > 0);
    const packStr = qtys.map((qty) => String(qty)).join(",");
    const packQty = choosePackQty(qtys, onHand);
    product.mandoub_qty_on_hand = onHand;
    product.mandoub_pack_qtys = packStr;
    product.mandoub_pack_qty = packQty;
    if (product.raw) {
        product.raw.mandoub_qty_on_hand = onHand;
        product.raw.mandoub_pack_qtys = packStr;
        product.raw.mandoub_pack_qty = packQty;
    }
    return product;
}

async function resolveMandoubWarehouseId(pos, orm) {
    const pickingId = recordId(pos.config?.picking_type_id) || pos.pickingType?.id;
    if (pickingId) {
        const rows = await orm.call("stock.picking.type", "read", [[pickingId], ["warehouse_id"]]);
        const warehouseId = recordId(rows?.[0]?.warehouse_id);
        if (warehouseId) {
            return warehouseId;
        }
    }
    const found = await orm.searchRead("stock.warehouse", [["code", "=", FACTORY_WAREHOUSE_CODE]], ["id"]);
    return found?.[0]?.id || false;
}

async function loadMandoubWarehouseStock(pos) {
    if (!isMandoubQuotationPos(pos)) {
        return;
    }
    const products = pos.models?.["product.product"]?.getAll?.() || [];
    if (!products.length) {
        return;
    }
    const orm = mandoubOrm(pos);
    if (!orm?.call || !orm.searchRead) {
        return;
    }
    const warehouseId = await resolveMandoubWarehouseId(pos, orm);
    const ids = products.map((product) => product.id).filter(Boolean);
    const qtyById = {};
    const packById = {};
    for (let offset = 0; offset < ids.length; offset += STOCK_CHUNK) {
        const slice = ids.slice(offset, offset + STOCK_CHUNK);
        const rows = await orm.call("product.product", "read", [slice, ["qty_available"]], {
            context: warehouseId ? { warehouse_id: warehouseId } : {},
        });
        for (const row of rows || []) {
            qtyById[row.id] = row.qty_available;
        }
        const packs = await orm.searchRead(
            "product.packaging",
            [
                ["product_id", "in", slice],
                ["sales", "=", true],
                ["qty", ">", 0],
            ],
            ["product_id", "qty"]
        );
        for (const row of packs || []) {
            const productId = recordId(row.product_id);
            if (!productId) {
                continue;
            }
            if (!packById[productId]) {
                packById[productId] = [];
            }
            packById[productId].push(row.qty);
        }
    }
    for (const product of products) {
        applyMandoubStockToProduct(product, qtyById[product.id], packById[product.id] || []);
    }
}

function cartPayloadFromOrder(pos) {
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
    async processServerData() {
        await super.processServerData(...arguments);
        try {
            await loadMandoubWarehouseStock(this);
        } catch (error) {
            console.warn("Mandoub warehouse stock could not be loaded", error);
        }
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
    printMandoubQuotationPdf(orderId, printUrl) {
        if (!orderId && !printUrl) {
            return;
        }
        const url = printUrl || `/report/pdf/sale.report_saleorder/${orderId}`;
        window.open(url, "_blank");
    },
    async createMandoubQuotationViaOrm(payload) {
        const orm = mandoubOrm(this);
        const companyId = recordId(this.config?.company_id);
        let warehouseId = false;
        let paymentTermId = false;
        try {
            warehouseId = await resolveMandoubWarehouseId(this, orm);
        } catch (_error) {
            warehouseId = false;
        }
        try {
            const terms = await orm.searchRead(
                "account.payment.term",
                [
                    ["name", "=", "30 يوماً"],
                    ["company_id", "in", companyId ? [companyId, false] : [false]],
                ],
                ["id"]
            );
            paymentTermId = terms?.[0]?.id || false;
        } catch (_error) {
            paymentTermId = false;
        }
        const lines = (payload.lines || []).map((line, index) => [
            0,
            0,
            {
                sequence: (index + 1) * 10,
                product_id: line.product_id,
                product_uom_qty: line.qty,
                price_unit: line.price_unit,
                discount: line.discount || 0,
                name: line.full_product_name || false,
            },
        ]);
        const vals = {
            partner_id: payload.partner_id,
            origin: payload.origin,
            client_order_ref: payload.uuid || false,
            user_id: payload.user_id || false,
            pricelist_id: payload.pricelist_id || false,
            fiscal_position_id: payload.fiscal_position_id || false,
            note: payload.note || false,
            order_line: lines,
        };
        if (companyId) {
            vals.company_id = companyId;
        }
        if (warehouseId) {
            vals.warehouse_id = warehouseId;
        }
        if (paymentTermId) {
            vals.payment_term_id = paymentTermId;
        }
        const created = await orm.create("sale.order", [vals]);
        const orderId = Array.isArray(created) ? created[0] : created;
        const [order] = await orm.read("sale.order", [orderId], ["name"]);
        try {
            const shadowCreated = await orm.create(
                "pos.order",
                [
                    {
                        session_id: payload.session_id,
                        partner_id: payload.partner_id,
                        amount_tax: 0,
                        amount_total: 0,
                        amount_paid: 0,
                        amount_return: 0,
                        state: "draft",
                        to_invoice: false,
                        general_note: `[طلب] | ${order.name}`,
                        lines: (payload.lines || []).map((line) => [
                            0,
                            0,
                            {
                                product_id: line.product_id,
                                qty: line.qty,
                                price_unit: line.price_unit,
                                price_subtotal: (line.price_unit || 0) * (line.qty || 0),
                                price_subtotal_incl: (line.price_unit || 0) * (line.qty || 0),
                                full_product_name: line.full_product_name || "",
                            },
                        ]),
                    },
                ],
                { context: { mandoub_kitchen_shadow: true } }
            );
            const shadowId = Array.isArray(shadowCreated) ? shadowCreated[0] : shadowCreated;
            await orm.call("pos_preparation_display.order", "process_order", [shadowId], {
                context: { mandoub_kitchen_shadow: true },
            });
            await orm.call("pos.order", "action_pos_order_cancel", [[shadowId]], {
                context: { mandoub_kitchen_shadow: true },
            });
        } catch (_error) {
            console.warn("Mandoub kitchen card could not be created from POS", _error);
        }
        return {
            sale_order_id: orderId,
            name: order.name,
            print_url: `/report/pdf/sale.report_saleorder/${orderId}`,
        };
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
                body: _t("اختر العميل ثم اضغط حفظ و طباعة."),
            });
            return;
        }
        const ui = this.env.services.ui;
        ui.block();
        try {
            const payload = cartPayloadFromOrder(this);
            let result;
            try {
                result = await this.data.call("sale.order", "create_from_mandoub_pos", [payload]);
            } catch (_error) {
                result = await this.createMandoubQuotationViaOrm(payload);
            }
            this.printMandoubQuotationPdf(result.sale_order_id, result.print_url);
            this.removeOrder(order, false);
            this.add_new_order();
            this.env.services.dialog.add(AlertDialog, {
                title: _t("حفظ و طباعة"),
                body:
                    result.message ||
                    _t(
                        "تم حفظ عرض السعر %s وطباعته. يظهر في المطبخ كطلب. مدير المبيعات يؤكد ثم المستودع يشحّن ثم الحسابات تفوتر.",
                        result.name
                    ),
            });
        } catch (error) {
            this.env.services.dialog.add(AlertDialog, {
                title: _t("حفظ و طباعة"),
                body: error?.data?.message || error?.message || String(error),
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

function relabelMandoubPayButtons(root) {
    const scope = root && typeof root.querySelectorAll === "function" ? root : document;
    const label = "حفظ و طباعة";
    scope.querySelectorAll(".pay-order-button, .pay-button").forEach((button) => {
        const titled =
            button.querySelector("span.d-block, span.pay-name, .mandoub-pay-label") || null;
        if (titled) {
            if (titled.textContent !== label) {
                titled.textContent = label;
            }
        } else {
            let replaced = false;
            button.childNodes.forEach((node) => {
                if (node.nodeType === 3 && node.textContent.trim() && node.textContent.trim() !== label) {
                    node.textContent = " " + label;
                    replaced = true;
                }
            });
            if (!replaced && !(button.textContent || "").includes(label)) {
                let lab = button.querySelector(".mandoub-pay-label");
                if (!lab) {
                    lab = document.createElement("span");
                    lab.className = "mandoub-pay-label";
                    button.appendChild(lab);
                }
                lab.textContent = label;
            }
        }
        button.setAttribute("aria-label", label);
        button.setAttribute("title", label);
    });
}

function watchMandoubPayButtons(pos) {
    if (!isMandoubQuotationPos(pos) || document.documentElement.dataset.mandoubPayWatch === "1") {
        return;
    }
    document.documentElement.dataset.mandoubPayWatch = "1";
    const apply = () => relabelMandoubPayButtons(document);
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.body, { childList: true, subtree: true });
}

patch(ActionpadWidget.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            if (isMandoubQuotationPos(this.pos)) {
                relabelMandoubPayButtons(this.el || this.__owl__?.bdom?.el || document);
                watchMandoubPayButtons(this.pos);
            }
        });
        onPatched(() => {
            if (isMandoubQuotationPos(this.pos)) {
                relabelMandoubPayButtons(this.el || this.__owl__?.bdom?.el || document);
            }
        });
    },
    get displayActionName() {
        return isMandoubQuotationPos(this.pos) ? _t("حفظ و طباعة") : this.props.actionName;
    },
});

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            if (isMandoubQuotationPos(this.pos)) {
                relabelMandoubPayButtons(this.el || this.__owl__?.bdom?.el || document);
                watchMandoubPayButtons(this.pos);
            }
        });
        onPatched(() => {
            if (isMandoubQuotationPos(this.pos)) {
                relabelMandoubPayButtons(this.el || this.__owl__?.bdom?.el || document);
            }
        });
    },
    get mandoubPayLabel() {
        return isMandoubQuotationPos(this.pos) ? _t("حفظ و طباعة") : _t("Pay");
    },
    get mandoubPaymentLabel() {
        return isMandoubQuotationPos(this.pos) ? _t("حفظ و طباعة") : _t("Payment");
    },
});

patch(ProductCard.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => this.injectMandoubQtyBadge());
        onPatched(() => this.injectMandoubQtyBadge());
    },
    get mandoubShowQtyOnHand() {
        const qty = productValue(this.props.product, "mandoub_qty_on_hand");
        return qty !== undefined && qty !== null && qty !== false;
    },
    get mandoubQtyOnHandLabel() {
        return formatOnHandQty(productValue(this.props.product, "mandoub_qty_on_hand"), this.env);
    },
    injectMandoubQtyBadge() {
        const root = this.__owl__?.bdom?.el;
        if (!root || typeof root.querySelector !== "function") {
            return;
        }
        const existing = root.querySelector(".mandoub-qty-on-hand");
        if (!this.mandoubShowQtyOnHand) {
            existing?.remove();
            return;
        }
        let badge = existing;
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "mandoub-qty-on-hand";
            const img = root.querySelector(".product-img");
            if (img) {
                img.appendChild(badge);
            } else {
                badge.classList.add("mandoub-qty-no-image");
                const content = root.querySelector(".product-content") || root;
                content.prepend(badge);
            }
        }
        badge.textContent = this.mandoubQtyOnHandLabel;
    },
});

    return {
        salesPackQty,
        choosePackQty,
        loadMandoubWarehouseStock,
        applyMandoubStockToProduct,
        isMandoubQuotationPos,
        cartPayloadFromOrder,
    };
});
