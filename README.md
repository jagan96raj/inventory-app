# Inventory & Billing MVP

Monorepo for inventory masters, stock, sales/purchase bills, fulfillment, and payments. Currency display uses **₹ INR** with decimal precision for money and kg.

See [REQUIREMENTS.md](./REQUIREMENTS.md) for the full specification.

## Prerequisites

- Docker Desktop (PostgreSQL)
- Python 3.11+
- Node.js 18+

## Setup

### 1. Environment

```powershell
cd C:\Users\Jagan Raj\Projects\inventory-app
copy .env.example .env
copy frontend\.env.example frontend\.env
```

Set a strong `JWT_SECRET` in `.env` (repo root). For voiding payments, fulfillment, operations, cash book entries, and authorized inventory qty edits, set **`VOID_AUTH_PASSWORD`** (falls back to the logged-in user’s password if unset). Google Sign-In can be added later.

### Database connection pool (v16.0.4)

Pool settings in repo root `.env` (defaults suit 1–5 concurrent users on one backend process):

```env
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
```

Increase `DB_POOL_SIZE` when staff report slow saves under concurrent use on a **single** backend worker. If running **multiple uvicorn workers**, ensure `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × workers` stays below Postgres `max_connections` (default `100` on the Docker image).

`frontend/.env` — leave `VITE_API_URL` **empty** to use the Vite proxy (recommended). After Spec v3+, run:

```powershell
cd backend
alembic upgrade head
```

### 2. Database

```powershell
docker compose up -d
```

Wait until Postgres is healthy on port `5432`.

### 3. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Optional — exact transitive versions (recommended for production / new machines):
# pip install -r requirements.lock
pip check
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Dependency pins (v16.0.14):** `requirements.txt` lists direct runtime deps with `==` pins. `requirements.lock` is a full transitive freeze from the working environment. Do **not** run bare `pip install -U` on production — bump pins deliberately, run `python -m unittest discover -s tests -p "test_*.py"`, then commit.

**Optional security scan (manual, periodic):**

```powershell
pip install pip-audit
pip-audit
```

Seed default bag types (50kg, 30kg, 25kg, Loose):

```powershell
curl -X POST http://localhost:8000/api/seed/bag-types
```

Or from the backend folder:

```powershell
cd backend
python scripts/seed_bag_types.py
```

Or use the **Seed** button on the Bag Types page.

Seed two months of sample bills, payments, and fulfillment (uses existing products, brands, locations, customers). **Dev only** — does not wipe the database; not guarded by v15.7.

```powershell
cd backend
python scripts/seed_sample_data.py
```

Re-run safely (skips existing `DEMO-*` bills). Use `--force` to remove and recreate demo data.

Clear all transactional data (keeps masters and users). **Blocked by default** — see [Destructive scripts (dev only)](#destructive-scripts-dev-only).

```powershell
cd backend
python scripts/clear_transactional_data.py
```

### 4. Frontend

Install **Node.js LTS** from [nodejs.org](https://nodejs.org/) so both `node` and `npm` work in PowerShell (Cursor’s bundled `node` alone does not include `npm`).

```powershell
cd frontend
npm install
npm run dev
```

**If `npm` is not recognized** but `node_modules` exists:

```powershell
cd frontend
.\start-dev.ps1
```

Open http://localhost:5173 — API docs at http://localhost:8000/docs

**If the UI shows "Failed to fetch":**

1. Postgres running: `docker compose up -d`
2. Migrations: `cd backend` → `alembic upgrade head`
3. Backend on port 8000: `uvicorn app.main:app --reload --port 8000`
4. `frontend/.env` has `VITE_API_URL=http://localhost:8000` (CORS allows `http://localhost:5173`)
5. Restart frontend after changing `.env`
6. Open the port Vite prints (default **5173**)

## Project layout

```
inventory-app/
  REQUIREMENTS.md
  docker-compose.yml
  .env.example
  scripts/          Windows backup/restore (v16.0.8)
  backend/          FastAPI + SQLAlchemy + Alembic
  frontend/         React + Vite + TypeScript
```

## Manual test checklist (Spec v4 — Part J)

| # | Test | Expected |
|---|------|----------|
| J1 | Bill 2 lines total ₹40,000; discount 10%; adjustment ₹1,000 off | Final payable **₹35,000** |
| J2 | After submit | `amount_paid=0`, due ₹35,000, payment **unpaid** |
| J3 | One payment ₹10,000 | **partial**, due ₹25,000 |
| J4 | Sales return after partial deliver | HTTP **201**, not 500 |
| J5 | Purchase return after partial deliver | HTTP **201**, not 500 |
| 6 | Sales fulfillment deliver | Stock subtracts; blocked if insufficient |
| 7 | Edit bill qty below fulfilled | Blocked |
| 8 | Bag types seed | 50/30/25 kg + Loose present |
| 9 | Payment modes | Balances per REQUIREMENTS Part H |

## Modules

- **Bills (sales / purchase)** — confirm, edit, void, set-off, fulfillment; **job work custody sales** via `stock_source=job_work` on sales lines (v14.0, **v14.5.1** UX).
- **Fulfillment** — deliver / receive / return, voidable, stock-aware; **audit log** at `/histories/fulfillment` (v14.5.2).
- **Payments** — cash / bank / credit-debit set-off, voidable, with multi-bank picker (Spec v12.21).
- **Inventory** — owner-tagged stock (`owned` | `job_work` per customer); opening qty + fulfillment; summary/detail views and owner filters (**v14.0–v14.2**, **v14.2.1** Detail: Owner→Product grouped rowspan); **0 kg rows hidden by default** with optional chip (v14.5.2); authorized qty edit (v13.2); **inventory rows are never hard-deleted** — clear stock via stock disposal or other operations (v15.2).
- **Operations (v14.1)** — Bag change, product transfer, stock disposal pass stock owner (Owned | Job work + customer); default owned.
- **Job Work orders (v14.0)** — create/view JW orders at `/job-work`; `JW-000001` format; no rates on receive.
- **Job Work fulfillment (v14.0–v14.3)** — receive, return, void receive at `/job-work/fulfillment`; unified **activity log** with Received/Returned badges (`entry_type`); simplified qty columns (Ordered / In custody / Remaining — no gross Received/Returned).
- **Processing jobs (v14.0–v14.9)** — input → output mass-balance; owner-aware input; mixed batches; consolidated powder with **owner-split inventory** (v14.9); batch void (v14.8).
- **Sales job work stock (v14.5.1)** — bill customer + `stock_source=job_work` + rate/kg to sell or charge for custody stock without processing; no Charge type dropdown.
- **Fulfillment audit log (v14.5.2)** — `/histories/fulfillment` — all bill deliver/receive/return events with filters and void.
- **Masters** — products, brands, locations, customers, bag types.
- **Accounts dashboard (v12.21, v13.2)** — `Stat` KPI tiles (3+2 grid); full-width bank table (opening + closing per account); recent cash book entries table; Indian number grouping.
- **Cash Book (v12.21)** — non-bill expense / income / transfer entries with optional `bill_id` link. Canonical use: enter a purchase bill with the supplier portion only (e.g. ₹28/kg) and record the lorry-owner freight separately as a **Cash Book expense linked to that bill** under category **Freight Charges**. Cash balance drops by the freight amount; the bill stays clean and the expense is traceable from the bill detail page.
- **Bank Accounts master (v12.21)** — multiple banks supported; exactly one is the default; list shows opening + closing balance (v13.2).
- **Expense Categories master (v12.21)** — seeded categories (Rent, Wages, Salary, Loan Repayment, EB Bill, Freight Charges, Other Expenses, Self Withdrawal, Capital Increase, Cash ↔ Bank Transfer); system rows are locked.
- **Customer Statement (v12.21)** — per-customer chronological events with running balance (bill create / void, payment / void, setoff).

## Role-based access (v15.0)

- Four roles: **owner**, **writer**, **stock_manager**, **factory_manager** — see `REQUIREMENTS.md` Spec v15.0 matrix.
- Owner manages users at **Administration → Users**.
- Void actions remain owner-only (plus `X-Void-Authorization` password).

## Inventory rows (v15.2)

Inventory stock lines cannot be deleted from the app — not even by the owner. To clear stock, use **Stock disposal** (or bag change, fulfillment, processing, transfers as appropriate). Zero-quantity rows may disappear automatically after operations; that is not a manual delete.

## Master deletes (v15.3)

Deleting products, brands, locations, bag types, or customers requires the **void authorization password** (same as voiding a payment). Staff roles cannot access master delete at all.

## Logout (v15.4)

Logout **invalidates the session on the server** immediately (JWT `jti` blocklist). Safe on shared PCs — after logout you must sign in again; the old cookie cannot access the app.

## How to allow staff (v15.1 signup lockdown)

1. **Once at go-live:** set `ALLOWED_EMAILS=jaganraj@rajagro.com` in `.env` (your owner email) and restart the backend. This blocks strangers from self-signup.
2. **For each staff member:** as **owner**, open **Administration → Users** → create their account and assign a role. **You do not need to edit `.env` again** — login accepts any email that already has an account in the database.
3. Optional: add emails to `ALLOWED_EMAILS` if you want them to self-sign up via the API (the public signup page is hidden).
4. For production, set `REQUIRE_ALLOWED_EMAILS=true` so the backend refuses to start without an allowlist.

Example `.env`:

```env
ALLOWED_EMAILS=jaganraj@rajagro.com
REQUIRE_ALLOWED_EMAILS=true
# Public multi-tenant signup (Spec v17.0.4). Keep false for Raj Agro production.
ALLOW_COMPANY_REGISTRATION=false
```

## Company registration (v17.0.4 — multi-tenant Phase 5)

Creates a **new** company + owner account (`POST /api/companies/register`, UI `/register`). **Separate** from staff invites and from allowlisted `/api/auth/signup`.

- **Raj Agro production:** leave `ALLOW_COMPANY_REGISTRATION=false` (default). Keep `ALLOWED_EMAILS` as above.
- **Local / intentional open signup:** set `ALLOW_COMPANY_REGISTRATION=true`, restart the backend. Login shows “Register your company”; new tenants get empty books and their own settings/counters.
- Do **not** weaken `ALLOWED_EMAILS` when enabling registration — staff at an existing company still join via **Users**.

## Destructive scripts (dev only)

`reset_db.py` and `clear_transactional_data.py` **wipe or clear database data**. They are **blocked by default** (Spec v15.7).

To run them on your **local** machine only:

```env
ALLOW_DESTRUCTIVE_SCRIPTS=true
DESTRUCTIVE_SCRIPT_CONFIRM=I_UNDERSTAND_DELETE_DATA
```

`DATABASE_URL` must point at **localhost** (e.g. docker compose Postgres). **Never** set these on a production server. Prefer [daily backups](#daily-database-backup-windows) and never run wipe scripts against live data.

## Daily database backup (Windows) (v16.0.8)

All business data lives in Docker Postgres.

**In-app (v17.3.19):** Owner → **Profile** → **Download backup** saves `graintrack-YYYY-MM-DD_HHmm.dump` on that device (`GET /api/admin/backup`). Lightsail: dump to `/tmp` inside the Postgres container (`pg_dump -Fc -f`), then `docker compose cp` (stdout `-f -` is empty). There is **no** in-app restore.

**Scheduled scripts (v16.0.8):** Use the repo scripts for automated daily dumps on Windows — still useful as a server-side copy.

### 1. Configure `.env`

```env
BACKUP_DIR=D:\InventoryBackups
BACKUP_RETENTION_DAYS=30
BACKUP_SCHEDULE_TIME=02:00
```

Create `BACKUP_DIR` on a drive with enough space, or point it at a OneDrive/Dropbox-synced folder.

### 2. Run a backup manually

```powershell
cd "C:\Users\Jagan Raj\Projects\inventory-app"
docker compose up -d
.\scripts\backup_db.ps1
```

Expect: `Backup saved: D:\InventoryBackups\inventory-YYYY-MM-DD_HHmm.dump (<size>)`

### 3. Register daily Task Scheduler job (once, as Administrator)

```powershell
# Right-click PowerShell -> Run as administrator
cd "C:\Users\Jagan Raj\Projects\inventory-app"
.\scripts\register_backup_task.ps1
```

Registers **`InventoryApp-DailyBackup`** (default daily at **02:00**). Verify in `taskschd.msc` → Task Scheduler Library.

Test immediately:

```powershell
Start-ScheduledTask -TaskName "InventoryApp-DailyBackup"
```

**Docker Desktop** must be running (or set to start at Windows login) when the task fires.

For overnight backups while logged off, re-run `register_backup_task.ps1 -Password 'YourWindowsPassword'` as Administrator.

### 4. Restore (dev / disaster recovery only)

**Warning:** This **replaces** the current database. Stop the backend first.

```powershell
.\scripts\restore_db.ps1 -BackupFile "D:\InventoryBackups\inventory-2026-06-22_0200.dump"
```

Type `RESTORE` when prompted. Then:

```powershell
cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

See `scripts/restore_db.ps1` and [REQUIREMENTS.md](./REQUIREMENTS.md) Spec v16.0.8 for details.

**Linux footnote:** `docker compose exec -T db pg_dump -U inventory -Fc -f - inventory > backup.dump`

**Production cloud:** When you move to a managed database (RDS, Cloud SQL, etc.), use the provider's automated backups instead of these scripts.

## Bill print & PDF (v16.0.9 / v17.0.5)

Commercial bill layout only — **no GST, HSN, or e-invoice**.

1. Set **company name, address, phone** under **Profile** (`/profile`) as **owner** (synced for bill print). Book Settings keeps cash opening + powder only.
2. Open any sales or purchase bill → **Print** (browser print) or **Download PDF** (`{bill_number}.pdf`).
3. Print view hides sidebar and app chrome; voided bills show a **VOIDED** watermark but remain printable for records.

## Dead code cleanup (v16.0.10)

Removed unused `routers/helpers.py`, dead frontend components (`Icons.tsx`, `pageTheme.ts`, `Drawer`, `ui/Tooltip`), and unreferenced service helpers — no user-facing changes.

## Seed bag types script (v16.0.11)

`backend/scripts/seed_bag_types.py` now matches `POST /api/seed/bag-types` (case-insensitive skip-if-exists). Safe to run repeatedly; does not wipe data.

## API layer consolidation (v16.0.12)

All frontend HTTP calls use `frontend/src/api/client.ts` (`api.get/post/put/delete` with `/api/...` paths). `frontend/src/api.ts` is a thin re-export shim only.

## Processing module split (v16.0.13)

`backend/app/services/processing/` package replaces the monolithic `processing.py`; `app.services.processing` facade preserves the same public API for routers and tests.

## Pinned backend dependencies (v16.0.14)

`backend/requirements.txt` uses `==` pins for all direct deps; `backend/requirements.lock` freezes transitive versions. No API, schema, or business logic changes — reproducible installs only.

## CI (v16.0.15)

![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)

Replace `OWNER/REPO` in the badge URL after pushing to GitHub (e.g. `jaganraj/inventory-app`).

GitHub Actions runs on every **push** and **pull request** to `main` or `master`:

| Job | What it runs |
|-----|----------------|
| `backend-tests` | Python 3.11 — `pip install -r requirements.txt -r requirements.lock` → full `unittest discover` |
| `frontend-build` | Node 18 — `npm ci` → `npm run build` |

Optional audit steps (`pip-audit`, `npm audit --audit-level=high`) are **informational only** (`continue-on-error`) until dependency advisories are cleaned up.

CI uses dummy env only (`JWT_SECRET` for tests) — **never** production `DATABASE_URL` or GitHub secrets. No Docker Postgres, no `reset_db`, no deploy step. CI runs only after code is pushed to GitHub.

**Run the same checks locally before push:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -p "test_*.py"

cd ..\frontend
npm ci
npm run build
```

## Maintenance — idempotency cleanup (v16.0.3)

The `idempotency_records` table stores anti–double-submit guard rows only (not business data). Old rows are pruned automatically on backend startup and at most once per hour during mutation claims.

Env vars (repo root `.env`):

```env
IDEMPOTENCY_RETENTION_DAYS=90
IDEMPOTENCY_STALE_IN_PROGRESS_HOURS=24
```

Optional weekly manual/scheduled cleanup:

```powershell
cd backend
python scripts/cleanup_idempotency.py
```

On Windows, you can schedule the script with Task Scheduler for long-running production deployments.

Reset entire schema (dev):

```powershell
cd backend
python scripts/reset_db.py
```

## How to run migration

```powershell
cd "C:\Users\Jagan Raj\Projects\inventory-app"
docker compose up -d
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
alembic current
```

Expect `044_spec_v1609_bill_print (head)`. Restart the backend after migrating.

## API highlights

- Auth: `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` (cookie session; includes `company_id` — v17.0.0)
- **Multi-tenant Phase 1–5 (v17.0.0–v17.0.4)** + **Profile (v17.0.5):** `companies` table; tenant isolation; per-company settings/counters; flag-gated `POST /api/companies/register`; `GET`/`PATCH /api/companies/me` (owner edits company header); Profile at `/profile`; bill print prefers `companies` (synced `book_settings` company_*).
- Masters: `/api/products`, `/brands`, `/locations`, `/customers`, `/bag-types`, `/api/bank-accounts`, `/api/expense-categories` (auth required)
- Inventory: `/api/inventory` (filters incl. `owner_type`, `customer_id`, `search`), `/api/inventory/stock-at-location`
- Operations: `/api/operations/bag-change|product-transfer|stock-disposal` (optional `owner_type`, `customer_id`; default owned — v14.1); `/api/operations/processing` list is lightweight (v16.0 — no batch lines; detail `/{id}` full fidelity)
- **Form dropdowns (v16.0.22):** Bill, processing, inventory, operations, and job-work forms use hybrid master pickers - async word search plus browse-on-open for first page only (`MASTER_SEARCH_LIMIT=30`) with hint "Showing first N - type to filter". No bulk full-list load on page open.
- Job Work orders: `/api/job-work`, `/api/job-work/{id}`
- Job Work fulfillment: `/api/job-work/fulfillment/orders`, `/api/job-work/receive`, `/api/job-work/return`, `/api/job-work/receipts/{id}/void` (v14.0)
- Job Work statement: `/api/job-work/customers/{id}/statement`
- Bills: `/api/bills?bill_type=sales|purchase`, confirm, edit confirmed, balance preview, `/api/bills/{id}/linked-entries`, `/api/bills/{id}/void-precheck`, `/api/bills/picker`
- Bill fulfillment: `/api/fulfillment`, `/api/fulfillment/bills`, `/api/fulfillment/audit` (v14.5.2)
- Payments: `/api/payments` (with `bank_account_id` when `payment_mode='bank'`)
- Accounts: `/api/accounts/summary`, `/api/accounts/customers`, `/api/accounts/customers/{id}/statement`
- Cash book: `/api/cashbook` (list / create / patch / void)
- Book settings: `/api/book-settings` (cash opening + powder; company header via Profile — v17.0.5)
- Reports: `/api/reports/dashboard-bundle` (v16.0.2 — all dashboard KPI/chart data in one call); individual `/api/reports/business-*`, `by-*`, `bills-export` unchanged
- Audit log (v16.0.5): `GET /api/audit/events` (owner only); UI `/histories/audit` — central trail for voids, edits, master deletes, user admin (not fulfillment deliver/receive)
- Login history (v16.0.6): `GET /api/login-history/events` (owner only); UI `/histories/logins` — sign-in successes and failures (not logout)
- User disable (v16.0.7): `users.is_active`; owner **Disable/Enable** on `/users` (soft ban — blocks login, keeps row for audit); **Delete** still permanent removal
- Bill print & PDF (v16.0.9 / v17.0.5): **Print** / **Download PDF** on bill detail; company header on **Profile** (owner); routes `/sales-bills/:id/print`, `/purchase-bills/:id/print` (no GST / e-invoice)

## Authentication (Spec v10 + v15.1 lockdown + v15.5 rate limit)

1. Set `JWT_SECRET` in `.env` (repo root) to a long random string.
2. Set **`ALLOWED_EMAILS`** to a comma-separated allowlist (required for production). Example: `jaganraj@rajagro.com`
3. Optional: **`REQUIRE_ALLOWED_EMAILS=true`** — backend refuses to start if the allowlist is empty.
4. **Login lockout (v15.5):** after **`LOGIN_MAX_FAILED_ATTEMPTS`** wrong passwords (default **5**), that email is paused for **`LOGIN_LOCKOUT_MINUTES`** (default **15**). Use strong passwords. Lockout expires automatically.
5. **Password policy (v15.6):** new passwords must be **8+ characters** with **uppercase**, **lowercase**, **number**, and **special character** (example: `RajAgro1!`). Applies to signup, owner user create/edit, and OTP password reset. Existing accounts can still log in with old passwords until changed.
6. **Anti double-submit (v15.8):** Save buttons lock while a request is in flight; the server claims each `Idempotency-Key` before creating payments, bills, fulfillment, etc., so double-click or slow-network retries do not duplicate records.
7. **Conditional bill void (v15.9):** Owner can void a clean finalized bill from bill detail; blocked when payments, fulfillment, or linked cash-book entries exist.
8. Run migration: `cd backend` → `alembic upgrade head`
9. Open http://localhost:5173/login to sign in. Public signup is disabled; owner creates staff in **Administration → Users**.
10. Sessions use an httpOnly JWT cookie (`access_token`); all API calls send `credentials: 'include'`.
11. Optional: `VOID_AUTH_PASSWORD` — required (or user login password) when voiding payments, fulfillment, bills, operations, cash book entries, or editing inventory quantities.

Google Sign-In can be added later; `POST /api/auth/google` is already on the backend.

## Void authorization (Spec v13.2)

Destructive actions (payment void, fulfillment void, **bill void (v15.9)**, operation void, cash book void, inventory qty edit, **master delete**) require header **`X-Void-Authorization`** with the value of `VOID_AUTH_PASSWORD` from `.env`, or the current user’s login password if that env var is empty. The UI prompts via **VoidConfirmDialog** on those flows.

## Production — CORS

When staff open the app from a real domain (not `localhost`), the browser only allows API calls if the backend explicitly trusts that website address. Set **`CORS_ORIGINS`** in `.env` (repo root) to the exact URL they type in the browser — scheme, domain, and port, with no trailing slash.

Example:

```env
CORS_ORIGINS=https://inventory.yourdomain.com
```

Multiple frontends (e.g. production + a staging URL) are comma-separated:

```env
CORS_ORIGINS=https://inventory.yourdomain.com,https://staging.yourdomain.com
```

If `CORS_ORIGINS` is empty, the backend uses local dev defaults (`http://localhost:5173` through `5175` and matching `127.0.0.1` URLs). That keeps Vite dev working without extra config. With the recommended Vite proxy (`VITE_API_URL` empty), the browser talks to the same origin as the UI, so CORS is usually not involved locally.

`https` vs `http` and the port must match exactly what appears in the address bar.

## Health checks

- **`GET /health`** — liveness only (API process is running). Does not touch the database. Always expect `200` with `{"status":"ok"}`.
- **`GET /health/ready`** — readiness (API can reach PostgreSQL). Use this for deploy probes and monitoring.

```powershell
curl http://localhost:8000/health/ready
```

When the database is reachable: `200` with `{"status":"ok","database":"ok"}`. When Postgres is down or misconfigured: `503` with `{"status":"degraded","database":"unavailable"}`. If `/health/ready` returns 503, check `docker compose up -d`, `DATABASE_URL` in `.env`, and `alembic upgrade head`.

## Notes

- **Credit balance** = you owe the customer; **debit balance** = they owe you.
- Bill **location is fixed** after creation; pick a new location only on a new bill.
- Inventory changes only via **Inventory** CRUD and **Fulfillment** — never on bill confirm or bill edit.
