# Manual test plan

**Project:** `C:\Users\Jagan Raj\Projects\inventory-app`  
**Last updated:** 08 Jul 2026 — covers Spec v5.4 through **v16.0.22**; backend v12.21 + v12.22  
**Full spec:** `REQUIREMENTS.md` · Desktop: `inventory-app-SPEC.md.txt` · Local: `C:\Users\Jagan Raj\inventory-app-SPEC.md.txt`

## v16.0.22 — Hybrid master picker (browse + word search)

1. **Typing filters results** — Type text in a master picker and pause; results load after debounce and match the query.
2. **Empty input browse** — Open dropdown with empty input; it shows first page only (<= MASTER_SEARCH_LIMIT).
3. **Hint text** — Dropdown shows `Showing first N — type to filter`.
4. **Browse then type** — After browse list appears, typing narrows results to matching options.
5. **No heavy dump** — Form open does not trigger bulk master payload spikes.

## v16.0.21 — Default page size 25

1. **Bills / inventory / payments** — With 26+ rows, page 1 shows 25; **Next** loads rows 26+.
2. **API default** — Omit `limit` on a list endpoint → response `limit` is **25**.
3. **Inventory product split** — If same product has many brand/bag rows that cross the 25-row boundary, first page ends mid-product and next page continues those remaining rows (by design).

## v16.0.20 — Fulfillment dialog layout + bill edit save fix

1. **Sales deliver dialog layout** — Open Deliver on a sales bill line: **Billed from this location** banner stays at top; below it, **Product/context** and **Delivery details** show side-by-side on wide screens.
2. **Purchase receive dialog layout** — Open Receive on a purchase line: context and receive form appear side-by-side on wide screens; stacked on mobile/smaller widths.
3. **Quantity stat rendering** — In context cards, values like `10 bags` or `1250.000 kg` stay on one line (no split word wrapping).
4. **Bill edit save** — Edit a finalized bill (discount/adjustment), click Save changes; request succeeds and no `idempotencyHeaders is not defined` runtime error appears.

## v16.0.19 — Backdated transaction dates

1. **Record payment** — Date field defaults to today; set a past date → payment `paid_at` reflects that date.
2. **Bill fulfillment** (deliver/return dialog) — Date field; past date allowed.
3. **Cash book new entry** — Entry date editable on create; read-only on edit.
4. **Job work receive/return** — Date field on action dialog.
5. **Future date** — UI blocks with `max=today`; API returns 422.
6. **Past date** — password dialog on save; API returns 403 without `X-Void-Authorization`.

## v16.0.18 — Processing input: no JW order picker

**Processing job → Input tab:**

1. **Job work line** — Select Stock owner **Job work (customer)** → pick customer → location/bag/qty. **No** “Job work order” / `JW-000001` dropdown.
2. **Stock filter** — Available stock still scoped to that customer's job_work custody at the location (same as before without picking an order).
3. **Submit** — Input batch saves; snapshot panel (Fresh in, mass balance) unchanged.

## v16.0.16 — Running remaining stock per line (multi-line bill & processing UX)

**Sales bill create** (`/sales-bills/new`):

1. Pick customer + location with **100 bags** of one product (e.g. Bajra) in owned stock.
2. Line 1: same product/brand/bag, **50 bags** → hint shows **100 bags** remaining (full stock for line 1).
3. Add line 2: same product/brand/bag/stock source, **50 bags** → hint shows **50 bags** remaining (100 minus line 1).
4. Line 2 at **60 bags** → exceed warning; submit blocked.
5. Two lines same product at **50 + 50** → bill **creates successfully** (no duplicate-line error).

**Purchase bill create** (`/purchase-bills/new`):

6. Two lines with same product/brand/bag → **duplicate-line error** (unchanged).

**Processing job input tab:**

7. Two input lines same location/bag/owner → line 1 shows full available; line 2 shows **Remaining (after earlier lines)** reduced by line 1 qty.
8. Submit validation still blocks when combined qty exceeds stock.

**Backend:** `tests/test_bill_running_stock_v16016.py` — sales duplicate lines OK; purchase duplicate 400.

## v16.0.15 — CI pipeline (go-live drawback #38)

1. **Push branch** — GitHub Actions `CI` workflow runs on push/PR to `main` or `master`.
2. **`backend-tests` job** — Full `python -m unittest discover -s tests -p "test_*.py"` passes (SQLite/mocks; no Docker Postgres required).
3. **`frontend-build` job** — `npm ci` + `npm run build` (`vite build`) succeeds.
4. **Local parity** — Same commands pass on dev machine before push.
5. **No production secrets** — Workflow does not reference production `.env` or `DATABASE_URL` from GitHub secrets; dummy `JWT_SECRET` only.

### v16.0.15.1 — Backend test suite green (CI prerequisite)

Amended tests/helpers only (no production logic changes): signup lockdown mocks (`LoginRateLimit` vs `User` scalar routing, `is_active=True`); RBAC owner user on bill API tests; processing mocks (`output_allocation_mode`, `processing_test_helpers.py`); inventory prune-zero row assertions; idempotency concurrent claim uses temp-file SQLite + `NullPool`. Full suite: `python -m unittest discover -s tests -p "test_*.py"` → 464 tests OK.

## v16.0.14 — Pin backend dependencies (go-live drawback #37)

1. **Fresh venv** — `cd backend` → `python -m venv .venv` → activate → `pip install -r requirements.txt` succeeds.
2. **pip check** — No broken dependencies after install.
3. **Backend tests** — `python -m unittest discover -s tests -p "test_*.py"` passes (or project-equivalent subset).
4. **App starts** — `uvicorn app.main:app --port 8000`; smoke: login → dashboard loads; `GET /health/ready` returns OK.
5. **Optional** — `pip-audit` documented in README (run manually; no CI required).

## v16.0.13 — Split processing.py monolith (go-live drawback #36)

1. **Imports unchanged** — `from app.services.processing import submit_batch, create_job, …` still works.
2. **Mixed input (v14.6.1)** — `tests.test_processing_v1461_input_allocation` passes.
3. **Powder** — `tests.test_processing_v147_consolidated_powder` passes.
4. **Batch void** — `tests.test_processing_void_v148` passes.
5. **Owner split / list** — `tests.test_processing_v145_owner_mode`, `test_processing_v1442_owner_split`, `test_processing_list_v160` pass.
6. **No migration** — `alembic current` unchanged.

## v16.0.12 — Consolidate duplicate API layer (go-live drawback #35)

1. **Masters** — Products, brands, locations, customers, bag types: list/add/edit/delete still work.
2. **Inventory** — List, add stock, edit quantity (void auth) unchanged.
3. **Formatting** — Customer credit/debit columns use locale INR (`formatInr`).
4. **Build** — `npm run build` passes; no `../api` legacy fetch imports remain in `src/`.

## v16.0.11 — Fix seed_bag_types.py (go-live drawback #34)

1. **CLI script** — `cd backend` → `python scripts/seed_bag_types.py` completes without `ImportError`.
2. **Idempotent** — Second run skips all four bag types (50kg, 30kg, 25kg, Loose).
3. **API unchanged** — `POST /api/seed/bag-types` still creates missing types only; case-insensitive name match.
4. **Automated** — `python -m unittest tests.test_seed_bag_types_v1611`.

## v16.0.10 — Dead code cleanup (go-live drawback #33)

1. **No behavior change** — App loads; bills, processing list, dashboard charts unchanged.
2. **Removed files** — Confirm deleted paths are gone; grep shows no broken imports.
3. **Automated** — `python -m unittest discover -s tests` (backend); `npm run build` (frontend).

## v16.0.9 — Bill print & PDF

1. **Company header** — Accounts → Book settings → set company name, address, phone → Save.
2. **Print** — Open a sales or purchase bill → **Print** → clean layout, no sidebar; browser print dialog.
3. **Download PDF** — **Download PDF** → saves `{bill_number}.pdf` (client-side).
4. **Voided bill** — VOIDED watermark visible; print still works for records.
5. **Customer address** — Bill print shows customer address/phone from customer master.
6. **Automated** — `python -m unittest tests.test_bill_print_v1609`.
7. **Migration** — `alembic upgrade head` (044); restart backend.

## v16.0.8 — Scheduled PostgreSQL backup (go-live drawback #30)

1. **Manual backup** — `docker compose up -d` → `.\scripts\backup_db.ps1` → `.dump` file in `BACKUP_DIR` with size log line.
2. **Retention** — Old `*.dump` files beyond `BACKUP_RETENTION_DAYS` removed on next run.
3. **Scheduled task** — Run `.\scripts\register_backup_task.ps1` as Administrator → `InventoryApp-DailyBackup` in Task Scheduler.
4. **Verify schedule** — `Start-ScheduledTask -TaskName 'InventoryApp-DailyBackup'` or wait until next 02:00; new file appears.
5. **Restore (dev only)** — Stop backend → `.\scripts\restore_db.ps1 -BackupFile <path>` → type `RESTORE` → verify data; run `alembic upgrade head` if needed.
6. **Errors** — Clear message if Docker/db not running.

## v16.0.7 — Disable user (soft ban) (go-live drawback #29)

1. **Disable** — Owner disables a writer on Users page → badge shows Disabled; writer cannot log in (403).
2. **Session kill** — Disabled user's existing session → next API call returns 401.
3. **Re-enable** — Owner enables user → login works again.
4. **Guards** — Cannot disable self or last owner (400).
5. **Delete unchanged** — Permanent removal still via Delete (separate from Disable).
6. **Automated** — `python -m unittest tests.test_user_disable_v1607 tests.test_auth_v10`.
7. **Migration** — `alembic upgrade head` (043); restart backend.

## v16.0.6 — Login history (go-live drawback #28)

1. **Owner access** — Sign in as owner → History → Login history loads; writer gets 403 on `/api/login-history/events`.
2. **Login creates row** — Successful login → success row with email; wrong password → failed row with `invalid_credentials`.
3. **Filters** — Filter by success/fail and date range; search by email.
4. **Audit log unchanged** — Business voids/edits still only on `/histories/audit`.
5. **Automated** — `python -m unittest tests.test_login_history_v1606 tests.test_auth_v10`.
6. **Migration** — `alembic upgrade head` (042); restart backend.

## v16.0.5 — Central audit log (go-live drawback #27)

1. **Owner access** — Sign in as owner → History → Audit log loads; writer gets 403 on `/api/audit/events`.
2. **Void creates row** — Void a payment or bill → new row with user email, action, entity label.
3. **Filters** — Filter by action (e.g. `bill_voided`) and date range; search by bill number in label.
4. **Fulfillment audit unchanged** — Deliver/receive events still only on `/histories/fulfillment`.
5. **Automated** — `python -m unittest tests.test_audit_log_v1605`.
6. **Migration** — `alembic upgrade head` (041); restart backend.

## v16.0.4 — Database connection pool tuning (go-live drawback #26)

1. **App starts** — Backend logs database pool settings on startup (`pool_size`, `max_overflow`, `max_connections`).
2. **Readiness** — `GET /health/ready` returns `200` with `database: ok` when Postgres is up.
3. **Normal ops** — Save a bill or payment; no connection-pool-related errors under normal use.
4. **Env override (optional)** — Set `DB_POOL_SIZE=8` in `.env`, restart backend, confirm startup log reflects new value.
5. **Automated** — `python -m unittest tests.test_database_pool_v1604`.
6. **No migration** — restart backend only.

## v16.0.3 — Idempotency retention cleanup (go-live drawback #25)

1. **Save still works** — Create a bill or payment with Save; confirm normal submit and idempotent replay (double-click / retry same key) within retention window.
2. **No UI change** — No new screens or settings; cleanup is backend-only.
3. **Dev prune check** — In dev DB, backdate a `completed` idempotency row `created_at` past 90 days → restart backend or run `python scripts/cleanup_idempotency.py` → row removed.
4. **Stuck in_progress** — Backdate an `in_progress` row past 24 hours → cleanup removes it; new submit with fresh key succeeds.
5. **Automated** — `python -m unittest tests.test_idempotency_cleanup_v1603 tests.test_idempotency_atomic_v158`.
6. **No migration** — restart backend only.

## v16.0.2 — Dashboard bundle API (go-live drawback #24)

1. **Single network call** — Open Dashboard → DevTools Network shows one `dashboard-bundle` request (not six separate report calls).
2. **KPIs unchanged** — Sales/purchase bill amount, qty ordered, MoM compare strip match prior behavior.
3. **Charts unchanged** — Daily area chart, product mix donut, top customer/location tables render as before.
4. **Month toggle** — Change month → one new `dashboard-bundle` call; data refreshes correctly.
5. **Bill type / group by** — Toggle sales vs purchase or product vs product+brand → bundle refetches; summary/compare/daily unchanged for same month.
6. **CSV export** — Download bills CSV still uses `GET /api/reports/bills-export` (unchanged).
7. **Automated** — `python -m unittest tests.test_dashboard_bundle_v1602 tests.test_reports_v111`.
8. **No migration** — restart backend; refresh frontend.

## v16.0.1 — Async master search on heavy forms (go-live drawback #23)

1. **Bill form opens fast** — New sales/purchase bill: Network tab shows no `limit=500` master list calls on page load.
2. **Customer search** — Type customer name in header → results appear; select and continue.
3. **Purchase line masters** — Product/brand/bag type lines use type-to-search (purchase bills).
4. **Sales stock lines** — Product/brand/bag still from location stock (unchanged cascade).
5. **Processing job** — Open job page: no bulk location/brand/customer fetch; search pickers work on input/output tabs.
6. **Inventory filters** — Filter bar comboboxes search on type; page load does not fetch 500×5 masters.
7. **Edit bill customer** — Edit finalized bill still shows customer name read-only from bill record.
8. **Book settings** — Powder destination fields show saved names; search to change.
9. **Automated** — `python -m unittest tests.test_master_search_v1601`.
10. **No migration** — restart backend; refresh frontend.

## v16.0 — Processing job list performance (go-live drawback #22)

1. **Open jobs list** — `/operations/processing` loads quickly; rows show product, brand, opened date (no batch line payloads in network tab).
2. **History list** — `/histories/processing` shows batch count and output kg for completed jobs; values match job detail summary.
3. **Detail unchanged** — Open a completed job → full batches, input/output lines, owner mode, allocation hints still present.
4. **Voided batches** — Void a batch on a completed job → list `batch_count` and output kg exclude voided batch.
5. **Automated** — `python -m unittest tests.test_processing_list_v160 tests.test_processing_list_status`.
6. **No migration** — restart backend only.

## v15.9 — Conditional bill void (go-live drawback #19)

1. **Clean bill void** — Finalize a purchase or sales bill with no payments, fulfillment, or linked cash-book entries → **Void bill** on detail page (owner) → confirm with void password → bill shows **Voided** badge; disappears from bill list; customer balance reversed.
2. **Block: payment** — Record a payment on a bill → void-precheck `can_void=false`; POST void returns **409** “active payments exist”.
3. **Block: fulfillment** — Deliver/receive on a line → void-precheck blocks; POST void returns **409** “fulfillment activity exists”.
4. **Block: linked cash-book** — Add freight expense linked to bill → void-precheck `linked_active_entries_count > 0` and `can_void=false`; POST void returns **409** “linked cash-book entries exist”.
5. **Auth required** — POST void without `X-Void-Authorization` → **403**.
6. **Voided bill read-only** — Edit, Record payment, and fulfillment/payment void actions disabled on voided bill detail.
7. **Customer statement** — After void, statement shows `bill_voided` event reversing the original bill balance.
8. **Automated** — `python -m unittest tests.test_bill_void_v159 tests.test_accounts_v1221.BillLinkedEndpointsTests`.
9. **Migration** — `alembic upgrade head` → `040_spec_v159_bill_void`; restart backend.

## v15.8 — Atomic idempotency / anti double-submit

1. **Double-click payment** — Open Record payment on a bill; enter amount; **double-click Submit** quickly → only **one** payment in Payments list / bill paid amount.
2. **Slow retry** — Throttle network (DevTools) or click Save twice on fulfillment / bill submit → one record; second response is cached replay or blocked while in progress.
3. **Button locked** — While saving, primary button shows **Saving…** and is disabled.
4. **Failure retry** — Submit with validation error (e.g. overpay) → fix and Save again with same form → succeeds (idempotency key reused until success).
5. **Automated** — `python -m unittest tests.test_idempotency_atomic_v158 tests.test_idempotency_v1215`.
6. **Migration** — `alembic upgrade head` → `039_spec_v158_idempotency_atomic`; restart backend.

## v15.7 — Destructive scripts locked

1. **Blocked by default** — `cd backend` → `python scripts/reset_db.py` without env flags → exits **1** with "destructive scripts disabled" message (no DB change).
2. **Clear transactional blocked** — Same for `python scripts/clear_transactional_data.py`.
3. **Local dev unlock** — In `.env` only on dev machine: `ALLOW_DESTRUCTIVE_SCRIPTS=true` and `DESTRUCTIVE_SCRIPT_CONFIRM=I_UNDERSTAND_DELETE_DATA`, `DATABASE_URL` pointing at `localhost` → scripts proceed.
4. **Never on production** — Do not set allow flag on live server `.env`.
5. **Automated** — `python -m unittest tests.test_destructive_scripts_guard_v157`.

## v15.6 — Strong password policy

1. **Weak password rejected** — Administration → Users → Create user with `NoSpecial1` → error (400 / banner) mentioning special character.
2. **Strong password accepted** — Create user with `RajAgro1!` → success.
3. **Edit user password** — Patch with weak password rejected; `Test@123` accepted.
4. **Existing login unchanged** — User with old weak password (created before policy) can still sign in.
5. **OTP new password** — Login with OTP + weak new password rejected; strong password accepted.
6. **Automated** — `python -m unittest tests.test_password_policy_v156 tests.test_auth_v10 tests.test_login_otp_v151`.

## v15.5 — Login rate limit

1. **Wrong passwords** — Enter wrong password **5 times** for the same email → 6th attempt shows blocked message (429 / friendly banner on login page).
2. **Wait or succeed** — Wait **15 minutes** OR sign in with the **correct password before lock** (counter clears on success).
3. **Different email** — Another user/email can still log in while one is locked.
4. **Allowlist** — Unauthorized email (403) does not trigger lockout counter.
5. **Automated** — `python -m unittest tests.test_login_rate_limit_v155 tests.test_auth_v10`.
6. **Migration** — `alembic upgrade head` → `038_spec_v155_login_rate_limit`; restart backend.

## v15.4 — Logout revokes session immediately

1. **Login** — Sign in; confirm dashboard loads.
2. **Logout** — Click Logout; redirected to login.
3. **Replay blocked** — Browser back or replay old API call with saved cookie → **401** / login required.
4. **Login again** — Fresh login works.
5. **Two users** — User A logs out; User B session still works (separate browsers or incognito).
6. **Automated** — `python -m unittest tests.test_logout_revoke_v154 tests.test_auth_v10`.
7. **Migration** — `alembic upgrade head` → `036_spec_v154_logout_revoke`; restart backend.

## v15.3 — Master delete void authorization

1. **Owner without void password** — On **Brands** (or Products / Customers / Locations / Bag types), delete an unused row without entering void password → **403** `Authorization password required to void`.
2. **Owner with void password** — Same unused row, enter `VOID_AUTH_PASSWORD` (or login password) in delete dialog → delete succeeds.
3. **Referenced master blocked** — Customer with bills: void password accepted but **400** with reference message (v12.2 guard unchanged).
4. **Staff cannot delete** — Writer / stock manager have no masters pages; direct `DELETE` as writer → **403** permission.
5. **Automated** — `python -m unittest tests.test_masters_delete_void_v153 tests.test_master_delete_v122`.

## v15.2 — No inventory row hard-delete

1. **Owner cannot delete row** — On **Inventory**, there is no Delete button. `DELETE /api/inventory/{id}` as owner → **403** `Inventory rows cannot be deleted. Use stock disposal or other operations.`
2. **Clear stock via disposal** — Create stock on hand; use **Operations → Stock disposal** to remove all bags → row disappears (auto-prune at zero kg). Row was not hard-deleted via inventory API.
3. **Opening stock unchanged** — Owner **Add stock** on Inventory still works (`POST /api/inventory`).
4. **Emergency qty edit unchanged** — Owner edit with void password still works (`PUT /api/inventory/{id}`).
5. **Automated** — `python -m unittest tests.test_inventory_v152_no_delete tests.test_inventory_v121 tests.test_operations_v141`.

## v15.1 — Signup lockdown

1. **`.env` allowlist** — Set `ALLOWED_EMAILS=jaganraj@rajagro.com` (comma-separate for more); restart backend.
2. **Blocked signup** — `POST /api/auth/signup` with `other@gmail.com` → **403** `Email not authorized`.
3. **Blocked login** — Existing user not on list → **403** on login (before password check).
4. **Allowlisted login** — `jaganraj@rajagro.com` can sign up (if new) and log in.
5. **Case insensitive** — `JaganRaj@RajAgro.com` matches allowlist.
6. **Login UI** — No **Create an account** link; footer says contact owner. `/signup` → `/login`.
7. **Staff flow** — Add email to `ALLOWED_EMAILS` + create user in **Users** page with role; staff logs in.
8. **Dev warning** — Empty `ALLOWED_EMAILS` → backend startup WARNING in logs.
9. **Production guard** — `REQUIRE_ALLOWED_EMAILS=true` with empty list → backend refuses to start.
10. **Automated** — `python -m unittest tests.test_signup_lockdown_v151 tests.test_auth_v10`.

## v15.0 — Role-based access control (RBAC)

1. **Migration** — `alembic upgrade head` → `033_spec_v150_rbac`; `jaganraj@rajagro.com` has role **owner**.
2. **Owner** — Full sidebar; **Administration → Users** lists users; create user with role; assign role to existing user.
3. **Unassigned user** — Sign up / login → **Pending access** screen; `GET /api/inventory` → 403.
4. **Writer** — Dashboard, inventory view, bill fulfillment, JW fulfillment, product transfer; no bills/payments/masters/void buttons.
5. **Stock manager** — Inventory view, bag change, stock disposal; no opening stock or direct qty edit.
6. **Factory manager** — Processing jobs + inventory view + book settings read-only; no bills.
7. **Void owner-only** — Non-owner calling void endpoint → 403 before password check.
8. **403 toast** — Trigger forbidden action from UI → error toast with API message.

## v15.5.1 — Powder stock line per batch + dashboard party tables

1. **Processing job page loads** — Open an in-progress or completed job (`/operations/processing/:id`) → page renders (no blank screen).
2. **Powder stock on Waste tab** — Enter brand **Powder**, storage location, bag type, **15 kg** loose; submit waste batch → inventory at that location +15 kg; Summary shows **Powder stock** tile and storage location (separate from dust/stone/sack).
3. **Audit waste unchanged** — Dust/stone/sack on same batch → no inventory rows for those; **Waste split by owner** excludes powder.
4. **Reject Powder output** — Powder as output brand line → error (use Waste tab).
5. **Dashboard tables** — Accounts dashboard: **Top customers** and **Sales by location** rows single-line; long names truncate with tooltip; numbers do not wrap or overlap columns.
6. **Legacy API** — `powder_kg` + book settings destination still works (`test_processing_v147_consolidated_powder.py`).
7. **Migration** — `alembic upgrade head` → `037_processing_powder_line`; restart backend.

## v14.7 — Consolidated processing powder

> **UI superseded by v15.5.1** — day-to-day: use Waste tab **Powder stock** (brand, location, bag type, qty). Book settings powder block is optional legacy.

1. **Masters** — Product **Powder** and brand **Powder** exist.
2. **Per-batch powder (v15.5.1)** — Waste tab **Powder stock**: pick location + 15 kg → inventory at that location; Summary waste includes powder; Output by brand has no Powder.
3. **Legacy book settings** — Optional: Accounts → Book settings powder destination; API `powder_kg` only → posts to configured tuple (`test_processing_v147_consolidated_powder.py`).
4. **Reject Powder output line** — Try Powder as output brand → error: enter in Waste section.
5. **Dust/stone/sack** — Same batch → no inventory rows for those.
6. **Mixed-owner job** — Owned + job_work input; 10 kg powder → split by owner proportion (owned + job_work inventory rows).

## v14.6.1 — Mixed processing allocation on input batch

> **Supersedes v14.6 output-tab steps** — allocation UI is on the Input tab when the batch creates a mix.

1. **Path A mixed job** — Input owned + job_work in one batch → Input tab shows **Output allocation** section before submit.
2. **Proportional** — Choose **Split by input proportion** on mixed-creating input → further input rejected; output splits by mix (~81/22 on 103 bags for 85+23 input).
3. **Single owner default** — **Single owner 100%** without changing dropdown → defaults to highest input kg (usually Owned); all output rows owned.
4. **More owned input** — Single owner Owned + add 50 more owned bags → allowed; +10 JW → error.
5. **Path B** — Batch 1 owned → Batch 2 JW with single-owner JW allocation → +more JW OK; +owned rejected.
6. **Output tab** — No allocation UI; output-only batch works without allocation fields when mode set.
7. **Lock** — Cannot change allocation mode after mixed input saved (error on output submit with conflicting body).
8. **Waste** — Single-owner mode: dust/stone/waste kg posts 100% to chosen owner.
9. **Single-owner job** — Only owned input → no allocation UI; output 100% owned (unchanged v14.5).
10. **Summary** — Shows `output_allocation_hint` and `input_rules_hint` (proportional closed vs single-owner open).

## v14.6 — Mixed processing output allocation

> **Superseded by v14.6.1** — steps below referred to Output tab; use v14.6.1 checklist instead.

1. **New mixed job** — Input owned + job_work (one batch) → Output tab shows **Output allocation** section.
2. **Proportional default** — **Use proportion** selected; first output batch splits bags/kg by input mix (e.g. 85 owned + 23 JW → ~81/22 on 103 bags).
3. **Single owner default** — Choose **Single owner 100%** without changing dropdown → defaults to highest input kg (usually Owned); all output rows owned.
4. **Override JW** — Single owner + select job_work customer → 100% to that custody row; confirm dialog mentions manual billing.
5. **Lock** — After first output with proportional, second output cannot switch to single owner (error).
6. **Waste** — Single-owner mode: dust/stone/waste kg posts 100% to chosen owner.
7. **Single-owner job** — Only owned input → no allocation UI; output 100% owned (unchanged v14.5).
8. **Summary** — After lock, Summary shows `output_allocation_hint` (proportional % or 100% owner).
9. **Migration** — `alembic upgrade head` (028); restart backend.

## v14.5.2 — Fulfillment audit log + inventory UX

1. **Audit log page** — `/histories/fulfillment` lists deliver/receive/return events newest first with bill, customer, product, qty, location.
2. **Filters** — Bill type (sales/purchase), event (deliver/return), status (active/voided), bill number search work.
3. **Event labels** — Sales deliver shows **Deliver**; purchase deliver shows **Receive**; returns show **Return**.
4. **Void from audit** — Void active entry with password; stock reverses; row shows voided.
5. **JW deliver stock** — Sales bill line `stock_source=job_work` → Fulfillment deliver dialog shows correct custody bags (not 0).
6. **Inventory Actions header** — Single line, aligned with edit button column.
7. **Zero kg rows** — 0 kg inventory rows hidden by default; **Zero kg rows** chip shows them; Clear filters hides again.
8. **No migration** — Restart backend; refresh frontend.

## v14.5.1 — Sales bill job work stock + 2-decimal display

1. **Job work product list** — Sales bill: customer = JW custody owner (e.g. Raghavendra), location with JW stock → Stock source **Job work** → product/brand/bag dropdowns populate (Bajra, Jowar, etc.).
2. **Wrong customer** — Bill customer ≠ custody owner → empty product list + message naming which customer has stock at that location.
3. **No Charge type field** — Only Stock source + rate/kg; bill saves with auto `line_charge_type`.
4. **Deliver JW line** — Fulfillment subtracts correct `job_work` inventory row for bill customer.
5. **Owned regression** — Stock source Owned still shows owned stock only.
6. **2 decimal places** — Processing job and qty displays show `.00` precision (e.g. 76.27% not 76.3).
7. **No migration** — Refresh frontend; optional backend restart for `stock-at-location` filters.

## v14.5 — Processing owner-mode input lock

1. **Mixed batch 1** — Input 85 owned + 23 JW in one batch → output batch splits correctly → **second input batch rejected** with clear message.
2. **Same-owner cumulative** — Batch 1 owned → Batch 2 more owned → output 100% owned inventory.
3. **Single-owner exception** — Batch 1 owned → **no output** → Batch 2 JW only → job becomes mixed → Batch 3 input rejected → output splits by combined kg.
4. **Output before different owner** — Batch 1 owned → output batch → Batch 2 JW input → **400** / error message.
5. **Second batch mixed in one submit** — Batch 1 owned → Batch 2 with owned + JW lines together → **400** (mixed only on first input batch).
6. **Input tab UI** — When `input_locked`, input form hidden/disabled; output tab still works.
7. **Single-owner + output** — Owner selector locked to current owner on input tab; banner shows locked message.
8. **Banners** — `input_rules_hint` shows mixed split % or single-owner guidance on input/output tabs.
9. **External mixed** — Still rejected (regression).
10. **Separate input/output batches** — v14.4.1 workflow still splits correctly (regression).
11. **No migration** — Logic-only; restart backend; test on **new** job.

## v14.4.2 — job_work owner detection + multi-owner split

1. **Two-owner output Summary** — New job: input batch 85 owned + 23 JW → output batch → Summary output rows show **both** Owned and Job work (not all Owned).
2. **Inventory Raj Agro** — Owned + JW customer rows with correct bag counts (sum = output bags).
3. **Three owners** — Input owned + Raghavendra + Murugan → output 103 bags → 3-way split; 3 `processing_output_line` owner groups; 3 inventory owner rows.
4. **External mixed batch** — Still rejected (400).
5. **Restart backend** — Deploy fix; test on a **new** job (old jobs not auto-fixed).
6. **Output tab banner** — Shows input mix % (e.g. `Input mix: 75.2% Owned, 24.8% Job work · Customer`).
7. **No migration** — Logic-only.

## v14.4.1 — Cumulative owner weights (separate input/output batches)

1. **Two-step UI workflow** — Submit input batch (90 owned + 28 JW), then output-only batch (113 bags raj agro) → inventory **86 owned + 27 JW** (not all owned).
2. **Waste on output-only batch** — After input-only batch, output-only batch with stone/misc → `waste_allocations` split per owner.
3. **Activity log** — Output and balance-return rows show **Owner** column (Owned / Job work · customer).
4. **No input guard** — Output-only batch on job with no prior input → clear error.
5. **No migration** — Logic-only.

## v14.4 — Mixed processing bag/kg owner split

1. **Owned-only batch** — All output lands in owned inventory; no job_work row created.
2. **Job-work-only batch** — All output in that customer's `job_work` inventory bucket.
3. **Mixed 90 owned + 28 JW bags in → 113 bags raj agro out** — Inventory shows **86 owned + 27 JW** whole bags (not 112 bags + loose residue).
4. **Mixed loose balance 90 kg** — ~68.644 kg owned + ~21.356 kg job_work (sum = 90 kg).
5. **Waste stone/misc** — Batch detail `waste_allocations` still split by kg per owner; totals sum to batch waste fields.
6. **External customer mixed batch** — Still rejected (400).
7. **No migration** — Logic-only change; `alembic upgrade head` unchanged.

## v14.3 — JW quantity UX + activity log

1. **Detail page columns** — No Received/Returned columns; show Ordered, In custody, Remaining (when open). In custody correct after return + re-receive (e.g. order 247, receive 247, return 237, receive 237 → custody 247, remaining 0).
2. **Activity log badges** — Activity log shows **Received** / **Returned** badges per `entry_type`; newest first.
3. **Return then re-receive** — After return 237 and receive 237 on a 247-bag line: `received_bags=484`, `returned_bags=237`, custody 247, remaining 0.
4. **Void return blocked** — Void on a return entry returns 400; void on receive still works with password.
5. **Fulfillment tables** — Receive tab: Product, Ordered, Remaining (no Received column). Return tab: Product, Ordered, In custody (no Returned column).
6. **Migration** — `alembic upgrade head` (027); existing receipt rows backfilled as `receive`.

## v14.2.1 — Inventory detail Owner · Product columns

1. **Column order** — Detail view table per location: **Owner** first, **Product** second, then Brand / Bag type / qty columns.
2. **Per-product rowspan** — Product with 3 brand/bag lines → Owner and Product cells each span 3 rows only (not one Owner cell for all products at location).
3. **Summary unchanged** — Summary view still shows owner in expand header; nested table has no Owner column.

## v14.2 — Inventory readability

1. **View toggle** — Summary (default) vs Detail; choice persists after reload (`v14.inventory.view`).
2. **Summary collapsed** — Locations collapsed by default; expand shows owner rows (Owned + each job-work customer) with kg totals.
3. **Summary expand owner** — Expanding an owner shows compact product lines (no full 7-column table).
4. **Detail view** — One calm table per location; **Owner · Product** grouped per product block (see **v14.2.1**); no rainbow gradients on location/product cells.
5. **Stat tiles** — Click Owned → filters to owned; Job work → job_work chip; Locations → clears location filter; Low stock → low-stock-only filter.
6. **Quick chips** — All / My stock / Job work set owner filters correctly.
7. **Search** — Typing product or brand name filters rows (API search); customer name matches client-side.
8. **Regression** — Add stock, edit qty with password, pagination, and low-stock amber still work in both views.

## v14.1 — Owner-tagged operations

1. **Bag change — owned** — Default owner; owned stock subtract/add; API omits owner → `owned` in response.
2. **Bag change — job work** — Select Job work + customer; only that customer's job_work stock in dropdowns; TO lines stay same owner.
3. **Product transfer — job work** — Move job_work stock between locations; owner preserved at destination.
4. **Stock disposal — job work** — Dispose job_work custody; owned stock at same tuple unchanged.
5. **Void regression** — Void owned bag change / transfer / disposal still restores inventory (v12.17).
6. **Migration** — `alembic upgrade head` (026); existing operation records default `owned`.

## v14.0 — Job Work + owner-tagged inventory

1. **JW create** — `/job-work/new` → customer + lines → `JW-000001` format; no rates or totals.
2. **JW fulfillment — receive** — `/job-work/fulfillment` (Receive tab) → receive bags at location; inventory shows Job · customer badge; customer credit/debit unchanged. **Not** on order detail page.
3. **JW fulfillment — void** — Void receipt from `/job-work/fulfillment` with password; stock reversed; order detail shows read-only history.
4. **JW fulfillment — return** — Return tab on `/job-work/fulfillment` subtracts job_work custody stock.
5. **JW order detail** — `/job-work/:id` is read-only for receipts; links to fulfillment; no receive/void buttons.
6. **Inventory filters** — Owned only / Job work only / by customer; summary tiles for owned vs in-custody.
7. **Mixed processing (internal)** — 80% job + 20% owned input → output and waste split proportionally (check `waste_allocations` on batch).
8. **External mixed batch** — `party_type=external` customer + owned input in same batch → API 400.
9. **Sales deliver** — Line with `stock_source=owned` subtracts owned row; `job_work` subtracts that bill customer's job_work row.
10. **Bill vs JW fulfillment** — `/fulfillment` shows bills only; `/job-work/fulfillment` shows JW orders only.
11. **Migration** — `alembic upgrade head` (025); existing inventory rows are `owned`.

## v13.2 — Void auth, bill date, inventory edit, accounts UI

1. **Void without password** — Attempt payment void from UI without password → blocked; with `VOID_AUTH_PASSWORD` or login password → success.
2. **Inventory edit** — Edit row qty; without password → 403; with password → updates; warning lists linked activity when counts > 0.
3. **Bill date** — Create bill with yesterday → OK; tomorrow → validation error (UI max date + API 422).
4. **Bill form layout** — Single scrollable page (header, lines, totals); no tab navigation.
5. **Bank closing balance** — Bank accounts master and accounts dashboard show opening + closing; closing matches live balance formula.
6. **Customer search** — Find customer by alternate phone on customers list and bill form Combobox.
7. **Accounts dashboard layout** — KPI tiles in 3+2 grid (amounts on one line, not wrapped); bank table columns Bank / A/C / IFSC / Opening / Closing; recent entries Date / Type / Category / Payment / Bill / Amount; tables full-width stacked; numeric columns do not wrap.

## Payment void v5.4

1. **Cash void (scenario A)** — Create purchase bill ₹10,000; record cash payment ₹2,000. Customer credit drops by ₹2,000; bill shows Partial. Void payment from bill detail. Bill due returns to ₹10,000 (Unpaid); customer credit restored.
2. **Debit + set-off cascade (scenario B)** — Purchase ₹10k + sales ₹10k for same customer; pay purchase with Debit balance ₹10k. Both bills Paid; credit and debit balances 0. Void primary debit payment. Confirm dialog mentions set-off count. Both bills Unpaid; balances restored; set-off row voided (struck-through on bill detail).
3. **Block set-off child void (scenario C)** — On payments list or bill detail, set-off row has no Void button (or disabled with tooltip). Direct API `POST /api/payments/{setoff_id}/void` returns 400.
4. **Block double void (scenario D)** — Void an active payment; Void button disappears / voided badge shown. Second void attempt returns 400.
5. **Payments list** — Voided payments no longer appear on `/payments` list; bill detail still shows them struck-through.
6. **Payment page refresh** — After void from bill detail, open Record payment: due, paid, and customer balances match backend.

## Bill adjustment v5.5

1. **Create — negative adjustment** — Enter adjustment −500; submit disabled / error "Adjustment must be zero or greater".
2. **Create — excessive adjustment** — Lines total ₹50,000; adjustment ₹60,000 → "Final payable cannot be negative"; API 400 if forced.
3. **Create — valid** — Adjustment ₹1,000 on ₹50,000 bill → final payable ₹49,000; customer balance updated correctly.
4. **Edit — excessive adjustment** — On bill with payments, raise adjustment so final payable &lt; 0 → blocked; if paid, also blocked when below amount paid.
5. **Edit — zero final payable** — Discount + adjustment exactly equal subtotal → final payable ₹0 allowed (if no payment conflict).

## Processing balance reprocess v9.4

1. **New job Input tab** — only “From stock”; no “Use unclean balance” option.
2. **After balance return 15 kg** — “Use unclean balance” appears; hint shows 15 kg available.
3. **Reprocess 15 kg** — succeeds; available becomes 0; net balance updates.
4. **Reprocess 20 kg when 15 available** — blocked on submit (UI + API 400).
5. **Opening unclean stock without job return** — cannot use as reprocess on new job.
6. **Sold balance** — job available &gt; 0 but no physical stock at location → friendly error.

## Dashboard bill-date reporting v11.1

1. **May sales — ordered vs delivered** — Sales bill 1000 kg ordered, 400 kg delivered → dashboard shows 1000 kg sales qty ordered.
2. **May purchase** — Purchase bill 500 kg → purchase qty ordered 500 kg; purchase bill amount correct.
3. **May bill, June payment** — May dashboard unchanged; no Collected/Due top KPIs.
4. **Subtitle** — Mentions delivery and payment may occur later.
5. **Daily chart** — Shows sales + purchase bill amounts per day with legend.
6. **Bill type toggle** — Product/customer/location tables switch Sales / Purchase; CSV export respects bill_type.
7. **Compare row** — Sales and purchase bill amount + qty ordered MoM (not collected).

## Master delete guards v12.2 (+ v15.3 void auth)

1. **Void password required (v15.3)** — Owner delete prompts `VoidConfirmDialog`; API without `X-Void-Authorization` → 403.
2. **Customer with bills, balance 0** — Delete blocked with bill message (not 500), even with void password.
3. **Customer with balance > 0** — Balance message shown.
4. **Unused customer** — Delete OK with void password.
5. **Product on bill, no inventory** — Blocked with "bills" message.
6. **Unused product** — Delete OK with void password.
7. **Brand on bill** — Blocked with "bills" message.
8. **Location on sales bill** — Blocked with "bills" message.
9. **Bag type on bill** — Still blocked (regression).
10. **Bag type on inventory** — Blocked with "inventory" message.

## Inventory row locking v12.3

1. **Sequential** — 100 bags; deliver 60 on bill 1 → 40 left; deliver 60 on bill 2 → Insufficient stock.
2. **Concurrent** — Two simultaneous deliver 60 on same stock → only one succeeds; final count 40 bags.
3. **Transfer** — Product transfer between locations; no negative stock on either row.
4. **DB safety** — bag_count and loose_kg never negative after operations.

## Bills list filters v12.4

1. **Sales — Unpaid only** — Segmented control Unpaid shows only unpaid bills.
2. **Sales — Partial delivery** — Delivery dropdown Partial shows only partially delivered bills.
3. **Sales — Unpaid + Not delivered** — Both filters active (AND); only matching bills shown.
4. **Purchase — same three** — Repeat checks 1–3 on `/purchase-bills`.
5. **Clear filters** — Button resets both filters to All and restores full list.
6. **Filtered empty state** — When no rows match, message describes active filters and Clear filters works.

## Fulfillment void v12.5

1. **Purchase receive → void** — Receive 25 bags → void → Not delivered, stock reduced by 25.
2. **Sales deliver → void** — Deliver 25 bags → void → Not delivered, stock restored (+25).
3. **Purchase receive + return** — Must void return before voiding receive entry.
4. **Insufficient stock** — Void sales return blocked when stock cannot cover reversal.
5. **Bill detail UI** — Voided entries shown struck-through with Voided badge; active entries have Void button.

## Legacy code removal v12.6

1. **Smoke** — App starts; create sales bill, deliver line, record payment — no import errors.

## Bill number generation v12.7

1. **Concurrent create** — Two users/tabs create sales bill at same time — both succeed with different numbers.
2. **Preview** — New bill form preview shows next number; updates after prior bill created.
3. **Independent sequences** — Sales `S-…` and purchase `P-…` counters advance separately.

## v13.0 UI redesign

1. **Login / signup** — Allowed email signs in and lands on dashboard. Disallowed email surfaces ALLOWED_EMAILS rejection inside the auth-card `Banner`.
2. **Theme toggle persists** — Cycle topbar theme between Light → Dark → System; reload — chosen mode reapplies (and `<html data-theme>` matches). System mode tracks the OS theme.
3. **Density toggle persists** — Switch comfortable ↔ compact from topbar; spacing on cards/tables changes; reload — density reapplied (`<html data-density>`).
4. **Sidebar collapse persists** — Collapse from sidebar footer; icon-only layout; reload — still collapsed. Expand restores labels. Mobile (<768 px) shows hamburger and a slide-over drawer.
5. **Command palette (Cmd/Ctrl+K)** — Press shortcut; palette opens; type to search bills (number/customer), customers, products; Enter navigates to the matching detail page. Esc closes.
6. **BillFormPage validation** — Next bill number preview pill renders next to title. Set adjustment < 0 → blocked with banner. Set grand_total < 0 (large adjustment) → blocked. Try `amount_paid > grand_total` → blocked.
7. **Payment void cascade** — Void primary debit payment from bills detail Payments tab — `ConfirmDialog` explains set-off cascade, then both bills return to Unpaid and balances restored.
8. **Fulfillment void** — Bill detail Fulfillment tab — void a sales deliver entry — `ConfirmDialog` explains stock reversal; row becomes `Voided` pill; stock returns to source location.
9. **Master delete guard banner** — Try to delete a customer with bills; v12.2 backend 400 message rendered through `Banner` + toast.
10. **Processing job UI** — Mass-balance bar visible. On a fresh job, reprocess section hidden with helper text. After a balance return, reprocess section appears with capped available kg.
11. **Dashboard KPIs** — Only bill-date accrual KPIs (Sales bill amount, Purchase bill amount, Sales qty ordered, Purchase qty ordered). No Collected/Due KPIs.
12. **Bills list filters** — Payment segmented (All / Unpaid / Partial / Paid), Delivery dropdown, AND logic, Clear filters; filtered empty state shows active filters.
13. **Mobile (<768 px)** — Sidebar becomes drawer, tables collapse to cards on bills list, sticky "New bill" FAB visible.
14. **Reduced motion** — Enable OS "Reduce motion"; reload — page transitions, count-up, sidebar width animation are disabled; UI still functional.
15. **Lighthouse a11y ≥ 95** — Run on `/dashboard`, `/sales-bills`, `/sales-bills/new`; score ≥ 95.

## v13.1 UI polish

1. **Readable tabs and tables** — Tab labels, table headers, and cell text are visibly larger app-wide; no squinting on Bills, Fulfillment, or Inventory lists.
2. **Add customer from bills** — On sales/purchase bills list or new bill form, **Add customer** opens a dialog; new customer can be billed immediately; credit/debit balances are not editable here (default 0).
3. **Bill detail Overview** — Product line items appear on Overview; separate Lines tab is gone; Payments and Fulfillment tabs use larger type and mobile-friendly cards.
4. **Sales vs purchase colors** — Fulfillment and Payments rows are tinted indigo (sales) or emerald (purchase); easy to scan mixed lists.
5. **Fulfillment grouping** — Fulfillment page groups lines under bill number + customer cards; Deliver/Return/Receive open a modal (not a full page); old `/fulfillment/deliver/:id` URL redirects to the modal on `/fulfillment`.
6. **Inventory grouping** — Stock grouped by location; product / brand / bag type columns aligned; low stock (total kg &lt; 500) shows amber warning.
7. **Add stock modal** — Inventory **Add stock** opens a dialog only; form scrolls when tall; no kg/quintal/ton unit tabs in the dialog.
8. **Master add/edit modals** — Products, brands, customers, locations, bag types: Add and Edit open dialogs; list page stays clean.
9. **Processing open job modal** — Processing list **Open job** is a dialog; job detail page shows summary metrics and mass-balance bar.
10. **Operations forms** — Bag change, transfer, and disposal use sectioned cards with balance/flow hints; bag types add form is a modal.
11. **Required field style** — Required fields show `(required)` text, not red dots.
12. **Processing summary** — Summary tab **At a glance** shows output by brand, waste, misc, and total loss only (no reprocessed/returned/can-reprocess); batch log expandable below.

## Bag type immutability v12.9

1. **Add bag type confirm** — Bag Types → Add bag type → fill form → **Review & add** opens confirm modal with name, weight, type, and permanence warning → **Cancel** returns to form with values kept → **Confirm & create** POSTs and list refreshes.
2. **PUT weight blocked** — API `PUT /bag-types/{id}` with different `weight_per_bag_kg` → 400 `"Bag type weight cannot be changed after creation. Create a new bag type instead."`
3. **PUT is_loose blocked** — API `PUT` toggling `is_loose` → 400 `"Bagged vs loose setting cannot be changed after creation. Create a new bag type instead."`
4. **Rename allowed** — API `PUT` with new name, same weight and is_loose → 200.
5. **Inventory unchanged** — Row with bag type; blocked weight PUT; `bag_count` and `total_quantity_kg` unchanged.

## Bills GET read-only v12.10

1. **Create and view** — Create sales bill ₹1,00,000 → open detail → same total shown.
2. **Refresh stable** — Refresh detail multiple times → total unchanged (matches what was saved).
3. **List matches detail** — Open sales bills list → totals match detail page.
4. **Edit still works** — Edit bill (change rate) → new total saved and shown.
5. **Payment unchanged** — Record payment against displayed due → succeeds as before.

## Bill write lock v12.11

1. **Concurrent edit save** — User A submits bill edit while User B submits edit on same bill; one succeeds, other gets `Bill is in use. Please try again in a moment.`
2. **Concurrent payment/void** — User A records payment while User B attempts payment or void on same bill; second writer gets bill-in-use message.
3. **Concurrent fulfillment/write** — User A posts fulfillment while User B edits same bill; second writer gets bill-in-use message.
4. **Read still allowed** — During another user write attempt, opening bill detail/list still works.

## Schema non-negative guards v12.12

1. **Negative rate blocked early** — Try API/tooling with bill line `rate_per_kg: -100` → 422 validation error on `rate_per_kg` (not finalize error).
2. **Negative bags blocked** — Bill line `ordered_bags: -10` → 422 on `ordered_bags`.
3. **Negative payment blocked** — Payment `amount: -500` or `0` → 422 on `amount`.
4. **Valid bill unchanged** — Create normal sales bill (100 bags, positive rate) → succeeds as before.
5. **Valid payment unchanged** — Record normal payment → succeeds as before.
6. **Discount bounds** — `discount_percent: 101` on create → 422; `0` and `100` still accepted.

## Complete bill concurrency protection v12.13

1. **Stale tab save blocked** — Open same bill edit in two tabs; save in tab A, then save in tab B without refresh → tab B gets 409 stale message (`Bill was updated by another user. Refresh and try again.`).
2. **Simultaneous save** — Two users click Save at the same moment → one succeeds, other gets 409 bill-in-use message.
3. **Stale payment blocked** — Record payment in tab A; attempt payment/void in tab B with old screen → 409 stale.
4. **Stale fulfillment blocked** — Post fulfillment, then retry from old fulfillment dialog without refresh → 409 stale.
5. **Different bills OK** — Edit/pay/fulfill on bill A and bill B concurrently → both succeed.
6. **Refresh retry** — After stale 409, refresh bill and retry with latest version → succeeds.

## Bill adjustment no-abs guard v12.14

1. **Valid adjustment unchanged** — Create bill subtotal ₹5,00,000, adjustment ₹1,000 → grand total ₹4,99,000.
2. **Negative adjustment blocked at API** — Try adjustment -100 on create/edit → 422 (v12.12; still true).
3. **No silent masking** — If a test row has negative adjustment in DB, edit/recalc fails with clear `adjustment must be >= 0` (not wrong total).
4. **Normal workflow** — Create, edit adjustment, payment flow unchanged for valid values.

## v12.20 — Health and readiness

| # | Test | Expected |
|---|------|----------|
| H1 | GET /health | 200 status ok |
| H2 | GET /health/ready, DB up | 200 database ok |
| H3 | GET /health/ready, DB down | 503 database unavailable |
| H4 | GET /health, DB down | still 200 (liveness only) |

## v12.19 — CORS

| # | Test | Steps | Expected |
|---|------|-------|----------|
| C1 | Dev default | `CORS_ORIGINS` unset; frontend localhost:5173 | App loads; API works |
| C2 | Custom origin | Set `CORS_ORIGINS=https://test.example.com`; restart backend | Only that origin allowed |
| C3 | Production doc | README mentions `CORS_ORIGINS` | Deployer knows what to set |

## App-wide pagination v12.18

1. **Bills list** — First page loads fast; Prev/Next work; filters + summary stats match; bill detail still shows full lines + opposite due.
2. **Payments** — Paginated list; void still works.
3. **Inventory** — Paginated list; add stock still works.
4. **Fulfillment** — Paginated actionable bills; deliver/receive still works.
5. **Operation histories** — Paginated; void still works (v12.17).
6. **Master tables** — Products/brands/bag-types/customers/locations paginated; CRUD still works.
7. **Bill form dropdowns** — Customer/product/brand/location/bag-type selects still populate (`limit=500`).
8. **Command palette** — Search bills/customers/products without loading full DB; results appear after typing.

## Operations void v12.17

1. **Bag change void** — Post bag change → history → Void → stock restored; row shows Voided.
2. **Transfer void** — Transfer A→B → Void → stock back at A.
3. **Disposal void** — Dispose → Void → stock restored.
4. **Double void** — Second void on same row → error "already voided".
5. **Insufficient reverse** — Transfer then sell/consume at destination → void transfer blocked with clear message.
6. **Idempotency** — Repeat void POST with same key → no double reverse.

## System timestamps only v12.16

1. **Bill create** — No date picker on create form; submit bill → bill date equals today (IST).
2. **Payment** — No paid-at picker; submit payment → paid time equals submit moment.
3. **Fulfillment** — No fulfilled-at picker; deliver/receive → timestamp equals submit moment.
4. **Operations** — Bag change/transfer/disposal/processing batch: no operation time picker; timestamp equals submit moment.
5. **Reports** — Bill created today appears in today's month dashboard (bill_date = create day).
6. **API** — POST create payloads without date fields still succeed; sending old `bill_date` field is rejected/ignored per schema.

## Idempotency keys v12.15

1. **Duplicate bill submit** — Start create bill, trigger same submit twice with same idempotency key (devtools/retry) → only one bill created.
2. **Normal bill submit** — Single submit still creates one bill as before.
3. **Duplicate payment replay** — Replay same payment POST with same key → no second payment row; same response returned.
4. **Key reuse mismatch** — Reuse key with different payload → 409 clear error.
5. **Operations/processing** — Repeat POST with same key on bag-change or processing batch → no duplicate stock movement.
6. **Missing key (API)** — Covered POST without header → 400 required-key message.

## v12.21 accounts/cash-book/multi-bank

### Automated suite
`backend/tests/test_accounts_v1221.py` — 35 unittest cases. Run with:

```bash
cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_accounts_v1221
```

Covers:

**Bank accounts**
1. Create / list / edit / soft-delete / refuse-delete when in use (by payment or cash-book entry).
2. Exactly one `is_default=TRUE` at any time; `make-default` atomically flips the previous default off.
3. Migration backfill: pre-existing bank-mode payment is assigned to the seeded default bank.

**Expense categories**
1. Create non-system category (expense or income); refuse `kind=transfer`.
2. Cannot rename or delete `is_system` rows.
3. Cannot delete an in-use category.
4. Seed rows present after migration.

**Cash book CRUD**
1. Expense (cash) → cash balance decreases.
2. Expense (bank A) → A decreases; cash and other banks unchanged.
3. Income (cash / bank) → matching balance increases.
4. Transfer cash → bank A → cash down, A up.
5. Transfer bank A → bank B → A down, B up.
6. Reject transfer with same source and destination (cash→cash, A→A).
7. Link to bill: create expense with `bill_id=X` → `GET /api/bills/X/linked-entries` returns it.
8. Edit with correct `expected_version` — balances re-derive; wrong version → 409.
9. Void: balances revert; void already-voided → 409.
10. Idempotency: same `Idempotency-Key` returns the same entry.
11. Paginated list with filters honours `PageOut`.

**Payments (multi-bank)**
1. Sales cash → cash up; sales bank A → A up.
2. Purchase cash → cash down; purchase bank A → A down.
3. Void any of the above → balance reverts.
4. Reject bank payment without `bank_account_id`.
5. Reject cash payment with `bank_account_id`.

**Bill linkage (v15.9)**
1. `void-precheck` returns `can_void=false` when active linked cash-book entries exist (`linked_active_entries_count > 0`).
2. Voiding the bill is **blocked** until linked entries are voided or unlinked; void does **not** auto-void linked entries.
3. Linked-entries list returns only this bill's entries, paginated.

**Accounts dashboard**
1. Summary returns correct cash + per-bank + total_bank + total_money.
2. Summary returns correct total_customer_credit / total_customer_debit.
3. Per-customer list paginates; `has_balance` filter works.
4. Customer statement returns events in chronological order with correct running balance across bill create, payment received, payment void, bill void, setoff.
5. Statement date-range filter narrows results.

### Frontend manual checklist
1. Sidebar shows the **Accounts** section with Dashboard, Cash book, Customer balances, Bank accounts, Expense categories sub-links.
2. Dashboard tiles render with Indian number grouping (₹1,23,456.78); per-bank breakdown appears under Total Bank.
3. Cash Book entry form: switching the segmented control between Expense/Income/Transfer resets the relevant fields; bill picker filters by search.
4. Bill detail page shows the **Linked Expenses** section with correct totals and an *Add linked expense* button that opens `/accounts/cashbook/new?bill_id=…&category=Freight%20Charges` pre-filled.
5. Bill void: **Void bill** appears only when `void-precheck.can_void`; confirmation uses `VoidConfirmDialog`; voided bills show badge and hide from lists.
6. Payment form shows the **Bank Account** dropdown only when payment mode = Bank, defaults to the `is_default` bank, and is required.
7. Payments list shows the **Bank** column populated for bank-mode payments and blank otherwise.
8. Bank accounts master: Make-default button flips the badge; delete on an in-use bank shows a friendly 409 toast; default bank cannot be deleted.
9. Expense categories master: system rows display a lock icon, Edit/Delete are disabled and titled "System category".
10. Book settings page persists the cash opening balance and the Accounts dashboard re-derives all cash totals.

### Migration smoke (Alembic `023_spec_v1221_accounts_cashbook`)
1. `alembic upgrade head` on an empty DB — new tables created; `Bank` default seeded; `book_settings` id=1 seeded.
2. `alembic upgrade head` on a DB with pre-existing bank-mode payments — every such payment ends up with `bank_account_id = (seeded Bank).id`.
3. `alembic downgrade -1` reverses cleanly: `payments.bank_account_id` is nulled then dropped; new tables dropped; bills table unchanged at every step.

