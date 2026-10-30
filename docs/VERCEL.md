# Vercel Services configuration

Import the repository root (`./`) as one **Services** project. The root `vercel.json` defines the approved topology: a public frontend and an internal backend. No cloud deployment has been created.

## Services and public surface

- `frontend`: `frontend/`, Next.js. Public catch-all `/(.*)`.
- `backend`: repository root `.`, FastAPI entrypoint `backend.main:app`. Internal only, with no top-level public rewrite.
- `frontend` declares a service binding targeting `backend`, injected as `BACKEND_URL`. Do not set this variable yourself in Vercel project settings.

The backend root intentionally differs from the auto-detected `backend/`: the Python code uses package-relative imports and loads reference annotations from repository-level `fixtures/annotations/`. Root `requirements.txt` mirrors the backend requirements because the Services local runner parses a flat dependency file; keep the two lists synchronized. The function configuration includes the cost catalog and annotations explicitly.

## Request flow

`browser → /api/reports → frontend Node route function → BACKEND_URL + api/reports → FastAPI`

All existing browser API, PDF image and export URLs remain same-origin `/api/*`. The frontend optional catch-all route handler reads the binding at request time, forwards the method, query, streaming body and useful headers, and returns the upstream response. It handles uploads, binary pages and exports without buffering full payloads. Backend routes retain their existing `/api/*` prefix. There is no framework mount prefix and no `/api/api` public URL.

The binding is never read in `next.config.ts`, a build, client-side code or middleware. Building the frontend does not require `BACKEND_URL`. Its local Python fallback is used only outside Vercel. If Vercel supplies no runtime binding, the API function returns a configuration error rather than calling localhost.

The backend does not call the frontend, so no reverse binding is declared. Public exposure of the backend is not necessary for browser requests because the frontend route function is their gateway. A binding is connectivity, not application authorization; this change does not introduce user accounts or private workspaces.

## Local verification

```sh
python3.12 -m venv .vercel/dev-venv
. .vercel/dev-venv/bin/activate
python -m pip install -r requirements.txt
HOUSESCOPE_DATA_DIR="$PWD/.vercel/local-data" npx vercel dev --local --listen 3100
```

Python 3.12 is pinned in `.python-version`. The backend local `devCommand` uses Uvicorn with this interpreter; it does not depend on a globally installed Python 3.9 or replace the existing `.venv`. The directory above is isolated local test data, not a hosted storage recommendation.

`vercel dev` is also supported when the project is linked. The local command uses the checked-in service definitions and generated bindings. Keep any local `HOUSESCOPE_DATA_DIR` override outside source control. Do not exercise `/analyze` for routing smoke tests; health, source routing and a small synthetic PDF upload are sufficient without inference cost.

For the existing two-process workflow, `bash scripts/start.sh` continues to work on port 3000 through the runtime gateway's local fallback.

## Supabase setup and environment variables

Fill the ignored repository-root `.env` with these server settings, then run:

```sh
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/setup_supabase.py
```

Database TLS verifies the pooler hostname using the bundled public Supabase CA certificate (`backend/supabase-ca.crt`, from Supabase’s HTTPS download endpoint).

The setup script creates the private `housescope` Postgres schema and private Storage bucket. It is idempotent, enables RLS without browser policies, and carries the existing local spending commitment into the hosted ledger once. It does not import local reports. You may also apply `supabase/migrations/001_housescope.sql` in the SQL editor, but use the script to configure Storage and retain the spending carryover.

Set these in Vercel project Environment Variables for Production (and Preview if needed), then redeploy:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Supabase Connect → Transaction pooler URI, including database password; generally port 6543. URL-encode special password characters. |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SECRET_KEY` | Server secret (`sb_secret_…`) or legacy service-role key; never a publishable/anon key |
| `OPENAI_API_KEY` | Existing server OpenAI API key |
| `PROJECT_BUDGET_USD` | `5`, the hard maximum for this shared project ledger |
| `SUPABASE_STORAGE_BUCKET` | `housescope` (optional; default) |

`BACKEND_URL` comes from the service binding; do not create it manually. Neither `NEXT_PUBLIC_SUPABASE_URL` nor a publishable Supabase key is needed for this server-managed integration. Never use a `NEXT_PUBLIC_` prefix on database URLs, server keys or session secrets.

Local `scripts/start.sh` continues using SQLite. To exercise Supabase locally, set `HOUSESCOPE_STORAGE=supabase` in the root `.env` and also in the frontend process environment. On Vercel both services select Supabase automatically. Do not set `HOUSESCOPE_DATA_DIR=/tmp`; there is no hosted SQLite fallback.

## Hosted request flow

1. The public Next.js API gateway creates a signed, HTTP-only anonymous workspace cookie and authenticates it to the internal backend. Report IDs and listings are scoped to that workspace. Keep `SUPABASE_SECRET_KEY` shared with both services; optionally set a stable `HOUSESCOPE_SESSION_SECRET` to avoid invalidating cookies when rotating the Supabase key.
2. Browser PDFs upload directly to a narrowly scoped signed Storage URL, avoiding the function request body limit. The backend validates the PDF and stores its original and indexed layout in the private bucket. The same 25 MB / 150-page limits apply.
3. Analysis reserves spending in Postgres under a transaction advisory lock, then processes at most one new model section per request. Successful sections are saved in Storage. The open browser advances to the next section; it is not a background worker.
4. A durable 360-second report lease prevents simultaneous extraction calls from multiple tabs/instances. Interrupted calls keep their spending reservation. Expired leases require explicit Resume; there are no automatic model retries. Closing the browser can pause progress; reopening the report continues saved sections. A Vercel plan must support the configured 300-second maximum duration.
5. Findings, reviews, repair budgets and stage events persist in Postgres. PDFs, layouts and model checkpoints persist in Storage. Local paths serve as object keys in hosted mode; no local disk is authoritative.
6. Original PDFs use short-lived signed downloads. The public Kentucky sample is fetched only from its fixed source and checked against the labeled document hash.

This is an anonymous demo workspace, not a user account system. Clearing browser cookies loses access to that workspace; the data remains in Supabase until removed. Anyone with the public app URL can consume the shared remaining analysis budget. Incoming upload objects remain private and can be periodically removed from the bucket's `incoming/` prefix after imports; do not delete indexed originals or checkpoints. Set a Supabase retention policy appropriate to your demo.

## Verification

The 12 offline tests and frontend production build pass. A live synthetic PDF roundtrip verifies Postgres persistence, signed upload/download, workspace isolation, page rendering, cost-budget access, bounded extraction, remote checkpoint resume and policy replay. Model responses were mocked; no paid inference was performed. The deployment itself is performed by the repository owner. A successful database setup is required before hosted analysis; the setup script reports connection failures without printing credentials.

Official references: [Vercel Services](https://vercel.com/docs/services), [service bindings](https://vercel.com/docs/services/bindings), [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres).
