# Step 11 — Notification Delivery Spec

## Overview

Notification delivery is a cross-cutting concern that spans pipeline steps 11 (Account Activation) and 12 (Lifecycle Management). The system already writes `Notification` records to the database with `status=pending` at account activation and reminder events — but those records are never dispatched through an SMS or email gateway. The missing piece is a background worker (or synchronous dispatcher) that reads pending notifications, calls external gateways, updates delivery status, and captures delivery receipts. This spec covers the full notification delivery pipeline: dispatcher, per-channel gateway integrations (SMS for Bangladesh), retry logic, and the admin/customer notification history UI.

## Regulatory Requirements

- BFIU 2026 requires that institutions maintain an **immutable audit trail** of all onboarding events, including notifications sent to customers.
- BFIU mandates a **5-year retention period** for all KYC data including notification logs.
- KYC lifecycle rules require that customers receive **advance notice** before their review date (as per periodic review scheduling).
- All customer data (including mobile numbers and email for notifications) must be stored on **locally hosted servers within Bangladesh**; notification gateway calls must route through domestically hosted infrastructure.
- Notification records must capture: channel, recipient address, message body, timestamp sent, timestamp delivered, and failure reason.

## Current State

### Backend

- **Model**: `app/models/workflow.py:286` — `Notification` table with columns: `id`, `user_id`, `kyc_application_id`, `channel`, `notification_type`, `recipient_address`, `message_body`, `status`, `retry_count`, `gateway_message_id`, `sent_at`, `delivered_at`, `created_at`.
- **Notification model fields** (workflow.py:257):
  - `channel`: string (sms/email/push), max 10
  - `notification_type`: string (otp, submission_confirmation, approval, rejection, edd_request, kyc_refresh_reminder, account_activation, failed_ekyc), max 40
  - `recipient_address`: string, max 255
  - `status`: pending/sent/delivered/failed, default `pending`
  - `retry_count`: int, default 0
  - `gateway_message_id`: string (provider ref), max 255, nullable
  - `sent_at`: datetime, nullable
  - `delivered_at`: datetime, nullable

- **Notification enums** (`app/models/enums.py:210`):
  - `NotificationChannel`: sms, email, push
  - `NotificationType`: otp, submission_confirmation, approval, rejection, edd_request, kyc_refresh_reminder, account_activation, failed_ekyc
  - `NotificationStatus`: pending, sent, delivered, failed

- **Notification written at account activation** (`app/crud/crud_admin.py:337`):
  ```python
  notif = Notification(
      user_id=app.user_id,
      kyc_application_id=app.id,
      channel=NotificationChannel.sms.value,
      notification_type=NotificationType.account_activation.value,
      recipient_address="PENDING",  # <-- placeholder, no real address
      message_body=(f"Your account {account_num} has been activated. "
                    f"Reference: {app.application_ref}"),
      status=NotificationStatus.pending.value,
  )
  ```

- **Reminder write at lifecycle** (`app/crud/crud_audit.py:209`):
  - `send_reminder()` increments `reminder_count` on `KYCRefreshSchedule` and creates `KYCRefreshEvent` — but **no Notification record is written**.

- **No gateway integration**: No SMS/email sending service exists in `app/services/`.

- **No notification CRUD**: No CRUD class for Notification queries (list, update status, etc.).

### Frontend

- **No notification API service** in `ekyc-frontend/src/api/services.ts` — no `notificationAPI` object.
- **No notification history page** for customers or agents.
- **CustomerLifecyclePage.tsx** (`ekyc-frontend/src/pages/customer/CustomerLifecyclePage.tsx`) calls `lifecycleAPI.sendReminder()` — but this only updates the schedule record in DB, it does not send any actual SMS.
- No UI to view sent notification history or retry failed notifications.

## Gaps — What Needs to Be Built

### Backend

1. **SMS Gateway Integration** (`app/services/notification_gateway.py`): A new service with a dispatcher that reads `Notification` records where `status=pending`, calls an SMS gateway (configurable via `SMS_GATEWAY_URL`, `SMS_API_KEY` env vars), and updates the record. For development, a mock/stub mode using `NOTIFICATION_MOCK=true` logs to console.

2. **Email Gateway Integration** (`app/services/notification_gateway.py`): SMTP-based email sender using FastAPI's email utils or aiohttp, configurable via `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` env vars.

3. **Notification Dispatcher Background Task** (`app/services/notification_dispatcher.py`): An async background task that periodically scans for pending notifications (every 30 seconds), dispatches them via the appropriate gateway, and updates status. Uses `asyncio.create_task` or a lightweight scheduler.

4. **CRUD for Notifications** (`app/crud/crud_notification.py`): New CRUD class with methods: `create`, `mark_sent`, `mark_delivered`, `mark_failed`, `get_pending_batch`, `list_by_user`, `list_by_application`.

5. **Fix recipient_address** in `crud_admin.activate_account`: Instead of `"PENDING"`, look up the user's mobile number and email from the `User` model.

6. **Write Notification record on reminder** in `crud_audit.send_reminder()`: After updating the schedule, also create a Notification record with `notification_type=kyc_refresh_reminder`.

7. **New API router** (`app/api/v1/notifications.py`): Endpoints for listing user notification history, retrying failed notifications (agent/admin only), and resending a notification.

### Frontend

1. **notificationAPI service** in `services.ts`: Add `notificationAPI` object with `listByUser`, `retry`, `resend` methods.

2. **Notification History Page** (`ekyc-frontend/src/pages/customer/NotificationHistoryPage.tsx`): New page showing all notifications sent to the logged-in customer with status badges (pending/sent/delivered/failed).

3. **Admin Notification Queue** (`ekyc-frontend/src/pages/admin/NotificationQueuePage.tsx`): New admin page listing all pending/failed notifications with retry controls.

4. **Types for notifications** in `ekyc-frontend/src/types/api.ts`: `NotificationRead`, `NotificationListItem`.

## Backend Specification

### New / Modified Endpoints

#### 1. `GET /notifications/me` — List current user's notification history

- **Auth**: `CurrentUser`
- **Query params**: `status?: NotificationStatus`, `page?: int`, `page_size?: int` (default 20)
- **Response**: `PaginatedResponse[NotificationRead]`
- **Business logic**: Query `notifications` table filtered by `user_id = current_user.id`, ordered by `created_at desc`.
- **CRUD method**: `crud_notification.list_by_user(db, user_id, status, offset, limit)`

#### 2. `POST /notifications/{notif_id}/retry` — Retry a failed notification

- **Auth**: `CurrentAgent` (requires `system_admin` or `compliance_officer` role)
- **Response**: `APIResponse[NotificationRead]`
- **Business logic**: Look up notification, verify status is `failed`, re-dispatch via gateway, update to `sent`.
- **CRUD method**: `crud_notification.retry(db, notif_id)`
- **Audit**: Record `AuditAction.notification_retry` in audit log.

#### 3. `GET /notifications` — Admin list all notifications with filters

- **Auth**: `CurrentAgent` (requires `system_admin` or `system_auditor`)
- **Query params**: `status?: NotificationStatus`, `notification_type?: NotificationType`, `channel?: NotificationChannel`, `user_id?: str`, `page?: int`, `page_size?: int`
- **Response**: `PaginatedResponse[NotificationRead]`
- **CRUD method**: `crud_notification.list_all(db, status, notif_type, channel, user_id, offset, limit)`

### New / Modified CRUD Methods

#### `crud_notification.py` — `CRUDNotification`

```python
class CRUDNotification:
    async def create(db, user_id, kyc_application_id, channel, notification_type, recipient_address, message_body) -> Notification

    async def mark_sent(db, notif_id: uuid.UUID, gateway_message_id: str) -> Notification

    async def mark_delivered(db, notif_id: uuid.UUID) -> Notification

    async def mark_failed(db, notif_id: uuid.UUID, reason: str) -> Notification

    async def get_pending_batch(db, limit: int = 50) -> list[Notification]

    async def list_by_user(db, user_id, status, offset, limit) -> tuple[list[Notification], int]

    async def list_all(db, status, notif_type, channel, user_id, offset, limit) -> tuple[list[Notification], int]

    async def retry(db, notif_id: uuid.UUID) -> Notification
```

**Business rules**:
- `mark_sent`: Sets `status=sent`, `sent_at=utcnow()`, `gateway_message_id`.
- `mark_delivered`: Sets `status=delivered`, `delivered_at=utcnow()`.
- `mark_failed`: Increments `retry_count`, sets `status=failed`. Does not auto-retry — retry is triggered manually via endpoint.
- `get_pending_batch`: Returns up to `limit` records where `status=pending`, ordered by `created_at asc`. This is called by the dispatcher.

### Data Model Changes

No new tables needed. The `notifications` table already exists.

**New columns needed** (via Alembic migration):
- `notifications.error_message`: `String(500)` nullable — stores the last failure reason from the gateway.
- `notifications.gateway_response`: `Text` nullable — stores raw gateway response for debugging.

New Alembic migration required.

## Frontend Specification

### onboardingStore Changes

No changes required — notification delivery is a background concern, not part of the onboarding step machine.

### New / Modified Pages or Components

#### 1. `ekyc-frontend/src/pages/customer/NotificationHistoryPage.tsx` (NEW)

- **What it renders**: List of notifications for the logged-in user. Each row shows: notification type badge, channel icon (SMS/email), message snippet (truncated), status badge, timestamp.
- **User interactions**: Filter by status (pending/sent/delivered/failed), pagination.
- **API calls**: `notificationAPI.listByUser({ status, page })` on mount and on filter change.
- **State**: None stored in store — use React Query with `queryKey: ['notifications', userId, status, page]`.

#### 2. `ekyc-frontend/src/pages/admin/NotificationQueuePage.tsx` (NEW)

- **What it renders**: Admin table of all notifications with filters (status, type, channel, user_id). Columns: User, Type, Channel, Address (masked), Status, Retry Count, Sent At, Delivered At, Actions.
- **User interactions**: Filter by status/type/channel, pagination, "Retry" button on failed rows.
- **API calls**: `notificationAPI.listAll({ status, notification_type, channel, page })` and `notificationAPI.retry(notifId)`.
- **State**: React Query, `queryKey: ['notification-queue', status, type, channel, page]`.

### API Service Additions

Add to `ekyc-frontend/src/api/services.ts`:

```typescript
// ── Notifications ─────────────────────────────────────────────────────────────
export const notificationAPI = {
  listByUser: (params?: { status?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<NotificationRead>>('/notifications/me', { params }),
  listAll: (params?: { status?: string; notification_type?: string; channel?: string; user_id?: string; page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<NotificationRead>>('/notifications', { params }),
  retry: (notifId: string) =>
    apiClient.post<APIResponse<NotificationRead>>(`/notifications/${notifId}/retry`),
}
```

### TypeScript Types

Add to `ekyc-frontend/src/types/api.ts`:

```typescript
export interface NotificationRead {
  id: string
  user_id: string
  kyc_application_id: string | null
  channel: 'sms' | 'email' | 'push'
  notification_type: string
  recipient_address: string
  message_body: string
  status: 'pending' | 'sent' | 'delivered' | 'failed'
  retry_count: number
  gateway_message_id: string | null
  sent_at: string | null
  delivered_at: string | null
  error_message: string | null
  created_at: string
}

export interface NotificationListItem {
  schedule_id: string
  account_id: string
  user_id: string
  risk_tier: string
  due_date: string
  status: string
  days_remaining: number
  is_overdue: boolean
  reminder_count: number
  last_reminder_at: string | null
}
```

Also add `NotificationRead` to the import list in `services.ts`.

## Acceptance Criteria

1. When `crud_admin.activate_account()` runs, it looks up the user's mobile number and writes it into `notification.recipient_address` — not `"PENDING"`.
2. When `crud_audit.send_reminder()` runs, it creates a `Notification` record with `notification_type=kyc_refresh_reminder` and `status=pending`.
3. The notification dispatcher (background task or sync call from the router) reads pending notifications and calls the configured SMS gateway.
4. After gateway call, notification status updates to `sent` with `gateway_message_id` and `sent_at` timestamp.
5. Failed notifications record the error message and remain with `status=failed` and incremented `retry_count`.
6. `GET /notifications/me` returns the current user's notification history paginated.
7. `POST /notifications/{id}/retry` re-dispatches a failed notification (admin only).
8. `GET /notifications` lists all notifications with filters (admin only).
9. Frontend: Customer can view their notification history at `/notifications`.
10. Frontend: Admin can view the notification queue at `/admin/notifications` and retry failed entries.
11. BFIU compliance: All notification dispatches are recorded in the audit log; 5-year retention metadata is stored.
12. SMS gateway is configurable via env vars; mock mode logs to console in development.

## Implementation Order

- [ ] 1. **Backend** — Alembic migration: add `error_message` and `gateway_response` columns to `notifications` table.
- [ ] 2. **Backend** — New file `app/crud/crud_notification.py`: `CRUDNotification` class with all methods.
- [ ] 3. **Backend** — New file `app/services/notification_gateway.py`: SMS and email gateway implementations (with mock mode for dev).
- [ ] 4. **Backend** — New file `app/services/notification_dispatcher.py`: background dispatcher that calls gateway and updates status.
- [ ] 5. **Backend** — Modify `crud_admin.activate_account()`: look up user mobile, write real recipient_address, also create Notification records for all notification types triggered by activation.
- [ ] 6. **Backend** — Modify `crud_audit.send_reminder()`: write a `Notification` record alongside the `KYCRefreshEvent`.
- [ ] 7. **Backend** — New file `app/api/v1/notifications.py`: router with `/notifications/me`, `/notifications/{id}/retry`, `/notifications` endpoints.
- [ ] 8. **Backend** — Register `notifications_router` in `app/api/v1/__init__.py`.
- [ ] 9. **Frontend** — Add `NotificationRead` and `NotificationListItem` types to `ekyc-frontend/src/types/api.ts`.
- [ ] 10. **Frontend** — Add `notificationAPI` to `ekyc-frontend/src/api/services.ts`.
- [ ] 11. **Frontend** — New `NotificationHistoryPage.tsx` for customer notification history.
- [ ] 12. **Frontend** — New `NotificationQueuePage.tsx` for admin notification queue.
- [ ] 13. **Frontend** — Add routes for both pages in `AppRouter.tsx` (customer: `/notifications`, agent/admin: `/admin/notifications`).
- [ ] 14. **Backend** — Environment variables: add `SMS_GATEWAY_URL`, `SMS_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFICATION_MOCK` to config.

## Testing Checklist

**Backend (Swagger UI / curl)**:

1. `POST /admin/applications/{appId}/activate` → verify notification record created with real `recipient_address` (not `PENDING`).
2. `GET /notifications/me` → verify returns notifications for the logged-in user.
3. `GET /notifications` → verify admin can list all notifications with filters.
4. Set `NOTIFICATION_MOCK=true` and trigger notification → verify log output shows dispatch attempt.
5. Trigger a reminder → verify `Notification` record created with `notification_type=kyc_refresh_reminder`.

**Frontend (browser walkthrough)**:

1. As a customer, complete onboarding and get account activated → check `/notifications` page for account_activation SMS.
2. As an agent, send a KYC refresh reminder → check notification history for the reminder.
3. As an admin, go to `/admin/notifications` → verify pending/failed table loads and retry button works.
4. Filter by `failed` status → verify only failed notifications appear.
5. Click retry → verify status updates to `sent` and UI reflects change.

**Edge cases**:
- Retry a notification that is not in `failed` status → expect 400 error.
- Gateway returns an error → verify notification status becomes `failed` with `error_message` populated.
- User has no notifications → verify empty state message.
- Very long message body → verify truncation in UI with expand on click.