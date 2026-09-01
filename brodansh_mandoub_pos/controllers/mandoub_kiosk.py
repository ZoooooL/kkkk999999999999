# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from werkzeug.exceptions import Unauthorized

from odoo.addons.brodansh_mandoub_pos.models.mandoub_setup import (
    is_mandoub_pos_name,
    normalize_arabic_name,
    partner_create_vals,
    partner_public_payload,
    partner_search_domain,
    pick_or_create_partner_action,
)


class MandoubKioskCustomer(http.Controller):
    def _mandoub_pos_config(self, access_token):
        token = (access_token or "").strip()
        if not token:
            raise Unauthorized()
        pos_config = (
            request.env["pos.config"]
            .sudo()
            .search([("access_token", "=", token)], limit=1)
        )
        if not pos_config or pos_config.self_ordering_mode == "nothing":
            raise Unauthorized()
        if not (
            pos_config.mandoub_quotation_mode or is_mandoub_pos_name(pos_config.name)
        ):
            raise Unauthorized()
        user = pos_config.self_ordering_default_user_id
        company = pos_config.company_id
        return pos_config.sudo(False).with_company(company).with_user(user).with_context(
            allowed_company_ids=company.ids
        )

    def _search_partners(self, pos_config, query):
        domain = partner_search_domain(query, pos_config.company_id.id)
        if not domain:
            return pos_config.env["res.partner"]
        return pos_config.env["res.partner"].search(domain, limit=20)

    def _payloads(self, partners):
        return [
            partner_public_payload(
                partner.id,
                partner.display_name,
                partner.phone or partner.mobile or "",
                partner.city or "",
            )
            for partner in partners
        ]

    @http.route(
        "/pos-self/mandoub/partners",
        type="json",
        auth="public",
        website=True,
        methods=["POST"],
    )
    def search_or_create_partner(self, access_token, query="", create=False):
        pos_config = self._mandoub_pos_config(access_token)
        typed = normalize_arabic_name(query)
        partners = self._search_partners(pos_config, typed)
        action = pick_or_create_partner_action(
            typed, partners.mapped("name") + partners.mapped("display_name")
        )
        created = None
        if create and action == "create":
            created = pos_config.env["res.partner"].create(
                partner_create_vals(typed, pos_config.company_id.id)
            )
            partners = created | partners
        elif create and action == "use_existing":
            exact = partners.filtered(
                lambda partner: normalize_arabic_name(partner.name) == typed
                or normalize_arabic_name(partner.display_name) == typed
            )[:1]
            created = exact[:1]
        selected = created[:1] if created else partners[:1]
        return {
            "action": action,
            "query": typed,
            "selected": self._payloads(selected)[0] if selected else False,
            "matches": self._payloads(partners),
        }
