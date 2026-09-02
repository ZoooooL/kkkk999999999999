#!/usr/bin/env python3
"""Stream a PostgreSQL custom dump to rclone without writing the dump to disk.

PASS1 measures size with pg_dump --snapshot | wc -c.
PASS2 uploads with rclone rcat --size so OneDrive does not spool /tmp.
"""
from __future__ import annotations

import glob
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request


ALLOWED_DEST = ("onedrive", "sftp")


def env(name, default=""):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip()


def dest_name():
    dest = env("DEST", "onedrive").lower()
    if dest not in ALLOWED_DEST:
        raise ValueError("DEST must be onedrive or sftp, got %r" % dest)
    return dest


def backup_filename(now=None):
    name = env("BACKUP_FILENAME")
    if name:
        return name
    db = env("PGDATABASE", "brodansh")
    stamp = time.strftime("%Y%m%d_%H%M%S", now or time.gmtime())
    return "%s_%s.dump" % (db, stamp)


def remote_folder(dest, onedrive_folder, sftp_path):
    if dest == "onedrive":
        folder = (onedrive_folder or "Brodansh_Backups").strip().strip("/")
        return folder
    path = (sftp_path or "/D:/Zool Sulotion").replace("\\", "/").strip()
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/D:/Zool Sulotion"


def remote_spec(dest, folder, filename):
    if dest == "onedrive":
        return "onedrive:%s/%s" % (folder, filename)
    return "winpc:%s/%s" % (folder, filename)


def mkdir_spec(dest, folder):
    if dest == "onedrive":
        return "onedrive:" + folder
    return "winpc:" + folder


def rcat_args(rclone_bin, conf, dest, remote, size, socks="127.0.0.1:1055"):
    args = [
        rclone_bin,
        "--config",
        conf,
        "rcat",
        "--size",
        str(int(size)),
        "--retries",
        "3",
        "--stats",
        "60s",
        "--stats-one-line",
        "--stats-log-level",
        "NOTICE",
    ]
    if dest == "onedrive":
        args.extend(
            [
                "--onedrive-drive-type",
                "personal",
                "--onedrive-chunk-size",
                "10M",
            ]
        )
    else:
        args.extend(
            [
                "--sftp-socks-proxy",
                socks,
                "--sftp-known-hosts-file",
                "none",
            ]
        )
    args.append(remote)
    return args


def mkdir_args(rclone_bin, conf, dest, folder, socks="127.0.0.1:1055"):
    args = [rclone_bin, "--config", conf, "mkdir"]
    if dest == "onedrive":
        args.extend(["--onedrive-drive-type", "personal"])
    else:
        args.extend(["--sftp-socks-proxy", socks, "--sftp-known-hosts-file", "none"])
    args.append(mkdir_spec(dest, folder))
    return args


def find_bin(name):
    extra = [
        "/usr/bin",
        "/usr/local/bin",
        "/usr/lib/postgresql/16/bin",
        "/usr/lib/postgresql/15/bin",
        "/usr/lib/postgresql/14/bin",
    ]
    for directory in os.environ.get("PATH", "").split(":") + extra:
        path = os.path.join(directory, name) if directory else name
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return name


def say(log_path, status_path, msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    with open(log_path, "a") as fh:
        fh.write(line + "\n")
    with open(status_path, "w") as fh:
        fh.write(msg[:500])
    sys.stderr.write(line + "\n")


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock(lock_path):
    if os.path.exists(lock_path):
        try:
            old = int(open(lock_path).read().strip() or "0")
        except (OSError, ValueError):
            old = 0
        if old and old != os.getpid() and pid_alive(old):
            return old
    with open(lock_path, "w") as fh:
        fh.write(str(os.getpid()))
    return 0


def clear_lock(lock_path):
    try:
        os.remove(lock_path)
    except OSError:
        pass


def clear_rclone_spools():
    for path in glob.glob("/tmp/rclone-spool*"):
        try:
            os.remove(path)
        except OSError:
            pass


def graph_drive_id(access_token):
    req = urllib.request.Request(
        "https://graph.microsoft.com/v1.0/me/drive?$select=id,driveType",
        headers={"Authorization": "Bearer " + access_token},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        info = json.loads(resp.read().decode())
    return str(info.get("id") or ""), str(info.get("driveType") or "personal")


def write_rclone_conf(dest, conf_path, rclone_bin):
    os.makedirs(os.path.dirname(conf_path) or ".", exist_ok=True)
    if dest == "onedrive":
        raw = env("ONEDRIVE_TOKEN_JSON")
        if not raw:
            if os.path.isfile(conf_path):
                return conf_path
            raise SystemExit("ONEDRIVE_TOKEN_JSON is empty and %s is missing" % conf_path)
        obj = json.loads(raw)
        access = str(obj.get("access_token") or "")
        drive_id = env("ONEDRIVE_DRIVE_ID")
        drive_type = env("ONEDRIVE_DRIVE_TYPE") or "personal"
        if access and not drive_id:
            try:
                drive_id, drive_type = graph_drive_id(access)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
                drive_id = drive_id or ""
        lines = ["[onedrive]", "type = onedrive", "drive_type = " + drive_type, "token = " + json.dumps(obj)]
        if drive_id:
            lines.insert(3, "drive_id = " + drive_id)
        with open(conf_path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
    else:
        host = env("SFTP_HOST", "100.78.222.34")
        user = env("SFTP_USER", "lenovo")
        password = env("SFTP_PASSWORD")
        socks = env("RCLONE_SOCKS", "127.0.0.1:1055")
        if not password:
            if os.path.isfile(conf_path):
                return conf_path
            raise SystemExit("SFTP_PASSWORD is empty and %s is missing" % conf_path)
        obsc = subprocess.check_output([rclone_bin, "obscure", password], text=True).strip()
        lines = [
            "[winpc]",
            "type = sftp",
            "host = " + host,
            "user = " + user,
            "pass = " + obsc,
            "port = 22",
            "socks_proxy = " + socks,
            "known_hosts_file = none",
            "shell_type = unix",
        ]
        with open(conf_path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
    os.chmod(conf_path, 0o600)
    return conf_path


def wait_for_tailscale(host, seconds, log_path, status_path):
    deadline = time.time() + int(seconds)
    ts = find_bin("tailscale")
    while time.time() < deadline:
        try:
            sock = env("TAILSCALE_SOCKET", "/var/run/tailscale/tailscaled.sock")
            out = subprocess.check_output(
                [ts, "--socket", sock, "status"],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=8,
            )
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
            out = ""
        if host and host in out and "Logged out" not in out:
            say(log_path, status_path, "Tailscale sees %s" % host)
            return True
        if "Logged out" in out:
            time.sleep(2)
            continue
        if host and host in out:
            return True
        time.sleep(2)
    say(log_path, status_path, "FAIL Tailscale did not show host %s" % host)
    return False


def measure_dump(pg_dump, db, snapshot, log_path, status_path):
    say(log_path, status_path, "PASS1 measure snapshot " + snapshot)
    dump1 = subprocess.Popen(
        [pg_dump, "--no-owner", "-Fc", "--snapshot=" + snapshot, db],
        stdout=subprocess.PIPE,
    )
    wc = subprocess.Popen(["wc", "-c"], stdin=dump1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if dump1.stdout is not None:
        dump1.stdout.close()
    out, _err = wc.communicate()
    drc1 = dump1.wait()
    if drc1 != 0 or wc.returncode != 0:
        raise SystemExit("FAIL measure dump rc=%s wc=%s" % (drc1, wc.returncode))
    size = int((out or b"0").decode().strip() or "0")
    if size < 1000:
        raise SystemExit("FAIL dump size too small: %s" % size)
    return size


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dest = dest_name()
    db = env("PGDATABASE", "brodansh")
    folder = remote_folder(dest, env("ONEDRIVE_FOLDER", "Brodansh_Backups"), env("SFTP_PATH", "/D:/Zool Sulotion"))
    fname = backup_filename()
    rclone_bin = env("RCLONE_BIN") or find_bin("rclone")
    conf = env("RCLONE_CONFIG", "/var/lib/rclone/rclone.conf")
    lock_path = env("BACKUP_LOCK", "/tmp/brodan_backup.lock")
    log_path = env("BACKUP_LOG", "/tmp/brodan_backup.log")
    status_path = env("BACKUP_STATUS", "/tmp/brodan_backup_status.txt")
    socks = env("RCLONE_SOCKS", "127.0.0.1:1055")
    holder = None

    def cleanup(*_a):
        if holder is not None and holder.poll() is None:
            try:
                holder.terminate()
            except OSError:
                pass
        clear_lock(lock_path)

    other = acquire_lock(lock_path)
    if other:
        say(log_path, status_path, "SKIP already running pid %s" % other)
        return 0

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    clear_rclone_spools()

    try:
        write_rclone_conf(dest, conf, rclone_bin)
        if dest == "sftp":
            host = env("SFTP_HOST", "100.78.222.34")
            wait_secs = int(env("TAILSCALE_WAIT_SECS", "90") or "90")
            if not wait_for_tailscale(host, wait_secs, log_path, status_path):
                return 1

        psql = find_bin("psql")
        pg_dump = find_bin("pg_dump")
        holder = subprocess.Popen(
            [psql, "-d", db, "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        holder.stdin.write("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;\n")
        holder.stdin.write("SELECT pg_export_snapshot();\n")
        holder.stdin.flush()
        snap = ""
        deadline = time.time() + 20
        while time.time() < deadline and not snap:
            line = holder.stdout.readline()
            if not line:
                break
            snap = line.strip()
        if not snap:
            err = holder.stderr.read() if holder.stderr else ""
            say(log_path, status_path, "FAIL snapshot: " + str(err)[:300])
            return 1
        holder.stdin.write("SELECT pg_sleep(172800);\n")
        holder.stdin.flush()

        size = measure_dump(pg_dump, db, snap, log_path, status_path)
        remote = remote_spec(dest, folder, fname)
        say(log_path, status_path, "PASS2 upload size=%s to %s" % (size, remote))
        logf = open(log_path, "a")
        subprocess.call(mkdir_args(rclone_bin, conf, dest, folder, socks), stdout=logf, stderr=subprocess.STDOUT)
        dump2 = subprocess.Popen(
            [pg_dump, "--no-owner", "-Fc", "--snapshot=" + snap, db],
            stdout=subprocess.PIPE,
        )
        rcat = subprocess.Popen(
            rcat_args(rclone_bin, conf, dest, remote, size, socks),
            stdin=dump2.stdout,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        if dump2.stdout is not None:
            dump2.stdout.close()
        rc = rcat.wait()
        drc = dump2.wait()
        if rc == 0 and drc == 0:
            say(log_path, status_path, "OK uploaded %s size=%s" % (remote, size))
            return 0
        say(log_path, status_path, "FAIL rcat rc=%s dump rc=%s" % (rc, drc))
        return 1
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main() or 0)
