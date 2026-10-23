# Deployment Guide

## Linux Server Deployment (Primary)

### Prerequisites
- Python 3.10+
- pip
- (Optional) Docker

### 1. Clone / copy the project to the server

```bash
cd /opt
git clone <your-repo> workplace-stress-letterbox
cd workplace-stress-letterbox
```

### 2. Install server dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-server.txt
```

### 3. Configure

```bash
cp config.yaml.example config.yaml
nano config.yaml
```

Key things to change:
- `server.host`: Set to `0.0.0.0` to accept LAN connections
- `server.port`: Default 5000; change if needed
- `server.secret_key`: Generate a random string: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `admin.password_hash`: Generate with:
  ```bash
  python3 -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
  ```
- `client.server_url`: Set to the server's LAN IP, e.g. `http://192.168.1.100:5000`
- `departments`: Update to match your organisation
- `database.path`: Defaults to `server/data/letterbox.db` — adjust if needed

### 4. Initialise the database

The database is created automatically on first run.

### 5a. Run with systemd (recommended for production)

`python server/app.py` starts Flask's built-in development server, which is
only meant for the single-machine demo. For a real server, run the same app
under gunicorn (installed with `requirements-server.txt`).

Create `/etc/systemd/system/stress-letterbox.service`:

```ini
[Unit]
Description=Stress Letterbox Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/workplace-stress-letterbox
ExecStart=/opt/workplace-stress-letterbox/venv/bin/gunicorn "server.app:create_app()" --bind 0.0.0.0:5000 --workers 1 --threads 4
Restart=on-failure
RestartSec=5
Environment=LETTERBOX_CONFIG=/opt/workplace-stress-letterbox/config.yaml

[Install]
WantedBy=multi-user.target
```

Notes:
- The listening address comes from `--bind`, not from `server.host` /
  `server.port` in `config.yaml` (those only apply to `python server/app.py`).
- Keep `--workers 1`. Login rate limiting is counted in memory, so separate
  worker processes would each keep their own count. `--threads` adds
  concurrency without that problem.
- The `www-data` user needs write access to `server/data/`.

```bash
systemctl daemon-reload
systemctl enable stress-letterbox
systemctl start stress-letterbox
systemctl status stress-letterbox
```

### 5b. Run with Docker (alternative)

Use the `Dockerfile` already in the repo root (don't duplicate it here — a
second copy just drifts out of sync). It runs the app under `gunicorn`
rather than Flask's own dev server, since that's what `python server/app.py`
would otherwise use — fine for the single-machine demo in `CLAUDE.md`, not
something to expose beyond that.

```bash
docker build -t stress-letterbox .
docker run -d \
  --name stress-letterbox \
  -p 5000:5000 \
  -v /opt/letterbox-data:/app/server/data \
  -v /opt/letterbox-config/config.yaml:/app/config.yaml:ro \
  stress-letterbox
```

### 6. Verify

Open a browser on the same network: `http://<server-ip>:5000/admin`

---

## Windows Server Notes

If the server must run on Windows:
1. All steps are the same; replace `venv/bin/activate` with `venv\Scripts\activate`
2. gunicorn doesn't run on Windows. Either run the Docker image with Docker
   Desktop (section 5b), or use waitress, a Windows-compatible production
   server:
   ```bat
   pip install waitress==3.0.2
   python -m waitress --call --listen=0.0.0.0:5000 --threads=4 server.app:create_app
   ```
   For auto-start, use NSSM (Non-Sucking Service Manager) to wrap that
   command as a Windows service. Don't wrap `python server/app.py` — that's
   the development server.
3. Open port 5000 in Windows Firewall

---

## Client Deployment (Windows + Linux)

**Before setting up any employee machine:** edit that machine's `config.yaml`
and set `client.server_url` to the real server's address (e.g.
`http://192.168.1.100:5000`), not `127.0.0.1`. A client left pointed at
`127.0.0.1` only ever talks to a server running on that same machine — the
most common rollout mistake. This has to be set per machine; it isn't
something the app can infer.

### Windows

```bat
cd C:\path\to\workplace-stress-letterbox
python -m venv venv
venv\Scripts\activate
pip install -r requirements-client.txt
```

Then either run `launch-client.bat` directly (double-click, or from a
terminal), or create a proper Desktop/Start Menu shortcut instead of relying
on someone remembering to double-click a `.bat` file:

```powershell
powershell -File tools\install_client_shortcut.ps1
```

This creates `Stress Letterbox.lnk` on the Desktop and in the Start Menu
(from which it can be pinned to the Start menu or taskbar), pointed straight
at the venv's `pythonw.exe` so it launches without a console window. It also
re-checks and warns if `config.yaml` still looks like a local demo address —
run it again any time as a sanity check, it's safe to re-run.

For auto-start on login instead: copy the same `.lnk` (or one made the same
way) into `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

### Linux

```bash
cd /path/to/workplace-stress-letterbox
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-client.txt
python client/main.py
```

For auto-start, add to the user's `.profile` or create a `.desktop` autostart entry:

```ini
# ~/.config/autostart/stress-letterbox.desktop
[Desktop Entry]
Type=Application
Name=Stress Letterbox
Exec=/path/to/venv/bin/python /path/to/client/main.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
```

---

## Backup

The entire server state lives in `server/data/letterbox.db`. A nightly cron backup:

```bash
0 2 * * * cp /opt/workplace-stress-letterbox/server/data/letterbox.db \
              /opt/backups/letterbox_$(date +\%Y\%m\%d).db
```

---

## TLS / HTTPS (Recommended for Production)

For a production deployment where the LAN is not fully trusted, put nginx in front:

```nginx
server {
    listen 443 ssl;
    server_name letterbox.yourorg.local;
    ssl_certificate     /etc/ssl/certs/letterbox.crt;
    ssl_certificate_key /etc/ssl/private/letterbox.key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Update `client.server_url` in `config.yaml` to `https://letterbox.yourorg.local`.
