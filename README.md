# Workplace Stress Letterbox

[![Tests](https://github.com/matlabwarrior/Stress-Letterbox/actions/workflows/tests.yml/badge.svg)](https://github.com/matlabwarrior/Stress-Letterbox/actions/workflows/tests.yml)

A privacy-first, self-hosted tool for logging moments of workplace stress.
Employees use a small desktop widget to note how they're doing, review
their entries privately, and choose what to submit. Leadership sees
aggregated, anonymous trends on a web dashboard, and nothing that reaches
the server can be traced back to a person.

Built for organisations of roughly 25–200 people, running on their own
network. It's designed as a demo and small internal pilot. Review
[`docs/deployment.md`](docs/deployment.md) before running it anywhere
beyond that.

---

## How it works

```
┌─────────────────────────────────────────────────────────────────┐
│                     EMPLOYEE'S COMPUTER                         │
│                                                                 │
│   PyQt6 tray widget  ◄──►  Local SQLite (letterbox.db)          │
│                            PIN hash, department, all entries,   │
│                            all written notes                    │
│                                                                 │
│   ╔═══════════════════════════════════════════════════════════╗ │
│   ║  ANONYMISATION BOUNDARY                                   ║ │
│   ║  Only these fields ever cross it:                         ║ │
│   ║    department, timestamp, stress_level, reason_category,  ║ │
│   ║    floor_x, floor_y  (location: off by default)           ║ │
│   ║  Never: names, PIN, machine name, IP, or any free text    ║ │
│   ╚═══════════════════════════════════════════════════════════╝ │
└───────────────────────────────┬─────────────────────────────────┘
                                │  HTTP on the local network
                                │  POST /api/submit
                                │  GET  /api/config, /api/departments
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       CENTRAL SERVER                            │
│                                                                 │
│   Flask app (gunicorn in Docker, or `python server/app.py`)     │
│                                                                 │
│   REST API  /api/*              Admin dashboard  /admin/*       │
│   - submit (re-filters fields)  - overview & trends             │
│   - departments, config         - filterable entries table      │
│   - floorplan (off by default)  - CSV / JSON export             │
│                                 - heatmap (off by default)      │
│                │                                                │
│                ▼                                                │
│   SQLite (server/data/letterbox.db)                             │
│   tables: entries, floorplans (no user table, no identity       │
│   columns; departments and reasons come from config.yaml)       │
└─────────────────────────────────────────────────────────────────┘
```

The two processes never share a database. The client keeps everything
locally until the employee explicitly reviews and submits.

---

## Privacy model

Privacy here is a property of the code, not a policy promise.

- **One whitelist, enforced twice.** `shared/constants.py` defines the six
  fields that may be submitted. The client's `_build_payload()`
  (`client/api/submit.py`) builds each outbound entry from exactly those
  fields, and the server's `_extract_entry()` (`server/api/submissions.py`)
  independently drops anything else. A bug on one side can't turn into a
  leak on its own.
- **No free text leaves the device.** Neither the quick-log note nor the
  "More detail" note is ever transmitted, in any configuration. Free text is
  the easiest way to accidentally identify someone, and the most likely to
  be read out of context.
- **No identities on the server.** No user accounts, no sessions, no machine
  identifiers. The database schema has nothing to re-identify.
- **Location tagging is opt-in.** A precise timestamp combined with a floor
  position can point to a single person, so the floor plan feature ships off
  (`floorplan.enabled: false`). Every related route returns 404 until an admin
  deliberately turns it on.
- **Coarse departments.** Configure departments of at least about five people,
  so a department label alone can't single anyone out.
- **The user stays in control.** Entries can be edited or permanently deleted
  before submission, and a review screen shows exactly what will be sent.

The full plain-language version for HR, staff representatives and data
protection officers is in [`docs/privacy-model.md`](docs/privacy-model.md).
To verify the guarantee yourself:

```bash
pytest tests/test_anonymisation_audit.py -v
```

---

## Quick start (one machine)

Requires Python 3.10+. Server and client run side by side, talking over
`localhost`. [`CLAUDE.md`](CLAUDE.md) has the full step-by-step demo
walkthrough.

```bash
# 1. Virtual environment + dependencies
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux / macOS
pip install -r requirements-server.txt -r requirements-client.txt

# 2. Configuration
copy config.yaml.example config.yaml     # Windows
# cp config.yaml.example config.yaml     # Linux / macOS
python tools/generate_admin_hash.py      # paste the hash into admin.password_hash
```

In `config.yaml`, also set `server.secret_key` to a long random string and
`client.server_url` to `http://127.0.0.1:5000`. There is no default admin
password.

```bash
# 3. Run (two terminals, venv active in both)
python server/app.py      # dashboard at http://127.0.0.1:5000/admin
python client/main.py     # first launch opens a setup wizard
```

On Windows you can also double-click `launch-server.bat` and
`launch-client.bat`, or run
`powershell -File tools\install_client_shortcut.ps1` to put a "Stress
Letterbox" shortcut on the Desktop and in the Start Menu.

---

## Deploying for a team

- **Server:** run it once on a machine everyone can reach. The included
  `Dockerfile` / `docker-compose.yml` run it under gunicorn, with the
  database and `config.yaml` mounted from the host so rebuilding the image
  never touches real data.
- **Clients:** install on each employee's computer, with `client.server_url`
  in that machine's `config.yaml` pointing at the server's address (not
  `127.0.0.1`). The shortcut installer warns if it still looks local.

Details, including Linux and Windows service setup, are in
[`docs/deployment.md`](docs/deployment.md).

---

## Configuration without code changes

Departments, reason categories, reminder frequency, retention period and the
floor plan feature all live in `config.yaml`. For example, to add a
department:

```yaml
departments:
  - id: your_new_dept
    name: Your New Department
    active: true
```

Restart the server (or call `POST /api/admin/reload-config` while logged in);
clients pick up the new list on their next launch. See
[`docs/adding-departments.md`](docs/adding-departments.md), including how to
retire a department without losing its history.

---

## Tests

```bash
pip install pytest
pytest tests/ -v
```

88 tests across client logic, the server API and its input validation,
admin login (CSRF protection and rate limiting), the floor plan on/off
switch, exports, and the privacy audit. They use their own temporary
database, so the server doesn't need to be running. GitHub Actions runs them
on Python 3.10 and 3.12 for every push and pull request.

---

## Tech stack

| Layer | Technologies |
|---|---|
| Desktop client | PyQt6, pystray, Pillow, requests, bcrypt, SQLite (stdlib) |
| Server | Python, Flask, Jinja2, SQLAlchemy 2, SQLite, bcrypt, Flask-Limiter, PyYAML |
| Dashboard | Vanilla JavaScript, Chart.js, Leaflet.js + Leaflet.heat, hand-written CSS |
| Deployment | Docker, Docker Compose, gunicorn |
| Testing / CI | pytest, GitHub Actions |

### Why these choices

- **Flask over FastAPI:** a low-traffic internal tool where batches are
  submitted weekly or monthly. Flask's simplicity means one IT admin can read
  and maintain every route, and Jinja2 templates fit the dashboard naturally.
- **SQLite over PostgreSQL:** very low write concurrency at this scale, no
  database service to run, and a backup is a file copy.
- **PyQt6 for the client:** cross-platform system-tray support and a proper
  frameless widget; tkinter looks dated and scales poorly on high-DPI
  screens.
- **Tray icon + floating popup, not a taskbar widget:** true Windows taskbar
  embedding needs native COM code, which isn't feasible in plain Python. See
  the note in `client/ui/widget.py`.

---

## Project structure

```
├── client/                      # PyQt6 desktop app
│   ├── main.py                  # Entry point: setup wizard, PIN, tray
│   ├── api/submit.py            # Anonymisation boundary (_build_payload) + server client
│   ├── storage/                 # Local SQLite: entries, PIN, session
│   └── ui/                      # Widget, letterbox, setup wizard, styles, icon
├── server/                      # Flask app
│   ├── app.py                   # App factory (create_app) + entry point
│   ├── config.py                # config.yaml loader
│   ├── extensions.py            # Rate limiter
│   ├── models/db.py             # SQLAlchemy models (entries, floorplans)
│   ├── api/                     # submit (re-filters fields), departments, floorplan
│   ├── dashboard/               # Admin login, routes, templates, static assets
│   └── data/                    # SQLite database lives here (not in git)
├── shared/constants.py          # SUBMISSION_FIELDS: the single field whitelist
├── tests/                       # pytest suite, incl. the privacy audit
├── tools/                       # Admin password hash, PIN reset, shortcut installer
├── docs/                        # Privacy model, deployment, departments
├── config.yaml.example          # Copy to config.yaml (never commit config.yaml)
├── Dockerfile, docker-compose.yml
├── launch-client / launch-server (.bat for Windows, .sh for Linux/macOS)
└── CLAUDE.md                    # Step-by-step single-machine demo guide
```

---

## License

MIT, see [`LICENSE`](LICENSE).
