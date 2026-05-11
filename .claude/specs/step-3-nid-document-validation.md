# Step 3 — NID Document Validation Spec

## Overview

This feature adds server-side validation to the NID upload and OCR extraction pipeline to ensure
that only authentic, machine-readable National ID card images are accepted, and that text
extraction succeeds with sufficient quality before the customer proceeds to biometric verification.
It implements the BFIU Circular No. 29 (2026) requirement that OCR capture must be mandatory in
both Bangla and English, and that the face-matching biometric step may only begin after a valid
NID image has been captured and key fields (name, NID number, DOB) have been successfully
extracted. This step sits between NID image upload (Phase A) and NID number validation against the
EC database (Phase C). Without it, the system accepts blank, corrupt, or non-NID images and
advances to face-match regardless of OCR quality.

---

## Regulatory Requirements

- **OCR capture mandatory** — BFIU 2026 mandates OCR extraction in both Bangla and English as a
  prerequisite to face-matching. A blank or unreadable NID must be rejected before proceeding.
- **Authenticity assurance** — Guidelines require "highest level of assurance and authenticity"
  for identity data. Accepting non-NID images undermines this mandate.
- **Biometric step gated on NID data** — Face-match requires a verified NID number and DOB
  (`FaceMatchRequest.nid_number`, `FaceMatchRequest.date_of_birth`). These must come from an
  OCR extraction that successfully extracted those two fields.
- **Immutable audit trail** — All successful and unsuccessful onboarding attempts must be logged
  with matching parameters. Validation failures (low confidence, missing critical fields) must
  appear in the audit log.
- **Retry / fallback** — If NID image quality is insufficient, the customer must be offered the
  option to retake photos. The system must not silently degrade.

---

## Current State

### Backend

| File | What exists |
|---|---|
| `app/api/v1/verification.py:150–166` | `GET /nid-upload-url` — generates presigned PUT URL; validates `side` and `content_type` only |
| `app/api/v1/verification.py:249–268` | `POST /documents/upload` — registers `KYCDocument` row; validates SHA256 hex length (64 chars) and mime_type |
| `app/api/v1/verification.py:169–203` | `POST /ocr/nid` — calls `run_ocr_extraction`, audits result; **no confidence threshold enforcement** |
| `app/crud/crud_verification.py:297–362` | `run_ocr_extraction()` — checks both doc rows exist, calls mock OCR, stores `OCRExtraction`; **no field-level validation** |
| `app/services/mock_ocr.py:12–30` | Mock OCR always returns `confidence_score=0.92` and all fields populated; **no simulation of failure/low-confidence** |

### Frontend

| File | What exists |
|---|---|
| `OnboardingPage.tsx` Phase B | Auto-triggers OCR; shows spinner; shows error with Retry + Enter manually |
| `OnboardingPage.tsx` Phase C | Displays confidence badge (green/amber/red); shows warning `Alert` if `< 0.8`; **does not block progression** |
| `AgentOnboardingPage.tsx` | Identical Phase B/C behaviour |
| `onboardingStore.ts` | `ocrResult: OCRResult \| null` stored; no `ocrValidated` flag |

### Stubs / Gaps

- `mock_ocr.py` always returns `confidence_score: 0.92` — never simulates low confidence or missing fields.
- No backend enforcement of minimum confidence score — any score proceeds.
- No backend check that critical fields (`extracted_nid`, `extracted_dob`) were actually extracted.
- Frontend confidence warning is advisory only; user can click "Validate NID" regardless of score.
- No file-size or image-dimension guard on the upload URL endpoint.

---

## Gaps — What Needs to Be Built

### Backend

**1. Confidence threshold enforcement in `run_ocr_extraction()`**
- What is missing: after OCR runs, `confidence_score` is stored but never checked against a minimum.
- Why needed: BFIU mandates readable Bangla + English capture; a score below threshold means the
  image is unacceptable and face-match data would be unreliable.
- File: `app/crud/crud_verification.py` — add threshold check after `db.add(ocr)` / before return.

**2. Critical-field presence check in `run_ocr_extraction()`**
- What is missing: `extracted_nid` and `extracted_dob` may be `None` even when confidence is high.
- Why needed: `POST /verify/nid` and `POST /verify/face` both require these fields. If they are
  absent the downstream steps will fail with a misleading error.
- File: `app/crud/crud_verification.py` — raise HTTP 422 if either field is `None` after extraction.

**3. NID number format validation in `run_ocr_extraction()`**
- What is missing: extracted NID string is stored as-is without format check.
- Why needed: Bangladesh NID numbers are exactly 10 or 17 digits (old format 10, new format 17,
  smart card 13). Accepting garbage strings prevents downstream EC validation from ever succeeding.
- File: `app/crud/crud_verification.py` — validate `extracted_nid` matches `^\d{10}$|^\d{13}$|^\d{17}$`.

**4. File-size guard on `GET /nid-upload-url`**
- What is missing: no `max_file_size_bytes` query parameter or header check.
- Why needed: prevents extremely large files (> 10 MB) from being registered and consuming storage,
  and deters binary blobs that are not images.
- File: `app/api/v1/verification.py` — add optional `file_size_bytes: int = 0` query param; raise
  422 if `> 10_000_000`.

**5. Mock OCR service — simulate validation scenarios**
- What is missing: mock always returns high confidence and all fields. Tests cannot exercise the
  failure paths added in gaps 1–3 without a real OCR service.
- Why needed: dev/test must be able to trigger low-confidence and missing-field paths.
- File: `app/services/mock_ocr.py` — read a `MOCK_OCR_SCENARIO` env var (`high_confidence`
  [default], `low_confidence`, `missing_nid`, `missing_dob`).

**6. Audit log on OCR validation failure**
- What is missing: when OCR extraction is rejected (low confidence / missing fields), no audit
  event is recorded.
- Why needed: BFIU mandates all unsuccessful onboarding attempts be logged.
- File: `app/api/v1/verification.py` `POST /ocr/nid` handler — wrap `run_ocr_extraction` in
  try/except and call `record_event` with `action=AuditAction.failed` before re-raising.

### Frontend

**7. Confidence threshold block in Phase C**
- What is missing: user can click "Validate NID" even when `confidence_score < 0.5`.
- Why needed: submitting an NID number extracted at < 50% confidence will almost certainly fail
  EC validation and confuse the user. The form should be blocked with a mandatory retake prompt.
- File: `OnboardingPage.tsx` and `AgentOnboardingPage.tsx` — disable "Validate NID" button and
  show mandatory retake `Alert` when `confidence_score !== null && confidence_score < 0.5`.

**8. Critical-field missing state in Phase C**
- What is missing: if `ocrResult.extracted_nid` or `ocrResult.extracted_dob` is `null`, the NID
  and DOB inputs render empty but the button is still clickable (string is empty → falsy check
  already disables, but UX gives no guidance).
- Why needed: user needs to know OCR failed to read a specific field so they can choose manual
  entry or retake photos, not just see an empty input.
- File: `OnboardingPage.tsx` and `AgentOnboardingPage.tsx` — add field-level `Alert` for each
  missing critical field alongside the input.

**9. File size / type guard before upload**
- What is missing: `<input type="file" accept="image/*">` allows any image; no size limit.
- Why needed: prevents accidental upload of 50 MB RAW files; gives immediate feedback without
  hitting the backend.
- File: `OnboardingPage.tsx` and `AgentOnboardingPage.tsx` — in `handleFileSelect`, check
  `file.size > 10_000_000` and `!file.type.startsWith('image/')` before calling any API; set
  `error` state and return early.

---

## Backend Specification

### New / Modified Endpoints

#### `GET /kyc/applications/{app_id}/nid-upload-url` (modify)

- **Auth:** CurrentActor (customer or agent)
- **New query param:** `file_size_bytes: int = 0` (optional)
- **Validation added:** raise `HTTPException(422, "File exceeds 10 MB limit")` if
  `file_size_bytes > 10_000_000`
- **Everything else unchanged**

#### `POST /kyc/applications/{app_id}/ocr/nid` (modify)

- **Auth:** CurrentActor
- **Body:** `NIDOCRRequest { nid_front_key, nid_back_key }` (unchanged)
- **Response:** `APIResponse[OCRResult]` (unchanged on success)
- **New behaviour:**
  1. Call `run_ocr_extraction()` inside try/except.
  2. On `HTTPException` from CRUD (validation failure): call `record_event` with
     `action=AuditAction.failed`, `entity_type="ocr_extractions"`,
     `new_value={"reason": exc.detail}`, then re-raise.
  3. On success: existing audit log unchanged.
- **File:** `app/api/v1/verification.py:169–203`

### New / Modified CRUD Methods

#### `CRUDVerification.run_ocr_extraction()` (modify)

**File:** `app/crud/crud_verification.py:297–362`

Add the following checks **after** `ocr_data = await mock_ocr_service.extract(...)` and
**before** constructing the `OCRExtraction` object:

```python
# 1. Confidence threshold
MIN_OCR_CONFIDENCE = 0.60
if (ocr_data.get("confidence_score") or 0) < MIN_OCR_CONFIDENCE:
    raise HTTPException(
        status_code=422,
        detail=f"OCR confidence too low ({ocr_data.get('confidence_score'):.0%}). "
               "Please retake clearer photos of the NID card.",
    )

# 2. Critical field presence
if not ocr_data.get("extracted_nid"):
    raise HTTPException(
        status_code=422,
        detail="OCR could not extract NID number. Please retake the NID front photo.",
    )
if not ocr_data.get("extracted_dob"):
    raise HTTPException(
        status_code=422,
        detail="OCR could not extract date of birth. Please retake the NID back photo.",
    )

# 3. NID number format (10, 13, or 17 digits)
import re
if not re.fullmatch(r"\d{10}|\d{13}|\d{17}", ocr_data["extracted_nid"]):
    raise HTTPException(
        status_code=422,
        detail="Extracted NID number has an invalid format. Please retake the NID front photo.",
    )
```

**Constant:** Add `MIN_OCR_CONFIDENCE = 0.60` at module level (configurable via `settings` later).

### Data Model Changes

None — `OCRExtraction.confidence_score` already exists as `float | None`. No migration needed.

---

## Frontend Specification

### onboardingStore Changes

No new state fields required. The existing `ocrResult: OCRResult | null` carries
`confidence_score`, `extracted_nid`, and `extracted_dob` — all needed for the new checks.

### New / Modified Pages or Components

#### `OnboardingPage.tsx` — `NIDStep` — Phase A `handleFileSelect`

**File:** `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`

Add at the top of `handleFileSelect`, before any API call:

```typescript
if (!file.type.startsWith('image/')) {
  setError('Only image files are accepted (JPEG, PNG, WebP).')
  return
}
if (file.size > 10_000_000) {
  setError('File is too large. Please use an image under 10 MB.')
  return
}
```

Also pass `file_size_bytes` to `getNIDUploadUrl` (new optional param — add to the query string):
No change required on frontend unless backend returns 422 for size; the existing error handler
already surfaces that.

#### `OnboardingPage.tsx` — `NIDStep` — Phase C

**Add field-level missing-field alerts** above each input:

```tsx
{!store.ocrResult?.extracted_nid && (
  <Alert variant="warning">
    NID number could not be read from the card. Enter it manually or retake photos.
  </Alert>
)}
{!store.ocrResult?.extracted_dob && (
  <Alert variant="warning">
    Date of birth could not be read from the card. Enter it manually or retake photos.
  </Alert>
)}
```

**Block "Validate NID" at confidence < 0.5:**

```tsx
const ocrBlocked = (store.ocrResult?.confidence_score ?? 1) < 0.5

// In the button:
<button
  onClick={handleValidate}
  disabled={!nid || !dob || loading || ocrBlocked}
  className="btn-primary flex-1"
>

// Above the button when blocked:
{ocrBlocked && (
  <Alert variant="error">
    OCR confidence is too low to proceed. Please retake the NID photos for a clearer scan.
  </Alert>
)}
```

#### `AgentOnboardingPage.tsx` — `NIDStep`

Apply identical changes to `handleFileSelect` (Phase A) and Phase C as above.

### API Service Additions

No new service functions required. The `getNIDUploadUrl` signature already accepts `contentType`;
`file_size_bytes` is a new optional query param that can be added if needed:

```typescript
// Optional enhancement to verificationAPI.getNIDUploadUrl:
getNIDUploadUrl: (appId: string, side: 'front' | 'back', contentType = 'image/jpeg', fileSizeBytes?: number) =>
  apiClient.get<APIResponse<NIDUploadUrlResponse>>(
    `/kyc/applications/${appId}/nid-upload-url`,
    { params: { side, content_type: contentType, ...(fileSizeBytes ? { file_size_bytes: fileSizeBytes } : {}) } }
  ),
```

### TypeScript Types

No new types required. `OCRResult` already has `confidence_score: number | null`,
`extracted_nid: string | null`, `extracted_dob: string | null`.

---

## Acceptance Criteria

1. `POST /ocr/nid` returns HTTP 422 with message containing "confidence too low" when OCR
   service returns `confidence_score < 0.60`.
2. `POST /ocr/nid` returns HTTP 422 with message containing "NID number" when
   `extracted_nid` is `null` or empty string.
3. `POST /ocr/nid` returns HTTP 422 with message containing "date of birth" when
   `extracted_dob` is `null` or empty string.
4. `POST /ocr/nid` returns HTTP 422 with message containing "invalid format" when
   `extracted_nid` is non-empty but not 10, 13, or 17 digits.
5. A failed OCR validation is recorded in the audit log with `action="failed"` and
   `entity_type="ocr_extractions"` containing the rejection reason.
6. `GET /nid-upload-url?file_size_bytes=10000001` returns HTTP 422 with "exceeds 10 MB".
7. Frontend: selecting a file > 10 MB shows an inline error and does not call any API.
8. Frontend: selecting a non-image file shows "Only image files are accepted" and does not call any API.
9. Frontend Phase C: when `ocrResult.confidence_score < 0.5`, the "Validate NID" button is
   disabled and a blocking error alert is displayed.
10. Frontend Phase C: when `ocrResult.extracted_nid` is `null`, a field-level warning alert
    appears above the NID number input.
11. Frontend Phase C: when `ocrResult.extracted_dob` is `null`, a field-level warning alert
    appears above the DOB input.
12. Frontend Phase C: when `ocrResult.confidence_score` is between 0.5 and 0.8, a warning
    alert is shown but the "Validate NID" button remains enabled (advisory only).
13. With `MOCK_OCR_SCENARIO=low_confidence`, `POST /ocr/nid` returns 422 (confidence check fires).
14. With `MOCK_OCR_SCENARIO=missing_nid`, `POST /ocr/nid` returns 422 (NID field check fires).
15. Mock OCR with `MOCK_OCR_SCENARIO=high_confidence` (default) still returns 200 and full OCR
    result — existing golden path is unbroken.

---

## Implementation Order

- [ ] 1. (backend) Add `MIN_OCR_CONFIDENCE = 0.60` constant and three validation checks
         (confidence, extracted_nid presence, extracted_nid format, extracted_dob presence)
         in `run_ocr_extraction()` — `app/crud/crud_verification.py`
- [ ] 2. (backend) Wrap `run_ocr_extraction()` call in `POST /ocr/nid` handler with try/except;
         call `record_event` with `AuditAction.failed` before re-raising — `app/api/v1/verification.py`
- [ ] 3. (backend) Add `file_size_bytes: int = 0` query param to `GET /nid-upload-url` handler
         with 422 guard — `app/api/v1/verification.py`
- [ ] 4. (backend) Add `MOCK_OCR_SCENARIO` env var support to `mock_ocr.py` — add four scenario
         branches: `high_confidence` (default), `low_confidence` (score 0.40, all fields present),
         `missing_nid` (score 0.92, `extracted_nid=None`), `missing_dob` (score 0.92, `extracted_dob=None`)
- [ ] 5. (frontend) Add file size (> 10 MB) and MIME type guard at top of `handleFileSelect` in
         `OnboardingPage.tsx` — set `error` state and return early
- [ ] 6. (frontend) Apply same file guard to `handleFileSelect` in `AgentOnboardingPage.tsx`
- [ ] 7. (frontend) Add field-level missing-field `Alert` for `extracted_nid` and `extracted_dob`
         in Phase C of `OnboardingPage.tsx`
- [ ] 8. (frontend) Apply same field-level alerts to Phase C of `AgentOnboardingPage.tsx`
- [ ] 9. (frontend) Disable "Validate NID" button and show blocking error when
         `confidence_score < 0.5` in `OnboardingPage.tsx`
- [ ] 10. (frontend) Apply same confidence block to `AgentOnboardingPage.tsx`
- [ ] 11. (frontend — optional) Pass `file_size_bytes` to `getNIDUploadUrl` in services.ts and
          both page files (allows backend 422 to also fire as a second line of defence)

---

## Testing Checklist

### Backend (Swagger / curl)

1. Start: `uvicorn app.main:app --reload`
2. Authenticate as customer, create application.
3. Upload NID front + back documents via `POST /documents/upload`.
4. `POST /ocr/nid` with valid keys → expect 200, `confidence_score: 0.92`, all fields populated.
5. Set `MOCK_OCR_SCENARIO=low_confidence`, restart, retry step 4 → expect 422, message contains
   "confidence too low".
6. Set `MOCK_OCR_SCENARIO=missing_nid`, restart, retry → expect 422, message contains "NID number".
7. Set `MOCK_OCR_SCENARIO=missing_dob`, restart, retry → expect 422, message contains "date of birth".
8. `GET /nid-upload-url?side=front&file_size_bytes=10000001` → expect 422, "exceeds 10 MB".
9. `GET /audit/logs` after steps 5–7 → confirm `action="failed"` entries with rejection reasons.

### Frontend (browser)

1. `npm run dev` in `ekyc-frontend/`, log in as `01712000001`.
2. Start new application, pass pre-check.
3. In Phase A: attempt to select a `.pdf` file → confirm error message, no spinner.
4. In Phase A: attempt to select a file > 10 MB → confirm error message, no spinner.
5. Upload valid JPEG front + back → confirm thumbnails, proceed to Phase B spinner.
6. Phase B auto-triggers OCR → confirm Phase C renders with green confidence badge (92%).
7. Set `MOCK_OCR_SCENARIO=low_confidence` on backend, retake photos and re-run OCR:
   - Confirm amber/red confidence badge.
   - Confirm blocking error alert and disabled "Validate NID" button.
8. Set `MOCK_OCR_SCENARIO=missing_nid`: confirm field-level warning above NID input.
9. Set `MOCK_OCR_SCENARIO=missing_dob`: confirm field-level warning above DOB input.
10. "Enter manually" path: confirm that manual mode bypasses OCR-based blocking (user typed NID
    manually so `ocrResult` is null / `ocrBlocked` is false).
11. Agent-assisted flow: repeat steps 3–9 in `AgentOnboardingPage` (same behaviour expected).

### Edge Cases

- `confidence_score = null` (OCR provider returned no score): should NOT block — treat as unknown,
  show no badge, allow progression. (`ocrBlocked` formula uses `?? 1` so null = pass).
- File exactly 10 MB (10_000_000 bytes): should pass the guard (guard fires on `>`).
- NID number "1234567890" (10 digits): valid format — no 422.
- NID number "12345678901" (11 digits): invalid — 422 with format message.
- `extracted_nid = "  "` (whitespace): treat as empty → present check fires (strip on backend).
