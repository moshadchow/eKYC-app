# Step 12 — KYC Lifecycle UI Spec

## Overview

This feature builds the complete frontend for KYC Lifecycle Management (pipeline Stage 12). The backend API is fully implemented across `app/api/v1/audit_lifecycle.py` (lifecycle_router) and `app/crud/crud_lifecycle.py`, exposing four endpoints: get refresh schedule, initiate refresh (customer), complete refresh (agent), and list overdue accounts. Currently the `/admin/lifecycle` route renders a stub `<div>` reading "KYC Lifecycle — coming in next step." This spec covers the three UI surfaces needed to surface that API: a Customer Lifecycle Panel (showing a customer their own review status and letting them initiate a refresh), an Agent Lifecycle Dashboard (overdue list + complete-refresh action), and a minor CRUD extension for an agent-facing paginated `list_all_schedules` query. Together these satisfy BFIU 2026 Circular 29 Section on Lifecycle Management and Periodic Updation, which mandates risk-tiered review frequencies, an automated notification mechanism, and a traceable event log for every refresh.

## Regulatory Requirements

- **Periodic review frequencies (BFIU 2026, Lifecycle Section):**
  - High-risk customers: KYC review every **1 year** (365 days) from last update
  - Medium-risk customers: KYC review every **2 years** (730 days) from last update
  - Low-risk customers: KYC review every **5 years** (1825 days) from last update
- Institutions must implement an **automated notification engine** to alert agents and customers when a review is due.
- When there is no change in information, a customer may provide a **self-declaration** via registered email or mobile — the system must support this pathway.
- If only an address change occurs, the customer submits a self-declaration; the institution must verify it (e.g., utility bill) within **2 months**.
- All high-risk accounts and EDD cases require approval from CAMLCO (4-eyes principle already enforced in approval flow).
- Customers whose risk grading escalates must have EDD initiated; a **1-month grace period** is permitted before temporary account closure.
- Institutions must maintain an **immutable audit trail** of every lifecycle event.
- Data must remain **on locally hosted servers** inside Bangladesh; no external transmission without BFIU approval.
- **5-year retention** of all digital KYC data from account closure date.

## Current State

### Backend

| File | Endpoint / Method | Notes |
|---|---|---|
| `app/api/v1/audit_lifecycle.py:48` | `GET /lifecycle/accounts/{account_id}/refresh-schedule` | Customer auth. Returns schedule + days_remaining + is_overdue |
| `app/api/v1/audit_lifecycle.py:64` | `POST /lifecycle/accounts/{account_id}/refresh/initiate` | Customer auth. Sets status → in_progress, logs event |
| `app/api/v1/audit_lifecycle.py:81` | `POST /lifecycle/accounts/{account_id}/refresh/complete` | Agent auth. Completes schedule, creates next, updates account |
| `app/api/v1/audit_lifecycle.py:102` | `GET /lifecycle/accounts/overdue` | Agent auth. Returns all overdue schedules |
| `app/crud/crud_lifecycle.py:31` | `CRUDLifecycle.get_schedule(db, account_id, user_id)` | Raises 404 if no schedule |
| `app/crud/crud_lifecycle.py:59` | `CRUDLifecycle.initiate_refresh(db, schedule)` | Sets in_progress, adds KYCRefreshEvent |
| `app/crud/crud_lifecycle.py:71` | `CRUDLifecycle.complete_refresh(db, account_id, new_risk_tier)` | Marks complete, creates next schedule |
| `app/crud/crud_lifecycle.py:126` | `CRUDLifecycle.list_overdue(db)` | Filters by due_date < today AND status in [scheduled, reminder_sent] |

### Frontend

| File | What exists |
|---|---|
| `ekyc-frontend/src/AppRouter.tsx:55` | `/admin/lifecycle` route renders stub `<div>KYC Lifecycle — coming in next step</div>` |
| `ekyc-frontend/src/api/services.ts:90` | `lifecycleAPI` object with `getSchedule`, `initiate`, `complete`, `overdue` — all wired |
| `ekyc-frontend/src/types/api.ts:320` | `RefreshSchedule` type defined |
| `ekyc-frontend/src/components/layout/AppShell.tsx:22` | Nav link "KYC Lifecycle" → `/admin/lifecycle` exists in adminNav |

### Stubs / Gaps

- No `LifecyclePage` component exists — the route is a stub string.
- No customer-facing lifecycle panel (customers have no way to see or initiate a KYC refresh from the UI).
- No agent-facing lifecycle table with overdue accounts.
- No `complete` action in the agent UI.
- `lifecycleAPI.overdue()` exists in services.ts but is never called from any component.
- Backend has no paginated `list_all_schedules` endpoint (agents need to browse all schedules, not just overdue ones).
- No `send_reminder` endpoint or CRUD method exists (reminder_count column exists in DB but is never incremented from the API layer).

## Gaps — What Needs to Be Built

### Backend Gaps

| Gap | Why needed | Where to add |
|---|---|---|
| `GET /lifecycle/accounts` — paginated list of all schedules for agents | Agents need to browse the full portfolio, not just overdue accounts | `app/api/v1/audit_lifecycle.py` + `app/crud/crud_lifecycle.py` |
| `POST /lifecycle/accounts/{account_id}/reminder` — mark reminder sent | BFIU requires traceable notification events; reminder_count must be incremented | `app/api/v1/audit_lifecycle.py` + `app/crud/crud_lifecycle.py` |

### Frontend Gaps

| Gap | Why needed | Where to add |
|---|---|---|
| `LifecyclePage` component | Replace stub route | New file: `ekyc-frontend/src/pages/admin/LifecyclePage.tsx` |
| Agent overdue table with complete-refresh action | Agents must be able to act on overdue accounts | Inside `LifecyclePage` |
| Agent all-schedules table with filters (risk tier, status) | Portfolio overview with upcoming reviews | Inside `LifecyclePage` |
| Customer lifecycle panel embedded in `OnboardingPage` post-submission OR as a new customer route | BFIU requires customers to be able to initiate self-service refresh | New component: `CustomerLifecyclePanel`, new route `/lifecycle` |
| `lifecycleAPI.listAll` service function | Calls the new paginated backend endpoint | `ekyc-frontend/src/api/services.ts` |
| `lifecycleAPI.sendReminder` service function | Calls the new reminder endpoint | `ekyc-frontend/src/api/services.ts` |
| `ScheduleListItem` TypeScript type | Typed response for the paginated list | `ekyc-frontend/src/types/api.ts` |
| AppRouter update: `/lifecycle` customer route | Customer needs access to their schedule | `ekyc-frontend/src/AppRouter.tsx` |
| AppShell nav update: add "My KYC Status" link for customers | Discoverability for customer lifecycle flow | `ekyc-frontend/src/components/layout/AppShell.tsx` |

## Backend Specification

### New / Modified Endpoints

---

#### 1. `GET /lifecycle/accounts` — Paginated schedule list (agent)

- **Auth:** `CurrentAgent` (any agent role)
- **Query params:**
  - `risk_tier` — optional, string (`low` | `medium` | `high`)
  - `status` — optional, string (`scheduled` | `reminder_sent` | `in_progress` | `completed` | `overdue`)
  - `page` — int, default 1
  - `page_size` — int, default 20, max 100
- **Response:** `PaginatedResponse[ScheduleListItem]`
  ```
  {
    total: int,
    page: int,
    page_size: int,
    data: [
      {
        schedule_id: str,
        account_id: str,
        user_id: str,
        risk_tier: str,
        due_date: str (ISO date),
        status: str,
        days_remaining: int,        # negative = overdue
        is_overdue: bool,
        reminder_count: int,
        last_reminder_at: str | null
      }
    ]
  }
  ```
- **Business logic:**
  1. Optionally filter by `risk_tier` and/or `status`
  2. Compute `days_remaining = (due_date - today).days` for each row
  3. Order by `due_date ASC` (soonest-due first)
  4. Paginate with offset/limit
- **CRUD method:** `crud_lifecycle.list_all(db, risk_tier, status, offset, limit)`

---

#### 2. `POST /lifecycle/accounts/{account_id}/reminder` — Send reminder (agent)

- **Auth:** `CurrentAgent`
- **Path param:** `account_id: uuid.UUID`
- **Request body:** none
- **Response:** `APIResponse[dict]`
  ```json
  { "schedule_id": "...", "reminder_count": 2, "last_reminder_at": "2026-05-08T..." }
  ```
- **Business logic:**
  1. Fetch `KYCRefreshSchedule` by `account_id`; raise 404 if not found
  2. Raise 400 if `schedule.status == completed`
  3. Increment `schedule.reminder_count += 1`
  4. Set `schedule.last_reminder_at = utcnow()`
  5. Set `schedule.status = RefreshStatus.reminder_sent`
  6. Add `KYCRefreshEvent(event_type=RefreshEventType.reminder_sent, notes=f"Reminder #{reminder_count} sent by agent {current_agent.employee_id}")`
  7. Record audit event `AuditAction.kyc_refresh_reminder`
  8. Return updated counts
- **CRUD method:** `crud_lifecycle.send_reminder(db, account_id, agent_id)`

---

### New / Modified CRUD Methods

#### `CRUDLifecycle.list_all`

```python
async def list_all(
    self,
    db: AsyncSession,
    risk_tier: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[KYCRefreshSchedule], int]:
```

- Builds `SELECT * FROM kyc_refresh_schedules` with optional `.where()` filters
- Orders by `KYCRefreshSchedule.due_date.asc()`
- Returns `(rows, total_count)` — use `func.count()` subquery for total
- File: `app/crud/crud_lifecycle.py`

---

#### `CRUDLifecycle.send_reminder`

```python
async def send_reminder(
    self,
    db: AsyncSession,
    account_id: uuid.UUID,
    agent_employee_id: str,
) -> KYCRefreshSchedule:
```

- Fetches schedule by `account_id` (no `user_id` filter — agent context)
- Raises `HTTPException(400)` if `schedule.status == RefreshStatus.completed`
- Mutates `reminder_count`, `last_reminder_at`, `status`
- Adds `KYCRefreshEvent`
- Returns updated schedule
- File: `app/crud/crud_lifecycle.py`

---

### Data Model Changes

No new tables or columns are required. All fields (`reminder_count`, `last_reminder_at`, `status`, `KYCRefreshEvent.event_type`) already exist. No new Alembic migration needed.

---

## Frontend Specification

### onboardingStore Changes

No changes needed. The lifecycle flow is a post-activation concern, separate from the onboarding wizard.

---

### New / Modified Pages or Components

---

#### 1. `ekyc-frontend/src/pages/admin/LifecyclePage.tsx` (new)

**What it renders:** Two-tab layout — "Overdue" and "All Schedules". Each tab is a table.

**Tab 1 — Overdue:**
- Calls `lifecycleAPI.overdue()` via React Query on mount
- Columns: Account ID (mono, last 8 chars), Risk Tier (StatusBadge), Due Date, Days Overdue, Reminder Count, Actions
- Actions per row:
  - "Send Reminder" button → calls `lifecycleAPI.sendReminder(accountId)` → invalidates query, shows success toast
  - "Complete Refresh" button → opens `CompleteRefreshModal`

**Tab 2 — All Schedules:**
- Calls `lifecycleAPI.listAll({ risk_tier, status, page })` via React Query
- Filters: Risk Tier select (all/low/medium/high), Status select (all/scheduled/reminder_sent/in_progress/completed/overdue)
- Columns: Account ID, Risk Tier, Due Date, Days Remaining (green if >30d, amber if 0–30d, red if negative), Status (StatusBadge), Reminder Count, Actions
- Pagination: Previous/Next footer matching AuditPage pattern
- "Send Reminder" button on each non-completed row

**User interactions:**
- Tab switch: local `useState` for `activeTab`
- "Send Reminder": `useMutation` → `lifecycleAPI.sendReminder` → `qc.invalidateQueries`
- "Complete Refresh": opens `CompleteRefreshModal` with `accountId` pre-filled

**State:** Local only (no store). Uses React Query for server state.

**Navigation:** No navigation — stays on page.

---

#### 2. `CompleteRefreshModal` (inline component in `LifecyclePage.tsx`)

**Props:** `{ open: boolean; accountId: string; onClose: () => void; onSuccess: () => void }`

**What it renders:**
- Risk Tier select: `low | medium | high` (optional — defaults to current tier if blank)
- Confirm button

**Interactions:**
- Confirm → calls `lifecycleAPI.complete(accountId, selectedTier)` → `onSuccess()` → invalidates queries

---

#### 3. `ekyc-frontend/src/pages/customer/CustomerLifecyclePage.tsx` (new)

**What it renders:** Single card showing the customer's KYC refresh status for their active account.

- Account ID input (or read from auth store if account_id is stored post-activation)
- Calls `lifecycleAPI.getSchedule(accountId)` via React Query
- Displays:
  - Risk Tier with color-coded badge
  - Due Date (formatted DD MMM YYYY)
  - Days Remaining — progress bar: green >30d, amber 8–30d, red ≤7d or overdue
  - Status badge
  - Last reminder date (if any)
- "Start KYC Refresh" button — visible only when `status` is `scheduled | reminder_sent | overdue`
  - Calls `lifecycleAPI.initiate(accountId)` → shows success state
  - After initiation, prompts user: "Your KYC refresh has been initiated. An agent will contact you within the review period."
- Self-declaration note: static info box explaining that if nothing has changed, a self-declaration via registered mobile/email is sufficient.

**State:**
- `accountId` — read from `authStore` if the `AccountActivated` response was persisted there, otherwise prompted via input
- React Query for schedule data

**Navigation:** Accessible via `/lifecycle` route (customer-guarded).

---

#### 4. Modified `AppRouter.tsx`

Add customer route:

```tsx
<Route element={<RequireAuth role="customer"><AppShell /></RequireAuth>}>
  <Route path="/onboarding" element={<OnboardingPage />} />
  <Route path="/lifecycle" element={<CustomerLifecyclePage />} />   {/* NEW */}
</Route>
```

Replace the stub agent route:

```tsx
<Route path="/admin/lifecycle" element={<LifecyclePage />} />   {/* was: stub div */}
```

---

#### 5. Modified `AppShell.tsx`

Add to `customerNav`:
```ts
{ to: '/lifecycle', icon: <RefreshCw className="h-4 w-4" />, label: 'KYC Status' }
```

---

#### 6. `authStore` — add `accountId` field (minor addition)

The customer needs their `account_id` to call lifecycle endpoints. The `AccountActivated` response from `/admin/applications/{appId}/activate` already returns `account_id`. The auth store should persist it so `CustomerLifecyclePage` can read it without requiring user input.

Add to `authStore.ts`:
- State field: `accountId: string | null`
- Action: `setAccountId: (id: string) => void`

The agent `activate` mutation in `AgentQueuePage.tsx` should call `setAccountId` on success if the current user is the customer (or this can be set from the onboarding flow on the customer's device — but since activation is an agent action, the customer must either be prompted to enter their account_id or have it communicated via a post-activation notification endpoint). **Pragmatic resolution:** `CustomerLifecyclePage` prompts for account_id if `authStore.accountId` is null, with a note: "Your account number was sent in your activation SMS."

---

### API Service Additions

Add to `ekyc-frontend/src/api/services.ts` within `lifecycleAPI`:

```ts
listAll: (params?: { risk_tier?: string; status?: string; page?: number; page_size?: number }) =>
  apiClient.get<PaginatedResponse<ScheduleListItem>>('/lifecycle/accounts', { params }),

sendReminder: (accountId: string) =>
  apiClient.post<APIResponse<{ schedule_id: string; reminder_count: number; last_reminder_at: string }>>(`/lifecycle/accounts/${accountId}/reminder`),
```

---

### TypeScript Types

Add to `ekyc-frontend/src/types/api.ts`:

```ts
export interface ScheduleListItem {
  schedule_id: string
  account_id: string
  user_id: string
  risk_tier: RiskClassification
  due_date: string
  status: RefreshStatus
  days_remaining: number
  is_overdue: boolean
  reminder_count: number
  last_reminder_at: string | null
}
```

Add `accountId: string | null` to the `authStore` state interface (internal type, not in `api.ts`).

---

## Acceptance Criteria

1. `GET /lifecycle/accounts?page=1` (agent token) returns HTTP 200 with `PaginatedResponse` shape; `total` equals count of all `kyc_refresh_schedules` rows.
2. `GET /lifecycle/accounts?risk_tier=high` filters results to only rows with `risk_tier = 'high'`.
3. `GET /lifecycle/accounts?status=overdue` returns only rows where `due_date < today AND status IN ('scheduled','reminder_sent')`.
4. `POST /lifecycle/accounts/{id}/reminder` increments `reminder_count` by 1 and sets `status = 'reminder_sent'`; returns 200 with updated count.
5. `POST /lifecycle/accounts/{id}/reminder` on a `completed` schedule returns HTTP 400.
6. `/admin/lifecycle` no longer renders the stub div — it renders `LifecyclePage` with two tabs: "Overdue" and "All Schedules".
7. Overdue tab displays accounts where `is_overdue = true`; "Send Reminder" button calls the reminder endpoint and updates the row without a full page reload.
8. "Complete Refresh" modal accepts an optional new risk tier; on confirm the account's `kyc_next_review_date` is updated per BFIU frequencies (high=1yr, medium=2yr, low=5yr).
9. A new `/lifecycle` route is accessible to authenticated customers and is listed in the customer sidebar as "KYC Status".
10. `CustomerLifecyclePage` renders a progress indicator showing days remaining; the color transitions to red when ≤7 days remain or when overdue.
11. "Start KYC Refresh" button is only enabled when status is `scheduled`, `reminder_sent`, or `overdue`; after clicking it the status displayed changes to `in_progress`.
12. A customer with `status = in_progress` sees an informational message instead of the start button.
13. All reminder and refresh-complete actions produce entries in `kyc_refresh_events` (verifiable via `GET /audit/logs?entity_type=kyc_refresh_schedules`).
14. BFIU compliance: high-risk accounts with `due_date` exactly 365 days after their last update date appear in the overdue list exactly 1 day after that date.
15. BFIU compliance: after `complete_refresh` with `risk_tier=medium`, `new_schedule.due_date` equals `today + 730 days`.

---

## Implementation Order

- [ ] 1. (backend) Add `CRUDLifecycle.list_all(db, risk_tier, status, offset, limit)` to `app/crud/crud_lifecycle.py`
- [ ] 2. (backend) Add `CRUDLifecycle.send_reminder(db, account_id, agent_employee_id)` to `app/crud/crud_lifecycle.py`
- [ ] 3. (backend) Add `GET /lifecycle/accounts` endpoint to `app/api/v1/audit_lifecycle.py` calling `crud_lifecycle.list_all`
- [ ] 4. (backend) Add `POST /lifecycle/accounts/{account_id}/reminder` endpoint to `app/api/v1/audit_lifecycle.py` calling `crud_lifecycle.send_reminder`
- [ ] 5. (backend) Verify `AuditAction.kyc_refresh_reminder` exists in `app/models/enums.py`; add if missing
- [ ] 6. (frontend) Add `ScheduleListItem` interface to `ekyc-frontend/src/types/api.ts`
- [ ] 7. (frontend) Add `listAll` and `sendReminder` to `lifecycleAPI` in `ekyc-frontend/src/api/services.ts`
- [ ] 8. (frontend) Add `accountId` state field and `setAccountId` action to `ekyc-frontend/src/store/authStore.ts`
- [ ] 9. (frontend) Create `ekyc-frontend/src/pages/admin/LifecyclePage.tsx` with "Overdue" tab using `lifecycleAPI.overdue()`
- [ ] 10. (frontend) Add "All Schedules" tab to `LifecyclePage` using `lifecycleAPI.listAll` with risk_tier and status filters + pagination
- [ ] 11. (frontend) Add `CompleteRefreshModal` inline component inside `LifecyclePage.tsx`
- [ ] 12. (frontend) Wire "Send Reminder" button to `lifecycleAPI.sendReminder` mutation in `LifecyclePage`
- [ ] 13. (frontend) Create `ekyc-frontend/src/pages/customer/CustomerLifecyclePage.tsx` with schedule display + initiate button
- [ ] 14. (frontend) Update `ekyc-frontend/src/AppRouter.tsx`: replace stub with `<LifecyclePage />` and add `/lifecycle` customer route
- [ ] 15. (frontend) Update `ekyc-frontend/src/components/layout/AppShell.tsx`: add "KYC Status" nav item to `customerNav`

---

## Testing Checklist

### Backend (Swagger UI / curl)

1. Log in as agent → `GET /lifecycle/accounts` → confirm shape matches `PaginatedResponse<ScheduleListItem>` with `days_remaining` computed.
2. `GET /lifecycle/accounts?risk_tier=high&status=scheduled` → all returned rows have `risk_tier=high` AND `status=scheduled`.
3. Seed a schedule with `due_date = yesterday` → `GET /lifecycle/accounts?status=overdue` → row appears; `is_overdue=true`, `days_remaining=-1`.
4. `POST /lifecycle/accounts/{id}/reminder` → response has `reminder_count: 1`; run again → `reminder_count: 2`.
5. `POST /lifecycle/accounts/{completed_id}/reminder` → HTTP 400 with "completed schedule" message.
6. `POST /lifecycle/accounts/{id}/refresh/complete` with `new_risk_tier=medium` → check `accounts.kyc_next_review_date` = today+730d.
7. `GET /audit/logs?entity_type=kyc_refresh_schedules` → entries for both reminder and complete events appear.

### Frontend (browser walkthrough)

1. Log in as `system_admin` → click "KYC Lifecycle" in sidebar → `LifecyclePage` renders (no stub text).
2. "Overdue" tab loads; if no overdue accounts, empty state is shown (no crash).
3. "All Schedules" tab: filter by `risk_tier=high` → table updates; clear filter → all rows return.
4. Click "Send Reminder" on any row → button shows loading state, row's `Reminder Count` increments, success feedback shown.
5. Click "Complete Refresh" → modal opens → select `medium` risk tier → confirm → row status changes to `completed`.
6. Log in as customer → "KYC Status" appears in sidebar → click it → `CustomerLifecyclePage` loads.
7. Enter account_id (or auto-populated) → schedule card renders with correct due date, risk tier badge, days remaining.
8. If `status=scheduled` → "Start KYC Refresh" button is enabled; click → status changes to `in_progress`, button disappears, info message shown.
9. If `status=completed` → button not shown; only status badge and due date visible.

### Edge cases

- Account with no schedule yet → `GET /lifecycle/accounts/{id}/refresh-schedule` returns 404; customer sees "No schedule found" message, not a crash.
- `days_remaining = 0` (due today) → displayed as amber/overdue depending on implementation; `is_overdue=false` since `due_date == today` (not `< today`).
- `complete_refresh` with no `new_risk_tier` → defaults to current schedule's `risk_tier`, not null.
- Agent calls `GET /lifecycle/accounts` as `maker` role (non-admin) → must succeed (any agent role allowed).
- Customer calls `GET /lifecycle/accounts` (agent-only endpoint) → must return HTTP 401/403.
- Reminder sent when `status=in_progress` → should succeed (not blocked, customer already engaged); test and confirm behavior.
