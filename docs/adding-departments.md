# Adding Departments, Reason Categories, and Suggested Solutions

## Departments

Adding a department **never requires code changes**.

### Step 1 — Edit config.yaml

```yaml
departments:
  - id: "operations"
    name: "Operations"
    active: true
  - id: "finance"
    name: "Finance"
    active: true
  - id: "your_new_dept"       # ← Add this block
    name: "Your New Department"
    active: true
```

Rules:
- `id` must be lowercase, no spaces (use underscores). Once assigned and data has been submitted with it, do **not** change the id — it is stored in the database.
- `name` is what users see. You can change the name freely without data loss.
- `active: false` hides the department from new clients but preserves existing data.

### Step 2 — Restart the server

```bash
systemctl restart stress-letterbox
```

Or, if running in development:

```bash
# POST to the reload endpoint (no restart needed)
curl -X POST http://localhost:5000/api/admin/reload-config \
     -b "session=<your-admin-session-cookie>"
```

### Step 3 — Clients update automatically

Clients pull the department list from the server on each launch. No client changes needed.

---

## Reason Categories

Same process as departments — edit `config.yaml` and restart:

```yaml
reason_categories:
  - id: "my_new_reason"
    label: "My New Reason Category"
```

---

## Suggested Solutions

The "What would help?" choices employees can attach to an entry. Same
process — edit `config.yaml` and restart:

```yaml
solution_categories:
  - id: "my_new_solution"
    label: "My New Suggestion"
```

Phrase labels as something that would help ("Clearer priorities"), not as
another complaint. Keep them as fixed choices: this list is shared with the
server, so it should never invite personal detail. Leave the section out
(or empty) and the client simply doesn't offer the option.

Don't reuse an `id` for a different meaning later — existing entries keep
the id they were submitted with.

---

## Privacy note on small departments

The system stores `department` as the only organisational identifier. If a department has only one or two people, submissions from that department could theoretically be re-identified. The admin is responsible for keeping departments at a coarse enough granularity (recommended minimum: 5 people per department). Consider merging small teams into broader groupings.
