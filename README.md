# Team Leave Scheduler

A small internal tool for a manager to view a team's leave calendar for
the next 30 days, submit leave requests, and approve or reject pending
ones.

See [`DECISIONS.md`](DECISIONS.md) for how the ambiguous business rules
were interpreted, and [`AI_USAGE.md`](AI_USAGE.md) for how AI tools were
used while building this.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, SQLite
- **Frontend:** plain HTML/JS (single file, no build step)
- **Tests:** pytest

## Running it 

### 1. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate  # optional but recommended
pip install -r requirements.txt

# Starts the API on http://localhost:8000
# The database is created and seeded automatically on startup
# (from data/employees.csv and data/public_holidays.json).
python3 -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs are then available at `http://localhost:8000/docs`.

### 2. Frontend

The frontend is a single static file with no build step. With the
backend running, just open it in a browser:

```bash
open frontend/index.html        # macOS
# or: xdg-open frontend/index.html   # Linux
# or just double-click frontend/index.html in a file browser
```

It talks to the API at `http://localhost:8000` by default (see the
`API_BASE` constant near the top of `frontend/index.html` if you need to
point it elsewhere).

### 3. Tests

```bash
cd backend
py -m pytest tests/ -v
```

This includes:
- Unit tests for the 30% team-cap rule (`test_rules.py`)
- Unit tests for the overlap rule (`test_rules.py`)
- Unit tests for weekend/holiday handling (`test_rules.py`)
- End-to-end API tests covering submit / approve / reject / list
  (`test_api.py`)

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/employees` | List all employees |
| `GET` | `/leave-requests?days=30` | List requests overlapping the next N days |
| `POST` | `/leave-requests` | Submit a new leave request |
| `POST` | `/leave-requests/{id}/approve` | Approve a pending request |
| `POST` | `/leave-requests/{id}/reject` | Reject a pending request |

## Seed data

- `backend/data/employees.csv` — 15 employees across Engineering,
  Operations, and Finance (5 each).
- `backend/data/public_holidays.json` — sample public holidays. Dates
  are shifted relative to "today" each time the DB is freshly seeded, so
  the demo always has holidays inside the next 60 days regardless of
  when it's run.

## Explicitly out of scope

Per the brief: no authentication/login, no notifications, no reporting,
no styled UI. Function over form.
