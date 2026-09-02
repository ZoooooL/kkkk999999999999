# Brodansh Odoo 18 — Docker

https://brodansh.de.com.eg/odoo is the Odoo 18 web client (not a URL prefix).
Live today: nginx TLS → `127.0.0.1:8069`, `/longpolling` → `8072`, process

`python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf`

(18.0 Enterprise, db `brodansh` ~51 GB). The same host also runs
`brodan-att.de.com.eg` on 8079 and shares PostgreSQL 16. Disk is ~5.5 GB free,
so this stack **reuses** the existing database directory and filestore. It does
not dump or copy the 51 GB database.

## Production on the live server (root)

1. Install Docker Engine + the Compose plugin.
2. Copy `docker/odoo/.env.example` to `docker/odoo/.env` and set `ODOO_UID` /
   `ODOO_GID` from `id odoo`.
3. Confirm filestore: `ODOO_DATA_DIR` (default `/home/odoo/.local/share/Odoo`).
4. Stop **only** the brodansh process (`odoo-server.conf`), never
   `odoo-server-att.conf`.
5. Start:

```bash
cd docker/odoo
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

Nginx and Let's Encrypt stay on the host so `brodan-att` and
`brodan.de.com.eg` keep working. Postgres stays on the host (local socket).
The container runs the **same** `/odoo/odoo-server/odoo-bin` with host
networking on 8069/8072.

Or: `sudo ./cutover.sh` (stops brodansh Odoo, starts the container, leaves
att/postgres/nginx running).

## Demo (this repository, empty database)

```bash
cd docker/odoo
docker compose --env-file .env.example up -d --build
docker compose run --rm odoo odoo -d brodansh -i base --stop-after-init --without-demo=all
docker compose up -d odoo nginx
```

Open http://127.0.0.1:18080/odoo — Community image only. Enterprise modules
(`web_enterprise`, POS, Studio, …) come from the live `/odoo/odoo-server`
bind-mount in production. Do not point the Community image at the live
`brodansh` database.
