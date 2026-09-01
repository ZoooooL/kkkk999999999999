# -*- coding: utf-8 -*-
{
    "name": "BRODAN Backup",
    "summary": "نسخ احتياطي لقاعدة البيانات مع فحص المساحة وجدولة يومية",
    "version": "18.0.1.0.0",
    "author": "BRODAN",
    "license": "LGPL-3",
    "category": "Administration",
    "depends": ["base", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "views/backup_views.xml",
        "data/backup_cron.xml",
    ],
    "installable": True,
    "application": True,
}
