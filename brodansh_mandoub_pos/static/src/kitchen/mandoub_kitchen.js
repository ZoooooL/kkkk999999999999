odoo.define("brodansh_mandoub_pos.mandoub_kitchen", [
    "@web/core/utils/patch",
    "@web/core/utils/hooks",
], function (require) {
    "use strict";

    const { patch } = require("@web/core/utils/patch");
    const { useService } = require("@web/core/utils/hooks");

    function optionalRequire(name) {
        try {
            return require(name);
        } catch (_error) {
            return null;
        }
    }

    function parseKitchenCardNote(note) {
        const text = String(note || "")
            .replace(/\n/g, " ")
            .trim();
        let parts = text.split("|").map((part) => part.trim()).filter(Boolean);
        if (parts.length && parts[0].startsWith("[")) {
            parts = parts.slice(1);
        }
        return {
            soName: parts[0] || "",
            partnerName: parts[1] || "",
            salespersonName: parts[2] || "",
        };
    }

    function saleOrderFormUrl(orderId) {
        const allowed = (odoo.__session_info__ && odoo.__session_info__.user_companies) || {};
        const ids = allowed.allowed || [];
        const cids = ids.length ? `&cids=${ids.join("-")}` : "";
        return `/web#model=sale.order&id=${orderId}&view_type=form${cids}`;
    }

    const OrderModelMod = optionalRequire("@pos_preparation_display/app/models/order");
    const OrderModel = OrderModelMod && (OrderModelMod.Order || OrderModelMod);
    if (OrderModel && OrderModel.prototype) {
        patch(OrderModel.prototype, {
            setup(order) {
                super.setup(...arguments);
                const parsed = parseKitchenCardNote(this.generalNote);
                this.mandoubSaleName = parsed.soName;
                this.mandoubPartnerName = parsed.partnerName;
                if (parsed.partnerName) {
                    this.responsible = parsed.partnerName;
                }
                if (parsed.soName) {
                    this.tracking_number = parsed.soName;
                }
            },
        });
    }

    const OrderCompMod = optionalRequire("@pos_preparation_display/app/components/order/order");
    const OrderComponent = OrderCompMod && (OrderCompMod.Order || OrderCompMod);
    if (OrderComponent && OrderComponent.prototype) {
        patch(OrderComponent.prototype, {
            setup() {
                super.setup(...arguments);
                this.orm = useService("orm");
            },
            getSortedOrderlines() {
                return [];
            },
            async clickOrder() {
                await this.openMandoubSaleOrder();
            },
            async openMandoubSaleOrder() {
                if (this.actionInProgress) {
                    return;
                }
                const order = this.props.order;
                const parsed = parseKitchenCardNote(order.generalNote);
                const soName = order.mandoubSaleName || parsed.soName;
                if (!soName) {
                    return;
                }
                try {
                    this.actionInProgress = true;
                    const ids = await this.orm.search("sale.order", [["name", "=", soName]], {
                        limit: 1,
                    });
                    const orderId = Array.isArray(ids) ? ids[0] : ids;
                    if (orderId) {
                        window.open(saleOrderFormUrl(orderId), "_blank", "noopener");
                    }
                } catch (error) {
                    console.warn("Mandoub kitchen could not open the sale order", error);
                } finally {
                    this.actionInProgress = false;
                }
            },
        });
    }
});
