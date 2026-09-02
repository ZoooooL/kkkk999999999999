/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { InstallScopedApp } from "@web/core/install_scoped_app/install_scoped_app";

const MANDOUB_POS_PREFIX = "مندوب —";

function appendCustomer(startUrl, customerName) {
    const url = startUrl || "";
    const name = (customerName || "").trim();
    if (!url || !name) {
        return url;
    }
    const glue = url.includes("?") ? "&" : "?";
    return `${url}${glue}customer=${encodeURIComponent(name)}`;
}

patch(InstallScopedApp.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.customerName = "";
    },
    get isMandoubCustomerApp() {
        const name = this.state.manifest?.name || "";
        const start = this.state.manifest?.start_url || "";
        return name.startsWith(MANDOUB_POS_PREFIX) || start.includes("pos-self");
    },
    get mandoubStartUrl() {
        return this.state.manifest?.start_url || "/";
    },
    get mandoubCustomerStartUrl() {
        return appendCustomer(this.mandoubStartUrl, this.state.customerName);
    },
    onMandoubCustomerInput(ev) {
        this.state.customerName = ev.target.value;
    },
    onOpenMandoubApp(ev) {
        const target = this.mandoubCustomerStartUrl || this.mandoubStartUrl;
        if (!target) {
            ev.preventDefault();
            return;
        }
        window.location.assign(target);
        ev.preventDefault();
    },
});
