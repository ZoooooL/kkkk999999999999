# -*- coding: utf-8 -*-
from odoo import fields, models

from ..models.mandoub_setup import (
    SHARED_KITCHEN_NAME,
    is_mandoub_pos_name,
    kitchen_display_name_for_pos,
    stage_spec_list,
)


class BrodanshMandoubSetupWizard(models.TransientModel):
    _name = "brodansh.mandoub.setup.wizard"
    _description = "تهيئة نقاط البيع وشاشات المطبخ للمناديب"

    company_id = fields.Many2one(
        "res.company",
        string="الشركة",
        required=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text(string="النتيجة", readonly=True)

    def action_apply(self):
        self.ensure_one()
        log = self._apply_setup()
        self.note = "\n".join(log)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _mandoub_configs(self):
        configs = self.env["pos.config"].search(
            [("company_id", "=", self.company_id.id), ("active", "=", True)]
        )
        return configs.filtered(lambda c: is_mandoub_pos_name(c.name))

    def _open_sessions(self, configs, log):
        Session = self.env["pos.session"]
        now = fields.Datetime.now()
        for config in configs:
            session = config.current_session_id
            if not session:
                session = Session.create(
                    {
                        "config_id": config.id,
                        "user_id": config.current_user_id.id or self.env.uid,
                    }
                )
                log.append("أنشئت جلسة لـ %s" % config.name)
            vals = {}
            if session.state in ("new", "opening_control"):
                vals["state"] = "opened"
            if not session.start_at:
                vals["start_at"] = now
            if vals:
                session.write(vals)
                log.append("فُتحت جلسة %s" % session.display_name)

    def _sync_stages(self, display, log):
        Stage = self.env["pos_preparation_display.stage"]
        specs = stage_spec_list()
        existing = display.stage_ids.sorted(lambda s: (s.sequence or 0, s.id))
        for record, spec in zip(existing, specs):
            record.write(spec)
        missing = specs[len(existing) :]
        if missing:
            for spec in missing:
                Stage.create(dict(spec, preparation_display_id=display.id))
                log.append("أُضيفت مرحلة %s على %s" % (spec["name"], display.name))

    def _ensure_display(self, name, pos_configs, log):
        Display = self.env["pos_preparation_display.display"]
        display = Display.search(
            [("name", "=", name), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        if not display:
            # Create stages first, then link POS. Odoo blocks stage
            # edits on a display already tied to an open POS session.
            display = Display.create(
                {
                    "name": name,
                    "company_id": self.company_id.id,
                    "stage_ids": [(0, 0, spec) for spec in stage_spec_list()],
                }
            )
            log.append("أُنشئت شاشة %s" % name)
        else:
            self._sync_stages(display, log)
        display.write({"pos_config_ids": [(6, 0, pos_configs.ids)]})
        return display

    def _apply_setup(self):
        log = []
        configs = self._mandoub_configs()
        if not configs:
            return ["لا توجد نقاط بيع يبدأ اسمها بـ «مندوب —» في هذه الشركة."]
        log.append("عُثر على %s نقطة بيع للمناديب." % len(configs))
        self._open_sessions(configs, log)
        self._ensure_display(SHARED_KITCHEN_NAME, configs, log)
        for config in configs:
            self._ensure_display(kitchen_display_name_for_pos(config.name), config, log)
        log.append("المراحل: مؤكد → تم الشحن → الفوترة")
        return log
