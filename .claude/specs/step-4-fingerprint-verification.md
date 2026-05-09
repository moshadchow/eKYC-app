# Step 4 — Fingerprint Verification Spec

## Overview

Fingerprint Verification is the biometric identity confirmation step for **Assisted Onboarding** — where a customer visits a branch or agent rather than self-checking in online. It is the agent-side counterpart to the face-match step (Step 4, same pipeline stage) and is governed by BFIU 2026 Circular 29 Section "Fingerprint Matching Protocol." In the onboarding pipeline, it sits after NID Verification (Step 3) and before Profile Capture (Step 5). After a successful NID check the agent captures a live fingerprint scan and transmits it to the EC verification server; if the template matches, the application advances to profile collection. If fingerprint matching fails across 3 consecutive sessions the system mandates a fallback to face-matching. Currently the backend endpoint `POST /kyc/applications/{app_id}/verify/fingerprint` is fully implemented (including retry-limit enforcement and fallback detection), and the `verificationAPI.fingerprint` service function exists in the frontend. However **there is zero UI for fingerprint verification** — the `OnboardingPage` wizard exposes only `face_match` as a biometric step, the `onboardingStore` has no fingerprint state, and no agent-facing assisted onboarding wizard exists at all. This spec covers building the agent-side fingerprint UI and integrating the fallback-to-face logic.

---

## Regulatory Requirements

- **Fingerprint Matching Protocol (BFIU 2026, Biometric Models section):**
  - Used in **Assisted Onboarding** scenarios (branch visit or agent): `onboarding_channel` = `assisted` or `branch`
  - Requires capture of NID number and date of birth first (NID already validated at Step 3)
  - Live fingerprint scan transmitted to EC verification server
  - **Maximum 10 fingerprint matching attempts per session**
  - **Maximum 2 sessions per day**
  - **If fingerprint matching fails across 3 consecutive sessions**, the institution **must** offer face-matching as an alternative
  - After 3 failed sessions, traditional paper KYC must be offered if face-match also fails (already enforced by backend `BIOMETRIC_MAX_TOTAL_SESSIONS = 3`)
- **Finger position:** Any of 10 fingers may be used; the system must record which finger was scanned
- **Liveness:** Physical presence assumed for assisted onboarding; agent supervises capture
- **Audit trail:** Every attempt (success and failure) must be logged with IP, device info, and result score
- **Daily session limits:** Max 2 sessions per day, max 3 total sessions ever per application — enforced in `crud_verification.get_attempt_counters`
- **Sector scope:** Applies to capital market BO accounts, life insurance, and non-life insurance via assisted channel

---

## Current State

### Backend

| File | Endpoint / Method | Notes |
|---|---|---|
| `app/api/v1/verification.py:107` | `POST /kyc/applications/{app_id}/verify/fingerprint` | Agent auth (`CurrentAgent`). Fully implemented. Calls `crud_verification.run_fingerprint_match`. Returns `matched`, `similarity_score`, `attempt_number`, `session_number`, `suggest_face_fallback`, `fallback_message` |
| `app/crud/crud_verification.py:155` | `CRUDVerification.run_fingerprint_match(db, app_id, nid_number, fingerprint_template, date_of_birth, finger_position, ip_address, device_info)` | Fully implemented. Persists `BiometricVerification` row, computes `suggest_face_fallback` when `max_fp_sessions >= 3` |
| `app/crud/crud_verification.py:47` | `CRUDVerification.get_attempt_counters(db, app_id, verification_type)` | Enforces 10/session, 2/day, 3-total limits. Raises HTTP 429 when exhausted |
| `app/crud/crud_verification.py:204` | `CRUDVerification.get_verification_status(db, app_id)` | Returns `fingerprint_matched`, `can_retry` among others |
| `app/services/mock_ec.py:109` | `MockECService.fingerprint_match(nid_number, fingerprint_template, finger_position)` | Mock — simulates ~80% pass rate, returns `matched`, `similarity_score`, `threshold=70.0` |
| `app/core/config.py:25` | `BIOMETRIC_MAX_ATTEMPTS_PER_SESSION=10`, `BIOMETRIC_MAX_SESSIONS_PER_DAY=2`, `BIOMETRIC_MAX_TOTAL_SESSIONS=3` | Configurable via env vars |

### Frontend

| File | What exists |
|---|---|
| `ekyc-frontend/src/api/services.ts:52` | `verificationAPI.fingerprint(appId, body)` — wired, typed as `FaceMatchResult & { suggest_face_fallback: boolean; fallback_message: string | null }` |
| `ekyc-frontend/src/types/api.ts:191` | `FaceMatchResult` — `matched`, `similarity_score`, `attempt_number`, `session_number`, `attempts_remaining` |
| `ekyc-frontend/src/types/api.ts:208` | `VerificationStatus` — includes `fingerprint_matched` field |
| `ekyc-frontend/src/store/onboardingStore.ts` | No fingerprint step, no fingerprint result state |
| `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx:54` | Hardcodes `onboarding_channel: 'self_checkin'` — no assisted channel path |

### Stubs / Gaps

- **No `fingerprint` step in `OnboardingStep` enum** — the store machine goes `nid_capture → face_match` unconditionally; there is no branch for assisted/fingerprint
- **No fingerprint result state** in `onboardingStore` (no `fingerprintResult` field, no `setFingerprintResult` action)
- **No `onboarding_channel` state** in `onboardingStore` — the wizard cannot represent an assisted session
- **No agent-facing onboarding wizard** — agents can queue-review submitted applications but have no way to initiate or assist a customer through the fingerprint step
- **No fallback-to-face UI** — `suggest_face_fallback` is returned by the API but never consumed in any component
- **`OnboardingPage` STEPS array** does not include a `fingerprint` step label
- **Review checklist** in `ReviewStep` only checks `faceMatchResult?.matched`, not `fingerprintResult?.matched`

---

## Gaps — What Needs to Be Built

### Backend Gaps

No new backend endpoints or CRUD methods are required. The fingerprint endpoint, retry logic, fallback detection, and audit recording are all fully implemented. The only backend change is a minor clarification: the `verify/fingerprint` endpoint currently requires `CurrentAgent` auth, which is correct — no change needed.

### Frontend Gaps

| Gap | Why needed | Where to add |
|---|---|---|
| `fingerprint` step in `OnboardingStep` type | Store machine needs to represent the fingerprint step for assisted flow | `ekyc-frontend/src/store/onboardingStore.ts` |
| `onboardingChannel` state + `setOnboardingChannel` action | Wizard needs to know if customer is in assisted vs self-checkin flow to branch to fingerprint vs face_match | `ekyc-frontend/src/store/onboardingStore.ts` |
| `fingerprintResult` state + `setFingerprintResult` action | Store must hold fingerprint attempt result for review checklist and fallback detection | `ekyc-frontend/src/store/onboardingStore.ts` |
| `FingerprintResult` TypeScript type | Typed response shape including `suggest_face_fallback` | `ekyc-frontend/src/types/api.ts` |
| `FingerprintStep` component in agent onboarding wizard | BFIU requires agents to perform fingerprint capture for assisted onboarding | New agent onboarding page or embedded step in new `AgentOnboardingPage.tsx` |
| Channel selection in pre-check / application creation step | `onboarding_channel` must be set to `assisted` or `branch` for fingerprint flow; `self_checkin` goes to face_match | `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx` (or new agent page) |
| Fallback-to-face navigation | When `suggest_face_fallback = true`, agent wizard must route to face-match step with a clear notice | `FingerprintStep` component |
| Review checklist update | `ReviewStep` check "Face or fingerprint verified" should pass when either biometric succeeds | `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx:488` |
| `AgentOnboardingPage.tsx` | Agent-initiated assisted onboarding wizard — wraps customer identity capture + fingerprint step; agents reach it from the queue or via a new route | New file: `ekyc-frontend/src/pages/agent/AgentOnboardingPage.tsx` |
| Route `/agent/onboarding/:appId` | Agent needs a URL to assist a specific application through fingerprint verification | `ekyc-frontend/src/AppRouter.tsx` |
| Nav link in agent sidebar | Agent must be able to navigate to assisted onboarding | `ekyc-frontend/src/components/layout/AppShell.tsx` |

---

## Backend Specification

No new or modified endpoints, CRUD methods, or data model changes are required. All backend logic is complete. This spec is frontend-only.

---

## Frontend Specification

### onboardingStore Changes

Add to `OnboardingStep` type:
```ts
| 'fingerprint'
```
Position in flow: `'nid_capture' → 'fingerprint' | 'face_match' → 'profile'`

Add to `OnboardingState` interface:
```ts
onboardingChannel: 'self_checkin' | 'assisted' | 'branch' | 'internet' | null
fingerprintResult: FingerprintResult | null

setOnboardingChannel: (channel: 'self_checkin' | 'assisted' | 'branch' | 'internet') => void
setFingerprintResult: (r: FingerprintResult) => void
```

Add to `initial` object:
```ts
onboardingChannel: null,
fingerprintResult: null,
```

Add to `create` body:
```ts
setOnboardingChannel: (channel) => set({ onboardingChannel: channel }),
setFingerprintResult: (r) => set({ fingerprintResult: r }),
```

**Step routing logic change** (in `OnboardingPage.PreCheckStep` or application creation, after `next('nid_capture')` completes and user proceeds):
- If `onboardingChannel === 'self_checkin' || onboardingChannel === 'internet'` → next step is `'face_match'`
- If `onboardingChannel === 'assisted' || onboardingChannel === 'branch'` → next step is `'fingerprint'`

---

### New / Modified Pages or Components

---

#### 1. `FingerprintStep` (inline component, to be placed in `AgentOnboardingPage.tsx`)

**What it renders:**
- Heading: "Fingerprint Verification"
- Subtitle: "Capture customer's live fingerprint and submit to EC database"
- Attempt counter display: "Session {n} — Attempt {n} of 10"
- Finger position selector: dropdown with 10 options (right_thumb, right_index, right_middle, right_ring, right_little, left_thumb, left_index, left_middle, left_ring, left_little); default: `right_index`
- Fingerprint template input: `<textarea>` or simulated scan button (in production: SDK-populated; in dev: manual base64 input field labeled "Fingerprint Template (Base64)")
  - In development: a "Simulate Scan" button that generates a placeholder base64 string to allow testing without physical hardware
- "Submit Fingerprint" button
- Result display after submission:
  - **Success:** green success banner "Fingerprint matched — score {score}%", "Continue" button → `next('profile')`
  - **Failure:** red error banner with score, "Retry" button (if `can_retry`)
  - **Fallback triggered** (`suggest_face_fallback = true`): amber warning banner displaying `fallback_message`, "Switch to Face Match" button → `next('face_match')` (store must be set up to handle this cross-channel transition)
  - **Session exhausted (429):** full-page block "Maximum sessions reached. Offer traditional paper KYC to customer."

**User interactions:**
- Select finger position → updates local state
- "Simulate Scan" / hardware SDK populates template → updates `fingerprintTemplate` local state
- "Submit Fingerprint" → calls `verificationAPI.fingerprint(appId, { nid_number, fingerprint_template, finger_position, date_of_birth })`
  - On success: `store.setFingerprintResult(result)`, show result banner
  - If `result.matched` → "Continue" button navigates to `'profile'`
  - If `!result.matched && suggest_face_fallback` → show "Switch to Face Match" button
  - If `!result.matched && !suggest_face_fallback` → show "Retry" button (clears template, keeps session)
  - On 429 error: show block screen, disable retry
- "Back" → navigates to `'nid_capture'`

**State read from store:** `application.id`, `nidRecord.nid_number`, `nidRecord.date_of_birth`
**State written to store:** `fingerprintResult` (via `setFingerprintResult`), `step` (via `setStep`)

**API call:** `verificationAPI.fingerprint(appId, body)` on submit button click

**Navigation:**
- Success (`matched = true`) → `store.setStep('profile')`
- Fallback triggered → `store.setStep('face_match')`
- 429 / total exhaustion → block screen, no navigation

---

#### 2. `AgentOnboardingPage.tsx` (new file)

**File path:** `ekyc-frontend/src/pages/agent/AgentOnboardingPage.tsx`

**Purpose:** An agent-controlled version of the onboarding wizard for assisted channel customers. Wraps the same step machine but with agent auth, `onboarding_channel = 'assisted'`, and the `fingerprint` step instead of `face_match`.

**Route param:** `appId` from URL — if present, the agent is resuming an existing application's biometric step; if absent, agent creates a new application for the customer.

**Steps shown in STEPS array:**
```ts
[
  { key: 'nid_capture', label: 'NID' },
  { key: 'fingerprint', label: 'Fingerprint' },
  { key: 'profile', label: 'Profile' },
]
```
(Nominee and signature steps are shown but can be skipped to "Review" for agent-assisted minimal path)

**What it renders:**
- Same `Steps` progress bar as `OnboardingPage`
- `NIDStep` (reusable — same logic as customer wizard)
- `FingerprintStep` (new — agent captures biometric)
- Condensed `ProfileStep` (can call `applicationsAPI.saveProfile` with pre-filled NID data)
- "Submit to Queue" action instead of full "Review" step

**Navigation:**
- After fingerprint success → `setStep('profile')`
- After fallback → `setStep('face_match')` (reuse `FaceMatchStep` logic from `OnboardingPage`)
- After profile save → call `applicationsAPI.submit(appId)` → redirect to `/agent/queue`

**API calls:**
- `applicationsAPI.agentCreate(body, customerMobile)` if no `appId` in URL (creates assisted application)
- `verificationAPI.fingerprint(appId, body)` in fingerprint step
- `applicationsAPI.saveProfile(appId, body)` in profile step
- `applicationsAPI.submit(appId)` on submit

---

#### 3. Modified `OnboardingPage.tsx`

Two targeted changes:

**Change 1 — Add channel selector in `PreCheckStep`** (before the "Check & Continue" button):
```tsx
<Field label="Onboarding Channel" required>
  <Select value={channel} onChange={e => setChannel(e.target.value)}>
    <option value="self_checkin">Self Check-in (online)</option>
    <option value="assisted">Assisted (agent at branch)</option>
  </Select>
</Field>
```
After creating the application, call `store.setOnboardingChannel(channel)`.

After NID validation in `NIDStep.handle()`, route based on channel:
```ts
const nextStep = store.onboardingChannel === 'assisted' ? 'fingerprint' : 'face_match'
next(nextStep)
```

**Change 2 — Add `FingerprintStep` component** (reuse the same component from `AgentOnboardingPage` if extracted to a shared location, or duplicate inline):
- Register in `stepComponents` map:
  ```ts
  fingerprint: <FingerprintStep />,
  ```
- Add `'Fingerprint'` to the `STEPS` array (conditionally shown only when `onboardingChannel === 'assisted'`)

**Change 3 — Update Review checklist** (line 488):
```ts
{ label: 'Biometric verified', done: !!store.faceMatchResult?.matched || !!store.fingerprintResult?.matched },
```
Remove the separate `{ label: 'Face matched', done: !!store.faceMatchResult?.matched }` entry and replace with the above unified check.

---

#### 4. Modified `AppRouter.tsx`

Add agent onboarding route:
```tsx
<Route path="/agent/onboarding/:appId?" element={<AgentOnboardingPage />} />
```
Add import: `import AgentOnboardingPage from '@/pages/agent/AgentOnboardingPage'`

---

#### 5. Modified `AppShell.tsx`

Add to `agentNav`:
```ts
{ to: '/agent/onboarding', icon: <UserCheck className="h-4 w-4" />, label: 'Assist Customer' },
```
Add `UserCheck` to the lucide-react import if not already present.

---

### API Service Additions

No new service functions needed — `verificationAPI.fingerprint` already exists at `ekyc-frontend/src/api/services.ts:52`. The return type annotation should be tightened:

```ts
// Current (services.ts:52):
fingerprint: (appId: string, body: {...}) =>
  apiClient.post<APIResponse<FaceMatchResult & { suggest_face_fallback: boolean; fallback_message: string | null }>>(...),

// Change to use named type:
fingerprint: (appId: string, body: { nid_number: string; fingerprint_template: string; finger_position?: string; date_of_birth: string }) =>
  apiClient.post<APIResponse<FingerprintResult>>(...),
```

---

### TypeScript Types

Add to `ekyc-frontend/src/types/api.ts` (after `FaceMatchResult`):

```ts
export interface FingerprintResult {
  matched: boolean
  similarity_score: number
  attempt_number: number
  session_number: number
  suggest_face_fallback: boolean
  fallback_message: string | null
}
```

Add `OnboardingChannel` type if not already exported (it exists in the enum but not as a standalone TS union — confirm, then add if needed):
```ts
export type OnboardingChannelValue = 'self_checkin' | 'assisted' | 'branch' | 'internet'
```

---

## Acceptance Criteria

1. `POST /kyc/applications/{app_id}/verify/fingerprint` with a valid agent token, NID, and base64 template → HTTP 200, `matched: true/false`, `attempt_number: 1`, `session_number: 1`, `suggest_face_fallback: false`.
2. After 10 failed attempts in session 1, the 11th attempt → HTTP 429 "per day" limit with session bumped to 2.
3. After exhausting all 3 sessions without a match → HTTP 429 "maximum sessions exhausted", `suggest_face_fallback: true` on the last successful-response attempt.
4. A customer token calling `POST /kyc/applications/{app_id}/verify/fingerprint` → HTTP 401/403 (agent-only endpoint).
5. `onboardingStore` has `fingerprintResult`, `onboardingChannel`, `setFingerprintResult`, `setOnboardingChannel` fields after the change.
6. Selecting "Assisted" channel in `PreCheckStep` and completing NID step routes the wizard to `fingerprint` step (not `face_match`).
7. Selecting "Self Check-in" channel in `PreCheckStep` routes to `face_match` as before (no regression).
8. `FingerprintStep` renders: finger position dropdown, template input, "Simulate Scan" button, and "Submit Fingerprint" button.
9. On a successful match: green success banner displays the similarity score; "Continue" button appears and navigates to `profile` step.
10. On a failed match without fallback: red error banner with score; "Retry" button clears the template field; attempt counter increments.
11. When `suggest_face_fallback = true`: amber warning banner shows `fallback_message`; "Switch to Face Match" button navigates to `face_match` step.
12. On HTTP 429 (session exhausted): full-block message "Maximum sessions reached. Offer traditional paper KYC to customer." — no retry button shown.
13. Review checklist in `ReviewStep` shows "Biometric verified" as complete when either `faceMatchResult.matched` OR `fingerprintResult.matched` is true.
14. `AgentOnboardingPage` is accessible at `/agent/onboarding` (no appId) and `/agent/onboarding/:appId` (resume existing).
15. **BFIU compliance:** `attempt_number` correctly increments from 1 to 10 within a session; session rolls over to 2 after 10 attempts within the same application.
16. **BFIU compliance:** `suggest_face_fallback` is `true` only after ≥3 fingerprint sessions have been exhausted without a match.

---

## Implementation Order

- [ ] 1. (frontend) Add `FingerprintResult` interface to `ekyc-frontend/src/types/api.ts`
- [ ] 2. (frontend) Add `OnboardingChannelValue` type alias to `ekyc-frontend/src/types/api.ts`
- [ ] 3. (frontend) Update `verificationAPI.fingerprint` return type to use `FingerprintResult` in `ekyc-frontend/src/api/services.ts`
- [ ] 4. (frontend) Add `fingerprint` to `OnboardingStep` union in `ekyc-frontend/src/store/onboardingStore.ts`
- [ ] 5. (frontend) Add `onboardingChannel`, `fingerprintResult`, `setOnboardingChannel`, `setFingerprintResult` to onboardingStore state and actions
- [ ] 6. (frontend) Add channel selector field to `PreCheckStep` in `ekyc-frontend/src/pages/onboarding/OnboardingPage.tsx`
- [ ] 7. (frontend) Update `NIDStep.handle()` to branch to `'fingerprint'` or `'face_match'` based on `store.onboardingChannel`
- [ ] 8. (frontend) Add `FingerprintStep` inline component to `OnboardingPage.tsx` with finger position selector, template input, simulate button, submit logic, and all result/fallback states
- [ ] 9. (frontend) Register `fingerprint` in `stepComponents` map and add it to `STEPS` array in `OnboardingPage.tsx`
- [ ] 10. (frontend) Update `ReviewStep` checklist to use unified "Biometric verified" check covering both face and fingerprint
- [ ] 11. (frontend) Create `ekyc-frontend/src/pages/agent/AgentOnboardingPage.tsx` with NID → Fingerprint → Profile → Submit flow
- [ ] 12. (frontend) Add `/agent/onboarding/:appId?` route to `ekyc-frontend/src/AppRouter.tsx`
- [ ] 13. (frontend) Add "Assist Customer" nav item to `agentNav` in `ekyc-frontend/src/components/layout/AppShell.tsx`

---

## Testing Checklist

### Backend (Swagger UI / curl)

1. Authenticate as agent → `POST /kyc/applications/{id}/verify/fingerprint` with body `{ nid_number: "1234567890123", fingerprint_template: "dGVzdA==", date_of_birth: "1990-05-15" }` → HTTP 200, `matched: true/false` (probabilistic mock).
2. Make 10 failed attempts in one session → attempt 11 → HTTP 429 with "per day" detail.
3. Make 2 full sessions of failures → start session 3 → confirm `session_number: 3` in response.
4. After 3 full failed sessions → HTTP 429 with "maximum sessions exhausted" message.
5. `GET /kyc/applications/{id}/verify/status` → `fingerprint_matched: true/false`, `can_retry: true/false` — verify these reflect the attempts above.
6. Try with customer token → HTTP 403.

### Frontend (browser walkthrough)

1. Log in as customer → `/onboarding` → Pre-check step: select "Assisted (agent at branch)" channel → proceed through NID → wizard shows "Fingerprint" step (not "Face Match").
2. On Fingerprint step: select finger position "Left Index" → click "Simulate Scan" → template field populates → click "Submit Fingerprint".
3. On success: green banner with score, "Continue" button → click → navigates to Profile step.
4. On failure: red banner, "Retry" button → click → template clears, can re-submit.
5. Simulate 3 sessions of failure (mock is probabilistic — may need to force failure via a known-bad NID or wait for random failures): verify amber "Switch to Face Match" banner appears.
6. Log in as agent → `/agent/onboarding` → create new assisted application → walk through NID → Fingerprint → Profile → Submit → redirected to `/agent/queue`.
7. Self-checkin regression: select "Self Check-in" in pre-check → NID step → routes to Face Match step (not fingerprint) — confirms no regression.
8. Review checklist: complete fingerprint (or face match) → navigate to Review step → "Biometric verified" shows checkmark.

### Edge cases

- `fingerprint_template` is empty string → form-level validation should prevent submission ("Template required").
- `attempt_number` displayed in UI matches the `attempt_number` returned by the API (not a static counter).
- Channel selection persists across page refresh (Zustand persist middleware) — returning to `/onboarding` after refresh retains channel selection.
- HTTP 429 mid-session (e.g., clock rollover between 2 sessions on the same day) → correct "Try again after 24 hours" message shown.
- `suggest_face_fallback = true` with `matched = true` — impossible per backend logic, but if it occurs UI should show success (matched state takes precedence).
- Agent creates application with `onboarding_channel = 'assisted'` but then the customer requests self-checkin face-match — the fallback path handles this: `suggest_face_fallback → next('face_match')` is the intended transition.
