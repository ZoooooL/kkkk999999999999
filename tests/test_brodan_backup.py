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
        self.assertEqual(mod.DEFAULT_SFTP_PATH, "D:/Zool Sulotion")
        self.assertEqual(mod.DEFAULT_SFTP_HOST, "192.168.8.18")
        self.assertEqual(mod.DEFAULT_SFTP_USER, "lenovo")
        self.assertIn("D:/Zool Sulotion", mod.sftp_missing_message())
        cmd = mod.sftp_upload_program(
            "brodansh",
            "192.168.8.18",
            "lenovo",
            "secret",
            r"D:\Zool Sulotion",
            "brodansh_1.dump.gz",
        )
        self.assertIn("sftp://192.168.8.18/D:/Zool%20Sulotion/brodansh_1.dump.gz", cmd)
        self.assertIn("pg_dump --no-owner -Fc brodansh", cmd)
        self.assertEqual(mod.sftp_upload_program("brodansh", "", "u", "p", "D:/x", "f"), "")
        self.assertEqual(mod.DEFAULT_FOLDER, "/var/tmp/brodan_backups")


if __name__ == "__main__":
    unittest.main()
