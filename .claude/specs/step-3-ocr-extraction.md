# Step 3 — OCR Extraction (NID Front + Back) Spec

## Overview

OCR extraction is the mechanism by which the system reads a customer's physical National ID card
image — both front and back — and converts it into structured, machine-readable text fields
(name in Bangla and English, NID number, date of birth, address, parents' names). This implements
BFIU Circular No. 29 (2026) Section on Face-matching, which mandates "OCR functionality:
mandatory capture in Bangla and English" as a prerequisite to biometric verification. In the
pipeline it sits inside Step 3 (NID Verification): after the customer uploads NID images to object
storage (Phase A), OCR extraction runs automatically (Phase B), and the extracted fields pre-fill
the NID number + DOB form that is then validated against the Election Commission database (Phase C).
The current implementation is complete for mock/dev use but has no production OCR provider
integration, a hardcoded confidence threshold, and no field-level quality metadata.

---

## Regulatory Requirements

- **OCR mandatory in Bangla and English** — BFIU 2026: "OCR Functionality: Mandatory capture in
  Bangla and English." The system must extract `extracted_name_bn` and `extracted_name_en`; if
  either is absent the extraction is incomplete.
- **Authenticity assurance** — "Highest level of assurance and authenticity" for identity data;
  OCR results must come from actual image analysis, not user-supplied text.
- **NID card accepted** — Guidelines apply only to natural persons with a valid NID issued by the
  Election Commission of Bangladesh. OCR must operate on that specific card layout.
- **Biometric step gated on NID data** — Face-match (`POST /verify/face`) requires `nid_number`
  and `date_of_birth`. These must be derived from a verified OCR extraction, not typed-in data
  alone.
- **Immutable audit trail** — "All successful and unsuccessful onboarding attempts must be logged
  with matching parameters." Every OCR call (pass or fail) must be written to `audit_logs`.
- **5-year retention** — All digital KYC data including OCR records retained from account closure.
- **Data residency** — All OCR processing and storage must remain within Bangladesh; cloud OCR
  providers must use BD-hosted endpoints or on-premise solutions.

---

## Current State

### Backend

| File | What exists | Lines |
|---|---|---|
| `app/services/mock_ocr.py` | `MockOCRService.extract()` — returns fixed Bangla+English fields; supports 4 scenarios via `MOCK_OCR_SCENARIO` env var | 1–52 |
| `app/crud/crud_verification.py` | `run_ocr_extraction()` — verifies both doc rows exist, calls OCR service, enforces 3 validation gates, persists `OCRExtraction` | 300–396 |
| `app/api/v1/verification.py` | `GET /nid-upload-url` — presigned PUT URL with side + MIME + size validation | 150–169 |
| `app/api/v1/verification.py` | `POST /ocr/nid` — calls CRUD, audits success + failure | 172–216 |
| `app/api/v1/verification.py` | `POST /documents/upload` — registers `KYCDocument` row | 262–281 |
| `app/core/storage.py` | `generate_presigned_put()` / `generate_presigned_get()` — boto3 S3v4 | full file |
| `app/models/onboarding.py` | `OCRExtraction` SQLModel — all fields including `confidence_score: float | None` | 264–298 |
| `app/core/config.py` | Storage settings (bucket, endpoint, keys); no OCR provider settings | full file |

### CRUD Validation Gates (already implemented)
1. **Gate 1** — `confidence_score < MIN_OCR_CONFIDENCE (0.60)` → HTTP 422
2. **Gate 2** — `extracted_nid` or `extracted_dob` missing/blank → HTTP 422
3. **Gate 3** — NID not matching `\d{10}|\d{13}|\d{17}` → HTTP 422

### Frontend

| File | What exists |
|---|---|
| `src/types/api.ts:242–256` | `OCRResult` interface — all fields, single aggregate `confidence_score` |
| `src/api/services.ts:60–68` | `verificationAPI.getNIDUploadUrl`, `runOCR`, `uploadDocument`; `uploadFileBlob` |
| `src/store/onboardingStore.ts` | `nidFrontKey`, `nidBackKey`, `ocrResult` state + setters |
| `OnboardingPage.tsx NIDStep` | Phase A (upload panels), Phase B (OCR spinner + retry/manual), Phase C (review + confidence block) |
| `AgentOnboardingPage.tsx NIDStep` | Identical 3-phase structure |

### Stubs / Gaps

- **`app/services/mock_ocr.py`** — only service implementation. No real OCR provider. Ignores
  actual image content entirely.
- `MIN_OCR_CONFIDENCE = 0.60` hardcoded in `crud_verification.py`; not configurable via env.
- No `OCR_PROVIDER`, `OCR_API_KEY`, `OCR_API_ENDPOINT` in `app/core/config.py` or `.env.example`.
- `OCRResult` has only a single aggregate `confidence_score`; no field-level confidence.
- No `ocr_provider` metadata field — can't audit which engine produced a result.
- No image quality pre-check (blur, glare, rotation) before sending to OCR.
- No `attempt_number` on `OCRExtraction`; re-runs create new rows but old rows aren't marked
  superseded.
- `raw_json` is unbounded `sa.Text`; large provider payloads (coordinates, per-word confidence)
  could bloat the DB.
- Date-of-birth parsing assumes ISO format; real cards may have Bangla numerals or dd/mm/yyyy.

---

## Gaps — What Needs to Be Built

### Backend

**1. Production OCR service class**
- What is missing: a concrete implementation of the OCR service that calls a real provider API.
- Why needed: regulatory mandate for actual image-to-text extraction; mock is not acceptable in
  production.
- File: **`app/services/ocr_service.py`** (new) — implement `OCRService` base class +
  `AWSTextractOCRService` (or equivalent) that calls AWS Textract/Google Vision using
  storage keys to fetch images from S3, processes OCR, and returns the same dict shape as mock.

**2. OCR provider settings**
- What is missing: `OCR_PROVIDER`, `OCR_API_KEY`, `OCR_API_ENDPOINT`, `OCR_CONFIDENCE_THRESHOLD`
  in `app/core/config.py` and `.env.example`.
- Why needed: removes hardcoded constant, makes threshold tunable without code change, and allows
  switching providers via environment (useful for staging vs prod).
- File: `app/core/config.py` — add 4 new `settings` fields.

**3. Service factory / provider switch**
- What is missing: code that reads `OCR_PROVIDER` and returns the correct service instance.
- Why needed: allows mock in dev/test, real provider in staging/prod, without changing CRUD code.
- File: `app/services/ocr_service.py` — `get_ocr_service() -> BaseOCRService` factory; CRUD
  imports this factory instead of `mock_ocr_service` directly.

**4. Field-level confidence + provider metadata in `OCRExtraction` model**
- What is missing: `ocr_provider`, `field_confidence_json`, `quality_flags_json` columns.
- Why needed: BFIU audit trail requires traceability; field-level confidence enables smarter
  per-field warnings in the UI; quality flags enable pre-submission image rejection.
- File: `app/models/onboarding.py` — add 3 new nullable columns; new Alembic migration required.

**5. DOB normalisation layer**
- What is missing: production NID cards use `dd/mm/yyyy` and sometimes Bangla numerals; the
  current parser only handles ISO `YYYY-MM-DD`.
- Why needed: silent parse failure → `extracted_dob = None` → Gate 2 rejects valid extractions.
- File: `app/crud/crud_verification.py` — replace the single `fromisoformat()` call with a
  `_parse_dob(raw: str) -> date | None` helper that tries multiple formats.

**6. `raw_json` size guard**
- What is missing: no length limit on the `raw_json` field before DB insert.
- Why needed: AWS Textract can return 500 KB+ of coordinate data per page; unchecked this bloats
  `ocr_extractions` table.
- File: `app/crud/crud_verification.py` — truncate or compress `raw_json` to max 64 KB before
  persisting; store full response in S3 if > threshold.

**7. Attempt number tracking on OCR re-runs**
- What is missing: `OCRExtraction` has no attempt counter; when a user retakes photos and re-runs
  OCR, the old row is not superseded and there's no ordering.
- Why needed: audit trail clarity; easy to identify latest valid extraction per application.
- File: `app/models/onboarding.py` — add `attempt_number: int` column (default 1, increments per
  app). `app/crud/crud_verification.py` — query max attempt and increment.

### Frontend

**8. Field-level confidence display in Phase C**
- What is missing: Phase C shows only one aggregate badge; if per-field confidence is available
  from production OCR, individual field warnings should appear inline.
- Why needed: user can immediately see which specific field (e.g., DOB) has low confidence rather
  than re-taking both photos.
- File: `src/pages/onboarding/OnboardingPage.tsx` and `AgentOnboardingPage.tsx` — render inline
  amber indicator next to each field if `field_confidence.{field} < 0.7`.

**9. OCR provider indicator (dev/debug)**
- What is missing: no indication in Phase C of which OCR engine produced the result.
- Why needed: during integration testing the team needs to know mock vs real provider results.
- File: `src/pages/onboarding/OnboardingPage.tsx` — show `ocrResult.ocr_provider` as a small
  `<code>` chip in dev mode (`import.meta.env.DEV`).

**10. `OCRResult` TypeScript type — extend for production fields**
- What is missing: `field_confidence`, `ocr_provider`, `quality_flags`, `attempt_number` fields.
- Why needed: TypeScript type safety when consuming extended OCR response from production backend.
- File: `src/types/api.ts` — extend `OCRResult` interface.

---

## Backend Specification

### New / Modified Endpoints

#### `POST /kyc/applications/{app_id}/ocr/nid` (no HTTP signature change)

No changes to URL, auth, or request body. Internal behaviour changes:
- CRUD now calls `get_ocr_service()` factory instead of `mock_ocr_service` directly.
- On success: `data` dict adds `ocr_provider` and `attempt_number` fields.
- Failure audit already implemented.

#### `GET /kyc/applications/{app_id}/nid-upload-url` (no change)

Already complete. No modifications needed.

### New / Modified CRUD Methods

#### `CRUDVerification.run_ocr_extraction()` (modify)

**File:** `app/crud/crud_verification.py`

**Changes:**
1. Replace `from app.services.mock_ocr import mock_ocr_service` import with
   `from app.services.ocr_service import get_ocr_service`.
2. Replace `await mock_ocr_service.extract(...)` with `await get_ocr_service().extract(...)`.
3. Replace single `fromisoformat()` call with `_parse_dob(raw)` helper.
4. Truncate `raw_json` if `len(raw_json) > 65_536`; store original key in `raw_json` as pointer.
5. Query `MAX(attempt_number)` for this `app_id` and set `attempt_number = max + 1` (or 1 if none).
6. Pass new fields to `OCRExtraction` constructor: `ocr_provider`, `field_confidence_json`,
   `quality_flags_json`, `attempt_number`.

**Add helper (module-level):**
```python
def _parse_dob(raw: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    # Attempt Bangla numeral normalisation then retry
    normalised = _normalise_bangla_digits(raw)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(normalised, fmt).date()
        except ValueError:
            continue
    return None

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

def _normalise_bangla_digits(s: str) -> str:
    return s.translate(_BANGLA_DIGITS)
```

### New CRUD / Service — `app/services/ocr_service.py`

**New file.** Follows same singleton pattern as `mock_ec.py` and `mock_ocr.py`.

```python
class BaseOCRService(ABC):
    @abstractmethod
    async def extract(self, nid_front_key: str, nid_back_key: str) -> dict:
        ...

class MockOCRService(BaseOCRService):
    # Moved from mock_ocr.py unchanged (keeps mock_ocr.py as thin shim for backwards compat)
    ...

class AWSTextractOCRService(BaseOCRService):
    async def extract(self, nid_front_key: str, nid_back_key: str) -> dict:
        # 1. Generate presigned GET URLs for both images (300s TTL)
        # 2. POST both URLs to AWS Textract DetectDocumentText or AnalyzeDocument
        # 3. Parse Textract response: locate name, NID, DOB, address blocks using
        #    bounding-box heuristics (NID card layout is known)
        # 4. Build and return the standard dict with all required fields
        # 5. Store full Textract JSON in raw_json (truncated if > 64 KB)
        ...

def get_ocr_service() -> BaseOCRService:
    provider = settings.OCR_PROVIDER  # "mock" | "aws_textract" | "google_vision"
    if provider == "aws_textract":
        return AWSTextractOCRService()
    return MockOCRService()  # default / dev fallback
```

**Return dict contract** (must be returned by ALL implementations):

```python
{
    "extracted_name_en":      str | None,
    "extracted_name_bn":      str | None,
    "extracted_nid":          str | None,       # raw, will be stripped + validated by CRUD
    "extracted_dob":          str | None,       # raw date string, will be parsed by CRUD
    "extracted_address":      str | None,
    "extracted_fathers_name": str | None,
    "extracted_mothers_name": str | None,
    "confidence_score":       float | None,     # 0.0–1.0 aggregate
    "field_confidence":       dict | None,      # per-field scores, optional
    "ocr_provider":           str,              # "mock" | "aws_textract" | "google_vision"
    "quality_flags":          dict | None,      # {"glare": bool, "blur": bool, ...}, optional
    "source_front_key":       str,
    "source_back_key":        str,
    "raw_json":               str,              # full provider response (may be truncated)
}
```

### Data Model Changes

**Table:** `ocr_extractions`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `attempt_number` | `Integer` | No | 1 | Increments per app; `MAX(attempt_number) + 1` at insert |
| `ocr_provider` | `VARCHAR(50)` | Yes | `None` | e.g. `"mock"`, `"aws_textract"`, `"google_vision"` |
| `field_confidence_json` | `sa.Text` | Yes | `None` | JSON string of per-field confidence scores |
| `quality_flags_json` | `sa.Text` | Yes | `None` | JSON string of image quality flags |

**New Alembic migration required:** Yes — `0002_ocr_extraction_extended.py`

```python
def upgrade():
    op.add_column("ocr_extractions", sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("ocr_extractions", sa.Column("ocr_provider", sa.String(50), nullable=True))
    op.add_column("ocr_extractions", sa.Column("field_confidence_json", sa.Text(), nullable=True))
    op.add_column("ocr_extractions", sa.Column("quality_flags_json", sa.Text(), nullable=True))
```

**Settings additions** (`app/core/config.py`):

```python
OCR_PROVIDER: str = "mock"                  # "mock" | "aws_textract" | "google_vision"
OCR_API_KEY: str = ""                       # Provider API key (blank = use IAM role for AWS)
OCR_API_ENDPOINT: str = ""                  # Provider endpoint (blank = use SDK default)
OCR_CONFIDENCE_THRESHOLD: float = 0.60      # Replaces hardcoded MIN_OCR_CONFIDENCE
```

Also update `.env.example` with these four keys and documentation comments.

---

## Frontend Specification

### onboardingStore Changes

No new store fields required. `ocrResult: OCRResult | null` is sufficient; the new fields
(`ocr_provider`, `field_confidence`, etc.) are part of the `OCRResult` type and will be
transparently available once the type is extended.

### New / Modified Pages or Components

#### `OnboardingPage.tsx` — `NIDStep` — Phase C (modify)

**File:** `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`

Add field-level confidence indicators next to each pre-filled input when `field_confidence` is
present on `ocrResult`:

```tsx
// After NID Number input:
{store.ocrResult?.field_confidence?.nid !== undefined &&
 store.ocrResult.field_confidence.nid < 0.7 && (
  <p className="text-xs text-amber-600 mt-1">
    NID field confidence: {(store.ocrResult.field_confidence.nid * 100).toFixed(0)}% — verify carefully
  </p>
)}

// After DOB input:
{store.ocrResult?.field_confidence?.dob !== undefined &&
 store.ocrResult.field_confidence.dob < 0.7 && (
  <p className="text-xs text-amber-600 mt-1">
    DOB field confidence: {(store.ocrResult.field_confidence.dob * 100).toFixed(0)}% — verify carefully
  </p>
)}
```

Add dev-mode provider chip in Phase C header:

```tsx
{import.meta.env.DEV && store.ocrResult?.ocr_provider && (
  <code className="text-xs bg-surface-100 text-surface-500 px-1.5 py-0.5 rounded">
    OCR: {store.ocrResult.ocr_provider}
  </code>
)}
```

Add attempt number display below header (helps support staff diagnose re-runs):

```tsx
{store.ocrResult?.attempt_number && store.ocrResult.attempt_number > 1 && (
  <p className="text-xs text-surface-400">Extraction attempt {store.ocrResult.attempt_number}</p>
)}
```

#### `AgentOnboardingPage.tsx` — `NIDStep` — Phase C (modify)

Apply identical field-level confidence indicators and dev-mode provider chip.

### API Service Additions

No new service functions needed. `verificationAPI.runOCR` is already wired. The new response
fields (`ocr_provider`, `field_confidence`, `attempt_number`) will be returned by the backend and
deserialized automatically once the `OCRResult` TypeScript type is extended.

### TypeScript Types

**`OCRResult`** — extend in `ekyc-frontend/src/types/api.ts`:

```typescript
export interface OCRResult {
  // ── Existing fields (unchanged) ──
  id: string
  kyc_application_id: string
  document_id: string
  extracted_name_en: string | null
  extracted_name_bn: string | null
  extracted_nid: string | null
  extracted_dob: string | null
  extracted_address: string | null
  extracted_fathers_name: string | null
  extracted_mothers_name: string | null
  confidence_score: number | null
  raw_json: string
  created_at: string

  // ── New fields (optional for backwards compat with mock) ──
  attempt_number?: number
  ocr_provider?: string
  field_confidence?: {
    name_en?: number
    name_bn?: number
    nid?: number
    dob?: number
    address?: number
    fathers_name?: number
    mothers_name?: number
  }
  quality_flags?: {
    glare_detected?: boolean
    blur_detected?: boolean
    rotation_detected?: boolean
    image_too_dark?: boolean
  }
}
```

All new fields are optional (`?`) so existing mock responses continue to deserialise without error.

---

## Acceptance Criteria

1. With `OCR_PROVIDER=mock`, `POST /ocr/nid` returns 200 with all existing fields unchanged —
   no regression from current golden path.
2. With `OCR_PROVIDER=aws_textract` (or equivalent) and valid NID images, `POST /ocr/nid`
   returns 200 with `ocr_provider: "aws_textract"` and real extracted fields from the images.
3. `POST /ocr/nid` with `MOCK_OCR_SCENARIO=low_confidence` returns 422 with "confidence too low"
   (existing gate still fires with threshold read from `settings.OCR_CONFIDENCE_THRESHOLD`).
4. `OCR_CONFIDENCE_THRESHOLD=0.80` in env raises the bar; a mock returning 0.75 now fails.
5. `OCR_CONFIDENCE_THRESHOLD=0.50` in env lowers the bar; a mock returning 0.60 now passes.
6. Date "15/05/1990" (dd/mm/yyyy format) is correctly parsed to `1990-05-15`; not rejected.
7. Date "১৫/০৫/১৯৯০" (Bangla numerals) is correctly normalised and parsed to `1990-05-15`.
8. An invalid date string returns `extracted_dob: null` (not a 500 server error).
9. After a retake (2nd OCR call on same app), the new `OCRExtraction` row has `attempt_number=2`;
   the first row has `attempt_number=1` and is not deleted.
10. `raw_json` exceeding 64 KB is truncated before DB insert; no DB error.
11. `GET /audit/logs` shows `entity_type="ocr_extractions"` rows with `ocr_provider` in
    `new_value` for both success and failure cases.
12. Frontend Phase C: when `ocrResult.field_confidence.nid < 0.7`, an amber per-field note
    appears below the NID input.
13. Frontend Phase C: when `import.meta.env.DEV`, a `<code>` chip shows `ocrResult.ocr_provider`.
14. Frontend Phase C: `attempt_number > 1` displays "Extraction attempt N" subtitle.
15. After a retake (Zustand `ocrResult` cleared, new OCR triggered), Phase B spinner re-appears
    and Phase C re-renders with attempt 2 data.

---

## Implementation Order

- [ ] 1. (backend) Add `OCR_PROVIDER`, `OCR_API_KEY`, `OCR_API_ENDPOINT`, `OCR_CONFIDENCE_THRESHOLD`
         to `app/core/config.py`; update `.env.example`
- [ ] 2. (backend) Replace hardcoded `MIN_OCR_CONFIDENCE = 0.60` in `crud_verification.py`
         with `settings.OCR_CONFIDENCE_THRESHOLD`
- [ ] 3. (backend) Create `app/services/ocr_service.py` with `BaseOCRService` ABC,
         `MockOCRService` (mirrors existing mock), and `get_ocr_service()` factory
- [ ] 4. (backend) Move `mock_ocr.py` logic into `ocr_service.py`; keep `mock_ocr.py` as a
         one-line shim (`from app.services.ocr_service import MockOCRService as mock_ocr_service`)
         for backwards compatibility
- [ ] 5. (backend) Update `crud_verification.py` to import `get_ocr_service` instead of
         `mock_ocr_service`; call `get_ocr_service().extract()`
- [ ] 6. (backend) Add `_parse_dob()` and `_normalise_bangla_digits()` helpers to
         `crud_verification.py`; replace `fromisoformat` with `_parse_dob`
- [ ] 7. (backend) Add `attempt_number`, `ocr_provider`, `field_confidence_json`,
         `quality_flags_json` columns to `OCRExtraction` model in `app/models/onboarding.py`
- [ ] 8. (backend) Write Alembic migration `0002_ocr_extraction_extended.py` for the 4 new columns
- [ ] 9. (backend) Update `run_ocr_extraction()` in `crud_verification.py` to:
         (a) query max attempt_number and increment,
         (b) truncate raw_json > 64 KB,
         (c) persist new columns
- [ ] 10. (backend) Update `POST /ocr/nid` response dict in `verification.py` to include
          `attempt_number`, `ocr_provider`, `field_confidence`, `quality_flags`
- [ ] 11. (backend) Implement `AWSTextractOCRService` (or chosen production provider) in
          `ocr_service.py` — fetch images via presigned GET, call provider, parse response to
          standard dict shape
- [ ] 12. (frontend) Extend `OCRResult` interface in `src/types/api.ts` with optional fields:
          `attempt_number`, `ocr_provider`, `field_confidence`, `quality_flags`
- [ ] 13. (frontend) Add field-level confidence notes below NID and DOB inputs in
          `OnboardingPage.tsx` Phase C
- [ ] 14. (frontend) Add dev-mode provider chip and attempt number display in `OnboardingPage.tsx`
          Phase C header
- [ ] 15. (frontend) Apply steps 13–14 identically to `AgentOnboardingPage.tsx` Phase C

---

## Testing Checklist

### Backend (Swagger / uvicorn)

1. `uvicorn app.main:app --reload`; authenticate as customer, create application.
2. Upload NID front + back via documents/upload. `POST /ocr/nid` → confirm 200, mock fields, no
   `ocr_provider` yet (step 3 not done) OR `ocr_provider: "mock"` once step 3 is done.
3. Set `OCR_CONFIDENCE_THRESHOLD=0.95` in env, restart, retry → confirm 422 (mock returns 0.92,
   now below threshold). Confirms settings wiring works.
4. `POST /ocr/nid` twice on same app → confirm second response has `attempt_number: 2`.
5. `SELECT attempt_number, ocr_provider FROM ocr_extractions WHERE kyc_application_id = '...'`
   → two rows: attempt_number 1 and 2.
6. Set `MOCK_OCR_SCENARIO=missing_nid` → confirm 422 and audit `action=failed`.
7. Test `_parse_dob` with a unit test covering "1990-05-15", "15/05/1990", "১৫/০৫/১৯৯০", and
   garbage string → confirm correct dates and None respectively.
8. With `OCR_PROVIDER=aws_textract` (staging only): upload real NID card photo →
   confirm extracted fields are populated from real card text.

### Frontend (browser)

1. `npm run dev` in `ekyc-frontend/`; log in, start application, pass pre-check.
2. Upload valid front + back JPEG → thumbnails appear, Phase B spinner shows.
3. Phase C: confirm green confidence badge (92% mock).
4. In dev browser: confirm `<code>OCR: mock</code>` chip in Phase C header.
5. Retake photos → Phase A resets, re-upload, Phase B triggers again.
6. Phase C after retake: confirm "Extraction attempt 2" subtitle.
7. If backend returns `field_confidence.nid < 0.7` (requires custom mock scenario): confirm amber
   note below NID input.

### Edge Cases

- `extracted_dob = "1990/5/15"` (no zero-padding): should parse correctly.
- `extracted_dob = "N/A"` or `"—"`: should return `null`, not raise.
- `raw_json` of 200 KB returned by real provider: confirm truncated to 64 KB in DB.
- Concurrent uploads: two sessions hitting OCR simultaneously for same app should both increment
  attempt_number correctly (use DB-level MAX query, not application cache).
- `OCR_PROVIDER` set to unknown value → `get_ocr_service()` falls back to mock (no crash).
- `field_confidence` absent from mock response: frontend renders no per-field notes (optional
  chaining handles gracefully).
