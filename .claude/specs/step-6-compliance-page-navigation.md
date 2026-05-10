# Step 6 & 8 — Compliance Page Navigation Spec

## Overview

The compliance page (`/agent/compliance/:appId`) is a critical agent-facing workflow for BFIU Phase 7 (Compliance Screening) and Phase 8 (Risk Grading / EDD). It currently exists with functional data fetching and action buttons but lacks proper integration into the agent workflow — the queue page opens a local summary modal instead of navigating to the compliance page, and there is no navigation path from onboarding back to compliance review. The missing piece is wiring the compliance page into the agent's review journey: queue → compliance review → back to queue with updated status.

## Regulatory Requirements

- **Phase 7 — Compliance Screening**: Institutions must screen customers against UN sanctions lists, internal blacklists, and adverse media databases. Screening results with `requires_review=true` must be escalated.
- **Phase 8 — Risk Grading**: Institutions must calculate a 7-factor risk score. Score ≥ 15 = high risk, triggering Enhanced Due Diligence (EDD). EDD deadline is 30 days per BFIU section 6.2.
- **Phase 8 — EDD Protocol**: High-risk accounts must provide documentary evidence (bank statements, income proof, source of fund declaration) and receive CAMLCO approval. EDD deadline tracking must be enforced.
- **4-eyes principle**: Compliance actions (screening run, risk score, EDD creation) must be logged with agent identity — maker-checker separation applies.

## Current State

### Backend

- **`app/api/v1/compliance.py`** — Full compliance router with:
  - `POST /{app_id}/screening/run` (line 49): runs UN sanctions, blacklist, adverse media screening
  - `GET /{app_id}/screening/results` (line 68): list screening results
  - `POST /{app_id}/pep-check` (line 80): record PEP/IP screening
  - `POST /{app_id}/beneficial-owners` (line 94): add beneficial owner
  - `GET /{app_id}/beneficial-owners` (line 107): list beneficial owners
  - `POST /{app_id}/risk-score` (line 119): calculate risk score (manual or auto)
  - `GET /{app_id}/risk-score` (line 150): get latest risk score
  - `POST /{app_id}/edd/request` (line 172): create EDD request for high-risk
  - `GET /{app_id}/edd/status` (line 192): get EDD status
  - `POST /{app_id}/edd/{edd_id}/documents` (line 207): upload EDD document

- **`app/crud/crud_compliance.py`** — All CRUD methods exist for screening, PEP/IP, beneficial owners, risk scores, and EDD. No gaps.

- **No notifications endpoint for compliance**: When screening or risk score completes, no notification is dispatched to the customer or agent.

### Frontend

- **`ekyc-frontend/src/pages/agent/CompliancePage.tsx`** (line 1): Fully implemented — shows Sanctions Screening, Risk Grading, and EDD sections with run/calculate/create actions. Fetches `screening`, `risk-score`, and `edd-status` via React Query. All buttons wired to mutations.

- **`ekyc-frontend/src/AppRouter.tsx`** (line 58): Route registered at `/agent/compliance/:appId`.

- **`ekyc-frontend/src/pages/agent/AgentQueuePage.tsx`** (line 149): "Review" button calls `setSelectedApp(entry.app_id)` — opens a local summary modal instead of navigating to `/agent/compliance/:appId`. No navigation to compliance page.

- **No back-to-queue button** in CompliancePage — agent cannot return to queue after starting review.

- **No status update** in CompliancePage — after running screening/calculating risk/creating EDD, the queue item is not refreshed.

- **No customer summary header** in CompliancePage — no customer name, NID number, application ref, or verification status shown at the top.

## Gaps — What Needs to Be Built

### Backend

1. **Compliance notification dispatch** (new CRUD): When `screening/run`, `risk-score`, or `edd/request` succeeds, create a `Notification` record so the dispatcher can notify relevant agents/stakeholders. This is needed for audit trail completeness and agent alerts.

### Frontend

1. **Queue "Review" → CompliancePage navigation** (`AgentQueuePage.tsx`): Change "Review" button from `setSelectedApp` modal open to `navigate('/agent/compliance/${entry.app_id}')`.

2. **CompliancePage header** (new): Add a customer summary card at the top showing: application ref, customer name, NID number (masked), verification status (biometric, NID), submission date.

3. **Back to Queue button** (new): Add a "← Back to Queue" button in CompliancePage header that navigates to `/agent/queue`.

4. **Queue status refresh on completion** (new): After running screening, calculating risk, or creating EDD, invalidate the queue query so the queue table reflects updated status.

5. **EDD document upload UI** (new): The `CompliancePage` shows EDD status but has no UI for uploading EDD documents. Add an "Upload Documents" section when `eddStatus.status = 'in_progress'`.

6. **PEP/IP Check form integration** (new): The `CompliancePage` has no form for recording PEP/IP check results. Add a section for the agent to set PEP/IP flags and trigger EDD from the compliance page.

## Backend Specification

### New / Modified Endpoints

No new endpoints required — all backend endpoints already exist in `app/api/v1/compliance.py`.

**Optional enhancement** (low priority): `POST /compliance/{app_id}/notify-agent` — sends an internal notification to the assigned agent when screening completes. This can be deferred.

### New / Modified CRUD Methods

No new CRUD methods required — all CRUD exists in `crud_compliance.py`.

**Optional enhancement**: Add `crud_compliance.notify_agent_on_completion()` to create `Notification` records when compliance events fire.

## Frontend Specification

### onboardingStore Changes

No changes required — the compliance page is agent-facing, not part of the customer onboarding flow.

### New / Modified Pages or Components

#### 1. `ekyc-frontend/src/pages/agent/AgentQueuePage.tsx` — Modify "Review" button (existing file)

- **Change**: "Review" button `onClick` from `setSelectedApp(entry.app_id)` → `navigate('/agent/compliance/${entry.app_id}')`
- **Why**: Aligns queue workflow with compliance review path per BFIU 4-eyes principle.

#### 2. `ekyc-frontend/src/pages/agent/CompliancePage.tsx` — Add header, back button, EDD upload

**New header section** (top of page):
- Application ref badge
- Customer name (from `reviewSummary`)
- NID number masked display (show first 4, last 4, mask middle: `1234xxxx5678`)
- Verification status chips: NID Validated ✓, Biometric Verified ✓ (green) or ✗ (red)
- Submitted date

**New "Back to Queue" button** (top-right corner):
- Navigate to `/agent/queue`
- Triggers `qc.invalidateQueries({ queryKey: ['queue'] })` on mount to refresh queue

**New PEP/IP Check section** (below Screening):
- Collapsible panel, default open
- Form fields: `is_pep` (toggle), `is_ip` (toggle), `is_family_of_pep` (toggle), `is_family_of_ip` (toggle), `is_high_official_intl_org` (toggle), `match_detail` (textarea)
- On submit: calls `complianceAPI.pepCheck(appId, body)`, shows EDD required badge if triggered
- Updates `riskScore` query on success

**New EDD Document Upload section** (shown when `eddStatus.status === 'in_progress'`):
- Document type selector: Bank Statement, Income Proof, Source of Fund Declaration, Tax Return, Business Documents, Other
- File input (drag-and-drop zone)
- SHA-256 checksum display after upload (using existing storage pattern)
- Upload button calls `complianceAPI.uploadEDDDocument(appId, eddId, { document_type, storage_key, checksum_sha256 })`
- Lists already uploaded documents from query data

**New "Complete Review" button** (bottom):
- Visible only when screening results exist and risk score is calculated
- Navigates back to queue with queue query invalidated

### API Service Additions

No new API service functions required — all exist in `complianceAPI`:
- `complianceAPI.runScreening` — already exists
- `complianceAPI.calculateRisk` — already exists
- `complianceAPI.createEDD` — already exists
- `complianceAPI.getScreening` — already exists
- `complianceAPI.getRisk` — already exists
- `complianceAPI.getEDDStatus` — already exists
- `complianceAPI.uploadEDDDocument` — already exists

**New**: Add to `complianceAPI`:
```typescript
pepCheck: (appId: string, body: PEPCheckRequest) =>
  apiClient.post<APIResponse<{ check_id: string; edd_required: boolean }>>(`/compliance/${appId}/pep-check`, body),
```

### TypeScript Types

Add to `ekyc-frontend/src/types/api.ts`:

```typescript
export interface PEPcheckResult {
  check_id: string
  edd_required: boolean
  is_pep: boolean
  is_ip: boolean
  is_family_of_pep: boolean
  is_family_of_ip: boolean
  is_high_official_intl_org: boolean
}

export interface CustomerSummaryHeader {
  app_id: string
  application_ref: string | null
  customer_name: string | null
  nid_number_masked: string | null
  nid_validated: boolean
  biometric_verified: boolean
  face_matched: boolean
  submitted_at: string | null
}
```

## Acceptance Criteria

1. Queue "Review" button navigates to `/agent/compliance/{appId}` instead of opening a local modal.
2. CompliancePage shows a customer summary header with application ref, name, masked NID, and verification status chips.
3. CompliancePage has a "← Back to Queue" button that returns to `/agent/queue`.
4. PEP/IP check form is visible and functional — submitting sets flags and triggers EDD badge if `edd_required=true`.
5. EDD document upload section appears when EDD status is `in_progress`, and documents can be uploaded.
6. After any compliance action (screening, risk, EDD), the agent can return to the queue which reflects the updated application status.
7. All compliance actions are logged in the audit trail via existing `record_event` calls in `compliance.py`.
8. EDD deadline countdown (days remaining) is shown in the EDD section.

## Implementation Order

- [ ] 1. **Frontend** — `AgentQueuePage.tsx`: change "Review" button to `navigate('/agent/compliance/${entry.app_id}')`, remove local summary modal dependency.
- [ ] 2. **Frontend** — `CompliancePage.tsx`: add customer summary header (fetch `reviewSummary` via `adminAPI.reviewSummary(appId)`).
- [ ] 3. **Frontend** — `CompliancePage.tsx`: add "← Back to Queue" button in header.
- [ ] 4. **Frontend** — Add `pepCheck` to `complianceAPI` in `services.ts`.
- [ ] 5. **Frontend** — `CompliancePage.tsx`: add PEP/IP check collapsible form section.
- [ ] 6. **Frontend** — `CompliancePage.tsx`: add EDD document upload section (visible when `eddStatus.status === 'in_progress'`).
- [ ] 7. **Frontend** — `CompliancePage.tsx`: add "Complete Review" bottom button that returns to queue.
- [ ] 8. **Backend** (optional) — Add `crud_compliance.notify_agent_on_completion()` to create notification records after compliance events.
- [ ] 9. **Frontend** — Add `PEPcheckResult` and `CustomerSummaryHeader` types to `types/api.ts`.

## Testing Checklist

**Backend (Swagger UI / curl)**:

1. `GET /api/v1/admin/applications/{appId}/review-summary` → verify returns customer name, NID, verification status.
2. `POST /api/v1/compliance/{appId}/pep-check` with all flags → verify returns `edd_required: true` when PEP/IP detected.
3. `POST /api/v1/compliance/{appId}/screening/run` → verify audit log entry created.
4. `POST /api/v1/compliance/{appId}/risk-score` → verify score ≥ 15 triggers EDD required.
5. `GET /api/v1/compliance/{appId}/edd/status` → verify days_remaining countdown.

**Frontend (browser walkthrough)**:

1. Agent logs in → lands on `/agent/queue` → sees queue table with "Review" button.
2. Click "Review" on any entry → navigate to `/agent/compliance/{appId}`.
3. Verify customer summary header shows: name, masked NID, verification badges.
4. Run screening → results appear → click "← Back to Queue" → queue table shows updated status.
5. Calculate risk score → score ≥ 15 → EDD Required badge appears.
6. Create EDD request → EDD status section appears with deadline countdown.
7. Fill PEP/IP form → submit → verify `edd_required` triggers EDD section.
8. EDD in progress → upload a document → verify document appears in list.