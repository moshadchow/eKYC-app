# Step 7 — Risk Scoring: Profession & Business Activity Hardcoded Spec

## Overview

The BFIU 2026 Circular 29 (section 6.3 / Annexure-1) mandates that every Regular e-KYC application undergo a 7-factor composite risk grading before a maker agent may submit the application for checker approval. Two of these seven factors — **profession risk** and **business activity risk** — are currently hardcoded to a flat score of `3` in `auto_calculate_scores()` regardless of what the customer entered in their profile. The actual BFIU Annexure-1 tables specify scores ranging from 1–5 for ~20 profession categories and ~10 business activity categories. This feature replaces the two hardcoded stubs with dynamic lookup tables that map the customer's declared `profession` and `source_of_fund` / business type to their correct BFIU risk weight. This step sits immediately after Compliance Screening (Step 6) and before EDD (Step 8) and Maker Review (Step 9).

## Regulatory Requirements

From BFIU Circular 29 Annexure-1 (reproduced in CLAUDE.md):

**Profession scores (score_profession):**
- Score 5: Pilot / Flight Attendant, Trustee
- Score 4: Journalist, Lawyer, Doctor, IT Sector Employee, Athlete / Media Celebrity
- Score 3: Government Service, Private Service: Managerial
- Score 2: Private Sector Employee, Self-employed Professional, Student, Share/Stocks Investor
- Score 1: Retiree

**Business activity scores (score_business_activity):**
- Score 5: Jeweler / Gold Business, Money Changer / MFS Agent, Real Estate Developer, Manpower Export, Art & Antiquities Dealer, RMG / Garments Accessories, Software / IT Business, Share / Stocks Investor
- Score 4: Construction Materials Trader
- Score 2: Small Business (< BDT 5M)
- Default (unrecognised / not provided): configurable, currently returns 3

**Risk classification thresholds (BFIU section 6.2):**
- Total score ≥ 15 → High risk (EDD required)
- Total score 8–14 → Medium risk
- Total score ≤ 7 → Low risk

**`HIGH_RISK_SCORE_THRESHOLD = 15`** is already configurable via `settings` (`app/core/config.py:39`).

## Current State

### Backend

- **`app/crud/crud_compliance.py`** — `CRUDCompliance.auto_calculate_scores()` (lines 195–248)
  - `score_profession`: hardcoded to `3` at line 245
  - `score_business_activity`: hardcoded to `3` at line 244
  - `profile.profession` is fetched (line 203) but never read
  - No lookup tables anywhere in the file

- **`app/api/v1/compliance.py`** — `POST /{app_id}/risk-score` (line 119)
  - Accepts optional `RiskScoreRequest` body for full manual override
  - When no body, delegates to `auto_calculate_scores()` — the stub path

- **`app/models/compliance.py`** — `RiskScore` table stores `score_profession` and `score_business_activity` as plain `int` columns (lines 149–150); no schema change needed

- **`app/models/onboarding.py`** — `CustomerProfile.profession` is a free-text `Optional[str]` field (line 98); no structured enum. `source_of_fund` is an enum-backed string (line 103).

### Frontend

- **`ekyc-frontend/src/pages/agent/CompliancePage.tsx`** — Displays the score breakdown grid (lines 138–145). `business_activity` and `profession` entries are shown by iterating `score_breakdown` object entries — no component changes needed to display corrected values.

- No frontend UI currently shows *what* profession/business score was derived from — there is no transparency for the agent to see which category the customer fell into.

### Stubs / Placeholders

```python
# crud_compliance.py line 244
"score_business_activity": 3,   # ← hardcoded stub
"score_profession": 3,           # ← hardcoded stub
```

No TODO comments are present; the stubs are silent.

## Gaps — What Needs to Be Built

### Backend

1. **No Annexure-1 lookup tables exist** — The BFIU scoring tables for profession and business activity live only in CLAUDE.md, not in code. They must be implemented as module-level dicts in `crud_compliance.py` (or a new `app/core/risk_tables.py`).

2. **`profession` field is not normalised** — `CustomerProfile.profession` is a free-text string. The lookup must handle case-insensitive partial matching or a canonical list of tokens so "Advocate" maps to the Lawyer/Lawyer bucket.

3. **Business activity not captured separately** — The current data model has no dedicated `business_activity` field. The closest proxy is `source_of_fund` (salary, business, investment…) and the free-text `profession` field. The spec proposes adding a `business_activity` free-text field to `CustomerProfile` and a corresponding request field to `CustomerProfileRequest`, with its own Annexure-1 lookup.

4. **Score derivation is opaque** — `score_breakdown` returned by the API does not include the matched profession/business category label, making audit trails non-compliant. The API response should add `matched_profession_category` and `matched_business_category` strings.

### Frontend

1. **No profession/business category selector** — The profile capture step offers a free-text `profession` input. This should become a `<Select>` driven by the Annexure-1 canonical category list, so the value stored is always a matchable token, not an arbitrary string.

2. **Score derivation not shown in CompliancePage** — The risk score breakdown grid shows numeric scores but not which category was matched. A tooltip or sub-label under each score tile should show the matched category name.

## Backend Specification

### New Module: `app/core/risk_tables.py`

Create a new file containing the Annexure-1 lookup tables as module-level dicts. This keeps scoring data out of CRUD code and makes it easy to update when BFIU revises the tables.

```python
# Annexure-1 profession risk scores (BFIU Circular 29)
PROFESSION_SCORES: dict[str, int] = {
    "pilot": 5, "flight_attendant": 5, "trustee": 5,
    "journalist": 4, "lawyer": 4, "advocate": 4, "doctor": 4, "physician": 4,
    "it_employee": 4, "software_engineer": 4, "athlete": 4, "media_celebrity": 4,
    "government_service": 3, "managerial": 3,
    "private_service": 2, "self_employed": 2, "student": 2,
    "shares_investor": 2, "stock_investor": 2,
    "retiree": 1,
}
PROFESSION_DEFAULT_SCORE = 3  # fallback for unrecognised values

# Annexure-1 business activity risk scores (BFIU Circular 29)
BUSINESS_ACTIVITY_SCORES: dict[str, int] = {
    "jeweler": 5, "gold_business": 5,
    "money_changer": 5, "mfs_agent": 5,
    "real_estate": 5, "real_estate_developer": 5,
    "manpower_export": 5, "recruitment": 5,
    "art_dealer": 5, "antiquities": 5,
    "rmg": 5, "garments": 5,
    "software_business": 5, "it_business": 5,
    "shares_trading": 5, "stock_trading": 5,
    "construction_materials": 4,
    "small_business": 2,
}
BUSINESS_DEFAULT_SCORE = 3  # fallback
```

**Lookup helper** (also in `risk_tables.py`):
```python
def lookup_score(value: str | None, table: dict[str, int], default: int) -> tuple[int, str]:
    """Case-insensitive token match. Returns (score, matched_key_or_'unmatched')."""
    if not value:
        return default, "not_provided"
    normalised = value.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
    for key, score in table.items():
        if key in normalised or normalised in key:
            return score, key
    return default, "unmatched"
```

### Modified `app/crud/crud_compliance.py`

#### `auto_calculate_scores()` — replace hardcoded stubs

Add import at top of file:
```python
from app.core.risk_tables import (
    PROFESSION_SCORES, PROFESSION_DEFAULT_SCORE,
    BUSINESS_ACTIVITY_SCORES, BUSINESS_DEFAULT_SCORE,
    lookup_score,
)
```

Replace lines 244–245:
```python
# OLD
"score_business_activity": 3,
"score_profession": 3,

# NEW
score_profession, matched_profession = lookup_score(
    profile.profession if profile else None,
    PROFESSION_SCORES, PROFESSION_DEFAULT_SCORE,
)
score_business, matched_business = lookup_score(
    profile.business_activity if profile else None,
    BUSINESS_ACTIVITY_SCORES, BUSINESS_DEFAULT_SCORE,
)
```

Return dict extended with matched category labels:
```python
return {
    "score_onboarding_channel": score_channel,
    "score_geography": score_geo,
    "score_customer_type": score_customer,
    "score_product": score_product,
    "score_business_activity": score_business,
    "score_profession": score_profession,
    "score_transaction_volume": score_txn,
    "score_transparency": score_transparency,
    # diagnostic extras — not persisted in risk_scores table, passed through to API response
    "_matched_profession_category": matched_profession,
    "_matched_business_category": matched_business,
}
```

The underscore-prefixed keys must be stripped before `**scores` is unpacked into the `RiskScore` constructor (they are not columns).

#### `create_risk_score()` — strip diagnostic keys before DB insert

```python
db_scores = {k: v for k, v in scores.items() if not k.startswith("_")}
total = sum(db_scores.values())
rs = RiskScore(kyc_application_id=app_id, **db_scores, ...)
```

### Modified `app/api/v1/compliance.py`

#### `calculate_risk_score` endpoint — include matched categories in response

The API response data dict should add:
```python
"matched_profession_category": scores.get("_matched_profession_category"),
"matched_business_category": scores.get("_matched_business_category"),
```

Full updated response block:
```python
return APIResponse(
    message=f"Risk score: {str(rs.risk_classification).upper()} (score: {rs.total_score})",
    data={
        "risk_score_id": str(rs.id), "total_score": rs.total_score,
        "risk_classification": rs.risk_classification, "edd_required": rs.edd_required,
        "score_breakdown": db_scores, "version": rs.version,
        "matched_profession_category": scores.get("_matched_profession_category"),
        "matched_business_category": scores.get("_matched_business_category"),
    },
)
```

### Data Model Changes

Add `business_activity` column to `CustomerProfile` / `customer_profiles` table:

**`app/models/onboarding.py` — `CustomerProfileBase`:**
```python
business_activity: Optional[str] = Field(default=None, max_length=255)
```

**New Alembic migration required:** `migrations/versions/0002_add_business_activity_to_customer_profiles.py`

```python
def upgrade():
    op.add_column('customer_profiles',
        sa.Column('business_activity', sa.String(255), nullable=True)
    )

def downgrade():
    op.drop_column('customer_profiles', 'business_activity')
```

### New / Modified Endpoints

No new endpoints. `POST /{app_id}/risk-score` is the only change (response shape extends with two optional string fields).

### CRUD Method Summary

| Method | File | Change |
|---|---|---|
| `auto_calculate_scores` | `crud_compliance.py:195` | Replace hardcoded stubs with `lookup_score()` calls; return diagnostic keys |
| `create_risk_score` | `crud_compliance.py:261` | Strip `_` prefixed keys from scores dict before DB insert |

## Frontend Specification

### onboardingStore Changes

No store changes needed — `profession` is already stored in the profile payload. The new `business_activity` field can be added to the profile step form without a store-level change since the store passes profile data as a plain object.

### Modified Pages / Components

#### 1. Profile capture step in `OnboardingPage.tsx` and `AgentOnboardingPage.tsx`

**What changes:** Replace the free-text `profession` `<Input>` with a `<Select>` driven by a canonical options list imported from a shared constants file. Add a new `business_activity` `<Select>` field below profession.

**New file: `ekyc-frontend/src/constants/riskCategories.ts`**
```ts
export const PROFESSION_OPTIONS = [
  { value: 'pilot', label: 'Pilot / Flight Attendant' },
  { value: 'trustee', label: 'Trustee' },
  { value: 'journalist', label: 'Journalist' },
  { value: 'lawyer', label: 'Lawyer / Advocate' },
  { value: 'doctor', label: 'Doctor / Physician' },
  { value: 'it_employee', label: 'IT Sector Employee' },
  { value: 'athlete', label: 'Athlete / Media Celebrity' },
  { value: 'government_service', label: 'Government Service' },
  { value: 'managerial', label: 'Private Service: Managerial' },
  { value: 'private_service', label: 'Private Sector Employee' },
  { value: 'self_employed', label: 'Self-employed Professional' },
  { value: 'student', label: 'Student' },
  { value: 'shares_investor', label: 'Share / Stocks Investor' },
  { value: 'retiree', label: 'Retiree' },
  { value: 'other', label: 'Other' },
]

export const BUSINESS_ACTIVITY_OPTIONS = [
  { value: 'jeweler', label: 'Jeweler / Gold Business' },
  { value: 'money_changer', label: 'Money Changer / MFS Agent' },
  { value: 'real_estate', label: 'Real Estate Developer' },
  { value: 'manpower_export', label: 'Manpower Export / Recruitment' },
  { value: 'art_dealer', label: 'Art and Antiquities Dealer' },
  { value: 'rmg', label: 'RMG / Garments Accessories' },
  { value: 'it_business', label: 'Software / IT Business' },
  { value: 'shares_trading', label: 'Share / Stocks Trading' },
  { value: 'construction_materials', label: 'Construction Materials Trader' },
  { value: 'small_business', label: 'Small Business (< BDT 5M)' },
  { value: 'other', label: 'Other / Not Applicable' },
]
```

**`OnboardingPage.tsx` — `ProfileStep`:**
- Replace `<Input type="text" ... name="profession">` with `<Select options={PROFESSION_OPTIONS} ...>`
- Add `<Field label="Business Activity (if applicable)"><Select options={BUSINESS_ACTIVITY_OPTIONS} .../></Field>` below profession
- Include `business_activity` in the profile save payload passed to `applicationsAPI.saveProfile()`

**`AgentOnboardingPage.tsx` — same `ProfileStep` section:** identical change.

#### 2. `CompliancePage.tsx` — show matched category labels

In the score breakdown grid (lines 138–145), if `riskScore.matched_profession_category` or `riskScore.matched_business_category` is present, render it as a sub-label below the numeric score for those two tiles:

```tsx
{Object.entries(riskScore.score_breakdown).map(([k, v]) => (
  <div key={k} className="bg-surface-50 rounded-lg p-3 text-center">
    <div className="text-lg font-semibold text-surface-800">{v as number}</div>
    <div className="text-xs text-surface-500 mt-0.5 capitalize">{k.replace(/_/g, ' ')}</div>
    {k === 'profession' && riskScore.matched_profession_category && (
      <div className="text-xs text-brand-500 mt-0.5 italic">{riskScore.matched_profession_category.replace(/_/g, ' ')}</div>
    )}
    {k === 'business_activity' && riskScore.matched_business_category && (
      <div className="text-xs text-brand-500 mt-0.5 italic">{riskScore.matched_business_category.replace(/_/g, ' ')}</div>
    )}
  </div>
))}
```

### API Service Additions

No new service functions needed. `complianceAPI.calculateRisk()` and `complianceAPI.getRisk()` already exist. The `RiskScoreResult` type in `types/api.ts` needs two optional fields added.

### TypeScript Types

**`ekyc-frontend/src/types/api.ts` — `RiskScoreResult`:** add two optional fields:
```ts
export interface RiskScoreResult {
  risk_score_id: string
  total_score: number
  risk_classification: RiskClassification
  edd_required: boolean
  score_breakdown: Record<string, number>
  version: number
  scored_at?: string
  matched_profession_category?: string   // ← new
  matched_business_category?: string     // ← new
}
```

**`ekyc-frontend/src/types/api.ts` — `CustomerProfileRequest`:** add one optional field:
```ts
export interface CustomerProfileRequest {
  // ...existing fields...
  business_activity?: string   // ← new
}
```

## Acceptance Criteria

1. `POST /compliance/{app_id}/risk-score` (no body, auto mode) with a customer whose `profession = "pilot"` returns `score_breakdown.profession = 5` and `matched_profession_category = "pilot"`.
2. `POST /compliance/{app_id}/risk-score` with a customer whose `profession = "Doctor"` (mixed case) returns `score_profession = 4`.
3. `POST /compliance/{app_id}/risk-score` with a customer whose `profession = "Chef"` (unrecognised) returns `score_profession = 3` (default) and `matched_profession_category = "unmatched"`.
4. Customer with `business_activity = "real_estate"` returns `score_business_activity = 5`.
5. Customer with `business_activity = null` (not provided) returns `score_business_activity = 3` (default) and `matched_business_category = "not_provided"`.
6. A pilot with no other risk flags (geography=1, product=1, channel=2, customer=1, txn=1, transparency=1, profession=5, business=3) reaches total=15 → `risk_classification = "high"` → `edd_required = true`.
7. The manual override path (`POST` with `RiskScoreRequest` body) is unaffected — manual scores bypass lookup entirely.
8. Frontend profile step shows `Profession` and `Business Activity` as dropdowns, not free-text.
9. CompliancePage risk score grid shows matched category labels under profession and business_activity score tiles when available.
10. Alembic migration successfully adds `business_activity` column to `customer_profiles` without data loss.
11. All existing risk score records in DB remain valid after migration (nullable column, no backfill required).

## Implementation Order

- [ ] 1. (backend) Create `app/core/risk_tables.py` with `PROFESSION_SCORES`, `BUSINESS_ACTIVITY_SCORES`, and `lookup_score()` helper
- [ ] 2. (backend) Add `business_activity: Optional[str]` to `CustomerProfileBase` in `app/models/onboarding.py`
- [ ] 3. (backend) Write Alembic migration `migrations/versions/0002_add_business_activity_to_customer_profiles.py`
- [ ] 4. (backend) Update `CustomerProfileRequest` in `app/api/v1/applications.py` to include optional `business_activity` field
- [ ] 5. (backend) Update `auto_calculate_scores()` in `app/crud/crud_compliance.py` — import lookup helpers, replace hardcoded stubs, return diagnostic keys
- [ ] 6. (backend) Update `create_risk_score()` in `app/crud/crud_compliance.py` — strip `_`-prefixed keys before DB insert
- [ ] 7. (backend) Update `calculate_risk_score` response in `app/api/v1/compliance.py` — include `matched_profession_category` and `matched_business_category`
- [ ] 8. (frontend) Create `ekyc-frontend/src/constants/riskCategories.ts` with canonical option lists
- [ ] 9. (frontend) Add `business_activity?: string` and `matched_profession_category?: string`, `matched_business_category?: string` to relevant interfaces in `types/api.ts`
- [ ] 10. (frontend) Replace free-text profession `<Input>` with `<Select>` and add `business_activity` `<Select>` in `OnboardingPage.tsx` profile step
- [ ] 11. (frontend) Same change in `AgentOnboardingPage.tsx` profile step
- [ ] 12. (frontend) Update `CompliancePage.tsx` score breakdown grid to show matched category sub-labels

## Testing Checklist

### Backend (Swagger UI or curl)

1. Run migration: `alembic upgrade head` — verify `customer_profiles` table has `business_activity` column
2. Create application → save profile with `profession: "Pilot"`, `business_activity: "real_estate"` → `POST /risk-score` (no body) → expect `score_profession=5`, `score_business_activity=5`, `total_score ≥ 15`, `edd_required=true`
3. Save profile with `profession: "Chef"` → calculate → expect `score_profession=3`, `matched_profession_category="unmatched"`
4. Save profile without profession or business_activity → calculate → expect both default to 3, matched categories = "not_provided"
5. Manual override: `POST /risk-score` with full `RiskScoreRequest` body setting `score_profession=1`, `score_business_activity=1` → verify those exact values stored; no lookup performed
6. `GET /risk-score` after auto-calculate — verify `matched_profession_category` and `matched_business_category` are NOT in the stored breakdown (they should only come from the calculate endpoint response, not the GET endpoint which reads from DB)

### Frontend

1. Navigate to `/onboarding` → pre-check → NID → biometrics → profile step → verify `Profession` is a dropdown with ≥14 options
2. Select "Pilot / Flight Attendant" → complete profile → submit application → agent calculates risk → verify `profession` score tile shows `5` with sub-label "pilot"
3. Leave `Business Activity` unset → risk score grid shows `business_activity = 3`, sub-label "not provided"
4. Select `Real Estate Developer` for business activity → risk score shows `5`
5. Verify `/agent/onboarding` profile step has identical profession + business activity dropdowns

### Edge Cases

- `profession = "PILOT"` (uppercase) → score 5 (case-insensitive)
- `profession = "Advocate"` → matches "advocate" key → score 4
- `profession = "Software Engineer"` → normalises to "software_engineer" → matches "software_engineer" in PROFESSION_SCORES (if added) or falls to default 3
- `business_activity = "other"` → no match in table → default score 3, category "unmatched"
- Profile not yet created when risk score is triggered → `profile = None` → both scores return default 3, no crash
