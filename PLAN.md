# HouseScope implementation specification

Source: https://chatgpt.com/share/6ae45e39-bc58-83e8-95dd-9d7d7eb5d4f0

## Purpose

Build an independent local prototype connecting home inspection reports to evidence-backed repair and renovation planning. Demonstrate alignment with House IQ's product vision and invite technical feedback. Do not claim affiliation, reproduce their branding, or assume gaps in their private product. Outreach is a later deliverable, not authorization to send messages.

## Core journey

Real US inspection PDF → page-aware parsing → structured findings → evidence checks → repair priorities → preliminary renovation plan → interactive assessment.

## Stack

- Next.js, TypeScript, Tailwind and shadcn/ui frontend.
- Python FastAPI, PyMuPDF and Pydantic backend.
- SQLite and local files for persistence.
- OpenAI API for structured extraction; verify available model IDs and current pricing before choosing a model. Model names and prices in the source conversation are unverified.
- No cloud deployment, vector database or complex agent framework needed for MVP.

## Implementation order

1. Establish frontend/backend structure and local configuration.
2. Obtain the primary public sample report; inspect extraction quality and manually label findings.
3. Validate uploads, hash documents, preserve page text, detect scans and chunk text.
4. Extract typed findings: system, location, title, description, source page and quotation, inspector recommendation and reported severity.
5. Validate page existence and normalized quotation matches; deduplicate findings and flag unsupported or ambiguous results. Quotation matching alone does not establish semantic support.
6. Build upload, processing status, findings filters and evidence detail views.
7. Add deterministic repair priorities, illustrative cost scenarios, related-work grouping, buyer questions and contractor scope.
8. Add summary export, evaluation results, usage reporting, README and a short demo.

## Integrity requirements

- Separate inspector statements from generated interpretations and priorities.
- Do not treat boilerplate or inspection limitations as defects.
- Flag image-only pages for review or selective vision processing; never silently omit them.
- Display no calibrated confidence score without calibration evidence.
- Costs come from a curated deterministic reference dataset with assumptions, source/date and unknown quantities visible. They are preliminary scenarios, not contractor quotes.
- Cache successful analysis; dashboard refresh and plan generation must not repeat extraction.
- Keep API keys server-side and out of source control.

## Budget

The user will supply an existing API key in the root .env. Use gpt-6-luna and make no paid calls during implementation. Configure a project experimentation ceiling of $5 with conservative call reservations and usage accounting. User constraint: total usage must remain at most $5; keep testing minimal. Record model, tokens, estimated cost, duration and failures. Verify credentials through the supported setup workflow before live API work.

## API outline

- POST /api/reports
- POST /api/reports/{id}/analyze
- GET /api/reports/{id}/status
- GET /api/reports/{id}/findings
- GET /api/reports/{id}/pages/{page}
- GET /api/reports/{id}/renovation-plan
- GET /api/reports/{id}/export

## Sample report candidates

These links and the source conversation's page/finding counts require verification:

- Primary Kentucky: https://peirsoninspections.com/sample-report
- Georgia: https://www.conleyhomeinspections.com/wp-content/uploads/2022/01/Sample-Inspection-Report.pdf
- Florida cost comparison: https://modernbuildinginspections.com/sample-report/
- Long report: https://www.patriotinspect.com/sample-report/

Retain attribution and inspect reuse terms. Public availability alone does not permit redistribution; keep downloaded originals out of a public repository unless permission allows it.

## Acceptance targets

- Complete one real report and the upload-to-assessment journey.
- Evaluate against manually labeled findings: target ≥90% precision and recall, ≥95% citation correctness, and zero unsupported critical findings in the primary evaluation.
- Report actual measurements rather than presenting targets as achieved.
- Repeat analysis returns cached results without new model calls.
- Record per-report usage and cost; reject work exceeding configured limits.

## Stretch scope

Selected-photo analysis, model comparisons, multiple-report comparison and richer project history follow the reliable core journey.

## Delivered engineering upgrade

Implemented versioned layout/word-coordinate indexing, reference continuation binding, separate observation/decision contracts, conservative multi-source consolidation, mechanical support gates, versioned priorities, shared repair scopes and acyclic dependencies, review correction with append-only revisions, one-to-one reference evaluation, durable run/stage traces and free local replay of saved observations.

Eight focused offline checks and a production frontend build pass. One live Kentucky development baseline cost $0.0102074; before/after local postprocessing results and limitations are recorded in docs/BASELINE.md. This single agent-labeled development report is not held-out validation.
