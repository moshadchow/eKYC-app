Generate a detailed feature specification for the eKYC onboarding platform and save it as a spec file.

**Argument received:** `$ARGUMENTS`

Parse the argument as `{step_number} {feature_name}` — e.g., `2 registration` means Step 2 and  feature "registration".

---

## Instructions

Follow these steps exactly:

### Step 1 — Read project context

Read the following files in full before doing anything else:
- `CLAUDE.md` — BFIU guidelines and regulatory context
- `app/api/v1/` — list all router files to understand implemented endpoints
- `ekyc-frontend/src/store/onboardingStore.ts` — current onboarding step machine
- `ekyc-frontend/src/AppRouter.tsx` — current routes

### Step 2 — Explore relevant existing code

Based on the feature name from the argument, search the codebase for related files. Use Grep to find:
- Any existing backend router, CRUD, or service files related to this feature
- Any existing frontend pages, components, or store slices related to this feature
- Any TODOs, stubs, or placeholder comments related to this feature

Read the relevant files in full (not just snippets).

### Step 3 — Map to BFIU pipeline stage

The eKYC onboarding pipeline has these stages in order:
1. **Pre-check** — Simplified vs Regular KYC decision, threshold enforcement
2. **Registration / Application** — Create KYC application, customer identity capture
3. **NID Verification** — NID number + DOB validation against EC database
4. **Biometric Verification** — Face-match (self check-in) or Fingerprint (assisted)
5. **Profile Capture** — Full customer profile, nominee, source of funds
6. **Compliance Screening** — UN sanctions, blacklist, adverse media, PEP/IP check
7. **Risk Grading** — 7-factor BFIU Annexure-1 risk scoring, EDD trigger
8. **EDD** — Enhanced Due Diligence document collection (high-risk only)
9. **Maker Review** — Maker agent reviews complete application
10. **Checker Approval** — 4-eyes principle, final approve/reject
11. **Account Activation** — Account creation, KYC next-review date, notifications
12. **Lifecycle Management** — Periodic refresh scheduling, overdue tracking

Use the step number from the argument to identify where this feature sits in the pipeline. Read the BFIU guidelines in CLAUDE.md for the specific regulatory requirements that apply to this step.

### Step 4 — Generate the spec file

Create a comprehensive spec and save it to `.claude/specs/step-{N}-{feature_name_snake_case}.md` where N is the step number and the feature name is lowercased with hyphens (e.g., `step-2-registration.md`).

The spec file must use this exact structure:

```
# Step {N} — {Feature Name} Spec

## Overview
One paragraph: what this feature does, which BFIU guideline section it implements, and how it fits into the overall onboarding pipeline (what comes before and after it).

## Regulatory Requirements
Bullet list of the specific BFIU 2026 mandates this feature must satisfy, with exact thresholds, limits, or rules copied from CLAUDE.md.

## Current State
What already exists in the codebase for this feature:
- Backend: list existing endpoints with their file paths and line numbers
- CRUD: list existing methods with file paths
- Frontend: list existing components/pages/store slices
- Note any stubs, mocks, or hardcoded placeholders

## Gaps — What Needs to Be Built
Separate sections for Backend and Frontend. For each gap:
- What is missing
- Why it's needed (regulatory or functional reason)
- File where it should be added

## Backend Specification

### New / Modified Endpoints
For each endpoint:
- Method + URL path
- Auth required (CurrentUser / CurrentAgent / CheckerAgent / public)
- Request body schema (field name, type, required/optional, validation rules)
- Response schema (use APIResponse[T] wrapper)
- Business logic summary (what the handler must do step by step)
- Which CRUD method it calls

### New / Modified CRUD Methods
For each method:
- Class name and method signature
- Parameters and return type
- DB operations (SELECT, INSERT, UPDATE) with table names
- Any business rules enforced at the CRUD layer

### Data Model Changes
Only include if new columns or tables are needed:
- Table name
- New column name, type, nullable, default, constraints
- Whether a new Alembic migration is required

## Frontend Specification

### onboardingStore Changes
- New state fields to add (name, type, initial value)
- New actions to add (name, what it does, what it sets)
- Step enum change if a new step is being added

### New / Modified Pages or Components
For each component:
- File path (existing or new)
- What it renders
- User interactions and what they trigger
- API calls made (which service function, on what event)
- State read from store / written to store
- Navigation: what happens on success, on error, on back

### API Service Additions
New functions to add to `ekyc-frontend/src/api/services.ts`:
- Function name
- HTTP method + endpoint
- Request type
- Response type

### TypeScript Types
New or modified types to add to the types file:
- Type/interface name
- Fields

## Acceptance Criteria
Numbered list of testable conditions. Each criterion must be specific and verifiable:
- Backend: what HTTP response is expected for a given input
- Frontend: what the user sees / can interact with
- BFIU compliance: which regulatory rule is satisfied

## Implementation Order
Ordered list of implementation tasks. Each task on one line, prefixed with a checkbox:
- [ ] 1. (backend or frontend label) — exact description of task and file to modify

Order tasks so that each one can be completed and tested before the next begins. Backend tasks that other tasks depend on come first.

## Testing Checklist
How to verify the feature end-to-end after implementation:
- Backend: curl or Swagger UI test steps
- Frontend: browser walkthrough steps
- Edge cases to verify (boundary values, error paths, retry limits)
```

### Step 5 — Save and confirm

After writing the file, print a one-line confirmation:
```
Spec saved → .claude/specs/step-{N}-{feature_name}.md  ({line_count} lines)
```
