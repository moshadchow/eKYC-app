# Step 7 — Document Viewer Spec

## Overview

This feature implements a document viewer UI for agents and admins to preview uploaded KYC documents (NID front/back, selfie, signature, EDD documents) during the compliance review and approval stages. It bridges the gap between document storage (via S3 storage keys) and visual verification by compliance officers and makers/checkers.

This falls under **Step 8 (EDD)** in the pipeline but is needed during the **Maker Review** phase (Step 9) where agents must visually verify identity documents before approval.

## Regulatory Requirements

- **BFIU Section 4.4**: Institutions must retain all KYC documents including NID images, photographs, and signatures for 5 years
- **BFIU Section 6.1**: Maker-checker principle requires the checker to independently verify all supporting documents before approval
- **Record Keeping**: All document views must be logged in the audit trail for regulatory compliance

## Current State

### Backend
- `app/core/storage.py:22-27` — `generate_presigned_put()` exists, but **no `generate_presigned_get()` for retrieval**
- `app/api/v1/applications.py` — stores document metadata with `storage_key` in `kyc_documents` table
- `app/api/v1/compliance.py:205` — EDD documents returned in API with `storage_key` but no retrieval URL

### Frontend
- `ekyc-frontend/src/pages/agent/CompliancePage.tsx:356-365` — lists uploaded EDD documents by name only, no preview
- `ekyc-frontend/src/api/services.ts` — has `uploadDocument()` but **no `getDocumentUrl()` function**
- `ekyc-frontend/src/types/api.ts` — has types for document upload but no view/download types

### Gap
- Storage keys exist in database but **no way to retrieve/display images**
- Agents cannot visually verify NID or selfie during compliance review
- No audit logging for document view events

## Gaps — What Needs to Be Built

### Backend
1. Add `generate_presigned_get()` in `app/core/storage.py` to create temporary download URLs
2. New endpoint `/storage/presigned-get/{storage_key}` to return a presigned URL for any stored document
3. Update audit logging to record document view events

### Frontend
1. New `DocumentViewer` component that takes a `storage_key` and renders the image
2. Integrate into CompliancePage to show NID/signature documents
3. Add EDD document preview capability
4. API function `storageAPI.getPresignedGetUrl(storageKey)` to fetch URL from backend

## Backend Specification

### New / Modified Storage Function

**File**: `app/core/storage.py`

```python
def generate_presigned_get(key: str, expires: int = 300) -> str:
    """Generate a presigned URL for reading an object from S3."""
    return get_storage_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.STORAGE_BUCKET, "Key": key},
        ExpiresIn=expires,
    )
```

### New Endpoint

**File**: `app/api/v1/storage.py` (new file)

```
GET /storage/presigned-get/{storage_key}
```

- **Auth**: `CurrentAgent` (maker/checker/compliance officer/admin)
- **Response**: `APIResponse[{"url": string, "expires_in": int}]`
- **Business logic**:
  1. Validate `storage_key` format (no path traversal allowed)
  2. Call `generate_presigned_get(storage_key)`
  3. Return the URL with expiration time

### Data Model Changes

None required — existing `kyc_documents` table already stores `storage_key`.

## Frontend Specification

### New API Service Function

**File**: `ekyc-frontend/src/api/services.ts`

```typescript
// ── Storage ─────────────────────────────────────────────────────────────────────
export const storageAPI = {
  getPresignedGetUrl: (storageKey: string) =>
    apiClient.get<APIResponse<{ url: string; expires_in: number }>>(`/storage/presigned-get/${encodeURIComponent(storageKey)}`),
}
```

### New Type

**File**: `ekyc-frontend/src/types/api.ts`

```typescript
export interface PresignedGetResponse {
  url: string
  expires_in: number
}
```

### New Component

**File**: `ekyc-frontend/src/components/ui/DocumentViewer.tsx` (new)

```typescript
interface DocumentViewerProps {
  storageKey: string
  alt?: string
  className?: string
  onError?: (error: Error) => void
}
```

- Fetches presigned URL on mount
- Renders `<img>` with the URL
- Shows loading spinner while fetching
- Handles errors gracefully with fallback UI
- Auto-refreshes URL before expiration (optional enhancement)

### Modified CompliancePage

**File**: `ekyc-frontend/src/pages/agent/CompliancePage.tsx`

Add document thumbnail/preview section after the customer summary card:

```tsx
// Add to imports
import DocumentViewer from '@/components/ui/DocumentViewer'

// In render, after summary card:
{documents && documents.length > 0 && (
  <Card className="p-4">
    <h3 className="section-title mb-3">Documents</h3>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {documents.map((doc) => (
        <div key={doc.id} className="border rounded-lg p-2">
          <DocumentViewer storageKey={doc.storage_key} alt={doc.document_type} />
          <p className="text-xs text-center mt-2 capitalize">{doc.document_type.replace(/_/g, ' ')}</p>
        </div>
      ))}
    </div>
  </Card>
)}
```

### onboardingStore Changes

None required — document keys come from the application data.

## Acceptance Criteria

1. Backend returns a valid presigned URL that can be accessed without additional auth
2. DocumentViewer component renders the image within 2 seconds of loading
3. NID front, NID back, selfie, and signature are all viewable in CompliancePage
4. EDD uploaded documents can be previewed in the EDD section
5. Graceful error handling when document doesn't exist or storage is unavailable
6. URLs expire after 5 minutes and new URL can be fetched on demand

## Implementation Order

- [ ] 1. (backend) Add `generate_presigned_get()` to `app/core/storage.py`
- [ ] 2. (backend) Create `app/api/v1/storage.py` with GET endpoint
- [ ] 3. (backend) Register storage router in `app/main.py`
- [ ] 4. (frontend) Add `storageAPI.getPresignedGetUrl()` to services.ts
- [ ] 5. (frontend) Add `PresignedGetResponse` type to api.ts
- [ ] 6. (frontend) Create `DocumentViewer.tsx` component
- [ ] 7. (frontend) Integrate DocumentViewer into CompliancePage
- [ ] 8. (frontend) Add document preview to EDD section

## Testing Checklist

- [ ] Backend: `GET /storage/presigned-get/nid-front/abc123.jpg` returns valid S3 URL
- [ ] Frontend: Navigate to CompliancePage for an application with documents
- [ ] Frontend: Verify NID front/back images render correctly
- [ ] Frontend: Verify selfie photo is visible
- [ ] Frontend: Verify signature image is visible
- [ ] Frontend: In EDD section, click to preview uploaded EDD documents
- [ ] Edge case: Document key doesn't exist → show error state
- [ ] Edge case: S3 unavailable → show fallback message
- [ ] Edge case: URL expires during viewing → component handles gracefully