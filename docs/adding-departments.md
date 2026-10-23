# Adding Departments, Reason Categories, and Floor Plans

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

## Floor Plans

Floor plans are uploaded through the admin dashboard at `/admin/heatmap`.

1. Navigate to **Floor Plan** in the admin sidebar
2. Expand **Upload / Change Floor Plan**
3. Upload a PNG, JPG, or SVG image
4. The new plan becomes active immediately — existing submissions with coordinates are re-mapped to the new image automatically (coordinates are stored as relative 0–1 percentages, so they remain valid across image changes if the physical layout hasn't changed)

### Multiple floor plans

Currently one floor plan is active at a time. If your organisation has multiple floors, a recommended approach is:
- Use a combined overview image showing all floors
- Or add a `floor_id` field to a future version of the config (the data model supports this via reason_category as a proxy)

---

## Privacy note on small departments

The system stores `department` as the only organisational identifier. If a department has only one or two people, submissions from that department could theoretically be re-identified. The admin is responsible for keeping departments at a coarse enough granularity (recommended minimum: 5 people per department). Consider merging small teams into broader groupings.
