odoo.define("brodansh_mandoub_pos.mandoub_quotation", [
    "@web/core/l10n/translation",
    "@web/core/utils/patch",
    "@web/core/confirmation_dialog/confirmation_dialog",
    "@point_of_sale/app/store/pos_store",
    "@point_of_sale/app/screens/payment_screen/payment_screen",
    "@point_of_sale/app/screens/product_screen/product_screen",
    "@odoo/owl",
], function (require) {
    "use strict";

    const { _t } = require("@web/core/l10n/translation");
    const { patch } = require("@web/core/utils/patch");
    const { AlertDialog } = require("@web/core/confirmation_dialog/confirmation_dialog");
    const { PosStore } = require("@point_of_sale/app/store/pos_store");
    const { PaymentScreen } = require("@point_of_sale/app/screens/payment_screen/payment_screen");
    const { ProductScreen } = require("@point_of_sale/app/screens/product_screen/product_screen");
    const { onMounted, onPatched, useState } = require("@odoo/owl");

    const MANDOUB_POS_PREFIX = "مندوب —";
    const FACTORY_WAREHOUSE_CODE = "WH-MS";
    const STOCK_CHUNK = 200;
    const DEFAULT_PACK_QTY = 12;
    const SAVE_PRINT_LABEL = "حفظ و طباعة";

    function optionalRequire(name) {
        try {
            return require(name);
        } catch (_error) {
            return null;
        }
    }

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

    function packUnitQty(packQtys, fallback = DEFAULT_PACK_QTY) {
        const qtys = (packQtys || []).map(Number).filter((qty) => qty > 0);
        return qtys.length ? Math.min(...qtys) : fallback;
    }

    function wholesaleLineQty(packQtys, packCount = 1, fallback = DEFAULT_PACK_QTY) {
        let count = Number(packCount);
        if (!count || count < 0 || Number.isNaN(count)) {
            count = 1;
        }
        return packUnitQty(packQtys, fallback) * count;
    }

    function productPackUnit(product, fallback = DEFAULT_PACK_QTY) {
        const packQtys = collectPackQtys(product);
        const loaded = Number(productValue(product, "mandoub_pack_qty"));
        if (!packQtys.length && loaded > 0) {
            return loaded;
        }
        return packUnitQty(packQtys, fallback);
    }

    function formatOnHandQty(qty) {
        if (qty === undefined || qty === null || qty === false) {
            return "";
        }
        const n = Number(qty);
        if (Number.isNaN(n)) {
            return "";
        }
        return Number.isInteger(n) ? String(n) : String(Math.round(n * 1000) / 1000);
    }

    function posConfigName(pos) {
        const name = pos?.config?.name;
        if (typeof name === "string") {
            return name;
        }
        if (name && typeof name === "object") {
            return name.display_name || name.name || "";
        }
        return String(name || "");
    }

    function isMandoubQuotationPos(pos) {
        const config = pos?.config;
        if (!config) {
            return false;
        }
        if (config.mandoub_quotation_mode) {
            return true;
        }
        return posConfigName(pos).startsWith(MANDOUB_POS_PREFIX);
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

    function mandoubCall(pos, model, method, args, kwargs) {
        if (pos.data?.call) {
            return pos.data.call(model, method, args, kwargs || {});
        }
        const orm = pos.env?.services?.orm;
        if (!orm?.call) {
            throw new Error("POS ORM is not available");
        }
        return orm.call(model, method, args, kwargs || {});
    }

    function mandoubSearchRead(pos, model, domain, fields) {
        if (pos.data?.searchRead) {
            return pos.data.searchRead(model, domain, fields);
        }
        const orm = pos.env?.services?.orm;
        if (orm?.searchRead) {
            return orm.searchRead(model, domain, fields);
        }
        return mandoubCall(pos, model, "search_read", [domain, fields]);
    }

    function applyMandoubStockToProduct(product, onHand, packQtys) {
        const qtys = (packQtys || []).map(Number).filter((qty) => qty > 0);
        const packStr = qtys.map((qty) => String(qty)).join(",");
        const packQty = packUnitQty(qtys);
        const qty = onHand === undefined || onHand === null ? 0 : Number(onHand);
        product.mandoub_qty_on_hand = qty;
        product.mandoub_pack_qtys = packStr;
        product.mandoub_pack_qty = packQty;
        if (product.raw) {
            product.raw.mandoub_qty_on_hand = qty;
            product.raw.mandoub_pack_qtys = packStr;
            product.raw.mandoub_pack_qty = packQty;
        }
        return product;
    }

    async function resolveMandoubWarehouseId(pos) {
        const pickingId = recordId(pos.config?.picking_type_id) || pos.pickingType?.id;
        if (pickingId) {
            const rows = await mandoubCall(pos, "stock.picking.type", "read", [
                [pickingId],
                ["warehouse_id"],
            ]);
            const warehouseId = recordId(rows?.[0]?.warehouse_id);
            if (warehouseId) {
                return warehouseId;
            }
        }
        const found = await mandoubSearchRead(
            pos,
            "stock.warehouse",
            [["code", "=", FACTORY_WAREHOUSE_CODE]],
            ["id"]
        );
        return found?.[0]?.id || false;
    }

    function posProducts(pos) {
        const model = pos.models?.["product.product"] || pos.data?.models?.["product.product"];
        if (!model) {
            return [];
        }
        if (typeof model.getAll === "function") {
            return model.getAll();
        }
        return [];
    }

    function productById(pos, id) {
        const model = pos.models?.["product.product"] || pos.data?.models?.["product.product"];
        if (!model || !id) {
            return null;
        }
        if (typeof model.get === "function") {
            return model.get(id);
        }
        return posProducts(pos).find((product) => product.id === id) || null;
    }

    function templateQty(pos, product, qtyById) {
        const own = qtyById[product.id];
        const configurable =
            product.isConfigurable?.() ||
            (product.attribute_line_ids && product.attribute_line_ids.length);
        if (!configurable) {
            return own;
        }
        const tmplId =
            recordId(product.product_tmpl_id) ||
            product.raw?.product_tmpl_id ||
            product.product_tmpl_id;
        if (!tmplId) {
            return own;
        }
        let total = 0;
        let found = false;
        for (const other of posProducts(pos)) {
            const otherTmpl =
                recordId(other.product_tmpl_id) || other.raw?.product_tmpl_id || other.product_tmpl_id;
            if (otherTmpl === tmplId && qtyById[other.id] !== undefined) {
                total += Number(qtyById[other.id]) || 0;
                found = true;
            }
        }
        return found ? total : own;
    }

    async function loadMandoubWarehouseStock(pos) {
        if (!isMandoubQuotationPos(pos) || pos._mandoubStockLoading) {
            return;
        }
        const products = posProducts(pos);
        if (!products.length) {
            return;
        }
        pos._mandoubStockLoading = true;
        try {
            const warehouseId = await resolveMandoubWarehouseId(pos);
            const ids = products.map((product) => product.id).filter(Boolean);
            const qtyById = {};
            const packById = {};
            for (let offset = 0; offset < ids.length; offset += STOCK_CHUNK) {
                const slice = ids.slice(offset, offset + STOCK_CHUNK);
                const rows = await mandoubCall(
                    pos,
                    "product.product",
                    "read",
                    [slice, ["qty_available"]],
                    { context: warehouseId ? { warehouse_id: warehouseId } : {} }
                );
                for (const row of rows || []) {
                    qtyById[row.id] = row.qty_available;
                }
                const packs = await mandoubSearchRead(
                    pos,
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
                applyMandoubStockToProduct(
                    product,
                    templateQty(pos, product, qtyById),
                    packById[product.id] || []
                );
            }
            pos._mandoubWarehouseId = warehouseId;
            pos._mandoubStockReady = true;
            decorateMandoubProductCards(pos);
        } catch (error) {
            console.warn("Mandoub warehouse stock could not be loaded", error);
        } finally {
            pos._mandoubStockLoading = false;
        }
    }

    function paintProductCard(el, qty) {
        if (!el || typeof el.querySelector !== "function") {
            return;
        }
        const known = qty !== undefined && qty !== null && qty !== false && !Number.isNaN(Number(qty));
        const n = known ? Number(qty) : null;
        el.classList.toggle("mandoub-out-of-stock", known && n <= 0);
        el.classList.toggle("mandoub-has-stock", known && n > 0);
        let badge = el.querySelector(":scope > .mandoub-qty-on-hand");
        if (!known) {
            badge?.remove();
            return;
        }
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "mandoub-qty-on-hand";
            el.appendChild(badge);
        }
        badge.classList.toggle("mandoub-qty-zero", n <= 0);
        badge.textContent = formatOnHandQty(n);
    }

    function decorateMandoubProductCards(pos) {
        if (!pos || !isMandoubQuotationPos(pos)) {
            return;
        }
        document.querySelectorAll("article.product[data-product-id]").forEach((el) => {
            const product = productById(pos, Number(el.dataset.productId));
            if (!product) {
                return;
            }
            paintProductCard(el, productValue(product, "mandoub_qty_on_hand"));
        });
        relabelMandoubPayButtons(document);
    }

    function relabelMandoubPayButtons(root) {
        const scope = root && typeof root.querySelectorAll === "function" ? root : document;
        scope.querySelectorAll(
            ".pay-order-button, .pay-button, .payment-screen .validation-button, .payment-screen button.next"
        ).forEach((button) => {
            const titled =
                button.querySelector("span.d-block, span.pay-name, .mandoub-pay-label") || null;
            if (titled) {
                if (titled.textContent !== SAVE_PRINT_LABEL) {
                    titled.textContent = SAVE_PRINT_LABEL;
                }
            } else {
                let replaced = false;
                button.childNodes.forEach((node) => {
                    if (node.nodeType === 3 && node.textContent.trim() && node.textContent.trim() !== SAVE_PRINT_LABEL) {
                        node.textContent = " " + SAVE_PRINT_LABEL;
                        replaced = true;
                    }
                });
                if (!replaced && !(button.textContent || "").includes(SAVE_PRINT_LABEL)) {
                    let lab = button.querySelector(".mandoub-pay-label");
                    if (!lab) {
                        lab = document.createElement("span");
                        lab.className = "mandoub-pay-label";
                        button.appendChild(lab);
                    }
                    lab.textContent = SAVE_PRINT_LABEL;
                }
            }
            button.setAttribute("aria-label", SAVE_PRINT_LABEL);
            button.setAttribute("title", SAVE_PRINT_LABEL);
        });
    }

    function watchMandoubUi(pos) {
        if (!pos || document.documentElement.dataset.mandoubUiWatch === "1") {
            return;
        }
        document.documentElement.dataset.mandoubUiWatch = "1";
        const apply = () => decorateMandoubProductCards(pos);
        apply();
        const observer = new MutationObserver(apply);
        observer.observe(document.body, { childList: true, subtree: true });
        loadMandoubWarehouseStock(pos);
        document.addEventListener(
            "click",
            (event) => {
                if (!isMandoubQuotationPos(pos)) {
                    return;
                }
                const payBtn = event.target.closest?.(".pay-order-button, .pay-button");
                const validateBtn = event.target.closest?.(
                    ".payment-screen button.next, .payment-screen .button.next, .payment-screen .validation-button"
                );
                if (!payBtn && !validateBtn) {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                pos.createMandoubQuotation();
            },
            true
        );
    }

    function capturePackCount(pos, vals) {
        const qty = Number(vals?.qty);
        if (qty && qty > 0 && qty !== 1) {
            return qty;
        }
        if (pos.numpadMode === "quantity") {
            const buf = pos.numberBuffer?.get?.();
            if (buf) {
                const parsed = parseFloat(buf);
                if (parsed && parsed > 0) {
                    return parsed;
                }
            }
        }
        return 1;
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
            origin: posConfigName(pos),
            lines: lines.map((line) => {
                const product = line.get_product ? line.get_product() : line.product_id;
                const cartonQty = Number(line.get_quantity ? line.get_quantity() : line.qty) || 0;
                const packQty = productPackUnit(product);
                return {
                    product_id: recordId(product),
                    qty: cartonQty,
                    carton_qty: cartonQty,
                    pack_qty: packQty,
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
        async setup() {
            const result = await super.setup(...arguments);
            try {
                if (isMandoubQuotationPos(this)) {
                    await loadMandoubWarehouseStock(this);
                    watchMandoubUi(this);
                }
            } catch (error) {
                console.warn("Mandoub POS setup extras failed", error);
            }
            return result;
        },
        async processServerData() {
            await super.processServerData(...arguments);
            try {
                await loadMandoubWarehouseStock(this);
            } catch (error) {
                console.warn("Mandoub warehouse stock could not be loaded", error);
            }
        },
        async pay() {
            if (isMandoubQuotationPos(this)) {
                return this.openMandoubSavePrint();
            }
            return super.pay(...arguments);
        },
        showScreen(name, props) {
            if (name === "PaymentScreen" && isMandoubQuotationPos(this)) {
                if (currentOrderPartner(this)) {
                    return this.createMandoubQuotation();
                }
            }
            return super.showScreen(name, props);
        },
        async openMandoubSavePrint() {
            if (!isMandoubQuotationPos(this)) {
                return super.pay?.(...arguments);
            }
            if (currentOrderPartner(this)) {
                return this.createMandoubQuotation();
            }
            this.mobile_pane = "right";
            return super.showScreen("PaymentScreen", {
                orderUuid: this.selectedOrderUuid,
            });
        },
        mandoubQuotationFormUrl(orderId) {
            const companyId = recordId(this.config?.company_id);
            const cids = companyId ? `&cids=${companyId}` : "";
            return `/web#model=sale.order&id=${orderId}&view_type=form${cids}`;
        },
        openMandoubQuotation(orderId) {
            if (!orderId) {
                return;
            }
            const formUrl = this.mandoubQuotationFormUrl(orderId);
            const opened = window.open(formUrl, "_blank");
            const action = this.action || this.env?.services?.action;
            if (!opened && action?.doAction) {
                action.doAction({
                    type: "ir.actions.act_url",
                    url: formUrl,
                    target: "new",
                });
            }
        },
        printMandoubQuotationPdf(orderId, printUrl) {
            if (!orderId && !printUrl) {
                return;
            }
            const url = printUrl || `/report/pdf/sale.report_saleorder/${orderId}`;
            const popup = window.open(url, "_blank");
            if (popup) {
                setTimeout(() => {
                    try {
                        popup.focus();
                        popup.print();
                    } catch (_error) {
                        /* browser may block print until the PDF loads */
                    }
                }, 1200);
            }
        },
        async createMandoubQuotationViaOrm(payload) {
            const companyId = recordId(this.config?.company_id);
            let warehouseId = false;
            let paymentTermId = false;
            try {
                warehouseId = await resolveMandoubWarehouseId(this);
            } catch (_error) {
                warehouseId = false;
            }
            try {
                const terms = await mandoubSearchRead(
                    this,
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
            const lines = (payload.lines || []).map((line, index) => {
                const cartonQty = Number(line.carton_qty || line.qty) || 0;
                const packQty = Number(line.pack_qty) || productPackUnit({ mandoub_pack_qty: line.pack_qty });
                const pieceQty = wholesaleLineQty([packQty], cartonQty, packQty || DEFAULT_PACK_QTY);
                const name = line.full_product_name
                    ? `${line.full_product_name} — ${cartonQty} كرتون × ${packQty || DEFAULT_PACK_QTY}`
                    : false;
                return [
                    0,
                    0,
                    {
                        sequence: (index + 1) * 10,
                        product_id: line.product_id,
                        product_uom_qty: pieceQty,
                        price_unit: line.price_unit,
                        discount: line.discount || 0,
                        name,
                    },
                ];
            });
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
            const created = await mandoubCall(this, "sale.order", "create", [[vals]]);
            const orderId = Array.isArray(created) ? created[0] : created;
            const [order] = await mandoubCall(this, "sale.order", "read", [[orderId], ["name"]]);
            try {
                const shadowCreated = await mandoubCall(
                    this,
                    "pos.order",
                    "create",
                    [
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
                                lines: (payload.lines || []).map((line) => {
                                    const cartonQty = Number(line.carton_qty || line.qty) || 0;
                                    const packQty = Number(line.pack_qty) || DEFAULT_PACK_QTY;
                                    const pieceQty = wholesaleLineQty([packQty], cartonQty, packQty);
                                    return [
                                        0,
                                        0,
                                        {
                                            product_id: line.product_id,
                                            qty: pieceQty,
                                            price_unit: line.price_unit,
                                            price_subtotal: (line.price_unit || 0) * pieceQty,
                                            price_subtotal_incl: (line.price_unit || 0) * pieceQty,
                                            full_product_name: line.full_product_name || "",
                                        },
                                    ];
                                }),
                            },
                        ],
                    ],
                    { context: { mandoub_kitchen_shadow: true } }
                );
                const shadowId = Array.isArray(shadowCreated) ? shadowCreated[0] : shadowCreated;
                await mandoubCall(
                    this,
                    "pos_preparation_display.order",
                    "process_order",
                    [shadowId],
                    { context: { mandoub_kitchen_shadow: true } }
                );
                await mandoubCall(
                    this,
                    "pos.order",
                    "action_pos_order_cancel",
                    [[shadowId]],
                    { context: { mandoub_kitchen_shadow: true } }
                );
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
            if (this._mandoubSaving) {
                return;
            }
            const order = this.get_order();
            if (!order || order.is_empty?.() || !(order.lines || []).length) {
                this.env.services.dialog.add(AlertDialog, {
                    title: _t("السلة فارغة"),
                    body: _t("أضف أصنافاً قبل حفظ و طباعة عرض السعر."),
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
            this._mandoubSaving = true;
            ui.block();
            try {
                const payload = cartPayloadFromOrder(this);
                let result;
                try {
                    result = await this.data.call("sale.order", "create_from_mandoub_pos", [payload]);
                } catch (_error) {
                    result = await this.createMandoubQuotationViaOrm(payload);
                }
                this.openMandoubQuotation(result.sale_order_id);
                this.printMandoubQuotationPdf(result.sale_order_id, result.print_url);
                this.removeOrder(order, false);
                this.add_new_order();
                this.showScreen?.("ProductScreen");
                this.env.services.dialog.add(AlertDialog, {
                    title: _t("حفظ و طباعة"),
                    body:
                        result.message ||
                        _t("تم حفظ عرض السعر %s وطباعته.", result.name || ""),
                });
            } catch (error) {
                this.env.services.dialog.add(AlertDialog, {
                    title: _t("حفظ و طباعة"),
                    body: error?.data?.message || error?.message || String(error),
                });
            } finally {
                this._mandoubSaving = false;
                ui.unblock();
            }
        },
        async getProductInfo(product, quantity, priceExtra = 0) {
            const result = await super.getProductInfo(product, quantity, priceExtra);
            if (!isMandoubQuotationPos(this) || !result?.productInfo) {
                return result;
            }
            const warehouseId = this._mandoubWarehouseId;
            const qty = productValue(product, "mandoub_qty_on_hand");
            const warehouses = result.productInfo.warehouses || [];
            if (qty !== undefined && qty !== null && warehouseId) {
                let found = false;
                result.productInfo.warehouses = warehouses
                    .map((row) => {
                        if (row.id === warehouseId) {
                            found = true;
                            return { ...row, available_quantity: qty, forecasted_quantity: qty };
                        }
                        return row;
                    })
                    .sort((left, right) => (left.id === warehouseId ? -1 : right.id === warehouseId ? 1 : 0));
                if (!found) {
                    result.productInfo.warehouses.unshift({
                        id: warehouseId,
                        name: "مستودع المصنع",
                        available_quantity: qty,
                        forecasted_quantity: qty,
                        uom: product.uom_id?.name || "",
                    });
                }
            } else if (qty !== undefined && qty !== null && warehouses[0]) {
                warehouses[0].available_quantity = qty;
                warehouses[0].forecasted_quantity = qty;
            }
            return result;
        },
    });

    patch(PaymentScreen.prototype, {
        setup() {
            super.setup(...arguments);
            this.mandoubCustomer = useState({
                query: partnerDisplay(currentOrderPartner(this.pos)),
                matches: [],
                error: "",
            });
            onMounted(() => {
                if (!isMandoubQuotationPos(this.pos)) {
                    return;
                }
                this.el?.classList.add("mandoub-save-print");
                relabelMandoubPayButtons(this.el || document);
                if (!this.mandoubCustomer.query) {
                    this.mandoubCustomer.query = partnerDisplay(currentOrderPartner(this.pos));
                }
            });
        },
        get showMandoubCustomerBar() {
            return isMandoubQuotationPos(this.pos);
        },
        get mandoubValidateLabel() {
            return isMandoubQuotationPos(this.pos) ? _t(SAVE_PRINT_LABEL) : _t("Validate");
        },
        onMandoubCustomerInput(ev) {
            this.mandoubCustomer.query = ev.target.value;
            this.mandoubCustomer.error = "";
            this.searchMandoubCustomer(ev.target.value);
        },
        onMandoubCustomerFocus() {
            if ((this.mandoubCustomer.query || "").trim()) {
                this.searchMandoubCustomer(this.mandoubCustomer.query);
            }
        },
        onMandoubCustomerKeydown(ev) {
            if (ev.key === "Enter") {
                ev.preventDefault();
                this.confirmMandoubCustomer();
            }
        },
        async searchMandoubCustomer(query) {
            const text = (query || "").trim();
            if (!text) {
                this.mandoubCustomer.matches = [];
                return;
            }
            let matches = localPartnerMatches(this.pos, text);
            if (matches.length < 3 && this.pos.data?.searchRead) {
                try {
                    const remote = await this.pos.data.searchRead("res.partner", [
                        "|",
                        "|",
                        ["name", "ilike", text],
                        ["phone", "ilike", text],
                        ["mobile", "ilike", text],
                    ]);
                    if (Array.isArray(remote) && remote.length) {
                        matches = remote;
                    }
                } catch (_error) {
                    // Keep local matches when the live search is unavailable.
                }
            }
            this.mandoubCustomer.matches = matches.slice(0, 12);
        },
        selectMandoubCustomer(partner) {
            assignOrderPartner(this.pos, partner);
            this.mandoubCustomer.query = partnerDisplay(partner);
            this.mandoubCustomer.matches = [];
            this.mandoubCustomer.error = "";
        },
        async confirmMandoubCustomer() {
            const text = (this.mandoubCustomer.query || "").trim();
            if (!text) {
                this.mandoubCustomer.error = _t("اكتب اسم العميل أولاً ثم اضغط حفظ و طباعة.");
                return false;
            }
            const exact = (this.mandoubCustomer.matches || []).find(
                (partner) => partnerDisplay(partner).replace("ـ", "").trim() === text
            );
            if (exact) {
                this.selectMandoubCustomer(exact);
                return true;
            }
            const localExact = localPartnerMatches(this.pos, text).find(
                (partner) => partnerDisplay(partner).replace("ـ", "").trim() === text
            );
            if (localExact) {
                this.selectMandoubCustomer(localExact);
                return true;
            }
            try {
                let partner = null;
                if (this.pos.data?.create) {
                    const created = await this.pos.data.create("res.partner", [
                        { name: text, customer_rank: 1 },
                    ]);
                    partner = Array.isArray(created) ? created[0] : created;
                } else if (this.pos.data?.call) {
                    const partnerId = await this.pos.data.call("res.partner", "create", [
                        { name: text, customer_rank: 1 },
                    ]);
                    partner = this.pos.models["res.partner"].get(partnerId) || {
                        id: partnerId,
                        name: text,
                    };
                }
                if (partner) {
                    this.selectMandoubCustomer(partner);
                    return true;
                }
            } catch (_error) {
                this.mandoubCustomer.error = _t("تعذر حفظ العميل. أعد المحاولة.");
                return false;
            }
            this.mandoubCustomer.error = _t("تعذر حفظ العميل. أعد المحاولة.");
            return false;
        },
        async validateOrder(isForceValidate) {
            if (isMandoubQuotationPos(this.pos)) {
                if (!currentOrderPartner(this.pos)) {
                    const saved = await this.confirmMandoubCustomer();
                    if (!saved) {
                        return;
                    }
                }
                await this.pos.createMandoubQuotation();
                this.pos.showScreen("ProductScreen");
                return;
            }
            return super.validateOrder(isForceValidate);
        },
        async _finalizeValidation() {
            if (isMandoubQuotationPos(this.pos)) {
                await this.pos.createMandoubQuotation();
                this.pos.showScreen("ProductScreen");
                return;
            }
            return super._finalizeValidation(...arguments);
        },
    });

    function partnerDisplay(partner) {
        if (!partner) {
            return "";
        }
        return partner.name || partner.display_name || "";
    }

    function partnerPhone(partner) {
        if (!partner) {
            return "";
        }
        return partner.phone || partner.mobile || "";
    }

    function currentOrderPartner(pos) {
        const order = pos.get_order?.();
        if (!order) {
            return null;
        }
        if (order.get_partner) {
            return order.get_partner();
        }
        return order.partner_id || null;
    }

    function assignOrderPartner(pos, partner) {
        const order = pos.get_order?.();
        if (!order || !partner) {
            return;
        }
        if (order.set_partner) {
            order.set_partner(partner);
        } else if (order.update) {
            order.update({ partner_id: partner });
        } else {
            order.partner_id = partner;
        }
    }

    function localPartnerMatches(pos, query) {
        const needle = (query || "").trim().toLowerCase();
        if (!needle || !pos.models?.["res.partner"]) {
            return [];
        }
        const records = pos.models["res.partner"].getAll?.() || [];
        const matches = [];
        for (const partner of records) {
            const name = partnerDisplay(partner).toLowerCase();
            const phone = partnerPhone(partner);
            if (name.includes(needle) || phone.includes(query.trim())) {
                matches.push(partner);
            }
            if (matches.length >= 12) {
                break;
            }
        }
        return matches;
    }

    patch(ProductScreen.prototype, {
        setup() {
            super.setup(...arguments);
            this.mandoubCustomer = useState({
                query: partnerDisplay(currentOrderPartner(this.pos)),
                matches: [],
                error: "",
            });
            onMounted(() => {
                if (isMandoubQuotationPos(this.pos)) {
                    watchMandoubUi(this.pos);
                    loadMandoubWarehouseStock(this.pos);
                    if (!this.mandoubCustomer.query) {
                        this.mandoubCustomer.query = partnerDisplay(currentOrderPartner(this.pos));
                    }
                }
            });
            onPatched(() => {
                if (isMandoubQuotationPos(this.pos)) {
                    decorateMandoubProductCards(this.pos);
                }
            });
        },
        get showMandoubCustomerBar() {
            return isMandoubQuotationPos(this.pos);
        },
        get mandoubPayLabel() {
            return isMandoubQuotationPos(this.pos) ? _t(SAVE_PRINT_LABEL) : _t("Pay");
        },
        get mandoubPaymentLabel() {
            return isMandoubQuotationPos(this.pos) ? _t(SAVE_PRINT_LABEL) : _t("Payment");
        },
        onMandoubCustomerInput(ev) {
            this.mandoubCustomer.query = ev.target.value;
            this.mandoubCustomer.error = "";
            this.searchMandoubCustomer(ev.target.value);
        },
        onMandoubCustomerFocus() {
            if ((this.mandoubCustomer.query || "").trim()) {
                this.searchMandoubCustomer(this.mandoubCustomer.query);
            }
        },
        onMandoubCustomerKeydown(ev) {
            if (ev.key === "Enter") {
                ev.preventDefault();
                this.confirmMandoubCustomer();
            }
        },
        async searchMandoubCustomer(query) {
            const text = (query || "").trim();
            if (!text) {
                this.mandoubCustomer.matches = [];
                return;
            }
            let matches = localPartnerMatches(this.pos, text);
            if (matches.length < 3 && this.pos.data?.searchRead) {
                try {
                    const remote = await this.pos.data.searchRead("res.partner", [
                        "|",
                        "|",
                        ["name", "ilike", text],
                        ["phone", "ilike", text],
                        ["mobile", "ilike", text],
                    ]);
                    if (Array.isArray(remote) && remote.length) {
                        matches = remote;
                    }
                } catch (_error) {
                    // Keep local matches when the live search is unavailable.
                }
            }
            this.mandoubCustomer.matches = matches.slice(0, 12);
        },
        selectMandoubCustomer(partner) {
            assignOrderPartner(this.pos, partner);
            this.mandoubCustomer.query = partnerDisplay(partner);
            this.mandoubCustomer.matches = [];
            this.mandoubCustomer.error = "";
        },
        async confirmMandoubCustomer() {
            const text = (this.mandoubCustomer.query || "").trim();
            if (!text) {
                this.mandoubCustomer.error = _t("اكتب اسم العميل أولاً ثم ابدأ الطلب.");
                return;
            }
            const exact = (this.mandoubCustomer.matches || []).find(
                (partner) => partnerDisplay(partner).replace("ـ", "").trim() === text
            );
            if (exact) {
                this.selectMandoubCustomer(exact);
                return;
            }
            const localExact = localPartnerMatches(this.pos, text).find(
                (partner) => partnerDisplay(partner).replace("ـ", "").trim() === text
            );
            if (localExact) {
                this.selectMandoubCustomer(localExact);
                return;
            }
            try {
                let partner = null;
                if (this.pos.data?.create) {
                    const created = await this.pos.data.create("res.partner", [
                        { name: text, customer_rank: 1 },
                    ]);
                    partner = Array.isArray(created) ? created[0] : created;
                } else if (this.pos.data?.call) {
                    const partnerId = await this.pos.data.call("res.partner", "create", [
                        { name: text, customer_rank: 1 },
                    ]);
                    partner = this.pos.models["res.partner"].get(partnerId) || {
                        id: partnerId,
                        name: text,
                    };
                }
                if (partner) {
                    this.selectMandoubCustomer(partner);
                    return;
                }
            } catch (_error) {
                this.mandoubCustomer.error = _t("تعذر حفظ العميل. أعد المحاولة.");
                return;
            }
            this.mandoubCustomer.error = _t("تعذر حفظ العميل. أعد المحاولة.");
        },
    });

    function patchOptionalUi() {
        const actionPadMod = optionalRequire(
            "@point_of_sale/app/screens/product_screen/action_pad/action_pad"
        );
        const ActionpadWidget = actionPadMod?.ActionpadWidget || actionPadMod;
        if (ActionpadWidget?.prototype && !ActionpadWidget._mandoubPatched) {
            ActionpadWidget._mandoubPatched = true;
            patch(ActionpadWidget.prototype, {
                setup() {
                    super.setup(...arguments);
                    onMounted(() => watchMandoubUi(this.pos));
                    onPatched(() => relabelMandoubPayButtons(this.el || document));
                },
            });
        }

        const cardMod = optionalRequire(
            "@point_of_sale/app/generic_components/product_card/product_card"
        );
        const ProductCard = cardMod?.ProductCard || cardMod;
        if (ProductCard?.prototype && !ProductCard._mandoubPatched) {
            ProductCard._mandoubPatched = true;
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
                get mandoubIsOutOfStock() {
                    return Number(productValue(this.props.product, "mandoub_qty_on_hand")) <= 0;
                },
                get mandoubQtyOnHandLabel() {
                    return formatOnHandQty(productValue(this.props.product, "mandoub_qty_on_hand"));
                },
                injectMandoubQtyBadge() {
                    const root = this.el || this.__owl__?.bdom?.el;
                    if (!root) {
                        return;
                    }
                    const qty = productValue(this.props.product, "mandoub_qty_on_hand");
                    paintProductCard(root, qty);
                },
            });
        }

        const summaryMod = optionalRequire(
            "@point_of_sale/app/screens/product_screen/order_summary/order_summary"
        );
        const OrderSummary = summaryMod?.OrderSummary || summaryMod;
        if (OrderSummary?.prototype && !OrderSummary._mandoubPatched) {
            OrderSummary._mandoubPatched = true;
        }
    }

    patchOptionalUi();
    setTimeout(patchOptionalUi, 500);

    console.info("[mandoub] POS save-print, stock badges, and wholesale packs loaded");

    return {
        packUnitQty,
        wholesaleLineQty,
        loadMandoubWarehouseStock,
        applyMandoubStockToProduct,
        isMandoubQuotationPos,
        cartPayloadFromOrder,
    };
});
