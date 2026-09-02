#!/usr/bin/env python3
"""Stream a deterministic gzip tar of the Odoo filestore to OneDrive.

Runs as postgres. File bytes come from local XML-RPC (the Odoo worker
reads the filestore). rclone rcat --size avoids spooling /tmp.
"""
import base64
import gzip
import io
import json
import os
import signal
import socket
import subprocess
import sys
import tarfile
import time
import xmlrpc.client

RCLONE = "/var/tmp/brodan_rclone/rclone"
CONF = "/var/tmp/brodan-rclone.conf"
LOCK = "/tmp/brodan_backup.lock"
LOG = "/tmp/brodan_fs_out.txt"
STATUS = "/tmp/brodan_fs_status.txt"
AUTH_KEY = "brodan.rpc_tmp"
SKIP_PATH = "/tmp/brodan_fs_skip.json"
BATCH_BYTES = 6 * 1024 * 1024
RESTORE_NAME = "RESTORE_BRODANSH.txt"
DB = ""
FOLDER = ""
FNAME = ""


def say(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    with open(STATUS, "w") as fh:
        fh.write(msg[:500])
    sys.stderr.write(line + "\n")


def find_bin(name):
    extra = ["/usr/bin", "/usr/lib/postgresql/16/bin", "/usr/lib/postgresql/15/bin", "/usr/lib/postgresql/14/bin"]
    for d in os.environ.get("PATH", "").split(":") + extra:
        path = os.path.join(d, name) if d else name
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return name


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def clear_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def cleanup(*_a):
    clear_lock()


def psql_cmd(sql):
    psql = find_bin("psql")
    return subprocess.check_output(
        [psql, "-d", DB, "-v", "ON_ERROR_STOP=1", "-Atc", sql],
        text=True,
        timeout=30,
    )


def load_auth():
    raw = (psql_cmd("SELECT value FROM ir_config_parameter WHERE key = '%s'" % AUTH_KEY) or "").strip()
    try:
        psql_cmd("DELETE FROM ir_config_parameter WHERE key = '%s'" % AUTH_KEY)
    except Exception:
        pass
    if not raw:
        say("FAIL missing rpc auth param")
        sys.exit(1)
    obj = json.loads(raw)
    url = str(obj.get("url") or "http://127.0.0.1:8069").rstrip("/")
    db = str(obj.get("db") or DB)
    user = str(obj.get("user") or "")
    key = str(obj.get("key") or "")
    if not (user and key):
        say("FAIL rpc auth incomplete")
        sys.exit(1)
    return url, db, user, key


def rpc_connect(url, db, user, key):
    socket.setdefaulttimeout(300)
    common = xmlrpc.client.ServerProxy("%s/xmlrpc/2/common" % url, allow_none=True)
    uid = common.authenticate(db, user, key, {})
    if not uid:
        say("FAIL xmlrpc auth")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy("%s/xmlrpc/2/object" % url, allow_none=True)
    return uid, models, db, key


def execute(models, db, uid, key, model, method, *args):
    last = None
    for attempt in range(4):
        try:
            return models.execute_kw(db, uid, key, model, method, list(args))
        except Exception as ex:
            last = ex
            time.sleep(1.5 * (attempt + 1))
    raise last


def list_ids(models, db, uid, key):
    return execute(
        models,
        db,
        uid,
        key,
        "ir.attachment",
        "search",
        [("store_fname", "!=", False)],
    ) or []


def read_meta(models, db, uid, key, ids):
    if not ids:
        return []
    return execute(models, db, uid, key, "ir.attachment", "read", ids, ["store_fname", "file_size"]) or []


def read_datas(models, db, uid, key, ids):
    if not ids:
        return []
    return execute(models, db, uid, key, "ir.attachment", "read", ids, ["store_fname", "datas"]) or []


def decode_row(row):
    fname = str(row.get("store_fname") or "").strip()
    raw = row.get("datas") or ""
    if not fname or not raw:
        return fname, b""
    try:
        data = base64.b64decode(raw)
    except Exception:
        return fname, b""
    return fname, data


def batched_payloads(models, db, uid, key, ids, skip):
    i = 0
    n = len(ids)
    while i < n:
        chunk = ids[i : i + 80]
        i += 80
        meta = read_meta(models, db, uid, key, chunk)
        groups = []
        current = []
        current_size = 0
        for row in meta:
            att_id = row["id"]
            if att_id in skip:
                continue
            fname = str(row.get("store_fname") or "").strip()
            size = int(row.get("file_size") or 0)
            if not fname:
                skip.add(att_id)
                continue
            if size <= 0:
                groups.append([att_id])
                continue
            if size > BATCH_BYTES:
                if current:
                    groups.append(current)
                    current = []
                    current_size = 0
                groups.append([att_id])
                continue
            if current and current_size + max(size, 1) > BATCH_BYTES:
                groups.append(current)
                current = []
                current_size = 0
            current.append(att_id)
            current_size += max(size, 1)
        if current:
            groups.append(current)
        for group in groups:
            rows = read_datas(models, db, uid, key, group)
            for row in rows:
                att_id = row["id"]
                fname, data = decode_row(row)
                if not fname or not data:
                    skip.add(att_id)
                    continue
                yield att_id, fname, data
            time.sleep(0.05)


def open_tar(fileobj):
    gz = gzip.GzipFile(filename="", mode="wb", fileobj=fileobj, compresslevel=1, mtime=0)
    tar = tarfile.open(fileobj=gz, mode="w:")
    return tar, gz


def add_member(tar, store_fname, data):
    info = tarfile.TarInfo(name="brodansh/" + store_fname)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    tar.addfile(info, io.BytesIO(data))


class Counter:
    def __init__(self):
        self.n = 0

    def write(self, data):
        n = len(data)
        self.n += n
        return n

    def flush(self):
        return None


def write_tar(fileobj, models, db, uid, key, ids, skip):
    tar, gz = open_tar(fileobj)
    count = 0
    bytes_in = 0
    try:
        for _att_id, fname, data in batched_payloads(models, db, uid, key, ids, skip):
            add_member(tar, fname, data)
            count += 1
            bytes_in += len(data)
            if count % 400 == 0:
                say("progress files=%s bytes_in=%s tar_out=%s" % (count, bytes_in, getattr(fileobj, "n", -1)))
    finally:
        tar.close()
        gz.close()
    return count, bytes_in


def restore_text():
    return (
        "Brodansh complete restore\n"
        "=========================\n"
        "OneDrive folder: Brodansh_Backups\n"
        "\n"
        "1) Database (PostgreSQL custom dump, already compressed with -Fc):\n"
        "   pg_restore --no-owner -d NEWDB brodansh_YYYYMMDD_HHMMSS.dump\n"
        "\n"
        "2) Attachments (this tar.gz is the full filestore):\n"
        "   tar -C /odoo/.local/share/Odoo/filestore -xzf brodansh_filestore_YYYYMMDD_HHMMSS.tar.gz\n"
        "   The archive contains brodansh/<hash-dir>/<hash> matching Odoo filestore layout.\n"
        "\n"
        "A dump file alone does NOT include images, PDFs, or other attachments.\n"
        "Keep one dump + this tar.gz together.\n"
    ).encode("utf-8")


def rclone_rcat(size, remote):
    logf = open(LOG, "a")
    return subprocess.Popen(
        [
            RCLONE,
            "--config",
            CONF,
            "rcat",
            "--size",
            str(int(size)),
            "--onedrive-drive-type",
            "personal",
            "--onedrive-chunk-size",
            "10M",
            "--retries",
            "3",
            "--stats",
            "60s",
            "--stats-one-line",
            "--stats-log-level",
            "NOTICE",
            remote,
        ],
        stdin=subprocess.PIPE,
        stdout=logf,
        stderr=subprocess.STDOUT,
    )


def main(argv=None):
    global DB, FOLDER, FNAME
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 4:
        sys.stderr.write("usage: brodan_filestore_stream.py DB FOLDER FNAME\n")
        sys.exit(2)
    DB, FOLDER, FNAME = argv[1], argv[2], argv[3]
    try:
        os.nice(10)
    except OSError:
        pass
    if os.path.exists(LOCK):
        try:
            old = int(open(LOCK).read().strip() or "0")
        except Exception:
            old = 0
        if old and old != os.getpid() and alive(old):
            say("SKIP already running pid %s" % old)
            sys.exit(0)
    open(LOCK, "w").write(str(os.getpid()))
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    for path in [p for p in os.listdir("/tmp") if p.startswith("rclone-spool")]:
        try:
            os.remove(os.path.join("/tmp", path))
        except OSError:
            pass
    url, rpc_db, user, key = load_auth()
    say("AUTH_OK xmlrpc %s db=%s" % (url, rpc_db))
    uid, models, rpc_db, key = rpc_connect(url, rpc_db, user, key)
    ids = list_ids(models, rpc_db, uid, key)
    say("PASS1 measure attachments=%s" % len(ids))
    skip = set()
    counter = Counter()
    count, bytes_in = write_tar(counter, models, rpc_db, uid, key, ids, skip)
    size = int(counter.n)
    open(SKIP_PATH, "w").write(json.dumps(sorted(skip)))
    if size < 1000 or count < 1:
        say("FAIL tar too small files=%s size=%s" % (count, size))
        cleanup()
        sys.exit(1)
    say("PASS2 upload files=%s bytes_in=%s tar_size=%s to onedrive:%s/%s" % (count, bytes_in, size, FOLDER, FNAME))
    subprocess.call(
        [RCLONE, "--config", CONF, "mkdir", "--onedrive-drive-type", "personal", "onedrive:" + FOLDER],
        stdout=open(LOG, "a"),
        stderr=subprocess.STDOUT,
    )
    skip2 = set(json.loads(open(SKIP_PATH).read() or "[]"))
    rcat = rclone_rcat(size, "onedrive:%s/%s" % (FOLDER, FNAME))
    count2, _bytes2 = write_tar(rcat.stdin, models, rpc_db, uid, key, ids, skip2)
    rcat.stdin.close()
    rc = rcat.wait()
    if rc != 0:
        say("FAIL rcat rc=%s files=%s" % (rc, count2))
        cleanup()
        sys.exit(1)
    note = restore_text()
    note_p = rclone_rcat(len(note), "onedrive:%s/%s" % (FOLDER, RESTORE_NAME))
    note_p.stdin.write(note)
    note_p.stdin.close()
    note_p.wait()
    say("OK uploaded onedrive:%s/%s files=%s tar_size=%s" % (FOLDER, FNAME, count2, size))
    cleanup()
    sys.exit(0)


if __name__ == "__main__":
    main()
