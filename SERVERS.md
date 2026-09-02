# سيرفرات أودو — أسعار حية سبتمبر 2026

المطلوب: Ubuntu 24.04 + Docker + Odoo 18 Enterprise + PostgreSQL 16 + Nginx، مع مستخدمي نقطة البيع والمناديب في مصر (`brodansh.de.com.eg`).

الحد الأدنى الحقيقي للإنتاج: **4 vCPU / 8 GB RAM / NVMe**. 4 GB تكفي للتجربة فقط.

أسعار اليوم (بدون ضريبة إلا إن ذُكر غير ذلك). تحقق من صفحة المزود قبل الدفع؛ Hetzner رفع الأسعار في 15 يونيو 2026.

## التوصية

| الترتيب | المزود | الخطة | المواصفات | السعر / شهر | لماذا |
| --- | --- | --- | --- | --- | --- |
| 1 — الأفضل قيمة | [Hetzner Cloud](https://www.hetzner.com/cloud/) | **CX33** (Falkenstein أو Nuremberg) | 4 vCPU · 8 GB · 80 GB NVMe · 20 TB | **€8.49 + €0.50 IPv4 ≈ €8.99** | أسرع أقراص، شبكة ثابتة، GDPR، Docker في دقيقة، أنسب لأودو |
| 1ب — أريح للإنتاج | Hetzner Cloud | **CX43** | 8 vCPU · 16 GB · 160 GB NVMe | **€15.99 + €0.50 ≈ €16.49** | نفس المزود مع رأس مال لذاكرة PostgreSQL وشاشات المطبخ |
| 2 — الأرخص بمواصفات كافية | [Contabo Cloud VPS](https://www.contabo.com/en/vps/cloud-vps/) | **Cloud VPS 10** | 3–4 vCPU · 8 GB · 75 GB NVMe | **≈ €4.50–€5.36** (شهري؛ أرخص سنوي) | أكبر RAM لكل يورو. الأداء أقل ثباتاً من Hetzner وقد يتأخر التجهيز |
| 3 — لوحة سهلة | [Hostinger KVM 2](https://www.hostinger.com/vps-hosting) | KVM 2 | 2 vCPU · 8 GB · 100 GB NVMe | **$8.99** عرض سنتين، يتجدد **$14.99** | مناسب إن أردت لوحة عربية/سهلة. CPU أضعف من CX33 |
| لا يُنصح به للميزانية | DigitalOcean Droplet 4 GB | Basic | 2 vCPU · 4 GB · 80 GB | **$24** | أضعف وأغلى من Hetzner بنحو 3× |
| مجاني لكن غير موثوق للحسابات | Oracle Cloud Always Free | VM.Standard.A1.Flex | 4 ARM · 24 GB | **$0** | ARM يعمل مع `odoo:18.0` (arm64)، لكن فتح الحساب والحدود صعبة |

**الخيار الافتراضي لبرودانش: Hetzner CX33، نظام Ubuntu 24.04، موقع FSN1 أو NBG1.** أضف Volume إن امتلأ الـ filestore (€0.0572/GB ≈ €5.7 لكل 100 GB). فعّل Backups (+20٪ ≈ €1.80) من اليوم الأول.

## لماذا ليس الأرخص دائماً؟

Contabo يعطي 8 GB بأقل من €6، لكن تقارير 2026 تشير إلى تباين في المعالج والشبكة وبطء في الدعم. أودو + PostgreSQL + POS حساس للـ IOPS. Hetzner NVMe أوضح في الإنتاج.

Hostinger أرخص في العرض الأول، لكن التجديد يقفز، و2 vCPU ضيقة مع `workers = 5`.

سيرفر داخل مصر (LightNode Cairo أو Hodi) يخفض زمن الاستجابة من ~80–100 ms (ألمانيا) إلى أقل من 20 ms، لكنه أغلى بكثير (Hodi Odoo من 5,490 EGP/شهر). لفريق مناديب على 4G الفرق مقبول على Hetzner ألمانيا؛ اختر القاهرة فقط إذا كان الـ POS يعلق على الشبكة.

## تكلفة شهرية متوقعة بعد النقل

| بند | Hetzner CX33 | Hetzner CX43 | Contabo VPS 10 |
| --- | --- | --- | --- |
| السيرفر | €8.99 | €16.49 | ~€5.36 |
| نسخ احتياطي داخلي | €1.80 | €3.30 | اختياري |
| قرص إضافي 100 GB | €5.72 | غير لازم أولاً | غير لازم أولاً |
| **المجموع** | **≈ €10–16** | **≈ €20** | **≈ €5–8** |

خارج ذلك: نطاق `brodansh.de.com.eg` يبقى كما هو. بعد النقل غيّر A record إلى IP الجديد ثم `./scripts/ssl-init.sh`.

## خطوات الطلب (Hetzner)

1. حساب على [console.hetzner.cloud](https://console.hetzner.cloud) (بطاقة أو PayPal).
2. New project → Add server.
3. Location: **Falkenstein (FSN1)** أو **Nuremberg (NBG1)**.
4. Image: **Ubuntu 24.04**.
5. Type: **CX33** (Cost-Optimized / shared).
6. Networking: IPv4 + IPv6.
7. SSH key، ثم Create.
8. على السيرفر:

```bash
apt-get update && apt-get install -y git
git clone <repo> /opt/odoo && cd /opt/odoo
./scripts/install-ubuntu-docker.sh
cp .env.example .env && vim .env
./scripts/up.sh
```

9. انقل القاعدة: `./scripts/migrate-from-live.sh` بعد ملء `LIVE_SSH_HOST`.

## مصادر الأسعار

- Hetzner Cloud + [ hump June 2026 price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
- [Hetzner CX/CAX caps (Aug 2026)](https://costgoat.com/pricing/hetzner): CX33 €8.49، CX43 €15.99 (بدون IPv4)
- Hostinger VPS page 2026-09-02: KVM 2 $8.99 intro / $14.99 renewal
- Contabo Cloud VPS 10 listings 2026: ~€4.50–€5.36
- Live Brodansh: `server_version = 18.0+e` behind `nginx/1.18.0 (Ubuntu)`
