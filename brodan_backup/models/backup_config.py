# -*- coding: utf-8 -*-
"""Helpers shared by the Python addon and the XML-RPC installer."""

import json

STUCK_BACKUP_MODULE_NAMES = (
    "brodan_backup",
    "brodan_backup_runtime_20260831_104812",
    "auto_backup_deejai",
)

CONFIG_MODEL = "x_brodan_backup_config"
LOG_MODEL = "x_brodan_backup_log"
MENU_NAME = "النسخ الاحتياطي"
CRON_NAME = "BRODAN: نسخة احتياطية يومية"
SERVER_ACTION_NAME = "BRODAN: تشغيل النسخة الاحتياطية"
DEFAULT_FOLDER = "/var/tmp/brodan_backups"
DEFAULT_SFTP_PATH = "/D:/Zool Sulotion"
DEFAULT_SFTP_HOST = "100.78.222.34"
DEFAULT_SFTP_USER = "lenovo"
DEFAULT_KEEP_DAYS = 2
DEFAULT_ONEDRIVE_FOLDER = "Brodansh_Backups"
RCLONE_BIN = "/var/tmp/brodan_rclone/rclone"
RCLONE_CONF = "/var/tmp/brodan-rclone.conf"
RCLONE_ZIP = "/var/tmp/rclone.zip"
# Refuse a local dump unless free bytes exceed database size plus this margin.
SAFETY_MARGIN_BYTES = 2 * 1024 * 1024 * 1024
MIN_PGDUMP_FREE_BYTES = 2 * 1024 * 1024 * 1024


def local_dump_allowed(db_size_bytes, free_bytes, margin_bytes=SAFETY_MARGIN_BYTES):
    """Return True only when a full local dump can fit on disk."""
    if db_size_bytes is None or free_bytes is None:
        return False
    try:
        db_size = int(db_size_bytes)
        free = int(free_bytes)
    except (TypeError, ValueError):
        return False
    if db_size <= 0 or free <= 0:
        return False
    return free > db_size + int(margin_bytes)


def skip_message(db_size_bytes, free_bytes):
    db_gb = (int(db_size_bytes or 0) / 1024 ** 3)
    free_gb = (int(free_bytes or 0) / 1024 ** 3)
    return (
        "تم تخطي النسخة المحلية: القاعدة %.1f GB والمساحة الحرة %.1f GB. "
        "أضف قرصاً أو اضبط SFTP للنسخ خارج السيرفر."
        % (db_gb, free_gb)
    )


def sftp_missing_message():
    return (
        "أدخل IP جهاز الويندوز في SFTP Host مع المستخدم وكلمة السر. "
        "المسار الافتراضي على القرص D هو %s (مشاركة \\\\WALEEDX1\\Zool Sulotion)."
        % DEFAULT_SFTP_PATH
    )


def unreachable_sftp_message(host, detail=""):
    host = host or DEFAULT_SFTP_HOST
    extra = (" تفصيل: " + str(detail).strip()[:300]) if str(detail or "").strip() else ""
    return (
        "السيرفر لا يصل إلى جهازك %s على المنفذ 22. لذلك يظهر التحميل ثم يتوقف "
        "بدون ملف على D. افتح Port Forwarding للمنفذ 22 على الراوتر إلى هذا الجهاز "
        "أو استخدم VPN ثم اضغط نسخ الآن."
        % host
    ) + extra


def shell_token(value):
    """Strip shell metacharacters before embedding in COPY TO PROGRAM."""
    text = str(value or "")
    for ch in ("'", '"', ";", "|", "&", "`", "$", "\n", "\r", " "):
        text = text.replace(ch, "")
    return text


def sftp_remote_url(remote_dir, filename=""):
    """Build an SFTP URL path. Windows OpenSSH uses /D:/folder; curl wants host/D:/folder."""
    remote_dir = str(remote_dir or DEFAULT_SFTP_PATH).replace("\\", "/").strip()
    remote_dir = remote_dir.replace("'", "").replace('"', "").replace(";", "")
    path = remote_dir.lstrip("/")
    if filename:
        path = "%s/%s" % (path.rstrip("/"), shell_token(filename) or str(filename).strip())
    return path.replace(" ", "%20")


def sftp_probe_program(host, user, password, remote_dir):
    """Tiny SFTP upload used to fail fast before starting a 50GB dump."""
    host = shell_token(host)
    user = shell_token(user)
    password = shell_token(password)
    if not (host and user and password):
        return ""
    remote = sftp_remote_url(remote_dir, "brodan_sftp_probe.txt")
    return (
        "printf brodan-sftp-ok | curl --connect-timeout 8 --max-time 20 "
        "--ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s "
        "> /tmp/brodan_sftp_probe.txt 2>&1"
        % (user, password, host, remote)
    )


def sftp_upload_program(dbname, host, user, password, remote_dir, filename):
    host = shell_token(host)
    user = shell_token(user)
    password = shell_token(password)
    filename = shell_token(filename)
    dbname = shell_token(dbname)
    if not (host and user and password and filename and dbname):
        return ""
    remote = sftp_remote_url(remote_dir, filename)
    return (
        "nohup sh -c \"pg_dump --no-owner -Fc %s | gzip | "
        "curl --connect-timeout 20 --ftp-create-dirs -sS -u %s:%s -T - sftp://%s/%s\" "
        ">/tmp/brodan_sftp_out.txt 2>&1 &"
        % (dbname, user, password, host, remote)
    )


def onedrive_missing_message():
    return (
        "الأفضل النسخ إلى OneDrive لأن سيرفر أودو يصل للإنترنت ولا يصل إلى اللاب. "
        "شغّل سكربت الربط على جهاز ويندوز، الصق الرمز في حقل OneDrive، ثم حفظ ونسخ الآن. "
        "الحساب المجاني 5GB لا يكفي؛ تحتاج مساحة كافية (يفضل Microsoft 365) لأن القاعدة نحو 50GB."
    )


def rclone_write_conf_program():
    """Install a stdin base64 token writer used by the live server action."""
    return (
        "cat > /var/tmp/brodan_write_rclone.py << 'BRD'\n"
        "import sys, base64, os, json, urllib.request, urllib.parse, urllib.error, subprocess, datetime\n"
        "raw = sys.stdin.read().strip().replace(chr(10), '').replace(chr(13), '')\n"
        "if raw.startswith(chr(34)) and raw.endswith(chr(34)):\n"
        "    raw = raw[1:-1]\n"
        "token = base64.b64decode(raw).decode()\n"
        "drive_id = ''\n"
        "drive_type = 'personal'\n"
        "status = 'start'\n"
        "obj = {}\n"
        "try:\n"
        "    obj = json.loads(token)\n"
        "except Exception:\n"
        "    obj = {}\n"
        "access = str(obj.get('access_token') or '')\n"
        "refresh = str(obj.get('refresh_token') or '')\n"
        "def graph_drive(acc):\n"
        "    req = urllib.request.Request('https://graph.microsoft.com/v1.0/me/drive?$select=id,driveType', headers={'Authorization': 'Bearer ' + acc})\n"
        "    with urllib.request.urlopen(req, timeout=20) as resp:\n"
        "        return json.loads(resp.read().decode())\n"
        "try:\n"
        "    if access:\n"
        "        info = graph_drive(access)\n"
        "        drive_id = str(info.get('id') or '')\n"
        "        drive_type = str(info.get('driveType') or 'personal')\n"
        "        status = 'access_ok'\n"
        "except Exception:\n"
        "    status = 'access_fail'\n"
        "if (not drive_id) and refresh:\n"
        "    try:\n"
        "        secret = subprocess.check_output(['/var/tmp/brodan_rclone/rclone', 'reveal', '_JUdzh3LnKNqSPcf4Wu5fgMFIQOI8glZu_akYgR8yf6egowNBg-R'], text=True, timeout=10).strip()\n"
        "        body = urllib.parse.urlencode({'client_id': 'b15665d9-eda6-4092-8539-0eec376afd59', 'client_secret': secret, 'grant_type': 'refresh_token', 'refresh_token': refresh, 'scope': 'Files.Read Files.ReadWrite Files.Read.All Files.ReadWrite.All Sites.Read.All offline_access'}).encode()\n"
        "        req = urllib.request.Request('https://login.microsoftonline.com/common/oauth2/v2.0/token', data=body, method='POST')\n"
        "        with urllib.request.urlopen(req, timeout=25) as resp:\n"
        "            tok = json.loads(resp.read().decode())\n"
        "        if tok.get('access_token'):\n"
        "            access = str(tok.get('access_token'))\n"
        "            obj['access_token'] = access\n"
        "            obj['token_type'] = str(tok.get('token_type') or 'Bearer')\n"
        "            if tok.get('refresh_token'):\n"
        "                obj['refresh_token'] = str(tok.get('refresh_token'))\n"
        "            if tok.get('expires_in'):\n"
        "                obj['expires_in'] = tok.get('expires_in')\n"
        "                exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=int(tok.get('expires_in')))\n"
        "                obj['expiry'] = exp.isoformat()\n"
        "            token = json.dumps(obj)\n"
        "            info = graph_drive(access)\n"
        "            drive_id = str(info.get('id') or '')\n"
        "            drive_type = str(info.get('driveType') or 'personal')\n"
        "            status = 'refresh_ok'\n"
        "        else:\n"
        "            status = 'refresh_empty'\n"
        "    except urllib.error.HTTPError as ex:\n"
        "        status = 'refresh_http:%s' % ex.code\n"
        "    except Exception as ex:\n"
        "        status = 'refresh_fail:' + type(ex).__name__\n"
        "lines = ['[onedrive]', 'type = onedrive', 'drive_type = ' + drive_type, 'token = ' + token]\n"
        "if drive_id:\n"
        "    lines.insert(3, 'drive_id = ' + drive_id)\n"
        "open('/var/tmp/brodan-rclone.conf', 'w').write(chr(10).join(lines) + chr(10))\n"
        "os.chmod('/var/tmp/brodan-rclone.conf', 0o600)\n"
        "open('/tmp/brodan_od_write_status.txt', 'w').write(status + ' drive_id=' + ('yes' if drive_id else 'no') + chr(10))\n"
        "if drive_id:\n"
        "    open('/tmp/brodan_od_newtoken.json', 'w').write(token)\n"
        "    os.chmod('/tmp/brodan_od_newtoken.json', 0o600)\n"
        "BRD"
    )


def rclone_install_program():
    return (
        "if [ ! -x %s ]; then "
        "curl -fsSL -o %s https://downloads.rclone.org/rclone-current-linux-amd64.zip && "
        "mkdir -p /var/tmp/brodan_rclone_extract /var/tmp/brodan_rclone && "
        "unzip -o %s -d /var/tmp/brodan_rclone_extract && "
        "RDIR=$(find /var/tmp/brodan_rclone_extract -maxdepth 1 -type d -name rclone-* | head -n 1) && "
        "cp \"$RDIR/rclone\" %s && chmod 755 %s && "
        "rm -rf %s /var/tmp/brodan_rclone_extract; "
        "fi; %s --config /var/tmp/brodan-rclone.conf version > /tmp/brodan_rclone_install.txt 2>&1; "
        "%s"
        % (RCLONE_BIN, RCLONE_ZIP, RCLONE_ZIP, RCLONE_BIN, RCLONE_BIN, RCLONE_ZIP, RCLONE_BIN, rclone_write_conf_program())
    )


ONEDRIVE_STREAM_SCRIPT = r'''#!/usr/bin/env python3
import glob, os, signal, subprocess, sys, time
DB = sys.argv[1]
FOLDER = sys.argv[2]
FNAME = sys.argv[3]
RCLONE = "/var/tmp/brodan_rclone/rclone"
CONF = "/var/tmp/brodan-rclone.conf"
LOCK = "/tmp/brodan_backup.lock"
LOG = "/tmp/brodan_od_out.txt"
STATUS = "/tmp/brodan_od_status.txt"
holder = None
def say(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    with open(LOG, "a") as fh:
        fh.write(line + "\n")
    with open(STATUS, "w") as fh:
        fh.write(msg[:500])
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
    global holder
    if holder is not None and holder.poll() is None:
        try:
            holder.terminate()
        except OSError:
            pass
    clear_lock()
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
for path in glob.glob("/tmp/rclone-spool*"):
    try:
        os.remove(path)
    except OSError:
        pass
psql = find_bin("psql")
pg_dump = find_bin("pg_dump")
holder = subprocess.Popen(
    [psql, "-d", DB, "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A"],
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
    say("FAIL snapshot: " + str(err)[:300])
    cleanup()
    sys.exit(1)
holder.stdin.write("SELECT pg_sleep(172800);\n")
holder.stdin.flush()
say("PASS1 measure snapshot " + snap)
dump1 = subprocess.Popen([pg_dump, "--no-owner", "-Fc", "--snapshot=" + snap, DB], stdout=subprocess.PIPE)
wc = subprocess.Popen(["wc", "-c"], stdin=dump1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
dump1.stdout.close()
out, err = wc.communicate()
drc1 = dump1.wait()
if drc1 != 0 or wc.returncode != 0:
    say("FAIL measure dump rc=%s wc=%s" % (drc1, wc.returncode))
    cleanup()
    sys.exit(1)
size = int((out or b"0").decode().strip() or "0")
if size < 1000:
    say("FAIL dump size too small: %s" % size)
    cleanup()
    sys.exit(1)
say("PASS2 upload size=%s to onedrive:%s/%s" % (size, FOLDER, FNAME))
logf = open(LOG, "a")
subprocess.call([RCLONE, "--config", CONF, "mkdir", "--onedrive-drive-type", "personal", "onedrive:" + FOLDER], stdout=logf, stderr=subprocess.STDOUT)
dump2 = subprocess.Popen([pg_dump, "--no-owner", "-Fc", "--snapshot=" + snap, DB], stdout=subprocess.PIPE)
rcat = subprocess.Popen(
    [RCLONE, "--config", CONF, "rcat", "--size", str(size), "--onedrive-drive-type", "personal", "--onedrive-chunk-size", "10M", "--retries", "3", "--stats", "60s", "--stats-one-line", "--stats-log-level", "NOTICE", "onedrive:%s/%s" % (FOLDER, FNAME)],
    stdin=dump2.stdout,
    stdout=logf,
    stderr=subprocess.STDOUT,
)
dump2.stdout.close()
rc = rcat.wait()
drc = dump2.wait()
if rc == 0 and drc == 0:
    say("OK uploaded onedrive:%s/%s size=%s" % (FOLDER, FNAME, size))
    cleanup()
    sys.exit(0)
say("FAIL rcat rc=%s dump rc=%s" % (rc, drc))
cleanup()
sys.exit(1)
'''

SFTP_STREAM_SCRIPT = (
    ONEDRIVE_STREAM_SCRIPT.replace(
        'CONF = "/var/tmp/brodan-rclone.conf"',
        'CONF = "/var/tmp/brodan-rclone-sftp.conf"',
    )
    .replace(
        'LOG = "/tmp/brodan_od_out.txt"',
        'LOG = "/tmp/brodan_sftp_out.txt"',
    )
    .replace(
        '[RCLONE, "--config", CONF, "mkdir", "--onedrive-drive-type", "personal", "onedrive:" + FOLDER]',
        '[RCLONE, "--config", CONF, "mkdir", "--sftp-known-hosts-file", "none", "winpc:" + FOLDER]',
    )
    .replace(
        '"--onedrive-drive-type", "personal", "--onedrive-chunk-size", "10M", "--retries", "3"',
        '"--sftp-socks-proxy", "127.0.0.1:1055", "--sftp-known-hosts-file", "none", "--retries", "3"',
    )
    .replace(
        '"onedrive:%s/%s" % (FOLDER, FNAME)',
        '"winpc:%s/%s" % (FOLDER, FNAME)',
    )
    .replace("to onedrive:%s/%s", "to sftp:%s/%s")
    .replace("OK uploaded onedrive:", "OK uploaded sftp:")
)


def sftp_stream_write_program():
    """Shell that writes the two-pass SFTP uploader onto the Odoo host."""
    import base64

    b64 = base64.b64encode(SFTP_STREAM_SCRIPT.encode("utf-8")).decode("ascii")
    inner = (
        "import base64,os; open('/var/tmp/brodan_sftp_stream.py','wb').write("
        "base64.b64decode('%s')); os.chmod('/var/tmp/brodan_sftp_stream.py', 0o755)"
    ) % b64
    return "python3 -c %s" % json.dumps(inner)


def rclone_write_sftp_conf_program():
    """Install a stdin base64 password writer for the Tailscale SFTP remote."""
    return (
        "cat > /var/tmp/brodan_write_sftp.py << 'BRDSFTP'\n"
        "import sys, base64, os, subprocess\n"
        "raw = sys.stdin.read().strip().replace(chr(10), '').replace(chr(13), '')\n"
        "pw = base64.b64decode(raw).decode()\n"
        "host = sys.argv[1] if len(sys.argv) > 1 else '100.78.222.34'\n"
        "user = sys.argv[2] if len(sys.argv) > 2 else 'lenovo'\n"
        "obsc = subprocess.check_output(['/var/tmp/brodan_rclone/rclone', 'obscure', pw], text=True).strip()\n"
        "lines = ['[winpc]', 'type = sftp', 'host = ' + host, 'user = ' + user, 'pass = ' + obsc, 'port = 22', 'socks_proxy = 127.0.0.1:1055', 'known_hosts_file = none', 'shell_type = unix']\n"
        "open('/var/tmp/brodan-rclone-sftp.conf', 'w').write(chr(10).join(lines) + chr(10))\n"
        "os.chmod('/var/tmp/brodan-rclone-sftp.conf', 0o600)\n"
        "BRDSFTP"
    )


def stream_write_program():
    """Shell that writes the two-pass OneDrive uploader onto the Odoo host."""
    import base64

    b64 = base64.b64encode(ONEDRIVE_STREAM_SCRIPT.encode("utf-8")).decode("ascii")
    inner = (
        "import base64,os; open('/var/tmp/brodan_od_stream.py','wb').write("
        "base64.b64decode('%s')); os.chmod('/var/tmp/brodan_od_stream.py', 0o755)"
    ) % b64
    return "python3 -c %s" % json.dumps(inner)


def rclone_rcat_program(dbname, folder, filename):
    dbname = shell_token(dbname)
    folder = shell_token(folder) or DEFAULT_ONEDRIVE_FOLDER
    filename = shell_token(filename)
    if not (dbname and filename):
        return ""
    return (
        "rm -f /tmp/rclone-spool*; nohup python3 /var/tmp/brodan_od_stream.py %s %s %s "
        ">/tmp/brodan_od_out.txt 2>&1 &"
        % (dbname, folder, filename)
    )


def rclone_probe_program():
    return (
        "%s --config %s lsd --onedrive-drive-type personal onedrive: --max-depth 1 --retries 1 "
        "--low-level-retries 1 --timeout 20s --contimeout 8s "
        "> /tmp/brodan_od_probe.txt 2>&1"
        % (RCLONE_BIN, RCLONE_CONF)
    )


def parse_df_available_bytes(df_text):
    """Parse `df -PB1` output and return the smallest Available column."""
    if not df_text:
        return None
    available = []
    for raw in str(df_text).splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("filesystem"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            available.append(int(parts[3]))
        except ValueError:
            continue
    return min(available) if available else None
