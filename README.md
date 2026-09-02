# Brodansh — Live 1 as-is, Live 2 = 100% clone

**Live 1 لا يُمَس:** https://brodansh.de.com.eg على AWS (`18.133.13.149`، Odoo 18.0+e). لا DNS، لا SSL، لا إعادة تشغيل، لا كتابة على القاعدة.

**Live 2** نسخة مطابقة جاهزة على Docker / Hetzner CX33 Ubuntu 24.04، على نطاق منفصل: `live2.brodansh.de.com.eg` أو IP السيرفر الجديد.

السكربتات ترفض أي هدف = `brodansh.de.com.eg` أو `18.133.13.149`.

## كيف تصبح Live 2 = Live 1 بنسبة 100%

النسخة الكاملة تحتاج نسخة **قراءة فقط** من Live 1: PostgreSQL + filestore + مجلد Enterprise. لا تغيّر Live 1؛ فقط `pg_dump` و`tar`.

**على Live 1 (قراءة فقط):**

```bash
# انسخ السكربت إلى AWS ثم:
sudo ./scripts/export-live1-readonly.sh
# ينتج: /tmp/brodansh-live1-readonly-XXXX.tar.gz
```

**على Live 2 (هذا Docker أو CX33):**

```bash
scp ubuntu@18.133.13.149:/tmp/brodansh-live1-readonly-*.tar.gz ./backups/
./scripts/import-live1-dump-to-live2.sh backups/brodansh-live1-readonly-XXXX.tar.gz
./scripts/check-live-parity.sh
```

أو بسحب SSH للقراءة فقط (لا يعيد تشغيل أودو على AWS):

```bash
./scripts/migrate-from-live.sh
```

ثم إن أردت Hetzner:

```bash
./scripts/pack-for-hetzner.sh --require-enterprise
./scripts/deploy-to-hetzner.sh root@CX33_IP
```

أضف سجل DNS **جديد** `live2.brodansh.de.com.eg` → IP هيتزنر. لا تغيّر سجل `brodansh.de.com.eg`.

## إنشاء سيرفر Live 2 (Hetzner CX33)

[console.hetzner.cloud](https://console.hetzner.cloud) → FSN1 أو NBG1 → Ubuntu 24.04 → **CX33** → الاسم **`brodansh-live2`**.

```bash
export HCLOUD_TOKEN=...
./scripts/hetzner-create-cx33.sh
```

## تشغيل Live 2 محلياً (بدون نسخ القاعدة بعد)

```bash
cp .env.example .env   # ODOO_DOMAIN=live2.brodansh.de.com.eg
./scripts/up.sh
```

وحدات برودانش في `addons/`: مناديب، دفتر الأستاذ، المستندات. Enterprise مرخّص ويُنسخ من Live 1 قراءة فقط.

## حماية Live 1

| ممنوع | مسموح |
| --- | --- |
| تغيير DNS لـ brodansh.de.com.eg | سجل جديد live2.brodansh.de.com.eg |
| certbot على النطاق الأصلي | شهادة Live 2 فقط |
| restart/upgrade على AWS | pg_dump / tar قراءة فقط |
| rsync إلى Live 1 | rsync من Live 1 إلى Live 2 |
