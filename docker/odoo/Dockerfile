FROM odoo:18.0

USER root
COPY entrypoint-brodan.sh /entrypoint-brodan.sh
RUN chmod 755 /entrypoint-brodan.sh \
    && mkdir -p /mnt/extra-addons /odoo/odoo-server

USER odoo
ENTRYPOINT ["/entrypoint-brodan.sh"]
