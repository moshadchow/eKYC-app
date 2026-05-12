# Step 3 — NID Upload Restriction Spec

## Overview
This feature tightens the NID image upload step (Step 3: NID Verification) so that only the two specific NID card scan types — front face and back face of the Bangladesh National Identity Card — are accepted. Currently, the file input allows any image via `accept="image/*"`, and the backend permits any MIME type in the `ALLOWED_NID_CONTENT_TYPES` set without additional format or label validation. The BFIU 2026 e-KYC Guidelines (Face-matching model, Section: "OCR Functionality") mandate that the system must capture both sides of the physical NID card with mandatory OCR extraction in both Bangla and English. Accepting arbitrary files (PDFs, screenshots of random documents, phone gallery photos of non-NID documents) undermines this mandate and produces garbage OCR results or silently passes bad data to the EC verification step. This feature comes after Step 2 (Application creation) and before Phase B (OCR extraction) and Phase C (NID number + DOB validation against EC database).

## Regulatory Requirements
- BFIU 2026 Guidelines, Face-matching model: "OCR Functionality — Mandatory capture in Bangla and English." The OCR must be performed on the physical NID card, which has two distinct sides.
- BFIU 2026, Biometric verification spec: The NID card image capture must meet image quality standards — high-resolution camera/webcam, adequate white lighting, no glare or reflection, preferably white background — implying only an actual card photograph is valid.
- The institution must maintain an immutable audit trail of the specific NID image capture parameters and verification results submitted to the EC server, meaning the document type must unambiguously be an NID side (front or back), not a generic "image".
- Simplified and Regular e-KYC both require NID + DOB verification through EC database query; invalid uploads would cause EC verification failures and must be caught as early as possible.

## Current State

### Backend
- **`app/api/v1/verification.py`** (lines 48–49):
  - `ALLOWED_NID_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}` — validated on presigned URL generation.
  - `ALLOWED_NID_SIDES = {"front", "back"}` — the `side` query param is validated.
  - No validation that the uploaded binary actually contains an NID card image (no server-side image quality check or document-type assertion beyond MIME type).
- **`POST /kyc/applications/{app_id}/documents/upload`** (`verification.py:273`): accepts `document_type: DocumentType` which is an enum. `DocumentType` enum (`app/models/enums.py:76-84`) includes `nid_front`, `nid_back`, but also `customer_photo`, `nominee_photo`, `signature`, `edd_document`, `guardian_nid`, `other`. The upload endpoint does **not** enforce that only `nid_front`/`nid_back` are submitted during the NID verification step — any `DocumentType` value is accepted.
- **`GET /kyc/applications/{app_id}/nid-upload-url`** (`verification.py:151`): correctly restricted by `ALLOWED_NID_SIDES` and `ALLOWED_NID_CONTENT_TYPES`. This endpoint is correctly scoped.

### Frontend
- **`ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`** (line 270):
  - `<input type="file" accept="image/*" capture="environment" ...>`
  - `accept="image/*"` allows ALL image subtypes: BMP, GIF, TIFF, SVG, AVIF, HEIC, etc. — not just JPEG/PNG/WebP.
  - There is a runtime check `file.type.startsWith('image/')` (line 162) which blocks non-image files in the handler, but any image subtype passes.
- **`ekyc-frontend/src/pages/agent/AgentOnboardingPage.tsx`** (line 210):
  - `<input type="file" accept="image/*" capture="environment" ...>` — same broad accept.
  - Runtime check at line 116 is identical: `!file.type.startsWith('image/')`.
- No guidance text tells the user that only the NID card photo is expected (the label says "NID Front"/"NID Back" but doesn't restrict the picker).
- The frontend sends whatever MIME type the file has as `mime_type: file.type || 'image/jpeg'` (OnboardingPage line 191, AgentOnboardingPage line 143) without enforcing an allowlist before the API call.

### Gaps Summary
- Frontend `accept` attribute is too broad — should be `accept="image/jpeg,image/png,image/webp"`.
- Frontend MIME-type validation in `handleFileSelect` only checks `startsWith('image/')` — should check exact allowed types.
- The `POST /documents/upload` endpoint does not validate that during the `nid_capture` step only `document_type` values of `nid_front` or `nid_back` are submitted. A caller could pass `edd_document` for an NID upload slot.
- No file extension hint or user-facing tooltip clarifies acceptable formats.

## Gaps — What Needs to Be Built

### Backend
- **Enforce document_type context on the `/documents/upload` endpoint**: When registering NID documents, validate that the `document_type` is one of `nid_front` or `nid_back`. Currently any enum value is accepted. Add a guard in `verification.py` or `crud_verification`.
- **File size is already validated on presigned URL generation but not on document registration**: Confirm `file_size_bytes > 0` on the `DocumentUploadRequest` to prevent zero-byte registrations.

### Frontend
- **Restrict the HTML `accept` attribute** on the NID file inputs in both `OnboardingPage.tsx` and `AgentOnboardingPage.tsx` from `"image/*"` to `"image/jpeg,image/png,image/webp"`.
- **Strengthen the runtime MIME-type guard** from `startsWith('image/')` to an explicit allowlist check against `['image/jpeg', 'image/png', 'image/webp']`.
- **Add user-facing format hint text** near the upload widget so users know only JPEG, PNG, or WebP photos of the physical NID card are accepted.
- **Update the error message** to be specific: "Only JPEG, PNG, or WebP photos of your NID card are accepted."

## Backend Specification

### Modified Endpoint: `POST /kyc/applications/{app_id}/documents/upload`
- **File**: `app/api/v1/verification.py:273`
- **Auth**: `CurrentActor` (customer or agent)
- **Change**: Add a validation constant and guard for NID document uploads.

**Add constant** (after `ALLOWED_NID_CONTENT_TYPES`, line 49):
```python
ALLOWED_NID_DOCUMENT_TYPES = {DocumentType.nid_front, DocumentType.nid_back}
ALLOWED_NID_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
```

**Add validation block** inside `register_document` handler (before calling `crud_verification.register_document`):
```
if body.document_type in ALLOWED_NID_DOCUMENT_TYPES:
    if body.mime_type not in ALLOWED_NID_MIME_TYPES:
        raise HTTPException(422, detail=f"NID images must be JPEG, PNG, or WebP. Got: {body.mime_type}")
    if body.file_size_bytes <= 0:
        raise HTTPException(422, detail="file_size_bytes must be greater than 0")
```

**Request body schema** (unchanged `DocumentUploadRequest`):
| Field | Type | Required | Validation |
|---|---|---|---|
| `document_type` | `DocumentType` enum | Yes | Must be a valid enum value |
| `storage_key` | `str` | Yes | Non-empty string |
| `mime_type` | `str` | Yes | If `document_type` is `nid_front`/`nid_back`: must be `image/jpeg`, `image/png`, or `image/webp` |
| `file_size_bytes` | `int` | Yes | If `document_type` is `nid_front`/`nid_back`: must be > 0 |
| `checksum_sha256` | `str` | Yes | Length 64 |
| `original_filename` | `str` | No | Optional |

**Response**: `APIResponse[{"document_id": str, "version": int}]` — unchanged.

**Business logic**:
1. Verify the application exists and the actor has access (`crud_verification.get_application`).
2. If `document_type` is `nid_front` or `nid_back`: validate `mime_type` is in `ALLOWED_NID_MIME_TYPES`; validate `file_size_bytes > 0`. Raise HTTP 422 otherwise.
3. Call `crud_verification.register_document(...)`.
4. Record audit event with `document_type` value.
5. Return document ID and version.

### Modified Endpoint: `GET /kyc/applications/{app_id}/nid-upload-url`
- **File**: `app/api/v1/verification.py:151`
- **Current**: Already validates `content_type in ALLOWED_NID_CONTENT_TYPES` and `side in ALLOWED_NID_SIDES`. No changes required — this endpoint is already correctly restricted.

### New / Modified CRUD Methods
No new CRUD methods required. The guard is enforced at the API router layer since it is purely a validation concern, not a business logic or DB concern.

### Data Model Changes
None. `DocumentType.nid_front` and `DocumentType.nid_back` already exist in `app/models/enums.py`. No new columns or migrations needed.

## Frontend Specification

### onboardingStore Changes
None required. Store already tracks `nidFrontKey` and `nidBackKey` independently.

### Modified Component: `OnboardingPage.tsx` — `NIDStep` / Phase A upload section

**File**: `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`

**Change 1 — `accept` attribute** (line 270):
```tsx
// Before
accept="image/*"

// After
accept="image/jpeg,image/png,image/webp"
```

**Change 2 — runtime MIME validation** in `handleFileSelect` (line 162):
```tsx
// Before
if (!file.type.startsWith('image/')) {
  setError('Only image files are accepted (JPEG, PNG, WebP).')
  return
}

// After
const ALLOWED_NID_MIME = ['image/jpeg', 'image/png', 'image/webp']
if (!ALLOWED_NID_MIME.includes(file.type)) {
  setError('Only JPEG, PNG, or WebP photos of your NID card are accepted.')
  return
}
```

**Change 3 — format hint text**: Add a hint below the existing instruction paragraph (after line 258, inside Phase A block):
```tsx
<p className="text-xs text-surface-400">
  Accepted formats: JPEG, PNG, WebP · Max size: 10 MB
</p>
```

**User interactions**:
- User clicks/taps the front or back upload zone — file picker opens filtered to JPEG/PNG/WebP.
- If user bypasses the picker (e.g., drag-and-drop or mobile quirk) and selects a disallowed type, `handleFileSelect` catches it immediately and shows an error alert.
- Error is dismissible via the existing `Alert` component with `onDismiss`.
- Valid file proceeds to S3 presigned upload → document registration → OCR auto-trigger as before.

**Navigation**: Unchanged — both sides must be uploaded before "Next: Extract Data" is enabled.

### Modified Component: `AgentOnboardingPage.tsx` — `NIDStep` / Phase A upload section

**File**: `ekyc-frontend/src/pages/agent/AgentOnboardingPage.tsx`

**Change 1 — `accept` attribute** (line 210):
```tsx
// Before
accept="image/*"

// After
accept="image/jpeg,image/png,image/webp"
```

**Change 2 — runtime MIME validation** in `handleFileSelect` (line 116):
```tsx
// Before
if (!file.type.startsWith('image/')) {
  setError('Only image files are accepted (JPEG, PNG, WebP).')
  return
}

// After
const ALLOWED_NID_MIME = ['image/jpeg', 'image/png', 'image/webp']
if (!ALLOWED_NID_MIME.includes(file.type)) {
  setError('Only JPEG, PNG, or WebP photos of the customer\'s NID card are accepted.')
  return
}
```

**Change 3 — format hint text**: Add the same hint line as OnboardingPage inside the Phase A block.

### API Service Additions
None required. `verificationAPI.getNIDUploadUrl` already passes `contentType` to the backend (which validates it). The `uploadDocument` call already sends `mime_type: file.type` — once the frontend guard is in place, only valid types reach the API.


### TypeScript Types
None required. Existing `DocumentUploadRequest` type and `DocumentType` union already handle `nid_front`/`nid_back`.

## Acceptance Criteria

1. **File picker scope**: When the NID upload zone is clicked in both `OnboardingPage` and `AgentOnboardingPage`, the OS file picker shows only JPEG, PNG, and WebP files as selectable. Other file types appear greyed out.
2. **Runtime rejection — wrong image type**: If a user selects a GIF, BMP, HEIC, AVIF, SVG, or any other non-JPEG/PNG/WebP image (e.g., via drag-and-drop on desktop), the `handleFileSelect` function immediately sets an error: "Only JPEG, PNG, or WebP photos of your NID card are accepted." No API call is made.
3. **Runtime rejection — non-image file**: If a PDF or .doc file is somehow selected, the same error fires (the new check catches it before the old `startsWith('image/')` check would have).
4. **Runtime acceptance — valid types**: A `.jpg`, `.jpeg`, `.png`, or `.webp` file proceeds through upload, document registration, and OCR without error.
5. **Backend rejection — wrong MIME on document registration**: A `POST /kyc/applications/{app_id}/documents/upload` request with `document_type: "nid_front"` and `mime_type: "application/pdf"` returns HTTP 422 with `detail` containing "NID images must be JPEG, PNG, or WebP."
6. **Backend rejection — zero-byte NID doc**: A request with `document_type: "nid_back"` and `file_size_bytes: 0` returns HTTP 422 with `detail` containing "file_size_bytes must be greater than 0."
7. **Backend acceptance — valid NID doc**: A request with `document_type: "nid_front"`, `mime_type: "image/jpeg"`, and `file_size_bytes: 204800` returns HTTP 200 with `document_id`.
8. **Backend acceptance — non-NID document types**: A request with `document_type: "edd_document"` and `mime_type: "application/pdf"` still returns HTTP 200 — the MIME restriction only applies to `nid_front`/`nid_back`.
9. **Hint text visible**: The "Accepted formats: JPEG, PNG, WebP · Max size: 10 MB" line is visible beneath the instruction text on the NID upload screen in both customer and agent flows.
10. **BFIU compliance**: The audit log entry for a successful NID document upload records `document_type: "nid_front"` or `"nid_back"` and a valid MIME type — satisfying the immutable audit trail requirement.

## Implementation Order

- [ ] 1. (backend) In `app/api/v1/verification.py`, add `ALLOWED_NID_DOCUMENT_TYPES` and `ALLOWED_NID_MIME_TYPES` constants after line 49, then add the validation block inside the `register_document` handler before the `crud_verification.register_document` call.
- [ ] 2. (backend) Run the test suite to confirm no existing tests break: `pytest -q`. If any test sends a non-image MIME with `document_type: nid_front`, update the test fixture to use `image/jpeg`.
- [ ] 3. (frontend) In `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`, update the `<input>` `accept` attribute at line 270 from `"image/*"` to `"image/jpeg,image/png,image/webp"`.
- [ ] 4. (frontend) In the same file, update the MIME-type guard in `handleFileSelect` (line 162) to use an explicit allowlist array.
- [ ] 5. (frontend) Add the format hint `<p>` below the lighting instruction paragraph in Phase A of `NIDStep`.
- [ ] 6. (frontend) In `ekyc-frontend/src/pages/agent/AgentOnboardingPage.tsx`, apply the same three changes (accept attribute, MIME guard, hint text) to the agent NID upload section.
- [ ] 7. (frontend) Run TypeScript compilation check: `npx tsc --noEmit` to confirm no type errors.

## Testing Checklist

### Backend — curl/Swagger
1. Request a presigned NID upload URL with an unsupported content_type:
   `GET /kyc/applications/{id}/nid-upload-url?side=front&content_type=image/gif` → expect 422.
2. Register a document with mismatched MIME:
   `POST /kyc/applications/{id}/documents/upload` with `{ "document_type": "nid_front", "mime_type": "application/pdf", ... }` → expect 422 "NID images must be JPEG, PNG, or WebP."
3. Register a document with zero bytes:
   `POST /kyc/applications/{id}/documents/upload` with `{ "document_type": "nid_back", "mime_type": "image/jpeg", "file_size_bytes": 0, ... }` → expect 422.
4. Register a valid NID front: `{ "document_type": "nid_front", "mime_type": "image/png", "file_size_bytes": 1024, ... }` → expect 200.
5. Register an EDD document with PDF MIME: `{ "document_type": "edd_document", "mime_type": "application/pdf", ... }` → expect 200 (not blocked).

### Frontend — browser walkthrough
1. Open the customer onboarding flow to the NID step.
2. Click the "NID Front" upload zone — verify the file picker only shows JPEG/PNG/WebP options (macOS: sidebar shows image filter; Windows: file type dropdown shows those types).
3. On a desktop browser, drag a `.gif` file onto the upload zone — verify the error alert "Only JPEG, PNG, or WebP photos of your NID card are accepted." appears without any network request.
4. On a desktop browser, drag a `.pdf` file — verify same error.
5. Select a valid `.jpg` file — verify it uploads successfully and shows the preview thumbnail.
6. Repeat steps 2–5 in the agent flow at `/agent/onboarding`.

### Edge cases
- **HEIC on iOS Safari**: `file.type` for a HEIC file is `image/heic`. The new allowlist excludes it, so the error fires. Users should be instructed to use the "Photo Library" option which serves JPEG to web browsers, not the Files app which may expose HEIC.
- **WebP from camera on Android Chrome**: `file.type` is `image/webp` — correctly accepted.
- **Empty `file.type`**: Some browsers return an empty string for type if the file extension is unrecognised. The allowlist check `['image/jpeg','image/png','image/webp'].includes('')` returns `false`, so the error fires correctly.
- **File renamed to `.jpg` but containing PDF bytes**: The MIME check relies on the browser-reported MIME type (from extension or content sniffing). The backend checksum and the EC OCR step will reject invalid image data regardless. This is an acceptable boundary; server-side magic-byte validation is out of scope for this feature.
- **10 MB boundary**: A 10,000,001-byte JPEG should be rejected by the existing size check at line 166 — confirm this still fires before the new MIME check.
