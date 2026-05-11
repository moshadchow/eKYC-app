# Step 3 — NID Upload (Front & Back) with OCR Extraction Spec

## Overview

This feature extends the existing NID Verification step (Step 3 of the onboarding pipeline) to require the customer to photograph or upload both the front and back sides of their physical NID card before manual NID number and DOB entry. The uploaded images are passed through an OCR engine which extracts and pre-fills name (English and Bangla), NID number, date of birth, address, fathers name, and mothers name. The extracted data is persisted in the `ocr_extractions` table (already defined in the schema), cross-checked against the Election Commission (EC) database response, and surfaced to the user for review before proceeding to biometric verification. This implements the BFIU 2026 face-matching model requirement which mandates "Mandatory capture in Bangla and English via OCR" as a prerequisite to the face-match step. It sits between Pre-check / Application creation (Step 2) and Biometric Verification (Step 4).

---

## Regulatory Requirements

- BFIU Circular No. 29 (2026), Face-matching Model: **"OCR Functionality: Mandatory capture in Bangla and English"** — NID card text in both scripts must be captured digitally before proceeding.
- BFIU guidelines specify that identity data must reach the **"highest level of assurance and authenticity"** — OCR cross-validation against the EC database response provides a second layer of identity assurance on top of manual NID number entry.
- Record-keeping mandate: all digital KYC data including **"onboarding logs, identity verification results"** must be retained for 5 years. OCR extraction results (raw JSON, confidence score, field values) must be stored in the immutable `ocr_extractions` audit trail.
- BFIU audit trail requirement: `audit_lifecycle.py` must capture **"NID image capture status"** — the spec explicitly names this as a gap requiring enhancement.
- Data sovereignty: NID card images contain biometric-quality PII and must be stored on locally-hosted or private-cloud infrastructure within Bangladesh. The existing S3-compatible presigned URL pattern must be used.
- Face-matching model table: **"Image Capture: High-resolution camera / webcam"** and **"Lighting Environment: Adequate white lighting; no glare"** — the frontend must provide on-screen guidance for capture quality.

---

## Current State

### Backend
- **`app/api/v1/verification.py`**:
  - `POST /kyc/applications/{app_id}/verify/nid` (line 56) — accepts manual NID number + DOB text, calls mock EC API, returns auto-fill fields. No image upload.
  - `GET /kyc/applications/{app_id}/selfie-upload-url` (line 120) — presigned PUT for selfies only (hardcoded `selfies/` key prefix).
  - `POST /kyc/applications/{app_id}/documents/upload` (line 179) — registers document metadata after binary upload. Accepts `document_type: nid_front | nid_back` via `DocumentType` enum (line 77 of `app/models/enums.py`). **This endpoint exists but is never called from the NID step.**
  - No OCR endpoint exists anywhere.

- **`app/crud/crud_verification.py`**:
  - `register_document()` (line 255) — inserts a `KYCDocument` row. Handles versioning. **Already usable for NID front/back.**
  - No OCR CRUD method exists.

- **`app/models/onboarding.py`** (lines 264–298):
  - `OCRExtraction`, `OCRExtractionBase`, `OCRExtractionCreate`, `OCRExtractionRead` models fully defined.
  - `ocr_extractions` table is created in migration `0001_initial_ekyc_tables.py` (line 378).
  - **Zero CRUD methods and zero API endpoints** read or write this table.

- **`app/core/storage.py`**: `generate_presigned_put(key, content_type, expires)` and `generate_presigned_get(key, expires)` are ready to use.

- **`app/models/enums.py`** line 77–78: `DocumentType.nid_front = "nid_front"` and `DocumentType.nid_back = "nid_back"` are already defined.

### Frontend
- **`ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`** — `NIDStep` (lines 121–165): renders two plain text inputs (NID number, DOB). No file upload, no camera capture, no OCR display.
- **`ekyc-frontend/src/store/onboardingStore.ts`**: no fields for NID image storage keys or OCR results.
- **`ekyc-frontend/src/api/services.ts`** — `verificationAPI.uploadDocument` (line 62) exists but is never called from the NID step.
- No NID image upload or OCR frontend component exists anywhere.

### Stubs / Mocks
- `crud_verification.validate_nid()` calls `mock_ec_service.validate_nid()` — this is a mock that always returns a fixed identity record. OCR cross-validation against EC data cannot be implemented until this is replaced with a real EC API, but the feature can be built and tested against the mock.

---

## Gaps — What Needs to Be Built

### Backend Gaps

1. **No presigned PUT URL endpoint for NID images**
   - Missing: a GET endpoint to generate a presigned S3 URL for `nid_front` and `nid_back` images, analogous to `GET /selfie-upload-url`.
   - Why needed: the frontend must upload images directly to object storage without routing binary data through FastAPI.
   - File: `app/api/v1/verification.py`

2. **No OCR endpoint**
   - Missing: a `POST /kyc/applications/{app_id}/ocr/nid` endpoint that accepts the two document storage keys, runs OCR extraction (mock service initially), persists the result to `ocr_extractions`, and returns extracted fields.
   - Why needed: BFIU mandates OCR capture in Bangla and English; extracted data must be stored for audit.
   - File: `app/api/v1/verification.py`

3. **No OCR CRUD method**
   - Missing: `CRUDVerification.run_ocr_extraction()` that calls the OCR service, maps results to `OCRExtraction`, and inserts the row.
   - Why needed: keeps business logic out of the router (existing project convention).
   - File: `app/crud/crud_verification.py`

4. **No OCR service / mock**
   - Missing: `app/services/mock_ocr.py` — a mock OCR service analogous to `mock_ec_service` that returns plausible extracted field values from a storage key.
   - Why needed: allows end-to-end testing without a real OCR provider; mirrors the mock EC pattern already in the codebase.
   - File: `app/services/mock_ocr.py` (new file)

5. **Audit logging of NID image capture**
   - Missing: the `validate_nid` audit event does not include `nid_image_captured: true/false`.
   - Why needed: BFIU explicitly names "NID image capture status" as a required audit field.
   - File: `app/api/v1/verification.py` line 65–70

### Frontend Gaps

1. **No NID image capture / upload UI in `NIDStep`**
   - Missing: two file input / camera capture panels for front and back of NID card, with quality guidance text.
   - Why needed: BFIU face-matching model requires OCR capture of physical NID card.
   - File: `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`

2. **No OCR result display / review UI**
   - Missing: after OCR, show extracted fields in a read-only review panel so the user can confirm or correct before proceeding.
   - Why needed: OCR engines are not 100% accurate; user review catches extraction errors before EC validation.
   - File: `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`

3. **No store state for NID upload / OCR**
   - Missing: `nidFrontKey`, `nidBackKey`, `ocrResult` fields and setters in `onboardingStore.ts`.
   - Why needed: state must persist across re-renders and step navigation.
   - File: `ekyc-frontend/src/store/onboardingStore.ts`

4. **No API service calls for NID upload URL or OCR**
   - Missing: `getNIDUploadUrl()` and `runOCR()` functions in `verificationAPI`.
   - File: `ekyc-frontend/src/api/services.ts`

---

## Backend Specification

### New / Modified Endpoints

#### 1. `GET /kyc/applications/{app_id}/nid-upload-url`
- **Auth:** `CurrentActor` (customer or agent)
- **Query params:**
  - `side`: `"front"` | `"back"` (required)
  - `content_type`: `"image/jpeg"` | `"image/png"` | `"image/webp"` (default `"image/jpeg"`)
- **Response:** `APIResponse[NIDUploadUrlResponse]`
  ```
  NIDUploadUrlResponse:
    upload_url: str       — presigned PUT URL
    storage_key: str      — key to pass back to OCR and register_document
    expires_in: int = 300
  ```
- **Business logic:**
  1. Validate `side` is `"front"` or `"back"`.
  2. Validate `content_type` is in `ALLOWED_NID_CONTENT_TYPES` (`image/jpeg`, `image/png`, `image/webp`).
  3. Call `crud_verification.get_application(db, app_id, actor.id)` to guard access.
  4. Generate storage key: `f"nid/{app_id}/{side}/{uuid4()}.jpg"`.
  5. Call `generate_presigned_put(key, content_type, expires=300)`.
  6. Return `NIDUploadUrlResponse`.
- **CRUD called:** `crud_verification.get_application()`

#### 2. `POST /kyc/applications/{app_id}/ocr/nid` *(new endpoint)*
- **Auth:** `CurrentActor` (customer or agent)
- **Request body:**
  ```
  NIDOCRRequest:
    nid_front_key: str    — required, storage key of uploaded front image
    nid_back_key: str     — required, storage key of uploaded back image
  ```
- **Response:** `APIResponse[OCRExtractionRead]`
- **Business logic:**
  1. Call `crud_verification.get_application(db, app_id, actor.id)`.
  2. Call `crud_verification.run_ocr_extraction(db, app_id, body.nid_front_key, body.nid_back_key)`.
  3. Audit: `record_event(... action=AuditAction.create, entity_type="ocr_extractions", new_value={"nid_image_captured": True, "confidence": result.confidence_score})`.
  4. Return `APIResponse(data=result)`.
- **CRUD called:** `crud_verification.run_ocr_extraction()`

#### 3. Modified `POST /kyc/applications/{app_id}/verify/nid`
- **No schema change.** Add to the audit `new_value` dict: `"nid_image_captured": bool` — pass as a query param `image_uploaded: bool = False` so the frontend can signal whether images were uploaded before NID text entry.
- **Why:** BFIU audit trail requirement for NID image capture status.

---

### New / Modified CRUD Methods

#### `CRUDVerification.run_ocr_extraction()`
- **Signature:**
  ```python
  async def run_ocr_extraction(
      self,
      db: AsyncSession,
      app_id: uuid.UUID,
      nid_front_key: str,
      nid_back_key: str,
  ) -> OCRExtraction:
  ```
- **Return type:** `OCRExtraction`
- **DB operations:**
  1. Verify both `KYCDocument` records exist for `nid_front` and `nid_back` under `app_id`. If not found, raise `HTTPException(422, "NID images must be registered before OCR")`.
  2. Fetch the most recent `nid_front` document for `app_id` to get its `id` (FK for `ocr_extractions.document_id`).
  3. Call `await mock_ocr_service.extract(nid_front_key, nid_back_key)` → returns dict of extracted fields + `raw_json` + `confidence_score`.
  4. INSERT into `ocr_extractions`: map all extracted fields from the mock response.
  5. `await db.flush()` and return the `OCRExtraction` instance.
- **Business rules:**
  - If `confidence_score < 0.5`, do not raise an error — return the low-confidence result and let the frontend warn the user. The user must still confirm before proceeding.
  - Existing `OCRExtraction` rows for the same `app_id` are not deleted — each upload creates a new row (versioning for audit trail).

---

### Data Model Changes

No new tables or columns required. The `ocr_extractions` table and all its columns are already defined in the migration and the SQLModel class. No Alembic migration needed.

---

## Frontend Specification

### onboardingStore Changes

**New state fields to add:**
```ts
nidFrontKey:  string | null   // initial: null — storage key after successful upload
nidBackKey:   string | null   // initial: null
ocrResult:    OCRResult | null // initial: null — extracted fields returned from /ocr/nid
```

**New actions to add:**
```ts
setNIDFrontKey: (key: string) => void   // sets nidFrontKey
setNIDBackKey:  (key: string) => void   // sets nidBackKey
setOCRResult:   (r: OCRResult) => void  // sets ocrResult
```

**Step enum:** No change — NID upload and OCR happen within the existing `'nid_capture'` step.

---

### New / Modified Pages or Components

#### Modified: `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx` — `NIDStep` function

**New sub-flow within `NIDStep` (3 phases, rendered conditionally):**

**Phase A — Image Upload** (shown when `!nidFrontKey || !nidBackKey`)
- Renders two upload panels side by side: "NID Front" and "NID Back".
- Each panel: a file `<input accept="image/*" capture="environment">` styled as a drag-and-drop zone, or a "Use Camera" button that opens the device camera.
- Quality guidance text: "Place card on a flat surface with good lighting. Avoid glare and shadows."
- On file select / capture:
  1. Call `verificationAPI.getNIDUploadUrl(appId, side)` → get `{ upload_url, storage_key }`.
  2. `PUT` blob to `upload_url` directly (same pattern as `uploadSelfieBlob`).
  3. Call `verificationAPI.uploadDocument(appId, { document_type: 'nid_front'/'nid_back', storage_key, mime_type, file_size_bytes, checksum_sha256 })` to register the document.
  4. Show thumbnail preview of the uploaded image.
  5. Set `store.setNIDFrontKey(key)` or `store.setNIDBackKey(key)`.
- "Next: Extract Data" button enabled only when both keys are set. On click, transitions to Phase B.

**Phase B — OCR Extraction** (shown when both keys set but `!ocrResult`)
- Shows a loading spinner: "Reading your NID card…"
- On mount (or button click): call `verificationAPI.runOCR(appId, { nid_front_key, nid_back_key })`.
- On success: call `store.setOCRResult(result)` and transition to Phase C.
- On failure: show error with a "Retry" button and a "Enter manually" escape hatch that skips to Phase C with empty prefill.

**Phase C — Review & Confirm** (shown when `ocrResult` is set)
- Displays extracted fields in a read-only review card: Name (EN), Name (BN), NID Number, Date of Birth, Address, Father's Name, Mother's Name, and Confidence Score badge (green ≥ 0.8, amber 0.5–0.8, red < 0.5).
- NID Number and DOB fields are editable `<Input>` pre-filled from OCR; user can correct OCR errors.
- Low-confidence warning: if `confidence_score < 0.8`, show an `<Alert variant="warning">` — "OCR confidence is low. Please verify the fields below carefully."
- "Validate NID" button: calls existing `verificationAPI.validateNID(appId, { nid_number, date_of_birth })`.
- On success: `store.setNIDRecord(result)` and call `next(nextStep)` (existing flow unchanged).
- "Back" button: clears `nidFrontKey`, `nidBackKey`, `ocrResult` in store and returns to Phase A.
- Navigation on back-step (overall): `prev()` as today.

---

### API Service Additions

Add to `verificationAPI` in `ekyc-frontend/src/api/services.ts`:

```ts
getNIDUploadUrl: (appId: string, side: 'front' | 'back', contentType = 'image/jpeg') =>
  apiClient.get<APIResponse<NIDUploadUrlResponse>>(
    `/kyc/applications/${appId}/nid-upload-url`,
    { params: { side, content_type: contentType } }
  ),

runOCR: (appId: string, body: NIDOCRRequest) =>
  apiClient.post<APIResponse<OCRResult>>(`/kyc/applications/${appId}/ocr/nid`, body),
```

Also add a reusable `uploadFileBlob(uploadUrl: string, blob: Blob): Promise<void>` alongside existing `uploadSelfieBlob` — identical implementation but named generically for NID images.

---

### TypeScript Types

Add to `ekyc-frontend/src/types/api.ts`:

```ts
export interface NIDUploadUrlResponse {
  upload_url: string
  storage_key: string
  expires_in: number
}

export interface NIDOCRRequest {
  nid_front_key: string
  nid_back_key: string
}

export interface OCRResult {
  id: string
  kyc_application_id: string
  document_id: string
  extracted_name_en: string | null
  extracted_name_bn: string | null
  extracted_nid: string | null
  extracted_dob: string | null       // ISO date string
  extracted_address: string | null
  extracted_fathers_name: string | null
  extracted_mothers_name: string | null
  confidence_score: number | null
  raw_json: string
  created_at: string
}
```

Also add to `onboardingStore.ts` imports: `OCRResult`.

---

## Acceptance Criteria

1. `GET /kyc/applications/{app_id}/nid-upload-url?side=front` with a valid customer token returns HTTP 200 with `upload_url` and `storage_key` where `storage_key` starts with `nid/{app_id}/front/`.
2. `GET /kyc/applications/{app_id}/nid-upload-url?side=invalid` returns HTTP 422.
3. A binary JPEG PUT to the returned `upload_url` succeeds (HTTP 200 from object storage).
4. `POST /kyc/applications/{app_id}/documents/upload` with `document_type: "nid_front"` and the returned `storage_key` returns HTTP 200 with a `document_id`.
5. `POST /kyc/applications/{app_id}/ocr/nid` with both registered keys returns HTTP 200 with all `extracted_*` fields populated and a `confidence_score` between 0 and 1.
6. The `ocr_extractions` table contains a new row with `kyc_application_id` equal to `app_id` after a successful OCR call.
7. An audit log entry with `action = "create"`, `entity_type = "ocr_extractions"`, and `nid_image_captured: true` is written to the `audit_logs` table.
8. Calling `POST /ocr/nid` without first registering both documents returns HTTP 422 with message "NID images must be registered before OCR".
9. Frontend: after landing on the NID step, the user sees two upload panels (front and back) before any NID text input fields are shown.
10. Frontend: after uploading both images, the OCR spinner appears, and then the review panel is shown pre-filled with extracted values.
11. Frontend: the NID number and DOB fields in Phase C are pre-filled from OCR but remain editable.
12. Frontend: if `confidence_score < 0.8`, an amber warning alert is displayed above the extracted fields.
13. Frontend: clicking "Validate NID" calls `POST /verify/nid` with the (possibly user-corrected) NID number and DOB; on success the step advances to biometric verification.
14. Frontend: clicking "Back" in Phase C clears upload state and returns to Phase A (both upload panels empty).
15. Store persistence: reloading the page mid-step restores `nidFrontKey`, `nidBackKey`, and `ocrResult` from Zustand persist storage.

---

## Implementation Order

- [ ] 1. (backend) Add `mock_ocr_service` in `app/services/mock_ocr.py` — returns a fixed dict of plausible extracted fields including `raw_json` and `confidence_score: 0.92`.
- [ ] 2. (backend) Add `CRUDVerification.run_ocr_extraction()` in `app/crud/crud_verification.py` — SELECTs existing `KYCDocument` rows, calls `mock_ocr_service.extract()`, INSERTs `OCRExtraction` row.
- [ ] 3. (backend) Add `GET /kyc/applications/{app_id}/nid-upload-url` endpoint in `app/api/v1/verification.py` — presigned PUT URL for `nid_front` and `nid_back`.
- [ ] 4. (backend) Add `POST /kyc/applications/{app_id}/ocr/nid` endpoint in `app/api/v1/verification.py` — calls `run_ocr_extraction`, records audit event.
- [ ] 5. (backend) Modify existing `POST /verify/nid` audit event in `app/api/v1/verification.py` to include `nid_image_captured` flag.
- [ ] 6. (frontend) Add `OCRResult`, `NIDUploadUrlResponse`, `NIDOCRRequest` types to `ekyc-frontend/src/types/api.ts`.
- [ ] 7. (frontend) Add `getNIDUploadUrl`, `runOCR`, and `uploadFileBlob` to `ekyc-frontend/src/api/services.ts`.
- [ ] 8. (frontend) Add `nidFrontKey`, `nidBackKey`, `ocrResult` state fields and setters to `ekyc-frontend/src/store/onboardingStore.ts`.
- [ ] 9. (frontend) Refactor `NIDStep` in `OnboardingPage.tsx` — add Phase A (upload panels), Phase B (OCR spinner), Phase C (review + existing validate flow).
- [ ] 10. (frontend) Apply same NID upload + OCR sub-flow to `AgentOnboardingPage.tsx` `NIDStep` for consistency in the Assisted channel.

---

## Testing Checklist

### Backend (Swagger UI at `/docs` or curl)
1. Authenticate as a customer (POST `/auth/customer/send-otp` → `verify-otp`).
2. Create an application (POST `/kyc/applications`).
3. `GET /kyc/applications/{id}/nid-upload-url?side=front` → confirm `upload_url` and `storage_key` returned.
4. PUT a JPEG file to the `upload_url` → confirm HTTP 200.
5. `POST /kyc/applications/{id}/documents/upload` with `document_type: "nid_front"` → confirm `document_id` returned.
6. Repeat steps 3–5 for `side=back` with `document_type: "nid_back"`.
7. `POST /kyc/applications/{id}/ocr/nid` with both `storage_key` values → confirm all `extracted_*` fields and `confidence_score` in response.
8. Query `SELECT * FROM ocr_extractions WHERE kyc_application_id = '{id}'` → confirm row exists.
9. `GET /audit/logs` → confirm entry with `entity_type = "ocr_extractions"` and `nid_image_captured: true`.
10. `POST /kyc/applications/{id}/ocr/nid` without prior document upload → confirm HTTP 422.
11. `GET /nid-upload-url?side=invalid` → confirm HTTP 422.

### Frontend (browser walkthrough)
1. Log in as customer `01712000001`, start New Application.
2. Complete Pre-check step → land on NID step.
3. Confirm two upload panels are shown ("NID Front", "NID Back") with no text inputs visible yet.
4. Upload a JPEG for front → confirm thumbnail appears, progress indicator, success state.
5. Upload a JPEG for back → confirm thumbnail appears.
6. Click "Next: Extract Data" → confirm spinner appears with "Reading your NID card…".
7. Confirm extracted fields appear pre-filled in Phase C review panel.
8. Confirm confidence score badge colour (green for mock score 0.92).
9. Confirm NID number and DOB fields are editable.
10. Click "Validate NID" → confirm success alert with name, step advances to Face Match.
11. Reload page → confirm store restores upload keys and OCR result (Phase C shown directly).

### Edge Cases
- Upload a non-image file (e.g., PDF) → frontend file input `accept="image/*"` rejects it.
- Simulate OCR failure (mock returns `confidence_score: 0.3`) → amber warning alert appears.
- Upload front image twice (retake) → document versioning increments; latest version used for OCR.
- Call OCR with a `nid_front_key` that doesn't match any `KYCDocument` row → HTTP 422.
- Cross-user access: call OCR endpoint with another user's `app_id` → HTTP 403.
