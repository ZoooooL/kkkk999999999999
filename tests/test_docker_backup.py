import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ROOT / "docker" / "backup"
spec = importlib.util.spec_from_file_location("run_backup", DOCKER / "run_backup.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _read(name):
    return (DOCKER / name).read_text(encoding="utf-8")


class DockerBackupTests(unittest.TestCase):
    def test_compose_and_dockerfile_ship_rclone_pg_dump_and_tailscale(self):
        dockerfile = _read("Dockerfile")
        compose = _read("docker-compose.yml")
        host_compose = _read("docker-compose.host.yml")
        entry = _read("entrypoint.sh")
        self.assertIn("postgresql-client-16", dockerfile)
        self.assertIn("rclone", dockerfile)
        self.assertIn("tailscale", dockerfile)
        self.assertIn("python3", dockerfile)
        self.assertIn("downloads.rclone.org", dockerfile)
        self.assertIn("backup:", compose)
        self.assertIn("required: false", compose)
        self.assertIn("required: false", host_compose)
        self.assertIn("host.docker.internal:host-gateway", compose)
        self.assertIn("network_mode: host", host_compose)
        self.assertIn("PGHOST: \"127.0.0.1\"", host_compose)
        self.assertIn("userspace-networking", entry)
        self.assertIn("socks5-server=127.0.0.1:1055", entry)
        self.assertIn("run_backup.py", entry)
        self.assertIn("TS_AUTHKEY", entry)

    def test_env_example_has_placeholders_not_secrets(self):
        example = _read(".env.example")
        self.assertIn("DEST=onedrive", example)
        self.assertIn("PGPASSWORD=", example)
        self.assertIn("ONEDRIVE_TOKEN_JSON=", example)
        self.assertIn("SFTP_PASSWORD=", example)
        self.assertIn("TS_AUTHKEY=", example)
        self.assertIn("100.78.222.34", example)
        self.assertIn("/D:/Zool Sulotion", example)
        self.assertNotIn("tskey-", example)
        self.assertNotIn("eyJ", example)
        self.assertNotRegex(example, r"PGPASSWORD=.+")
        for leaked in ("BEGIN PRIVATE", "refresh_token", "client_secret"):
            self.assertNotIn(leaked, example)

    def test_remote_paths_and_rcat_use_known_size(self):
        self.assertEqual(mod.remote_folder("onedrive", "Brodansh_Backups", ""), "Brodansh_Backups")
        self.assertEqual(
            mod.remote_folder("sftp", "", r"D:\Zool Sulotion"),
            "/D:/Zool Sulotion",
        )
        self.assertEqual(
            mod.remote_spec("onedrive", "Brodansh_Backups", "brodansh_1.dump"),
            "onedrive:Brodansh_Backups/brodansh_1.dump",
        )
        self.assertEqual(
            mod.remote_spec("sftp", "/D:/Zool Sulotion", "brodansh_1.dump"),
            "winpc:/D:/Zool Sulotion/brodansh_1.dump",
        )
        args = mod.rcat_args("rclone", "/cfg", "onedrive", "onedrive:Brodansh_Backups/f.dump", 4596004625)
        self.assertIn("--size", args)
        self.assertIn("4596004625", args)
        self.assertIn("rcat", args)
        self.assertNotIn("gzip", " ".join(args))
        sftp_args = mod.rcat_args("rclone", "/cfg", "sftp", "winpc:/D:/Zool Sulotion/f.dump", 1000)
        self.assertIn("--sftp-socks-proxy", sftp_args)
        self.assertIn("127.0.0.1:1055", sftp_args)

    def test_dest_validation_and_dump_filename(self):
        old = os.environ.get("DEST")
        os.environ["DEST"] = "ftp"
        try:
            with self.assertRaises(ValueError):
                mod.dest_name()
        finally:
            if old is None:
                os.environ.pop("DEST", None)
            else:
                os.environ["DEST"] = old
        os.environ["BACKUP_FILENAME"] = "fixed.dump"
        try:
            self.assertEqual(mod.backup_filename(), "fixed.dump")
        finally:
            os.environ.pop("BACKUP_FILENAME", None)
        name = mod.backup_filename()
        self.assertTrue(name.endswith(".dump"))
        self.assertNotIn(".gz", name)
        self.assertNotIn("| gzip |", _read("run_backup.py"))
        self.assertIn("pg_export_snapshot", _read("run_backup.py"))
        self.assertIn("--snapshot=", _read("run_backup.py"))
        self.assertIn("brodan_backup.lock", _read("run_backup.py"))
        self.assertIn("rclone-spool", _read("run_backup.py"))
        self.assertIn("--socket", _read("run_backup.py"))

    def test_gitignore_keeps_dotenv_out_of_git(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("docker/backup/.env", ignore)
        self.assertTrue((DOCKER / ".env.example").is_file())
        self.assertTrue((DOCKER / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
