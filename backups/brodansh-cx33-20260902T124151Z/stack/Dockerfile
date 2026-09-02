FROM odoo:18.0

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        fonts-noto-core \
        fonts-hosny-amiri \
        fonts-kacst \
        fonts-arabeyes \
        fonts-dejavu-core \
        locales \
    && printf 'en_US.UTF-8 UTF-8\nar_EG.UTF-8 UTF-8\n' > /etc/locale.gen \
    && locale-gen \
    && mkdir -p /var/log/odoo /mnt/enterprise /mnt/extra-addons \
    && chown -R odoo:odoo /var/log/odoo /mnt/enterprise /mnt/extra-addons \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

USER odoo
