# Privacy Model — Stress Letterbox

**Audience:** HR leads, managers, data protection officers, staff representatives, and any employee who wants to understand how their data is handled before using the system.

**Version:** 1.0  
**Last updated:** See repository history

---

## The core promise

> What you log stays on your device until **you** decide to share it.  
> When you do share it, nothing that goes to the central server can be traced back to you.

This is not a policy promise. It is an architectural guarantee — the system is built so that transmitting your identity is technically impossible, not merely discouraged.

---

## What the system does

Stress Letterbox is a tool for logging moments of workplace stress. It has two parts:

1. **Your device** — A small app where you write notes, rate your stress level, and optionally add context. Everything stays here until you choose to submit it.

2. **The central server** — A server your organisation runs internally. It receives anonymised batches from employees and shows aggregated results to an admin. It has no ability to identify who sent what.

---

## What is stored on your device

Your device stores:

| Field | What it is | Who can see it |
|-------|-----------|----------------|
| Your entries | The notes and ratings you log | Only you (protected by your PIN) |
| Your notes | Your quick-log description *and* any "more detail" you add later | Only you — neither ever leaves your device, under any configuration |
| Your PIN (as a hash) | A scrambled version of your PIN — the original is never stored | Nobody — not even the app itself reads it, it only checks whether a new guess matches |
| Your department | The department you selected on first launch | Only you locally; also sent with submissions (see below) |
| Your session state | Whether you're currently logged in | Only the app |

Your PIN protects all of this. It is stored using bcrypt, a one-way hashing algorithm. If someone took the database file from your computer, they would not be able to recover your PIN from it.

**Your device's database is never sent anywhere.**

---

## What is sent to the server

When you choose to submit, the following fields — and only these fields — are transmitted:

| Field | Example | Notes |
|-------|---------|-------|
| `department` | `"Finance"` | Coarse group label, not your name |
| `timestamp` | `"2024-06-15T10:30:00"` | When you logged the event |
| `stress_level` | `3` | A number from 1 to 5 |
| `reason_category` | `"Workload"` | From the dropdown list, optional |
| `floor_x` / `floor_y` | `0.45, 0.62` | Where you were on the floor plan, optional — **only if your organisation has explicitly turned this feature on**; it ships off by default |

**Nothing else is sent.** Specifically, the following are never transmitted:

- Your name
- Your PIN or any hash of it
- Your computer's name or IP address
- Any account identifier
- **Any free text you write, ever** — neither the quick-log note nor the "more detail" you can add later leaves your device, under any configuration. There is no setting that changes this.
- Any cookie, session token, or device fingerprint

### How this is enforced technically

The application has a single function — `_build_payload()` in `client/api/submit.py` — that constructs the data sent to the server. This function explicitly lists every field by name. It is not possible for extra fields to "slip through" because the function never uses a generic copy or spread operation.

The server has a matching function — `_extract_entry()` in `server/api/submissions.py` — that silently discards any field not in its whitelist, even if a hypothetical modified client tried to send identity data.

These two functions are the **anonymisation boundary**. Any independent developer can verify the privacy guarantee by reading those two functions and the automated tests in `tests/test_anonymisation_audit.py`.

---

## What the server stores

The central server stores only the fields listed in the table above. Its database has no user table, no account table, and no session table. The database schema has been designed so that there is no column for any personal identifier.

An admin with direct access to the database file sees rows like:

```
id | department | timestamp           | stress_level | reason_category | floor_x | floor_y
---|------------|---------------------|--------------|-----------------|---------|--------
1  | Finance    | 2024-06-15 10:30:00 | 3            | Workload        |         |
2  | IT         | 2024-06-15 14:00:00 | 4            | Noise           |         |
3  | Finance    | 2024-06-16 09:15:00 | 2            |                 |         |
```

(The database schema still has an `elaboration` column for historical reasons —
see "Audit and verification" below — but nothing ever writes to it, and no
dashboard view, export, or API response ever reads from it.)

There is no way to determine which employee submitted any of these rows.

---

## Your rights

### The right to delete

You can delete any entry from your local letterbox at any time before you submit it. Deletion is immediate and permanent — the entry is removed from your device's database with no recovery path, no backup, and no server notification. Nothing about a deleted entry ever reaches the central server.

### The right to review before submitting

Before anything is sent to the server, you are shown exactly what will be transmitted. You can deselect individual entries if you don't want to send them. There is no automatic or background submission.

### The right to keep entries indefinitely

Entries stay on your device until you submit them, delete them, or until the organisation's configured retention period elapses (default: 90 days after submission, configurable). Pending entries are never automatically deleted.

### The right to log out

Logging out clears your session from the device but does not delete your entries or your PIN. Your letterbox is protected by your PIN when you're logged out.

---

## Re-identification risk

The system prevents direct identification. However, it cannot prevent *statistical* re-identification in extreme cases:

- **Very small departments** — If a department has only one or two people, any entry from that department can only have come from one of them. For this reason, departments should be configured at a coarse level (minimum recommended: 5 people per department). The system administrator is responsible for this configuration.

- **Combining timestamp and floor location** — If floor location tagging is turned on and you submit an entry with a precise timestamp and floor plan location, and the only person on that floor at that time was you, that combination could theoretically identify you. This is exactly why the feature ships **off by default** (`floorplan.enabled: false` in `config.yaml`) — an organisation has to make a deliberate, informed decision to turn it on.

Free-text re-identification (someone describing a unique situation only they
experienced) is not on this list — it's not a residual risk to manage,
because that text structurally never reaches the server in the first place.

---

## What the admin can and cannot do

**The admin can:**
- See aggregated stress trends by department and time period
- Filter entries by department, stress level, reason category, and date
- Export filtered data as CSV or JSON
- Add or rename departments
- *If the organisation has explicitly turned the feature on* (`floorplan.enabled: true`): see a floor plan heatmap of where entries were located, and upload a floor plan image

**The admin cannot:**
- See who submitted any entry
- See any note you wrote, ever — not the quick-log description, not the "more detail" you add later. Neither is ever transmitted or stored server-side, regardless of configuration.
- Access your device
- Recover a deleted entry
- Create accounts or log in as users (there are no user accounts)
- See floor plan locations unless location tagging has been deliberately enabled (off by default)

---

## What happens if the app is uninstalled

If you uninstall the client application, your local database file in your operating system's app-data folder is not automatically deleted. You may wish to delete it manually. Its location is:

- **Windows:** `%APPDATA%\YourOrg\StressLetterbox\letterbox.db`
- **Linux:** `~/.local/share/StressLetterbox/letterbox.db`

Any entries you submitted before uninstalling remain on the central server in anonymised form.

---

## Audit and verification

The privacy guarantee can be independently verified:

1. **Read the code** — `client/api/submit.py::_build_payload()` and `server/api/submissions.py::_extract_entry()` are the two functions that define what data crosses the boundary. `shared/constants.py::SUBMISSION_FIELDS` is the single canonical list; `server/models/db.py::Entry.to_dict()` is what every dashboard view and export actually reads from, and it deliberately omits the (still-present, never-written-to) `elaboration` database column.

2. **Run the audit tests** — `pytest tests/test_anonymisation_audit.py -v` runs a dedicated suite of tests written to be readable by a non-developer reviewer. Each test has a plain-English explanation of what it checks.

3. **Inspect the database directly** — The server database is a standard SQLite file. Any SQLite browser (e.g. DB Browser for SQLite) can open it and confirm the schema has no identity columns.

---

## Questions

If you have questions about this privacy model, speak to your organisation's IT administrator or data protection officer. The system is open for inspection — any developer your organisation trusts can review the source code.
