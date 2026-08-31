# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .mandoub_setup import FACTORY_WAREHOUSE_CODE, default_pos_qty, DEFAULT_PACK_QTY


class ProductProduct(models.Model):
    _inherit = "product.product"

    mandoub_pack_qty = fields.Float(
        string="كمية التعبئة في نقطة البيع",
        compute="_compute_mandoub_pos_pack",
        help="ضغطة واحدة = تعبئة واحدة. 3 على لوحة الكمية × تعبئة 24 = 72.",
    )
    mandoub_qty_on_hand = fields.Float(
        string="الكمية في اليد",
        compute="_compute_mandoub_pos_pack",
    )
    mandoub_pack_qtys = fields.Char(
        string="تعبئات المبيعات",
        compute="_compute_mandoub_pos_pack",
        help="كميات التعبئة المتاحة مفصولة بفاصلة، مثل 12,24,36",
    )

    def _compute_mandoub_pos_pack(self):
        warehouse_aware = "warehouse_id" in self.env.context
        for product in self:
            packs = product.packaging_ids.filtered(lambda pack: pack.sales and pack.qty > 0)
            qtys = packs.mapped("qty")
            packagings = [{"qty": qty, "sales": True} for qty in qtys]
            qty_on_hand = product.qty_available
            product.mandoub_qty_on_hand = qty_on_hand
            product.mandoub_pack_qtys = ",".join(
                str(int(qty) if float(qty).is_integer() else qty) for qty in qtys
            )
            product.mandoub_pack_qty = default_pos_qty(
                packagings,
                qty_on_hand=qty_on_hand if warehouse_aware else None,
            )

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        for name in ("mandoub_pack_qty", "mandoub_qty_on_hand", "mandoub_pack_qtys"):
            if name not in fields_list:
                fields_list.append(name)
        return fields_list

    def _mandoub_pos_warehouse(self, config):
        warehouse = config.picking_type_id.warehouse_id
        if warehouse:
            return warehouse
        return self.env["stock.warehouse"].sudo().search(
            [
                ("company_id", "=", config.company_id.id),
                ("code", "=", FACTORY_WAREHOUSE_CODE),
            ],
            limit=1,
        )

    def _mandoub_sales_pack_qtys_by_product(self, product_ids):
        pack_qtys = {product_id: [] for product_id in product_ids}
        if not product_ids:
            return pack_qtys
        rows = self.env["product.packaging"].sudo().search_read(
            [
                ("product_id", "in", product_ids),
                ("sales", "=", True),
                ("qty", ">", 0),
            ],
            ["product_id", "qty"],
            load=False,
        )
        for row in rows:
            product_id = row.get("product_id")
            if isinstance(product_id, (list, tuple)):
                product_id = product_id[0]
            if product_id in pack_qtys:
                pack_qtys[product_id].append(row["qty"])
        return pack_qtys

    def _inject_mandoub_pos_stock(self, result, data):
        records = result.get("data") if isinstance(result, dict) else result
        if not records:
            return result
        config_rows = (data or {}).get("pos.config", {}).get("data") or []
        if not config_rows:
            return result
        config = self.env["pos.config"].browse(config_rows[0].get("id"))
        warehouse = self._mandoub_pos_warehouse(config)
        product_ids = [row["id"] for row in records if row.get("id")]
        products = self.sudo().browse(product_ids).with_company(config.company_id)
        if warehouse:
            products = products.with_context(warehouse_id=warehouse.id)
        qty_map = {row["id"]: row["qty_available"] for row in products.read(["qty_available"])}
        pack_qtys = self._mandoub_sales_pack_qtys_by_product(product_ids)
        for row in records:
            product_id = row.get("id")
            qtys = pack_qtys.get(product_id) or []
            on_hand = qty_map.get(product_id)
            row["mandoub_pack_qtys"] = ",".join(
                str(int(qty) if float(qty).is_integer() else qty) for qty in qtys
            )
            if on_hand is not None:
                row["mandoub_qty_on_hand"] = on_hand
            row["mandoub_pack_qty"] = default_pos_qty(
                [{"qty": qty, "sales": True} for qty in qtys],
                qty_on_hand=on_hand,
                fallback=DEFAULT_PACK_QTY,
            )
        if isinstance(result, dict):
            fields_list = list(result.get("fields") or [])
            for name in ("mandoub_qty_on_hand", "mandoub_pack_qtys", "mandoub_pack_qty"):
                if name not in fields_list:
                    fields_list.append(name)
            result["fields"] = fields_list
        return result

    def _load_pos_data(self, data):
        result = super()._load_pos_data(data)
        return self._inject_mandoub_pos_stock(result, data)
