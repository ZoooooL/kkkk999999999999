# Brodansh backup in Docker

Runs the same two-pass `pg_dump -Fc` → `rclone rcat --size` flow that the live
Odoo server action uses. The dump never lands on disk. This does **not** move
the ERP into Docker.

The live Odoo host currently has no Docker daemon. Install Docker with root
once, or run this compose on another Linux machine that can reach Postgres.

## OneDrive (recommended)

1. Copy `.env.example` to `.env` and fill `PGUSER`, `PGPASSWORD`, `ONEDRIVE_TOKEN_JSON`.
2. Keep `DEST=onedrive`.
3. If Docker is on the Odoo server:

```bash
cd docker/backup
docker compose -f docker-compose.host.yml --env-file .env up --build
```

4. If Docker is on another machine, set `PGHOST` to the Postgres host and:

```bash
cd docker/backup
docker compose --env-file .env up --build
```

## Windows folder (`D:\Zool Sulotion`)

Needs Tailscale on the laptop (awake, not Sleep) and an reusable auth key from
https://login.tailscale.com/admin/settings/keys

Set `DEST=sftp`, `TS_AUTHKEY`, `SFTP_PASSWORD` in `.env`, then the same compose
command. The container starts Tailscale in userspace and uploads through
SOCKS `127.0.0.1:1055`. Direct TCP to `100.78.222.34:22` is not used.

## Daily run

```bash
0 2 * * * cd /path/to/kkkk999999999999/docker/backup && docker compose --env-file .env run --rm backup
```

Do not start a second dump while one is already running. The container uses
`/tmp/brodan_backup.lock`.
