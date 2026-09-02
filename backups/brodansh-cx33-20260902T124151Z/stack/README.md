# Brodansh Odoo 18 — Ubuntu + Docker → Hetzner CX33

الهدف: أن يعمل **https://brodansh.de.com.eg** كما اللايف الآن 100% على **Hetzner CX33 / Ubuntu 24.04** (Falkenstein `fsn1`، وإلا Nuremberg `nbg1`).

اللايف الحالي: **Odoo 18.0 Enterprise** (`18.0+e`) خلف Nginx على **AWS London** (`18.133.13.149`).

مساران مدعومان (نفس النتيجة):

1. **Docker على جهازك ثم النقل إلى CX33** (المفضّل)
2. **إنشاء CX33 من [console.hetzner.cloud](https://console.hetzner.cloud) ثم سحب اللايف إليه**

كلاهما يحتاج: ملفات **Odoo Enterprise** + نسخة PostgreSQL + الـ filestore من السيرفر الحالي. هذه ليست في Git (ترخيص + بيانات).

## المسار 1 — Docker محلي ثم النقل

```bash
cp .env.example .env          # LIVE_SSH_HOST=18.133.13.149 و HETZNER_SSH=root@CX33_IP
./scripts/up.sh               # يقلع Odoo 18 + Postgres 16
# انسخ Enterprise من اللايف (مطلوب لـ 18.0+e):
rsync -az ubuntu@18.133.13.149:/opt/odoo/enterprise/ ./enterprise/
./scripts/migrate-from-live.sh
./scripts/check-live-parity.sh
./scripts/pack-for-hetzner.sh --require-enterprise
./scripts/deploy-to-hetzner.sh root@CX33_IP
```

على CX33 بعد التأكد من الدخول وPOS والتقارير:

```bash
# غيّر A record لـ brodansh.de.com.eg إلى IP هيتزنر
./scripts/ssl-init.sh
```

## المسار 2 — Hetzner أولاً

من الكونسول: Location **Falkenstein (fsn1)** أو **nbg1** · Image **Ubuntu 24.04** · Type **CX33** · IPv4+IPv6 · Backups · الاسم `brodansh-odoo`.

أو:

```bash
export HCLOUD_TOKEN=...
export HCLOUD_SSH_KEY=your-key
./scripts/hetzner-create-cx33.sh
```

ثم على السيرفر:

```bash
git clone <repo> /opt/odoo && cd /opt/odoo
./scripts/install-ubuntu-docker.sh
cp .env.example .env && vim .env
./scripts/up.sh
./scripts/migrate-from-live.sh
./scripts/check-live-parity.sh
./scripts/ssl-init.sh
```

لا تُحوّل DNS قبل نجاح `check-live-parity.sh` وتجربة المناديب والفواتير PDF.

## الوحدات المخصّصة المضمّنة

مجلد `addons/` يُحمَّل تلقائياً:

- `brodansh_mandoub_pos` — جلسات المناديب وشاشة المطبخ
- `brodan_partner_ledger_opening` — دفتر الأستاذ والرصيد الافتتاحي
- `brodansh_documents` — تنظيم المستندات

## تشغيل سريع للتجربة (Community)

بدون Enterprise يعمل أودو 18 Community فقط — ليس نسخة اللايف.

```bash
sudo ./scripts/install-ubuntu-docker.sh
cp .env.example .env
./scripts/up.sh
```

## Layout

| Path | Role |
| --- | --- |
| `compose.yaml` | Odoo + Postgres; Nginx with `--profile prod` |
| `addons/` | وحدات برودانش |
| `enterprise/` | Odoo Enterprise (gitignored) |
| `scripts/pack-for-hetzner.sh` | حزمة Docker محلية للنقل |
| `scripts/deploy-to-hetzner.sh` | رفع الحزمة إلى CX33 |
| `scripts/import-hetzner-pack.sh` | فك الحزمة على السيرفر |
| `scripts/migrate-from-live.sh` | سحب القاعدة من AWS |
| `scripts/check-live-parity.sh` | مقارنة الإصدار مع اللايف |
| `scripts/hetzner-create-cx33.sh` | طلب CX33 في FSN1/NBG1 |
