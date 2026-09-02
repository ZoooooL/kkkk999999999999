import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "brodan_backup" / "models" / "backup_config.py"
spec = importlib.util.spec_from_file_location("backup_config", HELPER)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class BrodanBackupTests(unittest.TestCase):
    def test_stuck_modules_are_the_imported_backup_apps(self):
        self.assertIn("brodan_backup_runtime_20260831_104812", mod.STUCK_BACKUP_MODULE_NAMES)
        self.assertIn("auto_backup_deejai", mod.STUCK_BACKUP_MODULE_NAMES)
        self.assertIn("brodan_backup", mod.STUCK_BACKUP_MODULE_NAMES)

    def test_local_dump_refused_when_disk_is_smaller_than_database(self):
        db_size = 54 * 1024 ** 3
        free = 6 * 1024 ** 3
        self.assertFalse(mod.local_dump_allowed(db_size, free))
        self.assertIn("تم تخطي", mod.skip_message(db_size, free))

    def test_local_dump_allowed_with_enough_headroom(self):
        db_size = 5 * 1024 ** 3
        free = 20 * 1024 ** 3
        self.assertTrue(mod.local_dump_allowed(db_size, free))

    def test_parse_df_takes_smallest_available(self):
        text = (
            "Filesystem 1-blocks Used Available Capacity Mounted on\n"
            "/dev/root 100 80 20 80% /\n"
            "/dev/tmp 50 40 10 80% /tmp\n"
        )
        self.assertEqual(mod.parse_df_available_bytes(text), 10)

    def test_windows_d_path_and_sftp_command(self):
        self.assertEqual(mod.DEFAULT_SFTP_PATH, "/D:/Zool Sulotion")
        self.assertEqual(mod.DEFAULT_SFTP_HOST, "100.78.222.34")
        self.assertEqual(mod.DEFAULT_SFTP_USER, "lenovo")
        self.assertIn("/D:/Zool Sulotion", mod.sftp_missing_message())
        cmd = mod.sftp_upload_program(
            "brodansh",
            "100.78.222.34",
            "lenovo",
            "secret",
            r"/D:/Zool Sulotion",
            "brodansh_1.dump.gz",
        )
        self.assertIn("sftp://100.78.222.34/D:/Zool%20Sulotion/brodansh_1.dump.gz", cmd)
        self.assertIn("pg_dump --no-owner -Fc brodansh", cmd)
        self.assertIn("--connect-timeout 20", cmd)
        self.assertIn("nohup sh -c", cmd)
        self.assertEqual(mod.sftp_upload_program("brodansh", "", "u", "p", "D:/x", "f"), "")
        self.assertEqual(mod.DEFAULT_FOLDER, "/var/tmp/brodan_backups")
        probe = mod.sftp_probe_program("100.78.222.34", "lenovo", "secret", r"/D:/Zool Sulotion")
        self.assertIn("--connect-timeout 8", probe)
        self.assertIn("brodan_sftp_probe.txt", probe)
        self.assertIn("100.78.222.34", mod.unreachable_sftp_message("100.78.222.34"))
        self.assertIn("يتوقف", mod.unreachable_sftp_message("100.78.222.34"))

    def test_onedrive_stream_command(self):
        self.assertEqual(mod.DEFAULT_ONEDRIVE_FOLDER, "Brodansh_Backups")
        self.assertIn("OneDrive", mod.onedrive_missing_message())
        self.assertIn("5GB", mod.onedrive_missing_message())
        install = mod.rclone_install_program()
        self.assertIn("brodan_write_rclone.py", install)
        self.assertIn("downloads.rclone.org", install)
        self.assertIn("/var/tmp/brodan_rclone/rclone", install)
        self.assertIn("login.microsoftonline.com", install)
        self.assertIn("refresh_token", install)
        self.assertIn("drive_id", install)
        cmd = mod.rclone_rcat_program("brodansh", "Brodansh_Backups", "brodansh_1.dump")
        self.assertIn("brodan_od_stream.py", cmd)
        self.assertIn("brodansh", cmd)
        self.assertIn("Brodansh_Backups", cmd)
        self.assertIn("brodansh_1.dump", cmd)
        self.assertIn("nohup python3", cmd)
        self.assertNotIn("| gzip |", cmd)
        self.assertEqual(mod.rclone_rcat_program("", "Brodansh_Backups", "f"), "")
        self.assertIn("--size", mod.ONEDRIVE_STREAM_SCRIPT)
        self.assertIn("pg_export_snapshot", mod.ONEDRIVE_STREAM_SCRIPT)
        self.assertIn("rcat", mod.ONEDRIVE_STREAM_SCRIPT)
        self.assertIn("brodan_backup.lock", mod.ONEDRIVE_STREAM_SCRIPT)
        self.assertIn("--snapshot=", mod.ONEDRIVE_STREAM_SCRIPT)
        self.assertIn("rclone-spool", mod.ONEDRIVE_STREAM_SCRIPT)
        write_py = mod.sftp_stream_write_program()
        self.assertIn("brodan_sftp_stream.py", write_py)
        self.assertIn("winpc:", mod.SFTP_STREAM_SCRIPT)
        self.assertIn("127.0.0.1:1055", mod.SFTP_STREAM_SCRIPT)
        self.assertIn("brodan-rclone-sftp.conf", mod.SFTP_STREAM_SCRIPT)
        conf_py = mod.rclone_write_sftp_conf_program()
        self.assertIn("brodan_write_sftp.py", conf_py)
        self.assertIn("socks_proxy", conf_py)
        probe = mod.rclone_probe_program()
        self.assertIn("lsd --onedrive-drive-type personal onedrive:", probe)
        self.assertIn("--contimeout 8s", probe)

    def test_backup_ui_is_owner_only(self):
        self.assertEqual(mod.BACKUP_OWNER_LOGIN, "whmm2299@hotmail.com")
        self.assertEqual(mod.BACKUP_OWNER_UID, 2)
        self.assertEqual(mod.BACKUP_GROUP_NAME, "Brodansh Backup Owner")
        self.assertIn("BRODAN: onedrive meta", mod.LEFTOVER_BACKUP_ACTION_NAMES)
        self.assertIn("BRODAN: run ts check", mod.LEFTOVER_BACKUP_ACTION_NAMES)
        self.assertIn("BRODAN: stop od dump", mod.LEFTOVER_BACKUP_ACTION_NAMES)
        views = (ROOT / "brodan_backup" / "views" / "backup_views.xml").read_text(encoding="utf-8")
        self.assertIn("groups=\"brodan_backup.group_backup_owner\"", views)
        access = (ROOT / "brodan_backup" / "security" / "ir.model.access.csv").read_text(encoding="utf-8")
        self.assertIn("group_backup_owner", access)
        self.assertNotIn("base.group_system", access)
        installer = (ROOT / "scripts" / "install_brodan_backup.py").read_text(encoding="utf-8")
        self.assertIn("restrict_backup_to_owner", installer)
        self.assertIn("LEFTOVER_BACKUP_ACTION_NAMES", installer)


if __name__ == "__main__":
    unittest.main()
