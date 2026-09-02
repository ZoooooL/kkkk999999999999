FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    DEST=onedrive \
    PGDATABASE=brodansh \
    RCLONE_CONFIG=/var/lib/rclone/rclone.conf \
    RCLONE_SOCKS=127.0.0.1:1055

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        iproute2 \
        procps \
        python3 \
        unzip \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
        | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 tailscale \
    && curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip \
    && unzip -o /tmp/rclone.zip -d /tmp \
    && RDIR="$(find /tmp -maxdepth 1 -type d -name 'rclone-*' | head -n 1)" \
    && cp "$RDIR/rclone" /usr/local/bin/rclone \
    && chmod 755 /usr/local/bin/rclone \
    && rm -rf /tmp/rclone.zip /tmp/rclone-* /var/lib/apt/lists/*

WORKDIR /app
COPY run_backup.py /app/run_backup.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/run_backup.py /app/entrypoint.sh \
    && mkdir -p /var/lib/tailscale /var/lib/rclone

VOLUME ["/var/lib/tailscale", "/var/lib/rclone"]

ENTRYPOINT ["/app/entrypoint.sh"]
