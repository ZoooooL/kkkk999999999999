# Brodansh — Live 1 as-is, Live 2 = matching clone

**Live 1 لا يُمَس:** https://brodansh.de.com.eg على AWS (`18.133.13.149`، Odoo 18.0+e). لا DNS، لا SSL، لا إعادة تشغيل، لا كتابة، ولا SSH من هذا المستودع إلا إذا فعّلت ذلك بنفسك.

**Live 2** ستاك Docker منفصل (محلي أو Hetzner CX33 Ubuntu 24.04). السكربتات ترفض `brodansh.de.com.eg` و`18.133.13.149` و`3.8.46.165`.

## ماذا يطابق Live 1؟

| | Live 1 (مجمّد) | Live 2 المستهدف |
| --- | --- | --- |
| الإصدار | 18.0+e | 18.0+e بعد وضع `enterprise/` |
| القواعد | `brodan`, `brodan2026`, `brodansh`, `test` | نفس الأسماء بعد الاستيراد |
| اختيار القاعدة | `list_db=True` علني | نفس الإعداد |
| النطاق | `brodansh.de.com.eg` | IP السيرفر الجديد أو نطاق **جديد** |

`live2.brodansh.de.com.eg` يشير حالياً إلى سيرفر AWS آخر (`3.8.46.165`، قاعدة `clo`). لن نغيّر هذا السجل.

## Live 2 جاهزة — النسخة 100% تحتاج ملف التصدير فقط

الستاك هنا يقلع ويُظهر نفس سلوك Live 1 (محدد القواعد). البيانات الحقيقية + Enterprise لا تُنسخ من الإنترنت.

**على Live 1 (قراءة فقط، لا إعادة تشغيل):**

```bash
sudo ./scripts/export-live1-readonly.sh
# ينتج: /tmp/brodansh-live1-readonly-XXXX.tar.gz
```

**على Live 2 (هذا المشروع — بدون SSH إلى AWS):**

```bash
cp /path/to/brodansh-live1-readonly-XXXX.tar.gz backups/
./scripts/prepare-live2-identical.sh
./scripts/check-live-parity.sh
```

`check-live-parity.sh` يجب أن يطبع `OK` عندما يتطابق الإصدار `18.0+e` وأسماء القواعد الأربع.

## تشغيل Live 2 بدون البيانات بعد

```bash
cp .env.example .env
./scripts/prepare-live2-identical.sh
```

وحدات برودانش في `addons/`: مناديب، دفتر الأستاذ، المستندات.

## Hetzner CX33 (اختياري)

[console.hetzner.cloud](https://console.hetzner.cloud) → FSN1 أو NBG1 → Ubuntu 24.04 → **CX33** → الاسم **`brodansh-live2`**.

أضف سجل DNS **جديد** إلى IP هيتزنر. لا تغيّر `brodansh.de.com.eg`.

## حماية Live 1

| ممنوع | مسموح |
| --- | --- |
| تغيير DNS لـ brodansh.de.com.eg | سجل جديد لسيرفر Live 2 |
| certbot على النطاق الأصلي | شهادة لنطاق Live 2 فقط بعد أن يشير DNS إليه |
| restart/upgrade على AWS | pg_dump / tar قراءة فقط على AWS ثم استيراد هنا |
| rsync/scp إلى Live 1 | نسخ ملف التصدير إلى مجلد `backups/` |
