# Brodansh Odoo 18 — Ubuntu + Docker

Production Docker stack for the live Brodansh ERP (`https://brodansh.de.com.eg`).

The live server currently reports **Odoo 18.0 Enterprise** (`18.0+e`) behind **Nginx on Ubuntu**. This repository installs the same major version on Ubuntu 24.04 with Docker Compose, then gives you a path to move PostgreSQL + the filestore + Enterprise addons onto a cheaper VPS.

## What you get

- Ubuntu 24.04 installer for Docker Engine + Compose
- Odoo 18 image with Arabic fonts (`Amiri`, `Kacst`, `Noto`) and `ar_EG` locale
- PostgreSQL 16 with `unaccent` and `pg_trgm`
- Named volumes for the database and filestore
- Nginx + Let's Encrypt profile for HTTPS
- Backup, restore, and live-migration scripts
- Server price comparison (September 2026) in `SERVERS.md`

Community starts 100% from `./scripts/up.sh`. Restoring the **live** database also needs Odoo Enterprise addons copied into `enterprise/` (that code is licensed, so it is not in git).

## Quick start on a new Ubuntu VPS

```bash
sudo apt-get update && sudo apt-get install -y git
git clone <this-repo> odoo && cd odoo
chmod +x scripts/*.sh
sudo ./scripts/install-ubuntu-docker.sh
# log out/in so docker group applies
cp .env.example .env
nano .env          # set POSTGRES_PASSWORD and ODOO_ADMIN_PASSWORD
./scripts/up.sh
```

Open `http://SERVER_IP:8069` → database manager → create `brodansh`.

Production with TLS after DNS points at the new IP:

```bash
./scripts/ssl-init.sh
docker compose --env-file .env --profile prod up -d
```

Then copy `config/odoo.prod.conf.runtime` over the runtime file (or set `workers` / `list_db = False`) and `docker compose up -d odoo`.

## Move the live database

1. Buy the VPS recommended in `SERVERS.md` (Hetzner CX33 is the default).
2. Point a test hostname, or use the server IP, and bring this stack up.
3. Put SSH details in `.env` (`LIVE_SSH_HOST`, paths).
4. Copy Enterprise addons (required for `18.0+e`):

   ```bash
   rsync -az root@LIVE:/path/to/enterprise/ ./enterprise/
   ```

5. Run:

   ```bash
   ./scripts/migrate-from-live.sh
   ./scripts/smoke-test.sh
   ```

6. Switch DNS for `brodansh.de.com.eg` only after login, POS, and PDF reports work.

Daily backup on the new server:

```bash
crontab -e
# 0 2 * * * /opt/odoo/scripts/backup.sh
```

## Layout

| Path | Role |
| --- | --- |
| `compose.yaml` | Odoo + Postgres; Nginx with `--profile prod` |
| `Dockerfile` | Official `odoo:18.0` + Arabic fonts |
| `config/odoo.conf` | First-boot config (`list_db = True`, `workers = 0`) |
| `config/odoo.prod.conf` | Production workers + `dbfilter` |
| `addons/` | Custom modules (mandoub POS, etc.) |
| `enterprise/` | Odoo Enterprise addons (gitignored) |
| `scripts/install-ubuntu-docker.sh` | Docker CE on Ubuntu |
| `scripts/up.sh` | Render secrets and start the stack |
| `scripts/backup.sh` / `restore.sh` | Dump/restore DB + filestore |
| `scripts/migrate-from-live.sh` | Pull from the current Ubuntu host |

## Requirements

| Item | Minimum | Comfortable for Brodansh POS |
| --- | --- | --- |
| vCPU | 2 | 4 |
| RAM | 4 GB | 8 GB (16 GB if many kitchen screens) |
| Disk | 40 GB NVMe | 80–160 GB + off-site backups |
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |

`scripts/install-ubuntu-docker.sh` also sets `net.bridge.bridge-nf-call-iptables=0` so Odoo can reach PostgreSQL on the Docker bridge (required on some nested/cloud VMs).
