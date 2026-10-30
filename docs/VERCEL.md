# Deploying the frontend on Vercel

The repository contains two applications. Importing the Next.js frontend does not also start the Python backend.

## Vercel project settings

- Repository: `Safiurrehmann/houseScope`
- Root Directory: `frontend`
- Framework Preset: Next.js
- Install Command: `npm ci` (or the default)
- Build Command: `npm run build`
- Output Directory: default
- Environment variable: `BACKEND_URL=https://your-hosted-python-api.example.com`

Use only the backend origin, without `/api`, credentials, query parameters or a trailing path. Redeploy after changing this variable because rewrites are resolved during the build. Requests to `/api/*` are forwarded to that backend. Local development still defaults to `http://127.0.0.1:8000`.

Do not put `OPENAI_API_KEY` in a browser-visible variable. For this split setup, configure it only on the Python backend host. No secret is needed by the frontend.

## What the backend still needs

The current FastAPI backend requires:

- A continuously running Python service for the existing background-task workflow.
- Persistent writable storage for SQLite, uploaded PDFs, layouts and extraction checkpoints.
- The OpenAI key and an appropriately configured remaining project budget.
- Access controls before real private inspection reports are accepted into the current shared workspace.
- Sample retrieval or explicitly provisioned sample files; original downloaded PDFs and the local database are intentionally absent from Git.

The repository is not an all-in-one Vercel deployment. Vercel supports FastAPI, but adapting this backend to serverless execution also requires replacing local persistent storage and reviewing how long-running analysis jobs execute and recover. Simply routing FastAPI on Vercel or moving SQLite to `/tmp` does not preserve the global spending ledger, reports or caches across instances.

For the smallest change, deploy this frontend to Vercel and run the existing backend on a Python host with persistent storage. For a Vercel-only design, migrate durable records and files to external database/object storage and adapt the analysis lifecycle first.

Official references:

- [Vercel FastAPI support](https://vercel.com/docs/frameworks/backend/fastapi)
- [Persistent versus temporary Python API data](https://vercel.com/i/where-to-host-python-api)

No hosted deployment has been created by the agent.
