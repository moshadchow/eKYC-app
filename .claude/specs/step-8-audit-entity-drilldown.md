# Step 8 — Audit Entity Drill-down Spec

## Overview

This feature adds entity-specific drill-down capability to the Audit Page. When an admin/auditor views audit logs, they can click on any entity (e.g., a KYC application, account, biometric record) to see its complete audit trail — all changes, actions, and events associated with that specific entity.

This falls under **Step 11 (Lifecycle Management)** in the pipeline and supports BFIU's mandatory 5-year audit retention requirement.

## Regulatory Requirements

- **BFIU Section 4.4**: Institutions must retain all audit logs for 5 years from account closure
- **BFIU Section 4.5**: All onboarding attempts (successful and unsuccessful) must be logged with specific matching parameters
- **Record Keeping**: Audit trail must capture actor, action, old/new values, timestamp, and IP address

## Current State

### Backend
- `app/api/v1/audit_lifecycle.py:35-45` — Endpoint `GET /audit/logs/{entity_type}/{entity_id}` exists and is functional
- Returns full audit trail for a specific entity with old_value, new_value, timestamps

### Frontend
- `ekyc-frontend/src/api/services.ts:104` — `auditAPI.entityTrail()` function exists but is **not used**
- `ekyc-frontend/src/pages/admin/AuditPage.tsx` — Lists logs in a table with entity_id shown but **not clickable**
- No drill-down modal or detail view implemented

### Gap
- AuditPage shows entity_id in the table but there's no way to view the detailed history for that specific entity
- The backend already has the endpoint; just needs frontend wiring

## Gaps — What Needs to Be Built

### Frontend Only
1. Add clickable behavior to entity_id in the audit logs table
2. Create a modal/sidebar to display entity-specific audit trail
3. Add loading and empty states for the drill-down view

## Backend Specification

No backend changes required — endpoint already exists.

## Frontend Specification

### New Component

**File**: `ekyc-frontend/src/components/ui/AuditTrailModal.tsx` (new)

```typescript
interface AuditTrailModalProps {
  entityType: string
  entityId: string
  open: boolean
  onClose: () => void
}
```

- Fetches audit trail on open using `auditAPI.entityTrail(entityType, entityId)`
- Displays a modal with:
  - Entity type and ID in header
  - Timeline/list of all audit events for this entity
  - Each entry shows: timestamp, actor, action, old value → new value
- Shows loading spinner while fetching
- Shows empty state if no events found

### Modified AuditPage

**File**: `ekyc-frontend/src/pages/admin/AuditPage.tsx`

1. Add state for selected entity:
   ```typescript
   const [selectedEntity, setSelectedEntity] = useState<{type: string; id: string} | null>(null)
   ```

2. Make entity_id column clickable:
   ```typescript
   <td className="px-5 py-3 font-mono text-xs text-brand-600 cursor-pointer hover:underline"
       onClick={() => setSelectedEntity({ type: l.entity_type, id: l.entity_id })}>
     {l.entity_id?.slice(-8) ?? '—'}
   </td>
   ```

3. Add modal at bottom:
   ```tsx
   {selectedEntity && (
     <AuditTrailModal
       entityType={selectedEntity.type}
       entityId={selectedEntity.id}
       open={!!selectedEntity}
       onClose={() => setSelectedEntity(null)}
     />
   )}
   ```

### API Service

Already exists: `auditAPI.entityTrail(entityType, entityId)` in services.ts

### TypeScript Types

No new types needed — existing `APIResponse<unknown[]>` is used.

## Acceptance Criteria

1. Clicking on any entity_id in the audit logs table opens a modal
2. Modal shows the complete audit trail for that entity (all events)
3. Each event shows: timestamp, actor, action, old_value → new_value
4. Loading state shown while fetching entity trail
5. Empty state shown if no events found for entity
6. Modal can be closed by clicking X or clicking outside

## Implementation Order

- [ ] 1. (frontend) Create `AuditTrailModal.tsx` component in `ekyc-frontend/src/components/ui/`
- [ ] 2. (frontend) Add export for AuditTrailModal in `ekyc-frontend/src/components/ui/index.tsx`
- [ ] 3. (frontend) Modify AuditPage.tsx to add clickable entity_id and integrate the modal

## Testing Checklist

- [ ] Navigate to `/admin/audit` as admin/auditor
- [ ] Click on any entity_id in the table
- [ ] Verify modal opens with audit trail for that entity
- [ ] Verify all events for that entity are shown
- [ ] Close modal and verify can open another entity
- [ ] Test with entities that have no events (should show empty state)
- [ ] Test pagination still works on main audit log page