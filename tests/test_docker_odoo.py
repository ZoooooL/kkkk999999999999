import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ODOO = ROOT / "docker" / "odoo"


def _read(name):
    return (ODOO / name).read_text(encoding="utf-8")


class DockerOdooTests(unittest.TestCase):
    def test_prod_reuses_live_enterprise_and_host_postgres(self):
        prod = _read("docker-compose.prod.yml")
        compose = _read("docker-compose.yml")
        cutover = _read("cutover.sh")
        dockerfile = _read("Dockerfile")
        entry = _read("entrypoint-brodan.sh")
        self.assertIn("odoo:18.0", dockerfile)
        self.assertIn("/odoo/odoo-server/odoo-bin", entry)
        self.assertIn("network_mode: host", prod)
        self.assertIn("/odoo:/odoo", prod)
        self.assertIn("/etc/odoo-server.conf", prod)
        self.assertIn("/var/run/postgresql:/var/run/postgresql", prod)
        self.assertIn("ODOO_DATA_DIR", prod)
        self.assertNotIn("postgres:", prod)
        self.assertIn("postgres:16", compose)
        self.assertIn("nginx:1.18", compose)
        self.assertIn("18080:80", compose)
        self.assertIn("odoo-server-att.conf", cutover)
        self.assertIn("pkill -f '/odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf'", cutover)
        self.assertNotIn("pg_dump", cutover)
        self.assertNotIn("pg_dump", prod)
        self.assertIn("must run as root", cutover)

    def test_nginx_and_odoo_match_brodansh_url(self):
        nginx = _read("nginx/brodansh.conf")
        conf = _read("config/odoo.conf")
        self.assertIn("server_name brodansh.de.com.eg", nginx)
        self.assertIn("proxy_pass http://brodansh_odoo;", nginx)
        self.assertIn("location /websocket", nginx)
        self.assertIn("location /longpolling", nginx)
        self.assertIn("X-Forwarded-Proto", nginx)
        self.assertIn("proxy_mode = True", conf)
        self.assertIn("dbfilter = ^brodansh$", conf)
        self.assertIn("http_port = 8069", conf)
        self.assertIn("gevent_port = 8072", conf)
        self.assertIn("brodan_backup", _read("docker-compose.yml"))
        self.assertNotIn("${ADMIN_PASSWD}", conf)

    def test_env_example_has_no_secrets(self):
        example = _read(".env.example")
        self.assertIn("ODOO_UID=", example)
        self.assertIn("ODOO_DATA_DIR=/home/odoo/.local/share/Odoo", example)
        self.assertNotIn("tskey-", example)
        self.assertNotIn("eyJ", example)
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("docker/odoo/.env", ignore)
        self.assertTrue((ODOO / "README.md").is_file())
        self.assertIn("/odoo", _read("README.md"))


if __name__ == "__main__":
    unittest.main()
