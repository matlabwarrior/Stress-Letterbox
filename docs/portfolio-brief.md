# Stress Letterbox

A privacy-first workplace stress logging system: a desktop widget for
employees to anonymously log moments of stress, and a web dashboard for
leadership to see aggregate trends — with no identifying data ever
leaving the employee's device.

## Tags

`Python` `Flask` `PyQt6` `SQLAlchemy` `SQLite` `bcrypt` `Docker` `pytest`
`Chart.js` `Leaflet.js` `Desktop App` `REST API` `Privacy Engineering`

## The problem

Workplace stress surveys are usually annual, anonymous-in-name-only, and
disconnected from the moment stress actually happens. This project is a
lightweight, always-available alternative: a system-tray widget lets someone
log a stress level and a short note in seconds, review and edit it privately
before sending anything, and only then choose to submit — with the app
showing, in plain terms, exactly what will be sent.

## Architecture

Two independent processes, communicating only over a local REST API:

- **Client** (`PyQt6` desktop widget) — runs from the system tray. Entries are
  drafted and stored in a local SQLite database first; nothing is
  transmitted until the user explicitly reviews and submits.
- **Server** (`Flask` + `SQLAlchemy`) — receives submissions and serves an
  admin dashboard: overview charts, a filterable entries table, CSV/JSON
  export, and an optional floor-plan heatmap (off by default — see below).

Both are designed to run on one machine for demos, or split across a
LAN/Docker deployment for real use.

## Privacy engineering (the interesting part)

The core design constraint: **the server should be structurally incapable of
storing who submitted an entry.**

- A single whitelist of 6 fields (`department`, `timestamp`, `stress_level`,
  `reason_category`, `floor_x`, `floor_y`) is the *only* data that can cross
  the client → server boundary. It's enforced twice, independently: once
  when the client builds the outbound payload, once again when the server
  parses an inbound request — so a bug in one layer doesn't silently become
  a data leak.
- **No free text ever crosses that boundary, full stop.** Both notes fields
  (the quick-log description and the letterbox's "more detail") stay on the
  device under every configuration — there's no setting that changes this,
  because free text is exactly what can re-identify someone or get read out
  of context by whoever has dashboard access.
- Location tagging (`floor_x`/`floor_y`) ships **off by default** — an admin
  has to deliberately opt in, since combining a precise timestamp with a
  floor location is its own re-identification vector.
- The server's database schema has no user table, no session table, no
  device identifier column — there is nothing to re-identify, even in a
  breach.
- The PIN that protects the local widget is bcrypt-hashed and never leaves
  the device — it protects the letterbox from a shoulder-surfing colleague,
  not from the server.
- All of this is continuously checked by an automated 3-layer privacy audit
  (payload construction → server-side filtering → database schema) as part
  of an 88-test automated suite, runnable with a single command.

## Key features

- System-tray widget: pick a stress level, add an optional note, done in
  seconds — the note stays on the device, always
- A private "letterbox" to review, edit, or delete entries before anything
  is sent
- An explicit review-and-submit step that shows exactly what will leave the
  device
- Admin dashboard: trends over time, breakdown by department/reason,
  CSV/JSON export
- Floor-plan heatmap, off by default — an admin can opt in if their
  organisation decides the tradeoff is worth it
- Configurable departments and reason categories, no code changes needed

## Tech stack detail

| Layer | Technologies |
|---|---|
| Server | Python, Flask, Jinja2, SQLAlchemy 2 (ORM), SQLite, bcrypt, PyYAML |
| Dashboard frontend | Vanilla JS (fetch API), Chart.js, Leaflet.js + Leaflet.heat, hand-written CSS |
| Desktop client | PyQt6, pystray, Pillow, requests, bcrypt, SQLite (stdlib) |
| Testing | pytest — 88 tests across unit, integration, and privacy-audit suites |
| Deployment | Docker, Docker Compose |

## Demo-ready

Runs entirely locally in under five minutes: start the Flask server, launch
the PyQt6 client, log a couple of entries, and watch them appear — fully
anonymised — on the admin dashboard. The privacy audit
(`pytest tests/test_anonymisation_audit.py -v`) is a good live demo moment
for a technical audience: it runs in under 3 seconds and gives a concrete,
verifiable answer to "how do you know this is actually anonymous?"
