/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { LandingPage } from "@pos_self_order/app/pages/landing_page/landing_page";
import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";
import { ProductListPage } from "@pos_self_order/app/pages/product_list_page/product_list_page";
import { SelfOrder } from "@pos_self_order/app/self_order_service";

const MANDOUB_POS_PREFIX = "مندوب —";

export function isMandoubKiosk(selfOrder) {
    const config = selfOrder?.config;
    if (!config) {
        return false;
    }
    if (config.mandoub_quotation_mode) {
        return true;
    }
    return Boolean(config.name) && String(config.name).startsWith(MANDOUB_POS_PREFIX);
}

function customerFromUrl() {
    try {
        return new URLSearchParams(window.location.search).get("customer") || "";
    } catch (_error) {
        return "";
    }
}

function partnerRecord(partner) {
    return {
        id: partner.id,
        name: partner.name,
        phone: partner.phone || false,
        mobile: partner.phone || false,
        street: false,
        city: partner.city || false,
    };
}

export function applyMandoubPartner(selfOrder, partner) {
    if (!selfOrder || !partner || !partner.id) {
        return false;
    }
    selfOrder.mandoubPartner = partner;
    try {
        selfOrder.models.loadConnectedData({
            "res.partner": [partnerRecord(partner)],
        });
        const rec = selfOrder.models["res.partner"].get(partner.id);
        if (rec && selfOrder.currentOrder) {
            selfOrder.currentOrder.partner_id = rec;
        }
    } catch (_error) {
        if (selfOrder.currentOrder?.update) {
            selfOrder.currentOrder.update({ partner_id: partner.id });
        }
    }
    return true;
}

export function currentMandoubPartner(selfOrder) {
    if (selfOrder?.mandoubPartner?.id) {
        return selfOrder.mandoubPartner;
    }
    const partner = selfOrder?.currentOrder?.partner_id;
    if (!partner) {
        return null;
    }
    if (typeof partner === "object") {
        return {
            id: partner.id,
            name: partner.name || partner.display_name,
            phone: partner.phone || partner.mobile || "",
            city: partner.city || "",
        };
    }
    return { id: partner, name: "", phone: "", city: "" };
}

async function searchMandoubPartners(selfOrder, query, create) {
    return rpc("/pos-self/mandoub/partners", {
        access_token: selfOrder.access_token,
        query: query || "",
        create: Boolean(create),
    });
}

function customerState(query = "") {
    return {
        query,
        matches: [],
        selected: null,
        error: "",
        searching: false,
    };
}

patch(SelfOrder.prototype, {
    async confirmOrder() {
        if (isMandoubKiosk(this) && !currentMandoubPartner(this)?.id) {
            this.notification.add(_t("اكتب اسم العميل أولاً ثم ابدأ الطلب."), { type: "danger" });
            this.router.navigate("default");
            return;
        }
        return super.confirmOrder(...arguments);
    },
});

patch(LandingPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.mandoubCustomer = useState(customerState(customerFromUrl()));
        const existing = currentMandoubPartner(this.selfOrder);
        if (existing?.name && !this.mandoubCustomer.query) {
            this.mandoubCustomer.query = existing.name;
            this.mandoubCustomer.selected = existing;
        }
    },
    get showMandoubCustomer() {
        return isMandoubKiosk(this.selfOrder);
    },
    onMandoubCustomerInput(ev) {
        this.mandoubCustomer.query = ev.target.value;
        this.mandoubCustomer.selected = null;
        this.mandoubCustomer.error = "";
        this._scheduleMandoubSearch();
    },
    _scheduleMandoubSearch() {
        clearTimeout(this._mandoubSearchTimer);
        const query = (this.mandoubCustomer.query || "").trim();
        if (query.length < 1) {
            this.mandoubCustomer.matches = [];
            return;
        }
        this._mandoubSearchTimer = setTimeout(() => this.searchMandoubCustomer(), 250);
    },
    async searchMandoubCustomer() {
        const query = (this.mandoubCustomer.query || "").trim();
        if (!query) {
            this.mandoubCustomer.matches = [];
            return;
        }
        this.mandoubCustomer.searching = true;
        try {
            const result = await searchMandoubPartners(this.selfOrder, query, false);
            this.mandoubCustomer.matches = result.matches || [];
        } catch (_error) {
            this.mandoubCustomer.matches = [];
        } finally {
            this.mandoubCustomer.searching = false;
        }
    },
    selectMandoubCustomer(partner) {
        this.mandoubCustomer.selected = partner;
        this.mandoubCustomer.query = partner.name;
        this.mandoubCustomer.matches = [];
        this.mandoubCustomer.error = "";
        applyMandoubPartner(this.selfOrder, partner);
    },
    async start() {
        if (!this.showMandoubCustomer) {
            return super.start(...arguments);
        }
        const query = (this.mandoubCustomer.query || "").trim();
        if (!query && !this.mandoubCustomer.selected) {
            this.mandoubCustomer.error = _t("اكتب اسم العميل أولاً ثم ابدأ الطلب.");
            return;
        }
        try {
            const result = await searchMandoubPartners(
                this.selfOrder,
                this.mandoubCustomer.selected?.name || query,
                true
            );
            const partner = result.selected || this.mandoubCustomer.selected;
            if (!partner?.id) {
                this.mandoubCustomer.error = _t("اكتب اسم العميل أولاً ثم ابدأ الطلب.");
                return;
            }
            applyMandoubPartner(this.selfOrder, partner);
            this.mandoubCustomer.selected = partner;
            this.mandoubCustomer.error = "";
        } catch (_error) {
            this.mandoubCustomer.error = _t("تعذر حفظ العميل. أعد المحاولة.");
            return;
        }
        return super.start(...arguments);
    },
});

patch(ProductListPage.prototype, {
    get mandoubCustomerLabel() {
        return currentMandoubPartner(this.selfOrder)?.name || "";
    },
    get showMandoubCustomerBanner() {
        return isMandoubKiosk(this.selfOrder);
    },
    editMandoubCustomer() {
        this.router.navigate("default");
    },
});

patch(CartPage.prototype, {
    get mandoubCustomerLabel() {
        return currentMandoubPartner(this.selfOrder)?.name || "";
    },
    get showMandoubCustomerBanner() {
        return isMandoubKiosk(this.selfOrder);
    },
    async pay() {
        if (this.showMandoubCustomerBanner && !currentMandoubPartner(this.selfOrder)?.id) {
            this.router.navigate("default");
            return;
        }
        return super.pay(...arguments);
    },
});
