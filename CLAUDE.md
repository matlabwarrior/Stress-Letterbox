# CLAUDE.md — Stress Letterbox: Single-Machine Demo Setup

## What you are doing

You are setting up the **Workplace Stress Letterbox** project so it runs fully on one machine — server and client together. The goal is a working demo suitable for presenting to an organisation.

The project has two processes that run simultaneously:
- **Server** — a Flask web app (`server/app.py`) that receives submissions and serves the admin dashboard
- **Client** — a PyQt6 desktop widget (`client/main.py`) that pops up from the system tray

Both talk to each other over `localhost`. No network configuration is needed.

---

## Step 1 — Confirm the project structure

Before doing anything, verify these files exist in the project root:

```
config.yaml
config.yaml.example
requirements-server.txt
requirements-client.txt
server/app.py
client/main.py
tools/generate_admin_hash.py
shared/constants.py
```

If `config.yaml` is missing (only `config.yaml.example` exists), copy it:

```bash
# Linux / Mac
cp config.yaml.example config.yaml

# Windows
copy config.yaml.example config.yaml
```

---

## Step 2 — Create a virtual environment and install dependencies

Create one venv that covers both server and client:

```bash
# Linux / Mac
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

Install everything:

```bash
pip install -r requirements-server.txt -r requirements-client.txt
```

**Expected result:** No errors. If PyQt6 fails on Linux, install the system Qt libraries first:
```bash
sudo apt install python3-pyqt6 libqt6widgets6   # Ubuntu/Debian
```

---

## Step 3 — Configure for single-machine use

Open `config.yaml` and make exactly these three changes. Do not change anything else.

### 3a — Secret key
Replace the placeholder with any long random string:
```yaml
server:
  secret_key: "demo-secret-key-replace-before-real-use"
```

### 3b — Server URL (localhost)
Change the client server URL from the LAN IP placeholder to localhost:
```yaml
client:
  server_url: "http://127.0.0.1:5000"
```

### 3c — Admin password hash
Run this command and copy the output:
```bash
python tools/generate_admin_hash.py
```
Follow the prompts. Paste the resulting hash into `config.yaml`:
```yaml
admin:
  username: "admin"
  password_hash: "<paste the hash output here>"
```

---

## Step 4 — Create the server data directory

```bash
# Linux / Mac
mkdir -p server/data

# Windows
mkdir server\data
```

---

## Step 5 — Start the server

Open a terminal (or use VS Code's integrated terminal). Make sure the venv is activated, then:

```bash
python server/app.py
```

**Expected output:**
```
 * Running on http://0.0.0.0:5000
 * Debug mode: off
```

Leave this terminal running. Do not close it.

**Verify it works:** Open a browser and go to `http://127.0.0.1:5000/admin` — you should see a login page.

---

## Step 6 — Start the client

Open a **second terminal** (keep the server terminal open). Activate the venv again in this new terminal:

```bash
# Linux / Mac
source venv/bin/activate
python client/main.py

# Windows
venv\Scripts\activate
python client\main.py
```

**Expected result:** A setup wizard appears (first launch only):
1. Welcome screen — click "Get started"
2. PIN screen — create any PIN (min 4 characters), confirm it
3. Department screen — select any department from the list

If the department list is empty, the client cannot reach the server. Check Step 5 is still running and that `config.yaml` has `server_url: "http://127.0.0.1:5000"`.

After setup, the main widget appears in the bottom-right corner of the screen and a tray icon appears in the system tray.

---

## Step 7 — Smoke test the full flow

Run through this sequence to confirm everything works end-to-end:

1. **Log an entry:**
   - In the widget, click a stress level button (1–5)
   - Optionally type a short note
   - Click "Log this moment"
   - The button briefly shows "✓ Logged"

2. **Open the letterbox:**
   - Click "📬 My Letterbox"
   - The entry should appear as a card
   - Try clicking "Edit" — add a reason category, and optionally some personal
     notes in "More detail" (this field is labelled as staying on-device —
     it's for you, not for submission)
   - Click "Save changes"

3. **Submit to the server:**
   - In the letterbox, click "Review & Submit →"
   - A dialog shows exactly what will be sent (department, timestamp, stress
     level, reason, and location if tagged — no names, no identifiers, and
     none of your written notes)
   - Click "Submit selected"
   - You should see a confirmation message

4. **Check the admin dashboard:**
   - In your browser: `http://127.0.0.1:5000/admin`
   - Log in with `admin` and the password you set in Step 3
   - The Overview page should show 1 entry
   - Click "All Entries" in the sidebar — the submitted entry should appear
     with department, stress level, and reason category. Notice there's no
     "notes" column at all — that's deliberate, not a missing feature.

---

## Step 8 — Run the privacy audit (optional, good for presentation)

This runs the anonymisation verification tests that confirm no identifying data was stored:

```bash
pytest tests/test_anonymisation_audit.py -v
```

**Expected result:** All tests pass. If any fail, do not use for a real demonstration until the issue is resolved.

To run the full test suite:
```bash
pytest tests/ -v
```

Note: The full test suite does not require the server to be running — the server tests use their own isolated test database.

---

## Running again after the first launch

The setup wizard only runs once. On subsequent launches:

- **Server:** `python server/app.py` (activate venv first)
- **Client:** `python client/main.py` (activate venv first, second terminal)

The client will ask for your PIN instead of showing the setup wizard.

---

## Troubleshooting

### Client shows "Could not reach server" during department selection
- The server is not running. Start it first (Step 5), then relaunch the client.
- Check `config.yaml` has `server_url: "http://127.0.0.1:5000"` exactly — no trailing slash.

### "Module not found" errors on launch
- The venv is not activated. Run `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows) before running either script.

### Client widget does not appear (Linux)
- PyQt6 requires a desktop session. This will not work over SSH without X forwarding. Run it from a physical desktop session.
- If the tray icon is missing, the widget may still be running — check for a window in the taskbar.

### Admin dashboard login fails
- The password hash in `config.yaml` was not generated correctly. Re-run `python tools/generate_admin_hash.py` and replace the hash.

### To reset the client (forgotten PIN)
```bash
python tools/reset_client.py
```
This clears the PIN without deleting any entries. The client will prompt for a new PIN on next launch.

### To wipe all server data and start fresh
```bash
rm server/data/letterbox.db        # Linux/Mac
del server\data\letterbox.db       # Windows
```
The database is recreated automatically on next server start.

---

## What to show in a presentation

Suggested demo sequence (approx. 5 minutes):

1. **Show the widget** — open it from the tray, walk through the stress level selector and the calm, non-clinical design language
2. **Log two or three entries** — use different stress levels and departments to generate data worth showing
3. **Open the letterbox** — show edit and reason category. Point out that the "More detail" notes field is explicitly labelled as staying on-device — free text never leaves the device, full stop, not even at submission time. Emphasise that nothing else leaves the device either until the user chooses to send it
4. **Show the submit review dialog** — point out that only the anonymised fields are listed; no name, no machine ID, no PIN
5. **Switch to the admin dashboard** — show the overview charts, the All Entries table, the department filter
6. **Run the audit** (if audience is technical) — `pytest tests/test_anonymisation_audit.py -v` in the terminal

---

## Key files for reference during presentation

| File | Purpose |
|------|---------|
| `shared/constants.py` | The exact list of fields that cross the anonymisation boundary |
| `client/api/submit.py` | `_build_payload()` — the sole function that constructs outbound data |
| `server/api/submissions.py` | `_extract_entry()` — server-side field whitelist |
| `docs/privacy-model.md` | Plain-English privacy explanation for stakeholders |
| `tests/test_anonymisation_audit.py` | Runnable privacy verification tests |
