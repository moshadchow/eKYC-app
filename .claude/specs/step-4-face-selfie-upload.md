# Step 4 — Face Selfie Upload Spec

## Overview

Face-matching is the biometric verification method for self check-in onboarding (non-assisted channel). After NID validation, the customer captures a live selfie that must be matched against the EC database photograph. The current implementation captures the selfie in the browser (canvas → JPEG data URL) but **never uploads the image anywhere** — it fabricates a storage key client-side (`selfies/{appId}-{timestamp}.jpg`) and passes it directly to `POST /kyc/applications/{app_id}/verify/face`. The backend `FaceMatchRequest` model accepts `selfie_storage_key` as a required string but does nothing with it (the mock EC service ignores it). In production, the actual image bytes must reach object storage **before** the verification call so the real EC API can retrieve and compare the image. This gap lives entirely in Step 4 of the pipeline, between NID capture (Step 3) and profile entry (Step 5), and must be closed before production.

---

## Regulatory Requirements

- **Biometric assurance**: BFIU 2026 Circular 29 requires "the highest level of assurance and authenticity" for identity data — a fabricated storage key with no actual image fails this requirement.
- **Liveness detection**: ISO 30107-3 PAD Level 2 passive liveness is mandated. The current implementation captures a canvas screenshot with no liveness enforcement; the storage pipeline must preserve the full-resolution capture for the EC liveness check.
- **Image quality mandates**: High-resolution camera/webcam capture, adequate white lighting, white uncluttered background — the live image must actually reach the EC API.
- **Immutable audit trail**: BFIU mandates a "digital log" of all successful and unsuccessful onboarding attempts capturing the specific matching parameters and verification results from the EC server. Without a real upload, the stored `selfie_storage_key` in the audit log is meaningless.
- **Data residency**: All customer data must be stored on locally hosted servers or private cloud servers within Bangladesh. The object storage bucket used for selfies must be locally hosted; no cross-border transmission.
- **5-year retention**: Digital KYC data including biometric images must be retained for 5 years from account closure.
- **Verification limits**: Max 10 face-match attempts per session, max 3 sessions total (already enforced by backend; upload failure should not burn an attempt).

---

## Current State

### Backend
- **`POST /kyc/applications/{app_id}/verify/face`** — `app/api/v1/verification.py:76–104`
  - Accepts `FaceMatchRequest` with `selfie_storage_key: str` (required)
  - Passes storage key to `crud_verification.run_face_match()` but only stores it in the `biometric_verifications` table — never fetches or validates the file exists
  - Mock EC service (`app/services/mock_ec.py:87–107`) ignores `selfie_storage_key` entirely, returns random score 70–98
- **`POST /kyc/applications/{app_id}/documents/upload`** — `app/api/v1/verification.py:149–167`
  - Registers document metadata **after** a presigned-URL binary upload
  - Docstring says "Register document metadata after binary upload via presigned URL" — implies presigned URL upload is the intended pattern
  - **No presigned URL generation endpoint exists anywhere in the codebase**
- **CRUD**: `app/crud/crud_verification.py` — `run_face_match()` stores `selfie_storage_key` in the DB row but does not validate or retrieve the file

### Frontend
- **`OnboardingPage.tsx` — `FaceMatchStep`** (lines 167–273):
  - Camera stream → canvas `drawImage` → `toDataURL('image/jpeg', 0.85)` — produces a base64 data URL string in memory
  - `handle()` at line 198: fabricates `selfies/${store.application.id}-${Date.now()}.jpg` as `storageKey`, never uploads the canvas data
  - Comment at line 198: `// In production: upload selfie to S3 first, get storage_key back`
- **`AgentOnboardingPage.tsx` — `FaceMatchStep`** (line 298):
  - Same pattern: `selfies/${appId}-${Date.now()}.jpg` generated client-side, never uploaded
- **No upload service function** in `ekyc-frontend/src/api/services.ts`
- **No presigned URL API call** anywhere in the frontend

### Gaps Summary
| Layer | Gap |
|---|---|
| Backend | No `GET /kyc/applications/{app_id}/selfie-upload-url` presigned URL endpoint |
| Backend | No validation that the storage key refers to an existing file |
| Frontend | Canvas data URL never POSTed to object storage |
| Frontend | No `uploadSelfie` service function |
| Frontend | `FaceMatchStep` in both `OnboardingPage.tsx` and `AgentOnboardingPage.tsx` need upload step |

---

## Gaps — What Needs to Be Built

### Backend

**1. Presigned URL generation endpoint**
- What is missing: No endpoint to generate a time-limited presigned PUT URL so the browser can upload directly to object storage
- Why needed: The browser cannot write to object storage without credentials; presigned URLs are the standard stateless pattern that avoids routing multi-MB images through the API server
- File: `app/api/v1/verification.py` (new endpoint) + `app/core/storage.py` (new storage client helper)

**2. Object storage client**
- What is missing: No S3/MinIO/compatible storage client exists in the project
- Why needed: The presigned URL endpoint and future document upload must share a configured client
- File: `app/core/storage.py` (new file)

**3. Storage configuration**
- What is missing: No `STORAGE_BUCKET`, `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` in `app/core/config.py`
- Why needed: Client must be configurable for local MinIO (dev) and domestic object storage (prod)
- File: `app/core/config.py`

### Frontend

**1. `uploadSelfie` service function**
- What is missing: No function to PUT the canvas blob to the presigned URL
- Why needed: Browser must perform the actual binary upload before calling `verificationAPI.faceMatch`
- File: `ekyc-frontend/src/api/services.ts`

**2. `getSelfieUploadUrl` service function**
- What is missing: No function to call the presigned URL generation endpoint
- Why needed: Frontend needs a time-limited URL to PUT the image
- File: `ekyc-frontend/src/api/services.ts`

**3. `FaceMatchStep` upload flow in `OnboardingPage.tsx`**
- What is missing: The `handle()` function skips the upload and fabricates a storage key
- Why needed: Real storage key must come from the presigned PUT response, not client-side fabrication
- File: `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`

**4. `FaceMatchStep` upload flow in `AgentOnboardingPage.tsx`**
- Same gap, same fix
- File: `ekyc-frontend/src/pages/agent/AgentOnboardingPage.tsx`

---

## Backend Specification

### New / Modified Endpoints

#### `GET /kyc/applications/{app_id}/selfie-upload-url`
- **Auth**: `CurrentUser` (customer token)
- **Path param**: `app_id: UUID`
- **Query param**: `content_type: str = "image/jpeg"` (optional, validated against allowlist `["image/jpeg", "image/png", "image/webp"]`)
- **Response**: `APIResponse[SelfieUploadUrlResponse]`
  ```python
  class SelfieUploadUrlResponse(BaseModel):
      upload_url: str       # presigned PUT URL, expires in 300s
      storage_key: str      # the object key the client must PUT to and pass to /verify/face
      expires_in: int = 300 # seconds
  ```
- **Business logic**:
  1. Verify application exists and belongs to `current_user.id`
  2. Generate storage key: `f"selfies/{app_id}/{uuid4()}.jpg"`
  3. Call `storage_client.generate_presigned_put(key, content_type, expires=300)`
  4. Return `{upload_url, storage_key, expires_in: 300}`
  5. No DB write — key is ephemeral until the face match call stores it
- **CRUD method**: none needed (stateless URL generation)

### New / Modified CRUD Methods

No CRUD changes needed. The existing `run_face_match()` already stores `selfie_storage_key` in `biometric_verifications`.

### Data Model Changes

No schema changes. `selfie_storage_key` column already exists in `biometric_verifications`.

### New Files / Config

#### `app/core/storage.py`
```python
import boto3
from botocore.config import Config
from app.core.config import settings

_client = None

def get_storage_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="ap-south-1",
        )
    return _client

def generate_presigned_put(key: str, content_type: str, expires: int = 300) -> str:
    client = get_storage_client()
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.STORAGE_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )
```

#### `app/core/config.py` additions
```python
STORAGE_ENDPOINT: str = "http://localhost:9000"   # MinIO for dev
STORAGE_BUCKET: str = "ekyc-uploads"
STORAGE_ACCESS_KEY: str = "minioadmin"
STORAGE_SECRET_KEY: str = "minioadmin"
```

---

## Frontend Specification

### onboardingStore Changes

None — no new step, no new state field needed. The storage key is transient (used once to call `verificationAPI.faceMatch`).

### New / Modified Pages or Components

#### `FaceMatchStep` in `OnboardingPage.tsx` (modified — `handle()` function)

Current (broken):
```ts
const storageKey = captured ? `selfies/${store.application.id}-${Date.now()}.jpg` : 'dev/test-selfie.jpg'
const res = await verificationAPI.faceMatch(store.application.id, { ..., selfie_storage_key: storageKey, ... })
```

New flow:
1. Call `verificationAPI.getSelfieUploadUrl(store.application.id)` → get `{ upload_url, storage_key }`
2. Convert `captured` (base64 data URL) to `Blob` via `fetch(captured).then(r => r.blob())`
3. PUT the blob to `upload_url` with `Content-Type: image/jpeg` using `fetch(upload_url, { method: 'PUT', body: blob, headers: { 'Content-Type': 'image/jpeg' } })`
4. If PUT fails → show error, do NOT call `verificationAPI.faceMatch` (don't burn an attempt)
5. Call `verificationAPI.faceMatch(store.application.id, { ..., selfie_storage_key: storage_key, ... })`

Loading states to display:
- "Uploading selfie…" while presigned URL is being fetched + blob is being PUT
- "Verifying…" while face match runs

#### `FaceMatchStep` in `AgentOnboardingPage.tsx` (modified — same `handle()` change)

Same transformation as above, using local `appId` state instead of `store.application.id`.

### API Service Additions

Add to `verificationAPI` in `ekyc-frontend/src/api/services.ts`:

```ts
getSelfieUploadUrl: (appId: string, contentType = 'image/jpeg') =>
  apiClient.get<APIResponse<SelfieUploadUrlResponse>>(
    `/kyc/applications/${appId}/selfie-upload-url`,
    { params: { content_type: contentType } }
  ),
```

Add standalone function (does not go through `apiClient` — the PUT goes directly to object storage, no auth header):
```ts
export async function uploadSelfieBlob(uploadUrl: string, blob: Blob): Promise<void> {
  const res = await fetch(uploadUrl, {
    method: 'PUT',
    body: blob,
    headers: { 'Content-Type': blob.type || 'image/jpeg' },
  })
  if (!res.ok) throw new Error(`Selfie upload failed: ${res.status} ${res.statusText}`)
}
```

### TypeScript Types

Add to `ekyc-frontend/src/types/api.ts`:
```ts
export interface SelfieUploadUrlResponse {
  upload_url: string
  storage_key: string
  expires_in: number
}
```

---

## Acceptance Criteria

1. `GET /kyc/applications/{app_id}/selfie-upload-url` with valid customer token returns HTTP 200 with `upload_url` (presigned PUT URL) and `storage_key`
2. `GET /kyc/applications/{app_id}/selfie-upload-url` with wrong customer token returns HTTP 403
3. `GET /kyc/applications/{app_id}/selfie-upload-url` with `content_type=application/pdf` returns HTTP 422
4. A browser can PUT a JPEG blob to the returned `upload_url` without auth headers and get HTTP 200 from object storage
5. After the PUT, the object appears in the `ekyc-uploads` bucket under `selfies/{app_id}/{uuid}.jpg`
6. The `storage_key` returned by the presigned URL endpoint matches the key used in the subsequent `POST /verify/face` call
7. If the PUT to object storage fails (network error), the UI shows an error and does NOT call `POST /verify/face` (no attempt wasted)
8. If the presigned URL fetch fails (e.g. 403), the UI shows an error before the camera capture submit button re-enables
9. The `biometric_verifications` row created by `POST /verify/face` stores the real `selfie_storage_key` pointing to the actual uploaded file
10. Customer can still progress through face match with `matched: true` after upload succeeds
11. BFIU compliance: the audit log entry for `biometric_success` / `biometric_failure` contains a `selfie_storage_key` that resolves to a real object in storage

---

## Implementation Order

- [ ] 1. (backend) Add `STORAGE_ENDPOINT`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` settings to `app/core/config.py`
- [ ] 2. (backend) Create `app/core/storage.py` with `get_storage_client()` and `generate_presigned_put()` using boto3
- [ ] 3. (backend) Add `SelfieUploadUrlResponse` Pydantic model and `GET /kyc/applications/{app_id}/selfie-upload-url` endpoint to `app/api/v1/verification.py`
- [ ] 4. (backend) Add `boto3` to project dependencies (`requirements.txt` or `pyproject.toml`)
- [ ] 5. (frontend) Add `SelfieUploadUrlResponse` interface to `ekyc-frontend/src/types/api.ts`
- [ ] 6. (frontend) Add `getSelfieUploadUrl` to `verificationAPI` in `ekyc-frontend/src/api/services.ts`
- [ ] 7. (frontend) Add standalone `uploadSelfieBlob(uploadUrl, blob)` export to `ekyc-frontend/src/api/services.ts`
- [ ] 8. (frontend) Update `FaceMatchStep.handle()` in `OnboardingPage.tsx`: fetch presigned URL → convert data URL to Blob → PUT to object storage → then call `verificationAPI.faceMatch` with real `storage_key`
- [ ] 9. (frontend) Update `FaceMatchStep.handle()` in `AgentOnboardingPage.tsx` with identical change
- [ ] 10. (backend) For local dev: add MinIO service to `docker-compose.yml` (or document manual setup), create `ekyc-uploads` bucket with CORS allowing `PUT` from `localhost:5173`

---

## Testing Checklist

### Backend
- Start MinIO locally: `docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"`
- Create bucket: MinIO console at `http://localhost:9001` → create `ekyc-uploads`
- `GET /kyc/applications/{valid_app_id}/selfie-upload-url` with customer token → should return 200 with presigned URL
- `curl -X PUT "<upload_url>" -H "Content-Type: image/jpeg" --data-binary @test.jpg` → should return 200
- Verify file appears in MinIO bucket under `selfies/` prefix
- `GET /kyc/applications/{valid_app_id}/selfie-upload-url?content_type=application/pdf` → should return 422

### Frontend
- Open `/onboarding`, complete pre-check (self_checkin) + NID step
- Face match step: open camera → capture selfie → click "Verify Face"
- Network tab should show: (1) GET to `/selfie-upload-url`, (2) PUT to MinIO/S3, (3) POST to `/verify/face`
- Verify POST body contains `selfie_storage_key` matching the `storage_key` from step (1) — not a fabricated string
- Verify MinIO bucket contains the uploaded image file
- Test agent face match fallback path in `/agent/onboarding` — same three-request sequence

### Edge Cases
- If MinIO is down: UI should show "Selfie upload failed" before attempting verification — attempt counter must NOT increment
- Presigned URL expiry: if user spends >5 min on camera screen then captures, the PUT will fail (expired URL) — UI must show "Upload expired, please try again" and re-fetch a new URL
- Zero-byte blob: `fetch(dataUrl).blob()` on an empty canvas → PUT should fail → proper error shown
- `content_type=image/png` allowed; `content_type=image/gif` should return 422
- CORS: object storage must allow `PUT` from the frontend origin (`localhost:5173` in dev)
